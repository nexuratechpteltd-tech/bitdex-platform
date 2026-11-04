# BITDEX — Quantitative HFT Simulation Data Provenance Audit

**Audit Date:** November 5, 2026  
**Subject:** Provenance of the 100 historical candles in the Quantitative HFT Simulation Panel  

---

## 1. Actual Origin of the 100 Candles

### Finding: **SYNTHETIC DETERMINISTIC SINE-WAVE DATA**
- **File:** `/opt/tauric-platform-staging/backend/app/services/exness/mock_adapter.py`
- **Function:** `get_historical_candles(symbol, timeframe="M1", count=100)` (Lines 227–250)
- **Exact Code Generating the Feed:**
  ```python
  tick = await self.get_latest_tick(symbol)
  mid = tick["mid"] # e.g. 2745.50 for XAUUSDm
  now_ts = int(time.time())
  candles = []
  for i in range(count, 0, -1):
      t = now_ts - (i * 60)
      wave = math.sin(i / 5.0) * 0.4
      c_open = mid + wave
      c_close = c_open + (0.1 if i % 2 == 0 else -0.1)
      candles.append({
          "time": t,
          "time_iso": datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
          "open": round(c_open, 2),
          "high": round(max(c_open, c_close) + 0.25, 2),
          "low": round(min(c_open, c_close) - 0.25, 2),
          "close": round(c_close, 2),
          "volume": 45 + (i % 20),
      })
  ```

### Provenance Classification:
- **Is it Live Broker Data?** **NO.**
- **Is it Downloaded Historical Data?** **NO.**
- **Is it Cached Data?** **NO.**
- **Classification:** **100% MATHEMATICAL SYNTHETIC GENERATION** based on `math.sin(i / 5.0)`.

---

## 2. Instrument & Contract Specifications for `XAUUSDm`

Defined in `/opt/tauric-platform-staging/backend/app/services/exness/simulation_engine.py` (Lines 40–50):
- **Contract Size:** `100.0` Troy Ounces per standard lot.
- **Volume:** `0.01 lots` $= 0.01 \times 100 = 1.0$ Troy Ounce of Gold.
- **Point Size:** `$0.01` (1 cent of gold price).
- **Point Value per Lot:** `$1.00 USD`.
- **Take-Profit (30 Points):** $30 \times \$0.01 = \$0.30$ price delta ($30 points).
- **Stop-Loss (60 Points):** $60 \times \$0.01 = \$0.60$ price delta ($60 points).
- **Spread:** `16.0 points` ($\$0.16$ per ounce).
- **Holding Window:** `15 bars` (15 minutes). If neither TP nor SL is touched within 15 1-minute bars, the position closes at `close` price of the 15th bar.
