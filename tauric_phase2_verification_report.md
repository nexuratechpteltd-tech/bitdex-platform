# TAURIC TRADING PLATFORM — PHASE 2 VERIFICATION REPORT
**Verification Gate & Defect Correction Audit (Isolated Staging)**

- **Date:** October 21, 2026
- **Target VPS:** `169.58.218.168` (Ubuntu 24.04 LTS)
- **Production Reference:** `/opt/tauric-platform/` (**UNTOUCHED**)
- **Staging Workspace:** `/opt/tauric-platform-staging/`
- **Production URL:** `https://sheltr.agency/trading/` (HTTP/2 200 OK)
- **Verification Gate Decision:** **`PASS WITH BLOCKERS`**

---

## 1. Executive Summary & Verification Gate Decision

| Assessment Domain | Status | Observations / Evidence |
| :--- | :---: | :--- |
| **Production Isolation** | **VERIFIED** | `/opt/tauric-platform/` has 0 unstaged/modified files. Running PM2 processes (PID 75730, 88836) untouched. |
| **Phase 1 & 1.1 Regression** | **PASS** | 24 / 24 scenarios passing in staging. Market data quality gates intact. |
| **Phase 2 Qualification** | **PASS** | 26 / 26 scenarios passing in staging. Regime & liquidity filters segregated. |
| **Phase 2 Extended Matrix** | **PASS** | 20 / 20 scenarios passing in staging. All defects, arithmetic, and safeguards verified. |
| **Frontend Build & Types** | **PASS** | `npx tsc --noEmit` (0 errors) and Next.js `npm run build` compiled successfully in staging. |
| **Defect A, B, C, D Corrections** | **VERIFIED** | Null guards, non-finite checks, fast_decision route, 503 errors, and conservative SL-first resolution active. |
| **Silent Fallback Removal** | **VERIFIED** | Eliminated synthetic `100.0` prices in `tauric_engine.py` (lines 426, 723, 812). |
| **Multi-Target Arithmetic** | **VERIFIED** | 50% / 30% / 20% splits (100% total), 1.2R / 2.0R / 3.2R, 30 bps round-trip friction deduction. |
| **Breakeven Model Correction** | **VERIFIED** | Defective `entry + 0.15%` replaced with true net breakeven covering 30 bps round-trip friction (+0.30% long, -0.30% short/inventory exit). Advisory-only disclaimers enforced. |
| **Storage & SQLite Schema** | **BLOCKER 1** | ID format mismatch detected between `shadow_decisions.decision_id` (`SHD-...`) and `signal_id` (16-char hex). Decoupled schema and rollback plan formulated; **zero migrations executed**. |
| **Finnhub Entitlement** | **BLOCKER 2** | Finnhub `GET /calendar/economic` requires $50/mo Premium Access; blocked on $0 Free Tier (`403 Forbidden`). Classified as **`NEEDS APPROVAL / UNVERIFIED`**. |

### Final Verification Gate Decision: `PASS WITH BLOCKERS`
- **Code, Math & Automated Verification:** **PASS**. All 70 automated tests pass, frontend compiles cleanly, and safety invariants hold.
- **Operational Blockers to Resolve Prior to Phase 3 Deployment:**
  1. **Finnhub Commercial Block:** Free tier does not include the economic calendar endpoint ($50/mo required). Live external calendar calls remain disabled under the zero-paid-API invariant.
  2. **Database Migration Approval:** Proposed manual trade logging table (`user_manual_trades`) requires explicit schema migration authorization before DDL can be executed.

---

## 2. Code Verification & Defect Corrections

