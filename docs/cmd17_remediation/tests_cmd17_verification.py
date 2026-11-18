#!/usr/bin/env python3
"""
BITDEX COMMAND 17 — COMPREHENSIVE OFFLINE UNIT, CRASH-INJECTION, RESTART & REAL-SERVICE INTEGRATION TEST SUITE
Strictly offline: zero broker network calls, zero live/demo order placements, isolated SQLite DB & temp state files.
Tests against ACTUAL ExnessTraderAPIClient.submit_order() operation-only payloads (from operator_9h_experiment.log)
reconciled via read-only broker snapshot/order-history/deal-history records, plus all 5 Command 16 findings.
"""
import asyncio
import hashlib
import json
import multiprocessing
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, "/opt/bitdex-research-v2")
sys.path.insert(0, "/opt/tauric-platform-staging/backend")

TEST_TMP_DIR = tempfile.mkdtemp(prefix="bitdex_cmd17_test_")
TEST_DB_PATH = os.path.join(TEST_TMP_DIR, "test_tauric_saas.db")
os.environ["SAAS_DB_PATH"] = TEST_DB_PATH

import run_operator_experiment_runner as runner
import app.services.trade_memory_service as tms_mod
from app.services.trade_memory_service import TradeMemoryService
from app.services.brokers.shared_risk_manager import SharedCentralRiskManager, PostFillRiskBreachGuard
from app.services.brokers.central_risk_gate import REAL_TRADING_PERMANENTLY_LOCKED
from strategies.eurusd_structure_a2 import EurUsdStructureA2

tms_mod.get_db_path = lambda: TEST_DB_PATH
TradeMemoryService.init_db()

runner.OperatorExperimentSupervisor._leg_state_path = staticmethod(
    lambda account_id: os.path.join(TEST_TMP_DIR, f"a2_leg_state_{account_id}.json")
)
runner.OperatorExperimentSupervisor._leg_lock_path = staticmethod(
    lambda account_id: os.path.join(TEST_TMP_DIR, f"a2_leg_state_{account_id}.lock")
)
runner.OperatorExperimentSupervisor._incident_path = staticmethod(
    lambda account_id: os.path.join(TEST_TMP_DIR, f"a2_post_fill_incidents_{account_id}.jsonl")
)


def _make_closed_candles(now_dt: datetime):
    d1_bars = [
        {
            "timestamp": (now_dt - timedelta(days=100 - i)).strftime("%Y-%m-%dT00:00:00Z"),
            "bid_open": 1.08000, "bid_high": 1.08500, "bid_low": 1.07500, "bid_close": 1.08100,
            "ask_open": 1.08010, "ask_high": 1.08510, "ask_low": 1.07510, "ask_close": 1.08110,
        }
        for i in range(80)
    ]
    h4_bars = [
        {
            "timestamp": (now_dt - timedelta(hours=4 * (60 - i))).strftime("%Y-%m-%dT%H:00:00Z"),
            "bid_open": 1.08000, "bid_high": 1.08500, "bid_low": 1.07500, "bid_close": 1.08100,
            "ask_open": 1.08010, "ask_high": 1.08510, "ask_low": 1.07510, "ask_close": 1.08110,
        }
        for i in range(50)
    ]
    h1_bars = [
        {
            "timestamp": (now_dt - timedelta(hours=300 - i)).strftime("%Y-%m-%dT%H:00:00Z"),
            "bid_open": 1.08000, "bid_high": 1.08500, "bid_low": 1.07500, "bid_close": 1.08100,
            "ask_open": 1.08010, "ask_high": 1.08510, "ask_low": 1.07510, "ask_close": 1.08110,
        }
        for i in range(280)
    ]
    return d1_bars, h4_bars, h1_bars


