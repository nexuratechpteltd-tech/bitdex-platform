#!/usr/bin/env python3
"""
BITDEX COMMAND 15 — COMPREHENSIVE OFFLINE UNIT & REAL-SERVICE INTEGRATION TEST SUITE
Strictly offline: zero broker network calls, zero live/demo order placements, isolated SQLite DB & temp state files.
Uses the REAL implementations of:
  - OperatorExperimentSupervisor (normaliser, transactional leg state manager, post-fill handler)
  - PostFillRiskBreachGuard
  - SharedCentralRiskManager
  - TradeMemoryService (backed by isolated temporary SQLite database via SAAS_DB_PATH)
  - Frozen EurUsdStructureA2 v2.0
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

# Create isolated temporary directory and SQLite DB for real TradeMemoryService testing
TEST_TMP_DIR = tempfile.mkdtemp(prefix="bitdex_cmd15_test_")
TEST_DB_PATH = os.path.join(TEST_TMP_DIR, "test_tauric_saas.db")
os.environ["SAAS_DB_PATH"] = TEST_DB_PATH

import run_operator_experiment_runner as runner
from app.services.trade_memory_service import TradeMemoryService, reconcile_partial_fills
from app.services.brokers.shared_risk_manager import SharedCentralRiskManager, PostFillRiskBreachGuard
from app.services.brokers.central_risk_gate import REAL_TRADING_PERMANENTLY_LOCKED
from strategies.eurusd_structure_a2 import EurUsdStructureA2

# Patch get_db_path in trade_memory_service to point strictly to isolated TEST_DB_PATH
import app.services.trade_memory_service as tms_mod
tms_mod.get_db_path = lambda: TEST_DB_PATH
TradeMemoryService.init_db()

# Redirect leg state / lock / incident paths to TEST_TMP_DIR during tests
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
    s = runner.OperatorExperimentSupervisor()
    ok, token = s.reserve_a2_leg_pending(acc, leg_id, {"worker": os.getpid()})
    return ok, token


async def run_all_tests():
    results = {
        "deduplication": {},
        "exness_parsing": {},
        "trade_memory": {},
        "post_fill_failures": {},
        "regression": {},
        "safety": {},
    }
    now_dt = datetime(2026, 11, 18, 12, 0, 0, tzinfo=timezone.utc)
    now_iso = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    d1_bars, h4_bars, h1_bars = _make_closed_candles(now_dt)

    def _mock_adapter(quote_val=None, quote_exc=None, open_pos=None):
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
        ad.get_order_history = AsyncMock(return_value=[])
        ad.get_trade_history = AsyncMock(return_value=[])
        return ad

    def _fake_sig_leg1(self_a2, bars, idx):
        leg = "BUY:1.07500:1.08500"
        if self_a2.last_leg_id == leg:
            return None
        self_a2.last_leg_id = leg
        return {"direction": "BUY", "sl": 1.07800, "tp": 1.08850}

    # =========================================================================
    # 1. DEDUPLICATION LIFECYCLE TESTS (Remediation B-1)
    # =========================================================================
    acc_dedup = "17000694512_DEDUP"
    sup = runner.OperatorExperimentSupervisor()

    # D1: Quote failure does not consume a leg
    with patch.object(EurUsdStructureA2, "generate_signal", _fake_sig_leg1):
        ad_qfail = _mock_adapter(quote_exc=RuntimeError("Exness quote timeout"))
        sigs_qfail = await sup.scan_market_opportunities(None, ad_qfail, now_utc=now_dt, account_id=acc_dedup)
        st_ok, last_leg = sup.load_a2_leg_state(acc_dedup)
        # Immediately retry with working quote -> must emit signal on the same leg!
        ad_qok = _mock_adapter({"bid": 1.08100, "ask": 1.08110})
        sigs_after_qfail = await sup.scan_market_opportunities(None, ad_qok, now_utc=now_dt, account_id=acc_dedup)
        # Release so next test can use same leg
        sup.release_a2_leg_reservation(acc_dedup, "BUY:1.07500:1.08500", "TEST_RESET", sigs_after_qfail[0]["reservation_id"])
    results["deduplication"]["D1_quote_failure_does_not_consume_leg"] = (
        len(sigs_qfail) == 0 and st_ok is True and last_leg is None and len(sigs_after_qfail) == 1
    )

    # D2: Spread rejection does not consume a leg
    with patch.object(EurUsdStructureA2, "generate_signal", _fake_sig_leg1):
        ad_wide = _mock_adapter({"bid": 1.08100, "ask": 1.08200})  # 10 pips > 2.5 pips max
        sigs_wide = await sup.scan_market_opportunities(None, ad_wide, now_utc=now_dt, account_id=acc_dedup)
        st_ok, last_leg = sup.load_a2_leg_state(acc_dedup)
        ad_norm = _mock_adapter({"bid": 1.08100, "ask": 1.08110})
        sigs_after_wide = await sup.scan_market_opportunities(None, ad_norm, now_utc=now_dt, account_id=acc_dedup)
        sup.release_a2_leg_reservation(acc_dedup, "BUY:1.07500:1.08500", "TEST_RESET", sigs_after_wide[0]["reservation_id"])
    results["deduplication"]["D2_spread_rejection_does_not_consume_leg"] = (
        len(sigs_wide) == 0 and st_ok is True and last_leg is None and len(sigs_after_wide) == 1
    )

    # D3: Sizing failure does not consume a leg (SL too wide -> lots is None)
    def _fake_sig_wide_sl(self_a2, bars, idx):
        leg = "BUY:1.07500:1.08500"
        if self_a2.last_leg_id == leg:
            return None
        self_a2.last_leg_id = leg
        return {"direction": "BUY", "sl": 0.95000, "tp": 1.25000}  # >1300 pips SL -> 0.01 lot > $10 risk -> None

    with patch.object(EurUsdStructureA2, "generate_signal", _fake_sig_wide_sl):
        sigs_szfail = await sup.scan_market_opportunities(None, _mock_adapter(), now_utc=now_dt, account_id=acc_dedup)
        st_ok, last_leg = sup.load_a2_leg_state(acc_dedup)
    with patch.object(EurUsdStructureA2, "generate_signal", _fake_sig_leg1):
        sigs_after_sz = await sup.scan_market_opportunities(None, _mock_adapter(), now_utc=now_dt, account_id=acc_dedup)
    results["deduplication"]["D3_sizing_failure_does_not_consume_leg"] = (
        len(sigs_szfail) == 0 and st_ok is True and last_leg is None and len(sigs_after_sz) == 1
    )

    # D4: Central risk preflight rejection does not consume a leg
    sig_for_pf = sigs_after_sz[0]
    with patch.object(SharedCentralRiskManager, "preflight_check", AsyncMock(return_value=(False, "MAX_CONCURRENT_POSITIONS", {}))):
        pf_res = await sup.execute_signal_Cycle(None, _mock_adapter(), sig_for_pf, now_iso, account_id=acc_dedup)
    st_ok_pf, last_leg_pf = sup.load_a2_leg_state(acc_dedup)
    with patch.object(EurUsdStructureA2, "generate_signal", _fake_sig_leg1):
        sigs_after_pf = await sup.scan_market_opportunities(None, _mock_adapter(), now_utc=now_dt, account_id=acc_dedup)
    results["deduplication"]["D4_preflight_rejection_does_not_consume_leg"] = (
        pf_res["status"] == "PREFLIGHT_REJECTED" and st_ok_pf is True and last_leg_pf is None and len(sigs_after_pf) == 1
    )

    # D5: Concurrent reservations cannot duplicate a leg
    # Release current reservation so leg is AVAILABLE, then spawn 6 concurrent worker processes trying to reserve it
    sup.release_a2_leg_reservation(acc_dedup, "BUY:1.07500:1.08500", "PREP_MP", sigs_after_pf[0]["reservation_id"])
    with multiprocessing.Pool(6) as pool:
        mp_res = pool.map(_mp_reserve_worker, [(acc_dedup, "BUY:1.07500:1.08500", TEST_TMP_DIR) for _ in range(12)])
    success_count = sum(1 for ok, _ in mp_res if ok)
    winning_token = next(tok for ok, tok in mp_res if ok)
    results["deduplication"]["D5_concurrent_reservations_single_winner"] = (success_count == 1)

    # D6: Confirmed fill consumes the leg durably & D7: Restart preserves confirmed state
    confirmed_exness_payload = {
        "status": "FILLED",
        "operation_id": "379900000000000001",
        "ack": {"operation_id": "379900000000000001", "status": "accepted"},
        "operation": {
            "operation_id": "379900000000000001",
            "status": "confirmed",
            "position_id": "75100001",
            "order_id": "154100001",
            "deal_id": "151900001",
            "instrument": "EURUSD",
            "side": "buy",
            "fill_price": 1.08110,
            "filled_volume": 0.03,
            "updated_at": now_iso,
        },
        "payload": {"instrument": "EURUSD", "side": "buy", "volume": "0.03"},
    }
    sig_to_fill = dict(sigs_after_pf[0], reservation_id=winning_token)
    fill_out = sup.process_broker_fill_response(
        confirmed_exness_payload, sig_to_fill, sig_to_fill["sl_price"], sig_to_fill["tp_price"], now_iso, acc_dedup, winning_token
    )
    # Simulate process restart with new supervisor instance
    sup_restarted = runner.OperatorExperimentSupervisor()
    with patch.object(EurUsdStructureA2, "generate_signal", _fake_sig_leg1):
        sigs_after_restart = await sup_restarted.scan_market_opportunities(None, _mock_adapter(), now_utc=now_dt, account_id=acc_dedup)
    st_ok_conf, persisted_conf_leg = sup_restarted.load_a2_leg_state(acc_dedup)
    results["deduplication"]["D6_confirmed_fill_consumes_leg_durably"] = (
        fill_out["status"] == "CONFIRMED_AND_PROTECTED" and fill_out["leg_state_saved"] is True and persisted_conf_leg == "BUY:1.07500:1.08500"
    )
    results["deduplication"]["D7_restart_preserves_confirmed_state"] = (len(sigs_after_restart) == 0)

    # D8: Missing state file triggers reconciliation from TradeMemoryService (does NOT reset consumed leg!)
    os.remove(sup._leg_state_path(acc_dedup))
    sup_missing = runner.OperatorExperimentSupervisor()
    with patch.object(EurUsdStructureA2, "generate_signal", _fake_sig_leg1):
        sigs_after_delete = await sup_missing.scan_market_opportunities(None, _mock_adapter(), now_utc=now_dt, account_id=acc_dedup)
    st_ok_reconciled, leg_reconciled = sup_missing.load_a2_leg_state(acc_dedup)
    results["deduplication"]["D8_missing_state_reconciles_from_tradememory_without_reset"] = (
        len(sigs_after_delete) == 0 and st_ok_reconciled is True and leg_reconciled == "BUY:1.07500:1.08500"
    )

    # D9: Missing state file + open EURUSD position on broker WITHOUT TradeMemory record -> incomplete reconciliation disables new entries
    acc_unrec = "17000694512_UNREC"
    sup_unrec = runner.OperatorExperimentSupervisor()
    ad_untracked_pos = _mock_adapter(open_pos=[{"position_id": "99999999", "symbol": "EURUSD", "side": "BUY", "volume": 0.03, "open_price": 1.08100}])
    with patch.object(EurUsdStructureA2, "generate_signal", _fake_sig_leg1):
        sigs_unrec = await sup_unrec.scan_market_opportunities(None, ad_untracked_pos, now_utc=now_dt, account_id=acc_unrec)
    results["deduplication"]["D9_incomplete_reconciliation_disables_new_entries"] = (
        len(sigs_unrec) == 0 and sup_unrec.post_fill_guard.new_entries_disabled is True and len(sup_unrec.critical_incidents) >= 1
    )

    # D10: Corrupt state file fails closed and disables new entries
    acc_corrupt = "17000694512_CORRUPT"
    with open(runner.OperatorExperimentSupervisor._leg_state_path(acc_corrupt), "w") as f:
        f.write("{CORRUPT_JSON!!!")
    sup_corrupt = runner.OperatorExperimentSupervisor()
    with patch.object(EurUsdStructureA2, "generate_signal", _fake_sig_leg1):
        sigs_corrupt = await sup_corrupt.scan_market_opportunities(None, _mock_adapter(), now_utc=now_dt, account_id=acc_corrupt)
    results["deduplication"]["D10_corrupt_state_fails_closed"] = (
        len(sigs_corrupt) == 0 and sup_corrupt.post_fill_guard.new_entries_disabled is True
    )

    # D11: Ambiguous fill locks leg and prevents retry across restart
    acc_ambig = "17000694512_AMBIG"
    sup_ambig = runner.OperatorExperimentSupervisor()
    with patch.object(EurUsdStructureA2, "generate_signal", _fake_sig_leg1):
        sigs_amb = await sup_ambig.scan_market_opportunities(None, _mock_adapter(), now_utc=now_dt, account_id=acc_ambig)
    amb_out = sup_ambig.process_broker_fill_response(
        {"status": "ACCEPTED", "operation_id": "379900000000000099", "operation": {"status": "accepted"}},
        sigs_amb[0], 1.07800, 1.08850, now_iso, acc_ambig, sigs_amb[0]["reservation_id"]
    )
    sup_ambig_restart = runner.OperatorExperimentSupervisor()
    with patch.object(EurUsdStructureA2, "generate_signal", _fake_sig_leg1):
        sigs_amb_retry = await sup_ambig_restart.scan_market_opportunities(None, _mock_adapter(), now_utc=now_dt, account_id=acc_ambig)
    results["deduplication"]["D11_ambiguous_fill_prevents_retry"] = (
        amb_out["new_entries_disabled"] is True and len(sigs_amb_retry) == 0 and sup_ambig_restart.post_fill_guard.new_entries_disabled is True
    )

    # =========================================================================
    # 2. EXNESS RESPONSE PARSING TESTS (Remediation C-3)
    # =========================================================================
    norm_fn = runner.OperatorExperimentSupervisor.normalize_exness_order_response

    # P1: Actual nested ExnessTraderAPIClient.submit_order() confirmed fill
    p1 = norm_fn(confirmed_exness_payload, "EURUSD", "BUY", "17000694512", 1.08100)
    results["exness_parsing"]["P1_nested_submit_order_confirmed_fill"] = (
        p1["normalized_status"] == "CONFIRMED_FULL_FILL"
        and p1["broker_ticket"] == "75100001"
        and p1["order_id"] == "154100001"
        and p1["deal_id"] == "151900001"
        and p1["operation_id"] == "379900000000000001"
        and p1["fill_price"] == 1.08110
        and p1["filled_volume"] == 0.03
    )

    # P2: Actual nested ExnessMT5BrokerAdapter.place_market_order() confirmed fill
    mt5_payload = {
        "status": "FILLED",
        "http_status": 200,
        "response": {
            "status": "FILLED",
            "account_id": "17000694512",
            "symbol": "EURUSDm",
            "side": "BUY",
            "ticket": "88100002",
            "order_id": "199100002",
            "deal_id": "299100002",
            "requested_volume": 0.03,
            "filled_volume": 0.03,
            "fill_price": 1.08115,
            "time_utc": now_iso,
        },
    }
    p2 = norm_fn(mt5_payload, "EURUSD", "BUY", "17000694512", 1.08100)
    results["exness_parsing"]["P2_nested_mt5_place_market_order_confirmed_fill"] = (
        p2["normalized_status"] == "CONFIRMED_FULL_FILL"
        and p2["broker_ticket"] == "88100002"
        and p2["order_id"] == "199100002"
        and p2["deal_id"] == "299100002"
        and p2["symbol"] == "EURUSD"
    )

    # P3: Accepted but not yet filled
    p3 = norm_fn({
        "status": "ACCEPTED",
        "operation_id": "379900000000000003",
        "ack": {"operation_id": "379900000000000003", "status": "accepted"},
        "operation": {"operation_id": "379900000000000003", "status": "accepted"},
        "payload": {"instrument": "EURUSD", "side": "buy", "volume": "0.03"},
    }, "EURUSD", "BUY", "17000694512")
    results["exness_parsing"]["P3_accepted_not_yet_filled"] = (p3["normalized_status"] == "ACCEPTED_NOT_FILLED")

    # P4: Pending operation
    p4 = norm_fn({
        "status": "PENDING",
        "operation_id": "379900000000000004",
        "operation": {"operation_id": "379900000000000004", "status": "pending"},
        "payload": {"instrument": "EURUSD", "side": "buy", "volume": "0.03"},
    }, "EURUSD", "BUY", "17000694512")
    results["exness_parsing"]["P4_pending_operation"] = (p4["normalized_status"] == "PENDING_OPERATION")

    # P5: Rejected response
    p5 = norm_fn({
        "status": "REJECTED",
        "http_status": 400,
        "error": {"code": "INSUFFICIENT_MARGIN", "message": "Not enough free margin"},
        "payload": {"instrument": "EURUSD", "side": "buy", "volume": "0.03"},
    }, "EURUSD", "BUY", "17000694512")
    results["exness_parsing"]["P5_rejected_response"] = (p5["normalized_status"] == "REJECTED")

    # P6: Partial fill & P7: Multiple deal records (with duplicate deal_ticket deduplication)
    partial_multi_payload = {
        "status": "FILLED",
        "operation_id": "379900000000000006",
        "operation": {
            "operation_id": "379900000000000006",
            "status": "confirmed",
            "position_id": "75100006",
            "order_id": "154100006",
            "instrument": "EURUSD",
            "side": "buy",
            "deals": [
                {"deal_id": "D-601", "position_id": "75100006", "order_id": "154100006", "price": 1.08100, "volume": 0.01},
                {"deal_id": "D-602", "position_id": "75100006", "order_id": "154100006", "price": 1.08130, "volume": 0.01},
                {"deal_id": "D-602", "position_id": "75100006", "order_id": "154100006", "price": 1.08130, "volume": 0.01},  # duplicate deal
            ],
            "updated_at": now_iso,
        },
        "payload": {"instrument": "EURUSD", "side": "buy", "volume": "0.03"},
    }
    p6 = norm_fn(partial_multi_payload, "EURUSD", "BUY", "17000694512", 1.08100)
    results["exness_parsing"]["P6_partial_fill_recognized"] = (
        p6["normalized_status"] == "CONFIRMED_PARTIAL_FILL"
        and p6["is_partial_fill"] is True
        and p6["requested_volume"] == 0.03
        and p6["filled_volume"] == 0.02
    )
    results["exness_parsing"]["P7_multiple_deals_vwap_and_dedup"] = (
        p6["fill_price"] == 1.08115 and p6["deal_ids"] == ["D-601", "D-602"]
    )

    # P8: Missing ticket (only operation_id present -> must NOT use operation_id as ticket!)
    p8 = norm_fn({
        "status": "FILLED",
        "operation_id": "379900000000000008",
        "operation": {
            "operation_id": "379900000000000008",
            "status": "confirmed",
            "order_id": "154100008",
            "instrument": "EURUSD",
            "side": "buy",
            "fill_price": 1.08110,
            "filled_volume": 0.03,
        },
        "payload": {"instrument": "EURUSD", "side": "buy", "volume": "0.03"},
    }, "EURUSD", "BUY", "17000694512")
    results["exness_parsing"]["P8_missing_ticket_rejected_as_ambiguous"] = (
        p8["normalized_status"] == "AMBIGUOUS" and p8["error_code"] == "MISSING_BROKER_TICKET"
    )

    # P9: Missing genuine order_id (only position_id and operation_id present -> must NOT copy either into order_id!)
    p9 = norm_fn({
        "status": "FILLED",
        "operation_id": "379900000000000009",
        "operation": {
            "operation_id": "379900000000000009",
            "status": "confirmed",
            "position_id": "75100009",
            "instrument": "EURUSD",
            "side": "buy",
            "fill_price": 1.08110,
            "filled_volume": 0.03,
        },
        "payload": {"instrument": "EURUSD", "side": "buy", "volume": "0.03"},
    }, "EURUSD", "BUY", "17000694512")
    results["exness_parsing"]["P9_missing_genuine_order_id_rejected_as_ambiguous"] = (
        p9["normalized_status"] == "AMBIGUOUS" and p9["error_code"] == "MISSING_GENUINE_ORDER_ID"
    )

    # P10: Missing fill price
    p10 = norm_fn({
        "status": "FILLED",
        "operation_id": "379900000000000010",
        "operation": {
            "operation_id": "379900000000000010",
            "status": "confirmed",
            "position_id": "75100010",
            "order_id": "154100010",
            "instrument": "EURUSD",
            "side": "buy",
            "filled_volume": 0.03,
        },
        "payload": {"instrument": "EURUSD", "side": "buy", "volume": "0.03"},
    }, "EURUSD", "BUY", "17000694512")
    results["exness_parsing"]["P10_missing_fill_price_rejected_as_ambiguous"] = (
        p10["normalized_status"] == "AMBIGUOUS" and p10["error_code"] == "MISSING_CONFIRMED_FILL_PRICE_OR_VOLUME"
    )

    # P11: Wrong instrument (XAUUSD instead of EURUSD)
    p11 = norm_fn({
        "status": "FILLED",
        "operation_id": "379900000000000011",
        "operation": {
            "operation_id": "379900000000000011",
            "status": "confirmed",
            "position_id": "75100011",
            "order_id": "154100011",
            "instrument": "XAUUSD",
            "side": "buy",
            "fill_price": 3880.0,
            "filled_volume": 0.01,
        },
        "payload": {"instrument": "XAUUSD", "side": "buy", "volume": "0.01"},
    }, "EURUSD", "BUY", "17000694512")
    results["exness_parsing"]["P11_wrong_instrument_rejected"] = (
        p11["normalized_status"] == "MALFORMED_OR_CONTRADICTORY" and p11["error_code"] == "WRONG_INSTRUMENT"
    )

    # P12: Wrong account
    p12 = norm_fn({
        "status": "FILLED",
        "account_id": "16000629657",
        "operation_id": "379900000000000012",
        "operation": {
            "operation_id": "379900000000000012",
            "status": "confirmed",
            "position_id": "75100012",
            "order_id": "154100012",
            "instrument": "EURUSD",
            "side": "buy",
            "fill_price": 1.08110,
            "filled_volume": 0.03,
        },
        "payload": {"instrument": "EURUSD", "side": "buy", "volume": "0.03"},
    }, "EURUSD", "BUY", "17000694512")
    results["exness_parsing"]["P12_wrong_account_rejected"] = (
        p12["normalized_status"] == "MALFORMED_OR_CONTRADICTORY" and p12["error_code"] == "ACCOUNT_OWNERSHIP_MISMATCH"
    )

    # P13: Malformed nested response
    p13 = norm_fn({"status": "FILLED", "operation_id": "123", "operation": "NOT_A_DICT"}, "EURUSD", "BUY", "17000694512")
    results["exness_parsing"]["P13_malformed_nested_response_rejected"] = (
        p13["normalized_status"] == "MALFORMED_OR_CONTRADICTORY" and p13["error_code"] == "MISSING_OPERATION_DICT"
    )

    # P14: Contradictory response fields (top status FILLED but operation.status rejected)
    p14 = norm_fn({
        "status": "FILLED",
        "operation_id": "379900000000000014",
        "operation": {"operation_id": "379900000000000014", "status": "rejected"},
        "payload": {"instrument": "EURUSD", "side": "buy", "volume": "0.03"},
    }, "EURUSD", "BUY", "17000694512")
    results["exness_parsing"]["P14_contradictory_response_fields_rejected"] = (
        p14["normalized_status"] == "MALFORMED_OR_CONTRADICTORY" and p14["error_code"] == "CONTRADICTORY_FILLED_AND_REJECTED"
    )

    # =========================================================================
    # 3. REAL TRADEMEMORY SERVICE INTEGRATION TESTS (Remediation C-1)
    # =========================================================================
    acc_tm = "17000694512_TM"
    sup_tm = runner.OperatorExperimentSupervisor()
    sig_tm = {
        "strategy": "LT_STRUCTURE_EURUSD_A2",
        "engine_type": "LONG_TERM",
        "strategy_version": "2.0",
        "symbol": "EURUSD",
        "side": "BUY",
        "volume": 0.03,
        "entry_price": 1.08100,
        "sl_price": 1.07800,
        "tp_price": 1.08850,
        "leg_id": "BUY:1.07200:1.08200",
        "reason": "TM integration test",
    }

    # TM1: Real TradeMemoryService accepts valid genuine broker_ticket + order_id + deal_id
    valid_tm_payload = {
        "status": "FILLED",
        "operation_id": "379900000000000101",
        "operation": {
            "operation_id": "379900000000000101",
            "status": "confirmed",
            "position_id": "75200101",
            "order_id": "154200101",
            "deal_id": "151200101",
            "instrument": "EURUSD",
            "side": "buy",
            "fill_price": 1.08105,
            "filled_volume": 0.03,
            "updated_at": now_iso,
        },
        "payload": {"instrument": "EURUSD", "side": "buy", "volume": "0.03"},
    }
    tm1_res = sup_tm.process_broker_fill_response(valid_tm_payload, sig_tm, 1.07800, 1.08850, now_iso, acc_tm)
    tm_rows = TradeMemoryService.get_trade_history(account_id=acc_tm, track="LT_STRUCTURE_EURUSD_A2", limit=10)
    results["trade_memory"]["TM1_real_service_accepts_genuine_order_id"] = (
        tm1_res["status"] == "CONFIRMED_AND_PROTECTED"
        and tm1_res["recorded"] is True
        and len(tm_rows) == 1
        and tm_rows[0]["broker_ticket"] == "75200101"
        and tm_rows[0]["order_id"] == "154200101"
        and tm_rows[0]["deal_id"] == "151200101"
    )

    # TM2: Duplicate broker_ticket is idempotent (across same or new supervisor instance via SQLite check)
    sup_tm_new = runner.OperatorExperimentSupervisor()
    tm2_res = sup_tm_new.process_broker_fill_response(valid_tm_payload, sig_tm, 1.07800, 1.08850, now_iso, acc_tm)
    tm_rows_after_dup = TradeMemoryService.get_trade_history(account_id=acc_tm, track="LT_STRUCTURE_EURUSD_A2", limit=10)
    results["trade_memory"]["TM2_duplicate_broker_ticket_idempotent"] = (
        tm2_res["status"] == "DUPLICATE_FILL_IGNORED" and tm2_res["recorded"] is False and len(tm_rows_after_dup) == 1
    )

    # TM3: Duplicate deal_id with different ticket is also caught idempotently
    dup_deal_payload = {
        "status": "FILLED",
        "operation_id": "379900000000000102",
        "operation": {
            "operation_id": "379900000000000102",
            "status": "confirmed",
            "position_id": "75200102",
            "order_id": "154200102",
            "deal_id": "151200101",  # same deal_id as TM1
            "instrument": "EURUSD",
            "side": "buy",
            "fill_price": 1.08105,
            "filled_volume": 0.03,
            "updated_at": now_iso,
        },
        "payload": {"instrument": "EURUSD", "side": "buy", "volume": "0.03"},
    }
    tm3_res = sup_tm.process_broker_fill_response(dup_deal_payload, sig_tm, 1.07800, 1.08850, now_iso, acc_tm)
    results["trade_memory"]["TM3_duplicate_deal_id_idempotent"] = (
        tm3_res["status"] == "DUPLICATE_FILL_IGNORED" and tm3_res["recorded"] is False
    )

    # TM4: Missing order_id fails safely (no fake identifier created, no TradeMemory row added, new_entries_disabled=True)
    sup_tm_missing_oid = runner.OperatorExperimentSupervisor()
    missing_oid_payload = {
        "status": "FILLED",
        "operation_id": "379900000000000103",
        "operation": {
            "operation_id": "379900000000000103",
            "status": "confirmed",
            "position_id": "75200103",
            "instrument": "EURUSD",
            "side": "buy",
            "fill_price": 1.08105,
            "filled_volume": 0.03,
        },
        "payload": {"instrument": "EURUSD", "side": "buy", "volume": "0.03"},
    }
    tm4_res = sup_tm_missing_oid.process_broker_fill_response(missing_oid_payload, sig_tm, 1.07800, 1.08850, now_iso, acc_tm)
    tm_rows_after_missing = TradeMemoryService.get_trade_history(account_id=acc_tm, track="LT_STRUCTURE_EURUSD_A2", limit=10)
    results["trade_memory"]["TM4_missing_order_id_fails_safely_no_fake_ids"] = (
        tm4_res["recorded"] is False
        and tm4_res["new_entries_disabled"] is True
        and len(tm_rows_after_missing) == 1
    )

    # =========================================================================
    # 4. POST-FILL FAIL-CLOSED EXCEPTION HANDLING TESTS (Remediation C-2)
    # =========================================================================
    # PF1: Mandatory sequence from Command 15 Section 6:
    # - Broker response represents a confirmed fill
    # - PostFillRiskBreachGuard evaluates the fill
    # - TradeMemoryService.record_trade() raises an exception
    # - Persistent state update is also tested for failure
    acc_pf = "17000694512_PF"
    sup_pf = runner.OperatorExperimentSupervisor()
    sig_pf = dict(sig_tm, leg_id="BUY:1.07300:1.08300")
    pf1_payload = {
        "status": "FILLED",
        "operation_id": "379900000000000201",
        "operation": {
            "operation_id": "379900000000000201",
            "status": "confirmed",
            "position_id": "75300201",
            "order_id": "154300201",
            "deal_id": "151300201",
            "instrument": "EURUSD",
            "side": "buy",
            "fill_price": 1.08105,
            "filled_volume": 0.03,
            "updated_at": now_iso,
        },
        "payload": {"instrument": "EURUSD", "side": "buy", "volume": "0.03"},
    }
    with patch.object(TradeMemoryService, "record_trade", side_effect=sqlite3.OperationalError("SQLite disk I/O error")):
        pf1_res = sup_pf.process_broker_fill_response(pf1_payload, sig_pf, 1.07800, 1.08850, now_iso, acc_pf)
    # Verify: fill recognized, new entries disabled, critical incident recorded with broker identifiers, leg confirmed on disk, duplicate call ignored
    pf1_dup = sup_pf.process_broker_fill_response(pf1_payload, sig_pf, 1.07800, 1.08850, now_iso, acc_pf)
    results["post_fill_failures"]["PF1_tradememory_exception_disables_entries_and_retains_ids"] = (
        pf1_res["fill_recognized"] is True
        and pf1_res["ticket"] == "75300201"
        and pf1_res["order_id"] == "154300201"
        and pf1_res["new_entries_disabled"] is True
        and pf1_res["leg_state_saved"] is True
        and pf1_res["errors"]["trade_memory_error"] is not None
        and any(inc["incident_code"] == "POST_FILL_TRADEMEMORY_RECORD_FAILURE" and inc["context"]["broker_ticket"] == "75300201" for inc in sup_pf.critical_incidents)
        and pf1_dup["status"] == "DUPLICATE_FILL_IGNORED"
    )

    # PF2: Both TradeMemoryService.record_trade() AND confirm_a2_leg_fill() fail after confirmed fill
    sup_pf2 = runner.OperatorExperimentSupervisor()
    pf2_payload = {
        "status": "FILLED",
        "operation_id": "379900000000000202",
        "operation": {
            "operation_id": "379900000000000202",
            "status": "confirmed",
            "position_id": "75300202",
            "order_id": "154300202",
            "deal_id": "151300202",
            "instrument": "EURUSD",
            "side": "buy",
            "fill_price": 1.08105,
            "filled_volume": 0.03,
            "updated_at": now_iso,
        },
        "payload": {"instrument": "EURUSD", "side": "buy", "volume": "0.03"},
    }
    with patch.object(TradeMemoryService, "record_trade", side_effect=RuntimeError("DB locked")), \
         patch.object(sup_pf2, "confirm_a2_leg_fill", side_effect=OSError("Disk full")):
        pf2_res = sup_pf2.process_broker_fill_response(pf2_payload, sig_pf, 1.07800, 1.08850, now_iso, acc_pf)
    results["post_fill_failures"]["PF2_state_and_tm_exceptions_fail_closed_with_incident"] = (
        pf2_res["fill_recognized"] is True
        and pf2_res["new_entries_disabled"] is True
        and pf2_res["errors"]["state_error"] is not None
        and pf2_res["errors"]["trade_memory_error"] is not None
        and len(sup_pf2.critical_incidents) == 2
    )

    # PF3: PostFillRiskBreachGuard raises unexpected exception -> fails closed (new_entries_disabled = True)
    sup_pf3 = runner.OperatorExperimentSupervisor()
    sup_pf3.ensure_post_fill_guard()
    pf3_payload = {
        "status": "FILLED",
        "operation_id": "379900000000000203",
        "operation": {
            "operation_id": "379900000000000203",
            "status": "confirmed",
            "position_id": "75300203",
            "order_id": "154300203",
            "deal_id": "151300203",
            "instrument": "EURUSD",
            "side": "buy",
            "fill_price": 1.08105,
            "filled_volume": 0.03,
            "updated_at": now_iso,
        },
        "payload": {"instrument": "EURUSD", "side": "buy", "volume": "0.03"},
    }
    with patch.object(sup_pf3.post_fill_guard, "evaluate_fill", side_effect=RuntimeError("Guard internal error")):
        pf3_res = sup_pf3.process_broker_fill_response(pf3_payload, sig_pf, 1.07800, 1.08850, now_iso, acc_pf)
    results["post_fill_failures"]["PF3_guard_exception_fails_closed"] = (
        pf3_res["fill_recognized"] is True
        and pf3_res["new_entries_disabled"] is True
        and pf3_res["errors"]["guard_error"] is not None
    )

    # PF4: Partial-fill reconciliation failure (missing deal_id in partial fill list) disables new entries
    sup_pf4 = runner.OperatorExperimentSupervisor()
    bad_partial_payload = {
        "status": "FILLED",
        "operation_id": "379900000000000204",
        "operation": {
            "operation_id": "379900000000000204",
            "status": "confirmed",
            "position_id": "75300204",
            "order_id": "154300204",
            "instrument": "EURUSD",
            "side": "buy",
            "deals": [{"price": 1.08100, "volume": 0.01}],  # missing deal_id!
        },
        "payload": {"instrument": "EURUSD", "side": "buy", "volume": "0.03"},
    }
    pf4_res = sup_pf4.process_broker_fill_response(bad_partial_payload, sig_pf, 1.07800, 1.08850, now_iso, acc_pf)
    results["post_fill_failures"]["PF4_partial_fill_incomplete_reconciliation_disables_entries"] = (
        pf4_res["recorded"] is False and pf4_res["new_entries_disabled"] is True
    )

    # PF5: Partial-fill risk breach trips PostFillRiskBreachGuard and records actual filled volume (not requested volume)
    sup_pf5 = runner.OperatorExperimentSupervisor()
    breach_partial_payload = {
        "status": "FILLED",
        "operation_id": "379900000000000205",
        "operation": {
            "operation_id": "379900000000000205",
            "status": "confirmed",
            "position_id": "75300205",
            "order_id": "154300205",
            "instrument": "EURUSD",
            "side": "buy",
            "deals": [
                {"deal_id": "D-205A", "position_id": "75300205", "order_id": "154300205", "price": 1.08300, "volume": 0.02},
                {"deal_id": "D-205B", "position_id": "75300205", "order_id": "154300205", "price": 1.08400, "volume": 0.01},
            ],
            "updated_at": now_iso,
        },
        "payload": {"instrument": "EURUSD", "side": "buy", "volume": "0.04"},
    }
    pf5_res = sup_pf5.process_broker_fill_response(breach_partial_payload, sig_pf, 1.07800, 1.08850, now_iso, acc_pf)
    results["post_fill_failures"]["PF5_partial_fill_uses_filled_volume_and_trips_guard_on_breach"] = (
        pf5_res["status"] == "POST_FILL_RISK_BREACH_NEW_ENTRIES_DISABLED"
        and pf5_res["is_partial_fill"] is True
        and pf5_res["fill_volume"] == 0.03
        and pf5_res["requested_volume"] == 0.04
        and pf5_res["new_entries_disabled"] is True
        and pf5_res["recorded"] is True
    )

    # =========================================================================
    # 5. REGRESSION & SAFETY VERIFICATION
    # =========================================================================
    def _sha256(p):
        with open(p, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    a2_sha = _sha256("/opt/bitdex-research-v2/strategies/eurusd_structure_a2.py")
    a2_frozen_sha = _sha256("/opt/bitdex-research-v2/strategies/eurusd_structure_a2.frozen_v2_0.py")
    results["regression"]["R1_frozen_a2_sha256_unchanged"] = (
        a2_sha == "231e0259c0a0a514537c5efef03139d2b4d5895c07ad8350164c3a04f2b19032"
        and a2_frozen_sha == "231e0259c0a0a514537c5efef03139d2b4d5895c07ad8350164c3a04f2b19032"
    )

    # R2: Closed-candle filtering still enforced
    h1_forming_test = [
        {"timestamp": "2026-11-18T10:00:00Z", "bid_open": 1.08, "bid_high": 1.082, "bid_low": 1.079, "bid_close": 1.081, "ask_open": 1.0801, "ask_high": 1.0821, "ask_low": 1.0791, "ask_close": 1.0811},
        {"timestamp": "2026-11-18T11:30:00Z", "bid_open": 1.08, "bid_high": 1.082, "bid_low": 1.079, "bid_close": 1.081, "ask_open": 1.0801, "ask_high": 1.0821, "ask_low": 1.0791, "ask_close": 1.0811},  # forming at 12:00:00Z
    ]
    filtered_h1 = runner.OperatorExperimentSupervisor.filter_closed_candles(h1_forming_test, 3600, now_dt, is_d1=False)
    results["regression"]["R2_closed_candle_filtering_enforced"] = (len(filtered_h1) == 1 and filtered_h1[0]["time"] == "2026-11-18T10:00:00Z")

    # R3: Tenant/account isolation between two accounts
    acc_iso_a = "17000694512_ISO_A"
    acc_iso_b = "17000109575_ISO_B"
    runner.OperatorExperimentSupervisor.save_a2_leg_state(acc_iso_a, "BUY:1.07000:1.08000")
    runner.OperatorExperimentSupervisor.save_a2_leg_state(acc_iso_b, None, state="AVAILABLE")
    ok_a, leg_a = runner.OperatorExperimentSupervisor.load_a2_leg_state(acc_iso_a)
    ok_b, leg_b = runner.OperatorExperimentSupervisor.load_a2_leg_state(acc_iso_b)
    results["regression"]["R3_tenant_account_isolation"] = (ok_a and leg_a == "BUY:1.07000:1.08000" and ok_b and leg_b is None)

    # Safety checks on live staging files
    with open("/opt/tauric-platform-staging/backend/data/experiment_lock.json", "r") as f:
        lock_data = json.load(f)
    import app.services.strategy_registry_service as srs
    a2_reg = srs.get_strategy_for_customer("LT_STRUCTURE_EURUSD_A2", "USR-ADM-B022F490")

    results["safety"] = {
        "experiment_lock_authorized_false": (lock_data.get("authorized") is False),
        "real_trading_permanently_locked": (runner.REAL_TRADING_PERMANENTLY_LOCKED is True and REAL_TRADING_PERMANENTLY_LOCKED is True),
        "real_account_16000629657_blocked": ((await SharedCentralRiskManager.preflight_check(None, "16000629657", None, "EURUSD", "BUY", 0.01, 1.08, 1.077, "LONG_TERM", True))[0] is False),
        "a2_execution_eligible_false": (a2_reg.get("execution_eligible") is False),
        "orig_runner_sha256": _sha256("/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py.bak_cmd15_20261118"),
        "final_runner_sha256": _sha256("/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py"),
        "frozen_a2_sha256": a2_sha,
    }

    all_passed = all(
        all(bool(v) for v in group.values())
        for k, group in results.items()
        if k != "safety"
    ) and all(
        bool(results["safety"][k])
        for k in ("experiment_lock_authorized_false", "real_trading_permanently_locked", "real_account_16000629657_blocked", "a2_execution_eligible_false")
    )

    results["verdict"] = (
        "COMMAND 15 PASSED — FILL HANDLING VERIFIED — EXECUTION DISABLED"
        if all_passed else
        "COMMAND 15 FAILED — EXECUTION DISABLED"
    )
    return results


if __name__ == "__main__":
    try:
        out = asyncio.run(run_all_tests())
        with open("/opt/bitdex-research-v2/docs/cmd15_fill_handling_verification.json", "w") as f:
            json.dump(out, f, indent=2)
        print(json.dumps(out, indent=2))
        if not out["verdict"].startswith("COMMAND 15 PASSED"):
            sys.exit(1)
    finally:
        shutil.rmtree(TEST_TMP_DIR, ignore_errors=True)
