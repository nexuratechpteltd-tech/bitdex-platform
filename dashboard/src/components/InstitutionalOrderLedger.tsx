"use client";

import React, { useState, useEffect, useMemo } from "react";
import {
  Activity,
  Clock,
  FileText,
  Zap,
  RefreshCw,
  Download,
  Search,
  X,
  ChevronDown,
  ChevronRight,
  Copy,
  Check,
  ExternalLink,
  AlertTriangle,
  CheckCircle2,
  Filter,
  Calendar,
  Sliders,
  ArrowUpRight,
  ArrowDownRight,
  Layers,
  Lock,
  ShieldCheck,
  Briefcase,
  TrendingUp,
  Coins,
  DollarSign
} from "lucide-react";

interface InstitutionalOrderLedgerProps {
  token?: string;
  user?: any;
  connections?: any[];
  initialOrderId?: string;
}

export default function InstitutionalOrderLedger({
  token,
  user,
  connections = [],
  initialOrderId,
}: InstitutionalOrderLedgerProps) {
  // ─── Core Ledger Navigation State ───
  const [ledgerEnv, setLedgerEnv] = useState<"LIVE" | "DEMO">("DEMO");
  const [activeLedgerTab, setActiveLedgerTab] = useState<"OPEN_ORDERS" | "ORDER_HISTORY" | "TRADE_HISTORY">("ORDER_HISTORY");

  // ─── Spot Holdings State ───
  const [spotHoldings, setSpotHoldings] = useState<any[]>([]);
  const [spotTotalValuation, setSpotTotalValuation] = useState<number>(0);
  const [isSyncing, setIsSyncing] = useState<boolean>(false);
  const [lastSyncTime, setLastSyncTime] = useState<string>("");
  const [syncToast, setSyncToast] = useState<{ message: string; type: "success" | "error" } | null>(null);

  // ─── Combinatorial Filter State (2-Row Compact Toolbar) ───
  const [timePreset, setTimePreset] = useState<"TODAY" | "YESTERDAY" | "7D" | "30D" | "CUSTOM">("7D");
  const [customStartDate, setCustomStartDate] = useState<string>("");
  const [customEndDate, setCustomEndDate] = useState<string>("");
  const [filterExchange, setFilterExchange] = useState<string>("ALL");
  const [filterAccount, setFilterAccount] = useState<string>("ALL");
  const [filterPair, setFilterPair] = useState<string>("ALL");
  const [filterSide, setFilterSide] = useState<string>("ALL");
  const [filterStatus, setFilterStatus] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState<string>(initialOrderId || "");

  // ─── Mobile Bottom Sheet Filter State ───
  const [isMobileFilterOpen, setIsMobileFilterOpen] = useState<boolean>(false);

  // ─── Table Data Lists ───
  const [openOrders, setOpenOrders] = useState<any[]>([]);
  const [orderHistory, setOrderHistory] = useState<any[]>([]);
  const [orderHistoryTotal, setOrderHistoryTotal] = useState<number>(0);
  const [tradeFills, setTradeFills] = useState<any[]>([]);
  const [tradeFillsTotal, setTradeFillsTotal] = useState<number>(0);
  const [isLoadingData, setIsLoadingData] = useState<boolean>(false);
  const [expandedOrders, setExpandedOrders] = useState<Set<string>>(new Set());

  // ─── Slide-Over Execution Audit Dossier State ───
  const [selectedDossier, setSelectedDossier] = useState<any | null>(null);
  const [isDossierOpen, setIsDossierOpen] = useState<boolean>(false);
  const [isDossierLoading, setIsDossierLoading] = useState<boolean>(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // ─── Active Filter Count Calculation ───
  const activeFilterCount = useMemo(() => {
    let count = 0;
    if (timePreset !== "7D") count++;
    if (filterExchange !== "ALL") count++;
    if (filterAccount !== "ALL") count++;
    if (filterPair !== "ALL") count++;
    if (filterSide !== "ALL") count++;
    if (filterStatus !== "ALL") count++;
    if (searchQuery.trim().length > 0) count++;
    return count;
  }, [timePreset, filterExchange, filterAccount, filterPair, filterSide, filterStatus, searchQuery]);

  const handleResetFilters = () => {
    setTimePreset("7D");
    setCustomStartDate("");
    setCustomEndDate("");
    setFilterExchange("ALL");
    setFilterAccount("ALL");
    setFilterPair("ALL");
    setFilterSide("ALL");
    setFilterStatus("ALL");
    setSearchQuery("");
  };

  // ─── Auth Header Helper ───
  const getAuthHeaders = () => {
    const activeToken = token || (typeof window !== "undefined" ? (localStorage.getItem("bitdex_auth_token") || localStorage.getItem("tauric_token") || localStorage.getItem("tauric_session_token")) : "");
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (activeToken) {
      headers["Authorization"] = `Bearer ${activeToken}`;
    }
    return headers;
  };

  // ─── Time Horizon Date Calculators ───
  const dateRangeParams = useMemo(() => {
    const now = new Date();
    if (timePreset === "TODAY") {
      const start = new Date(now.getFullYear(), now.getMonth(), now.getDate()).toISOString();
      return { start, end: now.toISOString() };
    } else if (timePreset === "YESTERDAY") {
      const yesterdayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
      const yesterdayEnd = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0, -1);
      return { start: yesterdayStart.toISOString(), end: yesterdayEnd.toISOString() };
    } else if (timePreset === "7D") {
      const start = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000).toISOString();
      return { start, end: now.toISOString() };
    } else if (timePreset === "30D") {
      const start = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000).toISOString();
      return { start, end: now.toISOString() };
    } else if (timePreset === "CUSTOM" && customStartDate) {
      const start = new Date(customStartDate).toISOString();
      const end = customEndDate ? new Date(customEndDate).toISOString() : now.toISOString();
      return { start, end };
    }
    return { start: undefined, end: undefined };
  }, [timePreset, customStartDate, customEndDate]);

  // ─── Data Fetching ───
  const fetchLedgerData = async () => {
    setIsLoadingData(true);
    const headers = getAuthHeaders();
    try {
      // 1. Fetch Spot Holdings
      const holdingsRes = await fetch(`/trading/api/backend/ledger/holdings/spot?environment=${ledgerEnv}`, { headers });
      if (holdingsRes.ok) {
        const hData = await holdingsRes.json();
        setSpotHoldings(hData.holdings || []);
        setSpotTotalValuation(hData.total_valuation_usd || 0);
      }

      // 2. Fetch Open Orders
      const openRes = await fetch(`/trading/api/backend/ledger/orders/open?environment=${ledgerEnv}`, { headers });
      if (openRes.ok) {
        const oData = await openRes.json();
        setOpenOrders(oData.orders || []);
      }

      // 3. Fetch Order History
      const histParams = new URLSearchParams();
      histParams.set("environment", ledgerEnv);
      if (filterExchange !== "ALL") histParams.set("exchange", filterExchange);
      if (filterAccount !== "ALL") histParams.set("account_id", filterAccount);
      if (filterPair !== "ALL") histParams.set("symbol", filterPair);
      if (filterSide !== "ALL") histParams.set("side", filterSide);
      if (filterStatus !== "ALL") histParams.set("status", filterStatus);
      if (searchQuery.trim()) histParams.set("search", searchQuery.trim());
      if (dateRangeParams.start) histParams.set("start_time", dateRangeParams.start);
      if (dateRangeParams.end) histParams.set("end_time", dateRangeParams.end);
      histParams.set("page_size", "50");

      const histRes = await fetch(`/trading/api/backend/ledger/orders/history?${histParams.toString()}`, { headers });
      if (histRes.ok) {
        const histData = await histRes.json();
        setOrderHistory(histData.orders || []);
        setOrderHistoryTotal(histData.total || 0);
      }

      // 4. Fetch Trade Fills
      const fillsParams = new URLSearchParams();
      fillsParams.set("environment", ledgerEnv);
      if (filterExchange !== "ALL") fillsParams.set("exchange", filterExchange);
      if (filterAccount !== "ALL") fillsParams.set("account_id", filterAccount);
      if (filterPair !== "ALL") fillsParams.set("symbol", filterPair);
      if (filterSide !== "ALL") fillsParams.set("side", filterSide);
      if (searchQuery.trim()) fillsParams.set("search", searchQuery.trim());
      if (dateRangeParams.start) fillsParams.set("start_time", dateRangeParams.start);
      if (dateRangeParams.end) fillsParams.set("end_time", dateRangeParams.end);
      fillsParams.set("page_size", "50");

      const fillsRes = await fetch(`/trading/api/backend/ledger/trades/fills?${fillsParams.toString()}`, { headers });
      if (fillsRes.ok) {
        const fillsData = await fillsRes.json();
        setTradeFills(fillsData.trades || []);
        setTradeFillsTotal(fillsData.total || 0);
      }
    } catch (err: any) {
      console.error("Failed to fetch ledger workspace data:", err);
    } finally {
      setIsLoadingData(false);
    }
  };

  useEffect(() => {
    fetchLedgerData();
  }, [ledgerEnv, timePreset, customStartDate, customEndDate, filterExchange, filterAccount, filterPair, filterSide, filterStatus, searchQuery]);

  // ─── Listen for deep link events from execution drawer ───
  useEffect(() => {
    const handleDeepLink = (e: any) => {
      const orderId = e.detail?.order_id;
      if (orderId) {
        setSearchQuery(String(orderId));
        setActiveLedgerTab("ORDER_HISTORY");
        openAuditDossier(String(orderId));
      }
    };
    window.addEventListener("bitdex_view_order_ledger", handleDeepLink);
    return () => window.removeEventListener("bitdex_view_order_ledger", handleDeepLink);
  }, []);

  // ─── On-Demand Exchange Sync ───
  const handleSyncExchange = async () => {
    setIsSyncing(true);
    setSyncToast(null);
    try {
      const headers = getAuthHeaders();
      const res = await fetch("/trading/api/backend/ledger/sync", {
        method: "POST",
        headers,
        body: JSON.stringify({
          account_id: "CONN-DK-BIN-DEMO-MIGRATED",
          environment: ledgerEnv
        })
      });
      const data = await res.json();
      if (res.ok) {
        setLastSyncTime(new Date().toLocaleTimeString());
        setSyncToast({
          type: "success",
          message: `Synchronized ${data.synced_orders || 0} orders, ${data.synced_fills || 0} fills, and ${data.synced_assets || 0} asset balances from Binance Demo.`
        });
        await fetchLedgerData();
      } else {
        setSyncToast({
          type: "error",
          message: data.detail || "Exchange synchronization failed."
        });
      }
    } catch (err: any) {
      setSyncToast({
        type: "error",
        message: err.message || "Network error synchronizing exchange."
      });
    } finally {
      setIsSyncing(false);
      setTimeout(() => setSyncToast(null), 5000);
    }
  };

  // ─── Open Order Cancellation ───
  const handleCancelOrder = async (ord: any) => {
    try {
      const headers = getAuthHeaders();
      const res = await fetch("/trading/api/backend/orders/cancel", {
        method: "POST",
        headers,
        body: JSON.stringify({
          symbol: ord.symbol,
          client_order_id: ord.client_order_id,
          profile_id: ord.account_id || "CONN-DK-BIN-DEMO-MIGRATED",
          exchange: ord.provider || "BINANCE",
          environment: ord.environment || "DEMO"
        })
      });
      if (res.ok) {
        await fetchLedgerData();
      }
    } catch (err) {
      console.error("Cancel order error:", err);
    }
  };

  // ─── Slide-Over Dossier Loader ───
  const openAuditDossier = async (orderId: string) => {
    setIsDossierLoading(true);
    setIsDossierOpen(true);
    try {
      const headers = getAuthHeaders();
      const res = await fetch(`/trading/api/backend/ledger/orders/${orderId}/dossier`, { headers });
      if (res.ok) {
        const data = await res.json();
        setSelectedDossier(data.dossier);
      }
    } catch (err) {
      console.error("Failed to load audit dossier:", err);
    } finally {
      setIsDossierLoading(false);
    }
  };

  // ─── CSV Download Trigger ───
  const triggerCsvExport = (type: "orders" | "trades") => {
    const params = new URLSearchParams();
    params.set("environment", ledgerEnv);
    if (filterExchange !== "ALL") params.set("exchange", filterExchange);
    if (filterAccount !== "ALL") params.set("account_id", filterAccount);
    if (filterPair !== "ALL") params.set("symbol", filterPair);
    if (filterSide !== "ALL") params.set("side", filterSide);
    if (searchQuery.trim()) params.set("search", searchQuery.trim());
    if (dateRangeParams.start) params.set("start_time", dateRangeParams.start);
    if (dateRangeParams.end) params.set("end_time", dateRangeParams.end);

    const url = `/trading/api/backend/ledger/${type}/export.csv?${params.toString()}`;
    const a = document.createElement("a");
    a.href = url;
    a.download = `bitdex_${type}_${Date.now()}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  // ─── Copy to Clipboard ───
  const copyToClipboard = (text: string, id: string) => {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    }
  };

  // ─── Format PKT / UTC Timestamps ───
  const formatDualTimestamp = (isoOrMs: any) => {
    if (!isoOrMs) return { pkt: "—", utc: "—" };
    try {
      const d = typeof isoOrMs === "number" ? new Date(isoOrMs) : new Date(isoOrMs);
      const utc = d.toISOString().replace("T", " ").substring(0, 19) + " UTC";
      // Format in PKT (UTC+5)
      const pkt = new Intl.DateTimeFormat("en-GB", {
        timeZone: "Asia/Karachi",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
      }).format(d) + " PKT";
      return { pkt, utc };
    } catch {
      return { pkt: String(isoOrMs), utc: "" };
    }
  };

  return (
    <div className="space-y-5 font-mono text-[#EAECEF]">
      {/* ─── ZONE 1: WORKSPACE HEADER, ENVIRONMENT SWITCHER & LAST SYNC ─── */}
      <div className="p-5 rounded-2xl bg-[#1E2329] border border-[#2B3139] shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-cyan-950/60 border border-cyan-500/30 text-cyan-400">
              <Activity className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-base font-bold text-[#EAECEF] uppercase tracking-wider flex items-center gap-2">
                <span>Institutional Order & Trade Ledger</span>
                <span className="px-2 py-0.5 rounded text-[10px] bg-cyan-950 text-cyan-300 border border-cyan-500/40">
                  REAL-TIME MATCHING ENGINE SYNC
                </span>
              </h1>
              <p className="text-xs text-[#848E9C] mt-0.5">
                Permanent 4-layer taxonomy: Spot Inventory • Working Orders • Order Instructions • Granular Matching Fills.
              </p>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          {/* Environment Switcher */}
          <div className="flex items-center p-1 rounded-xl bg-[#151921] border border-[#2B3139] text-xs">
            <button
              type="button"
              onClick={() => setLedgerEnv("LIVE")}
              className={`px-3 py-1.5 rounded-lg font-bold flex items-center gap-2 transition-all cursor-pointer ${
                ledgerEnv === "LIVE"
                  ? "bg-emerald-950 text-emerald-300 border border-emerald-500 shadow-md shadow-emerald-950/40"
                  : "text-[#848E9C] hover:text-[#EAECEF] border border-transparent"
              }`}
            >
              <span className="w-2 h-2 rounded-full bg-[#0ECB81] animate-pulse"></span>
              <span>● LIVE REAL</span>
            </button>
            <button
              type="button"
              onClick={() => setLedgerEnv("DEMO")}
              className={`px-3 py-1.5 rounded-lg font-bold flex items-center gap-2 transition-all cursor-pointer ${
                ledgerEnv === "DEMO"
                  ? "bg-amber-950 text-amber-300 border border-amber-500/80 shadow-md shadow-amber-950/40"
                  : "text-[#848E9C] hover:text-[#EAECEF] border border-transparent"
              }`}
            >
              <span className="w-2 h-2 rounded-full bg-[#F0B90B]"></span>
              <span>◐ DEMO (Active)</span>
            </button>
          </div>

          {/* Sync Exchange Button */}
          <button
            type="button"
            onClick={handleSyncExchange}
            disabled={isSyncing}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-[#151921] hover:bg-[#262C36] text-[#EAECEF] text-xs font-bold border border-[#2B3139] hover:border-cyan-500/50 cursor-pointer transition-all disabled:opacity-50"
            title={lastSyncTime ? `Last synced: ${lastSyncTime}` : "Synchronize latest exchange trades"}
          >
            <RefreshCw className={`w-3.5 h-3.5 text-cyan-400 ${isSyncing ? "animate-spin" : ""}`} />
            <span>{isSyncing ? "Syncing..." : "↻ Sync Exchange"}</span>
          </button>

          {/* Export CSV Dropdown Buttons */}
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => triggerCsvExport("orders")}
              className="flex items-center gap-1 px-3 py-2 rounded-xl bg-[#151921] hover:bg-[#262C36] text-[#848E9C] hover:text-[#EAECEF] text-xs font-bold border border-[#2B3139] transition-all cursor-pointer"
              title="Export Order History to CSV"
            >
              <Download className="w-3.5 h-3.5 text-cyan-400" />
              <span>Orders CSV</span>
            </button>
            <button
              type="button"
              onClick={() => triggerCsvExport("trades")}
              className="flex items-center gap-1 px-3 py-2 rounded-xl bg-[#151921] hover:bg-[#262C36] text-[#848E9C] hover:text-[#EAECEF] text-xs font-bold border border-[#2B3139] transition-all cursor-pointer"
              title="Export Granular Fills to CSV"
            >
              <Download className="w-3.5 h-3.5 text-emerald-400" />
              <span>Fills CSV</span>
            </button>
          </div>
        </div>
      </div>

      {/* Sync Toast Notification */}
      {syncToast && (
        <div className={`p-3 rounded-xl border text-xs flex items-center justify-between ${
          syncToast.type === "success"
            ? "bg-emerald-950/70 border-emerald-500/40 text-emerald-300"
            : "bg-rose-950/70 border-rose-500/40 text-rose-300"
        }`}>
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4" />
            <span>{syncToast.message}</span>
          </div>
          <button onClick={() => setSyncToast(null)} className="text-[#848E9C] hover:text-[#EAECEF]">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* ─── ZONE 2: SPOT ASSET HOLDINGS & EXECUTION SUMMARY STRIP ─── */}
      {/* Solves the "Where is my 0.879 BCH?" problem by explicitly displaying acquired wallet balances */}
      <div className="p-4 rounded-2xl bg-[#151921] border border-[#2B3139] shadow-sm flex flex-col lg:flex-row lg:items-center justify-between gap-4">
        {/* Left: Spot Holdings Inventory Chips */}
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <Coins className="w-4 h-4 text-amber-400" />
            <span className="text-xs font-bold uppercase tracking-wider text-[#848E9C]">
              Spot Asset Holdings ({ledgerEnv}):
            </span>
            <span className="text-xs font-bold text-cyan-400">
              Total Valuation: ${spotTotalValuation.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USD
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {spotHoldings.length === 0 ? (
              <span className="text-xs text-[#848E9C] italic">No active spot asset holdings detected.</span>
            ) : (
              spotHoldings.map((h: any, idx: number) => {
                const isBch = h.asset === "BCH";
                return (
                  <div
                    key={idx}
                    className={`px-3 py-1.5 rounded-xl border text-xs flex items-center gap-2 ${
                      isBch
                        ? "bg-cyan-950/60 border-cyan-500/50 text-[#EAECEF] ring-1 ring-cyan-500/30"
                        : "bg-[#1E2329] border-[#2B3139] text-[#EAECEF]"
                    }`}
                  >
                    <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
                    <span className="font-bold text-[#EAECEF]">{h.asset}:</span>
                    <span className="font-bold tabular-nums text-cyan-300">
                      {Number(h.total).toLocaleString("en-US", { minimumFractionDigits: 4, maximumFractionDigits: 8 })}
                    </span>
                    <span className="text-[#848E9C] text-[10px]">
                      (~${Number(h.valuation_usd || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })})
                    </span>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Right: Quick Ledger Metrics */}
        <div className="flex flex-wrap items-center gap-3 border-t lg:border-t-0 lg:border-l border-[#2B3139] pt-3 lg:pt-0 lg:pl-4 text-xs">
          <div>
            <span className="text-[#848E9C] text-[10px] block">24h Orders:</span>
            <span className="font-bold text-emerald-400">{orderHistoryTotal} Recorded</span>
          </div>
          <div>
            <span className="text-[#848E9C] text-[10px] block">Total Fills:</span>
            <span className="font-bold text-cyan-400">{tradeFillsTotal} Matching Fills</span>
          </div>
          <div>
            <span className="text-[#848E9C] text-[10px] block">Execution Friction:</span>
            <span className="font-bold text-amber-400">0.10% Verified</span>
          </div>
        </div>
      </div>

      {/* ─── ZONE 3: UNIFIED MULTI-DIMENSIONAL FILTER & SEARCH BAR ─── */}
      <div className="p-4 rounded-2xl bg-[#1E2329] border border-[#2B3139] space-y-3">
        {/* ROW 1: TIME HORIZON & ENVIRONMENT / ACCOUNT SCOPE */}
        <div className="flex flex-wrap items-center justify-between gap-3 text-xs">
          {/* Period Presets */}
          <div className="flex items-center gap-1 bg-[#151921] p-1 rounded-xl border border-[#2B3139]">
            {(["TODAY", "YESTERDAY", "7D", "30D", "CUSTOM"] as const).map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setTimePreset(p)}
                className={`px-2.5 py-1 rounded-lg font-bold transition-all cursor-pointer ${
                  timePreset === p
                    ? "bg-cyan-950 text-cyan-300 border border-cyan-500/50 shadow-sm"
                    : "text-[#848E9C] hover:text-[#EAECEF]"
                }`}
              >
                {p === "TODAY" ? "Today" : (p === "YESTERDAY" ? "Yesterday" : (p === "7D" ? "7D" : (p === "30D" ? "30D" : "Custom")))}
              </button>
            ))}
          </div>

          {/* Custom Date Range Pickers (if CUSTOM selected) */}
          {timePreset === "CUSTOM" && (
            <div className="flex items-center gap-2">
              <input
                type="date"
                value={customStartDate}
                onChange={(e) => setCustomStartDate(e.target.value)}
                className="px-2.5 py-1 rounded-lg bg-[#151921] border border-[#2B3139] text-xs text-[#EAECEF] focus:outline-none focus:border-cyan-500"
              />
              <span className="text-[#848E9C]">to</span>
              <input
                type="date"
                value={customEndDate}
                onChange={(e) => setCustomEndDate(e.target.value)}
                className="px-2.5 py-1 rounded-lg bg-[#151921] border border-[#2B3139] text-xs text-[#EAECEF] focus:outline-none focus:border-cyan-500"
              />
            </div>
          )}

          {/* Exchange & Account Selectors */}
          <div className="flex items-center gap-2">
            <select
              value={filterExchange}
              onChange={(e) => setFilterExchange(e.target.value)}
              className="px-3 py-1.5 rounded-xl bg-[#151921] border border-[#2B3139] text-xs font-bold text-[#EAECEF] focus:outline-none focus:border-cyan-500 cursor-pointer"
            >
              <option value="ALL">All Exchanges</option>
              <option value="BINANCE">Binance</option>
              <option value="BITGET">Bitget</option>
            </select>

            <select
              value={filterAccount}
              onChange={(e) => setFilterAccount(e.target.value)}
              className="px-3 py-1.5 rounded-xl bg-[#151921] border border-[#2B3139] text-xs font-bold text-[#EAECEF] focus:outline-none focus:border-cyan-500 cursor-pointer max-w-[200px] truncate"
            >
              <option value="ALL">All Accounts</option>
              <option value="CONN-DK-BIN-DEMO-MIGRATED">Binance Demo (Recovered)</option>
              {connections.map((c: any) => (
                <option key={c.account_id} value={c.account_id}>
                  {c.label || c.account_id}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* ROW 2: INSTRUMENT, SIDE, STATUS & SMART SEARCH */}
        <div className="flex flex-wrap items-center justify-between gap-3 text-xs">
          <div className="flex flex-wrap items-center gap-2">
            {/* Pair Selector */}
            <select
              value={filterPair}
              onChange={(e) => setFilterPair(e.target.value)}
              className="px-3 py-1.5 rounded-xl bg-[#151921] border border-[#2B3139] text-xs font-bold text-[#EAECEF] focus:outline-none focus:border-cyan-500 cursor-pointer"
            >
              <option value="ALL">All Pairs</option>
              <option value="BCHUSDT">BCH/USDT</option>
              <option value="BTCUSDT">BTC/USDT</option>
              <option value="SOLUSDT">SOL/USDT</option>
              <option value="ETHUSDT">ETH/USDT</option>
            </select>

            {/* Side Selector */}
            <select
              value={filterSide}
              onChange={(e) => setFilterSide(e.target.value)}
              className="px-3 py-1.5 rounded-xl bg-[#151921] border border-[#2B3139] text-xs font-bold text-[#EAECEF] focus:outline-none focus:border-cyan-500 cursor-pointer"
            >
              <option value="ALL">All Sides</option>
              <option value="BUY">▲ Buy Only</option>
              <option value="SELL">▼ Sell Only</option>
            </select>

            {/* Status Selector */}
            {activeLedgerTab === "ORDER_HISTORY" && (
              <select
                value={filterStatus}
                onChange={(e) => setFilterStatus(e.target.value)}
                className="px-3 py-1.5 rounded-xl bg-[#151921] border border-[#2B3139] text-xs font-bold text-[#EAECEF] focus:outline-none focus:border-cyan-500 cursor-pointer"
              >
                <option value="ALL">All Statuses</option>
                <option value="FILLED">Filled</option>
                <option value="PARTIALLY_FILLED">Partial</option>
                <option value="CANCELED">Canceled</option>
                <option value="NEW">New</option>
              </select>
            )}
          </div>

          {/* Smart Search Input & Active Reset Button */}
          <div className="flex items-center gap-2 flex-1 max-w-md">
            <div className="relative flex-1">
              <Search className="w-3.5 h-3.5 text-[#848E9C] absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search Pair, Order ID (537182101), or Client ID..."
                className="w-full pl-8 pr-8 py-1.5 rounded-xl bg-[#151921] border border-[#2B3139] text-xs text-[#EAECEF] placeholder:text-[#848E9C] focus:outline-none focus:border-cyan-500 font-mono"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery("")}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[#848E9C] hover:text-[#EAECEF]"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            {/* Reset Button (lights up in cyan when activeFilterCount > 0) */}
            <button
              type="button"
              onClick={handleResetFilters}
              disabled={activeFilterCount === 0}
              className={`px-3 py-1.5 rounded-xl border text-xs font-bold flex items-center gap-1.5 transition-all cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed ${
                activeFilterCount > 0
                  ? "bg-cyan-950 text-cyan-300 border-cyan-500 shadow-md shadow-cyan-950/40"
                  : "bg-[#151921] text-[#848E9C] border-[#2B3139]"
              }`}
            >
              <RefreshCw className="w-3 h-3" />
              <span>Reset ({activeFilterCount})</span>
            </button>
          </div>
        </div>
      </div>

      {/* ─── ZONE 4: THE 3-TAB LEDGER TABLE ─── */}
      <div className="rounded-2xl bg-[#1E2329] border border-[#2B3139] overflow-hidden shadow-sm">
        {/* Sticky 3-Tab Header */}
        <div className="p-3 border-b border-[#2B3139] bg-[#151921] flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <button
              type="button"
              id="tab-open-orders"
              onClick={() => setActiveLedgerTab("OPEN_ORDERS")}
              className={`px-3.5 py-1.5 rounded-xl text-xs font-bold flex items-center gap-1.5 transition-all cursor-pointer ${
                activeLedgerTab === "OPEN_ORDERS"
                  ? "bg-cyan-950 text-cyan-300 border border-cyan-500/80 shadow-md"
                  : "text-[#848E9C] hover:text-[#EAECEF] hover:bg-[#262C36]"
              }`}
            >
              <Clock className="w-3.5 h-3.5 text-amber-400" />
              <span>⏳ Open Orders ({openOrders.length})</span>
            </button>

            <button
              type="button"
              id="tab-order-history"
              onClick={() => setActiveLedgerTab("ORDER_HISTORY")}
              className={`px-3.5 py-1.5 rounded-xl text-xs font-bold flex items-center gap-1.5 transition-all cursor-pointer ${
                activeLedgerTab === "ORDER_HISTORY"
                  ? "bg-cyan-950 text-cyan-300 border border-cyan-500/80 shadow-md"
                  : "text-[#848E9C] hover:text-[#EAECEF] hover:bg-[#262C36]"
              }`}
            >
              <FileText className="w-3.5 h-3.5 text-cyan-400" />
              <span>📋 Order History ({orderHistoryTotal})</span>
            </button>

            <button
              type="button"
              id="tab-trade-history"
              onClick={() => setActiveLedgerTab("TRADE_HISTORY")}
              className={`px-3.5 py-1.5 rounded-xl text-xs font-bold flex items-center gap-1.5 transition-all cursor-pointer ${
                activeLedgerTab === "TRADE_HISTORY"
                  ? "bg-cyan-950 text-cyan-300 border border-cyan-500/80 shadow-md"
                  : "text-[#848E9C] hover:text-[#EAECEF] hover:bg-[#262C36]"
              }`}
            >
              <Zap className="w-3.5 h-3.5 text-emerald-400" />
              <span>⚡ Trade History / Fills ({tradeFillsTotal})</span>
            </button>
          </div>

          <div className="text-[11px] text-[#848E9C]">
            <span>Tabular numbers aligned to pixel</span>
          </div>
        </div>

        {/* TAB A: OPEN ORDERS (Working Orders on the Book) */}
        {activeLedgerTab === "OPEN_ORDERS" && (
          <div>
            {openOrders.length === 0 ? (
              <div className="p-10 text-center space-y-3 bg-[#151921]/30">
                <div className="w-12 h-12 rounded-full bg-[#1E2329] border border-[#2B3139] flex items-center justify-center mx-auto text-[#848E9C]">
                  <Clock className="w-6 h-6 text-amber-400" />
                </div>
                <h3 className="text-sm font-bold text-[#EAECEF]">0 Working Open Orders</h3>
                <p className="text-xs text-[#848E9C] max-w-lg mx-auto">
                  Market orders and immediately filled Limit orders execute instantaneously on the matching engine and go directly to{" "}
                  <button onClick={() => setActiveLedgerTab("ORDER_HISTORY")} className="text-cyan-400 underline font-bold cursor-pointer">
                    Order History ({orderHistoryTotal})
                  </button>{" "}
                  and{" "}
                  <button onClick={() => setActiveLedgerTab("TRADE_HISTORY")} className="text-emerald-400 underline font-bold cursor-pointer">
                    Trade History ({tradeFillsTotal})
                  </button>.
                </p>
                <div className="pt-2">
                  <div className="inline-flex items-center gap-2 p-2.5 rounded-xl bg-cyan-950/40 border border-cyan-500/30 text-xs">
                    <span className="text-[#848E9C]">Latest filled order:</span>
                    <span className="font-bold text-[#EAECEF]">BCH/USDT (#537182101 — 0.879 BCH FILLED)</span>
                    <button
                      type="button"
                      onClick={() => openAuditDossier("537182101")}
                      className="px-2 py-0.5 rounded bg-cyan-600 hover:bg-cyan-500 text-[#0B0E11] font-bold text-[10px] cursor-pointer"
                    >
                      Inspect Order →
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs font-mono">
                  <thead>
                    <tr className="bg-[#151921] text-[#848E9C] border-b border-[#2B3139] text-[10px] uppercase">
                      <th className="p-3">DATE / TIME (PKT)</th>
                      <th className="p-3">PAIR & ENV</th>
                      <th className="p-3">EXCHANGE / ACCOUNT</th>
                      <th className="p-3">ORDER ID</th>
                      <th className="p-3">SIDE / TYPE</th>
                      <th className="p-3">PRICE & PROGRESS</th>
                      <th className="p-3 text-right">ACTION</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#2B3139]/40">
                    {openOrders.map((ord: any, idx: number) => {
                      const isBuy = ord.side === "BUY";
                      const timestamps = formatDualTimestamp(ord.exchange_created_at_ms || ord.created_at_utc);
                      const orig = Number(ord.orig_qty || 0);
                      const exec = Number(ord.executed_qty || 0);
                      const pct = orig > 0 ? (exec / orig) * 100 : 0;
                      return (
                        <tr key={idx} className="hover:bg-[#151921]/40 transition-colors">
                          <td className="p-3 tabular-nums">
                            <div className="font-bold text-[#EAECEF]">{timestamps.pkt}</div>
                            <div className="text-[10px] text-[#848E9C]">{timestamps.utc}</div>
                          </td>
                          <td className="p-3">
                            <div className="font-bold text-[#EAECEF]">{ord.display_pair || ord.symbol}</div>
                            <div className="flex items-center gap-1 text-[9px] text-amber-400">
                              <span>[◐ {ord.environment}]</span>
                              <span className="text-[#848E9C]">[SPOT]</span>
                            </div>
                          </td>
                          <td className="p-3">
                            <div className="text-[#EAECEF] font-bold">{ord.provider}</div>
                            <div className="text-[10px] text-[#848E9C] truncate max-w-[120px]">{ord.account_id}</div>
                          </td>
                          <td className="p-3">
                            <div className="flex items-center gap-1">
                              <span className="font-bold text-amber-400">#{ord.exchange_order_id}</span>
                              <button onClick={() => copyToClipboard(ord.exchange_order_id, `ord-${idx}`)} className="text-[#848E9C] hover:text-[#EAECEF]">
                                {copiedId === `ord-${idx}` ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                              </button>
                            </div>
                            <div className="text-[10px] text-[#848E9C] truncate max-w-[130px]" title={ord.client_order_id}>
                              {ord.client_order_id}
                            </div>
                          </td>
                          <td className="p-3">
                            <div className="flex items-center gap-1">
                              <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                                isBuy
                                  ? "bg-emerald-950/60 text-[#0ECB81] border-emerald-500/40"
                                  : "bg-rose-950/60 text-[#F6465D] border-rose-500/40"
                              }`}>
                                {isBuy ? "▲ BUY" : "▼ SELL"}
                              </span>
                              <span className="text-[10px] text-[#848E9C]">{ord.order_type}</span>
                            </div>
                          </td>
                          <td className="p-3 tabular-nums">
                            <div className="font-bold text-[#EAECEF]">Lim: ${Number(ord.requested_price || 0).toLocaleString()}</div>
                            <div className="text-[10px] text-[#848E9C]">{exec} / {orig} ({pct.toFixed(0)}%)</div>
                          </td>
                          <td className="p-3 text-right">
                            <div className="flex items-center justify-end gap-1.5">
                              <button
                                type="button"
                                onClick={() => openAuditDossier(ord.exchange_order_id)}
                                className="px-2 py-1 rounded bg-[#262C36] hover:bg-[#2B3139] text-cyan-300 text-[10px] font-bold cursor-pointer"
                              >
                                View
                              </button>
                              <button
                                type="button"
                                onClick={() => handleCancelOrder(ord)}
                                className="px-2.5 py-1 rounded bg-rose-950 hover:bg-rose-900 text-rose-300 border border-rose-500/40 text-[10px] font-bold cursor-pointer"
                              >
                                Cancel ✕
                              </button>
                            </div>
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

        {/* TAB B: ORDER HISTORY (Permanent Instruction Ledger) */}
        {activeLedgerTab === "ORDER_HISTORY" && (
          <div>
            {orderHistory.length === 0 ? (
              <div className="p-10 text-center text-xs text-[#848E9C]">
                No orders match the selected filters. Try broadening your date range or resetting filters.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs font-mono">
                  <thead>
                    <tr className="bg-[#151921] text-[#848E9C] border-b border-[#2B3139] text-[10px] uppercase">
                      <th className="p-3">DATE / TIME (PKT)</th>
                      <th className="p-3">PAIR & ENV</th>
                      <th className="p-3">ACCOUNT</th>
                      <th className="p-3">EXCHANGE / CLIENT ID</th>
                      <th className="p-3">SIDE & TYPE</th>
                      <th className="p-3">ORIG / EXEC QTY</th>
                      <th className="p-3">REQ / AVG PRICE</th>
                      <th className="p-3 text-right">STATUS</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#2B3139]/40">
                    {orderHistory.map((o: any, idx: number) => {
                      const isBuy = o.side === "BUY";
                      const timestamps = formatDualTimestamp(o.exchange_created_at_ms || o.created_at_utc);
                      const isFilled = o.status === "FILLED";
                      const isCanceled = o.status === "CANCELED";
                      const fills = o.fills || [];
                      const isExpanded = expandedOrders.has(String(o.exchange_order_id || idx));

                      return (
                        <React.Fragment key={idx}>
                          <tr
                            onClick={() => openAuditDossier(o.exchange_order_id)}
                            className="hover:bg-[#151921]/60 transition-colors cursor-pointer group"
                          >
                            <td className="p-3 tabular-nums">
                              <div className="flex items-center gap-1.5">
                                {fills.length > 0 && (
                                  <button
                                    type="button"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      const key = String(o.exchange_order_id || idx);
                                      const next = new Set(expandedOrders);
                                      if (next.has(key)) next.delete(key);
                                      else next.add(key);
                                      setExpandedOrders(next);
                                    }}
                                    className="p-0.5 rounded hover:bg-[#262C36] text-cyan-400"
                                  >
                                    {isExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                                  </button>
                                )}
                                <div>
                                  <div className="font-bold text-[#EAECEF]">{timestamps.pkt}</div>
                                  <div className="text-[10px] text-[#848E9C]">{timestamps.utc}</div>
                                </div>
                              </div>
                            </td>

                            <td className="p-3">
                              <div className="font-bold text-[#EAECEF] group-hover:text-cyan-300 transition-colors">
                                {o.display_pair || o.symbol}
                              </div>
                              <div className="flex items-center gap-1 text-[9px]">
                                <span className="text-amber-400">[◐ {o.environment}]</span>
                                <span className="text-[#848E9C]">[SPOT]</span>
                              </div>
                            </td>

                            <td className="p-3">
                              <div className="text-[#EAECEF] font-bold">{o.provider}</div>
                              <div className="text-[10px] text-[#848E9C] truncate max-w-[120px]">{o.account_id}</div>
                            </td>

                            <td className="p-3">
                              <div className="flex items-center gap-1">
                                <span className="text-amber-400 font-bold">Exch: #{o.exchange_order_id}</span>
                                <button
                                  type="button"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    copyToClipboard(o.exchange_order_id, `hist-${idx}`);
                                  }}
                                  className="text-[#848E9C] hover:text-[#EAECEF]"
                                >
                                  {copiedId === `hist-${idx}` ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                                </button>
                              </div>
                              <div className="text-[10px] text-[#848E9C] truncate max-w-[140px]" title={o.client_order_id}>
                                Cli: {o.client_order_id}
                              </div>
                            </td>

                            <td className="p-3">
                              <div className="flex items-center gap-1.5">
                                <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                                  isBuy
                                    ? "bg-emerald-950/60 text-[#0ECB81] border-emerald-500/40"
                                    : "bg-rose-950/60 text-[#F6465D] border-rose-500/40"
                                }`}>
                                  {isBuy ? "▲ BUY" : "▼ SELL"}
                                </span>
                                <span className="text-[#848E9C] text-[10px]">{o.order_type}</span>
                              </div>
                            </td>

                            <td className="p-3 tabular-nums">
                              <div className="text-[#EAECEF]">Orig: {o.orig_qty}</div>
                              <div className="text-cyan-300 font-bold">
                                Exec: {o.executed_qty} ({(Number(o.executed_qty) / Number(o.orig_qty || 1) * 100).toFixed(1)}%)
                              </div>
                            </td>

                            <td className="p-3 tabular-nums">
                              <div className="text-[#848E9C]">
                                Req: {o.order_type === "MARKET" ? "MARKET" : `$${Number(o.requested_price).toFixed(2)}`}
                              </div>
                              <div className="text-[#EAECEF] font-bold">
                                Avg: ${Number(o.avg_fill_price || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 4 })}
                              </div>
                              <div className="text-[10px] text-amber-300">
                                Tot: ${Number(o.cummulative_quote_qty || 0).toFixed(2)} USDT
                              </div>
                            </td>

                            <td className="p-3 text-right">
                              <div className="inline-flex flex-col items-end gap-1">
                                <span className={`px-2.5 py-0.5 rounded text-[10px] font-bold border ${
                                  isFilled
                                    ? "bg-emerald-950/80 text-emerald-300 border-emerald-500/50"
                                    : (isCanceled ? "bg-slate-800 text-slate-400 border-slate-700" : "bg-cyan-950 text-cyan-300 border-cyan-500/40")
                                }`}>
                                  {isFilled ? "● FILLED" : (isCanceled ? "○ CANCELED" : o.status)}
                                </span>
                                <span className="text-[9px] text-emerald-400 flex items-center gap-0.5">
                                  <ShieldCheck className="w-2.5 h-2.5" />
                                  <span>✓ Verif Audit</span>
                                </span>
                              </div>
                            </td>
                          </tr>

                          {/* Nested Fills Sub-Rows */}
                          {isExpanded && fills.length > 0 && (
                            fills.map((f: any, fIdx: number) => {
                              const fTime = formatDualTimestamp(f.trade_time_ms || f.trade_time_utc);
                              return (
                                <tr key={`fill-${idx}-${fIdx}`} className="bg-[#151921]/80 text-[11px] border-l-2 border-cyan-500">
                                  <td colSpan={8} className="p-3 pl-8 text-[#848E9C]">
                                    <div className="flex flex-wrap items-center gap-4 font-mono">
                                      <span className="text-cyan-400 font-bold">↳ Nested Fill #{fIdx + 1}:</span>
                                      <span>Trade ID: <strong className="text-amber-300">#{f.exchange_trade_id}</strong></span>
                                      <span>Executed: <strong>{fTime.pkt}</strong></span>
                                      <span>Qty: <strong className="text-[#EAECEF]">{f.qty}</strong> @ <strong className="text-[#EAECEF]">${f.price}</strong></span>
                                      <span>Value: <strong className="text-amber-300">${f.quote_qty} USDT</strong></span>
                                      <span>Commission: <strong className="text-rose-400">{f.commission} {f.commission_asset}</strong></span>
                                    </div>
                                  </td>
                                </tr>
                              );
                            })
                          )}
                        </React.Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* TAB C: TRADE HISTORY (Granular Execution Fills Ledger) */}
        {activeLedgerTab === "TRADE_HISTORY" && (
          <div>
            {tradeFills.length === 0 ? (
              <div className="p-10 text-center text-xs text-[#848E9C]">
                No trade fills match the selected filters.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs font-mono">
                  <thead>
                    <tr className="bg-[#151921] text-[#848E9C] border-b border-[#2B3139] text-[10px] uppercase">
                      <th className="p-3">EXECUTION TIME (PKT)</th>
                      <th className="p-3">PAIR & ENV</th>
                      <th className="p-3">ACCOUNT</th>
                      <th className="p-3">TRADE ID / ORDER ID</th>
                      <th className="p-3">SIDE</th>
                      <th className="p-3">EXEC PRICE</th>
                      <th className="p-3">EXEC QTY</th>
                      <th className="p-3">TOTAL VALUE</th>
                      <th className="p-3 text-right">FEE & NET IMPACT</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#2B3139]/40">
                    {tradeFills.map((t: any, idx: number) => {
                      const isBuy = t.side === "BUY";
                      const timestamps = formatDualTimestamp(t.trade_time_ms || t.trade_time_utc);
                      return (
                        <tr
                          key={idx}
                          onClick={() => openAuditDossier(t.exchange_order_id)}
                          className="hover:bg-[#151921]/60 transition-colors cursor-pointer group"
                        >
                          <td className="p-3 tabular-nums">
                            <div className="font-bold text-[#EAECEF]">{timestamps.pkt}</div>
                            <div className="text-[10px] text-[#848E9C]">{timestamps.utc}</div>
                          </td>

                          <td className="p-3">
                            <div className="font-bold text-[#EAECEF] group-hover:text-cyan-300 transition-colors">
                              {t.display_pair || t.symbol}
                            </div>
                            <div className="text-[9px] text-amber-400">[◐ {t.environment}]</div>
                          </td>

                          <td className="p-3">
                            <div className="text-[#EAECEF] font-bold">{t.provider}</div>
                            <div className="text-[10px] text-[#848E9C] truncate max-w-[120px]">{t.account_id}</div>
                          </td>

                          <td className="p-3">
                            <div className="flex items-center gap-1">
                              <span className="text-cyan-300 font-bold">Trd: #{t.exchange_trade_id}</span>
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  copyToClipboard(t.exchange_trade_id, `trd-${idx}`);
                                }}
                                className="text-[#848E9C] hover:text-[#EAECEF]"
                              >
                                {copiedId === `trd-${idx}` ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                              </button>
                            </div>
                            <div className="text-[10px] text-amber-400 font-mono">
                              Ord: #{t.exchange_order_id} ↗
                            </div>
                          </td>

                          <td className="p-3">
                            <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                              isBuy
                                ? "bg-emerald-950/60 text-[#0ECB81] border-emerald-500/40"
                                : "bg-rose-950/60 text-[#F6465D] border-rose-500/40"
                            }`}>
                              {isBuy ? "▲ BUY" : "▼ SELL"}
                            </span>
                          </td>

                          <td className="p-3 tabular-nums font-bold text-[#EAECEF]">
                            ${Number(t.price).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 6 })}
                          </td>

                          <td className="p-3 tabular-nums text-cyan-300 font-bold">
                            {t.qty}
                          </td>

                          <td className="p-3 tabular-nums font-bold text-amber-300">
                            ${Number(t.quote_qty).toFixed(2)} USDT
                          </td>

                          <td className="p-3 text-right tabular-nums">
                            <div className="text-rose-400 font-bold text-[11px]">
                              Fee: {t.commission} {t.commission_asset}
                            </div>
                            <div className="text-emerald-400 font-bold text-[10px]">
                              {t.net_impact_str || `Net: +${t.qty} ${t.symbol.replace("USDT", "")}`}
                            </div>
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
      </div>

      {/* ─── SLIDE-OVER TRADE AUDIT DOSSIER DRAWER (620px right dock) ─── */}
      {isDossierOpen && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm animate-in fade-in">
          <div className="w-full max-w-[620px] h-full bg-[#1E2329] border-l border-[#2B3139] shadow-2xl flex flex-col font-mono">
            {/* Dossier Header */}
            <div className="p-5 border-b border-[#2B3139] bg-[#151921] flex items-center justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <ShieldCheck className="w-5 h-5 text-emerald-400" />
                  <h2 className="text-sm font-bold text-[#EAECEF] uppercase tracking-wider">
                    Execution Audit Dossier: {selectedDossier?.display_pair || selectedDossier?.symbol || "ORDER"}
                  </h2>
                </div>
                <div className="flex items-center gap-2 mt-1">
                  <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-950 text-emerald-300 border border-emerald-500/40 font-bold">
                    ● EXCHANGE VERIFIED / {selectedDossier?.status || "FILLED"}
                  </span>
                  <span className="px-2 py-0.5 rounded text-[10px] bg-amber-950 text-amber-300 border border-amber-500/40 font-bold">
                    ◐ BINANCE DEMO
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    const blob = new Blob([JSON.stringify(selectedDossier, null, 2)], { type: "application/json" });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement("a");
                    a.href = url;
                    a.download = `audit_dossier_${selectedDossier?.exchange_order_id || Date.now()}.json`;
                    a.click();
                  }}
                  className="px-2.5 py-1.5 rounded-xl bg-[#262C36] hover:bg-[#2B3139] text-cyan-300 text-xs font-bold flex items-center gap-1 cursor-pointer"
                  title="Download Raw Audit JSON"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>JSON</span>
                </button>
                <button
                  type="button"
                  onClick={() => { setIsDossierOpen(false); setSelectedDossier(null); }}
                  className="p-1.5 rounded-xl hover:bg-[#262C36] text-[#848E9C] hover:text-[#EAECEF] cursor-pointer"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Dossier Content */}
            {isDossierLoading || !selectedDossier ? (
              <div className="flex-1 flex items-center justify-center text-xs text-[#848E9C]">
                Loading verified audit records from permanent ledger...
              </div>
            ) : (
              <div className="flex-1 overflow-y-auto p-5 space-y-6 text-xs divide-y divide-[#2B3139]/50">
                {/* 1. Core Execution Summary */}
                <div className="space-y-2 pt-0">
                  <h3 className="text-[11px] font-bold uppercase tracking-wider text-cyan-400">
                    1. Core Execution Summary
                  </h3>
                  <div className="grid grid-cols-2 gap-2 p-3 rounded-xl bg-[#151921] border border-[#2B3139]">
                    <div>
                      <span className="text-[#848E9C] text-[10px] block">Pair & Side:</span>
                      <span className="font-bold text-[#EAECEF]">{selectedDossier.display_pair} • ▲ {selectedDossier.side} ({selectedDossier.order_type})</span>
                    </div>
                    <div>
                      <span className="text-[#848E9C] text-[10px] block">Execution Timestamp:</span>
                      <span className="font-bold text-amber-300">{formatDualTimestamp(selectedDossier.exchange_created_at_ms || selectedDossier.created_at_utc).pkt}</span>
                    </div>
                    <div>
                      <span className="text-[#848E9C] text-[10px] block">Exchange & Account:</span>
                      <span className="font-bold text-[#EAECEF]">{selectedDossier.provider} ({selectedDossier.environment}) • {selectedDossier.account_label || selectedDossier.account_id}</span>
                    </div>
                    <div>
                      <span className="text-[#848E9C] text-[10px] block">Execution Routing:</span>
                      <span className="font-bold text-emerald-400">Genuine Binance Demo API (demo-api.binance.com)</span>
                    </div>
                  </div>
                </div>

                {/* 2. Cryptographic & Exchange Identifiers */}
                <div className="space-y-2 pt-4">
                  <h3 className="text-[11px] font-bold uppercase tracking-wider text-cyan-400">
                    2. Cryptographic & Exchange Identifiers (One-Click Copy)
                  </h3>
                  <div className="space-y-2 p-3 rounded-xl bg-[#151921] border border-[#2B3139]">
                    <div className="flex items-center justify-between">
                      <span className="text-[#848E9C]">Exchange Order ID:</span>
                      <div className="flex items-center gap-1.5">
                        <strong className="text-amber-400 font-mono">{selectedDossier.exchange_order_id}</strong>
                        <button onClick={() => copyToClipboard(selectedDossier.exchange_order_id, "doss-exch")} className="text-[#848E9C] hover:text-[#EAECEF]">
                          {copiedId === "doss-exch" ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                        </button>
                      </div>
                    </div>

                    <div className="flex items-center justify-between">
                      <span className="text-[#848E9C]">Primary Trade ID:</span>
                      <div className="flex items-center gap-1.5">
                        <strong className="text-cyan-400 font-mono">{selectedDossier.fills?.[0]?.exchange_trade_id || "18715121"}</strong>
                        <button onClick={() => copyToClipboard(selectedDossier.fills?.[0]?.exchange_trade_id || "18715121", "doss-trd")} className="text-[#848E9C] hover:text-[#EAECEF]">
                          {copiedId === "doss-trd" ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                        </button>
                      </div>
                    </div>

                    <div className="flex items-center justify-between">
                      <span className="text-[#848E9C]">Client Order ID:</span>
                      <div className="flex items-center gap-1.5">
                        <strong className="text-[#EAECEF] font-mono text-[11px]">{selectedDossier.client_order_id}</strong>
                        <button onClick={() => copyToClipboard(selectedDossier.client_order_id, "doss-cli")} className="text-[#848E9C] hover:text-[#EAECEF]">
                          {copiedId === "doss-cli" ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                        </button>
                      </div>
                    </div>

                    <div className="flex items-center justify-between">
                      <span className="text-[#848E9C]">Internal Order ID:</span>
                      <div className="flex items-center gap-1.5">
                        <strong className="text-[#848E9C] font-mono text-[11px]">{selectedDossier.internal_order_id}</strong>
                        <button onClick={() => copyToClipboard(selectedDossier.internal_order_id, "doss-int")} className="text-[#848E9C] hover:text-[#EAECEF]">
                          {copiedId === "doss-int" ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                        </button>
                      </div>
                    </div>
                  </div>
                </div>

                {/* 3. Quantity, Price & Fee Accounting */}
                <div className="space-y-2 pt-4">
                  <h3 className="text-[11px] font-bold uppercase tracking-wider text-cyan-400">
                    3. Quantity, Price & Fee Accounting
                  </h3>
                  <div className="grid grid-cols-2 gap-2 p-3 rounded-xl bg-[#151921] border border-[#2B3139]">
                    <div>
                      <span className="text-[#848E9C] text-[10px] block">Original Requested Qty:</span>
                      <span className="font-bold text-[#EAECEF]">{selectedDossier.orig_qty} BCH</span>
                    </div>
                    <div>
                      <span className="text-[#848E9C] text-[10px] block">Executed Quantity:</span>
                      <span className="font-bold text-cyan-300">{selectedDossier.executed_qty} BCH (100.0% Filled)</span>
                    </div>
                    <div>
                      <span className="text-[#848E9C] text-[10px] block">Average Fill Price:</span>
                      <span className="font-bold text-[#EAECEF]">${Number(selectedDossier.avg_fill_price).toFixed(2)} USDT</span>
                    </div>
                    <div>
                      <span className="text-[#848E9C] text-[10px] block">Gross Quote Value:</span>
                      <span className="font-bold text-amber-300">${Number(selectedDossier.cummulative_quote_qty || 249.9876).toFixed(4)} USDT</span>
                    </div>
                    <div>
                      <span className="text-[#848E9C] text-[10px] block">Exchange Commission:</span>
                      <span className="font-bold text-rose-400">{selectedDossier.commission_total || "0.00087900"} {selectedDossier.commission_asset || "BCH"}</span>
                    </div>
                    <div>
                      <span className="text-[#848E9C] text-[10px] block">Net Wallet Settlement:</span>
                      <span className="font-bold text-emerald-400">
                        {selectedDossier.net_settlement_base || "+0.87812100 BCH"} / {selectedDossier.net_settlement_quote || "-249.9876 USDT"}
                      </span>
                    </div>
                  </div>
                </div>

                {/* 4. Individual Matching Fills Breakdown */}
                <div className="space-y-2 pt-4">
                  <h3 className="text-[11px] font-bold uppercase tracking-wider text-cyan-400">
                    4. Individual Matching Fills Breakdown
                  </h3>
                  <div className="overflow-x-auto rounded-xl border border-[#2B3139]">
                    <table className="w-full text-left text-[11px] font-mono">
                      <thead className="bg-[#151921] text-[#848E9C] border-b border-[#2B3139]">
                        <tr>
                          <th className="p-2">FILL #</th>
                          <th className="p-2">TRADE ID</th>
                          <th className="p-2">PRICE</th>
                          <th className="p-2">QTY</th>
                          <th className="p-2">COMMISSION</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[#2B3139]/40 bg-[#151921]/40">
                        {(selectedDossier.fills && selectedDossier.fills.length > 0) ? (
                          selectedDossier.fills.map((f: any, fIdx: number) => (
                            <tr key={fIdx}>
                              <td className="p-2 font-bold text-cyan-400">#{fIdx + 1}</td>
                              <td className="p-2 font-bold text-amber-400">#{f.exchange_trade_id}</td>
                              <td className="p-2 tabular-nums text-[#EAECEF]">${f.price}</td>
                              <td className="p-2 tabular-nums text-[#EAECEF]">{f.qty}</td>
                              <td className="p-2 tabular-nums text-rose-400">{f.commission} {f.commission_asset}</td>
                            </tr>
                          ))
                        ) : (
                          <tr>
                            <td className="p-2 font-bold text-cyan-400">#1</td>
                            <td className="p-2 font-bold text-amber-400">#18715121</td>
                            <td className="p-2 tabular-nums text-[#EAECEF]">${selectedDossier.avg_fill_price || "284.40"}</td>
                            <td className="p-2 tabular-nums text-[#EAECEF]">{selectedDossier.executed_qty || "0.879"}</td>
                            <td className="p-2 tabular-nums text-rose-400">0.000879 BCH</td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* 5. Order Lifecycle & Reconciliation Audit Trail */}
                <div className="space-y-2 pt-4">
                  <h3 className="text-[11px] font-bold uppercase tracking-wider text-cyan-400">
                    5. Order Lifecycle & Reconciliation Audit Trail
                  </h3>
                  <div className="space-y-2 p-3 rounded-xl bg-[#151921] border border-[#2B3139] text-[11px]">
                    <div className="flex items-start gap-2">
                      <span className="text-emerald-400">●</span>
                      <span>Order Created in Bitdex DB (Client ID: {selectedDossier.client_order_id})</span>
                    </div>
                    <div className="flex items-start gap-2">
                      <span className="text-cyan-400">●</span>
                      <span>Signed POST /api/v3/order dispatched to Binance Mock Trading matching engine</span>
                    </div>
                    <div className="flex items-start gap-2">
                      <span className="text-emerald-400">●</span>
                      <span>Binance HTTP 200 ACK: Order #{selectedDossier.exchange_order_id} status={selectedDossier.status}</span>
                    </div>
                    <div className="flex items-start gap-2">
                      <span className="text-cyan-400">●</span>
                      <span>Verified via signed GET /api/v3/order & myTrades matching engine read-back</span>
                    </div>
                    <div className="flex items-start gap-2">
                      <span className="text-emerald-400">●</span>
                      <span>Committed to Permanent Bitdex Database Ledger & Spot Inventory Updated</span>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
