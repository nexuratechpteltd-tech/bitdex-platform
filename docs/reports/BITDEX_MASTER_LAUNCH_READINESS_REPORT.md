# BITDEX — Existing VPS / Gateway / Exness Verification (Consolidated Evidence Report)

**Branch:** `feature/hft-redesign-and-navigation-cleanup` · **Baseline HEAD:** `ea37c886f225b2531d93689b95e369c14881ffed` · **Date:** 2026-11-05
**Legend:** PASSED = genuinely executed · FAILED · BLOCKED = missing external dependency · NOT TESTED

> **Headline: The Windows VPS / WireGuard / MT5 gateway could NOT be verified. No evidence of it exists from the Linux staging host.** Launch readiness: **NOT READY.**

## 1. Windows VPS & WireGuard (Phases 1–2)

| Check | Result | Evidence (executed from 169.58.218.168) |
|---|---|---|
| `wg` binary installed | **FAILED** | `wg: command not found` |
| `wg0` interface | **FAILED** | `Device "wg0" does not exist` |
| `/etc/wireguard/*.conf` | **FAILED** | directory does not exist |
| Ping 10.88.0.2 | **FAILED** | 2 sent / 0 received (100% loss) |
| `http://10.88.0.2:8001/health` | **FAILED** | unreachable (3s timeout) |
| `http://127.0.0.1:8095/health` (configured gateway URL) | **FAILED** | unreachable; nothing listens on 8095 |
| Windows VPS credentials / RDP / WinRM config in project | **BLOCKED** | none found in repo, `.env`, `~/.ssh/config`; I cannot log in to the Windows host |
| Windows version, MT5 terminal, Python, firewall, service state | **NOT TESTED** | requires Windows host access |
| Heartbeat / authenticated gateway call | **BLOCKED** | no reachable gateway |
| Token rotation / revoked-token rejection | **PASSED (unit-level only)** | `test_phase4_4_connectivity.py` tests 2–4 run the gateway code locally in-process (`MetaTrader5 library not found. Running in mock/testing environment`); this is NOT the Windows VPS |

**Discrepancies found**
- Command states gateway at `10.88.0.2:8001`; backend config is `EXNESS_MT5_GATEWAY_URL=http://127.0.0.1:8095`; Phase 4.4 report says 8095. Port 8001 on the Linux host is a different, local legacy uvicorn.
- Phase 4.4 test #5 "WireGuard & Firewall Isolation: PASSED" is a **code/config check only**; no tunnel exists on this host. That label overstated reality.
- The VPS is "reportedly already running", but nothing from Linux can reach it. Either the tunnel was never configured on the Linux side, or the Windows side is down/firewalled.

## 2. Genuine Exness MT5 (Phase 3) — **BLOCKED**
No terminal responses were obtainable. Therefore **no genuine** balance, equity, free margin, bid/ask, server identity or leverage exists for Demo or Real (460310009).

**Defect/risk findings (database inspection, secrets redacted):**
- `exness_demo_connections` holds 81 rows; most Demo rows have `adapter_mode=DETERMINISTIC_MOCK_DEMO` with `balance_usd=5000.0` — **simulated values, not broker data**.
- Admin Real `460310009` is stored with `balance_usd=0.0, equity_usd=0.0` and `last_reconciled_at=NULL`: **never reconciled with a broker**. These 0.0 values must not be read as genuine.
- `POST /hft/exness/demo/connect` defaults `use_mock=True` (risk of accidental mock connection; mock responses correctly report `broker_authenticated:false, is_mock:true`).
- Test data pollution: many synthetic test customers/accounts remain in the staging DB (cleanup recommended).

## 3. Exness Trader API (Phase 4) — **BLOCKED**
Ed25519/EdDSA signing code verified only by unit tests (`test_phase4_5_trader_payments.py`: 11 PASSED / 1 BLOCKED). No genuine customer API key exists, so REST auth, WebSocket streaming, reconnection and revoked-key behavior against Exness are **NOT verified**. Official-doc compatibility was not re-fetched in this run (**NOT TESTED**).

## 4. Market Data (Phase 5)
| Source class | Result |
|---|---|
| A. Exness-authenticated broker quotes | **BLOCKED** — none available |
| B. Binance public | **PASSED** — live call: BTC/USDT bid 80210.0 / ask 80210.01, source `crypto:binance:spot`, public (not a customer broker quote) |
| C. Forex indicative (Yahoo-style) | **PASSED (instrument registry/session only)** — session NEW_YORK, market_open true; spreads in registry (e.g. EURUSD 1.0 pip) are **static assumptions**, not live quotes. A live price fetch was not completed (method `fetch_price` does not exist on the provider; my probe errored) |
| D. Simulated strategy data | present in backtests only |