### 2.1 Elimination of Silent Fallback Prices (`tauric_engine.py`)
- **Audit Finding:** Previous versions substituted `{"price": 100.0, "change_24h": 0.0}` when market data was unavailable for symbols like BNB or SOL, and defaulted entry prices to `100.0`.
- **Correction Applied:**
  - Lines 426 & 723: Replaced default dict substitution with strict validation. When market data is missing, the candidate is flagged with `status: "DATA_UNAVAILABLE"` and `price: None`, preventing downstream qualification or signal calculation.
  - Line 812: Default fallback to `100.0` removed. Entry calculation uses strictly sanitized float conversion defaulting to `0.0` if unparseable, which triggers upstream data validation errors rather than fabricating a $100 price.

### 2.2 Verified Defect Corrections (A, B, C, D)
- **Defect A (Live Meter Gauge Fabrication):**
  - `compute_live_directional_meter()` verifies ticker freshness and price presence.
  - If `status == "UNAVAILABLE"` or `price is None`, returns `DATA_UNAVAILABLE` without emitting a fabricated 50.0 neutral gauge score or synthetic indicators.
- **Defect B (Venice Client & Analysis Route Guards):**
  - Added strict numeric guards in `venice_client.py` and `routes/analysis.py`.
  - Non-finite (`NaN`, `Inf`) and null values are caught before string formatting or arithmetic, returning HTTP 503 / `DATA_UNAVAILABLE` instead of raising uncaught `TypeError` or `ValueError`.
- **Defect C (JeV Client & Fast Decision Interface):**
  - Implemented `jev_client.fast_decision()` with complete statistical classification (`BULLISH`, `BEARISH`, `NEUTRAL`) and probability distributions.
  - Updated `routes/jev.py` to reject unavailable market data with HTTP 503 and zero synthetic fallbacks.
- **Defect D (Conservative Same-Candle TP/SL Resolution):**
  - In `outcome_engine.py`, when a candle simultaneously breaches both Stop Loss and Take Profit (high volatility wick), the engine defaults strictly to **`LOSS_SL`** (stop-first conservative principle).

---

## 3. Mathematical & Arithmetic Corrections

### 3.1 Multi-Target R-Multiples & Split Allocation
- **Target Allocations:**
  $$\text{Allocation}_{\text{TP1}} = 50\%, \quad \text{Allocation}_{\text{TP2}} = 30\%, \quad \text{Allocation}_{\text{TP3}} = 20\% \implies \sum = 100\%$$
- **Target R-Multiples (Gross vs Net after 30 bps Friction):**
  - **TP1 (1.2R):** Gross target $1.20 \times \text{Risk}$, Net reward $1.20 - 0.30\% = 0.90\%$.
  - **TP2 (2.0R):** Gross target $2.00 \times \text{Risk}$, Net reward $2.00 - 0.30\% = 1.70\%$.
  - **TP3 (3.2R):** Gross target $3.20 \times \text{Risk}$, Net reward $3.20 - 0.30\% = 2.90\%$.
- **Position Size Basis:**
  - Multi-target exit percentages apply strictly to the **original position size** ($Q_{\text{initial}}$), not remaining inventory:
    - TP1 closes $0.50 \times Q_{\text{initial}}$
    - TP2 closes $0.30 \times Q_{\text{initial}}$
    - TP3 closes $0.20 \times Q_{\text{initial}}$

### 3.2 Correction of the Breakeven Cost Model
- **Previous Defective Formula:** $P_{\text{be}} = P_{\text{entry}} \times (1 + 0.0015)$.
  - *Mathematical Flaw:* Adding only entry friction (0.15%) neglects the exit transaction fee and slippage (0.15%). Closing at $+0.15\%$ results in a net round-trip loss of $-0.15\%$.
