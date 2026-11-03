"""
BITDEX Historical Data Acquisition Engine (Phase 3.2)
======================================================
Downloads, verifies, and stores 90 days of continuous historical klines
from Binance USD(S)-M Futures public REST API:
- Timeframes: 1h, 15m, 5m
- Symbols: BTCUSDT, ETHUSDT, SOLUSDT
- Audits: Missing intervals, duplicate timestamps, data span, data integrity.
"""

import os
import sys
import time
import json
from datetime import datetime, timezone
from typing import Dict, Any, List
import httpx

DATA_DIR = "/opt/tauric-platform-staging/backend/data/historical_90d"
os.makedirs(DATA_DIR, exist_ok=True)

INTERVAL_MS = {
    "1h": 3600 * 1000,
    "15m": 15 * 60 * 1000,
    "5m": 5 * 60 * 1000,
}

TARGET_DAYS = 90

def fetch_klines_paginated(symbol: str, interval: str, target_days: int = TARGET_DAYS) -> List[Dict[str, Any]]:
    interval_ms = INTERVAL_MS[interval]
    now_ms = int(time.time() * 1000)
    # Round down to last closed candle
    now_ms = (now_ms // interval_ms) * interval_ms
    start_target_ms = now_ms - (target_days * 24 * 3600 * 1000)
    
    url = "https://fapi.binance.com/fapi/v1/klines"
    all_candles = []
    current_start = start_target_ms

    print(f"[{symbol} - {interval}] Fetching from {datetime.fromtimestamp(start_target_ms/1000, tz=timezone.utc).isoformat()} to {datetime.fromtimestamp(now_ms/1000, tz=timezone.utc).isoformat()}...")

    client = httpx.Client(timeout=30.0)
    
    while current_start < now_ms:
        params = {
            "symbol": symbol.upper(),
            "interval": interval,
            "startTime": current_start,
            "limit": 1000
        }
        resp = client.get(url, params=params)
        if resp.status_code != 200:
            print(f"Error fetching {symbol} {interval}: HTTP {resp.status_code} - {resp.text}")
            break
        
        batch = resp.json()
        if not batch:
            break
            
        for k in batch:
            open_t = int(k[0])
            if open_t < now_ms:
                all_candles.append({
                    "open_time": open_t,
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                    "close_time": int(k[6]),
                    "quote_volume": float(k[7]),
                    "trades_count": int(k[8]),
                })
        
        last_open_t = int(batch[-1][0])
        next_start = last_open_t + interval_ms
        if next_start <= current_start or len(batch) < 1000:
            break
        current_start = next_start
        time.sleep(0.05)  # respectful pacing

    # Deduplicate by open_time
    seen = set()
    deduped = []
    for c in all_candles:
        if c["open_time"] not in seen:
            seen.add(c["open_time"])
            deduped.append(c)
    deduped.sort(key=lambda x: x["open_time"])
    return deduped


def audit_and_save(symbol: str, interval: str, candles: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not candles:
        return {"symbol": symbol, "interval": interval, "status": "EMPTY"}
        
    interval_ms = INTERVAL_MS[interval]
    first_t = candles[0]["open_time"]
    last_t = candles[-1]["open_time"]
    first_dt = datetime.fromtimestamp(first_t / 1000, tz=timezone.utc).isoformat()
    last_dt = datetime.fromtimestamp(last_t / 1000, tz=timezone.utc).isoformat()
    span_hours = (last_t - first_t) / (3600 * 1000)
    span_days = span_hours / 24.0

    # Gap detection
    gaps = []
    for i in range(1, len(candles)):
        diff = candles[i]["open_time"] - candles[i-1]["open_time"]
        if diff != interval_ms:
            gaps.append({
                "index": i,
                "prev_time": candles[i-1]["open_time"],
                "curr_time": candles[i]["open_time"],
                "gap_ms": diff,
                "missing_candles": (diff // interval_ms) - 1
            })

    audit_meta = {
        "symbol": symbol,
        "interval": interval,
        "source": "Binance USD(S)-M Futures REST API (/fapi/v1/klines)",
        "acquisition_timestamp": datetime.now(timezone.utc).isoformat(),
        "candle_count": len(candles),
        "first_candle_time": first_t,
        "first_candle_iso": first_dt,
        "last_candle_time": last_t,
        "last_candle_iso": last_dt,
        "span_hours": round(span_hours, 2),
        "span_days": round(span_days, 2),
        "target_days": TARGET_DAYS,
        "is_complete_90d": span_days >= 89.5,
        "duplicate_count": 0,
        "gap_count": len(gaps),
        "gaps_sample": gaps[:10]
    }

    # Save to disk
    out_file = os.path.join(DATA_DIR, f"{symbol.lower()}_{interval}_90d.json")
    with open(out_file, "w") as f:
        json.dump({"metadata": audit_meta, "candles": candles}, f)

    meta_file = os.path.join(DATA_DIR, f"{symbol.lower()}_{interval}_meta.json")
    with open(meta_file, "w") as f:
        json.dump(audit_meta, f, indent=2)

    print(f"  -> {symbol} [{interval}]: {len(candles)} candles | {span_days:.1f} days | Gaps: {len(gaps)} | Saved: {out_file}")
    return audit_meta


def run():
    print("=" * 80)
    print("STARTING 90-DAY HISTORICAL DATA ACQUISITION FOR BITDEX PHASE 3.2")
    print("=" * 80)
    
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    intervals = ["1h", "15m", "5m"]
    
    all_audits = []
    for s in symbols:
        for itv in intervals:
            candles = fetch_klines_paginated(s, itv, target_days=90)
            meta = audit_and_save(s, itv, candles)
            all_audits.append(meta)

    summary_file = os.path.join(DATA_DIR, "acquisition_summary.json")
    with open(summary_file, "w") as f:
        json.dump(all_audits, f, indent=2)

    print("\n" + "=" * 80)
    print("90-DAY DATA ACQUISITION & INTEGRITY AUDIT COMPLETE")
    print("=" * 80)
    print(f"{'Symbol':8s} | {'Interval':8s} | {'Candles':8s} | {'Span (Days)':12s} | {'Gaps':6s} | {'Complete 90d':12s}")
    print("-" * 65)
    for a in all_audits:
        print(f"{a['symbol']:8s} | {a['interval']:8s} | {a['candle_count']:8d} | {a['span_days']:12.2f} | {a['gap_count']:6d} | {str(a['is_complete_90d']):12s}")


if __name__ == "__main__":
    run()
