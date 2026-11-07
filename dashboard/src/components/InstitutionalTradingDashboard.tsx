"use client";

import React, { useEffect, useState, useCallback, useMemo, useRef } from "react";
import {
  ShieldCheck,
  Activity,
  AlertTriangle,
  Cpu,
  TrendingUp,
  TrendingDown,
  Layers,
  Lock,
  RefreshCw,
  Zap,
  CheckCircle2,
  Clock,
  ArrowUpRight,
  ArrowDownRight,
  Sliders,
  DollarSign,
  Scale,
  Ban,
  AlertCircle,
  Eye,
  BarChart3,
  Search,
  Check,
  X,
  Play,
  Square,
  ChevronDown,
  ChevronUp,
  Info,
  ListFilter,
  ArrowRight
} from "lucide-react";
import ProtectionCenter from "./ProtectionCenter";

interface TradingOverviewData {
  account: {
    account_id: string;
    wallet_balance: number;
    available_balance: number;
    unrealized_pnl: number;
    margin_balance: number;
    engine_b_enabled: number;
    trading_locked: number;
    environment: string;
    is_provisioned?: boolean;
  };
  engine_a: {
    name: string;
    strategy: string;
    status: string;
    active_pairs: string[];
    live_locked: boolean;
    allocated_capital_usd: number;
  };
  engine_b: {
    name: string;
    strategy: string;
    status: string;
    enabled: boolean;
    operational?: boolean;
    operational_status?: string;
    live_locked: boolean;
    parameters: {
      donchian_period: number;
      adx_threshold: number;
      rvol_threshold: number;
      max_leverage: number;
      order_type: string;
      fill_timeout_seconds: number;
    };
    active_leases_count: number;
    status_description?: string;
  };
  risk: {
    aggregate_exposure_pct: number;
    max_exposure_cap_pct: number;
    max_leverage_clamp: number;
    naked_positions_count: number;
    stop_loss_coverage_pct?: number | null;
    circuit_breaker_active: boolean;
    live_trading_locked: boolean;
    read_only_mode: boolean;
  };
  active_leases: Array<{
    symbol: string;
    engine_id: string;
    lease_token: string;
    acquired_at: string;
    expires_at: string;
    status: string;
  }>;
  positions: Array<{
    symbol: string;
    position_side: string;
    quantity: number;
    entry_price: number;
    mark_price: number;
    unrealized_pnl: number;
    margin_type: string;
    leverage: number;
    stop_exchange_order_id?: number | null;
  }>;
  recent_trades: Array<{
    trade_id: string;
    symbol: string;
    side: string;
    quantity: number;
    entry_price: number;
    exit_price: number;
    realized_pnl: number;
    fee_usd: number;
    created_at: string;
  }>;
}

interface ConnectedAccount {
  account_id: string;
  source: string;
  exchange: string;
  platform?: string;
  environment: "REAL" | "DEMO";
  environment_label: string;
  masked_id: string;
  connection_status: string;
  connected: boolean;
  currency: string;
  available_balance: number | null;
  equity: number | null;
  last_connected_at: string | null;
  display_label: string;
  real_consent_recorded: boolean | null;
}

interface HftPair {
  symbol: string;
  price: number;
  quote_volume_24h: number;
  spread_usd: number;
  spread_ratio: number;
  spread_bps: number;
  depth_usd?: number;
  funding_rate: number;
  price_change_pct_24h: number;
  rank_score: number;
  base_asset: string;
  quote_asset: string;
}

interface RejectedPair {
  symbol: string;
  reason: string;
}

interface StrategyConfig {
  config_id?: string;
  symbol: string;
  direction: "AUTO" | "LONG_ONLY" | "SHORT_ONLY";
  margin_allocation_usd: number;
  leverage: number;
  net_profit_target_pct: number;
  max_loss_pct: number;
  max_holding_duration_seconds: number;
  session_mode: "SINGLE_CYCLE" | "CONTINUOUS";
  daily_loss_limit_usd: number;
  max_daily_trades: number;
  status?: string;
}


interface HftPositionItem {
  position_id: string;
  symbol: string;
  direction: "LONG" | "SHORT";
  size: number;
  entry_price: number;
  mark_price: number;
  unrealized_pnl: number;
  realized_pnl?: number;
  isolated_margin?: number;
  leverage: number;
  status: "OPEN" | "CLOSED";
  stop_loss_price?: number | null;
  take_profit_price?: number | null;
  opened_at?: string;
  source?: string;
}

interface HftOrderItem {
  order_id: string;
  symbol: string;
  side: "BUY" | "SELL";
  order_type: string;
  price: number;
  quantity: number;
  status: "NEW" | "OPEN" | "PARTIALLY_FILLED" | "FILLED" | "CANCELLED" | "REJECTED";
  executed_qty?: number;
  created_at?: string;
}

interface HftAccountSummaryData {
  account_id: string;
  environment: string;
  wallet_balance_usd: number;
  available_balance_usd: number;
  unrealized_pnl_usd: number;
  margin_balance_usd: number;
  equity_usd: number;
  margin_type: string;
  default_leverage: number;
  max_leverage_limit: number;
  kill_switch_active: boolean;
  engine_b_enabled: boolean;
}

interface ChecklistItem {
  id: string;
  name: string;
  passed: boolean;
  critical: boolean;
  detail: string;
}


// Safe numeric formatting helpers to prevent TypeError crashes on undefined/null metrics
function safeNum(val: any, decimals = 2, fallback = "0.00"): string {
  if (val === null || val === undefined || val === "") return fallback;
  const n = Number(val);
  return isNaN(n) ? fallback : n.toFixed(decimals);
}

