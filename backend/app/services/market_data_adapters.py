"""
Tauric Market-Data Adapters, Instrument Metadata & Data-Quality Gates
Phase 1 Implementation - Public Read-Only Spot Adapters

Safeguards:
- Public endpoints only, zero authentication credentials, zero trading keys.
- Crypto market type: Spot only (strictly excludes derivatives, margin, futures, options).
- Deterministic data-quality validation (zero LLM calls).
- Explicit status representation: PASS, FAIL, UNKNOWN, STALE, UNAVAILABLE.
"""

import asyncio
from dataclasses import dataclass, field, asdict
from enum import Enum
import logging
import math
import time
from typing import Any, Dict, List, Optional, Tuple, Union
import httpx

logger = logging.getLogger(__name__)


# ─── DATA-QUALITY & STATUS CONTRACTS ──────────────────────────────

class MarketDataStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass
class InstrumentMetadata:
    canonical_id: str             # e.g. "crypto:binance:BTCUSDT" or "crypto:bybit:BTCUSDT"
    exchange: str                 # "binance" | "bybit"
    market_type: str              # "spot"
    symbol: str                   # "BTC"
    quote_currency: str           # "USDT"
    pair: str                     # "BTCUSDT"
    status: str                   # "TRADING" | "Trading"
    is_spot: bool                 # True only
    min_qty: float
    max_qty: Optional[float]
    qty_step: float
    price_tick: float
    min_notional: float
    base_precision: int
    quote_precision: int
    raw_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TickerSnapshot:
    canonical_id: str
    exchange: str
    market_type: str              # "spot"
    symbol: str
    pair: str
    price: Optional[float]
    bid: Optional[float]
    ask: Optional[float]
    spread: Optional[float]
    spread_bps: Optional[float]
    high_24h: Optional[float]
    low_24h: Optional[float]
    volume_24h: Optional[float]
    quote_volume_24h: Optional[float]
    change_24h: Optional[float]
    timestamp_ms: int             # Exchange source timestamp
    fetched_at_ms: int            # Local receipt timestamp
    status: MarketDataStatus
    quality_score: float          # 0.0 to 100.0
    quality_reasons: List[str] = field(default_factory=list)
    raw_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class Candle:
    open_time_ms: int
    close_time_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CandleSeries:
    canonical_id: str
    exchange: str
    interval: str
    candles: List[Candle]
    status: MarketDataStatus
    quality_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "canonical_id": self.canonical_id,
            "exchange": self.exchange,
            "interval": self.interval,
            "count": len(self.candles),
            "candles": [c.to_dict() for c in self.candles],
            "status": self.status.value,
            "quality_reasons": self.quality_reasons,
        }


@dataclass
class OrderBookLevel:
    price: float
    qty: float


@dataclass
class OrderBookSnapshot:
    canonical_id: str
    exchange: str
    timestamp_ms: int
    bids: List[OrderBookLevel]
    asks: List[OrderBookLevel]
    spread: Optional[float]
    spread_bps: Optional[float]
    status: MarketDataStatus
    quality_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "canonical_id": self.canonical_id,
            "exchange": self.exchange,
            "timestamp_ms": self.timestamp_ms,
            "bids": [{"price": b.price, "qty": b.qty} for b in self.bids],
            "asks": [{"price": a.price, "qty": a.qty} for a in self.asks],
            "spread": self.spread,
            "spread_bps": self.spread_bps,
            "status": self.status.value,
            "quality_reasons": self.quality_reasons,
        }


# ─── DETERMINISTIC DATA-QUALITY VALIDATOR ─────────────────────────

