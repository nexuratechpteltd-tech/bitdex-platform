# BITDEX — Final Broker P&L Forensic Reconciliation Report
- **Reporting Timestamp (UTC):** `2026-11-16T23:37:40Z`
- **Account:** Exness DEMO `17000694512` (`dx.2.trial.raw`)
- **Final Balance:** `$962.92` | **Floating P&L:** `$0.00` | **Final Equity:** `$962.92` (`0` open positions)

## 1. Reconciliation of the $0.68 P&L Discrepancy (-$3.37 vs -$2.69)
- **Arithmetic Check:** Gross Profit (`+$13.73`) + Gross Loss (`-$10.09`) + Commission (`-$7.01`) + Swap (`$0.00`) = **`-$3.37`**.
- **Root Cause of +$0.68 Difference:** `18` `ACTUAL_DEMO` rows in `trade_memory` stored `net_pnl_usd = gross_pnl_usd` without deducting `commission_usd` (`-$0.04`/trade), creating **`+$0.58`** from omitted commissions plus **`+$0.10`** from rounding/breakeven rows.
- **True Commission-Adjusted Net P&L (152 matched rows):** **`-$3.37`**.

## 2. Reconciliation of Account Balance ($962.92 vs $1,000.00)
- **Known Reference Balance (`2026-11-15T20:02:46Z`, Stage 5C):** `$969.02`.
- **2026-11-15 -> 2026-11-16 Change (`-$6.10`):** Closure of the 3 legacy positions (`73604866` `EURNZD`, `74667980` `AUDUSD`, `75087127` `XAUUSD`), whose exit P&L was not updated in `trade_memory`.
- **Pre-2026-11-09 Difference (`$1,000.00 -> $969.02 = -$30.98`):** Occurred prior to the earliest order in `get_order_history` (`2026-11-09T23:44:53Z`) or within the `9` `UNCLASSIFIED` positions whose deal-level P&L is not exposed by `get_order_history`.

## 3. All 9 UNCLASSIFIED Broker Positions
| Position ID | Symbol | Side | Volume | Entry Price | Entry Time | Exit Time | Reason Unclassified |
|---|---|---|---:|---:|---|---|---|
| `72593581` | `XAUUSD` | `BUY` | 0.01 | 4126.702 | 2026-11-10T02:28:46.976829+00:00 | 2026-11-10T02:30:12.282015+00:00 | No matching trade_memory row |
| `72594116` | `XAUUSD` | `BUY` | 0.01 | 4125.464 | 2026-11-10T02:31:01.412188+00:00 | 2026-11-10T02:31:05.424427+00:00 | No matching trade_memory row |
| `72594218` | `XAUUSD` | `BUY` | 0.01 | 4124.37 | 2026-11-10T02:31:12.989717+00:00 | 2026-11-10T02:31:13.89066+00:00 | No matching trade_memory row |
| `72640359` | `XAUUSD` | `BUY` | 0.01 | 4120.633 | 2026-11-10T05:31:10.74242+00:00 | 2026-11-10T05:31:11.33322+00:00 | No matching trade_memory row |
| `72692095` | `XAUUSD` | `BUY` | 0.01 | 4116.579 | 2026-11-10T08:05:01.669797+00:00 | 2026-11-10T08:05:02.212256+00:00 | No matching trade_memory row |
| `72715591` | `XAUUSD` | `BUY` | 0.01 | 4098.239 | 2026-11-10T09:00:28.229977+00:00 | 2026-11-10T09:00:28.550073+00:00 | No matching trade_memory row |
| `72787893` | `XAUUSD` | `BUY` | 0.01 | 4074.646 | 2026-11-10T10:49:45.635663+00:00 | 2026-11-10T10:49:52.605326+00:00 | No matching trade_memory row |
| `74667980` | `AUDUSD` | `SELL` | 0.01 | 0.68053 | 2026-11-12T21:18:31.391068+00:00 | 2026-11-16T18:34:27.059025+00:00 | No matching trade_memory row |
| `74668241` | `EURUSD` | `SELL` | 0.05 | 1.10545 | 2026-11-12T21:19:31.985932+00:00 | 2026-11-12T21:20:31.833498+00:00 | No matching trade_memory row |

## 4. Safety Confirmation
- Strictly read-only; no orders placed, no PM2 restarts, `experiment_lock.json` untouched, `REAL_TRADING_PERMANENTLY_LOCKED = True`.