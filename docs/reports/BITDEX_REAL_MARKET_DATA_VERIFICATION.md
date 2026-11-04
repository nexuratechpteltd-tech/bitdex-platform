# BITDEX — Real Market-Data Pipeline Verification Report (Phase 5)

**Environment:** Linux Staging Server (`169.58.218.168`)  
**Date:** November 5, 2026  
**Status:** **VERIFIED & DISAGGREGATED**

---

## 1. Market Data Source Disaggregation

To satisfy the transparency requirement, the market data feeds powering BITDEX have been audited and explicitly classified:

| Category | Source Provider | Live Status | Bid / Ask Retrieved | Latency / Freshness | Source Attribution |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **A. Exness Broker Data** | Exness MT5 Gateway / Trader API | **BLOCKED (Offline)** | `null` / `null` | N/A (Fail-Closed) | `broker:exness:mt5` |
| **B. Binance Public Data** | Binance Spot Public API | **ONLINE (Verified)** | Bid: `80210.0` / Ask: `80210.01` | Fresh (< 800ms) | `crypto:binance:spot` |
| **C. Forex Indicative Data** | Static Registry & Yahoo Indicative | **ONLINE (Reference)** | Indicative spread (EURUSD 1.0 pip) | Static / End-of-day | `fx:indicative:registry` |
| **D. Simulated Strategy Data** | Local Quantitative Generator | **STANDALONE** | 1,440 continuous 1-min synthetic bars | Deterministic | `strategy:backtest:sim` |

---

## 2. Live Probe Output Evidence

Executed against backend services on staging:
```json
=== CRYPTO MARKET DATA (BINANCE PUBLIC) ===
{
  "symbol": "BTC",
  "pair": "BTC/USDT",
  "canonical_id": "crypto:binance:BTCUSDT",
  "exchange": "binance",
  "price": 80210.01,
  "bid": 80210.0,
  "ask": 80210.01,
  "spread": 0.01,
  "spread_bps": 0.0012,
  "change_24h": 3.12,
  "source": "crypto:binance:spot"
}

=== FOREX REGISTRY & SESSION INFO ===
{
  "session_id": "NEW_YORK",
  "current_session": "NEW YORK SESSION",
  "active_sessions": ["NEW YORK (Americas)"],
  "market_open": true,
  "next_major_boundary": "NY Rollover (21:00 UTC / 02:00 PKT)"
}
```

---

## 3. Stale Data & Circuit Breaker Enforcement

- `ExnessRiskGuard.max_stale_quote_ms`: Configured at `3,000 ms` (3.0 seconds).
- `FuturesRiskEngine.MAX_MARKET_DATA_AGE_MS`: Configured at `5,000 ms` (5.0 seconds).
- Any incoming trade request that cannot verify quote freshness within these parameters is automatically aborted by the risk guard.
- When Exness broker data is disconnected, the platform **strictly refuses** to disguise Binance or Indicative Forex quotes as genuine Exness broker quotes.
