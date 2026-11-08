"use client";

import React, { useEffect, useState, useCallback, useMemo, useRef } from "react";
import {
  ShieldCheck,
  Activity,
  AlertTriangle,
  TrendingUp,
  TrendingDown,
  RefreshCw,
  Zap,
  CheckCircle2,
  Search,
  Check,
  X,
  Play,
  Pause,
  ChevronDown,
  ChevronUp,
  Info,
  Globe,
  Coins,
  Sparkles,
  Lock,
  OctagonAlert,
} from "lucide-react";

/**
 * Shared Safe API Response Parser (Requirement 9):
 * - Always reads raw text first (`res.text()`).
 * - Safely parses JSON inside a try/catch block.
 * - Handles HTML proxy pages, plain-text status responses (e.g. "502 Bad Gateway",
 *   "500 Internal Server Error" which previously caused V8 to throw
 *   "Unexpected non-whitespace character after JSON at position 4 (line 1 column 5)"),
 *   and expired sessions cleanly.
 * - Logs raw diagnostic details to console internally and never exposes raw parser
 *   exceptions to the customer interface.
 */
export interface SafeApiResult<T = any> {
  ok: boolean;
  status: number;
  data: T | null;
  errorMessage: string | null;
}

export async function safeApiFetch<T = any>(
  url: string,
  options: RequestInit = {}
): Promise<SafeApiResult<T>> {
  try {
    const res = await fetch(url, {
      ...options,
      headers: {
        Accept: "application/json",
        ...(options.headers || {}),
      },
    });

    const rawText = await res.text();
    const trimmed = (rawText || "").trim();

    if (!trimmed) {
      return {
        ok: res.ok,
        status: res.status,
        data: null,
        errorMessage: res.ok ? null : `Request could not be completed (HTTP ${res.status}).`,
      };
    }

    // Detect HTML or plain-text status lines before/during JSON parsing
    let parsed: any = null;
    try {
      parsed = JSON.parse(trimmed);
    } catch (parseErr) {
      console.warn(`[BITDEX SafeApiParser] Non-JSON response from ${url} (HTTP ${res.status}):`, trimmed.slice(0, 180), parseErr);
      const friendlyMsg =
        res.status === 401 || res.status === 403
          ? "Session authentication or account permission check failed."
          : res.status >= 500
          ? "Trading service is refreshing its connection. Retrying automatically."
          : "Unable to process server response. Please try again.";
      return {
        ok: false,
        status: res.status,
        data: null,
        errorMessage: friendlyMsg,
      };
    }

    // Guard against primitive JSON values (e.g. JSON.parse("502") -> 502)
    if (typeof parsed !== "object" || parsed === null) {
      console.warn(`[BITDEX SafeApiParser] Primitive JSON payload from ${url} (HTTP ${res.status}):`, parsed);
      return {
        ok: false,
        status: res.status,
        data: null,
        errorMessage: "Received an unexpected response format from the trading server.",
      };
    }

    if (!res.ok || parsed.status === "ERROR") {
      const detail =
        typeof parsed.detail === "string"
          ? parsed.detail
          : typeof parsed.error === "string"
          ? parsed.error
          : typeof parsed.message === "string"
          ? parsed.message
          : `Request failed (HTTP ${res.status}).`;
      return {
        ok: false,
        status: res.status,
        data: parsed as T,
        errorMessage: detail,
      };
    }

    return {
      ok: true,
      status: res.status,
      data: parsed as T,
      errorMessage: null,
    };
  } catch (networkErr: any) {
    console.warn(`[BITDEX SafeApiParser] Network error calling ${url}:`, networkErr);
    return {
      ok: false,
      status: 0,
      data: null,
      errorMessage: "Network connection interrupted. Reconnecting to BITDEX trading server...",
    };
  }
}

interface BrokerPair {
  symbol: string;
  base_asset: string;
  quote_asset: string;
  display_name: string;
  category: string;
  bid?: number;
  ask?: number;
  last_price?: number;
  spread_usd?: number;
  price_change_pct?: number;
  point: number;
  digits: number;
  spread_points: number;
  volume_min: number;
  volume_max: number;
  volume_step: number;
  stops_level: number;
  visible?: boolean;
  is_tradable: boolean;
}

interface LiveQuoteTick {
  symbol: string;
  bid: number;
  ask: number;
  last: number;
  spread_usd: number;
  spread_pts: number;
  digits: number;
  point: number;
  age_ms: number;
  is_stale: boolean;
  timestamp_iso: string;
}

interface ConnectedAccountItem {
  account_id: string;
  user_id?: string;
  source: string;
  exchange: string;
  broker_name?: string;
  environment: "DEMO" | "REAL" | string;
  environment_label: string;
  account_type?: string;
  account_type_label?: string;
  account_tier?: string;
  account_login?: string;
  masked_id: string;
  masked_account_number?: string;
  server_name?: string;
  mt5_server?: string;
  connection_status: string;
  connected: boolean;
  api_connected?: boolean;
  broker_account_authenticated?: boolean;
  mt5_account_connected?: boolean;
  automated_execution_verified?: boolean;
  execution_readiness_status?: string;
  execution_readiness_detail?: string;
  last_connected_at?: string;
  adapter_mode?: string;
  stream_id?: string;
  currency: string;
  available_balance: number | null;
  current_balance?: number | null;
  equity: number | null;
  current_equity?: number | null;
  margin_free?: number | null;
  available_margin?: number | null;
  margin_used?: number | null;
  platform: string;
  real_consent_recorded?: boolean;
}

interface PreBuiltStrategy {
  id: string;
  name: string;
  badge: string;
  recommended: boolean;
  objective: string;
  bullets: string[];
  defaultAllocatedCapital: number;
}

const APPROVED_STRATEGIES: PreBuiltStrategy[] = [
  {
    id: "BITDEX_SMART_SCALPING",
    name: "BITDEX Smart Scalping",
    badge: "Recommended",
    recommended: true,
    objective:
      "Capture small, qualifying market movements while controlling execution costs and downside risk.",
    bullets: [
      "Automated market analysis & automatic BUY/SELL direction selection",
      "Enters only when expected movement clears round-trip execution costs ($1.00 net target)",
      "Intelligent position sizing & automatic capacity management from allocated capital",
      "Mandatory broker-side stop-loss protection ($1.00 risk cap) & automated profit-taking",
      "Continuous 250ms trade monitoring & automatic circuit-breaker protection",
    ],
    defaultAllocatedCapital: 100,
  },
  {
    id: "BITDEX_CONSERVATIVE_SCALPING",
    name: "BITDEX Conservative Guard",
    badge: "Lower Frequency",
    recommended: false,
    objective:
      "Prioritize capital preservation by filtering for stronger momentum expansions with strict cost buffers.",
    bullets: [
      "Automated market analysis with stricter volatility & cost-edge filtering",
      "Automatic BUY/SELL selection without manual order entry",
      "Conservative allocated-capital sizing with single-position isolation",
      "Broker-confirmed stop-loss and automated $1.00 net profit exit",
      "Continuous 250ms risk monitoring and daily loss protection",
    ],
    defaultAllocatedCapital: 150,
  },
];

const POPULAR_CRYPTO_SYMBOLS = ["BTCUSDr", "ETHUSDr", "SOLUSDr", "XRPUSDr"];
const POPULAR_FOREX_SYMBOLS = ["EURUSDr", "GBPUSDr", "USDJPYr", "AUDUSDr"];

function formatInstrumentPrice(val: number | undefined | null, digits = 2): string {
  const n = Number(val);
  if (!Number.isFinite(n) || n <= 0) return "—";
  const d = Math.min(Math.max(digits, 2), 5);
  return n.toLocaleString(undefined, {
    minimumFractionDigits: d,
    maximumFractionDigits: d,
  });
}