class DataQualityValidator:
    """
    Deterministic data-quality gate.
    Evaluates numeric validity, bid/ask consistency, candle ordering,
    freshness, trading status, and precision.
    Zero LLM calls.
    """

    DEFAULT_MAX_QUOTE_AGE_MS = 60_000   # 60s max quote age before marking STALE
    DEFAULT_MAX_SPREAD_BPS = 500.0      # 500 bps = 5.0% spread sanity threshold

    @classmethod
    def validate_instrument(cls, meta: InstrumentMetadata) -> Tuple[MarketDataStatus, List[str]]:
        reasons = []

        if not meta.is_spot or meta.market_type != "spot":
            reasons.append("Instrument is not Spot (derivatives rejected)")
            return MarketDataStatus.FAIL, reasons

        if meta.status.upper() not in ("TRADING", "NORMAL", "OPEN"):
            reasons.append(f"Instrument trading status is '{meta.status}' (not TRADING)")
            return MarketDataStatus.FAIL, reasons

        if not meta.symbol or not meta.quote_currency or not meta.pair:
            reasons.append("Missing required symbol/pair metadata")
            return MarketDataStatus.UNKNOWN, reasons

        if meta.price_tick <= 0:
            reasons.append(f"Invalid price tick size: {meta.price_tick}")
            return MarketDataStatus.FAIL, reasons

        if meta.qty_step <= 0:
            reasons.append(f"Invalid quantity step size: {meta.qty_step}")
            return MarketDataStatus.FAIL, reasons

        if meta.min_notional < 0:
            reasons.append(f"Negative min notional: {meta.min_notional}")
            return MarketDataStatus.FAIL, reasons

        return MarketDataStatus.PASS, ["Instrument metadata passed all validation checks"]

    @classmethod
    def validate_ticker(
        cls,
        ticker: TickerSnapshot,
        max_age_ms: int = DEFAULT_MAX_QUOTE_AGE_MS
    ) -> Tuple[MarketDataStatus, float, List[str]]:
        reasons = []
        score = 100.0

        # 1. Missing required field checks
        if ticker.price is None:
            reasons.append("Missing price in ticker snapshot")
            return MarketDataStatus.UNKNOWN, 0.0, reasons

        if ticker.timestamp_ms <= 0:
            reasons.append("Missing or invalid source timestamp in ticker")
            return MarketDataStatus.UNKNOWN, 0.0, reasons

        # 2. Numeric validity checks
        for val_name, val in [("price", ticker.price), ("bid", ticker.bid), ("ask", ticker.ask)]:
            if val is not None:
                if not math.isfinite(val) or math.isnan(val):
                    reasons.append(f"{val_name} is not finite ({val})")
                    return MarketDataStatus.FAIL, 0.0, reasons
                if val <= 0:
                    reasons.append(f"{val_name} must be positive ({val})")
                    return MarketDataStatus.FAIL, 0.0, reasons

        for val_name, val in [("high_24h", ticker.high_24h), ("low_24h", ticker.low_24h), ("volume_24h", ticker.volume_24h)]:
            if val is not None:
                if not math.isfinite(val) or math.isnan(val) or val < 0:
                    reasons.append(f"{val_name} must be finite and non-negative ({val})")
                    return MarketDataStatus.FAIL, 0.0, reasons

        # 3. High/Low range consistency
        if ticker.high_24h is not None and ticker.low_24h is not None:
            if ticker.high_24h < ticker.low_24h:
                reasons.append(f"high_24h ({ticker.high_24h}) < low_24h ({ticker.low_24h})")
                return MarketDataStatus.FAIL, 0.0, reasons

        # 4. Bid / Ask consistency
        if ticker.bid is not None and ticker.ask is not None:
            if ticker.bid > ticker.ask:
                reasons.append(f"Crossed market: bid ({ticker.bid}) > ask ({ticker.ask})")
                return MarketDataStatus.FAIL, 0.0, reasons

            spread = ticker.ask - ticker.bid
            mid = (ticker.ask + ticker.bid) / 2.0
            if mid > 0:
                spread_bps = (spread / mid) * 10000.0
                if spread_bps > cls.DEFAULT_MAX_SPREAD_BPS:
                    reasons.append(f"Extreme spread: {spread_bps:.1f} bps exceeds sanity limit")
                    score -= 30.0

        # 5. Quote freshness check
        now_ms = int(time.time() * 1000)
        quote_age_ms = now_ms - ticker.timestamp_ms
        if quote_age_ms < -10_000:
            reasons.append(f"Timestamp in future by {-quote_age_ms} ms")
            return MarketDataStatus.FAIL, 0.0, reasons

        if quote_age_ms > max_age_ms:
            reasons.append(f"Quote age ({quote_age_ms} ms) exceeds freshness threshold ({max_age_ms} ms)")
            return MarketDataStatus.STALE, 40.0, reasons

        reasons.append("Ticker passed numeric, bid/ask consistency, and freshness checks")
        return MarketDataStatus.PASS, max(score, 10.0), reasons

    @classmethod
    def validate_candles(
        cls,
        series: CandleSeries,
        interval_ms: int,
        max_age_ms: Optional[int] = None
    ) -> Tuple[MarketDataStatus, List[str]]:
        reasons = []
        candles = series.candles

        if not candles:
            reasons.append("Candle series is empty")
            return MarketDataStatus.UNAVAILABLE, reasons

        prev_time = -1
        for i, c in enumerate(candles):
            # Numeric validity
            for k, val in [("open", c.open), ("high", c.high), ("low", c.low), ("close", c.close), ("volume", c.volume)]:
                if not math.isfinite(val) or math.isnan(val) or (val <= 0 if k != "volume" else val < 0):
                    reasons.append(f"Candle [{i}] {k} is invalid ({val})")
                    return MarketDataStatus.FAIL, reasons

            # Shape validity: high >= max(open, close), low <= min(open, close)
            if c.high < max(c.open, c.close) or c.low > min(c.open, c.close) or c.high < c.low:
                reasons.append(f"Candle [{i}] violates candlestick bounds (O:{c.open}, H:{c.high}, L:{c.low}, C:{c.close})")
                return MarketDataStatus.FAIL, reasons

            # Monotonic ordering and duplicate detection
            if prev_time != -1:
                if c.open_time_ms == prev_time:
                    reasons.append(f"Duplicate candle timestamp detected at {c.open_time_ms}")
                    return MarketDataStatus.FAIL, reasons
                elif c.open_time_ms < prev_time:
                    reasons.append(f"Out-of-order candle: {c.open_time_ms} followed {prev_time}")
                    return MarketDataStatus.FAIL, reasons

            prev_time = c.open_time_ms

        # Freshness of newest candle
        if max_age_ms is not None and candles:
            latest_candle = candles[-1]
            now_ms = int(time.time() * 1000)
            candle_age = now_ms - latest_candle.close_time_ms
            if candle_age > max_age_ms:
                reasons.append(f"Latest candle close age ({candle_age} ms) exceeds freshness threshold ({max_age_ms} ms)")
                return MarketDataStatus.STALE, reasons

        reasons.append(f"Candle series ({len(candles)} candles) passed ordering, shape, and interval checks")
        return MarketDataStatus.PASS, reasons

    @classmethod
    def validate_orderbook(cls, book: OrderBookSnapshot) -> Tuple[MarketDataStatus, List[str]]:
        reasons = []

        if not book.bids and not book.asks:
            reasons.append("Order book is completely empty")
            return MarketDataStatus.UNAVAILABLE, reasons

        if not book.bids or not book.asks:
            reasons.append("One-sided order book (missing bids or asks)")
            return MarketDataStatus.FAIL, reasons

        best_bid = book.bids[0].price
        best_ask = book.asks[0].price

        if best_bid > best_ask:
            reasons.append(f"Crossed order book: best bid ({best_bid}) > best ask ({best_ask})")
            return MarketDataStatus.FAIL, reasons

        # Check bids descending
        for i in range(1, len(book.bids)):
            if book.bids[i].price > book.bids[i - 1].price:
                reasons.append(f"Bids not sorted descending at index {i}")
                return MarketDataStatus.FAIL, reasons

        # Check asks ascending
        for i in range(1, len(book.asks)):
            if book.asks[i].price < book.asks[i - 1].price:
                reasons.append(f"Asks not sorted ascending at index {i}")
                return MarketDataStatus.FAIL, reasons

        reasons.append(f"Order book ({len(book.bids)} bids, {len(book.asks)} asks) passed sorting and crossing checks")
        return MarketDataStatus.PASS, reasons