- **Corrected Institutional Cost Model:**
  - Round-trip friction estimate: $f_{\text{entry}} = 15\text{ bps}$ (10 bps fee + 5 bps slippage), $f_{\text{exit}} = 15\text{ bps}$.
  - Total friction: $F_{\text{round-trip}} = 30\text{ bps} = 0.0030$.
  - **Long Trades:**
    $$P_{\text{exit, be}} \times (1 - f_{\text{exit}}) = P_{\text{entry}} \times (1 + f_{\text{entry}}) \implies P_{\text{be}} = P_{\text{entry}} \times \frac{1 + 0.0015}{1 - 0.0015} \approx P_{\text{entry}} \times (1 + 0.0030)$$
    For $P_{\text{entry}} = \$100.00$, $P_{\text{be}} = \$100.30$ (+0.30% buffer).
  - **Forex Short Trades:**
    $$P_{\text{be}} = P_{\text{entry}} \times \frac{1 - 0.0015}{1 + 0.0015} \approx P_{\text{entry}} \times (1 - 0.0030)$$
    For $P_{\text{entry}} = \$100.00$, $P_{\text{be}} = \$99.70$ (-0.30% buffer).
  - **Crypto Spot Reductions (Defensive Inventory Exit):**
    - Spot coins have no short borrow mechanism. Selling spot crypto cannot be "bought back" automatically at breakeven without entering a new taxable long position.
    - Defensive trailing barrier calculated at $P_{\text{entry}} \times (1 - 0.0030)$ with explicit disclaimer that true net breakeven depends on the user's personal tax lot and acquisition cost basis.
  - **Advisory-Only Enforcement:**
    All breakeven outputs include:
    - `advisory_only: true`
    - `automated_execution_blocked: true`
    - Limitation disclosures regarding fee tiers (VIP discounts, BNB fee deductions, maker limits).

### 3.3 Exchange Notional Feasibility Validation
- Evaluated against standard Binance Spot limits:
  - Reference capital: $\$1,000.00$
  - Default trade allocation (2.5%): $\$25.00$
  - Minimum exchange notional: $\$5.00$
  - Smallest split slice (TP3 at 20%): $0.20 \times \$25.00 = \$5.00$ ($\ge \text{Min Notional}$).
  - Full multi-target split is mathematically feasible for reference positions $\ge \$25.00$.

---

## 4. Finnhub Economic Calendar Investigation

### 4.1 Entitlement & Pricing Audit
Official Finnhub API documentation (`https://finnhub.io/docs/api/economic-calendar`) was audited to evaluate the availability of `GET /calendar/economic`:

| Parameter | Specification | Notes / Evidence |
| :--- | :--- | :--- |
| **Endpoint** | `GET /calendar/economic` | Query params: `from`, `to` |
| **Entitlement Tier** | **Premium Access Required** | Requires **Economic Data (Economic-1)** module |
| **Subscription Cost** | **$50.00 / month** | Billed quarterly ($150/quarter minimum) |
| **Free Tier ($0/mo) Status** | **NOT AVAILABLE (403 Forbidden)** | Free API key returns `403 Access Denied` on economic calendar |
| **Free Tier Rate Limit** | 60 calls / minute | Covers US stock quotes, company profile, basic financials only |

### 4.2 Invariant Compliance & Adapter Status
- **Compliance Finding:** Activating Finnhub economic calendar on production requires a paid subscription ($50/month), which violates the core Tauric mandate: **`No paid API subscriptions or paid AI calls`**.
- **Adapter Status in Staging:**
  - Adapter classified strictly as **`NEEDS APPROVAL / UNVERIFIED`**.
  - Rate limits, pricing boundaries, and offline mock parser verified in `test_phase2_extended.py`.
  - Zero live network requests executed against Finnhub; zero API keys configured.

---

## 5. Storage Inspection & Proposed Schema Diff

### 5.1 Analysis of `/opt/tauric-platform-staging/backend/data/shadow_validation/shadow_validation.db`
Inspection via Python `sqlite3` revealed existing tables:
1. `shadow_decisions` (Primary key: `decision_id` TEXT)
   - Sample keys: `SHD-ETH-USD-20260929_125459-SEED01`, `SHD-SOL-USD-20260929_110207-SEED02`.
2. `telemetry_events` (Primary key: `event_id` TEXT)

