#!/usr/bin/env python3
"""
Tauric Platform — Phase 1 Public Smoke Tests
Live network smoke tests against real Binance Spot and Bybit Spot public APIs.
Strictly rate-limited (1 request per exchange), zero execution, zero AI calls.
"""

import asyncio
import json
import time
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(backend_dir))

from app.services.market_data_adapters import (
    BinanceSpotAdapter,
    BybitSpotAdapter,
    DataQualityValidator,
    MarketDataStatus,
)
from app.services.telemetry_manager import telemetry_manager


async def run_smoke_tests():
    print("=" * 70)
    print("PHASE 1 PUBLIC ADAPTER NETWORK SMOKE TEST")
    print("=" * 70)

    t_before = telemetry_manager.get_telemetry()
    tokens_before = t_before.get("known_tokens", 0)

    # 1. Binance Spot Smoke Test
    print("\n[1/2] Testing Binance Spot Public APIs (BTCUSDT)...")
    bin_adapter = BinanceSpotAdapter(timeout_seconds=6.0)
    
    t0 = time.time()
    meta_bin = await bin_adapter.fetch_instrument_metadata("BTC")
    t_meta = int((time.time() - t0) * 1000)

    t1 = time.time()
    ticker_bin = await bin_adapter.fetch_ticker("BTC")
    t_ticker = int((time.time() - t1) * 1000)

    t2 = time.time()
    klines_bin = await bin_adapter.fetch_klines("BTC", interval="1h", limit=5)
    t_klines = int((time.time() - t2) * 1000)

    print(f"  -> Metadata : {meta_bin.canonical_id} | Spot={meta_bin.is_spot} | Status={meta_bin.status} | MinNotional=${meta_bin.min_notional} ({t_meta}ms)")
    print(f"  -> Ticker   : Price=${ticker_bin.price:,.2f} | 24h={ticker_bin.change_24h:+.2f}% | Spread=${ticker_bin.spread} ({ticker_bin.spread_bps} bps) | Status={ticker_bin.status.value} ({t_ticker}ms)")
    print(f"  -> Klines   : Count={len(klines_bin.candles)} | Status={klines_bin.status.value} ({t_klines}ms)")
    print(f"  -> Quality  : Score={ticker_bin.quality_score}/100 | Reasons: {ticker_bin.quality_reasons}")

    # Small pause to respect provider rate limits
    await asyncio.sleep(1.0)

    # 2. Bybit Spot Smoke Test
    print("\n[2/2] Testing Bybit Spot Public APIs (BTCUSDT)...")
    by_adapter = BybitSpotAdapter(timeout_seconds=6.0)

    t0 = time.time()
    meta_by = await by_adapter.fetch_instrument_metadata("BTC")
    t_meta = int((time.time() - t0) * 1000)

    t1 = time.time()
    ticker_by = await by_adapter.fetch_ticker("BTC")
    t_ticker = int((time.time() - t1) * 1000)

    t2 = time.time()
    klines_by = await by_adapter.fetch_klines("BTC", interval="1h", limit=5)
    t_klines = int((time.time() - t2) * 1000)

    print(f"  -> Metadata : {meta_by.canonical_id} | Spot={meta_by.is_spot} | Status={meta_by.status} | MinNotional=${meta_by.min_notional} ({t_meta}ms)")
    print(f"  -> Ticker   : Price=${ticker_by.price:,.2f} | 24h={ticker_by.change_24h:+.2f}% | Spread=${ticker_by.spread} ({ticker_by.spread_bps} bps) | Status={ticker_by.status.value} ({t_ticker}ms)")
    print(f"  -> Klines   : Count={len(klines_by.candles)} | Status={klines_by.status.value} ({t_klines}ms)")
    print(f"  -> Quality  : Score={ticker_by.quality_score}/100 | Reasons: {ticker_by.quality_reasons}")

    t_after = telemetry_manager.get_telemetry()
    tokens_after = t_after.get("known_tokens", 0)
    delta_tokens = tokens_after - tokens_before

    print("\n" + "=" * 70)
    print(f"SMOKE TEST SUMMARY: Binance={ticker_bin.status.value} | Bybit={ticker_by.status.value}")
    print(f"AI Token Delta = {delta_tokens} (Must be exactly 0)")
    print("=" * 70)

    if ticker_bin.status == MarketDataStatus.PASS and ticker_by.status == MarketDataStatus.PASS and delta_tokens == 0:
        return 0
    return 1


if __name__ == "__main__":
    code = asyncio.run(run_smoke_tests())
    sys.exit(code)
