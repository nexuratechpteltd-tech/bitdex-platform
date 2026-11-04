# BITDEX — BTCUSDT Strategy Configuration vs XAUUSDm Simulation

**Audit Date:** November 5, 2026  
**Subject:** Separation of BTCUSDT Perpetual Futures Specifications from XAUUSDm CFD Simulation  

---

## 1. Parameter & Specification Comparison Matrix

| Specification | BTCUSDT (Perpetual Futures) | XAUUSDm (Exness CFD) | Architectural Separation |
| :--- | :--- | :--- | :--- |
| **Asset Class** | Crypto Perpetual Futures (Binance/Bitget) | Commodity Metal CFD (Exness MT5) | Distinct backend engines |
| **Contract Size** | `1.0 BTC` | `100.0 oz Gold` | Explicitly parameterized |
| **Quote Unit** | USDT per BTC | USD per Troy Ounce | Distinct quote currencies |
| **Point Size** | `$1.00` | `$0.01` (1 cent) | Point size differs by $100\times$ |
| **Leverage Available** | Clamped to `5x` (Institutional ceiling) | Up to `200x` (Real) / `2000x` (Demo) | Separate risk clamp models |
| **Margin Requirement** | $\text{Notional} / \text{Leverage} = (0.01 \times 80,000) / 5 = \$160$ | $(0.01 \times 100 \times 2745) / 200 = \$13.72$ | Vastly different margin requirements |
| **Friction Model** | Maker: `0.02%`, Taker: `0.04%` (GTX post-only) | Bid/Ask spread (16 points = $0.16) | Exchange maker fee vs broker spread |
| **Holding Max** | `900s` (15 minutes) | `15 bars` (15 minutes on M1) | Evaluated per engine loop |
| **Stop Orders** | Exchange-confirmed conditional stop | MT5 broker-side protective stop | Native exchange stop vs MT5 bridge |

---

## 2. Integrity Evaluation

- **Code Isolation:** `saas_customer.py` routes manage `BTCUSDT` under `futures_strategy_configs` and `futures_accounts`. `exness_hft.py` routes manage `XAUUSDm` under `exness_demo_connections`.
- **Finding:** The calculation logic does not cross-pollinate contract sizes. However, having both in the same user interface caused significant cognitive confusion for operators.
- **Recommendation:** Full retirement of the synthetic XAUUSDm simulation panel from the frontend, leaving only the clean pair selection, checklist, and open trades monitor as requested.