def _mp_reserve_worker(args):
    acc, leg_id, tmp_dir = args
    runner.OperatorExperimentSupervisor._leg_state_path = staticmethod(
        lambda account_id: os.path.join(tmp_dir, f"a2_leg_state_{account_id}.json")
    )
    runner.OperatorExperimentSupervisor._leg_lock_path = staticmethod(
        lambda account_id: os.path.join(tmp_dir, f"a2_leg_state_{account_id}.lock")
    )
    runner.OperatorExperimentSupervisor._incident_path = staticmethod(
        lambda account_id: os.path.join(tmp_dir, f"a2_post_fill_incidents_{account_id}.jsonl")
    )
    s = runner.OperatorExperimentSupervisor()
    ok, token = s.reserve_a2_leg_pending(acc, leg_id, {"worker": os.getpid()})
    return ok, token


async def run_all_tests():
    results = {
        "fix1_order_submitted_crash_safety": {},
        "fix2_broker_history_reconciliation": {},
        "fix3_actual_exness_terminal_reconciliation": {},
        "fix4_independent_deal_ledger_idempotency": {},
        "fix5_durable_post_fill_lock_across_restart": {},
        "regression_and_safety": {},
    }
    now_dt = datetime(2026, 11, 18, 12, 0, 0, tzinfo=timezone.utc)
    now_iso = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    d1_bars, h4_bars, h1_bars = _make_closed_candles(now_dt)

    def _mock_adapter(quote_val=None, quote_exc=None, open_pos=None, order_hist=None, deal_hist=None, submit_res=None, submit_exc=None):
        ad = MagicMock()
        async def _hc(sym, timeframe="H1", count=100):
            if timeframe == "D1": return d1_bars
            if timeframe == "H4": return h4_bars
            return h1_bars
        ad.get_historical_candles = AsyncMock(side_effect=_hc)
        if quote_exc:
            ad.get_live_quote = AsyncMock(side_effect=quote_exc)
        else:
            ad.get_live_quote = AsyncMock(return_value=quote_val or {"bid": 1.08100, "ask": 1.08110})
        ad.get_open_positions = AsyncMock(return_value=open_pos if open_pos is not None else [])
        ad.get_order_history = AsyncMock(return_value=order_hist if order_hist is not None else [])
        ad.get_trade_history = AsyncMock(return_value=deal_hist if deal_hist is not None else [])
        ad.client = MagicMock()
        ad.client.get_trading_snapshot = AsyncMock(return_value={"positions": open_pos or [], "orders": []})
        ad.client.get_trade_history = AsyncMock(return_value=deal_hist if deal_hist is not None else [])
        if submit_exc:
            ad.place_market_order = AsyncMock(side_effect=submit_exc)
        else:
            ad.place_market_order = AsyncMock(return_value=submit_res or {})
        return ad

    def _fake_sig_leg1(self_a2, bars, idx):
        leg = "BUY:1.07500:1.08500"
        if self_a2.last_leg_id == leg:
            return None
        self_a2.last_leg_id = leg
        return {"direction": "BUY", "sl": 1.07800, "tp": 1.08850}

    def _fake_sig_leg2(self_a2, bars, idx):
        leg = "BUY:1.07900:1.08900"
        if self_a2.last_leg_id == leg:
            return None
        self_a2.last_leg_id = leg
        return {"direction": "BUY", "sl": 1.08000, "tp": 1.09050}

    # =========================================================================
    # FIX 1: Persist order_submitted = True BEFORE place_market_order()
    # =========================================================================
    acc_f1 = "17000694512_FIX1"
    sup_f1 = runner.OperatorExperimentSupervisor()

    # F1.1: Pre-submission quote/spread/sizing/preflight rejections still do NOT consume leg
    with patch.object(EurUsdStructureA2, "generate_signal", _fake_sig_leg1):
        s_qfail = await sup_f1.scan_market_opportunities(None, _mock_adapter(quote_exc=RuntimeError("timeout")), now_utc=now_dt, account_id=acc_f1)
        s_spfail = await sup_f1.scan_market_opportunities(None, _mock_adapter({"bid": 1.081, "ask": 1.082}), now_utc=now_dt, account_id=acc_f1)
        s_ok = await sup_f1.scan_market_opportunities(None, _mock_adapter(), now_utc=now_dt, account_id=acc_f1)
    with patch.object(SharedCentralRiskManager, "preflight_check", AsyncMock(return_value=(False, "MAX_POS", {}))):
        pf_rej = await sup_f1.execute_signal_Cycle(None, _mock_adapter(), s_ok[0], now_iso, account_id=acc_f1)
    with patch.object(EurUsdStructureA2, "generate_signal", _fake_sig_leg1):
        s_retry_after_pf = await sup_f1.scan_market_opportunities(None, _mock_adapter(), now_utc=now_dt, account_id=acc_f1)
    results["fix1_order_submitted_crash_safety"]["F1_1_pre_submission_rejections_do_not_consume_leg"] = (
        len(s_qfail) == 0 and len(s_spfail) == 0 and pf_rej["status"] == "PREFLIGHT_REJECTED" and len(s_retry_after_pf) == 1
    )

    # F1.2: Verify order_submitted=True is persisted on disk BEFORE adapter.place_market_order executes,
    # and simulate a process crash (SystemExit / BaseException) INSIDE place_market_order before it returns!
    observed_disk_order_submitted = []
    async def _crash_inside_place_order(**kwargs):
        _, doc_on_disk = runner.OperatorExperimentSupervisor._read_leg_state_doc_unlocked(acc_f1)
        pend = (doc_on_disk or {}).get("pending_reservation") or {}
        observed_disk_order_submitted.append(bool((pend.get("signal_meta") or {}).get("order_submitted")))
        raise BaseException("SIMULATED_HARD_PROCESS_CRASH_DURING_HTTP_POST")

    ad_crash = _mock_adapter()
    ad_crash.place_market_order = AsyncMock(side_effect=_crash_inside_place_order)
    crashed = False
    with patch.object(SharedCentralRiskManager, "preflight_check", AsyncMock(return_value=(True, "OK", {}))):
        try:
            await sup_f1.execute_signal_Cycle(None, ad_crash, s_retry_after_pf[0], now_iso, account_id=acc_f1)
        except BaseException:
            crashed = True

    results["fix1_order_submitted_crash_safety"]["F1_2_order_submitted_true_on_disk_before_broker_call"] = (
        crashed is True and observed_disk_order_submitted == [True]
    )

    # F1.3: Restart after mid-submission crash (even when open_positions is empty) MUST fail closed and block duplicate submission!
    sup_f1_restarted = runner.OperatorExperimentSupervisor()
    with patch.object(EurUsdStructureA2, "generate_signal", _fake_sig_leg1):
        s_after_crash = await sup_f1_restarted.scan_market_opportunities(None, _mock_adapter(), now_utc=now_dt, account_id=acc_f1)
    results["fix1_order_submitted_crash_safety"]["F1_3_crash_during_submission_blocks_duplicate_on_restart"] = (
        len(s_after_crash) == 0
        and sup_f1_restarted.post_fill_guard.new_entries_disabled is True
        and any(i["incident_code"] == "PENDING_SUBMITTED_ORDER_UNRECONCILABLE" for i in sup_f1_restarted.critical_incidents)
    )

    # =========================================================================
    # FIX 2: Read-Only Exness Snapshot, Order-History & Deal-History Reconciliation
    # =========================================================================
    # F2.1: Crash occurred after broker fill & position already closed via SL/TP before restart (open_positions=[], deal_history has EURUSD deal)
    acc_f2a = "17000694512_FIX2A"
    sup_f2a = runner.OperatorExperimentSupervisor()
    await sup_f2a.reconcile_or_initialize_a2_leg_state(_mock_adapter(), acc_f2a)
    sup_f2a.reserve_a2_leg_pending(acc_f2a, "BUY:1.07500:1.08500", {"direction": "BUY", "order_submitted": False})

    sup_f2a_restart = runner.OperatorExperimentSupervisor()
    ad_closed_deal = _mock_adapter(
        open_pos=[],
        order_hist=[{"order": {"order_id": "154999001", "position_id": "75999001", "instrument": "EURUSD", "side": "buy", "state": "filled"}}],
        deal_hist=[{"deal": {"deal_id": "151999001", "order_id": "154999001", "position_id": "75999001", "instrument": "EURUSD", "entry": "IN", "price": 1.08110, "volume": 0.03}}],
    )
    with patch.object(EurUsdStructureA2, "generate_signal", _fake_sig_leg1):
        s_f2a = await sup_f2a_restart.scan_market_opportunities(None, ad_closed_deal, now_utc=now_dt, account_id=acc_f2a)
    results["fix2_broker_history_reconciliation"]["F2_1_closed_position_in_deal_history_detected_on_restart"] = (
        len(s_f2a) == 0
        and sup_f2a_restart.post_fill_guard.new_entries_disabled is True
        and any(i["incident_code"] == "PENDING_RESERVATION_WITH_UNTRACKED_BROKER_HISTORY" for i in sup_f2a_restart.critical_incidents)
    )

    # F2.2: Missing state file + untracked EURUSD order/deal in broker history -> fails closed (never treats as clean history)
    acc_f2b = "17000694512_FIX2B"
    sup_f2b = runner.OperatorExperimentSupervisor()
    with patch.object(EurUsdStructureA2, "generate_signal", _fake_sig_leg1):
        s_f2b = await sup_f2b.scan_market_opportunities(None, ad_closed_deal, now_utc=now_dt, account_id=acc_f2b)
    results["fix2_broker_history_reconciliation"]["F2_2_missing_state_with_untracked_broker_history_fails_closed"] = (
        len(s_f2b) == 0
        and sup_f2b.post_fill_guard.new_entries_disabled is True
        and any(i["incident_code"] == "MISSING_STATE_UNRECONCILABLE_BROKER_HISTORY" for i in sup_f2b.critical_incidents)
    )

    # =========================================================================
    # FIX 3: Reconcile ACTUAL ExnessTraderAPIClient.submit_order() Operation Response
    # =========================================================================
    acc_f3 = "17000694512"
    sup_f3 = runner.OperatorExperimentSupervisor()

    # Exact structure from operator_9h_experiment.log line 130 (no position_id/order_id/deal_id/fill_price inside operation!)
    actual_live_submit_order_return = {
        "status": "FILLED",
        "operation_id": "379428714124935168",
        "ack": {
            "operation_id": "379428714124935168",
            "status": "accepted",
            "client_request_id": "bitdex-ord-fa2d2d91b0f04d61",
        },
        "operation": {
            "operation_id": "379428714124935168",
            "status": "confirmed",
            "request_type": "open_position",
            "client_request_id": "bitdex-ord-fa2d2d91b0f04d61",
            "created_at": "2026-11-18T11:59:59.100000+00:00",
            "updated_at": "2026-11-18T11:59:59.250000+00:00",
        },
        "payload": {
            "instrument": "EURUSD",
            "side": "buy",
            "volume": "0.03",
            "comment": "OPEXP_LONG",
            "stop_loss_price": "1.07800",
            "take_profit_price": "1.08850",
        },
    }

    # F3.1: Without broker snapshot/history match, un-reconciled operation response MUST fail closed as AMBIGUOUS (never fabricated)
    norm_unreconciled = sup_f3.normalize_exness_order_response(actual_live_submit_order_return, "EURUSD", "BUY", acc_f3, 1.08100)
    results["fix3_actual_exness_terminal_reconciliation"]["F3_1_unreconciled_operation_response_never_fabricated"] = (
        norm_unreconciled["normalized_status"] == "AMBIGUOUS"
        and norm_unreconciled["error_code"] == "MISSING_BROKER_TICKET"
    )

    # F3.2: End-to-end execute_signal_Cycle with actual ExnessTraderAPIClient.submit_order() response + read-only broker snapshot/order/deal records
    ad_f3 = _mock_adapter(
        open_pos=[],  # empty during scan
        order_hist=[],
        deal_hist=[],
        submit_res=actual_live_submit_order_return,
    )
    with patch.object(EurUsdStructureA2, "generate_signal", _fake_sig_leg1):
        s_f3 = await sup_f3.scan_market_opportunities(None, ad_f3, now_utc=now_dt, account_id=acc_f3)

    # After place_market_order, broker snapshot & history reflect the newly opened position, order, and deal
    ad_f3.get_open_positions = AsyncMock(return_value=[{
        "ticket": "75087127",
        "position_id": "75087127",
        "protective_order_id": "154088638",
        "symbol": "EURUSD",
        "instrument": "EURUSD",
        "side": "BUY",
        "volume": 0.03,
        "open_price": 1.08112,
        "entry_price": 1.08112,
        "sl": 1.07800,
        "tp": 1.08850,
    }])
    ad_f3.get_order_history = AsyncMock(return_value=[
        {"order": {"order_id": "154088637", "position_id": "75087127", "instrument": "EURUSD", "side": "buy", "order_type": "market", "state": "filled", "client_request_id": "bitdex-ord-fa2d2d91b0f04d61"}},
        {"order": {"order_id": "154088638", "position_id": "75087127", "instrument": "EURUSD", "side": "sell", "order_type": "sltp", "state": "placed"}},
    ])
    ad_f3.get_trade_history = AsyncMock(return_value=[
        {"deal": {"deal_id": "151888637", "order_id": "154088637", "position_id": "75087127", "instrument": "EURUSD", "side": "buy", "entry": "IN", "price": 1.08112, "volume": 0.03}},
    ])

    with patch.object(SharedCentralRiskManager, "preflight_check", AsyncMock(return_value=(True, "OK", {}))):
        exec_f3 = await sup_f3.execute_signal_Cycle(None, ad_f3, s_f3[0], now_iso, account_id=acc_f3)

    tm_f3 = TradeMemoryService.get_trade_history(account_id=acc_f3, track="LT_STRUCTURE_EURUSD_A2", limit=10)
    results["fix3_actual_exness_terminal_reconciliation"]["F3_2_actual_terminal_operation_reconciled_with_genuine_ids"] = (
        exec_f3["status"] == "CONFIRMED_AND_PROTECTED"
        and exec_f3["ticket"] == "75087127"
        and exec_f3["order_id"] == "154088637"
        and exec_f3["deal_id"] == "151888637"
        and exec_f3["operation_id"] == "379428714124935168"
        and exec_f3["fill_price"] == 1.08112
        and exec_f3["fill_volume"] == 0.03
        and len(tm_f3) == 1
        and tm_f3[0]["broker_ticket"] == "75087127"
        and tm_f3[0]["order_id"] == "154088637"
        and tm_f3[0]["deal_id"] == "151888637"
    )

    # F3.3: Restart after F3.2 with open position still active on broker -> state is cleanly reconciled and leg is not repeated
    sup_f3_restart = runner.OperatorExperimentSupervisor()
    with patch.object(EurUsdStructureA2, "generate_signal", _fake_sig_leg1):
        s_f3_repeat = await sup_f3_restart.scan_market_opportunities(None, ad_f3, now_utc=now_dt, account_id=acc_f3)
    results["fix3_actual_exness_terminal_reconciliation"]["F3_3_restart_with_reconciled_open_position_preserves_dedup"] = (
        len(s_f3_repeat) == 0 and sup_f3_restart.post_fill_guard.new_entries_disabled is False
    )

    # =========================================================================
    # FIX 4: Independent Deal Ledger & Cross-Restart Sub-Deal Idempotency
    # =========================================================================
    acc_f4 = "17000694512_FIX4"
    sup_f4 = runner.OperatorExperimentSupervisor()
    sig_f4 = {
        "strategy": "LT_STRUCTURE_EURUSD_A2", "engine_type": "LONG_TERM", "strategy_version": "2.0",
        "symbol": "EURUSD", "side": "BUY", "volume": 0.03, "entry_price": 1.08100,
        "sl_price": 1.07800, "tp_price": 1.08850, "leg_id": "BUY:1.07600:1.08600", "reason": "multi-deal test",
    }
    multi_deal_mt5 = {
        "status": "FILLED",
        "http_status": 200,
        "response": {
            "status": "FILLED",
            "account_id": acc_f4,
            "symbol": "EURUSDm",
            "side": "BUY",
            "ticket": "88400001",
            "order_id": "199400001",
            "requested_volume": 0.03,
            "deals": [
                {"deal_id": "DEAL-401", "position_id": "88400001", "order_id": "199400001", "price": 1.08100, "volume": 0.01},
                {"deal_id": "DEAL-402", "position_id": "88400001", "order_id": "199400001", "price": 1.08130, "volume": 0.01},
            ],
            "time_utc": now_iso,
        },
    }
    res_f4_1 = sup_f4.process_broker_fill_response(multi_deal_mt5, sig_f4, 1.07800, 1.08850, now_iso, acc_f4)

    # Verify individual deal rows exist in a2_deal_ledger
    conn_check = TradeMemoryService.get_connection()
    dl_rows = conn_check.execute("SELECT deal_id, volume_lots, fill_price FROM a2_deal_ledger WHERE account_id = ? ORDER BY deal_id", (acc_f4,)).fetchall()
    conn_check.close()
    results["fix4_independent_deal_ledger_idempotency"]["F4_1_individual_deals_persisted_in_ledger"] = (
        res_f4_1["status"] == "CONFIRMED_PARTIAL_FILL_AND_PROTECTED"
        and len(dl_rows) == 2
        and dl_rows[0]["deal_id"] == "DEAL-401"
        and dl_rows[1]["deal_id"] == "DEAL-402"
    )

    # Simulate a brand-new process instance (restart) where in-memory _reconciled_deal_ids is empty,
    # and replay individual sub-deal "DEAL-401" even under a different outer ticket/order_id:
    sup_f4_restarted = runner.OperatorExperimentSupervisor()
    subdeal_replay_mt5 = {
        "status": "FILLED",
        "http_status": 200,
        "response": {
            "status": "FILLED",
            "account_id": acc_f4,
            "symbol": "EURUSDm",
            "side": "BUY",
            "ticket": "88400099",
            "order_id": "199400099",
            "deal_id": "DEAL-401",
            "requested_volume": 0.01,
            "filled_volume": 0.01,
            "fill_price": 1.08100,
            "time_utc": now_iso,
        },
    }
    res_f4_replay = sup_f4_restarted.process_broker_fill_response(subdeal_replay_mt5, sig_f4, 1.07800, 1.08850, now_iso, acc_f4)
    tm_f4_rows = TradeMemoryService.get_trade_history(account_id=acc_f4, track="LT_STRUCTURE_EURUSD_A2", limit=10)
    results["fix4_independent_deal_ledger_idempotency"]["F4_2_cross_restart_subdeal_replay_blocked"] = (
        res_f4_replay["status"] == "DUPLICATE_FILL_IGNORED"
        and res_f4_replay["recorded"] is False
        and len(tm_f4_rows) == 1
    )

    # =========================================================================
    # FIX 5: Durable Post-Fill Safety Incidents & Entry-Disable Across Restart
    # =========================================================================
    # F5.1: Post-fill risk breach (> $10.00) disables new entries AND persists across process restart
    acc_f5a = "17000694512_FIX5A"
    sup_f5a = runner.OperatorExperimentSupervisor()
    breach_mt5 = {
        "status": "FILLED",
        "http_status": 200,
        "response": {
            "status": "FILLED",
            "account_id": acc_f5a,
            "symbol": "EURUSDm",
            "side": "BUY",
            "ticket": "88500001",
            "order_id": "199500001",
            "deal_id": "DEAL-501",
            "requested_volume": 0.04,
            "filled_volume": 0.04,
            "fill_price": 1.08200,  # SL 1.07800 -> 40 pips * 0.04 lots = $16.00 > $10.00 budget!
            "time_utc": now_iso,
        },
    }
    res_f5a = sup_f5a.process_broker_fill_response(breach_mt5, sig_f4, 1.07800, 1.08850, now_iso, acc_f5a)
    # Create brand-new supervisor instance simulating process restart and try to scan for a new leg
    sup_f5a_restart = runner.OperatorExperimentSupervisor()
    with patch.object(EurUsdStructureA2, "generate_signal", _fake_sig_leg2):
        s_f5a_after_restart = await sup_f5a_restart.scan_market_opportunities(None, _mock_adapter(), now_utc=now_dt, account_id=acc_f5a)
    st_ok_f5a, _ = sup_f5a_restart.load_a2_leg_state(acc_f5a)
    results["fix5_durable_post_fill_lock_across_restart"]["F5_1_post_fill_risk_breach_persists_across_restart"] = (
        res_f5a["status"] == "POST_FILL_RISK_BREACH_NEW_ENTRIES_DISABLED"
        and res_f5a["new_entries_disabled"] is True
        and len(s_f5a_after_restart) == 0
        and sup_f5a_restart.post_fill_guard.new_entries_disabled is True
        and st_ok_f5a is False
    )

    # F5.2: Post-fill TradeMemoryService DB exception disables new entries AND persists across process restart
    acc_f5b = "17000694512_FIX5B"
    sup_f5b = runner.OperatorExperimentSupervisor()
    db_err_mt5 = {
        "status": "FILLED",
        "http_status": 200,
        "response": {
            "status": "FILLED",
            "account_id": acc_f5b,
            "symbol": "EURUSDm",
            "side": "BUY",
            "ticket": "88500002",
            "order_id": "199500002",
            "deal_id": "DEAL-502",
            "requested_volume": 0.03,
            "filled_volume": 0.03,
            "fill_price": 1.08100,  # within budget ($9.00)
            "time_utc": now_iso,
        },
    }
    with patch.object(TradeMemoryService, "record_trade", side_effect=sqlite3.OperationalError("SQLite disk I/O error")):
        res_f5b = sup_f5b.process_broker_fill_response(db_err_mt5, sig_f4, 1.07800, 1.08850, now_iso, acc_f5b)

    # Create brand-new supervisor instance simulating process restart and try to scan for a new leg
    sup_f5b_restart = runner.OperatorExperimentSupervisor()
    with patch.object(EurUsdStructureA2, "generate_signal", _fake_sig_leg2):
        s_f5b_after_restart = await sup_f5b_restart.scan_market_opportunities(None, _mock_adapter(), now_utc=now_dt, account_id=acc_f5b)
    st_ok_f5b, _ = sup_f5b_restart.load_a2_leg_state(acc_f5b)
    results["fix5_durable_post_fill_lock_across_restart"]["F5_2_tradememory_exception_lock_persists_across_restart"] = (
        res_f5b["status"] == "CRITICAL_POST_FILL_PROTECTION_OR_PERSISTENCE_FAILURE"
        and res_f5b["new_entries_disabled"] is True
        and len(s_f5b_after_restart) == 0
        and sup_f5b_restart.post_fill_guard.new_entries_disabled is True
        and st_ok_f5b is False
    )

    # F5.3: Even if state file is deleted after a post-fill incident, the durable JSONL incident log still blocks entries on restart!
    os.remove(runner.OperatorExperimentSupervisor._leg_state_path(acc_f5b))
    sup_f5b_deleted_state = runner.OperatorExperimentSupervisor()
    with patch.object(EurUsdStructureA2, "generate_signal", _fake_sig_leg2):
        s_f5b_del = await sup_f5b_deleted_state.scan_market_opportunities(None, _mock_adapter(), now_utc=now_dt, account_id=acc_f5b)
    results["fix5_durable_post_fill_lock_across_restart"]["F5_3_durable_incident_jsonl_blocks_entries_even_if_state_deleted"] = (
        len(s_f5b_del) == 0 and sup_f5b_deleted_state.post_fill_guard.new_entries_disabled is True
    )

    # =========================================================================
    # 6. REGRESSION, CONCURRENCY & SAFETY CHECKS
    # =========================================================================
    acc_mp = "17000694512_MP17"
    sup_mp = runner.OperatorExperimentSupervisor()
    await sup_mp.reconcile_or_initialize_a2_leg_state(_mock_adapter(), acc_mp)
    with multiprocessing.Pool(6) as pool:
        mp_out = pool.map(_mp_reserve_worker, [(acc_mp, "BUY:1.07500:1.08500", TEST_TMP_DIR) for _ in range(12)])
    results["regression_and_safety"]["R1_multiprocess_concurrent_reservation_single_winner"] = (
        sum(1 for ok, _ in mp_out if ok) == 1
    )

    def _sha256(p):
        with open(p, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    a2_sha = _sha256("/opt/bitdex-research-v2/strategies/eurusd_structure_a2.py")
    a2_frozen_sha = _sha256("/opt/bitdex-research-v2/strategies/eurusd_structure_a2.frozen_v2_0.py")
    with open("/opt/tauric-platform-staging/backend/data/experiment_lock.json", "r") as f:
        lock_data = json.load(f)
    import app.services.strategy_registry_service as srs
    a2_reg = srs.get_strategy_for_customer("LT_STRUCTURE_EURUSD_A2", "USR-ADM-B022F490")

    results["regression_and_safety"].update({
        "R2_frozen_a2_sha256_unchanged": (
            a2_sha == "231e0259c0a0a514537c5efef03139d2b4d5895c07ad8350164c3a04f2b19032"
            and a2_frozen_sha == "231e0259c0a0a514537c5efef03139d2b4d5895c07ad8350164c3a04f2b19032"
        ),
        "S1_experiment_lock_authorized_false": (lock_data.get("authorized") is False),
        "S2_real_trading_permanently_locked": (runner.REAL_TRADING_PERMANENTLY_LOCKED is True and REAL_TRADING_PERMANENTLY_LOCKED is True),
        "S3_real_account_16000629657_blocked": ((await SharedCentralRiskManager.preflight_check(None, "16000629657", None, "EURUSD", "BUY", 0.01, 1.08, 1.077, "LONG_TERM", True))[0] is False),
        "S4_a2_execution_eligible_false": (a2_reg.get("execution_eligible") is False),
        "orig_cmd17_backup_sha256": _sha256("/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py.bak_cmd17_20261118"),
        "final_cmd17_runner_sha256": _sha256("/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py"),
        "frozen_a2_sha256": a2_sha,
    })

    all_passed = all(
        all(bool(v) for k2, v in group.items() if isinstance(v, bool))
        for group in results.values()
        if isinstance(group, dict)
    )
    results["verdict"] = (
        "COMMAND 17 PASSED — ALL FIVE EXECUTION-RELIABILITY FIXES VERIFIED — EXECUTION DISABLED"
        if all_passed else
        "COMMAND 17 FAILED — EXECUTION DISABLED"
    )
    return results


if __name__ == "__main__":
    try:
        out = asyncio.run(run_all_tests())
        with open("/opt/bitdex-research-v2/docs/cmd17_verification.json", "w") as f:
            json.dump(out, f, indent=2)
        print(json.dumps(out, indent=2))
        if not out["verdict"].startswith("COMMAND 17 PASSED"):
            sys.exit(1)
    finally:
        shutil.rmtree(TEST_TMP_DIR, ignore_errors=True)
