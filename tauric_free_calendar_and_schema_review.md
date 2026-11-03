# TAURIC — FINANCE CALENDAR STAGING INTEGRATION & SCHEMA REVIEW
**Staging Implementation, Validation & Architectural Audit (No Deployment)**

- **Date:** October 21, 2026
- **Target Host:** VPS `169.58.218.168` (Ubuntu 24.04 LTS)
- **Production Reference:** `/opt/tauric-platform/` (**UNTOUCHED & ONLINE**)
- **Staging Workspace:** `/opt/tauric-platform-staging/`
- **Database Under Review:** `/opt/tauric-platform-staging/backend/data/shadow_validation/shadow_validation.db`
- **Live Production URL:** `https://sheltr.agency/trading/` (HTTP/2 200 OK)
- **Approved Attribution:** “Economic calendar data provided by Finance Calendar” with clickable link to `https://www.financecalendar.com`
- **Final Acceptance Status:** **`PASS — STAGING ONLY`**

---

## 1. Executive Summary & Verification Decisions

| Evaluation Item | Status | Verified Evidence |
| :--- | :---: | :--- |
| **Production Isolation** | **VERIFIED** | `/opt/tauric-platform/` has 0 unstaged/modified files. Running PM2 processes (PID 75730, 88836) untouched. |
| **Official Provider Verification** | **VERIFIED** | Live docs at `https://www.financecalendar.com/api` audited. Commercial use confirmed; keyless quota confirmed. |
| **Approved Attribution** | **IMPLEMENTED** | Visible link rendered in staging dashboard and signal detail modals: [Finance Calendar](https://www.financecalendar.com). |
| **Adapter Architecture** | **IMPLEMENTED** | [`finance_calendar_adapter.py`](file:///opt/tauric-platform-staging/backend/app/services/finance_calendar_adapter.py) created with `enabled=False` default, canonical UTC, PKT formatting, deduplication, and `EventCalendarSource` protocol. |
| **Automated Test Matrix** | **PASS (85/85)** | 15 new Finance Calendar tests + 70 existing regression tests passing with 0 failures and 0 errors. |
| **Frontend Build & Types** | **PASS** | `npx tsc --noEmit` (0 errors) and Next.js `npm run build` compiled successfully in staging. |
| **Event-Risk Safety Gating** | **VERIFIED** | Disabled provider reports `UNKNOWN` risk; missing data reports `CALENDAR_UNAVAILABLE`; never fabricates phantom blackouts. |
| **Zero Client-Side Polling** | **VERIFIED** | Calendar metadata bundled inside existing `/signals/` endpoint payload; zero external calls on navigation/tab switching. |
| **Zero Schema Changes** | **VERIFIED** | SQLite database hash `9033d755...` identical in staging and production. Zero DDL executed. |
| **Zero Paid Provider Usage** | **VERIFIED** | No credentials, no paid endpoints, $\Delta\text{Tokens} = 0$. Finnhub paid endpoint remains disabled. |

---

## 2. Official Provider Documentation & Terms Review

The official documentation and terms for Finance Calendar were audited directly from production sources:
- **Official Website:** `https://www.financecalendar.com`
- **API Documentation:** `https://www.financecalendar.com/api/`
- **Base Endpoint:** `https://www.financecalendar.com/wp-json/fc/v1`
- **Bulk Mirror Endpoint:** `https://www.financecalendar.com/wp-content/uploads/fc/calendar.json`
- **Public Repository & OpenAPI Spec:** `https://github.com/awarenessdays/financecalendar-api`

### 2.1 Confirmed Provider Capabilities
1. **Unauthenticated / Keyless Access:**
   - Programmatic access is available keyless without registration or API tokens.
   - Keyless quota: **2,000 requests/day per IP address**, resetting at `00:00:00 UTC`.
   - Optional free registered key: increases quota to **10,000 requests/day**.
2. **Commercial-Use Permission:**
   - Commercial applications are explicitly permitted under official terms:
     > *"It is free for any use, commercial included, with one condition: a visible link to financecalendar.com wherever the data appears."*
3. **Attribution Satisfaction:**
   - Approved wording: *"Economic calendar data provided by Finance Calendar"* with a direct link to `https://www.financecalendar.com`.
   - Verified that placing this attribution on the dashboard header and modal details fulfills the provider's fair-use requirements.
4. **Data Coverage & Timestamps:**
   - Covers 14 countries: US, GB, EU, DE, JP, CA, AU, CN, CH, NZ, NO, SE, IN, HK.
   - Includes >50 release and decision series (FOMC, CPI, NFP, GDP, PCE, Retail Sales, ECB, BoE, BoJ, etc.) and 12 exchange holiday tables. Earnings dates are excluded.
   - Timestamps are published in RFC 3339 / ISO 8601 UTC format (`release_at_utc`).
5. **Data Freshness, Revisions & Missing Values:**
   - `consensus` (forecast) is populated approximately 2 days prior to scheduled release.
   - `actual` is populated within the hour of official release, triggering a status transition from `confirmed` to `released`.
   - Prior revisions are published and tracked via the `/changes` endpoint.
   - Response headers provide rate-limit tracking: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`.
   - HTTP 429 errors include standard `Retry-After` headers.

---

## 3. Staging-Only Adapter Implementation

The adapter was implemented in [`backend/app/services/finance_calendar_adapter.py`](file:///opt/tauric-platform-staging/backend/app/services/finance_calendar_adapter.py) following Tauric's zero-risk staging requirements:

### 3.1 Architectural Properties
- **Disabled by Default:** Initialized with `enabled: bool = False`. The adapter cannot perform outbound network requests unless explicitly enabled in configuration.
- **Canonical Time Representation:**
  - Internally stores and operates on canonical UTC ISO 8601 strings and Unix epoch milliseconds (`scheduled_timestamp_ms`).
  - Generates authoritative PKT (`UTC+05:00`) strings exclusively for human presentation.
- **Normalized Data Model (`NormalizedEconomicEvent`):**
  - Captures `event_id`, `series_code`, `title`, `country`, `currency`, `scheduled_utc`, `scheduled_pkt`, `impact`, `impact_weight`, `status`, `actual`, `forecast`, `previous`, `revised_previous`, `is_revised`, `unit`, `source_url`.
  - Distinguishes explicitly between:
    - `is_missing_actual = (actual is None)`
    - `is_missing_forecast = (forecast is None)`
    - `is_not_yet_released = (status in ("scheduled", "confirmed") and actual is None)`
    - `is_confirmed_release = (status == "released" and actual is not None)`
    - `is_feed_unavailable = (status == "FEED_UNAVAILABLE")`
- **Deduplication & Deterministic Ordering:**
  - Events are deduplicated on `(event_id, scheduled_utc)`.
  - Chronologically sorted by `scheduled_timestamp_ms` ascending, then `series_code` ascending.
- **Stale Data Detection:**
  - Enforces a 1-hour (`3600s`) stale threshold. Stale cache shifts provider status to `STALE`.
- **Event-Specific Actual vs. Forecast Interpretation:**
  - Replaces blunt universal rules with an indicator taxonomy:
    - *Inflation (CPI, PCE, PPI):* Actual > Forecast is **BULLISH** for Currency, **BEARISH** for Crypto (higher-for-longer rate drag).
    - *Employment (NFP, ADP):* Actual > Forecast is **BULLISH** for Currency, **BEARISH** for Crypto (delayed easing).
    - *Jobless Claims / Unemployment:* Actual > Forecast is **BEARISH** for Currency, **BULLISH** for Crypto (dovish easing expectation).
    - *Rate Decisions (FOMC, ECB, BoE):* Actual > Forecast is **BULLISH** for Currency, **BEARISH** for Crypto.
    - *Growth (GDP, PMI, Retail Sales):* Actual > Forecast is **BULLISH** for Currency, **NEUTRAL** for Crypto.
- **Protocol Conformance:** Implements `EventCalendarSource` (`get_events(start_ms, end_ms)` and `is_reliable()`), integrating directly with [`regime_engine.py`](file:///opt/tauric-platform-staging/backend/app/services/regime_engine.py).

---

## 4. Event-Risk Gating & Safety Behavior

Downstream consumers were audited to ensure unknown or unconfigured event risk cannot accidentally pass safety gates:

1. **Provider Disabled State:**
   ```python
   {
       "event_risk_status": "UNKNOWN",
       "is_blackout": False,
       "policy": "CALENDAR_UNAVAILABLE",
       "reason": "Economic calendar provider is disabled in production isolation.",
       "recommendation": "WAIT_OR_MANUAL_VERIFICATION"
   }
   ```
   An unconfigured calendar is never treated as proof that markets are safe.
2. **Missing / Stale Feed State:**
   When cache age exceeds 1 hour or errors occur, `event_risk_status` reports `STALE` or `UNAVAILABLE`.
3. **Anti-Silent-Clear Rule:**
   The adapter never outputs `CLEAR` when data is missing or unverified. Downstream signals display `NEWS: UNKNOWN` so human traders are alerted to unverified macro conditions.
4. **Anti-Phantom Rule:**
   The engine never invents phantom blackout events. Blackout windows ($\pm 30\text{ minutes}$) are triggered exclusively by confirmed, verified high-impact events.

---

## 5. Dashboard Attribution & UI Presentation

The staging frontend in [`dashboard/src/components/UnifiedSignalDashboard.tsx`](file:///opt/tauric-platform-staging/dashboard/src/components/UnifiedSignalDashboard.tsx) was updated:

1. **Prominent Header Attribution:**
   - Renders: *“Economic calendar data provided by [Finance Calendar](https://www.financecalendar.com)”* with a clickable external link opening in a new tab with `rel="noopener noreferrer"`.
2. **Status Readout & Authoritative Time:**
   - Displays real-time provider state: `STATUS: DISABLED` (or `AVAILABLE`, `STALE`, `UNAVAILABLE`).
   - Displays feed sync time in authoritative PKT (e.g. `-- (Provider Disabled in Staging)`), maintaining canonical UTC internally.
   - Displays event horizon scope: `14-Day Horizon (14 Countries)`.
3. **Prominent Event-Risk Warning:**
   - Renders a warning card when the calendar is unconfigured:
     > *"EVENT-RISK WARNING: MACRO NEWS GATING IS CURRENTLY UNVERIFIED. The economic calendar is currently disabled in staging isolation to ensure 100% zero-cost compliance. Downstream signals must treat event risk as UNKNOWN rather than assuming markets are clear."*
4. **Signal Card & Modal Integration:**
   - Each signal card displays a `NEWS: UNKNOWN` badge.
   - Modal detail views include an institutional Macroeconomic News & Blackout Protection card with the approved Finance Calendar attribution.
5. **Zero Client Polling Invariant:**
   - Calendar metadata is bundled directly in the `/signals/` backend response. Switching tabs, filtering markets, or searching tickers causes **zero additional network calls**.

---

## 6. Manual-Trade Schema Review (Strictly Read-Only)

The proposed schema for `user_manual_trades` and child fill ledger `user_manual_trade_fills` was finalized in documentation:

### 6.1 Database Inspection
- File: `/opt/tauric-platform-staging/backend/data/shadow_validation/shadow_validation.db`
- Hash: `SHA256: 9033d755e6fcef8822b82d62289f0fe020b5f5a60006d3a31f2752c2240aa865`
- Existing tables: `shadow_decisions` (9 rows), `telemetry_events` (0 rows).
- Foreign-key status: `PRAGMA foreign_keys = 0` (DISABLED by default in Python SQLite).

### 6.2 Key Architectural Decisions
1. **Decoupled Identifiers:** `signal_id` (deterministic 16-char hash) remains distinct from optional `shadow_decision_id` (`SHD-...` benchmark run).
2. **Normalized Child Fill Ledger:** Instead of overwriting single columns, `user_manual_trade_fills` stores every partial execution fill with price, filled quantity, fees paid, and UTC timestamp.
3. **Canonical UTC Timestamps:** Redundant `entry_time_pkt` table columns are omitted to prevent state desynchronization. UTC is stored canonically; PKT is formatted at the presentation layer.
4. **Authenticated Identity:** `user_id TEXT NOT NULL` without a hardcoded default string.
5. **Rollback Safety Reality:**
   - `DROP TABLE` is catastrophic once real user trades exist.
   - An operational rollback must rely on pre-migration hot snapshots (`shadow_validation.db.bak_YYYYMMDD_HHMMSS`), versioned schema migrations (`schema_migrations` table), additive forward compatibility, and database restore procedures.
   - **Zero DDL statements were executed.**

---

## 7. Staging Automated Test Suite & Build Evidence

### 7.1 Finance Calendar Test Suite (`test_phase3_finance_calendar.py`)
```bash
cd /opt/tauric-platform-staging/backend && \
.venv/bin/python3 -m unittest test_phase3_finance_calendar.py
```
**Results:** `Ran 15 tests in 2.145s — OK (15 / 15 PASS)`
- Scenario 1: Valid scheduled events parsing: PASS
- Scenario 2: Released events with actual/forecast/prior: PASS
- Scenario 3: Missing actual/forecast values without synthetic defaults: PASS
- Scenario 4: Revised previous values tracking: PASS
- Scenario 5: Duplicate event deduplication: PASS
- Scenario 6: Malformed/missing timestamps skipped safely: PASS
- Scenario 7: Canonical UTC conversion and PKT display (+05:00): PASS
- Scenario 8: Empty responses and malformed payloads: PASS
- Scenario 9: Bounded retry, rate limits, and 429 specifications: PASS
- Scenario 10: Stale calendar data detection (>1h): PASS
- Scenario 11: Provider disabled by default and UNKNOWN risk: PASS
- Scenario 12: Attribution text and link verification: PASS
- Scenario 13: Zero client API calls on page navigation: PASS
- Scenario 14: Zero paid fallback, zero tokens consumed, trading locked: PASS
- Scenario 15: Regime engine `EventCalendarSource` protocol integration: PASS

### 7.2 Full Automated Regression Suite (85 Scenarios)
```bash
cd /opt/tauric-platform-staging/backend && \
.venv/bin/python3 -m unittest test_phase1_market_data.py test_phase2_qualification.py test_phase2_extended.py test_phase3_finance_calendar.py
```
**Results:** `Ran 85 tests in 4.465s — OK (85 / 85 PASS)`
- Phase 1 & 1.1 Market Data Quality Gates: 24/24 PASS
- Phase 2 Regime & Liquidity Qualification: 26/26 PASS
- Phase 2 Extended Multi-Target & Safeguards: 20/20 PASS
- Phase 3 Finance Calendar Integration: 15/15 PASS
- **Grand Total: 85 / 85 Passing (100% Success Rate).**

### 7.3 Frontend Compilation & Typecheck
```bash
cd /opt/tauric-platform-staging/dashboard && npx tsc --noEmit && npm run build
```
**Results:**
- `npx tsc --noEmit`: **0 errors**.
- `next build`: **Compiled successfully** (4 static pages, 87.1 kB shared JS).

---

## 8. Production Verification & Safeguards

The production environment was verified untouched via SSH before concluding:

```bash
pm2 status
```
```
┌────┬─────────────────────┬─────────────┬─────────┬─────────┬──────────┬────────┬──────┬───────────┬──────────┬──────────┬──────────┬──────────┐
│ id │ name                │ namespace   │ version │ mode    │ pid      │ uptime │ ↺    │ status    │ cpu      │ mem      │ user     │ watching │
├────┼─────────────────────┼─────────────┼─────────┼─────────┼──────────┼────────┼──────┼───────────┼──────────┼──────────┼──────────┼──────────┤
│ 0  │ tauric-backend      │ default     │ N/A     │ fork    │ 75730    │ 10h    │ 5    │ online    │ 0%       │ 270.0mb  │ root     │ disabled │
│ 1  │ tauric-dashboard    │ default     │ N/A     │ fork    │ 88836    │ 7h     │ 8    │ online    │ 0%       │ 62.2mb   │ root     │ disabled │
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
- Production source directory `/opt/tauric-platform/` has **zero modified files**.
- Production processes (PIDs 75730, 88836) have **not been restarted or reloaded**.
- Production database schemas have **not been altered**.
- Zero exchange orders placed; zero private keys introduced.
- AI token consumption ledger remains strictly at **0**.

---

## 9. Final Acceptance Gate Decision

**`PASS — STAGING ONLY`**

All staging implementation and validation tasks for Finance Calendar are complete. Production remains untouched, locked in read-only mode, and awaiting explicit approval prior to any deployment or schema migration.
