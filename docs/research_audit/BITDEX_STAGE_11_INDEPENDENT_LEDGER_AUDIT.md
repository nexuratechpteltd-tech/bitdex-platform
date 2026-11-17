# BITDEX — Stage 11: Independent Ledger Verification & Strategy Performance Audit

- **Account:** Exness DEMO `17000694512` (`dx.2.trial.raw`)
- **Authoritative Source:** Exness `GET /v1/history/accounts/17000694512/deals` (adaptive bisection: `323` deals across `161` positions + `1` deposit)
- **Ledger CSV:** `/opt/bitdex-research-v2/docs/BITDEX_STAGE_11_VERIFIED_POSITION_LEDGER.csv` (SHA256: `1cc7359f1ced77ecb0cb5f6794ff683a23085fd02871b7aa89fb9d78533c1ec3`)

## 1. Exact Account Balance Reconciliation (`$0.00` Difference)
- **Starting Deposit (`deal_id 149053551`):** `+$1,000.00`
- **Lifetime Net P&L (`161` positions):** `$-37.08`
- **Reconstructed Balance:** `$962.92`
- **Actual Broker Balance / Equity (`0` open):** `$962.92`
- **Unexplained Difference:** **`$0.0`**

## 2. Independent Strategy Performance (Broker Deal Ledger)
| Strategy | Trades | Wins | Losses | WR% | Gross Profit | Gross Loss | Commission | Net P&L | PF | Avg Win | Avg Loss | Max Consec L | Max DD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `LONG_TERM` | 17 | 6 | 11 | 35.29% | $31.71 | $-51.78 | $-1.37 | $-21.44 | 0.61 | $5.21 | $-4.79 | 4 | $39.55 |
| `SCALPING` | 135 | 41 | 94 | 30.37% | $41.04 | $-51.38 | $-9.29 | $-19.63 | 0.8 | $0.93 | $-0.62 | 14 | $19.77 |
| `UNCLASSIFIED` | 9 | 3 | 6 | 33.33% | $8.68 | $-3.9 | $-0.79 | $3.99 | 2.23 | $2.83 | $-0.75 | 4 | $4.04 |

## 3. Historical Strategy Decisions
- **`SCALPING` (Track 1):** **RETIRED** (`135` trades, `-$19.63` net P&L, PF `0.80`, `14` max consecutive losses).
- **`LONG_TERM` (Legacy multi-pair run):** **RESEARCH ONLY / ELIGIBLE FOR ISOLATED VALIDATION ONLY** (`17` trades, `-$21.44` net P&L, PF `0.61`, `$39.55` max DD; requires strict `LT_STRUCTURE_EURUSD`-only isolation if re-tested).
- **`UNCLASSIFIED` (`9` trades):** Remain **UNCLASSIFIED** (`+$3.99` net P&L).

## 4. Safety Confirmation
- Strictly read-only; no orders placed, no PM2 restarts, `experiment_lock.json` untouched, `REAL_TRADING_PERMANENTLY_LOCKED = True`.
