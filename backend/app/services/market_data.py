"""
Tauric Market Data Service — Dynamic Multi-Market Spot Implementation
Integrates with MarketDataAdapterRegistry and DataQualityValidator.
Supports 28+ genuine Spot pairs quoted in both USDT and BTC.
Static misleading fallbacks (DEFAULT_FALLBACKS) are completely removed.
"""

import time
import asyncio
import logging
from typing import Dict, List, Any, Optional

from .market_data_adapters import (
    market_data_registry,
    MarketDataStatus,
    TickerSnapshot,
    DataQualityValidator,
    parse_market_pair,
)

logger = logging.getLogger(__name__)

SUPPORTED_SYMBOLS = [
    "BTC", "ETH", "SOL", "BNB", "ADA", "DOGE", "XRP", "AVAX", "DOT", "LINK",
    "NEAR", "LTC", "ATOM", "UNI", "APT", "BCH"
]

SUPPORTED_PAIRS = [
    # USDT Quoted Spot Pairs (16 pairs)
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "ADA/USDT", "DOGE/USDT", "XRP/USDT",
    "AVAX/USDT", "DOT/USDT", "LINK/USDT", "NEAR/USDT", "LTC/USDT", "ATOM/USDT", "UNI/USDT",
    "APT/USDT", "BCH/USDT",
    # BTC Quoted Spot Pairs (12 pairs)
    "ETH/BTC", "SOL/BTC", "BNB/BTC", "ADA/BTC", "DOGE/BTC", "XRP/BTC",
    "AVAX/BTC", "DOT/BTC", "LINK/BTC", "LTC/BTC", "ATOM/BTC", "NEAR/BTC"
]

# Memory cache with explicit provenance and timestamps
_cached_market_data: Dict[str, Any] = {}
_last_fetch_time: float = 0.0
CACHE_TTL = 4.0        # seconds: fresh cache window
MAX_STALE_TTL = 30.0   # seconds: maximum age after which cached data becomes UNAVAILABLE


def get_cached_asset_usd_price(asset: str) -> Optional[float]:
    """
    Returns live USD price from market data cache without inventing fake prices.
    Returns 1.0 for USD pegged stablecoins.
    """
    clean = asset.upper().strip()
    if clean in ("USDT", "USD", "USDC", "FDUSD", "BUSD", "DAI"):
        return 1.0

    pair_key = f"{clean}/USDT"
    if pair_key in _cached_market_data and _cached_market_data[pair_key].get("price"):
        return float(_cached_market_data[pair_key]["price"])

    if clean in _cached_market_data and _cached_market_data[clean].get("price"):
        return float(_cached_market_data[clean]["price"])

    return None


async def fetch_single_symbol_market_data(
    symbol: str,
    exchange: str = "binance"
) -> Dict[str, Any]:
    """
    Dynamically fetches real market ticker for ANY Spot pair via public adapter.
    Supports spot pairs quoted in USDT and BTC (e.g. ADA/USDT, ADA/BTC, BNB/BTC).
    Static-price fallbacks are strictly removed.
    Returns explicit status: PASS, STALE, UNAVAILABLE, FAIL, or UNKNOWN.
    """
    adapter = market_data_registry.get_adapter(exchange)
    base, quote, pair = adapter.parse_market_pair(symbol)
    display_pair = f"{base}/{quote}"
    canonical_id = f"crypto:{exchange}:{pair}"
    now_ms = int(time.time() * 1000)

    try:
        snapshot = await adapter.fetch_ticker(symbol)
        return _format_ticker_response(snapshot, exchange, display_pair, base)
    except Exception as e:
        logger.error(f"Error fetching ticker for {symbol} on {exchange}: {e}")
        return {
            "symbol": base,
            "pair": display_pair,
            "canonical_id": canonical_id,
            "exchange": exchange,
            "price": None,
            "bid": None,
            "ask": None,
            "spread": None,
            "spread_bps": None,
            "change_24h": None,
            "high_24h": None,
            "low_24h": None,
            "volume_24h": None,
            "quote_volume_24h": None,
            "market_status": "UNAVAILABLE",
            "status": MarketDataStatus.UNAVAILABLE.value,
            "source": f"crypto:{exchange}:spot",
            "updated_at": now_ms,
            "fetched_at": now_ms,
            "is_cached": False,
            "data_quality": {
                "status": MarketDataStatus.UNAVAILABLE.value,
                "quality_score": 0.0,
                "reasons": [f"Adapter exception: {type(e).__name__} - {str(e)}"],
                "rate_limited": adapter.is_rate_limited(),
            }
        }


