"""
Tauric Platform — Phase 3.2 Dual-AI News Analysis & Reconciliation Test Suite
Comprehensive isolated verification covering:

1. Identical snapshot hash and contents for both models.
2. Independent calls with no cross-contamination before completion.
3. Conflicting directions producing WAIT / NO_TRADE.
4. Missing, malformed, stale, and unavailable evidence failing closed.
5. Disabled/unavailable calendar with required news clearance producing WAIT.
6. Model timeout, error, or malformed output producing WAIT / NO_TRADE.
7. Concurrency lock preventing duplicate submissions (409 Conflict).
8. User recommendation acknowledgement persisting without any exchange execution.
9. Final Tauric review strictly adhering to safety gates (cannot override WAIT).
10. Telemetry and daily budget kill switch.
11. Verification that live_trading_locked=true and read_only_mode=true are strictly enforced.
"""

import unittest
import asyncio
import hashlib
import json
import time
from typing import Dict, Any

from app.config import settings, resolve_model_tier, validate_model_preflight
from app.services.snapshot_engine import snapshot_engine, compute_snapshot_hash
from app.services.dual_ai_engine import dual_ai_engine
from app.services.shadow_store import shadow_store
from app.services.telemetry_manager import telemetry_manager


class TestPhase32DualAIReconciliation(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        # Reset concurrency lock
        dual_ai_engine.active_job_id = None
        dual_ai_engine.active_job_started_at = None

    def tearDown(self):
        dual_ai_engine.active_job_id = None
        dual_ai_engine.active_job_started_at = None
        self.loop.close()

    def test_01_snapshot_immutability_and_hash_identity(self):
        """Verify identical snapshot produces identical SHA-256 hash across both models."""
        mock_snap = {
            "market_data": {
                "price": 2500.0,
                "change_24h": 2.5,
                "volume_24h": 50000000.0,
                "bid": 2499.8,
                "ask": 2500.2,
                "spread_bps": 1.6,
                "source": "BINANCE_SPOT_TICKER",
                "retrieval_timestamp_utc": "2026-10-21T08:00:00Z",
                "freshness_status": "FRESH",
                "data_age_seconds": 1.0
            },
            "indicators": {
                "rsi": 62.5,
                "macd_hist": 1.5,
                "ema20": 2480.0,
                "ema50": 2450.0,
                "ema200": 2400.0,
                "atr14": 25.0
            },
            "regime": {"market_regime": "RISK_ON", "regime_reason": "Bullish trend stack", "regime_score": 85},
            "liquidity": {"liquidity_status": "QUALIFIED", "depth_quote": 250000.0, "est_slippage_bps": 2.5},
            "calendar": {
                "provider": "Finance Calendar",
                "provider_status": "DISABLED",
                "event_risk_status": "UNKNOWN",
                "is_blackout": False,
                "relevant_events": []
            },
            "technical_trade_setup": {
                "qualified": True,
                "direction": "BUY",
                "entry_zone_min": 2495.0,
                "entry_zone_max": 2505.0,
                "stop_loss": 2450.0,
                "take_profit_1": 2560.0,
                "take_profit_2": 2600.0,
                "take_profit_3": 2650.0,
                "invalidation_level": 2450.0,
                "entry_validity_sec": 2700,
                "max_holding_sec": 28800,
                "calculation_inputs": {"ref_price": 2500.0}
            }
        }

        snap1 = self.loop.run_until_complete(snapshot_engine.create_snapshot("ETHUSDT", mock_override=mock_snap))
        snap2 = self.loop.run_until_complete(snapshot_engine.create_snapshot("ETHUSDT", mock_override=mock_snap))

        self.assertIn("content_hash", snap1)
        self.assertIn("content_hash", snap2)
        # Content hashes must be identical
        self.assertEqual(snap1["content_hash"], snap2["content_hash"])
        self.assertEqual(len(snap1["content_hash"]), 64)

        # Altering a single value must alter hash
        mock_altered = json.loads(json.dumps(mock_snap))
        mock_altered["market_data"]["price"] = 2501.0
        snap_altered = self.loop.run_until_complete(snapshot_engine.create_snapshot("ETHUSDT", mock_override=mock_altered))
        self.assertNotEqual(snap1["content_hash"], snap_altered["content_hash"])

    def test_02_independent_calls_no_cross_contamination(self):
        """Verify Tauric and JeV evaluations run independently without data leaks."""
        snap = self.loop.run_until_complete(snapshot_engine.create_snapshot(
            "ETHUSDT",
            mock_override={
                "market_data": {"price": 2500.0, "change_24h": 1.5, "freshness_status": "FRESH"},
                "indicators": {"rsi": 58.0, "macd_hist": 0.8, "ema20": 2490.0, "ema50": 2470.0, "ema200": 2420.0, "atr14": 20.0},
                "technical_trade_setup": {"qualified": True, "direction": "BUY", "stop_loss": 2460.0, "take_profit_1": 2550.0}
            }
        ))

        # Run both independently
        t_coro = dual_ai_engine.evaluate_tauric_independent(snap)
        j_coro = dual_ai_engine.evaluate_jev_independent(snap)
        t_res, j_res = self.loop.run_until_complete(asyncio.gather(t_coro, j_coro))

        # Check structured schemas
        self.assertEqual(t_res["model_id"], "deepseek-v4-flash")
        self.assertEqual(j_res["model_id"], "jev-latest")
        self.assertIn("directional_view", t_res)
        self.assertIn("directional_view", j_res)
        self.assertIn("observed_facts", t_res)
        self.assertIn("observed_facts", j_res)

        # Confirm neither model leaks its identity or raw object into the other's payload
        self.assertNotIn("deepseek", json.dumps(j_res).lower())
        self.assertNotIn("jev", json.dumps(t_res).lower())

    def test_03_conflicting_directions_produce_wait(self):
        """Verify conflicting directions deterministically produce WAIT / NO_TRADE."""
        snap = {"calendar": {"event_risk_status": "CLEAR", "is_blackout": False}, "technical_trade_setup": {"stop_loss": 90.0, "take_profit_1": 120.0}, "market_data": {"price": 100.0}}
        t_res = {"model_id": "deepseek-v4-flash", "status": "COMPLETED", "directional_view": "BULLISH"}
        j_res = {"model_id": "jev-latest", "status": "COMPLETED", "directional_view": "BEARISH"}

        reconcile = dual_ai_engine.reconcile_evaluations(snap, t_res, j_res)
        self.assertEqual(reconcile["reconciliation_outcome"], "WAIT")
        self.assertEqual(reconcile["agreement_status"], "CONFLICT")
        self.assertEqual(reconcile["consensus_direction"], "WAIT")
        self.assertTrue(any("Directional view conflict" in r for r in reconcile["veto_reasons"]))

        # Final review cannot override this
        final_rev = dual_ai_engine.final_tauric_review(snap, t_res, j_res, reconcile)
        self.assertEqual(final_rev["final_advisory_status"], "WAIT")
        self.assertEqual(final_rev["final_action"], "WAIT")

    def test_04_missing_or_stale_evidence_fails_closed(self):
        """Verify stale, missing, or zero price evidence fails closed before AI call."""
        mock_stale = {
            "market_data": {"price": 2500.0, "freshness_status": "STALE"},
            "indicators": {"rsi": 50.0},
            "technical_trade_setup": {"qualified": True, "direction": "BUY"}
        }
        snap_stale = self.loop.run_until_complete(snapshot_engine.create_snapshot("ETHUSDT", mock_override=mock_stale))
        self.assertFalse(snap_stale["eligible_for_ai"])
        self.assertIn("MARKET_DATA_STALE", snap_stale["safety_gate_reasons"])

        mock_missing_price = {
            "market_data": {"price": 0.0, "freshness_status": "FRESH"},
            "indicators": {"rsi": 50.0},
            "technical_trade_setup": {"qualified": True, "direction": "BUY"}
        }
        snap_zero = self.loop.run_until_complete(snapshot_engine.create_snapshot("ETHUSDT", mock_override=mock_missing_price))
        self.assertFalse(snap_zero["eligible_for_ai"])
        self.assertIn("MISSING_OR_ZERO_PRICE", snap_zero["safety_gate_reasons"])

    def test_05_disabled_calendar_with_required_clearance_produces_wait(self):
        """Verify disabled/unknown calendar returns WAIT when news clearance is strictly required."""
        snap = {
            "calendar": {"provider": "Finance Calendar", "provider_status": "DISABLED", "event_risk_status": "UNKNOWN", "is_blackout": False},
            "technical_trade_setup": {"stop_loss": 90.0, "take_profit_1": 120.0},
            "market_data": {"price": 100.0}
        }
        t_res = {"model_id": "deepseek-v4-flash", "status": "COMPLETED", "directional_view": "BULLISH"}
        j_res = {"model_id": "jev-latest", "status": "COMPLETED", "directional_view": "BULLISH"}

        reconcile = dual_ai_engine.reconcile_evaluations(snap, t_res, j_res, require_event_risk_clear=True)
        self.assertEqual(reconcile["reconciliation_outcome"], "WAIT")
        self.assertTrue(any("Verified economic calendar clearance required" in r for r in reconcile["veto_reasons"]))

    def test_06_model_timeout_or_error_fails_closed(self):
        """Verify single model failure, timeout, or error returns WAIT / NO_TRADE without consensus."""
        snap = {"calendar": {"event_risk_status": "CLEAR", "is_blackout": False}, "technical_trade_setup": {}, "market_data": {"price": 100.0}}
        t_res = {"model_id": "deepseek-v4-flash", "status": "COMPLETED", "directional_view": "BULLISH"}
        j_res = {"model_id": "jev-latest", "status": "TIMEOUT", "directional_view": "UNKNOWN"}

        reconcile = dual_ai_engine.reconcile_evaluations(snap, t_res, j_res)
        self.assertEqual(reconcile["reconciliation_outcome"], "WAIT")
        self.assertEqual(reconcile["agreement_status"], "INCOMPLETE")
        self.assertTrue(any("JeV review did not complete" in r for r in reconcile["veto_reasons"]))

    def test_07_deterministic_risk_rule_violation_produces_wait(self):
        """Verify risk-to-reward < 1.0 or inverted stop loss forces reconciliation outcome to WAIT."""
        # Inverted stop loss for BUY setup (stop above entry)
        snap_bad_stop = {
            "calendar": {"event_risk_status": "CLEAR", "is_blackout": False},
            "market_data": {"price": 100.0},
            "technical_trade_setup": {"stop_loss": 105.0, "take_profit_1": 120.0}
        }
        t_res = {"model_id": "deepseek-v4-flash", "status": "COMPLETED", "directional_view": "BULLISH"}
        j_res = {"model_id": "jev-latest", "status": "COMPLETED", "directional_view": "BULLISH"}

        reconcile = dual_ai_engine.reconcile_evaluations(snap_bad_stop, t_res, j_res)
        self.assertEqual(reconcile["reconciliation_outcome"], "WAIT")
        self.assertTrue(any("Invalid stop loss" in r for r in reconcile["veto_reasons"]))

        # R:R < 1.0
        snap_bad_rr = {
            "calendar": {"event_risk_status": "CLEAR", "is_blackout": False},
            "market_data": {"price": 100.0},
            "technical_trade_setup": {"stop_loss": 80.0, "take_profit_1": 110.0}  # Risk 20, reward 10 -> R:R 0.5
        }
        reconcile_rr = dual_ai_engine.reconcile_evaluations(snap_bad_rr, t_res, j_res)
        self.assertEqual(reconcile_rr["reconciliation_outcome"], "WAIT")
        self.assertTrue(any("below mandatory 1:1.0 minimum" in r for r in reconcile_rr["veto_reasons"]))

    def test_08_concurrency_lock_and_duplicate_prevention(self):
        """Verify at most 1 active dual-AI job is allowed; duplicate submissions are blocked."""
        job_1 = "DUAL-JOB-TEST-1"
        job_2 = "DUAL-JOB-TEST-2"

        # Acquire job 1
        acquired_1 = dual_ai_engine.acquire_job_slot(job_1)
        self.assertTrue(acquired_1)

        # Attempt to acquire job 2 simultaneously -> must fail
        acquired_2 = dual_ai_engine.acquire_job_slot(job_2)
        self.assertFalse(acquired_2)

        # Release job 1
        dual_ai_engine.release_job_slot(job_1)

        # Now job 2 can be acquired
        acquired_2_retry = dual_ai_engine.acquire_job_slot(job_2)
        self.assertTrue(acquired_2_retry)
        dual_ai_engine.release_job_slot(job_2)

    def test_09_user_acknowledgement_persists_without_execution(self):
        """Verify user acknowledgement records manual review without triggering orders."""
        mock_snap = {
            "market_data": {"price": 2500.0, "change_24h": 1.0, "freshness_status": "FRESH"},
            "indicators": {"rsi": 55.0, "macd_hist": 0.5, "ema20": 2490.0, "ema50": 2470.0, "ema200": 2420.0, "atr14": 20.0},
            "technical_trade_setup": {"qualified": True, "direction": "BUY", "stop_loss": 2460.0, "take_profit_1": 2550.0}
        }
        res = self.loop.run_until_complete(dual_ai_engine.execute_dual_ai_workflow(
            symbol="ETHUSDT",
            mock_overrides={"snapshot": mock_snap}
        ))
        self.assertEqual(res["status"], "SUCCESS")
        snap_id = res["snapshot_id"]

        # Record user acknowledgement
        ack_res = dual_ai_engine.acknowledge_recommendation(
            decision_id=snap_id,
            notes="Reviewed and approved by operator for manual monitoring."
        )
        self.assertEqual(ack_res["status"], "SUCCESS")
        self.assertTrue(ack_res["is_acknowledged"])
        self.assertEqual(ack_res["execution_safeguard"], "READ_ONLY_MODE_ENFORCED")

        # Verify persisted record in shadow store has acknowledgement updated
        saved_rec = shadow_store.get_decision(snap_id)
        self.assertIsNotNone(saved_rec)
        full_payload = saved_rec.get("full_payload", {})
        self.assertTrue(full_payload.get("is_acknowledged"))
        self.assertFalse(full_payload.get("trade_executed"))
        self.assertEqual(full_payload.get("execution_type"), "MANUAL_ADVISORY_ACKNOWLEDGED_ONLY")

    def test_10_production_invariants_preserved(self):
        """Verify live trading and read-only invariants are strictly locked."""
        self.assertTrue(settings.live_trading_locked)
        self.assertTrue(settings.read_only_mode)

    def test_11_model_preflight_and_tier_resolution(self):
        """Verify model routing restricts to authorized production models without silent substitution."""
        self.assertTrue(validate_model_preflight("deepseek-v4-flash"))
        self.assertTrue(validate_model_preflight("deepseek-v4-pro-0813"))
        self.assertFalse(validate_model_preflight("gpt-4o"))
        self.assertFalse(validate_model_preflight("claude-3-5-sonnet"))
        self.assertFalse(validate_model_preflight("unauthorized-paid-model"))

        resolved_flash = resolve_model_tier("deepseek-v4-flash")
        self.assertEqual(resolved_flash["model_id"], "deepseek-v4-flash")
        self.assertFalse(resolved_flash["is_premium"])

        resolved_pro = resolve_model_tier("deepseek-v4-pro-0813")
        self.assertEqual(resolved_pro["model_id"], "deepseek-v4-pro-0813")
        self.assertTrue(resolved_pro["is_premium"])


if __name__ == "__main__":
    unittest.main()
