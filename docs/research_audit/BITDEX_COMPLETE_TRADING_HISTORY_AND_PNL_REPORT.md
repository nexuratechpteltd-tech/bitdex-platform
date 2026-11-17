# BITDEX — Complete Trading History & P&L Report (Broker-Reconciled)

- **Reporting Timestamp (UTC):** `2026-11-16T23:37:40Z`
- **Broker Account:** Exness DEMO `17000694512` (`dx.2.trial.raw`)
- **Balance:** `$962.92` | **Equity:** `$962.92` | **Open Positions:** `0` | **Floating P&L:** `$0.00`

## 1. Overall Realized Performance
- **Total Broker Positions (`get_order_history`):** `161` closed positions (`348` filled order events, `0` currently open)
- **Reconciled with `ACTUAL_DEMO` Trade Memory:** `152` reconciled | `9` `UNCLASSIFIED` / unreconciled
- **Wins / Losses (152 Reconciled):** `18` wins / `128` losses / `6` breakeven (Win Rate `11.84%`)
- **Gross Profit:** `$13.73` | **Gross Loss:** `-$10.09`
- **Commission:** `-$7.01` | **Swap:** `$0.00`
- **Net Realized P&L (152 Reconciled):** `-$2.69` | **Gross Profit Factor:** `1.36`

## 2. Strategy Breakdown
| Strategy | Total | Reconciled | Wins | Losses | Win Rate | Gross Profit | Gross Loss | Commission | Net P&L | PF |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `LONG_TERM` | 17 | 17 | 5 | 7 | 29.41% | $7.92 | -$4.29 | -$0.91 | $2.72 | 1.85 |
| `SCALPING` | 135 | 135 | 13 | 121 | 9.63% | $5.81 | -$5.80 | -$6.10 | -$5.41 | 1.00 |
| `UNCLASSIFIED` | 9 | 0 | 0 | 0 | 0.00% | $0.00 | $0.00 | $0.00 | UNRECONCILED | 0.00 |

## 3. Instrument Breakdown
| Instrument | Total | Reconciled | Wins | Losses | Win Rate | Gross Profit | Gross Loss | Commission | Net P&L | PF |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `AUDUSD` | 5 | 4 | 2 | 2 | 50.00% | $6.47 | -$0.12 | -$0.25 | $6.10 | 53.92 |
| `BTCUSD` | 7 | 7 | 4 | 3 | 57.14% | $0.95 | -$1.08 | -$0.28 | -$0.21 | 0.88 |
| `EURJPY` | 1 | 1 | 0 | 1 | 0.00% | $0.00 | -$0.21 | -$0.07 | -$0.28 | 0.00 |
| `EURNZD` | 2 | 2 | 1 | 1 | 50.00% | $0.37 | $0.00 | -$0.12 | $0.25 | 999.00 |
| `EURUSD` | 13 | 12 | 1 | 10 | 8.33% | $0.02 | -$0.13 | -$0.55 | -$0.54 | 0.15 |
| `GBPAUD` | 1 | 1 | 1 | 0 | 100.00% | $0.96 | $0.00 | -$0.07 | $0.89 | 999.00 |
| `GBPCAD` | 3 | 3 | 1 | 2 | 33.33% | $0.08 | -$4.18 | -$0.40 | -$4.50 | 0.02 |
| `GBPUSD` | 5 | 5 | 1 | 4 | 20.00% | $0.05 | -$0.18 | -$0.22 | -$0.23 | 0.28 |
| `NZDUSD` | 1 | 1 | 0 | 1 | 0.00% | $0.00 | -$0.32 | -$0.14 | -$0.46 | 0.00 |
| `USDCAD` | 3 | 3 | 0 | 3 | 0.00% | $0.01 | -$0.24 | -$0.35 | -$0.58 | 0.04 |
| `USDCHF` | 4 | 4 | 3 | 1 | 75.00% | $1.70 | $0.00 | -$0.28 | $1.42 | 999.00 |
| `USDJPY` | 2 | 2 | 1 | 1 | 50.00% | $0.96 | -$0.15 | -$0.20 | $0.61 | 6.40 |
| `XAGUSD` | 2 | 2 | 1 | 1 | 50.00% | $0.85 | -$1.65 | -$0.08 | -$0.80 | 0.52 |
| `XAUUSD` | 112 | 105 | 2 | 98 | 1.90% | $1.31 | -$1.83 | -$4.00 | -$4.36 | 0.72 |

## 4. Complete Individual Trade List
See `/opt/bitdex-research-v2/docs/bitdex_complete_trades.csv` for all `161` individual broker positions with `position_id`, `entry_order_id`, `exit_order_id`, `symbol`, `side`, `strategy`, `status`, `volume`, `entry_price`, `exit_price`, `entry_time`, `exit_time`, `gross_pnl`, `commission`, `swap`, and `net_pnl`.