Stale-data limits: `ExnessRiskGuard.max_stale_quote_ms=3000`, `FuturesRiskEngine.MAX_MARKET_DATA_AGE_MS=5000`. Earlier suite `test_phase3_2_dual_ai.py` shows **FAIL: stale evidence still `eligible_for_ai=True`** (pre-existing, not fixed in this run) — stale-feed gating for strategies is therefore **not fully proven**. WebSocket reconnection / duplicate handling: **NOT TESTED**.

## 5. Customer connectivity (Phase 6)
`test_phase4_6_customer_acceptance.py`: **12 PASSED / 0 FAILED** (staging integration against local backend, mock adapter): masking, AES-256-GCM ciphertext+nonce at rest, disconnect wipes credentials, cross-tenant 404, admin non-leakage, session revocation. These prove isolation logic, **not** genuine broker connections.

## 6. Strategy validation (Phase 7)
`test_phase5_quantitative_validation.py`: **12 PASSED** — but on **synthetic** 1,440 bars (not broker data). OOS: 64.0% win rate, +$17.70; walk-forward 3/3 windows positive; Monte Carlo 99% VaR max DD 22.8%. These are simulation results, **not evidence of future returns**; swap assumptions and real Exness commission/spread were not validated against broker data.

## 7. Execution safety (Phase 8)
Locks (`live_trading_locked`, `read_only_mode`, `emergency_lock_active`) verified `True`; unchanged. **Zero broker orders placed (Demo or Real).**
Fixes applied this session in `backend/app/routes/exness_hft.py`:
1. `TradeExecutionRequest` now accepts `trade_mode`/`quantity`/`account_id` aliases (previously a REAL order using these fields got HTTP **422** — Phase 6 test 12 failed). 
2. **DEMO order path previously returned `FILLED` with hardcoded fabricated fill prices (e.g. 2745.50 / 78500.0) even with locks enabled.** It now returns `BLOCKED_BY_SAFETY_LOCK` (`barrier: READ_ONLY_MODE`) while locks are on.
Caveat: Phase 6 test 12 now passes because the unactivated test customer is blocked by the `$20` activation gate (403) before reaching the lock; the REAL lock itself is separately proven by Phase 4.4 test 7 (`BLOCKED_BY_SAFETY_LOCK`, HTTP 200 body, no order submitted).
Regression side-effect: older suites `test_phase4_1_acceptance.py` (tests 2, 8, 9, 10) and `test_phase4_dual_exness_execution.py` (test 6) now **FAIL** because their customers lack `$20` activation (403) and/or expect a simulated Demo fill. These tests need updating; they were not modified here.

## 8. Payment / $20 activation (Phase 9)
`test_phase6_activation_security.py`: **16 PASSED** (amount, currency, HMAC, cross-tenant, idempotency, revocation, RBAC). DB shows provider label `BINANCE_PAY` on activations, but these were **internally signed test payments**. No genuine merchant is connected/settled → **BLOCKED**: real provider credentials, sandbox vs live config unverified. 5 test rows are `ACTIVE` in staging DB from tests (no real charge).

## 9. Test summary (this run)
| Suite | Type | Result |
|---|---|---|
| phase4_4_connectivity | local/mock integration | 11 P / 1 BLOCKED / 0 F |
| phase4_5_trader_payments | unit/mock | 11 P / 1 BLOCKED |
| phase4_6_customer_acceptance | staging integration (mock adapter) | 12 P |
| phase5_quantitative_validation | simulation | 12 P |
| phase6_launch_audit | staging integration | 12 P (after fix; was 11 P / 1 F) |
| phase6_activation_security | staging integration | 16 P |
| phase4_1_acceptance, phase4_dual_exness_execution | legacy | **FAILED** (see §7) |
| phase3_2_dual_ai | legacy | **FAILED** stale-evidence test |

## 10. Outstanding blockers (exact)
1. Linux side WireGuard not installed/configured (no `wg0`, no config); Windows peer unreachable (100% loss).
2. Windows host access (RDP/WinRM credentials or an operator running the audit there) to inspect terminal, service, firewall.
3. Gateway URL inconsistency (`127.0.0.1:8095` vs `10.88.0.2:8001`).
4. Genuine Exness Demo + Real login via MT5 terminal; Trader API key/permissions.
5. Payment merchant credentials/sandbox.
6. Fix stale-evidence gating (`test_phase3_2_dual_ai` test 4) and update legacy tests.

## 11. Decision
**NOT LAUNCH READY. Staging remains safe (all locks on, zero orders).** No external-service verification (Windows VPS, MT5, Exness API, payment merchant) succeeded in this run.