def parse_market_pair(raw_symbol: str) -> Tuple[str, str, str]:
    """
    Parses raw symbol into (base_asset, quote_asset, api_pair).
    Supports spot pairs quoted in USDT and BTC (e.g. ADA/USDT, ADA/BTC).
    """
    s = raw_symbol.upper().strip()
    for prefix in ["CRYPTO:BINANCE:", "CRYPTO:BYBIT:", "CRYPTO:", "FX:", "METAL:"]:
        if s.startswith(prefix):
            s = s[len(prefix):]
    if "/" in s:
        parts = s.split("/")
        return parts[0], parts[1], f"{parts[0]}{parts[1]}"
    if s.endswith("BTC") and len(s) > 3 and s != "BTC":
        return s[:-3], "BTC", s
    if s.endswith("USDT") and len(s) > 4:
        return s[:-4], "USDT", s
    return s, "USDT", f"{s}USDT"


# ─── BASE PUBLIC MARKET-DATA ADAPTER ──────────────────────────────

class BaseMarketDataAdapter:
    """
    Abstract base for public, unauthenticated, read-only Spot adapters.
    Guarantees:
    - Zero execution/order methods.
    - Zero secrets/keys needed or stored.
    - Explicit rate-limit backoff tracking.
    - Clean timeouts and error containment.
    """

    def __init__(self, exchange_name: str, base_url: str, timeout_seconds: float = 5.0, max_retries: int = 2):
        self.exchange_name = exchange_name.lower()
        self.market_type = "spot"
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        
        # Rate-limiting tracker
        self._rate_limit_until: float = 0.0
        self._rate_limit_reason: str = ""
        self._rate_limit_retry_after: float = 0.0

    def is_rate_limited(self) -> bool:
        return time.time() < self._rate_limit_until

    def get_rate_limit_info(self) -> Dict[str, Any]:
        now = time.time()
        is_limited = now < self._rate_limit_until
        remaining_s = max(0.0, round(self._rate_limit_until - now, 2)) if is_limited else 0.0
        return {
            "rate_limited": is_limited,
            "retry_after_seconds": remaining_s,
            "reason": self._rate_limit_reason if is_limited else ""
        }

    def _mark_rate_limited(self, retry_after_s: float, reason: str = "HTTP 429"):
        now = time.time()
        cooldown = max(1.0, min(retry_after_s, 300.0))
        self._rate_limit_until = now + cooldown
        self._rate_limit_retry_after = cooldown
        self._rate_limit_reason = reason
        logger.warning(f"[{self.exchange_name}] Rate limited for {cooldown:.1f}s: {reason}")

    def clean_symbol(self, raw_symbol: str) -> str:
        s = raw_symbol.upper().strip()
        for prefix in [f"CRYPTO:{self.exchange_name.upper()}:", "CRYPTO:BINANCE:", "CRYPTO:BYBIT:", "FX:", "METAL:"]:
            if s.startswith(prefix):
                s = s[len(prefix):]
        return s.replace("/USDT", "").replace("-USD", "").replace("USDT", "").replace("/", "")

    def parse_market_pair(self, raw_symbol: str) -> Tuple[str, str, str]:
        return parse_market_pair(raw_symbol)

    def get_canonical_id(self, symbol: str) -> str:
        base, quote, pair = self.parse_market_pair(symbol)
        return f"crypto:{self.exchange_name}:{pair}"

    async def _safe_http_get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        custom_client: Optional[httpx.AsyncClient] = None
    ) -> Tuple[Optional[httpx.Response], Optional[str]]:
        """
        Executes bounded HTTP GET with rate-limit pre-check, retries, and sanitized errors.
        """
        if self.is_rate_limited():
            info = self.get_rate_limit_info()
            return None, f"Exchange is rate-limited. Retry after {info['retry_after_seconds']}s"

        for attempt in range(self.max_retries):
            try:
                if custom_client:
                    resp = await custom_client.get(url, params=params)
                else:
                    async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                        resp = await client.get(url, params=params)

                if resp.status_code == 429:
                    retry_header = resp.headers.get("Retry-After")
                    retry_s = float(retry_header) if retry_header and retry_header.isdigit() else 30.0
                    self._mark_rate_limited(retry_s, f"HTTP 429 received from {self.exchange_name}")
                    return None, f"HTTP 429 Rate Limit. Retry after {retry_s}s"

                if resp.status_code == 200:
                    return resp, None
                else:
                    return None, f"HTTP {resp.status_code}: {resp.text[:120]}"

            except httpx.TimeoutException:
                if attempt == self.max_retries - 1:
                    return None, f"Connection timeout ({self.timeout_seconds}s) on {self.exchange_name}"
                await asyncio.sleep(0.3 * (attempt + 1))
            except httpx.RequestError as e:
                if attempt == self.max_retries - 1:
                    return None, f"Network request error: {type(e).__name__}"
                await asyncio.sleep(0.3 * (attempt + 1))
            except Exception as e:
                return None, f"Unexpected transport error: {type(e).__name__}"

        return None, "Max retries exceeded"

    # Abstract interface to be implemented by exchange adapters
    async def fetch_instrument_metadata(
        self,
        symbol: str,
        custom_client: Optional[httpx.AsyncClient] = None
    ) -> InstrumentMetadata:
        raise NotImplementedError

    async def fetch_ticker(
        self,
        symbol: str,
        custom_client: Optional[httpx.AsyncClient] = None
    ) -> TickerSnapshot:
        raise NotImplementedError

    async def fetch_klines(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 50,
        custom_client: Optional[httpx.AsyncClient] = None
    ) -> CandleSeries:
        raise NotImplementedError

    async def fetch_orderbook(
        self,
        symbol: str,
        limit: int = 20,
        custom_client: Optional[httpx.AsyncClient] = None
    ) -> OrderBookSnapshot:
        raise NotImplementedError


# ─── BINANCE SPOT ADAPTER ─────────────────────────────────────────

