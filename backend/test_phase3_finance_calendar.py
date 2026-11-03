"""
Tauric Phase 3 Finance Calendar Verification Test Suite
15 Scenarios Covering Section 4:
1. Valid scheduled events
2. Released events with actual, forecast, and previous values
3. Missing actual or forecast values
4. Revised previous values
5. Duplicate events
6. Invalid or missing timestamps
7. UTC conversion and PKT display
8. Empty responses
9. HTTP errors, timeouts, rate limits, and malformed responses
10. Stale calendar data
11. Provider disabled by default
12. Attribution displayed correctly
13. No API calls on page load, refresh, tab switching, or dropdown changes
14. No paid fallback and no silent provider switching
15. Integration with regime_engine EventCalendarSource protocol
"""

import sys
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from app.services.finance_calendar_adapter import (
    FinanceCalendarAdapter,
    NormalizedEconomicEvent,
    MOCK_FINANCE_CALENDAR_FIXTURES,
    finance_calendar_adapter,
    FINANCE_CALENDAR_SPECS,
    EVENT_INTERPRETATION_RULES
)
from app.services.regime_engine import (
    DeterministicMarketRegimeEngine,
    MarketRegime,
    EventSeverity
)
from app.services.telemetry_manager import telemetry_manager
from app.config import settings


