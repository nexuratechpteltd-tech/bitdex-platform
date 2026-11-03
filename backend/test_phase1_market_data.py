#!/usr/bin/env python3
"""
Tauric Platform — Phase 1 Test Suite
Market-Data Adapters, Instrument Metadata & Deterministic Data-Quality Gates

Covers all 17 mandatory verification scenarios using mocked HTTP fixtures.
Zero AI calls, zero execution keys, zero production changes.
"""

import asyncio
import math
import time
import unittest
from typing import Dict, Any, List
import httpx

import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(backend_dir))

from app.services.market_data_adapters import (
    MarketDataStatus,
    InstrumentMetadata,
    TickerSnapshot,
    Candle,
    CandleSeries,
    OrderBookLevel,
    OrderBookSnapshot,
    DataQualityValidator,
    BinanceSpotAdapter,
    BybitSpotAdapter,
    MarketDataAdapterRegistry,
    market_data_registry,
)
from app.services.market_data import (
    fetch_single_symbol_market_data,
    fetch_live_market_data,
    SUPPORTED_SYMBOLS,
    _cached_market_data,
)
from app.config import settings
from app.services.telemetry_manager import telemetry_manager


class MockTransport(httpx.AsyncBaseTransport):
    """Deterministic mock transport for httpx."""
    def __init__(self, handler):
        self.handler = handler

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return await self.handler(request)