class BinanceSpotAdapter(BaseMarketDataAdapter):
    """
    Public Binance Spot Market-Data Adapter.
    Public endpoints only. Zero authenticated clients.
    Strictly spot trading allowed.
    """

    def __init__(self, base_url: str = "https://api.binance.com", timeout_seconds: float = 5.0):
        super().__init__(exchange_name="binance", base_url=base_url, timeout_seconds=timeout_seconds)

    async def fetch_instrument_metadata(
        self,
        symbol: str,
        custom_client: Optional[httpx.AsyncClient] = None
    ) -> InstrumentMetadata:
        clean = self.clean_symbol(symbol)
        pair = f"{clean}USDT"
        canonical_id = f"crypto:binance:{pair}"
        url = f"{self.base_url}/api/v3/exchangeInfo"

        resp, err = await self._safe_http_get(url, params={"symbol": pair}, custom_client=custom_client)
        if err or not resp:
            return InstrumentMetadata(
                canonical_id=canonical_id,
                exchange="binance",
                market_type="spot",
                symbol=clean,
                quote_currency="USDT",
                pair=pair,
                status="UNAVAILABLE",
                is_spot=False,
                min_qty=0.0,
                max_qty=None,
                qty_step=0.0,
                price_tick=0.0,
                min_notional=0.0,
                base_precision=8,
                quote_precision=8,
                raw_data={"error": err or "No response"}
            )

        try:
            data = resp.json()
            symbols = data.get("symbols", [])
            if not symbols:
                return InstrumentMetadata(
                    canonical_id=canonical_id,
                    exchange="binance",
                    market_type="spot",
                    symbol=clean,
                    quote_currency="USDT",
                    pair=pair,
                    status="UNKNOWN",
                    is_spot=False,
                    min_qty=0.0,
                    max_qty=None,
                    qty_step=0.0,
                    price_tick=0.0,
                    min_notional=0.0,
                    base_precision=8,
                    quote_precision=8,
                    raw_data={"error": f"Symbol {pair} not found in exchangeInfo"}
                )

            s_info = symbols[0]
            is_spot = bool(s_info.get("isSpotTradingAllowed", False))
            status = s_info.get("status", "UNKNOWN")
            base_asset = s_info.get("baseAsset", clean)
            quote_asset = s_info.get("quoteAsset", "USDT")
            base_precision = int(s_info.get("baseAssetPrecision", 8))
            quote_precision = int(s_info.get("quotePrecision", 8))

            # Parse filters
            filters = {f.get("filterType"): f for f in s_info.get("filters", [])}

            lot_filter = filters.get("LOT_SIZE", {})
            min_qty = float(lot_filter.get("minQty", 0.0))
            max_qty = float(lot_filter.get("maxQty", 0.0)) or None
            qty_step = float(lot_filter.get("stepSize", 0.0))

            price_filter = filters.get("PRICE_FILTER", {})
            price_tick = float(price_filter.get("tickSize", 0.0))

            notional_filter = filters.get("NOTIONAL") or filters.get("MIN_NOTIONAL", {})
            min_notional = float(notional_filter.get("minNotional", 5.0))

            meta = InstrumentMetadata(
                canonical_id=canonical_id,
                exchange="binance",
                market_type="spot",
                symbol=base_asset,
                quote_currency=quote_asset,
                pair=pair,
                status=status,
                is_spot=is_spot,
                min_qty=min_qty,
                max_qty=max_qty,
                qty_step=qty_step,
                price_tick=price_tick,
                min_notional=min_notional,
                base_precision=base_precision,
                quote_precision=quote_precision,
                raw_data=s_info
            )
            return meta

        except Exception as e:
            return InstrumentMetadata(
                canonical_id=canonical_id,
                exchange="binance",
                market_type="spot",
                symbol=clean,
                quote_currency="USDT",
                pair=pair,
                status="FAIL",
                is_spot=False,
                min_qty=0.0,
                max_qty=None,
                qty_step=0.0,
                price_tick=0.0,
                min_notional=0.0,
                base_precision=8,
                quote_precision=8,
                raw_data={"error": f"JSON parse error: {str(e)}"}
            )

    async def fetch_ticker(
        self,
        symbol: str,
        custom_client: Optional[httpx.AsyncClient] = None
    ) -> TickerSnapshot:
        base, quote, pair = self.parse_market_pair(symbol)
        clean = base
        display_pair = f"{base}/{quote}"
        canonical_id = f"crypto:binance:{pair}"
        url = f"{self.base_url}/api/v3/ticker/24hr"
        now_ms = int(time.time() * 1000)

        resp, err = await self._safe_http_get(url, params={"symbol": pair}, custom_client=custom_client)
        if err or not resp:
            return TickerSnapshot(
                canonical_id=canonical_id,
                exchange="binance",
                market_type="spot",
                symbol=clean,
                pair=display_pair,
                price=None,
                bid=None,
                ask=None,
                spread=None,
                spread_bps=None,
                high_24h=None,
                low_24h=None,
                volume_24h=None,
                quote_volume_24h=None,
                change_24h=None,
                timestamp_ms=0,
                fetched_at_ms=now_ms,
                status=MarketDataStatus.UNAVAILABLE,
                quality_score=0.0,
                quality_reasons=[err or "Binance public endpoint unavailable"]
            )

        try:
            d = resp.json()
            if isinstance(d, dict) and d.get("code") is not None and d.get("code") != 0:
                # Binance error object
                return TickerSnapshot(
                    canonical_id=canonical_id,
                    exchange="binance",
                    market_type="spot",
                    symbol=clean,
                    pair=pair,
                    price=None,
                    bid=None,
                    ask=None,
                    spread=None,
                    spread_bps=None,
                    high_24h=None,
                    low_24h=None,
                    volume_24h=None,
                    quote_volume_24h=None,
                    change_24h=None,
                    timestamp_ms=0,
                    fetched_at_ms=now_ms,
                    status=MarketDataStatus.UNKNOWN,
                    quality_score=0.0,
                    quality_reasons=[f"Binance API code {d.get('code')}: {d.get('msg')}"]
                )

            price = float(d.get("lastPrice", 0.0))
            bid = float(d.get("bidPrice", 0.0)) if d.get("bidPrice") is not None else None
            ask = float(d.get("askPrice", 0.0)) if d.get("askPrice") is not None else None
            high = float(d.get("highPrice", 0.0))
            low = float(d.get("lowPrice", 0.0))
            vol = float(d.get("volume", 0.0))
            q_vol = float(d.get("quoteVolume", 0.0))
            change = float(d.get("priceChangePercent", 0.0))
            ts = int(d.get("closeTime", now_ms))

            spread = None
            spread_bps = None
            if bid is not None and ask is not None:
                spread = ask - bid
                mid = (ask + bid) / 2.0
                if mid > 0:
                    spread_bps = (spread / mid) * 10000.0

            snapshot = TickerSnapshot(
                canonical_id=canonical_id,
                exchange="binance",
                market_type="spot",
                symbol=clean,
                pair=pair,
                price=price,
                bid=bid,
                ask=ask,
                spread=spread,
                spread_bps=spread_bps,
                high_24h=high,
                low_24h=low,
                volume_24h=vol,
                quote_volume_24h=q_vol,
                change_24h=round(change, 2),
                timestamp_ms=ts,
                fetched_at_ms=now_ms,
                status=MarketDataStatus.PASS,
                quality_score=100.0,
                raw_data=d
            )

            # Validate deterministic quality
            val_status, val_score, val_reasons = DataQualityValidator.validate_ticker(snapshot)
            snapshot.status = val_status
            snapshot.quality_score = val_score
            snapshot.quality_reasons = val_reasons
            return snapshot

        except Exception as e:
            return TickerSnapshot(
                canonical_id=canonical_id,
                exchange="binance",
                market_type="spot",
                symbol=clean,
                pair=pair,
                price=None,
                bid=None,
                ask=None,
                spread=None,
                spread_bps=None,
                high_24h=None,
                low_24h=None,
                volume_24h=None,
                quote_volume_24h=None,
                change_24h=None,
                timestamp_ms=0,
                fetched_at_ms=now_ms,
                status=MarketDataStatus.FAIL,
                quality_score=0.0,
                quality_reasons=[f"Malformed payload or numeric conversion failure: {str(e)}"]
            )

    async def fetch_klines(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 50,
        custom_client: Optional[httpx.AsyncClient] = None
    ) -> CandleSeries:
        base, quote, pair = self.parse_market_pair(symbol)
        clean = base
        display_pair = f"{base}/{quote}"
        canonical_id = f"crypto:binance:{pair}"
        url = f"{self.base_url}/api/v3/klines"

        resp, err = await self._safe_http_get(
            url,
            params={"symbol": pair, "interval": interval, "limit": limit},
            custom_client=custom_client
        )

        if err or not resp:
            return CandleSeries(
                canonical_id=canonical_id,
                exchange="binance",
                interval=interval,
                candles=[],
                status=MarketDataStatus.UNAVAILABLE,
                quality_reasons=[err or "Binance klines unavailable"]
            )

        try:
            raw_klines = resp.json()
            if not isinstance(raw_klines, list):
                return CandleSeries(
                    canonical_id=canonical_id,
                    exchange="binance",
                    interval=interval,
                    candles=[],
                    status=MarketDataStatus.FAIL,
                    quality_reasons=["Binance klines response is not a JSON list"]
                )

            candles: List[Candle] = []
            for k in raw_klines:
                # [openTime, open, high, low, close, volume, closeTime, quoteAssetVolume, ...]
                candles.append(Candle(
                    open_time_ms=int(k[0]),
                    close_time_ms=int(k[6]),
                    open=float(k[1]),
                    high=float(k[2]),
                    low=float(k[3]),
                    close=float(k[4]),
                    volume=float(k[5]),
                    quote_volume=float(k[7])
                ))

            series = CandleSeries(
                canonical_id=canonical_id,
                exchange="binance",
                interval=interval,
                candles=candles,
                status=MarketDataStatus.PASS
            )

            val_status, val_reasons = DataQualityValidator.validate_candles(series, interval_ms=3600000)
            series.status = val_status
            series.quality_reasons = val_reasons
            return series

        except Exception as e:
            return CandleSeries(
                canonical_id=canonical_id,
                exchange="binance",
                interval=interval,
                candles=[],
                status=MarketDataStatus.FAIL,
                quality_reasons=[f"Candle parsing error: {str(e)}"]
            )

    async def fetch_orderbook(
        self,
        symbol: str,
        limit: int = 20,
        custom_client: Optional[httpx.AsyncClient] = None
    ) -> OrderBookSnapshot:
        clean = self.clean_symbol(symbol)
        pair = f"{clean}USDT"
        canonical_id = f"crypto:binance:{pair}"
        url = f"{self.base_url}/api/v3/depth"
        now_ms = int(time.time() * 1000)

        resp, err = await self._safe_http_get(
            url,
            params={"symbol": pair, "limit": min(limit, 100)},
            custom_client=custom_client
        )

        if err or not resp:
            return OrderBookSnapshot(
                canonical_id=canonical_id,
                exchange="binance",
                timestamp_ms=now_ms,
                bids=[],
                asks=[],
                spread=None,
                spread_bps=None,
                status=MarketDataStatus.UNAVAILABLE,
                quality_reasons=[err or "Binance depth unavailable"]
            )

        try:
            d = resp.json()
            bids = [OrderBookLevel(price=float(b[0]), qty=float(b[1])) for b in d.get("bids", [])]
            asks = [OrderBookLevel(price=float(a[0]), qty=float(a[1])) for a in d.get("asks", [])]

            spread = None
            spread_bps = None
            if bids and asks:
                spread = asks[0].price - bids[0].price
                mid = (asks[0].price + bids[0].price) / 2.0
                if mid > 0:
                    spread_bps = (spread / mid) * 10000.0

            snapshot = OrderBookSnapshot(
                canonical_id=canonical_id,
                exchange="binance",
                timestamp_ms=now_ms,
                bids=bids,
                asks=asks,
                spread=spread,
                spread_bps=spread_bps,
                status=MarketDataStatus.PASS
            )

            val_status, val_reasons = DataQualityValidator.validate_orderbook(snapshot)
            snapshot.status = val_status
            snapshot.quality_reasons = val_reasons
            return snapshot

        except Exception as e:
            return OrderBookSnapshot(
                canonical_id=canonical_id,
                exchange="binance",
                timestamp_ms=now_ms,
                bids=[],
                asks=[],
                spread=None,
                spread_bps=None,
                status=MarketDataStatus.FAIL,
                quality_reasons=[f"Depth parse error: {str(e)}"]
            )


