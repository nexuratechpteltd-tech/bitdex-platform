"""
Tauric Platform — Macroeconomic Calendar and News-Analysis Test Suite
Phase: Macroeconomic Calendar and News-Analysis Integration Repair
Environment: Staging Only (/opt/tauric-platform-staging/)
Zero-live trading, read-only mode, and fail-closed safety verification.
"""

import sys
import os
import asyncio
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

# Ensure staging backend path is on sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "backend"))

from app.config import settings
from app.services.finance_calendar_adapter import (
    finance_calendar_adapter,
    FinanceCalendarAdapter,
    NormalizedEconomicEvent,
    FINANCE_CALENDAR_SPECS,
    MOCK_FINANCE_CALENDAR_FIXTURES
)
from app.services.snapshot_engine import snapshot_engine, compute_snapshot_hash
from app.services.dual_ai_engine import DualAIEngine


class TestResults:
    passed = 0
    failed = 0
    errors = []

    @classmethod
    def assert_true(cls, cond: bool, msg: str):
        if cond:
            cls.passed += 1
            print(f"  [PASS] {msg}")
        else:
            cls.failed += 1
            cls.errors.append(msg)
            print(f"  [FAIL] {msg}")

    @classmethod
    def assert_equal(cls, actual: Any, expected: Any, msg: str):
        if actual == expected:
            cls.passed += 1
            print(f"  [PASS] {msg}")
        else:
            cls.failed += 1
            err = f"{msg} (Expected: {expected}, Got: {actual})"
            cls.errors.append(err)
            print(f"  [FAIL] {err}")


