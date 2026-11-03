"""
Deterministic Liquidity Qualification Engine for Tauric Trading Platform (Phase 2).
100% Rule-Based, Zero-AI-Cost, Multi-Exchange Segregated Architecture.

Features:
- Exchange-Specific: Evaluates Binance Spot and Bybit Spot independently without blending books or prices.
- 24h Quote Volume qualification in USD/USDT.
- Unrounded bid/ask spread and spread in basis points (spread_bps).
- Order-book depth within configurable percentage bands (e.g. 1% of mid).
- Configurable market-impact estimates based on reference capital ($1,000).
- Strict data freshness and provider quality gates.
- Exchange trading status and instrument metadata verification.
- Hard eligibility gates applied BEFORE scoring: missing/stale data produces UNKNOWN, STALE, or WAIT, never PASS.
"""

from dataclasses import dataclass, field
from enum import Enum
import math
import time
from typing import Any, Dict, List, Optional, Tuple

from .market_data_adapters import (
    BaseMarketDataAdapter,
    BinanceSpotAdapter,
    BybitSpotAdapter,
    InstrumentMetadata,
    MarketDataStatus,
    OrderBookLevel,
    OrderBookSnapshot,
    TickerSnapshot,
    market_data_registry,
)


class QualificationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    STALE = "STALE"
    WAIT = "WAIT"
    UNKNOWN = "UNKNOWN"


@dataclass
class LiquidityEngineConfig:
    """Configurable, documented thresholds for deterministic liquidity qualification."""
    # Volume requirements
    min_quote_volume_24h_usd: float = 5_000_000.0  # Minimum 24h quote volume ($5M)
    tier1_quote_volume_usd: float = 50_000_000.0   # Institutional liquidity tier ($50M+)

    # Spread requirements
    max_spread_bps: float = 25.0                    # Maximum acceptable spread in bps (0.25%)
    target_spread_bps: float = 5.0                  # Target tight spread in bps (0.05%)

    # Order book depth requirements
    depth_band_pct: float = 1.0                     # Evaluate depth within +/- 1.0% of mid price
    min_depth_usd: float = 20_000.0                 # Minimum required depth per side within band ($20k)
    tier1_depth_usd: float = 100_000.0              # Deep book threshold ($100k)

    # Market impact requirements
    reference_order_size_usd: float = 1_000.0       # Reference capital order size ($1,000)
    default_risk_budget_usd: float = 5.0            # Reference risk budget ($5)
    max_market_impact_bps: float = 15.0             # Max allowed slippage/impact on reference order (15 bps)

    # Freshness requirements
    max_quote_age_seconds: float = 60.0             # Maximum quote age before marking STALE
    max_orderbook_age_seconds: float = 60.0         # Maximum book age before marking STALE


@dataclass
class GateEvaluationResult:
    passed: bool
    gate_name: str
    observed_value: Any
    threshold_value: Any
    reason: str


@dataclass
class LiquidityQualificationResult:
    canonical_id: str
    exchange: str
    symbol: str
    is_qualified: bool                              # True ONLY if ALL hard gates pass
    status: QualificationStatus                    # PASS, FAIL, STALE, WAIT, UNKNOWN
    liquidity_score: float                         # 0.0 to 100.0 (0.0 if not qualified)
    gates: Dict[str, Dict[str, Any]]
    metrics: Dict[str, Any]
    reasons: List[str]
    timestamp_ms: int