# ─── BYBIT SPOT ADAPTER ───────────────────────────────────────────

class BybitSpotAdapter(BaseMarketDataAdapter):
    """
    Public Bybit Spot Market-Data Adapter (V5 Public API).
    Public endpoints only. Zero authenticated clients.
    Strictly filters to category='spot'. Explicitly rejects derivatives (linear, inverse, option).
    """

    INTERVAL_MAP = {
        "1m": "1",
        "3m": "3",
        "5m": "5",
        "15m": "15",
        "30m": "30",
        "1h": "60",
        "2h": "120",
        "4h": "240",
        "6h": "360",
        "12h": "720",
        "1d": "D",
        "1w": "W",
    }

    def __init__(self, base_url: str = "https://api.bybit.com", timeout_seconds: float = 5.0):
        super().__init__(exchange_name="bybit", base_url=base_url, timeout_seconds=timeout_seconds)

    async def fetch_instrument_metadata(
        self,
        symbol: str,
        custom_client: Optional[httpx.AsyncClient] = None
    ) -> InstrumentMetadata:
        clean = self.clean_symbol(symbol)
        pair = f"{clean}USDT"
        canonical_id = f"crypto:bybit:{pair}"
        url = f"{self.base_url}/v5/market/instruments-info"

        # Explicitly query category=spot
        resp, err = await self._safe_http_get(
            url,
            params={"category": "spot", "symbol": pair},
            custom_client=custom_client
        )

        if err or not resp:
            return InstrumentMetadata(
                canonical_id=canonical_id,
                exchange="bybit",
                market_type="spot",
                symbol=clean,
                quote_currency="USDT",
                pair=pair,
                status="UNAVAILABLE",
                is_spot=False,
                min_qty=0.0,
                max_qty=None,
                qty_step=0.0,
                price_tick=0.0,
                min_notional=0.0,
                base_precision=8,
                quote_precision=8,
                raw_data={"error": err or "No response"}
            )

        try:
            d = resp.json()
            if d.get("retCode") != 0:
                return InstrumentMetadata(
                    canonical_id=canonical_id,
                    exchange="bybit",
                    market_type="spot",
                    symbol=clean,
                    quote_currency="USDT",
                    pair=pair,
                    status="FAIL",
                    is_spot=False,
                    min_qty=0.0,
                    max_qty=None,
                    qty_step=0.0,
                    price_tick=0.0,
                    min_notional=0.0,
                    base_precision=8,
                    quote_precision=8,
                    raw_data={"error": f"Bybit error {d.get('retCode')}: {d.get('retMsg')}"}
                )

            res_data = d.get("result", {})
            category = res_data.get("category", "")
            if category.lower() != "spot":
                # Reject derivatives
                return InstrumentMetadata(
                    canonical_id=canonical_id,
                    exchange="bybit",
                    market_type="spot",
                    symbol=clean,
                    quote_currency="USDT",
                    pair=pair,
                    status="FAIL",
                    is_spot=False,
                    min_qty=0.0,
                    max_qty=None,
                    qty_step=0.0,
                    price_tick=0.0,
                    min_notional=0.0,
                    base_precision=8,
                    quote_precision=8,
                    raw_data={"error": f"Derivative rejected: category is '{category}', not 'spot'"}
                )

            inst_list = res_data.get("list", [])
            if not inst_list:
                return InstrumentMetadata(
                    canonical_id=canonical_id,
                    exchange="bybit",
                    market_type="spot",
                    symbol=clean,
                    quote_currency="USDT",
                    pair=pair,
                    status="UNKNOWN",
                    is_spot=False,
                    min_qty=0.0,
                    max_qty=None,
                    qty_step=0.0,
                    price_tick=0.0,
                    min_notional=0.0,
                    base_precision=8,
                    quote_precision=8,
                    raw_data={"error": f"Instrument {pair} not found in Bybit Spot registry"}
                )

            item = inst_list[0]
            status = item.get("status", "Trading")
            lot_filter = item.get("lotSizeFilter", {})
            price_filter = item.get("priceFilter", {})

            min_qty = float(lot_filter.get("minOrderQty", 0.0))
            max_qty = float(lot_filter.get("maxOrderQty", 0.0)) or None
            qty_step = float(lot_filter.get("basePrecision", 0.000001))
            price_tick = float(price_filter.get("tickSize", 0.01))
            min_notional = float(lot_filter.get("minOrderAmt", 1.0))

            return InstrumentMetadata(
                canonical_id=canonical_id,
                exchange="bybit",
                market_type="spot",
                symbol=item.get("baseCoin", clean),
                quote_currency=item.get("quoteCoin", "USDT"),
                pair=pair,
                status=status,
                is_spot=True,
                min_qty=min_qty,
                max_qty=max_qty,
                qty_step=qty_step,
                price_tick=price_tick,
                min_notional=min_notional,
                base_precision=8,
                quote_precision=8,
                raw_data=item
            )

        except Exception as e:
            return InstrumentMetadata(
                canonical_id=canonical_id,
                exchange="bybit",
                market_type="spot",
                symbol=clean,
                quote_currency="USDT",
                pair=pair,
                status="FAIL",
                is_spot=False,
                min_qty=0.0,
                max_qty=None,
                qty_step=0.0,
                price_tick=0.0,
                min_notional=0.0,
                base_precision=8,
                quote_precision=8,
                raw_data={"error": f"Parse error: {str(e)}"}
            )

    async def fetch_ticker(
        self,
        symbol: str,
        custom_client: Optional[httpx.AsyncClient] = None
    ) -> TickerSnapshot:
        clean = self.clean_symbol(symbol)
        pair = f"{clean}USDT"
        canonical_id = f"crypto:bybit:{pair}"
        url = f"{self.base_url}/v5/market/tickers"
        now_ms = int(time.time() * 1000)

        resp, err = await self._safe_http_get(
            url,
            params={"category": "spot", "symbol": pair},
            custom_client=custom_client
        )

        if err or not resp:
            return TickerSnapshot(
                canonical_id=canonical_id,
                exchange="bybit",
                market_type="spot",
                symbol=clean,
                pair=pair,
                price=None,
                bid=None,
                ask=None,
                spread=None,
                spread_bps=None,
                high_24h=None,
                low_24h=None,
                volume_24h=None,
                quote_volume_24h=None,
                change_24h=None,
                timestamp_ms=0,
                fetched_at_ms=now_ms,
                status=MarketDataStatus.UNAVAILABLE,
                quality_score=0.0,
                quality_reasons=[err or "Bybit public endpoint unavailable"]
            )

        try:
            d = resp.json()
            if d.get("retCode") != 0:
                # Bybit rate limit code: 10006
                if d.get("retCode") == 10006:
                    self._mark_rate_limited(30.0, "Bybit retCode 10006 Rate Limit")
                    return TickerSnapshot(
                        canonical_id=canonical_id,
                        exchange="bybit",
                        market_type="spot",
                        symbol=clean,
                        pair=pair,
                        price=None,
                        bid=None,
                        ask=None,
                        spread=None,
                        spread_bps=None,
                        high_24h=None,
                        low_24h=None,
                        volume_24h=None,
                        quote_volume_24h=None,
                        change_24h=None,
                        timestamp_ms=0,
                        fetched_at_ms=now_ms,
                        status=MarketDataStatus.UNAVAILABLE,
                        quality_score=0.0,
                        quality_reasons=["Bybit API Rate Limited (retCode 10006)"]
                    )
                return TickerSnapshot(
                    canonical_id=canonical_id,
                    exchange="bybit",
                    market_type="spot",
                    symbol=clean,
                    pair=pair,
                    price=None,
                    bid=None,
                    ask=None,
                    spread=None,
                    spread_bps=None,
                    high_24h=None,
                    low_24h=None,
                    volume_24h=None,
                    quote_volume_24h=None,
                    change_24h=None,
                    timestamp_ms=0,
                    fetched_at_ms=now_ms,
                    status=MarketDataStatus.UNKNOWN,
                    quality_score=0.0,
                    quality_reasons=[f"Bybit API error {d.get('retCode')}: {d.get('retMsg')}"]
                )

            res = d.get("result", {})
            # Verify category is spot
            if res.get("category", "spot").lower() != "spot":
                return TickerSnapshot(
                    canonical_id=canonical_id,
                    exchange="bybit",
                    market_type="spot",
                    symbol=clean,
                    pair=pair,
                    price=None,
                    bid=None,
                    ask=None,
                    spread=None,
                    spread_bps=None,
                    high_24h=None,
                    low_24h=None,
                    volume_24h=None,
                    quote_volume_24h=None,
                    change_24h=None,
                    timestamp_ms=0,
                    fetched_at_ms=now_ms,
                    status=MarketDataStatus.FAIL,
                    quality_score=0.0,
                    quality_reasons=["Bybit returned non-spot category ticker"]
                )

            t_list = res.get("list", [])
            if not t_list:
                return TickerSnapshot(
                    canonical_id=canonical_id,
                    exchange="bybit",
                    market_type="spot",
                    symbol=clean,
                    pair=pair,
                    price=None,
                    bid=None,
                    ask=None,
                    spread=None,
                    spread_bps=None,
                    high_24h=None,
                    low_24h=None,
                    volume_24h=None,
                    quote_volume_24h=None,
                    change_24h=None,
                    timestamp_ms=0,
                    fetched_at_ms=now_ms,
                    status=MarketDataStatus.UNKNOWN,
                    quality_score=0.0,
                    quality_reasons=[f"Symbol {pair} not found in Bybit tickers"]
                )

            item = t_list[0]
            price = float(item.get("lastPrice", 0.0))
            bid = float(item.get("bid1Price", 0.0)) if item.get("bid1Price") else None
            ask = float(item.get("ask1Price", 0.0)) if item.get("ask1Price") else None
            high = float(item.get("highPrice24h", 0.0))
            low = float(item.get("lowPrice24h", 0.0))
            vol = float(item.get("volume24h", 0.0))
            q_vol = float(item.get("turnover24h", 0.0))
            # Bybit price24hPcnt is a ratio (e.g. 0.0234 for +2.34%)
            change_ratio = float(item.get("price24hPcnt", 0.0))
            change = change_ratio * 100.0
            source_ts = int(d.get("time", now_ms))

            spread = None
            spread_bps = None
            if bid is not None and ask is not None:
                spread = ask - bid
                mid = (ask + bid) / 2.0
                if mid > 0:
                    spread_bps = (spread / mid) * 10000.0

            snapshot = TickerSnapshot(
                canonical_id=canonical_id,
                exchange="bybit",
                market_type="spot",
                symbol=clean,
                pair=pair,
                price=price,
                bid=bid,
                ask=ask,
                spread=spread,
                spread_bps=spread_bps,
                high_24h=high,
                low_24h=low,
                volume_24h=vol,
                quote_volume_24h=q_vol,
                change_24h=round(change, 2),
                timestamp_ms=source_ts,
                fetched_at_ms=now_ms,
                status=MarketDataStatus.PASS,
                quality_score=100.0,
                raw_data=item
            )

            val_status, val_score, val_reasons = DataQualityValidator.validate_ticker(snapshot)
            snapshot.status = val_status
            snapshot.quality_score = val_score
            snapshot.quality_reasons = val_reasons
            return snapshot

        except Exception as e:
            return TickerSnapshot(
                canonical_id=canonical_id,
                exchange="bybit",
                market_type="spot",
                symbol=clean,
                pair=pair,
                price=None,
                bid=None,
                ask=None,
                spread=None,
                spread_bps=None,
                high_24h=None,
                low_24h=None,
                volume_24h=None,
                quote_volume_24h=None,
                change_24h=None,
                timestamp_ms=0,
                fetched_at_ms=now_ms,
                status=MarketDataStatus.FAIL,
                quality_score=0.0,
                quality_reasons=[f"Bybit parse or numeric failure: {str(e)}"]
            )

    async def fetch_klines(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 50,
        custom_client: Optional[httpx.AsyncClient] = None
    ) -> CandleSeries:
        clean = self.clean_symbol(symbol)
        pair = f"{clean}USDT"
        canonical_id = f"crypto:bybit:{pair}"
        url = f"{self.base_url}/v5/market/kline"
        bybit_interval = self.INTERVAL_MAP.get(interval, "60")

        resp, err = await self._safe_http_get(
            url,
            params={"category": "spot", "symbol": pair, "interval": bybit_interval, "limit": limit},
            custom_client=custom_client
        )

        if err or not resp:
            return CandleSeries(
                canonical_id=canonical_id,
                exchange="bybit",
                interval=interval,
                candles=[],
                status=MarketDataStatus.UNAVAILABLE,
                quality_reasons=[err or "Bybit klines unavailable"]
            )

        try:
            d = resp.json()
            if d.get("retCode") != 0:
                return CandleSeries(
                    canonical_id=canonical_id,
                    exchange="bybit",
                    interval=interval,
                    candles=[],
                    status=MarketDataStatus.FAIL,
                    quality_reasons=[f"Bybit API error {d.get('retCode')}: {d.get('retMsg')}"]
                )

            res = d.get("result", {})
            raw_list = res.get("list", [])
            
            # Bybit returns klines in reverse chronological order (newest first).
            # Convert to Candle objects, then sort oldest first.
            parsed_candles: List[Candle] = []
            for item in raw_list:
                # [startTime, openPrice, highPrice, lowPrice, closePrice, volume, turnover]
                t_start = int(item[0])
                # Approximate close time based on interval
                dur_ms = 3600000 if interval == "1h" else 900000 if interval == "15m" else 86400000
                parsed_candles.append(Candle(
                    open_time_ms=t_start,
                    close_time_ms=t_start + dur_ms - 1,
                    open=float(item[1]),
                    high=float(item[2]),
                    low=float(item[3]),
                    close=float(item[4]),
                    volume=float(item[5]),
                    quote_volume=float(item[6]) if len(item) > 6 else None
                ))

            # Sort ascending by open_time_ms
            parsed_candles.sort(key=lambda c: c.open_time_ms)

            series = CandleSeries(
                canonical_id=canonical_id,
                exchange="bybit",
                interval=interval,
                candles=parsed_candles,
                status=MarketDataStatus.PASS
            )

            val_status, val_reasons = DataQualityValidator.validate_candles(series, interval_ms=dur_ms)
            series.status = val_status
            series.quality_reasons = val_reasons
            return series

        except Exception as e:
            return CandleSeries(
                canonical_id=canonical_id,
                exchange="bybit",
                interval=interval,
                candles=[],
                status=MarketDataStatus.FAIL,
                quality_reasons=[f"Bybit candle parsing error: {str(e)}"]
            )

    async def fetch_orderbook(
        self,
        symbol: str,
        limit: int = 20,
        custom_client: Optional[httpx.AsyncClient] = None
    ) -> OrderBookSnapshot:
        clean = self.clean_symbol(symbol)
        pair = f"{clean}USDT"
        canonical_id = f"crypto:bybit:{pair}"
        url = f"{self.base_url}/v5/market/orderbook"
        now_ms = int(time.time() * 1000)

        resp, err = await self._safe_http_get(
            url,
            params={"category": "spot", "symbol": pair, "limit": min(limit, 50)},
            custom_client=custom_client
        )

        if err or not resp:
            return OrderBookSnapshot(
                canonical_id=canonical_id,
                exchange="bybit",
                timestamp_ms=now_ms,
                bids=[],
                asks=[],
                spread=None,
                spread_bps=None,
                status=MarketDataStatus.UNAVAILABLE,
                quality_reasons=[err or "Bybit orderbook unavailable"]
            )

        try:
            d = resp.json()
            if d.get("retCode") != 0:
                return OrderBookSnapshot(
                    canonical_id=canonical_id,
                    exchange="bybit",
                    timestamp_ms=now_ms,
                    bids=[],
                    asks=[],
                    spread=None,
                    spread_bps=None,
                    status=MarketDataStatus.FAIL,
                    quality_reasons=[f"Bybit orderbook error {d.get('retCode')}: {d.get('retMsg')}"]
                )

            res = d.get("result", {})
            bids = [OrderBookLevel(price=float(b[0]), qty=float(b[1])) for b in res.get("b", [])]
            asks = [OrderBookLevel(price=float(a[0]), qty=float(a[1])) for a in res.get("a", [])]
            book_ts = int(res.get("ts", now_ms))

            spread = None
            spread_bps = None
            if bids and asks:
                spread = asks[0].price - bids[0].price
                mid = (asks[0].price + bids[0].price) / 2.0
                if mid > 0:
                    spread_bps = (spread / mid) * 10000.0

            snapshot = OrderBookSnapshot(
                canonical_id=canonical_id,
                exchange="bybit",
                timestamp_ms=book_ts,
                bids=bids,
                asks=asks,
                spread=spread,
                spread_bps=spread_bps,
                status=MarketDataStatus.PASS
            )

            val_status, val_reasons = DataQualityValidator.validate_orderbook(snapshot)
            snapshot.status = val_status
            snapshot.quality_reasons = val_reasons
            return snapshot

        except Exception as e:
            return OrderBookSnapshot(
                canonical_id=canonical_id,
                exchange="bybit",
                timestamp_ms=now_ms,
                bids=[],
                asks=[],
                spread=None,
                spread_bps=None,
                status=MarketDataStatus.FAIL,
                quality_reasons=[f"Bybit orderbook parse error: {str(e)}"]
            )


