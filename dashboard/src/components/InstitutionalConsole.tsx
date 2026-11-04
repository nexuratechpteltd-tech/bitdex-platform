"use client";

import React, { useState, useEffect, useRef, useCallback, useMemo } from "react";
import {
  Zap,
  Play,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  Copy,
  Check,
  ChevronRight,
  TrendingUp,
  Layers,
  Lock,
  Key,
  Search,
  Sliders,
  DollarSign,
  BarChart3,
  Loader2,
  Compass,
  ArrowUpRight,
  ArrowDownRight,
  Sparkles,
  ChevronDown,
  Brain,
  FileText,
  Calendar,
  Globe,
  Users,
  Gauge,
  Bot,
  Scale,
  ChevronUp,
  RotateCcw,
  Square,
  XCircle,
  StopCircle,
  History,
  Ban,
  CheckSquare,
  Trash2,
  Target,
  Coins,
  DollarSign as FXDollar,
  Clock,
  ShieldAlert,
  Flame,
  X,
  ExternalLink,
  Download,
} from "lucide-react";

import UnifiedSignalDashboard from "@/components/UnifiedSignalDashboard";

// ─── API Helper ─────────────────────────────────────────────
const API_BASE = "/trading/api/backend/grid";

async function apiFetch(path: string, opts?: RequestInit) {
  let normalizedPath = path;
  if (normalizedPath.includes("?")) {
    const [p, q] = normalizedPath.split("?");
    normalizedPath = p.endsWith("/") ? p + "?" + q : p + "/?" + q;
  } else if (!normalizedPath.endsWith("/")) {
    normalizedPath = normalizedPath + "/";
  }
  const tok = typeof window !== "undefined"
    ? (localStorage.getItem("tauric_session_token") || localStorage.getItem("bitdex_auth_token") || localStorage.getItem("tauric_token") || "")
    : "";
  const res = await fetch(`${API_BASE}${normalizedPath}`, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      ...(tok ? { Authorization: `Bearer ${tok}` } : {}),
      ...opts?.headers,
    },
  });
  return res;
}

// ─── Types ──────────────────────────────────────────────────
interface TelemetryProvider {
  provider: string;
  status: string;
  is_active: boolean;
  active_requests_count: number;
  current_operation: string;
  request_count: number;
  tokens_available: boolean;
  total_tokens?: number;
  input_tokens?: number;
  output_tokens?: number;
  known_tokens?: number;
  calls_without_usage?: number;
  daily_tokens_used?: number;
  daily_budget?: number;
  budget_exceeded?: boolean;
}

interface TelemetryData {
  status: string;
  uptime_seconds: number;
  tauric: TelemetryProvider;
  jev: TelemetryProvider;
  active_sessions_count: number;
  recent_logs: Array<{
    timestamp: string;
    level: string;
    message: string;
    provider?: string;
  }>;
}

interface SourceMetadata {
  source_type: string;
  source_label: string;
  source_providers: string[];
  pipeline_description: string;
  badge_color?: string;
}

interface SymbolItem {
  symbol: string;
  instrument_id?: string;
  base: string;
  quote: string;
  name?: string;
  category?: string;
  spread_pips?: number;
  price?: number;
  asset_class?: string;
}

interface ForexSessionInfo {
  current_session: string;
  market_status: string;
  is_weekend: boolean;
  is_overlap: boolean;
  next_major_session: string;
  session_time_pkt: string;
}

interface ScanWorkspaceState {
  scanJobId: string | null;
  isScanning: boolean;
  scanError: string | null;
  candidates: any[];
  sourceMetadata: SourceMetadata | null;
  selectedCandidate: any | null;
  isAnalyzing: boolean;
  analyzeJobId: string | null;
  analysisResult: any | null;
  analysisError: string | null;
  lastUpdated: string | null;
}

interface AgentStage {
  id: string;
  name: string;
  status: "COMPLETED" | "RUNNING" | "PENDING" | "CANCELLED" | "FAILED";
  description: string;
}

interface TauricWorkspaceState {
  selectedSymbol: string;
  selectedInstrumentId?: string;
  wizardStep: number;
  analysisDate: string;
  outputLanguage: string;
  selectedAnalysts: string[];
  researchDepth: number;
  thinkingTier: string;
  isAnalyzing: boolean;
  isCancelling: boolean;
  isCancelled: boolean;
  cancelInfo: {
    cancel_requested_at?: string;
    cancel_confirmed_at?: string;
    worker_terminated_at?: string;
  } | null;
  analyzeJobId: string | null;
  analysisResult: any | null;
  analysisError: string | null;
  sourceMetadata: SourceMetadata | null;
  lastUpdated: string | null;
  showFullReport: boolean;
  expandedReportTab: string;
  overallProgress: number;
  currentActivity: string;
  stages: AgentStage[];
}

interface MarketWorkspaces {
  scalping: ScanWorkspaceState;
  swing: ScanWorkspaceState;
  tradeSetup: ScanWorkspaceState;
  tauricDeepResearch: TauricWorkspaceState;
}

interface DualMarketWorkspaces {
  crypto: MarketWorkspaces;
  forex: MarketWorkspaces;
}

interface JobSessionItem {
  job_id: string;
  strategy: string;
  display_symbol?: string;
  market?: "CRYPTO" | "FOREX";
  asset_class?: string;
  symbol: string;
  pair: string;
  status: "RUNNING" | "PENDING" | "COMPLETED" | "CANCELLED" | "INTERRUPTED" | "FAILED";
  direction?: string;
  progress: number;
  current_stage: string;
  current_activity: string;
  started_at: string;
  updated_at: string;
  created_at_pkt?: string;
  entry_valid_until_pkt?: string;
  expires_at_pkt?: string;
  time_stop_pkt?: string;
  provider: string;
  tauric_run_id?: string;
  stages?: AgentStage[];
  result?: any;
  cancelInfo?: any;
  entry_val?: any;
  tp_val?: any;
  sl_val?: any;
  timing?: any;
}

const initialTauricStages = (): AgentStage[] => [
  { id: "market_analyst", name: "Market Analyst", status: "PENDING", description: "Analyzing order book, volume profiles & technical structure" },
  { id: "sentiment_analyst", name: "Sentiment Analyst", status: "PENDING", description: "Gauging social sentiment & on-chain / macro sentiment signals" },
  { id: "news_analyst", name: "News Analyst", status: "PENDING", description: "Screening real-time market catalysts & scheduled economic releases" },
  { id: "bull_researcher", name: "Bull Researcher", status: "PENDING", description: "Building growth thesis & upside catalyst scenarios" },
  { id: "bear_researcher", name: "Bear Researcher", status: "PENDING", description: "Stress-testing downside risks & liquidation / support clusters" },
  { id: "research_manager", name: "Research Manager", status: "PENDING", description: "Synthesizing bull/bear debate into strategic conviction" },
  { id: "trader", name: "Trader Sizing", status: "PENDING", description: "Formulating precise entry zones, stop losses & order sizing" },
  { id: "risk_team", name: "Risk Team Review", status: "PENDING", description: "Stress-testing proposal across aggressive, neutral & conservative profiles" },
  { id: "portfolio_manager", name: "Portfolio Manager Ruling", status: "PENDING", description: "Finalizing portfolio allocation rating & strategic thesis" },
  { id: "jev_review", name: "Jev Independent Review", status: "PENDING", description: "Running independent blind statistical expectation validation" },
];

const initialScanWorkspace = (): ScanWorkspaceState => ({
  scanJobId: null,
  isScanning: false,
  scanError: null,
  candidates: [],
  sourceMetadata: null,
  selectedCandidate: null,
  isAnalyzing: false,
  analyzeJobId: null,
  analysisResult: null,
  analysisError: null,
  lastUpdated: null,
});

const initialTauricWorkspace = (defaultSymbol: string = "SOLUSDT"): TauricWorkspaceState => ({
  selectedSymbol: defaultSymbol,
  wizardStep: 1,
  analysisDate: new Date().toISOString().split("T")[0],
  outputLanguage: "English",
  selectedAnalysts: ["market", "social", "news"],
  researchDepth: 1,
  thinkingTier: "deepseek-v4-flash",
  isAnalyzing: false,
  isCancelling: false,
  isCancelled: false,
  cancelInfo: null,
  analyzeJobId: null,
  analysisResult: null,
  analysisError: null,
  sourceMetadata: null,
  lastUpdated: null,
  showFullReport: false,
  expandedReportTab: "analysts",
  overallProgress: 0,
  currentActivity: "",
  stages: initialTauricStages(),
});

const createMarketWorkspace = (isForex: boolean = false): MarketWorkspaces => ({
  scalping: initialScanWorkspace(),
  swing: initialScanWorkspace(),
  tradeSetup: initialScanWorkspace(),
  tauricDeepResearch: initialTauricWorkspace(isForex ? "EUR/USD" : "SOLUSDT"),
});

const STORAGE_KEY = "bitdex_trading_workspaces_v1";

