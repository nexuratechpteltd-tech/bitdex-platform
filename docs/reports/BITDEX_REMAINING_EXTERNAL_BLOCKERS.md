# BITDEX.LTD — Remaining External Infrastructure & Credential Blockers

**Repository:** `https://github.com/nexuratechpteltd-tech/bitdex-platform`  
**Branch:** `feature/hft-redesign-and-navigation-cleanup`  
**Staging Environment:** `https://bitdex.ltd`  
**Status:** **ALL SOFTWARE COMPLETE — 3 EXTERNAL PROVISIONING DEPENDENCIES RECORDED**

---

## 1. Executive Summary

All software engineering, UI stability fixes, `$20.00 USD` HFT account activation gates, session revocation security, technical SEO, and automated test suites (`74 PASSED | 2 BLOCKED | 0 FAILED`) are complete on the Linux staging host (`169.58.218.168`).

In strict compliance with anti-fabrication rules, the following **3 external infrastructure/credential provisioning dependencies** are documented with exact verification checklists.

---

## 2. External Dependency #1: Windows Server Host for Official MetaTrader 5 Desktop Gateway

- **Why It Is External**: The official `MetaTrader5` Python package (`MetaTrader5>=5.0.45`) and MetaQuotes MT5 terminal (`terminal64.exe`) are Windows-only native x64 binaries and cannot execute natively on Linux (`169.58.218.168`).
- **Completed Software Package Ready in Repository**:
  - `scripts/windows_gateway_package/` (`mt5_gateway_server.py`, `install_windows_gateway.ps1`, `verify_windows_gateway.ps1`, `gateway_config.template.json`, `WINDOWS_MT5_DEPLOYMENT_RUNBOOK.md`).
- **Exact Operator Provisioning Steps**:
  1. Provision a Windows Server 2022 x64 VPS (minimum 2 vCPU, 4 GB RAM).
  2. Establish a WireGuard VPN or mutual-TLS link to `169.58.218.168`.
  3. Run `install_windows_gateway.ps1` and `verify_windows_gateway.ps1` on the Windows host.
  4. Update `EXNESS_MT5_GATEWAY_URL` and `EXNESS_MT5_GATEWAY_TOKEN` in `/opt/tauric-platform-staging/backend/.env` and reload `tauric-backend-staging`.

---

## 3. External Dependency #2: Customer-Issued Exness Personal Area API Credentials

- **Why It Is External**: Under the Fundamental Account Ownership Rule (Phase 4.1), administrator Exness accounts are strictly isolated and never shared with customers. Live customer Exness Trader API (`api.exness.com`) authentication requires a customer-generated Personal Area bearer token or API key pair.
- **Completed Software Package Ready in Repository**:
  - `backend/app/services/exness/trader_api_client.py`, `payments_service.py`, `vault.py`, and the 3-step onboarding UI in `ExchangeConnectionsView.tsx`.
- **Exact Verification Steps Once Customer Credentials Are Entered**:
  1. Log in as a customer on `https://bitdex.ltd/#connections`.
  2. Enter customer-owned Exness Personal Area API credentials or MT5 Demo/Real login (`Exness-MT5Trial*` / `Exness-MT5Real*`).
  3. Re-run `test_phase4_5_trader_payments.py` to transition the single external credential check from `BLOCKED` to `PASSED`.

---

## 4. External Dependency #3: Live Production Payment Merchant Webhook Secret (`BINANCE_PAY` / `STRIPE`)

- **Why It Is External**: Staging (`https://bitdex.ltd`) operates in non-financial sandbox/signed-HMAC verification mode so zero real customer funds are charged during staging testing.
- **Completed Software Package Ready in Repository**:
  - `backend/app/services/activation_service.py` (HMAC-SHA256 verification, exact `$20.00 USD` enforcement, cross-tenant reference isolation, and `hft_activation_webhooks` replay idempotency).
- **Exact Production Cutover Steps**:
  1. Configure live merchant credentials (`BITDEX_ACTIVATION_WEBHOOK_SECRET`, `BINANCE_PAY_API_KEY`, `BINANCE_PAY_SECRET_KEY`) in `.env`.
  2. Point the payment provider's webhook callback URL to `https://bitdex.ltd/api/v1/saas/customer/hft/activation/webhook`.