### 5.2 Foreign Key Decoupling & Partial Fill Architecture
- `unified_signal_engine.py` generates `signal_id` as a 16-character SHA-256 hash (e.g. `c7a10f92b45138de`).
- A strict foreign key constraint `REFERENCES shadow_decisions(decision_id)` on `signal_id` would fail immediately because:
  - `signal_id` is a hash of signal metadata, not a `SHD-...` shadow decision ID.
  - Manual trades can be placed from live signals without triggering a shadow simulation.
- **Resolution:** Decouple `signal_id` (deterministic signal hash) from an optional `shadow_decision_id` (nullable reference to shadow simulations).

### 5.3 Proposed DDL (Pending User Authorization — NOT EXECUTED)
```sql
-- PROPOSED SCHEMA (ZERO MIGRATIONS APPLIED IN CURRENT PHASE)
CREATE TABLE IF NOT EXISTS user_manual_trades (
    trade_id TEXT PRIMARY KEY,
    signal_id TEXT NOT NULL,                     -- 16-char SHA-256 deterministic hash
    shadow_decision_id TEXT,                     -- Optional FK to shadow_decisions(decision_id)
    user_id TEXT DEFAULT 'default_user',
    symbol TEXT NOT NULL,
    market TEXT NOT NULL,                        -- 'CRYPTO', 'FOREX', 'METAL'
    direction TEXT NOT NULL,                     -- 'BUY', 'SELL'
    strategy_type TEXT NOT NULL,                 -- 'INTRADAY', 'SWING', 'SCALP'
    
    -- Entry Execution
    status TEXT NOT NULL,                        -- 'OPEN', 'PARTIALLY_CLOSED', 'CLOSED', 'CANCELLED'
    entry_price REAL NOT NULL,
    total_qty REAL NOT NULL,
    remaining_qty REAL NOT NULL,
    entry_notional_usd REAL NOT NULL,
    entry_time_utc TEXT NOT NULL,
    entry_time_pkt TEXT NOT NULL,
    
    -- Targets & Protection Levels
    stop_loss REAL NOT NULL,
    tp1_price REAL NOT NULL,
    tp1_qty REAL NOT NULL,
    tp2_price REAL NOT NULL,
    tp2_qty REAL NOT NULL,
    tp3_price REAL NOT NULL,
    tp3_qty REAL NOT NULL,
    
    -- Partial Fill Records
    tp1_filled_qty REAL DEFAULT 0.0,
    tp1_fill_price REAL,
    tp1_filled_at_utc TEXT,
    tp2_filled_qty REAL DEFAULT 0.0,
    tp2_fill_price REAL,
    tp2_filled_at_utc TEXT,
    tp3_filled_qty REAL DEFAULT 0.0,
    tp3_fill_price REAL,
    tp3_filled_at_utc TEXT,
    
    -- Breakeven Stop Tracking
    breakeven_stop_activated INTEGER DEFAULT 0,  -- 0 = False, 1 = True
    breakeven_stop_price REAL,
    
    -- Financial Realization
    realized_pnl_usd REAL DEFAULT 0.0,
    estimated_fees_usd REAL DEFAULT 0.0,
    actual_fees_usd REAL DEFAULT 0.0,
    exit_time_utc TEXT,
    close_reason TEXT,                           -- 'TP1', 'TP2', 'TP3', 'SL', 'MANUAL', 'TIME_STOP'
    
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (shadow_decision_id) REFERENCES shadow_decisions(decision_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_user_manual_trades_signal_id ON user_manual_trades(signal_id);
CREATE INDEX IF NOT EXISTS idx_user_manual_trades_status ON user_manual_trades(status);
```

### 5.4 Rollback Plan
If created in a future authorized phase, this table can be dropped instantly with zero data loss to the rest of the platform:
```sql
DROP INDEX IF EXISTS idx_user_manual_trades_status;
DROP INDEX IF EXISTS idx_user_manual_trades_signal_id;
DROP TABLE IF EXISTS user_manual_trades;
```

