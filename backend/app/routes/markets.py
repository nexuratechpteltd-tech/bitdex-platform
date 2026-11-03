from fastapi import HTTPException
from datetime import datetime, timezone
import math
import time
import httpx
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Query
from ..services.market_data import fetch_live_market_data, SUPPORTED_SYMBOLS, SUPPORTED_PAIRS
from ..services.venice_client import venice_client
from ..services.forex_market_data import INSTRUMENT_REGISTRY, forex_market_data

router = APIRouter(prefix="/markets", tags=["Markets"])

_BINANCE_PAIRS_CACHE: List[str] = []
_BINANCE_CACHE_TIME: float = 0.0

async def _fetch_binance_pairs() -> List[str]:
    global _BINANCE_PAIRS_CACHE, _BINANCE_CACHE_TIME
    now = time.time()
    if _BINANCE_PAIRS_CACHE and (now - _BINANCE_CACHE_TIME) < 3600:
        return _BINANCE_PAIRS_CACHE

    pairs = list(SUPPORTED_PAIRS)
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            r = await client.get("https://api.binance.com/api/v3/ticker/price")
            if r.status_code == 200:
                data = r.json()
                for item in data:
                    sym = item.get("symbol", "")
                    if sym.endswith("USDT") and not sym.endswith("UPUSDT") and not sym.endswith("DOWNUSDT"):
                        base = sym[:-4]
                        pair = f"{base}/USDT"
                        if pair not in pairs:
                            pairs.append(pair)
                    elif sym.endswith("BTC") and not sym.endswith("UPBTC") and not sym.endswith("DOWNBTC"):
                        base = sym[:-3]
                        pair = f"{base}/BTC"
                        if pair not in pairs:
                            pairs.append(pair)
                _BINANCE_PAIRS_CACHE = pairs
                _BINANCE_CACHE_TIME = now
    except Exception:
        if not _BINANCE_PAIRS_CACHE:
            _BINANCE_PAIRS_CACHE = pairs
    return _BINANCE_PAIRS_CACHE or pairs

@router.get("/search")
async def search_markets(q: str = Query("", description="Symbol or pair query, e.g. BTC, ETH, EUR, XAU")):
    """
    Universal Pair Search (Phase 5).
    Searches across Crypto (USDT and BTC quoted) and Forex & Metals instruments without billable AI runs.
    """
    query = q.strip().upper().replace(" ", "").replace("/", "")
    results = []
    
    # 1. Search Forex & Metals Instruments
    for inst_id, meta in INSTRUMENT_REGISTRY.items():
        clean = meta.get("clean_symbol", "")
        raw = meta.get("raw_symbol", "")
        base = meta.get("base", "")
        quote = meta.get("quote", "")
        name = meta.get("name", "").upper()
        clean_match = clean.replace("/", "")
        if not query or (query in clean_match or query in raw or query in base or query in quote or query in name):
            results.append({
                "canonical_symbol": clean,
                "symbol": clean,
                "asset_class": "FOREX" if meta.get("asset_class") == "fx" else "METALS",
                "base_asset": base,
                "quote_asset": quote,
                "data_provider": "YAHOO_FINANCE_COMPOSITE",
                "category": meta.get("category", "MAJORS"),
                "name": meta.get("name", clean),
                "is_tradable": False,  # read-only intelligence
                "is_active": True
            })
            
    # 2. Search Crypto Instruments (Binance public spot pairs)
    all_crypto_pairs = await _fetch_binance_pairs()
    for cp in all_crypto_pairs:
        base, quote = cp.split("/") if "/" in cp else (cp.replace("USDT", ""), "USDT")
        cp_match = cp.replace("/", "")
        if not query or (query in cp_match or query in base or query in quote):
            results.append({
                "canonical_symbol": cp,
                "symbol": cp,
                "asset_class": "CRYPTO",
                "base_asset": base,
                "quote_asset": quote,
                "data_provider": "BINANCE_PUBLIC_SPOT",
                "category": "MAJORS" if base in ("BTC", "ETH") else "ALTCOINS" if quote == "USDT" else "BTC_QUOTED",
                "name": f"{base} / {quote}",
                "is_tradable": False,  # read-only intelligence
                "is_active": True
            })
            if len(results) >= 60:
                break
            
    return {
        "status": "SUCCESS",
        "query": q,
        "count": len(results),
        "results": results[:50]
    }

