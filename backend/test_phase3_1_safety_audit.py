"""
Tauric Phase 3.1 Safety Audit and Hardening Test Suite
Verifies:
1. Fail-closed event-risk audit (8 independent cases):
   - Case 1: Provider disabled
   - Case 2: No successful initial fetch
   - Case 3: Stale cached events
   - Case 4: Network timeout and HTTP errors
   - Case 5: Malformed or empty payload
   - Case 6: Missing event impact classification
   - Case 7: Relevant event within the configured risk window
   - Case 8: No relevant events in a successfully fetched and sufficiently fresh window
2. is_blackout=False CANNOT override an unsafe or unknown event_risk_status when event-risk gate is required (holds as WAIT).
3. Distinguish fresh clean window (CLEAR) from unavailable/unconfigured data (UNKNOWN/NOT_CONFIGURED).
4. Rejection of generic 'actual > forecast' rules: unmapped indicators return UNKNOWN.
5. Ambiguous indicators return MIXED.
6. Central bank rate decisions evaluated with explicit comparison basis (hikes, cuts, holds).
7. Raw values, surprise direction, revision, and model interpretation distinguished; zero trade orders.
8. API / Dashboard serialization and approved Finance Calendar attribution verified.
9. Safety invariants: live_trading_locked=True, read_only_mode=True, zero AI calls, zero token usage.
"""

import math
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from app.services.finance_calendar_adapter import (
    FinanceCalendarAdapter,
    NormalizedEconomicEvent,
    FINANCE_CALENDAR_SPECS,
    AMBIGUOUS_SERIES,
    EVENT_INTERPRETATION_RULES
)
from app.services.regime_engine import (
    DeterministicMarketRegimeEngine,
    MarketRegime,
    EventSeverity,
    MacroEvent,
    RegimeEngineConfig
)
from app.services.telemetry_manager import telemetry_manager
from app.config import settings