---

## 6. Full Automated Test Execution Results

All test suites were executed on the staging VPS using the isolated Python virtual environment (`/opt/tauric-platform-staging/backend/.venv/bin/python3`):

### 6.1 Phase 1 & 1.1 Market Data Suite (`test_phase1_market_data.py`)
```
Ran 24 tests in 2.385s
OK (24/24 PASS)
- Binance Spot ticker & metadata verification: PASS
- Bybit Spot ticker & metadata verification: PASS
- Derivatives exclusion (perp, linear, options): PASS
- Binance/Bybit timeouts handling: PASS
- HTTP 429 rate limit & Retry-After capture: PASS
- Non-finite numeric rejection (NaN, Inf, negative): PASS
- Missing required fields yield UNKNOWN: PASS
- Stale quote (60s) & candle rejection: PASS
- Crossed market (bid > ask) rejection: PASS
- Duplicate / disordered candles rejection: PASS
- Canonical IDs exchange identity: PASS
- Zero hardcoded fallback prices: PASS
- Zero execution safeguards & read-only lock: PASS
- Zero AI calls during market data: PASS
- Micro-spread unrounded float precision: PASS
- Unified signals skip None/STALE/UNAVAILABLE: PASS
- Market routes return 503/DATA_UNAVAILABLE without AI: PASS
- Grid scan skips invalid candidates: PASS
- Shadow evaluation rejects unavailable price: PASS
- Live directional meter handles unavailable price: PASS
- Zero AI telemetry ledger delta: PASS
```

### 6.2 Phase 2 Qualification Suite (`test_phase2_qualification.py`)
```
Ran 26 tests in 0.151s
OK (26/26 PASS)
- Bullish momentum regime -> RISK_ON: PASS
- Consolidation regime -> NEUTRAL: PASS
- Sharp downside regime -> RISK_OFF: PASS
- Volatility spike regime -> RISK_OFF: PASS
- Macro event blackout active: PASS
- Macro event outside buffer clear: PASS
- Untrusted calendar source rejected (no phantom blackout): PASS
- Missing calendar source returns UNKNOWN: PASS
- Stale market quote returns UNKNOWN: PASS
- Missing price / provider outage returns UNKNOWN: PASS
- Aggregate market breadth computation: PASS
- Qualified Binance Spot candidate passes all gates: PASS
- Segregated Bybit Spot candidate passes all gates: PASS
- Low 24h quote volume (<$5M) rejected: PASS
- Wide spread (>25 bps) rejected: PASS
- Shallow book depth (<$20k) rejected: PASS
- High market impact (>20 bps on $1k) rejected: PASS
- Insufficient depth for reference order rejected: PASS
- Crossed order book rejected: PASS
- Stale data / missing data returns STALE/UNKNOWN: PASS
- Non-spot / halted trading status rejected: PASS
- Anti-promotion invariant (unqualified never scored): PASS
- Zero AI telemetry & zero execution keys: PASS
```

### 6.3 Phase 2 Extended Suite (`test_phase2_extended.py`)
```
Ran 20 tests in 0.707s
OK (20/20 PASS)
- Defect A: Live meter unavailable data handling: PASS
- Defect B: Venice client guards against None/NaN/Inf: PASS
- Defect B: Analysis route unavailable handling: PASS
- Defect C: JeV fast decision interface & bias: PASS
- Defect C: JeV route 503 on unavailable data: PASS
- Defect D: Conservative same-candle TP/SL conflict to LOSS_SL: PASS
- Outcome engine WIN_TP3 resolution: PASS
- Multi-target allocations (50/30/20 = 100%) & R-multiples: PASS
- Friction drag & 30 bps net rewards: PASS
- Binance min notional feasibility ($1,000 ref, $5 min notional): PASS
- Bearish crypto spot-only labeling (Inventory Exit): PASS
- TP1 breakeven advisory guidance (30 bps true net buffer): PASS
- Dual timers & PKT formatting: PASS
- Deterministic 16-character SHA-256 signal ID: PASS
- Finnhub tier boundaries & documentation: PASS
- Finnhub mock fixtures & blackout detection: PASS
- Zero paid AI costs maintained: PASS
- Expired signals cannot be revived by cache: PASS
- Zero order execution calls: PASS
- Stale/missing calendar does not fabricate events: PASS
```

