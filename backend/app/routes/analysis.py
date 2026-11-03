import math
from fastapi import APIRouter
from ..services.market_data import fetch_live_market_data, SUPPORTED_SYMBOLS
from ..services.venice_client import venice_client

router = APIRouter(prefix="/analysis", tags=["AI Analysis"])

@router.get("")
async def get_all_analysis():
    market_data = await fetch_live_market_data()
    analyses = []
    
    for sym in SUPPORTED_SYMBOLS:
        info = market_data.get(sym, {})
        status = info.get("status")
        price = info.get("price")
        change_24h = info.get("change_24h")
        
        # Rigorous check: status must be PASS or NORMAL, price and change_24h must be finite numbers
        is_valid_data = (
            status in ("PASS", "NORMAL")
            and price is not None
            and change_24h is not None
            and isinstance(price, (int, float))
            and isinstance(change_24h, (int, float))
            and math.isfinite(price)
            and math.isfinite(change_24h)
        )
        
        if is_valid_data:
            res = await venice_client.get_regime_analysis(
                sym, 
                float(price), 
                float(change_24h)
            )
        else:
            # Safe UNAVAILABLE fallback without crashing
            res = {
                "symbol": sym,
                "status": "DATA_UNAVAILABLE",
                "regime": "UNKNOWN",
                "confidence": 0.0,
                "bias": "NO_DATA",
                "current_price": None,
                "change_24h": None,
                "reasoning_summary": f"Market data for {sym} is unavailable, stale, or failed quality validation (status: {status}).",
                "risk_warnings": ["Data quality gate triggered: live evaluation suspended.", "Fail-closed risk parameters active."],
                "execution_lock": "READ_ONLY_MODE_ENFORCED",
                "provider": "Venice AI (Optional Advisory)",
                "provider_mandatory": False
            }
        analyses.append(res)
        
    return {
        "provider": "Venice AI",
        "primary_model": venice_client.primary_model,
        "pro_model": venice_client.pro_model,
        "supported_regimes": ["SCALPABLE", "TRENDING_UP", "TRENDING_DOWN", "UNSAFE", "UNKNOWN"],
        "analyses": analyses,
        "execution_policy": "NO_ORDER_EXECUTION_ADVISORY_ONLY"
    }

@router.get("/regime/{symbol}")
async def get_symbol_analysis(symbol: str):
    sym = symbol.upper().replace("USDT", "").replace("-USD", "")
    market_data = await fetch_live_market_data()
    info = market_data.get(sym, {})
    status = info.get("status")
    price = info.get("price")
    change_24h = info.get("change_24h")
    
    is_valid_data = (
        status in ("PASS", "NORMAL")
        and price is not None
        and change_24h is not None
        and isinstance(price, (int, float))
        and isinstance(change_24h, (int, float))
        and math.isfinite(price)
        and math.isfinite(change_24h)
    )
    
    if is_valid_data:
        return await venice_client.get_regime_analysis(
            sym, 
            float(price), 
            float(change_24h)
        )
    else:
        return {
            "symbol": sym,
            "status": "DATA_UNAVAILABLE",
            "regime": "UNKNOWN",
            "confidence": 0.0,
            "bias": "NO_DATA",
            "current_price": None,
            "change_24h": None,
            "reasoning_summary": f"Market data for {sym} is unavailable, stale, or failed quality validation (status: {status}).",
            "risk_warnings": ["Data quality gate triggered: live evaluation suspended.", "Fail-closed risk parameters active."],
            "execution_lock": "READ_ONLY_MODE_ENFORCED",
            "provider": "Venice AI (Optional Advisory)",
            "provider_mandatory": False
        }