class TestPhase31SafetyAudit(unittest.TestCase):

    def setUp(self):
        # Fresh isolated adapter instance for tests
        self.adapter = FinanceCalendarAdapter(enabled=False)
        self.regime_engine = DeterministicMarketRegimeEngine()
        self.now_utc = datetime.now(timezone.utc)
        self.now_ms = int(self.now_utc.timestamp() * 1000)

    # =========================================================================
    # SECTION 1: 8 INDEPENDENT FAIL-CLOSED EVENT-RISK AUDIT CASES
    # =========================================================================

    def test_case_01_provider_disabled(self):
        """Case 1: Provider disabled -> UNKNOWN/DISABLED; holds as WAIT when gate required."""
        self.adapter.enabled = False
        self.assertEqual(self.adapter.get_provider_status(), "DISABLED")

        # Adapter evaluate_event_risk
        risk = self.adapter.evaluate_event_risk("BTCUSDT", current_time_ms=self.now_ms)
        self.assertEqual(risk["event_risk_status"], "UNKNOWN")
        self.assertFalse(risk["is_blackout"])
        self.assertEqual(risk["recommendation"], "WAIT_OR_MANUAL_VERIFICATION")

        # Regime engine check_event_blackout
        is_bo, regime, reasons, ev = self.regime_engine.check_event_blackout(self.now_ms, self.adapter, "BTCUSDT")
        self.assertFalse(is_bo)
        self.assertEqual(regime, MarketRegime.UNKNOWN)
        self.assertIn("untrustworthy", reasons[0].lower())

        # Regime engine evaluate_symbol_regime: fail-closed when gate required
        res = self.regime_engine.evaluate_symbol_regime(
            symbol="BTCUSDT",
            price=68000.0,
            change_24h=1.5,
            data_status="PASS",
            calendar_source=self.adapter,
            current_time_ms=self.now_ms,
            require_event_risk_clear=True
        )
        self.assertEqual(res.status, "WAIT")
        self.assertEqual(res.regime, MarketRegime.UNKNOWN)
        self.assertEqual(res.event_risk_status, "DISABLED")
        self.assertFalse(res.is_blackout)

    def test_case_02_no_successful_initial_fetch(self):
        """Case 2: Enabled but no initial fetch -> UNAVAILABLE; holds as WAIT when gate required."""
        self.adapter.enabled = True
        self.adapter._last_retrieval_utc = None
        self.adapter._cached_events = []
        self.assertTrue(self.adapter.is_stale())
        self.assertEqual(self.adapter.get_provider_status(), "STALE")

        # Adapter evaluate_event_risk
        risk = self.adapter.evaluate_event_risk("BTCUSDT", current_time_ms=self.now_ms)
        self.assertEqual(risk["event_risk_status"], "STALE")
        self.assertFalse(risk["is_blackout"])
        self.assertEqual(risk["recommendation"], "WAIT_OR_MANUAL_VERIFICATION")

        # Regime engine evaluate_symbol_regime: fail-closed
        res = self.regime_engine.evaluate_symbol_regime(
            symbol="BTCUSDT",
            price=68000.0,
            change_24h=1.5,
            data_status="PASS",
            calendar_source=self.adapter,
            current_time_ms=self.now_ms,
            require_event_risk_clear=True
        )
        self.assertEqual(res.status, "WAIT")
        self.assertEqual(res.regime, MarketRegime.UNKNOWN)
        self.assertIn("no successful initial fetch", res.reasons[0].lower())

    def test_case_03_stale_cached_events(self):
        """Case 3: Stale cached events (>1h) -> STALE; holds as WAIT when gate required."""
        self.adapter.enabled = True
        # Set last retrieval to 2 hours ago
        self.adapter._last_retrieval_utc = self.now_utc - timedelta(hours=2)
        self.adapter._cached_events = [
            NormalizedEconomicEvent(
                event_id="old-1",
                series_code="cpi",
                title="Stale CPI",
                country="US",
                currency="USD",
                scheduled_utc=(self.now_utc + timedelta(minutes=5)).isoformat(),
                scheduled_timestamp_ms=self.now_ms + 300000,
                scheduled_pkt="--",
                impact="HIGH",
                impact_weight=3,
                status="confirmed"
            )
        ]
        self.assertTrue(self.adapter.is_stale())
        self.assertEqual(self.adapter.get_provider_status(), "STALE")

        # Evaluate risk
        risk = self.adapter.evaluate_event_risk("BTCUSDT", current_time_ms=self.now_ms)
        self.assertEqual(risk["event_risk_status"], "STALE")
        self.assertFalse(risk["is_blackout"])

        # Regime engine check
        res = self.regime_engine.evaluate_symbol_regime(
            symbol="BTCUSDT",
            price=68000.0,
            change_24h=2.0,
            data_status="PASS",
            calendar_source=self.adapter,
            current_time_ms=self.now_ms,
            require_event_risk_clear=True
        )
        self.assertEqual(res.status, "WAIT")
        self.assertEqual(res.regime, MarketRegime.UNKNOWN)
        self.assertEqual(res.event_risk_status, "STALE")

    def test_case_04_network_timeout_and_http_errors(self):
        """Case 4: Calendar fetch error / timeout -> UNAVAILABLE; holds as WAIT when gate required."""
        mock_source = MagicMock()
        mock_source.enabled = True
        mock_source.is_stale.return_value = False
        mock_source._last_retrieval_utc = self.now_utc
        mock_source.is_reliable.return_value = True
        mock_source.get_events.side_effect = TimeoutError("Connection to calendar timed out after 10s")

        is_bo, regime, reasons, ev = self.regime_engine.check_event_blackout(self.now_ms, mock_source, "BTCUSDT")
        self.assertFalse(is_bo)
        self.assertEqual(regime, MarketRegime.UNKNOWN)
        self.assertIn("timed out", reasons[0])

        res = self.regime_engine.evaluate_symbol_regime(
            symbol="BTCUSDT",
            price=68000.0,
            change_24h=1.2,
            data_status="PASS",
            calendar_source=mock_source,
            current_time_ms=self.now_ms,
            require_event_risk_clear=True
        )
        self.assertEqual(res.status, "WAIT")
        self.assertEqual(res.regime, MarketRegime.UNKNOWN)
        self.assertEqual(res.event_risk_status, "UNAVAILABLE")

    def test_case_05_malformed_or_empty_payload(self):
        """Case 5: Calendar returns non-list malformed payload -> UNAVAILABLE; holds as WAIT."""
        mock_source = MagicMock()
        mock_source.enabled = True
        mock_source.is_stale.return_value = False
        mock_source._last_retrieval_utc = self.now_utc
        mock_source.is_reliable.return_value = True
        mock_source.get_events.return_value = {"error": "unexpected JSON object"}

        is_bo, regime, reasons, ev = self.regime_engine.check_event_blackout(self.now_ms, mock_source, "BTCUSDT")
        self.assertFalse(is_bo)
        self.assertEqual(regime, MarketRegime.UNKNOWN)
        self.assertIn("non-list", reasons[0].lower())

        res = self.regime_engine.evaluate_symbol_regime(
            symbol="BTCUSDT",
            price=68000.0,
            change_24h=1.2,
            data_status="PASS",
            calendar_source=mock_source,
            current_time_ms=self.now_ms,
            require_event_risk_clear=True
        )
        self.assertEqual(res.status, "WAIT")
        self.assertEqual(res.event_risk_status, "UNAVAILABLE")

    def test_case_06_missing_event_impact_classification(self):
        """Case 6: Event in risk window lacks impact classification -> UNKNOWN; holds as WAIT."""
        self.adapter.enabled = True
        self.adapter._last_retrieval_utc = self.now_utc
        self.adapter._last_error = None
        # Event in 10 minutes with impact missing/None
        raw_event = [{
            "id": "unclassified-speech-2026",
            "series": "fed-speech",
            "title": "Fed Governor Speech Unclassified",
            "country": "US",
            "impact": None,
            "release_at_utc": (self.now_utc + timedelta(minutes=10)).isoformat(),
            "status": "confirmed"
        }]
        self.adapter.load_mock_fixtures(raw_event)
        self.assertTrue(self.adapter.is_reliable())

        # Adapter evaluate_event_risk
        risk = self.adapter.evaluate_event_risk("BTCUSDT", current_time_ms=self.now_ms)
        self.assertEqual(risk["event_risk_status"], "UNKNOWN")
        self.assertFalse(risk["is_blackout"])
        self.assertEqual(risk["policy"], "UNCLASSIFIED_EVENT_RISK")
        self.assertEqual(risk["recommendation"], "WAIT_OR_MANUAL_VERIFICATION")

        # Regime engine check_event_blackout
        is_bo, regime, reasons, ev = self.regime_engine.check_event_blackout(self.now_ms, self.adapter, "BTCUSDT")
        self.assertFalse(is_bo)
        self.assertEqual(regime, MarketRegime.UNKNOWN)
        self.assertIn("lacks impact classification", reasons[0].lower())

        # Regime engine evaluate_symbol_regime: fail-closed
        res = self.regime_engine.evaluate_symbol_regime(
            symbol="BTCUSDT",
            price=68000.0,
            change_24h=1.5,
            data_status="PASS",
            calendar_source=self.adapter,
            current_time_ms=self.now_ms,
            require_event_risk_clear=True
        )
        self.assertEqual(res.status, "WAIT")
        self.assertEqual(res.regime, MarketRegime.UNKNOWN)
        self.assertEqual(res.event_risk_status, "UNKNOWN")

    def test_case_07_relevant_event_within_configured_risk_window(self):
        """Case 7: High-impact event within [-15m, +30m] window -> BLACKOUT."""
        self.adapter.enabled = True
        self.adapter._last_retrieval_utc = self.now_utc
        self.adapter._last_error = None
        raw_event = [{
            "id": "fomc-decision-blackout",
            "series": "fomc",
            "title": "FOMC Rate Decision",
            "country": "US",
            "impact": "high",
            "release_at_utc": (self.now_utc + timedelta(minutes=15)).isoformat(),
            "status": "confirmed"
        }]
        self.adapter.load_mock_fixtures(raw_event)
        self.assertTrue(self.adapter.is_reliable())

        # Adapter evaluate_event_risk
        risk = self.adapter.evaluate_event_risk("BTCUSDT", current_time_ms=self.now_ms)
        self.assertEqual(risk["event_risk_status"], "BLACKOUT")
        self.assertTrue(risk["is_blackout"])
        self.assertEqual(risk["recommendation"], "SUSPEND_ENTRY")

        # Regime engine evaluate_symbol_regime
        res = self.regime_engine.evaluate_symbol_regime(
            symbol="BTCUSDT",
            price=68000.0,
            change_24h=2.0,
            data_status="PASS",
            calendar_source=self.adapter,
            current_time_ms=self.now_ms,
            require_event_risk_clear=True
        )
        self.assertEqual(res.status, "BLACKOUT")
        self.assertEqual(res.regime, MarketRegime.EVENT_BLACKOUT)
        self.assertTrue(res.is_blackout)
        self.assertEqual(res.event_risk_status, "BLACKOUT")
        self.assertIsNotNone(res.blackout_event)

    def test_case_08_no_relevant_events_in_fresh_window(self):
        """Case 8: Fresh calendar with no events in window -> CLEAR / PASS."""
        self.adapter.enabled = True
        self.adapter._last_retrieval_utc = self.now_utc
        self.adapter._last_error = None
        # Event scheduled 24 hours away (well outside ±30m window)
        raw_event = [{
            "id": "fomc-tomorrow",
            "series": "fomc",
            "title": "FOMC Rate Decision",
            "country": "US",
            "impact": "high",
            "release_at_utc": (self.now_utc + timedelta(hours=24)).isoformat(),
            "status": "confirmed"
        }]
        self.adapter.load_mock_fixtures(raw_event)
        self.assertTrue(self.adapter.is_reliable())

        # Adapter evaluate_event_risk
        risk = self.adapter.evaluate_event_risk("BTCUSDT", current_time_ms=self.now_ms)
        self.assertEqual(risk["event_risk_status"], "CLEAR")
        self.assertFalse(risk["is_blackout"])
        self.assertEqual(risk["recommendation"], "STANDARD_OPERATION")

        # Regime engine evaluate_symbol_regime
        res = self.regime_engine.evaluate_symbol_regime(
            symbol="BTCUSDT",
            price=68000.0,
            change_24h=1.5,
            data_status="PASS",
            calendar_source=self.adapter,
            current_time_ms=self.now_ms,
            require_event_risk_clear=True
        )
        self.assertEqual(res.status, "PASS")
        self.assertEqual(res.regime, MarketRegime.RISK_ON)
        self.assertEqual(res.event_risk_status, "CLEAR")
        self.assertFalse(res.is_blackout)

    # =========================================================================
    # SECTION 2: FAIL-CLOSED SAFETY GATES & DISTINCTION
    # =========================================================================

    def test_blackout_false_cannot_override_unknown_event_risk(self):
        """Proves is_blackout=False CANNOT override UNKNOWN event-risk to issue PASS when gate required."""
        self.adapter.enabled = False
        is_bo, regime, _, _ = self.regime_engine.check_event_blackout(self.now_ms, self.adapter, "BTCUSDT")
        # is_blackout is False because provider is disabled, NOT because the window is confirmed clear
        self.assertFalse(is_bo)
        self.assertEqual(regime, MarketRegime.UNKNOWN)

        # When require_event_risk_clear=True, it MUST NOT return PASS
        res = self.regime_engine.evaluate_symbol_regime(
            symbol="ETHUSDT",
            price=3500.0,
            change_24h=3.0,
            data_status="PASS",
            calendar_source=self.adapter,
            current_time_ms=self.now_ms,
            require_event_risk_clear=True
        )
        self.assertNotEqual(res.status, "PASS")
        self.assertEqual(res.status, "WAIT")
        self.assertEqual(res.event_risk_status, "DISABLED")

    def test_distinguish_clean_window_from_unconfigured_calendar(self):
        """Distinguishes fresh clean window (CLEAR) from unconfigured calendar (NOT_CONFIGURED)."""
        # A. Unconfigured calendar
        res_unconfigured = self.regime_engine.evaluate_symbol_regime(
            symbol="BTCUSDT",
            price=68000.0,
            change_24h=0.5,
            calendar_source=None,
            require_event_risk_clear=False  # default crypto analysis allows proceeding without phantom events
        )
        self.assertEqual(res_unconfigured.status, "PASS")
        self.assertEqual(res_unconfigured.event_risk_status, "NOT_CONFIGURED")

        # But if event-risk gate is strictly required:
        res_unconfigured_req = self.regime_engine.evaluate_symbol_regime(
            symbol="BTCUSDT",
            price=68000.0,
            change_24h=0.5,
            calendar_source=None,
            require_event_risk_clear=True
        )
        self.assertEqual(res_unconfigured_req.status, "WAIT")
        self.assertEqual(res_unconfigured_req.event_risk_status, "NOT_CONFIGURED")

        # B. Configured, fresh, clean window
        self.adapter.enabled = True
        self.adapter._last_retrieval_utc = self.now_utc
        self.adapter._cached_events = []
        res_fresh_clean = self.regime_engine.evaluate_symbol_regime(
            symbol="BTCUSDT",
            price=68000.0,
            change_24h=0.5,
            calendar_source=self.adapter,
            require_event_risk_clear=True
        )
        self.assertEqual(res_fresh_clean.status, "PASS")
        self.assertEqual(res_fresh_clean.event_risk_status, "CLEAR")

    # =========================================================================
    # SECTION 3: ECONOMIC INTERPRETATION AUDIT
    # =========================================================================

    def test_reject_generic_actual_greater_than_forecast_rule(self):
        """Proves generic actual > forecast rules are rejected for unmapped series (returns UNKNOWN)."""
        # Random unmapped indicator
        interp = FinanceCalendarAdapter.interpret_actual_vs_forecast(
            series_code="random-unmapped-survey",
            actual=55.2,
            forecast=50.0,
            raw_actual="55.2",
            raw_forecast="50.0"
        )
        self.assertEqual(interp["status"], "UNKNOWN")
        self.assertEqual(interp["currency_bias"], "UNKNOWN")
        self.assertEqual(interp["crypto_bias"], "UNKNOWN")
        self.assertEqual(interp["surprise_direction"], "POSITIVE")
        self.assertEqual(interp["surprise_diff"], 5.2)
        self.assertIn("rejected for safety", interp["model_interpretation"].lower())
        self.assertEqual(interp["raw_actual"], "55.2")

    def test_ambiguous_indicators_return_mixed(self):
        """Proves indicators with multi-channel transmission return MIXED."""
        for amb in ["trade-balance", "crude-oil-stocks", "michigan-sentiment", "average-hourly-earnings"]:
            interp = FinanceCalendarAdapter.interpret_actual_vs_forecast(
                series_code=amb,
                actual=120.0,
                forecast=100.0,
                raw_actual="120.0",
                raw_forecast="100.0"
            )
            self.assertEqual(interp["status"], "MIXED", f"Series '{amb}' must return status=MIXED")
            self.assertEqual(interp["currency_bias"], "MIXED")
            self.assertEqual(interp["crypto_bias"], "MIXED")
            self.assertIn("ambiguous", interp["model_interpretation"].lower())

    def test_central_bank_rate_decision_explicit_comparison(self):
        """Tests rate decisions with explicit comparison basis for hikes, cuts, and holds."""
        # 1. Hawkish Rate Hike Surprise (actual 5.50% > forecast 5.25%)
        hike = FinanceCalendarAdapter.interpret_actual_vs_forecast(
            series_code="fomc",
            actual=5.50,
            forecast=5.25,
            previous=5.25,
            raw_actual="5.50%",
            raw_forecast="5.25%"
        )
        self.assertEqual(hike["status"], "EVALUATED")
        self.assertEqual(hike["currency_bias"], "BULLISH")
        self.assertEqual(hike["crypto_bias"], "BEARISH")
        self.assertIn("benchmark", hike["comparison_basis"].lower())
        self.assertIn("hike", hike["model_interpretation"].lower())

        # 2. Dovish Rate Cut Surprise (actual 4.75% < forecast 5.00%)
        cut = FinanceCalendarAdapter.interpret_actual_vs_forecast(
            series_code="fomc",
            actual=4.75,
            forecast=5.00,
            previous=5.25
        )
        self.assertEqual(cut["status"], "EVALUATED")
        self.assertEqual(cut["currency_bias"], "BEARISH")
        self.assertEqual(cut["crypto_bias"], "BULLISH")
        self.assertIn("cut", cut["model_interpretation"].lower())

        # 3. Rate Hold in line with consensus (actual 5.25% == forecast 5.25% == prior 5.25%)
        hold = FinanceCalendarAdapter.interpret_actual_vs_forecast(
            series_code="fomc",
            actual=5.25,
            forecast=5.25,
            previous=5.25
        )
        self.assertEqual(hold["status"], "EVALUATED")
        self.assertEqual(hold["currency_bias"], "NEUTRAL")
        self.assertEqual(hold["crypto_bias"], "NEUTRAL")
        self.assertEqual(hold["surprise_diff"], 0.0)
        self.assertIn("unchanged", hold["model_interpretation"].lower())

    def test_distinguishes_raw_values_revisions_and_zero_orders(self):
        """Verifies raw strings, revision capture, and strict zero-order invariant."""
        interp = FinanceCalendarAdapter.interpret_actual_vs_forecast(
            series_code="us-cpi",
            actual=3.2,
            forecast=3.1,
            previous=3.4,
            raw_actual="3.2%",
            raw_forecast="3.1%",
            raw_previous="3.4%",
            revised_previous=3.5
        )
        self.assertEqual(interp["measured_value"], 3.2)
        self.assertEqual(interp["raw_actual"], "3.2%")
        self.assertEqual(interp["forecast_value"], 3.1)
        self.assertEqual(interp["raw_forecast"], "3.1%")
        self.assertEqual(interp["previous_value"], 3.4)
        self.assertEqual(interp["raw_previous"], "3.4%")
        self.assertEqual(interp["revised_previous"], 3.5)
        self.assertTrue(interp["is_revised"])
        self.assertEqual(interp["surprise_direction"], "POSITIVE")

        # Zero trade orders: never generates BUY/SELL orders or trade commands
        self.assertNotIn("order_type", interp)
        self.assertNotIn("action", interp)
        self.assertIn("not a trade recommendation", interp["disclaimer"].lower())

    # =========================================================================
    # SECTION 4: DASHBOARD / API SERIALIZATION & ATTRIBUTION
    # =========================================================================

    def test_dashboard_serialization_and_attribution(self):
        """Verifies API serialization exposes accurate status and approved attribution."""
        specs = self.adapter.get_provider_specs()
        self.assertEqual(specs["provider_name"], "Finance Calendar")
        self.assertEqual(specs["status"], "DISABLED")
        self.assertEqual(specs["approved_attribution_text"], "Economic calendar data provided by Finance Calendar")
        self.assertEqual(specs["approved_attribution_link"], "https://www.financecalendar.com")

        # Check NormalizedEconomicEvent.to_dict serialization
        ev = NormalizedEconomicEvent(
            event_id="fomc-oct-2026",
            series_code="fomc",
            title="FOMC Rate Decision",
            country="US",
            currency="USD",
            scheduled_utc="2026-10-28T18:00:00Z",
            scheduled_timestamp_ms=1793210400000,
            scheduled_pkt="2026-10-28 23:00:00 PKT",
            impact="HIGH",
            impact_weight=3,
            status="confirmed",
            actual=None,
            forecast=5.25,
            previous=5.25
        )
        d = ev.to_dict()
        self.assertEqual(d["event_id"], "fomc-oct-2026")
        self.assertEqual(d["impact"], "HIGH")
        self.assertTrue(d["is_not_yet_released"])
        self.assertFalse(d["is_confirmed_release"])
        self.assertIsNone(d["interpretation"])

    # =========================================================================
    # SECTION 5: ZERO AI INFERENCE / ZERO ORDERS / SAFETY INVARIANTS
    # =========================================================================

    def test_safety_invariants_preserved(self):
        """Verifies spot-only, live_trading_locked=True, read_only_mode=True, zero token usage."""
        self.assertTrue(settings.live_trading_locked)
        self.assertTrue(settings.read_only_mode)

        # Zero tokens consumed
        telemetry = telemetry_manager.get_telemetry()
        self.assertEqual(telemetry.get("known_tokens", 0), 0)
        self.assertEqual(telemetry.get("daily_tokens_used", 0), 0)


if __name__ == "__main__":
    unittest.main()
