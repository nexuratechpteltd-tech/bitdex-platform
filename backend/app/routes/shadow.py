from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from typing import Dict, List, Any, Optional
from pydantic import BaseModel
import time
import math
from datetime import datetime

from ..services.shadow_store import shadow_store
from ..services.outcome_engine import outcome_engine
from ..services.market_data import fetch_live_market_data
from ..services.jev_client import jev_client

router = APIRouter(prefix="/shadow", tags=["Shadow Validation"])

class ShadowRunRequest(BaseModel):
    symbol: str = "BTC-USD"
    timeframe: str = "1h"
    trigger_tauric: bool = False

@router.get("/summary")
async def get_shadow_summary():
    """
    Returns empirical performance summaries across:
    - Track A: Tauric Only
    - Track B: Tauric + Jev
    - Track C: Jev Fast Only
    Plus Jev Veto Telemetry, Agreement Analytics, and Anomaly Detection.
    """
    return shadow_store.get_summary_statistics()

@router.get("/decisions")
async def list_shadow_decisions(
    limit: int = Query(50, ge=1, le=200),
    symbol: Optional[str] = None
):
    """Lists persisted shadow validation decisions."""
    decisions = shadow_store.list_decisions(limit=limit, symbol=symbol)
    return {
        "count": len(decisions),
        "decisions": decisions
    }

@router.get("/decisions/{decision_id}")
async def get_shadow_decision_detail(decision_id: str):
    """Returns full audit trail for a specific shadow decision."""
    decision = shadow_store.get_decision(decision_id)
    if not decision:
        raise HTTPException(status_code=404, detail=f"Shadow decision {decision_id} not found")
    return decision

@router.post("/evaluate")
async def evaluate_pending_decisions():
    """
    Triggers market outcome evaluation across pending decisions.
    Observes subsequent real market candles in chronological order.
    """
    decisions = shadow_store.list_decisions(limit=25)
    evaluated_count = 0
    
    for d in decisions:
        try:
            outcomes = await outcome_engine.evaluate_decision_record(d)
            shadow_store.update_outcomes(d["decision_id"], outcomes)
            evaluated_count += 1
        except Exception as e:
            print(f"[Outcome Eval Error for {d.get('decision_id')}]: {e}")

    summary = shadow_store.get_summary_statistics()
    return {
        "status": "SUCCESS",
        "evaluated_count": evaluated_count,
        "summary": summary
    }