async def test_suite():
    print("=" * 70)
    print("TAURIC MACROECONOMIC CALENDAR & NEWS INTEGRATION VERIFICATION")
    print(f"Execution Timestamp: {datetime.now(timezone.utc).isoformat()} UTC")
    print("=" * 70)

    # ─────────────────────────────────────────────────────────────────
    print("\n[1] TEST: Provider Specifications, Terms & Mandatory Attribution")
    specs = finance_calendar_adapter.get_provider_specs()
    TestResults.assert_equal(specs["provider_name"], "Finance Calendar", "Provider name is Finance Calendar")
    TestResults.assert_equal(specs["attribution_required"], True, "Attribution is required by provider terms")
    TestResults.assert_equal(
        specs["approved_attribution_text"],
        "Economic calendar data provided by Finance Calendar",
        "Exact required attribution text matches"
    )
    TestResults.assert_equal(
        specs["approved_attribution_link"],
        "https://www.financecalendar.com",
        "Attribution links to official provider site"
    )
    TestResults.assert_equal(specs["commercial_use_permitted"], True, "Commercial use permitted with attribution")

    # ─────────────────────────────────────────────────────────────────
    print("\n[2] TEST: Timezone Invariants & Canonical UTC / PKT Formatting")
    now_utc = datetime.now(timezone.utc)
    dt, ts_ms, utc_str, pkt_str = FinanceCalendarAdapter._parse_timestamp("2026-10-28T18:00:00+00:00")
    TestResults.assert_true(dt is not None, "Parsed valid UTC timestamp")
    TestResults.assert_equal(utc_str, "2026-10-28T18:00:00+00:00", "Canonical UTC representation preserved")
    TestResults.assert_equal(pkt_str, "2026-10-28 23:00:00 PKT", "PKT presentation string is exactly UTC + 5h")

    # Invalid timestamp handling
    dt_inv, ts_inv, _, _ = FinanceCalendarAdapter._parse_timestamp("invalid-date-string")
    TestResults.assert_true(dt_inv is None and ts_inv is None, "Malformed timestamp rejected safely without crash")

    # ─────────────────────────────────────────────────────────────────
    print("\n[3] TEST: Payload Parsing Robustness (List vs Dict unwrapping)")
    raw_dict_payload = {
        "from": "2026-10-22",
        "to": "2026-11-05",
        "count": 2,
        "events": MOCK_FINANCE_CALENDAR_FIXTURES[:2],
        "attribution": {"source": "financecalendar.com"}
    }
    parsed_from_dict = finance_calendar_adapter.parse_events(raw_dict_payload)
    TestResults.assert_equal(len(parsed_from_dict), 2, "parse_events correctly unwraps dict with 'events' key")

    parsed_from_list = finance_calendar_adapter.parse_events(MOCK_FINANCE_CALENDAR_FIXTURES[:2])
    TestResults.assert_equal(len(parsed_from_list), 2, "parse_events correctly handles raw list")

    # ─────────────────────────────────────────────────────────────────
    print("\n[4] TEST: Event-Specific Actual vs Forecast Heuristic Interpretation")
    # Rate Decision surprise hike
    hike_interp = FinanceCalendarAdapter.interpret_actual_vs_forecast(
        series_code="fomc", actual=5.50, forecast=5.25, previous=5.25, currency="USD"
    )
    TestResults.assert_equal(hike_interp["currency_bias"], "BULLISH", "Rate hike surprise is Bullish for USD")
    TestResults.assert_equal(hike_interp["crypto_bias"], "BEARISH", "Rate hike surprise is Bearish for Crypto")

    # Inflation cool-down
    cpi_cool = FinanceCalendarAdapter.interpret_actual_vs_forecast(
        series_code="us-cpi", actual=2.9, forecast=3.1, previous=3.4, currency="USD"
    )
    TestResults.assert_equal(cpi_cool["currency_bias"], "BEARISH", "Below-consensus inflation is Bearish for USD")
    TestResults.assert_equal(cpi_cool["crypto_bias"], "BULLISH", "Below-consensus inflation is Bullish for Crypto")

    # Unmapped series rejection
    unmapped = FinanceCalendarAdapter.interpret_actual_vs_forecast(
        series_code="some-obscure-indicator", actual=100.0, forecast=90.0
    )
    TestResults.assert_equal(unmapped["status"], "UNKNOWN", "Unmapped series rejects blunt heuristic with UNKNOWN")

    # Ambiguous multi-channel series
    ambiguous = FinanceCalendarAdapter.interpret_actual_vs_forecast(
        series_code="crude-oil-stocks", actual=2.5, forecast=1.0
    )
    TestResults.assert_equal(ambiguous["status"], "MIXED", "Multi-channel indicator classified as MIXED")

    # ─────────────────────────────────────────────────────────────────
    print("\n[5] TEST: Fail-Closed Safety Gate & Event Risk Statuses")
    # 5a. Disabled adapter check
    disabled_adapter = FinanceCalendarAdapter(enabled=False)
    risk_disabled = disabled_adapter.evaluate_event_risk("BTCUSDT")
    TestResults.assert_equal(risk_disabled["event_risk_status"], "UNKNOWN", "Disabled adapter returns UNKNOWN risk")
    TestResults.assert_equal(risk_disabled["is_blackout"], False, "Disabled adapter does not falsely claim blackout")

    # 5b. Active blackout window check
    active_adapter = FinanceCalendarAdapter(enabled=True)
    target_time_ms = int(datetime.fromisoformat("2026-10-28T18:00:00+00:00").timestamp() * 1000)
    active_adapter.load_mock_fixtures(MOCK_FINANCE_CALENDAR_FIXTURES)
    
    # Check 10 minutes before FOMC
    risk_blackout = active_adapter.evaluate_event_risk("BTCUSDT", current_time_ms=target_time_ms - (10 * 60 * 1000))
    TestResults.assert_equal(risk_blackout["event_risk_status"], "BLACKOUT", "High impact event in window triggers BLACKOUT")
    TestResults.assert_equal(risk_blackout["is_blackout"], True, "is_blackout is True during FOMC window")
    TestResults.assert_equal(risk_blackout["recommendation"], "SUSPEND_ENTRY", "Recommends SUSPEND_ENTRY during blackout")

    # Check clear window (e.g. 2 hours after event)
    risk_clear = active_adapter.evaluate_event_risk("BTCUSDT", current_time_ms=target_time_ms + (120 * 60 * 1000))
    TestResults.assert_equal(risk_clear["event_risk_status"], "CLEAR", "Outside window returns CLEAR")
    TestResults.assert_equal(risk_clear["is_blackout"], False, "is_blackout is False outside window")

    # ─────────────────────────────────────────────────────────────────
    print("\n[6] TEST: Live Ingestion & Summary Contract")
    events = await finance_calendar_adapter.fetch_events(days_ahead=14, force=True)
    TestResults.assert_true(len(events) > 0, f"Successfully fetched live/cached events ({len(events)} events)")
    summary = finance_calendar_adapter.get_calendar_summary()
    TestResults.assert_equal(summary["provider"], "Finance Calendar", "Summary has provider name")
    TestResults.assert_equal(summary["status"], "AVAILABLE", "Summary reports AVAILABLE status")
    TestResults.assert_true("events" in summary and len(summary["events"]) > 0, "Summary contains 14-day events list")
    TestResults.assert_true("PKT" in summary["last_retrieval_pkt"], "Summary last_retrieval_pkt contains PKT timezone")

    # ─────────────────────────────────────────────────────────────────
    print("\n[7] TEST: Frozen Snapshot Engine Event Risk Inclusion")
    snapshot = await snapshot_engine.create_snapshot("BTCUSDT")
    cal_snap = snapshot.get("calendar", {})
    TestResults.assert_true("provider" in cal_snap, "Snapshot contains calendar.provider")
    TestResults.assert_true("event_risk_status" in cal_snap, "Snapshot contains calendar.event_risk_status")
    TestResults.assert_true("is_blackout" in cal_snap, "Snapshot contains calendar.is_blackout")
    TestResults.assert_true("attribution_approved" in cal_snap, "Snapshot carries approved provider attribution")

    # ─────────────────────────────────────────────────────────────────
    print("\n[8] TEST: Dual-AI News-Aware Reasoning (Tauric & JeV)")
    dual_engine = DualAIEngine()
    
    # Test Blackout veto in reconciliation
    blackout_snapshot = snapshot.copy()
    blackout_snapshot["calendar"] = {
        "provider": "Finance Calendar",
        "provider_status": "AVAILABLE",
        "event_risk_status": "BLACKOUT",
        "is_blackout": True,
        "policy": "EVENT_BLACKOUT"
    }
    tauric_res = await dual_engine.evaluate_tauric_independent(blackout_snapshot)
    jev_res = await dual_engine.evaluate_jev_independent(blackout_snapshot)
    
    TestResults.assert_true(
        any("blackout" in str(c).lower() for c in tauric_res.get("contradicting_evidence", [])),
        "Tauric independent evaluation notes active blackout window in contradicting evidence"
    )
    TestResults.assert_true(
        any("blackout" in str(c).lower() for c in jev_res.get("contradicting_evidence", [])),
        "JeV independent evaluation notes active blackout window in contradicting evidence"
    )

    reconciled = dual_engine.reconcile_evaluations(blackout_snapshot, tauric_res, jev_res)
    TestResults.assert_equal(reconciled["reconciliation_outcome"], "WAIT", "Reconciliation halts on active blackout window")
    TestResults.assert_true(
        any("blackout" in str(v).lower() for v in reconciled.get("veto_reasons", [])),
        "Reconciliation veto reasons explicitly cites active blackout window"
    )

    # ─────────────────────────────────────────────────────────────────
    print("\n[9] TEST: Hard Live-Trading Lock & Read-Only Safety Enforcements")
    TestResults.assert_equal(settings.live_trading_locked, True, "settings.live_trading_locked is True")
    TestResults.assert_equal(settings.read_only_mode, True, "settings.read_only_mode is True")

    # ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print(f"TEST SUMMARY: {TestResults.passed} PASSED, {TestResults.failed} FAILED")
    print("=" * 70)

    if TestResults.failed > 0:
        print("\nFAILURES:")
        for err in TestResults.errors:
            print(f"  - {err}")
        return 1
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(test_suite())
    sys.exit(exit_code)
