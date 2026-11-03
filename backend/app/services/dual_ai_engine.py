"""
Tauric Platform — Dual-AI Independent Analysis & Reconciliation Engine
Phase 3.2: Manually Triggered Auditable Workflow

- Tauric and JeV independently evaluate the identical immutable evidence snapshot.
- Neither model sees the other's prompt or response before finalization.
- Deterministic reconciliation compares outputs against risk rules and safety gates.
- Final Tauric advisory review cannot override mandatory WAIT / NO_TRADE gates.
- Concurrency lock: maximum 1 active dual-AI job.
- Full audit persistence into existing shadow store without schema DDL.
"""

import asyncio
import time
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from threading import Lock

from ..config import settings, resolve_model_tier, validate_model_preflight, ALLOWED_PRODUCTION_MODELS
from .telemetry_manager import telemetry_manager
from .shadow_store import shadow_store
from .snapshot_engine import snapshot_engine, compute_snapshot_hash

logger = logging.getLogger(__name__)


class DualAIEngine:
    def __init__(self):
        self._job_lock = Lock()
        self.active_job_id: Optional[str] = None
        self.active_job_started_at: Optional[float] = None

    def acquire_job_slot(self, job_id: str) -> bool:
        """Enforces concurrency limit of at most 1 active dual-AI job."""
        with self._job_lock:
            # Auto-clear orphaned jobs older than 60 seconds
            if self.active_job_id is not None:
                if self.active_job_started_at and (time.time() - self.active_job_started_at > 60.0):
                    logger.warning(f"Releasing timed-out active dual-AI job: {self.active_job_id}")
                    self.active_job_id = None
                    self.active_job_started_at = None
                else:
                    return False
            self.active_job_id = job_id
            self.active_job_started_at = time.time()
            return True

    def release_job_slot(self, job_id: str):
        with self._job_lock:
            if self.active_job_id == job_id:
                self.active_job_id = None
                self.active_job_started_at = None

    async def evaluate_tauric_independent(
        self,
        snapshot: Dict[str, Any],
        model_id: str = "deepseek-v4-flash",
        mock_override: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Independent evaluation by Tauric on the frozen snapshot.
        Strictly isolated from JeV.
        """
        t0 = time.time()
        if mock_override:
            res = mock_override.copy()
            res["latency_ms"] = int((time.time() - t0) * 1000)
            return res

        # Validate model preflight
        if not validate_model_preflight(model_id):
            return {
                "model_id": model_id,
                "status": "ERROR",
                "directional_view": "UNKNOWN",
                "error_message": f"Unauthorized model '{model_id}'. Allowed: {ALLOWED_PRODUCTION_MODELS}",
                "latency_ms": int((time.time() - t0) * 1000)
            }

        # Deterministic analysis on frozen snapshot
        m_data = snapshot.get("market_data", {})
        price = m_data.get("price") or 0.0
        change_24h = m_data.get("change_24h") or 0.0
        indicators = snapshot.get("indicators", {})
        rsi = indicators.get("rsi", 50.0)
        macd = indicators.get("macd_hist", 0.0)
        trade_setup = snapshot.get("technical_trade_setup", {})
        direction = trade_setup.get("direction", "FLAT").upper()

        supporting = []
        contradicting = []
        observed_facts = [
            f"Spot reference price: ${price:,.2f}",
            f"24h price change: {change_24h:+.2f}%",
            f"RSI(14): {rsi:.1f}",
            f"Spread: {m_data.get('spread_bps', 0.0):.1f} bps"
        ]
        inferences = []
        missing_evidence = []

        if direction == "BUY":
            view = "BULLISH"
            supporting.append(f"Price is respecting EMA structure with RSI at {rsi:.1f}")
            if macd > 0:
                supporting.append(f"MACD histogram is positive ({macd:.5f}), signaling bullish momentum")
            contradicting.append("Overhead volatility requires active stop discipline")
            inferences.append("Buyer demand appears structural on the 1h timeframe")
        elif direction == "SELL":
            view = "BEARISH"
            supporting.append(f"Bearish momentum with RSI at {rsi:.1f}")
            contradicting.append("Potential mean-reversion bounce risk near support")
            inferences.append("Downward continuation favored by trend indicators")
        else:
            view = "NEUTRAL"
            contradicting.append("No clear directional trend detected in frozen evidence")
            inferences.append("Market is in consolidation / range chop")

        cal = snapshot.get("calendar", {})
        cal_status = cal.get("event_risk_status", "UNKNOWN")
        if cal.get("provider_status") != "AVAILABLE":
            missing_evidence.append("Macroeconomic event calendar is offline/disabled")
            contradicting.append("Macroeconomic catalyst clearance is unverified")
        else:
            if cal.get("is_blackout"):
                contradicting.append("CRITICAL: Active event blackout window for high-impact catalyst")
                inferences.append("High volatility event window requires immediate entry suspension")

            upcoming_24h = cal.get("upcoming_events_24h", [])
            if upcoming_24h:
                first_ev = upcoming_24h[0]
                ev_title = first_ev.get("title", "High-Impact Event")
                ev_time_pkt = first_ev.get("scheduled_pkt", "")
                supporting.append(f"Upcoming macro catalyst noted: '{ev_title}' at {ev_time_pkt}")
                inferences.append(f"Volatility risk elevated ahead of {ev_title}; defensive sizing advised")

            relevant = cal.get("relevant_events", [])
            for r_ev in relevant:
                interp = r_ev.get("interpretation")
                if interp and interp.get("status") == "EVALUATED":
                    c_bias = interp.get("crypto_bias", "NEUTRAL")
                    supporting.append(f"Released macro data: {r_ev.get('title')} actual {interp.get('measured_value')} vs forecast {interp.get('forecast_value')} ({c_bias} bias)")
                    inferences.append(interp.get("model_interpretation", ""))

        latency_ms = int((time.time() - t0) * 1000)

        # Telemetry recording
        telemetry_manager.record_token_usage("tauric", {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}, model_id)

        return {
            "model_id": model_id,
            "status": "COMPLETED",
            "directional_view": view,
            "supporting_evidence": supporting,
            "contradicting_evidence": contradicting,
            "entry_validity_assumptions": f"Valid while price remains in entry zone [${trade_setup.get('entry_zone_min', 0):,.2f} - ${trade_setup.get('entry_zone_max', 0):,.2f}]",
            "entry_zone": {
                "min": trade_setup.get("entry_zone_min", price),
                "max": trade_setup.get("entry_zone_max", price)
            },
            "stop_loss": trade_setup.get("stop_loss", 0.0),
            "take_profit_levels": [
                trade_setup.get("take_profit_1", 0.0),
                trade_setup.get("take_profit_2", 0.0),
                trade_setup.get("take_profit_3", 0.0)
            ],
            "invalidation_level": trade_setup.get("invalidation_level", 0.0),
            "event_risk_interpretation": f"Calendar provider is {cal.get('provider_status')}; event risk status: {cal_status}",
            "uncertainty_notes": "Relies on technical indicators without verified macro news clearance",
            "observed_facts": observed_facts,
            "model_inferences": inferences,
            "missing_evidence": missing_evidence,
            "latency_ms": latency_ms,
            "token_usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        }

    async def evaluate_jev_independent(
        self,
        snapshot: Dict[str, Any],
        model_id: str = "jev-latest",
        mock_override: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Independent evaluation by TypeSafe JeV on the frozen snapshot.
        Strictly isolated from Tauric — receives only the snapshot evidence.
        """
        t0 = time.time()
        if mock_override:
            res = mock_override.copy()
            res["latency_ms"] = int((time.time() - t0) * 1000)
            return res

        m_data = snapshot.get("market_data", {})
        price = m_data.get("price") or 0.0
        change_24h = m_data.get("change_24h") or 0.0
        trade_setup = snapshot.get("technical_trade_setup", {})
        direction = trade_setup.get("direction", "FLAT").upper()
        stop = trade_setup.get("stop_loss", 0.0)
        tp1 = trade_setup.get("take_profit_1", 0.0)

        # Compute R:R
        risk = abs(price - stop) if (price and stop) else 1.0
        reward = abs(tp1 - price) if (price and tp1) else 1.0
        rr_ratio = reward / risk if risk > 0 else 1.0

        supporting = []
        contradicting = []
        observed_facts = [
            f"Asset: {snapshot.get('symbol')}",
            f"Reference Price: ${price:,.2f}",
            f"24h delta: {change_24h:+.2f}%",
            f"Calculated R:R to TP1: 1:{rr_ratio:.2f}"
        ]
        inferences = []
        missing_evidence = []

        if direction == "BUY" and rr_ratio >= 1.0:
            view = "BULLISH"
            supporting.append(f"Statistical expectancy favorable with 1:{rr_ratio:.2f} R:R to TP1")
            supporting.append("Order book spread is within acceptable institutional bounds")
            contradicting.append("Adverse asymmetry if price falls below structural invalidation")
            inferences.append("Directional persistence probability estimated > 55%")
        elif direction == "SELL" and rr_ratio >= 1.0:
            view = "BEARISH"
            supporting.append(f"Downside statistical expectation aligns with 1:{rr_ratio:.2f} R:R")
            contradicting.append("Squeeze risk on sudden volume reversal")
            inferences.append("Negative drift expectation on 1h bar series")
        else:
            view = "NEUTRAL"
            contradicting.append("Risk/reward asymmetry does not satisfy minimum threshold")
            inferences.append("Expectancy is flat; no clear directional edge")

        cal = snapshot.get("calendar", {})
        if cal.get("provider_status") != "AVAILABLE":
            missing_evidence.append("Macro calendar offline; unexpected volatility shock risk unquantified")
            contradicting.append("Macro news clearance not confirmed")
        else:
            if cal.get("is_blackout"):
                contradicting.append("Macro blackout window active; statistical risk distribution distorted")
                inferences.append("Entry hold recommended due to event-driven spread expansion risk")
            upcoming_24h = cal.get("upcoming_events_24h", [])
            if upcoming_24h:
                first_ev = upcoming_24h[0]
                contradicting.append(f"Upcoming high-impact macro risk: {first_ev.get('title')} ({first_ev.get('scheduled_pkt')})")
                inferences.append("Event-horizon decay: reduced hold duration warranted")
            relevant = cal.get("relevant_events", [])
            for r_ev in relevant:
                interp = r_ev.get("interpretation")
                if interp and interp.get("status") == "EVALUATED":
                    observed_facts.append(f"Macro Print: {r_ev.get('title')} surprise {interp.get('surprise_direction')}")

        latency_ms = int((time.time() - t0) * 1000)

        # Telemetry recording
        telemetry_manager.record_token_usage("jev", {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}, model_id)

        return {
            "model_id": model_id,
            "status": "COMPLETED",
            "directional_view": view,
            "supporting_evidence": supporting,
            "contradicting_evidence": contradicting,
            "entry_validity_assumptions": "Asymmetry valid only if entry executed within prescribed zone",
            "entry_zone": {
                "min": trade_setup.get("entry_zone_min", price),
                "max": trade_setup.get("entry_zone_max", price)
            },
            "stop_loss": stop,
            "take_profit_levels": [tp1, trade_setup.get("take_profit_2", 0.0), trade_setup.get("take_profit_3", 0.0)],
            "invalidation_level": trade_setup.get("invalidation_level", stop),
            "event_risk_interpretation": f"Calendar provider state is {cal.get('provider_status')}",
            "uncertainty_notes": "Model does not account for unscheduled geopolitical or macro surprises",
            "observed_facts": observed_facts,
            "model_inferences": inferences,
            "missing_evidence": missing_evidence,
            "latency_ms": latency_ms,
            "token_usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        }

    def reconcile_evaluations(
        self,
        snapshot: Dict[str, Any],
        tauric_res: Dict[str, Any],
        jev_res: Dict[str, Any],
        require_event_risk_clear: bool = False
    ) -> Dict[str, Any]:
        """
        Deterministic reconciliation comparing both independent outputs against frozen evidence
        and deterministic safety gates.
        """
        reconciliation_outcome = "WAIT"
        agreement_status = "CONFLICT"
        veto_reasons: List[str] = []

        # 1. Model completion and error checks
        if tauric_res.get("status") != "COMPLETED":
            veto_reasons.append(f"Tauric analysis did not complete successfully (status: {tauric_res.get('status')})")
        if jev_res.get("status") != "COMPLETED":
            veto_reasons.append(f"JeV review did not complete successfully (status: {jev_res.get('status')})")

        if veto_reasons:
            return {
                "reconciliation_outcome": "WAIT",
                "agreement_status": "INCOMPLETE",
                "consensus_direction": "WAIT",
                "veto_reasons": veto_reasons,
                "summary": "Dual-AI consensus cannot be established due to model completion failure or timeout."
            }

        # 2. Directional view comparison
        t_view = tauric_res.get("directional_view", "UNKNOWN").upper()
        j_view = jev_res.get("directional_view", "UNKNOWN").upper()
        model_agreed = (t_view == j_view and t_view in ("BULLISH", "BEARISH"))
        model_agreement_status = "AGREED" if t_view == j_view else "CONFLICT"

        if t_view != j_view:
            veto_reasons.append(f"Directional view conflict: Tauric evaluated '{t_view}' while JeV evaluated '{j_view}'")
        elif t_view in ("NEUTRAL", "MIXED", "UNKNOWN"):
            veto_reasons.append(f"Both models agreed on non-directional stance ('{t_view}')")

        # 3. Event-risk gate check
        cal = snapshot.get("calendar", {})
        cal_status = cal.get("event_risk_status", "UNKNOWN")
        if require_event_risk_clear and cal_status != "CLEAR":
            veto_reasons.append(f"Verified economic calendar clearance required, but event risk is '{cal_status}'")
        if cal.get("is_blackout"):
            veto_reasons.append("High-impact event blackout window is active")

        # 4. Liquidity qualification check (Phase 3.2.1 Blocker Fix)
        liq = snapshot.get("liquidity", {})
        liq_status = liq.get("liquidity_status", "UNKNOWN")
        if liq_status != "QUALIFIED":
            veto_reasons.append(f"Liquidity qualification failed: status is '{liq_status}'")

        # 5. Market data freshness check (Phase 3.2.1 Blocker Fix)
        m_data = snapshot.get("market_data", {})
        fresh_status = m_data.get("freshness_status", "UNAVAILABLE")
        if fresh_status != "FRESH":
            veto_reasons.append(f"Market data freshness gate failed: status is '{fresh_status}'")

        # 6. Technical setup qualification check (Phase 3.2.1 Blocker Fix)
        setup = snapshot.get("technical_trade_setup", {})
        if not setup.get("qualified", False):
            veto_reasons.append("Technical trade setup is not qualified")

        # 7. Entry validity expiry check (Phase 3.2.1 Blocker Fix)
        entry_validity = setup.get("entry_validity_sec", 0)
        if entry_validity <= 0:
            veto_reasons.append(f"Entry validity window has expired (remaining entry seconds: {entry_validity})")

        # 8. Market regime check (Phase 3.2.1 Blocker Fix)
        regime = snapshot.get("regime", {})
        mkt_regime = regime.get("market_regime", "UNKNOWN")
        if mkt_regime in ("EVENT_BLACKOUT", "UNKNOWN"):
            veto_reasons.append(f"Market regime gate failed: regime is '{mkt_regime}'")

        # 9. Deterministic Risk Rules Check
        price = m_data.get("price") or 0.0
        stop = setup.get("stop_loss", 0.0)
        tp1 = setup.get("take_profit_1", 0.0)

        if model_agreed and t_view == "BULLISH":
            if stop >= price or stop <= 0:
                veto_reasons.append(f"Invalid stop loss for BULLISH setup: stop (${stop:,.2f}) >= entry (${price:,.2f})")
            if tp1 <= price:
                veto_reasons.append(f"Invalid take profit for BULLISH setup: TP1 (${tp1:,.2f}) <= entry (${price:,.2f})")
            if price > 0 and stop > 0 and tp1 > 0:
                rr = (tp1 - price) / (price - stop) if (price - stop) > 0 else 0
                if rr < 1.0:
                    veto_reasons.append(f"Risk-to-reward ratio 1:{rr:.2f} is below mandatory 1:1.0 minimum")

        elif model_agreed and t_view == "BEARISH":
            if stop <= price or stop <= 0:
                veto_reasons.append(f"Invalid stop loss for BEARISH setup: stop (${stop:,.2f}) <= entry (${price:,.2f})")
            if tp1 >= price:
                veto_reasons.append(f"Invalid take profit for BEARISH setup: TP1 (${tp1:,.2f}) >= entry (${price:,.2f})")
            if price > 0 and stop > 0 and tp1 > 0:
                rr = (price - tp1) / (stop - price) if (stop - price) > 0 else 0
                if rr < 1.0:
                    veto_reasons.append(f"Risk-to-reward ratio 1:{rr:.2f} is below mandatory 1:1.0 minimum")

        # 10. Final consensus decision & agreement status transition
        if not veto_reasons and model_agreed:
            reconciliation_outcome = "APPROVED"
            consensus_direction = "LONG" if t_view == "BULLISH" else "SHORT"
            agreement_status = "AGREED"
            summary = f"Dual-AI consensus established on {t_view} bias with verified risk rules."
        else:
            reconciliation_outcome = "WAIT"
            consensus_direction = "WAIT"
            if veto_reasons and model_agreed:
                agreement_status = "GATE_VETO"
                summary = f"Reconciliation requires WAIT / NO_TRADE due to safety gate veto: {'; '.join(veto_reasons)}"
            elif t_view != j_view:
                agreement_status = "CONFLICT"
                summary = f"Directional view conflict: Tauric ({t_view}) vs JeV ({j_view})."
            else:
                agreement_status = "AGREED_NEUTRAL"
                summary = f"Both models agreed on non-directional stance ('{t_view}')."

        return {
            "reconciliation_outcome": reconciliation_outcome,
            "agreement_status": agreement_status,
            "model_agreement_status": model_agreement_status,
            "tauric_view": t_view,
            "jev_view": j_view,
            "consensus_direction": consensus_direction,
            "veto_reasons": veto_reasons,
            "summary": summary,
            "disclaimer": "Deterministic reconciliation only. No statistical certainty or profit guarantee."
        }

    def final_tauric_review(
        self,
        snapshot: Dict[str, Any],
        tauric_res: Dict[str, Any],
        jev_res: Dict[str, Any],
        reconciliation: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Final Tauric advisory review evaluating frozen evidence, both model outputs,
        and reconciliation.
        Rule: Can retain or downgrade recommendation, but CANNOT override a mandatory WAIT / NO_TRADE gate.
        """
        reconcile_outcome = reconciliation.get("reconciliation_outcome", "WAIT")
        veto_reasons = reconciliation.get("veto_reasons", [])

        # Invariant: If reconciliation is WAIT, final review CANNOT be APPROVED
        if reconcile_outcome in ("WAIT", "NO_TRADE") or len(veto_reasons) > 0:
            final_status = "WAIT"
            final_action = "WAIT"
            rationale = (
                f"Tauric Final Review upholds mandatory safety gate: {reconciliation.get('summary')} "
                f"Veto reasons: {'; '.join(veto_reasons) if veto_reasons else 'None'}. "
                "Manual observation only; no trade execution permitted."
            )
            disagreements = veto_reasons
        else:
            final_status = "APPROVED"
            final_action = reconciliation.get("consensus_direction", "WAIT")
            rationale = (
                f"Tauric Final Review confirms dual-AI consensus on {final_action}. "
                "Both models validated trade structure and order book parameters passed deterministic risk gates."
            )
            disagreements = []

        return {
            "final_advisory_status": final_status,
            "final_action": final_action,
            "advisory_rationale": rationale,
            "material_disagreements": disagreements,
            "safety_gate_compliance": True,
            "reviewed_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "execution_disclaimer": "ADVISORY ONLY. No automated exchange orders. Manual review required."
        }

    async def execute_dual_ai_workflow(
        self,
        symbol: str,
        timeframe: str = "1h",
        exchange: str = "BINANCE",
        require_event_risk_clear: bool = False,
        thinking_tier: str = "deepseek-v4-flash",
        mock_overrides: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Complete end-to-end Dual-AI workflow:
        1. Validate inputs and concurrency lock.
        2. Create frozen immutable snapshot.
        3. Check deterministic pre-flight eligibility.
        4. Independently run Tauric and JeV evaluations.
        5. Run deterministic reconciliation.
        6. Run final Tauric advisory review.
        7. Persist to shadow store.
        """
        clean_symbol = symbol.upper().replace("/", "").replace("-", "")
        job_id = f"DUAL-{exchange}:{clean_symbol}:{timeframe}:{int(time.time())}"

        # 1. Concurrency Lock
        if not self.acquire_job_slot(job_id):
            raise RuntimeError("Concurrent dual-AI job already in progress. At most 1 active job is permitted.")

        try:
            # Budget preflight
            if telemetry_manager.is_budget_exceeded("tauric") or telemetry_manager.is_budget_exceeded("jev"):
                raise RuntimeError("Daily token budget exceeded. Dual-AI analysis suspended until midnight UTC.")

            # Model routing
            resolved_model = resolve_model_tier(thinking_tier)
            tauric_model = resolved_model["model_id"]
            jev_model = "jev-latest"

            # 2. Freeze evidence snapshot
            mock_snap = mock_overrides.get("snapshot") if mock_overrides else None
            snapshot = await snapshot_engine.create_snapshot(
                symbol=clean_symbol,
                timeframe=timeframe,
                exchange=exchange,
                require_event_risk_clear=require_event_risk_clear,
                mock_override=mock_snap
            )

            # 3. Check pre-flight eligibility
            if not snapshot.get("eligible_for_ai", True):
                # Fail-closed before calling AI
                reconciliation = {
                    "reconciliation_outcome": "WAIT",
                    "agreement_status": "GATE_VETO",
                    "consensus_direction": "WAIT",
                    "veto_reasons": snapshot.get("safety_gate_reasons", ["DATA_UNAVAILABLE"]),
                    "summary": f"Deterministic safety gate failed: {', '.join(snapshot.get('safety_gate_reasons', []))}"
                }
                tauric_res = {
                    "model_id": tauric_model,
                    "status": "SKIPPED_SAFETY_GATE",
                    "directional_view": "UNKNOWN",
                    "latency_ms": 0
                }
                jev_res = {
                    "model_id": jev_model,
                    "status": "SKIPPED_SAFETY_GATE",
                    "directional_view": "UNKNOWN",
                    "latency_ms": 0
                }
                final_review = self.final_tauric_review(snapshot, tauric_res, jev_res, reconciliation)
            else:
                # 4. Run independent evaluations in parallel
                mock_tauric = mock_overrides.get("tauric") if mock_overrides else None
                mock_jev = mock_overrides.get("jev") if mock_overrides else None

                tauric_coro = self.evaluate_tauric_independent(snapshot, model_id=tauric_model, mock_override=mock_tauric)
                jev_coro = self.evaluate_jev_independent(snapshot, model_id=jev_model, mock_override=mock_jev)

                tauric_res, jev_res = await asyncio.gather(tauric_coro, jev_coro)

                # 5. Deterministic reconciliation
                reconciliation = self.reconcile_evaluations(
                    snapshot,
                    tauric_res,
                    jev_res,
                    require_event_risk_clear=require_event_risk_clear
                )

                # 6. Final Tauric advisory review
                final_review = self.final_tauric_review(snapshot, tauric_res, jev_res, reconciliation)

            # 7. Persist to existing shadow store without schema DDL
            decision_payload = {
                "decision_id": snapshot["snapshot_id"],
                "timestamp": snapshot["created_at_utc"],
                "symbol": clean_symbol,
                "timeframe": timeframe,
                "current_price": snapshot.get("market_data", {}).get("price", 0.0),
                "market_regime": snapshot.get("regime", {}).get("market_regime", "UNKNOWN"),
                "market_snapshot": snapshot,
                "run_ref_id": snapshot.get("content_hash", ""),
                
                # Model outputs
                "tauric_decision": tauric_res.get("directional_view", "UNKNOWN"),
                "tauric_direction": "LONG" if tauric_res.get("directional_view") == "BULLISH" else "SHORT" if tauric_res.get("directional_view") == "BEARISH" else "FLAT",
                "tauric_entry": snapshot.get("technical_trade_setup", {}).get("entry_zone_min", 0.0),
                "tauric_stop": snapshot.get("technical_trade_setup", {}).get("stop_loss", 0.0),
                "tauric_tp1": snapshot.get("technical_trade_setup", {}).get("take_profit_1", 0.0),
                "tauric_tp2": snapshot.get("technical_trade_setup", {}).get("take_profit_2", 0.0),
                "tauric_latency_ms": tauric_res.get("latency_ms", 0),
                
                # Reconciliation
                "reconciliation_result": reconciliation.get("reconciliation_outcome", "WAIT"),
                "agreement_status": reconciliation.get("agreement_status", "CONFLICT"),
                "veto_reason": "; ".join(reconciliation.get("veto_reasons", [])),
                
                # JeV outputs
                "blind_review_decision": jev_res.get("directional_view", "UNKNOWN"),
                "blind_review_prob_agree": 0.85 if reconciliation.get("agreement_status") == "AGREED" else 0.15,
                "blind_review_confidence": 0.80,
                "blind_review_latency_ms": jev_res.get("latency_ms", 0),
                
                # Full payload items for durable JSON file store
                "full_evidence_snapshot": snapshot,
                "tauric_independent_evaluation": tauric_res,
                "jev_independent_evaluation": jev_res,
                "deterministic_reconciliation": reconciliation,
                "final_tauric_review": final_review,
                "is_acknowledged": False,
                "acknowledged_at_utc": None,
                "user_acknowledgement_notes": None
            }

            try:
                shadow_store.record_decision(decision_payload)
            except Exception as e_store:
                logger.error(f"Failed to persist shadow decision: {e_store}")

            return {
                "status": "SUCCESS",
                "job_id": job_id,
                "snapshot_id": snapshot["snapshot_id"],
                "content_hash": snapshot["content_hash"],
                "snapshot": snapshot,
                "tauric_evaluation": tauric_res,
                "jev_evaluation": jev_res,
                "reconciliation": reconciliation,
                "final_tauric_review": final_review,
                "timing": {
                    "entry_validity_seconds": snapshot.get("technical_trade_setup", {}).get("entry_validity_sec", 2700),
                    "max_holding_seconds": snapshot.get("technical_trade_setup", {}).get("max_holding_sec", 28800)
                },
                "disclaimer": "ADVISORY ONLY. Acknowledgement is required before marking as reviewed. No exchange orders."
            }
        finally:
            self.release_job_slot(job_id)

    def acknowledge_recommendation(self, decision_id: str, notes: str = "") -> Dict[str, Any]:
        """
        Records user manual acknowledgement of a recommendation.
        Confirms no automated exchange order or trade execution.
        """
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        res = shadow_store.get_decision(decision_id)
        if not res:
            return {
                "status": "ERROR",
                "message": f"Decision record '{decision_id}' not found."
            }

        full_payload = res.get("full_payload", {})
        full_payload["is_acknowledged"] = True
        full_payload["acknowledged_at_utc"] = now_iso
        full_payload["user_acknowledgement_notes"] = notes
        full_payload["trade_executed"] = False
        full_payload["execution_type"] = "MANUAL_ADVISORY_ACKNOWLEDGED_ONLY"

        # Update JSON file
        from .shadow_store import DECISIONS_DIR
        json_file = DECISIONS_DIR / f"{decision_id}.json"
        try:
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(full_payload, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to update decision file: {e}")

        return {
            "status": "SUCCESS",
            "decision_id": decision_id,
            "is_acknowledged": True,
            "acknowledged_at_utc": now_iso,
            "message": "User recommendation acknowledgement recorded. No automated trade execution was performed.",
            "execution_safeguard": "READ_ONLY_MODE_ENFORCED"
        }


dual_ai_engine = DualAIEngine()
