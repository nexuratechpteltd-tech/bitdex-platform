import sys
import json
import asyncio
from pathlib import Path
from datetime import datetime

# Add backend to path
sys.path.insert(0, "/opt/tauric-platform/backend")

from app.services.shadow_store import shadow_store
from app.services.outcome_engine import outcome_engine

REPORTS_DIR = Path("/opt/tauric-platform/backend/data/reports")

async def seed():
    print("Initializing shadow validation store...")
    count = 0
    
    # 1. Ingest RUN-ETH-USD-20260929_125459
    eth_path = REPORTS_DIR / "ETH-USD_20260929_125459" / "run_data.json"
    if eth_path.exists():
        try:
            with open(eth_path, "r", encoding="utf-8") as f:
                r = json.load(f)
            
            jfd = r.get("jev_fast_decision") or {}
            jbc = r.get("jev_blind_check") or {}
            trader = r.get("trading_team", {}).get("trader") or {}
            pm = r.get("portfolio_manager") or {}
            
            entry = 2711.28
            stop = 2850.0
            tp1 = round(entry * 0.965, 2)
            tp2 = round(entry * 0.940, 2)
            
            eth_rec = {
                "decision_id": "SHD-ETH-USD-20260929_125459-SEED01",
                "timestamp": r.get("start_time", "2026-09-29T12:54:59"),
                "symbol": "ETH-USD",
                "timeframe": "1d",
                "current_price": entry,
                "market_regime": "trending_up",
                "market_snapshot": jfd.get("telemetry", {"price": entry, "change_24h": 2.21}),
                
                # Track A
                "tauric_decision": pm.get("rating", "Underweight"),
                "tauric_direction": "SHORT",
                "tauric_entry": entry,
                "tauric_stop": stop,
                "tauric_tp1": tp1,
                "tauric_tp2": tp2,
                "tauric_size": "Standard (5% equity)",
                "tauric_horizon": "1w-2w",
                "tauric_latency_ms": 1120000,
                
                # Track B
                "reconciliation_result": "VETOED",
                "agreement_status": "DISAGREE",
                "veto_reason": jbc.get("log_summary", "Jev Blind Check DISAGREE with Tauric Hold proposal (Agree Prob: 1.0%, Confidence: 98.0%). Final Shadow Decision: NO_TRADE."),
                "blind_review_decision": "DISAGREE",
                "blind_review_prob_agree": 0.01,
                "blind_review_prob_disagree": 0.99,
                "blind_review_confidence": 0.98,
                "blind_review_risk_profile": "unacceptable_risk",
                "blind_review_latency_ms": 1350,
                
                # Track C
                "jev_fast_decision": "WAIT",
                "jev_fast_direction": "LONG",
                "jev_fast_entry": entry,
                "jev_fast_stop": round(entry * 0.982, 2),
                "jev_fast_tp1": round(entry * 1.027, 2),
                "jev_fast_tp2": round(entry * 1.045, 2),
                "jev_fast_confidence": 0.30,
                "jev_fast_probabilities": {"wait": 0.53, "scalp": 0.45, "setup_detected": 0.02},
                "jev_fast_latency_ms": 1250,
                
                "run_ref_id": "RUN-ETH-USD-20260929_125459"
            }
            
            did = shadow_store.record_decision(eth_rec)
            outcomes = await outcome_engine.evaluate_decision_record(eth_rec)
            shadow_store.update_outcomes(did, outcomes)
            print(f"Seeded ETH-USD: {did} -> {outcomes['track_a_outcome']}")
            count += 1
        except Exception as e:
            print(f"Error seeding ETH: {e}")

    # 2. Ingest RUN-SOL-USD-20260929_110207
    sol_path = REPORTS_DIR / "SOL-USD_20260929_110207" / "run_data.json"
    if sol_path.exists():
        try:
            with open(sol_path, "r", encoding="utf-8") as f:
                r = json.load(f)
            
            entry = 117.50
            stop = 130.00
            tp1 = 110.45
            tp2 = 100.34
            
            sol_rec = {
                "decision_id": "SHD-SOL-USD-20260929_110207-SEED02",
                "timestamp": r.get("start_time", "2026-09-29T11:02:07"),
                "symbol": "SOL-USD",
                "timeframe": "1d",
                "current_price": entry,
                "market_regime": "trending_down",
                "market_snapshot": {"price": entry, "change_24h": -2.40},
                
                # Track A
                "tauric_decision": "Sell",
                "tauric_direction": "SHORT",
                "tauric_entry": entry,
                "tauric_stop": stop,
                "tauric_tp1": tp1,
                "tauric_tp2": tp2,
                "tauric_size": "Standard (5% equity)",
                "tauric_horizon": "1w-2w",
                "tauric_latency_ms": 1440000,
                
                # Track B
                "reconciliation_result": "APPROVED",
                "agreement_status": "AGREE",
                "veto_reason": "",
                "blind_review_decision": "AGREE",
                "blind_review_prob_agree": 0.88,
                "blind_review_prob_disagree": 0.12,
                "blind_review_confidence": 0.85,
                "blind_review_risk_profile": "acceptable_risk",
                "blind_review_latency_ms": 1100,
                
                # Track C
                "jev_fast_decision": "SCALP",
                "jev_fast_direction": "SHORT",
                "jev_fast_entry": entry,
                "jev_fast_stop": 119.50,
                "jev_fast_tp1": 114.20,
                "jev_fast_tp2": 111.00,
                "jev_fast_confidence": 0.78,
                "jev_fast_probabilities": {"scalp": 0.78, "wait": 0.15, "setup_detected": 0.07},
                "jev_fast_latency_ms": 1400,
                
                "run_ref_id": "RUN-SOL-USD-20260929_110207"
            }
            
            did = shadow_store.record_decision(sol_rec)
            outcomes = await outcome_engine.evaluate_decision_record(sol_rec)
            shadow_store.update_outcomes(did, outcomes)
            print(f"Seeded SOL-USD: {did} -> {outcomes['track_a_outcome']}")
            count += 1
        except Exception as e:
            print(f"Error seeding SOL: {e}")

    summary = shadow_store.get_summary_statistics()
    print("Seeding complete. Current shadow sample:", summary["current_shadow_sample"])

if __name__ == "__main__":
    asyncio.run(seed())
