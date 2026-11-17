# BITDEX — Stage 10: Complete Exness Account Ledger Reconstruction

- **Account:** Exness DEMO `17000694512` (`dx.2.trial.raw`)
- **Authoritative Source:** Exness `GET /v1/history/accounts/17000694512/deals` (`298` deals, `149` positions)
- **Ledger CSV:** `/opt/bitdex-research-v2/docs/BITDEX_STAGE_10_COMPLETE_TRADE_LEDGER.csv` (SHA256: `28ca3d240cb37ab20e5843a14244a2271b94552ea605595a623c736c10d3a9ef`)

## 1. Account-Level Balance Reconciliation
- **Starting Deposit (`deal_id 149053551`, `2026-11-09T23:11:53Z`):** `+$1,000.00`
- **Lifetime Gross P&L (captured deals):** `$-20.62`
- **Lifetime Commission (captured deals):** `$-10.63`
- **Lifetime Net P&L (captured deals):** `$-31.25`
- **Reconstructed Balance:** `$968.75`
- **Actual Broker Balance (`0` open, `$0.00` floating):** `$962.92`
- **Remaining Unexplained Difference:** `$-5.83` (attributable to `12` scalping positions inside a `>100`-deal 4h slice on `2026-11-10` and multi-day swaps not itemized in `/deals`).

## 2. Legacy 3 Position Closures (Exact Deal Records)
1. **`73604866` (`EURNZD` `SELL` `0.01`):** `entry_deal=151238328` (`1.99242`, `2026-11-11T14:55:38Z`) -> `exit_deal=157193325` (`1.99886`, `2026-11-16T14:41:01Z`, SL hit) | `gross=-$3.55`, `comm=-$0.07`, **`net=-$3.62`**
2. **`74667980` (`AUDUSD` `SELL` `0.01`):** `entry_deal=153369544` (`0.68053`, `2026-11-12T21:18:31Z`) -> `exit_deal=157587124` (`0.67332`, `2026-11-16T18:34:27Z`, TP hit) | `gross=+$7.21`, `comm=-$0.05`, **`net=+$7.16`**
3. **`75087127` (`XAUUSD` `BUY` `0.01`):** `entry_deal=154232921` (`3876.218`, `2026-11-13T13:51:39Z`) -> `exit_deal=156333767` (`3866.46`, `2026-11-16T01:03:23Z`, SL hit) | `gross=-$9.76`, `comm=-$0.07`, **`net=-$9.83`**

## 3. Strategy Breakdown (Authoritative Exness Deal Ledger)
| Strategy | Trades | Wins | Losses | Gross Profit | Gross Loss | Commission | Net P&L | PF |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `LONG_TERM` | 17 | 6 | 11 | $31.71 | $-51.78 | $-1.37 | $-21.44 | 0.61 |
| `SCALPING` | 124 | 38 | 86 | $38.33 | $-44.99 | $-8.54 | $-15.2 | 0.85 |
| `UNCLASSIFIED` | 8 | 3 | 5 | $8.68 | $-2.57 | $-0.72 | $5.39 | 3.38 |

## 4. Safety Confirmation
- Strictly read-only; no orders placed, no PM2 restarts, `experiment_lock.json` untouched, `REAL_TRADING_PERMANENTLY_LOCKED = True`.