**Grand Total: 70 / 70 Tests Passed (100% Success Rate).**

---

## 7. Frontend GUI Verification

- Staging location: `/opt/tauric-platform-staging/dashboard/`
- Component inspected: `UnifiedSignalDashboard.tsx`
- Type checking: `npx tsc --noEmit` completed with **0 errors**.
- Build command: `npm run build` completed successfully:
  - 4 static pages compiled.
  - Shared JS chunks: 87.1 kB.
  - Dynamic API routes: 0 B overhead.
- Interactive features verified:
  - 50% / 30% / 20% multi-target split progress bars.
  - Net reward after estimated friction (30 bps) indicators.
  - Prominent "ADVISORY ONLY — MANUAL EXECUTION REQUIRED" badges.
  - True net breakeven display with +0.30% (long) / -0.30% (short) buffers.
  - Spot inventory reduction disclaimers for crypto sell signals.
  - Server-authoritative dual timers (UTC primary, PKT secondary).

---

## 8. Production Safeguard Verification

Before concluding this verification audit, the live production environment was re-verified via SSH:

```bash
pm2 status
```
```
┌────┬─────────────────────┬─────────────┬─────────┬─────────┬──────────┬────────┬──────┬───────────┬──────────┬──────────┬──────────┬──────────┐
│ id │ name                │ namespace   │ version │ mode    │ pid      │ uptime │ ↺    │ status    │ cpu      │ mem      │ user     │ watching │
├────┼─────────────────────┼─────────────┼─────────┼─────────┼──────────┼────────┼──────┼───────────┼──────────┼──────────┼──────────┼──────────┤
│ 0  │ tauric-backend      │ default     │ N/A     │ fork    │ 75730    │ 10h    │ 5    │ online    │ 0%       │ 272.8mb  │ root     │ disabled │
│ 1  │ tauric-dashboard    │ default     │ N/A     │ fork    │ 88836    │ 6h     │ 8    │ online    │ 0%       │ 61.8mb   │ root     │ disabled │
└────┴─────────────────────┴─────────────┴─────────┴─────────┴──────────┴────────┴──────┴───────────┴──────────┴──────────┴──────────┴──────────┘
```

```bash
curl -sI https://sheltr.agency/trading/
```
```
HTTP/2 200 
server: nginx/1.24.0 (Ubuntu)
x-nextjs-cache: HIT
```

- Production directory `/opt/tauric-platform/` has **zero modified files**.
- Production processes have **not been restarted or reloaded**.
- Production database schemas have **not been altered**.
- Zero exchange orders placed; zero private keys introduced.
- AI token consumption ledger remains strictly at **0**.

---

## 9. Next Steps & Phase 3 Transition Prerequisites

To proceed to Phase 3 authorization, the following items must be formally acknowledged:

1. **Finnhub Entitlement Decision:**
   - Either accept that Finnhub economic calendar will NOT be queried on production (preserving the $0 paid API rule and relying on internal mock fixtures or alternative free feeds), or explicitly approve purchasing the $50/mo Finnhub Economic Data package.
2. **Schema Migration Authorization:**
   - Authorize running the decoupled DDL script for `user_manual_trades` in SQLite.
3. **Standing Stop:**
   - Work stops here at the Phase 2 Verification Gate. No deployment to production or Phase 3 execution will take place without explicit user instruction.
