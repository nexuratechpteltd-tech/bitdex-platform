import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, Query, HTTPException
from ..services.unified_signal_engine import unified_signal_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/signals", tags=["Unified AI Signals"])

@router.get("")
async def get_signals(
    tab: str = Query("ALL", description="Filter tab: ALL | BUY | SELL | SCALPING"),
    market: str = Query("ALL", description="Market filter: ALL | CRYPTO | FOREX | METAL"),
    search: Optional[str] = Query(None, description="Search ticker, symbol or asset name"),
    min_score: int = Query(0, description="Minimum confirmation score threshold (0-100)"),
    force_refresh: bool = Query(False, description="Bypass in-memory 15s cache")
) -> Dict[str, Any]:
    """
    Unified Technical Signals Feed (Deterministic, 100% Zero-AI-Cost).
    Returns rule-based signals published on live bars, scored from 0-100 based on
    confirming indicators (NEVER as a probability of profit).
    """
    try:
        raw_feed = await unified_signal_engine.generate_unified_signals(force_refresh=force_refresh)
        all_signals = raw_feed.get("signals", [])
        metrics = raw_feed.get("metrics", {})

        filtered = all_signals

        # 1. Tab Filter
        tab_upper = tab.upper()
        if tab_upper in ("BUY", "SELL", "SCALPING"):
            filtered = [s for s in filtered if s["tab_category"].upper() == tab_upper]

        # 2. Market Filter
        mkt_upper = market.upper()
        if mkt_upper in ("CRYPTO", "FOREX", "METAL"):
            filtered = [s for s in filtered if s["market"].upper() == mkt_upper]

        # 3. Minimum Score Filter
        if min_score > 0:
            filtered = [s for s in filtered if s["score"] >= min_score]

        # 4. Search Filter
        if search and search.strip():
            query = search.strip().lower()
            filtered = [
                s for s in filtered
                if query in s["symbol"].lower() or query in s["name"].lower() or query in s["instrument_id"].lower()
            ]

        return {
            "status": "SUCCESS",
            "metrics": metrics,
            "calendar": raw_feed.get("calendar", {
                "provider": "Finance Calendar",
                "official_url": "https://www.financecalendar.com",
                "status": "DISABLED",
                "approved_attribution_text": "Economic calendar data provided by Finance Calendar",
                "approved_attribution_link": "https://www.financecalendar.com",
                "event_risk_policy": "UNKNOWN",
                "warning": "Economic calendar provider is disabled in production isolation. Event risk remains UNKNOWN."
            }),
            "filter": {
                "tab": tab_upper,
                "market": mkt_upper,
                "search": search,
                "min_score": min_score,
                "returned_count": len(filtered)
            },
            "signals": filtered
        }
    except Exception as e:
        logger.error(f"Error fetching unified signals: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to compute unified technical signals")

@router.get("/detail/{instrument_id:path}")
async def get_signal_detail(instrument_id: str) -> Dict[str, Any]:
    """
    Returns full technical intelligence details and indicators for a single signal card.
    Used by the [ Expand ] modal. Zero-AI-cost.
    """
    try:
        raw_feed = await unified_signal_engine.generate_unified_signals(force_refresh=False)
        clean_raw = instrument_id.strip()
        match = next((s for s in raw_feed.get("signals", []) if s["instrument_id"] == clean_raw), None)
        if not match:
            # Try searching by clean symbol
            sym_clean = clean_raw.split(":")[-1].replace("/", "").replace("-", "").upper()
            match = next((s for s in raw_feed.get("signals", []) if s["symbol"].replace("/", "").replace("-", "").upper() == sym_clean), None)

        if not match:
            raise HTTPException(status_code=404, detail=f"Signal for {instrument_id} not found")

        return {
            "status": "SUCCESS",
            "signal": match
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving signal detail: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve signal detail")

@router.get("/meter/{instrument_id:path}")
async def get_live_meter(
    instrument_id: str,
    mock_state: Optional[str] = Query(None, description="Optional mock override: BULLISH | NEUTRAL | BEARISH"),
    mock_price: Optional[float] = Query(None, description="Optional mock live price"),
    mock_rsi: Optional[float] = Query(None, description="Optional mock RSI(14) level")
) -> Dict[str, Any]:
    """
    Live Bullish/Bearish Directional Meter (Deterministic, Zero-AI-Cost).
    Returns real-time 0-100 directional score, needle angle, bullish/neutral/bearish state,
    indicator components, data freshness status, and agreement/invalidation with original signal.
    """
    try:
        # Sanitize instrument_id to avoid HTTP 400 illegal characters on exchange queries
        sanitized_id = instrument_id.strip()
        meter_data = await unified_signal_engine.compute_live_directional_meter(
            instrument_id=sanitized_id,
            mock_state=mock_state,
            mock_price=mock_price,
            mock_rsi=mock_rsi
        )
        return meter_data
    except Exception as e:
        logger.error(f"Error computing live meter for {instrument_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to compute live meter: {str(e)}")

@router.get("/calendar")
async def get_macroeconomic_calendar(
    days: int = Query(14, description="Horizon days (default: 14)"),
    force_refresh: bool = Query(False, description="Bypass cache and force fetch")
) -> Dict[str, Any]:
    """
    Macroeconomic Event Calendar (14-Day Horizon).
    Returns normalized economic calendar events, live sync state, and approved attribution.
    """
    try:
        from ..services.finance_calendar_adapter import finance_calendar_adapter
        if force_refresh or finance_calendar_adapter.is_stale() or not finance_calendar_adapter._cached_events:
            await finance_calendar_adapter.fetch_events(days_ahead=days, force=force_refresh)
        return {
            "status": "SUCCESS",
            "calendar": finance_calendar_adapter.get_calendar_summary()
        }
    except Exception as e:
        logger.error(f"Error fetching macroeconomic calendar: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch macroeconomic calendar")