function safeFormatPrice(val: any, fallback = "---"): string {
  if (val === null || val === undefined || val === "") return fallback;
  const n = Number(val);
  if (isNaN(n)) return fallback;
  if (n >= 1) {
    return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  return n.toFixed(4);
}

export default function InstitutionalTradingDashboard({
  token,
  className = "",
}: {
  token?: string;
  className?: string;
}) {
  const [data, setData] = useState<TradingOverviewData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ type: "success" | "error" | "info"; message: string } | null>(null);

  // Dynamic Pairs State
  const [hftPairs, setHftPairs] = useState<HftPair[]>([]);
  const [rejectedPairs, setRejectedPairs] = useState<RejectedPair[]>([]);
  const [loadingPairs, setLoadingPairs] = useState<boolean>(false);
  const [pairSearch, setPairSearch] = useState<string>("");
  const [selectedPair, setSelectedPair] = useState<string>("BTCUSDT");
  const [showRejected, setShowRejected] = useState<boolean>(false);

  // Section J: Connected exchange & account selector
  const [connectedAccounts, setConnectedAccounts] = useState<ConnectedAccount[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string>(() =>
    typeof window !== "undefined" ? window.localStorage.getItem("bitdex_hft_account") || "" : ""
  );
  const [accountsError, setAccountsError] = useState<string | null>(null);
  const [consentModalOpen, setConsentModalOpen] = useState<boolean>(false);
  const [consentChecked, setConsentChecked] = useState<boolean>(false);
  const [stepUpPassword, setStepUpPassword] = useState<string>("");
  const [consentError, setConsentError] = useState<string | null>(null);
  const [consentBusy, setConsentBusy] = useState<boolean>(false);
  const [pendingAction, setPendingAction] = useState<null | "CONFIG" | "START">(null);

  // Strategy Configuration State
  const [isConfigModalOpen, setIsConfigModalOpen] = useState<boolean>(false);
  const [strategyConfig, setStrategyConfig] = useState<StrategyConfig>({
    symbol: "BTCUSDT",
    direction: "AUTO",
    margin_allocation_usd: 50.0,
    leverage: 3,
    net_profit_target_pct: 0.60,
    max_loss_pct: 0.90,
    max_holding_duration_seconds: 900,
    session_mode: "SINGLE_CYCLE",
    daily_loss_limit_usd: 20.0,
    max_daily_trades: 10,
    status: "NOT_CONFIGURED"
  });
  const [savingConfig, setSavingConfig] = useState<boolean>(false);

  // Pre-Trade Validation Checklist State
  const [checklist, setChecklist] = useState<ChecklistItem[]>([]);
  const [isReady, setIsReady] = useState<boolean>(false);
  const [validating, setValidating] = useState<boolean>(false);

  // Session Control State
  const [sessionActionLoading, setSessionActionLoading] = useState<boolean>(false);
  const [sessionState, setSessionState] = useState<
    "NOT_CONFIGURED" | "CONFIGURED" | "VALIDATING" | "READY" | "ACTIVE" | "STOPPING" | "STOPPED" | "FAILED"
  >("NOT_CONFIGURED");

  // ─── Phase 2: $20.00 USD One-Time HFT Account Activation State ───────────
  const [activationStatus, setActivationStatus] = useState<string>("NOT_ACTIVATED");
  const [activationInfo, setActivationInfo] = useState<any>(null);
  const [isActivationModalOpen, setIsActivationModalOpen] = useState<boolean>(false);
  const [activationProvider, setActivationProvider] = useState<string>("BINANCE_PAY");
  const [activationCheckoutData, setActivationCheckoutData] = useState<any>(null);
  const [activationBusy, setActivationBusy] = useState<boolean>(false);

  const getAuthToken = useCallback(() => {
    return (
      token ||
      (typeof window !== "undefined"
        ? localStorage.getItem("bitdex_auth_token") ||
          localStorage.getItem("tauric_token") ||
          localStorage.getItem("tauric_session_token") ||
          ""
        : "")
    );
  }, [token]);

  // ─── Authoritative Broker-Backed Activity & Telemetry State ───────────────
  const [bottomTab, setBottomTab] = useState<"POSITIONS" | "OPEN_ORDERS" | "CLOSED_TRADES" | "HISTORY" | "ACCOUNT">("POSITIONS");
  const [hftPositions, setHftPositions] = useState<HftPositionItem[]>([]);
  const [hftOrders, setHftOrders] = useState<HftOrderItem[]>([]);
  const [hftAccountSummary, setHftAccountSummary] = useState<HftAccountSummaryData | null>(null);
  const [loadingBottomData, setLoadingBottomData] = useState<boolean>(false);

  // Fetch Customer $20 HFT Activation Status
  const fetchActivationStatus = useCallback(async () => {
    try {
      const authToken = getAuthToken();
      if (!authToken) return;
      const res = await fetch("/api/backend/saas/customer/hft/activation/status", {
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer " + authToken,
        },
      });
      if (res.ok) {
        const json = await res.json();
        if (json.activation) {
          setActivationInfo(json.activation);
          setActivationStatus(json.activation.activation_status || "NOT_ACTIVATED");
        }
      }
    } catch (err) {
      console.warn("Could not fetch HFT activation status:", err);
    }
  }, [getAuthToken]);

  // Initiate $20.00 USD Activation Checkout
  const handleInitiateActivationCheckout = async () => {
    setActivationBusy(true);
    setFeedback(null);
    try {
      const authToken = getAuthToken();
      const res = await fetch("/api/backend/saas/customer/hft/activation/checkout", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(authToken ? { Authorization: "Bearer " + authToken } : {}),
        },
        body: JSON.stringify({ provider: activationProvider }),
      });
      const json = await res.json();
      if (!res.ok) {
        const msg = typeof json.detail === "object" ? json.detail.message : json.detail;
        throw new Error(msg || "Failed to initiate $20.00 USD activation checkout.");
      }
      if (json.status === "ALREADY_ACTIVE") {
        setActivationStatus("ACTIVE");
        setActivationInfo(json.activation);
        setIsActivationModalOpen(false);
        setFeedback({ type: "success", message: "Your BITDEX HFT account is already activated." });
        return;
      }
      setActivationCheckoutData(json.checkout);
      if (json.activation) {
        setActivationInfo(json.activation);
        setActivationStatus(json.activation.activation_status);
      }
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message || "Activation checkout error" });
    } finally {
      setActivationBusy(false);
    }
  };

  // Complete & Verify Signed $20.00 USD Activation Payment
  const handleCompleteActivationPayment = async () => {
    if (!activationCheckoutData) return;
    setActivationBusy(true);
    setFeedback(null);
    try {
      const authToken = getAuthToken();
      const res = await fetch("/api/backend/saas/customer/hft/activation/verify", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(authToken ? { Authorization: "Bearer " + authToken } : {}),
        },
        body: JSON.stringify({
          payment_reference: activationCheckoutData.payment_reference,
          amount: 20.0,
          currency: "USD",
          signature: activationCheckoutData.verification_signature,
          provider: activationCheckoutData.provider,
        }),
      });
      const json = await res.json();
      if (!res.ok) {
        const msg = typeof json.detail === "object" ? json.detail.message : json.detail;
        throw new Error(msg || "Payment verification failed.");
      }
      if (json.activation) {
        setActivationInfo(json.activation);
        setActivationStatus(json.activation.activation_status || "ACTIVE");
      } else {
        setActivationStatus("ACTIVE");
      }
      setActivationCheckoutData(null);
      setIsActivationModalOpen(false);
      setFeedback({
        type: "success",
        message: "Account Activated ($20.00 USD verified). High-Frequency Trading configuration and execution controls are now unlocked.",
      });
      await runValidation(selectedPair);
      await fetchOverview();
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message || "Payment verification failed" });
    } finally {
      setActivationBusy(false);
    }
  };

  // Fetch Authoritative Bottom Panel Activity Data
  const fetchBottomData = useCallback(async () => {
    try {
      setLoadingBottomData(true);
      const authToken = getAuthToken();
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        ...(authToken ? { Authorization: "Bearer " + authToken } : {}),
      };

      if (!selectedAccountId) {
        setHftPositions([]);
        setHftOrders([]);
        return;
      }
      const q = `?account_id=${encodeURIComponent(selectedAccountId)}`;
      const [posRes, ordRes, accRes] = await Promise.all([
        fetch(`/api/backend/saas/customer/trading/hft/positions${q}`, { headers }),
        fetch(`/api/backend/saas/customer/trading/hft/orders${q}`, { headers }),
        fetch(`/api/backend/saas/customer/trading/hft/account-summary${q}`, { headers }),
      ]);
      // Never keep data from a previously selected account
      setHftPositions([]);
      setHftOrders([]);

      if (posRes.ok) {
        const posJson = await posRes.json();
        if (posJson.open_positions && Array.isArray(posJson.open_positions)) {
          setHftPositions(posJson.open_positions);
        }
      }
      if (ordRes.ok) {
        const ordJson = await ordRes.json();
        if (ordJson.open_orders && Array.isArray(ordJson.open_orders)) {
          setHftOrders(ordJson.open_orders);
        }
      }
      if (accRes.ok) {
        const accJson = await accRes.json();
        if (accJson.account_id) {
          setHftAccountSummary(accJson);
        }
      }
    } catch (err) {
      console.warn("Could not fetch HFT bottom activity data:", err);
    } finally {
      setLoadingBottomData(false);
    }
  }, [getAuthToken, selectedAccountId]);

  // 1. Fetch Trading Overview
  const fetchOverview = useCallback(async () => {
    try {
      const authToken = getAuthToken();
      const res = await fetch("/api/backend/saas/customer/trading/overview", {
        headers: {
          "Content-Type": "application/json",
          ...(authToken ? { Authorization: "Bearer " + authToken } : {}),
        },
      });
      if (!res.ok) throw new Error(`Overview fetch failed (${res.status})`);
      const json = await res.json();
      if (json.status === "SUCCESS") {
        setData(json);
        setError(null);
      } else {
        setError(json.error || "Failed to load trading overview");
      }
    } catch (err: any) {
      setError(err.message || "Failed to connect to backend");
    } finally {
      setLoading(false);
    }
  }, [getAuthToken]);

  // 2. Fetch HFT Eligible Pairs
  const fetchHftPairs = useCallback(async () => {
    try {
      setLoadingPairs(true);
      const authToken = getAuthToken();
      const res = await fetch("/api/backend/saas/customer/trading/hft/pairs", {
        headers: {
          "Content-Type": "application/json",
          ...(authToken ? { Authorization: "Bearer " + authToken } : {}),
        },
      });
      if (res.ok) {
        const json = await res.json();
        if (json.pairs && Array.isArray(json.pairs)) {
          setHftPairs(json.pairs);
          if (json.pairs.length > 0 && !selectedPair) {
            setSelectedPair(json.pairs[0].symbol);
          }
        }
        if (json.rejected_pairs && Array.isArray(json.rejected_pairs)) {
          setRejectedPairs(json.rejected_pairs);
        }
      }
    } catch {
      // Non-blocking
    } finally {
      setLoadingPairs(false);
    }
  }, [getAuthToken, selectedPair]);

  // 3. Fetch Strategy Configuration for Selected Pair
  const fetchStrategyConfig = useCallback(async (sym: string) => {
    try {
      const authToken = getAuthToken();
      const res = await fetch(`/api/backend/saas/customer/trading/hft/config?symbol=${sym}`, {
        headers: {
          "Content-Type": "application/json",
          ...(authToken ? { Authorization: "Bearer " + authToken } : {}),
        },
      });
      if (res.ok) {
        const json = await res.json();
        if (json.config) {
          setStrategyConfig(json.config);
          if (json.config.status === "ACTIVE") {
            setSessionState("ACTIVE");
          } else if (json.config.status === "CONFIGURED") {
            setSessionState("CONFIGURED");
          } else {
            setSessionState("NOT_CONFIGURED");
          }
        }
      }
    } catch {
      // Non-blocking
    }
  }, [getAuthToken]);

  // 4. Run Pre-Trade Validation Checklist
  const runValidation = useCallback(async (sym: string) => {
    try {
      setValidating(true);
      const authToken = getAuthToken();
      const acctQ = selectedAccountId ? `&account_id=${encodeURIComponent(selectedAccountId)}` : "";
      const res = await fetch(`/api/backend/saas/customer/trading/hft/validation?symbol=${sym}${acctQ}`, {
        headers: {
          "Content-Type": "application/json",
          ...(authToken ? { Authorization: "Bearer " + authToken } : {}),
        },
      });
      if (res.ok) {
        const json = await res.json();
        setChecklist(json.checklist || []);
        setIsReady(Boolean(json.is_ready));
        if (json.session_active) {
          setSessionState("ACTIVE");
        } else if (json.is_ready) {
          setSessionState("READY");
        } else if (json.strategy_configured) {
          setSessionState("CONFIGURED");
        } else {
          setSessionState("NOT_CONFIGURED");
        }
      }
    } catch {
      // Non-blocking
    } finally {
      setValidating(false);
    }
  }, [getAuthToken, selectedAccountId]);

  const fetchConnectedAccounts = useCallback(async () => {
    try {
      const authToken = getAuthToken();
      const res = await fetch("/api/backend/saas/customer/trading/hft/connected-accounts", {
        headers: { ...(authToken ? { Authorization: "Bearer " + authToken } : {}) },
      });
      if (!res.ok) throw new Error(`Could not load connected accounts (${res.status})`);
      const json = await res.json();
      const list: ConnectedAccount[] = json.accounts || [];
      setConnectedAccounts(list);
      setAccountsError(null);
      setSelectedAccountId((cur) => (cur && list.some((a) => a.account_id === cur) ? cur : (list.length > 0 ? list[0].account_id : "")));
    } catch (err: any) {
      setAccountsError(err.message || "Could not load connected accounts");
    }
  }, [getAuthToken]);

  const selectedAccount = useMemo(
    () => connectedAccounts.find((a) => a.account_id === selectedAccountId) || null,
    [connectedAccounts, selectedAccountId]
  );

  useEffect(() => {
    fetchConnectedAccounts();
  }, [fetchConnectedAccounts]);

  useEffect(() => {
    if (typeof window !== "undefined") window.localStorage.setItem("bitdex_hft_account", selectedAccountId);
    setHftAccountSummary(null);
    setConsentChecked(false);
    setStepUpPassword("");
    setConsentError(null);
    const newlySelected = connectedAccounts.find((a) => a.account_id === selectedAccountId);
    if (newlySelected && newlySelected.environment === "REAL" && !newlySelected.real_consent_recorded) {
      setConsentModalOpen(true);
    }
    // Refresh pre-trade checklist immediately when selected account changes
    if (selectedPair) {
      runValidation(selectedPair);
    }
  }, [selectedAccountId, connectedAccounts, selectedPair, runValidation]);

  // Gate any configure/arm action on account selection, connectivity and REAL consent
  const guardAccountAction = (action: "CONFIG" | "START"): boolean => {
    if (!selectedAccount) {
      setFeedback({ type: "error", message: "Select a connected Exness trading account before configuring or arming a session." });
      return false;
    }
    if (!selectedAccount.connected) {
      setFeedback({ type: "error", message: `${selectedAccount.display_label} is not verified (${selectedAccount.connection_status}). Execution disabled.` });
      return false;
    }
    if (selectedAccount.environment === "REAL" && !selectedAccount.real_consent_recorded) {
      setPendingAction(action);
      setConsentChecked(false);
      setStepUpPassword("");
      setConsentError(null);
      setConsentModalOpen(true);
      return false;
    }
    return true;
  };

  const submitRealConsent = async () => {
    if (!selectedAccount || !consentChecked || !stepUpPassword.trim()) return;
    setConsentBusy(true);
    setConsentError(null);
    try {
      const authToken = getAuthToken();
      const res = await fetch("/api/backend/saas/customer/trading/hft/consent/real-trading", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(authToken ? { Authorization: "Bearer " + authToken } : {}) },
        body: JSON.stringify({
          account_id: selectedAccount.account_id,
          confirmed: true,
          consent_version: "REAL-CONSENT-v2",
          step_up_password: stepUpPassword.trim(),
        }),
      });
      const json = await res.json();
      if (!res.ok) {
        const msg = typeof json.detail === "string" ? json.detail : "Step-up authentication or consent recording failed.";
        setConsentError(msg);
        throw new Error(msg);
      }
      setConnectedAccounts((prev) =>
        prev.map((a) => (a.account_id === selectedAccount.account_id ? { ...a, real_consent_recorded: true } : a))
      );
      setConsentModalOpen(false);
      setStepUpPassword("");
      setFeedback({
        type: "info",
        message: "Voluntary Real-account consent recorded (REAL-CONSENT-v2). Live execution remains locked by platform safety controls.",
      });
      if (pendingAction === "CONFIG") setIsConfigModalOpen(true);
      setPendingAction(null);
      if (selectedPair) runValidation(selectedPair);
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message });
    } finally {
      setConsentBusy(false);
    }
  };

  useEffect(() => {
    fetchOverview();
    fetchHftPairs();
    fetchActivationStatus();
    fetchBottomData();
    const interval = setInterval(() => {
      fetchOverview();
      fetchBottomData();
    }, 10000);
    return () => clearInterval(interval);
  }, [fetchOverview, fetchHftPairs, fetchActivationStatus, fetchBottomData]);

  useEffect(() => {
    if (selectedPair) {
      fetchStrategyConfig(selectedPair);
      runValidation(selectedPair);
    }
  }, [selectedPair, fetchStrategyConfig, runValidation]);

  // Filtered eligible pairs
  const filteredPairs = useMemo(() => {
    if (!pairSearch.trim()) return hftPairs;
    const q = pairSearch.toUpperCase();
    return hftPairs.filter((p) => p.symbol.includes(q) || p.base_asset.includes(q));
  }, [hftPairs, pairSearch]);

  const activePairObj = useMemo(() => {
    return hftPairs.find((p) => p.symbol === selectedPair) || hftPairs[0] || null;
  }, [hftPairs, selectedPair]);

  // Duplicate Pair Protection Check
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

  // Live Break-Even Calculator for Strategy Config
  const breakEvenMath = useMemo(() => {
    const margin = strategyConfig.margin_allocation_usd;
    const lev = strategyConfig.leverage;
    const notional = margin * lev;
    const makerFeeRatePct = 0.02; // Binance USD(S)-M VIP 0 Maker Tier (0.020%)
    const takerFeeRatePct = 0.05; // Binance USD(S)-M VIP 0 Taker Tier (0.050%)
    const roundTripMakerFeePct = makerFeeRatePct * 2; // 0.040%
    const bufferPct = 0.01; // 0.010% funding / slippage allowance
    const totalFrictionPct = roundTripMakerFeePct + bufferPct; // 0.050%
    const contingentStopFrictionPct = makerFeeRatePct + takerFeeRatePct + bufferPct; // 0.080%
    const targetPct = strategyConfig.net_profit_target_pct;
    const netReturnPct = Math.max(0, targetPct - totalFrictionPct);
    const estDollarProfit = (notional * (netReturnPct / 100));
    const estFeeDollar = notional * (totalFrictionPct / 100);

    return {
      notional,
      makerFeeRatePct,
      takerFeeRatePct,
      roundTripMakerFeePct,
      contingentStopFrictionPct,
      totalFrictionPct,
      requiredMovePct: totalFrictionPct,
      netReturnPct,
      estDollarProfit,
      estFeeDollar
    };
  }, [strategyConfig.margin_allocation_usd, strategyConfig.leverage, strategyConfig.net_profit_target_pct]);

  // Save Strategy Config Handler
  const handleSaveConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingConfig(true);
    setFeedback(null);
    try {
      const authToken = getAuthToken();
      const res = await fetch("/api/backend/saas/customer/trading/hft/config", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(authToken ? { Authorization: "Bearer " + authToken } : {}),
        },
        body: JSON.stringify({
          symbol: selectedPair,
          direction: strategyConfig.direction,
          margin_allocation_usd: Number(strategyConfig.margin_allocation_usd),
          leverage: Number(strategyConfig.leverage),
          net_profit_target_pct: Number(strategyConfig.net_profit_target_pct),
          max_loss_pct: Number(strategyConfig.max_loss_pct),
          max_holding_duration_seconds: Number(strategyConfig.max_holding_duration_seconds),
          session_mode: strategyConfig.session_mode,
          daily_loss_limit_usd: Number(strategyConfig.daily_loss_limit_usd),
          max_daily_trades: Number(strategyConfig.max_daily_trades)
        }),
      });

      const resJson = await res.json();
      if (!res.ok) {
        if (res.status === 403 && resJson.detail?.error === "ACCOUNT_ACTIVATION_REQUIRED") {
          setIsConfigModalOpen(false);
          setIsActivationModalOpen(true);
          throw new Error(resJson.detail.message || "One-time $20.00 USD Account Activation required.");
        }
        const errMsg = typeof resJson.detail === "object" ? resJson.detail.message : resJson.detail;
        throw new Error(errMsg || "Failed to save strategy configuration.");
      }

      setFeedback({
        type: "success",
        message: `Strategy configuration for ${selectedPair} saved. Review pre-trade checklist before arming.`
      });
      setIsConfigModalOpen(false);
      await runValidation(selectedPair);
      await fetchOverview();
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message });
    } finally {
      setSavingConfig(false);
    }
  };

  // Start Session Handler
  const handleStartSession = async () => {
    setSessionActionLoading(true);
    setFeedback(null);
    try {
      const authToken = getAuthToken();
      const res = await fetch("/api/backend/saas/customer/trading/hft/session/start", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(authToken ? { Authorization: "Bearer " + authToken } : {}),
        },
        body: JSON.stringify({ symbol: selectedPair }),
      });

      const resJson = await res.json();
      if (!res.ok) {
        if (res.status === 403 && resJson.detail?.error === "ACCOUNT_ACTIVATION_REQUIRED") {
          setIsActivationModalOpen(true);
          throw new Error(resJson.detail.message || "One-time $20.00 USD Account Activation required.");
        }
        const errMsg = typeof resJson.detail === "object" ? resJson.detail.message : resJson.detail;
        throw new Error(errMsg || "Failed to arm HFT session.");
      }

      setFeedback({
        type: "info",
        message: resJson.message || `HFT session for ${selectedPair} ARMED in Controlled Testnet Validation Mode.`
      });
      await runValidation(selectedPair);
      await fetchOverview();
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message });
    } finally {
      setSessionActionLoading(false);
    }
  };

  // Stop Session Handler
  const handleStopSession = async () => {
    setSessionActionLoading(true);
    setFeedback(null);
    try {
      const authToken = getAuthToken();
      const res = await fetch("/api/backend/saas/customer/trading/hft/session/stop", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(authToken ? { Authorization: "Bearer " + authToken } : {}),
        },
        body: JSON.stringify({ symbol: selectedPair }),
      });

      const resJson = await res.json();
      if (!res.ok) {
        throw new Error(resJson.detail || "Failed to stop HFT session.");
      }

      setSessionState("STOPPED");
      setFeedback({
        type: "info",
        message: resJson.message || `HFT session for ${selectedPair} disarmed and stopped cleanly.`
      });
      await runValidation(selectedPair);
      await fetchOverview();
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message });
    } finally {
      setSessionActionLoading(false);
    }
  };

  if (loading && !data) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[300px] space-y-4">
        <RefreshCw className="w-8 h-8 text-[#00E5FF] animate-spin" />
        <span className="text-xs font-mono text-[#94A3B8]">Loading High-Frequency Trading Terminal...</span>
      </div>
    );
  }

  const account = data?.account;
  const positions = data?.positions || [];
  const recentTrades = data?.recent_trades || [];

  return (
    <div className={`space-y-6 max-w-full overflow-hidden ${className}`}>
      {/* ─── FEEDBACK NOTIFICATION BANNER ─────────────────────────────────── */}
      {feedback && (
        <div
          className={`p-4 rounded-xl border flex items-center justify-between gap-3 text-xs font-mono transition-all ${
            feedback.type === "success"
              ? "bg-[#10B981]/15 border-[#10B981]/30 text-[#10B981]"
              : feedback.type === "error"
              ? "bg-[#F6465D]/15 border-[#F6465D]/30 text-[#F6465D]"
              : "bg-[#00E5FF]/15 border-[#00E5FF]/30 text-[#00E5FF]"
          }`}
        >
          <div className="flex items-center gap-2 min-w-0">
            {feedback.type === "success" ? (
              <CheckCircle2 className="w-4 h-4 shrink-0" />
            ) : feedback.type === "error" ? (
              <AlertTriangle className="w-4 h-4 shrink-0" />
            ) : (
              <Info className="w-4 h-4 shrink-0" />
            )}
            <span className="truncate">{feedback.message}</span>
          </div>
          <button
            type="button"
            onClick={() => setFeedback(null)}
            className="text-[#94A3B8] hover:text-white shrink-0 cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* ─── TERMINAL HEADER & ENVIRONMENT SAFEGUARDS ───────────────────────── */}
      <div className="p-4 sm:p-5 rounded-2xl bg-[#121218] border border-[#272735] flex flex-wrap items-center justify-between gap-4 shadow-lg">
        <div className="space-y-1 min-w-0">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-[#00E5FF]/10 border border-[#00E5FF]/30 flex items-center justify-center text-[#00E5FF] shrink-0">
              <Zap className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-base sm:text-lg font-bold text-white font-mono flex items-center gap-2">
                HIGH-FREQUENCY TRADING (USDⓈ-M FUTURES)
                <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-cyan-950/60 text-cyan-400 border border-cyan-500/30">
                  GTX Post-Only
                </span>
              </h2>
              <p className="text-xs text-[#94A3B8] font-mono">
                Sub-second momentum scalper · Triple-filtered breakout regime · Atomic symbol mutual locks
              </p>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {activationStatus === "ACTIVE" ? (
            <div
              id="hft-activation-badge"
              data-status="ACTIVE"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-[#10B981]/15 border border-[#10B981]/40 text-xs font-mono font-bold text-[#10B981]"
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>HFT ACTIVATED ($20 VERIFIED)</span>
            </div>
          ) : (
            <button
              type="button"
              id="hft-activation-badge"
              data-status={activationStatus}
              onClick={() => setIsActivationModalOpen(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-amber-500/15 hover:bg-amber-500/25 border border-amber-500/40 text-xs font-mono font-bold text-amber-400 cursor-pointer transition-all"
            >
              <Lock className="w-3.5 h-3.5" />
              <span>UNACTIVATED — ACTIVATE HFT ($20.00)</span>
            </button>
          )}
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-[#10B981]/10 border border-[#10B981]/30 text-xs font-mono text-[#10B981]">
            <span className="w-2 h-2 rounded-full bg-[#10B981] animate-pulse" />
            <span>Execution Gate: Standby Validation</span>
          </div>

          <button
            type="button"
            onClick={() => {
              fetchOverview();
              fetchHftPairs();
              if (selectedPair) runValidation(selectedPair);
            }}
            className="p-2 rounded-lg bg-[#181822] hover:bg-[#272735] border border-[#272735] text-[#94A3B8] hover:text-white transition-all cursor-pointer"
            title="Refresh All Feeds"
          >
            <RefreshCw className={`w-4 h-4 ${loadingPairs || validating ? "animate-spin text-[#00E5FF]" : ""}`} />
          </button>
        </div>
      </div>

      {/* ─── INSTITUTIONAL RISK & PROTECTION CENTER (DYNAMIC) ───────────────── */}
      <ProtectionCenter token={token} />

      {/* ─── CONNECTED EXCHANGE & ACCOUNT SELECTOR (Section J) ─────────────── */}
      <div id="hft-account-selector" className="p-4 sm:p-5 rounded-2xl bg-[#121218] border border-[#272735] space-y-3 shadow-lg font-mono">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <label htmlFor="hft-account-select" className="text-xs font-bold text-white uppercase tracking-wide">Trading Account</label>
          <button type="button" onClick={fetchConnectedAccounts} className="text-[10px] text-[#94A3B8] hover:text-white flex items-center gap-1 cursor-pointer">
            <RefreshCw className="w-3 h-3" /> Refresh accounts
          </button>
        </div>
        <select
          id="hft-account-select"
          value={selectedAccountId}
          onChange={(e) => setSelectedAccountId(e.target.value)}
          className="w-full bg-[#0B0E11] border border-[#272735] rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-[#00E5FF]"
        >
          <option value="">
            {connectedAccounts.length === 0
              ? "NO VERIFIED TRADING ACCOUNTS CONNECTED"
              : "— Select a verified Exness trading account —"}
          </option>
          {connectedAccounts.filter(a => a.environment === "DEMO").length > 0 && (
            <optgroup label="DEMO ACCOUNTS (SIMULATION / TRIAL)">
              {connectedAccounts.filter(a => a.environment === "DEMO").map((a) => (
                <option key={a.account_id} value={a.account_id}>
                  {a.display_label} [{a.platform || "MT5"}] · {a.connected ? "VERIFIED" : a.connection_status}
                  {typeof a.available_balance === "number" && !isNaN(a.available_balance) ? ` · $${a.available_balance.toFixed(2)} ${a.currency}` : ""}
                </option>
              ))}
            </optgroup>
          )}
          {connectedAccounts.filter(a => a.environment === "REAL").length > 0 && (
            <optgroup label="REAL ACCOUNTS (LIVE TRADING - STRICT CONSENT REQUIRED)">
              {connectedAccounts.filter(a => a.environment === "REAL").map((a) => (
                <option key={a.account_id} value={a.account_id}>
                  {a.display_label} [{a.platform || "EXNESS_TERMINAL"}] · {a.connected ? "VERIFIED" : a.connection_status}
                  {typeof a.available_balance === "number" && !isNaN(a.available_balance) ? ` · $${a.available_balance.toFixed(2)} ${a.currency}` : ""}
                </option>
              ))}
            </optgroup>
          )}
        </select>
        {accountsError && <div className="text-xs text-[#F6465D]">{accountsError}</div>}
        {connectedAccounts.length === 0 && !accountsError && (
          <div className="p-3 rounded-xl bg-[#0B0E11] border border-[#272735] text-xs text-[#94A3B8] flex items-center justify-between gap-2 flex-wrap">
            <span className="font-bold text-amber-400">NO VERIFIED TRADING ACCOUNTS CONNECTED</span>
            <span className="text-[11px] text-[#64748B]">
              Attach your Exness API credentials in Connected Accounts to enable HFT account selection.
            </span>
          </div>
        )}
        {selectedAccount && (
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2 text-[11px]">
            {[
              ["Exchange", selectedAccount.exchange],
              ["Platform", selectedAccount.platform || (selectedAccount.environment === "DEMO" ? "MT5" : "EXNESS_TERMINAL")],
              ["Environment", selectedAccount.environment],
              ["Account", selectedAccount.masked_id],
              ["Status", selectedAccount.connected ? "CONNECTED" : selectedAccount.connection_status],
              ["Currency", selectedAccount.currency],
              ["Available", typeof selectedAccount.available_balance === "number" && !isNaN(selectedAccount.available_balance) ? `$${selectedAccount.available_balance.toFixed(2)}` : "Not retrieved"],
              ["Equity", typeof selectedAccount.equity === "number" && !isNaN(selectedAccount.equity) ? `$${selectedAccount.equity.toFixed(2)}` : "Not retrieved"],
            ].map(([k, v]) => (
              <div key={k} className="p-2 rounded-lg bg-[#0B0E11] border border-[#272735]">
                <div className="text-[#64748B] uppercase text-[9px]">{k}</div>
                <div className={`font-bold truncate ${k === "Environment" && v === "REAL" ? "text-[#F6465D]" : k === "Status" && v !== "CONNECTED" ? "text-amber-400" : "text-white"}`}>{v}</div>
              </div>
            ))}
          </div>
        )}
        {selectedAccount && !selectedAccount.connected && (
          <div className="p-2.5 rounded-lg bg-[#F6465D]/10 border border-[#F6465D]/30 text-xs text-[#F6465D] flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            This account could not be verified ({selectedAccount.connection_status}). Execution is disabled for this account.
          </div>
        )}
        {selectedAccount?.environment === "REAL" && (
          <div className="p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-xs text-amber-400 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            REAL account selected — real funds. {selectedAccount.real_consent_recorded ? "Consent on record." : "Explicit consent is required before configuring or arming."}
          </div>
        )}
        {hasDuplicatePair && selectedAccount && (
          <div className="p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-xs text-amber-400 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            {selectedPair} already has an open position or working order on {selectedAccount.masked_id}.
          </div>
        )}
      </div>

      {/* ─── STEP 1: DYNAMIC BINANCE USD(S)-M PAIR DISCOVERY ─────────────────── */}
      <div className="p-4 sm:p-5 rounded-2xl bg-[#121218] border border-[#272735] space-y-4 shadow-lg">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#272735] pb-3">
          <div className="flex items-center gap-2 font-mono">
            <span className="w-5 h-5 rounded-full bg-[#00E5FF]/20 text-[#00E5FF] text-xs font-bold flex items-center justify-center">
              1
            </span>
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">
              Select Futures Contract ({filteredPairs.length} Qualified Candidates)
            </h3>
          </div>

          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="w-3.5 h-3.5 text-[#94A3B8] absolute left-2.5 top-2.5" />
              <input
                type="text"
                value={pairSearch}
                onChange={(e) => setPairSearch(e.target.value)}
                placeholder="Search contract..."
                className="pl-8 pr-3 py-1.5 bg-[#0A0A0E] border border-[#272735] rounded-lg text-xs font-mono text-white placeholder-[#64748B] focus:outline-none focus:border-[#00E5FF] w-36 sm:w-48"
              />
            </div>

            <button
              type="button"
              onClick={() => setShowRejected(!showRejected)}
              className="text-xs font-mono text-[#94A3B8] hover:text-[#00E5FF] border border-[#272735] rounded-lg px-2.5 py-1.5 flex items-center gap-1 cursor-pointer hover:bg-[#181822] transition-all"
            >
              <span>{showRejected ? "Hide Disqualified" : "Disqualified Pairs"}</span>
              {showRejected ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            </button>
          </div>
        </div>

                {/* Verified Binance Spot Market Data Instruments */}
        <div className="p-3.5 rounded-xl bg-[#0A0A0E] border border-[#272735] space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-white uppercase tracking-wider">
                Verified Binance Instruments
              </span>
              <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-950/60 text-emerald-400 border border-emerald-500/30 font-bold">
                Binance Spot Market Data (Public Feed)
              </span>
            </div>
            <span className="text-[10px] text-[#64748B]">
              Real-time tick evaluation &bull; Controlled Validation Mode
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2 pt-1">
            {["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT"].map((pairSym) => {
              const pairData = hftPairs.find((p) => p.symbol === pairSym);
              const isSelected = selectedPair === pairSym;
              const price = pairData?.price;
              const chg = pairData?.price_change_pct_24h;
              const isPos = chg !== undefined && chg >= 0;
              return (
                <button
                  key={pairSym}
                  type="button"
                  onClick={() => {
                    setSelectedPair(pairSym);
                    setStrategyConfig((prev) => ({ ...prev, symbol: pairSym }));
                  }}
                  className={`p-2.5 rounded-xl border text-left transition-all cursor-pointer font-mono ${
                    isSelected
                      ? "bg-[#00E5FF]/15 border-[#00E5FF] shadow-sm shadow-[#00E5FF]/20"
                      : "bg-[#121218] border-[#272735] hover:border-[#94A3B8]/40 hover:bg-[#181822]"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-white">{pairSym}</span>
                    {isSelected && <span className="w-1.5 h-1.5 rounded-full bg-[#00E5FF]" />}
                  </div>
                  <div className="mt-1 flex items-baseline justify-between text-[11px]">
                    <span className="font-bold text-[#EAECEF] tabular-nums">
                      {price !== undefined && price !== null ? `$${safeFormatPrice(price)}` : "---"}
                    </span>
                    <span className={`text-[10px] font-bold tabular-nums ${isPos ? "text-[#10B981]" : "text-[#F6465D]"}`}>
                      {chg !== undefined && chg !== null ? `${isPos ? "+" : ""}${safeNum(chg, 2)}%` : ""}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Pair Grid (Responsive: 1 col on mobile, 2 on tablet, 3-4 on desktop) */}
        {filteredPairs.length === 0 ? (
          <div className="text-center py-8 text-xs font-mono text-[#94A3B8]">
            No qualified futures pairs match your filter.
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {filteredPairs.map((pair, idx) => {
              const isSelected = pair.symbol === selectedPair;
              const isPositive = pair.price_change_pct_24h >= 0;
              return (
                <div
                  key={pair.symbol} data-testid="hft-pair-card"
                  onClick={() => {
                    setSelectedPair(pair.symbol);
                    setStrategyConfig((prev) => ({ ...prev, symbol: pair.symbol }));
                  }}
                  className={`p-3.5 rounded-xl border transition-all cursor-pointer font-mono flex flex-col justify-between ${
                    isSelected
                      ? "bg-[#00E5FF]/10 border-[#00E5FF] shadow-md shadow-[#00E5FF]/10"
                      : "bg-[#0A0A0E] border-[#272735] hover:border-[#94A3B8]/40 hover:bg-[#151921]"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs font-bold text-white tracking-wide">
                        {pair.symbol.replace("USDT", "")}/USDT
                      </span>
                      <span className="text-[9px] px-1.5 py-0.2 rounded bg-[#181822] text-[#94A3B8] border border-[#272735]">
                        PERP
                      </span>
                    </div>

                    <span className="text-[10px] px-1.5 py-0.5 rounded font-bold bg-[#10B981]/15 text-[#10B981] border border-[#10B981]/30">
                      RANK #{idx + 1}
                    </span>
                  </div>

                  <div className="flex items-baseline justify-between mb-2">
                    <span className="text-sm font-bold text-white tabular-nums">
                      ${safeFormatPrice(pair?.price)}
                    </span>
                    <span className={`text-xs font-bold tabular-nums flex items-center ${isPositive ? "text-[#10B981]" : "text-[#F6465D]"}`}>
                      {isPositive ? <ArrowUpRight className="w-3 h-3 mr-0.5" /> : <ArrowDownRight className="w-3 h-3 mr-0.5" />}
                      {pair?.price_change_pct_24h > 0 ? "+" : ""}{safeNum(pair?.price_change_pct_24h, 2)}%
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-1.5 text-[10px] text-[#94A3B8] pt-2 border-t border-[#181822]">
                    <div>
                      <span className="text-[#64748B] block">24h Vol:</span>
                      <span className="text-white font-medium">
                        ${safeNum((pair?.quote_volume_24h ?? 0) / 1e6, 1)}M
                      </span>
                    </div>
                    <div>
                      <span className="text-[#64748B] block">Spread:</span>
                      <span className="text-[#00E5FF] font-medium">
                        {safeNum(pair?.spread_bps, 1)} bps
                      </span>
                    </div>
                    <div>
                      <span className="text-[#64748B] block">Funding:</span>
                      <span className="text-white font-medium">
                        {safeNum((pair?.funding_rate ?? 0) * 100, 4)}%
                      </span>
                    </div>
                    <div>
                      <span className="text-[#64748B] block">Liquidity:</span>
                      <span className="text-[#10B981] font-medium">
                        HIGH (Passed)
                      </span>
                    </div>
                  </div>

                  {isSelected && (
                    <div className="mt-2 pt-2 border-t border-[#00E5FF]/20 flex items-center justify-between text-[11px] text-[#00E5FF] font-bold">
                      <span className="flex items-center gap-1">
                        <Check className="w-3.5 h-3.5" /> Selected Contract
                      </span>
                      <span>Configured</span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Disqualified Pairs Drawer */}
        {showRejected && rejectedPairs.length > 0 && (
          <div className="mt-4 p-3.5 rounded-xl bg-[#0A0A0E] border border-amber-950/40 text-xs font-mono space-y-2">
            <div className="flex items-center gap-2 text-amber-400 font-bold">
              <AlertTriangle className="w-4 h-4" />
              <span>Gated / Disqualified Contracts &amp; Strict Risk Reasons</span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2 pt-1 max-h-48 overflow-y-auto">
              {rejectedPairs.map((r, i) => (
                <div key={i} className="p-2 rounded bg-[#121218] border border-[#272735] flex items-center justify-between gap-2">
                  <span className="font-bold text-white">{r.symbol}</span>
                  <span className="text-[10px] text-[#F6465D] font-mono truncate" title={r.reason}>
                    {r.reason}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ─── STEP 2 & 3: STRATEGY CONFIGURATION & PRE-TRADE CHECKLIST ────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Duplicate Pair Protection Warning */}
        {hasDuplicatePair && (
          <div className="col-span-full p-3.5 rounded-xl bg-amber-950/30 border border-amber-500/40 text-amber-200 text-xs font-mono flex items-center gap-3">
            <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0" />
            <div className="space-y-0.5">
              <span className="font-bold text-amber-300">
                Duplicate Position / Working Order Warning ({selectedPair}):
              </span>
              <p className="text-[11px] text-amber-200/80">
                An active position or working order already exists on {selectedPair} on your broker account.
                Duplicate execution is blocked by netting protection rules to prevent unhedged directional exposure.
              </p>
            </div>
          </div>
        )}


        {/* Step 2 Card: Strategy Parameters & Active Settings */}
        <div className="p-4 sm:p-5 rounded-2xl bg-[#121218] border border-[#272735] space-y-4 shadow-lg flex flex-col justify-between">
          <div className="space-y-3">
            <div className="flex items-center justify-between border-b border-[#272735] pb-3">
              <div className="flex items-center gap-2 font-mono">
                <span className="w-5 h-5 rounded-full bg-[#00E5FF]/20 text-[#00E5FF] text-xs font-bold flex items-center justify-center">
                  2
                </span>
                <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                  Strategy Configuration ({selectedPair})
                </h3>
              </div>

              <button
                type="button"
                id="btn-open-config-modal"
                onClick={() => {
                  if (activationStatus !== "ACTIVE") {
                    setIsActivationModalOpen(true);
                  } else if (guardAccountAction("CONFIG")) {
                    setIsConfigModalOpen(true);
                  }
                }}
                className="px-3 py-1.5 rounded-lg bg-[#00E5FF]/15 hover:bg-[#00E5FF] border border-[#00E5FF]/40 text-[#00E5FF] hover:text-[#0B0E11] text-xs font-mono font-bold transition-all flex items-center gap-1.5 cursor-pointer"
              >
                <Sliders className="w-3.5 h-3.5" />
                <span>{activationStatus === "ACTIVE" ? "Configure Strategy" : "Configure Strategy ($20 Unlock)"}</span>
              </button>
            </div>

            {/* Active Parameters Overview Table */}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 font-mono text-xs">
              <div className="p-2.5 rounded-xl bg-[#0A0A0E] border border-[#272735]">
                <span className="text-[10px] text-[#64748B] block">Direction:</span>
                <span className="font-bold text-white">{strategyConfig.direction}</span>
              </div>
              <div className="p-2.5 rounded-xl bg-[#0A0A0E] border border-[#272735]">
                <span className="text-[10px] text-[#64748B] block">Margin Allocated:</span>
                <span className="font-bold text-white">${safeNum(strategyConfig?.margin_allocation_usd, 2)}</span>
              </div>
              <div className="p-2.5 rounded-xl bg-[#0A0A0E] border border-[#272735]">
                <span className="text-[10px] text-[#64748B] block">Isolated Leverage:</span>
                <span className="font-bold text-[#00E5FF]">{strategyConfig.leverage}x</span>
              </div>
              <div className="p-2.5 rounded-xl bg-[#0A0A0E] border border-[#272735]">
                <span className="text-[10px] text-[#64748B] block">Net Target (TP):</span>
                <span className="font-bold text-[#10B981]">+{safeNum(strategyConfig?.net_profit_target_pct, 2)}%</span>
              </div>
              <div className="p-2.5 rounded-xl bg-[#0A0A0E] border border-[#272735]">
                <span className="text-[10px] text-[#64748B] block">Max Loss (SL):</span>
                <span className="font-bold text-[#F6465D]">-{safeNum(strategyConfig?.max_loss_pct, 2)}%</span>
              </div>
              <div className="p-2.5 rounded-xl bg-[#0A0A0E] border border-[#272735]">
                <span className="text-[10px] text-[#64748B] block">Holding Max:</span>
                <span className="font-bold text-white">{Math.round(strategyConfig.max_holding_duration_seconds / 60)} min</span>
              </div>
            </div>

            {/* Break-Even Math Card */}
            <div className="p-3 rounded-xl bg-[#0A0A0E] border border-[#272735] text-xs font-mono space-y-1.5">
              <div className="flex items-center justify-between text-[#94A3B8]">
                <span>Notional Scalp Exposure:</span>
                <span className="font-bold text-white">${safeNum(breakEvenMath?.notional, 2)}</span>
              </div>
              <div className="flex items-center justify-between text-[#94A3B8]">
                <span>Estimated Maker Friction (0.04% + Buffer):</span>
                <span className="font-bold text-[#00E5FF]">+{safeNum(breakEvenMath?.totalFrictionPct, 3)}% (~${safeNum(breakEvenMath?.estFeeDollar, 3)})</span>
              </div>
              <div className="flex items-center justify-between text-[#94A3B8] border-t border-[#181822] pt-1.5">
                <span className="text-[#10B981]">Net Target Return at Fill:</span>
                <span className="font-bold text-[#10B981]">+{safeNum(breakEvenMath?.netReturnPct, 2)}% (~+${safeNum(breakEvenMath?.estDollarProfit, 2)}/cycle)</span>
              </div>
            </div>
          </div>

          <p className="text-[11px] text-[#64748B] font-mono">
            Orders are dispatched exclusively as Post-Only Limit Maker (`GTX`). Zero market orders are issued to guarantee maker rebates.
          </p>
        </div>

        {/* Step 3 Card: Pre-Trade Safety Checklist */}
        <div className="p-4 sm:p-5 rounded-2xl bg-[#121218] border border-[#272735] space-y-4 shadow-lg flex flex-col justify-between">
          <div className="space-y-3">
            <div className="flex items-center justify-between border-b border-[#272735] pb-3">
              <div className="flex items-center gap-2 font-mono">
                <span className="w-5 h-5 rounded-full bg-[#00E5FF]/20 text-[#00E5FF] text-xs font-bold flex items-center justify-center">
                  3
                </span>
                <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                  Pre-Trade Safety Checklist
                </h3>
              </div>

              <span
                className={`text-[10px] font-mono font-bold px-2.5 py-1 rounded-full border flex items-center gap-1.5 ${
                  isReady
                    ? "bg-[#10B981]/15 text-[#10B981] border-[#10B981]/40"
                    : "bg-amber-950/40 text-amber-400 border-amber-500/40"
                }`}
              >
                <span className={`w-1.5 h-1.5 rounded-full ${isReady ? "bg-[#10B981] animate-pulse" : "bg-amber-400"}`} />
                {isReady ? "ALL 9 GATES PASSED (READY)" : "GATES PENDING"}
              </span>
            </div>

            {/* Checklist items */}
            <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
              {checklist.length === 0 ? (
                <div className="text-xs font-mono text-[#94A3B8] text-center py-4">
                  Evaluating pre-trade prerequisites...
                </div>
              ) : (
                checklist.map((item) => (
                  <div
                    key={item.id} data-testid="checklist-item"
                    className={`p-2.5 rounded-xl border text-xs font-mono flex items-start justify-between gap-3 ${
                      item.passed
                        ? "bg-[#0A0A0E] border-[#272735]"
                        : "bg-red-950/20 border-red-500/30 text-red-200"
                    }`}
                  >
                    <div className="space-y-0.5 min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className={`font-bold ${item.passed ? "text-white" : "text-[#F6465D]"}`}>
                          {item.name}
                        </span>
                        {item.critical && (
                          <span className="text-[9px] px-1 rounded bg-[#181822] text-[#64748B]">
                            CRITICAL
                          </span>
                        )}
                      </div>
                      <p className="text-[11px] text-[#94A3B8] truncate">{item.detail}</p>
                    </div>

                    <div className="shrink-0 pt-0.5">
                      {item.passed ? (
                        <CheckCircle2 className="w-4 h-4 text-[#10B981]" />
                      ) : (
                        <AlertTriangle className="w-4 h-4 text-[#F6465D]" />
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="text-[11px] text-[#64748B] font-mono flex items-center justify-between border-t border-[#181822] pt-2">
            <span>Supervisor: ProtectionWatchdog (PM2)</span>
            <span>Collision Guard: SymbolLeases (CAS)</span>
          </div>
        </div>
      </div>

      {/* ─── STEP 4: SESSION CONTROL & ACTIVATION INTERFACE ─────────────────── */}
      <div className="p-4 sm:p-5 rounded-2xl bg-[#121218] border border-[#272735] space-y-4 shadow-lg">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#272735] pb-3">
          <div className="flex items-center gap-2 font-mono">
            <span className="w-5 h-5 rounded-full bg-[#00E5FF]/20 text-[#00E5FF] text-xs font-bold flex items-center justify-center">
              4
            </span>
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">
              Session Lifecycle Control ({selectedPair})
            </h3>
          </div>

          <div className="flex items-center gap-2 font-mono text-xs">
            <span className="text-[#94A3B8]">Session State:</span>
            <span
              className={`px-3 py-1 rounded-full font-bold border flex items-center gap-1.5 ${
                sessionState === "ACTIVE"
                  ? "bg-[#10B981]/15 text-[#10B981] border-[#10B981]/40"
                  : sessionState === "READY"
                  ? "bg-[#00E5FF]/15 text-[#00E5FF] border-[#00E5FF]/40"
                  : sessionState === "CONFIGURED"
                  ? "bg-amber-950/40 text-amber-400 border-amber-500/40"
                  : "bg-[#181822] text-[#94A3B8] border-[#272735]"
              }`}
            >
              <span
                className={`w-2 h-2 rounded-full ${
                  sessionState === "ACTIVE"
                    ? "bg-[#10B981] animate-pulse"
                    : sessionState === "READY"
                    ? "bg-[#00E5FF]"
                    : "bg-[#64748B]"
                }`}
              />
              {sessionState}
            </span>
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-4 font-mono text-xs">
          <div className="space-y-1">
            <p className="text-white font-medium">
              Autonomous Post-Only Scalper · Binance USDⓈ-M Perps
            </p>
            <p className="text-[#94A3B8]">
              {sessionState === "ACTIVE"
                ? "Session active in Controlled Testnet Validation Mode. Order placement held at execution gate."
                : isReady
                ? "All 9 security and risk checks passed. Ready for simulated session arming."
                : "Prerequisites incomplete. Review pre-trade checklist above to arm session."}
            </p>
          </div>

          <div className="flex items-center gap-3">
            {sessionState === "ACTIVE" ? (
              <button
                type="button"
                id="btn-stop-hft-session"
                onClick={handleStopSession}
                disabled={sessionActionLoading}
                className="px-5 py-2.5 rounded-xl bg-[#F6465D] hover:bg-[#F6465D]/90 text-white font-bold transition-all flex items-center gap-2 cursor-pointer shadow-lg shadow-[#F6465D]/20 disabled:opacity-50"
              >
                {sessionActionLoading ? (
                  <RefreshCw className="w-4 h-4 animate-spin" />
                ) : (
                  <Square className="w-4 h-4 fill-white" />
                )}
                <span>Emergency Stop / Disarm</span>
              </button>
            ) : (
              <button
                type="button"
                id="btn-start-hft-session"
                onClick={() => {
                  if (activationStatus !== "ACTIVE") {
                    setIsActivationModalOpen(true);
                  } else if (guardAccountAction("START")) {
                    handleStartSession();
                  }
                }}
                disabled={(activationStatus === "ACTIVE" && !isReady) || sessionActionLoading || hasDuplicatePair || !selectedAccount || !selectedAccount.connected}
                className={`px-5 py-2.5 rounded-xl font-bold transition-all flex items-center gap-2 ${
                  activationStatus !== "ACTIVE"
                    ? "bg-amber-500 hover:bg-amber-400 text-[#0B0E11] cursor-pointer shadow-lg shadow-amber-500/20"
                    : isReady && !sessionActionLoading
                    ? "bg-[#10B981] hover:bg-[#10B981]/90 text-[#0B0E11] cursor-pointer shadow-lg shadow-[#10B981]/20"
                    : "bg-[#181822] text-[#64748B] border border-[#272735] cursor-not-allowed opacity-60"
                }`}
              >
                {sessionActionLoading ? (
                  <RefreshCw className="w-4 h-4 animate-spin" />
                ) : activationStatus !== "ACTIVE" ? (
                  <Lock className="w-4 h-4" />
                ) : (
                  <Play className="w-4 h-4 fill-current" />
                )}
                <span>{activationStatus !== "ACTIVE" ? "Activate Account ($20.00) to Start HFT" : "Arm & Start Session"}</span>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* ─── AUTHORITATIVE BOTTOM TRADING ACTIVITY PANEL (5 TABS) ────────── */}
      <div className="p-4 sm:p-5 rounded-2xl bg-[#121218] border border-[#272735] space-y-4 shadow-xl font-mono">
        {/* Panel Header */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#272735] pb-3">
          <div className="flex items-center gap-2">
            <Layers className="w-5 h-5 text-[#00E5FF]" />
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">
              Authoritative Trading Activity &amp; Portfolio Journal
            </h3>
            <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-950/60 text-emerald-400 border border-emerald-500/30">
              BROKER-CONFIRMED DATA
            </span>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={fetchBottomData}
              disabled={loadingBottomData}
              className="px-2.5 py-1 rounded-lg bg-[#0A0A0E] border border-[#272735] hover:border-[#00E5FF] text-xs text-[#94A3B8] hover:text-white flex items-center gap-1.5 transition-all cursor-pointer"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loadingBottomData ? "animate-spin text-[#00E5FF]" : ""}`} />
              <span>Refresh</span>
            </button>
          </div>
        </div>

        {/* 5 Navigation Tabs */}
        <div className="flex items-center gap-2 border-b border-[#1E2736] pb-2 overflow-x-auto text-xs">
          <button
            type="button"
            onClick={() => setBottomTab("POSITIONS")}
            className={`px-3 py-1.5 rounded-lg font-bold transition-all flex items-center gap-1.5 cursor-pointer ${
              bottomTab === "POSITIONS"
                ? "bg-[#00E5FF] text-[#0B0E11]"
                : "text-[#94A3B8] hover:text-white hover:bg-[#181822]"
            }`}
          >
            <span>Open Positions</span>
            <span className={`text-[10px] px-1.5 py-0.2 rounded-full ${bottomTab === "POSITIONS" ? "bg-black/30 text-[#0B0E11]" : "bg-[#1E2736] text-[#94A3B8]"}`}>
              {hftPositions.filter((p) => p.status === "OPEN").length}
            </span>
          </button>

          <button
            type="button"
            onClick={() => setBottomTab("OPEN_ORDERS")}
            className={`px-3 py-1.5 rounded-lg font-bold transition-all flex items-center gap-1.5 cursor-pointer ${
              bottomTab === "OPEN_ORDERS"
                ? "bg-[#00E5FF] text-[#0B0E11]"
                : "text-[#94A3B8] hover:text-white hover:bg-[#181822]"
            }`}
          >
            <span>Open Orders</span>
            <span className={`text-[10px] px-1.5 py-0.2 rounded-full ${bottomTab === "OPEN_ORDERS" ? "bg-black/30 text-[#0B0E11]" : "bg-[#1E2736] text-[#94A3B8]"}`}>
              {hftOrders.filter((o) => o.status === "NEW" || o.status === "OPEN" || o.status === "PARTIALLY_FILLED").length}
            </span>
          </button>

          <button
            type="button"
            onClick={() => setBottomTab("CLOSED_TRADES")}
            className={`px-3 py-1.5 rounded-lg font-bold transition-all flex items-center gap-1.5 cursor-pointer ${
              bottomTab === "CLOSED_TRADES"
                ? "bg-[#00E5FF] text-[#0B0E11]"
                : "text-[#94A3B8] hover:text-white hover:bg-[#181822]"
            }`}
          >
            <span>Closed Trades</span>
            <span className={`text-[10px] px-1.5 py-0.2 rounded-full ${bottomTab === "CLOSED_TRADES" ? "bg-black/30 text-[#0B0E11]" : "bg-[#1E2736] text-[#94A3B8]"}`}>
              {data?.recent_trades?.length || 0}
            </span>
          </button>

          <button
            type="button"
            onClick={() => setBottomTab("HISTORY")}
            className={`px-3 py-1.5 rounded-lg font-bold transition-all flex items-center gap-1.5 cursor-pointer ${
              bottomTab === "HISTORY"
                ? "bg-[#00E5FF] text-[#0B0E11]"
                : "text-[#94A3B8] hover:text-white hover:bg-[#181822]"
            }`}
          >
            <span>Trade History</span>
          </button>

          <button
            type="button"
            onClick={() => setBottomTab("ACCOUNT")}
            className={`px-3 py-1.5 rounded-lg font-bold transition-all flex items-center gap-1.5 cursor-pointer ${
              bottomTab === "ACCOUNT"
                ? "bg-[#00E5FF] text-[#0B0E11]"
                : "text-[#94A3B8] hover:text-white hover:bg-[#181822]"
            }`}
          >
            <span>Account Overview</span>
          </button>
        </div>

        {/* TAB 1: OPEN POSITIONS */}
        {bottomTab === "POSITIONS" && (
          <div className="space-y-3">
            {hftPositions.filter((p) => p.status === "OPEN").length === 0 ? (
              <div className="p-8 text-center text-xs text-[#94A3B8] bg-[#0A0A0E] rounded-xl border border-[#272735] space-y-1">
                <p className="font-bold text-white">No active open positions on broker account.</p>
                <p className="text-[#64748B]">Controlled validation mode prevents live order dispatch. Positions will appear here when filled.</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-[#272735] text-[#64748B] text-[10px] uppercase">
                      <th className="py-2.5 px-3">Position ID</th>
                      <th className="py-2.5 px-3">Symbol</th>
                      <th className="py-2.5 px-3">Direction</th>
                      <th className="py-2.5 px-3">Size</th>
                      <th className="py-2.5 px-3">Entry Price</th>
                      <th className="py-2.5 px-3">Mark Price</th>
                      <th className="py-2.5 px-3">Unrealized P&amp;L</th>
                      <th className="py-2.5 px-3">Leverage</th>
                      <th className="py-2.5 px-3">Stop Loss</th>
                      <th className="py-2.5 px-3">Take Profit</th>
                      <th className="py-2.5 px-3">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#181822]">
                    {hftPositions
                      .filter((p) => p.status === "OPEN")
                      .map((pos) => {
                        const isLong = pos.direction === "LONG";
                        const isProfitable = pos.unrealized_pnl >= 0;
                        return (
                          <tr key={pos.position_id} className="hover:bg-[#151921] transition-colors">
                            <td className="py-2.5 px-3 text-[#94A3B8] font-mono">{pos.position_id}</td>
                            <td className="py-2.5 px-3 font-bold text-white">{pos.symbol}</td>
                            <td className="py-2.5 px-3">
                              <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                isLong ? "bg-emerald-950/60 text-emerald-400 border border-emerald-500/30" : "bg-red-950/60 text-red-400 border border-red-500/30"
                              }`}>
                                {pos.direction}
                              </span>
                            </td>
                            <td className="py-2.5 px-3 tabular-nums text-white font-medium">{pos.size}</td>
                            <td className="py-2.5 px-3 tabular-nums text-white">${safeFormatPrice(pos.entry_price)}</td>
                            <td className="py-2.5 px-3 tabular-nums text-white font-medium">${safeFormatPrice(pos.mark_price)}</td>
                            <td className={`py-2.5 px-3 tabular-nums font-bold ${isProfitable ? "text-[#10B981]" : "text-[#F6465D]"}`}>
                              {isProfitable ? "+" : ""}${safeNum(pos.unrealized_pnl, 2)}
                            </td>
                            <td className="py-2.5 px-3 tabular-nums text-[#00E5FF] font-bold">{pos.leverage}x</td>
                            <td className="py-2.5 px-3 tabular-nums text-[#F6465D]">
                              {pos.stop_loss_price ? `$${safeNum(pos.stop_loss_price, 2)}` : "STANDBY"}
                            </td>
                            <td className="py-2.5 px-3 tabular-nums text-[#10B981]">
                              {pos.take_profit_price ? `$${safeNum(pos.take_profit_price, 2)}` : "STANDBY"}
                            </td>
                            <td className="py-2.5 px-3">
                              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-[#10B981]/15 text-[#10B981] border border-[#10B981]/30">
                                {pos.status}
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* TAB 2: OPEN ORDERS */}
        {bottomTab === "OPEN_ORDERS" && (
          <div className="space-y-3">
            {hftOrders.filter((o) => o.status === "NEW" || o.status === "OPEN" || o.status === "PARTIALLY_FILLED").length === 0 ? (
              <div className="p-8 text-center text-xs text-[#94A3B8] bg-[#0A0A0E] rounded-xl border border-[#272735] space-y-1">
                <p className="font-bold text-white">No working open orders on broker account.</p>
                <p className="text-[#64748B]">All limit GTX orders will be listed here with live execution state.</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-[#272735] text-[#64748B] text-[10px] uppercase">
                      <th className="py-2.5 px-3">Order ID</th>
                      <th className="py-2.5 px-3">Symbol</th>
                      <th className="py-2.5 px-3">Side</th>
                      <th className="py-2.5 px-3">Type</th>
                      <th className="py-2.5 px-3">Price</th>
                      <th className="py-2.5 px-3">Quantity</th>
                      <th className="py-2.5 px-3">Status</th>
                      <th className="py-2.5 px-3">Created</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#181822]">
                    {hftOrders
                      .filter((o) => o.status === "NEW" || o.status === "OPEN" || o.status === "PARTIALLY_FILLED")
                      .map((ord) => (
                        <tr key={ord.order_id} className="hover:bg-[#151921] transition-colors">
                          <td className="py-2.5 px-3 text-[#94A3B8] font-mono">{ord.order_id}</td>
                          <td className="py-2.5 px-3 font-bold text-white">{ord.symbol}</td>
                          <td className={`py-2.5 px-3 font-bold ${ord.side === "BUY" ? "text-[#10B981]" : "text-[#F6465D]"}`}>
                            {ord.side}
                          </td>
                          <td className="py-2.5 px-3 text-[#94A3B8]">{ord.order_type}</td>
                          <td className="py-2.5 px-3 tabular-nums text-white">${safeNum(ord.price, 2)}</td>
                          <td className="py-2.5 px-3 tabular-nums text-white">{ord.quantity}</td>
                          <td className="py-2.5 px-3">
                            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-[#00E5FF]/15 text-[#00E5FF] border border-[#00E5FF]/30">
                              {ord.status}
                            </span>
                          </td>
                          <td className="py-2.5 px-3 text-[#64748B] text-[11px]">{ord.created_at || "---"}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* TAB 3: CLOSED TRADES */}
        {bottomTab === "CLOSED_TRADES" && (
          <div className="space-y-3">
            {(!data?.recent_trades || data.recent_trades.length === 0) ? (
              <div className="p-8 text-center text-xs text-[#94A3B8] bg-[#0A0A0E] rounded-xl border border-[#272735] space-y-1">
                <p className="font-bold text-white">No closed trades recorded for this account.</p>
                <p className="text-[#64748B]">Controlled validation mode prevents live order dispatch. Completed trades will populate here.</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-[#272735] text-[#64748B] text-[10px] uppercase">
                      <th className="py-2.5 px-3">Trade ID</th>
                      <th className="py-2.5 px-3">Symbol</th>
                      <th className="py-2.5 px-3">Side</th>
                      <th className="py-2.5 px-3">Quantity</th>
                      <th className="py-2.5 px-3">Entry Price</th>
                      <th className="py-2.5 px-3">Exit Price</th>
                      <th className="py-2.5 px-3">Fee ($)</th>
                      <th className="py-2.5 px-3">Realized Net P&amp;L</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#181822]">
                    {data.recent_trades.map((t) => (
                      <tr key={t.trade_id} className="hover:bg-[#151921] transition-colors">
                        <td className="py-2.5 px-3 text-[#94A3B8] font-mono">{t.trade_id}</td>
                        <td className="py-2.5 px-3 font-bold text-white">{t.symbol}</td>
                        <td className={`py-2.5 px-3 font-bold ${t.side === "BUY" ? "text-[#10B981]" : "text-[#F6465D]"}`}>
                          {t.side}
                        </td>
                        <td className="py-2.5 px-3 tabular-nums">{t.quantity}</td>
                        <td className="py-2.5 px-3 tabular-nums">${safeNum(t.entry_price, 2)}</td>
                        <td className="py-2.5 px-3 tabular-nums">${safeNum(t.exit_price, 2)}</td>
                        <td className="py-2.5 px-3 tabular-nums text-[#94A3B8]">${safeNum(t.fee_usd, 4)}</td>
                        <td className={`py-2.5 px-3 tabular-nums font-bold ${t.realized_pnl >= 0 ? "text-[#10B981]" : "text-[#F6465D]"}`}>
                          ${safeNum(t.realized_pnl, 2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* TAB 4: TRADE HISTORY */}
        {bottomTab === "HISTORY" && (
          <div className="space-y-3">
            <div className="p-3 rounded-xl bg-[#0A0A0E] border border-[#272735] flex items-center justify-between text-xs text-[#94A3B8]">
              <span>Audited Trade History Journal &bull; Net-of-Maker Rebate</span>
              <span>All records cryptographically signed in database</span>
            </div>
            {(!data?.recent_trades || data.recent_trades.length === 0) ? (
              <div className="p-8 text-center text-xs text-[#94A3B8] bg-[#0A0A0E] rounded-xl border border-[#272735]">
                No historical trades on record.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-[#272735] text-[#64748B] text-[10px] uppercase">
                      <th className="py-2.5 px-3">Timestamp</th>
                      <th className="py-2.5 px-3">Trade ID</th>
                      <th className="py-2.5 px-3">Symbol</th>
                      <th className="py-2.5 px-3">Side</th>
                      <th className="py-2.5 px-3">Qty</th>
                      <th className="py-2.5 px-3">Executed Price</th>
                      <th className="py-2.5 px-3">Fee</th>
                      <th className="py-2.5 px-3">Net P&amp;L</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#181822]">
                    {data.recent_trades.map((t) => (
                      <tr key={t.trade_id} className="hover:bg-[#151921] transition-colors">
                        <td className="py-2.5 px-3 text-[#64748B] text-[11px]">{t.created_at || "---"}</td>
                        <td className="py-2.5 px-3 text-[#94A3B8] font-mono">{t.trade_id}</td>
                        <td className="py-2.5 px-3 font-bold text-white">{t.symbol}</td>
                        <td className={`py-2.5 px-3 font-bold ${t.side === "BUY" ? "text-[#10B981]" : "text-[#F6465D]"}`}>{t.side}</td>
                        <td className="py-2.5 px-3 tabular-nums">{t.quantity}</td>
                        <td className="py-2.5 px-3 tabular-nums">${safeNum(t.exit_price, 2)}</td>
                        <td className="py-2.5 px-3 tabular-nums text-[#94A3B8]">${safeNum(t.fee_usd, 4)}</td>
                        <td className={`py-2.5 px-3 tabular-nums font-bold ${t.realized_pnl >= 0 ? "text-[#10B981]" : "text-[#F6465D]"}`}>${safeNum(t.realized_pnl, 2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* TAB 5: ACCOUNT OVERVIEW */}
        {bottomTab === "ACCOUNT" && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 text-xs">
              <div className="p-3.5 rounded-xl bg-[#0A0A0E] border border-[#272735]">
                <span className="text-[10px] text-[#64748B] block uppercase">Account Identifier:</span>
                <span className="font-bold text-white font-mono">{hftAccountSummary?.account_id || data?.account?.account_id || "---"}</span>
              </div>
              <div className="p-3.5 rounded-xl bg-[#0A0A0E] border border-[#272735]">
                <span className="text-[10px] text-[#64748B] block uppercase">Environment:</span>
                <span className="font-bold text-[#00E5FF] font-mono">{hftAccountSummary?.environment || data?.account?.environment || "DEMO"}</span>
              </div>
              <div className="p-3.5 rounded-xl bg-[#0A0A0E] border border-[#272735]">
                <span className="text-[10px] text-[#64748B] block uppercase">Authoritative Wallet Balance:</span>
                <span className="font-bold text-white font-mono text-sm">
                  ${safeNum(hftAccountSummary?.wallet_balance_usd ?? data?.account?.wallet_balance ?? 0, 2)}
                </span>
              </div>
              <div className="p-3.5 rounded-xl bg-[#0A0A0E] border border-[#272735]">
                <span className="text-[10px] text-[#64748B] block uppercase">Available Margin:</span>
                <span className="font-bold text-[#10B981] font-mono text-sm">
                  ${safeNum(hftAccountSummary?.available_balance_usd ?? data?.account?.available_balance ?? 0, 2)}
                </span>
              </div>
              <div className="p-3.5 rounded-xl bg-[#0A0A0E] border border-[#272735]">
                <span className="text-[10px] text-[#64748B] block uppercase">Margin In Use:</span>
                <span className="font-bold text-white font-mono">
                  ${safeNum(hftAccountSummary?.margin_balance_usd ?? data?.account?.margin_balance ?? 0, 2)}
                </span>
              </div>
              <div className="p-3.5 rounded-xl bg-[#0A0A0E] border border-[#272735]">
                <span className="text-[10px] text-[#64748B] block uppercase">Total Equity:</span>
                <span className="font-bold text-white font-mono text-sm">
                  ${safeNum(hftAccountSummary?.equity_usd ?? (data?.account?.wallet_balance || 0), 2)}
                </span>
              </div>
              <div className="p-3.5 rounded-xl bg-[#0A0A0E] border border-[#272735]">
                <span className="text-[10px] text-[#64748B] block uppercase">Margin Mode:</span>
                <span className="font-bold text-[#00E5FF] font-mono">ISOLATED (LEVERAGE CLAMP: 5x)</span>
              </div>
              <div className="p-3.5 rounded-xl bg-[#0A0A0E] border border-[#272735]">
                <span className="text-[10px] text-[#64748B] block uppercase">Safety Locks:</span>
                <span className={`font-bold font-mono ${(hftAccountSummary?.environment || selectedAccount?.environment) === "DEMO" ? "text-amber-400" : "text-red-400"}`}>
                  {(hftAccountSummary?.environment || selectedAccount?.environment) === "DEMO" ? "DEMO AUTHORIZED • READ-ONLY" : "LIVE LOCKED • READ-ONLY"}
                </span>
              </div>
            </div>
          </div>
        )}
      </div>

{/* ─── MODAL: STEP 2 STRATEGY CONFIGURATION MODAL ─────────────────────── */}
      {isConfigModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
          <div className="w-full max-w-xl rounded-2xl bg-[#121218] border border-[#272735] shadow-2xl overflow-hidden font-mono text-xs flex flex-col max-h-[90vh]">
            {/* Modal Header */}
            <div className="p-4 sm:p-5 border-b border-[#272735] flex items-center justify-between bg-[#181822]">
              <div className="flex items-center gap-2">
                <Sliders className="w-4 h-4 text-[#00E5FF]" />
                <h3 className="text-sm font-bold text-white">
                  Configure HFT Scalp Strategy — {selectedPair}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setIsConfigModalOpen(false)}
                className="text-[#94A3B8] hover:text-white cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Modal Form Content */}
            <form onSubmit={handleSaveConfig} className="p-4 sm:p-5 space-y-4 overflow-y-auto flex-1">
              {/* Direction */}
              <div className="space-y-1.5">
                <label className="text-white font-bold block">Execution Direction:</label>
                <div className="grid grid-cols-3 gap-2">
                  {(["AUTO", "LONG_ONLY", "SHORT_ONLY"] as const).map((dir) => (
                    <button
                      key={dir}
                      type="button"
                      onClick={() => setStrategyConfig({ ...strategyConfig, direction: dir })}
                      className={`py-2 px-3 rounded-xl border text-center font-bold cursor-pointer transition-all ${
                        strategyConfig.direction === dir
                          ? "bg-[#00E5FF] text-[#0B0E11] border-[#00E5FF]"
                          : "bg-[#0A0A0E] text-[#94A3B8] border-[#272735] hover:text-white hover:bg-[#181822]"
                      }`}
                    >
                      {dir}
                    </button>
                  ))}
                </div>
                <p className="text-[10px] text-[#64748B]">
                  AUTO evaluates trend direction from ADX and Donchian channel breakouts.
                </p>
              </div>

              {/* Margin Allocation & Quick Pills */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-white font-bold">Demo / Testnet Margin Allocation ($):</label>
                  <span className="text-[#00E5FF] font-bold">${safeNum(strategyConfig?.margin_allocation_usd, 2)}</span>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    min="10"
                    max="500"
                    step="5"
                    value={strategyConfig.margin_allocation_usd}
                    onChange={(e) => setStrategyConfig({ ...strategyConfig, margin_allocation_usd: Number(e.target.value) })}
                    className="flex-1 px-3 py-2 bg-[#0A0A0E] border border-[#272735] rounded-xl text-white font-bold focus:outline-none focus:border-[#00E5FF]"
                  />
                  <div className="flex items-center gap-1">
                    {[25, 50, 100, 250].map((amt) => (
                      <button
                        key={amt}
                        type="button"
                        onClick={() => setStrategyConfig({ ...strategyConfig, margin_allocation_usd: amt })}
                        className="px-2.5 py-2 rounded-xl bg-[#181822] hover:bg-[#272735] border border-[#272735] text-[#94A3B8] hover:text-white font-bold cursor-pointer"
                      >
                        ${amt}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Leverage Slider */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-white font-bold">Isolated Leverage (Clamped to Max 5x):</label>
                  <span className="text-[#00E5FF] font-bold">{strategyConfig.leverage}x</span>
                </div>
                <div className="grid grid-cols-4 gap-2">
                  {[1, 2, 3, 5].map((lev) => (
                    <button
                      key={lev}
                      type="button"
                      onClick={() => setStrategyConfig({ ...strategyConfig, leverage: lev })}
                      className={`py-2 px-3 rounded-xl border text-center font-bold cursor-pointer transition-all ${
                        strategyConfig.leverage === lev
                          ? "bg-[#00E5FF] text-[#0B0E11] border-[#00E5FF]"
                          : "bg-[#0A0A0E] text-[#94A3B8] border-[#272735] hover:text-white"
                      }`}
                    >
                      {lev}x
                    </button>
                  ))}
                </div>
                <p className="text-[10px] text-[#64748B]">
                  Notional position: ${safeNum((strategyConfig?.margin_allocation_usd ?? 0) * (strategyConfig?.leverage ?? 1), 2)} USD.
                </p>
              </div>

              {/* Profit Target & Max Loss Grid */}
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-white font-bold block">Net Profit Target (%):</label>
                  <input
                    type="number"
                    min="0.2"
                    max="5.0"
                    step="0.05"
                    value={strategyConfig.net_profit_target_pct}
                    onChange={(e) => setStrategyConfig({ ...strategyConfig, net_profit_target_pct: Number(e.target.value) })}
                    className="w-full px-3 py-2 bg-[#0A0A0E] border border-[#272735] rounded-xl text-[#10B981] font-bold focus:outline-none focus:border-[#10B981]"
                  />
                  <span className="text-[10px] text-[#64748B] block">Minimum +0.20%</span>
                </div>

                <div className="space-y-1">
                  <label className="text-white font-bold block">Max Loss SL (%):</label>
                  <input
                    type="number"
                    min="0.3"
                    max="5.0"
                    step="0.05"
                    value={strategyConfig.max_loss_pct}
                    onChange={(e) => setStrategyConfig({ ...strategyConfig, max_loss_pct: Number(e.target.value) })}
                    className="w-full px-3 py-2 bg-[#0A0A0E] border border-[#272735] rounded-xl text-[#F6465D] font-bold focus:outline-none focus:border-[#F6465D]"
                  />
                  <span className="text-[10px] text-[#64748B] block">Protective hard stop</span>
                </div>
              </div>

              {/* Holding Duration & Session Mode */}
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-white font-bold block">Max Hold Time:</label>
                  <select
                    value={strategyConfig.max_holding_duration_seconds}
                    onChange={(e) => setStrategyConfig({ ...strategyConfig, max_holding_duration_seconds: Number(e.target.value) })}
                    className="w-full px-3 py-2 bg-[#0A0A0E] border border-[#272735] rounded-xl text-white font-bold focus:outline-none"
                  >
                    <option value={300}>5 Minutes</option>
                    <option value={900}>15 Minutes</option>
                    <option value={1800}>30 Minutes</option>
                    <option value={3600}>60 Minutes</option>
                  </select>
                </div>

                <div className="space-y-1">
                  <label className="text-white font-bold block">Session Mode:</label>
                  <select
                    value={strategyConfig.session_mode}
                    onChange={(e) => setStrategyConfig({ ...strategyConfig, session_mode: e.target.value as any })}
                    className="w-full px-3 py-2 bg-[#0A0A0E] border border-[#272735] rounded-xl text-white font-bold focus:outline-none"
                  >
                    <option value="SINGLE_CYCLE">Single Cycle (Exit &amp; Stop)</option>
                    <option value="CONTINUOUS">Continuous Scalp</option>
                  </select>
                </div>
              </div>

              {/* Live Break-Even Math Card inside Modal */}
              <div className="p-3.5 rounded-xl bg-[#0A0A0E] border border-[#00E5FF]/30 space-y-2">
                <div className="flex items-center gap-2 text-[#00E5FF] font-bold">
                  <Activity className="w-4 h-4" />
                  <span>Live Fee &amp; Break-Even Accounting:</span>
                </div>
                <div className="grid grid-cols-2 gap-2 text-[11px] text-[#94A3B8]">
                  <div>
                    <span>Maker Fees (Roundtrip):</span>
                    <span className="font-bold text-white block">0.040%</span>
                  </div>
                  <div>
                    <span>Friction &amp; Funding:</span>
                    <span className="font-bold text-white block">0.010%</span>
                  </div>
                  <div>
                    <span>Gross Break-Even Required:</span>
                    <span className="font-bold text-[#00E5FF] block">+{safeNum(breakEvenMath?.requiredMovePct, 3)}%</span>
                  </div>
                  <div>
                    <span>Net Gain at Target:</span>
                    <span className="font-bold text-[#10B981] block">
                      +${safeNum(breakEvenMath?.estDollarProfit, 2)} (+{safeNum(breakEvenMath?.netReturnPct, 2)}%)
                    </span>
                  </div>
                </div>
              </div>

              {/* Modal Actions */}
              <div className="pt-2 flex items-center justify-end gap-3 border-t border-[#272735]">
                <button
                  type="button"
                  onClick={() => setIsConfigModalOpen(false)}
                  className="px-4 py-2 rounded-xl bg-[#181822] hover:bg-[#272735] text-[#94A3B8] hover:text-white font-bold cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={savingConfig}
                  className="px-5 py-2 rounded-xl bg-[#00E5FF] hover:bg-[#00E5FF]/90 text-[#0B0E11] font-bold cursor-pointer shadow-md shadow-[#00E5FF]/20 flex items-center gap-1.5"
                >
                  {savingConfig && <RefreshCw className="w-4 h-4 animate-spin" />}
                  <span>Save &amp; Validate Configuration</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
      {/* ─── PHASE 2: $20.00 USD ONE-TIME HFT ACCOUNT ACTIVATION MODAL ─────── */}
      {isActivationModalOpen && (
        <div
          id="hft-activation-modal"
          className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto"
        >
          <div className="bg-[#121218] border border-[#272735] rounded-2xl max-w-lg w-full p-5 sm:p-6 space-y-5 shadow-2xl font-mono">
            <div className="flex items-start justify-between gap-3 border-b border-[#272735] pb-4">
              <div className="space-y-1">
                <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-amber-500/15 border border-amber-500/30 text-amber-400 text-[10px] font-bold uppercase">
                  <Lock className="w-3 h-3" />
                  <span>One-Time HFT Account Activation</span>
                </div>
                <h3 className="text-base sm:text-lg font-bold text-white">
                  Activate Your BITDEX Account
                </h3>
                <p className="text-xs text-[#94A3B8]">
                  Your account must be activated before you can use High-Frequency Trading.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setIsActivationModalOpen(false)}
                className="text-[#94A3B8] hover:text-white cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Fee Display Card */}
            <div className="p-4 rounded-xl bg-[#0A0A0E] border border-[#00E5FF]/40 flex items-center justify-between">
              <div>
                <span className="text-[11px] text-[#94A3B8] block uppercase">One-Time Activation Fee</span>
                <span className="text-2xl font-extrabold text-[#00E5FF]">$20.00 USD</span>
              </div>
              <div className="text-right text-[11px] text-[#10B981]">
                <span className="font-bold block">LIFETIME HFT ACCESS</span>
                <span className="text-[#94A3B8]">No recurring monthly fee</span>
              </div>
            </div>

            {/* What Activation Unlocks */}
            <div className="space-y-2 text-xs text-[#94A3B8]">
              <div className="text-white font-bold">What $20.00 Activation Unlocks:</div>
              <div className="flex items-start gap-2">
                <CheckCircle2 className="w-4 h-4 text-[#10B981] shrink-0 mt-0.5" />
                <span>Unlocks HFT Strategy Configuration &amp; Autonomous Session Controls</span>
              </div>
              <div className="flex items-start gap-2">
                <CheckCircle2 className="w-4 h-4 text-[#10B981] shrink-0 mt-0.5" />
                <span>Enables Exness MT5 &amp; Binance Futures HFT Execution Gateways</span>
              </div>
              <div className="flex items-start gap-2">
                <CheckCircle2 className="w-4 h-4 text-[#10B981] shrink-0 mt-0.5" />
                <span>Activates Real-Time Pre-Trade Quantitative Risk Guard &amp; Watchdog</span>
              </div>
            </div>

            {/* Payment Method & Verification Step */}
            {!activationCheckoutData ? (
              <div className="space-y-3 pt-1">
                <label className="block text-xs text-[#94A3B8]">
                  Select Payment Settlement Method:
                </label>
                <div className="grid grid-cols-2 gap-2.5 text-xs">
                  <button
                    type="button"
                    onClick={() => setActivationProvider("BINANCE_PAY")}
                    className={`p-3 rounded-xl border text-left transition-all cursor-pointer ${
                      activationProvider === "BINANCE_PAY"
                        ? "bg-[#00E5FF]/15 border-[#00E5FF] text-white font-bold"
                        : "bg-[#0A0A0E] border-[#272735] text-[#94A3B8]"
                    }`}
                  >
                    <div className="text-white font-bold">Binance Pay</div>
                    <div className="text-[10px] text-[#94A3B8]">Instant $20 USDT/USD</div>
                  </button>
                  <button
                    type="button"
                    onClick={() => setActivationProvider("CRYPTO_USDT")}
                    className={`p-3 rounded-xl border text-left transition-all cursor-pointer ${
                      activationProvider === "CRYPTO_USDT"
                        ? "bg-[#00E5FF]/15 border-[#00E5FF] text-white font-bold"
                        : "bg-[#0A0A0E] border-[#272735] text-[#94A3B8]"
                    }`}
                  >
                    <div className="text-white font-bold">USDT Direct</div>
                    <div className="text-[10px] text-[#94A3B8]">TRC20 / ERC20 Verified</div>
                  </button>
                </div>
              </div>
            ) : (
              <div className="p-3.5 rounded-xl bg-[#0A0A0E] border border-amber-500/40 space-y-2 text-xs">
                <div className="flex items-center justify-between text-amber-400 font-bold">
                  <span>Payment Invoice Generated</span>
                  <span>{activationCheckoutData.payment_reference}</span>
                </div>
                <div className="text-[11px] text-[#94A3B8]">
                  Amount Due: <strong className="text-white">${safeNum(activationCheckoutData?.amount, 2)} {activationCheckoutData.currency}</strong> via <strong className="text-white">{activationCheckoutData.provider}</strong>
                </div>
              </div>
            )}

            {/* Modal Footer Buttons */}
            <div className="pt-3 border-t border-[#272735] flex flex-wrap items-center justify-between gap-3">
              <button
                type="button"
                id="btn-continue-viewing-hft"
                onClick={() => {
                  setActivationCheckoutData(null);
                  setIsActivationModalOpen(false);
                }}
                className="px-4 py-2.5 rounded-xl bg-[#181822] hover:bg-[#272735] text-[#94A3B8] hover:text-white text-xs font-bold cursor-pointer"
              >
                Continue Viewing Dashboard
              </button>

              {!activationCheckoutData ? (
                <button
                  type="button"
                  id="btn-pay-activate-20"
                  disabled={activationBusy}
                  onClick={handleInitiateActivationCheckout}
                  className="px-5 py-2.5 rounded-xl bg-[#00E5FF] hover:bg-[#00E5FF]/90 text-[#0B0E11] text-xs font-extrabold cursor-pointer shadow-lg shadow-[#00E5FF]/20 flex items-center gap-2"
                >
                  {activationBusy && <RefreshCw className="w-4 h-4 animate-spin" />}
                  <span>Pay $20.00 &amp; Activate Account</span>
                </button>
              ) : (
                <button
                  type="button"
                  id="btn-confirm-activate-20"
                  disabled={activationBusy}
                  onClick={handleCompleteActivationPayment}
                  className="px-5 py-2.5 rounded-xl bg-[#10B981] hover:bg-[#10B981]/90 text-[#0B0E11] text-xs font-extrabold cursor-pointer shadow-lg shadow-[#10B981]/20 flex items-center gap-2"
                >
                  {activationBusy && <RefreshCw className="w-4 h-4 animate-spin" />}
                  <span>Verify $20.00 Payment &amp; Unlock HFT</span>
                </button>
              )}
            </div>
          </div>
        </div>
      )}
      {consentModalOpen && selectedAccount && (
        <div className="fixed inset-0 z-[100] bg-black/80 backdrop-blur-sm flex items-center justify-center p-4" role="dialog" aria-modal="true" id="real-consent-modal">
          <div className="w-full max-w-lg rounded-2xl bg-[#121218] border border-[#F6465D]/40 shadow-2xl p-5 sm:p-6 space-y-4 font-mono max-h-[92vh] overflow-y-auto">
            <div className="flex items-center justify-between gap-2 border-b border-[#272735] pb-3">
              <div className="flex items-center gap-2 text-[#F6465D]">
                <AlertTriangle className="w-5 h-5 shrink-0" />
                <h3 className="text-xs sm:text-sm font-bold uppercase">
                  One-Time Real Account Authentication &amp; Voluntary Consent
                </h3>
              </div>
              <span className="text-[10px] px-2 py-0.5 rounded bg-rose-950/60 text-rose-400 border border-rose-500/30 font-bold">
                REAL-CONSENT-v2
              </span>
            </div>

            <div className="p-3 rounded-xl bg-[#0A0A0E] border border-[#272735] flex items-center justify-between text-xs">
              <span className="text-[#94A3B8]">Selected Real Account:</span>
              <span className="font-bold text-white">{selectedAccount.display_label}</span>
            </div>

            {consentError && (
              <div className="p-3 rounded-xl bg-rose-950/40 border border-rose-500/40 text-xs text-rose-300 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 shrink-0 text-rose-400" />
                <span>{consentError}</span>
              </div>
            )}

            <ul className="text-xs text-[#94A3B8] space-y-1.5 list-disc pl-5">
              <li>This account uses real money. You can lose part or all of the funds allocated.</li>
              <li>Leveraged positions can be liquidated, and losses can exceed your expectations.</li>
              <li>Trading fees, spreads, swaps and slippage apply and reduce returns.</li>
              <li>Live execution remains locked by platform safety controls (<code>live_trading_locked = True</code>).</li>
            </ul>

            {/* Step 1: Step-Up Authentication */}
            <div className="space-y-1.5 pt-1">
              <label htmlFor="real-consent-step-up-password" className="text-[11px] font-bold text-white uppercase block">
                1. Step-Up Authentication (Account Password or Email Verification)
              </label>
              <input
                type="password"
                id="real-consent-step-up-password"
                value={stepUpPassword}
                onChange={(e) => setStepUpPassword(e.target.value)}
                placeholder="Enter your BITDEX password to verify identity"
                className="w-full px-3 py-2.5 rounded-lg bg-[#0A0A0E] border border-[#272735] text-xs text-white focus:outline-none focus:border-[#00E5FF]"
              />
            </div>

            {/* Step 2: Explicit Voluntary Consent Checkbox */}
            <div className="p-3.5 rounded-xl bg-[#0A0A0E] border border-[#272735]">
              <label className="flex items-start gap-2.5 text-xs text-white cursor-pointer select-none">
                <input
                  type="checkbox"
                  id="real-consent-checkbox"
                  checked={consentChecked}
                  onChange={(e) => setConsentChecked(e.target.checked)}
                  className="mt-0.5 shrink-0"
                />
                <span className="leading-relaxed">
                  I voluntarily authorise BITDEX to use my selected REAL trading account for High-Frequency Trading. I understand that trading involves financial risk and that losses may occur.
                </span>
              </label>
            </div>

            {/* Step 3: Explicit Confirmation Button */}
            <div className="flex flex-wrap justify-end gap-2.5 pt-2 border-t border-[#272735]">
              <button
                type="button"
                onClick={() => {
                  setConsentModalOpen(false);
                  setPendingAction(null);
                }}
                className="px-4 py-2 rounded-lg bg-[#181822] border border-[#272735] text-xs text-[#94A3B8] hover:text-white cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                id="real-consent-confirm"
                disabled={!consentChecked || !stepUpPassword.trim() || consentBusy}
                onClick={submitRealConsent}
                className={`px-4 py-2 rounded-lg text-xs font-bold transition-all ${
                  consentChecked && stepUpPassword.trim() && !consentBusy
                    ? "bg-[#F6465D] hover:bg-[#F6465D]/90 text-white cursor-pointer shadow-lg shadow-[#F6465D]/20"
                    : "bg-[#181822] text-[#64748B] cursor-not-allowed"
                }`}
              >
                {consentBusy ? "Authenticating & Recording…" : "Authenticate & Confirm Real-Account Consent"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
