# BITDEX — PHASE 13: AUTHORITATIVE BOTTOM TRADING ACTIVITY PANEL REPORT

**Timestamp:** 2026-11-05T00:18:00Z  
**Host:** Linux Staging Server (`169.58.218.168`)  
**Repository:** `https://github.com/nexuratechpteltd-tech/bitdex-platform`  
**Target File:** `dashboard/src/components/InstitutionalTradingDashboard.tsx`  

---

## 1. Executive Summary

Replacing the former synthetic simulation and ad-hoc trade journal, the **Authoritative Bottom Trading Activity Panel** provides institutional clients with an audited, broker-backed record of positions, orders, executions, and account equity.

---

## 2. 5-Tab Architecture

The panel is structured into five dedicated operational tabs:

### Tab 1: Open Positions
- **Source**: `GET /api/backend/saas/customer/trading/hft/positions`
- **Columns**:
  - `Position ID`: e.g. `POS-DEMO-BTC-01`
  - `Symbol`: Contract name (e.g. `BTCUSDT`)
  - `Direction`: `LONG` (green badge) / `SHORT` (red badge)
  - `Size`: Executed contracts / units
  - `Entry Price`: Execution fill price
  - `Mark Price`: Real-time index price
  - `Unrealized P&L`: Marked-to-market dollar profit/loss
  - `Leverage`: Isolated leverage factor (e.g. `1x`, `3x`)
  - `Stop Loss`: Active protective order price or `STANDBY`
  - `Take Profit`: Target fill price or `STANDBY`
  - `Status`: `OPEN`
- **Empty State**: `"No active open positions on broker account. Controlled validation mode prevents live order dispatch. Positions will appear here when filled."`

### Tab 2: Open Orders
- **Source**: `GET /api/backend/saas/customer/trading/hft/orders`
- **Columns**: `Order ID`, `Symbol`, `Side`, `Type` (`LIMIT GTX`), `Price`, `Quantity`, `Status` (`NEW` / `OPEN` / `PARTIALLY_FILLED`), `Created`.
- **Empty State**: `"No working open orders on broker account. All limit GTX orders will be listed here with live execution state."`

### Tab 3: Closed Trades
- **Source**: `GET /api/backend/saas/customer/trading/overview` (`recent_trades`)
- **Columns**: `Trade ID`, `Symbol`, `Side`, `Quantity`, `Entry Price`, `Exit Price`, `Fee ($)`, `Realized Net P&L`.
- **Empty State**: `"No closed trades recorded for this account. Controlled validation mode prevents live order dispatch. Completed trades will populate here."`

### Tab 4: Trade History
- **Source**: Authoritative journal records
- **Columns**: `Timestamp`, `Trade ID`, `Symbol`, `Side`, `Qty`, `Executed Price`, `Fee`, `Net P&L`.
- **Integrity**: Every record is cryptographically signed and stored in SQLite audit tables.

### Tab 5: Account Overview
- **Source**: `GET /api/backend/saas/customer/trading/hft/account-summary`
- **Telemetry Display**:
  - `Account Identifier`: Authoritative broker account ID (e.g. `FACC-1A8D671544D0`).
  - `Environment`: `DEMO` or `LIVE`.
  - `Authoritative Wallet Balance`: Real settled balance (`$0.00` or funded amount).
  - `Available Margin`: Uncommitted capital for strategy sizing.
  - `Margin In Use`: Total collateral committed across positions.
  - `Total Equity`: Current balance + floating unrealized P&L.
  - `Margin Mode`: `ISOLATED (LEVERAGE CLAMP: 5x)`.
  - `Safety Locks`: `LIVE LOCKED • READ-ONLY`.

---

## 3. Real-Time Telemetry & Zero Fabrication Guarantee

1. **Automatic Polling**: Refreshes asynchronously every 10 seconds alongside the terminal overview.
2. **Manual Refresh**: Dedicated refresh button with spinning state indicator.
3. **Fail-Closed Presentation**: No synthetic fallback data, mock candles, or simulated trades are ever injected when feeds are empty.
