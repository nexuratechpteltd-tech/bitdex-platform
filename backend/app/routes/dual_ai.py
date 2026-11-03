"""
Tauric Platform — Dual-AI Analysis & Reconciliation API Route
Phase 3.2: Manually Triggered Dual-AI Analysis & Advisory Review

Enforces:
- Explicit user submission only (no calls on page load/navigation)
- Max 1 active concurrent job (409 Conflict if busy)
- Cost & token budget preflight (503 if budget exceeded)
- Model preflight against allowed production models
- Deterministic reconciliation & final Tauric review
- Read-only safety invariants (no exchange orders)
"""

import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..services.snapshot_engine import snapshot_engine
from ..services.dual_ai_engine import dual_ai_engine
from ..services.shadow_store import shadow_store
from ..services.telemetry_manager import telemetry_manager
from ..config import validate_model_preflight, resolve_model_tier

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dual-ai", tags=["Dual-AI Analysis & Reconciliation"])


class SnapshotRequest(BaseModel):
    symbol: str = Field(..., description="Trading pair, e.g. BTCUSDT, ETHUSDT")
    timeframe: str = Field("1h", description="Candle timeframe, e.g. 1h, 4h, 15m")
    exchange: str = Field("BINANCE", description="Exchange: BINANCE or BYBIT")
    require_event_risk_clear: bool = Field(False, description="Require verified economic calendar clearance")


class DualAIAnalysisRequest(BaseModel):
    symbol: str = Field(..., description="Trading pair, e.g. BTCUSDT, ETHUSDT")
    timeframe: str = Field("1h", description="Candle timeframe, e.g. 1h, 4h, 15m")
    exchange: str = Field("BINANCE", description="Exchange: BINANCE or BYBIT")
    require_event_risk_clear: bool = Field(False, description="Require verified economic calendar clearance")
    thinking_tier: str = Field("deepseek-v4-flash", description="Model tier: deepseek-v4-flash or deepseek-v4-pro-0813")


class AcknowledgeRequest(BaseModel):
    decision_id: str = Field(..., description="Snapshot ID / Decision ID to acknowledge")
    notes: Optional[str] = Field("", description="Optional user review notes")


@router.post("/snapshot")
async def generate_frozen_snapshot(req: SnapshotRequest) -> Dict[str, Any]:
    """
    Generates a deterministic frozen evidence snapshot with SHA-256 content hash.
    Zero AI cost. Evaluates data freshness and deterministic safety eligibility.
    """
    try:
        snapshot = await snapshot_engine.create_snapshot(
            symbol=req.symbol,
            timeframe=req.timeframe,
            exchange=req.exchange,
            require_event_risk_clear=req.require_event_risk_clear
        )
        return {
            "status": "SUCCESS",
            "snapshot_id": snapshot["snapshot_id"],
            "content_hash": snapshot["content_hash"],
            "snapshot": snapshot
        }
    except Exception as e:
        logger.error(f"Failed to generate evidence snapshot: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to freeze evidence snapshot: {str(e)}")


@router.post("/analyze")
async def run_dual_ai_analysis(req: DualAIAnalysisRequest) -> Dict[str, Any]:
    """
    Explicit user action triggering the Dual-AI Analysis workflow:
    1. Validates model preflight & token budget
    2. Enforces concurrency limit (max 1 active job)
    3. Creates immutable frozen snapshot
    4. Evaluates Tauric & JeV independently
    5. Reconciles deterministically (conflict -> WAIT)
    6. Runs final Tauric review (cannot override WAIT)
    7. Persists full auditable record in shadow store
    """
    # 1. Model preflight
    resolved = resolve_model_tier(req.thinking_tier)
    model_id = resolved["model_id"]
    if not validate_model_preflight(model_id):
        raise HTTPException(
            status_code=400,
            detail=f"Requested model '{req.thinking_tier}' is unauthorized. Allowed production models: deepseek-v4-flash, deepseek-v4-pro-0813"
        )

    # 2. Token budget preflight
    if telemetry_manager.is_budget_exceeded("tauric") or telemetry_manager.is_budget_exceeded("jev"):
        raise HTTPException(
            status_code=503,
            detail="Daily analysis token budget exceeded. Analysis suspended until midnight UTC."
        )

    # 3. Execute dual-AI workflow
    try:
        result = await dual_ai_engine.execute_dual_ai_workflow(
            symbol=req.symbol,
            timeframe=req.timeframe,
            exchange=req.exchange,
            require_event_risk_clear=req.require_event_risk_clear,
            thinking_tier=model_id
        )
        return result
    except RuntimeError as re:
        msg = str(re)
        if "Concurrent dual-AI job already in progress" in msg:
            raise HTTPException(status_code=409, detail=msg)
        elif "budget exceeded" in msg.lower():
            raise HTTPException(status_code=503, detail=msg)
        else:
            raise HTTPException(status_code=400, detail=msg)
    except Exception as e:
        logger.error(f"Error in dual-AI execution: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Dual-AI execution failure: {str(e)}")


@router.post("/acknowledge")
async def acknowledge_recommendation(req: AcknowledgeRequest) -> Dict[str, Any]:
    """
    Records explicit user acknowledgement of a dual-AI recommendation.
    Explicitly affirms: acknowledgement is NOT an exchange order and performs no execution.
    """
    try:
        res = dual_ai_engine.acknowledge_recommendation(
            decision_id=req.decision_id,
            notes=req.notes or ""
        )
        if res.get("status") == "ERROR":
            raise HTTPException(status_code=404, detail=res.get("message"))
        return res
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error recording acknowledgement: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to record acknowledgement: {str(e)}")


@router.get("/decisions")
async def list_decisions(
    limit: int = Query(20, description="Max decisions to return"),
    symbol: Optional[str] = Query(None, description="Optional symbol filter")
) -> Dict[str, Any]:
    """
    Lists historical dual-AI / shadow decisions from the auditable store.
    """
    try:
        rows = shadow_store.list_decisions(limit=limit, symbol=symbol)
        return {
            "status": "SUCCESS",
            "count": len(rows),
            "decisions": rows
        }
    except Exception as e:
        logger.error(f"Error listing decisions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve decision audit history")


@router.get("/decision/{decision_id}")
async def get_decision_detail(decision_id: str) -> Dict[str, Any]:
    """
    Retrieves a single full decision record including snapshot, model outputs,
    reconciliation, and acknowledgement status.
    """
    try:
        row = shadow_store.get_decision(decision_id)
        if not row:
            raise HTTPException(status_code=404, detail=f"Decision '{decision_id}' not found.")
        return {
            "status": "SUCCESS",
            "decision": row
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching decision detail: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve decision record")
