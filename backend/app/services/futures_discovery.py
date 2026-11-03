"""
BITDEX Autonomous Futures Market Discovery Service
===================================================
Scans Binance USD(S)-M Futures universe, dynamically filters eligible trading
pairs, screens liquidity, spreads, volatility, and filters, and ranks candidate pairs.
"""

import time
import math
import logging
from typing import Optional, Dict, Any, List
import httpx

from .binance_futures_adapter import BinanceFuturesAdapter, BinanceFuturesError

logger = logging.getLogger("bitdex.futures.discovery")


class MarketDiscoveryService:
    """Discovers and filters eligible Binance USD(S)-M Futures pairs for scalping."""

    DEFAULT_MIN_QUOTE_VOLUME_USD = 20_000_000.0  # $20M 24h volume
    DEFAULT_MAX_SPREAD_RATIO = 0.0005             # 0.05% max spread (5 bps)
    DEFAULT_MAX_DATA_AGE_MS = 3000                # 3 seconds freshness limit

    def __init__(
        self,
        adapter: Optional[BinanceFuturesAdapter] = None,
        min_quote_volume: float = DEFAULT_MIN_QUOTE_VOLUME_USD,
        max_spread_ratio: float = DEFAULT_MAX_SPREAD_RATIO,
        max_data_age_ms: int = DEFAULT_MAX_DATA_AGE_MS,
    ):
        self.adapter = adapter or BinanceFuturesAdapter(environment="testnet")
        self.min_quote_volume = min_quote_volume
        self.max_spread_ratio = max_spread_ratio
        self.max_data_age_ms = max_data_age_ms

    def fetch_24hr_tickers(self) -> List[Dict[str, Any]]:
        """GET /fapi/v1/ticker/24hr - fetch 24h market stats for all symbols."""
        res = self.adapter._request("GET", "/fapi/v1/ticker/24hr")
        if isinstance(res, list):
            return res
        return [res] if isinstance(res, dict) else []

    def fetch_book_tickers(self) -> Dict[str, Dict[str, float]]:
        """GET /fapi/v1/ticker/bookTicker - fetch best bid/ask for spread calculations."""
        res = self.adapter._request("GET", "/fapi/v1/ticker/bookTicker")
        book_map = {}
        items = res if isinstance(res, list) else [res]
        for it in items:
            sym = it.get("symbol")
            if sym:
                try:
                    bid = float(it.get("bidPrice", 0.0))
                    ask = float(it.get("askPrice", 0.0))
                    bid_qty = float(it.get("bidQty", 0.0))
                    ask_qty = float(it.get("askQty", 0.0))
                    book_map[sym] = {
                        "bid": bid,
                        "ask": ask,
                        "bid_qty": bid_qty,
                        "ask_qty": ask_qty,
                        "spread": ask - bid,
                        "spread_ratio": ((ask - bid) / ask) if ask > 0 else 1.0
                    }
                except (ValueError, TypeError):
                    continue
        return book_map

    def fetch_klines(self, symbol: str, interval: str = "5m", limit: int = 30) -> List[Dict[str, Any]]:
        """GET /fapi/v1/klines - fetch recent candles."""
        params = {"symbol": symbol.upper(), "interval": interval, "limit": limit}
        res = self.adapter._request("GET", "/fapi/v1/klines", params=params)
        klines = []
        for k in res:
            klines.append({
                "open_time": int(k[0]),
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "close_time": int(k[6]),
                "quote_volume": float(k[7]),
                "trades_count": int(k[8]),
            })
        return klines

    def compute_atr(self, klines: List[Dict[str, Any]], period: int = 14) -> float:
        """Compute Average True Range from klines."""
        if len(klines) < 2:
            return 0.0
        tr_list = []
        for i in range(1, len(klines)):
            high = klines[i]["high"]
            low = klines[i]["low"]
            prev_close = klines[i - 1]["close"]
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_list.append(tr)
        if not tr_list:
            return 0.0
        recent_trs = tr_list[-period:]
        return sum(recent_trs) / len(recent_trs)

    def scan_and_rank_eligible_pairs(
        self,
        universe_override: Optional[List[str]] = None,
        max_candidates: int = 10,
    ) -> Dict[str, Any]:
        """
        Scan all Binance USD(S)-M contracts and return ranked eligible candidates.
        Also returns detailed rejection logs for auditing.
        """
        t0 = int(time.time() * 1000)
        try:
            exchange_info = self.adapter.get_exchange_info()
            symbols_meta = {s["symbol"]: s for s in exchange_info.get("symbols", [])}
        except Exception as e:
            logger.error("Failed to fetch exchangeInfo: %s", str(e))
            return {"status": "FAILED", "error": str(e), "candidates": [], "rejected": []}

        try:
            all_tickers = self.fetch_24hr_tickers()
            book_tickers = self.fetch_book_tickers()
        except Exception as e:
            logger.error("Failed to fetch ticker data: %s", str(e))
            return {"status": "FAILED", "error": str(e), "candidates": [], "rejected": []}

        now_ms = int(time.time() * 1000)
        eligible_candidates = []
        rejected_symbols = []

        for t in all_tickers:
            sym = t.get("symbol", "")
            if not sym.endswith("USDT"):
                continue  # USDT contracts only

            if universe_override and sym not in universe_override:
                continue

            meta = symbols_meta.get(sym)
            if not meta:
                rejected_symbols.append({"symbol": sym, "reason": "SYMBOL_META_NOT_FOUND"})
                continue

            # 1. Trading status
            if meta.get("status") != "TRADING":
                rejected_symbols.append({"symbol": sym, "reason": f"STATUS_NOT_TRADING ({meta.get('status')})"})
                continue

            # 2. Market data freshness
            close_time = int(t.get("closeTime", 0))
            if close_time > 0 and (now_ms - close_time) > self.max_data_age_ms + 10_000:
                # Allow testnet leeway of 10s if testnet traffic is slower
                rejected_symbols.append({"symbol": sym, "reason": "STALE_MARKET_DATA"})
                continue

            # 3. Liquidity & Volume
            quote_vol = float(t.get("quoteVolume", 0.0))
            if quote_vol < self.min_quote_volume:
                rejected_symbols.append({"symbol": sym, "reason": f"INSUFFICIENT_VOLUME (${quote_vol:,.0f} < ${self.min_quote_volume:,.0f})"})
                continue

            # 4. Bid/Ask Spread
            b_info = book_tickers.get(sym)
            if not b_info or b_info["ask"] <= 0:
                rejected_symbols.append({"symbol": sym, "reason": "MISSING_ORDER_BOOK_TICKER"})
                continue

            spread_ratio = b_info["spread_ratio"]
            if spread_ratio > self.max_spread_ratio:
                rejected_symbols.append({"symbol": sym, "reason": f"SPREAD_TOO_WIDE ({spread_ratio*100:.3f}% > {self.max_spread_ratio*100:.3f}%)"})
                continue

            # 5. Order book depth (lenient on testnet where order book liquidity is thin)
            depth_usd = min(b_info["bid"] * b_info["bid_qty"], b_info["ask"] * b_info["ask_qty"])
            min_depth = 100.0 if (self.adapter and getattr(self.adapter, "environment", "") == "testnet") else 1000.0
            if depth_usd < min_depth:
                rejected_symbols.append({"symbol": sym, "reason": f"THIN_TOP_OF_BOOK_DEPTH (${depth_usd:.0f} < ${min_depth:.0f})"})
                continue

            price = float(t.get("lastPrice", 0.0))
            price_change_pct = float(t.get("priceChangePercent", 0.0))

            # Eligible! Score and rank
            # Liquidity score (log volume) + tight spread bonus
            vol_score = min(50.0, math.log10(max(1.0, quote_vol)) * 5.0)
            spread_score = max(0.0, (1.0 - (spread_ratio / self.max_spread_ratio)) * 30.0)
            activity_score = min(20.0, abs(price_change_pct) * 2.0)
            overall_rank_score = round(vol_score + spread_score + activity_score, 2)

            eligible_candidates.append({
                "symbol": sym,
                "price": price,
                "quote_volume_24h": round(quote_vol, 2),
                "spread_usd": round(b_info["spread"], 6),
                "spread_ratio": round(spread_ratio, 6),
                "spread_bps": round(spread_ratio * 10000, 2),
                "depth_usd": round(depth_usd, 2),
                "price_change_pct_24h": price_change_pct,
                "rank_score": overall_rank_score,
                "base_asset": meta.get("baseAsset"),
                "quote_asset": meta.get("quoteAsset"),
            })

        # Sort candidates descending by rank score
        eligible_candidates.sort(key=lambda x: x["rank_score"], reverse=True)
        top_candidates = eligible_candidates[:max_candidates]

        return {
            "status": "SUCCESS",
            "scan_duration_ms": int(time.time() * 1000) - t0,
            "total_scanned": len(all_tickers),
            "eligible_count": len(eligible_candidates),
            "rejected_count": len(rejected_symbols),
            "candidates": top_candidates,
            "rejected_sample": rejected_symbols[:20]
        }
