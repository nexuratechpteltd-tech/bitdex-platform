import math
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional
from ..services.jev_client import jev_client
from ..services.market_data import fetch_live_market_data

router = APIRouter(prefix="/jev", tags=["TypeSafe Jev"])

class FastDecisionRequest(BaseModel):
    ticker: str = "ETH-USD"

class BlindCheckRequest(BaseModel):
    ticker: str = "ETH-USD"
    trade_plan: Dict[str, Any]

@router.get("/status")
async def get_jev_status():
    return await jev_client.check_connectivity()

@router.post("/fast-decision")
async def run_fast_decision(req: FastDecisionRequest):
    ticker = req.ticker.strip().upper()
    sym = ticker.replace("USDT", "").replace("-USD", "")
    
    live_markets = await fetch_live_market_data()
    market_state = live_markets.get(sym)
    if not market_state or market_state.get("status") not in ("PASS", "NORMAL"):
        raise HTTPException(
            status_code=503,
            detail=f"Live market data for {sym} is unavailable or failed quality checks. Jev evaluation cannot proceed."
        )
    
    price = market_state.get("price")
    if price is None or not (isinstance(price, (int, float)) and math.isfinite(price) and price > 0):
        raise HTTPException(
            status_code=503,
            detail=f"Live price for {sym} is non-finite or invalid. Jev evaluation cannot proceed."
        )

    result = await jev_client.fast_decision(ticker, market_state)
    return result

@router.post("/blind-check")
async def run_blind_check(req: BlindCheckRequest):
    ticker = req.ticker.strip().upper()
    sym = ticker.replace("USDT", "").replace("-USD", "")
    
    live_markets = await fetch_live_market_data()
    market_state = live_markets.get(sym)
    if not market_state or market_state.get("status") not in ("PASS", "NORMAL"):
        raise HTTPException(
            status_code=503,
            detail=f"Live market data for {sym} is unavailable or failed quality checks. Jev blind check cannot proceed."
        )
    
    price = market_state.get("price")
    if price is None or not (isinstance(price, (int, float)) and math.isfinite(price) and price > 0):
        raise HTTPException(
            status_code=503,
            detail=f"Live price for {sym} is non-finite or invalid. Jev blind check cannot proceed."
        )

    result = await jev_client.blind_check(ticker, req.trade_plan, market_state)
    return result
