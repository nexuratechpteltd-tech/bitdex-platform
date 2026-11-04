# BITDEX — Genuine Exness MT5 Terminal & Broker Connectivity (Phase 3)

**Target Broker:** Exness (MetaTrader 5)  
**Target Accounts:**
- Admin Demo: `149827361` (`Exness-MT5Trial`)
- Admin Real: `460310009` (`Exness-Real`)  
**Date:** November 5, 2026  
**Status:** **BLOCKED (Zero Mock Fallbacks / Zero Fabricated Balances)**

---

## 1. Terminal Telemetry & Account Status

Due to the Windows MT5 Gateway host being offline, live broker authentication checks could not query a running Exness MetaTrader 5 terminal.

In accordance with strict safety mandates, **no hardcoded, simulated, cached, or fabricated broker responses were substituted.**

| Telemetry Attribute | Required Verification | Live Terminal Status | Reason / Evidence |
| :--- | :--- | :--- | :--- |
| **Terminal Initialization** | `mt5.initialize() == True` | **BLOCKED** | Windows gateway daemon unreachable |
| **Broker / Server Identity** | Confirm `Exness-MT5Trial` / `Exness-Real` | **BLOCKED** | No active connection |
| **Account Login Status** | Validated trade session | **BLOCKED** | No active connection |
| **Account Currency** | Broker reported currency (USD) | **BLOCKED** | Live response unavailable |
| **Account Type** | DEMO vs REAL | **BLOCKED** | Live response unavailable |
| **Trading Permissions** | Read-Only (Real) / Trading (Demo) | **BLOCKED** | Live response unavailable |
| **Account Balance** | Genuine broker balance | **BLOCKED** | Live response unavailable |
| **Account Equity** | Genuine broker equity | **BLOCKED** | Live response unavailable |
| **Free Margin / Level** | Broker margin calculation | **BLOCKED** | Live response unavailable |
| **Bid / Ask Real Prices** | Live quote stream from Exness | **BLOCKED** | Live response unavailable |
| **Symbol Availability** | Catalog check (Forex, Crypto CFDs) | **BLOCKED** | Live response unavailable |
| **Market Session Status** | Broker market session state | **BLOCKED** | Live response unavailable |

---

## 2. SQLite Database Integrity Audit

An inspection of `tauric_saas.db` on staging revealed:
1. **Existing Demo Accounts:**
   Historical test entries in `exness_demo_connections` contain `adapter_mode = DETERMINISTIC_MOCK_DEMO` with `balance_usd = 5000.0`. These are recognized as **simulated mocks** and are flagged as `is_mock = true` in API output.
2. **Existing Real Accounts (460310009):**
   Recorded with `balance_usd = 0.0`, `equity_usd = 0.0`, and `last_reconciled_at = NULL`. The platform correctly refrains from inventing a non-zero balance for this unverified account.
3. **Execution Guardrails:**
   Any request to `/hft/exness/demo/connect` with `use_mock=False` immediately throws HTTP 503 `GATEWAY_UNAVAILABLE` when the gateway cannot be reached, preserving fail-closed behavior.