class TestPhase1MarketData(unittest.IsolatedAsyncioTestCase):

    # ─── 1. Binance Spot successful response ──────────────────────────
    async def test_01_binance_spot_successful_response(self):
        """Scenario 1: Binance Spot successful ticker and metadata response."""
        now_ms = int(time.time() * 1000)
        async def handler(request: httpx.Request) -> httpx.Response:
            url_str = str(request.url)
            if "exchangeInfo" in url_str:
                return httpx.Response(200, json={
                    "symbols": [{
                        "symbol": "BTCUSDT",
                        "status": "TRADING",
                        "baseAsset": "BTC",
                        "quoteAsset": "USDT",
                        "isSpotTradingAllowed": True,
                        "baseAssetPrecision": 8,
                        "quotePrecision": 8,
                        "filters": [
                            {"filterType": "LOT_SIZE", "minQty": "0.00001", "maxQty": "9000.0", "stepSize": "0.00001"},
                            {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                            {"filterType": "NOTIONAL", "minNotional": "5.0"}
                        ]
                    }]
                })
            elif "ticker/24hr" in url_str:
                return httpx.Response(200, json={
                    "symbol": "BTCUSDT",
                    "lastPrice": "82500.50",
                    "bidPrice": "82500.00",
                    "askPrice": "82501.00",
                    "highPrice": "83500.00",
                    "lowPrice": "81000.00",
                    "volume": "15420.5",
                    "quoteVolume": "1272000000.0",
                    "priceChangePercent": "1.85",
                    "closeTime": now_ms - 500
                })
            return httpx.Response(404)

        client = httpx.AsyncClient(transport=MockTransport(handler))
        adapter = BinanceSpotAdapter()
        
        # Test Metadata
        meta = await adapter.fetch_instrument_metadata("BTC", custom_client=client)
        self.assertEqual(meta.canonical_id, "crypto:binance:BTCUSDT")
        self.assertTrue(meta.is_spot)
        self.assertEqual(meta.status, "TRADING")
        self.assertEqual(meta.min_notional, 5.0)

        # Test Ticker
        ticker = await adapter.fetch_ticker("BTC", custom_client=client)
        self.assertEqual(ticker.status, MarketDataStatus.PASS)
        self.assertEqual(ticker.canonical_id, "crypto:binance:BTCUSDT")
        self.assertEqual(ticker.price, 82500.50)
        self.assertEqual(ticker.bid, 82500.00)
        self.assertEqual(ticker.ask, 82501.00)
        self.assertEqual(ticker.quality_score, 100.0)

    # ─── 2. Bybit Spot successful response ────────────────────────────
    async def test_02_bybit_spot_successful_response(self):
        """Scenario 2: Bybit Spot successful ticker and metadata response."""
        now_ms = int(time.time() * 1000)
        async def handler(request: httpx.Request) -> httpx.Response:
            url_str = str(request.url)
            if "instruments-info" in url_str:
                return httpx.Response(200, json={
                    "retCode": 0,
                    "retMsg": "OK",
                    "result": {
                        "category": "spot",
                        "list": [{
                            "symbol": "BTCUSDT",
                            "baseCoin": "BTC",
                            "quoteCoin": "USDT",
                            "status": "Trading",
                            "lotSizeFilter": {
                                "basePrecision": "0.000001",
                                "minOrderQty": "0.00004",
                                "maxOrderQty": "63.0",
                                "minOrderAmt": "1"
                            },
                            "priceFilter": {"tickSize": "0.1"}
                        }]
                    }
                })
            elif "tickers" in url_str:
                return httpx.Response(200, json={
                    "retCode": 0,
                    "retMsg": "OK",
                    "result": {
                        "category": "spot",
                        "list": [{
                            "symbol": "BTCUSDT",
                            "lastPrice": "82490.2",
                            "bid1Price": "82490.0",
                            "ask1Price": "82490.5",
                            "highPrice24h": "83400.0",
                            "lowPrice24h": "81200.0",
                            "volume24h": "9420.0",
                            "turnover24h": "777000000.0",
                            "price24hPcnt": "0.0152"
                        }]
                    },
                    "time": now_ms - 200
                })
            return httpx.Response(404)

        client = httpx.AsyncClient(transport=MockTransport(handler))
        adapter = BybitSpotAdapter()

        meta = await adapter.fetch_instrument_metadata("BTC", custom_client=client)
        self.assertEqual(meta.canonical_id, "crypto:bybit:BTCUSDT")
        self.assertTrue(meta.is_spot)
        self.assertEqual(meta.status, "Trading")
        self.assertEqual(meta.min_notional, 1.0)

        ticker = await adapter.fetch_ticker("BTC", custom_client=client)
        self.assertEqual(ticker.status, MarketDataStatus.PASS)
        self.assertEqual(ticker.canonical_id, "crypto:bybit:BTCUSDT")
        self.assertEqual(ticker.price, 82490.2)
        self.assertEqual(ticker.change_24h, 1.52)
        self.assertEqual(ticker.quality_score, 100.0)

    # ─── 3. Derivatives excluded from Spot instrument selection ───────
    async def test_03_derivatives_excluded_from_spot(self):
        """Scenario 3: Non-spot instruments (perpetual futures, linear, options) must be rejected."""
        # A. Bybit linear category rejection
        async def bybit_linear_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "retCode": 0,
                "retMsg": "OK",
                "result": {
                    "category": "linear",  # Not spot!
                    "list": [{
                        "symbol": "BTCUSDT",
                        "status": "Trading",
                        "lotSizeFilter": {},
                        "priceFilter": {}
                    }]
                }
            })

        client_bybit = httpx.AsyncClient(transport=MockTransport(bybit_linear_handler))
        bybit_adapter = BybitSpotAdapter()
        meta = await bybit_adapter.fetch_instrument_metadata("BTC", custom_client=client_bybit)
        self.assertFalse(meta.is_spot)
        self.assertEqual(meta.status, "FAIL")
        self.assertIn("Derivative rejected", meta.raw_data.get("error", ""))

        # B. Binance non-spot rejection
        async def binance_futures_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "symbols": [{
                    "symbol": "BTCUSDT",
                    "status": "TRADING",
                    "isSpotTradingAllowed": False,  # Margin/Futures only
                    "filters": []
                }]
            })

        client_binance = httpx.AsyncClient(transport=MockTransport(binance_futures_handler))
        binance_adapter = BinanceSpotAdapter()
        meta_bin = await binance_adapter.fetch_instrument_metadata("BTC", custom_client=client_binance)
        self.assertFalse(meta_bin.is_spot)
        val_status, reasons = DataQualityValidator.validate_instrument(meta_bin)
        self.assertEqual(val_status, MarketDataStatus.FAIL)
        self.assertTrue(any("Instrument is not Spot" in r for r in reasons))

    # ─── 4. Binance timeout ───────────────────────────────────────────
    async def test_04_binance_timeout(self):
        """Scenario 4: Timeout on Binance must report UNAVAILABLE with diagnostic reason."""
        async def timeout_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("ReadTimeout on api.binance.com")

        client = httpx.AsyncClient(transport=MockTransport(timeout_handler))
        adapter = BinanceSpotAdapter(timeout_seconds=0.1)
        ticker = await adapter.fetch_ticker("BTC", custom_client=client)

        self.assertEqual(ticker.status, MarketDataStatus.UNAVAILABLE)
        self.assertIsNone(ticker.price)
        self.assertTrue(any("timeout" in r.lower() for r in ticker.quality_reasons))

    # ─── 5. Bybit timeout ─────────────────────────────────────────────
    async def test_05_bybit_timeout(self):
        """Scenario 5: Timeout on Bybit must report UNAVAILABLE with diagnostic reason."""
        async def timeout_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("ReadTimeout on api.bybit.com")

        client = httpx.AsyncClient(transport=MockTransport(timeout_handler))
        adapter = BybitSpotAdapter(timeout_seconds=0.1)
        ticker = await adapter.fetch_ticker("BTC", custom_client=client)

        self.assertEqual(ticker.status, MarketDataStatus.UNAVAILABLE)
        self.assertIsNone(ticker.price)
        self.assertTrue(any("timeout" in r.lower() for r in ticker.quality_reasons))

    # ─── 6. HTTP rate limit ───────────────────────────────────────────
    async def test_06_http_rate_limit(self):
        """Scenario 6: HTTP 429 response must capture Retry-After and record rate limit state."""
        async def rate_limited_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, headers={"Retry-After": "45"}, text="Rate limit exceeded")

        client = httpx.AsyncClient(transport=MockTransport(rate_limited_handler))
        adapter = BinanceSpotAdapter()
        ticker = await adapter.fetch_ticker("BTC", custom_client=client)

        self.assertEqual(ticker.status, MarketDataStatus.UNAVAILABLE)
        self.assertTrue(adapter.is_rate_limited())
        rate_info = adapter.get_rate_limit_info()
        self.assertTrue(rate_info["rate_limited"])
        self.assertGreaterEqual(rate_info["retry_after_seconds"], 40.0)

    # ─── 7. Malformed JSON or invalid numeric values ──────────────────
    async def test_07_malformed_numeric_values(self):
        """Scenario 7: NaN, negative, or non-finite values must be rejected deterministically."""
        now_ms = int(time.time() * 1000)
        # Price is negative
        bad_ticker = TickerSnapshot(
            canonical_id="crypto:binance:BTCUSDT",
            exchange="binance",
            market_type="spot",
            symbol="BTC",
            pair="BTCUSDT",
            price=-100.0,
            bid=82000.0,
            ask=82001.0,
            spread=1.0,
            spread_bps=0.12,
            high_24h=83000.0,
            low_24h=81000.0,
            volume_24h=500.0,
            quote_volume_24h=40000000.0,
            change_24h=1.0,
            timestamp_ms=now_ms,
            fetched_at_ms=now_ms,
            status=MarketDataStatus.PASS,
            quality_score=100.0
        )
        status, score, reasons = DataQualityValidator.validate_ticker(bad_ticker)
        self.assertEqual(status, MarketDataStatus.FAIL)
        self.assertEqual(score, 0.0)
        self.assertTrue(any("must be positive" in r for r in reasons))

        # Price is NaN
        bad_ticker.price = float("nan")
        status, score, reasons = DataQualityValidator.validate_ticker(bad_ticker)
        self.assertEqual(status, MarketDataStatus.FAIL)
        self.assertTrue(any("not finite" in r for r in reasons))

    # ─── 8. Missing bid, ask, timestamp, or metadata ──────────────────
    async def test_08_missing_required_fields(self):
        """Scenario 8: Missing price or timestamp must yield UNKNOWN status, never PASS."""
        now_ms = int(time.time() * 1000)
        missing_price = TickerSnapshot(
            canonical_id="crypto:binance:BTCUSDT",
            exchange="binance",
            market_type="spot",
            symbol="BTC",
            pair="BTCUSDT",
            price=None,
            bid=82000.0,
            ask=82001.0,
            spread=1.0,
            spread_bps=0.12,
            high_24h=83000.0,
            low_24h=81000.0,
            volume_24h=500.0,
            quote_volume_24h=40000000.0,
            change_24h=1.0,
            timestamp_ms=now_ms,
            fetched_at_ms=now_ms,
            status=MarketDataStatus.PASS,
            quality_score=100.0
        )
        status, score, reasons = DataQualityValidator.validate_ticker(missing_price)
        self.assertEqual(status, MarketDataStatus.UNKNOWN)
        self.assertTrue(any("Missing price" in r for r in reasons))

        # Missing timestamp
        missing_price.price = 82000.0
        missing_price.timestamp_ms = 0
        status, score, reasons = DataQualityValidator.validate_ticker(missing_price)
        self.assertEqual(status, MarketDataStatus.UNKNOWN)
        self.assertTrue(any("timestamp" in r.lower() for r in reasons))

    # ─── 9. Stale quote rejection ─────────────────────────────────────
    async def test_09_stale_quote_rejection(self):
        """Scenario 9: Quote older than threshold (60s) must be marked STALE."""
        old_time = int((time.time() - 300) * 1000)  # 5 minutes old
        stale_ticker = TickerSnapshot(
            canonical_id="crypto:binance:BTCUSDT",
            exchange="binance",
            market_type="spot",
            symbol="BTC",
            pair="BTCUSDT",
            price=82000.0,
            bid=81999.0,
            ask=82001.0,
            spread=2.0,
            spread_bps=0.24,
            high_24h=83000.0,
            low_24h=81000.0,
            volume_24h=500.0,
            quote_volume_24h=40000000.0,
            change_24h=1.0,
            timestamp_ms=old_time,
            fetched_at_ms=int(time.time() * 1000),
            status=MarketDataStatus.PASS,
            quality_score=100.0
        )
        status, score, reasons = DataQualityValidator.validate_ticker(stale_ticker, max_age_ms=60_000)
        self.assertEqual(status, MarketDataStatus.STALE)
        self.assertLessEqual(score, 40.0)
        self.assertTrue(any("exceeds freshness threshold" in r for r in reasons))

    # ─── 10. Stale candle rejection ───────────────────────────────────
    async def test_10_stale_candle_rejection(self):
        """Scenario 10: Candle series whose latest candle is stale must be marked STALE."""
        four_hours_ago = int((time.time() - 14400) * 1000)
        candles = [
            Candle(open_time_ms=four_hours_ago, close_time_ms=four_hours_ago + 3599999, open=80000.0, high=80500.0, low=79800.0, close=80200.0, volume=100.0)
        ]
        series = CandleSeries(
            canonical_id="crypto:binance:BTCUSDT",
            exchange="binance",
            interval="1h",
            candles=candles,
            status=MarketDataStatus.PASS
        )
        status, reasons = DataQualityValidator.validate_candles(series, interval_ms=3600000, max_age_ms=7200000)
        self.assertEqual(status, MarketDataStatus.STALE)
        self.assertTrue(any("exceeds freshness threshold" in r for r in reasons))

    # ─── 11. Invalid bid/ask relationship ─────────────────────────────
    async def test_11_invalid_bid_ask_relationship(self):
        """Scenario 11: Crossed market (bid > ask) must be rejected with status FAIL."""
        now_ms = int(time.time() * 1000)
        crossed_ticker = TickerSnapshot(
            canonical_id="crypto:binance:BTCUSDT",
            exchange="binance",
            market_type="spot",
            symbol="BTC",
            pair="BTCUSDT",
            price=82000.0,
            bid=82100.0,   # Crossed: bid > ask!
            ask=82000.0,
            spread=-100.0,
            spread_bps=-12.1,
            high_24h=83000.0,
            low_24h=81000.0,
            volume_24h=500.0,
            quote_volume_24h=40000000.0,
            change_24h=1.0,
            timestamp_ms=now_ms,
            fetched_at_ms=now_ms,
            status=MarketDataStatus.PASS,
            quality_score=100.0
        )
        status, score, reasons = DataQualityValidator.validate_ticker(crossed_ticker)
        self.assertEqual(status, MarketDataStatus.FAIL)
        self.assertEqual(score, 0.0)
        self.assertTrue(any("Crossed market" in r for r in reasons))

        # Crossed Orderbook
        crossed_book = OrderBookSnapshot(
            canonical_id="crypto:binance:BTCUSDT",
            exchange="binance",
            timestamp_ms=now_ms,
            bids=[OrderBookLevel(price=82100.0, qty=1.0)],
            asks=[OrderBookLevel(price=82050.0, qty=1.0)],
            spread=-50.0,
            spread_bps=-6.0,
            status=MarketDataStatus.PASS
        )
        book_status, book_reasons = DataQualityValidator.validate_orderbook(crossed_book)
        self.assertEqual(book_status, MarketDataStatus.FAIL)
        self.assertTrue(any("Crossed order book" in r for r in book_reasons))

    # ─── 12. Duplicate and out-of-order candles ───────────────────────
    async def test_12_duplicate_and_out_of_order_candles(self):
        """Scenario 12: Duplicate open timestamps or disordered candles must trigger status FAIL."""
        t0 = 1729470000000
        # Duplicate timestamp
        duplicate_candles = [
            Candle(open_time_ms=t0, close_time_ms=t0 + 3599999, open=80000.0, high=80500.0, low=79800.0, close=80200.0, volume=100.0),
            Candle(open_time_ms=t0, close_time_ms=t0 + 3599999, open=80200.0, high=80600.0, low=80100.0, close=80400.0, volume=120.0),
        ]
        series = CandleSeries(
            canonical_id="crypto:binance:BTCUSDT",
            exchange="binance",
            interval="1h",
            candles=duplicate_candles,
            status=MarketDataStatus.PASS
        )
        status, reasons = DataQualityValidator.validate_candles(series, interval_ms=3600000)
        self.assertEqual(status, MarketDataStatus.FAIL)
        self.assertTrue(any("Duplicate candle timestamp" in r for r in reasons))

        # Out of order
        out_of_order_candles = [
            Candle(open_time_ms=t0 + 3600000, close_time_ms=t0 + 7199999, open=80200.0, high=80600.0, low=80100.0, close=80400.0, volume=120.0),
            Candle(open_time_ms=t0, close_time_ms=t0 + 3599999, open=80000.0, high=80500.0, low=79800.0, close=80200.0, volume=100.0),
        ]
        series.candles = out_of_order_candles
        status, reasons = DataQualityValidator.validate_candles(series, interval_ms=3600000)
        self.assertEqual(status, MarketDataStatus.FAIL)
        self.assertTrue(any("Out-of-order" in r for r in reasons))

    # ─── 13. Correct exchange identity in canonical IDs ───────────────
    async def test_13_canonical_id_exchange_identity(self):
        """Scenario 13: Canonical IDs must explicitly identify exchange and instrument."""
        binance_adapter = BinanceSpotAdapter()
        bybit_adapter = BybitSpotAdapter()

        self.assertEqual(binance_adapter.get_canonical_id("BTC"), "crypto:binance:BTCUSDT")
        self.assertEqual(bybit_adapter.get_canonical_id("BTC"), "crypto:bybit:BTCUSDT")
        self.assertEqual(binance_adapter.get_canonical_id("ETH/USDT"), "crypto:binance:ETHUSDT")
        self.assertEqual(bybit_adapter.get_canonical_id("ETH/USDT"), "crypto:bybit:ETHUSDT")

        reg = MarketDataAdapterRegistry()
        m_type, ex, pair = reg.parse_canonical_id("crypto:binance:BTCUSDT")
        self.assertEqual(ex, "binance")
        self.assertEqual(pair, "BTCUSDT")

        m_type2, ex2, pair2 = reg.parse_canonical_id("crypto:bybit:SOLUSDT")
        self.assertEqual(ex2, "bybit")
        self.assertEqual(pair2, "SOLUSDT")

    # ─── 14. No silent use of hardcoded fallback prices ───────────────
    async def test_14_no_hardcoded_fallback_prices(self):
        """Scenario 14: Failed requests must NEVER return old DEFAULT_FALLBACKS (e.g. 63450.0)."""
        # Inject network failure into adapter
        adapter = BinanceSpotAdapter()
        async def fail_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="Internal Server Error")

        # Clear memory cache
        from app.services import market_data
        market_data._cached_market_data.clear()
        market_data._last_fetch_time = 0.0

        client = httpx.AsyncClient(transport=MockTransport(fail_handler))
        ticker = await adapter.fetch_ticker("BTC", custom_client=client)

        # Must report UNAVAILABLE, price None
        self.assertEqual(ticker.status, MarketDataStatus.UNAVAILABLE)
        self.assertIsNone(ticker.price)
        self.assertNotEqual(ticker.price, 63450.0)

        # Also verify formatted consumer response
        resp = market_data._format_ticker_response(ticker, "binance", "BTCUSDT", "BTC")
        self.assertIsNone(resp["price"])
        self.assertEqual(resp["market_status"], "UNAVAILABLE")
        self.assertEqual(resp["status"], "UNAVAILABLE")
        self.assertNotEqual(resp["source"], "reference_baseline")

    # ─── 15. No regression to existing Forex data interfaces ──────────
    async def test_15_forex_interfaces_preserved(self):
        """Scenario 15: Forex market data provider, instruments, and registry remain completely functional."""
        from app.services.forex_market_data import forex_market_data, INSTRUMENT_REGISTRY, parse_instrument_id

        self.assertIn("fx:EURUSD", INSTRUMENT_REGISTRY)
        self.assertIn("metal:XAUUSD", INSTRUMENT_REGISTRY)

        meta = forex_market_data.get_instrument_meta("fx:EURUSD")
        self.assertEqual(meta["clean_symbol"], "EUR/USD")
        self.assertEqual(meta["asset_class"], "fx")

        session = forex_market_data.get_current_session()
        self.assertIn("current_session", session)
        self.assertIn("market_status", session)

        parsed_id = parse_instrument_id("EUR/USD")
        self.assertEqual(parsed_id, "fx:EURUSD")

    # ─── 16. No exchange execution requests or trading keys ───────────
    async def test_16_zero_execution_safeguards(self):
        """Scenario 16: Zero trading client initialization, zero private keys, read-only mode locked."""
        self.assertTrue(settings.live_trading_locked, "live_trading_locked must be True")
        self.assertTrue(settings.read_only_mode, "read_only_mode must be True")

        bin_adapter = BinanceSpotAdapter()
        by_adapter = BybitSpotAdapter()

        # Verify no execution methods exist on adapters
        forbidden_methods = ["create_order", "place_order", "cancel_order", "execute", "buy", "sell"]
        for m in forbidden_methods:
            self.assertFalse(hasattr(bin_adapter, m), f"Binance adapter has forbidden method {m}")
            self.assertFalse(hasattr(by_adapter, m), f"Bybit adapter has forbidden method {m}")

        # Verify zero auth headers or api key members
        self.assertFalse(hasattr(bin_adapter, "api_key"))
        self.assertFalse(hasattr(bin_adapter, "secret_key"))
        self.assertFalse(hasattr(by_adapter, "api_key"))
        self.assertFalse(hasattr(by_adapter, "secret_key"))

    # ─── 17. No AI-provider calls and zero ledger additions ───────────
    async def test_17_zero_ai_calls_during_market_data(self):
        """Scenario 17: Market data adapters and quality gates must NEVER call LLM or increment AI token ledger."""
        telemetry_before = telemetry_manager.get_telemetry()
        tokens_before = telemetry_before.get("known_tokens", 0)

        # Run multiple validator operations
        now_ms = int(time.time() * 1000)
        t = TickerSnapshot(
            canonical_id="crypto:binance:BTCUSDT",
            exchange="binance",
            market_type="spot",
            symbol="BTC",
            pair="BTCUSDT",
            price=82000.0,
            bid=81999.0,
            ask=82001.0,
            spread=2.0,
            spread_bps=0.24,
            high_24h=83000.0,
            low_24h=81000.0,
            volume_24h=500.0,
            quote_volume_24h=40000000.0,
            change_24h=1.0,
            timestamp_ms=now_ms,
            fetched_at_ms=now_ms,
            status=MarketDataStatus.PASS,
            quality_score=100.0
        )
        DataQualityValidator.validate_ticker(t)

        c = CandleSeries(
            canonical_id="crypto:binance:BTCUSDT",
            exchange="binance",
            interval="1h",
            candles=[Candle(open_time_ms=now_ms - 3600000, close_time_ms=now_ms - 1, open=81900.0, high=82100.0, low=81850.0, close=82000.0, volume=50.0)],
            status=MarketDataStatus.PASS
        )
        DataQualityValidator.validate_candles(c, 3600000)

        telemetry_after = telemetry_manager.get_telemetry()
        tokens_after = telemetry_after.get("known_tokens", 0)

        delta_tokens = tokens_after - tokens_before
        self.assertEqual(delta_tokens, 0, f"AI tokens increased by {delta_tokens} during market-data operations!")

    # ─── 18. Spread unrounded precision regression test ───────────────
    async def test_18_spread_unrounded_precision(self):
        """Scenario 18: Micro-spreads (e.g. 1e-10) must retain full internal float precision and not be rounded to zero."""
        now_ms = int(time.time() * 1000)
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "symbol": "PEPEUSDT",
                "lastPrice": "0.000010500000000",
                "bidPrice": "0.000010500000000",
                "askPrice": "0.000010500000005",  # spread = 0.000000000005 = 5e-12
                "highPrice": "0.0000110",
                "lowPrice": "0.0000100",
                "volume": "100000000.0",
                "quoteVolume": "1000.0",
                "priceChangePercent": "2.5",
                "closeTime": now_ms - 100
            })

        client = httpx.AsyncClient(transport=MockTransport(handler))
        adapter = BinanceSpotAdapter()
        ticker = await adapter.fetch_ticker("PEPE", custom_client=client)

        self.assertEqual(ticker.status, MarketDataStatus.PASS)
        expected_spread = 0.000010500000005 - 0.000010500000000
        self.assertIsNotNone(ticker.spread)
        self.assertGreater(ticker.spread, 0.0, "Micro-spread must NOT be rounded to zero internally!")
        self.assertAlmostEqual(ticker.spread, expected_spread, places=14)

    # ─── 19. Unified signal generation skips None and unavailable data ──
    async def test_19_unified_signals_skips_none_and_unavailable(self):
        """Scenario 19: Unified signal generation skips symbols with price=None, STALE, or UNAVAILABLE."""
        from app.services.unified_signal_engine import unified_signal_engine
        from unittest.mock import patch

        now_ms = int(time.time() * 1000)
        # Mock crypto market data with a mix of valid, None, STALE, and UNAVAILABLE
        mock_crypto = {
            "BTC": {"symbol": "BTC", "pair": "BTC/USDT", "price": 82000.0, "change_24h": 1.5, "high_24h": 83000.0, "low_24h": 81000.0, "volume_24h": 1e7, "status": "PASS"},
            "ETH": {"symbol": "ETH", "pair": "ETH/USDT", "price": None, "change_24h": None, "status": "UNAVAILABLE"},
            "SOL": {"symbol": "SOL", "pair": "SOL/USDT", "price": 105.0, "change_24h": 0.5, "high_24h": 110.0, "low_24h": 100.0, "volume_24h": 5e6, "status": "STALE"},
            "DOGE": {"symbol": "DOGE", "pair": "DOGE/USDT", "price": float("nan"), "change_24h": 0.0, "status": "FAIL"},
        }
        for s in SUPPORTED_SYMBOLS:
            if s not in mock_crypto:
                mock_crypto[s] = {"symbol": s, "pair": f"{s}/USDT", "price": None, "status": "UNAVAILABLE"}

        with patch("app.services.unified_signal_engine.fetch_live_market_data", return_value=mock_crypto):
            res = await unified_signal_engine.generate_unified_signals(force_refresh=True)
            self.assertEqual(res["status"], "SUCCESS")
            # Must NOT crash, and ETH / DOGE / SOL must NOT be processed as qualified signals
            crypto_signals = [s for s in res.get("signals", []) if s.get("market") == "CRYPTO"]
            # Only BTC could qualify
            for sig in crypto_signals:
                self.assertIsNotNone(sig.get("reference_price"))
                self.assertNotEqual(sig["symbol"], "ETH/USDT")
                self.assertNotEqual(sig["symbol"], "DOGE/USDT")
                self.assertNotEqual(sig["symbol"], "SOL/USDT")

    # ─── 20. Market listing and detail routes do not throw on missing data ─
    async def test_20_market_routes_no_ai_when_unavailable(self):
        """Scenario 20: GET /markets and /markets/{sym} must return DATA_UNAVAILABLE and zero AI calls when price=None."""
        from app.routes.markets import get_markets, get_market_detail
        from unittest.mock import patch

        mock_degraded = {
            s: {"symbol": s, "pair": f"{s}/USDT", "price": None, "change_24h": None, "status": "UNAVAILABLE"}
            for s in SUPPORTED_SYMBOLS
        }

        with patch("app.routes.markets.fetch_live_market_data", return_value=mock_degraded):
            # 1. get_markets
            res = await get_markets()
            self.assertEqual(res["count"], len(SUPPORTED_SYMBOLS))
            for item in res["data"]:
                self.assertEqual(item["ai_regime"], "DATA_UNAVAILABLE")
                self.assertIsNone(item["price"])
                self.assertEqual(item["ai_confidence"], 0.0)

            # 2. get_market_detail
            detail = await get_market_detail("BTC")
            self.assertEqual(detail["ai_analysis"]["regime"], "DATA_UNAVAILABLE")
            self.assertEqual(detail["ai_analysis"]["confidence"], 0.0)

    # ─── 21. Grid and trade setup scans skip invalid candidates ────────
    async def test_21_grid_scan_skips_invalid_candidates(self):
        """Scenario 21: Grid and trade setup scans skip invalid candidates without arithmetic exceptions."""
        from app.services.spot_grid_engine import spot_grid_engine
        from app.services.trade_setup_engine import trade_setup_engine
        from unittest.mock import patch

        mock_degraded = {
            "BTC": {"price": None, "change_24h": None, "status": "UNAVAILABLE"},
            "ETH": {"price": float("inf"), "change_24h": 0.0, "status": "FAIL"},
            "SOL": {"price": -50.0, "change_24h": 0.0, "status": "FAIL"},
        }

        with patch("app.services.spot_grid_engine.SpotGridEngine.evaluate_pair_for_grid") as mock_eval:
            with patch("app.services.market_data.fetch_live_market_data", return_value=mock_degraded):
                with patch("app.services.spot_grid_engine.SpotGridEngine.fetch_exchange_info", return_value=None):
                    candidates = await spot_grid_engine.scan_spot_grid_candidates(user_capital=100.0)
                    self.assertEqual(len(candidates), 0, "No candidates should be generated from invalid prices")
                    mock_eval.assert_not_called()

        with patch("app.services.trade_setup_engine.TradeSetupEngine.evaluate_trade_setup") as mock_ts_eval:
            with patch("app.services.market_data.fetch_live_market_data", return_value=mock_degraded):
                ts_candidates = await trade_setup_engine.scan_trade_setup_candidates(user_capital=100.0)
                self.assertEqual(len(ts_candidates), 0, "No trade setups should be generated from invalid prices")
                mock_ts_eval.assert_not_called()

    # ─── 22. Shadow evaluation aborts on unavailable live price ────────
    async def test_22_shadow_evaluation_rejects_unavailable_price(self):
        """Scenario 22: Shadow evaluation raises 503 instead of evaluating against None or fabricated price."""
        from app.routes.shadow import execute_shadow_cycle, ShadowRunRequest
        from fastapi import HTTPException
        from unittest.mock import patch

        mock_degraded = {
            "BTC": {"symbol": "BTC", "price": None, "change_24h": None, "status": "UNAVAILABLE"}
        }

        with patch("app.routes.shadow.fetch_live_market_data", return_value=mock_degraded):
            req = ShadowRunRequest(symbol="BTC-USD")
            with self.assertRaises(HTTPException) as ctx:
                await execute_shadow_cycle(req)
            self.assertEqual(ctx.exception.status_code, 503)
            self.assertIn("unavailable", ctx.exception.detail.lower())

    # ─── 23. Live directional meter returns DATA_UNAVAILABLE on None ──
    async def test_23_live_directional_meter_handles_unavailable(self):
        """Scenario 23: Live directional meter returns DATA_UNAVAILABLE when price is None."""
        from app.services.unified_signal_engine import unified_signal_engine
        from unittest.mock import patch

        mock_ticker = {
            "symbol": "BTC",
            "pair": "BTC/USDT",
            "price": None,
            "status": "UNAVAILABLE",
            "data_quality": {"status": "UNAVAILABLE", "reasons": ["Provider offline"]}
        }

        with patch("app.services.unified_signal_engine.fetch_single_symbol_market_data", return_value=mock_ticker):
            res = await unified_signal_engine.compute_live_directional_meter("BTC")
            self.assertEqual(res["status"], "DATA_UNAVAILABLE")
            self.assertIsNone(res["current_price"])
            self.assertIn("unavailable", res["message"].lower())

    # ─── 24. Zero AI ledger delta in Phase 1.1 ─────────────────────────
    async def test_24_zero_ai_ledger_delta_phase1_1(self):
        """Scenario 24: Verifies telemetry tokens and requests remain exactly 0 across all operations."""
        t = telemetry_manager.get_telemetry()
        known = t.get("known_tokens", 0)
        daily = t.get("daily_tokens_used", 0)
        reqs = t.get("request_count", 0)
        self.assertEqual(known, 0)
        self.assertEqual(daily, 0)
        self.assertEqual(reqs, 0)


if __name__ == "__main__":
    print("=" * 70)
    print("RUNNING TAURIC PHASE 1 & 1.1 AUTOMATED TEST SUITE (24 SCENARIOS)")
    print("=" * 70)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestPhase1MarketData)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    print("=" * 70)
    print(f"TESTS RUN: {result.testsRun} | FAILURES: {len(result.failures)} | ERRORS: {len(result.errors)}")
    print("=" * 70)
    sys.exit(0 if result.wasSuccessful() else 1)