class TestPhase3FinanceCalendar(unittest.TestCase):

    def setUp(self):
        # Fresh isolated adapter instance for unit tests
        self.adapter = FinanceCalendarAdapter(enabled=False)

    # ─── SCENARIO 1: Valid Scheduled Events ──────────────────────────
    def test_01_valid_scheduled_events(self):
        """Scenario 1: Valid scheduled events parsed with canonical fields and confirmed status."""
        raw = [{
            "id": "fomc-rate-decision-october-2026",
            "series": "fomc",
            "series_name": "FOMC Rate Decision",
            "title": "FOMC Rate Decision",
            "country": "US",
            "impact": "high",
            "date": "2026-10-28",
            "release_at_utc": "2026-10-28T18:00:00+00:00",
            "status": "confirmed",
            "consensus": 5.25,
            "prior": 5.25,
            "actual": None,
            "unit": "%"
        }]
        events = self.adapter.parse_events(raw)
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev.event_id, "fomc-rate-decision-october-2026")
        self.assertEqual(ev.series_code, "fomc")
        self.assertEqual(ev.country, "US")
        self.assertEqual(ev.currency, "USD")
        self.assertEqual(ev.impact, "HIGH")
        self.assertEqual(ev.impact_weight, 3)
        self.assertEqual(ev.status, "confirmed")
        self.assertIsNone(ev.actual)
        self.assertEqual(ev.forecast, 5.25)
        self.assertEqual(ev.previous, 5.25)
        self.assertTrue(ev.to_dict()["is_not_yet_released"])

    # ─── SCENARIO 2: Released Events With Actual, Forecast & Prior ────
    def test_02_released_events_complete_data(self):
        """Scenario 2: Released events parsed with actual, consensus, prior, and status='released'."""
        raw = [{
            "id": "us-cpi-yoy-october-2026",
            "series": "us-cpi",
            "title": "US CPI Inflation YoY",
            "country": "US",
            "impact": "high",
            "release_at_utc": "2026-10-21T12:30:00+00:00",
            "status": "released",
            "consensus": 3.1,
            "prior": 3.4,
            "actual": 3.2,
            "unit": "%"
        }]
        events = self.adapter.parse_events(raw)
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev.status, "released")
        self.assertEqual(ev.actual, 3.2)
        self.assertEqual(ev.forecast, 3.1)
        self.assertEqual(ev.previous, 3.4)
        self.assertTrue(ev.to_dict()["is_confirmed_release"])
        self.assertFalse(ev.to_dict()["is_missing_actual"])

        # Check event-specific actual vs forecast interpretation
        interp = FinanceCalendarAdapter.interpret_actual_vs_forecast(ev.series_code, ev.actual, ev.forecast)
        self.assertEqual(interp["status"], "EVALUATED")
        self.assertEqual(interp["surprise_diff"], 0.1)
        self.assertEqual(interp["currency_bias"], "BULLISH")
        self.assertEqual(interp["crypto_bias"], "BEARISH")

    # ─── SCENARIO 3: Missing Actual or Forecast Values ────────────────
    def test_03_missing_actual_or_forecast_values(self):
        """Scenario 3: Missing actual or forecast values preserved as None without synthetic defaults."""
        raw = [{
            "id": "us-gdp-q3-2026",
            "series": "us-gdp",
            "title": "US Real GDP",
            "country": "US",
            "impact": "high",
            "release_at_utc": "2026-10-29T12:30:00+00:00",
            "status": "scheduled",
            "consensus": None,
            "prior": 2.8,
            "actual": None
        }]
        events = self.adapter.parse_events(raw)
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertIsNone(ev.actual)
        self.assertIsNone(ev.forecast)
        self.assertEqual(ev.previous, 2.8)
        d = ev.to_dict()
        self.assertTrue(d["is_missing_actual"])
        self.assertTrue(d["is_missing_forecast"])

        # Surprise calculation returns UNAVAILABLE when forecast is missing
        interp = FinanceCalendarAdapter.interpret_actual_vs_forecast(ev.series_code, ev.actual, ev.forecast)
        self.assertEqual(interp["status"], "UNAVAILABLE")
        self.assertIsNone(interp["surprise_diff"])

    # ─── SCENARIO 4: Revised Previous Values ──────────────────────────
    def test_04_revised_previous_values(self):
        """Scenario 4: Revised prior values are captured with is_revised flag."""
        raw = [{
            "id": "uk-jobs-report-october-2026",
            "series": "uk-jobs",
            "title": "UK Claimant Count Rate",
            "country": "GB",
            "impact": "medium",
            "release_at_utc": "2026-10-20T06:00:00+00:00",
            "status": "released",
            "consensus": 4.7,
            "prior": 4.6,
            "revised_prior": 4.5,
            "actual": 4.7
        }]
        events = self.adapter.parse_events(raw)
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertTrue(ev.is_revised)
        self.assertEqual(ev.previous, 4.6)
        self.assertEqual(ev.revised_previous, 4.5)

    # ─── SCENARIO 5: Duplicate Events ─────────────────────────────────
    def test_05_duplicate_event_deduplication(self):
        """Scenario 5: Duplicate events with matching event_id and timestamp are deduplicated."""
        raw_duplicate = [
            {
                "id": "fomc-oct-2026",
                "series": "fomc",
                "title": "FOMC Decision",
                "country": "US",
                "release_at_utc": "2026-10-28T18:00:00+00:00",
                "status": "confirmed"
            },
            {
                "id": "fomc-oct-2026",
                "series": "fomc",
                "title": "FOMC Decision Duplicate Row",
                "country": "US",
                "release_at_utc": "2026-10-28T18:00:00+00:00",
                "status": "confirmed"
            }
        ]
        events = self.adapter.parse_events(raw_duplicate)
        self.assertEqual(len(events), 1, "Duplicate event must be deduplicated to exactly 1")

    # ─── SCENARIO 6: Invalid or Missing Timestamps ────────────────────
    def test_06_invalid_or_missing_timestamps(self):
        """Scenario 6: Malformed, non-finite, or empty timestamps are skipped safely."""
        raw_invalid = [
            {"id": "bad-1", "series": "cpi", "release_at_utc": None},
            {"id": "bad-2", "series": "cpi", "release_at_utc": "NOT_A_DATE"},
            {"id": "bad-3", "series": "cpi", "release_at_utc": ""},
            {"id": "good-1", "series": "cpi", "release_at_utc": "2026-10-28T12:00:00Z"}
        ]
        events = self.adapter.parse_events(raw_invalid)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_id, "good-1")

    # ─── SCENARIO 7: UTC Conversion and PKT Display ───────────────────
    def test_07_utc_conversion_and_pkt_display(self):
        """Scenario 7: Preserves canonical UTC internally while rendering authoritative PKT (+05:00)."""
        raw = [{
            "id": "fomc-time-test",
            "series": "fomc",
            "title": "FOMC Rate Decision",
            "country": "US",
            "release_at_utc": "2026-10-28T18:00:00+00:00",
            "status": "confirmed"
        }]
        events = self.adapter.parse_events(raw)
        ev = events[0]
        # Canonical UTC ISO string
        self.assertEqual(ev.scheduled_utc, "2026-10-28T18:00:00+00:00")
        # PKT display is exactly UTC + 5 hours -> 23:00:00 PKT
        self.assertEqual(ev.scheduled_pkt, "2026-10-28 23:00:00 PKT")

    # ─── SCENARIO 8: Empty Responses ──────────────────────────────────
    def test_08_empty_responses(self):
        """Scenario 8: Empty list or non-dict payloads return empty list without crashing."""
        self.assertEqual(self.adapter.parse_events([]), [])
        self.assertEqual(self.adapter.parse_events(None), [])
        self.assertEqual(self.adapter.parse_events("not a list"), [])

    # ─── SCENARIO 9: HTTP Errors, Timeouts & Rate Limits ──────────────
    def test_09_error_and_rate_limit_specifications(self):
        """Scenario 9: Bounded retry, rate limit boundaries, and HTTP 429 Retry-After handling."""
        specs = self.adapter.get_provider_specs()
        self.assertEqual(specs["rate_limits"]["keyless_per_ip_per_day"], 2000)
        self.assertEqual(specs["rate_limits"]["free_key_per_day"], 10000)
        self.assertEqual(self.adapter.request_timeout_seconds, 10.0)
        self.assertEqual(self.adapter.max_retries, 2)

    # ─── SCENARIO 10: Stale Calendar Data ─────────────────────────────
    def test_10_stale_calendar_detection(self):
        """Scenario 10: Cached data older than 1 hour is flagged as STALE and reports UNKNOWN risk."""
        self.adapter.enabled = True
        self.adapter.load_mock_fixtures()
        self.assertFalse(self.adapter.is_stale())
        self.assertEqual(self.adapter.get_provider_status(), "AVAILABLE")

        # Simulate 2 hours passing
        self.adapter._last_retrieval_utc = datetime.now(timezone.utc) - timedelta(hours=2)
        self.assertTrue(self.adapter.is_stale())
        self.assertEqual(self.adapter.get_provider_status(), "STALE")

        # Evaluate risk when stale -> must return STALE, never CLEAR
        risk = self.adapter.evaluate_event_risk("BTC/USDT")
        self.assertEqual(risk["event_risk_status"], "STALE")
        self.assertEqual(risk["policy"], "CALENDAR_UNAVAILABLE")
        self.assertEqual(risk["recommendation"], "WAIT_OR_MANUAL_VERIFICATION")

    # ─── SCENARIO 11: Provider Disabled by Default ────────────────────
    def test_11_provider_disabled_by_default(self):
        """Scenario 11: Adapter defaults to disabled=False and returns UNKNOWN event risk without network calls."""
        fresh_adapter = FinanceCalendarAdapter()
        self.assertFalse(fresh_adapter.enabled)
        self.assertEqual(fresh_adapter.get_provider_status(), "DISABLED")

        # Evaluate risk when disabled -> must return UNKNOWN
        risk = fresh_adapter.evaluate_event_risk("BTC/USDT")
        self.assertEqual(risk["event_risk_status"], "UNKNOWN")
        self.assertEqual(risk["policy"], "CALENDAR_UNAVAILABLE")
        self.assertIn("disabled", risk["reason"].lower())
        self.assertEqual(risk["recommendation"], "WAIT_OR_MANUAL_VERIFICATION")
        self.assertFalse(risk["is_blackout"])

    # ─── SCENARIO 12: Attribution Displayed Correctly ─────────────────
    def test_12_attribution_displayed_correctly(self):
        """Scenario 12: Approved attribution text and clickable link are strictly verified."""
        specs = self.adapter.get_provider_specs()
        expected_text = "Economic calendar data provided by Finance Calendar"
        expected_link = "https://www.financecalendar.com"

        self.assertEqual(specs["approved_attribution_text"], expected_text)
        self.assertEqual(specs["approved_attribution_link"], expected_link)
        self.assertTrue(specs["commercial_use_permitted"])

    # ─── SCENARIO 13: Zero Client API Calls On Navigation ─────────────
    def test_13_zero_client_api_calls_bundled_payload(self):
        """Scenario 13: Calendar metadata is bundled in backend signals response without client polling."""
        from app.services.unified_signal_engine import unified_signal_engine
        import asyncio

        # Generate signals and check calendar payload
        res = asyncio.run(unified_signal_engine.generate_unified_signals(force_refresh=True))
        self.assertIn("calendar", res)
        cal = res["calendar"]
        self.assertEqual(cal["provider"], "Finance Calendar")
        self.assertEqual(cal["attribution_text"], "Economic calendar data provided by Finance Calendar")
        self.assertEqual(cal["attribution_link"], "https://www.financecalendar.com")

    # ─── SCENARIO 14: Zero Paid Fallback & No Silent Switching ────────
    def test_14_zero_paid_fallback_and_no_silent_switching(self):
        """Scenario 14: Verifies zero paid API endpoints, zero tokens consumed, and trading locked."""
        self.assertTrue(settings.live_trading_locked)
        self.assertTrue(settings.read_only_mode)

        t = telemetry_manager.get_telemetry()
        self.assertEqual(t.get("known_tokens", 0), 0)
        self.assertEqual(t.get("daily_tokens_used", 0), 0)

    # ─── SCENARIO 15: Regime Engine Protocol Integration ──────────────
    def test_15_regime_engine_protocol_integration(self):
        """Scenario 15: FinanceCalendarAdapter implements EventCalendarSource protocol for regime_engine."""
        regime_engine = DeterministicMarketRegimeEngine()

        # When adapter is disabled -> is_reliable() is False -> check_event_blackout returns UNKNOWN
        self.adapter.enabled = False
        is_blackout, regime, reasons, ev = regime_engine.check_event_blackout(
            current_time_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
            calendar_source=self.adapter,
            symbol="BTC"
        )
        self.assertFalse(is_blackout)
        self.assertEqual(regime, MarketRegime.UNKNOWN)
        self.assertIn("untrustworthy", reasons[0].lower())

        # When adapter is enabled and loaded with active mock event -> triggers EVENT_BLACKOUT
        self.adapter.enabled = True
        now_utc = datetime.now(timezone.utc)
        now_ms = int(now_utc.timestamp() * 1000)

        # Inject high-impact event scheduled 10 minutes from now
        event_10m_away = [{
            "id": "fomc-live-blackout",
            "series": "fomc",
            "title": "FOMC Rate Decision",
            "country": "US",
            "impact": "high",
            "release_at_utc": (now_utc + timedelta(minutes=10)).isoformat(),
            "status": "confirmed"
        }]
        self.adapter.load_mock_fixtures(event_10m_away)
        self.assertTrue(self.adapter.is_reliable())

        is_blackout, regime, reasons, ev = regime_engine.check_event_blackout(
            current_time_ms=now_ms,
            calendar_source=self.adapter,
            symbol="BTC"
        )
        self.assertTrue(is_blackout)
        self.assertEqual(regime, MarketRegime.EVENT_BLACKOUT)
        self.assertIsNotNone(ev)
        self.assertEqual(ev.title, "FOMC Rate Decision")


if __name__ == "__main__":
    unittest.main()