async def fetch_live_market_data(
    exchange: str = "binance",
    force_refresh: bool = False
) -> Dict[str, Any]:
    """
    Fetches real Spot market data across all SUPPORTED_PAIRS (both USDT and BTC quoted).
    Zero static-price fallbacks.
    Returns explicit status, source, and data-quality metadata for each symbol.
    """
    global _cached_market_data, _last_fetch_time
    now = time.time()
    now_ms = int(now * 1000)
    cache_age = now - _last_fetch_time

    # 1. Fresh cache check
    if not force_refresh and _cached_market_data and cache_age < CACHE_TTL:
        return _cached_market_data

    adapter = market_data_registry.get_adapter(exchange)
    
    # 2. Concurrently fetch tickers across supported pairs (both USDT and BTC quoted)
    tasks = [adapter.fetch_ticker(p) for p in SUPPORTED_PAIRS]
    results_list = await asyncio.gather(*tasks, return_exceptions=True)

    results: Dict[str, Any] = {}
    any_success = False

    for p, res in zip(SUPPORTED_PAIRS, results_list):
        base, quote, pair = adapter.parse_market_pair(p)
        display_pair = f"{base}/{quote}"
        canonical_id = f"crypto:{exchange}:{pair}"

        if isinstance(res, TickerSnapshot):
            resp_dict = _format_ticker_response(res, exchange, display_pair, base)
            results[p] = resp_dict
            if quote == "USDT" and base not in results:
                results[base] = resp_dict
            if res.status == MarketDataStatus.PASS:
                any_success = True
        else:
            err_msg = str(res) if isinstance(res, Exception) else "Unknown fetch failure"
            err_dict = {
                "symbol": base,
                "pair": display_pair,
                "canonical_id": canonical_id,
                "exchange": exchange,
                "price": None,
                "bid": None,
                "ask": None,
                "spread": None,
                "spread_bps": None,
                "change_24h": None,
                "high_24h": None,
                "low_24h": None,
                "volume_24h": None,
                "quote_volume_24h": None,
                "market_status": "UNAVAILABLE",
                "status": MarketDataStatus.UNAVAILABLE.value,
                "source": f"crypto:{exchange}:spot",
                "updated_at": now_ms,
                "fetched_at": now_ms,
                "is_cached": False,
                "data_quality": {
                    "status": MarketDataStatus.UNAVAILABLE.value,
                    "quality_score": 0.0,
                    "reasons": [err_msg],
                    "rate_limited": adapter.is_rate_limited(),
                }
            }
            results[p] = err_dict

    # 3. If completely failed, check if previous cache can be used in STALE mode
    if not any_success and _cached_market_data:
        if cache_age < MAX_STALE_TTL:
            logger.warning(f"All live fetches failed. Returning STALE cache (age {cache_age:.1f}s)")
            stale_results: Dict[str, Any] = {}
            for sym, prev in _cached_market_data.items():
                stale_entry = dict(prev)
                stale_entry["status"] = MarketDataStatus.STALE.value
                stale_entry["market_status"] = "STALE"
                stale_entry["source"] = "cache:stale"
                stale_entry["is_cached"] = True
                stale_entry["data_quality"] = {
                    "status": MarketDataStatus.STALE.value,
                    "quality_score": 35.0,
                    "reasons": [f"Live fetch unavailable; serving cache aged {cache_age:.1f}s"],
                    "cache_age_seconds": round(cache_age, 1)
                }
                stale_results[sym] = stale_entry
            return stale_results

    if any_success:
        _cached_market_data = results
        _last_fetch_time = now

    return results


def _format_ticker_response(
    snapshot: TickerSnapshot,
    exchange: str,
    pair_display: str,
    clean_sym: str
) -> Dict[str, Any]:
    """
    Formats a TickerSnapshot into standard consumer response dict.
    Maintains backward compatibility while enforcing explicit status and provenance.
    """
    is_pass = snapshot.status == MarketDataStatus.PASS
    is_stale = snapshot.status == MarketDataStatus.STALE

    market_status = "NORMAL" if is_pass else "STALE" if is_stale else snapshot.status.value

    return {
        "symbol": clean_sym,
        "pair": pair_display,
        "canonical_id": snapshot.canonical_id,
        "exchange": snapshot.exchange,
        "price": snapshot.price,
        "bid": snapshot.bid,
        "ask": snapshot.ask,
        "spread": snapshot.spread,
        "spread_bps": snapshot.spread_bps,
        "change_24h": snapshot.change_24h,
        "high_24h": snapshot.high_24h,
        "low_24h": snapshot.low_24h,
        "volume_24h": snapshot.volume_24h,
        "quote_volume_24h": snapshot.quote_volume_24h,
        "market_status": market_status,
        "status": snapshot.status.value,
        "source": f"crypto:{exchange}:spot" if not is_stale else "cache:stale",
        "updated_at": snapshot.timestamp_ms,
        "fetched_at": snapshot.fetched_at_ms,
        "is_cached": False,
        "data_quality": {
            "status": snapshot.status.value,
            "quality_score": snapshot.quality_score,
            "reasons": snapshot.quality_reasons,
        }
    }
