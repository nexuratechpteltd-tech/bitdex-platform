# BITDEX — Stage 6: First Controlled Forex Demo Preparation

## 1. Existing Position Risk Reconciliation
- **73604866 (`EURNZD` SELL `0.01`):** `entry=1.99242`, `sl=1.99886` -> est. SL risk `~$3.74`
- **74667980 (`AUDUSD` SELL `0.01`):** `entry=0.68053`, `sl=0.68436` -> exact SL risk `$3.83`
- **75087127 (`XAUUSD` BUY `0.01`):** `entry=3876.218`, `sl=3866.46` -> exact SL risk `$9.76`
- **Total Legacy SL Risk:** `~$17.33` (leaves `~$32.67` within a `$50.00` aggregate cap; `1` new `EURUSD` trade at `$10.00` keeps aggregate risk `~$27.33 <= $50.00`).

## 2. Authorization & Expiry Status
- **Current `experiment_lock.json`:** `authorized: True`, `expires_at_utc: 2026-11-18T18:52:03Z`, `expired: False`.
- **Note:** Existing authorization is **still active** (`not expired`). No new authorization or PM2 `#16` reload may proceed until explicit operator deactivation or expiry.

## 3. Legacy Concurrency & Revised Authorization Draft (Not Applied)
- Because `3` legacy positions (`EURNZD`, `AUDUSD`, `XAUUSD`) are open, `max_concurrent_positions` in `SharedCentralRiskManager.preflight_check()` (`len(open_positions) >= _max_pos`) will block new `EURUSD` entries unless set to `4` (`3` legacy + `1` new `EURUSD` position) or scoped to new `EURUSD` positions.
- **Draft `experiment_lock.json` (for separate approval):**
  - `account_id`: `"17000694512"`, `server`: `"dx.2.trial.raw"`
  - `authorized_strategies`: `["LT_STRUCTURE_EURUSD"]` (scalping & crypto remain blocked)
  - `max_risk_per_trade_usd`: `10.0`, `max_aggregate_loss_usd`: `50.0`, `max_concurrent_positions`: `4` (`3` legacy + `1` new `EURUSD`)

## 4. Controlled PM2 #16 Reload Plan & Safe Rollback
- **Stage 4 Source:** `shared_risk_manager.py` (SHA256: `646d83b29ea2e47ad2fd76e751d03e620f5d864d0871a9f0f38a440283d61fb5`)
- **Safe Rollback Target:** `shared_risk_manager.py.stage4_verified`
- **Reload Command (on separate approval):** `pm2 restart 16` (while keeping PM2 `#11` `online`).

## 5. Safety Confirmation
- No orders placed, `experiment_lock.json` unchanged, PM2 `#11` and `#16` untouched.