@router.get("")
async def get_markets():
    market_data = await fetch_live_market_data()
    items = []
    
    for sym in SUPPORTED_SYMBOLS:
        info = market_data.get(sym, {})
        price = info.get("price")
        change_24h = info.get("change_24h")
        status = info.get("status", info.get("market_status", "UNAVAILABLE"))
        
        # Guard: Only call AI regime analysis if data is fresh (PASS/NORMAL) and price/change are finite numbers
        if (
            status in ("PASS", "NORMAL")
            and price is not None
            and change_24h is not None
            and isinstance(price, (int, float))
            and isinstance(change_24h, (int, float))
            and math.isfinite(price)
            and math.isfinite(change_24h)
        ):
            regime_info = await venice_client.get_regime_analysis(sym, float(price), float(change_24h))
            ai_regime = regime_info["regime"]
            ai_confidence = regime_info["confidence"]
            ai_model = regime_info["model"]
            last_analysis_time = regime_info["timestamp"]
        else:
            ai_regime = "DATA_UNAVAILABLE"
            ai_confidence = 0.0
            ai_model = "deterministic_guard"
            last_analysis_time = None
        
        items.append({
            "symbol": sym,
            "pair": f"{sym}/USDT",
            "price": price,
            "change_24h": change_24h,
            "high_24h": info.get("high_24h"),
            "low_24h": info.get("low_24h"),
            "volume_24h": info.get("volume_24h"),
            "market_status": info.get("market_status", status),
            "status": status,
            "data_quality": info.get("data_quality", {}),
            "ai_regime": ai_regime,
            "ai_confidence": ai_confidence,
            "ai_model": ai_model,
            "last_analysis_time": last_analysis_time
        })
        
    return {
        "count": len(items),
        "data": items,
        "source": "live_public_orderbooks",
        "trading_mode": "READ_ONLY"
    }

@router.get("/integrity-monitor")
async def get_market_data_integrity_monitor():
    """
    Market Data Integrity Monitor — live state from the WebSocket/polling integrity service.
    Provider connections, subscriptions, last messages, stale symbols, API failures,
    rate limits and cross-provider (Binance vs Bitget) discrepancies.
    """
    from ..services.market_integrity import market_integrity
    return market_integrity.monitor()


@router.get("/quotes")
async def get_verified_quotes(provider: Optional[str] = None, symbols: Optional[str] = None):
    """Per-symbol verified quotes with provider timestamp, receipt timestamp, age and data_state."""
    from ..services.market_integrity import market_integrity
    syms = [s.strip() for s in symbols.split(",") if s.strip()] if symbols else None
    return {"status": "SUCCESS", "quotes": market_integrity.quotes(provider, syms)}


@router.get("/market-cap")
async def get_market_caps():
    """Market capitalisation from CoinGecko (configured provider). Never estimated."""
    from ..services.market_integrity import market_integrity
    return {"status": "SUCCESS", "provider": "coingecko", "quotes": market_integrity.quotes("coingecko")}


