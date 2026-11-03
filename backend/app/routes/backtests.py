from fastapi import APIRouter
from ..services.research_store import get_backtest_runs

router = APIRouter(prefix="/backtests", tags=["Backtests"])

@router.get("")
async def get_backtests():
    bts = get_backtest_runs()
    return {
        "total_backtests": len(bts),
        "backtests": bts,
        "engine": "Tauric Vectorized & Event-Driven Engine"
    }