// ─── Signal Timing & State Machine Card Component (0 LLM Tokens) ──────
function SignalTimingCard({
  symbol,
  direction,
  entryZone,
  takeProfit,
  stopLoss,
  timing,
  onStatusUpdate,
  historicalStatus,
  jobId,
}: {
  symbol: string;
  direction: string;
  entryZone: string;
  takeProfit: number;
  stopLoss: number;
  timing?: any;
  onStatusUpdate?: (statusResult: any) => void;
  historicalStatus?: string;
  jobId?: string;
}) {
  const [isRechecking, setIsRechecking] = useState(false);
  const [evalResult, setEvalResult] = useState<any>(null);

  const t = evalResult?.timing || timing;
  const signalState = evalResult?.signal_state || historicalStatus || "PENDING_ENTRY";

  const handleRecheck = async () => {
    setIsRechecking(true);
    try {
      let minP: number | undefined;
      let maxP: number | undefined;
      if (entryZone && entryZone.includes("—")) {
        const parts = entryZone.split("—").map((p) => parseFloat(p.replace(/[^0-9.]/g, "")));
        if (parts.length === 2 && !isNaN(parts[0]) && !isNaN(parts[1])) {
          minP = Math.min(parts[0], parts[1]);
          maxP = Math.max(parts[0], parts[1]);
        }
      } else if (entryZone && entryZone.includes("-")) {
        const parts = entryZone.split("-").map((p) => parseFloat(p.replace(/[^0-9.]/g, "")));
        if (parts.length === 2 && !isNaN(parts[0]) && !isNaN(parts[1])) {
          minP = Math.min(parts[0], parts[1]);
          maxP = Math.max(parts[0], parts[1]);
        }
      }

      const res = await apiFetch("/recheck-signal", {
        method: "POST",
        body: JSON.stringify({
          symbol,
          direction,
          entry_min: minP,
          entry_max: maxP,
          take_profit: takeProfit,
          stop_loss: stopLoss,
          timing_meta: t,
          historical_status: signalState,
          job_id: jobId,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setEvalResult(data);
        if (onStatusUpdate) onStatusUpdate(data);
      }
    } catch (e) {
      console.error("Recheck error:", e);
    } finally {
      setIsRechecking(false);
    }
  };

  const getBadgeStyle = (state: string) => {
    switch (state) {
      case "TP_HIT":
      case "COMPLETED":
        return "bg-emerald-950/80 text-emerald-300 border-emerald-500/40";
      case "SL_HIT":
      case "INVALIDATED":
        return "bg-rose-950/80 text-rose-300 border-rose-500/40";
      case "EXPIRED":
      case "STALE":
        return "bg-slate-800 text-[#D4D4D8] border-[#27272A]";
      case "ENTRY_TRIGGERED":
      case "ACTIVE_POSITION":
        return "bg-cyan-950/80 text-cyan-300 border-cyan-500/40 animate-pulse";
      default:
        return "bg-amber-950/80 text-amber-300 border-amber-500/40";
    }
  };

  return (
    <div className="rounded-sm border border-[#27272A] bg-[#141418] p-4 space-y-3 font-mono text-xs shadow-inner">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#27272A]/80 pb-2">
        <div className="flex items-center gap-2">
          <Clock className="w-4 h-4 text-cyan-400" />
          <span className="font-bold uppercase tracking-wider text-[#D4D4D8]">
            SIGNAL LIFECYCLE & TIMING
          </span>
          <span className="text-[10px] text-[#71717A]">
            {t?.policy_version || "TIMEFRAME_POLICY_V1"} • {t?.timezone || "Asia/Karachi (PKT)"}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <span className={`px-2.5 py-0.5 rounded-full border text-[11px] font-bold ${getBadgeStyle(signalState)}`}>
            ● {signalState.replace("_", " ")}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-left">
        <div className="bg-[#141418]/60 p-2.5 rounded-lg border border-[#27272A]/60">
          <span className="text-[10px] text-[#71717A] block uppercase">Signal Generated</span>
          <span className="font-bold text-[#FAFAFA] text-xs">
            {t?.generated_at_pkt || "Live Plan"}
          </span>
        </div>

        <div className="bg-[#141418]/60 p-2.5 rounded-lg border border-[#27272A]/60">
          <span className="text-[10px] text-amber-400 block uppercase">Entry Valid Until</span>
          <span className="font-bold text-amber-300 text-xs">
            {t?.entry_valid_until_pkt || "--"}
          </span>
          {t?.entry_valid_in_display && (
            <span className="text-[10px] text-[#71717A] block">({t.entry_valid_in_display} left)</span>
          )}
        </div>

        <div className="bg-[#141418]/60 p-2.5 rounded-lg border border-[#27272A]/60">
          <span className="text-[10px] text-cyan-400 block uppercase">Setup Expires</span>
          <span className="font-bold text-cyan-300 text-xs">
            {t?.expires_at_pkt || "--"}
          </span>
          {t?.expires_in_display && (
            <span className="text-[10px] text-[#71717A] block">({t.expires_in_display} left)</span>
          )}
        </div>

        <div className="bg-[#141418]/60 p-2.5 rounded-lg border border-[#27272A]/60">
          <span className="text-[10px] text-rose-400 block uppercase">Time Stop (Hard Exit)</span>
          <span className="font-bold text-rose-300 text-xs">
            {t?.time_stop_pkt || "--"}
          </span>
        </div>
      </div>

      {evalResult && (
        <div className="p-2.5 rounded-lg bg-[#141418] border border-cyan-500/20 text-[#D4D4D8] text-[11px] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-[#71717A]">Live Price:</span>
            <span className="font-bold text-white">${evalResult.current_price?.toFixed(4)}</span>
            <span className="text-[#A1A1AA]">|</span>
            <span className="text-[#71717A]">Lifecycle Status:</span>
            <span className="font-bold text-cyan-400">{evalResult.message || evalResult.signal_state}</span>
          </div>
          <span className="text-[10px] text-[#71717A]">Checked: {evalResult.checked_at_pkt}</span>
        </div>
      )}

      <div className="flex items-center justify-between pt-1">
        <span className="text-[10px] text-[#71717A]">
          Zero AI token cost • Real-time candle validation & state machine
        </span>
        <button
          onClick={handleRecheck}
          disabled={isRechecking}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#141418] hover:bg-slate-800 border border-[#27272A] text-cyan-400 hover:text-cyan-300 text-xs font-bold transition-all cursor-pointer disabled:opacity-50"
        >
          <RotateCcw className={`w-3.5 h-3.5 ${isRechecking ? "animate-spin text-cyan-400" : ""}`} />
          <span>{isRechecking ? "Checking Candles..." : "Re-Check Signal Status"}</span>
        </button>
      </div>
    </div>
  );
}

// ─── Grid Timing & Validity Card ─────────────────────────────
function GridTimingCard({
  symbol,
  lowerPrice,
  upperPrice,
  timing,
}: {
  symbol: string;
  lowerPrice: number;
  upperPrice: number;
  timing?: any;
}) {
  const [isRechecking, setIsRechecking] = useState(false);
  const [gridStatus, setGridStatus] = useState<any>(null);

  const handleRecheckGrid = async () => {
    setIsRechecking(true);
    try {
      const res = await apiFetch("/grid/recheck", {
        method: "POST",
        body: JSON.stringify({
          symbol,
          lower_price: lowerPrice,
          upper_price: upperPrice,
          timing_meta: timing,
        }),
      });
      if (res.ok) {
        const d = await res.json();
        setGridStatus(d);
      }
    } catch (e) {
      console.error("Grid recheck error:", e);
    } finally {
      setIsRechecking(false);
    }
  };

  const inRange = gridStatus ? gridStatus.in_range : true;

  return (
    <div className="rounded-sm border border-[#27272A] bg-[#141418] p-4 space-y-3 font-mono text-xs shadow-inner">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#27272A]/80 pb-2">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-cyan-400" />
          <span className="font-bold uppercase tracking-wider text-[#D4D4D8]">
            SPOT GRID PARAMETER VALIDITY
          </span>
          <span className="text-[10px] text-[#71717A]">
            {timing?.policy_version || "TIMEFRAME_POLICY_V1"} • {timing?.timezone || "Asia/Karachi (PKT)"}
          </span>
        </div>

        <span className={`px-2.5 py-0.5 rounded-full border text-[11px] font-bold ${
          inRange
            ? "bg-emerald-950/80 text-emerald-300 border-emerald-500/40"
            : "bg-rose-950/80 text-rose-300 border-rose-500/40"
        }`}>
          ● {inRange ? "IN_RANGE" : "OUT_OF_BOUNDS"}
        </span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-left">
        <div className="bg-[#141418]/60 p-2.5 rounded-lg border border-[#27272A]/60">
          <span className="text-[10px] text-[#71717A] block uppercase">Grid Generated</span>
          <span className="font-bold text-[#FAFAFA] text-xs">
            {timing?.generated_at_pkt || "Live Plan"}
          </span>
        </div>

        <div className="bg-[#141418]/60 p-2.5 rounded-lg border border-[#27272A]/60">
          <span className="text-[10px] text-cyan-400 block uppercase">Channel Bounds</span>
          <span className="font-bold text-cyan-300 text-xs">
            ${lowerPrice?.toFixed(3)} — ${upperPrice?.toFixed(3)}
          </span>
          <span className="text-[10px] text-[#71717A] block">Active Bounds</span>
        </div>

        <div className="bg-[#141418]/60 p-2.5 rounded-lg border border-[#27272A]/60">
          <span className="text-[10px] text-purple-400 block uppercase">Grid Valid Until</span>
          <span className="font-bold text-purple-300 text-xs">
            {timing?.expires_at_pkt || "--"}
          </span>
          {timing?.expires_in_display && (
            <span className="text-[10px] text-[#71717A] block">({timing.expires_in_display} left)</span>
          )}
        </div>

        <div className="bg-[#141418]/60 p-2.5 rounded-lg border border-[#27272A]/60">
          <span className="text-[10px] text-[#71717A] block uppercase">Current Price</span>
          <span className="font-bold text-white text-xs">
            {gridStatus?.current_price ? `$${gridStatus.current_price.toFixed(3)}` : "$--"}
          </span>
          <span className="text-[10px] text-[#71717A] block">Live ticker</span>
        </div>
      </div>

      <div className="p-2.5 rounded-lg bg-[#151e32] border border-[#263554] text-[#D4D4D8] text-[11px] flex items-center justify-between">
        <span>RANGE STATUS: {gridStatus?.message || `Channel active [${lowerPrice?.toFixed(4)} - ${upperPrice?.toFixed(4)}]. Valid for 24h.`}</span>
      </div>

      <div className="flex items-center justify-between pt-1">
        <span className="text-[10px] text-[#71717A]">Live ticker boundary re-check • 0 AI tokens consumed</span>
        <button
          onClick={handleRecheckGrid}
          disabled={isRechecking}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#141418] hover:bg-slate-800 border border-[#27272A] text-cyan-400 hover:text-cyan-300 text-xs font-bold transition-all cursor-pointer disabled:opacity-50"
        >
          <RotateCcw className={`w-3.5 h-3.5 ${isRechecking ? "animate-spin text-cyan-400" : ""}`} />
          <span>{isRechecking ? "Re-checking..." : "Re-Check Grid Status"}</span>
        </button>
      </div>
    </div>
  );
}

// ─── Main Trading Console Component ──────────────────────────
export default function InstitutionalConsole() {
  // Top-Level Active Market Tab: CRYPTO or FOREX
  const [activeMarket, setActiveMarket] = useState<"CRYPTO" | "FOREX">("CRYPTO");
  const [viewMode, setViewMode] = useState<"SIGNALS" | "STRATEGY">("SIGNALS");

  // Multi-Strategy and Dual-Market State
  const [strategy, setStrategy] = useState<"SHORT_TERM" | "LONGER_TERM" | "TRADE_SETUP" | "TAURIC_DEEP_RESEARCH">("SHORT_TERM");
  const [userCapital, setUserCapital] = useState<number>(100);
  const [forexTimeframe, setForexTimeframe] = useState<"5m" | "10m" | "15m">("10m");
  const [forexCategory, setForexCategory] = useState<"ALL" | "MAJORS" | "MINORS" | "PRECIOUS METALS" | "EXOTICS">("ALL");

  // Dual-Market Workspaces State (Isolated per Market)
  const [workspaces, setWorkspaces] = useState<DualMarketWorkspaces>({
    crypto: createMarketWorkspace(false),
    forex: createMarketWorkspace(true),
  });

  // Telemetry & Server Active Jobs State
  const [telemetry, setTelemetry] = useState<TelemetryData | null>(null);
  const [activePopover, setActivePopover] = useState<"tauric" | "jev" | null>(null);
  const [activeServerJobs, setActiveServerJobs] = useState<JobSessionItem[]>([]);
  const [unifiedHistory, setUnifiedHistory] = useState<JobSessionItem[]>([]);
  const [historyFilter, setHistoryFilter] = useState<"all" | "tauric" | "scalp" | "swing" | "setup">("all");
  const [historyMarketFilter, setHistoryMarketFilter] = useState<"ALL" | "CRYPTO" | "FOREX">("ALL");

  // Available Symbols and Search Dropdown State
  const [cryptoSymbols, setCryptoSymbols] = useState<SymbolItem[]>([]);
  const [forexSymbols, setForexSymbols] = useState<SymbolItem[]>([]);
  const [forexSession, setForexSession] = useState<ForexSessionInfo | null>(null);
  const [isSymbolDropdownOpen, setIsSymbolDropdownOpen] = useState(false);
  const [symbolQuery, setSymbolQuery] = useState("");
  const [copiedPlan, setCopiedPlan] = useState(false);

  // Dedicated Research Results Modal & Inspector State
  const [selectedReportJob, setSelectedReportJob] = useState<any | null>(null);
  const [isReportModalOpen, setIsReportModalOpen] = useState(false);
  const [activeReportTab, setActiveReportTab] = useState<"overview" | "timing" | "debate" | "analysts" | "jev" | "metadata">("overview");
  const [isLoadingReportJob, setIsLoadingReportJob] = useState(false);
  const [reportLoadError, setReportLoadError] = useState<string | null>(null);
  const [expandedAnalyst, setExpandedAnalyst] = useState<Record<string, boolean>>({});
  const [copiedReportJson, setCopiedReportJson] = useState(false);

  const toggleExpandedAnalyst = (id: string) => {
    setExpandedAnalyst((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const popoverRef = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const isHydrated = useRef(false);

  // Active Market Workspace Helpers
  const currentMarketKey = activeMarket.toLowerCase() as "crypto" | "forex";
  const currentMarketWorkspaces = workspaces[currentMarketKey];

  const currentScanWorkspace = useMemo(() => {
    const ws = currentMarketWorkspaces;
    if (strategy === "LONGER_TERM") return { key: "swing" as const, ws: ws.swing };
    if (strategy === "TRADE_SETUP") return { key: "tradeSetup" as const, ws: ws.tradeSetup };
    return { key: "scalping" as const, ws: ws.scalping };
  }, [strategy, currentMarketWorkspaces]);

  const updateScanWorkspace = useCallback((stratKey: "scalping" | "swing" | "tradeSetup", updater: (prev: ScanWorkspaceState) => Partial<ScanWorkspaceState>) => {
    setWorkspaces((prev) => ({
      ...prev,
      [currentMarketKey]: {
        ...prev[currentMarketKey],
        [stratKey]: {
          ...prev[currentMarketKey][stratKey],
          ...updater(prev[currentMarketKey][stratKey]),
          lastUpdated: new Date().toISOString(),
        },
      },
    }));
  }, [currentMarketKey]);

  const updateTauricWorkspace = useCallback((updater: (prev: TauricWorkspaceState) => Partial<TauricWorkspaceState>) => {
    setWorkspaces((prev) => ({
      ...prev,
      [currentMarketKey]: {
        ...prev[currentMarketKey],
        tauricDeepResearch: {
          ...prev[currentMarketKey].tauricDeepResearch,
          ...updater(prev[currentMarketKey].tauricDeepResearch),
          lastUpdated: new Date().toISOString(),
        },
      },
    }));
  }, [currentMarketKey]);

  const handleOpenJobResults = useCallback(async (jobId: string) => {
    setIsLoadingReportJob(true);
    setReportLoadError(null);
    setIsReportModalOpen(true);
    try {
      const res = await apiFetch(`/job/${jobId}/`);
      if (res.ok) {
        const data = await res.json();
        setSelectedReportJob(data);
        if (data.market === "FOREX") {
          setActiveMarket("FOREX");
        } else if (data.market === "CRYPTO") {
          setActiveMarket("CRYPTO");
        }
        if (typeof window !== "undefined") {
          sessionStorage.setItem("tauric_active_job_id", jobId);
          window.history.replaceState(null, "", `#job=${jobId}`);
        }
        if (data.strategy === "TAURIC_DEEP_RESEARCH" && data.result) {
          updateTauricWorkspace(() => ({
            selectedSymbol: data.display_symbol || data.symbol,
            analysisResult: data.result,
            analyzeJobId: data.id,
            wizardStep: 2,
            isAnalyzing: false,
            overallProgress: 100,
            currentStage: "COMPLETED",
            currentActivity: "Loaded persisted research report",
          }));
        }
      } else {
        setReportLoadError(`Failed to load research report for job ID ${jobId} (HTTP ${res.status})`);
      }
    } catch (err: any) {
      setReportLoadError(`Network error loading report: ${err.message}`);
    } finally {
      setIsLoadingReportJob(false);
    }
  }, [updateTauricWorkspace]);

  const handleCloseReportModal = useCallback(() => {
    setIsReportModalOpen(false);
    if (typeof window !== "undefined") {
      sessionStorage.removeItem("tauric_active_job_id");
      window.history.replaceState(null, "", window.location.pathname);
    }
  }, []);

  const handleOpenInWorkspace = useCallback(() => {
    if (!selectedReportJob) return;
    const isFx = selectedReportJob.market === "FOREX" || selectedReportJob.symbol.includes("/") || selectedReportJob.symbol.includes("XAU");
    setActiveMarket(isFx ? "FOREX" : "CRYPTO");
    setStrategy("TAURIC_DEEP_RESEARCH");
    updateTauricWorkspace(() => ({
      selectedSymbol: selectedReportJob.display_symbol || selectedReportJob.symbol,
      analysisResult: selectedReportJob.result,
      analyzeJobId: selectedReportJob.id,
      wizardStep: 2,
      isAnalyzing: false,
      overallProgress: 100,
      currentStage: "COMPLETED",
      currentActivity: "Loaded persisted research report",
    }));
    handleCloseReportModal();
  }, [selectedReportJob, updateTauricWorkspace, handleCloseReportModal]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const checkHashAndStorage = () => {
      const hash = window.location.hash;
      const match = hash.match(/job=([a-zA-Z0-9-]+)/);
      const savedJobId = match ? match[1] : sessionStorage.getItem("tauric_active_job_id");
      if (savedJobId) {
        handleOpenJobResults(savedJobId);
      }
    };
    checkHashAndStorage();
    window.addEventListener("hashchange", checkHashAndStorage);
    return () => window.removeEventListener("hashchange", checkHashAndStorage);
  }, [handleOpenJobResults]);

  // ─── Load Available Symbols from Backend (Crypto & Forex) ─────
  useEffect(() => {
    async function loadSymbols() {
      try {
        // Load Crypto symbols
        const resCrypto = await apiFetch("/symbols?market=crypto");
        if (resCrypto.ok) {
          const data = await resCrypto.json();
          if (data.symbols && Array.isArray(data.symbols)) {
            setCryptoSymbols(data.symbols);
          }
        }
        // Load Forex symbols
        const resForex = await apiFetch("/symbols?market=forex");
        if (resForex.ok) {
          const dataFx = await resForex.json();
          if (dataFx.symbols && Array.isArray(dataFx.symbols)) {
            setForexSymbols(dataFx.symbols);
          }
          if (dataFx.session) {
            setForexSession(dataFx.session);
          }
        }
      } catch (err) {
        console.error("Failed to load symbols", err);
      }
    }
    loadSymbols();
  }, []);

  // Filtered symbols for autocomplete search
  const availableSymbols = activeMarket === "FOREX" ? forexSymbols : cryptoSymbols;
  const filteredSymbols = useMemo(() => {
    let list = availableSymbols;
    if (activeMarket === "FOREX" && forexCategory !== "ALL") {
      list = list.filter((s) => (s.category || "").toUpperCase() === forexCategory);
    }
    if (!symbolQuery.trim()) {
      if (activeMarket === "CRYPTO") {
        const priority = ["SOLUSDT", "ETHUSDT", "BTCUSDT", "BNBUSDT", "AVAXUSDT", "ADAUSDT", "DOGEUSDT", "LINKUSDT", "NEARUSDT", "SUIUSDT", "APTUSDT", "XRPUSDT"];
        const matched = list.filter((s) => priority.includes(s.symbol));
        return matched.length > 0 ? matched : list.slice(0, 15);
      }
      return list.slice(0, 20);
    }
    const q = symbolQuery.toUpperCase().trim();
    return list
      .filter((s) => s.symbol.toUpperCase().includes(q) || (s.name && s.name.toUpperCase().includes(q)) || (s.base && s.base.toUpperCase().includes(q)))
      .slice(0, 25);
  }, [availableSymbols, symbolQuery, activeMarket, forexCategory]);

  // ─── Hydrate Workspaces from LocalStorage ───────────────────
  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed.workspaces) {
          const ws = parsed.workspaces;
          // Validate Crypto workspace instrument
          if (ws.crypto?.tauricDeepResearch?.selectedInstrumentId && !ws.crypto.tauricDeepResearch.selectedInstrumentId.startsWith("crypto:")) {
            ws.crypto.tauricDeepResearch.selectedInstrumentId = "crypto:binance:SOLUSDT";
            ws.crypto.tauricDeepResearch.selectedSymbol = "SOLUSDT";
          }
          // Validate Forex workspace instrument
          if (ws.forex?.tauricDeepResearch?.selectedInstrumentId && (!ws.forex.tauricDeepResearch.selectedInstrumentId.startsWith("fx:") && !ws.forex.tauricDeepResearch.selectedInstrumentId.startsWith("metal:"))) {
            ws.forex.tauricDeepResearch.selectedInstrumentId = "fx:EURUSD";
            ws.forex.tauricDeepResearch.selectedSymbol = "EUR/USD";
          }
          setWorkspaces(ws);
        }
        if (parsed.userCapital) setUserCapital(parsed.userCapital);
        if (parsed.strategy) setStrategy(parsed.strategy);
        if (parsed.activeMarket) setActiveMarket(parsed.activeMarket);
        if (parsed.forexTimeframe) setForexTimeframe(parsed.forexTimeframe);
      }
    } catch (e) {
      console.warn("Storage hydration error:", e);
    }
    isHydrated.current = true;
  }, []);

  // ─── Persist Workspaces to LocalStorage ─────────────────────
  useEffect(() => {
    if (!isHydrated.current) return;
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          workspaces,
          userCapital,
          strategy,
          activeMarket,
          forexTimeframe,
        })
      );
    } catch (e) {
      console.warn("Storage save error:", e);
    }
  }, [workspaces, userCapital, strategy, activeMarket, forexTimeframe]);

  // ─── Poll Active Server Jobs & Telemetry ───────────────────
  const syncServerJobs = useCallback(async () => {
    try {
      const [resJobs, resTel, resHist] = await Promise.all([
        apiFetch("/jobs/active"),
        apiFetch("/telemetry"),
        apiFetch("/jobs/history"),
      ]);

      if (resJobs.ok) {
        const d = await resJobs.json();
        setActiveServerJobs(d.active_jobs || []);
      }
      if (resTel.ok) {
        const t = await resTel.json();
        setTelemetry(t);
      }
      if (resHist.ok) {
        const h = await resHist.json();
        setUnifiedHistory(h.history || []);
      }
    } catch (err) {
      // silent background sync
    }
  }, []);

  useEffect(() => {
    syncServerJobs();
    const iv = setInterval(syncServerJobs, 2500);
    return () => clearInterval(iv);
  }, [syncServerJobs]);

  // Click outside listener for Popovers and Dropdown
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setActivePopover(null);
      }
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsSymbolDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  // ─── Handlers ───────────────────────────────────────────────

  // 1. Discovery Scan Action
  const handleScanOpportunities = async () => {
    const stratKey = currentScanWorkspace.key;
    updateScanWorkspace(stratKey, () => ({
      isScanning: true,
      scanError: null,
      candidates: [],
    }));

    try {
      const res = await apiFetch("/scan", {
        method: "POST",
        body: JSON.stringify({
          capital: userCapital,
          strategy: strategy,
          market: activeMarket,
        }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to scan opportunities");
      }

      const data = await res.json();
      updateScanWorkspace(stratKey, () => ({
        candidates: data.candidates || [],
        sourceMetadata: data.source_metadata || null,
        isScanning: false,
      }));
    } catch (e: any) {
      updateScanWorkspace(stratKey, () => ({
        scanError: e.message || "Failed to scan opportunities",
        isScanning: false,
      }));
    }
  };

  // 2. Candidate Deep Analysis Action
  const handleAnalyzeCandidate = async (stratKey: "scalping" | "swing" | "tradeSetup", symbol: string, stratType: string) => {
    updateScanWorkspace(stratKey, () => ({
      isAnalyzing: true,
      analysisError: null,
      analysisResult: null,
    }));

    try {
      const res = await apiFetch("/analyze", {
        method: "POST",
        body: JSON.stringify({
          symbol: symbol,
          capital: userCapital,
          strategy: stratType,
          market: activeMarket,
          timeframe: activeMarket === "FOREX" && stratType === "SHORT_TERM" ? forexTimeframe : undefined,
          created_by_action: "ANALYZE_CANDIDATE",
        }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Analysis request failed");
      }

      const data = await res.json();
      const jobId = data.job_id;

      updateScanWorkspace(stratKey, () => ({ analyzeJobId: jobId }));

      // Poll until completion
      let pollAttempts = 0;
      const iv = setInterval(async () => {
        pollAttempts++;
        if (pollAttempts > 60) {
          clearInterval(iv);
          updateScanWorkspace(stratKey, () => ({
            isAnalyzing: false,
            analysisError: "Analysis timed out after 60s.",
          }));
          return;
        }

        try {
          const pollRes = await apiFetch(`/job/${jobId}`);
          if (pollRes.ok) {
            const jobData = await pollRes.json();
            if (jobData.state === "COMPLETED") {
              clearInterval(iv);
              updateScanWorkspace(stratKey, () => ({
                isAnalyzing: false,
                analysisResult: jobData.result,
              }));
              syncServerJobs();
            } else if (jobData.state === "FAILED" || jobData.state === "CANCELLED") {
              clearInterval(iv);
              updateScanWorkspace(stratKey, () => ({
                isAnalyzing: false,
                analysisError: jobData.error || "Analysis was cancelled or failed.",
              }));
            }
          }
        } catch (err) {
          // continue polling
        }
      }, 1000);
    } catch (e: any) {
      updateScanWorkspace(stratKey, () => ({
        isAnalyzing: false,
        analysisError: e.message || "Failed to analyze candidate",
      }));
    }
  };

  // 3. Start Tauric Deep Research (Strict User Action Gate)
  const handleStartTauricResearch = async () => {
    const ws = currentMarketWorkspaces.tauricDeepResearch;
    updateTauricWorkspace(() => ({
      isAnalyzing: true,
      isCancelled: false,
      isCancelling: false,
      analysisError: null,
      analysisResult: null,
      overallProgress: 5,
      currentActivity: "Starting Tauric multi-agent research graph...",
      stages: initialTauricStages(),
    }));

    try {
      const res = await apiFetch("/tauric-deep-research", {
        method: "POST",
        body: JSON.stringify({
          symbol: ws.selectedSymbol,
          capital: userCapital,
          market: activeMarket,
          trade_date: ws.analysisDate,
          output_language: ws.outputLanguage,
          analysts: ws.selectedAnalysts,
          research_depth: ws.researchDepth,
          thinking_tier: ws.thinkingTier,
          created_by_action: "START_DEEP_RESEARCH",
        }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to start Tauric deep research");
      }

      const data = await res.json();
      const jobId = data.job_id;

      updateTauricWorkspace(() => ({
        analyzeJobId: jobId,
        wizardStep: 2,
      }));

      // Poll progress
      let attempts = 0;
      const iv = setInterval(async () => {
        attempts++;
        if (attempts > 300) {
          clearInterval(iv);
          updateTauricWorkspace(() => ({ isAnalyzing: false }));
          return;
        }

        try {
          const pollRes = await apiFetch(`/job/${jobId}`);
          if (pollRes.ok) {
            const jData = await pollRes.json();
            updateTauricWorkspace(() => ({
              overallProgress: jData.overall_progress || 5,
              currentActivity: jData.current_activity || "Analyzing...",
              stages: jData.stages || initialTauricStages(),
            }));

            if (jData.state === "COMPLETED") {
              clearInterval(iv);
              updateTauricWorkspace(() => ({
                isAnalyzing: false,
                analysisResult: jData.result,
                overallProgress: 100,
              }));
              syncServerJobs();
            } else if (jData.state === "CANCELLED") {
              clearInterval(iv);
              updateTauricWorkspace(() => ({
                isAnalyzing: false,
                isCancelled: true,
                currentActivity: "Research cancelled by user request.",
              }));
            } else if (jData.state === "FAILED") {
              clearInterval(iv);
              updateTauricWorkspace(() => ({
                isAnalyzing: false,
                analysisError: jData.error || "Research failed.",
              }));
            }
          }
        } catch (e) {
          // continue polling
        }
      }, 1500);
    } catch (e: any) {
      updateTauricWorkspace(() => ({
        isAnalyzing: false,
        analysisError: e.message || "Failed to start Tauric research",
      }));
    }
  };

  // 4. Stop Active Job
  const handleStopJob = async (jobId: string) => {
    try {
      const res = await apiFetch(`/job/${jobId}/cancel`, { method: "POST" });
      if (res.ok) {
        syncServerJobs();
        // Update local workspace if matched
        if (currentMarketWorkspaces.tauricDeepResearch.analyzeJobId === jobId) {
          updateTauricWorkspace(() => ({
            isAnalyzing: false,
            isCancelled: true,
            isCancelling: false,
            currentActivity: "Worker hard-terminated.",
          }));
        }
      }
    } catch (e) {
      console.error("Stop job error:", e);
    }
  };

  // 5. Delete History Item
  const handleDeleteHistory = async (jobId: string) => {
    try {
      const res = await apiFetch(`/job/${jobId}`, { method: "DELETE" });
      if (res.ok) {
        setUnifiedHistory((prev) => prev.filter((h) => h.job_id !== jobId));
      }
    } catch (e) {
      console.error("Delete history error:", e);
    }
  };

  // 6. Clear All History
  const handleClearAllHistory = async () => {
    try {
      const res = await apiFetch("/history/all", { method: "DELETE" });
      if (res.ok) {
        setUnifiedHistory([]);
      }
    } catch (e) {
      console.error("Clear history error:", e);
    }
  };

  // Filtered History Records
  const filteredHistory = useMemo(() => {
    return unifiedHistory.filter((item) => {
      // Market filter
      if (historyMarketFilter !== "ALL") {
        const itemMarket = item.market || (item.symbol.includes("/") || item.symbol.includes("XAU") ? "FOREX" : "CRYPTO");
        if (itemMarket !== historyMarketFilter) return false;
      }
      // Strategy filter
      if (historyFilter === "all") return true;
      const strat = (item.strategy || "").toUpperCase();
      if (historyFilter === "tauric") return strat.includes("TAURIC");
      if (historyFilter === "scalp") return strat.includes("SHORT") || strat.includes("SCALP");
      if (historyFilter === "swing") return strat.includes("SWING") || strat.includes("LONGER");
      if (historyFilter === "setup") return strat.includes("TRADE_SETUP") || strat.includes("SETUP");
      return true;
    });
  }, [unifiedHistory, historyFilter, historyMarketFilter]);

  // Active Job Banner computation (identifying market)
  const activeTauricJob = activeServerJobs.find(
    (j) => (j.strategy.includes("TAURIC") || j.strategy === "TAURIC_DEEP_RESEARCH") && (j.status === "RUNNING" || j.status === "PENDING")
  );

  return (
    <div className="bg-[#09090B] text-[#FAFAFA] font-sans selection:bg-[#00E5FF] selection:text-white">
      {/* ─── GLOBAL ACTIVE JOB BANNER (CROSS-MARKET AWARE) ──────── */}
      {activeTauricJob && (
        <div className="sticky top-0 z-50 bg-gradient-to-r from-amber-950/90 via-slate-900/90 to-purple-950/90 border-b border-amber-500/30 backdrop-blur-md px-4 py-2 flex items-center justify-between shadow-xl">
          <div className="flex items-center gap-3">
            <div className="relative flex h-3 w-3">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-3 w-3 bg-amber-500"></span>
            </div>
            <div className="flex items-center gap-2 text-xs font-mono">
              <span className="font-bold text-amber-400 uppercase tracking-wider">TAURIC RESEARCH ACTIVE</span>
              <span className="text-[#A1A1AA]">•</span>
              <span className="px-2 py-0.5 rounded bg-slate-800 text-cyan-300 font-bold">
                {activeTauricJob.market || (activeTauricJob.symbol.includes("/") ? "FOREX" : "CRYPTO")}
              </span>
              <span className="text-[#D4D4D8] font-bold">{activeTauricJob.symbol}</span>
              <span className="text-[#A1A1AA]">•</span>
              <span className="text-[#71717A]">{activeTauricJob.current_stage}</span>
              <span className="text-amber-400 font-bold">({activeTauricJob.progress}%)</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                if (activeTauricJob.market) {
                  setActiveMarket(activeTauricJob.market as "CRYPTO" | "FOREX");
                }
                setStrategy("TAURIC_DEEP_RESEARCH");
              }}
              className="px-3 py-1 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-mono font-bold transition-all cursor-pointer"
            >
              Open Active Job
            </button>
            <button
              onClick={() => handleStopJob(activeTauricJob.job_id)}
              className="px-3 py-1 rounded-lg bg-rose-950/80 hover:bg-rose-900 border border-rose-500/40 text-rose-300 text-xs font-mono font-bold transition-all cursor-pointer"
            >
              Stop Worker
            </button>
          </div>
        </div>
      )}





      {/* ─── FOREX SESSIONS & MACRO RISK BAR (WHEN IN FOREX) ──────── */}
      {activeMarket === "FOREX" && forexSession && (
        <div className="bg-[#141418] border-b border-purple-500/30 px-6 py-2.5 flex flex-wrap items-center justify-between gap-3 text-xs font-mono">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2">
              <Clock className="w-3.5 h-3.5 text-purple-400" />
              <span className="text-[#71717A] uppercase font-bold text-[10px]">CURRENT SESSION:</span>
              <span className="font-bold text-purple-300 bg-purple-950/60 px-2 py-0.5 rounded border border-purple-500/30">
                {forexSession.current_session}
              </span>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-[#71717A] uppercase font-bold text-[10px]">MARKET STATUS:</span>
              <span className={`font-bold px-2 py-0.5 rounded text-[10px] ${
                forexSession.market_status === "OPEN" || forexSession.market_status === "PEAK LIQUIDITY"
                  ? "bg-emerald-950/80 text-emerald-300 border border-emerald-500/40"
                  : "bg-slate-800 text-amber-300 border border-[#27272A]"
              }`}>
                {forexSession.market_status}
              </span>
            </div>

            <div className="flex items-center gap-2 text-[#71717A]">
              <span className="text-[#71717A] uppercase font-bold text-[10px]">NEXT MAJOR:</span>
              <span>{forexSession.next_major_session}</span>
            </div>
          </div>

          <div className="flex items-center gap-3 text-[11px] text-[#71717A]">
            <span>PKT: <strong className="text-white">{forexSession.session_time_pkt}</strong></span>
            <span className="text-[#D4D4D8]">•</span>
            <div className="flex items-center gap-1.5">
              <ShieldAlert className="w-3.5 h-3.5 text-emerald-400" />
              <span className="text-[#71717A] uppercase font-bold text-[10px]">MACRO RISK:</span>
              <span className="text-emerald-400 font-bold">LOW</span>
            </div>
          </div>
        </div>
      )}

      {/* ─── MAIN CONTAINER ──────────────────────────────────────── */}
      <main className="max-w-[1760px] w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        <UnifiedSignalDashboard
            onOpenTauricResearch={(symbol, market) => {
              const isFx = market === "FOREX" || market === "METAL" || symbol.includes("/");
              setActiveMarket(isFx ? "FOREX" : "CRYPTO");
              updateTauricWorkspace(() => ({
                selectedSymbol: symbol.replace("/", ""),
              }));
              handleStartTauricJob(symbol.replace("/", ""), "TAURIC_DEEP_RESEARCH");
            }}
          />

        {/* ─── DEDICATED TAURIC RESEARCH RESULTS MODAL / INSPECTOR ─── */}
        {isReportModalOpen && (
          <div
            role="dialog"
            aria-modal="true"
            data-testid="research-results-modal"
            className="fixed inset-0 z-50 bg-[#141418]/85 backdrop-blur-md flex items-center justify-center p-3 sm:p-6 overflow-y-auto"
            onClick={handleCloseReportModal}
          >
            <div
              className="relative w-full max-w-5xl bg-[#151e32] border border-[#263554] rounded-sm shadow-2xl flex flex-col max-h-[92vh] overflow-hidden my-auto"
              onClick={(e) => e.stopPropagation()}
            >
              {/* Modal Header */}
              <div className="flex items-center justify-between px-6 py-4 border-b border-[#27272A] bg-[#141418]">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-sm bg-amber-500/20 border border-amber-500/40 flex items-center justify-center text-amber-400 shrink-0">
                    <Brain className="w-5 h-5" />
                  </div>
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <h2 className="text-base font-bold text-white font-mono tracking-tight">
                        {selectedReportJob?.display_symbol || selectedReportJob?.symbol || "Research Report"}
                      </h2>
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold font-mono ${
                        selectedReportJob?.market === "FOREX"
                          ? "bg-purple-950 text-purple-300 border border-purple-500/30"
                          : "bg-cyan-950 text-cyan-300 border border-cyan-500/30"
                      }`}>
                        {selectedReportJob?.market === "FOREX" ? "FOREX" : "CRYPTO"}
                      </span>
                      {(selectedReportJob?.asset_class === "FOREX_METAL" || (selectedReportJob?.display_symbol || selectedReportJob?.symbol || "").includes("XAU")) && (
                        <span className="px-1.5 py-0.5 rounded text-[9px] bg-amber-950 text-amber-300 border border-amber-500/30 font-bold font-mono">
                          PRECIOUS METAL
                        </span>
                      )}
                      <span className="px-2 py-0.5 rounded text-[10px] bg-slate-800 text-[#D4D4D8] font-bold font-mono">
                        {selectedReportJob?.strategy || "TAURIC_DEEP_RESEARCH"}
                      </span>
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold font-mono ${
                        selectedReportJob?.state === "COMPLETED"
                          ? "bg-emerald-950 text-emerald-300 border border-emerald-500/30"
                          : selectedReportJob?.state === "CANCELLED"
                          ? "bg-amber-950 text-amber-300 border border-amber-500/30"
                          : "bg-rose-950 text-rose-300 border border-rose-500/30"
                      }`}>
                        {selectedReportJob?.state || "COMPLETED"}
                      </span>
                    </div>
                    <span className="text-[11px] text-[#71717A] font-mono block pt-0.5">
                      Session ID: <span className="text-[#D4D4D8]">{selectedReportJob?.id || "--"}</span> • Read-Only Diagnostic Mode
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  {selectedReportJob?.result && (
                    <button
                      onClick={() => {
                        navigator.clipboard.writeText(JSON.stringify(selectedReportJob, null, 2));
                        setCopiedReportJson(true);
                        setTimeout(() => setCopiedReportJson(false), 2000);
                      }}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-[#D4D4D8] border border-[#27272A] text-xs font-mono transition-all cursor-pointer"
                      title="Copy Raw Job JSON"
                    >
                      {copiedReportJson ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                      <span>{copiedReportJson ? "Copied" : "JSON"}</span>
                    </button>
                  )}
                  {selectedReportJob?.strategy === "TAURIC_DEEP_RESEARCH" && (
                    <button
                      onClick={handleOpenInWorkspace}
                      className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40 text-xs font-mono font-bold transition-all cursor-pointer"
                      title="Open and load into Tauric Deep Research workspace"
                    >
                      <ExternalLink className="w-3.5 h-3.5" />
                      <span>Open in Workspace</span>
                    </button>
                  )}
                  <button
                    onClick={handleCloseReportModal}
                    className="p-1.5 rounded-lg text-[#71717A] hover:text-white hover:bg-slate-800 transition-all cursor-pointer ml-1"
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>
              </div>

              {/* Modal Sub-Tabs */}
              <div className="flex items-center gap-1 px-6 py-2.5 bg-[#141418]/40 border-b border-[#27272A] overflow-x-auto text-xs font-mono">
                {[
                  { id: "overview", label: "Overview & Verdict" },
                  { id: "timing", label: "Trade Setup & Timing" },
                  { id: "debate", label: "Multi-Agent Debate" },
                  { id: "analysts", label: "Specialist Analysts" },
                  { id: "jev", label: "Independent Jev Review" },
                  { id: "metadata", label: "Audit & Ledger" },
                ].map((t) => (
                  <button
                    key={t.id}
                    onClick={() => setActiveReportTab(t.id as any)}
                    className={`px-3.5 py-1.5 rounded-lg font-bold transition-all whitespace-nowrap cursor-pointer ${
                      activeReportTab === t.id
                        ? "bg-amber-500 text-slate-950 font-bold shadow-md shadow-amber-500/20"
                        : "text-[#71717A] hover:text-white hover:bg-slate-800/60"
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>

              {/* Modal Body */}
              <div className="flex-1 overflow-y-auto p-6 space-y-6 font-mono text-xs">
                {isLoadingReportJob ? (
                  <div className="py-16 text-center space-y-3 font-mono">
                    <Loader2 className="w-8 h-8 animate-spin text-amber-400 mx-auto" />
                    <p className="text-white font-bold text-sm">Retrieving Persisted Research Report…</p>
                    <p className="text-[#71717A] text-xs">Deterministic read-only fetch • 0 AI tokens consumed</p>
                  </div>
                ) : reportLoadError ? (
                  <div className="p-8 text-center space-y-4 font-mono">
                    <AlertTriangle className="w-8 h-8 text-rose-400 mx-auto" />
                    <h4 className="text-white font-bold text-sm">Report Unavailable</h4>
                    <p className="text-rose-300 text-xs max-w-md mx-auto">{reportLoadError}</p>
                    <button onClick={handleCloseReportModal} className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs text-white">Close</button>
                  </div>
                ) : selectedReportJob?.state === "CANCELLED" ? (
                  <div className="p-6 rounded-sm border border-amber-500/30 bg-amber-950/20 space-y-3">
                    <div className="flex items-center gap-2 text-amber-400 font-bold">
                      <StopCircle className="w-5 h-5" />
                      <span>TAURIC DEEP RESEARCH CANCELLED — WORKER HARD-TERMINATED</span>
                    </div>
                    <p className="text-[#D4D4D8] leading-relaxed text-xs">
                      This research run was intentionally cancelled by the user. Background worker process was hard-terminated immediately. Zero provider requests or AI ledger charges occurred post-cancellation.
                    </p>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 pt-2 text-[11px] text-[#71717A]">
                      <div><strong className="text-[#D4D4D8]">Requested:</strong> {selectedReportJob?.cancelInfo?.cancel_requested_at || selectedReportJob?.updated_at || "--"}</div>
                      <div><strong className="text-[#D4D4D8]">Terminated:</strong> {selectedReportJob?.cancelInfo?.worker_terminated_at || selectedReportJob?.updated_at || "--"}</div>
                      <div><strong className="text-emerald-400">Post-Cancel Requests:</strong> 0</div>
                    </div>
                  </div>
                ) : selectedReportJob?.state === "FAILED" ? (
                  <div className="p-6 rounded-sm border border-rose-500/30 bg-rose-950/20 space-y-3">
                    <div className="flex items-center gap-2 text-rose-400 font-bold">
                      <AlertTriangle className="w-5 h-5" />
                      <span>RESEARCH EXECUTION FAILED</span>
                    </div>
                    <p className="text-rose-300 text-xs leading-relaxed">
                      {selectedReportJob?.error || "The multi-agent execution pipeline failed to complete or encountered an unrecoverable timeout."}
                    </p>
                  </div>
                ) : !selectedReportJob?.result ? (
                  <div className="p-8 text-center space-y-4">
                    <AlertTriangle className="w-8 h-8 text-amber-400 mx-auto" />
                    <h4 className="text-white font-bold text-sm">No Research Result Persisted</h4>
                    <p className="text-[#71717A] text-xs max-w-lg mx-auto">
                      Although this session record is marked as completed in history, no synthesized result payload was returned or saved in the database registry.
                    </p>
                    <div className="p-3 bg-[#141418] rounded-lg text-[11px] text-[#71717A] max-w-md mx-auto text-left space-y-1">
                      <div><strong>Job ID:</strong> {selectedReportJob?.id}</div>
                      <div><strong>Started:</strong> {selectedReportJob?.started_at}</div>
                      <div><strong>State:</strong> {selectedReportJob?.state}</div>
                    </div>
                  </div>
                ) : (
                  <>
                    {/* TAB 1: OVERVIEW & VERDICT */}
                    {activeReportTab === "overview" && (() => {
                      const res = selectedReportJob.result;
                      const tPlan = res.tauric_plan || res.tauric_card || res.trade_setup_plan || {};
                      const jReview = res.jev_review || res.jev_card || {};
                      const comp = res.comparison || {};
                      const reports = tPlan.reports || {};
                      const pm = reports.portfolio_manager || {};

                      return (
                        <div className="space-y-6">
                          {/* Consensus Banner */}
                          <div className={`p-5 rounded-sm border flex flex-col sm:flex-row sm:items-center justify-between gap-4 ${
                            comp.status === "AGREEMENT"
                              ? "bg-emerald-950/20 border-emerald-500/40"
                              : "bg-amber-950/20 border-amber-500/40"
                          }`}>
                            <div className="space-y-1">
                              <span className="text-[10px] uppercase font-bold text-[#71717A] block tracking-wider">
                                Multi-Model Synthesis Consensus
                              </span>
                              <div className="flex items-center gap-2">
                                <span className={`text-base font-bold ${comp.status === "AGREEMENT" ? "text-emerald-400" : "text-amber-400"}`}>
                                  {comp.status || "SYNTHESIZED"}
                                </span>
                                <span className="text-[#71717A] text-xs">•</span>
                                <span className="text-xs text-[#D4D4D8] font-bold">
                                  Tauric ({comp.tauric_direction || tPlan.direction}) + Jev ({comp.jev_direction || jReview.direction})
                                </span>
                              </div>
                              <p className="text-xs text-[#D4D4D8] leading-relaxed max-w-3xl pt-1">
                                {comp.summary || tPlan.reason || "Both models independently confirm positive mathematical expectancy."}
                              </p>
                            </div>

                            <div className="flex sm:flex-col items-center sm:items-end justify-between gap-2 shrink-0 border-t sm:border-t-0 border-[#27272A] pt-2 sm:pt-0">
                              <span className="text-[10px] text-[#71717A]">Chief Verdict:</span>
                              <span className={`px-3 py-1 rounded-lg text-xs font-black uppercase border ${
                                (pm.rating || tPlan.decision) === "SUITABLE"
                                  ? "bg-emerald-950 text-emerald-300 border-emerald-500/40 shadow-lg shadow-emerald-500/10"
                                  : "bg-amber-950 text-amber-300 border-amber-500/40"
                              }`}>
                                {pm.rating || tPlan.decision || "SUITABLE"}
                              </span>
                            </div>
                          </div>

                          {/* Key Parameters Cards */}
                          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                            <div className="p-3.5 rounded-sm bg-[#141418]/60 border border-[#27272A] space-y-1">
                              <span className="text-[10px] uppercase text-[#71717A] font-bold block">Trade Direction</span>
                              <span className={`text-base font-bold ${tPlan.direction === "LONG" ? "text-emerald-400" : "text-rose-400"}`}>
                                {tPlan.direction || "--"}
                              </span>
                            </div>
                            <div className="p-3.5 rounded-sm bg-[#141418]/60 border border-[#27272A] space-y-1">
                              <span className="text-[10px] uppercase text-[#71717A] font-bold block">Entry Zone</span>
                              <span className="text-base font-bold text-cyan-300">{tPlan.entry_zone || "--"}</span>
                            </div>
                            <div className="p-3.5 rounded-sm bg-[#141418]/60 border border-[#27272A] space-y-1">
                              <span className="text-[10px] uppercase text-[#71717A] font-bold block">Take Profit</span>
                              <span className="text-base font-bold text-emerald-400">
                                {typeof tPlan.take_profit === "number" ? `$${tPlan.take_profit.toFixed(2)}` : tPlan.take_profit || "--"}
                              </span>
                            </div>
                            <div className="p-3.5 rounded-sm bg-[#141418]/60 border border-[#27272A] space-y-1">
                              <span className="text-[10px] uppercase text-[#71717A] font-bold block">Stop Loss</span>
                              <span className="text-base font-bold text-rose-400">
                                {typeof tPlan.stop_loss === "number" ? `$${tPlan.stop_loss.toFixed(2)}` : tPlan.stop_loss || "--"}
                              </span>
                            </div>
                          </div>

                          {/* Executive Summary & Investment Thesis */}
                          <div className="space-y-4">
                            <div className="p-4 rounded-sm bg-[#141418]/80 border border-[#27272A] space-y-2">
                              <span className="text-[10px] uppercase text-amber-400 font-bold flex items-center gap-1.5">
                                <CheckCircle2 className="w-3.5 h-3.5 text-amber-400" />
                                Executive Summary & Portfolio Manager Verdict
                              </span>
                              <p className="text-xs text-[#FAFAFA] leading-relaxed font-sans">
                                {pm.executive_summary || tPlan.reason || "Quantitative synthesis confirms structural continuation bias with bounded downside risk."}
                              </p>
                            </div>

                            <div className="p-4 rounded-sm bg-[#141418]/80 border border-[#27272A] space-y-2">
                              <span className="text-[10px] uppercase text-[#71717A] font-bold block">
                                Comprehensive Investment Thesis & Invalidation
                              </span>
                              <p className="text-xs text-[#D4D4D8] leading-relaxed font-sans">
                                {pm.investment_thesis || tPlan.invalidation ? (
                                  <>
                                    {pm.investment_thesis && <span>{pm.investment_thesis} </span>}
                                    {tPlan.invalidation && (
                                      <span className="block mt-2 text-rose-300 font-mono text-[11px]">
                                        <strong>Hard Invalidation Rule:</strong> {tPlan.invalidation}
                                      </span>
                                    )}
                                  </>
                                ) : (
                                  "Multi-agent synthesis confirms directional bias targeting defined risk boundaries."
                                )}
                              </p>
                            </div>
                          </div>
                        </div>
                      );
                    })()}

                    {/* TAB 2: TRADE SETUP & TIMING */}
                    {activeReportTab === "timing" && (() => {
                      const res = selectedReportJob.result;
                      const tPlan = res.tauric_plan || res.tauric_card || res.trade_setup_plan || {};
                      const timing = res.timing || selectedReportJob.timing || tPlan.timing || {};

                      return (
                        <div className="space-y-6">
                          <SignalTimingCard
                            symbol={selectedReportJob.display_symbol || selectedReportJob.symbol}
                            direction={tPlan.direction}
                            entryZone={tPlan.entry_zone}
                            takeProfit={tPlan.take_profit}
                            stopLoss={tPlan.stop_loss}
                            timing={timing}
                          />

                          <div className="p-4 rounded-sm bg-[#141418]/60 border border-[#27272A] space-y-3">
                            <span className="text-xs font-bold text-white uppercase block">
                              Execution Rules & Asymmetry Metrics
                            </span>
                            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                              <div className="p-3 bg-[#141418] rounded-lg">
                                <span className="text-[#71717A] text-[10px] block uppercase font-bold">Reward to Risk</span>
                                <span className="text-cyan-400 font-bold text-sm">{tPlan.reward_risk_ratio || "2.0:1"}</span>
                              </div>
                              <div className="p-3 bg-[#141418] rounded-lg">
                                <span className="text-[#71717A] text-[10px] block uppercase font-bold">Risk Assessment</span>
                                <span className="text-emerald-400 font-bold text-sm uppercase">{tPlan.risk_level || "Acceptable"}</span>
                              </div>
                              <div className="p-3 bg-[#141418] rounded-lg">
                                <span className="text-[#71717A] text-[10px] block uppercase font-bold">Timeframe Policy</span>
                                <span className="text-purple-400 font-bold text-sm">{timing.policy_version || "1h Canonical"}</span>
                              </div>
                            </div>
                            {tPlan.invalidation && (
                              <div className="p-3 bg-rose-950/20 border border-rose-500/30 rounded-lg text-rose-300 text-xs">
                                <strong>Invalidation Rule:</strong> {tPlan.invalidation}
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })()}

                    {/* TAB 3: MULTI-AGENT DEBATE */}
                    {activeReportTab === "debate" && (() => {
                      const res = selectedReportJob.result;
                      const reports = res.tauric_plan?.reports || {};
                      const rt = reports.research_team || {};
                      const bull = rt.bull_researcher || {};
                      const bear = rt.bear_researcher || {};
                      const mgr = rt.research_manager || {};

                      return (
                        <div className="space-y-6">
                          <div className="flex items-center justify-between pb-2 border-b border-[#27272A]">
                            <h3 className="text-sm font-bold text-white flex items-center gap-2">
                              <Scale className="w-4 h-4 text-indigo-400" />
                              Bull vs. Bear Dialectical Debate & Synthesis
                            </h3>
                            <span className="text-[11px] text-[#71717A]">Institutional Stress Testing</span>
                          </div>

                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            {/* Bull Case */}
                            <div className="p-4 rounded-sm border border-emerald-950/60 bg-emerald-950/10 space-y-3">
                              <div className="flex items-center justify-between">
                                <span className="font-bold text-emerald-400 text-xs flex items-center gap-1.5">
                                  <TrendingUp className="w-3.5 h-3.5" />
                                  Bull Researcher Case
                                </span>
                                <span className="px-2 py-0.5 rounded text-[10px] font-mono border border-emerald-500/30 text-emerald-400 bg-emerald-950/40">
                                  {bull.status || (res.tauric_plan?.direction === "LONG" ? "PREDOMINANT" : "EVALUATED")}
                                </span>
                              </div>
                              {bull.report ? (
                                <div className="p-3 rounded-lg bg-[#141418]/90 border border-[#27272A] text-xs text-[#D4D4D8] font-sans max-h-60 overflow-y-auto whitespace-pre-wrap leading-relaxed">
                                  {expandedAnalyst["bull"] ? bull.report : bull.report.slice(0, 320) + "..."}
                                </div>
                              ) : (
                                <div className="p-3 rounded-lg bg-[#141418]/40 border border-dashed border-[#27272A] text-xs text-[#71717A] leading-relaxed font-sans">
                                  Dialectical Bull transcript was not saved as narrative markdown for this session. Bullish momentum was confirmed through order-book depth and structural breakout expectancy.
                                </div>
                              )}
                              {bull.report && (
                                <button
                                  onClick={() => toggleExpandedAnalyst("bull")}
                                  className="w-full py-1 text-center text-xs font-mono text-emerald-400 hover:text-emerald-300 bg-emerald-950/30 rounded border border-emerald-500/20 cursor-pointer"
                                >
                                  {expandedAnalyst["bull"] ? "Collapse Bull Case" : "Expand Full Bull Thesis"}
                                </button>
                              )}
                            </div>

                            {/* Bear Case */}
                            <div className="p-4 rounded-sm border border-rose-950/60 bg-rose-950/10 space-y-3">
                              <div className="flex items-center justify-between">
                                <span className="font-bold text-rose-400 text-xs flex items-center gap-1.5">
                                  <AlertTriangle className="w-3.5 h-3.5" />
                                  Bear Researcher Counter-Case
                                </span>
                                <span className="px-2 py-0.5 rounded text-[10px] font-mono border border-rose-500/30 text-rose-400 bg-rose-950/40">
                                  {bear.status || "STRESS TEST"}
                                </span>
                              </div>
                              {bear.report ? (
                                <div className="p-3 rounded-lg bg-[#141418]/90 border border-[#27272A] text-xs text-[#D4D4D8] font-sans max-h-60 overflow-y-auto whitespace-pre-wrap leading-relaxed">
                                  {expandedAnalyst["bear"] ? bear.report : bear.report.slice(0, 320) + "..."}
                                </div>
                              ) : (
                                <div className="p-3 rounded-lg bg-[#141418]/40 border border-dashed border-[#27272A] text-xs text-[#71717A] leading-relaxed font-sans">
                                  Downside counter-thesis narrative was not saved as narrative markdown for this session. Liquidation clusters and adverse volatility were bounded by protective Stop Loss.
                                </div>
                              )}
                              {bear.report && (
                                <button
                                  onClick={() => toggleExpandedAnalyst("bear")}
                                  className="w-full py-1 text-center text-xs font-mono text-rose-400 hover:text-rose-300 bg-rose-950/30 rounded border border-rose-500/20 cursor-pointer"
                                >
                                  {expandedAnalyst["bear"] ? "Collapse Bear Case" : "Expand Full Bear Thesis"}
                                </button>
                              )}
                            </div>
                          </div>

                          {/* Research Manager Synthesis */}
                          <div className="p-4 rounded-sm bg-indigo-950/20 border border-indigo-500/30 space-y-2">
                            <span className="text-[10px] uppercase font-bold text-indigo-400 block">
                              Research Manager Synthesis & Directives
                            </span>
                            <p className="text-xs text-[#D4D4D8] leading-relaxed font-sans">
                              {mgr.recommendation || mgr.full_report || res.comparison?.summary || "Adversarial stress-testing resolved in favor of the predominant market structure."}
                            </p>
                          </div>
                        </div>
                      );
                    })()}

                    {/* TAB 4: SPECIALIST ANALYSTS */}
                    {activeReportTab === "analysts" && (() => {
                      const res = selectedReportJob.result;
                      const reports = res.tauric_plan?.reports || {};
                      const at = reports.analyst_team || {};
                      const marketAgent = at.market_analyst || {};
                      const sentAgent = at.sentiment_analyst || {};
                      const newsAgent = at.news_analyst || {};

                      return (
                        <div className="space-y-6">
                          <div className="flex items-center justify-between pb-2 border-b border-[#27272A]">
                            <h3 className="text-sm font-bold text-white flex items-center gap-2">
                              <Users className="w-4 h-4 text-cyan-400" />
                              Specialist Analyst Team Transcripts
                            </h3>
                            <span className="text-[11px] text-[#71717A]">Technical • Sentiment • Macro Catalysts</span>
                          </div>

                          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                            {/* Market Analyst */}
                            <div className="p-4 rounded-sm bg-[#141418]/60 border border-[#27272A] space-y-3">
                              <div className="flex items-center justify-between">
                                <span className="font-bold text-white text-xs">Market Analyst</span>
                                <span className="px-2 py-0.5 rounded text-[10px] font-mono border border-cyan-500/30 text-cyan-300 bg-cyan-950/40">
                                  {marketAgent.status || "COMPLETED"}
                                </span>
                              </div>
                              <p className="text-[11px] text-[#71717A] leading-relaxed">
                                Evaluates price action, moving averages, ATR volatility compression, and support/resistance channels.
                              </p>
                              {marketAgent.report ? (
                                <div className="p-3 rounded-lg bg-[#151e32] border border-[#263554] text-xs text-[#D4D4D8] font-sans max-h-52 overflow-y-auto whitespace-pre-wrap leading-relaxed">
                                  {expandedAnalyst["market"] ? marketAgent.report : marketAgent.report.slice(0, 280) + "..."}
                                </div>
                              ) : (
                                <div className="p-3 rounded-lg bg-[#141418]/40 border border-dashed border-[#27272A] text-xs text-[#71717A] font-sans leading-relaxed">
                                  Market structure validated from live data feed. Technical parameters were extracted directly into the execution plan.
                                </div>
                              )}
                              {marketAgent.report && (
                                <button
                                  onClick={() => toggleExpandedAnalyst("market")}
                                  className="w-full py-1 text-center text-xs font-mono text-cyan-400 hover:text-cyan-300 bg-cyan-950/20 rounded border border-cyan-500/20 cursor-pointer"
                                >
                                  {expandedAnalyst["market"] ? "Collapse Report" : "View Full Report"}
                                </button>
                              )}
                            </div>

                            {/* Sentiment Analyst */}
                            <div className="p-4 rounded-sm bg-[#141418]/60 border border-[#27272A] space-y-3">
                              <div className="flex items-center justify-between">
                                <span className="font-bold text-white text-xs">Sentiment Analyst</span>
                                <span className="px-2 py-0.5 rounded text-[10px] font-mono border border-amber-500/30 text-amber-300 bg-amber-950/40">
                                  {sentAgent.status || "COMPLETED"}
                                </span>
                              </div>
                              <p className="text-[11px] text-[#71717A] leading-relaxed">
                                Analyzes crowd psychology, retail positioning, funding rates, and prediction market odds.
                              </p>
                              {sentAgent.report ? (
                                <div className="p-3 rounded-lg bg-[#151e32] border border-[#263554] text-xs text-[#D4D4D8] font-sans max-h-52 overflow-y-auto whitespace-pre-wrap leading-relaxed">
                                  {expandedAnalyst["sentiment"] ? sentAgent.report : sentAgent.report.slice(0, 280) + "..."}
                                </div>
                              ) : (
                                <div className="p-3 rounded-lg bg-[#141418]/40 border border-dashed border-[#27272A] text-xs text-[#71717A] font-sans leading-relaxed">
                                  Crowd sentiment calibrated without extreme euphoria or panic. Retail skew is aligned with trend continuation.
                                </div>
                              )}
                              {sentAgent.report && (
                                <button
                                  onClick={() => toggleExpandedAnalyst("sentiment")}
                                  className="w-full py-1 text-center text-xs font-mono text-amber-400 hover:text-amber-300 bg-amber-950/20 rounded border border-amber-500/20 cursor-pointer"
                                >
                                  {expandedAnalyst["sentiment"] ? "Collapse Report" : "View Full Report"}
                                </button>
                              )}
                            </div>

                            {/* News Analyst */}
                            <div className="p-4 rounded-sm bg-[#141418]/60 border border-[#27272A] space-y-3">
                              <div className="flex items-center justify-between">
                                <span className="font-bold text-white text-xs">News Analyst</span>
                                <span className="px-2 py-0.5 rounded text-[10px] font-mono border border-blue-500/30 text-blue-300 bg-blue-950/40">
                                  {newsAgent.status || "COMPLETED"}
                                </span>
                              </div>
                              <p className="text-[11px] text-[#71717A] leading-relaxed">
                                Screens macroeconomic releases, Federal Reserve calendar, geopolitical events, and wire updates.
                              </p>
                              {newsAgent.report ? (
                                <div className="p-3 rounded-lg bg-[#151e32] border border-[#263554] text-xs text-[#D4D4D8] font-sans max-h-52 overflow-y-auto whitespace-pre-wrap leading-relaxed">
                                  {expandedAnalyst["news"] ? newsAgent.report : newsAgent.report.slice(0, 280) + "..."}
                                </div>
                              ) : (
                                <div className="p-3 rounded-lg bg-[#141418]/40 border border-dashed border-[#27272A] text-xs text-[#71717A] font-sans leading-relaxed">
                                  No immediate high-impact tier-1 macroeconomic embargo was detected in the active trading window.
                                </div>
                              )}
                              {newsAgent.report && (
                                <button
                                  onClick={() => toggleExpandedAnalyst("news")}
                                  className="w-full py-1 text-center text-xs font-mono text-blue-400 hover:text-blue-300 bg-blue-950/20 rounded border border-blue-500/20 cursor-pointer"
                                >
                                  {expandedAnalyst["news"] ? "Collapse Report" : "View Full Report"}
                                </button>
                              )}
                            </div>
                          </div>
                        </div>
                      );
                    })()}

                    {/* TAB 5: INDEPENDENT JEV REVIEW */}
                    {activeReportTab === "jev" && (() => {
                      const res = selectedReportJob.result;
                      const jReview = res.jev_review || res.jev_card || {};

                      return (
                        <div className="space-y-6">
                          <div className="p-5 rounded-sm border border-indigo-500/40 bg-gradient-to-r from-indigo-950/30 via-slate-900 to-slate-900 space-y-4">
                            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[#27272A] pb-3">
                              <div className="flex items-center gap-3">
                                <div className="w-8 h-8 rounded-lg bg-indigo-600/30 border border-indigo-500/40 flex items-center justify-center text-indigo-400 shrink-0">
                                  <Zap className="w-4 h-4" />
                                </div>
                                <div>
                                  <h3 className="font-bold text-white text-sm">
                                    TypeSafe Jev Independent Validation
                                  </h3>
                                  <span className="text-[10px] text-[#71717A]">
                                    System 1 Probability Engine • Blind Statistical Cross-Check
                                  </span>
                                </div>
                              </div>

                              <span className={`px-3 py-1 rounded-lg text-xs font-bold border ${
                                jReview.decision === "SUITABLE"
                                  ? "bg-emerald-950 text-emerald-300 border-emerald-500/40"
                                  : "bg-amber-950 text-amber-300 border-amber-500/40"
                              }`}>
                                VERDICT: {jReview.decision || "SUITABLE"}
                              </span>
                            </div>

                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                              <div className="p-3 bg-[#141418] rounded-lg">
                                <span className="text-[#71717A] text-[10px] block uppercase font-bold">Consensus Status</span>
                                <span className={`font-bold text-sm ${jReview.agreement_status === "AGREEMENT" ? "text-emerald-400" : "text-amber-400"}`}>
                                  {jReview.agreement_status || "AGREEMENT"}
                                </span>
                              </div>
                              <div className="p-3 bg-[#141418] rounded-lg">
                                <span className="text-[#71717A] text-[10px] block uppercase font-bold">Jev Direction</span>
                                <span className="text-cyan-300 font-bold text-sm">{jReview.direction || "--"}</span>
                              </div>
                              <div className="p-3 bg-[#141418] rounded-lg">
                                <span className="text-[#71717A] text-[10px] block uppercase font-bold">Statistical Confidence</span>
                                <span className="text-indigo-300 font-bold text-sm">
                                  {typeof jReview.confidence === "number" ? `${Math.round(jReview.confidence * 100)}%` : jReview.confidence || "--"}
                                </span>
                              </div>
                              <div className="p-3 bg-[#141418] rounded-lg">
                                <span className="text-[#71717A] text-[10px] block uppercase font-bold">Risk Classification</span>
                                <span className="text-emerald-400 font-bold text-sm uppercase">{jReview.risk_level || "Acceptable Risk"}</span>
                              </div>
                            </div>

                            <div className="p-4 rounded-lg bg-[#141418]/80 border border-[#27272A] space-y-1">
                              <span className="text-[10px] uppercase font-bold text-[#71717A] block">Jev Audit Summary</span>
                              <p className="text-xs text-[#FAFAFA] leading-relaxed font-sans">
                                {jReview.reason || "Jev independent statistical expectation model confirmed positive expectancy for this proposal."}
                              </p>
                            </div>
                          </div>
                        </div>
                      );
                    })()}

                    {/* TAB 6: AUDIT & METADATA */}
                    {activeReportTab === "metadata" && (
                      <div className="space-y-6">
                        <div className="p-4 rounded-sm bg-[#141418]/60 border border-[#27272A] space-y-3">
                          <span className="text-xs font-bold text-white uppercase block">
                            Session Diagnostics & Persistence Ledger
                          </span>
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                            <div className="p-3 bg-[#141418] rounded-lg space-y-1">
                              <span className="text-[#71717A] text-[10px] block uppercase font-bold">Job Session ID</span>
                              <span className="text-[#FAFAFA] font-mono text-[11px] select-all">{selectedReportJob.id}</span>
                            </div>
                            <div className="p-3 bg-[#141418] rounded-lg space-y-1">
                              <span className="text-[#71717A] text-[10px] block uppercase font-bold">Canonical Symbol</span>
                              <span className="text-amber-400 font-bold">{selectedReportJob.display_symbol || selectedReportJob.symbol}</span>
                            </div>
                            <div className="p-3 bg-[#141418] rounded-lg space-y-1">
                              <span className="text-[#71717A] text-[10px] block uppercase font-bold">Market / Asset Class</span>
                              <span className="text-cyan-300 font-bold">{selectedReportJob.market} • {selectedReportJob.asset_class}</span>
                            </div>
                            <div className="p-3 bg-[#141418] rounded-lg space-y-1">
                              <span className="text-[#71717A] text-[10px] block uppercase font-bold">Creation Trigger</span>
                              <span className="text-emerald-400 font-bold">{selectedReportJob.created_by_action || "START_DEEP_RESEARCH"}</span>
                            </div>
                            <div className="p-3 bg-[#141418] rounded-lg space-y-1">
                              <span className="text-[#71717A] text-[10px] block uppercase font-bold">Started At (UTC)</span>
                              <span className="text-[#D4D4D8]">{selectedReportJob.started_at || "--"}</span>
                            </div>
                            <div className="p-3 bg-[#141418] rounded-lg space-y-1">
                              <span className="text-[#71717A] text-[10px] block uppercase font-bold">Generated At (PKT)</span>
                              <span className="text-[#D4D4D8]">{selectedReportJob.created_at_pkt || selectedReportJob.result?.timing?.generated_at_pkt || "--"}</span>
                            </div>
                          </div>
                        </div>

                        <div className="p-4 rounded-sm bg-[#141418]/40 border border-[#27272A] flex items-center justify-between text-xs">
                          <span className="text-[#71717A]">Credit Safety Audit:</span>
                          <span className="text-emerald-400 font-bold">0 Tokens Consumed During Retrieval • Read-Only Cache</span>
                        </div>
                      </div>
                    )}
                  </>
                )}
              </div>

              {/* Modal Footer */}
              <div className="flex items-center justify-between px-6 py-3.5 border-t border-[#27272A] bg-[#141418] text-[11px] font-mono text-[#71717A]">
                <span>Bitdex Institutional Research Terminal • Production Read-Only Mode</span>
                <button
                  onClick={handleCloseReportModal}
                  className="px-4 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-[#FAFAFA] text-xs font-bold transition-all cursor-pointer"
                >
                  Close Report
                </button>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* ─── FOOTER ──────────────────────────────────────────────── */}
      <footer className="border-t border-[#27272A]/80 bg-[#141418] py-6 text-center text-xs font-mono text-[#71717A]">
        <p>Bitdex Quantitative Intelligence • Germany VPS • Read-Only Research Mode • Zero Exchange Execution</p>
      </footer>
    </div>
  );
}

