"""
Tauric Trading Platform — Phase 2 Automated Test Suite
Deterministic Market-Regime & Liquidity Qualification Engines

Scenarios Covered:
01. Normal / Trending Bullish Regime -> RISK_ON
02. Consolidation / Range-Bound Regime -> NEUTRAL
03. Sharp Downside Breakdown (<= -3.0%) -> RISK_OFF
04. Extreme Volatility Spike (>= 5.0%) -> RISK_OFF
05. Macro Event Blackout within Active Window -> EVENT_BLACKOUT
06. Event Blackout with Event Outside Window -> No Blackout
07. Untrusted Calendar Source -> UNKNOWN (Never Invents Phantom Events)
08. Missing Calendar Source -> UNKNOWN for Blackout Check (No Inventions)
09. Stale Market Quote -> Status STALE, Regime UNKNOWN
10. Missing / Non-Finite Price -> Status UNKNOWN, Regime UNKNOWN
11. Provider Outage / Degraded Status -> Status UNKNOWN, Regime UNKNOWN
12. Aggregate Market Breadth -> RISK_ON, RISK_OFF, NEUTRAL, and Degraded
13. Fully Qualified Liquidity Candidate (Binance Spot) -> PASS, Score >= 50
14. Segregated Bybit Spot Candidate -> PASS with Bybit Provenance (No Blending)
15. Low Quote Volume Gate (< $5M) -> FAIL, is_qualified=False, Score=0.0
16. Wide Spread Gate (> 25 bps) -> FAIL, is_qualified=False, Score=0.0
17. Shallow Order Book Depth Gate (< $20k within 1%) -> FAIL, is_qualified=False, Score=0.0
18. High Market Impact Gate (> 15 bps on $1k Order) -> FAIL, is_qualified=False, Score=0.0
19. Insufficient Book Depth to Fill $1,000 Reference Order -> FAIL, is_qualified=False
20. Crossed Market Rejection (bid >= ask) -> FAIL, is_qualified=False
21. Stale Data Liquidity Gate -> STALE, is_qualified=False (Never PASS)
22. Missing / Unavailable Liquidity Data -> UNKNOWN, is_qualified=False (Never PASS)
23. Non-Spot / Derivatives Instrument Rejection -> FAIL, is_qualified=False
24. Halted / Suspended Trading Status Rejection -> FAIL, is_qualified=False
25. Anti-Promotion Invariant Across All Degraded States
26. Zero AI Telemetry Delta and Zero Execution Keys
"""

import math
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

from app.services.market_data_adapters import (
    InstrumentMetadata,
    MarketDataStatus,
    OrderBookLevel,
    OrderBookSnapshot,
    TickerSnapshot,
)
from app.services.regime_engine import (
    DeterministicMarketRegimeEngine,
    EventCalendarSource,
    EventSeverity,
    MacroEvent,
    MarketRegime,
    RegimeEngineConfig,
)
from app.services.liquidity_engine import (
    LiquidityEngineConfig,
    LiquidityQualificationEngine,
    QualificationStatus,
)
from app.services.telemetry_manager import telemetry_manager



def make_metadata(
    canonical_id: str = "crypto:binance:BTCUSDT",
    exchange: str = "binance",
    symbol: str = "BTC",
    pair: str = "BTCUSDT",
    quote_currency: str = "USDT",
    status: str = "TRADING",
    is_spot: bool = True,
    min_notional: float = 5.0
) -> InstrumentMetadata:
    return InstrumentMetadata(
        canonical_id=canonical_id,
        exchange=exchange,
        market_type="spot",
        symbol=symbol,
        quote_currency=quote_currency,
        pair=pair,
        status=status,
        is_spot=is_spot,
        min_qty=0.0001,
        max_qty=1000.0,
        qty_step=0.0001,
        price_tick=0.01,
        min_notional=min_notional,
        base_precision=8,
        quote_precision=2,
        raw_data={}
    )