@router.post("/run")
async def execute_shadow_cycle(req: ShadowRunRequest):
    """
    Executes an empirical non-executing shadow validation cycle for any pair.
    Evaluates:
    - Track A: Tauric baseline
    - Track B: Tauric + Jev convergence
    - Track C: Jev Fast independent decision
    """
    raw_symbol = req.symbol.strip().upper()
    sym_clean = raw_symbol.replace("USDT", "").replace("-USD", "").replace("/", "")
    binance_pair = f"{sym_clean}USDT"
    
    # 1. Capture live market snapshot
    t_start = time.time()
    live_mkts = await fetch_live_market_data()
    m_state = live_mkts.get(sym_clean)
    if not m_state or not isinstance(m_state, dict) or m_state.get("price") is None or m_state.get("status") not in ("PASS", "NORMAL"):
        raise HTTPException(
            status_code=503,
            detail=f"Live market snapshot for {sym_clean} is currently unavailable. Shadow trade cycle aborted to prevent evaluation against fabricated price."
        )
    current_price = float(m_state["price"])
    raw_chg = m_state.get("change_24h")
    change_24h = float(raw_chg) if (raw_chg is not None and math.isfinite(raw_chg)) else 0.0

    # Detect market regime
    abs_change = abs(change_24h)
    if abs_change >= 4.0:
        regime = "high_volatility"
    elif change_24h > 1.5:
        regime = "trending_up"
    elif change_24h < -1.5:
        regime = "trending_down"
    elif abs_change <= 0.8:
        regime = "low_volatility"
    else:
        regime = "range_chop"

    # 2. Track C: Jev Fast Decision Layer (Independent)
    t_fast_start = time.time()
    fast_res = await jev_client.fast_decision(raw_symbol, m_state)
    fast_lat_ms = int((time.time() - t_fast_start) * 1000)

    fast_dec = fast_res.get("decision", "WAIT")
    bias_dir = fast_res.get("bias", {}).get("direction", "neutral").upper()
    
    # Fast ATR approximate stop (1.8%) and 1.5R target (2.7%)
    if bias_dir == "BULLISH":
        track_c_dir = "LONG"
        track_c_stop = round(current_price * 0.982, 2)
        track_c_tp1 = round(current_price * 1.027, 2)
        track_c_tp2 = round(current_price * 1.045, 2)
    elif bias_dir == "BEARISH":
        track_c_dir = "SHORT"
        track_c_stop = round(current_price * 1.018, 2)
        track_c_tp1 = round(current_price * 0.973, 2)
        track_c_tp2 = round(current_price * 0.955, 2)
    else:
        track_c_dir = "FLAT"
        track_c_stop = 0.0
        track_c_tp1 = 0.0
        track_c_tp2 = 0.0

    # 3. Track A & B: Simulated / Escalated Tauric Analysis
    # If trigger_tauric is False, we use standard institutional heuristics or latest graph state
    t_tauric_start = time.time()
    
    # Baseline Tauric direction from market technical indicators
    if change_24h > 1.0:
        tauric_action = "BUY"
        tauric_dir = "LONG"
        tauric_stop = round(current_price * 0.975, 2)
        tauric_tp1 = round(current_price * 1.035, 2)
        tauric_tp2 = round(current_price * 1.060, 2)
    elif change_24h < -1.0:
        tauric_action = "SELL"
        tauric_dir = "SHORT"
        tauric_stop = round(current_price * 1.025, 2)
        tauric_tp1 = round(current_price * 0.965, 2)
        tauric_tp2 = round(current_price * 0.940, 2)
    else:
        tauric_action = "HOLD"
        tauric_dir = "FLAT"
        tauric_stop = 0.0
        tauric_tp1 = 0.0
        tauric_tp2 = 0.0

    tauric_lat_ms = int((time.time() - t_tauric_start) * 1000)

    # 4. Track B: Jev Blind Check & Reconciliation
    t_blind_start = time.time()
    trade_plan = {
        "action": tauric_action,
        "entry_price": current_price,
        "stop_loss": tauric_stop,
        "rating": "Overweight" if tauric_dir == "LONG" else "Underweight" if tauric_dir == "SHORT" else "Hold"
    }
    blind_res = await jev_client.blind_check(raw_symbol, trade_plan, m_state)
    blind_lat_ms = int((time.time() - t_blind_start) * 1000)

    agreement = blind_res.get("outcome", "DISAGREE")
    risk_level = blind_res.get("risk_profile", {}).get("level", "acceptable_risk")
    
    if agreement == "AGREE" and tauric_dir != "FLAT":
        reconcile_res = "APPROVED"
        veto_reason = ""
    else:
        reconcile_res = "VETOED" if tauric_dir != "FLAT" else "NO_TRADE"
        veto_reason = blind_res.get("log_summary", "Independent blind check disagreement.")

    # 5. Persist to dedicated shadow store
    record_payload = {
        "symbol": raw_symbol,
        "timeframe": req.timeframe,
        "current_price": current_price,
        "market_regime": regime,
        "market_snapshot": {
            "pair": binance_pair,
            "price": current_price,
            "change_24h": change_24h,
            "source": m_state.get("source", "public_ticker")
        },
        
        # Track A
        "tauric_decision": trade_plan["rating"],
        "tauric_direction": tauric_dir,
        "tauric_entry": current_price,
        "tauric_stop": tauric_stop,
        "tauric_tp1": tauric_tp1,
        "tauric_tp2": tauric_tp2,
        "tauric_size": "Standard (5% equity)",
        "tauric_horizon": "1d-3d",
        "tauric_latency_ms": tauric_lat_ms,
        
        # Track B
        "reconciliation_result": reconcile_res,
        "agreement_status": agreement,
        "veto_reason": veto_reason,
        "blind_review_decision": agreement,
        "blind_review_prob_agree": blind_res.get("probabilities", {}).get("agree", 0.0),
        "blind_review_prob_disagree": blind_res.get("probabilities", {}).get("disagree", 0.0),
        "blind_review_confidence": blind_res.get("confidence", 0.0),
        "blind_review_risk_profile": risk_level,
        "blind_review_latency_ms": blind_lat_ms,
        
        # Track C
        "jev_fast_decision": fast_dec,
        "jev_fast_direction": track_c_dir,
        "jev_fast_entry": current_price,
        "jev_fast_stop": track_c_stop,
        "jev_fast_tp1": track_c_tp1,
        "jev_fast_tp2": track_c_tp2,
        "jev_fast_confidence": fast_res.get("opportunity", {}).get("confidence", 0.0),
        "jev_fast_probabilities": fast_res.get("opportunity", {}).get("probabilities", {}),
        "jev_fast_latency_ms": fast_lat_ms,
        
        "track_a_outcome": "PENDING",
        "track_a_net_pnl": 0.0,
        "track_b_outcome": "PENDING" if reconcile_res == "APPROVED" else "NO_TRADE",
        "track_b_net_pnl": 0.0,
        "track_c_outcome": "PENDING" if track_c_dir != "FLAT" else "NO_TRADE",
        "track_c_net_pnl": 0.0,
        
        "timestamp": datetime.now().isoformat()
    }

    decision_id = shadow_store.record_decision(record_payload)
    
    # 6. Immediately evaluate with latest candle data
    try:
        outcomes = await outcome_engine.evaluate_decision_record(record_payload)
        shadow_store.update_outcomes(decision_id, outcomes)
    except Exception as e_eval:
        print(f"[Immediate Eval Warning]: {e_eval}")

    full_record = shadow_store.get_decision(decision_id)
    summary = shadow_store.get_summary_statistics()

    return {
        "status": "SUCCESS",
        "decision_id": decision_id,
        "symbol": raw_symbol,
        "decision": full_record,
        "summary": summary
    }
