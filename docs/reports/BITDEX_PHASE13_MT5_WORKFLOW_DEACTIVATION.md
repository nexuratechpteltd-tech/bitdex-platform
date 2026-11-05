# BITDEX — PHASE 13: CUSTOMER MT5 WORKFLOW DEACTIVATION & INFRASTRUCTURE PRESERVATION REPORT

**Timestamp:** 2026-11-05T00:21:00Z  
**Host:** Linux Staging Server (`169.58.218.168`)  
**Repository:** `https://github.com/nexuratechpteltd-tech/bitdex-platform`  

---

## 1. Executive Summary

This report confirms the formal retirement of customer-facing MetaTrader 5 (MT5) setup wizards and establishes that all underlying Windows VPS MT5 gateway files and WireGuard configurations remain preserved for administrative operations.

---

## 2. Customer-Facing MT5 Retirement

### Rationale
Retail MT5 gateway configurations require customers to manage Windows VPS services, WireGuard tunnels, NSSM daemons, and MT5 terminal credentials. This introduced significant friction and failure points. Transitioning retail clients to the official Exness Trader API (`https://www.exness-api.com`) provides direct REST/WebSocket connectivity without client-side VPS requirements.

### Customer Interface Modifications
1. **Removed Tabs**:
   - `Step B: MT5 Demo` onboarding tab removed from customer view.
   - `Step C: MT5 Real` onboarding tab removed from customer view.
2. **Removed Wizards**:
   - MT5 terminal path selectors, NSSM service instructions, and Windows tunnel setup guides removed from customer dashboards.
3. **Consolidated Interface**:
   - Replaced by the unified Exness Trader API Connection Card and Modal in `ExchangeConnectionsView.tsx`.

---

## 3. Preservation of Windows VPS Infrastructure

In strict adherence to project safety rules:
- **No VPS Deletion**: The existing Windows VPS was neither decommissioned nor overwritten.
- **No Gateway Deletion**: All gateway automation scripts, NSSM batch files, and documentation remain intact in the repository:
  - `gateway/windows/setup_windows_gateway.ps1` (Preserved)
  - `gateway/windows/run_gateway.bat` (Preserved)
  - `gateway/windows/install_service_nssm.bat` (Preserved)
  - `gateway/windows/DEPLOYMENT_RUNBOOK.md` (Preserved)
- **Backend Adapter Retention**: `ExnessMT5GatewayAdapter` remains functional in `backend/app/services/exness/mt5_gateway_adapter.py` for administrative and institutional MT5 operations.