def make_ticker(
    canonical_id: str = "crypto:binance:BTCUSDT",
    exchange: str = "binance",
    symbol: str = "BTC",
    pair: str = "BTCUSDT",
    price: float = 84000.0,
    bid: float = 83999.99,
    ask: float = 84000.01,
    spread: float = 0.02,
    spread_bps: float = 0.00238,
    change_24h: float = 1.5,
    high_24h: float = 85000.0,
    low_24h: float = 83000.0,
    volume_24h: float = 12000.0,
    quote_volume_24h: float = 1_000_000_000.0,
    timestamp_ms: int = None,
    status: MarketDataStatus = MarketDataStatus.PASS,
    quality_score: float = 100.0,
    quality_reasons: list = None
) -> TickerSnapshot:
    now_ms = int(time.time() * 1000)
    ts = timestamp_ms if timestamp_ms is not None else now_ms
    return TickerSnapshot(
        canonical_id=canonical_id,
        exchange=exchange,
        market_type="spot",
        symbol=symbol,
        pair=pair,
        price=price,
        bid=bid,
        ask=ask,
        spread=spread,
        spread_bps=spread_bps,
        high_24h=high_24h,
        low_24h=low_24h,
        volume_24h=volume_24h,
        quote_volume_24h=quote_volume_24h,
        change_24h=change_24h,
        timestamp_ms=ts,
        fetched_at_ms=now_ms,
        status=status,
        quality_score=quality_score,
        quality_reasons=quality_reasons or []
    )

class MockCalendarSource:
    """Mock calendar source that can be flagged trustworthy or untrustworthy."""
    def __init__(self, events=None, reliable=True):
        self._events = events or []
        self._reliable = reliable

    def get_events(self, start_ms: int, end_ms: int):
        return [e for e in self._events if start_ms <= e.timestamp_ms <= end_ms]

    def is_reliable(self) -> bool:
        return self._reliable


