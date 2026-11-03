from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from ..services.tauric_engine import tauric_engine

router = APIRouter(prefix="/research", tags=["Tauric Research"])

class RunRequest(BaseModel):
    ticker: str = "BTC-USD"
    analysts: List[str] = ["market", "sentiment", "news"]
    research_depth: int = 1
    trade_date: Optional[str] = None

@router.get("")
async def get_research_info():
    runs = tauric_engine.list_runs()
    return {
        "status": "ACTIVE",
        "total_runs": len(runs),
        "runs": runs,
        "engine": "Tauric / TradingAgents Multi-Agent Decision Graph"
    }

@router.get("/runs")
async def list_runs():
    return tauric_engine.list_runs()

@router.get("/runs/{run_id}")
async def get_run_details(run_id: str):
    run = tauric_engine.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return run

@router.post("/run")
async def trigger_run(req: RunRequest):
    ticker = req.ticker.strip().upper()
    if not ticker:
        raise HTTPException(status_code=400, detail="Ticker cannot be empty")
    
    analysts_mapped = []
    for a in req.analysts:
        if a == "sentiment":
            analysts_mapped.append("social")
        else:
            analysts_mapped.append(a)
    if not analysts_mapped:
        analysts_mapped = ["market", "social", "news"]

    depth = max(1, min(req.research_depth, 3))
    run_id = tauric_engine.start_run(
        ticker=ticker,
        analysts=analysts_mapped,
        research_depth=depth,
        trade_date=req.trade_date
    )
    return {
        "run_id": run_id,
        "ticker": ticker,
        "status": "RUNNING",
        "message": f"Tauric multi-agent research started for {ticker}"
    }
