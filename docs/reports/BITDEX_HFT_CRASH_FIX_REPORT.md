# BITDEX.LTD — Phase 1: Critical `#hft` Application Crash Fix Report

**Repository:** `https://github.com/nexuratechpteltd-tech/bitdex-platform`  
**Branch:** `feature/hft-redesign-and-navigation-cleanup`  
**Staging Environment:** `https://bitdex.ltd/#hft`  
**Status:** **RESOLVED & VERIFIED (0 Uncaught Exceptions, 0 HTTP 401/500 Errors)**

---

## 1. Executive Summary

Navigating to `https://bitdex.ltd/#hft` or clicking **HFT** in the customer navigation sidebar previously triggered a fatal Next.js client-side crash:
> `Application error: a client-side exception has occurred (see the browser console for more information).`

Independent reproduction and code inspection isolated **three compounding defects** in [CustomerPortal.tsx](file:///opt/tauric-platform-staging/dashboard/src/components/CustomerPortal.tsx) and [ProtectionCenter.tsx](file:///opt/tauric-platform-staging/dashboard/src/components/ProtectionCenter.tsx):
1. **Fatal React Hook Violation (`Minified React error #321`)**: A `useEffect(...)` hook was illegally nested inside the `navigateTo(dest: NavDestination)` event callback function in `CustomerPortal.tsx` (lines 111–128). Whenever a customer clicked any sidebar item (such as **HFT**), React threw `Error: Minified React error #321 (Invalid hook call. Hooks can only be called inside of the body of a function component)`.
2. **Temporal Dead Zone / Pre-Initialization State Setter Access**: `navigateTo` referenced `setActiveTab` and `setTradingMode` on lines 131–145 before their `useState` declarations on lines 147 and 168.
3. **Token Variable Shadowing Causing Background HTTP 401 Errors**: `fetchLedgerData` and `handleCancelWorkingOrder` in `CustomerPortal.tsx` declared `const token = localStorage.getItem("bitdex_auth_token") || localStorage.getItem("tauric_token")`, shadowing the valid `token` prop and omitting `tauric_session_token`, which caused background requests to `/orders/positions` and `/orders/open` to fail with `HTTP 401 Unauthorized`.

---

## 2. Captured Browser Stack Trace (Pre-Fix Reproduction)

Using headless Chromium (`puppeteer`) against `http://127.0.0.1:33900/#overview` -> clicking **HFT**, the exact runtime exception was captured prior to the fix:

```text
PAGEERROR: Minified React error #321; visit https://react.dev/errors/321 for the full message or use the non-minified dev environment for full errors and additional helpful warnings. 
STACK: Error: Minified React error #321; visit https://react.dev/errors/321 for the full message or use the non-minified dev environment for full errors and additional helpful warnings.
    at rS (http://127.0.0.1:33900/_next/static/chunks/dacb1409-86bf47671ce2e10a.js:1:40064)
    at t.useEffect (http://127.0.0.1:33900/_next/static/chunks/627-749c648a9e3d628d.js:2:31424)
    at L (http://127.0.0.1:33900/_next/static/chunks/4.45954ac97a9614ba.js:1:234977)
    at onClick (http://127.0.0.1:33900/_next/static/chunks/4.45954ac97a9614ba.js:1:107481)
```

Along with background network 401s:
```text
HTTP_ERR: 401 http://127.0.0.1:33900/trading/api/backend/orders/positions?environment=DEMO&market_type=ALL
HTTP_ERR: 401 http://127.0.0.1:33900/trading/api/backend/orders/open?environment=DEMO
```

---

## 3. Code Remediation Implemented

### 3.1 Top-Level Hook Ordering & Removal of Nested `useEffect` in `CustomerPortal.tsx`
- Moved all `useState` declarations (`activeTab`, `settingsSubTab`, `tradingMode`) to the top level of `CustomerPortal` prior to `navigateTo`.
- Removed the duplicate, illegally nested `useEffect` inside `navigateTo` (preserving the legitimate top-level `useEffect` hash listener on line 186).

### 3.2 Elimination of Token Prop Shadowing in `CustomerPortal.tsx` & `ProtectionCenter.tsx`
- Replaced shadowed `const token = ...` in `fetchLedgerData` and `handleCancelWorkingOrder` with:
  ```ts
  const activeToken = token || localStorage.getItem("tauric_session_token") || localStorage.getItem("bitdex_auth_token") || localStorage.getItem("tauric_token");
  ```
- Updated `ProtectionCenter.tsx` to include `localStorage.getItem("tauric_session_token")` in its token resolution chain.

---

## 4. Post-Fix Verification Matrix

| Test Scenario | Expected Outcome | Observed Result | Status |
| :--- | :--- | :--- | :--- |
| Authenticated customer clicks **HFT** from `#overview` | Navigates to `#hft` with 0 React hook errors | `0` `pageerror` exceptions, HFT terminal rendered | **PASS** |
| Direct browser reload on `https://bitdex.ltd/#hft` | Hydrates `#hft` cleanly without crash | `0` `pageerror` exceptions, `0` HTTP 401/500 errors | **PASS** |
| Logged-in **unactivated** customer opens `#hft` | Renders HFT terminal in View-Only mode with `UNACTIVATED — ACTIVATE HFT ($20.00)` badge | Rendered cleanly; clicking action buttons opens `$20.00 USD` Activation Modal | **PASS** |
| Logged-in **activated** customer opens `#hft` | Renders HFT terminal with `HFT ACTIVATED ($20 VERIFIED)` badge and unlocked config modal | Rendered cleanly; strategy config modal opens & saves | **PASS** |
| Customer with **no Exness/Binance connection** opens `#hft` | Renders HFT terminal with clear connection prerequisite in Pre-Trade Checklist | Rendered cleanly; no null/undefined property exceptions | **PASS** |
| Mobile (`360px`, `390px`, `430px`), Tablet (`768px`, `1024px`), Desktop (`1440px`) | Zero horizontal overflow (`overflowPx === 0`) and zero chart/canvas elements | `0px` horizontal overflow across all 6 viewports; `0` `<canvas>` elements | **PASS** |