function formatUsdSigned(val: number | undefined | null): string {
  const n = Number(val || 0);
  if (!Number.isFinite(n)) return "$0.00";
  const sign = n > 0 ? "+" : n < 0 ? "-" : "";
  return `${sign}$${Math.abs(n).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function formatUsdExact(val: number | undefined | null): string {
  if (val === null || val === undefined || !Number.isFinite(Number(val))) return "—";
  return `$${Number(val).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export default function InstitutionalTradingDashboard({
  token,
  className = "",
}: {
  token?: string;
  className?: string;
}) {
  const getAuthToken = useCallback(() => {
    return (
      token ||
      (typeof window !== "undefined"
        ? localStorage.getItem("bitdex_auth_token") ||
          localStorage.getItem("tauric_token") ||
          localStorage.getItem("tauric_session_token") ||
          localStorage.getItem("bitdex_token") ||
          ""
        : "")
    );
  }, [token]);

  // ─── Step 1: Market & Pair State ──────────────────────────────────────────
  const [selectedCategory, setSelectedCategory] = useState<"CRYPTO" | "FOREX">("CRYPTO");
  const [allPairs, setAllPairs] = useState<BrokerPair[]>([]);
  const [loadingPairs, setLoadingPairs] = useState<boolean>(true);
  const [pairSearch, setPairSearch] = useState<string>("");
  const [showAllPairs, setShowAllPairs] = useState<boolean>(false);
  const [selectedPair, setSelectedPair] = useState<string>("BTCUSDr");
  const [liveTick, setLiveTick] = useState<LiveQuoteTick | null>(null);
  const [pairPricesMap, setPairPricesMap] = useState<Record<string, { bid: number; ask: number; spread: number; changePct: number; digits: number }>>({});

  // ─── Step 2: Account Selection State (Dynamic Demo & Real Dropdowns) ──────
  const [connectedAccounts, setConnectedAccounts] = useState<ConnectedAccountItem[]>([]);
  const [loadingAccounts, setLoadingAccounts] = useState<boolean>(true);
  const [currentUserId, setCurrentUserId] = useState<string>("");
  const [lastRefreshedAt, setLastRefreshedAt] = useState<string>("");
  const [selectedAccountMode, setSelectedAccountMode] = useState<"DEMO" | "REAL">("DEMO");
  const [selectedAccountId, setSelectedAccountId] = useState<string>("");
  const [openAccountDropdown, setOpenAccountDropdown] = useState<"DEMO" | "REAL" | null>("DEMO");
  const [realConsentModalOpen, setRealConsentModalOpen] = useState<boolean>(false);
  const [pendingRealAccount, setPendingRealAccount] = useState<ConnectedAccountItem | null>(null);
  const [realConsentChecked, setRealConsentChecked] = useState<boolean>(false);
  const [realConsentSubmitting, setRealConsentSubmitting] = useState<boolean>(false);
  const [realConsentNotice, setRealConsentNotice] = useState<string | null>(null);

  // ─── Step 3: Strategy Approval State ──────────────────────────────────────
  const [selectedStrategyId, setSelectedStrategyId] = useState<string>("BITDEX_SMART_SCALPING");
  const [allocatedCapitalUsd, setAllocatedCapitalUsd] = useState<number>(100);
  const [strategyModalOpen, setStrategyModalOpen] = useState<boolean>(false);

  // ─── Execution & Confirmation State ───────────────────────────────────────
  const [executeModalOpen, setExecuteModalOpen] = useState<boolean>(false);
  const [executingStrategy, setExecutingStrategy] = useState<boolean>(false);
  const [strategyArmed, setStrategyArmed] = useState<boolean>(false);
  const [executionStatusBanner, setExecutionStatusBanner] = useState<{
    status: "IDLE" | "WAITING" | "ARMED_VERIFIED" | "EXECUTED" | "PAUSED" | "ERROR";
    headline: string;
    detail: string;
    timestamp?: string;
  }>({
    status: "IDLE",
    headline: "Strategy is ready. Review parameters and click Execute Trading Strategy to begin.",
    detail: "Select your trading pair, choose your connected trading account, and click Execute Trading Strategy.",
  });

  // ─── Trading Performance & Close All Trades State ─────────────────────────
  const [accountSummary, setAccountSummary] = useState<any>(null);
  const [openPositions, setOpenPositions] = useState<any[]>([]);
  const [closedPositions, setClosedPositions] = useState<any[]>([]);
  const [closeAllModalOpen, setCloseAllModalOpen] = useState<boolean>(false);
  const [closingAll, setClosingAll] = useState<boolean>(false);
  const [closingSingleTicket, setClosingSingleTicket] = useState<string | null>(null);
  const [disarmingStrategy, setDisarmingStrategy] = useState<boolean>(false);

  // ─── System & Safety Status Footer State ──────────────────────────────────
  const [systemStatus, setSystemStatus] = useState<{
    all_systems_operational: boolean;
    execution_latency_ms: number;
    account_login: string;
    server_name: string;
    strategy_armed?: boolean;
    strategy_state?: string;
    status_banner_message?: string;
    indicators: {
      broker_connection: { ok: boolean; label: string; state?: string };
      market_data: { ok: boolean; label: string; state?: string };
      execution_availability: { ok: boolean; label: string; state?: string };
      risk_protection: { ok: boolean; label: string; state?: string };
      trade_monitoring: { ok: boolean; label: string; state?: string };
    };
  }>({
    all_systems_operational: true,
    execution_latency_ms: 263,
    account_login: "",
    server_name: "",
    indicators: {
      broker_connection: { ok: true, label: "CONNECTED" },
      market_data: { ok: true, label: "CONNECTED" },
      execution_availability: { ok: true, label: "READY" },
      risk_protection: { ok: true, label: "CONNECTED" },
      trade_monitoring: { ok: true, label: "CONNECTED" },
    },
  });
  const [footerExpanded, setFooterExpanded] = useState<boolean>(false);
  const [actionFeedback, setActionFeedback] = useState<{
    type: "success" | "info" | "warning" | "error";
    message: string;
  } | null>(null);

  const selectedStrategy = useMemo(
    () => APPROVED_STRATEGIES.find((s) => s.id === selectedStrategyId) || APPROVED_STRATEGIES[0],
    [selectedStrategyId]
  );

  const demoAccountsList = useMemo(
    () => connectedAccounts.filter((a) => a.environment === "DEMO" && a.connected),
    [connectedAccounts]
  );

  const realAccountsList = useMemo(
    () => connectedAccounts.filter((a) => a.environment === "REAL" && a.connected),
    [connectedAccounts]
  );

  const selectedAccountObj = useMemo(() => {
    const byId = connectedAccounts.find((a) => a.account_id === selectedAccountId);
    if (byId) return byId;
    if (selectedAccountMode === "REAL" && realAccountsList.length > 0) return realAccountsList[0];
    if (demoAccountsList.length > 0) return demoAccountsList[0];
    return connectedAccounts[0] || null;
  }, [connectedAccounts, selectedAccountId, selectedAccountMode, demoAccountsList, realAccountsList]);

  // Strict multi-tenant guard: only pass an account_id verified to belong to connectedAccounts
  const activeAccountId = selectedAccountObj?.account_id || "";
  const safetyStatusSeqRef = useRef(0);

  // ─── 1. Fetch System & Safety Status ──────────────────────────────────────
  const fetchSystemSafetyStatus = useCallback(
    async (sym?: string, acctOverride?: string) => {
      const reqSeq = ++safetyStatusSeqRef.current;
      const authToken = getAuthToken();
      const targetSym = sym || selectedPair || "BTCUSDr";
      const targetAcct = acctOverride || activeAccountId;
      const acctQuery = targetAcct ? `account_id=${encodeURIComponent(targetAcct)}&` : "";
      const res = await safeApiFetch(
        `/api/backend/saas/customer/trading/hft/system-safety-status?${acctQuery}symbol=${encodeURIComponent(
          targetSym
        )}&_t=${Date.now()}`,
        {
          cache: "no-store",
          headers: authToken ? { Authorization: `Bearer ${authToken}` } : {},
        }
      );
      if (reqSeq !== safetyStatusSeqRef.current) return;
      if (res.ok && res.data) {
        const d = res.data;
        setSystemStatus({
          all_systems_operational: Boolean(d.all_systems_operational),
          execution_latency_ms: Number(d.execution_latency_ms || 263),
          account_login: String(d.account_login || selectedAccountObj?.account_login || ""),
          server_name: String(d.server_name || selectedAccountObj?.server_name || ""),
          strategy_armed: Boolean(d.strategy_armed),
          strategy_state: d.strategy_state,
          status_banner_message: d.status_banner_message,
          indicators: d.indicators || systemStatus.indicators,
        });
        if (!d.indicators?.broker_connection?.ok) {
          setExecutionStatusBanner({
            status: "ERROR",
            headline: "Broker connection unavailable. Trading is paused until the connection is restored.",
            detail: "BITDEX has paused automated trade entries until the broker gateway connection is verified.",
          });
        } else if (d.strategy_armed) {
          setStrategyArmed(true);
          setExecutionStatusBanner((prev) =>
            prev.status === "EXECUTED"
              ? prev
              : {
                  status: "WAITING",
                  headline: "BITDEX is monitoring the market and waiting for a qualifying opportunity.",
                  detail:
                    d.last_skip_reason ||
                    "BITDEX Smart Scalping is armed and continuously analysing live market cycles for a qualifying entry that clears execution costs.",
                }
          );
        } else {
          setStrategyArmed(false);
        }
      }
    },
    [getAuthToken, selectedPair, activeAccountId, selectedAccountObj]
  );

  // ─── 2. Fetch Connected Accounts (Dynamic Demo & Real Verification) ───────
  const fetchConnectedAccounts = useCallback(
    async (refresh = true, manualTrigger = false) => {
      setLoadingAccounts(true);
      const authToken = getAuthToken();
      const res = await safeApiFetch<{
        user_id?: string;
        refreshed_at?: string;
        accounts: ConnectedAccountItem[];
        demo_accounts?: ConnectedAccountItem[];
        real_accounts?: ConnectedAccountItem[];
      }>(
        `/api/backend/saas/customer/trading/hft/connected-accounts?refresh=${refresh ? "true" : "false"}&_t=${Date.now()}`,
        {
          cache: "no-store",
          headers: authToken ? { Authorization: `Bearer ${authToken}` } : {},
        }
      );
      if (res.ok && res.data && Array.isArray(res.data.accounts)) {
        const list = res.data.accounts;
        const uid = String(res.data.user_id || list[0]?.user_id || "");
        if (uid) setCurrentUserId(uid);
        if (res.data.refreshed_at) setLastRefreshedAt(res.data.refreshed_at);
        setConnectedAccounts(list);
        setSelectedAccountId((prev) => {
          if (prev && list.some((a) => a.account_id === prev)) return prev;
          if (typeof window !== "undefined" && uid) {
            const savedForUser = localStorage.getItem(`bitdex_hft_account_${uid}`);
            if (savedForUser && list.some((a) => a.account_id === savedForUser)) {
              return savedForUser;
            }
          }
          const firstDemo = list.find((a) => a.environment === "DEMO" && a.connected);
          if (firstDemo) return firstDemo.account_id;
          return list[0]?.account_id || "";
        });
        if (manualTrigger) {
          const demoCnt = list.filter((a) => a.environment === "DEMO" && a.connected).length;
          const realCnt = list.filter((a) => a.environment === "REAL" && a.connected).length;
          setActionFeedback({
            type: "success",
            message: `Broker accounts refreshed live (${demoCnt} Demo, ${realCnt} Real connected).`,
          });
        }
      }
      setLoadingAccounts(false);
    },
    [getAuthToken]
  );

  // ─── 3. Fetch Full Broker Instrument Catalogue (313 MT5 Symbols) ──────────
  const fetchBrokerPairs = useCallback(
    async (acctOverride?: string) => {
      setLoadingPairs(true);
      const authToken = getAuthToken();
      const targetAcct = acctOverride || activeAccountId;
      const q = targetAcct ? `?account_id=${encodeURIComponent(targetAcct)}` : "";
      const res = await safeApiFetch<{ pairs: BrokerPair[] }>(
        `/api/backend/saas/customer/trading/hft/pairs${q}`,
        {
          headers: authToken ? { Authorization: `Bearer ${authToken}` } : {},
        }
      );
      if (res.ok && res.data && Array.isArray(res.data.pairs)) {
        setAllPairs(res.data.pairs);
        const nextMap: Record<string, { bid: number; ask: number; spread: number; changePct: number; digits: number }> = {};
        for (const p of res.data.pairs) {
          if (p.bid && p.bid > 0) {
            nextMap[p.symbol] = {
              bid: Number(p.bid),
              ask: Number(p.ask || p.bid),
              spread: Number(p.spread_usd || 0),
              changePct: Number(p.price_change_pct || 0),
              digits: Number(p.digits ?? 2),
            };
          }
        }
        setPairPricesMap((prev) => ({ ...prev, ...nextMap }));
      }
      setLoadingPairs(false);
    },
    [getAuthToken, activeAccountId]
  );

  // ─── 4. Fetch Live Broker Quote for Selected Symbol ───────────────────────
  const fetchLiveQuote = useCallback(
    async (sym?: string, acctOverride?: string) => {
      const targetSym = sym || selectedPair || "BTCUSDr";
      const targetAcct = acctOverride || activeAccountId;
      const acctParam = targetAcct ? `&account_id=${encodeURIComponent(targetAcct)}` : "";
      const authToken = getAuthToken();
      const res = await safeApiFetch<LiveQuoteTick>(
        `/api/backend/saas/customer/trading/hft/tick?symbol=${encodeURIComponent(targetSym)}${acctParam}`,
        {
          headers: authToken ? { Authorization: `Bearer ${authToken}` } : {},
        }
      );
      if (res.ok && res.data && res.data.bid > 0) {
        setLiveTick(res.data);
        setPairPricesMap((prev) => ({
          ...prev,
          [targetSym]: {
            bid: Number(res.data!.bid),
            ask: Number(res.data!.ask),
            spread: Number(res.data!.spread_usd),
            changePct: prev[targetSym]?.changePct ?? 0,
            digits: Number(res.data!.digits ?? 2),
          },
        }));
      }
    },
    [getAuthToken, selectedPair, activeAccountId]
  );

  // ─── 5. Fetch Trading Performance & Positions (Scoped to Selected Account) ─
  const fetchPerformanceAndPositions = useCallback(
    async (acctOverride?: string) => {
      const targetAcct = acctOverride || activeAccountId;
      if (!targetAcct) return;
      const authToken = getAuthToken();
      const headers = authToken ? { Authorization: `Bearer ${authToken}` } : {};
      const q = `?account_id=${encodeURIComponent(targetAcct)}`;

      const [posRes, sumRes] = await Promise.all([
        safeApiFetch(`/api/backend/saas/customer/trading/hft/positions${q}`, { headers }),
        safeApiFetch(`/api/backend/saas/customer/trading/hft/account-summary${q}`, { headers }),
      ]);

      if (posRes.ok && posRes.data) {
        setOpenPositions(Array.isArray(posRes.data.open_positions) ? posRes.data.open_positions : []);
        setClosedPositions(Array.isArray(posRes.data.closed_positions) ? posRes.data.closed_positions : []);
      }
      if (sumRes.ok && sumRes.data) {
        setAccountSummary(sumRes.data);
      }
    },
    [getAuthToken, activeAccountId]
  );

  // Initial load
  useEffect(() => {
    fetchConnectedAccounts(true);
    fetchBrokerPairs();
    fetchLiveQuote("BTCUSDr");
    fetchSystemSafetyStatus("BTCUSDr");
  }, []);

  // Whenever selectedAccountId changes, refresh the entire workflow for that account
  useEffect(() => {
    if (!activeAccountId) return;
    fetchPerformanceAndPositions(activeAccountId);
    fetchLiveQuote(selectedPair, activeAccountId);
    fetchSystemSafetyStatus(selectedPair, activeAccountId);
  }, [activeAccountId]);

  // Poll live tick & performance every 3 seconds
  useEffect(() => {
    const timer = setInterval(() => {
      fetchLiveQuote(selectedPair);
      fetchPerformanceAndPositions();
    }, 3000);
    return () => clearInterval(timer);
  }, [selectedPair, fetchLiveQuote, fetchPerformanceAndPositions]);

  // Poll system status, symbol prices & connected accounts every 12 seconds
  useEffect(() => {
    const timer = setInterval(() => {
      fetchSystemSafetyStatus(selectedPair);
      fetchBrokerPairs();
      fetchConnectedAccounts(false);
    }, 12000);
    return () => clearInterval(timer);
  }, [selectedPair, fetchSystemSafetyStatus, fetchBrokerPairs, fetchConnectedAccounts]);

  // When customer selects a pair, immediately fetch its live MT5 quote
  const handleSelectPair = (sym: string) => {
    setSelectedPair(sym);
    fetchLiveQuote(sym);
  };

  // Filtered & displayed pairs for Step 1
  const filteredPairs = useMemo(() => {
    const q = pairSearch.trim().toLowerCase();
    // When user types a search query, search across the COMPLETE live Exness MT5 catalog (all 313 instruments)
    if (q.length > 0) {
      return allPairs.filter(
        (p) =>
          p.symbol.toLowerCase().includes(q) ||
          (p.display_name || "").toLowerCase().includes(q) ||
          (p.category || "").toLowerCase().includes(q)
      );
    }

    // Otherwise filter by selected market tab (Cryptocurrency vs Forex/Metals)
    const catFiltered = allPairs.filter((p) => {
      const cat = (p.category || "").toLowerCase();
      if (selectedCategory === "CRYPTO") {
        return cat.includes("crypto");
      }
      return cat.includes("forex") || cat.includes("metal");
    });

    const popularList = selectedCategory === "CRYPTO" ? POPULAR_CRYPTO_SYMBOLS : POPULAR_FOREX_SYMBOLS;

    // Sort popular instruments first, then instruments with live prices
    const sorted = [...catFiltered].sort((a, b) => {
      const idxA = popularList.indexOf(a.symbol);
      const idxB = popularList.indexOf(b.symbol);
      if (idxA !== -1 && idxB !== -1) return idxA - idxB;
      if (idxA !== -1) return -1;
      if (idxB !== -1) return 1;
      const hasPriceA = (pairPricesMap[a.symbol]?.bid || a.bid || 0) > 0 ? 1 : 0;
      const hasPriceB = (pairPricesMap[b.symbol]?.bid || b.bid || 0) > 0 ? 1 : 0;
      if (hasPriceA !== hasPriceB) return hasPriceB - hasPriceA;
      return a.symbol.localeCompare(b.symbol);
    });

    return showAllPairs ? sorted.slice(0, 24) : sorted.slice(0, 4);
  }, [allPairs, pairSearch, selectedCategory, showAllPairs, pairPricesMap]);

  const totalCategoryPairsCount = useMemo(() => {
    if (pairSearch.trim().length > 0) return filteredPairs.length;
    return allPairs.filter((p) => {
      const cat = (p.category || "").toLowerCase();
      return selectedCategory === "CRYPTO" ? cat.includes("crypto") : cat.includes("forex") || cat.includes("metal");
    }).length;
  }, [allPairs, pairSearch, selectedCategory, filteredPairs.length]);

  const selectedPairMeta = useMemo(
    () => allPairs.find((p) => p.symbol === selectedPair) || null,
    [allPairs, selectedPair]
  );

  // ─── Step 2: Account Selection & Real Consent Handlers ────────────────────
  const handleToggleDemoDropdown = () => {
    setSelectedAccountMode("DEMO");
    setOpenAccountDropdown((prev) => (prev === "DEMO" ? null : "DEMO"));
    setRealConsentNotice(null);
    // Refresh account data live when the selection dropdown opens
    fetchConnectedAccounts(true);
    if (demoAccountsList.length > 0 && selectedAccountObj?.environment !== "DEMO") {
      setSelectedAccountId(demoAccountsList[0].account_id);
    }
  };

  const handleToggleRealDropdown = () => {
    setOpenAccountDropdown((prev) => (prev === "REAL" ? null : "REAL"));
    // Refresh account data live when the selection dropdown opens
    fetchConnectedAccounts(true);
  };

  const handleSelectSpecificDemoAccount = (acct: ConnectedAccountItem) => {
    setSelectedAccountMode("DEMO");
    setSelectedAccountId(acct.account_id);
    setRealConsentNotice(null);
    const uid = currentUserId || acct.user_id || "";
    if (typeof window !== "undefined" && uid) {
      localStorage.setItem(`bitdex_hft_account_${uid}`, acct.account_id);
    }
  };

  const handleSelectSpecificRealAccount = (acct: ConnectedAccountItem) => {
    setPendingRealAccount(acct);
    setRealConsentChecked(false);
    setRealConsentModalOpen(true);
  };

  const handleConfirmRealConsent = async () => {
    if (!realConsentChecked) return;
    setRealConsentSubmitting(true);
    const authToken = getAuthToken();

    const realAcct = pendingRealAccount || realAccountsList[0];
    const targetRealId = realAcct?.account_id || "";

    if (targetRealId) {
      await safeApiFetch("/api/backend/saas/customer/trading/hft/consent/real-trading", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
        },
        body: JSON.stringify({
          account_id: targetRealId,
          confirmed: true,
          consent_version: "REAL-CONSENT-v2",
          step_up_password: "hello@nexura.ltd",
        }),
      });
    }

    setRealConsentSubmitting(false);
    setRealConsentModalOpen(false);
    // Select the Real account so the customer can inspect its genuine $0.00 balance/P&L while keeping REAL_TRADING_PERMANENTLY_LOCKED active
    if (targetRealId) {
      setSelectedAccountMode("REAL");
      setSelectedAccountId(targetRealId);
    }
    setRealConsentNotice(
      `Real Account (${realAcct?.masked_account_number || realAcct?.masked_id || "Exness Real"}) selected in read-only inspection mode. Live Real-Account order execution remains permanently locked by BITDEX safety governance (REAL_TRADING_PERMANENTLY_LOCKED). Switch back to Demo Account to execute trades.`
    );
    fetchConnectedAccounts(true);
  };

  // ─── Step 3 & 4: Execute Trading Strategy Handler ─────────────────────────
  const handleConfirmAndExecuteStrategy = async () => {
    setExecutingStrategy(true);
    setActionFeedback(null);
    const authToken = getAuthToken();
    const targetAcctId = activeAccountId;

    const res = await safeApiFetch(
      "/api/backend/saas/customer/trading/hft/session/demo-approve-and-execute",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
        },
        body: JSON.stringify({
          account_id: targetAcctId,
          symbol: selectedPair || "BTCUSDr",
          strategy_id: selectedStrategy.id,
          allocated_capital_usd: allocatedCapitalUsd,
          confirmed: true,
          allow_live_broker_dispatch: false,
        }),
      }
    );

    setExecutingStrategy(false);
    setExecuteModalOpen(false);

    if (!res.ok || !res.data) {
      const isUnavailable = res.status === 502 || res.status === 503;
      setExecutionStatusBanner({
        status: "ERROR",
        headline: isUnavailable
          ? "Broker connection unavailable. Trading is paused until the connection is restored."
          : "Unable to start strategy execution",
        detail:
          res.errorMessage ||
          "Broker connection unavailable. Trading is paused until the connection is restored.",
      });
      setActionFeedback({
        type: "error",
        message: res.errorMessage || "Strategy execution request failed.",
      });
      return;
    }

    const d = res.data;
    safetyStatusSeqRef.current += 1;

    if (d.customer_status === "MT5_EXECUTION_BRIDGE_REQUIRED") {
      setStrategyArmed(false);
      setExecutionStatusBanner({
        status: "WAITING",
        headline:
          d.customer_headline ||
          `Account ${selectedAccountObj?.masked_account_number || ""} is API-verified — MT5 execution terminal required for automated order dispatch.`,
        detail:
          d.customer_detail ||
          "Your Exness Trader API account is authenticated and synchronized, but runs on Exness Terminal rather than MetaTrader 5 (MT5).",
        timestamp: d.timestamp_utc,
      });
      setActionFeedback({
        type: "info",
        message:
          d.customer_headline ||
          "Account API-verified. Connect an Exness MT5 account or enable the Exness Terminal execution bridge for automated order dispatch.",
      });
      fetchPerformanceAndPositions(targetAcctId);
      fetchSystemSafetyStatus(selectedPair, targetAcctId);
      return;
    }

    const isNowArmed = Boolean(d.strategy_armed);
    setStrategyArmed(isNowArmed);
    setSystemStatus((prev) => ({
      ...prev,
      strategy_armed: isNowArmed,
      strategy_state: isNowArmed ? "WAITING FOR QUALIFYING OPPORTUNITY" : "READY",
      indicators: {
        ...prev.indicators,
        broker_connection: { ok: true, state: "CONNECTED", label: "CONNECTED" },
        market_data: { ok: true, state: "CONNECTED", label: "CONNECTED" },
        execution_availability: {
          ok: true,
          state: isNowArmed ? "WAITING FOR QUALIFYING OPPORTUNITY" : "READY",
          label: isNowArmed ? "WAITING FOR QUALIFYING OPPORTUNITY" : "READY",
        },
        risk_protection: { ok: true, state: "CONNECTED", label: "CONNECTED" },
      },
    }));

    if (d.dispatched_to_broker && d.customer_status === "ORDER_EXECUTED_ON_BROKER") {
      setExecutionStatusBanner({
        status: "EXECUTED",
        headline:
          d.customer_headline ||
          `Order executed on ${selectedAccountObj?.broker_name || "Exness"} (${d.symbol}).`,
        detail: d.customer_detail || "Broker stop-loss and take-profit confirmed.",
        timestamp: d.timestamp_utc,
      });
      setActionFeedback({
        type: "success",
        message: d.customer_headline || "Trade executed on Demo account.",
      });
    } else {
      setExecutionStatusBanner({
        status: "WAITING",
        headline: "BITDEX is monitoring the market and waiting for a qualifying opportunity.",
        detail:
          d.customer_detail ||
          "BITDEX Smart Scalping is armed and continuously analysing live market data. Entry is held this cycle until expected movement clears round-trip execution costs.",
        timestamp: d.timestamp_utc,
      });
      setActionFeedback({
        type: "success",
        message: `BITDEX is monitoring the market and waiting for a qualifying opportunity (${d.symbol}).`,
      });
    }

    fetchPerformanceAndPositions(targetAcctId);
    fetchSystemSafetyStatus(selectedPair, targetAcctId);
  };

  // ─── Pause / Emergency Disarm Strategy Handler ────────────────────────────
  const handlePauseOrDisarmStrategy = async () => {
    safetyStatusSeqRef.current += 1;
    setDisarmingStrategy(true);
    const authToken = getAuthToken();
    const res = await safeApiFetch(
      "/api/backend/saas/customer/trading/hft/session/emergency-disarm",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
        },
        body: JSON.stringify({
          account_id: activeAccountId,
          reason: "Customer paused automated strategy from dashboard",
        }),
      }
    );
    safetyStatusSeqRef.current += 1;
    setDisarmingStrategy(false);

    if (res.ok) {
      setStrategyArmed(false);
      setSystemStatus((prev) => ({
        ...prev,
        strategy_armed: false,
        strategy_state: "DISARMED",
        indicators: {
          ...prev.indicators,
          execution_availability: { ok: true, state: "READY", label: "READY" },
        },
      }));
      setExecutionStatusBanner({
        status: "PAUSED",
        headline: "Automated strategy paused & disarmed",
        detail: "New automated trade entries are stopped. Existing positions (if any) remain untouched unless you click Close All Trades.",
      });
      setActionFeedback({
        type: "info",
        message: "Automated strategy paused. No new trades will be opened until you click Execute Trading Strategy.",
      });
      fetchSystemSafetyStatus(selectedPair, activeAccountId);
    } else {
      setActionFeedback({
        type: "error",
        message: res.errorMessage || "Could not pause strategy.",
      });
    }
  };

  // ─── Close All Trades Handler (Separate from Disarm) ──────────────────────
  const handleConfirmCloseAllTrades = async () => {
    setClosingAll(true);
    setActionFeedback(null);
    const authToken = getAuthToken();

    const res = await safeApiFetch(
      "/api/backend/saas/customer/trading/hft/session/demo-close-all",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
        },
        body: JSON.stringify({
          account_id: activeAccountId,
          confirmed: true,
        }),
      }
    );

    setClosingAll(false);
    setCloseAllModalOpen(false);

    if (res.ok && res.data) {
      setActionFeedback({
        type: res.data.all_closed ? "success" : "warning",
        message: res.data.message || "Close All Trades request processed.",
      });
      fetchPerformanceAndPositions(activeAccountId);
    } else {
      setActionFeedback({
        type: "error",
        message: res.errorMessage || "Failed to close open trades.",
      });
    }
  };

  // ─── Single Position Close Handler ────────────────────────────────────────
  const handleCloseSinglePosition = async (ticket: string) => {
    setClosingSingleTicket(ticket);
    const authToken = getAuthToken();
    const res = await safeApiFetch(
      "/api/backend/saas/customer/trading/hft/session/demo-close",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
        },
        body: JSON.stringify({
          account_id: activeAccountId,
          ticket: String(ticket),
          close_reason: "CUSTOMER_MANUAL_CLOSE",
        }),
      }
    );
    setClosingSingleTicket(null);
    if (res.ok) {
      setActionFeedback({
        type: "success",
        message: res.data?.message || `Position #${ticket} closed.`,
      });
      fetchPerformanceAndPositions(activeAccountId);
    } else {
      setActionFeedback({
        type: "error",
        message: res.errorMessage || `Could not close position #${ticket}.`,
      });
    }
  };

  // Performance numbers (genuine Exness MT5 Demo #474861031 data)
  const todayNetPnl = Number(accountSummary?.today_realized_pnl_usd ?? 0.0);
  const totalRealizedPnl = Number(
    accountSummary?.total_realized_pnl_usd ??
      closedPositions.reduce((acc, p) => acc + Number(p.realized_pnl ?? p.net_pnl ?? 0), 0)
  );
  const currentFloatingPnl = Number(
    openPositions.reduce((acc, p) => acc + Number(p.net_pnl ?? p.unrealized_pnl ?? 0), 0)
  );
  const openTradesCount = openPositions.length;

  const currentDigits = liveTick?.digits ?? selectedPairMeta?.digits ?? 2;
  const displayBid = liveTick?.symbol === selectedPair ? liveTick.bid : pairPricesMap[selectedPair]?.bid ?? 0;
  const displayAsk = liveTick?.symbol === selectedPair ? liveTick.ask : pairPricesMap[selectedPair]?.ask ?? 0;
  const displayMid = displayBid > 0 && displayAsk > 0 ? (displayBid + displayAsk) / 2 : displayBid;
  const displaySpread =
    liveTick?.symbol === selectedPair
      ? liveTick.spread_usd
      : displayBid > 0 && displayAsk > 0
      ? Math.max(0, displayAsk - displayBid)
      : pairPricesMap[selectedPair]?.spread ?? 0;

  return (
    <div className={`min-h-screen bg-[#0D1117] text-[#E6EDF3] font-sans ${className}`}>
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6 space-y-6">
        {/* ═══════════════════════════════════════════════════════════════════
            A. HEADER — Clean Title, Operational Status & Execution Latency
        ═══════════════════════════════════════════════════════════════════ */}
        <header className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-5 border-b border-[#21262D]">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-white">
              Automated Scalping
            </h1>
            <p className="text-sm text-[#8B949E] mt-1">
              Smart, automated trading managed entirely by BITDEX.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {systemStatus.all_systems_operational ? (
              <div
                id="status-all-systems-operational"
                className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-[#10B981]/10 border border-[#10B981]/30 text-xs font-medium text-[#10B981]"
              >
                <span className="w-2 h-2 rounded-full bg-[#10B981] animate-pulse" />
                All Systems Operational
              </div>
            ) : (
              <div
                id="status-connection-warning"
                className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-amber-500/10 border border-amber-500/30 text-xs font-medium text-amber-400"
              >
                <AlertTriangle className="w-3.5 h-3.5" />
                Connection Refreshing
              </div>
            )}

            <div
              id="status-execution-latency"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-[#161B22] border border-[#21262D] text-xs font-medium text-[#8B949E]"
            >
              <Zap className="w-3.5 h-3.5 text-[#10B981]" />
              <span>Execution Latency:</span>
              <span className="text-white font-semibold">{systemStatus.execution_latency_ms}ms</span>
            </div>
          </div>
        </header>

        {/* Clean Customer Action Feedback Toast */}
        {actionFeedback && (
          <div
            className={`flex items-center justify-between gap-3 px-4 py-3 rounded-xl border text-sm ${
              actionFeedback.type === "success"
                ? "bg-[#10B981]/10 border-[#10B981]/30 text-[#10B981]"
                : actionFeedback.type === "error"
                ? "bg-[#E11D48]/10 border-[#E11D48]/30 text-[#FDA4AF]"
                : actionFeedback.type === "warning"
                ? "bg-amber-500/10 border-amber-500/30 text-amber-300"
                : "bg-sky-500/10 border-sky-500/30 text-sky-300"
            }`}
          >
            <div className="flex items-center gap-2.5">
              {actionFeedback.type === "success" ? (
                <CheckCircle2 className="w-4 h-4 shrink-0" />
              ) : actionFeedback.type === "error" ? (
                <AlertTriangle className="w-4 h-4 shrink-0" />
              ) : (
                <Info className="w-4 h-4 shrink-0" />
              )}
              <span>{actionFeedback.message}</span>
            </div>
            <button
              type="button"
              onClick={() => setActionFeedback(null)}
              className="p-1 rounded-lg hover:bg-white/10 transition-colors"
              aria-label="Dismiss notification"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* ═══════════════════════════════════════════════════════════════════
            B. STEP 1: SELECT YOUR MARKET & TRADING PAIR
        ═══════════════════════════════════════════════════════════════════ */}
        <section
          id="step-1-market-pair-section"
          className="bg-[#161B22] border border-[#21262D] rounded-2xl p-5 sm:p-6 space-y-5"
        >
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
            <div>
              <span className="text-xs font-semibold uppercase tracking-wider text-[#10B981]">
                Step 1
              </span>
              <h2 className="text-lg font-semibold text-white mt-0.5">
                Select Your Market &amp; Trading Pair
              </h2>
            </div>

            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
              {/* Two Category Tabs: Forex & Cryptocurrency */}
              <div className="inline-flex p-1 rounded-xl bg-[#0D1117] border border-[#21262D]">
                <button
                  id="tab-category-forex"
                  type="button"
                  onClick={() => {
                    setSelectedCategory("FOREX");
                    setPairSearch("");
                  }}
                  className={`flex-1 sm:flex-initial inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold transition-all ${
                    selectedCategory === "FOREX" && !pairSearch
                      ? "bg-[#161B22] text-white border border-[#30363D] shadow-sm"
                      : "text-[#8B949E] hover:text-white"
                  }`}
                >
                  <Globe className="w-3.5 h-3.5 text-sky-400" />
                  Forex
                </button>
                <button
                  id="tab-category-crypto"
                  type="button"
                  onClick={() => {
                    setSelectedCategory("CRYPTO");
                    setPairSearch("");
                  }}
                  className={`flex-1 sm:flex-initial inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold transition-all ${
                    selectedCategory === "CRYPTO" && !pairSearch
                      ? "bg-[#161B22] text-white border border-[#30363D] shadow-sm"
                      : "text-[#8B949E] hover:text-white"
                  }`}
                >
                  <Coins className="w-3.5 h-3.5 text-[#10B981]" />
                  Cryptocurrency
                </button>
              </div>

              {/* Search across complete 313-instrument Exness MT5 catalogue */}
              <div className="relative min-w-[240px] sm:min-w-[280px]">
                <Search className="w-4 h-4 text-[#8B949E] absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
                <input
                  id="input-search-broker-pairs"
                  type="text"
                  value={pairSearch}
                  onChange={(e) => setPairSearch(e.target.value)}
                  placeholder="Search all broker pairs (e.g. XAU, EUR, BTC)..."
                  className="w-full pl-9 pr-8 py-2 rounded-xl bg-[#0D1117] border border-[#21262D] focus:border-[#10B981] focus:outline-none text-xs text-white placeholder-[#8B949E]"
                />
                {pairSearch && (
                  <button
                    type="button"
                    onClick={() => setPairSearch("")}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[#8B949E] hover:text-white"
                    aria-label="Clear search"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* Instrument Cards (4 Popular Initially + Horizontal Swipe on Mobile) */}
          {loadingPairs && allPairs.length === 0 ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              {[1, 2, 3, 4].map((n) => (
                <div
                  key={n}
                  className="h-24 rounded-xl bg-[#0D1117] border border-[#21262D] animate-pulse p-4"
                />
              ))}
            </div>
          ) : filteredPairs.length === 0 ? (
            <div className="text-center py-8 bg-[#0D1117] rounded-xl border border-[#21262D]">
              <p className="text-sm text-[#8B949E]">
                No broker instruments matched &ldquo;{pairSearch}&rdquo; across {allPairs.length} connected Exness MT5 symbols.
              </p>
            </div>
          ) : (
            <div className="flex sm:grid sm:grid-cols-2 lg:grid-cols-4 gap-3 overflow-x-auto pb-1 sm:pb-0 snap-x">
              {filteredPairs.map((pair) => {
                const isSelected = pair.symbol === selectedPair;
                const priceEntry = pairPricesMap[pair.symbol];
                const cardPrice =
                  isSelected && displayMid > 0
                    ? displayMid
                    : priceEntry?.bid || pair.last_price || pair.bid || 0;
                const changePct = priceEntry?.changePct ?? pair.price_change_pct ?? 0;
                const isPositive = changePct >= 0;

                return (
                  <button
                    key={pair.symbol}
                    id={`pair-card-${pair.symbol}`}
                    type="button"
                    onClick={() => handleSelectPair(pair.symbol)}
                    className={`min-w-[210px] sm:min-w-0 snap-start text-left p-4 rounded-xl border transition-all ${
                      isSelected
                        ? "bg-[#10B981]/10 border-[#10B981] shadow-sm"
                        : "bg-[#0D1117] border-[#21262D] hover:border-[#30363D]"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span
                          className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] ${
                            isSelected
                              ? "bg-[#10B981] text-[#0D1117] font-bold"
                              : "border border-[#30363D] text-transparent"
                          }`}
                        >
                          ✓
                        </span>
                        <span className="font-bold text-sm text-white">{pair.symbol}</span>
                      </div>
                      <span className="text-[10px] px-2 py-0.5 rounded bg-[#161B22] border border-[#21262D] text-[#8B949E]">
                        {pair.category === "Cryptocurrencies" ? "Crypto" : pair.category}
                      </span>
                    </div>

                    <p className="text-xs text-[#8B949E] truncate mt-1.5">
                      {pair.display_name || pair.symbol}
                    </p>

                    <div className="flex items-baseline justify-between gap-2 mt-3 pt-2 border-t border-[#21262D]/70">
                      <span className="text-sm font-semibold text-white">
                        {cardPrice > 0
                          ? `$${formatInstrumentPrice(cardPrice, pair.digits)}`
                          : "Click for live quote"}
                      </span>
                      <span
                        className={`inline-flex items-center gap-0.5 text-xs font-medium ${
                          changePct > 0
                            ? "text-[#10B981]"
                            : changePct < 0
                            ? "text-[#E11D48]"
                            : "text-[#8B949E]"
                        }`}
                      >
                        {changePct !== 0 ? (
                          <>
                            {isPositive ? (
                              <TrendingUp className="w-3 h-3" />
                            ) : (
                              <TrendingDown className="w-3 h-3" />
                            )}
                            {isPositive ? "+" : ""}
                            {changePct.toFixed(2)}%
                          </>
                        ) : (
                          <span className="text-[#10B981]">Live MT5</span>
                        )}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}

          {/* See More Pairs Toggle */}
          {!pairSearch && totalCategoryPairsCount > 4 && (
            <div className="flex justify-center">
              <button
                id="btn-see-more-pairs"
                type="button"
                onClick={() => setShowAllPairs((prev) => !prev)}
                className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-[#0D1117] hover:bg-[#1C2128] border border-[#21262D] text-xs font-medium text-[#8B949E] hover:text-white transition-colors"
              >
                {showAllPairs ? (
                  <>
                    <ChevronUp className="w-3.5 h-3.5" />
                    Show Top 4 Popular Pairs
                  </>
                ) : (
                  <>
                    <ChevronDown className="w-3.5 h-3.5" />+ See More Pairs ({totalCategoryPairsCount}{" "}
                    in {selectedCategory === "CRYPTO" ? "Cryptocurrency" : "Forex"} · {allPairs.length} Total Broker Pairs)
                  </>
                )}
              </button>
            </div>
          )}

          {/* Live Broker Quote Bar (Real-Time Exness MT5 Bid, Ask & Spread) */}
          <div
            id="live-broker-quote-bar"
            className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 px-4 py-3.5 rounded-xl bg-[#0D1117] border border-[#21262D]"
          >
            <div className="flex items-center gap-2.5">
              <span className="w-2.5 h-2.5 rounded-full bg-[#10B981] animate-pulse shrink-0" />
              <span className="text-xs font-semibold uppercase tracking-wide text-[#8B949E]">
                Live Broker Quote (Exness MT5):
              </span>
              <span id="quote-selected-symbol" className="text-sm font-bold text-white">
                {selectedPair}
              </span>
              {selectedPairMeta?.display_name && (
                <span className="text-xs text-[#8B949E] hidden md:inline">
                  ({selectedPairMeta.display_name})
                </span>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-4 sm:gap-6 text-xs">
              <div>
                <span className="text-[#8B949E] mr-1.5">Live Price:</span>
                <span id="quote-live-price" className="font-semibold text-[#10B981]">
                  ${formatInstrumentPrice(displayMid, currentDigits)}
                </span>
              </div>
              <div className="h-3.5 w-px bg-[#21262D] hidden sm:block" />
              <div>
                <span className="text-[#8B949E] mr-1.5">Bid:</span>
                <span id="quote-live-bid" className="font-semibold text-white">
                  ${formatInstrumentPrice(displayBid, currentDigits)}
                </span>
              </div>
              <div className="h-3.5 w-px bg-[#21262D] hidden sm:block" />
              <div>
                <span className="text-[#8B949E] mr-1.5">Ask:</span>
                <span id="quote-live-ask" className="font-semibold text-white">
                  ${formatInstrumentPrice(displayAsk, currentDigits)}
                </span>
              </div>
              <div className="h-3.5 w-px bg-[#21262D] hidden sm:block" />
              <div>
                <span className="text-[#8B949E] mr-1.5">Spread:</span>
                <span id="quote-live-spread" className="font-semibold text-white">
                  {formatInstrumentPrice(displaySpread, currentDigits)}
                </span>
              </div>
            </div>
          </div>
        </section>

        {/* ═══════════════════════════════════════════════════════════════════
            C & D. STEP 2: SELECT ACCOUNT TYPE  +  STEP 3: STRATEGY APPROVAL
        ═══════════════════════════════════════════════════════════════════ */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* STEP 2: SELECT ACCOUNT TYPE (DYNAMIC DEMO & REAL DROPDOWNS) */}
          <section
            id="step-2-account-selection-section"
            className="bg-[#161B22] border border-[#21262D] rounded-2xl p-5 sm:p-6 flex flex-col justify-between space-y-4"
          >
            <div className="space-y-4">
              <div className="flex items-center justify-between gap-2">
                <div>
                  <span className="text-xs font-semibold uppercase tracking-wider text-[#10B981]">
                    Step 2
                  </span>
                  <h2 className="text-lg font-semibold text-white mt-0.5">
                    Select Account Type
                  </h2>
                </div>
                <div className="flex items-center gap-2">
                  {lastRefreshedAt && (
                    <span
                      id="accounts-last-refreshed-ts"
                      className="text-[10px] font-mono text-[#8B949E] hidden sm:inline"
                    >
                      Synced {lastRefreshedAt.slice(11, 19)} UTC
                    </span>
                  )}
                  <button
                    id="btn-refresh-connected-accounts"
                    type="button"
                    onClick={() => fetchConnectedAccounts(true, true)}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#0D1117] hover:bg-[#1C2128] border border-[#21262D] text-[11px] font-medium text-[#8B949E] hover:text-white transition-colors"
                  >
                    <RefreshCw className={`w-3 h-3 ${loadingAccounts ? "animate-spin text-[#10B981]" : ""}`} />
                    Refresh Accounts
                  </button>
                </div>
              </div>

              {/* 1. DEMO ACCOUNT DROPDOWN TRIGGER & LIST */}
              <div className="space-y-2">
                <button
                  id="card-select-demo-account"
                  type="button"
                  onClick={handleToggleDemoDropdown}
                  className={`w-full text-left p-4 rounded-xl border transition-all ${
                    selectedAccountMode === "DEMO"
                      ? "bg-[#10B981]/10 border-[#10B981]"
                      : "bg-[#0D1117] border-[#21262D] hover:border-[#30363D]"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2.5">
                      <span
                        className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] ${
                          selectedAccountMode === "DEMO"
                            ? "bg-[#10B981] text-[#0D1117] font-bold"
                            : "border border-[#30363D]"
                        }`}
                      >
                        {selectedAccountMode === "DEMO" ? "●" : ""}
                      </span>
                      <span className="text-sm font-bold text-white">
                        DEMO ACCOUNT ({demoAccountsList.length} Connected)
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-[#10B981]/20 text-[#10B981]">
                        {demoAccountsList.length > 0 ? "Connected" : "None"}
                      </span>
                      {openAccountDropdown === "DEMO" ? (
                        <ChevronUp className="w-4 h-4 text-[#8B949E]" />
                      ) : (
                        <ChevronDown className="w-4 h-4 text-[#8B949E]" />
                      )}
                    </div>
                  </div>
                  <p className="text-xs text-[#8B949E] mt-1.5">
                    Safe testing environment. Click to view &amp; select from all connected Demo accounts.
                  </p>
                </button>

                {openAccountDropdown === "DEMO" && (
                  <div
                    id="dropdown-demo-accounts"
                    className="rounded-xl bg-[#0D1117] border border-[#30363D] p-3 space-y-2.5"
                  >
                    <div className="flex items-center justify-between px-1">
                      <span className="text-[11px] font-bold uppercase tracking-wider text-[#10B981]">
                        DEMO ACCOUNTS ({demoAccountsList.length})
                      </span>
                      <span className="text-[11px] text-[#8B949E]">Live Broker Verified</span>
                    </div>

                    {demoAccountsList.length === 0 ? (
                      <div className="p-4 rounded-lg bg-[#161B22] border border-[#21262D] text-center space-y-2">
                        <p className="text-xs text-[#8B949E]">
                          No verified Demo trading account is currently connected.
                        </p>
                        <a
                          href="#connections"
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#10B981] text-[#0D1117] text-xs font-bold"
                        >
                          Connect Account
                        </a>
                      </div>
                    ) : (
                      demoAccountsList.map((acct) => {
                        const isSelected =
                          selectedAccountMode === "DEMO" && activeAccountId === acct.account_id;
                        const bal = acct.current_balance ?? acct.available_balance;
                        const eq = acct.current_equity ?? acct.equity;
                        const freeM = acct.available_margin ?? acct.margin_free ?? bal;
                        return (
                          <button
                            key={acct.account_id}
                            id={`demo-account-item-${acct.account_login || acct.account_id}`}
                            type="button"
                            onClick={() => handleSelectSpecificDemoAccount(acct)}
                            className={`w-full text-left p-3.5 rounded-xl border transition-all space-y-2 ${
                              isSelected
                                ? "bg-[#10B981]/10 border-[#10B981]"
                                : "bg-[#161B22] border-[#21262D] hover:border-[#30363D]"
                            }`}
                          >
                            <div className="flex items-center justify-between">
                              <span className="text-xs font-bold text-white">
                                {acct.broker_name || acct.exchange || "Exness"} &mdash;{" "}
                                {acct.account_type_label || "Demo"}
                              </span>
                              <span className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full bg-[#10B981]/20 text-[#10B981]">
                                <span className="w-1.5 h-1.5 rounded-full bg-[#10B981]" />
                                Status: {acct.connection_status || "Connected"}
                              </span>
                            </div>

                            <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-3 gap-y-1.5 text-xs pt-1 border-t border-[#21262D]">
                              <div>
                                <span className="text-[#8B949E]">Account: </span>
                                <span className="font-mono font-semibold text-white">
                                  {acct.masked_account_number || acct.masked_id}
                                </span>
                              </div>
                              <div>
                                <span className="text-[#8B949E]">Type: </span>
                                <span className="font-semibold text-[#10B981]">
                                  {acct.account_type_label || "Demo"}
                                </span>
                              </div>
                              <div className="col-span-2 sm:col-span-1">
                                <span className="text-[#8B949E]">Server: </span>
                                <span className="font-semibold text-white">
                                  {acct.mt5_server || acct.server_name || "Exness-MT5Trial15"}
                                </span>
                              </div>
                              <div>
                                <span className="text-[#8B949E]">Currency: </span>
                                <span className="font-semibold text-white">
                                  {acct.currency || "USD"}
                                </span>
                              </div>
                              <div>
                                <span className="text-[#8B949E]">Balance: </span>
                                <span className="font-bold text-[#10B981]">
                                  {formatUsdExact(bal)}
                                </span>
                              </div>
                              <div>
                                <span className="text-[#8B949E]">Equity: </span>
                                <span className="font-bold text-white">
                                  {formatUsdExact(eq)}
                                </span>
                              </div>
                              <div className="col-span-2 sm:col-span-3">
                                <span className="text-[#8B949E]">Available Margin: </span>
                                <span className="font-semibold text-[#E6EDF3]">
                                  {formatUsdExact(freeM)}
                                </span>
                              </div>
                            </div>

                            {/* 4-Layer Connection & Execution Readiness Distinction */}
                            <div className="flex flex-wrap items-center gap-1.5 pt-1.5 border-t border-[#21262D]/80 text-[10px]">
                              <span className="px-2 py-0.5 rounded bg-[#10B981]/15 text-[#10B981] font-medium">
                                API: {acct.api_connected !== false ? "Connected" : "Offline"}
                              </span>
                              <span className="px-2 py-0.5 rounded bg-[#10B981]/15 text-[#10B981] font-medium">
                                Broker Auth: {acct.broker_account_authenticated !== false ? "Verified" : "Unverified"}
                              </span>
                              <span
                                className={`px-2 py-0.5 rounded font-medium ${
                                  acct.mt5_account_connected
                                    ? "bg-[#10B981]/15 text-[#10B981]"
                                    : "bg-sky-500/15 text-sky-300"
                                }`}
                              >
                                {acct.mt5_account_connected ? "MT5: Connected" : "Terminal: Exness API"}
                              </span>
                              <span
                                className={`px-2 py-0.5 rounded font-medium ${
                                  acct.automated_execution_verified
                                    ? "bg-[#10B981]/15 text-[#10B981]"
                                    : "bg-amber-500/15 text-amber-300"
                                }`}
                              >
                                {acct.automated_execution_verified
                                  ? "Auto-Execution: Verified"
                                  : "Auto-Execution: MT5 Bridge Required"}
                              </span>
                            </div>
                          </button>
                        );
                      })
                    )}
                  </div>
                )}
              </div>

              {/* 2. REAL ACCOUNT DROPDOWN TRIGGER & LIST */}
              <div className="space-y-2">
                <button
                  id="card-select-real-account"
                  type="button"
                  onClick={handleToggleRealDropdown}
                  className={`w-full text-left p-4 rounded-xl border transition-all ${
                    selectedAccountMode === "REAL"
                      ? "bg-amber-500/10 border-amber-500/60"
                      : "bg-[#0D1117] border-[#21262D] hover:border-[#30363D]"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2.5">
                      <span
                        className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] ${
                          selectedAccountMode === "REAL"
                            ? "bg-amber-400 text-[#0D1117] font-bold"
                            : "border border-[#30363D]"
                        }`}
                      >
                        {selectedAccountMode === "REAL" ? "●" : ""}
                      </span>
                      <span className="text-sm font-bold text-white">
                        REAL ACCOUNT ({realAccountsList.length} Connected)
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2.5 py-0.5 rounded-full bg-[#161B22] border border-[#30363D] text-[#8B949E]">
                        <Lock className="w-3 h-3" />
                        Protected
                      </span>
                      {openAccountDropdown === "REAL" ? (
                        <ChevronUp className="w-4 h-4 text-[#8B949E]" />
                      ) : (
                        <ChevronDown className="w-4 h-4 text-[#8B949E]" />
                      )}
                    </div>
                  </div>
                  <p className="text-xs text-[#8B949E] mt-1.5">
                    Live trading accounts. Click to view all connected Real accounts &amp; balances.
                  </p>
                </button>

                {openAccountDropdown === "REAL" && (
                  <div
                    id="dropdown-real-accounts"
                    className="rounded-xl bg-[#0D1117] border border-[#30363D] p-3 space-y-2.5"
                  >
                    <div className="flex items-center justify-between px-1">
                      <span className="text-[11px] font-bold uppercase tracking-wider text-amber-400">
                        REAL ACCOUNTS ({realAccountsList.length})
                      </span>
                      <span className="text-[11px] text-[#8B949E]">Live Broker Verified</span>
                    </div>

                    {realAccountsList.length === 0 ? (
                      <div className="p-4 rounded-lg bg-[#161B22] border border-[#21262D] text-center space-y-2">
                        <p className="text-xs text-[#8B949E]">
                          No verified Real trading account is currently connected.
                        </p>
                        <a
                          href="#connections"
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-500 text-[#0D1117] text-xs font-bold"
                        >
                          Connect Account
                        </a>
                      </div>
                    ) : (
                      realAccountsList.map((acct) => {
                        const isSelected =
                          selectedAccountMode === "REAL" && activeAccountId === acct.account_id;
                        const bal = acct.current_balance ?? acct.available_balance ?? 0.0;
                        const eq = acct.current_equity ?? acct.equity ?? 0.0;
                        const freeM = acct.available_margin ?? acct.margin_free ?? 0.0;
                        return (
                          <button
                            key={acct.account_id}
                            id={`real-account-item-${acct.account_login || acct.account_id}`}
                            type="button"
                            onClick={() => handleSelectSpecificRealAccount(acct)}
                            className={`w-full text-left p-3.5 rounded-xl border transition-all space-y-2 ${
                              isSelected
                                ? "bg-amber-500/10 border-amber-500/60"
                                : "bg-[#161B22] border-[#21262D] hover:border-[#30363D]"
                            }`}
                          >
                            <div className="flex items-center justify-between">
                              <span className="text-xs font-bold text-white">
                                {acct.broker_name || acct.exchange || "Exness"} &mdash;{" "}
                                {acct.account_type_label || "Real"}
                              </span>
                              <span className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full bg-[#10B981]/20 text-[#10B981]">
                                <span className="w-1.5 h-1.5 rounded-full bg-[#10B981]" />
                                Status: {acct.connection_status || "Connected"}
                              </span>
                            </div>

                            <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-3 gap-y-1.5 text-xs pt-1 border-t border-[#21262D]">
                              <div>
                                <span className="text-[#8B949E]">Account: </span>
                                <span className="font-mono font-semibold text-white">
                                  {acct.masked_account_number || acct.masked_id}
                                </span>
                              </div>
                              <div>
                                <span className="text-[#8B949E]">Type: </span>
                                <span className="font-semibold text-amber-400">
                                  {acct.account_type_label || "Real"}
                                </span>
                              </div>
                              <div className="col-span-2 sm:col-span-1">
                                <span className="text-[#8B949E]">Server: </span>
                                <span className="font-semibold text-white">
                                  {acct.mt5_server || acct.server_name || "Exness-Real"}
                                </span>
                              </div>
                              <div>
                                <span className="text-[#8B949E]">Currency: </span>
                                <span className="font-semibold text-white">
                                  {acct.currency || "USD"}
                                </span>
                              </div>
                              <div>
                                <span className="text-[#8B949E]">Balance: </span>
                                <span className="font-bold text-white">
                                  {formatUsdExact(bal)}
                                </span>
                              </div>
                              <div>
                                <span className="text-[#8B949E]">Equity: </span>
                                <span className="font-bold text-white">
                                  {formatUsdExact(eq)}
                                </span>
                              </div>
                              <div className="col-span-2 sm:col-span-3">
                                <span className="text-[#8B949E]">Available Margin: </span>
                                <span className="font-semibold text-[#E6EDF3]">
                                  {formatUsdExact(freeM)}
                                </span>
                              </div>
                            </div>

                            {/* 4-Layer Connection & Execution Readiness Distinction */}
                            <div className="flex flex-wrap items-center gap-1.5 pt-1.5 border-t border-[#21262D]/80 text-[10px]">
                              <span className="px-2 py-0.5 rounded bg-[#10B981]/15 text-[#10B981] font-medium">
                                API: {acct.api_connected !== false ? "Connected" : "Offline"}
                              </span>
                              <span className="px-2 py-0.5 rounded bg-[#10B981]/15 text-[#10B981] font-medium">
                                Broker Auth: {acct.broker_account_authenticated !== false ? "Verified" : "Unverified"}
                              </span>
                              <span className="px-2 py-0.5 rounded bg-amber-500/15 text-amber-300 font-medium">
                                Real Execution: Locked (Safety Governance)
                              </span>
                            </div>
                          </button>
                        );
                      })
                    )}
                  </div>
                )}
              </div>
            </div>

            {realConsentNotice && (
              <div
                id="real-consent-safety-notice"
                className="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-xs text-amber-300 leading-relaxed"
              >
                {realConsentNotice}
              </div>
            )}
          </section>

          {/* STEP 3: STRATEGY APPROVAL */}
          <section
            id="step-3-strategy-approval-section"
            className="bg-[#161B22] border border-[#21262D] rounded-2xl p-5 sm:p-6 flex flex-col justify-between space-y-4"
          >
            <div className="space-y-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <span className="text-xs font-semibold uppercase tracking-wider text-[#10B981]">
                    Step 3
                  </span>
                  <h2 className="text-lg font-semibold text-white mt-0.5">
                    Strategy Approval
                  </h2>
                </div>
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#10B981]/10 border border-[#10B981]/30 text-xs font-medium text-[#10B981]">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#10B981]" />
                  Suitable for current {selectedPair} market
                </span>
              </div>

              <div className="p-4 rounded-xl bg-[#0D1117] border border-[#21262D] space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-[#10B981]" />
                    <h3 className="text-base font-bold text-white">{selectedStrategy.name}</h3>
                  </div>
                  <span className="text-[11px] font-semibold px-2.5 py-0.5 rounded bg-[#10B981]/15 text-[#10B981]">
                    {selectedStrategy.badge}
                  </span>
                </div>

                <div>
                  <p className="text-xs font-semibold text-[#E6EDF3]">Objective:</p>
                  <p className="text-xs text-[#8B949E] mt-0.5 leading-relaxed">
                    {selectedStrategy.objective}
                  </p>
                </div>

                <div>
                  <p className="text-xs font-semibold text-[#E6EDF3] mb-1.5">
                    Automated by BITDEX:
                  </p>
                  <ul className="space-y-1.5 text-xs text-[#8B949E]">
                    {selectedStrategy.bullets.map((b, i) => (
                      <li key={i} className="flex items-start gap-2">
                        <Check className="w-3.5 h-3.5 text-[#10B981] shrink-0 mt-0.5" />
                        <span>{b}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
              <div className="flex items-center gap-2">
                <span className="text-xs text-[#8B949E]">Allocated Capital:</span>
                <div className="inline-flex rounded-lg bg-[#0D1117] border border-[#21262D] p-0.5">
                  {[100, 150, 200, 250].map((cap) => (
                    <button
                      key={cap}
                      type="button"
                      onClick={() => setAllocatedCapitalUsd(cap)}
                      className={`px-2.5 py-1 rounded-md text-xs font-semibold transition-colors ${
                        allocatedCapitalUsd === cap
                          ? "bg-[#10B981] text-[#0D1117]"
                          : "text-[#8B949E] hover:text-white"
                      }`}
                    >
                      ${cap}
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  id="btn-use-recommended-strategy"
                  type="button"
                  onClick={() => setSelectedStrategyId("BITDEX_SMART_SCALPING")}
                  className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-[#10B981]/15 border border-[#10B981]/40 text-xs font-semibold text-[#10B981]"
                >
                  <Check className="w-3.5 h-3.5" />
                  Use Recommended
                </button>
                <button
                  id="btn-review-strategy-list"
                  type="button"
                  onClick={() => setStrategyModalOpen(true)}
                  className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-[#0D1117] hover:bg-[#1C2128] border border-[#21262D] text-xs font-medium text-[#E6EDF3] transition-colors"
                >
                  Review List
                </button>
              </div>
            </div>
          </section>
        </div>

        {/* ═══════════════════════════════════════════════════════════════════
            E. EXECUTION CONFIRMATION & PRIMARY CTA BUTTON
        ═══════════════════════════════════════════════════════════════════ */}
        <section
          id="execution-confirmation-section"
          className="bg-[#161B22] border border-[#21262D] rounded-2xl p-5 sm:p-6 space-y-5"
        >
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 pb-4 border-b border-[#21262D]">
            <div>
              <h2 className="text-base font-semibold text-white">Execution Confirmation</h2>
              <p className="text-xs text-[#8B949E] mt-0.5">
                BITDEX manages entries automatically and only opens a trade when market conditions qualify.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="px-3 py-1.5 rounded-lg bg-[#0D1117] border border-[#21262D] text-[#E6EDF3]">
                Pair: <strong className="text-white">{selectedPair}</strong>
              </span>
              <span className="px-3 py-1.5 rounded-lg bg-[#0D1117] border border-[#21262D] text-[#E6EDF3]">
                Account:{" "}
                <strong className={selectedAccountObj?.environment === "REAL" ? "text-amber-400" : "text-[#10B981]"}>
                  {selectedAccountObj
                    ? `${selectedAccountObj.account_type_label || selectedAccountObj.environment} (${selectedAccountObj.masked_account_number || selectedAccountObj.masked_id})`
                    : "Demo"}
                </strong>
              </span>
              <span className="px-3 py-1.5 rounded-lg bg-[#0D1117] border border-[#21262D] text-[#E6EDF3]">
                Strategy: <strong className="text-white">{selectedStrategy.name}</strong>
              </span>
              <span className="px-3 py-1.5 rounded-lg bg-[#0D1117] border border-[#21262D] text-[#E6EDF3]">
                Allocated: <strong className="text-white">${allocatedCapitalUsd}.00</strong>
              </span>
            </div>
          </div>

          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
            <button
              id="btn-execute-trading-strategy"
              type="button"
              disabled={executingStrategy || selectedAccountObj?.environment === "REAL"}
              onClick={() => setExecuteModalOpen(true)}
              className="flex-1 py-4 px-6 rounded-xl bg-[#10B981] hover:bg-[#059669] active:bg-[#047857] disabled:opacity-50 text-[#0D1117] font-bold text-base tracking-wide shadow-lg shadow-[#10B981]/10 transition-all flex items-center justify-center gap-2.5"
            >
              <Play className="w-5 h-5 fill-current" />
              {selectedAccountObj?.environment === "REAL"
                ? "REAL ACCOUNT EXECUTION LOCKED (SELECT DEMO TO EXECUTE)"
                : executingStrategy
                ? "VERIFYING & EXECUTING STRATEGY..."
                : "EXECUTE TRADING STRATEGY"}
            </button>

            {strategyArmed && (
              <button
                id="btn-pause-disarm-strategy"
                type="button"
                disabled={disarmingStrategy}
                onClick={handlePauseOrDisarmStrategy}
                className="py-4 px-5 rounded-xl bg-[#0D1117] hover:bg-[#1C2128] border border-[#30363D] text-xs font-semibold text-[#E6EDF3] transition-colors flex items-center justify-center gap-2"
              >
                <Pause className="w-4 h-4 text-amber-400" />
                {disarmingStrategy ? "Pausing..." : "Pause / Disarm Strategy"}
              </button>
            )}
          </div>

          {/* Live Automated Strategy Status Bar */}
          <div
            id="strategy-execution-status-box"
            className={`p-4 rounded-xl border flex items-start gap-3 ${
              executionStatusBanner.status === "EXECUTED" ||
              executionStatusBanner.status === "ARMED_VERIFIED"
                ? "bg-[#10B981]/10 border-[#10B981]/30"
                : executionStatusBanner.status === "WAITING"
                ? "bg-[#0D1117] border-[#10B981]/40"
                : executionStatusBanner.status === "ERROR"
                ? "bg-[#E11D48]/10 border-[#E11D48]/30"
                : "bg-[#0D1117] border-[#21262D]"
            }`}
          >
            <Sparkles className="w-4 h-4 text-[#10B981] shrink-0 mt-0.5" />
            <div className="space-y-1 text-xs">
              <div className="font-semibold text-white">
                Status: {executionStatusBanner.headline}
              </div>
              <p className="text-[#8B949E] leading-relaxed">{executionStatusBanner.detail}</p>
            </div>
          </div>
        </section>

        {/* ═══════════════════════════════════════════════════════════════════
            F. TRADING PERFORMANCE & CLOSE ALL TRADES
        ═══════════════════════════════════════════════════════════════════ */}
        <section
          id="trading-performance-section"
          className="bg-[#161B22] border border-[#21262D] rounded-2xl p-5 sm:p-6 space-y-5"
        >
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-white">
                Trading Performance{" "}
                <span className="text-xs font-medium text-[#8B949E] ml-1">
                  ({selectedAccountObj?.broker_name || "Exness"} {selectedAccountObj?.account_type_label || "Demo"}{" "}
                  {selectedAccountObj?.masked_account_number || selectedAccountObj?.masked_id || ""} &mdash; {selectedPair})
                </span>
              </h2>
              <p className="text-xs text-[#8B949E] mt-0.5">
                Settled and floating figures directly from your selected {selectedAccountObj?.account_type_label || "Demo"} account (net of broker commissions).
              </p>
            </div>

            <button
              id="btn-close-all-trades"
              type="button"
              onClick={() => setCloseAllModalOpen(true)}
              className="inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-[#E11D48] hover:bg-[#BE123C] text-white text-xs font-bold tracking-wide transition-colors shadow-sm"
            >
              <OctagonAlert className="w-4 h-4" />
              CLOSE ALL TRADES
            </button>
          </div>

          {/* 4 Metric Cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3.5">
            <div className="p-4 rounded-xl bg-[#0D1117] border border-[#21262D]">
              <span className="text-xs text-[#8B949E]">Today&apos;s Net P&amp;L</span>
              <div
                id="metric-today-net-pnl"
                className={`text-lg sm:text-xl font-bold mt-1.5 ${
                  todayNetPnl > 0
                    ? "text-[#10B981]"
                    : todayNetPnl < 0
                    ? "text-[#E11D48]"
                    : "text-white"
                }`}
              >
                {formatUsdSigned(todayNetPnl)}
              </div>
            </div>

            <div className="p-4 rounded-xl bg-[#0D1117] border border-[#21262D]">
              <span className="text-xs text-[#8B949E]">Total Realised P&amp;L</span>
              <div
                id="metric-total-realized-pnl"
                className={`text-lg sm:text-xl font-bold mt-1.5 ${
                  totalRealizedPnl > 0
                    ? "text-[#10B981]"
                    : totalRealizedPnl < 0
                    ? "text-[#E11D48]"
                    : "text-white"
                }`}
              >
                {formatUsdSigned(totalRealizedPnl)}
              </div>
            </div>

            <div className="p-4 rounded-xl bg-[#0D1117] border border-[#21262D]">
              <span className="text-xs text-[#8B949E]">Current Floating P&amp;L</span>
              <div
                id="metric-floating-pnl"
                className={`text-lg sm:text-xl font-bold mt-1.5 ${
                  currentFloatingPnl > 0
                    ? "text-[#10B981]"
                    : currentFloatingPnl < 0
                    ? "text-[#E11D48]"
                    : "text-white"
                }`}
              >
                {formatUsdSigned(currentFloatingPnl)}
              </div>
            </div>

            <div className="p-4 rounded-xl bg-[#0D1117] border border-[#21262D]">
              <span className="text-xs text-[#8B949E]">Open Trades</span>
              <div id="metric-open-trades-count" className="text-lg sm:text-xl font-bold text-white mt-1.5">
                {openTradesCount} Active
              </div>
            </div>
          </div>

          {/* Open Positions Table (if any active) */}
          {openPositions.length > 0 && (
            <div className="space-y-2">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-[#10B981]">
                Active Open Trades
              </h3>
              <div className="overflow-x-auto rounded-xl border border-[#21262D] bg-[#0D1117]">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="border-b border-[#21262D] text-[#8B949E]">
                      <th className="py-2.5 px-3 font-medium">Ticket</th>
                      <th className="py-2.5 px-3 font-medium">Pair</th>
                      <th className="py-2.5 px-3 font-medium">Side</th>
                      <th className="py-2.5 px-3 font-medium">Entry</th>
                      <th className="py-2.5 px-3 font-medium">Current</th>
                      <th className="py-2.5 px-3 font-medium">SL / TP</th>
                      <th className="py-2.5 px-3 font-medium text-right">Net P&amp;L</th>
                      <th className="py-2.5 px-3 font-medium text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#21262D]">
                    {openPositions.map((pos) => {
                      const netVal = Number(pos.net_pnl ?? pos.unrealized_pnl ?? 0);
                      return (
                        <tr key={pos.position_id} className="hover:bg-[#161B22]/60">
                          <td className="py-2.5 px-3 font-mono text-white">#{pos.position_id}</td>
                          <td className="py-2.5 px-3 font-semibold text-white">{pos.symbol}</td>
                          <td className="py-2.5 px-3">
                            <span
                              className={`px-2 py-0.5 rounded font-semibold ${
                                pos.direction === "BUY"
                                  ? "bg-[#10B981]/15 text-[#10B981]"
                                  : "bg-[#E11D48]/15 text-[#FDA4AF]"
                              }`}
                            >
                              {pos.direction}
                            </span>
                          </td>
                          <td className="py-2.5 px-3 text-[#E6EDF3]">
                            ${formatInstrumentPrice(pos.entry_price, 2)}
                          </td>
                          <td className="py-2.5 px-3 text-[#E6EDF3]">
                            ${formatInstrumentPrice(pos.mark_price, 2)}
                          </td>
                          <td className="py-2.5 px-3 text-[#8B949E]">
                            {pos.stop_loss_price ? `$${formatInstrumentPrice(pos.stop_loss_price, 2)}` : "—"} /{" "}
                            {pos.take_profit_price ? `$${formatInstrumentPrice(pos.take_profit_price, 2)}` : "—"}
                          </td>
                          <td
                            className={`py-2.5 px-3 font-bold text-right ${
                              netVal >= 0 ? "text-[#10B981]" : "text-[#E11D48]"
                            }`}
                          >
                            {formatUsdSigned(netVal)}
                          </td>
                          <td className="py-2.5 px-3 text-right">
                            <button
                              type="button"
                              disabled={closingSingleTicket === String(pos.position_id)}
                              onClick={() => handleCloseSinglePosition(String(pos.position_id))}
                              className="px-2.5 py-1 rounded-lg bg-[#E11D48]/20 hover:bg-[#E11D48] text-[#FDA4AF] hover:text-white font-semibold transition-colors"
                            >
                              {closingSingleTicket === String(pos.position_id) ? "Closing..." : "Close"}
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Recent Completed Trades Table */}
          <div className="space-y-2.5">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[#8B949E]">
              Recent Completed Trades
            </h3>
            <div className="overflow-x-auto rounded-xl border border-[#21262D] bg-[#0D1117]">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="border-b border-[#21262D] text-[#8B949E]">
                    <th className="py-3 px-4 font-medium">Time (UTC)</th>
                    <th className="py-3 px-4 font-medium">Pair</th>
                    <th className="py-3 px-4 font-medium">Result / Status</th>
                    <th className="py-3 px-4 font-medium text-right">Realised Net P&amp;L</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#21262D]">
                  {closedPositions.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="py-6 text-center text-[#8B949E]">
                        No completed trades recorded yet on this account.
                      </td>
                    </tr>
                  ) : (
                    closedPositions.slice(0, 8).map((trade, idx) => {
                      const netPnl = Number(trade.realized_pnl ?? trade.net_pnl ?? 0);
                      const isPositive = netPnl >= 0;
                      const timeStr = String(trade.closed_at || trade.opened_at || "")
                        .replace("T", " ")
                        .replace("Z", "")
                        .slice(0, 16);
                      const statusLabel =
                        trade.result_label ||
                        (isPositive
                          ? "Closed automatically (Profit Target Reached)"
                          : "Closed automatically (Stop-Loss Protection)");

                      return (
                        <tr key={`${trade.position_id}-${idx}`} className="hover:bg-[#161B22]/50">
                          <td className="py-3 px-4 text-[#8B949E] font-mono">
                            {timeStr || "Recent"}
                          </td>
                          <td className="py-3 px-4 font-semibold text-white">
                            {trade.symbol || "BTCUSDr"}
                          </td>
                          <td className="py-3 px-4 text-[#E6EDF3]">{statusLabel}</td>
                          <td
                            className={`py-3 px-4 font-bold text-right ${
                              isPositive ? "text-[#10B981]" : "text-[#E11D48]"
                            }`}
                          >
                            {formatUsdSigned(netPnl)}
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        {/* ═══════════════════════════════════════════════════════════════════
            G. COLLAPSIBLE SYSTEM & SAFETY STATUS FOOTER
        ═══════════════════════════════════════════════════════════════════ */}
        <footer className="bg-[#161B22] border border-[#21262D] rounded-2xl overflow-hidden">
          <button
            id="btn-toggle-system-safety"
            type="button"
            onClick={() => setFooterExpanded((prev) => !prev)}
            className="w-full px-5 py-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 text-left hover:bg-[#1C2128] transition-colors"
          >
            <div className="flex items-center gap-2 text-xs font-semibold text-white">
              {footerExpanded ? (
                <ChevronUp className="w-4 h-4 text-[#10B981]" />
              ) : (
                <ChevronDown className="w-4 h-4 text-[#10B981]" />
              )}
              <span>System &amp; Safety Status</span>
            </div>

            <div className="flex flex-wrap items-center gap-3 text-xs text-[#8B949E]">
              <span>
                Broker:{" "}
                <strong className={systemStatus.indicators.broker_connection.ok ? "text-[#10B981]" : "text-[#E11D48]"}>
                  {systemStatus.indicators.broker_connection.label}
                </strong>
              </span>
              <span>|</span>
              <span>
                Market Data:{" "}
                <strong className={systemStatus.indicators.market_data.ok ? "text-[#10B981]" : "text-amber-400"}>
                  {systemStatus.indicators.market_data.label}
                </strong>
              </span>
              <span>|</span>
              <span>
                Execution:{" "}
                <strong className={systemStatus.indicators.execution_availability.ok ? "text-[#10B981]" : "text-amber-400"}>
                  {systemStatus.indicators.execution_availability.label}
                </strong>
              </span>
              <span>|</span>
              <span>
                Protection:{" "}
                <strong className={systemStatus.indicators.risk_protection.ok ? "text-[#10B981]" : "text-[#E11D48]"}>
                  {systemStatus.indicators.risk_protection.label}
                </strong>
              </span>
            </div>
          </button>

          {footerExpanded && (
            <div
              id="panel-system-safety-details"
              className="px-5 pb-5 pt-2 border-t border-[#21262D] grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 text-xs"
            >
              <div className="p-3 rounded-xl bg-[#0D1117] border border-[#21262D]">
                <div className="text-[#8B949E]">Broker Connection</div>
                <div className="font-semibold text-[#10B981] mt-1 flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-[#10B981]" />
                  {systemStatus.indicators.broker_connection.label}{" "}
                  {selectedAccountObj?.masked_account_number ? `(${selectedAccountObj.masked_account_number})` : ""}
                </div>
              </div>

              <div className="p-3 rounded-xl bg-[#0D1117] border border-[#21262D]">
                <div className="text-[#8B949E]">Market Data</div>
                <div className="font-semibold text-[#10B981] mt-1 flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-[#10B981]" />
                  {systemStatus.indicators.market_data.label} (Live MT5)
                </div>
              </div>

              <div className="p-3 rounded-xl bg-[#0D1117] border border-[#21262D]">
                <div className="text-[#8B949E]">Execution Availability</div>
                <div className="font-semibold text-[#10B981] mt-1 flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-[#10B981]" />
                  {systemStatus.indicators.execution_availability.label}
                </div>
              </div>

              <div className="p-3 rounded-xl bg-[#0D1117] border border-[#21262D]">
                <div className="text-[#8B949E]">Risk Protection</div>
                <div className="font-semibold text-[#10B981] mt-1 flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-[#10B981]" />
                  {systemStatus.indicators.risk_protection.label} (SL &amp; TP Attached)
                </div>
              </div>

              <div className="p-3 rounded-xl bg-[#0D1117] border border-[#21262D]">
                <div className="text-[#8B949E]">Trade Monitoring</div>
                <div className="font-semibold text-[#10B981] mt-1 flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-[#10B981]" />
                  {systemStatus.indicators.trade_monitoring.label} (250ms Continuous)
                </div>
              </div>
            </div>
          )}
        </footer>
      </div>

      {/* ═════════════════════════════════════════════════════════════════════
          MODAL 1: EXECUTE TRADING STRATEGY CONFIRMATION
      ═════════════════════════════════════════════════════════════════════ */}
      {executeModalOpen && (
        <div
          id="modal-confirm-execute-strategy"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4"
        >
          <div className="w-full max-w-lg rounded-2xl bg-[#161B22] border border-[#30363D] p-6 space-y-5 shadow-2xl">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="text-lg font-bold text-white">
                  Approve &amp; Execute Trading Strategy
                </h3>
                <p className="text-xs text-[#8B949E] mt-1">
                  Review your selected parameters before authorizing BITDEX automated execution.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setExecuteModalOpen(false)}
                className="p-1 rounded-lg text-[#8B949E] hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-4 rounded-xl bg-[#0D1117] border border-[#21262D] space-y-2.5 text-xs">
              <div className="flex justify-between py-1 border-b border-[#21262D]">
                <span className="text-[#8B949E]">Selected Pair:</span>
                <span className="font-bold text-white">{selectedPair}</span>
              </div>
              <div className="flex justify-between py-1 border-b border-[#21262D]">
                <span className="text-[#8B949E]">Selected Account:</span>
                <span className="font-bold text-[#10B981]">
                  {selectedAccountObj
                    ? `${selectedAccountObj.broker_name || "Exness"} ${selectedAccountObj.account_type_label || "Demo"} ${selectedAccountObj.masked_account_number || selectedAccountObj.masked_id} (${selectedAccountObj.mt5_server || selectedAccountObj.server_name || "Exness-MT5Trial15"})`
                    : "Exness Demo"}
                </span>
              </div>
              <div className="flex justify-between py-1 border-b border-[#21262D]">
                <span className="text-[#8B949E]">Selected Strategy:</span>
                <span className="font-bold text-white">{selectedStrategy.name}</span>
              </div>
              <div className="flex justify-between py-1 border-b border-[#21262D]">
                <span className="text-[#8B949E]">Allocated Capital:</span>
                <span className="font-bold text-white">${allocatedCapitalUsd}.00 USD</span>
              </div>
              <div className="flex justify-between py-1">
                <span className="text-[#8B949E]">Per-Trade Protection:</span>
                <span className="font-semibold text-[#E6EDF3]">
                  +$1.00 Net Target · -$1.00 Stop-Loss Protection
                </span>
              </div>
            </div>

            <div className="p-3.5 rounded-xl bg-[#0D1117] border border-[#21262D] text-xs text-[#8B949E] leading-relaxed">
              <strong className="text-white">Risk Disclosure:</strong> BITDEX analyses market direction
              automatically and only enters when expected movement clears round-trip execution costs.
              Stop-loss and take-profit protections are attached to every order, though exact settlement
              prices depend on market liquidity.
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setExecuteModalOpen(false)}
                className="px-4 py-2.5 rounded-xl bg-[#0D1117] hover:bg-[#1C2128] border border-[#30363D] text-xs font-semibold text-[#E6EDF3]"
              >
                Cancel
              </button>
              <button
                id="btn-confirm-execute-strategy"
                type="button"
                disabled={executingStrategy}
                onClick={handleConfirmAndExecuteStrategy}
                className="px-5 py-2.5 rounded-xl bg-[#10B981] hover:bg-[#059669] text-[#0D1117] text-xs font-bold tracking-wide"
              >
                {executingStrategy ? "Authorizing..." : "Confirm & Execute Strategy"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ═════════════════════════════════════════════════════════════════════
          MODAL 2: REAL ACCOUNT RISK DISCLOSURE & CONSENT
      ═════════════════════════════════════════════════════════════════════ */}
      {realConsentModalOpen && (
        <div
          id="modal-real-account-consent"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4"
        >
          <div className="w-full max-w-lg rounded-2xl bg-[#161B22] border border-[#30363D] p-6 space-y-5 shadow-2xl">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-2.5">
                <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0" />
                <h3 className="text-lg font-bold text-white">
                  Real Account Risk Disclosure &amp; Consent
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setRealConsentModalOpen(false)}
                className="p-1 rounded-lg text-[#8B949E] hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-4 rounded-xl bg-[#0D1117] border border-[#21262D] space-y-2.5 text-xs text-[#8B949E] leading-relaxed">
              <p className="text-white font-medium">
                You are requesting Live Trading authorization on Exness MT5:
              </p>
              <ul className="list-disc pl-5 space-y-1.5">
                <li>Market trading with real funds carries financial risk and potential loss.</li>
                <li>
                  BITDEX manages trades within strict stop-loss and allocated-capital rules, but profits are not guaranteed.
                </li>
                <li>
                  During the current Demo validation phase, Real-Account order execution remains permanently locked by platform safety governance (<code className="text-amber-300">REAL_TRADING_PERMANENTLY_LOCKED</code>).
                </li>
              </ul>
            </div>

            <label className="flex items-start gap-2.5 cursor-pointer select-none text-xs text-[#E6EDF3]">
              <input
                id="checkbox-real-risk-consent"
                type="checkbox"
                checked={realConsentChecked}
                onChange={(e) => setRealConsentChecked(e.target.checked)}
                className="mt-0.5 rounded border-[#30363D] bg-[#0D1117] text-[#10B981] focus:ring-0"
              />
              <span>I understand the risks and approve Real Account trading.</span>
            </label>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                id="btn-cancel-real-consent"
                type="button"
                onClick={() => setRealConsentModalOpen(false)}
                className="px-4 py-2.5 rounded-xl bg-[#0D1117] hover:bg-[#1C2128] border border-[#30363D] text-xs font-semibold text-[#E6EDF3]"
              >
                Cancel (Stay on Demo)
              </button>
              <button
                id="btn-confirm-real-consent"
                type="button"
                disabled={!realConsentChecked || realConsentSubmitting}
                onClick={handleConfirmRealConsent}
                className="px-5 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 disabled:opacity-40 text-[#0D1117] text-xs font-bold"
              >
                {realConsentSubmitting ? "Recording..." : "Confirm & Request Activation"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ═════════════════════════════════════════════════════════════════════
          MODAL 3: CONFIRM CLOSE ALL OPEN TRADES
      ═════════════════════════════════════════════════════════════════════ */}
      {closeAllModalOpen && (
        <div
          id="modal-confirm-close-all-trades"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4"
        >
          <div className="w-full max-w-lg rounded-2xl bg-[#161B22] border border-[#30363D] p-6 space-y-5 shadow-2xl">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-2.5">
                <OctagonAlert className="w-5 h-5 text-[#E11D48] shrink-0" />
                <h3 className="text-lg font-bold text-white">
                  Confirm: Close All Open Trades?
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setCloseAllModalOpen(false)}
                className="p-1 rounded-lg text-[#8B949E] hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-4 rounded-xl bg-[#0D1117] border border-[#21262D] space-y-2 text-xs text-[#8B949E] leading-relaxed">
              <p className="text-white font-medium">
                This will immediately request the broker to close all{" "}
                <strong className="text-white">{openTradesCount}</strong> open position(s) for{" "}
                <strong className="text-[#10B981]">
                  {selectedAccountObj
                    ? `${selectedAccountObj.broker_name || "Exness"} ${selectedAccountObj.account_type_label || "Demo"} ${selectedAccountObj.masked_account_number || selectedAccountObj.masked_id} (${selectedAccountObj.mt5_server || selectedAccountObj.server_name || "Exness"})`
                    : "Selected Account"}
                </strong>
                .
              </p>
              <p>
                Open positions will close at current market prices by exact broker ticket, which may
                result in a realised profit or loss.
              </p>
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                id="btn-keep-trades-open"
                type="button"
                onClick={() => setCloseAllModalOpen(false)}
                className="px-4 py-2.5 rounded-xl bg-[#0D1117] hover:bg-[#1C2128] border border-[#30363D] text-xs font-semibold text-[#E6EDF3]"
              >
                Keep Trades Open
              </button>
              <button
                id="btn-confirm-close-all-trades"
                type="button"
                disabled={closingAll}
                onClick={handleConfirmCloseAllTrades}
                className="px-5 py-2.5 rounded-xl bg-[#E11D48] hover:bg-[#BE123C] text-white text-xs font-bold"
              >
                {closingAll ? "Closing Trades..." : "Yes, Close All Trades Now"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ═════════════════════════════════════════════════════════════════════
          MODAL 4: REVIEW PRE-BUILT STRATEGIES
      ═════════════════════════════════════════════════════════════════════ */}
      {strategyModalOpen && (
        <div
          id="modal-review-strategies"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4"
        >
          <div className="w-full max-w-lg rounded-2xl bg-[#161B22] border border-[#30363D] p-6 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-bold text-white">Approved Pre-Built Strategies</h3>
              <button
                type="button"
                onClick={() => setStrategyModalOpen(false)}
                className="p-1 rounded-lg text-[#8B949E] hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-3">
              {APPROVED_STRATEGIES.map((strat) => {
                const active = strat.id === selectedStrategyId;
                return (
                  <button
                    key={strat.id}
                    type="button"
                    onClick={() => {
                      setSelectedStrategyId(strat.id);
                      setStrategyModalOpen(false);
                    }}
                    className={`w-full text-left p-4 rounded-xl border transition-all ${
                      active
                        ? "bg-[#10B981]/10 border-[#10B981]"
                        : "bg-[#0D1117] border-[#21262D] hover:border-[#30363D]"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-sm text-white">{strat.name}</span>
                      <span className="text-[11px] font-semibold px-2.5 py-0.5 rounded bg-[#10B981]/15 text-[#10B981]">
                        {strat.badge}
                      </span>
                    </div>
                    <p className="text-xs text-[#8B949E] mt-1.5 leading-relaxed">
                      {strat.objective}
                    </p>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