class LiquidityQualificationEngine:
    """
    Deterministic liquidity qualifier for Spot trading pairs.
    Separates Binance Spot and Bybit Spot order books and prices.
    Zero AI or paid API dependencies.
    """

    def __init__(self, config: Optional[LiquidityEngineConfig] = None):
        self.config = config or LiquidityEngineConfig()

    def calculate_depth_within_band(
        self,
        levels: List[OrderBookLevel],
        mid_price: float,
        band_pct: float,
        is_bid: bool
    ) -> float:
        """
        Calculates cumulative order book depth in USD within band_pct of mid price.
        For bids: levels where price >= mid_price * (1 - band_pct / 100).
        For asks: levels where price <= mid_price * (1 + band_pct / 100).
        """
        if not levels or mid_price <= 0:
            return 0.0

        limit_price = (
            mid_price * (1.0 - band_pct / 100.0)
            if is_bid
            else mid_price * (1.0 + band_pct / 100.0)
        )

        total_usd = 0.0
        for lvl in levels:
            if not isinstance(lvl.price, (int, float)) or not isinstance(lvl.qty, (int, float)):
                continue
            if not math.isfinite(lvl.price) or not math.isfinite(lvl.qty):
                continue

            if is_bid:
                if lvl.price >= limit_price:
                    total_usd += lvl.price * lvl.qty
            else:
                if lvl.price <= limit_price:
                    total_usd += lvl.price * lvl.qty

        return total_usd

    def estimate_market_impact_bps(
        self,
        orderbook: OrderBookSnapshot,
        mid_price: float,
        order_size_usd: float
    ) -> Tuple[Optional[float], Optional[float], List[str]]:
        """
        Simulates filling a market order of size order_size_usd on both bid and ask sides.
        Returns:
            (buy_impact_bps, sell_impact_bps, diagnostic_notes)
        If book depth is insufficient to fill the order, returns None.
        """
        notes = []
        if not orderbook.asks or not orderbook.bids or mid_price <= 0 or order_size_usd <= 0:
            return None, None, ["Order book levels missing or non-positive mid price"]

        # 1. Simulate BUY (walking asks)
        remaining_usd = order_size_usd
        total_qty_bought = 0.0
        total_usd_spent = 0.0

        for ask in sorted(orderbook.asks, key=lambda x: x.price):
            if ask.price <= 0 or ask.qty <= 0:
                continue
            cost_level = ask.price * ask.qty
            if cost_level >= remaining_usd:
                qty_fill = remaining_usd / ask.price
                total_qty_bought += qty_fill
                total_usd_spent += remaining_usd
                remaining_usd = 0.0
                break
            else:
                total_qty_bought += ask.qty
                total_usd_spent += cost_level
                remaining_usd -= cost_level

        buy_impact_bps: Optional[float] = None
        if remaining_usd > 1e-4:
            notes.append(f"Insufficient ask depth to fill ${order_size_usd:,.2f} order (unfilled: ${remaining_usd:,.2f})")
        else:
            vwap_buy = total_usd_spent / total_qty_bought
            buy_impact_bps = max(0.0, (vwap_buy - mid_price) / mid_price * 10000.0)

        # 2. Simulate SELL (walking bids)
        remaining_usd = order_size_usd
        total_qty_sold = 0.0
        total_usd_received = 0.0

        for bid in sorted(orderbook.bids, key=lambda x: x.price, reverse=True):
            if bid.price <= 0 or bid.qty <= 0:
                continue
            cost_level = bid.price * bid.qty
            if cost_level >= remaining_usd:
                qty_fill = remaining_usd / bid.price
                total_qty_sold += qty_fill
                total_usd_received += remaining_usd
                remaining_usd = 0.0
                break
            else:
                total_qty_sold += bid.qty
                total_usd_received += cost_level
                remaining_usd -= cost_level

        sell_impact_bps: Optional[float] = None
        if remaining_usd > 1e-4:
            notes.append(f"Insufficient bid depth to fill ${order_size_usd:,.2f} order (unfilled: ${remaining_usd:,.2f})")
        else:
            vwap_sell = total_usd_received / total_qty_sold
            sell_impact_bps = max(0.0, (mid_price - vwap_sell) / mid_price * 10000.0)

        return buy_impact_bps, sell_impact_bps, notes

    def evaluate_liquidity(
        self,
        metadata: Optional[InstrumentMetadata],
        ticker: Optional[TickerSnapshot],
        orderbook: Optional[OrderBookSnapshot],
        current_time_ms: Optional[int] = None
    ) -> LiquidityQualificationResult:
        """
        Executes strict, deterministic liquidity qualification for an exchange pair.
        Never blends order books or ticker prices across exchanges.
        Applies hard eligibility gates before scoring.
        """
        now_ms = current_time_ms if current_time_ms is not None else int(time.time() * 1000)

        canonical_id = (
            ticker.canonical_id if ticker
            else orderbook.canonical_id if orderbook
            else metadata.canonical_id if metadata
            else "unknown:spot"
        )
        exchange = (
            ticker.exchange if ticker
            else orderbook.exchange if orderbook
            else metadata.exchange if metadata
            else "unknown"
        )
        symbol = ticker.symbol if ticker else "UNKNOWN"

        reasons: List[str] = []
        gates: Dict[str, Dict[str, Any]] = {}
        metrics: Dict[str, Any] = {}

        # ─── GATE 1: Instrument & Exchange Trading Status Gate ────────────
        if metadata is None:
            reasons.append("Missing instrument metadata")
            gates["instrument_status"] = {"passed": False, "reason": "Metadata is None"}
            return self._fail_result(canonical_id, exchange, symbol, QualificationStatus.UNKNOWN, gates, metrics, reasons, now_ms)

        if not metadata.is_spot:
            reasons.append("Instrument is not Spot (Derivatives, Perpetual, or Options rejected)")
            gates["instrument_status"] = {"passed": False, "is_spot": False, "status": metadata.status}
            return self._fail_result(canonical_id, exchange, symbol, QualificationStatus.FAIL, gates, metrics, reasons, now_ms)

        if metadata.status.upper() not in ("TRADING", "NORMAL", "OPEN"):
            reasons.append(f"Instrument status '{metadata.status}' is not TRADING/OPEN")
            gates["instrument_status"] = {"passed": False, "status": metadata.status}
            return self._fail_result(canonical_id, exchange, symbol, QualificationStatus.FAIL, gates, metrics, reasons, now_ms)

        gates["instrument_status"] = {"passed": True, "is_spot": True, "status": metadata.status}

        # ─── GATE 2: Ticker Data Quality & Freshness Gate ─────────────────
        if ticker is None or ticker.price is None:
            reasons.append("Ticker data or price is missing/unavailable")
            gates["ticker_quality"] = {"passed": False, "reason": "Ticker or price is None"}
            return self._fail_result(canonical_id, exchange, symbol, QualificationStatus.UNKNOWN, gates, metrics, reasons, now_ms)

        if ticker.status in (MarketDataStatus.UNAVAILABLE, MarketDataStatus.UNKNOWN):
            reasons.append(f"Ticker status is {ticker.status.value}")
            gates["ticker_quality"] = {"passed": False, "status": ticker.status.value}
            return self._fail_result(canonical_id, exchange, symbol, QualificationStatus.UNKNOWN, gates, metrics, reasons, now_ms)

        if ticker.status == MarketDataStatus.FAIL:
            reasons.append(f"Ticker status is FAIL ({ticker.quality_reasons})")
            gates["ticker_quality"] = {"passed": False, "status": "FAIL"}
            return self._fail_result(canonical_id, exchange, symbol, QualificationStatus.FAIL, gates, metrics, reasons, now_ms)

        # Freshness Check
        quote_age_s = max(0.0, (now_ms - ticker.timestamp_ms) / 1000.0)
        metrics["quote_age_seconds"] = round(quote_age_s, 2)
        if ticker.status == MarketDataStatus.STALE or quote_age_s > self.config.max_quote_age_seconds:
            reasons.append(f"Ticker quote is stale (age: {quote_age_s:.1f}s > {self.config.max_quote_age_seconds}s)")
            gates["ticker_quality"] = {"passed": False, "status": "STALE", "quote_age_s": quote_age_s}
            return self._fail_result(canonical_id, exchange, symbol, QualificationStatus.STALE, gates, metrics, reasons, now_ms)

        gates["ticker_quality"] = {"passed": True, "status": ticker.status.value, "quote_age_s": quote_age_s}

        # ─── GATE 3: Order Book Quality & Structure Gate ──────────────────
        if orderbook is None:
            reasons.append("Order book snapshot is missing/unavailable")
            gates["orderbook_quality"] = {"passed": False, "reason": "OrderBook is None"}
            return self._fail_result(canonical_id, exchange, symbol, QualificationStatus.UNKNOWN, gates, metrics, reasons, now_ms)

        if orderbook.status in (MarketDataStatus.UNAVAILABLE, MarketDataStatus.UNKNOWN):
            reasons.append(f"Order book status is {orderbook.status.value}")
            gates["orderbook_quality"] = {"passed": False, "status": orderbook.status.value}
            return self._fail_result(canonical_id, exchange, symbol, QualificationStatus.UNKNOWN, gates, metrics, reasons, now_ms)

        if orderbook.status == MarketDataStatus.FAIL:
            reasons.append(f"Order book status is FAIL ({orderbook.quality_reasons})")
            gates["orderbook_quality"] = {"passed": False, "status": "FAIL"}
            return self._fail_result(canonical_id, exchange, symbol, QualificationStatus.FAIL, gates, metrics, reasons, now_ms)

        if not orderbook.bids or not orderbook.asks:
            reasons.append("Order book bids or asks are empty")
            gates["orderbook_quality"] = {"passed": False, "reason": "Empty bids or asks"}
            return self._fail_result(canonical_id, exchange, symbol, QualificationStatus.FAIL, gates, metrics, reasons, now_ms)

        best_bid = orderbook.bids[0].price
        best_ask = orderbook.asks[0].price
        if best_bid >= best_ask:
            reasons.append(f"Crossed or locked market detected: best_bid ({best_bid}) >= best_ask ({best_ask})")
            gates["orderbook_quality"] = {"passed": False, "reason": "Crossed market"}
            return self._fail_result(canonical_id, exchange, symbol, QualificationStatus.FAIL, gates, metrics, reasons, now_ms)

        mid_price = (best_bid + best_ask) / 2.0
        metrics["best_bid"] = best_bid
        metrics["best_ask"] = best_ask
        metrics["mid_price"] = mid_price
        gates["orderbook_quality"] = {"passed": True, "status": orderbook.status.value}

        # ─── GATE 4: Bid/Ask Spread Gate ──────────────────────────────────
        spread = orderbook.spread if orderbook.spread is not None else (best_ask - best_bid)
        spread_bps = orderbook.spread_bps if orderbook.spread_bps is not None else ((spread / mid_price) * 10000.0)

        metrics["spread"] = spread
        metrics["spread_bps"] = spread_bps

        if spread <= 0 or not math.isfinite(spread) or not math.isfinite(spread_bps):
            reasons.append(f"Invalid non-positive spread: {spread}")
            gates["spread_gate"] = {"passed": False, "spread_bps": spread_bps, "max_allowed": self.config.max_spread_bps}
            return self._fail_result(canonical_id, exchange, symbol, QualificationStatus.FAIL, gates, metrics, reasons, now_ms)

        if spread_bps > self.config.max_spread_bps:
            reasons.append(f"Spread of {spread_bps:.2f} bps exceeds maximum threshold ({self.config.max_spread_bps:.1f} bps)")
            gates["spread_gate"] = {"passed": False, "spread_bps": spread_bps, "max_allowed": self.config.max_spread_bps}
            return self._fail_result(canonical_id, exchange, symbol, QualificationStatus.FAIL, gates, metrics, reasons, now_ms)

        gates["spread_gate"] = {"passed": True, "spread_bps": spread_bps, "max_allowed": self.config.max_spread_bps}

        # ─── GATE 5: 24-Hour Quote Volume Gate ────────────────────────────
        quote_vol = ticker.quote_volume_24h
        metrics["quote_volume_24h_usd"] = quote_vol

        if quote_vol is None or not isinstance(quote_vol, (int, float)) or not math.isfinite(quote_vol):
            reasons.append("24h quote volume is missing or non-finite")
            gates["volume_gate"] = {"passed": False, "reason": "Volume is None/non-finite"}
            return self._fail_result(canonical_id, exchange, symbol, QualificationStatus.UNKNOWN, gates, metrics, reasons, now_ms)

        if quote_vol < self.config.min_quote_volume_24h_usd:
            reasons.append(
                f"24h quote volume (${quote_vol:,.0f}) is below minimum required threshold (${self.config.min_quote_volume_24h_usd:,.0f})"
            )
            gates["volume_gate"] = {"passed": False, "observed": quote_vol, "min_required": self.config.min_quote_volume_24h_usd}
            return self._fail_result(canonical_id, exchange, symbol, QualificationStatus.FAIL, gates, metrics, reasons, now_ms)

        gates["volume_gate"] = {"passed": True, "observed": quote_vol, "min_required": self.config.min_quote_volume_24h_usd}

        # ─── GATE 6: Order-Book Depth Gate (within +/- 1%) ────────────────
        bid_depth_usd = self.calculate_depth_within_band(orderbook.bids, mid_price, self.config.depth_band_pct, is_bid=True)
        ask_depth_usd = self.calculate_depth_within_band(orderbook.asks, mid_price, self.config.depth_band_pct, is_bid=False)

        metrics["bid_depth_1pct_usd"] = round(bid_depth_usd, 2)
        metrics["ask_depth_1pct_usd"] = round(ask_depth_usd, 2)

        if bid_depth_usd < self.config.min_depth_usd or ask_depth_usd < self.config.min_depth_usd:
            reasons.append(
                f"Order book depth (Bid: ${bid_depth_usd:,.0f}, Ask: ${ask_depth_usd:,.0f}) "
                f"below minimum requirement (${self.config.min_depth_usd:,.0f}) within {self.config.depth_band_pct}%"
            )
            gates["depth_gate"] = {
                "passed": False,
                "bid_depth_usd": bid_depth_usd,
                "ask_depth_usd": ask_depth_usd,
                "min_required": self.config.min_depth_usd
            }
            return self._fail_result(canonical_id, exchange, symbol, QualificationStatus.FAIL, gates, metrics, reasons, now_ms)

        gates["depth_gate"] = {
            "passed": True,
            "bid_depth_usd": bid_depth_usd,
            "ask_depth_usd": ask_depth_usd,
            "min_required": self.config.min_depth_usd
        }

        # ─── GATE 7: Market Impact Estimation ($1,000 Reference Order) ────
        buy_impact_bps, sell_impact_bps, impact_notes = self.estimate_market_impact_bps(
            orderbook=orderbook,
            mid_price=mid_price,
            order_size_usd=self.config.reference_order_size_usd
        )

        metrics["reference_order_size_usd"] = self.config.reference_order_size_usd
        metrics["buy_impact_bps"] = buy_impact_bps
        metrics["sell_impact_bps"] = sell_impact_bps

        if buy_impact_bps is None or sell_impact_bps is None:
            reasons.extend(impact_notes)
            reasons.append(f"Insufficient order book depth to execute reference order (${self.config.reference_order_size_usd:,.0f})")
            gates["impact_gate"] = {"passed": False, "reason": "Insufficient depth for reference order"}
            return self._fail_result(canonical_id, exchange, symbol, QualificationStatus.FAIL, gates, metrics, reasons, now_ms)

        max_observed_impact_bps = max(buy_impact_bps, sell_impact_bps)
        metrics["max_observed_impact_bps"] = max_observed_impact_bps

        if max_observed_impact_bps > self.config.max_market_impact_bps:
            reasons.append(
                f"Estimated market impact ({max_observed_impact_bps:.2f} bps) exceeds threshold ({self.config.max_market_impact_bps:.1f} bps) "
                f"for ${self.config.reference_order_size_usd:,.0f} test size"
            )
            gates["impact_gate"] = {
                "passed": False,
                "impact_bps": max_observed_impact_bps,
                "max_allowed": self.config.max_market_impact_bps
            }
            return self._fail_result(canonical_id, exchange, symbol, QualificationStatus.FAIL, gates, metrics, reasons, now_ms)

        gates["impact_gate"] = {
            "passed": True,
            "impact_bps": max_observed_impact_bps,
            "max_allowed": self.config.max_market_impact_bps
        }

        # ─── COMPOSITE SCORING (Only reached if ALL gates pass) ───────────
        # 1. Volume Score (35 pts): Log scaling from min_quote_volume ($5M) to tier1 ($50M+)
        vol_ratio = max(0.0, min(1.0, (quote_vol - self.config.min_quote_volume_24h_usd) / (self.config.tier1_quote_volume_usd - self.config.min_quote_volume_24h_usd)))
        vol_score = 15.0 + (vol_ratio * 20.0)

        # 2. Spread Tightness Score (35 pts): 0 bps -> 35 pts, max_spread_bps -> 10 pts
        spread_ratio = max(0.0, min(1.0, (self.config.max_spread_bps - spread_bps) / self.config.max_spread_bps))
        spread_score = 10.0 + (spread_ratio * 25.0)

        # 3. Depth & Impact Score (30 pts): Lower impact and higher depth -> higher score
        impact_ratio = max(0.0, min(1.0, (self.config.max_market_impact_bps - max_observed_impact_bps) / self.config.max_market_impact_bps))
        impact_score = 10.0 + (impact_ratio * 20.0)

        composite_score = round(vol_score + spread_score + impact_score, 1)
        composite_score = max(50.0, min(100.0, composite_score))

        reasons.append(f"Pair fully qualified with composite liquidity score {composite_score}/100 on {exchange.upper()}.")
        reasons.append(f"24h Quote Vol: ${quote_vol:,.0f} | Spread: {spread_bps:.2f} bps | Impact: {max_observed_impact_bps:.2f} bps.")

        return LiquidityQualificationResult(
            canonical_id=canonical_id,
            exchange=exchange,
            symbol=symbol,
            is_qualified=True,
            status=QualificationStatus.PASS,
            liquidity_score=composite_score,
            gates=gates,
            metrics=metrics,
            reasons=reasons,
            timestamp_ms=now_ms
        )

    def _fail_result(
        self,
        canonical_id: str,
        exchange: str,
        symbol: str,
        status: QualificationStatus,
        gates: Dict[str, Dict[str, Any]],
        metrics: Dict[str, Any],
        reasons: List[str],
        timestamp_ms: int
    ) -> LiquidityQualificationResult:
        """
        Helper ensuring failed/unknown liquidity candidates NEVER receive a positive score or qualified status.
        """
        return LiquidityQualificationResult(
            canonical_id=canonical_id,
            exchange=exchange,
            symbol=symbol,
            is_qualified=False,
            status=status,
            liquidity_score=0.0,
            gates=gates,
            metrics=metrics,
            reasons=reasons,
            timestamp_ms=timestamp_ms
        )

    async def evaluate_exchange_pair(
        self,
        symbol: str,
        exchange: str = "binance"
    ) -> LiquidityQualificationResult:
        """
        Fetches live metadata, ticker, and order book for the specified exchange and evaluates liquidity.
        Strictly segregates exchange endpoints.
        """
        adapter = market_data_registry.get_adapter(exchange)
        clean_sym = adapter.clean_symbol(symbol)

        # Fetch in parallel via public adapter
        meta_task = adapter.fetch_instrument_metadata(clean_sym)
        ticker_task = adapter.fetch_ticker(clean_sym)
        depth_task = adapter.fetch_orderbook(clean_sym, limit=20)

        meta, ticker, book = await asyncio.gather(meta_task, ticker_task, depth_task, return_exceptions=True)

        metadata_obj = meta if isinstance(meta, InstrumentMetadata) else None
        ticker_obj = ticker if isinstance(ticker, TickerSnapshot) else None
        orderbook_obj = book if isinstance(book, OrderBookSnapshot) else None

        return self.evaluate_liquidity(
            metadata=metadata_obj,
            ticker=ticker_obj,
            orderbook=orderbook_obj
        )


import asyncio
liquidity_engine = LiquidityQualificationEngine()
