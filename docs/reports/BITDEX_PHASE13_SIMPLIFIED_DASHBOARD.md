# BITDEX — PHASE 13: SIMPLIFIED TRADING TERMINAL & PRE-TRADE WORKFLOW REPORT

**Timestamp:** 2026-11-05T00:17:00Z  
**Host:** Linux Staging Server (`169.58.218.168`)  
**Repository:** `https://github.com/nexuratechpteltd-tech/bitdex-platform`  
**Target File:** `dashboard/src/components/InstitutionalTradingDashboard.tsx`  

---

## 1. Simplified Guided Workflow Design

The redesigned trading dashboard implements a streamlined, linear customer journey consisting of 4 focused operational stages:

```
[ Step 1: Verified Instrument Selection ]
                   │
                   ▼
[ Step 2: Strategy Configuration & Break-Even Math ]
                   │
                   ▼
[ Step 3: Pre-Trade Safety & Netting Checklist ]
                   │
                   ▼
[ Step 4: Controlled Session Arming & Lifecycle ]
```

---

## 2. Top Instrument Selector (Verified Binance Pairs)

### Verified Instruments Row
Positioned prominently at the top of Step 1, a dedicated quick-select bar displays the five authorized institutional Binance instruments:
- `BTCUSDT`
- `ETHUSDT`
- `SOLUSDT`
- `BNBUSDT`
- `ADAUSDT`

### Instrument Card Telemetry
Each instrument displays:
- Real-time market price (USD).
- 24-hour price change percentage (green positive / red negative).
- Data source badge: `"Binance Spot Market Data (Public Feed)"`.
- Real-time tick evaluation status: `"Controlled Validation Mode"`.

Selecting any card immediately updates the strategy context, queries the active database configuration for that symbol, and runs the pre-trade validation gate.

---

## 3. Duplicate Pair Protection (Anti-Hedging & Netting Guard)

### Problem Addressed
Under institutional netting rules, launching an autonomous scalp engine on a contract where open positions or working limit orders already exist can cause accidental over-leverage or unhedged collisions.

### Implementation
A reactive hook evaluates active positions and open orders against the selected pair:
```tsx
const hasDuplicatePair = useMemo(() => {
  if (!selectedPair) return false;
  const hasOpenPos = hftPositions.some(
    (p) => p.symbol === selectedPair && (p.status === "OPEN" || (p.size && p.size > 0))
  );
  const hasOpenOrd = hftOrders.some(
    (o) => o.symbol === selectedPair && (o.status === "NEW" || o.status === "OPEN" || o.status === "PARTIALLY_FILLED")
  );
  return hasOpenPos || hasOpenOrd;
}, [selectedPair, hftPositions, hftOrders]);
```

### Visual Feedback & Enforcement
When `hasDuplicatePair` is `true`:
1. **Warning Card**: An amber warning banner renders across the configuration section:
   > ⚠️ **Duplicate Position / Working Order Warning (`BTCUSDT`)**: An active position or working order already exists on `BTCUSDT` on your broker account. Duplicate execution is blocked by netting protection rules to prevent unhedged directional exposure.
2. **Button Lock**: The "Arm & Start Session" button in Step 4 is disabled:
   `disabled={(activationStatus === "ACTIVE" && !isReady) || sessionActionLoading || hasDuplicatePair}`

---

## 4. Pre-Trade Gate Status Indicators

The Pre-Trade Safety Checklist evaluates 9 independent conditions before allowing session arming:
1. `CAS Symbol Lease Availability`: Verifies symbol exclusivity.
2. `Margin Adequacy`: Displays `"Available: $X.XX | Required: $Y.YY"`. Evaluates [PASS] only if balance covers isolated margin.
3. `Exchange Connection`: Verifies `"Binance Spot Market Data"` profile.
4. `Trading Lock Status`: Confirms staging read-only mode and live trading lock.
5. `Protection Watchdog Kill Switch`: Confirms disarmed emergency halt.
6. `Daily Loss Limit`: Verifies threshold configuration.
7. `Max Open Positions Limit`: Confirms ceiling compliance.
8. `Minimum Grid/Scalp Spacing`: Checks fee-adjusted threshold.
9. `Engine B Coordination`: Validates daemon health.

Status Badges:
- **GREEN**: Gate passed with verified broker condition.
- **RED**: Critical gate failed (blocks execution).
- **AMBER**: Non-critical warning or condition pending user action.
