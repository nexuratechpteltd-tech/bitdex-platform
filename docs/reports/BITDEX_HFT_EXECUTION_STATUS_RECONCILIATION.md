# BITDEX — HFT Execution Status & Frontend Label Reconciliation

**Audit Date:** November 5, 2026  
**Subject:** Comprehensive reconciliation of displayed UI badges versus real backend states.  

---

## 1. Status Disaggregation Table

| Displayed UI Badge | Actual Backend Reality | Source Component / Service | Accuracy Verdict |
| :--- | :--- | :--- | :--- |
| **`Exness: NOT CONNECTED`** | Verified: Zero active live broker sessions to Exness MT5 bridge. | `exness_hft.py` (`get_exness_status`) | **TRUE (ACCURATE)** |
| **`Binance Testnet API: Active LIVE profile linked`** | A Binance connection row exists in SQLite table `user_exchange_connections`, but its `environment` column contains `"LIVE"` while the label/checklist says `"Binance Testnet"`. | `saas_customer.py` (Line 2275) | **CONFUSING / MISMATCHED** |
| **`Simulated / Demo`** | Active adapter is `ExnessDeterministicMockAdapter`. All prices are simulated. | `exness_hft.py` | **TRUE (ACCURATE)** |
| **`LIVE FEED`** | Quotes for BTC/USDT come from Binance Spot public ticker. They are live crypto prices, but **NOT** Exness broker CFD quotes. | `market_data.py` | **PARTIALLY MISLEADING** |
| **`Emergency Lock Active`** | `live_trading_locked = True` and `read_only_mode = True` in `config.py`. | `config.py` & `risk_guard.py` | **TRUE (ACCURATE)** |
| **`Circuit Breaker: Disarmed`** | Local dynamic account drawdown kill-switch has not tripped. Distinct from top-level `live_trading_locked`. | `futures_accounts.kill_switch_active` | **TRUE (ACCURATE)** |
| **`Controlled Validation Mode`** | Frontend string label indicating mainnet orders are locked while testnet validation runs. | `saas_customer.py` (Checklist item) | **FRONTEND LABEL ONLY** |

---

## 2. Binance Testnet vs Live Endpoint Verification
- **Audit Finding:** In `saas_customer.py`, testnet endpoints point to `https://testnet.binancefuture.com`.
- In `user_exchange_connections`, connection `CONN-BIN-LIVE-MIGRATED` holds credentials for Binance Spot read-only public market data (`https://api.binance.com`).
- Live trading execution on Binance is permanently disabled by `live_trading_locked = True`.
