# BITDEX — Stage 5C: Final Position Reconciliation Report

- **Snapshot UTC:** `2026-11-15T20:02:46Z`
- **Account:** Exness DEMO `17000694512` (`dx.2.trial.raw`) | Balance `$969.02` | Equity `$976.95`

## 1. Open Positions (3) & Pending Orders (0)
| Ticket | Instrument | Side | Volume | Entry | SL | TP | Supervised By |
|---|---|---|---|---|---|---|---|
| `73604866` | `EURNZD` | `SELL` | `0.01` | `1.99242` | `1.99886` | `1.9771` | PM2 `#11` (`online`) |
| `74667980` | `AUDUSD` | `SELL` | `0.01` | `0.68053` | `0.68436` | `0.67332` | PM2 `#11` (`online`) |
| `75087127` | `XAUUSD` | `BUY` | `0.01` | `3876.218` | `3866.46` | `3901.46` | PM2 `#11` (`online`) |

- **Pending Orders:** `0`

## 2. Experiment Authorization & Process Health
- `experiment_lock.json`: `authorized: true`, `account_id: 17000694512`, `authorized_strategies: ["LT_STRUCTURE_EURUSD"]`, `expires_at_utc: 2026-11-18T18:52:03Z` (not expired).
- PM2 `#11`: `online` (`PID 3271427`); PM2 `#16`: `online` (`PID 46520`, `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py`).
- Stage 4 `shared_risk_manager.py` SHA256: `646d83b29ea2e47ad2fd76e751d03e620f5d864d0871a9f0f38a440283d61fb5`
- Safe Stage 4 Rollback Target: `shared_risk_manager.py.stage4_verified` (never revert to pre-Stage 4 backup).

## 3. Reload Decision: **BLOCKED**
Reload remains **BLOCKED** because `experiment_lock.json` authorization is still active (`expires_at_utc: 2026-11-18T18:52:03Z`). No services were restarted or modified.