@router.get("/overview")
async def get_markets_overview():
    """
    Combined Live Market Overview for Crypto (Binance Spot) and Forex (Yahoo Finance FX).
    Zero AI tokens consumed.
    """
    now = time.time()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # 1. Fetch Crypto
    crypto_data = await fetch_live_market_data()
    top_crypto_keys = ["BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "ADA", "AVAX"]
    crypto_items = []
    for k in top_crypto_keys:
        if k in crypto_data:
            c = crypto_data[k]
            crypto_items.append({
                "symbol": c.get("pair", f"{k}/USDT"),
                "base": k,
                "quote": "USDT",
                "name": k,
                "price": c.get("price"),
                "change_24h": c.get("change_24h"),
                "high_24h": c.get("high_24h"),
                "low_24h": c.get("low_24h"),
                "volume_24h": c.get("volume_24h"),
                "market": "CRYPTO",
                "status": c.get("status", "UNAVAILABLE"),
                "source": c.get("source", "crypto:binance:spot"),
                "freshness_sec": round(now - (c.get("fetched_at") / 1000.0), 1) if c.get("fetched_at") else None,
                "updated_at": c.get("updated_at")
            })

    # 1b. Also include BTC-quoted pairs from SUPPORTED_PAIRS (e.g. ADA/BTC)
    btc_pairs = [p for p in SUPPORTED_PAIRS if p.endswith("/BTC")]
    for p in btc_pairs:
        if p in crypto_data:
            c = crypto_data[p]
            base, quote = p.split("/")
            crypto_items.append({
                "symbol": p,
                "base": base,
                "quote": quote,
                "name": base,
                "price": c.get("price"),
                "change_24h": c.get("change_24h"),
                "high_24h": c.get("high_24h"),
                "low_24h": c.get("low_24h"),
                "volume_24h": c.get("volume_24h"),
                "market": "CRYPTO",
                "status": c.get("status", "UNAVAILABLE"),
                "source": c.get("source", "crypto:binance:spot"),
                "freshness_sec": round(now - (c.get("fetched_at") / 1000.0), 1) if c.get("fetched_at") else None,
                "updated_at": c.get("updated_at")
            })

    try:
        from ..services.market_integrity import market_integrity
        for it in crypto_items:
            api_pair = f"{it['base']}{it['quote']}"
            q = market_integrity.get("binance_spot", api_pair)
            it["data_state"] = q["data_state"] if q else ("LIVE" if it.get("status") == "PASS" else "UNAVAILABLE")
            it["provider_ts_utc"] = q["provider_timestamp_utc"] if q else now_iso
            mc = market_integrity.get("coingecko", it["base"])
            it["market_cap_usd"] = mc.get("market_cap_usd") if mc and mc["data_state"] in ("LIVE", "DELAYED") else None
            it["market_cap_source"] = "coingecko" if it["market_cap_usd"] else None
    except Exception:
        pass

    # 2. Fetch Forex
    top_fx = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD", "USD/CHF", "XAU/USD"]
    fx_items = []
    for f in top_fx:
        try:
            tick = await forex_market_data.fetch_ticker(f)
            p = tick.get("price") or tick.get("mid")
            fx_items.append({
                "symbol": tick.get("symbol", f),
                "base": tick.get("base", f.split("/")[0]),
                "quote": tick.get("quote", f.split("/")[1]),
                "name": tick.get("name", f),
                "price": p,
                "change_24h": tick.get("change_24h"),
                "high_24h": tick.get("high_24h"),
                "low_24h": tick.get("low_24h"),
                "spread_pips": tick.get("spread_pips"),
                "bid_ask_derivation": tick.get("bid_ask_derivation"),
                "data_state": tick.get("data_state", "UNAVAILABLE"),
                "provider_ts_utc": tick.get("provider_ts_utc"),
                "market": "METALS" if "XAU" in f else "FOREX",
                "status": tick.get("session", {}).get("market_status", "NORMAL"),
                "source": "forex:yahoo_finance_chart:composite_indicative",
                "freshness_sec": round(tick["quote_age_ms"] / 1000.0, 1) if tick.get("quote_age_ms") is not None else None,
                "updated_at": tick.get("quote_ts_utc")
            })
        except Exception:
            pass

    # 3. Dedicated Precious Metals (Gold & Silver)
    metals_list = ["XAU/USD", "XAG/USD"]
    metals_items = []
    for m in metals_list:
        try:
            tick = await forex_market_data.fetch_ticker(m)
            p = tick.get("price") or tick.get("mid")
            metals_items.append({
                "symbol": tick.get("symbol", m),
                "base": tick.get("base", m.split("/")[0]),
                "quote": tick.get("quote", m.split("/")[1]),
                "name": "Gold / US Dollar" if "XAU" in m else "Silver / US Dollar",
                "price": p,
                "change_24h": tick.get("change_24h"),
                "high_24h": tick.get("high_24h"),
                "low_24h": tick.get("low_24h"),
                "spread_pips": tick.get("spread_pips"),
                "bid_ask_derivation": tick.get("bid_ask_derivation"),
                "data_state": tick.get("data_state", "UNAVAILABLE"),
                "provider_ts_utc": tick.get("provider_ts_utc"),
                "market": "METALS",
                "status": tick.get("session", {}).get("market_status", "NORMAL"),
                "source": "forex:yahoo_finance_chart:composite_indicative",
                "freshness_sec": round(tick["quote_age_ms"] / 1000.0, 1) if tick.get("quote_age_ms") is not None else None,
                "updated_at": tick.get("quote_ts_utc")
            })
        except Exception:
            pass

    session = forex_market_data.get_current_session()
    
    return {
        "status": "SUCCESS",
        "timestamp_utc": now_iso,
        "crypto": crypto_items,
        "forex": fx_items,
        "metals": metals_items,
        "session": {
            "name": session.get("current_session") or session.get("name", "Active Session"),
            "market_open": session.get("market_open", True),
            "market_status": session.get("market_status", "NORMAL"),
            "next_major_boundary": session.get("next_major_boundary"),
            "session_time_pkt": session.get("session_time_pkt"),
            "session_time_utc": session.get("session_time_utc")
        }
    }


@router.get("/{symbol}")
async def get_market_detail(symbol: str):
    sym = symbol.upper().replace("/USDT", "").replace("USDT", "").replace("-USD", "")
    market_data = await fetch_live_market_data()
    if sym not in market_data:
        raise HTTPException(status_code=404, detail=f"Symbol {sym} is not a supported market. No substitute instrument is returned.")
        
    info = market_data.get(sym, {})
    price = info.get("price")
    change_24h = info.get("change_24h")
    status = info.get("status", info.get("market_status", "UNAVAILABLE"))

    if (
        status in ("PASS", "NORMAL")
        and price is not None
        and change_24h is not None
        and isinstance(price, (int, float))
        and isinstance(change_24h, (int, float))
        and math.isfinite(price)
        and math.isfinite(change_24h)
    ):
        analysis = await venice_client.get_regime_analysis(sym, float(price), float(change_24h))
    else:
        analysis = {
            "regime": "DATA_UNAVAILABLE",
            "confidence": 0.0,
            "model": "deterministic_guard",
            "timestamp": None,
            "reasoning": f"Market data for {sym} is currently {status}. AI regime analysis skipped."
        }
    
    return {
        "ticker": info,
        "ai_analysis": analysis
    }


