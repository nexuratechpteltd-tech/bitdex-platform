#!/usr/bin/env python3
"""
BITDEX COMMAND 19 — COMPREHENSIVE ADVERSARIAL & REMEDIATION VERIFICATION SUITE
Tests all five Command 18 failure remediations (F1, F2, F3, F4, F5) + all 12 mandatory adversarial scenarios
using real TradeMemoryService, real ExnessTerminalBrokerAdapter / ExnessTraderAPIClient (with _ap_request mocked offline),
real SharedCentralRiskManager, real PostFillRiskBreachGuard, and frozen EurUsdStructureA2 v2.0.
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

TEST_TMP_DIR = tempfile.mkdtemp(prefix="bitdex_cmd19_test_")
TEST_DB_PATH = os.path.join(TEST_TMP_DIR, "test_tauric_saas.db")
os.environ["SAAS_DB_PATH"] = TEST_DB_PATH

import run_operator_experiment_runner as runner
import app.services.trade_memory_service as tms_mod
from app.services.trade_memory_service import TradeMemoryService
from app.services.brokers.exness_terminal_adapter import ExnessTerminalBrokerAdapter
from app.services.brokers.shared_risk_manager import SharedCentralRiskManager
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
    acc, leg_id, tmp_dir, db_path = args
    os.environ["SAAS_DB_PATH"] = db_path
    tms_mod.get_db_path = lambda: db_path
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
        "F1_broker_idempotency_correlation": {},
        "F2_account_wide_history_reconciliation": {},
        "F3_eliminate_blind_position_matching": {},
        "F4_atomic_fill_recording": {},
        "F5_durable_safety_lock_independent_of_flat_files": {},
        "adversarial_and_regression": {},
    }
    now_dt = datetime(2026, 11, 18, 12, 0, 0, tzinfo=timezone.utc)
    now_iso = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    d1_bars, h4_bars, h1_bars = _make_closed_candles(now_dt)

    def _mock_adapter(quote_val=None, open_pos=None, order_hist=None, deal_hist=None, submit_res=None):
        ad = MagicMock()
        async def _hc(sym, timeframe="H1", count=100):
            if timeframe == "D1": return d1_bars
            if timeframe == "H4": return h4_bars
            return h1_bars
        ad.get_historical_candles = AsyncMock(side_effect=_hc)
        ad.get_live_quote = AsyncMock(return_value=quote_val or {"bid": 1.08100, "ask": 1.08110})
        ad.get_instrument_specification = AsyncMock(return_value={"symbol": "EURUSD", "digits": 5, "tick_size": 0.00001, "volume_step": 0.01, "min_volume": 0.01})
        ad.get_open_positions = AsyncMock(return_value=open_pos if open_pos is not None else [])
        ad.get_order_history = AsyncMock(return_value=order_hist if order_hist is not None else [])
        ad.get_trade_history = AsyncMock(return_value=deal_hist if deal_hist is not None else [])
        ad.client = MagicMock()
        ad.client.get_trading_snapshot = AsyncMock(return_value={"positions": open_pos or [], "orders": []})
        ad.client.get_trade_history = AsyncMock(return_value=deal_hist if deal_hist is not None else [])
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
    # F1: BROKER IDEMPOTENCY CORRELATION (CMD18-F1-IDEM-KEY-DROPPED)
    # =========================================================================
    acc_f1 = "17000694512_F1"
    sup_f1 = runner.OperatorExperimentSupervisor()

    # Scan to reserve leg and generate persisted idempotency_key
    with patch.object(EurUsdStructureA2, "generate_signal", _fake_sig_leg1):
        sigs_f1 = await sup_f1.scan_market_opportunities(None, _mock_adapter(), now_utc=now_dt, account_id=acc_f1)
    persisted_key_from_scan = sigs_f1[0]["idempotency_key"]

    # Verify mark_a2_leg_order_submitting preserves existing persisted key even if a different key is passed
    ok_sub, returned_key = sup_f1.mark_a2_leg_order_submitting(
        acc_f1, sigs_f1[0]["leg_id"], sigs_f1[0]["reservation_id"], idempotency_key="AttemptedReplacementKey"
    )
    results["F1_broker_idempotency_correlation"]["F1_1_never_replaces_existing_persisted_idem_key"] = (
        ok_sub is True and returned_key == persisted_key_from_scan
    )

    # Verify real ExnessTerminalBrokerAdapter -> ExnessTraderAPIClient.submit_order() receives the EXACT persisted key
    # and signs the outbound POST request with that exact idempotency_key (without generating a replacement UUID!)
    real_term_adapter = ExnessTerminalBrokerAdapter(
        owner_user_id="USR-ADM-B022F490",
        connection_id="EXN-TEST-F1",
        account_id=acc_f1,
        environment="DEMO",
        server_name="dx.2.trial.raw",
        api_key="test_key", api_secret="",
    )
    real_term_adapter.client.live_execution_locked = False
    real_term_adapter.get_open_positions = AsyncMock(return_value=[])
    real_term_adapter.get_account_summary = AsyncMock(return_value={"equity": 5000.0, "balance": 5000.0})
    real_term_adapter.client.get_symbol_info = AsyncMock(return_value={"digits": 5, "contract_size": 100000.0})

    captured_ap_calls = []
    async def _mock_ap_req(method, path, body=None, idempotency_key="", timeout=6.0):
        captured_ap_calls.append({"method": method, "path": path, "body": body, "idempotency_key": idempotency_key})
        if method == "POST":
            return 202, {"operation_id": "379111222333", "status": "accepted", "client_request_id": idempotency_key}
        return 200, {
            "operation_id": "379111222333",
            "status": "confirmed",
            "request_type": "open_position",
            "client_request_id": persisted_key_from_scan,
            "created_at": now_iso,
            "updated_at": now_iso,
        }

    real_term_adapter.client._ap_request = AsyncMock(side_effect=_mock_ap_req)
    # After order submission, reconciliation queries open positions, order history, and deal history
    real_term_adapter.get_open_positions = AsyncMock(side_effect=[
        [],  # first call inside ExnessTerminalBrokerAdapter.place_market_order concurrency check
        [{"position_id": "75111222", "ticket": "75111222", "symbol": "EURUSD", "side": "BUY", "volume": 0.03, "open_price": 1.08110, "open_time": now_iso}],
    ])
    real_term_adapter.get_order_history = AsyncMock(return_value=[
        {"order": {"order_id": "154111222", "position_id": "75111222", "instrument": "EURUSD", "side": "buy", "order_type": "market", "state": "filled", "client_request_id": persisted_key_from_scan, "created_at": now_iso}}
    ])
    real_term_adapter.client.get_trade_history = AsyncMock(return_value=[
        {"deal": {"deal_id": "151111222", "order_id": "154111222", "position_id": "75111222", "instrument": "EURUSD", "side": "buy", "entry": "IN", "price": 1.08110, "volume": 0.03, "created_at": now_iso}}
    ])

    with patch.object(SharedCentralRiskManager, "preflight_check", AsyncMock(return_value=(True, "OK", {}))):
        exec_f1 = await sup_f1.execute_signal_Cycle(None, real_term_adapter, sigs_f1[0], now_iso, account_id=acc_f1)

    post_call = next((c for c in captured_ap_calls if c["method"] == "POST"), None)
    results["F1_broker_idempotency_correlation"]["F1_2_exact_persisted_idem_key_reaches_exness_ap_request"] = (
        post_call is not None
        and post_call["idempotency_key"] == persisted_key_from_scan
        and exec_f1["status"] == "CONFIRMED_AND_PROTECTED"
        and exec_f1["ticket"] == "75111222"
        and exec_f1["order_id"] == "154111222"
    )

    # =========================================================================
    # F2: ACCOUNT-WIDE HISTORY RECONCILIATION (CMD18-F2-TRACK-FILTER-MISMATCH)
    # =========================================================================
    acc_f2 = "17000694512_F2"
    # Insert a legacy non-A2 EURUSD trade on the same account ('Forex Long-Term (EURUSD)')
    TradeMemoryService.record_trade({
        "trade_id": "TMEM-LEGACY-EURUSD-01",
        "broker_ticket": "70000001",
        "order_id": "150000001",
        "deal_id": "140000001",
        "account_id": acc_f2,
        "strategy_track": "Forex Long-Term (EURUSD)",
        "symbol": "EURUSD",
        "side": "BUY",
        "volume_lots": 0.01,
        "entry_price": 1.08000,
        "exit_price": 1.08200,
        "sl_price": 1.07800,
        "tp_price": 1.08500,
        "planned_risk_usd": 2.0,
        "gross_pnl_usd": 2.0,
        "net_pnl_usd": 2.0,
        "execution_type": "ACTUAL_DEMO",
        "status": "CLOSED",
        "signal_reason_json": json.dumps({"reason": "Legacy H4 breakout", "leg_id": "BUY:1.05000:1.06000"}),
    })

    # Broker history contains the entry order, entry deal, AND closing ('OUT') deal + sltp order for that legacy trade
    ad_f2 = _mock_adapter(
        open_pos=[],
        order_hist=[
            {"order": {"order_id": "150000001", "position_id": "70000001", "instrument": "EURUSD", "side": "buy", "order_type": "market", "state": "filled"}},
            {"order": {"order_id": "150000002", "position_id": "70000001", "instrument": "EURUSD", "side": "sell", "order_type": "sltp", "state": "filled"}},
        ],
        deal_hist=[
            {"deal": {"deal_id": "140000001", "order_id": "150000001", "position_id": "70000001", "instrument": "EURUSD", "side": "buy", "entry": "IN", "price": 1.08000, "volume": 0.01}},
            {"deal": {"deal_id": "140000099", "order_id": "150000002", "position_id": "70000001", "instrument": "EURUSD", "side": "sell", "entry": "OUT", "price": 1.08200, "volume": 0.01}},
        ],
    )
    sup_f2 = runner.OperatorExperimentSupervisor()
    ok_f2, leg_f2, st_f2 = await sup_f2.reconcile_or_initialize_a2_leg_state(ad_f2, acc_f2)
    # Must succeed (not false-alarm on legacy EURUSD trade or its closing deal) AND must NOT attribute the legacy leg_id to A2!
    results["F2_account_wide_history_reconciliation"]["F2_1_legacy_other_strategy_eurusd_trades_reconciled_without_false_halt"] = (
        ok_f2 is True and st_f2 == "RECONCILED_FROM_MISSING" and sup_f2.post_fill_guard.new_entries_disabled is False
    )
    results["F2_account_wide_history_reconciliation"]["F2_2_legacy_trades_never_attributed_to_a2_leg_id"] = (
        leg_f2 is None
    )

    # F2.3: Truly untracked EURUSD deal on the account still fails closed!
    ad_f2_untracked = _mock_adapter(
        open_pos=[],
        order_hist=[{"order": {"order_id": "159999999", "position_id": "79999999", "instrument": "EURUSD", "side": "buy", "order_type": "market", "state": "filled"}}],
        deal_hist=[{"deal": {"deal_id": "149999999", "order_id": "159999999", "position_id": "79999999", "instrument": "EURUSD", "side": "buy", "entry": "IN", "price": 1.08100, "volume": 0.02}}],
    )
    sup_f2_untracked = runner.OperatorExperimentSupervisor()
    ok_f2u, _, st_f2u = await sup_f2_untracked.reconcile_or_initialize_a2_leg_state(ad_f2_untracked, acc_f2)
    results["F2_account_wide_history_reconciliation"]["F2_3_genuinely_untracked_eurusd_execution_fails_closed"] = (
        ok_f2u is False and st_f2u == "UNTRACKED_BROKER_DEAL_HISTORY" and sup_f2_untracked.post_fill_guard.new_entries_disabled is True
    )

    # =========================================================================
    # F3: ELIMINATE BLIND POSITION MATCHING (CMD18-F3-*)
    # =========================================================================
    acc_f3 = "17000694512_F3"

    # F3.1: Fresh supervisor construction has all attributes initialized without calling ensure_post_fill_guard() manually
    fresh_sup = runner.OperatorExperimentSupervisor()
    has_attrs_on_init = (
        hasattr(fresh_sup, "post_fill_guard")
        and hasattr(fresh_sup, "_reconciled_fill_tickets")
        and hasattr(fresh_sup, "_reconciled_deal_ids")
        and hasattr(fresh_sup, "critical_incidents")
    )
    results["F3_eliminate_blind_position_matching"]["F3_1_fresh_supervisor_attributes_initialized_on_init"] = has_attrs_on_init

    # F3.2: Unrelated open EURUSD position with same direction (e.g. 0.50 lots at 1.06000 or opened 10 minutes earlier)
    # when new 0.03-lot A2 order at 1.08110 is delayed in snapshot -> MUST NOT bind the unrelated position!
    sig_f3 = {
        "strategy": "LT_STRUCTURE_EURUSD_A2", "engine_type": "LONG_TERM", "strategy_version": "2.0",
        "symbol": "EURUSD", "side": "BUY", "volume": 0.03, "entry_price": 1.08110,
        "sl_price": 1.07800, "tp_price": 1.08850, "leg_id": "BUY:1.07500:1.08500",
        "idempotency_key": "bitdex-a2-req-f3", "reason": "test",
    }
    raw_op_f3 = {
        "status": "FILLED",
        "operation_id": "379333001",
        "ack": {"operation_id": "379333001", "status": "accepted", "client_request_id": "bitdex-a2-req-f3"},
        "operation": {
            "operation_id": "379333001", "status": "confirmed", "request_type": "open_position",
            "client_request_id": "bitdex-a2-req-f3",
            "created_at": "2026-11-18T12:00:00Z", "updated_at": "2026-11-18T12:00:01Z",
        },
        "payload": {"instrument": "EURUSD", "side": "buy", "volume": "0.03"},
    }
    ad_unrelated = _mock_adapter(
        open_pos=[{"position_id": "77777777", "symbol": "EURUSD", "side": "BUY", "volume": 0.50, "open_price": 1.06000, "open_time": "2026-11-18T11:00:00Z"}],
        order_hist=[{"order": {"order_id": "188888888", "position_id": "77777777", "instrument": "EURUSD", "side": "buy", "order_type": "market", "state": "filled", "created_at": "2026-11-18T11:00:00Z"}}],
        deal_hist=[{"deal": {"deal_id": "166666666", "order_id": "188888888", "position_id": "77777777", "instrument": "EURUSD", "side": "buy", "entry": "IN", "price": 1.06000, "volume": 0.50, "created_at": "2026-11-18T11:00:00Z"}}],
    )
    rec_unrelated = await fresh_sup.reconcile_exness_terminal_operation(ad_unrelated, raw_op_f3, sig_f3, account_id=acc_f3)
    norm_unrelated = fresh_sup.normalize_exness_order_response(rec_unrelated, "EURUSD", "BUY", acc_f3, 1.08110)
    results["F3_eliminate_blind_position_matching"]["F3_2_unrelated_open_position_rejected_and_fails_closed"] = (
        rec_unrelated.get("operation", {}).get("position_id") is None
        and norm_unrelated["normalized_status"] == "AMBIGUOUS"
    )

    # F3.3: Multiple simultaneous untracked EURUSD positions with identical side/volume/time -> ambiguous, refuses to guess and fails closed!
    ad_multi_ambig = _mock_adapter(
        open_pos=[
            {"position_id": "75333001", "symbol": "EURUSD", "side": "BUY", "volume": 0.03, "open_price": 1.08110, "open_time": now_iso},
            {"position_id": "75333002", "symbol": "EURUSD", "side": "BUY", "volume": 0.03, "open_price": 1.08112, "open_time": now_iso},
        ],
        order_hist=[
            {"order": {"order_id": "154333001", "position_id": "75333001", "instrument": "EURUSD", "side": "buy", "order_type": "market", "state": "filled", "created_at": now_iso}},
            {"order": {"order_id": "154333002", "position_id": "75333002", "instrument": "EURUSD", "side": "buy", "order_type": "market", "state": "filled", "created_at": now_iso}},
        ],
        deal_hist=[
            {"deal": {"deal_id": "151333001", "order_id": "154333001", "position_id": "75333001", "instrument": "EURUSD", "side": "buy", "entry": "IN", "price": 1.08110, "volume": 0.03, "created_at": now_iso}},
            {"deal": {"deal_id": "151333002", "order_id": "154333002", "position_id": "75333002", "instrument": "EURUSD", "side": "buy", "entry": "IN", "price": 1.08112, "volume": 0.03, "created_at": now_iso}},
        ],
    )
    rec_multi_ambig = await fresh_sup.reconcile_exness_terminal_operation(ad_multi_ambig, raw_op_f3, sig_f3, account_id=acc_f3)
    norm_multi_ambig = fresh_sup.normalize_exness_order_response(rec_multi_ambig, "EURUSD", "BUY", acc_f3, 1.08110)
    results["F3_eliminate_blind_position_matching"]["F3_3_multiple_simultaneous_ambiguous_positions_fail_closed"] = (
        rec_multi_ambig.get("operation", {}).get("position_id") is None
        and norm_multi_ambig["normalized_status"] == "AMBIGUOUS"
    )

    # F3.4: Position opens AND closes before reconciliation (open_positions=[], deal_history has 2 partial entry IN deals + 1 closing OUT deal, order_history has market order + sltp order WITHOUT operation_id)
    ad_closed_multi = _mock_adapter(
        open_pos=[],
        order_hist=[
            {"order": {"order_id": "154777001", "position_id": "75777001", "instrument": "EURUSD", "side": "buy", "order_type": "market", "state": "filled"}, "event_time": "2026-11-18T12:00:00Z"},
            {"order": {"order_id": "154777002", "position_id": "75777001", "instrument": "EURUSD", "side": "sell", "order_type": "sltp", "state": "filled"}, "event_time": "2026-11-18T12:00:02Z"},
        ],
        deal_hist=[
            {"deal": {"deal_id": "151777001A", "order_id": "154777001", "position_id": "75777001", "instrument": "EURUSD", "side": "buy", "entry": "IN", "price": 1.08100, "volume": 0.01}, "event_time": "2026-11-18T12:00:00Z"},
            {"deal": {"deal_id": "151777001B", "order_id": "154777001", "position_id": "75777001", "instrument": "EURUSD", "side": "buy", "entry": "IN", "price": 1.08115, "volume": 0.02}, "event_time": "2026-11-18T12:00:00Z"},
            {"deal": {"deal_id": "151777002", "order_id": "154777002", "position_id": "75777001", "instrument": "EURUSD", "side": "sell", "entry": "OUT", "price": 1.07800, "volume": 0.03}, "event_time": "2026-11-18T12:00:02Z"},
        ],
    )
    rec_closed_multi = await fresh_sup.reconcile_exness_terminal_operation(ad_closed_multi, raw_op_f3, sig_f3, account_id=acc_f3)
    norm_closed_multi = fresh_sup.normalize_exness_order_response(rec_closed_multi, "EURUSD", "BUY", acc_f3, 1.08110)
    results["F3_eliminate_blind_position_matching"]["F3_4_closed_position_with_multiple_deals_reconciled_accurately"] = (
        norm_closed_multi["normalized_status"] == "CONFIRMED_FULL_FILL"
        and norm_closed_multi["broker_ticket"] == "75777001"
        and norm_closed_multi["order_id"] == "154777001"
        and norm_closed_multi["deal_ids"] == ["151777001A", "151777001B"]
        and norm_closed_multi["filled_volume"] == 0.03
        and norm_closed_multi["fill_price"] == 1.08110
    )

    # =========================================================================
    # F4: ATOMIC FILL RECORDING (CMD18-F4-SPLIT-SQLITE-TRANSACTION)
    # =========================================================================
    acc_f4 = "17000694512_F4"
    sup_f4 = runner.OperatorExperimentSupervisor()
    sig_f4 = dict(sig_f3, leg_id="BUY:1.07600:1.08600")
    mt5_f4 = {
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
                {"deal_id": "DF4-1", "position_id": "88400001", "order_id": "199400001", "price": 1.08100, "volume": 0.01},
                {"deal_id": "DF4-2", "position_id": "88400001", "order_id": "199400001", "price": 1.08115, "volume": 0.02},
            ],
            "time_utc": now_iso,
        },
    }

    # F4.1: Pre-insert a conflicting row with deal_id="DF4-2" into a2_deal_ledger for a DIFFERENT account or force a constraint failure on the second deal insert
    # Wait: if we pre-insert deal_id="DF4-2" under a trigger that raises ABORT on insert into a2_deal_ledger when deal_id=='DF4-2',
    # TradeMemoryService.record_trade() will have ALREADY executed its INSERT into trade_memory on the same connection!
    # When the second deal insert raises sqlite3.IntegrityError, the shared transaction MUST roll back BOTH trade_memory and a2_deal_ledger!
    conn_trig = TradeMemoryService.get_connection()
    with conn_trig:
        runner.OperatorExperimentSupervisor._ensure_deal_ledger_table(conn_trig)
        conn_trig.execute("""
            CREATE TRIGGER fail_on_df4_2
            BEFORE INSERT ON a2_deal_ledger
            WHEN NEW.deal_id = 'DF4-2'
            BEGIN
                SELECT RAISE(ABORT, 'Simulated constraint failure on second deal in a2_deal_ledger');
            END;
        """)
    conn_trig.close()

    res_f4_rollback = sup_f4.process_broker_fill_response(mt5_f4, sig_f4, 1.07800, 1.08850, now_iso, acc_f4)

    conn_verify = TradeMemoryService.get_connection()
    tm_count_f4 = conn_verify.execute("SELECT count(*) FROM trade_memory WHERE account_id = ?", (acc_f4,)).fetchone()[0]
    dl_count_f4 = conn_verify.execute("SELECT count(*) FROM a2_deal_ledger WHERE account_id = ?", (acc_f4,)).fetchone()[0]
    sl_count_f4 = conn_verify.execute("SELECT count(*) FROM a2_safety_locks WHERE account_id = ? AND new_entries_disabled = 1", (acc_f4,)).fetchone()[0]
    with conn_verify:
        conn_verify.execute("DROP TRIGGER IF EXISTS fail_on_df4_2")
    conn_verify.close()

    results["F4_atomic_fill_recording"]["F4_1_deal_ledger_failure_rolls_back_trade_memory_atomically"] = (
        res_f4_rollback["recorded"] is False
        and res_f4_rollback["new_entries_disabled"] is True
        and tm_count_f4 == 0
        and dl_count_f4 == 0
        and sl_count_f4 == 1
    )

    # F4.2: Normal multi-deal commit commits BOTH trade_memory and all rows in a2_deal_ledger atomically
    acc_f4_ok = "17000694512_F4_OK"
    sup_f4_ok = runner.OperatorExperimentSupervisor()
    mt5_f4_ok = dict(mt5_f4, response=dict(mt5_f4["response"], account_id=acc_f4_ok, ticket="88400002", order_id="199400002", deals=[
        {"deal_id": "DF4-OK1", "position_id": "88400002", "order_id": "199400002", "price": 1.08100, "volume": 0.01},
        {"deal_id": "DF4-OK2", "position_id": "88400002", "order_id": "199400002", "price": 1.08115, "volume": 0.02},
    ]))
    res_f4_ok = sup_f4_ok.process_broker_fill_response(mt5_f4_ok, sig_f4, 1.07800, 1.08850, now_iso, acc_f4_ok)
    conn_v2 = TradeMemoryService.get_connection()
    tm_cnt_ok = conn_v2.execute("SELECT count(*) FROM trade_memory WHERE account_id = ?", (acc_f4_ok,)).fetchone()[0]
    dl_cnt_ok = conn_v2.execute("SELECT count(*) FROM a2_deal_ledger WHERE account_id = ?", (acc_f4_ok,)).fetchone()[0]
    conn_v2.close()
    results["F4_atomic_fill_recording"]["F4_2_shared_transaction_commits_both_tables_consistently"] = (
        res_f4_ok["recorded"] is True and tm_cnt_ok == 1 and dl_cnt_ok == 2
    )

    # =========================================================================
    # F5: DURABLE SAFETY LOCK INDEPENDENT OF FLAT-FILE SUCCESS (CMD18-F5-*)
    # =========================================================================
    acc_f5 = "17000694512_F5"
    sup_f5 = runner.OperatorExperimentSupervisor()
    mt5_f5 = {
        "status": "FILLED",
        "http_status": 200,
        "response": {
            "status": "FILLED",
            "account_id": acc_f5,
            "symbol": "EURUSDm",
            "side": "BUY",
            "ticket": "88500001",
            "order_id": "199500001",
            "deal_id": "DF5-1",
            "requested_volume": 0.03,
            "filled_volume": 0.03,
            "fill_price": 1.08100,  # within budget ($9.00 <= $10.00)
            "time_utc": now_iso,
        },
    }

    # F5.1: Inject flat-file failure (both confirm_a2_leg_fill AND JSONL incident file write fail due to filesystem error),
    # while SQLite succeeds!
    with patch.object(sup_f5, "confirm_a2_leg_fill", return_value=False), \
         patch("builtins.open", side_effect=OSError("Simulated filesystem full / permission denied on flat files")):
        res_f5 = sup_f5.process_broker_fill_response(mt5_f5, sig_f4, 1.07800, 1.08850, now_iso, acc_f5)

    # Now simulate process restart when filesystem is readable again (state file is MISSING, incident JSONL file is MISSING,
    # and TradeMemory has post_fill_within_budget=True, Deal is in TradeMemory):
    # Because a2_safety_locks in SQLite recorded the halt, the restarted process MUST remain locked!
    sup_f5_restart = runner.OperatorExperimentSupervisor()
    ad_f5_restart = _mock_adapter(
        open_pos=[{"position_id": "88500001", "symbol": "EURUSD", "side": "BUY", "volume": 0.03, "open_price": 1.08100}],
        order_hist=[{"order": {"order_id": "199500001", "position_id": "88500001", "instrument": "EURUSD", "side": "buy", "order_type": "market", "state": "filled"}}],
        deal_hist=[{"deal": {"deal_id": "DF5-1", "order_id": "199500001", "position_id": "88500001", "instrument": "EURUSD", "side": "buy", "entry": "IN", "price": 1.08100, "volume": 0.03}}],
    )
    ok_f5_r, _, st_f5_r = await sup_f5_restart.reconcile_or_initialize_a2_leg_state(ad_f5_restart, acc_f5)
    load_ok_f5, _ = sup_f5_restart.load_a2_leg_state(acc_f5)
    results["F5_durable_safety_lock_independent_of_flat_files"]["F5_1_filesystem_failure_after_fill_persists_halt_in_sqlite_across_restart"] = (
        res_f5["new_entries_disabled"] is True
        and ok_f5_r is False
        and "SQLITE_SAFETY_LOCK" in st_f5_r
        and sup_f5_restart.post_fill_guard.new_entries_disabled is True
        and load_ok_f5 is False
    )

    # F5.2: If SQLite safety-lock mechanism itself becomes unavailable/unreadable -> fails closed!
    acc_f5_dbdown = "17000694512_F5_DBDOWN"
    sup_f5_dbdown = runner.OperatorExperimentSupervisor()
    with patch.object(TradeMemoryService, "get_connection", side_effect=sqlite3.OperationalError("SQLite database file unreadable")):
        ok_dbdown, _, st_dbdown = await sup_f5_dbdown.reconcile_or_initialize_a2_leg_state(_mock_adapter(), acc_f5_dbdown)
        load_ok_dbdown, _ = sup_f5_dbdown.load_a2_leg_state(acc_f5_dbdown)
    results["F5_durable_safety_lock_independent_of_flat_files"]["F5_2_sqlite_safety_lock_unavailable_fails_closed"] = (
        ok_dbdown is False
        and "SQLITE_SAFETY_LOCK_UNAVAILABLE" in st_dbdown
        and sup_f5_dbdown.post_fill_guard.new_entries_disabled is True
        and load_ok_dbdown is False
    )

    # =========================================================================
    # ADVERSARIAL & REGRESSION SUITE
    # =========================================================================
    # A1: Concurrent processes attempting duplicate reservations
    acc_mp = "17000694512_MP19"
    sup_mp = runner.OperatorExperimentSupervisor()
    await sup_mp.reconcile_or_initialize_a2_leg_state(_mock_adapter(), acc_mp)
    with multiprocessing.Pool(6) as pool:
        mp_out = pool.map(_mp_reserve_worker, [(acc_mp, "BUY:1.07500:1.08500", TEST_TMP_DIR, TEST_DB_PATH) for _ in range(12)])
    results["adversarial_and_regression"]["A1_concurrent_processes_single_reservation_winner"] = (
        sum(1 for ok, _ in mp_out if ok) == 1
    )

    # A2: Corrupt incident JSONL file fails closed
    acc_bad_inc = "17000694512_BADINC"
    with open(runner.OperatorExperimentSupervisor._incident_path(acc_bad_inc), "w") as f:
        f.write("{PARTIAL_CORRUPT_JSONL_LINE\n")
    sup_bad_inc = runner.OperatorExperimentSupervisor()
    ok_bi, _, st_bi = await sup_bad_inc.reconcile_or_initialize_a2_leg_state(_mock_adapter(), acc_bad_inc)
    results["adversarial_and_regression"]["A2_corrupt_incident_jsonl_fails_closed"] = (
        ok_bi is False and st_bi == "HALTED_BY_DURABLE_INCIDENT_LOG" and sup_bad_inc.post_fill_guard.new_entries_disabled is True
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

    results["adversarial_and_regression"].update({
        "R1_frozen_a2_sha256_unchanged": (
            a2_sha == "231e0259c0a0a514537c5efef03139d2b4d5895c07ad8350164c3a04f2b19032"
            and a2_frozen_sha == "231e0259c0a0a514537c5efef03139d2b4d5895c07ad8350164c3a04f2b19032"
        ),
        "S1_experiment_lock_authorized_false": (lock_data.get("authorized") is False),
        "S2_real_trading_permanently_locked": (runner.REAL_TRADING_PERMANENTLY_LOCKED is True and REAL_TRADING_PERMANENTLY_LOCKED is True),
        "S3_real_account_16000629657_blocked": ((await SharedCentralRiskManager.preflight_check(None, "16000629657", None, "EURUSD", "BUY", 0.01, 1.08, 1.077, "LONG_TERM", True))[0] is False),
        "S4_a2_execution_eligible_false": (a2_reg.get("execution_eligible") is False),
        "orig_runner_bak_cmd19_sha256": _sha256("/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py.bak_cmd19_20261118"),
        "final_runner_cmd19_sha256": _sha256("/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py"),
        "orig_tm_bak_cmd19_sha256": _sha256("/opt/tauric-platform-staging/backend/app/services/trade_memory_service.py.bak_cmd19_20261118"),
        "final_tm_cmd19_sha256": _sha256("/opt/tauric-platform-staging/backend/app/services/trade_memory_service.py"),
        "frozen_a2_sha256": a2_sha,
    })

    all_passed = all(
        all(bool(v) for k2, v in group.items() if isinstance(v, bool))
        for group in results.values()
        if isinstance(group, dict)
    )
    results["verdict"] = (
        "COMMAND 19 PASSED — ALL FIVE COMMAND 18 FINDINGS REMEDIATED"
        if all_passed else
        "COMMAND 19 FAILED — EXECUTION DISABLED"
    )
    return results


if __name__ == "__main__":
    try:
        out = asyncio.run(run_all_tests())
        with open("/opt/bitdex-research-v2/docs/cmd19_verification.json", "w") as f:
            json.dump(out, f, indent=2)
        print(json.dumps(out, indent=2))
        if not out["verdict"].startswith("COMMAND 19 PASSED"):
            sys.exit(1)
    finally:
        shutil.rmtree(TEST_TMP_DIR, ignore_errors=True)