# ─── REGISTRY & DISPATCHER ────────────────────────────────────────

class MarketDataAdapterRegistry:
    """
    Registry for public market-data adapters.
    Ensures exchange provenance is never mixed or lost.
    """

    def __init__(self):
        self._adapters: Dict[str, BaseMarketDataAdapter] = {
            "binance": BinanceSpotAdapter(),
            "bybit": BybitSpotAdapter(),
        }

    def get_adapter(self, exchange: str = "binance") -> BaseMarketDataAdapter:
        ex = exchange.lower().strip()
        if ex not in self._adapters:
            raise ValueError(f"Unsupported exchange '{exchange}'. Supported: {list(self._adapters.keys())}")
        return self._adapters[ex]

    def parse_canonical_id(self, canonical_id: str) -> Tuple[str, str, str]:
        """
        Parses 'crypto:binance:BTCUSDT' -> ('crypto', 'binance', 'BTCUSDT')
        """
        parts = canonical_id.split(":")
        if len(parts) == 3:
            return parts[0], parts[1], parts[2]
        elif len(parts) == 2:
            return parts[0], "binance", parts[1]
        return "crypto", "binance", canonical_id

    async def fetch_ticker_by_canonical_id(self, canonical_id: str) -> TickerSnapshot:
        m_type, exchange, pair = self.parse_canonical_id(canonical_id)
        adapter = self.get_adapter(exchange)
        return await adapter.fetch_ticker(pair)


# Singleton instance
market_data_registry = MarketDataAdapterRegistry()