class TestPhase2Qualification(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.now_ms = int(time.time() * 1000)
        self.regime_engine = DeterministicMarketRegimeEngine()
        self.liquidity_engine = LiquidityQualificationEngine()

    # ─── 01. Normal / Trending Bullish Regime ───────────────────────────
    def test_01_trending_bullish_regime_risk_on(self):
        """Scenario 1: Bullish momentum (+2.5%), price above EMAs -> RISK_ON."""
        res = self.regime_engine.evaluate_symbol_regime(
            symbol="BTC",
            price=84000.0,
            change_24h=2.5,
            quote_timestamp_ms=self.now_ms - 2000,
            data_status="PASS",
            indicators={"ema50": 82000.0, "ema200": 78000.0, "rsi": 62.0},
            current_time_ms=self.now_ms
        )
        self.assertEqual(res.regime, MarketRegime.RISK_ON)
        self.assertEqual(res.status, "PASS")
        self.assertGreaterEqual(res.confidence, 0.80)
        self.assertFalse(res.is_blackout)

    # ─── 02. Consolidation / Range-Bound Regime ─────────────────────────
    def test_02_consolidation_regime_neutral(self):
        """Scenario 2: Low directional drift (+0.2%), balanced indicators -> NEUTRAL."""
        res = self.regime_engine.evaluate_symbol_regime(
            symbol="ETH",
            price=3200.0,
            change_24h=0.2,
            quote_timestamp_ms=self.now_ms - 1500,
            data_status="PASS",
            indicators={"rsi": 51.5},
            current_time_ms=self.now_ms
        )
        self.assertEqual(res.regime, MarketRegime.NEUTRAL)
        self.assertEqual(res.status, "PASS")
        self.assertGreaterEqual(res.confidence, 0.75)

    # ─── 03. Sharp Downside Breakdown ───────────────────────────────────
    def test_03_sharp_downside_regime_risk_off(self):
        """Scenario 3: Severe 24h drop (-4.2% <= -3.0%) -> RISK_OFF."""
        res = self.regime_engine.evaluate_symbol_regime(
            symbol="SOL",
            price=140.0,
            change_24h=-4.2,
            quote_timestamp_ms=self.now_ms - 1000,
            data_status="PASS",
            indicators={"rsi": 28.0},
            current_time_ms=self.now_ms
        )
        self.assertEqual(res.regime, MarketRegime.RISK_OFF)
        self.assertEqual(res.status, "PASS")
        self.assertGreaterEqual(res.confidence, 0.85)

    # ─── 04. Extreme Volatility Spike ───────────────────────────────────
    def test_04_extreme_volatility_spike_risk_off(self):
        """Scenario 4: Extreme volatility spike (+6.5% >= 5.0%) triggers volatility RISK_OFF."""
        res = self.regime_engine.evaluate_symbol_regime(
            symbol="DOGE",
            price=0.18,
            change_24h=6.5,
            quote_timestamp_ms=self.now_ms - 1000,
            data_status="PASS",
            current_time_ms=self.now_ms
        )
        self.assertEqual(res.regime, MarketRegime.RISK_OFF)
        self.assertEqual(res.status, "PASS")
        self.assertIn("volatility", res.reasons[0].lower())

    # ─── 05. Macro Event Blackout within Active Window ──────────────────
    def test_05_macro_event_blackout_active(self):
        """Scenario 5: High-impact FOMC event 10m away -> EVENT_BLACKOUT."""
        event_time_ms = self.now_ms + (10 * 60 * 1000)  # 10 mins in future
        fomc = MacroEvent(
            event_id="FOMC-2026-10",
            title="FOMC Rate Decision",
            timestamp_ms=event_time_ms,
            severity=EventSeverity.HIGH,
            is_trustworthy=True
        )
        cal = MockCalendarSource(events=[fomc], reliable=True)

        res = self.regime_engine.evaluate_symbol_regime(
            symbol="BTC",
            price=84000.0,
            change_24h=1.5,
            quote_timestamp_ms=self.now_ms - 1000,
            data_status="PASS",
            calendar_source=cal,
            current_time_ms=self.now_ms
        )
        self.assertEqual(res.regime, MarketRegime.EVENT_BLACKOUT)
        self.assertEqual(res.status, "BLACKOUT")
        self.assertTrue(res.is_blackout)
        self.assertIsNotNone(res.blackout_event)
        self.assertEqual(res.blackout_event["event_id"], "FOMC-2026-10")

    # ─── 06. Event Outside Blackout Window ──────────────────────────────
    def test_06_event_outside_blackout_window(self):
        """Scenario 6: High-impact event 2 hours away (outside 30m buffer) -> Not Blackout."""
        event_time_ms = self.now_ms + (120 * 60 * 1000)  # 2 hours in future
        cpi = MacroEvent(
            event_id="CPI-2026-10",
            title="US CPI Release",
            timestamp_ms=event_time_ms,
            severity=EventSeverity.HIGH,
            is_trustworthy=True
        )
        cal = MockCalendarSource(events=[cpi], reliable=True)

        res = self.regime_engine.evaluate_symbol_regime(
            symbol="BTC",
            price=84000.0,
            change_24h=1.5,
            quote_timestamp_ms=self.now_ms - 1000,
            data_status="PASS",
            calendar_source=cal,
            current_time_ms=self.now_ms
        )
        self.assertFalse(res.is_blackout)
        self.assertEqual(res.regime, MarketRegime.RISK_ON)

    # ─── 07. Untrusted Calendar Source ──────────────────────────────────
    def test_07_untrusted_calendar_source_rejected(self):
        """Scenario 7: Untrusted calendar provider returns UNKNOWN; never invents phantom blackout."""
        fake_event = MacroEvent(
            event_id="FAKE-1",
            title="Fabricated Event",
            timestamp_ms=self.now_ms + 5000,
            is_trustworthy=False
        )
        untrusted_cal = MockCalendarSource(events=[fake_event], reliable=False)

        is_blackout, regime, reasons, ev = self.regime_engine.check_event_blackout(
            current_time_ms=self.now_ms,
            calendar_source=untrusted_cal
        )
        self.assertFalse(is_blackout)
        self.assertEqual(regime, MarketRegime.UNKNOWN)
        self.assertIn("untrustworthy", reasons[0].lower())
        self.assertIsNone(ev)

    # ─── 08. Missing Calendar Source ────────────────────────────────────
    def test_08_missing_calendar_source_no_invention(self):
        """Scenario 8: None calendar source returns UNKNOWN; never fabricates events."""
        is_blackout, regime, reasons, ev = self.regime_engine.check_event_blackout(
            current_time_ms=self.now_ms,
            calendar_source=None
        )
        self.assertFalse(is_blackout)
        self.assertEqual(regime, MarketRegime.UNKNOWN)
        self.assertIsNone(ev)

    # ─── 09. Stale Market Quote ─────────────────────────────────────────
    def test_09_stale_market_quote_rejected(self):
        """Scenario 9: Quote older than 60s is marked STALE and regime UNKNOWN."""
        res = self.regime_engine.evaluate_symbol_regime(
            symbol="BTC",
            price=84000.0,
            change_24h=2.0,
            quote_timestamp_ms=self.now_ms - (75 * 1000),  # 75s old
            data_status="PASS",
            current_time_ms=self.now_ms
        )
        self.assertEqual(res.regime, MarketRegime.UNKNOWN)
        self.assertEqual(res.status, "STALE")
        self.assertEqual(res.confidence, 0.0)

    # ─── 10. Missing / Non-Finite Price ─────────────────────────────────
    def test_10_missing_price_returns_unknown(self):
        """Scenario 10: price=None or NaN returns UNKNOWN with 0.0 confidence."""
        res_none = self.regime_engine.evaluate_symbol_regime(
            symbol="BTC", price=None, change_24h=1.0, data_status="PASS"
        )
        self.assertEqual(res_none.regime, MarketRegime.UNKNOWN)
        self.assertEqual(res_none.status, "UNKNOWN")

        res_nan = self.regime_engine.evaluate_symbol_regime(
            symbol="BTC", price=float("nan"), change_24h=1.0, data_status="PASS"
        )
        self.assertEqual(res_nan.regime, MarketRegime.UNKNOWN)

    # ─── 11. Provider Outage / Degraded Status ──────────────────────────
    def test_11_provider_outage_returns_unknown(self):
        """Scenario 11: data_status='UNAVAILABLE' or 'FAIL' returns UNKNOWN."""
        res = self.regime_engine.evaluate_symbol_regime(
            symbol="BTC", price=84000.0, change_24h=1.0, data_status="UNAVAILABLE"
        )
        self.assertEqual(res.regime, MarketRegime.UNKNOWN)
        self.assertEqual(res.status, "UNKNOWN")

    # ─── 12. Aggregate Market Breadth ───────────────────────────────────
    def test_12_aggregate_market_breadth(self):
        """Scenario 12: Aggregate breadth correctly determines market-wide regime."""
        # 1. Broad Risk-On
        breadth_risk_on = {
            "BTC": {"status": "PASS", "change_24h": 2.5},
            "ETH": {"status": "PASS", "change_24h": 3.1},
            "SOL": {"status": "PASS", "change_24h": 1.8},
            "BNB": {"status": "PASS", "change_24h": 1.2},
        }
        res_on = self.regime_engine.evaluate_market_breadth_regime(breadth_risk_on)
        self.assertEqual(res_on.regime, MarketRegime.RISK_ON)
        self.assertEqual(res_on.metrics["breadth_ratio"], 1.0)

        # 2. Broad Risk-Off
        breadth_risk_off = {
            "BTC": {"status": "PASS", "change_24h": -3.8},
            "ETH": {"status": "PASS", "change_24h": -4.5},
            "SOL": {"status": "PASS", "change_24h": -5.1},
            "BNB": {"status": "PASS", "change_24h": -2.9},
        }
        res_off = self.regime_engine.evaluate_market_breadth_regime(breadth_risk_off)
        self.assertEqual(res_off.regime, MarketRegime.RISK_OFF)

        # 3. Degraded / All Unavailable Breadth
        breadth_degraded = {
            "BTC": {"status": "UNAVAILABLE", "change_24h": None},
            "ETH": {"status": "FAIL", "change_24h": None},
        }
        res_deg = self.regime_engine.evaluate_market_breadth_regime(breadth_degraded)
        self.assertEqual(res_deg.regime, MarketRegime.UNKNOWN)

    # ─── 13. Fully Qualified Liquidity Candidate (Binance Spot) ─────────
    def test_13_fully_qualified_binance_spot_candidate(self):
        """Scenario 13: Healthy Binance Spot candidate with deep book passes all gates."""
        meta = make_metadata(
            canonical_id="crypto:binance:BTCUSDT",
            exchange="binance",
            symbol="BTC",
            pair="BTCUSDT",
            status="TRADING",
            is_spot=True,
            min_notional=5.0
        )
        ticker = make_ticker(
            canonical_id="crypto:binance:BTCUSDT",
            exchange="binance",
            symbol="BTC",
            price=84000.0,
            bid=83999.99,
            ask=84000.01,
            spread=0.02,
            spread_bps=0.00238,
            change_24h=1.5,
            quote_volume_24h=1_008_000_000.0,
            timestamp_ms=self.now_ms - 1000,
            status=MarketDataStatus.PASS
        )
        # Deep order book ($150k on each side within 1%)
        orderbook = OrderBookSnapshot(
            canonical_id="crypto:binance:BTCUSDT",
            exchange="binance",
            timestamp_ms=self.now_ms - 1000,
            bids=[OrderBookLevel(price=83999.99 - (i * 0.5), qty=0.5) for i in range(25)],
            asks=[OrderBookLevel(price=84000.01 + (i * 0.5), qty=0.5) for i in range(25)],
            spread=0.02,
            spread_bps=0.00238,
            status=MarketDataStatus.PASS,
            quality_reasons=[]
        )

        res = self.liquidity_engine.evaluate_liquidity(meta, ticker, orderbook, current_time_ms=self.now_ms)
        self.assertTrue(res.is_qualified)
        self.assertEqual(res.status, QualificationStatus.PASS)
        self.assertGreaterEqual(res.liquidity_score, 80.0)
        self.assertTrue(all(g["passed"] for g in res.gates.values()))

    # ─── 14. Segregated Bybit Spot Candidate ────────────────────────────
    def test_14_segregated_bybit_spot_candidate(self):
        """Scenario 14: Bybit Spot candidate is evaluated independently with Bybit provenance."""
        meta = make_metadata(
            canonical_id="crypto:bybit:BTCUSDT",
            exchange="bybit",
            symbol="BTC",
            pair="BTCUSDT",
            status="Trading",
            is_spot=True
        )
        ticker = make_ticker(
            canonical_id="crypto:bybit:BTCUSDT",
            exchange="bybit",
            symbol="BTC",
            price=84002.50,
            bid=84002.00,
            ask=84003.00,
            spread=1.00,
            spread_bps=0.119,
            change_24h=1.45,
            quote_volume_24h=420_000_000.0,
            timestamp_ms=self.now_ms - 800,
            status=MarketDataStatus.PASS
        )
        orderbook = OrderBookSnapshot(
            canonical_id="crypto:bybit:BTCUSDT",
            exchange="bybit",
            timestamp_ms=self.now_ms - 800,
            bids=[OrderBookLevel(price=84002.0 - i, qty=0.08) for i in range(25)],
            asks=[OrderBookLevel(price=84003.0 + i, qty=0.08) for i in range(25)],
            spread=1.00,
            spread_bps=0.119,
            status=MarketDataStatus.PASS,
            quality_reasons=[]
        )

        res = self.liquidity_engine.evaluate_liquidity(meta, ticker, orderbook, current_time_ms=self.now_ms)
        self.assertTrue(res.is_qualified)
        self.assertEqual(res.exchange, "bybit")
        self.assertEqual(res.canonical_id, "crypto:bybit:BTCUSDT")

    # ─── 15. Low Quote Volume Gate (< $5M) ──────────────────────────────
    def test_15_low_quote_volume_rejected(self):
        """Scenario 15: 24h volume of $1.5M < $5.0M threshold fails volume gate."""
        meta = make_metadata(canonical_id="crypto:binance:LOWUSDT", exchange="binance", symbol="LOW", pair="LOWUSDT", status="TRADING")
        ticker = make_ticker(
            canonical_id="crypto:binance:LOWUSDT", exchange="binance", symbol="LOW",
            price=10.0, bid=9.99, ask=10.01, spread=0.02, spread_bps=20.0,
            quote_volume_24h=1_500_000.0, timestamp_ms=self.now_ms - 1000
        )
        orderbook = OrderBookSnapshot(
            canonical_id="crypto:binance:LOWUSDT", exchange="binance", timestamp_ms=self.now_ms,
            bids=[OrderBookLevel(price=9.99 - (i * 0.01), qty=500.0) for i in range(10)],
            asks=[OrderBookLevel(price=10.01 + (i * 0.01), qty=500.0) for i in range(10)],
            spread=0.02, spread_bps=20.0, status=MarketDataStatus.PASS, quality_reasons=[]
        )

        res = self.liquidity_engine.evaluate_liquidity(meta, ticker, orderbook, current_time_ms=self.now_ms)
        self.assertFalse(res.is_qualified)
        self.assertEqual(res.status, QualificationStatus.FAIL)
        self.assertEqual(res.liquidity_score, 0.0)
        self.assertFalse(res.gates["volume_gate"]["passed"])

    # ─── 16. Wide Spread Gate (> 25 bps) ────────────────────────────────
    def test_16_wide_spread_rejected(self):
        """Scenario 16: Spread of 38 bps > 25 bps threshold fails spread gate."""
        meta = make_metadata(canonical_id="crypto:binance:WIDEUSDT", exchange="binance", symbol="WIDE", pair="WIDEUSDT", status="TRADING")
        ticker = make_ticker(
            canonical_id="crypto:binance:WIDEUSDT", exchange="binance", symbol="WIDE",
            price=100.0, bid=99.81, ask=100.19, spread=0.38, spread_bps=38.0,
            quote_volume_24h=10_000_000.0, timestamp_ms=self.now_ms - 1000
        )
        orderbook = OrderBookSnapshot(
            canonical_id="crypto:binance:WIDEUSDT", exchange="binance", timestamp_ms=self.now_ms,
            bids=[OrderBookLevel(price=99.81 - i, qty=50.0) for i in range(10)],
            asks=[OrderBookLevel(price=100.19 + i, qty=50.0) for i in range(10)],
            spread=0.38, spread_bps=38.0, status=MarketDataStatus.PASS, quality_reasons=[]
        )

        res = self.liquidity_engine.evaluate_liquidity(meta, ticker, orderbook, current_time_ms=self.now_ms)
        self.assertFalse(res.is_qualified)
        self.assertEqual(res.status, QualificationStatus.FAIL)
        self.assertEqual(res.liquidity_score, 0.0)
        self.assertFalse(res.gates["spread_gate"]["passed"])

    # ─── 17. Shallow Order Book Depth Gate (< $20k) ─────────────────────
    def test_17_shallow_order_book_depth_rejected(self):
        """Scenario 17: Order book depth of $8,000 within 1% < $20,000 fails depth gate."""
        meta = make_metadata(canonical_id="crypto:binance:THINUSDT", exchange="binance", symbol="THIN", pair="THINUSDT", status="TRADING")
        ticker = make_ticker(
            canonical_id="crypto:binance:THINUSDT", exchange="binance", symbol="THIN",
            price=50.0, bid=49.99, ask=50.01, spread=0.02, spread_bps=4.0,
            quote_volume_24h=10_000_000.0, timestamp_ms=self.now_ms - 1000
        )
        # Only 80 units * $50 = $4,000 per side
        orderbook = OrderBookSnapshot(
            canonical_id="crypto:binance:THINUSDT", exchange="binance", timestamp_ms=self.now_ms,
            bids=[OrderBookLevel(price=49.99, qty=80.0)],
            asks=[OrderBookLevel(price=50.01, qty=80.0)],
            spread=0.02, spread_bps=4.0, status=MarketDataStatus.PASS, quality_reasons=[]
        )

        res = self.liquidity_engine.evaluate_liquidity(meta, ticker, orderbook, current_time_ms=self.now_ms)
        self.assertFalse(res.is_qualified)
        self.assertEqual(res.status, QualificationStatus.FAIL)
        self.assertFalse(res.gates["depth_gate"]["passed"])

    # ─── 18. High Market Impact Gate (> 15 bps on $1k) ──────────────────
    def test_18_high_market_impact_rejected(self):
        """Scenario 18: Reference $1,000 order causes 24 bps slippage -> fails impact gate."""
        meta = make_metadata(canonical_id="crypto:binance:SLIPUSDT", exchange="binance", symbol="SLIP", pair="SLIPUSDT", status="TRADING")
        ticker = make_ticker(
            canonical_id="crypto:binance:SLIPUSDT", exchange="binance", symbol="SLIP",
            price=100.0, bid=99.98, ask=100.02, spread=0.04, spread_bps=4.0,
            quote_volume_24h=10_000_000.0, timestamp_ms=self.now_ms - 1000
        )
        # Asks jump sharply: 1 unit at 100.02 ($100), next at 100.40 ($900) -> impact > 25 bps
        orderbook = OrderBookSnapshot(
            canonical_id="crypto:binance:SLIPUSDT", exchange="binance", timestamp_ms=self.now_ms,
            bids=[OrderBookLevel(price=99.98, qty=5.0), OrderBookLevel(price=99.50, qty=500.0)],
            asks=[OrderBookLevel(price=100.02, qty=1.0), OrderBookLevel(price=100.45, qty=500.0)],
            spread=0.04, spread_bps=4.0, status=MarketDataStatus.PASS, quality_reasons=[]
        )

        res = self.liquidity_engine.evaluate_liquidity(meta, ticker, orderbook, current_time_ms=self.now_ms)
        self.assertFalse(res.is_qualified)
        self.assertEqual(res.status, QualificationStatus.FAIL)
        self.assertFalse(res.gates["impact_gate"]["passed"])

    # ─── 19. Insufficient Book Depth to Fill $1,000 Order ────────────────
    def test_19_insufficient_depth_for_reference_order(self):
        """Scenario 19: Order book total depth ($300) cannot fill $1,000 reference order."""
        meta = make_metadata(canonical_id="crypto:binance:TINYUSDT", exchange="binance", symbol="TINY", pair="TINYUSDT", status="TRADING")
        ticker = make_ticker(
            canonical_id="crypto:binance:TINYUSDT", exchange="binance", symbol="TINY",
            price=10.0, bid=9.99, ask=10.01, spread=0.02, spread_bps=20.0,
            quote_volume_24h=10_000_000.0, timestamp_ms=self.now_ms - 1000
        )
        # Total depth is only 15 units * $10 = $150
        orderbook = OrderBookSnapshot(
            canonical_id="crypto:binance:TINYUSDT", exchange="binance", timestamp_ms=self.now_ms,
            bids=[OrderBookLevel(price=9.99, qty=15.0)],
            asks=[OrderBookLevel(price=10.01, qty=15.0)],
            spread=0.02, spread_bps=20.0, status=MarketDataStatus.PASS, quality_reasons=[]
        )

        res = self.liquidity_engine.evaluate_liquidity(meta, ticker, orderbook, current_time_ms=self.now_ms)
        self.assertFalse(res.is_qualified)
        self.assertEqual(res.status, QualificationStatus.FAIL)

    # ─── 20. Crossed Market Rejection ───────────────────────────────────
    def test_20_crossed_market_rejection(self):
        """Scenario 20: Crossed order book (bid > ask) is immediately rejected with status FAIL."""
        meta = make_metadata(canonical_id="crypto:binance:CROSSUSDT", exchange="binance", symbol="CROSS", pair="CROSSUSDT", status="TRADING")
        ticker = make_ticker(
            canonical_id="crypto:binance:CROSSUSDT", exchange="binance", symbol="CROSS",
            price=50.0, bid=50.50, ask=49.50, spread=-1.0, spread_bps=-200.0,
            quote_volume_24h=10_000_000.0, timestamp_ms=self.now_ms - 1000,
            status=MarketDataStatus.FAIL, quality_reasons=["Crossed market"]
        )
        orderbook = OrderBookSnapshot(
            canonical_id="crypto:binance:CROSSUSDT", exchange="binance", timestamp_ms=self.now_ms,
            bids=[OrderBookLevel(price=50.50, qty=100.0)],
            asks=[OrderBookLevel(price=49.50, qty=100.0)],
            spread=-1.0, spread_bps=-200.0, status=MarketDataStatus.FAIL, quality_reasons=["Crossed market"]
        )

        res = self.liquidity_engine.evaluate_liquidity(meta, ticker, orderbook, current_time_ms=self.now_ms)
        self.assertFalse(res.is_qualified)
        self.assertEqual(res.status, QualificationStatus.FAIL)

    # ─── 21. Stale Data Liquidity Gate ──────────────────────────────────
    def test_21_stale_data_liquidity_gate(self):
        """Scenario 21: Ticker older than 60s returns status STALE, never PASS."""
        meta = make_metadata(canonical_id="crypto:binance:STALEUSDT", exchange="binance", symbol="STALE", pair="STALEUSDT", status="TRADING")
        ticker = make_ticker(
            canonical_id="crypto:binance:STALEUSDT", exchange="binance", symbol="STALE",
            price=50.0, bid=49.99, ask=50.01, spread=0.02, spread_bps=4.0,
            quote_volume_24h=10_000_000.0, timestamp_ms=self.now_ms - (90 * 1000),
            status=MarketDataStatus.STALE, quality_reasons=["Stale quote"]
        )
        orderbook = OrderBookSnapshot(
            canonical_id="crypto:binance:STALEUSDT", exchange="binance", timestamp_ms=self.now_ms,
            bids=[OrderBookLevel(price=49.99, qty=1000.0)],
            asks=[OrderBookLevel(price=50.01, qty=1000.0)],
            spread=0.02, spread_bps=4.0, status=MarketDataStatus.PASS, quality_reasons=[]
        )

        res = self.liquidity_engine.evaluate_liquidity(meta, ticker, orderbook, current_time_ms=self.now_ms)
        self.assertFalse(res.is_qualified)
        self.assertEqual(res.status, QualificationStatus.STALE)
        self.assertEqual(res.liquidity_score, 0.0)

    # ─── 22. Missing / Unavailable Liquidity Data ───────────────────────
    def test_22_missing_data_returns_unknown_or_wait(self):
        """Scenario 22: Missing ticker or UNAVAILABLE status returns UNKNOWN, never PASS."""
        meta = make_metadata(canonical_id="crypto:binance:NONEUSDT", exchange="binance", symbol="NONE", pair="NONEUSDT", status="TRADING")
        res_none_ticker = self.liquidity_engine.evaluate_liquidity(meta, None, None, current_time_ms=self.now_ms)
        self.assertFalse(res_none_ticker.is_qualified)
        self.assertEqual(res_none_ticker.status, QualificationStatus.UNKNOWN)
        self.assertEqual(res_none_ticker.liquidity_score, 0.0)

        ticker_unavail = make_ticker(
            canonical_id="crypto:binance:NONEUSDT", exchange="binance", symbol="NONE",
            price=None, bid=None, ask=None, spread=None, spread_bps=None,
            change_24h=None, quote_volume_24h=None, timestamp_ms=self.now_ms,
            status=MarketDataStatus.UNAVAILABLE, quality_reasons=["Provider timeout"]
        )
        res_unavail = self.liquidity_engine.evaluate_liquidity(meta, ticker_unavail, None, current_time_ms=self.now_ms)
        self.assertFalse(res_unavail.is_qualified)
        self.assertEqual(res_unavail.status, QualificationStatus.UNKNOWN)
        self.assertEqual(res_unavail.liquidity_score, 0.0)

    # ─── 23. Non-Spot / Derivatives Instrument Rejection ────────────────
    def test_23_non_spot_instrument_rejected(self):
        """Scenario 23: Non-spot instrument (is_spot=False) is rejected at Gate 1."""
        meta = make_metadata(
            canonical_id="crypto:binance:BTCUSDT_PERP",
            exchange="binance",
            symbol="BTC",
            pair="BTCUSDT",
            status="TRADING",
            is_spot=False
        )
        res = self.liquidity_engine.evaluate_liquidity(meta, None, None, current_time_ms=self.now_ms)
        self.assertFalse(res.is_qualified)
        self.assertEqual(res.status, QualificationStatus.FAIL)
        self.assertFalse(res.gates["instrument_status"]["passed"])

    # ─── 24. Halted / Suspended Trading Status Rejection ─────────────────
    def test_24_halted_trading_status_rejected(self):
        """Scenario 24: Halted / maintenance exchange status is rejected at Gate 1."""
        meta = make_metadata(
            canonical_id="crypto:binance:HALTUSDT",
            exchange="binance",
            symbol="HALT",
            pair="HALTUSDT",
            status="HALTED",
            is_spot=True
        )
        res = self.liquidity_engine.evaluate_liquidity(meta, None, None, current_time_ms=self.now_ms)
        self.assertFalse(res.is_qualified)
        self.assertEqual(res.status, QualificationStatus.FAIL)

    # ─── 25. Anti-Promotion Invariant Across All Degraded States ─────────
    def test_25_anti_promotion_invariant(self):
        """Scenario 25: Asserts no failed, stale, or unknown candidate can EVER be qualified or score > 0."""
        degraded_statuses = [QualificationStatus.FAIL, QualificationStatus.STALE, QualificationStatus.UNKNOWN, QualificationStatus.WAIT]
        for st in degraded_statuses:
            res = self.liquidity_engine._fail_result(
                canonical_id="test", exchange="binance", symbol="TEST", status=st,
                gates={}, metrics={}, reasons=["Degraded test"], timestamp_ms=self.now_ms
            )
            self.assertFalse(res.is_qualified, f"Candidate with status {st} must NOT be qualified!")
            self.assertEqual(res.liquidity_score, 0.0, f"Candidate with status {st} must have score 0.0!")

    # ─── 26. Zero AI Telemetry Delta and Zero Execution Keys ────────────
    def test_26_zero_ai_telemetry_and_zero_execution_keys(self):
        """Scenario 26: Asserts zero LLM tokens and requests consumed, and trading locked."""
        from app.config import settings
        self.assertTrue(settings.live_trading_locked)
        self.assertTrue(settings.read_only_mode)

        t = telemetry_manager.get_telemetry()
        known = t.get("known_tokens", 0)
        daily = t.get("daily_tokens_used", 0)
        reqs = t.get("request_count", 0)
        self.assertEqual(known, 0)
        self.assertEqual(daily, 0)
        self.assertEqual(reqs, 0)


if __name__ == "__main__":
    print("=" * 70)
    print("RUNNING TAURIC PHASE 2 AUTOMATED TEST SUITE (26 SCENARIOS)")
    print("=" * 70)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestPhase2Qualification)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    print("=" * 70)
    print(f"PHASE 2 TESTS RUN: {result.testsRun} | FAILURES: {len(result.failures)} | ERRORS: {len(result.errors)}")
    print("=" * 70)
    sys.exit(0 if result.wasSuccessful() else 1)
