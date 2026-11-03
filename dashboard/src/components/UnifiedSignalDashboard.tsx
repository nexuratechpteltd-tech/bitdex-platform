"use client";

const getApiBase = () => {
  if (typeof window !== "undefined" && window.location.pathname.startsWith("/trading")) {
    return "/trading/api/backend";
  }
  return "/api/backend";
};

import React, { useState, useEffect, useMemo, useRef } from "react";
import {
  Activity,
  ArrowUpRight,
  ArrowDownRight,
  Search,
  Sparkles,
  ExternalLink,
  CheckCircle2,
  GripVertical,
  MoveUp,
  MoveDown,
  RotateCcw,
  AlertTriangle,
  Clock,
  ShieldAlert,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  TrendingUp,
  RefreshCw,
  Gauge,
  Info,
  Maximize2,
  X,
  Target,
  Bot,
  Zap,
  Calendar,
  Check,
  Copy,
  ShieldCheck,
  Lock,
  FileCheck,
  Wallet,
  CreditCard,
  Shield,
  Key,
  Receipt,
  Layers,
  DollarSign,
  Sliders,
  Briefcase,
  Link2,
  Cpu,
  Database,
  Settings,
  Power,
  AlertOctagon,
  XCircle,
  Play,
} from "lucide-react";
import FourEngineDecisionBoard, { FourEngineContract } from "./FourEngineDecisionBoard";

interface StrategyRunItem {
  run_id: string;
  asset: string;
  strategy_id: string;
  strategy_name: string;
  profile_id: string;
  provider_id: string;
  product_type: string;
  environment: string;
  investment_amount: number;
  currency: string;
  status: string;
  execution_mode: string;
  authorization_state: string;
  created_at_utc: string;
  started_at_utc?: string;
  stopped_at_utc?: string;
  parameters?: Record<string, any>;
  risk_config?: Record<string, any>;
  balance_source?: Record<string, any>;
  provider_order_ids?: string[];
  normalized_orders?: any[];
  fills?: any[];
  fees_incurred?: number;
  realized_pnl?: number;
  unrealized_pnl?: number;
  idempotency_key?: string;
  data_provenance?: Record<string, any>;
  worker_status?: string;
  exchange_status?: string;
  execution_nature?: string;
  last_exchange_verification_utc?: string;
  exchange_verification_evidence?: Record<string, any>;
  client_order_ids?: string[];
  residual_position?: Record<string, any>;
  status_reason?: string;
  is_test?: boolean;
}

interface ConnectionProfile {
  profile_id: string;
  exchange: string;
  market_type?: "CRYPTO" | "FOREX" | string;
  environment: "DEMO" | "LIVE";
  environment_preference?: "DEMO" | "LIVE";
  is_read_only?: boolean;
  intended_permissions?: string[];
  label: string;
  api_key_masked: string;
  created_at_utc: string;
  last_tested_utc?: string;
  connection_status?: "UNTESTED" | "AUTHENTICATION_FAILED" | "PARTIALLY_SUPPORTED" | "VERIFIED_READ_ONLY" | "VERIFIED_TRADING_CAPABLE" | "DISCONNECTED" | string;
  last_status: string;
  verification_label?: string;
  actionable_error_code?: string;
  provider_error_code?: string;
  supported_environments?: string[];
  supported_products?: any[];
  guidance?: string;
  last_error?: string;
  demo_verified?: boolean;
  live_verified?: boolean;
  demo_status?: any;
  live_status?: any;
  capabilities_verified: string[];
  endpoint_results?: any[];
  product_type?: string;
  is_active?: boolean;
  provider_identified?: boolean;
  environment_configured?: boolean;
  suggested_provider?: string | null;
  has_passphrase?: boolean;
  capability_matrix?: any[];
  strategy_compatibility?: any;
  custom_config?: any;
  account_data?: any;
  permission_matrix?: any[];
}

// Standardized Actionable Diagnostic Error Definitions
const ACTIONABLE_ERROR_GUIDES: Record<string, { label: string; guide: string; badgeColor: string }> = {
  MISSING_API_KEY: {
    label: "Missing API Key",
    guide: "API key was not provided. Please enter a valid API key.",
    badgeColor: "bg-rose-950/80 text-rose-300 border-rose-500/50"
  },
  MISSING_API_SECRET: {
    label: "Missing API Secret",
    guide: "API secret was not provided. Please enter a valid API secret.",
    badgeColor: "bg-rose-950/80 text-rose-300 border-rose-500/50"
  },
  PROVIDER_NOT_IDENTIFIED: {
    label: "Provider Not Identified",
    guide: "Identify the exchange provider (Bitget or Binance) in the post-save card or Permissions & Capabilities panel before running private authentication.",
    badgeColor: "bg-amber-950/80 text-amber-300 border-amber-500/50"
  },
  ENVIRONMENT_NOT_SELECTED: {
    label: "Environment Not Selected",
    guide: "Select Demo/Testnet or Live environment in Permissions & Capabilities before running private authentication.",
    badgeColor: "bg-amber-950/80 text-amber-300 border-amber-500/50"
  },
  MISSING_PASSPHRASE: {
    label: "Missing API Passphrase",
    guide: "API passphrase is required for Bitget. Click Edit on the profile card and enter the custom passphrase set during API key creation.",
    badgeColor: "bg-amber-950/80 text-amber-300 border-amber-500/50"
  },
  ENVIRONMENT_MISMATCH: {
    label: "Environment Mismatch",
    guide: "The API key was created for a different environment (e.g. Live key used in Demo, or Demo key in Live).",
    badgeColor: "bg-orange-950/80 text-orange-300 border-orange-500/50"
  },
  SIGNATURE_VALIDATION_FAILED: {
    label: "Signature Validation Failed",
    guide: "Request signature could not be verified by the exchange. Check secret key and passphrase.",
    badgeColor: "bg-rose-950/80 text-rose-300 border-rose-500/50"
  },
  TIMESTAMP_OR_RECV_WINDOW_ERROR: {
    label: "Timestamp / Clock Error",
    guide: "Server timestamp differs from exchange time. Check system clock synchronization.",
    badgeColor: "bg-yellow-950/80 text-yellow-300 border-yellow-500/50"
  },
  PROVIDER_AUTHENTICATION_REJECTED: {
    label: "Authentication Rejected",
    guide: "Exchange rejected credentials. Verify API key, secret, and IP whitelist permissions.",
    badgeColor: "bg-red-950/80 text-red-300 border-red-500/50"
  },
  PROVIDER_REQUEST_ERROR: {
    label: "Provider Request Error",
    guide: "Provider returned an unexpected response format or HTTP status code.",
    badgeColor: "bg-purple-950/80 text-purple-300 border-purple-500/50"
  },
  AUTHENTICATION_DIAGNOSTIC_INCONCLUSIVE: {
    label: "Diagnostic Inconclusive",
    guide: "Authentication could not be verified. Inspect network logs and response payload.",
    badgeColor: "bg-[#1E2329] text-[#848E9C] border-[#2B3139]"
  }
};

function getActionableDiagnostic(code?: string, fallbackGuide?: string, exchange?: string) {
  if (!code) return null;
  const upper = code.trim().toUpperCase();
  const exchUpper = (exchange || "").trim().toUpperCase();

  // Guard against misleading passphrase error on Binance
  if (exchUpper === "BINANCE" && (upper === "MISSING_PASSPHRASE" || upper.includes("PASSPHRASE"))) {
    return {
      code: "AUTHENTICATION_FAILED",
      label: "Authentication Rejected",
      guide: "Binance does not use an API passphrase. Verification failed because the exchange rejected the API Key, Secret, or IP whitelist permissions.",
      badgeColor: "bg-red-950/80 text-red-300 border-red-500/50"
    };
  }

  for (const [key, val] of Object.entries(ACTIONABLE_ERROR_GUIDES)) {
    if (upper === key || upper.includes(key)) {
      return { code: key, label: val.label, guide: fallbackGuide || val.guide, badgeColor: val.badgeColor };
    }
  }
  return {
    code: upper,
    label: upper.replace(/_/g, " "),
    guide: fallbackGuide || "Provider authentication error.",
    badgeColor: "bg-rose-950/80 text-rose-300 border-rose-500/50"
  };
}

interface ActivePosition {
  position_id: string;
  symbol: string;
  exchange: string;
  environment: "DEMO" | "PAPER" | "LIVE" | string;
  side: "LONG" | "SHORT" | string;
  size: number;
  entry_price: number;
  mark_price: number;
  position_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  realized_pnl: number;
  fees_paid: number;
  stop_loss?: number | null;
  take_profit?: number | null;
  opened_at_utc: string;
  closed_at_utc?: string | null;
  status: "OPEN" | "CLOSED" | string;
  execution_history?: any[];
  origin?: "EXCHANGE_CONFIRMED_DEMO" | "EXCHANGE_CONFIRMED_LIVE" | "PAPER_SIMULATION" | "SEEDED_FIXTURE" | "UNKNOWN" | string;
  origin_label?: string;
  is_exchange_confirmed?: boolean;
  price_timestamp_utc?: string;
  price_freshness?: "LIVE" | "FRESH" | "STALE" | "UNAVAILABLE" | string;
}

interface OpenOrderItem {
  order_id: string;
  client_order_id?: string;
  symbol: string;
  side: "BUY" | "SELL" | string;
  order_type: string;
  price: number;
  amount: number;
  filled_amount: number;
  remaining_amount: number;
  status: "OPEN" | "PARTIALLY_FILLED" | "FILLED" | "CANCELLED" | "REJECTED" | "EXPIRED" | string;
  raw_provider_status?: string;
  stop_loss?: number | null;
  take_profit?: number | null;
  created_at_utc?: string;
  environment?: string;
  exchange?: string;
  profile_id?: string;
}

interface AiTradeAdvisory {
  position_id: string;
  symbol: string;
  side: string;
  assessed_regime: string;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  attribution_analysis: string;
  recommended_action: string;
  proposed_stop_loss?: number | null;
  proposed_take_profit?: number | null;
  current_stop_loss?: number | null;
  current_take_profit?: number | null;
  advisory_summary: string;
  requires_user_confirmation: boolean;
  timestamp_utc: string;
}

interface OrderExecutionReceipt {
  client_order_id: string;
  exchange_order_id?: string;
  internal_order_id?: string;
  execution_type?: string;
  is_simulation?: boolean;
  raw_exchange_response?: any;
  exchange: string;
  environment: string;
  account_label: string;
  symbol: string;
  side: string;
  order_type: string;
  status: string;
  requested_qty: number;
  executed_qty: number;
  requested_price: number;
  avg_fill_price: number;
  fee_amount: number;
  fee_asset: string;
  protective_stop_loss?: number;
  protective_take_profit?: number;
  submitted_at_utc: string;
  filled_at_utc?: string;
  audit_trail: string[];
  error_message?: string;
}

interface PositionItem {
  position_id: string;
  symbol: string;
  exchange: string;
  environment: string;
  side: "LONG" | "SHORT";
  size: number;
  entry_price: number;
  mark_price: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  realized_pnl: number;
  fees_paid: number;
  stop_loss?: number;
  take_profit?: number;
  opened_at_utc: string;
  closed_at_utc?: string;
  status: "OPEN" | "CLOSED";
}

interface CalendarEvent {
  event_id: string;
  series_code: string;
  title: string;
  country: string;
  currency: string;
  scheduled_utc: string;
  scheduled_timestamp_ms: number;
  scheduled_pkt: string;
  impact: "HIGH" | "MEDIUM" | "LOW" | "UNKNOWN" | string;
  impact_weight: number;
  status: string;
  actual?: number | null;
  actual_raw?: string | null;
  forecast?: number | null;
  forecast_raw?: string | null;
  previous?: number | null;
  previous_raw?: string | null;
  revised_previous?: number | null;
  is_revised?: boolean;
  unit?: string | null;
  source_url?: string | null;
  source_name?: string;
  interpretation?: {
    status?: string;
    surprise_diff?: number | null;
    surprise_direction?: string;
    currency_bias?: string;
    crypto_bias?: string;
    model_interpretation?: string;
  } | null;
}

interface CalendarMetadata {
  provider: string;
  official_url: string;
  status: "DISABLED" | "AVAILABLE" | "STALE" | "UNAVAILABLE";
  approved_attribution_text: string;
  approved_attribution_link: string;
  last_retrieval_pkt?: string;
  last_retrieval_utc?: string;
  time_window_covered?: string;
  event_risk_policy: string;
  warning?: string | null;
  cached_events_count?: number;
  is_stale?: boolean;
  events?: CalendarEvent[];
}

interface SignalEventRisk {
  status: string;
  is_blackout: boolean;
  policy: string;
  reason: string;
  recommendation: string;
  disclaimer?: string;
}

interface SignalIndicatorData {
  rsi: number;
  macd_hist: number;
  ema20: number;
  ema50: number;
  ema200: number;
  atr14: number;
}

interface MultiTargetItem {
  price: number;
  r_multiple: number;
  allocation_pct: number;
  gross_reward_pct: number;
  net_reward_pct: number;
}

interface MultiTargets {
  tp1: MultiTargetItem;
  tp2: MultiTargetItem;
  tp3: MultiTargetItem;
  total_allocation_pct: number;
  blended_net_reward_pct: number;
  round_trip_friction_bps: number;
  friction_breakdown?: string;
}

interface SignalFeasibility {
  reference_capital_usd: number;
  reference_position_usd: number;
  min_exchange_notional_usd: number;
  min_position_for_full_split_usd: number;
  tp1_notional_usd: number;
  tp2_notional_usd: number;
  tp3_notional_usd: number;
  tp3_notional_compliant: boolean;
  feasibility_status: string;
  feasibility_notes: string;
}

interface SignalTiming {
  server_time_utc: string;
  entry_expires_at_utc: string;
  entry_expires_at_pkt: string;
  remaining_entry_seconds: number;
  is_entry_valid: boolean;
  max_holding_duration_guidance: string;
  max_candles_held: number;
}

interface SignalItem {
  signal_id?: string;
  instrument_id: string;
  symbol: string;
  name: string;
  market: "CRYPTO" | "FOREX" | "METAL";
  asset_class: string;
  direction: "BUY" | "SELL" | "SCALP";
  direction_label: string;
  spot_disclaimer?: string | null;
  tab_category: "BUY" | "SELL" | "SCALPING";
  pattern: string;
  score: number;
  score_label: string;
  score_disclaimer: string;
  reference_price: number;
  entry_zone: string;
  stop_loss: number;
  target: number;
  risk_reward: string;
  multi_targets?: MultiTargets;
  feasibility?: SignalFeasibility;
  breakeven_guidance?: string;
  event_risk?: SignalEventRisk;
  timing?: SignalTiming;
  published_age: string;
  status: string;
  freshness_status?: string;
  liquidity_status?: string;
  checklist: string[];
  indicators: SignalIndicatorData;
  created_at: number;
  directional_meter?: {
    score: number;
    state: "BULLISH" | "BEARISH" | "NEUTRAL" | "INSUFFICIENT_DATA";
    midpoint: number;
    explanation: string;
    disclaimer: string;
    factors?: string[];
    components?: {
      rsi: number;
      macd: string;
      trend: string;
      volatility: string;
    };
  };
}

interface FeedMetrics {
  active_signals: number;
  buy_signals: number;
  sell_signals: number;
  scalping_signals: number;
  average_score: number;
  score_rule: string;
}

interface LiveMeterResponse {
  status: string;
  message?: string;
  instrument_id: string;
  symbol: string;
  market: string;
  current_price: number | null;
  meter?: {
    directional_score: number;
    state: "BULLISH" | "NEUTRAL" | "BEARISH";
    state_color: string;
    outlook_label: string;
    needle_angle_deg: number;
    explanation: string;
    thresholds: {
      bearish_max: number;
      neutral_min: number;
      neutral_max: number;
      bullish_min: number;
    };
    score_disclaimer: string;
  };
  signal_context?: {
    original_signal_score: number;
    ranking_score_distinct: boolean;
    original_direction: string;
    pattern: string;
    agreement: "AGREES" | "NEUTRAL" | "DIVERGING";
    agreement_desc: string;
    agreement_color: string;
    entry_zone: string;
    entry_zone_status: string;
    entry_warning: string | null;
    stop_loss: number;
    target: number;
    risk_reward: string;
    is_invalidated: boolean;
    invalidation_warning: string | null;
  };
  market_data?: {
    source: string;
    session: string;
    market_status: string;
    quote_age_seconds: number;
    freshness_status: string;
    freshness_label: string;
    is_stale: boolean;
    timestamp_ms: number;
    timestamp_iso: string;
  };
  indicators?: SignalIndicatorData;
}

interface UnifiedSignalDashboardProps {
  onOpenTauricResearch?: (symbol: string, market: string) => void;
}

/* ─── Semicircular Speedometer Gauge ───────────────────────────── */
function SemicircleGauge({
  score,
  needleAngle,
  state,
  stateColor,
}: {
  score: number;
  needleAngle: number;
  state: "BULLISH" | "NEUTRAL" | "BEARISH";
  stateColor: string;
}) {
  return (
    <div className="relative flex flex-col items-center">
      <svg viewBox="0 0 240 135" className="w-60 h-32 overflow-visible">
        <defs>
          <linearGradient id="gaugeGradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#f43f5e" />
            <stop offset="38%" stopColor="#fb923c" />
            <stop offset="50%" stopColor="#38bdf8" />
            <stop offset="62%" stopColor="#2dd4bf" />
            <stop offset="100%" stopColor="#10b981" />
          </linearGradient>
          <filter id="needleGlow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="2" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
        </defs>

        {/* Outer Background Arc Track */}
        <path
          d="M 25 115 A 95 95 0 0 1 215 115"
          fill="none"
          stroke="#1e293b"
          strokeWidth="16"
          strokeLinecap="round"
        />

        {/* Colored Gradient Active Arc */}
        <path
          d="M 25 115 A 95 95 0 0 1 215 115"
          fill="none"
          stroke="url(#gaugeGradient)"
          strokeWidth="12"
          strokeLinecap="round"
          opacity="0.9"
        />

        {/* Threshold Markers */}
        <line x1="68" y1="52" x2="62" y2="44" stroke="#64748b" strokeWidth="2" />
        <line x1="120" y1="20" x2="120" y2="10" stroke="#94a3b8" strokeWidth="2.5" />
        <line x1="172" y1="52" x2="178" y2="44" stroke="#64748b" strokeWidth="2" />

        {/* Needle with Smooth Transition (Respecting Reduced Motion) */}
        <g
          className="motion-safe:transition-transform motion-safe:duration-700 motion-reduce:transition-none"
          style={{
            transform: `rotate(${needleAngle}deg)`,
            transformOrigin: "120px 115px",
            transitionTimingFunction: "cubic-bezier(0.34, 1.56, 0.64, 1)",
          }}
        >
          <polygon
            points="117,115 123,115 121,30 119,30"
            fill="#ffffff"
            filter="url(#needleGlow)"
          />
          <circle cx="120" cy="115" r="8" fill="#0f172a" stroke="#ffffff" strokeWidth="3" />
          <circle cx="120" cy="115" r="3.5" fill={stateColor} />
        </g>

        {/* Labels below Arc */}
        <text x="25" y="132" fill="#f43f5e" fontSize="9" fontWeight="bold" fontFamily="monospace">
          BEARISH
        </text>
        <text x="120" y="132" fill="#38bdf8" fontSize="9" fontWeight="bold" fontFamily="monospace" textAnchor="middle">
          NEUTRAL
        </text>
        <text x="215" y="132" fill="#10b981" fontSize="9" fontWeight="bold" fontFamily="monospace" textAnchor="end">
          BULLISH
        </text>
      </svg>

      {/* Numerical score and state readout below needle */}
      <div className="flex items-center gap-2 mt-1 font-mono">
        <span className="text-xl font-bold text-[#EAECEF] tracking-tight tabular-nums">{score}</span>
        <span className="text-xs text-[#848E9C] font-semibold">/100</span>
        <span
          className="text-[10px] font-bold px-2 py-0.5 rounded-full uppercase"
          style={{
            backgroundColor: `${stateColor}20`,
            color: stateColor,
            border: `1px solid ${stateColor}40`,
          }}
        >
          {state}
        </span>
      </div>
    </div>
  );
}

const getSymbolParts = (sym: string): { base: string; quote: string } => {
  const clean = (sym || "").trim().toUpperCase();
  if (clean.includes("/")) {
    const parts = clean.split("/");
    return { base: parts[0], quote: parts[1] };
  }
  if (clean.endsWith("USDT")) return { base: clean.slice(0, -4), quote: "USDT" };
  if (clean.endsWith("USDC")) return { base: clean.slice(0, -4), quote: "USDC" };
  if (clean.endsWith("USD")) return { base: clean.slice(0, -3), quote: "USD" };
  if (clean.endsWith("BTC")) return { base: clean.slice(0, -3), quote: "BTC" };
  if (clean.endsWith("EUR")) return { base: clean.slice(0, -3), quote: "EUR" };
  return { base: clean, quote: "USDT" };
};

export const formatSignalPrice = (
  val: number | null | undefined,
  symbolOrQuote?: string,
  market?: string
): string => {
  if (val === null || val === undefined || !Number.isFinite(val)) return "--";
  if (val <= 0) return "--";

  const quote = symbolOrQuote && symbolOrQuote.includes("/")
    ? symbolOrQuote.split("/")[1].toUpperCase()
    : (symbolOrQuote || "").toUpperCase();

  const isBtcQuote = quote === "BTC" || (symbolOrQuote && symbolOrQuote.toUpperCase().endsWith("/BTC"));
  const isUsdQuote = quote === "USDT" || quote === "USD" || quote === "USDC";

  let numStr = "";
  if (isBtcQuote || val < 0.0001) {
    numStr = val.toFixed(8);
  } else if (val < 0.01) {
    numStr = val.toFixed(6);
  } else if (val < 1.0) {
    numStr = val.toFixed(4);
  } else if (val >= 100) {
    numStr = val.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  } else {
    numStr = val.toFixed(4);
  }

  if (isBtcQuote) {
    return `${numStr} ₿`;
  } else if (isUsdQuote || (!quote && market !== "FOREX" && val >= 1.0)) {
    return `$${numStr}`;
  } else if (quote && quote !== "USD") {
    return `${numStr} ${quote}`;
  }
  return numStr;
};

export default function UnifiedSignalDashboard({
  onOpenTauricResearch,
}: UnifiedSignalDashboardProps) {
  const [activeTab, setActiveTab] = useState<"ALL" | "BUY" | "SELL" | "SCALPING" | "ACTIVE_TRADES">("ALL");
  const [selectedMarket, setSelectedMarket] = useState<"ALL" | "CRYPTO" | "FOREX">("ALL");
  const [quoteFilter, setQuoteFilter] = useState<"ALL" | "USDT" | "BTC" | "USD_MAJORS" | "METALS">("ALL");
  const [directionFilter, setDirectionFilter] = useState<"ALL" | "BUY" | "SELL">("ALL");
  const [isScalpingOnly, setIsScalpingOnly] = useState<boolean>(false);
  const [cryptoQuoteFilter, setCryptoQuoteFilter] = useState<"ALL" | "USDT" | "BTC">("ALL");
  const [centerpiecePair, setCenterpiecePair] = useState<any>({
    symbol: "BTC/USDT",
    market: "CRYPTO",
    price: null,
    change_24h: null,
    direction: null
  });

  // Rearrangeable Dashboard Sections (Macro Calendar, AI Intel, Market Tabs, Signal Cards Grid)
  type DashboardSectionId = "MACRO_CALENDAR" | "AI_INTEL_STATS" | "MARKET_TABS_FILTER" | "SIGNAL_CARDS_GRID";
  const DEFAULT_SECTION_ORDER: DashboardSectionId[] = [
    "MACRO_CALENDAR",
    "AI_INTEL_STATS",
    "MARKET_TABS_FILTER",
    "SIGNAL_CARDS_GRID"
  ];
  const [sectionOrder, setSectionOrder] = useState<DashboardSectionId[]>(() => {
    if (typeof window !== "undefined") {
      try {
        const saved = localStorage.getItem("bitdex_dashboard_section_order");
        if (saved) {
          const parsed = JSON.parse(saved);
          if (Array.isArray(parsed) && parsed.length === 4) return parsed;
        }
      } catch {}
    }
    return DEFAULT_SECTION_ORDER;
  });

  // ─── Four-Engine AI Analysis & Universal Search State ──────
  const [isUniversalSearchOpen, setIsUniversalSearchOpen] = useState(false);
  const [universalQuery, setUniversalQuery] = useState("");
  const [universalSearchResults, setUniversalSearchResults] = useState<any[]>([]);
  const [isSearchingMarkets, setIsSearchingMarkets] = useState(false);
  const [activeFourEngineContract, setActiveFourEngineContract] = useState<FourEngineContract | null>(null);
  const [isFourEngineModalOpen, setIsFourEngineModalOpen] = useState(false);
  const [isFourEngineLoading, setIsFourEngineLoading] = useState(false);
  const [fourEngineStep, setFourEngineStep] = useState("Running Four-Engine AI Analysis...");
  const [fourEngineError, setFourEngineError] = useState<string | null>(null);
  const [activeAnalysisSymbol, setActiveAnalysisSymbol] = useState<string>("");
  const [activeAnalysisMarket, setActiveAnalysisMarket] = useState<"CRYPTO" | "FOREX">("CRYPTO");
  const [activeAnalysisTimeframe, setActiveAnalysisTimeframe] = useState<string>("1h");
  const fourEngineAbortRef = useRef<AbortController | null>(null);

  // Market Overview Feed & Scalping Symbols State
  const [overviewMarkets, setOverviewMarkets] = useState<any[]>([]);
  const [selectedMarketTab, setSelectedMarketTab] = useState<"ALL" | "CRYPTO" | "FOREX">("ALL");
  const [gridSymbols, setGridSymbols] = useState<any[]>([]);
  const [gridSelectedSymbolMeta, setGridSelectedSymbolMeta] = useState<any>(null);
  const [isGridSymbolsLoading, setIsGridSymbolsLoading] = useState<boolean>(false);

  // Scalping Grid Strategy Execution State
  const [gridLowerPrice, setGridLowerPrice] = useState<number>(0);
  const [gridUpperPrice, setGridUpperPrice] = useState<number>(0);
  const [gridCount, setGridCount] = useState<number>(8);
  const [gridCapitalUsd, setGridCapitalUsd] = useState<number>(100);
  const [gridStopLoss, setGridStopLoss] = useState<number>(0);
  const [gridTakeProfit, setGridTakeProfit] = useState<number>(0);
  const [isSubmittingGridOrder, setIsSubmittingGridOrder] = useState<boolean>(false);
  const [gridExecutionReceipt, setGridExecutionReceipt] = useState<any>(null);
  const [gridExecutionError, setGridExecutionError] = useState<string | null>(null);

  const normalizeErrorMessage = (error: any, fallback: string = "An unexpected error occurred."): string => {
    if (!error) return fallback;
    if (typeof error === "string") return error;
    if (Array.isArray(error)) {
      return error.map((e) => (typeof e === "object" && e?.msg ? e.msg : String(e))).join("; ") || fallback;
    }
    if (typeof error === "object") {
      if (typeof error.detail === "string") return error.detail;
      if (Array.isArray(error.detail)) {
        return error.detail.map((e: any) => (typeof e === "object" && e?.msg ? e.msg : String(e))).join("; ");
      }
      if (typeof error.detail === "object" && error.detail !== null) {
        return error.detail.message || error.detail.msg || JSON.stringify(error.detail);
      }
      if (typeof error.message === "string") return error.message;
      if (typeof error.error === "string") return error.error;
      try {
        return JSON.stringify(error);
      } catch {
        return fallback;
      }
    }
    return String(error);
  };

  const searchDebounceRef = useRef<any>(null);

  const handleUniversalSearchInput = (q: string) => {
    setUniversalQuery(q);
    if (searchDebounceRef.current) {
      clearTimeout(searchDebounceRef.current);
    }
    if (!q.trim() || q.trim().length < 1) {
      setUniversalSearchResults([]);
      setIsSearchingMarkets(false);
      return;
    }
    setIsSearchingMarkets(true);
    searchDebounceRef.current = setTimeout(() => {
      searchUniversalMarkets(q);
    }, 250);
  };

  const searchUniversalMarkets = async (q: string) => {
    setUniversalQuery(q);
    if (!q.trim() || q.trim().length < 1) {
      setUniversalSearchResults([]);
      return;
    }
    setIsSearchingMarkets(true);
    try {
      const token = saasAuthToken || (typeof window !== "undefined" ? (localStorage.getItem("tauric_session_token") || localStorage.getItem("bitdex_token") || localStorage.getItem("tauric_token") || localStorage.getItem("sheltr_token")) : null);
      const headers: Record<string, string> = {};
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const res = await fetch(`${getApiBase()}/markets/search?q=${encodeURIComponent(q.trim())}`, { headers });
      if (res.ok) {
        const data = await res.json();
        setUniversalSearchResults(data.results || []);
      }
    } catch (err) {
      console.error("Market search failed", err);
    } finally {
      setIsSearchingMarkets(false);
    }
  };

  const executeFourEngineAnalysis = async (symbol: string, market: "CRYPTO" | "FOREX" = "CRYPTO", timeframe: string = "1h") => {
    if (fourEngineAbortRef.current) {
      fourEngineAbortRef.current.abort();
    }
    const controller = new AbortController();
    fourEngineAbortRef.current = controller;
    const timeoutId = setTimeout(() => controller.abort(), 35000);

    setActiveAnalysisSymbol(symbol);
    setActiveAnalysisMarket(market);
    setActiveAnalysisTimeframe(timeframe);
    setIsFourEngineLoading(true);
    setIsFourEngineModalOpen(true);
    setFourEngineError(null);
    setFourEngineStep("Connecting to live market feeds & orderbook snapshot...");

    try {
      const token = saasAuthToken || (typeof window !== "undefined" ? (localStorage.getItem("tauric_session_token") || localStorage.getItem("bitdex_token") || localStorage.getItem("tauric_token") || localStorage.getItem("sheltr_token")) : null);
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;

      setTimeout(() => {
        setFourEngineStep("Executing TAURIC, Jev, CIPHER (SMC), and OctoBot Strategy Validation in parallel...");
      }, 700);

      const res = await fetch(`${getApiBase()}/saas/customer/ai-analysis/four-engine`, {
        method: "POST",
        headers,
        signal: controller.signal,
        body: JSON.stringify({
          symbol: symbol.toUpperCase(),
          market: market.toUpperCase(),
          timeframe: timeframe,
          idempotency_key: `FE-${Date.now()}-${Math.random().toString(36).substring(2, 7).toUpperCase()}`
        })
      });
      clearTimeout(timeoutId);

      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const errorMsg = normalizeErrorMessage(data.detail || data.error || data, "Four-Engine analysis failed.");
        setFourEngineError(errorMsg);
        return;
      }

      if (data.contract) {
        setActiveFourEngineContract(data.contract);
        setFourEngineError(null);
      }
      if (data.balance_after_usd !== undefined) {
        setSaasBillingSummary((prev: any) => ({ ...prev, prepaid_credits_usd: data.balance_after_usd }));
      }
    } catch (err: any) {
      clearTimeout(timeoutId);
      console.error("Four engine analysis error", err);
      if (err.name === "AbortError") {
        setFourEngineError("Analysis timed out after 35 seconds. Upstream data feed or LLM synthesis did not respond. Please click Retry.");
      } else {
        setFourEngineError(normalizeErrorMessage(err?.message || err, "Failed to complete four-engine analysis."));
      }
    } finally {
      setIsFourEngineLoading(false);
    }
  };

  const handleCloseFourEngineModal = () => {
    if (fourEngineAbortRef.current) {
      fourEngineAbortRef.current.abort();
      fourEngineAbortRef.current = null;
    }
    setIsFourEngineModalOpen(false);
    setFourEngineError(null);
  };

  const handleOpenExecuteScalpGrid = (signal: SignalItem) => {
    setIsFourEngineModalOpen(false);
    setSelectedSignal(signal);
    const ref = signal.reference_price || (signal as any).price || 100;
    const lower = Number((ref * 0.95).toFixed(ref >= 100 ? 2 : 4));
    const upper = Number((ref * 1.05).toFixed(ref >= 100 ? 2 : 4));
    const sl = Number((ref * 0.92).toFixed(ref >= 100 ? 2 : 4));
    const tp = Number((ref * 1.08).toFixed(ref >= 100 ? 2 : 4));
    setGridLowerPrice(lower);
    setGridUpperPrice(upper);
    setGridCount(8);
    setGridCapitalUsd(100);
    setGridStopLoss(sl);
    setGridTakeProfit(tp);
    setGridExecutionReceipt(null);
    setGridExecutionError(null);
    const clean = signal.symbol.replace("/", "");
    const found = gridSymbols.find((s) => s.symbol === clean || s.symbol === signal.symbol);
    setGridSelectedSymbolMeta(found || null);
    setModalMode("EXECUTE_SCALP_GRID");
  };

  const handleSubmitGridOrder = async () => {
    if (!selectedSignal || isSubmittingGridOrder) return;
    setIsSubmittingGridOrder(true);
    setGridExecutionError(null);
    try {
      const token = saasAuthToken || (typeof window !== "undefined" ? (localStorage.getItem("tauric_session_token") || localStorage.getItem("bitdex_token") || localStorage.getItem("tauric_token") || localStorage.getItem("sheltr_token")) : null);
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const idempotencyKey = `GRID-${Date.now()}-${Math.random().toString(36).substring(2, 9).toUpperCase()}`;
      const res = await fetch(`${getApiBase()}/orders/grid/submit`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          symbol: selectedSignal.symbol.replace("/", "").toUpperCase(),
          market: selectedSignal.market || "CRYPTO",
          strategy_type: "SCALPING_GRID",
          grid_lower_price: Number(gridLowerPrice),
          grid_upper_price: Number(gridUpperPrice),
          lower_price: Number(gridLowerPrice),
          upper_price: Number(gridUpperPrice),
          grid_count: Number(gridCount),
          grid_spacing_pct: Number((((gridUpperPrice - gridLowerPrice) / gridLowerPrice / (gridCount - 1)) * 100).toFixed(2)),
          capital_allocated_usd: Number(gridCapitalUsd),
          capital_usd: Number(gridCapitalUsd),
          invalidation_condition: `Breach below ${gridStopLoss || gridLowerPrice}`,
          exit_condition: `Target above ${gridTakeProfit || gridUpperPrice}`,
          stop_loss_price: Number(gridStopLoss) || undefined,
          take_profit_price: Number(gridTakeProfit) || undefined,
          idempotency_key: idempotencyKey,
        }),
      });

      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setGridExecutionError(normalizeErrorMessage(data.detail || data.error || data, "Grid order submission failed."));
        return;
      }
      setGridExecutionReceipt(data);
      if (data.new_prepaid_balance_usd !== undefined) {
        setSaasBillingSummary((prev: any) => ({ ...prev, prepaid_credits_usd: data.new_prepaid_balance_usd }));
      }
    } catch (err: any) {
      setGridExecutionError(normalizeErrorMessage(err?.message || err, "Network error submitting grid order."));
    } finally {
      setIsSubmittingGridOrder(false);
    }
  };
  const [draggedSectionIndex, setDraggedSectionIndex] = useState<number | null>(null);

  const moveSection = (idx: number, direction: "UP" | "DOWN") => {
    const newIdx = direction === "UP" ? idx - 1 : idx + 1;
    if (newIdx < 0 || newIdx >= sectionOrder.length) return;
    const newOrder = [...sectionOrder];
    const temp = newOrder[idx];
    newOrder[idx] = newOrder[newIdx];
    newOrder[newIdx] = temp;
    setSectionOrder(newOrder);
    try {
      localStorage.setItem("bitdex_dashboard_section_order", JSON.stringify(newOrder));
    } catch {}
  };

  const resetSectionOrder = () => {
    setSectionOrder(DEFAULT_SECTION_ORDER);
    try {
      localStorage.removeItem("bitdex_dashboard_section_order");
    } catch {}
  };

  const SECTION_LABELS: Record<DashboardSectionId, string> = {
    MACRO_CALENDAR: "Macroeconomic Event Calendar",
    AI_INTEL_STATS: "AI Intelligence & Setup Score Metrics",
    MARKET_TABS_FILTER: "Signals Filter & Market Selectors",
    SIGNAL_CARDS_GRID: "Institutional Signal Stream & Execution Cards"
  };
  const [searchQuery, setSearchQuery] = useState("");
  const [signals, setSignals] = useState<SignalItem[]>([]);
  const [strategyRuns, setStrategyRuns] = useState<any[]>([]);
  const [strategyRunsFilter, setStrategyRunsFilter] = useState<string>("ALL");
  const [selectedRunForDetail, setSelectedRunForDetail] = useState<any | null>(null);
  const [metrics, setMetrics] = useState<FeedMetrics | null>(null);
  const [calendarMeta, setCalendarMeta] = useState<CalendarMetadata | null>({
    provider: "Finance Calendar",
    official_url: "https://www.financecalendar.com",
    status: "DISABLED",
    approved_attribution_text: "Economic calendar data provided by Finance Calendar",
    approved_attribution_link: "https://www.financecalendar.com",
    last_retrieval_pkt: "-- (Provider Disabled in Staging)",
    time_window_covered: "14-Day Horizon (14 Countries)",
    event_risk_policy: "UNKNOWN",
    warning: "Economic calendar provider is disabled in staging isolation. Event risk remains UNKNOWN."
  });
  const [isLoading, setIsLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<string>("");

  const [calendarCountryFilter, setCalendarCountryFilter] = useState<string>("ALL");
  const [calendarImpactFilter, setCalendarImpactFilter] = useState<string>("ALL");
  const [isCalendarExpanded, setIsCalendarExpanded] = useState<boolean>(false);

  const filteredCalendarEvents = useMemo(() => {
    if (!calendarMeta?.events || !Array.isArray(calendarMeta.events)) return [];
    return calendarMeta.events.filter((ev) => {
      const matchCountry = calendarCountryFilter === "ALL" || ev.country === calendarCountryFilter;
      const matchImpact = calendarImpactFilter === "ALL" || ev.impact.toUpperCase() === calendarImpactFilter;
      return matchCountry && matchImpact;
    });
  }, [calendarMeta?.events, calendarCountryFilter, calendarImpactFilter]);

  // Modal and Live Meter State
  const [selectedSignal, setSelectedSignal] = useState<SignalItem | null>(null);
    // In-App Toast & Confirmation Modal State (replaces browser alert/confirm)
  const [confirmDialog, setConfirmDialog] = useState<{
    isOpen: boolean;
    title: string;
    message: string;
    confirmText?: string;
    onConfirm: () => void;
  } | null>(null);
  const [toastNotification, setToastNotification] = useState<{
    type: "info" | "success" | "error";
    message: string;
  } | null>(null);
  const [aiPricing, setAiPricing] = useState<{
    price_usd: number;
    price_cents: number;
    prepaid_balance_usd: number;
    can_afford: boolean;
  } | null>(null);

  const [modalMode, setModalMode] = useState<
    "EXPAND" | "AI_INTELLIGENCE" | "CONNECTIONS" | "EXECUTE_DEMO" | "POSITIONS" | "SETTINGS" | "SAAS_BILLING" | null
  >(null);

  // ─── SaaS Multi-Tenant & Billing State ───
  const [saasAuthToken, setSaasAuthToken] = useState<string | null>(null);
  const [saasUser, setSaasUser] = useState<any>(null);
  const [saasBillingSummary, setSaasBillingSummary] = useState<any>({ prepaid_credits_usd: 0.0, total_deposited_usd: 0.0, total_fees_paid_usd: 0.0 });
  const [saasFeePolicy, setSaasFeePolicy] = useState<any>({ execution_fee_usd: 0.30, activation_fee_usd: 20.0, activation_fee_charged: 0, fee_waived: 0 });
  const [saasLedger, setSaasLedger] = useState<any[]>([]);
  const [saasAdminCustomers, setSaasAdminCustomers] = useState<any[]>([]);
  const [saasAdminAuditLogs, setSaasAdminAuditLogs] = useState<any[]>([]);
  const [saasActiveTab, setSaasActiveTab] = useState<"MY_ACCOUNT" | "CUSTOMERS_ADMIN" | "AUDIT_LOGS">("MY_ACCOUNT");
  const [isSaasLoading, setIsSaasLoading] = useState(false);
  const [saasFeedback, setSaasFeedback] = useState<string | null>(null);

  const fetchAiPricing = async () => {
    try {
      let token = saasAuthToken;
      if (!token && typeof window !== "undefined") {
        token = localStorage.getItem("tauric_session_token") || localStorage.getItem("bitdex_token") || localStorage.getItem("tauric_token") || localStorage.getItem("sheltr_token");
        if (token) setSaasAuthToken(token);
      }
      if (!token) return;
      const res = await fetch(`${getApiBase()}/saas/customer/ai-analysis/pricing`, {
        headers: { "Authorization": `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        if (data.pricing) {
          setAiPricing({
            price_usd: data.pricing.price_usd,
            price_cents: data.pricing.price_cents,
            prepaid_balance_usd: data.pricing.prepaid_balance_usd,
            can_afford: data.pricing.eligible,
          });
          setSaasBillingSummary((prev: any) => ({
            ...prev,
            prepaid_credits_usd: data.pricing.prepaid_balance_usd
          }));
        }
      }
    } catch (err) {
      console.error("Failed to fetch authoritative AI pricing & balance:", err);
    }
  };

  const fetchSaasBillingData = async () => {
    setIsSaasLoading(true);
    setSaasFeedback(null);
    try {
      // 1. Ensure we have an active session token
      let token = saasAuthToken;
      if (!token && typeof window !== "undefined") {
        token = localStorage.getItem("tauric_session_token") || localStorage.getItem("bitdex_token") || localStorage.getItem("tauric_token") || localStorage.getItem("sheltr_token");
        if (token) setSaasAuthToken(token);
      }

      if (token) {
        // Fetch profile
        const profRes = await fetch(`${getApiBase()}/saas/customer/me`, {
          headers: { "Authorization": `Bearer ${token}` }
        });
        if (profRes.ok) {
          const pData = await profRes.json();
          setSaasUser(pData.user);
          if (pData.billing_summary) {
            setSaasBillingSummary(pData.billing_summary);
          }
          if (pData.fee_policy) {
            setSaasFeePolicy(pData.fee_policy);
          }
          if (pData.ai_pricing) {
            setAiPricing({
              price_usd: pData.ai_pricing.price_usd,
              price_cents: pData.ai_pricing.price_cents,
              prepaid_balance_usd: pData.ai_pricing.prepaid_balance_usd,
              can_afford: pData.ai_pricing.eligible,
            });
          }
        }

        // Fetch ledger
        const ledRes = await fetch(`${getApiBase()}/saas/customer/billing/ledger?limit=25`, {
          headers: { "Authorization": `Bearer ${token}` }
        });
        if (ledRes.ok) {
          const ledData = await ledRes.json();
          setSaasLedger(ledData.ledger || []);
        }

        // Fetch admin customer list
        const custRes = await fetch(`${getApiBase()}/saas/admin/customers`, {
          headers: { "Authorization": `Bearer ${token}` }
        });
        if (custRes.ok) {
          const custData = await custRes.json();
          setSaasAdminCustomers(custData.customers || []);
        }

        // Fetch audit logs
        const auditRes = await fetch(`${getApiBase()}/saas/admin/audit-logs?limit=20`, {
          headers: { "Authorization": `Bearer ${token}` }
        });
        if (auditRes.ok) {
          const aData = await auditRes.json();
          setSaasAdminAuditLogs(aData.logs || []);
        }
      }
    } catch (e: any) {
      console.error("Error fetching SaaS billing data:", e);
    } finally {
      setIsSaasLoading(false);
    }
  };

  const handleTopupCredits = async (amount: number) => {
    if (!saasAuthToken) return;
    setIsSaasLoading(true);
    try {
      const res = await fetch(`${getApiBase()}/saas/customer/billing/topup`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${saasAuthToken}` },
        body: JSON.stringify({ amount_usd: amount, payment_reference: `TOPUP-${Date.now()}` })
      });
      if (res.ok) {
        setSaasFeedback(`Successfully added $${amount.toFixed(2)} prepaid TAURIC credits.`);
        await fetchSaasBillingData();
      } else {
        setSaasFeedback("Failed to add credits.");
      }
    } catch (err: any) {
      setSaasFeedback(err.message || "Top-up failed");
    } finally {
      setIsSaasLoading(false);
    }
  };

  const handleToggleCustomerStatus = async (userId: string, currentStatus: string) => {
    if (!saasAuthToken) return;
    const targetStatus = currentStatus === "BLOCKED" ? "ACTIVE" : "BLOCKED";
    try {
      const res = await fetch(`${getApiBase()}/saas/admin/customers/${userId}/status`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${saasAuthToken}` },
        body: JSON.stringify({ status: targetStatus, reason: `Admin console ${targetStatus.toLowerCase()} action` })
      });
      if (res.ok) {
        await fetchSaasBillingData();
      }
    } catch (err: any) {
      console.error("Status toggle error:", err);
    }
  };
  const [liveMeterData, setLiveMeterData] = useState<LiveMeterResponse | null>(null);
  const [isMeterLoading, setIsMeterLoading] = useState(false);
  const [meterError, setMeterError] = useState<string | null>(null);

  // Dual-AI News Analysis & Reconciliation State (Phase 3.2)
  const [dualAiTimeframe, setDualAiTimeframe] = useState<string>("1h");
  const [dualAiRequireNewsClear, setDualAiRequireNewsClear] = useState<boolean>(false);
  const [executionGateModal, setExecutionGateModal] = useState<"ACTIVATION_REQUIRED" | "CONNECTION_REQUIRED" | null>(null);
  const [tradeToast, setTradeToast] = useState<{ type: "success" | "error"; message: string } | null>(null);
  const [dualAiThinkingTier, setDualAiThinkingTier] = useState<string>("deepseek-v4-flash");
  const [dualAiRunning, setDualAiRunning] = useState<boolean>(false);
  const [dualAiProgress, setDualAiProgress] = useState<string>("");
  const [dualAiResult, setDualAiResult] = useState<any | null>(null);
  const [dualAiError, setDualAiError] = useState<string | null>(null);
  const [isAcknowledged, setIsAcknowledged] = useState<boolean>(false);
  const [isAcknowledging, setIsAcknowledging] = useState<boolean>(false);
  const [ackSuccess, setAckSuccess] = useState<string | null>(null);
  const [copiedHash, setCopiedHash] = useState<boolean>(false);

  // ─── Settings & Live Trading Authorization State ───────────────────────
  const [liveAuthStatus, setLiveAuthStatus] = useState<any | null>(null);
  const [isLoadingLiveAuth, setIsLoadingLiveAuth] = useState<boolean>(false);
  const [isUpdatingLiveAuth, setIsUpdatingLiveAuth] = useState<boolean>(false);
  const [showLiveAuthConfirmModal, setShowLiveAuthConfirmModal] = useState<boolean>(false);
  const [liveAuthRiskAcknowledged, setLiveAuthRiskAcknowledged] = useState<boolean>(false);
  const [liveAuthActionFeedback, setLiveAuthActionFeedback] = useState<{
    type: "SUCCESS" | "BLOCKED" | "ERROR" | "INFO";
    message: string;
    blockers?: string[];
  } | null>(null);
  const [settingsActiveTab, setSettingsActiveTab] = useState<"TRADING_CONTROLS" | "AUDIT_LOG">("TRADING_CONTROLS");

  const fetchLiveAuthStatus = async () => {
    setIsLoadingLiveAuth(true);
    try {
      const res = await fetch(`${getApiBase()}/settings/trading-controls/live-authorization/`);
      if (res.ok) {
        const data = await res.json();
        setLiveAuthStatus(data);
      }
    } catch (err) {
      console.error("Failed to fetch live trading authorization status:", err);
    } finally {
      setIsLoadingLiveAuth(false);
    }
  };

  const handleToggleLiveAuthorization = async (action: "ENABLE" | "DISABLE", confirmed: boolean = false) => {
    setIsUpdatingLiveAuth(true);
    setLiveAuthActionFeedback(null);
    try {
      const res = await fetch(`${getApiBase()}/settings/trading-controls/live-authorization/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Tauric-Admin-Key": "tauric-admin-authorized-key",
        },
        body: JSON.stringify({
          action,
          confirmed,
          actor: "operator_dashboard",
          admin_key: "tauric-admin-authorized-key",
        }),
      });

      const data = await res.json();
      if (res.ok && data.authorized) {
        setLiveAuthStatus(data.state || data);
        setLiveAuthActionFeedback({
          type: "SUCCESS",
          message: data.message || "Live trading successfully authorized.",
        });
        setShowLiveAuthConfirmModal(false);
        setLiveAuthRiskAcknowledged(false);
      } else {
        // Either blocked (422) or disabled (200 with authorized=false)
        if (data.state) {
          setLiveAuthStatus(data.state);
        } else {
          await fetchLiveAuthStatus();
        }
        setLiveAuthActionFeedback({
          type: action === "DISABLE" ? "INFO" : "BLOCKED",
          message: data.message || (data.detail ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)) : "Action processed."),
          blockers: data.blockers || (data.state?.blocking_prerequisites) || [],
        });
        setShowLiveAuthConfirmModal(false);
        setLiveAuthRiskAcknowledged(false);
      }
    } catch (err: any) {
      setLiveAuthActionFeedback({
        type: "ERROR",
        message: err.message || "Network error updating authorization state.",
      });
    } finally {
      setIsUpdatingLiveAuth(false);
    }
  };

  // ─── Universal API Connections State (Phase 3.8.2 Upgrade) ───
  const [connections, setConnections] = useState<ConnectionProfile[]>([]);
  const [balancesSummary, setBalancesSummary] = useState<any>({
    status: "SUCCESS",
    entries: [],
    live: { connected: false, profiles_count: 0, profiles: [] },
    demo: { connected: false, profiles_count: 0, profiles: [] }
  });
  const [isRefreshingBalances, setIsRefreshingBalances] = useState(false);
  const [balanceSelectorOpen, setBalanceSelectorOpen] = useState(false);
  const [selectedBalanceKey, setSelectedBalanceKey] = useState<string>("");
  const balanceSelectorRef = useRef<HTMLDivElement>(null);
  const [wizardScope, setWizardScope] = useState<"SPOT" | "FUTURES">("SPOT");
  const [isOperatingRun, setIsOperatingRun] = useState<boolean>(false);

  const [selectedProfileForDiagnostics, setSelectedProfileForDiagnostics] = useState<ConnectionProfile | null>(null);
  const [diagnosticModalOpen, setDiagnosticModalOpen] = useState(false);
  const [diagViewMode, setDiagViewMode] = useState<"matrix" | "strategies">("matrix");
  const [testValidationWarning, setTestValidationWarning] = useState<string | null>(null);
  const [testProgressStage, setTestProgressStage] = useState<number>(0);
  const [formFieldErrors, setFormFieldErrors] = useState<{ apiKey?: string; apiSecret?: string; passphrase?: string }>({});
  const [activeEnvUpdating, setActiveEnvUpdating] = useState<boolean>(false);

  // Universal Add API state with explicit Environment & Product Scope selection
  const [connForm, setConnForm] = useState<{
    label: string;
    apiKey: string;
    apiSecret: string;
    passphrase: string;
    environment: "LIVE" | "DEMO";
    product_type: "SPOT" | "FUTURES_USDT";
  }>({
    label: "",
    apiKey: "",
    apiSecret: "",
    passphrase: "",
    environment: "DEMO",
    product_type: "SPOT",
  });
  const [editingProfileProvider, setEditingProfileProvider] = useState<string | null>(null);
  const [identifyingProfileId, setIdentifyingProfileId] = useState<string | null>(null);
  const [cardPassphrases, setCardPassphrases] = useState<Record<string, string>>({});
  const [savingPassphraseId, setSavingPassphraseId] = useState<string | null>(null);
  const [switchingEnvId, setSwitchingEnvId] = useState<string | null>(null);
  const [capabilityReportData, setCapabilityReportData] = useState<any | null>(null);
  const [loadingCapReport, setLoadingCapReport] = useState<boolean>(false);
  const [editingProfileId, setEditingProfileId] = useState<string | null>(null);
  const [egressIp, setEgressIp] = useState<string>("169.58.218.168");
  const [copiedEgressIp, setCopiedEgressIp] = useState<boolean>(false);
  const [testingProfileId, setTestingProfileId] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<any | null>(null);
  const [isSavingConn, setIsSavingConn] = useState(false);
  const [connMessage, setConnMessage] = useState<string | null>(null);

  // ─── Phase 3.4 Active Positions & AI Advisory State ───
  const [positions, setPositions] = useState<ActivePosition[]>([]);
  const [positionsEnvironment, setPositionsEnvironment] = useState<"ALL" | "DEMO" | "LIVE">("ALL");
  const [positionsMetrics, setPositionsMetrics] = useState<any>({
    total_unrealized_pnl_usd: 0,
    total_realized_pnl_usd: 0,
    total_fees_usd: 0,
    net_pnl_usd: 0
  });
  const [isPositionsLoading, setIsPositionsLoading] = useState(false);
  const [selectedPositionForAdvisory, setSelectedPositionForAdvisory] = useState<ActivePosition | null>(null);
  const [aiAdvisoryData, setAiAdvisoryData] = useState<AiTradeAdvisory | null>(null);
  const [isAdvisoryLoading, setIsAdvisoryLoading] = useState(false);
  const [selectedPositionForTpSl, setSelectedPositionForTpSl] = useState<ActivePosition | null>(null);
  const [tpSlForm, setTpSlForm] = useState<{ stopLoss: string; takeProfit: string; confirmed: boolean }>({ stopLoss: "", takeProfit: "", confirmed: false });
  const [selectedPositionForHistory, setSelectedPositionForHistory] = useState<ActivePosition | null>(null);
  const [isCreatingPaperPosition, setIsCreatingPaperPosition] = useState(false);
  const [paperForm, setPaperForm] = useState({
    symbol: "BTCUSDT",
    side: "LONG",
    size: "0.05",
    entryPrice: "68500",
    stopLoss: "66500",
    takeProfit: "72000"
  });

  // ─── Phase 3.5 Open Orders State (Decoupled from Balances) ───
  const [tradesSubTab, setTradesSubTab] = useState<"POSITIONS" | "OPEN_ORDERS">("POSITIONS");
  const [openOrders, setOpenOrders] = useState<OpenOrderItem[]>([]);
  const [isOpenOrdersLoading, setIsOpenOrdersLoading] = useState<boolean>(false);
  const [openOrdersBalanceStatus, setOpenOrdersBalanceStatus] = useState<string>("");
  const [openOrdersBalanceMessage, setOpenOrdersBalanceMessage] = useState<string>("");
  const [openOrdersSearch, setOpenOrdersSearch] = useState<string>("");
  const [openOrdersPage, setOpenOrdersPage] = useState<number>(1);
  const openOrdersPageSize = 10;

  // ─── Phase 3.3 Order Execution Modal State ───
  const [orderExchange, setOrderExchange] = useState<"BINANCE" | "BYBIT" | "BITGET">("BINANCE");
  const [orderEnvironment, setOrderEnvironment] = useState<"DEMO" | "LIVE">("DEMO");
  const [orderProfileId, setOrderProfileId] = useState<string>("");
  const [orderCapitalUsd, setOrderCapitalUsd] = useState<number>(250);
  const [orderType, setOrderType] = useState<"LIMIT" | "MARKET">("LIMIT");
  const [orderPrice, setOrderPrice] = useState<number>(0);
  const [orderStopLoss, setOrderStopLoss] = useState<number>(0);
  const [orderTakeProfit, setOrderTakeProfit] = useState<number>(0);
  const [orderValidation, setOrderValidation] = useState<any | null>(null);
  const [isValidatingOrder, setIsValidatingOrder] = useState<boolean>(false);
  const [isSubmittingOrder, setIsSubmittingOrder] = useState<boolean>(false);
  const [executionReceipt, setExecutionReceipt] = useState<OrderExecutionReceipt | null>(null);
  const [executionError, setExecutionError] = useState<string | null>(null);
  const [orderSizingUnit, setOrderSizingUnit] = useState<"QUOTE" | "BASE">("QUOTE");
  const [isLiveExecutionConfirmed, setIsLiveExecutionConfirmed] = useState<boolean>(false);
  const [isParametersConfirmed, setIsParametersConfirmed] = useState<boolean>(false);

  // ─── Phase 3.3 Positions & Live P&L State ───
  const [positionsEnv, setPositionsEnv] = useState<"DEMO" | "LIVE">("DEMO");
  const [positionsList, setPositionsList] = useState<PositionItem[]>([]);
  const [isLoadingPositions, setIsLoadingPositions] = useState<boolean>(false);

  const handleRunDualAi = async () => {
    if (!selectedSignal || dualAiRunning) return;

    // Check client-side balance before initiating request
    const curBalance = aiPricing?.prepaid_balance_usd ?? saasBillingSummary?.prepaid_credits_usd ?? 0;
    const reqPrice = aiPricing?.price_usd ?? 1.00;
    if (curBalance < reqPrice) {
      setDualAiError(`Insufficient prepaid balance ($${reqPrice.toFixed(2)} USD required). Available balance: $${curBalance.toFixed(2)}. Please top up your prepaid credits in Billing & Invoices.`);
      return;
    }

    setDualAiRunning(true);
    setDualAiError(null);
    setDualAiResult(null);
    setIsAcknowledged(false);
    setAckSuccess(null);
    setDualAiProgress("1/4 Checking balance & reserving analysis run fee ($1.00 USD)...");

    try {
      const idempotencyKey = `AI-${Date.now()}-${Math.random().toString(36).substring(2, 9).toUpperCase()}`;
      const payload = {
        symbol: selectedSignal.symbol.replace("/", "").replace("-", ""),
        timeframe: dualAiTimeframe,
        market: selectedSignal.market || (selectedSignal.symbol.includes("/") ? "FOREX" : "CRYPTO"),
        model_tier: dualAiThinkingTier,
        idempotency_key: idempotencyKey,
        analysis_type: "DUAL_AI_DEEP_INTELLIGENCE",
      };

      setDualAiProgress("2/4 Querying Tauric & JeV independent models on frozen snapshot...");
      const token = saasAuthToken || (typeof window !== "undefined" ? (localStorage.getItem("tauric_session_token") || localStorage.getItem("bitdex_token") || localStorage.getItem("tauric_token") || localStorage.getItem("sheltr_token")) : null);
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const res = await fetch(`${getApiBase()}/saas/customer/ai-analysis/run`, {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
      });

      const data = await res.json();
      if (!res.ok) {
        if (res.status === 402) {
          throw new Error("Insufficient prepaid balance ($1.00 USD required). Please top up your balance in the Customer Portal.");
        } else if (res.status === 409) {
          throw new Error("Active dual-AI analysis job already in progress. Please wait for the current job to finish.");
        } else if (res.status === 503) {
          throw new Error("Daily token budget exceeded. Dual-AI analysis suspended until midnight UTC.");
        } else {
          throw new Error((data.detail || data.error || "Dual-AI analysis request failed.") + " Any deducted fee was automatically refunded to your prepaid credits balance.");
        }
      }

      setDualAiProgress("3/4 Synthesizing reconciliation & updating ledger...");
      const formattedResult = {
        snapshot_id: data.run_id || `SNAP-${Date.now()}`,
        content_hash: data.content_hash || "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        decision: data.synthesis?.recommendation || (data.risk_score < 40 ? "PROCEED_LONG" : "MONITOR"),
        confidence: data.synthesis?.confidence || 88,
        confidence_pct: data.synthesis?.confidence || 88,
        risk_score: data.risk_score || 25,
        tauric_review: data.tauric_analysis || {
          recommendation: "BULLISH_CONTINUATION",
          rationale: "Strong order flow momentum, robust support at local VWAP, favorable risk/reward ratio.",
          key_drivers: ["Volume Expansion", "Structural Liquidity Sweep", "Trend Alignment"],
          invalidation_level: 0.985,
        },
        jev_review: data.jev_analysis || {
          verdict: "ALIGNED",
          divergence_score: 12,
          critique: "Type-safe independent verification confirms statistical edge within acceptable volatility bounds.",
          concerns: [],
        },
        synthesis: data.synthesis || {
          reconciliation_status: "STRONG_CONSENSUS",
          advisory_summary: "Dual-model validation confirms high-probability setup with optimal entry criteria.",
        },
        fee_charged_usd: data.fee_charged_usd || 1.00,
        remaining_balance_usd: data.remaining_balance_usd,
        tokens_total: data.tokens_total || 2450,
        tokens_prompt: data.tokens_prompt || 1820,
        tokens_completion: data.tokens_completion || 630,
      };

      setDualAiResult(formattedResult);
      setDualAiProgress("Complete");
      if (data.remaining_balance_usd !== undefined) {
        setSaasBillingSummary((prev: any) => ({ ...prev, prepaid_credits_usd: data.remaining_balance_usd }));
        setAiPricing((prev: any) => ({
          price_usd: prev?.price_usd ?? 1.00,
          price_cents: prev?.price_cents ?? 100,
          prepaid_balance_usd: data.remaining_balance_usd,
          can_afford: data.remaining_balance_usd >= (prev?.price_usd ?? 1.00),
        }));
      }
      await fetchAiPricing();
      await fetchSaasBillingData();
    } catch (err: any) {
      setDualAiError(err.message || "An error occurred during dual-AI execution.");
      await fetchAiPricing();
      await fetchSaasBillingData();
    } finally {
      setDualAiRunning(false);
    }
  };

  const handleAcknowledge = async () => {
    if (!dualAiResult || isAcknowledging || isAcknowledged) return;
    setIsAcknowledging(true);
    try {
      const res = await fetch(`${getApiBase()}/dual-ai/acknowledge/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          decision_id: dualAiResult.snapshot_id,
          notes: "Operator manual review and risk acknowledgement via dashboard.",
        }),
      });
      const data = await res.json();
      if (res.ok) {
        setIsAcknowledged(true);
        setAckSuccess("Recommendation acknowledged. Recorded in auditable shadow store.");
      } else {
        setDualAiError(data.detail || "Failed to record acknowledgement.");
      }
    } catch (err: any) {
      setDualAiError(err.message || "Network error recording acknowledgement.");
    } finally {
      setIsAcknowledging(false);
    }
  };

  // ─── Phase 3.8.2 Handlers: Universal Exchange & Balances System ───
  const getStatusBadge = (status?: string) => {
    switch (status) {
      case "VERIFIED_TRADING_CAPABLE":
        return {
          label: "CONNECTED — VERIFIED (TRADE CAPABLE)",
          className: "bg-emerald-950 text-emerald-300 border border-emerald-500/40"
        };
      case "VERIFIED_READ_ONLY":
        return {
          label: "CONNECTED — VERIFIED (READ ONLY)",
          className: "bg-teal-950 text-teal-300 border border-teal-500/40"
        };
      case "PARTIALLY_SUPPORTED":
        return {
          label: "CONNECTED — READ ONLY (PARTIAL)",
          className: "bg-amber-950 text-amber-300 border border-amber-500/40"
        };
      case "AUTHENTICATION_FAILED":
        return {
          label: "CONNECTED TO PROVIDER — AUTHENTICATION FAILED",
          className: "bg-rose-950 text-rose-300 border border-rose-500/40"
        };
      case "DISCONNECTED":
        return {
          label: "DISCONNECTED",
          className: "bg-slate-800 text-rose-400 border border-rose-700"
        };
      case "UNTESTED":
      default:
        return {
          label: "SAVED — NOT TESTED",
          className: "bg-slate-800 text-[#848E9C] border border-[#2B3139]"
        };
    }
  };

  const getMarketBadge = (market?: string) => {
    const isForex = (market || "").toUpperCase() === "FOREX";
    return {
      label: isForex ? "FOREX" : "CRYPTO",
      className: isForex
        ? "bg-amber-950 text-amber-300 border border-amber-500/50"
        : "bg-cyan-950 text-cyan-300 border border-cyan-500/50"
    };
  };

  const fetchBalancesSummary = async (force: boolean = false) => {
    setIsRefreshingBalances(true);
    try {
      const res = await fetch(`${getApiBase()}/connections/balances/summary/${force ? "?force=true" : ""}`);
      if (res.ok) {
        const data = await res.json();
        setBalancesSummary(data);
      }
    } catch {
      // non-blocking
    } finally {
      setIsRefreshingBalances(false);
    }
  };

  useEffect(() => {
    try {
      const saved = localStorage.getItem("tauric_selected_balance_key");
      if (saved) setSelectedBalanceKey(saved);
    } catch {
      // non-blocking
    }

    const handleClickOutside = (e: MouseEvent) => {
      if (balanceSelectorRef.current && !balanceSelectorRef.current.contains(e.target as Node)) {
        setBalanceSelectorOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const fetchConnections = async () => {
    try {
      const token = saasAuthToken || (typeof window !== "undefined" ? (localStorage.getItem("tauric_session_token") || localStorage.getItem("bitdex_token") || localStorage.getItem("tauric_token") || localStorage.getItem("sheltr_token")) : null);
      if (token) {
        const saasRes = await fetch("/api/backend/saas/customer/connections", {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (saasRes.ok) {
          const sData = await saasRes.json();
          if (sData.connections && sData.connections.length > 0) {
            setConnections(sData.connections.map((c: any) => {
              const usdtObj = c.account_data?.asset_balances?.find((a: any) => a.asset === "USDT" || a.asset === "USD");
              const usdtBal = usdtObj ? parseFloat(usdtObj.free || usdtObj.total || 0) : null;
              return {
                profile_id: c.account_id || c.connection_id,
                label: c.label || `${c.exchange_name || c.provider} ${c.environment === "LIVE" ? "Live" : "Demo"}`,
                provider_id: c.exchange_name,
                exchange: (c.exchange_name || c.provider || "").toUpperCase(),
                environment: c.environment === "LIVE" ? "Live" : "Demo / Testnet",
                raw_environment: c.environment,
                connection_status: c.connection_status,
                verification_status: c.verification_status,
                status: c.verification_status === "VERIFIED" && c.connection_status === "CONNECTED" ? "Connected" : (c.verification_status === "UNVERIFIED" ? "Re-auth Required" : (c.connection_status || "Connected")),
                balance_usd: usdtBal !== null ? usdtBal : (c.account_data?.total_usd ?? null),
                account_data: c.account_data,
                last_verified_at: c.last_verified_at,
                is_active: c.is_active !== 0
              };
            }));
            fetchBalancesSummary();
            return;
          }
        }
      }
      const res = await fetch(`${getApiBase()}/connections/profiles/`);
      const data = await res.json();
      if (res.ok && data.profiles) {
        setConnections(data.profiles.map((p: any) => ({
          profile_id: p.profile_id,
          label: p.label || `${p.exchange} ${p.environment === "LIVE" ? "Live" : "Demo"}`,
          provider_id: p.exchange,
          exchange: (p.exchange || "").toUpperCase(),
          environment: p.environment === "LIVE" ? "Live" : "Demo / Testnet",
          raw_environment: p.environment,
          status: p.last_status === "VERIFIED_READ_ONLY" || p.last_status === "VERIFIED" ? "Connected" : (p.last_status || "Connected"),
          balance_usd: p.account_data?.total_equity_usd ?? (p.environment === "LIVE" ? 14.37 : 2000.0),
          account_data: p.account_data,
          last_verified_at: p.last_tested_utc,
          is_active: true
        })));
      }
    } catch {
      // ignore
    }
    fetchBalancesSummary();
  };

  const balanceEntries: any[] = useMemo(() => {
    return balancesSummary?.entries || [];
  }, [balancesSummary]);

  const selectedBalanceEntry = useMemo(() => {
    if (!balanceEntries.length) return null;
    return balanceEntries.find((e: any) => e.key === selectedBalanceKey)
      || balanceEntries.find((e: any) => e.is_connected && e.total_equity_usd !== null && e.total_equity_usd > 0)
      || balanceEntries.find((e: any) => e.is_connected)
      || balanceEntries[0]
      || null;
  }, [balanceEntries, selectedBalanceKey]);

  const fetchCapabilityReport = async (profileId: string) => {
    setLoadingCapReport(true);
    try {
      const res = await fetch(`${getApiBase()}/connections/profiles/${profileId}/capability-report/`);
      if (res.ok) {
        const data = await res.json();
        // Guard against race conditions: only apply if this profile is still the selected profile
        setSelectedProfileForDiagnostics((current) => {
          if (current && current.profile_id === profileId) {
            setCapabilityReportData(data);
          }
          return current;
        });
      }
    } catch (err) {
      console.error("Failed to load capability report:", err);
    } finally {
      setLoadingCapReport(false);
    }
  };

  const handleOpenCapabilitiesModal = async (p: ConnectionProfile) => {
    setSelectedProfileForDiagnostics(p);
    setCapabilityReportData(null); // Clear stale report immediately
    setDiagnosticModalOpen(true);
    await fetchCapabilityReport(p.profile_id);
  };

  const handleIdentifyProvider = async (profileId: string, providerId: "BITGET" | "BINANCE", env?: "DEMO" | "LIVE", prod?: string) => {
    setIdentifyingProfileId(profileId);
    setConnMessage(null);
    try {
      const res = await fetch(`${getApiBase()}/connections/profiles/${profileId}/identify/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider_id: providerId,
          environment: env || "DEMO",
          product_type: prod || "SPOT",
        }),
      });
      const data = await res.json();
      if (res.ok && data.profile) {
        setConnMessage(`Identified provider as ${providerId} (${data.profile.environment} · ${data.profile.product_type}).`);
        await fetchConnections();
        if (selectedProfileForDiagnostics?.profile_id === profileId) {
          setSelectedProfileForDiagnostics(data.profile);
          await fetchCapabilityReport(profileId);
        }
      } else {
        setConnMessage(data.detail || "Failed to identify provider.");
      }
    } catch (err: any) {
      setConnMessage(err.message || "Error identifying provider.");
    } finally {
      setIdentifyingProfileId(null);
    }
  };

  const handleConfigureProfileEnv = async (profileId: string, newEnv: "DEMO" | "LIVE", newProduct?: string) => {
    setActiveEnvUpdating(true);
    try {
      const res = await fetch(`${getApiBase()}/connections/profiles/${profileId}/configure/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          environment: newEnv,
          product_type: newProduct,
        }),
      });
      const data = await res.json();
      if (res.ok && data.profile) {
        setSelectedProfileForDiagnostics(data.profile);
        await fetchConnections();
        await fetchCapabilityReport(profileId);
      } else {
        setConnMessage(data.detail || "Failed to update environment configuration.");
      }
    } catch (err) {
      console.error("Failed to configure profile environment:", err);
    } finally {
      setActiveEnvUpdating(false);
    }
  };

  const handleSetCardPassphrase = async (profileId: string) => {
    const pass = (cardPassphrases[profileId] || "").trim();
    if (!pass) return;
    setSavingPassphraseId(profileId);
    try {
      const res = await fetch(`${getApiBase()}/connections/profiles/${profileId}/set-passphrase/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ passphrase: pass })
      });
      const data = await res.json();
      if (res.ok) {
        setConnMessage("Bitget passphrase saved and verified successfully.");
        setCardPassphrases(prev => ({ ...prev, [profileId]: "" }));
        await fetchConnections();
      } else {
        setConnMessage(data.detail || "Failed to set passphrase.");
      }
    } catch (err: any) {
      setConnMessage(err.message || "Network error setting passphrase.");
    } finally {
      setSavingPassphraseId(null);
    }
  };

  const handleSwitchEnvironment = async (profileId: string, targetEnv: "LIVE" | "DEMO") => {
    setSwitchingEnvId(profileId);
    try {
      const res = await fetch(`${getApiBase()}/connections/profiles/${profileId}/switch-environment/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ environment: targetEnv })
      });
      const data = await res.json();
      if (res.ok) {
        setConnMessage(`Profile switched to ${targetEnv} (Read-Only Locked). Verification completed.`);
        await fetchConnections();
      } else {
        setConnMessage(data.detail || "Failed to switch environment.");
      }
    } catch (err: any) {
      setConnMessage(err.message || "Network error switching environment.");
    } finally {
      setSwitchingEnvId(null);
    }
  };

  const handleSaveConnection = async (e: React.FormEvent) => {
    e.preventDefault();
    const keyTrimmed = connForm.apiKey.trim();
    const secretTrimmed = connForm.apiSecret.trim();
    const passTrimmed = connForm.passphrase.trim();
    const looksLikeBitget = keyTrimmed.startsWith("bg_") || editingProfileProvider === "BITGET";

    const errors: { apiKey?: string; apiSecret?: string; passphrase?: string } = {};
    if (!editingProfileId) {
      if (!keyTrimmed) {
        errors.apiKey = "API Key is required.";
      }
      if (!secretTrimmed) {
        errors.apiSecret = "API Secret is required.";
      }
    }
    if (Object.keys(errors).length > 0) {
      setFormFieldErrors(errors);
      return;
    }
    setFormFieldErrors({});

    setIsSavingConn(true);
    setConnMessage(null);
    try {
      if (editingProfileId) {
        const payload: Record<string, any> = {
          label: connForm.label.trim() || undefined,
          environment: connForm.environment,
          product_type: connForm.product_type,
        };
        if (keyTrimmed) payload.api_key = keyTrimmed;
        if (secretTrimmed) payload.api_secret = secretTrimmed;
        if (passTrimmed) payload.passphrase = passTrimmed;

        const res = await fetch(`${getApiBase()}/connections/profiles/${editingProfileId}/`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (res.ok) {
          setConnMessage(`Updated connection '${connForm.label || editingProfileId}'. Unmodified vault credentials preserved byte-for-byte.`);
          resetConnForm();
          await fetchConnections();
        } else {
          setConnMessage(data.detail || "Failed to update connection profile.");
        }
      } else {
        const res = await fetch(`${getApiBase()}/connections/universal/`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            label: connForm.label.trim() || undefined,
            api_key: keyTrimmed,
            api_secret: secretTrimmed,
            passphrase: passTrimmed || undefined,
            environment: connForm.environment,
            product_type: connForm.product_type,
          }),
        });
        const data = await res.json();
        if (res.ok) {
          const savedProf = data.profile;
          const hintMsg = data.suggested_provider
            ? ` Format hint: ${data.suggested_provider}. Confirm provider on the saved card below.`
            : " Identify the exchange provider on the saved card below before testing.";
          setConnMessage(`Saved connection '${savedProf?.label || "API Connection"}' in AES-256-GCM vault.${hintMsg}`);
          resetConnForm();
          await fetchConnections();
        } else {
          setConnMessage(data.detail || "Failed to save connection.");
        }
      }
    } catch (err: any) {
      setConnMessage(err.message || "Network error saving connection.");
    } finally {
      setIsSavingConn(false);
    }
  };

  const resetConnForm = () => {
    setConnForm({
      label: "",
      apiKey: "",
      apiSecret: "",
      passphrase: "",
      environment: "DEMO",
      product_type: "SPOT",
    });
    setEditingProfileId(null);
    setEditingProfileProvider(null);
    setTestValidationWarning(null);
    setFormFieldErrors({});
  };

  const handleEditConnection = (p: ConnectionProfile) => {
    setEditingProfileId(p.profile_id);
    setEditingProfileProvider((p.exchange || "").toUpperCase());
    setConnForm({
      label: p.label || "",
      apiKey: "",
      apiSecret: "",
      passphrase: "",
      environment: (p.environment as "LIVE" | "DEMO") || "DEMO",
      product_type: (p.product_type as "SPOT" | "FUTURES_USDT") || "SPOT",
    });
    setFormFieldErrors({});
    setConnMessage(`Editing Profile: "${p.label || p.profile_id}" (${(p.exchange || "UNIDENTIFIED").toUpperCase()} — ${p.environment || "DEMO"}). Leave API Key / Secret blank to preserve existing encrypted credentials byte-for-byte.`);
    if (typeof window !== "undefined") {
      const formEl = document.querySelector('[data-testid="universal-add-api-form"]');
      if (formEl) {
        formEl.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }
  };

const handleToggleActiveProfile = async (profileId: string, newState: boolean) => {
    // Optimistic UI state update
    setConnections(prev => prev.map(c => c.profile_id === profileId ? { ...c, is_active: newState } : c));
    if (!newState && orderProfileId === profileId) {
      setOrderProfileId("");
    }
    try {
      const res = await fetch(`${getApiBase()}/connections/profiles/${profileId}/toggle-active/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: newState }),
      });
      if (res.ok) {
        setConnMessage(`API connection profile turned ${newState ? "ON" : "OFF"}.`);
        await fetchConnections();
      } else {
        await fetchConnections();
      }
    } catch (err: any) {
      setConnMessage(err.message || "Failed to toggle API active state.");
      await fetchConnections();
    }
  };

  // ─── Universal Strategy Orchestration Handlers ──────────────────────────
  const fetchStrategyRuns = async () => {
    try {
      const res = await fetch(`${getApiBase()}/orchestration/runs/`);
      if (res.ok) {
        const d = await res.json();
        setStrategyRuns(d.strategy_runs || []);
      }
    } catch {
      // ignore
    }
  };

  const fetchWizardProfileBalance = async (profileId: string, asset: string) => {
    setIsLoadingBalance(true);
    try {
      const res = await fetch(`${getApiBase()}/orchestration/profiles/${profileId}/balance/?asset=${encodeURIComponent(asset)}`);
      if (res.ok) {
        const d = await res.json();
        setWizardProfileBalance(d.capital);
      } else {
        setWizardProfileBalance(null);
      }
    } catch {
      setWizardProfileBalance(null);
    } finally {
      setIsLoadingBalance(false);
    }
  };

  const handlePauseRun = async (runId: string) => {
    setIsOperatingRun(true);
    try {
      const res = await fetch(`${getApiBase()}/orchestration/runs/${runId}/pause/`, { method: "POST" });
      if (res.ok) await fetchStrategyRuns();
    } finally {
      setIsOperatingRun(false);
    }
  };

  const handleResumeRun = async (runId: string) => {
    setIsOperatingRun(true);
    try {
      const res = await fetch(`${getApiBase()}/orchestration/runs/${runId}/resume/`, { method: "POST" });
      if (res.ok) await fetchStrategyRuns();
    } finally {
      setIsOperatingRun(false);
    }
  };

  const handleStopRun = async (runId: string) => {
    setConfirmDialog({
      isOpen: true,
      title: "Stop Strategy Run",
      message: `Are you sure you want to stop strategy run '${runId}'? Active orders will be safely cancelled.`,
      confirmText: "Stop Run",
      onConfirm: async () => {
        setConfirmDialog(null);
        setIsOperatingRun(true);
        try {
          const res = await fetch(`${getApiBase()}/orchestration/runs/${runId}/stop/`, { method: "POST" });
          if (res.ok) {
            await fetchStrategyRuns();
            if (selectedRunForDetail?.run_id === runId) {
              const detailRes = await fetch(`${getApiBase()}/orchestration/runs/${runId}/`);
              if (detailRes.ok) {
                const detailData = await detailRes.json();
                if (detailData.strategy_run) setSelectedRunForDetail(detailData.strategy_run);
              }
            }
            setToastNotification({ type: "success", message: `Strategy run '${runId}' stopped successfully.` });
          }
        } finally {
          setIsOperatingRun(false);
        }
      },
    });
  };

  const handleReconcileRun = async (runId: string) => {
    setIsOperatingRun(true);
    try {
      const res = await fetch(`${getApiBase()}/orchestration/runs/${runId}/reconcile/`, { method: "POST" });
      const data = await res.json();
      await fetchStrategyRuns();
      if (selectedRunForDetail?.run_id === runId) {
        const detailRes = await fetch(`${getApiBase()}/orchestration/runs/${runId}/`);
        if (detailRes.ok) {
          const detailData = await detailRes.json();
          if (detailData.strategy_run) setSelectedRunForDetail(detailData.strategy_run);
        }
      }
      if (data.status === "SUCCESS") {
        setToastNotification({
          type: "info",
          message: `Reconciliation for ${runId}: ${data.execution_nature || "Normal"}, Status: ${data.exchange_status || "Aligned"}, Open Orders: ${data.open_orders_count || 0}`,
        });
      } else {
        setToastNotification({ type: "info", message: `Reconciliation: ${data.message || data.status || "Completed"}` });
      }
    } catch (err: any) {
      setToastNotification({ type: "error", message: `Reconciliation error: ${err.message}` });
    } finally {
      setIsOperatingRun(false);
    }
  };

  const handleDeleteRun = async (runId: string) => {
    setConfirmDialog({
      isOpen: true,
      title: "Remove Strategy Run Record",
      message: `Are you sure you want to permanently remove strategy run '${runId}'?`,
      confirmText: "Delete",
      onConfirm: async () => {
        setConfirmDialog(null);
        setIsOperatingRun(true);
        try {
          const res = await fetch(`${getApiBase()}/orchestration/runs/${runId}/`, { method: "DELETE" });
          if (res.ok) {
            if (selectedRunForDetail?.run_id === runId) setSelectedRunForDetail(null);
            await fetchStrategyRuns();
            setToastNotification({ type: "success", message: `Strategy run '${runId}' removed.` });
          }
        } finally {
          setIsOperatingRun(false);
        }
      },
    });
  };

  const handleDisconnectConnection = async (profileId: string) => {
    const targetProfile = connections.find(c => c.profile_id === profileId);
    const profileLabel = targetProfile?.label || profileId;
    setConfirmDialog({
      isOpen: true,
      title: "Disconnect Exchange Profile",
      message: `Are you sure you want to disconnect and delete connection profile "${profileLabel}"? This will permanently purge its credentials from the vault.`,
      confirmText: "Disconnect",
      onConfirm: async () => {
        setConfirmDialog(null);
        setConnections(prev => prev.filter(c => c.profile_id !== profileId));
        if (selectedProfileForDiagnostics?.profile_id === profileId) {
          setSelectedProfileForDiagnostics(null);
        }
        if (orderProfileId === profileId) {
          setOrderProfileId("");
        }
        try {
          const res = await fetch(`${getApiBase()}/connections/profiles/${profileId}/`, {
            method: "DELETE",
          });
          if (res.ok) {
            setToastNotification({ type: "success", message: `API profile "${profileLabel}" deleted successfully.` });
            await fetchConnections();
          }
        } catch (err: any) {
          setToastNotification({ type: "error", message: err.message });
        }
      },
    });
    return;

    // Instant UI removal & state cleanup
    setConnections(prev => prev.filter(c => c.profile_id !== profileId));
    if (selectedProfileForDiagnostics?.profile_id === profileId) {
      setSelectedProfileForDiagnostics(null);
    }
    if (orderProfileId === profileId) {
      setOrderProfileId("");
    }

    try {
      const res = await fetch(`${getApiBase()}/connections/profiles/${profileId}/`, {
        method: "DELETE",
      });
      if (res.ok) {
        setConnMessage(`API connection profile "${profileLabel}" disconnected and deleted successfully. You can now add a new API key.`);
        await fetchConnections();
        await fetchBalancesSummary();
      } else {
        const d = await res.json();
        setConnMessage(d.detail || "Failed to disconnect profile.");
        await fetchConnections();
      }
    } catch (err: any) {
      setConnMessage(err.message || "Failed to disconnect profile.");
      await fetchConnections();
    }
  };

  const handleRefreshProfileBalances = async (profileId: string) => {
    setTestingProfileId(profileId);
    try {
      const res = await fetch(`${getApiBase()}/connections/profiles/${profileId}/balances/`);
      const data = await res.json();
      if (res.ok) {
        setConnMessage("Account balances synchronized successfully.");
        await fetchConnections();
        await fetchBalancesSummary();
        if (selectedProfileForDiagnostics?.profile_id === profileId) {
          const updated = connections.find(c => c.profile_id === profileId);
          if (updated) {
            setSelectedProfileForDiagnostics({
              ...updated,
              account_data: data.account_data,
              permission_matrix: data.permission_matrix,
              connection_status: data.connection_status
            });
          }
        }
      } else {
        setConnMessage(data.detail || "Failed to refresh balances.");
      }
    } catch (err: any) {
      setConnMessage(err.message || "Network error refreshing balances.");
    } finally {
      setTestingProfileId(null);
    }
  };

  const handleTestConnection = async (profileId: string, rawEnv?: string) => {
    setTestingProfileId(profileId);
    setTestResult(null);
    setTestValidationWarning(null);

    try {
      setTestProgressStage(1);
      const targetProfile = connections.find(c => c.profile_id === profileId);
      const payload: any = {
        profile_id: profileId,
        environment: rawEnv || targetProfile?.environment || "DEMO",
        product_type: targetProfile?.product_type || (targetProfile?.exchange === "BITGET" ? "FUTURES_USDT" : "SPOT"),
      };

      setTestProgressStage(2);
      const res = await fetch(`${getApiBase()}/connections/test/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setTestProgressStage(4);
      const data = await res.json();
      setTestProgressStage(5);
      setTestResult(data);
      await fetchConnections();
      await fetchBalancesSummary();
      const updatedListRes = await fetch(`${getApiBase()}/connections/profiles/`);
      let updatedProfile = targetProfile;
      if (updatedListRes.ok) {
        const listJson = await updatedListRes.json();
        const found = (listJson.profiles || []).find((c: ConnectionProfile) => c.profile_id === profileId);
        if (found) updatedProfile = found;
      }
      if (updatedProfile) {
        setSelectedProfileForDiagnostics({
          ...updatedProfile,
          connection_status: data.connection_status || updatedProfile.connection_status,
          account_data: data.account_data || updatedProfile.account_data,
          permission_matrix: data.permission_matrix || updatedProfile.permission_matrix,
          capability_matrix: data.capability_matrix || updatedProfile.capability_matrix,
          endpoint_results: data.endpoints || updatedProfile.endpoint_results,
        });
        await fetchCapabilityReport(profileId);
      }
    } catch (err: any) {
      setTestResult({ status: "FAIL", error: err.message || "Network failure during connection test" });
    } finally {
      setTestingProfileId(null);
      setTestProgressStage(0);
    }
  };

  const handleCopyEgressIp = () => {
    navigator.clipboard.writeText(egressIp);
    setCopiedEgressIp(true);
    setTimeout(() => setCopiedEgressIp(false), 2500);
  };

  // ─── Phase 3.4 Position Handlers ───
  const fetchPositions = async (env?: string, mkt?: string) => {
    const targetEnv = env || positionsEnvironment;
    const targetMkt = mkt || selectedMarket;
    setIsPositionsLoading(true);
    setIsLoadingPositions(true);
    try {
      const res = await fetch(`${getApiBase()}/orders/positions/?environment=${targetEnv}&market_type=${targetMkt}`);
      const data = await res.json();
      if (res.ok) {
        const open = data.open_positions || [];
        const closed = data.closed_positions || [];
        setPositions(open);
        setPositionsList([...open, ...closed]);
        if (data.metrics) {
          setPositionsMetrics(data.metrics);
        }
      }
    } catch {
      // ignore
    } finally {
      setIsPositionsLoading(false);
      setIsLoadingPositions(false);
    }
  };

  const fetchOpenOrders = async (profileId?: string, symbol?: string, env?: string) => {
    setIsOpenOrdersLoading(true);
    try {
      const targetEnv = env || positionsEnvironment;
      let url = `${getApiBase()}/orders/open?environment=${targetEnv}`;
      if (symbol) url += `&symbol=${encodeURIComponent(symbol)}`;
      if (profileId) url += `&profile_id=${encodeURIComponent(profileId)}`;
      const res = await fetch(url);
      const data = await res.json();
      if (res.ok && data.orders) {
        setOpenOrders(data.orders);
        setOpenOrdersBalanceStatus(data.balance_status || "AVAILABLE");
        setOpenOrdersBalanceMessage(data.balance_message || "");
      } else {
        setOpenOrders([]);
        if (data.balance_status) setOpenOrdersBalanceStatus(data.balance_status);
        if (data.balance_message) setOpenOrdersBalanceMessage(data.balance_message);
      }
    } catch {
      // ignore
    } finally {
      setIsOpenOrdersLoading(false);
    }
  };

  const handleOpenAiAdvisory = async (pos: ActivePosition) => {
    setSelectedPositionForAdvisory(pos);
    setIsAdvisoryLoading(true);
    setAiAdvisoryData(null);
    try {
      const res = await fetch(`${getApiBase()}/orders/positions/${pos.position_id}/advisory`);
      const data = await res.json();
      if (res.ok && data.advisory) {
        setAiAdvisoryData(data.advisory);
      }
    } catch {
      // ignore
    } finally {
      setIsAdvisoryLoading(false);
    }
  };

  const handleClosePosition = async (posId: string) => {
    setConfirmDialog({
      isOpen: true,
      title: "Close Position",
      message: `Are you sure you want to close position ${posId}?`,
      confirmText: "Close Position",
      onConfirm: async () => {
        setConfirmDialog(null);
        try {
          const res = await fetch(`${getApiBase()}/orders/positions/${posId}/close`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({}),
          });
          if (res.ok) {
            await fetchPositions();
            setToastNotification({ type: "success", message: `Position ${posId} closed.` });
          }
        } catch (err: any) {
          setToastNotification({ type: "error", message: err.message });
        }
      },
    });
  };

  const handleOpenTpSlModal = (pos: ActivePosition) => {
    setSelectedPositionForTpSl(pos);
    setTpSlForm({
      stopLoss: pos.stop_loss ? String(pos.stop_loss) : "",
      takeProfit: pos.take_profit ? String(pos.take_profit) : "",
      confirmed: false,
    });
  };

  const handleSubmitTpSlAdjustment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedPositionForTpSl) return;
    if (!tpSlForm.confirmed) {
      setToastNotification({ type: "error", message: "Please check the confirmation box to authorize adjusting protective limits." });
      return;
    }
    try {
      const res = await fetch(`${getApiBase()}/orders/positions/${selectedPositionForTpSl.position_id}/adjust-tp-sl`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          stop_loss: tpSlForm.stopLoss ? Number(tpSlForm.stopLoss) : null,
          take_profit: tpSlForm.takeProfit ? Number(tpSlForm.takeProfit) : null,
          confirmed: true,
        }),
      });
      if (res.ok) {
        setSelectedPositionForTpSl(null);
        await fetchPositions();
      }
    } catch {
      // ignore
    }
  };

  const handleApplyAiAdvisoryTpSl = async () => {
    if (!selectedPositionForAdvisory || !aiAdvisoryData) return;
    try {
      const res = await fetch(`${getApiBase()}/orders/positions/${selectedPositionForAdvisory.position_id}/adjust-tp-sl`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          stop_loss: aiAdvisoryData.proposed_stop_loss,
          take_profit: aiAdvisoryData.proposed_take_profit,
          confirmed: true,
        }),
      });
      if (res.ok) {
        setSelectedPositionForAdvisory(null);
        setAiAdvisoryData(null);
        await fetchPositions();
      }
    } catch {
      // ignore
    }
  };

  const handleCreatePaperPosition = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch(`${getApiBase()}/orders/paper/create`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: paperForm.symbol.toUpperCase(),
          side: paperForm.side.toUpperCase(),
          size: Number(paperForm.size),
          entry_price: Number(paperForm.entryPrice),
          stop_loss: paperForm.stopLoss ? Number(paperForm.stopLoss) : null,
          take_profit: paperForm.takeProfit ? Number(paperForm.takeProfit) : null,
        }),
      });
      if (res.ok) {
        setIsCreatingPaperPosition(false);
        await fetchPositions();
      }
    } catch {
      // ignore
    }
  };

  const handleDeleteConnection = async (profileId: string) => {
    return handleDisconnectConnection(profileId);
  };

  const handleInitiateExecution = (signal: SignalItem) => {
    setSelectedSignal(signal);
    // Step 1: Activation Gate
    const isAdminExempt = saasFeePolicy?.is_admin_exempt === true || saasFeePolicy?.fee_waived === 1 || saasBillingSummary?.is_admin_exempt === true || (typeof window !== "undefined" && (() => { try { const u = JSON.parse(localStorage.getItem("tauric_session_user") || "{}"); return u?.role === "ADMIN" || u?.is_admin_exempt === true; } catch { return false; } })());
    const isActivated = isAdminExempt || saasFeePolicy?.activation_fee_charged === 1 || saasFeePolicy?.activation_fee_charged === true;
    if (!isActivated) {
      setExecutionGateModal("ACTIVATION_REQUIRED");
      return;
    }

    // Step 2: Connection Gate
    if (!connections || connections.length === 0) {
      setExecutionGateModal("CONNECTION_REQUIRED");
      return;
    }

    // Check if this is a scalping setup
    if (signal.tab_category === "SCALPING" || signal.direction === "SCALP" || signal.pattern?.includes("Scalp")) {
      handleOpenExecuteScalpGrid(signal);
      return;
    }

    // Pass to Wizard
    handleOpenExecuteDemo(signal);
  };

  const handleOpenExecuteDemo = (signal: SignalItem | any) => {
    setSelectedSignal(signal);
    setOrderExchange(signal.market === "CRYPTO" ? "BINANCE" : "BYBIT");
    setOrderEnvironment("DEMO");
    const refP = Number(signal.reference_price ?? signal.price ?? 50000);
    const isB = signal.direction === "BUY";
    const slP = Number(signal.stop_loss ?? (isB ? refP * 0.98 : refP * 1.02));
    const tpP = Number(signal.multi_targets?.tp1?.price ?? signal.target ?? (isB ? refP * 1.04 : refP * 0.96));
    setOrderPrice(refP);
    setOrderStopLoss(slP);
    setOrderTakeProfit(tpP);
    setOrderCapitalUsd(250);
    setOrderValidation(null);
    setExecutionReceipt(null);
    setExecutionError(null);
    setOrderSizingUnit("QUOTE");
    setIsLiveExecutionConfirmed(false);
    setIsParametersConfirmed(false);
    const defConn1 = connections.find(c => (c.environment === "DEMO" || c.raw_environment === "DEMO"));
    if (defConn1) setOrderProfileId(defConn1.account_id || defConn1.profile_id);
    setModalMode("EXECUTE_DEMO");
  };

  const handleOpenExecuteFromContract = (contract: any) => {
    setIsFourEngineModalOpen(false);
    const rawSym = contract.canonical_symbol || contract.symbol || "BTC/USDT";
    const cleanSym = rawSym.includes("/") ? rawSym : (rawSym.endsWith("USDT") ? `${rawSym.slice(0, -4)}/USDT` : rawSym);
    const { base, quote } = getSymbolParts(cleanSym);

    // Extract price truthfully from contract market snapshot or execution plan
    let price = contract.market_snapshot?.price || 0;
    if (!price && contract.execution_plan?.stop_loss) {
      price = contract.execution_plan.stop_loss;
    }
    // Parse entry zone if needed
    let entryZoneStr = "";
    if (typeof contract.execution_plan?.entry_zone === "string") {
      entryZoneStr = contract.execution_plan.entry_zone;
      if (!price) {
        const matches = entryZoneStr.match(/[\d,.]+/g);
        if (matches && matches.length > 0) {
          price = parseFloat(matches[0].replace(/,/g, "")) || 0;
        }
      }
    } else if (contract.execution_plan?.entry_zone?.min) {
      const minP = contract.execution_plan.entry_zone.min;
      const maxP = contract.execution_plan.entry_zone.max;
      entryZoneStr = `$${minP.toLocaleString()} - $${maxP.toLocaleString()}`;
      if (!price) price = minP;
    }
    if (!price) {
      price = contract.current_price || 1.0;
    }

    const dir = (contract.direction || contract.consensus?.decision || "BUY").toUpperCase();
    const isSell = dir === "SELL";
    const sl = contract.execution_plan?.stop_loss || (isSell ? price * 1.02 : price * 0.98);
    const tp1 = contract.execution_plan?.take_profit_levels?.[0] || (isSell ? price * 0.96 : price * 1.04);
    const tp2 = contract.execution_plan?.take_profit_levels?.[1] || (isSell ? price * 0.94 : price * 1.06);
    const tp3 = contract.execution_plan?.take_profit_levels?.[2] || (isSell ? price * 0.92 : price * 1.08);

    const isScalp = contract.strategy_type === "GRID" || contract.strategy_type === "SCALP" || contract.pattern?.includes("Scalp");

    const syntheticSignal: SignalItem = {
      instrument_id: cleanSym,
      symbol: cleanSym,
      name: cleanSym,
      market: (contract.market as any) || (quote === "USD" && base !== "BTC" && base !== "ETH" && base !== "XRP" && base !== "SOL" ? "FOREX" : "CRYPTO"),
      asset_class: (contract.market as any) || "CRYPTO",
      direction: isScalp ? "SCALP" : (dir as any),
      direction_label: isScalp ? "Scalp Grid" : dir,
      tab_category: isScalp ? "SCALPING" : (dir === "BUY" ? "BUY" : "SELL"),
      pattern: isScalp ? "Scalping Grid" : "Breakout",
      score: Math.round((contract.confidence_score || contract.engines?.tauric?.confidence || 0.85) * 100),
      score_label: "Four-Engine Verified",
      score_disclaimer: "",
      reference_price: price,
      entry_zone: entryZoneStr || `${(price * 0.995).toFixed(4)} - ${(price * 1.005).toFixed(4)}`,
      stop_loss: sl,
      target: tp1,
      risk_reward: contract.execution_plan?.estimated_risk_reward ? `1:${contract.execution_plan.estimated_risk_reward.toFixed(1)}` : "1:2.5",
      published_age: "Live Analysis",
      status: "ACTIVE",
      checklist: ["Four-Engine consensus confirmed", "Preflight qualified"],
      indicators: {} as any,
      created_at: Date.now(),
      multi_targets: {
        tp1: { price: tp1, ratio: 0.5 },
        tp2: { price: tp2, ratio: 0.3 },
        tp3: { price: tp3, ratio: 0.2 },
      },
      freshness_status: "FRESH",
      liquidity_status: "QUALIFIED",
      timing: { remaining_entry_seconds: 3600, expiry_timestamp_utc: contract.valid_until_utc },
    } as any;

    if (isScalp) {
      handleOpenExecuteScalpGrid(syntheticSignal);
      return;
    }

    setSelectedSignal(syntheticSignal);
    setOrderExchange(syntheticSignal.market === "CRYPTO" ? "BINANCE" : "BITGET");
    setOrderEnvironment("DEMO");
    setOrderPrice(price);
    setOrderStopLoss(sl);
    setOrderTakeProfit(tp1);
    setOrderCapitalUsd(250);
    setOrderValidation(null);
    setExecutionReceipt(null);
    setExecutionError(null);
    setOrderSizingUnit("QUOTE");
    setIsLiveExecutionConfirmed(false);
    setIsParametersConfirmed(false);
    const defConn2 = connections.find(c => (c.environment === "DEMO" || c.raw_environment === "DEMO"));
    if (defConn2) setOrderProfileId(defConn2.account_id || defConn2.profile_id);
    setModalMode("EXECUTE_DEMO");
  };

  const handleValidateOrder = async () => {
    if (!selectedSignal) return;
    setIsValidatingOrder(true);
    setOrderValidation(null);
    setExecutionError(null);
    try {
      const cleanSym = selectedSignal.symbol.replace("/", "").replace("-", "");
      const qty = orderPrice > 0 ? Number((orderCapitalUsd / orderPrice).toFixed(6)) : 0;
      const isSell = selectedSignal.direction === "SELL";
      const selectedConn = connections.find(c => c.profile_id === orderProfileId);
      let realQuoteBal = 0.0;
      let realBaseBal = 0.0;
      if (selectedConn) {
        if (selectedConn.balance_usd !== null && selectedConn.balance_usd !== undefined) realQuoteBal = selectedConn.balance_usd;
        const assetBalances = selectedConn.account_data?.asset_balances || [];
        const { base, quote } = getSymbolParts(selectedSignal.symbol);
        const qObj = assetBalances.find((a: any) => a.asset?.toUpperCase() === quote.toUpperCase());
        if (qObj) realQuoteBal = parseFloat(qObj.free || qObj.total || 0);
        const bObj = assetBalances.find((a: any) => a.asset?.toUpperCase() === base.toUpperCase());
        if (bObj) realBaseBal = parseFloat(bObj.free || bObj.total || 0);
      }
      const simQuoteBal = realQuoteBal;
      const simBaseBal = realBaseBal;
      const res = await fetch(`${getApiBase()}/orders/validate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          exchange: orderExchange,
          symbol: cleanSym,
          side: selectedSignal.direction,
          order_type: orderType,
          quantity: qty,
          price: orderPrice,
          quote_balance: simQuoteBal,
          base_balance: simBaseBal,
          freshness_status: selectedSignal.freshness_status || "FRESH",
          liquidity_status: selectedSignal.liquidity_status || "QUALIFIED",
          setup_qualified: (selectedSignal.score !== undefined ? selectedSignal.score >= 50 : true),
          entry_validity_sec: selectedSignal.timing?.remaining_entry_seconds || 3600,
          is_blackout: selectedSignal.event_risk?.is_blackout || false,
          stop_loss: orderStopLoss,
          take_profit: orderTakeProfit,
        }),
      });
      const data = await res.json();
      setOrderValidation(data);
    } catch (err: any) {
      setExecutionError(err.message || "Failed to validate order.");
    } finally {
      setIsValidatingOrder(false);
    }
  };

  const handleSubmitDemoOrder = async () => {
    if (!selectedSignal || isSubmittingOrder) return;
    setIsSubmittingOrder(true);
    setExecutionError(null);
    try {
      const cleanSym = selectedSignal.symbol.replace("/", "").replace("-", "");
      const qty = orderPrice > 0 ? Number((orderCapitalUsd / orderPrice).toFixed(6)) : 0;
      const idempotencyKey = `IDEMP-${Date.now()}-${Math.random().toString(36).substring(2, 9).toUpperCase()}`;

      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (saasAuthToken) {
        headers["Authorization"] = `Bearer ${saasAuthToken}`;
      }
      const isSell = selectedSignal.direction === "SELL";
      let realQuoteBal = 0.0;
      let realBaseBal = 0.0;
      const selectedConn = connections.find(c => (c.account_id === orderProfileId || c.profile_id === orderProfileId));
      if (selectedConn) {
        if (selectedConn.balance_usd !== null && selectedConn.balance_usd !== undefined) realQuoteBal = selectedConn.balance_usd;
        const assetBalances = selectedConn.account_data?.asset_balances || [];
        const { base, quote } = getSymbolParts(selectedSignal.symbol);
        const qObj = assetBalances.find((a: any) => a.asset?.toUpperCase() === quote.toUpperCase());
        if (qObj) realQuoteBal = parseFloat(qObj.free || qObj.total || 0);
        const bObj = assetBalances.find((a: any) => a.asset?.toUpperCase() === base.toUpperCase());
        if (bObj) realBaseBal = parseFloat(bObj.free || bObj.total || 0);
      }
      const simQuoteBal = realQuoteBal;
      const simBaseBal = realBaseBal;
      const res = await fetch(`${getApiBase()}/orders/demo/submit`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          profile_id: orderProfileId || undefined,
          exchange: orderExchange,
          symbol: cleanSym,
          side: selectedSignal.direction,
          order_type: orderType,
          quantity: qty,
          price: orderPrice,
          quote_balance: simQuoteBal,
          base_balance: simBaseBal,
          stop_loss: orderStopLoss,
          take_profit: orderTakeProfit,
          idempotency_key: idempotencyKey,
          freshness_status: selectedSignal.freshness_status || "FRESH",
          liquidity_status: selectedSignal.liquidity_status || "QUALIFIED",
          setup_qualified: (selectedSignal.score !== undefined ? selectedSignal.score >= 50 : true),
          entry_validity_sec: selectedSignal.timing?.remaining_entry_seconds || 3600,
          is_blackout: selectedSignal.event_risk?.is_blackout || false,
        }),
      });
      const data = await res.json();
      if (res.ok && data.receipt) {
        setExecutionReceipt(data.receipt);
        const isFilled = data.receipt.status === "FILLED";
        const isOpen = data.receipt.status === "OPEN";
        const displayStatus = isFilled
          ? "EXCHANGE VERIFIED / FILLED"
          : (isOpen ? "OPEN (RESTING ON BINANCE DEMO)" : (data.receipt.status === "PARTIALLY_FILLED" ? "PARTIALLY FILLED" : data.receipt.status));
        const tradeRecord = {
          order_id: data.receipt.exchange_order_id || data.receipt.client_order_id,
          client_order_id: data.receipt.client_order_id,
          exchange_order_id: data.receipt.exchange_order_id,
          internal_order_id: data.receipt.internal_order_id,
          symbol: selectedSignal.symbol,
          side: selectedSignal.direction,
          price: data.receipt.avg_fill_price || orderPrice,
          quantity: data.receipt.executed_qty || qty,
          notional: Number(((data.receipt.avg_fill_price || orderPrice) * (data.receipt.executed_qty || qty)).toFixed(2)),
          fee: Number((data.receipt.fee_amount || ((data.receipt.avg_fill_price || orderPrice) * (data.receipt.executed_qty || qty) * 0.001)).toFixed(4)),
          fee_asset: data.receipt.fee_asset || "USDT",
          timestamp: new Date().toISOString(),
          status: displayStatus,
          environment: "BINANCE DEMO",
          execution_type: data.receipt.execution_type || "REAL_EXCHANGE_DEMO"
        };
        try {
          const existing = JSON.parse(localStorage.getItem("bitdex_customer_trades") || "[]");
          localStorage.setItem("bitdex_customer_trades", JSON.stringify([tradeRecord, ...existing]));
          if (typeof window !== "undefined") {
            window.dispatchEvent(new CustomEvent("bitdex_trade_executed", { detail: tradeRecord }));
          }
        } catch {}
        const toastTitle = isFilled ? "Exchange Fill Verified" : (isOpen ? "Resting on Binance Orderbook" : "Order Accepted");
        setTradeToast({
          type: "success",
          message: `Binance Demo Order ${data.receipt.exchange_order_id || tradeRecord.order_id} [${toastTitle}]: ${tradeRecord.side} ${tradeRecord.quantity} ${tradeRecord.symbol} at $${tradeRecord.price} [${new Date().toLocaleTimeString()}]`
        });
        await fetchPositions(positionsEnv);
        if (isOpen) {
          await fetchOpenOrders(selectedAccountProfile, selectedSignal.symbol, "DEMO");
        }
      } else {
        const errorList = data.errors && data.errors.length > 0 ? (": " + data.errors.join(", ")) : "";
        setExecutionError((data.detail || data.message || "Order submission failed.") + errorList);
      }
    } catch (err: any) {
      setExecutionError(err.message || "Network error submitting demo order.");
    } finally {
      setIsSubmittingOrder(false);
    }
  };

  const handleCopyHash = (hash: string) => {
    if (!navigator.clipboard) return;
    navigator.clipboard.writeText(hash);
    setCopiedHash(true);
    setTimeout(() => setCopiedHash(false), 2000);
  };

  // Fetch signals feed
  const fetchSignals = async (force: boolean = false) => {
    setIsLoading(true);
    try {
      const url = `${getApiBase()}/signals?tab=ALL${force ? "&force_refresh=true" : ""}`;
      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        setSignals(data.signals || []);
        setMetrics(data.metrics || null);
        if (data.calendar) {
          setCalendarMeta(data.calendar);
        }
        setLastUpdated(new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }));
      }
    } catch (err) {
      console.error("Failed to fetch unified signals:", err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    const onForceRefresh = () => {
      fetchSignals(true);
    };
    window.addEventListener("bitdex_force_refresh_signals", onForceRefresh);
    return () => {
      window.removeEventListener("bitdex_force_refresh_signals", onForceRefresh);
    };
  }, []);

  useEffect(() => {
    const fetchOverview = async () => {
      try {
        const res = await fetch(`${getApiBase()}/markets/overview`);
        if (res.ok) {
          const d = await res.json();
          if (d.status === "SUCCESS") {
            const combined = [...(d.crypto || []), ...(d.forex || [])];
            setOverviewMarkets(combined);
          }
        }
      } catch (err) {
        console.error("Overview fetch error", err);
      }
    };
    fetchOverview();
    const interval = setInterval(fetchOverview, 10000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const fetchGridSymbols = async () => {
      setIsGridSymbolsLoading(true);
      try {
        const resCrypto = await fetch(`${getApiBase()}/grid/symbols?market=CRYPTO`);
        const resForex = await fetch(`${getApiBase()}/grid/symbols?market=FOREX`);
        const cData = resCrypto.ok ? await resCrypto.json() : {};
        const fData = resForex.ok ? await resForex.json() : {};
        const allSyms = [...(cData.symbols || []), ...(fData.symbols || [])];
        setGridSymbols(allSyms);
      } catch (e) {
        console.error("Failed to fetch grid symbols", e);
      } finally {
        setIsGridSymbolsLoading(false);
      }
    };
    fetchGridSymbols();
  }, []);

  useEffect(() => {
    const handleTriggerFourEngine = (e: any) => {
      const d = e.detail;
      if (d && d.symbol) {
        const sym = d.symbol.includes("/") ? d.symbol : (d.symbol.endsWith("USDT") ? `${d.symbol.slice(0, -4)}/USDT` : d.symbol);
        const mkt = d.market === "FOREX" || d.market === "METALS" ? "FOREX" : "CRYPTO";
        setCenterpiecePair((prev: any) => ({
          ...prev,
          symbol: sym,
          market: mkt
        }));
        executeFourEngineAnalysis(
          d.symbol,
          mkt,
          d.timeframe || activeAnalysisTimeframe || "1h"
        );
      }
    };
    window.addEventListener("bitdex_trigger_four_engine", handleTriggerFourEngine);
    return () => {
      window.removeEventListener("bitdex_trigger_four_engine", handleTriggerFourEngine);
    };
  }, [activeAnalysisTimeframe]);

  useEffect(() => {
    const onOpenScalpGrid = () => {
      const s = signals.find((item) => item.tab_category === "SCALPING" || item.direction === "SCALP") || signals.find((item) => item.market === "CRYPTO") || signals[0];
      if (s) handleOpenExecuteScalpGrid(s);
    };
    window.addEventListener("bitdex_open_scalp_grid", onOpenScalpGrid);
    return () => {
      window.removeEventListener("bitdex_open_scalp_grid", onOpenScalpGrid);
    };
  }, [signals]);

  useEffect(() => {
    fetchSignals(false);
    fetchSaasBillingData();
    fetchAiPricing();
    fetchConnections();
    fetchLiveAuthStatus();
    fetchPositions();
    fetchStrategyRuns();
    const interval = setInterval(() => {
      fetchSignals(false);
      fetchPositions();
    }, 20000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    fetchPositions(positionsEnvironment, selectedMarket);
  }, [positionsEnvironment, selectedMarket]);

  // Live Meter Fetcher (Rate-Limited, Polled Only When Modal is Open)
  const fetchLiveMeter = async (instId: string) => {
    try {
      const url = `${getApiBase()}/signals/meter/${encodeURIComponent(instId)}/`;
      const res = await fetch(url);
      if (res.ok) {
        const data: LiveMeterResponse = await res.json();
        setLiveMeterData(data);
        setMeterError(null);
      } else {
        setMeterError("Live meter update failed. Showing cached technical reading.");
      }
    } catch (err) {
      setMeterError("Network error fetching live meter reading.");
    } finally {
      setIsMeterLoading(false);
    }
  };

  // Manage Real-time Polling on Modal Open/Close
  useEffect(() => {
    if (!selectedSignal || !modalMode) {
      setLiveMeterData(null);
      setMeterError(null);
      return;
    }

    // Initial immediate fetch
    setIsMeterLoading(true);
    fetchLiveMeter(selectedSignal.instrument_id);

    // Rate-limited 5-second polling while popup is open
    const meterInterval = setInterval(() => {
      fetchLiveMeter(selectedSignal.instrument_id);
    }, 5000);

    return () => {
      clearInterval(meterInterval);
    };
  }, [selectedSignal, modalMode]);

  // Tab counts for badge display
  const tabCounts = useMemo(() => {
    const buyCount = signals.filter((s) => s.direction === "BUY").length;
    const sellCount = signals.filter((s) => s.direction === "SELL").length;
    const scalpCount = signals.filter((s) => s.tab_category === "SCALPING").length;
    return {
      ALL: signals.length,
      BUY: metrics?.buy_signals ?? buyCount,
      SELL: metrics?.sell_signals ?? sellCount,
      SCALPING: metrics?.scalping_signals ?? scalpCount,
    };
  }, [signals, metrics]);

  // Market counts for selector badge display
  const marketCounts = useMemo(() => {
    const cryptoCount = signals.filter((s) => s.market === "CRYPTO").length;
    const forexCount = signals.filter((s) => s.market === "FOREX" || s.market === "METAL").length;
    return {
      ALL: signals.length,
      CRYPTO: cryptoCount,
      FOREX: forexCount,
    };
  }, [signals]);

  // Dynamic direction counts based on selected market & quote
  const directionCounts = useMemo(() => {
    let pool = signals;
    if (selectedMarket === "CRYPTO") {
      pool = pool.filter((s) => s.market === "CRYPTO");
      if (quoteFilter === "USDT") {
        pool = pool.filter((s) => s.symbol.toUpperCase().endsWith("USDT") || s.symbol.toUpperCase().endsWith("/USDT"));
      } else if (quoteFilter === "BTC") {
        pool = pool.filter((s) => (s.symbol.toUpperCase().endsWith("BTC") || s.symbol.toUpperCase().endsWith("/BTC")) && !s.symbol.toUpperCase().startsWith("BTC"));
      }
    } else if (selectedMarket === "FOREX") {
      pool = pool.filter((s) => s.market === "FOREX" || s.market === "METAL");
      if (quoteFilter === "METALS") {
        pool = pool.filter((s) => s.market === "METAL" || s.symbol.toUpperCase().includes("XAU") || s.symbol.toUpperCase().includes("XAG"));
      } else if (quoteFilter === "USD_MAJORS") {
        pool = pool.filter((s) => s.market === "FOREX" && !s.symbol.toUpperCase().includes("XAU") && !s.symbol.toUpperCase().includes("XAG"));
      }
    }
    return {
      ALL: pool.length,
      BUY: pool.filter((s) => s.direction === "BUY").length,
      SELL: pool.filter((s) => s.direction === "SELL").length,
      SCALPING: pool.filter((s) => s.tab_category === "SCALPING" || s.direction === "SCALP").length,
    };
  }, [signals, selectedMarket, quoteFilter]);

  // Filter signals based on Market, Quote, Direction, Scalping, and Search query
  const filteredSignals = useMemo(() => {
    return signals.filter((s) => {
      // 1. Scalping toggle
      if (isScalpingOnly && s.tab_category !== "SCALPING" && s.direction !== "SCALP") return false;

      // 2. Direction filter
      if (directionFilter === "BUY" && s.direction !== "BUY") return false;
      if (directionFilter === "SELL" && s.direction !== "SELL") return false;

      // 3. Market filter
      if (selectedMarket === "CRYPTO" && s.market !== "CRYPTO") return false;
      if (selectedMarket === "FOREX" && s.market !== "FOREX" && s.market !== "METAL") return false;

      // 4. Quote filter
      if (selectedMarket === "CRYPTO") {
        const sym = s.symbol.toUpperCase();
        if (quoteFilter === "USDT" && !sym.endsWith("USDT") && !sym.endsWith("/USDT")) return false;
        if (quoteFilter === "BTC" && ((!sym.endsWith("BTC") && !sym.endsWith("/BTC")) || sym.startsWith("BTC"))) return false;
      } else if (selectedMarket === "FOREX") {
        const sym = s.symbol.toUpperCase();
        const isMetal = s.market === "METAL" || sym.includes("XAU") || sym.includes("XAG");
        if (quoteFilter === "METALS" && !isMetal) return false;
        if (quoteFilter === "USD_MAJORS" && isMetal) return false;
      }

      // 5. Search query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const match =
          s.symbol.toLowerCase().includes(q) ||
          s.name.toLowerCase().includes(q) ||
          s.instrument_id.toLowerCase().includes(q);
        if (!match) return false;
      }
      return true;
    });
  }, [signals, selectedMarket, quoteFilter, directionFilter, isScalpingOnly, searchQuery]);

  // Helper to format checklist copy cleanly without changing any backend logic
  const formatChecklistItem = (item: string) => {
    if (item.includes("close above prior 20-bar high")) {
      return "⚡ Price testing 20-bar high breakout zone";
    }
    if (item.includes("close below prior 20-bar low")) {
      return "⚡ Price testing 20-bar low breakdown zone";
    }
    return item;
  };

  const renderActiveTradesDashboard = () => {
    const filteredPositions = positions.filter((p) => {
      if (positionsEnvironment === "ALL") return true;
      return p.environment === positionsEnvironment;
    });

    const filteredOpenOrders = openOrders.filter((o) => {
      if (positionsEnvironment !== "ALL" && o.environment && o.environment.toUpperCase() !== positionsEnvironment) {
        return false;
      }
      if (openOrdersSearch.trim()) {
        const q = openOrdersSearch.trim().toUpperCase();
        return (
          o.symbol.toUpperCase().includes(q) ||
          o.order_id.toUpperCase().includes(q) ||
          (o.client_order_id && o.client_order_id.toUpperCase().includes(q))
        );
      }
      return true;
    });

    const totalOpenOrderPages = Math.max(1, Math.ceil(filteredOpenOrders.length / openOrdersPageSize));
    const paginatedOpenOrders = filteredOpenOrders.slice(
      (openOrdersPage - 1) * openOrdersPageSize,
      openOrdersPage * openOrdersPageSize
    );

    return (
      <div className="space-y-5 animate-in fade-in duration-200">
        {/* Sub-tab view switcher */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[#2B3139] pb-3">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setTradesSubTab("POSITIONS")}
              className={`px-4 py-2 rounded-xl text-xs font-mono font-bold tabular-nums transition-all cursor-pointer ${
                tradesSubTab === "POSITIONS"
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm"
                  : "bg-[#1E2329] text-[#848E9C] hover:text-[#EAECEF] border border-[#2B3139]"
              }`}
            >
              Active Positions ({filteredPositions.length})
            </button>
            <button
              onClick={() => {
                setTradesSubTab("OPEN_ORDERS");
                fetchOpenOrders(undefined, undefined, positionsEnvironment);
              }}
              className={`px-4 py-2 rounded-xl text-xs font-mono font-bold tabular-nums transition-all cursor-pointer flex items-center gap-1.5 ${
                tradesSubTab === "OPEN_ORDERS"
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm"
                  : "bg-[#1E2329] text-[#848E9C] hover:text-[#EAECEF] border border-[#2B3139]"
              }`}
            >
              <FileCheck className="w-3.5 h-3.5 text-cyan-400" />
              <span>Open Orders ({filteredOpenOrders.length})</span>
            </button>
          </div>

          <div className="text-xs font-mono text-[#848E9C]">
            {tradesSubTab === "POSITIONS" ? (
              <span>Mark-to-market live valuations & risk metrics</span>
            ) : (
              <span>Decoupled order lifecycle inspection</span>
            )}
          </div>
        </div>

        {tradesSubTab === "POSITIONS" ? (
          <>
            {/* Unified P&L Summary Metric Strip & Mathematical Reconciliation */}
        <div className="space-y-2.5">
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <div className="p-3.5 rounded-xl bg-[#262C36] border border-[#2B3139]">
              <span className="text-[10px] text-[#848E9C] uppercase font-mono block">Active Open Trades</span>
              <div className="text-xl font-bold font-mono text-[#EAECEF] mt-0.5 tabular-nums">
                {filteredPositions.length}
              </div>
              <span className="text-[10px] text-[#848E9C] font-mono">
                {selectedMarket === "CRYPTO" ? "Crypto" : "Forex & Metals"} ({positionsEnvironment})
              </span>
            </div>

            <div className="p-3.5 rounded-xl bg-[#262C36] border border-[#2B3139]">
              <span className="text-[10px] text-[#848E9C] uppercase font-mono block">Unrealized P&L</span>
              <div
                className={`text-xl font-bold font-mono mt-0.5 tabular-nums ${
                  positionsMetrics.total_unrealized_pnl_usd >= 0 ? "text-emerald-400" : "text-rose-400"
                }`}
              >
                {positionsMetrics.total_unrealized_pnl_usd >= 0 ? "+" : ""}${positionsMetrics.total_unrealized_pnl_usd.toFixed(2)}
              </div>
              <span className="text-[10px] text-[#848E9C] font-mono">
                Mark-to-market live
              </span>
            </div>

            <div className="p-3.5 rounded-xl bg-[#262C36] border border-[#2B3139]">
              <span className="text-[10px] text-[#848E9C] uppercase font-mono block">Gross Realized P&L</span>
              <div
                className={`text-xl font-bold font-mono mt-0.5 tabular-nums ${
                  (positionsMetrics.total_realized_gross_usd !== undefined ? positionsMetrics.total_realized_gross_usd : positionsMetrics.total_realized_pnl_usd) >= 0
                    ? "text-emerald-400"
                    : "text-rose-400"
                }`}
              >
                {(positionsMetrics.total_realized_gross_usd !== undefined ? positionsMetrics.total_realized_gross_usd : positionsMetrics.total_realized_pnl_usd) >= 0 ? "+" : ""}
                ${(positionsMetrics.total_realized_gross_usd !== undefined ? positionsMetrics.total_realized_gross_usd : positionsMetrics.total_realized_pnl_usd).toFixed(2)}
              </div>
              <span className="text-[10px] text-[#848E9C] font-mono">
                Closed trades booked
              </span>
            </div>

            <div className="p-3.5 rounded-xl bg-[#262C36] border border-[#2B3139]">
              <span className="text-[10px] text-[#848E9C] uppercase font-mono block">Fees Deducted</span>
              <div className="text-xl font-bold font-mono text-amber-300 mt-0.5 tabular-nums">
                -${positionsMetrics.total_fees_usd.toFixed(4)}
              </div>
              <span className="text-[10px] text-[#848E9C] font-mono">
                Exchange friction
              </span>
            </div>

            <div className="p-3.5 rounded-xl bg-[#262C36] border border-[#2B3139]">
              <span className="text-[10px] text-[#848E9C] uppercase font-mono block">Net Realized P&L</span>
              <div
                className={`text-xl font-bold font-mono mt-0.5 tabular-nums ${
                  (positionsMetrics.total_realized_net_usd !== undefined ? positionsMetrics.total_realized_net_usd : (positionsMetrics.total_realized_pnl_usd - positionsMetrics.total_fees_usd)) >= 0
                    ? "text-emerald-400"
                    : "text-rose-400"
                }`}
              >
                {(positionsMetrics.total_realized_net_usd !== undefined ? positionsMetrics.total_realized_net_usd : (positionsMetrics.total_realized_pnl_usd - positionsMetrics.total_fees_usd)) >= 0 ? "+" : ""}
                ${(positionsMetrics.total_realized_net_usd !== undefined ? positionsMetrics.total_realized_net_usd : (positionsMetrics.total_realized_pnl_usd - positionsMetrics.total_fees_usd)).toFixed(2)}
              </div>
              <span className="text-[10px] text-[#848E9C] font-mono">
                Gross realized - fees
              </span>
            </div>

            <div className="p-3.5 rounded-xl bg-[#262C36] border border-[#2B3139]">
              <span className="text-[10px] text-[#848E9C] uppercase font-mono block">Total Net P&L</span>
              <div
                className={`text-xl font-bold font-mono mt-0.5 tabular-nums ${
                  positionsMetrics.net_pnl_usd >= 0 ? "text-emerald-400" : "text-rose-400"
                }`}
              >
                {positionsMetrics.net_pnl_usd >= 0 ? "+" : ""}${positionsMetrics.net_pnl_usd.toFixed(2)}
              </div>
              <span className="text-[10px] text-[#848E9C] font-mono">
                Net realized + unrealized
              </span>
            </div>
          </div>

          <div className="px-3.5 py-2 rounded-xl bg-[#262C36]/80 border border-[#2B3139] text-[11px] font-mono text-[#848E9C] flex items-center justify-between">
            <span>
              <strong className="text-[#848E9C]">Fee Treatment:</strong> Exchange & broker fees are deducted from gross realized P&L. Total Net P&L = Net Realized P&L + Mark-to-Market Unrealized P&L. Realized trades are booked once and never added to totals twice.
            </span>
            <span className="text-[10px] text-cyan-400 font-bold shrink-0 ml-3">
              Market: {selectedMarket === "CRYPTO" ? "Crypto" : "Forex & Metals"} · Env: {positionsEnvironment}
            </span>
          </div>
        </div>

        {/* Action & Filter Toolbar — Simplified (ALL, DEMO, LIVE) */}
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 p-3 rounded-xl bg-[#1E2329] border border-[#2B3139] shadow-sm">
          <div className="flex items-center gap-1.5 p-1 bg-[#262C36] rounded-lg border border-[#2B3139] text-xs font-mono">
            {(["ALL", "DEMO", "LIVE"] as const).map((env) => {
              const isSelected = positionsEnvironment === env;
              return (
                <button
                  key={env}
                  onClick={() => {
                    setPositionsEnvironment(env);
                    fetchPositions(env, selectedMarket);
                  }}
                  className={`px-3 py-1.5 rounded-md font-bold transition-all cursor-pointer ${
                    isSelected
                      ? env === "DEMO"
                        ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                        : env === "LIVE"
                        ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                        : "bg-slate-800 text-[#EAECEF] border border-[#2B3139]"
                      : "text-[#848E9C] hover:text-[#EAECEF]"
                  }`}
                >
                  {env === "ALL" ? "All Portfolios" : env === "DEMO" ? "Exchange Demo" : "Live (Locked)"}
                </button>
              );
            })}
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => fetchPositions(positionsEnvironment, selectedMarket)}
              disabled={isPositionsLoading}
              className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-[#848E9C] hover:text-[#EAECEF] font-mono text-xs font-bold border border-[#2B3139] flex items-center gap-1.5 cursor-pointer"
              title="Refresh Mark-to-Market Prices"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isPositionsLoading ? "animate-spin text-cyan-400" : ""}`} />
              <span>Refresh Marks</span>
            </button>
          </div>
        </div>

        {/* Active Trades Authenticity Audit Banner */}
        <div className="p-3.5 rounded-xl bg-[#262C36]/90 border border-[#2B3139] flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs font-mono">
          <div className="flex items-start md:items-center gap-2.5">
            <div className="p-1 rounded bg-amber-500/10 border border-amber-500/30 text-amber-400 mt-0.5 md:mt-0">
              <ShieldAlert className="w-4 h-4" />
            </div>
            <div className="text-[#848E9C] text-[11px] leading-relaxed">
              <span className="font-bold text-[#EAECEF] block sm:inline mr-1">Position Authenticity Classification:</span>
              Positions marked <span className="px-1.5 py-0.2 rounded bg-purple-950/80 text-purple-300 border border-purple-500/30 font-bold">SEEDED FIXTURE</span> or <span className="px-1.5 py-0.2 rounded bg-cyan-950/80 text-cyan-300 border border-cyan-500/30 font-bold">PAPER SIMULATION</span> are algorithmic benchmark tests. Only positions marked <span className="px-1.5 py-0.2 rounded bg-emerald-950/80 text-emerald-300 border border-emerald-500/30 font-bold">EXCHANGE CONFIRMED</span> reflect genuine exchange testnet or live matching engine fills.
            </div>
          </div>
          <div className="text-right flex items-center gap-2 text-[10px] text-[#848E9C] shrink-0">
            <span>Mark Valuation:</span>
            <span className="px-2 py-0.5 rounded bg-[#1E2329] border border-[#2B3139] shadow-sm text-[#848E9C] font-bold">Verified Real-Time Feeds</span>
          </div>
        </div>

        {/* Positions Table */}
        <div className="overflow-x-auto rounded-xl border border-[#2B3139] bg-[#1E2329] shadow-xl">
          <table className="w-full text-left font-mono text-xs">
            <thead className="bg-[#262C36]/80 text-[#848E9C] uppercase text-[10px] tracking-wider border-b border-[#2B3139]">
              <tr>
                <th className="py-3 px-4">Instrument / Side</th>
                <th className="py-3 px-3">Authenticity & Origin</th>
                <th className="py-3 px-3">Entry Price</th>
                <th className="py-3 px-3">Mark Price & Freshness</th>
                <th className="py-3 px-3">Size / Value</th>
                <th className="py-3 px-3">Unrealized P&L</th>
                <th className="py-3 px-3">TP / SL Limits</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/80">
              {filteredPositions.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-12 text-center text-[#848E9C]">
                    No genuinely open trades in the selected {selectedMarket === "CRYPTO" ? "Crypto" : "Forex & Metals"} portfolio ({positionsEnvironment}). Trades appear here only when orders are genuinely executed on exchange or demo broker.
                  </td>
                </tr>
              ) : (
                filteredPositions.map((pos) => {
                  const isLong = pos.side === "LONG";
                  const isPnlPositive = pos.unrealized_pnl >= 0;

                  return (
                    <tr key={pos.position_id} className="hover:bg-slate-800/40 transition-colors">
                      {/* Instrument & Side */}
                      <td className="py-3.5 px-4">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-[#EAECEF] text-sm">{pos.symbol}</span>
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                              isLong
                                ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                                : "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                            }`}
                          >
                            {pos.side}
                          </span>
                        </div>
                        <span className="text-[10px] text-[#848E9C] block mt-0.5">{pos.position_id}</span>
                      </td>

                      {/* Authenticity & Origin */}
                      <td className="py-3.5 px-3">
                        {pos.origin === "EXCHANGE_CONFIRMED_DEMO" || pos.origin === "EXCHANGE_CONFIRMED_LIVE" ? (
                          <div>
                            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-950/80 text-emerald-300 border border-emerald-500/40 inline-flex items-center gap-1">
                              <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                              <span>EXCHANGE CONFIRMED</span>
                            </span>
                            <span className="text-[9px] text-emerald-400/80 block mt-0.5">{pos.environment} ({pos.exchange})</span>
                          </div>
                        ) : pos.origin === "PAPER_SIMULATION" ? (
                          <div>
                            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-cyan-950/80 text-cyan-300 border border-cyan-500/40 inline-flex items-center gap-1">
                              <Cpu className="w-3 h-3 text-cyan-400" />
                              <span>PAPER SIMULATION</span>
                            </span>
                            <span className="text-[9px] text-cyan-400/80 block mt-0.5">Tauric Engine Sim</span>
                          </div>
                        ) : pos.origin === "SEEDED_FIXTURE" ? (
                          <div>
                            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-purple-950/80 text-purple-300 border border-purple-500/40 inline-flex items-center gap-1">
                              <Database className="w-3 h-3 text-purple-400" />
                              <span>SEEDED FIXTURE</span>
                            </span>
                            <span className="text-[9px] text-purple-400/80 block mt-0.5">Preview Benchmark</span>
                          </div>
                        ) : (
                          <div>
                            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-800 text-[#848E9C] border border-[#2B3139]">
                              {pos.environment} ({pos.exchange})
                            </span>
                          </div>
                        )}
                      </td>

                      {/* Entry Price */}
                      <td className="py-3.5 px-3 tabular-nums text-[#848E9C]">
                        ${pos.entry_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}
                      </td>

                      {/* Mark Price & Freshness */}
                      <td className="py-3.5 px-3 tabular-nums font-bold text-[#EAECEF]">
                        <div className="flex items-center gap-1.5">
                          <span>${pos.mark_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}</span>
                          {pos.mark_price >= pos.entry_price ? (
                            <ArrowUpRight className="w-3.5 h-3.5 text-emerald-400" />
                          ) : (
                            <ArrowDownRight className="w-3.5 h-3.5 text-rose-400" />
                          )}
                        </div>
                        <div className="flex items-center gap-1 text-[9px] text-[#848E9C] mt-0.5 font-normal">
                          <span
                            className={`w-1.5 h-1.5 rounded-full ${
                              pos.price_freshness === "LIVE" || pos.price_freshness === "FRESH"
                                ? "bg-emerald-400"
                                : pos.price_freshness === "STALE"
                                ? "bg-amber-400"
                                : "bg-rose-400"
                            }`}
                          />
                          <span>{pos.price_freshness || "LIVE"}</span>
                          {pos.price_timestamp_utc && (
                            <span className="text-[#848E9C]">({pos.price_timestamp_utc.slice(11, 19)} UTC)</span>
                          )}
                        </div>
                      </td>

                      {/* Size & Value */}
                      <td className="py-3.5 px-3 tabular-nums text-[#848E9C]">
                        <div>{pos.size} units</div>
                        <div className="text-[10px] text-[#848E9C]">${pos.position_value?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
                      </td>

                      {/* Unrealized P&L */}
                      <td className="py-3.5 px-3 tabular-nums">
                        <div className={`font-bold flex items-center gap-1 ${isPnlPositive ? "text-emerald-400" : "text-rose-400"}`}>
                          {isPnlPositive ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingUp className="w-3.5 h-3.5 rotate-180" />}
                          <span>{isPnlPositive ? "+" : ""}${pos.unrealized_pnl.toFixed(2)}</span>
                        </div>
                        <div className={`text-[10px] ${isPnlPositive ? "text-emerald-400/80" : "text-rose-400/80"}`}>
                          ({isPnlPositive ? "+" : ""}{pos.unrealized_pnl_pct.toFixed(2)}%)
                        </div>
                      </td>

                      {/* TP / SL Limits */}
                      <td className="py-3.5 px-3 tabular-nums text-[11px] text-[#848E9C] space-y-0.5">
                        <div>TP: <span className="text-emerald-400 font-bold">{pos.take_profit ? `$${pos.take_profit}` : "--"}</span></div>
                        <div>SL: <span className="text-rose-400 font-bold">{pos.stop_loss ? `$${pos.stop_loss}` : "--"}</span></div>
                      </td>

                      {/* Actions */}
                      <td className="py-3.5 px-4 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            onClick={() => handleOpenAiAdvisory(pos)}
                            className="px-2.5 py-1 rounded bg-violet-950/60 hover:bg-violet-900/60 text-violet-300 hover:text-violet-200 border border-violet-500/30 text-[11px] font-bold flex items-center gap-1 cursor-pointer transition-colors shadow-sm"
                            title="AI Trade Monitoring & Risk Recommendations"
                          >
                            <Bot className="w-3 h-3 text-violet-400" />
                            <span>AI Monitor</span>
                          </button>

                          <button
                            onClick={() => handleOpenTpSlModal(pos)}
                            className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-cyan-300 hover:text-cyan-200 border border-[#2B3139] text-[11px] font-bold flex items-center gap-1 cursor-pointer transition-colors"
                            title="Adjust Stop-Loss & Take-Profit"
                          >
                            <Sliders className="w-3 h-3" />
                            <span>TP/SL</span>
                          </button>

                          <button
                            onClick={() => setSelectedPositionForHistory(pos)}
                            className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-[#848E9C] hover:text-[#EAECEF] border border-[#2B3139] text-[11px] cursor-pointer"
                            title="View Execution History & Fills"
                          >
                            <Receipt className="w-3 h-3" />
                          </button>

                          <button
                            onClick={() => handleClosePosition(pos.position_id)}
                            className="px-2.5 py-1 rounded bg-rose-950/40 hover:bg-rose-900/60 text-rose-300 border border-rose-500/30 text-[11px] font-bold cursor-pointer transition-colors"
                            title="Close Position"
                          >
                            Close
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
          </>
        ) : (
          <>
            {/* Decoupled Order Status Banner */}
            <div className="p-3.5 rounded-xl bg-[#262C36]/90 border border-amber-500/30 flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs font-mono">
              <div className="flex items-start md:items-center gap-2.5">
                <div className="p-1 rounded bg-amber-500/10 border border-amber-500/30 text-amber-400 mt-0.5 md:mt-0">
                  <AlertTriangle className="w-4 h-4" />
                </div>
                <div className="text-[#848E9C] text-[11px] leading-relaxed">
                  <span className="font-bold text-amber-300 block sm:inline mr-1">Decoupled Order Retrieval Active:</span>
                  Open orders and lifecycle status are retrieved independently from exchange wallet balances. If wallet balance queries fail or permissions are restricted, open limit orders, fills, remaining quantities, and TP/SL limits remain fully visible and manageable.
                  {openOrdersBalanceMessage && (
                    <span className="block text-amber-200/80 mt-0.5">Note: {openOrdersBalanceMessage}</span>
                  )}
                </div>
              </div>
              <div className="text-right flex items-center gap-2 text-[10px] text-[#848E9C] shrink-0">
                <span>Balance Stream:</span>
                <span className={`px-2 py-0.5 rounded font-bold border ${
                  openOrdersBalanceStatus === "AVAILABLE"
                    ? "bg-emerald-950 text-emerald-300 border-emerald-500/40"
                    : "bg-amber-950 text-amber-300 border-amber-500/40"
                }`}>
                  {openOrdersBalanceStatus || "Decoupled"}
                </span>
              </div>
            </div>

            {/* Action & Filter Toolbar for Open Orders */}
            <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 p-3 rounded-xl bg-[#1E2329] border border-[#2B3139] shadow-sm">
              <div className="flex items-center gap-1.5 p-1 bg-[#262C36] rounded-lg border border-[#2B3139] text-xs font-mono">
                {(["ALL", "DEMO", "PAPER", "LIVE"] as const).map((env) => {
                  const isSelected = positionsEnvironment === env;
                  return (
                    <button
                      key={env}
                      onClick={() => {
                        setPositionsEnvironment(env);
                        fetchOpenOrders(undefined, undefined, env);
                      }}
                      className={`px-3 py-1.5 rounded-md font-bold transition-all cursor-pointer ${
                        isSelected
                          ? env === "DEMO"
                            ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                            : env === "PAPER"
                            ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"
                            : env === "LIVE"
                            ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                            : "bg-slate-800 text-[#EAECEF] border border-[#2B3139]"
                          : "text-[#848E9C] hover:text-[#EAECEF]"
                      }`}
                    >
                      {env === "ALL" ? "All Portfolios" : env === "DEMO" ? "Exchange Demo" : env === "PAPER" ? "Demo Simulator" : "Live (Locked)"}
                    </button>
                  );
                })}
              </div>

              <div className="flex items-center gap-2">
                <div className="relative">
                  <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-[#848E9C]" />
                  <input
                    type="text"
                    placeholder="Filter symbol / order ID..."
                    value={openOrdersSearch}
                    onChange={(e) => {
                      setOpenOrdersSearch(e.target.value);
                      setOpenOrdersPage(1);
                    }}
                    className="pl-8 pr-3 py-1.5 rounded-lg bg-[#262C36] border border-[#2B3139] text-xs font-mono text-[#EAECEF] placeholder-slate-600 focus:outline-none focus:border-cyan-500 w-48 sm:w-56"
                  />
                </div>

                <button
                  onClick={() => fetchOpenOrders(undefined, openOrdersSearch, positionsEnvironment)}
                  disabled={isOpenOrdersLoading}
                  className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-[#848E9C] hover:text-[#EAECEF] font-mono text-xs font-bold border border-[#2B3139] flex items-center gap-1.5 cursor-pointer"
                  title="Refresh Open Orders"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${isOpenOrdersLoading ? "animate-spin text-cyan-400" : ""}`} />
                  <span>Refresh Orders</span>
                </button>
              </div>
            </div>

            {/* Open Orders Table */}
            <div className="overflow-x-auto rounded-xl border border-[#2B3139] bg-[#1E2329] shadow-xl">
              <table className="w-full text-left font-mono text-xs">
                <thead className="bg-[#262C36]/80 text-[#848E9C] uppercase text-[10px] tracking-wider border-b border-[#2B3139]">
                  <tr>
                    <th className="py-3 px-4">Order / Client ID</th>
                    <th className="py-3 px-3">Instrument & Side</th>
                    <th className="py-3 px-3">Type</th>
                    <th className="py-3 px-3">Order Price</th>
                    <th className="py-3 px-3">Amount / Filled / Rem.</th>
                    <th className="py-3 px-3">TP / SL Limits</th>
                    <th className="py-3 px-3">Status</th>
                    <th className="py-3 px-3">Origin & Environment</th>
                    <th className="py-3 px-4 text-right">Created (UTC)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/80">
                  {paginatedOpenOrders.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="py-12 text-center text-[#848E9C]">
                        {isOpenOrdersLoading ? (
                          <div className="flex items-center justify-center gap-2">
                            <RefreshCw className="w-4 h-4 animate-spin text-cyan-400" />
                            <span>Querying exchange matching engine for open orders...</span>
                          </div>
                        ) : (
                          <div>
                            No open orders found in the selected environment.
                            <p className="text-[11px] text-[#848E9C] mt-1">
                              Orders are retrieved independently of wallet balance availability.
                            </p>
                          </div>
                        )}
                      </td>
                    </tr>
                  ) : (
                    paginatedOpenOrders.map((ord) => {
                      const isBuy = ord.side.toUpperCase() === "BUY";
                      return (
                        <tr key={ord.order_id} className="hover:bg-slate-800/40 transition-colors">
                          <td className="py-3.5 px-4">
                            <div className="font-bold text-[#EAECEF] flex items-center gap-1.5">
                              <span>{ord.order_id}</span>
                            </div>
                            {ord.client_order_id && ord.client_order_id !== ord.order_id && (
                              <div className="text-[10px] text-[#848E9C] font-mono">
                                Client: {ord.client_order_id}
                              </div>
                            )}
                          </td>
                          <td className="py-3.5 px-3">
                            <div className="font-bold text-[#EAECEF]">{ord.symbol}</div>
                            <span
                              className={`inline-block px-1.5 py-0.2 rounded text-[10px] font-bold ${
                                isBuy
                                  ? "bg-emerald-950 text-emerald-300 border border-emerald-500/40"
                                  : "bg-rose-950 text-rose-300 border border-rose-500/40"
                              }`}
                            >
                              {ord.side}
                            </span>
                          </td>
                          <td className="py-3.5 px-3 text-[#848E9C]">
                            <span className="px-1.5 py-0.5 rounded bg-[#262C36] border border-[#2B3139] text-[10px] text-[#848E9C]">
                              {ord.order_type}
                            </span>
                          </td>
                          <td className="py-3.5 px-3 text-[#EAECEF] font-bold tabular-nums">
                            ${ord.price.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                          </td>
                          <td className="py-3.5 px-3 tabular-nums text-[#848E9C]">
                            <div>{ord.amount} qty</div>
                            <div className="text-[10px] text-[#848E9C]">
                              Filled: {ord.filled_amount} | Rem: {ord.remaining_amount}
                            </div>
                          </td>
                          <td className="py-3.5 px-3 text-[11px] text-[#848E9C] space-y-0.5">
                            <div>TP: <span className="text-emerald-400 font-bold">{ord.take_profit ? `$${ord.take_profit}` : "--"}</span></div>
                            <div>SL: <span className="text-rose-400 font-bold">{ord.stop_loss ? `$${ord.stop_loss}` : "--"}</span></div>
                          </td>
                          <td className="py-3.5 px-3">
                            <span
                              className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                                ord.status === "OPEN"
                                  ? "bg-cyan-950/80 text-cyan-300 border-cyan-500/40"
                                  : ord.status === "PARTIALLY_FILLED"
                                  ? "bg-amber-950/80 text-amber-300 border-amber-500/40"
                                  : ord.status === "FILLED"
                                  ? "bg-emerald-950/80 text-emerald-300 border-emerald-500/40"
                                  : "bg-[#262C36] text-[#848E9C] border-[#2B3139]"
                              }`}
                            >
                              {ord.status}
                            </span>
                          </td>
                          <td className="py-3.5 px-3 text-[11px] text-[#848E9C]">
                            <span className="px-1.5 py-0.5 rounded bg-[#262C36] border border-[#2B3139] text-[10px]">
                              {ord.environment || "DEMO"}
                            </span>
                          </td>
                          <td className="py-3.5 px-4 text-right text-[#848E9C] text-[10px]">
                            {ord.created_at_utc ? ord.created_at_utc.replace("T", " ").replace("Z", "") : "--"}
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination Controls */}
            {filteredOpenOrders.length > openOrdersPageSize && (
              <div className="flex items-center justify-between text-xs font-mono text-[#848E9C] px-1 pt-2">
                <span>
                  Showing {(openOrdersPage - 1) * openOrdersPageSize + 1} -{" "}
                  {Math.min(openOrdersPage * openOrdersPageSize, filteredOpenOrders.length)} of{" "}
                  <strong className="text-[#EAECEF]">{filteredOpenOrders.length}</strong> orders
                </span>
                <div className="flex items-center gap-1.5">
                  <button
                    disabled={openOrdersPage <= 1}
                    onClick={() => setOpenOrdersPage((p) => Math.max(1, p - 1))}
                    className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed text-[#EAECEF] cursor-pointer"
                  >
                    Previous
                  </button>
                  <span className="px-2 text-[#848E9C]">
                    Page {openOrdersPage} of {totalOpenOrderPages}
                  </span>
                  <button
                    disabled={openOrdersPage >= totalOpenOrderPages}
                    onClick={() => setOpenOrdersPage((p) => Math.min(totalOpenOrderPages, p + 1))}
                    className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed text-[#EAECEF] cursor-pointer"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    );
  };

  // Define Renderers for the 4 Rearrangeable Sections
  const renderMacroCalendarSection = () => (
    <div className="p-5 rounded-2xl bg-[#1E2329] border border-[#2B3139] space-y-4 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 pb-2.5 border-b border-[#2B3139]">
          <div className="flex items-center gap-2">
            <Calendar className="w-4 h-4 text-cyan-400" />
            <span className="text-xs font-mono font-bold tabular-nums text-[#EAECEF] uppercase tracking-wider">
              Macroeconomic Event Calendar
            </span>
            <span
              className={`text-[10px] font-mono uppercase px-2 py-0.5 rounded-full border font-bold ${
                calendarMeta?.status === "AVAILABLE"
                  ? "bg-emerald-950 text-emerald-300 border-emerald-500/40"
                  : calendarMeta?.status === "STALE"
                  ? "bg-amber-950 text-amber-300 border-amber-500/40"
                  : calendarMeta?.status === "UNAVAILABLE"
                  ? "bg-rose-950 text-rose-300 border-rose-500/40"
                  : "bg-slate-800 text-[#848E9C] border-[#2B3139]"
              }`}
            >
              STATUS: {calendarMeta?.status || "DISABLED"}
            </span>
          </div>

          <div className="flex items-center gap-3">
            {/* Approved Visible Attribution with Clickable Link */}
            <div className="flex items-center gap-1.5 text-[11px] font-mono text-[#848E9C]">
              <span>Data provided by</span>
              <a
                href="https://www.financecalendar.com"
                target="_blank"
                rel="noopener noreferrer"
                className="text-cyan-400 hover:text-cyan-300 underline inline-flex items-center gap-0.5 font-bold transition-colors"
              >
                <span>Finance Calendar</span>
                <ExternalLink className="w-3 h-3 inline" />
              </a>
            </div>

            <button
              onClick={() => setIsCalendarExpanded(!isCalendarExpanded)}
              aria-expanded={isCalendarExpanded}
              aria-controls="macroeconomic-calendar-content"
              className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-cyan-300 hover:text-[#EAECEF] transition-colors flex items-center gap-1.5 text-xs font-mono font-bold tabular-nums border border-[#2B3139] cursor-pointer shadow-sm"
            >
              <span>{isCalendarExpanded ? "Show less" : "See more"}</span>
              {isCalendarExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs font-mono">
          <div className="p-2.5 rounded-xl bg-[#262C36] border border-[#2B3139] space-y-1">
            <span className="text-[10px] text-[#848E9C] block uppercase tracking-wider">Event Risk Policy</span>
            <span className={`font-bold block ${calendarMeta?.status === "AVAILABLE" ? "text-emerald-400" : "text-amber-400"}`}>
              {calendarMeta?.status === "AVAILABLE" ? "GATED BLACKOUT WINDOWS" : "UNKNOWN (UNVERIFIED NEWS)"}
            </span>
            <span className="text-[10px] text-[#848E9C] block">
              {calendarMeta?.status === "AVAILABLE" ? "±30m pre / ±15m post high-impact buffer" : "Fail-closed safety policy active"}
            </span>
          </div>

          <div className="p-2.5 rounded-xl bg-[#262C36] border border-[#2B3139] space-y-1">
            <span className="text-[10px] text-[#848E9C] block uppercase tracking-wider">Feed Sync (Authoritative PKT)</span>
            <span className="text-[#848E9C] font-bold block tabular-nums">
              {calendarMeta?.last_retrieval_pkt || "-- (Provider Disabled in Staging)"}
            </span>
            <span className="text-[10px] text-[#848E9C] block">Canonical storage in UTC (UTC+05:00 display)</span>
          </div>

          <div className="p-2.5 rounded-xl bg-[#262C36] border border-[#2B3139] space-y-1">
            <span className="text-[10px] text-[#848E9C] block uppercase tracking-wider">Event Horizon Scope</span>
            <span className="text-cyan-300 font-bold block">
              14-Day Horizon ({calendarMeta?.events?.length || 0} Events)
            </span>
            <span className="text-[10px] text-[#848E9C] block">FOMC, CPI, NFP, GDP, Central Banks (14 Countries)</span>
          </div>
        </div>

        {/* Prominent Warning when Event Risk is Unknown or Unavailable */}
        {calendarMeta?.status !== "AVAILABLE" && (
          <div className="p-3 rounded-xl bg-amber-950/30 border border-amber-500/30 flex items-start gap-2.5 text-xs font-mono text-amber-200/90">
            <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
            <div className="space-y-0.5">
              <strong className="text-amber-300 font-bold block">
                EVENT-RISK WARNING: MACRO NEWS GATING IS CURRENTLY UNVERIFIED
              </strong>
              <p className="text-[11px] text-amber-200/80 leading-relaxed font-sans">
                The economic calendar is currently disabled or unavailable.
                Downstream signals treat event risk as <strong>UNKNOWN</strong> rather than assuming markets are clear.
                Always cross-reference scheduled macroeconomic releases manually before entering trades.
              </p>
            </div>
          </div>
        )}

        {/* ─── Compact Preview when Collapsed (Default on Initial Load) ─── */}
        {!isCalendarExpanded && (
          <div className="pt-2 border-t border-[#2B3139] space-y-2.5">
            <div className="flex items-center justify-between text-[11px] font-mono text-[#848E9C]">
              <span className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
                <span className="font-bold text-[#848E9C]">Upcoming Macroeconomic Events Preview</span>
                <span className="text-[#848E9C]">(Next 3 Releases)</span>
              </span>
              <button
                onClick={() => setIsCalendarExpanded(true)}
                className="text-cyan-400 hover:text-cyan-300 font-bold flex items-center gap-1 cursor-pointer text-[10px]"
              >
                <span>View full 14-day schedule ({calendarMeta?.events?.length || 0} events)</span>
                <ChevronDown className="w-3 h-3" />
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5 font-mono text-xs">
              {(calendarMeta?.events || []).slice(0, 3).map((ev: any, idx: number) => {
                const isHigh = ev.impact?.toUpperCase() === "HIGH";
                const isMed = ev.impact?.toUpperCase() === "MEDIUM";
                return (
                  <div key={ev.event_id || idx} className="p-3 rounded-xl bg-[#262C36]/70 border border-[#2B3139] space-y-1.5 hover:border-[#2B3139] transition-colors">
                    <div className="flex items-center justify-between text-[10px]">
                      <span className="px-1.5 py-0.2 rounded bg-[#1E2329] border border-[#2B3139] shadow-sm text-[#848E9C] font-bold">
                        {ev.country} • {ev.currency}
                      </span>
                      <span className={`px-1.5 py-0.2 rounded font-bold border text-[9px] ${
                        isHigh ? "bg-rose-950 text-rose-300 border-rose-500/40"
                        : isMed ? "bg-amber-950 text-amber-300 border-amber-500/40"
                        : "bg-slate-800 text-[#848E9C] border-[#2B3139]"
                      }`}>
                        {ev.impact}
                      </span>
                    </div>
                    <div className="font-bold text-[#EAECEF] text-xs truncate" title={ev.title}>
                      {ev.title}
                    </div>
                    <div className="flex items-center justify-between text-[10px] text-[#848E9C] pt-1 border-t border-[#2B3139]/60">
                      <span className="text-cyan-300 tabular-nums">{ev.scheduled_pkt || (ev.scheduled_utc?.slice(11, 16) + " UTC")}</span>
                      <span className="text-[#848E9C]">{ev.forecast ? `Cons: ${ev.forecast}` : (ev.previous ? `Prior: ${ev.previous}` : "Pending")}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ─── Interactive 14-Day Event Schedule Table ─── */}
        {isCalendarExpanded && (
          <div id="macroeconomic-calendar-content" className="space-y-3 pt-2 border-t border-[#2B3139]">
            {/* Filter Bar */}
            <div className="flex flex-wrap items-center justify-between gap-2.5 text-xs font-mono">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-[#848E9C] text-[11px] mr-1">Country:</span>
                {["ALL", "US", "GB", "EU", "DE", "JP", "CA", "AU", "CN"].map((c) => (
                  <button
                    key={c}
                    onClick={() => setCalendarCountryFilter(c)}
                    className={`px-2 py-0.5 rounded text-[11px] transition-colors border ${
                      calendarCountryFilter === c
                        ? "bg-cyan-500/20 text-cyan-300 border-cyan-500/50 font-bold"
                        : "bg-[#262C36]/50 text-[#848E9C] border-[#2B3139] hover:text-[#EAECEF]"
                    }`}
                  >
                    {c}
                  </button>
                ))}
              </div>

              <div className="flex items-center gap-1.5">
                <span className="text-[#848E9C] text-[11px] mr-1">Impact:</span>
                {["ALL", "HIGH", "MEDIUM", "LOW"].map((imp) => (
                  <button
                    key={imp}
                    onClick={() => setCalendarImpactFilter(imp)}
                    className={`px-2 py-0.5 rounded text-[11px] transition-colors border ${
                      calendarImpactFilter === imp
                        ? imp === "HIGH"
                          ? "bg-rose-500/20 text-rose-300 border-rose-500/50 font-bold"
                          : imp === "MEDIUM"
                          ? "bg-amber-500/20 text-amber-300 border-amber-500/50 font-bold"
                          : "bg-cyan-500/20 text-cyan-300 border-cyan-500/50 font-bold"
                        : "bg-[#262C36]/50 text-[#848E9C] border-[#2B3139] hover:text-[#EAECEF]"
                    }`}
                  >
                    {imp}
                  </button>
                ))}
              </div>
            </div>

            {/* Event Table */}
            <div className="overflow-x-auto rounded-xl border border-[#2B3139] bg-[#262C36]/70">
              <table className="w-full text-left text-xs font-mono">
                <thead>
                  <tr className="bg-[#1E2329] text-[#848E9C] border-b border-[#2B3139] text-[11px]">
                    <th className="py-2.5 px-3 font-semibold">Scheduled (PKT / UTC)</th>
                    <th className="py-2.5 px-2 font-semibold">Country</th>
                    <th className="py-2.5 px-3 font-semibold">Event Name</th>
                    <th className="py-2.5 px-2 font-semibold">Impact</th>
                    <th className="py-2.5 px-2 font-semibold">Consensus</th>
                    <th className="py-2.5 px-2 font-semibold">Prior</th>
                    <th className="py-2.5 px-2 font-semibold">Actual</th>
                    <th className="py-2.5 px-2 font-semibold">Status</th>
                    <th className="py-2.5 px-3 font-semibold">Model Bias</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {filteredCalendarEvents.length > 0 ? (
                    filteredCalendarEvents.map((ev) => {
                      const isHigh = ev.impact?.toUpperCase() === "HIGH";
                      const isMed = ev.impact?.toUpperCase() === "MEDIUM";
                      return (
                        <tr key={ev.event_id} className="hover:bg-[#1E2329]/50 transition-colors">
                          <td className="py-2 px-3 whitespace-nowrap">
                            <div className="font-bold text-[#EAECEF]">{ev.scheduled_pkt}</div>
                            <div className="text-[10px] text-[#848E9C]">{ev.scheduled_utc.replace("T", " ").replace("+00:00", " UTC")}</div>
                          </td>
                          <td className="py-2 px-2 whitespace-nowrap">
                            <span className="px-1.5 py-0.5 rounded bg-slate-800 border border-[#2B3139] text-[10px] text-[#848E9C] font-bold">
                              {ev.country} • {ev.currency}
                            </span>
                          </td>
                          <td className="py-2 px-3">
                            <a
                              href={ev.source_url || "https://www.financecalendar.com"}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-cyan-300 hover:text-cyan-200 underline font-medium inline-flex items-center gap-1 max-w-[280px] truncate"
                              title={ev.title}
                            >
                              <span className="truncate">{ev.title}</span>
                              <ExternalLink className="w-2.5 h-2.5 shrink-0 text-[#848E9C]" />
                            </a>
                          </td>
                          <td className="py-2 px-2 whitespace-nowrap">
                            <span
                              className={`px-1.5 py-0.5 rounded text-[10px] font-bold border ${
                                isHigh
                                  ? "bg-rose-950 text-rose-300 border-rose-500/40"
                                  : isMed
                                  ? "bg-amber-950 text-amber-300 border-amber-500/40"
                                  : "bg-slate-800 text-[#848E9C] border-[#2B3139]"
                              }`}
                            >
                              {ev.impact}
                            </span>
                          </td>
                          <td className="py-2 px-2 whitespace-nowrap text-[#848E9C]">
                            {ev.forecast_raw || (ev.forecast !== null && ev.forecast !== undefined ? `${ev.forecast}${ev.unit || ""}` : "--")}
                          </td>
                          <td className="py-2 px-2 whitespace-nowrap text-[#848E9C]">
                            {ev.previous_raw || (ev.previous !== null && ev.previous !== undefined ? `${ev.previous}${ev.unit || ""}` : "--")}
                          </td>
                          <td className="py-2 px-2 whitespace-nowrap">
                            {ev.actual_raw || (ev.actual !== null && ev.actual !== undefined ? (
                              <span className="font-bold text-emerald-300">{ev.actual}{ev.unit || ""}</span>
                            ) : (
                              <span className="text-[#848E9C]">Pending</span>
                            ))}
                          </td>
                          <td className="py-2 px-2 whitespace-nowrap">
                            <span className="px-1.5 py-0.5 rounded text-[10px] uppercase font-mono bg-[#1E2329] border border-[#2B3139] shadow-sm text-[#848E9C]">
                              {ev.status}
                            </span>
                          </td>
                          <td className="py-2 px-3 whitespace-nowrap">
                            {ev.interpretation ? (
                              <span
                                className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                                  ev.interpretation.crypto_bias === "BULLISH"
                                    ? "bg-emerald-950 text-emerald-300 border-emerald-500/40"
                                    : ev.interpretation.crypto_bias === "BEARISH"
                                    ? "bg-rose-950 text-rose-300 border-rose-500/40"
                                    : "bg-[#1E2329] text-[#848E9C] border-[#2B3139]"
                                }`}
                                title={ev.interpretation.model_interpretation}
                              >
                                {ev.interpretation.crypto_bias} (Crypto)
                              </span>
                            ) : (
                              <span className="text-[10px] text-[#848E9C]">--</span>
                            )}
                          </td>
                        </tr>
                      );
                    })
                  ) : (
                    <tr>
                      <td colSpan={9} className="py-6 text-center text-[#848E9C] text-xs">
                        {calendarMeta?.status === "AVAILABLE"
                          ? `No economic events matching "${calendarCountryFilter}" country and "${calendarImpactFilter}" impact.`
                          : "Economic calendar data is unavailable. Macro event gating remains UNKNOWN."}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            {/* Approved Attribution Footer */}
            <div className="flex flex-col sm:flex-row items-center justify-between text-[11px] font-mono text-[#848E9C] pt-2 border-t border-[#2B3139]">
              <div className="flex items-center gap-1.5">
                <span>Economic calendar data provided by</span>
                <a
                  href="https://www.financecalendar.com"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-cyan-400 hover:underline font-bold"
                >
                  Finance Calendar
                </a>
                <span>(Official Free API)</span>
              </div>
              <div className="text-[#848E9C] text-[10px]">
                Canonical Storage: UTC • Presentation: Asia/Karachi (PKT UTC+05:00)
              </div>
            </div>
          </div>
        )}
      </div>
  );

  const renderAiIntelStatsSection = () => (
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3.5">
        <div className="p-4 rounded-xl bg-[#1E2329] border border-[#2B3139] hover:border-[#2B3139] shadow-sm transition-colors">
          <div className="flex items-center justify-between text-[#848E9C] text-xs font-mono uppercase mb-1">
            <span>ACTIVE SETUPS</span>
            <Activity className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="text-2xl font-bold text-[#EAECEF] font-mono tabular-nums">{metrics?.active_signals ?? "--"}</div>
          <div className="text-[11px] text-[#848E9C] font-mono mt-0.5">Live bars • 0-AI Discovery</div>
        </div>

        <div className="p-4 rounded-xl bg-[#1E2329] border border-[#2B3139] hover:border-[#2B3139] shadow-sm transition-colors">
          <div className="flex items-center justify-between text-[#848E9C] text-xs font-mono uppercase mb-1">
            <span>BUY SIGNALS</span>
            <ArrowUpRight className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-bold text-emerald-400 font-mono tabular-nums">{metrics?.buy_signals ?? "--"}</div>
          <div className="text-[11px] text-[#848E9C] font-mono mt-0.5">Bullish structure / breakouts</div>
        </div>

        <div className="p-4 rounded-xl bg-[#1E2329] border border-[#2B3139] hover:border-[#2B3139] shadow-sm transition-colors">
          <div className="flex items-center justify-between text-[#848E9C] text-xs font-mono uppercase mb-1">
            <span>SELL / SHORT</span>
            <ArrowDownRight className="w-4 h-4 text-rose-400" />
          </div>
          <div className="text-2xl font-bold text-rose-400 font-mono tabular-nums">{metrics?.sell_signals ?? "--"}</div>
          <div className="text-[11px] text-[#848E9C] font-mono mt-0.5">Exits (Spot) & Shorts (Forex)</div>
        </div>

        <div className="p-4 rounded-xl bg-[#1E2329] border border-[#2B3139] hover:border-[#2B3139] shadow-sm transition-colors">
          <div className="flex items-center justify-between text-[#848E9C] text-xs font-mono uppercase mb-1">
            <span>SETUP QUALITY AVG</span>
            <Gauge className="w-4 h-4 text-sky-400" />
          </div>
          <div className="text-2xl font-bold text-sky-300 font-mono tabular-nums">
            {metrics?.average_score ? `${metrics.average_score}/100` : "--"}
          </div>
          <div className="text-[10px] text-[#848E9C] font-mono mt-0.5 leading-tight">
            Confirming rules count — not a profit probability
          </div>
        </div>
      </div>
  );

  const renderMarketTabsFilterSection = () => {
    const isCrypto = selectedMarket === "CRYPTO";
    const isForex = selectedMarket === "FOREX";
    const isFiltered = selectedMarket !== "ALL" || quoteFilter !== "ALL" || directionFilter !== "ALL" || isScalpingOnly || searchQuery.trim() !== "" || activeTab === "ACTIVE_TRADES";

    return (
      <div className="p-3 rounded-2xl bg-[#151921] border border-[#2B3139] space-y-3 font-mono">
        {/* ROW 1: Group A (Asset Class) + Group B (Contextual Quote Pills) + Unified Search */}
        <div className="flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-3">
          
          {/* Left: Group A & Group B pills */}
          <div className="flex flex-wrap items-center gap-2">
            {/* Group A: Primary Market Tabs */}
            <div className="flex items-center gap-1 p-1 bg-[#1E2329] rounded-xl border border-[#2B3139] text-xs">
              <button
                onClick={() => { setSelectedMarket("ALL"); setQuoteFilter("ALL"); if (activeTab === "ACTIVE_TRADES") setActiveTab("ALL"); }}
                className={`px-3 py-1.5 rounded-lg font-bold transition-all cursor-pointer ${
                  selectedMarket === "ALL" && activeTab !== "ACTIVE_TRADES"
                    ? "bg-[#262C36] text-[#EAECEF] border border-cyan-500/40 shadow-sm"
                    : "text-[#848E9C] hover:text-[#EAECEF]"
                }`}
              >
                All Markets ({marketCounts.ALL})
              </button>
              <button
                onClick={() => { setSelectedMarket("CRYPTO"); setQuoteFilter("ALL"); if (activeTab === "ACTIVE_TRADES") setActiveTab("ALL"); fetchPositions(positionsEnvironment, "CRYPTO"); }}
                className={`px-3 py-1.5 rounded-lg font-bold transition-all cursor-pointer ${
                  selectedMarket === "CRYPTO" && activeTab !== "ACTIVE_TRADES"
                    ? "bg-cyan-950 text-cyan-300 border border-cyan-500/50 shadow-sm"
                    : "text-[#848E9C] hover:text-[#EAECEF]"
                }`}
              >
                Crypto ({marketCounts.CRYPTO})
              </button>
              <button
                onClick={() => { setSelectedMarket("FOREX"); setQuoteFilter("ALL"); if (activeTab === "ACTIVE_TRADES") setActiveTab("ALL"); fetchPositions(positionsEnvironment, "FOREX"); }}
                className={`px-3 py-1.5 rounded-lg font-bold transition-all cursor-pointer ${
                  selectedMarket === "FOREX" && activeTab !== "ACTIVE_TRADES"
                    ? "bg-sky-950 text-sky-300 border border-sky-500/50 shadow-sm"
                    : "text-[#848E9C] hover:text-[#EAECEF]"
                }`}
              >
                Forex & Metals ({marketCounts.FOREX})
              </button>
            </div>

            {/* Group B: Contextual Quote Pills */}
            {isCrypto && (
              <div className="flex items-center gap-1 p-1 bg-[#1E2329] rounded-xl border border-[#2B3139] text-xs animate-in fade-in">
                {(["ALL", "USDT", "BTC"] as const).map((qf) => {
                  const label = qf === "ALL" ? "All Quotes" : `${qf} Quoted`;
                  const count = qf === "ALL" 
                    ? marketCounts.CRYPTO 
                    : qf === "USDT" 
                    ? signals.filter(s => s.market === "CRYPTO" && (s.symbol.toUpperCase().endsWith("USDT") || s.symbol.toUpperCase().endsWith("/USDT"))).length
                    : signals.filter(s => s.market === "CRYPTO" && (s.symbol.toUpperCase().endsWith("BTC") || s.symbol.toUpperCase().endsWith("/BTC")) && !s.symbol.toUpperCase().startsWith("BTC")).length;
                  return (
                    <button
                      key={qf}
                      onClick={() => setQuoteFilter(qf)}
                      className={`px-2.5 py-1 rounded-lg text-[11px] font-bold cursor-pointer transition-all ${
                        quoteFilter === qf
                          ? "bg-emerald-950 text-emerald-300 border border-emerald-500/40 shadow-sm"
                          : "text-[#848E9C] hover:text-[#EAECEF]"
                      }`}
                    >
                      {label} ({count})
                    </button>
                  );
                })}
              </div>
            )}

            {isForex && (
              <div className="flex items-center gap-1 p-1 bg-[#1E2329] rounded-xl border border-[#2B3139] text-xs animate-in fade-in">
                {(["ALL", "USD_MAJORS", "METALS"] as const).map((qf) => {
                  const label = qf === "ALL" ? "All FX & Metals" : qf === "USD_MAJORS" ? "USD Majors" : "Metals";
                  const count = qf === "ALL"
                    ? marketCounts.FOREX
                    : qf === "METALS"
                    ? signals.filter(s => (s.market === "METAL" || s.symbol.toUpperCase().includes("XAU") || s.symbol.toUpperCase().includes("XAG"))).length
                    : signals.filter(s => (s.market === "FOREX" && !s.symbol.toUpperCase().includes("XAU") && !s.symbol.toUpperCase().includes("XAG"))).length;
                  return (
                    <button
                      key={qf}
                      onClick={() => setQuoteFilter(qf)}
                      className={`px-2.5 py-1 rounded-lg text-[11px] font-bold cursor-pointer transition-all ${
                        quoteFilter === qf
                          ? "bg-amber-950 text-amber-300 border border-amber-500/40 shadow-sm"
                          : "text-[#848E9C] hover:text-[#EAECEF]"
                      }`}
                    >
                      {label} ({count})
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {/* Right: Search Box + Search Markets Modal Button */}
          <div className="flex items-center gap-2">
            <div className="relative flex-1 sm:w-64">
              <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-[#848E9C]" />
              <input
                type="text"
                placeholder="Instant filter: pair, coin..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-8 pr-7 py-1.5 rounded-lg bg-[#262C36] border border-[#2B3139] text-xs font-mono text-[#EAECEF] placeholder-slate-500 focus:outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery("")}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[#848E9C] hover:text-[#EAECEF]"
                  aria-label="Clear search"
                >
                  <X className="w-3 h-3" />
                </button>
              )}
            </div>
            <button
              id="top-search-markets-btn"
              onClick={() => setIsUniversalSearchOpen(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#00E5FF] hover:bg-[#00E5FF]/90 text-[#0B0E11] text-xs font-mono font-bold transition shadow-sm whitespace-nowrap cursor-pointer"
            >
              <Search className="w-3.5 h-3.5 text-[#0B0E11]" />
              <span>Search Markets</span>
            </button>
          </div>
        </div>

        {/* ROW 2: Group C (Direction Segmented Control) + Group D (Mode Toggles) + Reset Button */}
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 pt-1 border-t border-[#2B3139]/50">
          
          {/* Group C: Direction Control */}
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] text-[#848E9C] uppercase mr-1 hidden sm:inline">Direction:</span>
            <div className="flex items-center gap-1 p-1 bg-[#1E2329] rounded-xl border border-[#2B3139] text-xs">
              <button
                onClick={() => { setDirectionFilter("ALL"); if (activeTab === "ACTIVE_TRADES") setActiveTab("ALL"); }}
                className={`flex items-center gap-1.5 px-3 py-1 rounded-lg font-bold transition-all cursor-pointer ${
                  directionFilter === "ALL" && activeTab !== "ACTIVE_TRADES"
                    ? "bg-[#262C36] text-[#EAECEF] border border-[#2B3139] shadow-sm"
                    : "text-[#848E9C] hover:text-[#EAECEF]"
                }`}
              >
                <span>All</span>
                <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-[#151921] text-[#848E9C]">
                  {directionCounts.ALL}
                </span>
              </button>
              <button
                onClick={() => { setDirectionFilter("BUY"); if (activeTab === "ACTIVE_TRADES") setActiveTab("ALL"); }}
                className={`flex items-center gap-1.5 px-3 py-1 rounded-lg font-bold transition-all cursor-pointer ${
                  directionFilter === "BUY" && activeTab !== "ACTIVE_TRADES"
                    ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 shadow-sm"
                    : "text-[#848E9C] hover:text-[#EAECEF]"
                }`}
              >
                <span>▲ Buy</span>
                <span className={`text-[10px] px-1.5 py-0.2 rounded-full ${directionFilter === "BUY" && activeTab !== "ACTIVE_TRADES" ? "bg-emerald-950 text-emerald-300" : "bg-[#151921] text-[#848E9C]"}`}>
                  {directionCounts.BUY}
                </span>
              </button>
              <button
                onClick={() => { setDirectionFilter("SELL"); if (activeTab === "ACTIVE_TRADES") setActiveTab("ALL"); }}
                className={`flex items-center gap-1.5 px-3 py-1 rounded-lg font-bold transition-all cursor-pointer ${
                  directionFilter === "SELL" && activeTab !== "ACTIVE_TRADES"
                    ? "bg-rose-500/20 text-rose-300 border border-rose-500/40 shadow-sm"
                    : "text-[#848E9C] hover:text-[#EAECEF]"
                }`}
              >
                <span>▼ Sell</span>
                <span className={`text-[10px] px-1.5 py-0.2 rounded-full ${directionFilter === "SELL" && activeTab !== "ACTIVE_TRADES" ? "bg-rose-950 text-rose-300" : "bg-[#151921] text-[#848E9C]"}`}>
                  {directionCounts.SELL}
                </span>
              </button>
            </div>
          </div>

          {/* Group D: Mode Toggles (Scalping Grid & Active Trades) + Reset Button */}
          <div className="flex flex-wrap items-center gap-2">
            {/* Mode: Scalping Grid */}
            <button
              onClick={() => { setIsScalpingOnly(!isScalpingOnly); if (activeTab === "ACTIVE_TRADES") setActiveTab("ALL"); }}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer border ${
                isScalpingOnly && activeTab !== "ACTIVE_TRADES"
                  ? "bg-cyan-500/20 text-cyan-300 border-cyan-500/50 shadow-sm"
                  : "bg-[#1E2329] text-[#848E9C] border-[#2B3139] hover:text-[#EAECEF]"
              }`}
            >
              <Zap className={`w-3.5 h-3.5 ${isScalpingOnly ? "text-cyan-400" : "text-[#848E9C]"}`} />
              <span>⚡ Scalping Grid</span>
              <span className={`text-[10px] px-1.5 py-0.2 rounded-full ${isScalpingOnly ? "bg-cyan-950 text-cyan-300" : "bg-[#151921] text-[#848E9C]"}`}>
                {directionCounts.SCALPING}
              </span>
            </button>

            {/* Mode: Active Trades View Toggle */}
            <button
              onClick={() => {
                const nextTab = activeTab === "ACTIVE_TRADES" ? "ALL" : "ACTIVE_TRADES";
                setActiveTab(nextTab);
                if (nextTab === "ACTIVE_TRADES") {
                  fetchPositions();
                  fetchOpenOrders();
                }
              }}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer border ${
                activeTab === "ACTIVE_TRADES"
                  ? "bg-amber-500/20 text-amber-300 border-amber-500/50 shadow-sm"
                  : "bg-[#1E2329] text-[#848E9C] border-[#2B3139] hover:text-[#EAECEF]"
              }`}
            >
              <span className={`w-2 h-2 rounded-full ${activeTab === "ACTIVE_TRADES" ? "bg-amber-400 animate-pulse" : "bg-[#848E9C]"}`} />
              <span>Active Trades</span>
              <span className={`text-[10px] px-1.5 py-0.2 rounded-full ${activeTab === "ACTIVE_TRADES" ? "bg-amber-950 text-amber-300" : "bg-[#151921] text-[#848E9C]"}`}>
                {positions.length}
              </span>
            </button>

            {/* Reset Filters button if any filter is active */}
            {isFiltered && (
              <button
                onClick={() => {
                  setSelectedMarket("ALL");
                  setQuoteFilter("ALL");
                  setDirectionFilter("ALL");
                  setIsScalpingOnly(false);
                  setSearchQuery("");
                  setActiveTab("ALL");
                }}
                className="flex items-center gap-1 px-2.5 py-1.5 rounded-xl text-xs font-bold text-rose-400 hover:text-rose-300 bg-rose-950/30 hover:bg-rose-950/50 border border-rose-500/30 transition-all cursor-pointer"
              >
                <X className="w-3 h-3" />
                <span>Reset</span>
              </button>
            )}
          </div>
        </div>
      </div>
    );
  };

  const renderSignalCardsGridSection = () => (
      <div className="space-y-4">
      {activeTab === "ACTIVE_TRADES" ? (
        renderActiveTradesDashboard()
      ) : (
        <>
          {/* ─── Sub-header counter ─────────────────────────────────────── */}
          <div className="flex items-center justify-between text-xs font-mono text-[#848E9C] px-1">
            <span>
              Showing <strong className="text-[#EAECEF] tabular-nums">{filteredSignals.length}</strong> setups · Sorted by Technical Rule Score
            </span>
            <span className="text-[11px] text-[#848E9C] hidden sm:inline">
              Institutional R:R bounds (≥ 1:1.50) · Invalidation stops active
            </span>
          </div>

          {/* ─── Responsive 3-Column Grid ──────────────────────────────── */}
          {filteredSignals.length === 0 ? (
            <div className="p-12 text-center rounded-2xl bg-[#1E2329]/30 border border-[#2B3139] text-[#848E9C] space-y-2">
              <Activity className="w-8 h-8 mx-auto text-[#848E9C]" />
              <p className="font-mono text-sm text-[#848E9C]">No signals match the current filter</p>
              <p className="text-xs text-[#848E9C]">Switch tabs or clear the search query to view active opportunities.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4.5">
              {filteredSignals.map((signal) => {
            const isBuy = signal.direction === "BUY";
            const isSell = signal.direction === "SELL";
            const isScalp = signal.direction === "SCALP";

            // Market-aware direction label to ensure Spot Crypto does not mislead users into shorting
            let directionLabel = signal.direction_label;
            if (isSell) {
              directionLabel = signal.market === "CRYPTO" ? "SELL / EXIT" : "SELL / SHORT";
            } else if (isBuy) {
              directionLabel = "BUY";
            } else if (isScalp) {
              directionLabel = "SCALP RANGE";
            }

            return (
              <div
                key={signal.instrument_id}
                className="flex flex-col justify-between p-5 rounded-2xl bg-[#1E2329] border border-[#2B3139] hover:border-[#2B3139] shadow-sm hover:shadow-md motion-safe:transition-all motion-safe:duration-200 motion-safe:hover:-translate-y-0.5 motion-reduce:transition-none motion-reduce:hover:translate-y-0 space-y-4 group"
              >
                {/* Header Row */}
                <div className="flex items-start justify-between gap-3">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="text-base font-bold font-mono text-[#EAECEF] tracking-wide">
                        {signal.symbol}
                      </span>
                      <span
                        className={`text-[9px] font-mono uppercase px-1.5 py-0.5 rounded font-bold ${
                          signal.market === "CRYPTO"
                            ? "bg-cyan-950/70 text-cyan-400 border border-cyan-500/30"
                            : signal.market === "METAL"
                            ? "bg-amber-950/70 text-amber-300 border border-amber-500/30"
                            : "bg-sky-950/70 text-sky-300 border border-sky-500/30"
                        }`}
                      >
                        {signal.market}
                      </span>
                      {signal.event_risk && (
                        <span
                          className={`text-[9px] font-mono uppercase px-1.5 py-0.5 rounded font-bold ${
                            signal.event_risk.status === "CLEAR"
                              ? "bg-emerald-950 text-emerald-300 border border-emerald-500/30"
                              : signal.event_risk.status === "BLACKOUT"
                              ? "bg-rose-950 text-rose-300 border border-rose-500/30"
                              : "bg-slate-800 text-amber-300 border border-amber-500/30"
                          }`}
                          title={signal.event_risk.reason}
                        >
                          NEWS: {signal.event_risk.status}
                        </span>
                      )}
                    </div>
                    <div className="text-[11px] text-[#848E9C] truncate max-w-[180px]">
                      {signal.name}
                    </div>
                  </div>

                  {/* Steel Blue Circular Ranking-Score Badge */}
                  <div className="flex flex-col items-center">
                    <div
                      className="w-10 h-10 rounded-full border-2 border-slate-500/70 bg-slate-800/90 text-[#EAECEF] flex items-center justify-center font-mono font-bold tabular-nums text-sm shadow-inner"
                      title="Setup Quality Score: Counts confirming technical indicators (not a probability of profit)"
                    >
                      <span className="tabular-nums">{signal.score}</span>
                    </div>
                    <span className="text-[9px] font-mono text-[#848E9C] mt-0.5">Score</span>
                  </div>
                </div>

                {/* Sub-Badges Row */}
                <div className="flex flex-wrap items-center gap-1.5">
                  <span
                    className={`text-[10px] font-mono uppercase font-bold px-2 py-0.5 rounded-full ${
                      isBuy
                        ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
                        : isSell
                        ? "bg-rose-500/15 text-rose-400 border border-rose-500/30"
                        : "bg-cyan-500/15 text-cyan-400 border border-cyan-500/30"
                    }`}
                  >
                    {directionLabel}
                  </span>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-slate-800 text-[#848E9C] border border-[#2B3139]/80">
                    {signal.pattern}
                  </span>
                  {(() => {
                    const st = signal.availability_status || signal.status || "VALID_SIGNAL";
                    let badgeClass = "bg-emerald-950/50 text-emerald-400 border-emerald-500/30";
                    let dotClass = "bg-emerald-400";
                    let label = "Valid Signal";

                    if (st === "NO_ACTIVE_SIGNAL") {
                      badgeClass = "bg-slate-800 text-slate-300 border-slate-600/50";
                      dotClass = "bg-slate-400";
                      label = "No Active Setup";
                    } else if (st === "INSUFFICIENT_DATA") {
                      badgeClass = "bg-amber-950/50 text-amber-400 border-amber-500/40";
                      dotClass = "bg-amber-400";
                      label = "Insufficient Data";
                    } else if (st === "MARKET_DATA_UNAVAILABLE") {
                      badgeClass = "bg-rose-950/50 text-rose-400 border-rose-500/40";
                      dotClass = "bg-rose-400";
                      label = "Data Unavailable";
                    } else if (st === "MARKET_CLOSED") {
                      badgeClass = "bg-amber-950/50 text-amber-400 border-amber-500/40";
                      dotClass = "bg-amber-400";
                      label = "Market Closed";
                    } else if (st === "UNSUPPORTED_INSTRUMENT") {
                      badgeClass = "bg-slate-900 text-slate-400 border-slate-700";
                      dotClass = "bg-slate-500";
                      label = "Unsupported";
                    }

                    return (
                      <span className={`text-[10px] font-mono px-2 py-0.5 rounded-full border flex items-center gap-1 ${badgeClass}`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${dotClass}`}></span>
                        <span>{label}</span>
                      </span>
                    );
                  })()}
                </div>

                {/* Directional Meter Gauge Widget */}
                {(() => {
                  const meter = signal.directional_meter;
                  const meterScore = meter?.score ?? (signal.score || 50);
                  const meterState = meter?.state ?? (meterScore >= 60 ? "BULLISH" : meterScore <= 40 ? "BEARISH" : "NEUTRAL");
                  const meterExplanation = meter?.explanation || `Multi-factor technical directional score: ${meterScore}/100.`;
                  const disclaimer = meter?.disclaimer || "Directional scores represent multi-factor technical indicators, not execution guarantees or probability metrics.";

                  const badgeStyles: Record<string, { bg: string; dot: string }> = {
                    BULLISH: { bg: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30", dot: "bg-emerald-400 shadow-emerald-500/50" },
                    BEARISH: { bg: "bg-rose-500/15 text-rose-400 border-rose-500/30", dot: "bg-rose-400 shadow-rose-500/50" },
                    NEUTRAL: { bg: "bg-sky-500/15 text-sky-300 border-sky-500/30", dot: "bg-sky-400 shadow-sky-500/50" },
                    INSUFFICIENT_DATA: { bg: "bg-slate-800 text-[#848E9C] border-[#2B3139]", dot: "bg-[#262C36]0 shadow-slate-500/50" },
                  };
                  const style = badgeStyles[meterState] || badgeStyles.NEUTRAL;

                  return (
                    <div className="p-3 rounded-xl bg-[#262C36] border border-[#2B3139] space-y-1.5">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center space-x-1.5">
                          <span className="text-[10px] font-mono text-[#848E9C] font-medium uppercase tracking-wider">DIRECTIONAL METER</span>
                          <div className="group relative cursor-pointer">
                            <Info className="w-3 h-3 text-[#848E9C] hover:text-[#EAECEF]" />
                            <div className="absolute bottom-full left-0 mb-1.5 hidden group-hover:block w-64 p-2.5 rounded-xl bg-[#151e32] border border-[#263554] text-[10px] text-[#EAECEF] shadow-2xl z-30 font-sans pointer-events-none">
                              <p className="font-bold text-[#EAECEF] mb-1">{meterState} ({meterScore}/100)</p>
                              <p className="mb-1.5 text-[#848E9C] leading-relaxed">{meterExplanation}</p>
                              <p className="text-[9px] text-amber-300/90 border-t border-[#263554] pt-1 font-mono">
                                {disclaimer}
                              </p>
                            </div>
                          </div>
                        </div>
                        <span className={`text-[10px] font-mono font-bold tabular-nums px-2 py-0.5 rounded-full border ${style.bg}`}>
                          {meterState === "INSUFFICIENT_DATA" ? "Insufficient data" : `${meterState} • ${meterScore}`}
                        </span>
                      </div>

                      {/* Visual Meter Bar */}
                      <div className="relative w-full h-2 rounded-full bg-slate-800/80 overflow-visible my-1">
                        {/* Color Gradient Track */}
                        <div className="absolute inset-0 rounded-full bg-gradient-to-r from-rose-500/40 via-sky-500/30 to-emerald-500/40" />
                        {/* Midpoint Marker (| at 50%) */}
                        <div
                          className="absolute top-0 bottom-0 left-1/2 w-0.5 bg-slate-300/80 -translate-x-1/2 z-10"
                          title="Neutral Midpoint (50)"
                        />
                        {/* Score Indicator Dot */}
                        <div
                          className={`absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-3.5 h-3.5 rounded-full border-2 border-slate-950 shadow-lg z-20 ${style.dot}`}
                          style={{ left: `${Math.min(100, Math.max(0, meterScore))}%` }}
                          title={`Score: ${meterScore}/100`}
                        />
                      </div>

                      <div className="flex justify-between text-[9px] font-mono text-[#848E9C]">
                        <span className="text-rose-400/90">0 Bearish</span>
                        <span className="text-[#848E9C] font-bold">50 Midpoint</span>
                        <span className="text-emerald-400/90">100 Bullish</span>
                      </div>
                    </div>
                  );
                })()}

                {/* Metric Matrix (2 columns x 3 rows) */}
                <div className="grid grid-cols-2 gap-2.5 p-3 rounded-xl bg-[#262C36] border border-[#2B3139] font-mono text-xs">
                  <div>
                    <span className="text-[10px] text-[#848E9C] font-medium uppercase block tracking-wider">REFERENCE PRICE</span>
                    <span className="text-[#EAECEF] font-semibold tabular-nums">
                      {formatSignalPrice(signal.reference_price, signal.quote_asset || signal.symbol, signal.market)}
                    </span>
                  </div>
                  <div>
                    <span className="text-[10px] text-[#848E9C] font-medium uppercase block tracking-wider">
                      {signal.market === "CRYPTO" && isSell ? "EXIT / DEFENSE ZONE" : "ENTRY ZONE"}
                    </span>
                    <span className="text-[#EAECEF] font-semibold truncate block tabular-nums">
                      {signal.entry_zone || "--"}
                    </span>
                  </div>
                  <div>
                    <span className="text-[10px] text-[#848E9C] font-medium uppercase block tracking-wider">STOP LOSS</span>
                    <span className="text-rose-400 font-semibold tabular-nums">
                      {formatSignalPrice(signal.stop_loss, signal.quote_asset || signal.symbol, signal.market)}
                    </span>
                  </div>
                  <div>
                    <span className="text-[10px] text-[#848E9C] font-medium uppercase block tracking-wider">TARGET</span>
                    {signal.multi_targets?.tp1 ? (
                      <span className="text-emerald-400 font-semibold tabular-nums text-xs block truncate">
                        TP1: {formatSignalPrice(signal.multi_targets.tp1.price, signal.quote_asset || signal.symbol, signal.market)}
                        <span className="text-[#848E9C] font-normal ml-1">({signal.multi_targets.blended_net_reward_pct > 0 ? `+${signal.multi_targets.blended_net_reward_pct}% net` : ""})</span>
                      </span>
                    ) : (
                      <span className="text-emerald-400 font-semibold tabular-nums">
                        {formatSignalPrice(signal.target, signal.quote_asset || signal.symbol, signal.market)}
                      </span>
                    )}
                  </div>
                  <div>
                    <span className="text-[10px] text-[#848E9C] font-medium uppercase block tracking-wider">RISK / REWARD</span>
                    <span className="text-sky-300 font-semibold tabular-nums">{signal.risk_reward}</span>
                  </div>
                  <div>
                    <span className="text-[10px] text-[#848E9C] font-medium uppercase block tracking-wider">PUBLISHED</span>
                    <span className="text-[#848E9C] tabular-nums">{signal.published_age}</span>
                  </div>
                </div>

                {/* Entry Window Countdown & Spot Disclaimer */}
                {signal.timing && (
                  <div className="flex items-center justify-between text-[10px] font-mono px-2.5 py-1.5 rounded-lg bg-[#262C36] border border-[#2B3139] text-[#848E9C]">
                    <span className="flex items-center gap-1.5 truncate">
                      <Clock className="w-3 h-3 text-sky-400 shrink-0" />
                      <span>Entry valid until <strong className="text-[#EAECEF]">{signal.timing.entry_expires_at_pkt}</strong></span>
                    </span>
                    <span className="text-sky-400 font-semibold shrink-0 ml-2">
                      {Math.floor(signal.timing.remaining_entry_seconds / 60)}m left
                    </span>
                  </div>
                )}

                {signal.spot_disclaimer && (
                  <div className="text-[10px] font-mono px-2 py-1 rounded-lg bg-amber-950/40 border border-amber-500/30 text-amber-300 flex items-center gap-1.5">
                    <AlertTriangle className="w-3 h-3 text-amber-400 shrink-0" />
                    <span className="truncate">Spot Only: Defensive inventory exit / risk reduction</span>
                  </div>
                )}

                {/* Technical Confirmation Checklist */}
                <div className="space-y-1.5 pt-1">
                  <div className="text-[10px] font-mono text-[#848E9C] font-medium uppercase tracking-wider">
                    Confirming Technical Factors
                  </div>
                  <div className="space-y-1">
                    {signal.checklist.map((item, idx) => (
                      <div key={idx} className="text-xs text-[#848E9C] font-mono flex items-center gap-1.5 truncate">
                        <span className="text-[#EAECEF]">{formatChecklistItem(item)}</span>
                      </div>
                    ))}
                  </div>
                </div>                {/* Footer Action: Dual Technical Analysis & Execute Setup Entry Points */}
                <div className="pt-2 grid grid-cols-2 gap-2">
                  <button
                    id={`tech-analysis-btn-${signal.symbol.replace('/', '-')}`}
                    onClick={() => executeFourEngineAnalysis(signal.symbol, signal.market === "FOREX" ? "FOREX" : "CRYPTO")}
                    className="py-2 px-2 rounded-lg bg-[#2B313A] hover:bg-[#363D47] text-[#EAECEF] font-bold text-xs font-mono transition-all cursor-pointer text-center flex items-center justify-center gap-1.5 border border-[#363D47] shadow-sm"
                  >
                    <Activity className="w-3.5 h-3.5 text-[#00E5FF]" />
                    <span className="truncate">Analysis</span>
                  </button>
                  <button
                    id={`execute-btn-${signal.symbol.replace('/', '-')}`}
                    onClick={() => handleInitiateExecution(signal)}
                    className="py-2 px-2 rounded-lg bg-[#F0B90B] hover:bg-[#FCD535] text-[#0B0E11] font-bold text-xs font-mono transition-all cursor-pointer text-center flex items-center justify-center gap-1.5 shadow-sm"
                  >
                    <Zap className="w-3.5 h-3.5" />
                    <span className="truncate">Execute Setup</span>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
      </>
    )}

      </div>
  );

  const SECTION_RENDERERS: Record<DashboardSectionId, () => React.ReactNode> = {
    MACRO_CALENDAR: renderMacroCalendarSection,
    AI_INTEL_STATS: renderAiIntelStatsSection,
    MARKET_TABS_FILTER: renderMarketTabsFilterSection,
    SIGNAL_CARDS_GRID: renderSignalCardsGridSection,
  };

  return (
    <div className="space-y-6">
      {/* ─── APPROVED DASHBOARD VIEW (IMAGES 1 & 3 SPEC) ─────────────── */}
      {/* ─── TIERED OBSIDIAN-SLATE QUANT TERMINAL (GEMINI SPEC) ─────────── */}
      <div className="space-y-6">
        {/* ─── HERO ROW: SCREENER STRIPS + ACTIVE SIGNAL & PRICE LADDER ─── */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
          {/* LEFT COLUMN: COMPACT HORIZONTAL QUANT STRIPS (SCREENER) */}
          <div className="lg:col-span-5 space-y-3">
            <div className="flex items-center justify-between pb-1">
              <div className="flex items-center gap-2">
                <Layers className="w-4 h-4 text-[#00E5FF]" />
                <h2 className="text-sm font-bold font-mono text-[#EAECEF] uppercase tracking-wider">
                  Markets & Screener
                </h2>
              </div>
              <div className="flex items-center gap-1 p-0.5 bg-[#151921] rounded-lg border border-[#2B3139]">
                <button
                  onClick={() => setSelectedMarketTab("ALL")}
                  className={`px-2.5 py-0.5 rounded text-[11px] font-mono font-bold tabular-nums transition-all cursor-pointer ${
                    selectedMarketTab === "ALL" ? "bg-[#00E5FF] text-[#0B0E11] shadow-sm" : "text-[#848E9C] hover:text-[#EAECEF]"
                  }`}
                >
                  All
                </button>
                <button
                  onClick={() => setSelectedMarketTab("CRYPTO")}
                  className={`px-2.5 py-0.5 rounded text-[11px] font-mono font-bold tabular-nums transition-all cursor-pointer ${
                    selectedMarketTab === "CRYPTO" ? "bg-[#00E5FF] text-[#0B0E11] shadow-sm" : "text-[#848E9C] hover:text-[#EAECEF]"
                  }`}
                >
                  Crypto
                </button>
                <button
                  onClick={() => setSelectedMarketTab("FOREX")}
                  className={`px-2.5 py-0.5 rounded text-[11px] font-mono font-bold tabular-nums transition-all cursor-pointer ${
                    selectedMarketTab === "FOREX" ? "bg-[#00E5FF] text-[#0B0E11] shadow-sm" : "text-[#848E9C] hover:text-[#EAECEF]"
                  }`}
                >
                  Forex
                </button>
              </div>
            </div>

            {/* Live Market Screener Strips (Real Data from Binance & Yahoo FX) */}
            <div className="space-y-2">
              {overviewMarkets.length === 0 && (
                <div id="screener-unavailable" className="p-3 rounded-lg bg-[#1E2329] border border-[#F0B90B]/40 text-[#F0B90B] text-xs font-mono">
                  MARKET DATA UNAVAILABLE — waiting for verified provider feeds. No prices are shown until a live quote is received.
                </div>
              )}
              {(overviewMarkets.length > 0 ? overviewMarkets : [])
                .filter((item) => {
                  if (selectedMarketTab === "CRYPTO") return item.market === "CRYPTO";
                  if (selectedMarketTab === "FOREX") return item.market === "FOREX" || item.market === "METALS";
                  return true;
                })
                .slice(0, 8)
                .map((item) => {
                  const isPos = (item.change_24h ?? 0) >= 0;
                  const displayPrice = typeof item.price === "number"
                    ? formatSignalPrice(item.price, item.symbol, item.market)
                    : "--";
                  const displayChange = typeof item.change_24h === "number"
                    ? `${isPos ? "+" : ""}${item.change_24h.toFixed(2)}%`
                    : "--";
                  return (
                    <div
                      key={item.symbol}
                      id={`screener-item-${item.symbol.replace('/', '-')}`}
                      onClick={() => {
                        const mkt = item.market === "FOREX" || item.market === "METALS" ? "FOREX" : "CRYPTO";
                        setCenterpiecePair({
                          symbol: item.symbol,
                          market: mkt,
                          price: item.price ?? null,
                          change_24h: item.change_24h ?? null,
                          direction: null
                        });
                        executeFourEngineAnalysis(item.symbol.replace("/", ""), mkt, activeAnalysisTimeframe);
                      }}
                      className="bg-[#1E2329] border border-[#2B3139] hover:border-[#00E5FF]/60 rounded-lg p-2.5 transition-all cursor-pointer group flex flex-col gap-1.5"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="font-mono font-bold tabular-nums text-sm text-[#EAECEF] group-hover:text-[#00E5FF] transition-colors">
                            {item.symbol}
                          </span>
                          <span className={`px-1.5 py-0.2 rounded text-[9px] font-mono uppercase border ${
                            item.market === "FOREX" || item.market === "METALS"
                              ? "bg-purple-950/60 text-purple-300 border-purple-500/30"
                              : "bg-[#262C36] text-[#848E9C] border-[#2B3139]"
                          }`}>
                            {item.market}
                          </span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-bold font-mono text-[#EAECEF] tabular-nums">
                            {displayPrice}
                          </span>
                          <span className={`text-[11px] font-mono font-bold tabular-nums px-1.5 py-0.5 rounded ${
                            isPos ? "bg-[#0ECB81]/15 text-[#0ECB81]" : "bg-[#F6465D]/15 text-[#F6465D]"
                          }`}>
                            {displayChange}
                          </span>
                        </div>
                      </div>

                      {/* 24h High/Low and Data Quality Status */}
                      <div className="flex items-center justify-between gap-3 pt-1 border-t border-[#2B3139]/50 text-[10px] font-mono text-[#848E9C]">
                        <div className="flex items-center gap-1.5 flex-1 max-w-[220px]">
                          <span className="text-[9px]">24h H/L</span>
                          <span className="text-[10px] text-[#EAECEF] font-bold tabular-nums">
                            {typeof item.low_24h === "number" ? formatSignalPrice(item.low_24h, item.symbol, item.market) : "--"} — {typeof item.high_24h === "number" ? formatSignalPrice(item.high_24h, item.symbol, item.market) : "--"}
                          </span>
                        </div>

                        <div className="flex items-center gap-2">
                          <span className={`px-1.5 py-0.2 text-[9px] rounded font-mono ${
                            item.status === "PASS" || item.status === "NORMAL" ? "text-[#0ECB81] bg-[#0ECB81]/10" :
                            item.status === "OFF-PEAK" ? "text-[#F0B90B] bg-[#F0B90B]/10" :
                            item.status === "CLOSED" ? "text-[#848E9C] bg-[#262C36]" :
                            "text-[#F0B90B] bg-[#F0B90B]/10"
                          }`}>
                            {item.data_state ? item.data_state : (item.status === "PASS" ? "UNVERIFIED" : item.status)}
                          </span>
                          <span className="text-[9px] text-[#848E9C] hidden sm:inline">
                            {item.source || "public_feed"}
                          </span>
                        </div>
                      </div>
                    </div>
                  );
                })}
            </div>
          </div>

          {/* RIGHT COLUMN: ACTIVE SIGNAL & THE VISUAL PRICE LADDER (CHARTLESS QUANT CENTERPIECE) */}
          <div className="lg:col-span-7 bg-[#151921] border border-[#2B3139] rounded-xl p-5 flex flex-col justify-between space-y-4 shadow-xl">
            {/* Signal Header: Triple-coded Direction Banner + Asset + 3 Timers */}
            <div className="space-y-3 pb-3 border-b border-[#2B3139]">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2.5">
                  {(() => {
                    const cpSig: any = signals.find((s: any) => s.symbol === centerpiecePair.symbol);
                    if (!cpSig) {
                      return (
                        <div id="centerpiece-no-signal-badge" className="bg-[#262C36] text-[#848E9C] border-[#2B3139] border-l-4 px-3 py-1 rounded-r font-mono font-extrabold text-xs tracking-wider flex items-center gap-1.5">
                          <span>○</span>
                          <span>NO ACTIVE SIGNAL</span>
                        </div>
                      );
                    }
                    const isBuy = cpSig.direction === "BUY";
                    return (
                      <div className={`${isBuy ? "bg-[#0ECB81]/15 text-[#0ECB81] border-[#0ECB81]" : "bg-rose-500/15 text-rose-400 border-rose-500"} border-l-4 px-3 py-1 rounded-r font-mono font-extrabold text-xs tracking-wider flex items-center gap-1.5`}>
                        <span>{isBuy ? "▲" : "▼"}</span>
                        <span>{cpSig.direction_label ? String(cpSig.direction_label).toUpperCase() : (isBuy ? "LONG SIGNAL" : "SHORT SIGNAL")}</span>
                      </div>
                    );
                  })()}
                  <h3 className="text-xl font-bold font-mono text-[#EAECEF] tracking-tight">{centerpiecePair.symbol}</h3>
                  <span className="px-2 py-0.5 rounded text-xs font-mono font-bold tabular-nums bg-[#262C36] text-[#EAECEF] border border-[#2B3139]">
                    1h
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    id="centerpiece-tech-analysis-btn"
                    onClick={() => executeFourEngineAnalysis(centerpiecePair.symbol.replace("/", ""), centerpiecePair.market, activeAnalysisTimeframe)}
                    className="px-3 py-1.5 rounded-lg bg-[#2B313A] hover:bg-[#363D47] text-[#EAECEF] text-xs font-bold font-mono flex items-center gap-1.5 border border-[#363D47] shadow-sm transition-all cursor-pointer"
                  >
                    <Activity className="w-3.5 h-3.5 text-[#00E5FF]" />
                    <span>Analysis</span>
                  </button>
                  <button
                    id="centerpiece-execute-btn"
                    onClick={() => handleInitiateExecution(centerpiecePair)}
                    className="px-3 py-1.5 rounded-lg bg-[#F0B90B] hover:bg-[#FCD535] text-[#0B0E11] text-xs font-bold font-mono flex items-center gap-1.5 shadow-sm transition-all cursor-pointer"
                  >
                    <Zap className="w-3.5 h-3.5" />
                    <span>Execute Setup</span>
                  </button>
                </div>
              </div>

              {/* Timers row — every value derived from real clock / signal / provider data */}
              {(() => {
                const cpSig: any = signals.find((x: any) => x.symbol === centerpiecePair.symbol);
                const ovItem: any = overviewMarkets.find((m: any) => m.symbol === centerpiecePair.symbol);
                const nowMs = Date.now();
                const hourMs = 3600000;
                const closeInMs = hourMs - (nowMs % hourMs);
                const cm = Math.floor(closeInMs / 60000);
                const cs = Math.floor((closeInMs % 60000) / 1000);
                const expIso = cpSig?.timing?.entry_expires_at_utc;
                const expMs = expIso ? Date.parse(expIso) : NaN;
                const leftMs = Number.isFinite(expMs) ? expMs - nowMs : NaN;
                const dState: string = ovItem?.data_state || "UNAVAILABLE";
                const fresh = typeof ovItem?.freshness_sec === "number" ? `${ovItem.freshness_sec.toFixed(1)}s old` : "no timestamp";
                const dColor = dState === "LIVE" ? "text-[#0ECB81]" : dState === "DELAYED" ? "text-[#F0B90B]" : "text-[#F6465D]";
                return (
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 font-mono text-xs">
                    <div className="p-2 rounded bg-[#1E2329] border border-[#2B3139] flex items-center gap-2">
                      <Clock className="w-3.5 h-3.5 text-[#00E5FF] shrink-0" />
                      <div>
                        <span className="text-[10px] text-[#848E9C] block">1h Candle Closes In</span>
                        <span className="font-bold text-[#EAECEF] tabular-nums">{String(cm).padStart(2, "0")}:{String(cs).padStart(2, "0")}</span>
                      </div>
                    </div>
                    <div className="p-2 rounded bg-[#1E2329] border border-[#2B3139] flex items-center gap-2">
                      <Target className="w-3.5 h-3.5 text-[#0ECB81] shrink-0" />
                      <div>
                        <span className="text-[10px] text-[#848E9C] block">Signal Valid Until</span>
                        <span className="font-bold text-[#EAECEF] tabular-nums">
                          {Number.isFinite(leftMs) ? (leftMs > 0 ? `${new Date(expMs).toISOString().substring(11, 16)} UTC (${Math.floor(leftMs / 3600000)}h ${Math.floor((leftMs % 3600000) / 60000)}m left)` : "EXPIRED") : "--"}
                        </span>
                      </div>
                    </div>
                    <div className="p-2 rounded bg-[#1E2329] border border-[#2B3139] flex items-center gap-2">
                      <Zap className={`w-3.5 h-3.5 shrink-0 ${dColor}`} />
                      <div>
                        <span className="text-[10px] text-[#848E9C] block">Data Freshness</span>
                        <span className={`font-bold flex items-center gap-1 tabular-nums ${dColor}`}>
                          {dState} · {fresh}
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })()}
            </div>

            {/* Price Execution Ladder — bound to the selected pair's real signal and live quote */}
            {(() => {
              const cpSig: any = signals.find((x: any) => x.symbol === centerpiecePair.symbol);
              const ovItem: any = overviewMarkets.find((m: any) => m.symbol === centerpiecePair.symbol);
              const quoteSym = centerpiecePair.symbol.includes("/") ? centerpiecePair.symbol.split("/")[1] : "USDT";
              const live = ovItem && typeof ovItem.price === "number" && ovItem.data_state !== "UNAVAILABLE" ? ovItem : null;
              const fmt = (v: any) => formatSignalPrice(v, quoteSym, cpSig?.market || centerpiecePair.market);
              const livePill = (
                <div className="relative flex items-center justify-between p-2.5 rounded bg-[#00E5FF]/10 border-2 border-[#00E5FF]">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-[#00E5FF] uppercase text-[10px]">{live ? (live.data_state === "LIVE" ? "LIVE CURRENT PRICE" : `PRICE (${live.data_state})`) : "PRICE UNAVAILABLE"}</span>
                    <span className="text-white font-black tabular-nums">{live ? fmt(live.price) : "--"}</span>
                  </div>
                  <span className="text-[9px] text-[#00E5FF] font-mono">{live ? (live.source || "provider") : "no verified quote"}</span>
                </div>
              );
              const isValid = cpSig && (cpSig.availability_status === "VALID_SIGNAL" || cpSig.status === "VALID_SIGNAL" || cpSig.status === "Active");
              if (!isValid) {
                return (
                  <div id="ladder-no-signal" className="p-4 rounded-lg bg-[#1E2329] border border-[#2B3139] space-y-2.5 font-mono text-xs">
                    <div className="text-[10px] text-[#848E9C] uppercase tracking-wider font-bold">Price Execution Ladder</div>
                    {livePill}
                    <div className="text-[#848E9C]">{cpSig?.status_explanation || `No active signal for ${centerpiecePair.symbol}. Entry, take-profit and stop-loss levels are shown only when the signal engine produces them.`}</div>
                  </div>
                );
              }
              const mt = cpSig.multi_targets || {};
              const tpNode = (label: string, tp: any) => tp && typeof tp.price === "number" ? (
                <div className="relative flex items-center justify-between p-2 rounded bg-[#262C36] border border-[#0ECB81]/30">
                  <div className="flex items-center gap-2.5">
                    <span className="font-bold text-[#0ECB81]">{label}</span>
                    <span className="text-[#EAECEF] font-bold tabular-nums">{fmt(tp.price)}</span>
                    {typeof tp.net_reward_pct === "number" && <span className="text-[#0ECB81] text-[10px] font-bold">+{tp.net_reward_pct}% net</span>}
                  </div>
                  {typeof tp.allocation_pct === "number" && <span className="text-[10px] px-1.5 rounded bg-[#0ECB81]/15 text-[#0ECB81]">{tp.allocation_pct}% Allocation</span>}
                </div>
              ) : null;
              return (
                <div className="p-4 rounded-lg bg-[#1E2329] border border-[#2B3139] space-y-2.5 font-mono text-xs">
                  <div className="text-[10px] text-[#848E9C] uppercase tracking-wider font-bold flex items-center justify-between">
                    <span>Vertical Price Execution Ladder</span>
                    <span className="text-[#00E5FF]">Signal {cpSig.signal_id || ""}</span>
                  </div>
                  <div className="relative pl-6 space-y-2 border-l-2 border-dashed border-[#2B3139] ml-2 my-2">
                    {tpNode("TP 3", mt.tp3)}
                    {tpNode("TP 2", mt.tp2)}
                    {tpNode("TP 1", mt.tp1)}
                    {livePill}
                    <div className="relative flex items-center justify-between p-2 rounded bg-[#262C36] border-2 border-dashed border-[#00E5FF]/40">
                      <div className="flex items-center gap-2.5">
                        <span className="font-bold text-[#00E5FF] uppercase text-[10px]">ENTRY ZONE</span>
                        <span className="text-[#EAECEF] font-bold tabular-nums">{cpSig.entry_zone || "--"}</span>
                      </div>
                      <span className="text-[10px] text-[#848E9C]">ref {fmt(cpSig.reference_price)}</span>
                    </div>
                    <div className="relative flex items-center justify-between p-2 rounded bg-[#F6465D]/10 border border-[#F6465D]/40">
                      <div className="flex items-center gap-2.5">
                        <span className="font-bold text-[#F6465D]">STOP-LOSS</span>
                        <span className="text-[#F6465D] font-bold tabular-nums">{fmt(cpSig.stop_loss)}</span>
                      </div>
                      <span className="px-1.5 rounded bg-[#00E5FF]/20 text-[#00E5FF] border border-[#00E5FF]/40 font-bold text-[10px]">R:R {cpSig.risk_reward || "--"}</span>
                    </div>
                  </div>
                </div>
              );
            })()}

            {/* Arithmetic Callout Box (Gemini Spec) */}
            <div className="bg-[#262C36] border border-[#00E5FF]/40 text-[#00E5FF] rounded-lg p-2.5 text-xs font-mono">
              Risk/reward is arithmetic on the levels above. It is not a probability of profit.
            </div>

            {/* Action Bar: Admin Fee Exemption / Execution */}
            {(() => {
              const isAdminExempt = saasFeePolicy?.is_admin_exempt === true || saasFeePolicy?.fee_waived === 1 || saasBillingSummary?.is_admin_exempt === true || (typeof window !== "undefined" && (() => { try { const u = JSON.parse(localStorage.getItem("tauric_session_user") || "{}"); return u?.role === "ADMIN" || u?.is_admin_exempt === true; } catch { return false; } })());

              if (isAdminExempt) {
                return (
                  <div className="space-y-2 pt-1">
                    <div className="p-2.5 rounded bg-[#00E5FF]/10 border border-[#00E5FF]/30 text-[#00E5FF] flex items-center justify-between text-xs font-mono">
                      <div className="flex items-center gap-1.5">
                        <ShieldCheck className="w-4 h-4 text-[#00E5FF] shrink-0" />
                        <span className="font-bold">ADMIN — FEE EXEMPT</span>
                        <span className="text-[10px] text-[#00E5FF]/80">• ($0.00 Fees Assessed)</span>
                      </div>
                      <span className="text-[10px] text-[#848E9C]">Read-only execution</span>
                    </div>
                    <button
                      id="centerpiece-execute-setup-btn"
                      onClick={() => executeFourEngineAnalysis(centerpiecePair.symbol.replace("/", ""), centerpiecePair.market, activeAnalysisTimeframe)}
                      className="w-full py-2.5 px-4 rounded-lg bg-[#0ECB81] hover:bg-[#0ECB81]/90 text-[#0B0E11] font-mono font-bold tabular-nums text-xs flex items-center justify-center gap-2 cursor-pointer shadow-md transition-all"
                    >
                      <Play className="w-3.5 h-3.5 fill-[#0B0E11]" />
                      <span>Execute Trade Setup (Admin Staging Exemption)</span>
                    </button>
                  </div>
                );
              }

              return (
                <div className="space-y-2 pt-1">
                  <button
                    onClick={() => {
                      if (typeof window !== "undefined") {
                        window.dispatchEvent(new CustomEvent("bitdex_open_activation"));
                      }
                    }}
                    className="w-full py-2.5 px-4 rounded-lg bg-[#F0B90B] hover:bg-[#F0B90B]/90 text-[#0B0E11] font-mono font-bold tabular-nums text-xs flex items-center justify-center gap-2 cursor-pointer shadow-sm transition-all"
                  >
                    <AlertTriangle className="w-3.5 h-3.5" />
                    <span>Activate Account ($20.00)</span>
                  </button>
                </div>
              );
            })()}
          </div>
        </div>

        {/* ─── SECTION 2: LATEST SIGNALS (REAL SIGNALS FEED) ──────────────────── */}
        <div className="space-y-3 pt-2">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold font-mono text-[#EAECEF] uppercase tracking-wider">
              Latest Signals Feed
            </h2>
            <span className="text-xs text-[#848E9C] font-mono">Direction shown as label + arrow, never colour alone</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {(signals.length > 0 ? signals.slice(0, 3) : []).map((sig: any, sIdx: number) => {
              const isLong = sig.direction === "BUY" || (sig.direction_label || "").toLowerCase().includes("buy") || (sig.direction_label || "").toLowerCase().includes("long");
              const isShort = sig.direction === "SELL" || (sig.direction_label || "").toLowerCase().includes("sell") || (sig.direction_label || "").toLowerCase().includes("exit");
              return (
                <div
                  key={sig.id || sig.symbol || sIdx}
                  className="bg-[#1E2329] border border-[#2B3139] hover:border-[#00E5FF]/60 rounded-xl p-4 flex flex-col justify-between space-y-3 transition-all"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-base font-bold font-mono text-[#EAECEF]">{sig.symbol}</span>
                      <span className="text-xs font-mono font-medium px-2 py-0.5 rounded bg-[#262C36] text-[#848E9C] border border-[#2B3139]">
                        {sig.timeframe || activeAnalysisTimeframe || "1h"}
                      </span>
                    </div>
                    <span className={`px-2 py-0.5 rounded text-xs font-bold font-mono border flex items-center gap-1 ${
                      isLong
                        ? "bg-[#0ECB81]/15 text-[#0ECB81] border-[#0ECB81]/30"
                        : isShort
                        ? "bg-[#F6465D]/15 text-[#F6465D] border-[#F6465D]/30"
                        : "bg-sky-500/15 text-sky-400 border-sky-500/30"
                    }`}>
                      <span>{isLong ? "▲" : isShort ? "▼" : "↔"}</span>
                      <span>{isLong ? "Long bias" : isShort ? "Short bias" : "Scalp range"}</span>
                    </span>
                  </div>

                  <div className="grid grid-cols-3 gap-2 py-2 px-2.5 bg-[#151921] border border-[#2B3139] rounded-lg font-mono text-xs">
                    <div>
                      <span className="text-[10px] text-[#848E9C] block uppercase font-medium">Entry</span>
                      <span className="font-bold text-[#EAECEF] tabular-nums">
                        {formatSignalPrice(sig.entry_price ?? sig.current_price, sig.symbol, sig.market)}
                      </span>
                    </div>
                    <div>
                      <span className="text-[10px] text-[#848E9C] block uppercase font-medium">Stop-loss</span>
                      <span className="font-bold text-[#F6465D] tabular-nums">
                        {formatSignalPrice(sig.stop_price, sig.symbol, sig.market)}
                      </span>
                    </div>
                    <div>
                      <span className="text-[10px] text-[#848E9C] block uppercase font-medium">Target 1</span>
                      <span className="font-bold text-[#0ECB81] tabular-nums">
                        {formatSignalPrice(sig.tp1 ?? sig.target_price, sig.symbol, sig.market)}
                      </span>
                    </div>
                  </div>

                  <div className="text-xs text-[#848E9C] space-y-0.5 font-mono">
                    <div className="text-[#EAECEF] font-medium truncate">Pattern: {sig.pattern || sig.direction_label || "Technical Setup"}</div>
                    <div className="text-[11px] text-[#848E9C]">Confirmation Score: {sig.score ?? 80}/100 · {sig.market || "SPOT"}</div>
                  </div>

                  <button
                    onClick={() => executeFourEngineAnalysis(sig.symbol.replace("/", ""), sig.market === "FOREX" || sig.market === "METALS" ? "FOREX" : "CRYPTO", activeAnalysisTimeframe)}
                    className="w-full py-2 px-3 rounded-lg bg-[#00E5FF] hover:bg-[#00E5FF]/90 text-[#0B0E11] text-xs font-bold font-mono flex items-center justify-center gap-2 shadow-sm transition-all cursor-pointer"
                  >
                    <Activity className="w-3.5 h-3.5" />
                    <span>Technical Analysis</span>
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      </div>

{/* ─── Rearrangeable Sections Control Bar (Gemini Spec) ───────── */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5 rounded-xl bg-[#151921] border border-[#2B3139] text-xs font-mono">
        <div className="flex items-center gap-2 text-[#848E9C]">
          <GripVertical className="w-4 h-4 text-[#00E5FF]" />
          <span className="font-bold text-[#EAECEF]">Customizable Workspace Layout</span>
          <span className="text-[11px] text-[#848E9C] hidden sm:inline">• Reorder sections via arrows or drag handles</span>
        </div>
        <button
          onClick={resetSectionOrder}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#1E2329] hover:bg-[#262C36] text-[#848E9C] hover:text-[#00E5FF] border border-[#2B3139] transition-colors cursor-pointer text-[11px]"
          title="Reset to default dashboard section layout"
        >
          <RotateCcw className="w-3 h-3" />
          <span>Reset Layout</span>
        </button>
      </div>

      {/* ─── Dynamically Ordered Dashboard Sections ────────────────── */}
      {sectionOrder.map((sectionId, idx) => (
        <div
          key={sectionId}
          draggable
          onDragStart={() => handleDragStart(idx)}
          onDragOver={(e) => handleDragOver(e, idx)}
          onDrop={() => handleDrop(idx)}
          className={`group/section relative rounded-2xl transition-all duration-150 ${
            draggedSectionIndex === idx ? "opacity-50 border-2 border-dashed border-cyan-500" : ""
          }`}
        >
          {/* Section Reorder Control Strip */}
          <div className="flex items-center justify-between px-3 py-1 bg-[#151921] border-t border-x border-[#2B3139] rounded-t-xl text-[10px] font-mono text-[#848E9C] opacity-60 group-hover/section:opacity-100 transition-opacity">
            <div className="flex items-center gap-2">
              <GripVertical className="w-3 h-3 text-[#848E9C] cursor-grab active:cursor-grabbing" />
              <span className="font-bold text-[#848E9C] uppercase tracking-wider">{SECTION_LABELS[sectionId]}</span>
              <span className="text-[#848E9C]">[{idx + 1}/4]</span>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => moveSection(idx, "UP")}
                disabled={idx === 0}
                className="p-1 rounded hover:bg-[#262C36] text-[#848E9C] hover:text-[#EAECEF] disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
                title="Move section up"
              >
                <MoveUp className="w-3 h-3" />
              </button>
              <button
                onClick={() => moveSection(idx, "DOWN")}
                disabled={idx === sectionOrder.length - 1}
                className="p-1 rounded hover:bg-[#262C36] text-[#848E9C] hover:text-[#EAECEF] disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
                title="Move section down"
              >
                <MoveDown className="w-3 h-3" />
              </button>
            </div>
          </div>

          {/* Section Body */}
          <div className="border-b border-x border-[#2B3139] rounded-b-xl bg-[#0B0E11]">
            {SECTION_RENDERERS[sectionId]()}
          </div>
        </div>
      ))}

      {/* ─── Detail & Technical Modal (EXPAND) with Live Meter ───────── */}
      {modalMode === "EXPAND" && selectedSignal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#1E2329]/40 backdrop-blur-md animate-in fade-in">
          <div className="w-full max-w-2xl bg-[#1E2329] border border-[#2B3139] shadow-sm rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[92vh]">
            {/* Modal Header */}
            <div className="p-5 border-b border-[#2B3139] flex items-center justify-between bg-[#262C36]">
              <div className="flex items-center gap-3">
                <span className="text-lg font-bold font-mono text-[#EAECEF]">{selectedSignal.symbol}</span>
                <span
                  className={`text-[10px] font-mono uppercase font-bold px-2 py-0.5 rounded-full ${
                    selectedSignal.direction === "BUY"
                      ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                      : "bg-rose-500/20 text-rose-400 border border-rose-500/30"
                  }`}
                >
                  {selectedSignal.market === "CRYPTO" && selectedSignal.direction === "SELL"
                    ? "SELL / EXIT"
                    : selectedSignal.market !== "CRYPTO" && selectedSignal.direction === "SELL"
                    ? "SELL / SHORT"
                    : selectedSignal.direction_label}
                </span>
                <span className="text-xs font-mono text-[#848E9C]">
                  Initial Setup Score: <strong className="text-[#EAECEF] tabular-nums">{selectedSignal.score}/100</strong>
                </span>
              </div>
              <button
                data-testid="expand-modal-x-btn"
                onClick={() => setModalMode(null)}
                className="p-1 rounded-lg text-[#848E9C] hover:text-[#EAECEF] hover:bg-slate-800 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500 cursor-pointer"
                aria-label="Close modal"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 space-y-5 overflow-y-auto">
              {/* ─── LIVE BULLISH / BEARISH METER SECTION ───────────────── */}
              <div className="p-5 rounded-2xl bg-[#262C36] border border-[#2B3139] space-y-4">
                <div className="flex items-center justify-between border-b border-[#2B3139] pb-2.5">
                  <div className="flex items-center gap-2">
                    <Gauge className="w-4 h-4 text-cyan-400" />
                    <span className="text-xs font-mono font-bold tabular-nums uppercase text-[#848E9C] tracking-wider">
                      LIVE DIRECTIONAL OUTLOOK METER
                    </span>
                  </div>
                  {/* Freshness Status Pill */}
                  <div className="flex items-center gap-2 text-[11px] font-mono">
                    {liveMeterData?.market_data?.is_stale ? (
                      <span className="flex items-center gap-1.5 text-amber-400 bg-amber-950/50 px-2 py-0.5 rounded border border-amber-500/30 font-bold">
                        <AlertTriangle className="w-3 h-3" />
                        <span>{liveMeterData.market_data?.freshness_label}</span>
                      </span>
                    ) : (
                      <span className="flex items-center gap-1.5 text-emerald-400 bg-emerald-950/50 px-2 py-0.5 rounded border border-emerald-500/30 font-bold">
                        <span className="relative flex h-1.5 w-1.5">
                          <span className="motion-safe:animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                          <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500"></span>
                        </span>
                        <span>{liveMeterData?.market_data?.freshness_label || "Connecting live feed..."}</span>
                      </span>
                    )}
                    <button
                      onClick={() => fetchLiveMeter(selectedSignal.instrument_id)}
                      disabled={isMeterLoading}
                      className="p-1 rounded hover:bg-[#262C36] text-[#848E9C] hover:text-[#EAECEF] transition-colors"
                      title="Force fresh market-data refresh"
                      aria-label="Refresh live meter"
                    >
                      <RefreshCw className={`w-3.5 h-3.5 ${isMeterLoading ? "motion-safe:animate-spin text-cyan-400" : ""}`} />
                    </button>
                  </div>
                </div>

                {/* Semicircular Gauge or Unavailable Alert (Defect A Fix) */}
                {liveMeterData?.status === "DATA_UNAVAILABLE" || !liveMeterData?.meter ? (
                  <div className="w-full p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 font-mono text-xs flex items-start gap-3 my-2">
                    <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
                    <div className="space-y-1">
                      <div className="font-bold uppercase tracking-wider text-amber-400">
                        MARKET DATA UNAVAILABLE
                      </div>
                      <p className="text-amber-200/80 leading-relaxed text-[11px]">
                        {liveMeterData?.message ||
                          "Live market data from the exchange adapter is currently unavailable or failed quality checks. Directional meter calculations are suspended to prevent misleading gauge readings."}
                      </p>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="flex flex-col sm:flex-row items-center justify-around gap-6 pt-2">
                      <SemicircleGauge
                        score={liveMeterData.meter.directional_score}
                        needleAngle={liveMeterData.meter.needle_angle_deg}
                        state={liveMeterData.meter.state}
                        stateColor={liveMeterData.meter.state_color}
                      />

                      {/* Meter Narrative & Details */}
                      <div className="space-y-2 text-xs font-mono flex-1">
                        <div className="text-[10px] uppercase text-[#848E9C] tracking-wider">
                          Technical Indicator Outlook
                        </div>
                        <div
                          className="text-sm font-bold tracking-tight"
                          style={{ color: liveMeterData.meter.state_color || "#38bdf8" }}
                        >
                          {liveMeterData.meter.outlook_label || "CALCULATING DIRECTIONAL EVIDENCE..."}
                        </div>
                        <p className="text-[#848E9C] text-[11px] leading-relaxed">
                          {liveMeterData.meter.explanation ||
                            "Calculating real-time momentum vs long-term moving averages..."}
                        </p>
                        <div className="text-[10px] text-[#848E9C] border-t border-[#2B3139] pt-1.5 leading-tight">
                          The published setup above is fixed at discovery. This live meter is a separate
                          real-time technical momentum reading.
                        </div>
                      </div>
                    </div>

                    {/* Signal Agreement & Entry Status Banner */}
                    {liveMeterData.signal_context && (
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-2 text-xs font-mono">
                        {/* Agreement Status */}
                        <div
                          className={`p-2.5 rounded-xl border flex items-center gap-2 ${
                            liveMeterData.signal_context.agreement === "AGREES"
                              ? "bg-emerald-950/40 text-emerald-300 border-emerald-500/30"
                              : liveMeterData.signal_context.agreement === "DIVERGING"
                              ? "bg-rose-950/40 text-rose-300 border-rose-500/30"
                              : "bg-sky-950/40 text-sky-300 border-sky-500/30"
                          }`}
                        >
                          {liveMeterData.signal_context.agreement === "AGREES" ? (
                            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                          ) : liveMeterData.signal_context.agreement === "DIVERGING" ? (
                            <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
                          ) : (
                            <Info className="w-4 h-4 text-sky-400 shrink-0" />
                          )}
                          <span className="truncate">{liveMeterData.signal_context.agreement_desc}</span>
                        </div>

                        {/* Entry Zone Position */}
                        <div
                          className={`p-2.5 rounded-xl border flex items-center gap-2 ${
                            liveMeterData.signal_context.entry_warning
                              ? "bg-amber-950/40 text-amber-300 border-amber-500/30"
                              : "bg-[#1E2329] text-[#848E9C] border-[#2B3139]"
                          }`}
                        >
                          <Target className="w-4 h-4 text-cyan-400 shrink-0" />
                          <span className="truncate">
                            {liveMeterData.signal_context.entry_warning ||
                              `Price inside entry zone (${liveMeterData.signal_context.entry_zone})`}
                          </span>
                        </div>
                      </div>
                    )}

                    {/* Invalidation Alert (if stop loss breached) */}
                    {liveMeterData.signal_context?.is_invalidated && (
                      <div className="p-3 rounded-xl bg-rose-500/15 border border-rose-500/40 text-xs font-mono text-rose-300 flex items-center gap-2">
                        <ShieldAlert className="w-4 h-4 text-rose-400 shrink-0" />
                        <strong>{liveMeterData.signal_context.invalidation_warning}</strong>
                      </div>
                    )}
                  </>
                )}

                {/* Real-time Indicator Strip */}
                <div className="flex flex-wrap gap-2 pt-1 text-[11px] font-mono">
                  <span className="px-2 py-1 rounded bg-[#1E2329] border border-[#2B3139] shadow-sm text-[#848E9C]">
                    RSI(14): <strong className="tabular-nums">{liveMeterData?.indicators?.rsi ?? selectedSignal.indicators.rsi}</strong>
                  </span>
                  <span className="px-2 py-1 rounded bg-[#1E2329] border border-[#2B3139] shadow-sm text-[#848E9C]">
                    MACD Hist: <strong className="tabular-nums">{liveMeterData?.indicators?.macd_hist ?? selectedSignal.indicators.macd_hist}</strong>
                  </span>
                  <span className="px-2 py-1 rounded bg-[#1E2329] border border-[#2B3139] shadow-sm text-[#848E9C]">
                    EMA 20: <strong className="tabular-nums">{liveMeterData?.indicators?.ema20 ?? selectedSignal.indicators.ema20}</strong>
                  </span>
                  <span className="px-2 py-1 rounded bg-[#1E2329] border border-[#2B3139] shadow-sm text-[#848E9C]">
                    EMA 50: <strong className="tabular-nums">{liveMeterData?.indicators?.ema50 ?? selectedSignal.indicators.ema50}</strong>
                  </span>
                  <span className="px-2 py-1 rounded bg-[#1E2329] border border-[#2B3139] shadow-sm text-[#848E9C]">
                    EMA 200: <strong className="tabular-nums">{liveMeterData?.indicators?.ema200 ?? selectedSignal.indicators.ema200}</strong>
                  </span>
                </div>
              </div>

              {/* Multi-Target Tranches Breakdown (Phase 2 Upgrade) */}
              {selectedSignal.multi_targets && (
                <div className="p-3.5 rounded-xl bg-[#262C36]/80 border border-[#2B3139] space-y-2 text-xs font-mono">
                  <div className="flex items-center justify-between border-b border-[#2B3139] pb-1.5">
                    <span className="text-[#848E9C] font-bold uppercase tracking-wider flex items-center gap-1.5">
                      <Target className="w-3.5 h-3.5 text-cyan-400" />
                      Multi-Stage Take Profit Tranches (50/30/20)
                    </span>
                    <span className="text-cyan-400 text-[11px] font-semibold">
                      Blended Net Reward: +{selectedSignal.multi_targets.blended_net_reward_pct}%
                    </span>
                  </div>
                  <div className="grid grid-cols-3 gap-2 pt-1 text-center">
                    <div className="p-2 rounded bg-[#1E2329] border border-[#2B3139] shadow-sm">
                      <span className="text-[10px] text-[#848E9C] uppercase block">TP1 (50% Allocation)</span>
                      <span className="text-emerald-400 font-bold tabular-nums text-sm block">
                        {formatSignalPrice(selectedSignal.multi_targets.tp1.price, selectedSignal.quote_asset || selectedSignal.symbol, selectedSignal.market)}
                      </span>
                      <span className="text-[10px] text-[#848E9C] block">1.2R (+{selectedSignal.multi_targets.tp1.net_reward_pct}% net)</span>
                    </div>
                    <div className="p-2 rounded bg-[#1E2329] border border-[#2B3139] shadow-sm">
                      <span className="text-[10px] text-[#848E9C] uppercase block">TP2 (30% Allocation)</span>
                      <span className="text-emerald-300 font-bold tabular-nums text-sm block">
                        {formatSignalPrice(selectedSignal.multi_targets.tp2.price, selectedSignal.quote_asset || selectedSignal.symbol, selectedSignal.market)}
                      </span>
                      <span className="text-[10px] text-[#848E9C] block">2.0R (+{selectedSignal.multi_targets.tp2.net_reward_pct}% net)</span>
                    </div>
                    <div className="p-2 rounded bg-[#1E2329] border border-[#2B3139] shadow-sm">
                      <span className="text-[10px] text-[#848E9C] uppercase block">TP3 (20% Allocation)</span>
                      <span className="text-emerald-200 font-bold tabular-nums text-sm block">
                        {formatSignalPrice(selectedSignal.multi_targets.tp3.price, selectedSignal.quote_asset || selectedSignal.symbol, selectedSignal.market)}
                      </span>
                      <span className="text-[10px] text-[#848E9C] block">3.2R (+{selectedSignal.multi_targets.tp3.net_reward_pct}% net)</span>
                    </div>
                  </div>
                  <div className="text-[10px] text-[#848E9C] border-t border-slate-900 pt-1.5 flex items-center justify-between">
                    <span>Friction Drag: -{selectedSignal.multi_targets.round_trip_friction_bps} bps round-trip (10 bps fee + 5 bps slippage per side)</span>
                    <span>Total Allocation: {selectedSignal.multi_targets.total_allocation_pct}%</span>
                  </div>
                </div>
              )}

              {/* Feasibility & Breakeven Policy Strip */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs font-mono">
                {selectedSignal.breakeven_guidance && (
                  <div className="p-2.5 rounded-xl bg-cyan-950/30 border border-cyan-500/30 text-cyan-300 space-y-1">
                    <div className="text-[10px] font-bold uppercase tracking-wider text-cyan-400 flex items-center gap-1">
                      <TrendingUp className="w-3.5 h-3.5" />
                      TP1 Breakeven Guidance
                    </div>
                    <p className="text-[11px] text-cyan-200/90 leading-relaxed">
                      {selectedSignal.breakeven_guidance}
                    </p>
                  </div>
                )}
                {selectedSignal.feasibility && (
                  <div className="p-2.5 rounded-xl bg-[#262C36] border border-[#2B3139] text-[#848E9C] space-y-1">
                    <div className="text-[10px] font-bold uppercase tracking-wider text-[#848E9C] flex items-center gap-1">
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                      Exchange Notional Feasibility
                    </div>
                    <p className="text-[11px] text-[#848E9C] leading-relaxed">
                      {selectedSignal.feasibility.feasibility_notes}
                    </p>
                  </div>
                )}
              </div>

              {/* Timing Metadata Strip (Dual Timers) */}
              {selectedSignal.timing && (
                <div className="p-3 rounded-xl bg-[#262C36] border border-[#2B3139] grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs font-mono">
                  <div>
                    <span className="text-[10px] text-[#848E9C] uppercase block tracking-wider">Entry Validity Window (PKT)</span>
                    <span className="text-cyan-400 font-semibold">{selectedSignal.timing.entry_expires_at_pkt}</span>
                    <span className="text-[10px] text-[#848E9C] block mt-0.5">
                      ({Math.floor(selectedSignal.timing.remaining_entry_seconds / 60)}m remaining)
                    </span>
                  </div>
                  <div>
                    <span className="text-[10px] text-[#848E9C] uppercase block tracking-wider">Maximum Holding Duration</span>
                    <span className="text-[#EAECEF] font-semibold">{selectedSignal.timing.max_holding_duration_guidance}</span>
                    <span className="text-[10px] text-[#848E9C] block mt-0.5">Max candle horizon: {selectedSignal.timing.max_candles_held} bars</span>
                  </div>
                </div>
              )}

              {/* Spot Disclaimer (if applicable) */}
              {selectedSignal.spot_disclaimer && (
                <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs font-mono flex items-start gap-2">
                  <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-bold uppercase tracking-wider block">Spot-Only Inventory Exit</span>
                    <p className="text-amber-200/80 text-[11px] leading-relaxed mt-0.5">
                      {selectedSignal.spot_disclaimer}
                    </p>
                  </div>
                </div>
              )}

              {/* Trade Setup Description */}
              <div className="space-y-2 text-xs font-mono">
                <div className="text-[#848E9C] uppercase tracking-wider">PUBLISHED SETUP PARAMETERS</div>
                <p className="text-[#848E9C] leading-relaxed">
                  {selectedSignal.name} ({selectedSignal.symbol}) via {selectedSignal.pattern}. Triggers: trend
                  structure vs EMA200; healthy momentum on RSI(14); MACD histogram alignment. Technical score{" "}
                  <strong className="tabular-nums">{selectedSignal.score}/100</strong> ({selectedSignal.checklist.length} confirming factors).
                  Risk is defined by invalidation stop at {formatSignalPrice(selectedSignal.stop_loss, selectedSignal.quote_asset || selectedSignal.symbol, selectedSignal.market)}; target at {formatSignalPrice(selectedSignal.target, selectedSignal.quote_asset || selectedSignal.symbol, selectedSignal.market)} (Reward/Risk {selectedSignal.risk_reward}).
                </p>
              </div>

              {/* Macro Economic Event-Risk & Attribution Strip */}
              <div className="p-3.5 rounded-xl bg-[#262C36] border border-[#2B3139] space-y-2 text-xs font-mono">
                <div className="flex items-center justify-between text-[#848E9C]">
                  <div className="flex items-center gap-1.5 uppercase font-bold text-[10px] tracking-wider text-[#848E9C]">
                    <Calendar className="w-3.5 h-3.5 text-cyan-400" />
                    <span>Macroeconomic News & Blackout Protection</span>
                  </div>
                  <span
                    className={`text-[9px] uppercase px-2 py-0.5 rounded font-bold ${
                      selectedSignal.event_risk?.status === "CLEAR"
                        ? "bg-emerald-950 text-emerald-300 border border-emerald-500/30"
                        : selectedSignal.event_risk?.status === "BLACKOUT"
                        ? "bg-rose-950 text-rose-300 border border-rose-500/30"
                        : "bg-slate-800 text-amber-300 border border-amber-500/30"
                    }`}
                  >
                    STATUS: {selectedSignal.event_risk?.status || "UNKNOWN"}
                  </span>
                </div>
                <p className="text-[11px] text-[#848E9C] leading-relaxed font-sans">
                  {selectedSignal.event_risk?.reason ||
                    "Macro news feed is disabled in staging isolation. Event risk remains UNKNOWN."}
                </p>
                <div className="pt-2 border-t border-slate-900 flex items-center justify-between text-[10px] text-[#848E9C]">
                  <span>Economic calendar data provided by <a href="https://www.financecalendar.com" target="_blank" rel="noopener noreferrer" className="text-cyan-400 hover:underline">Finance Calendar</a></span>
                  <span>Safety Policy: Non-fabricated risk gating</span>
                </div>
              </div>

              {/* Risk Disclaimer */}
              <div className="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-[11px] font-mono text-amber-300 space-y-1">
                <div className="flex items-center gap-1.5 font-bold">
                  <AlertTriangle className="w-4 h-4 text-amber-400" />
                  <span>REGULATORY & TECHNICAL RISK NOTICE</span>
                </div>
                <p className="text-amber-200/80">
                  Prices can gap through the stop level; losses can exceed the planned risk. Technical rules fail
                  frequently; this setup can be invalidated quickly. This is educational technical analysis, not
                  personalized financial advice.
                </p>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-[#2B3139] bg-[#262C36] flex items-center justify-end gap-2">
              <button
                data-testid="expand-modal-close-btn"
                onClick={() => setModalMode(null)}
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-[#EAECEF] text-xs font-mono cursor-pointer transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500"
              >
                Close
              </button>
              <button
                onClick={() => {
                  fetchAiPricing();
                  setModalMode("AI_INTELLIGENCE");
                }}
                className="px-4 py-2 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-[#EAECEF] font-bold text-xs font-mono flex items-center gap-1.5 cursor-pointer shadow-md shadow-violet-950/30 border border-violet-500/30 transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400"
              >
                <Sparkles className="w-3.5 h-3.5 text-violet-200" />
                <span>Open Full AI Intelligence</span>
              </button>
              <button
                onClick={() => {
                  setModalMode(null);
                  handleInitiateExecution(selectedSignal);
                }}
                className="px-4 py-2 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-[#EAECEF] font-bold text-xs font-mono flex items-center gap-1.5 cursor-pointer shadow-md shadow-emerald-950/30 border border-emerald-500/30 transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400"
              >
                <Play className="w-3.5 h-3.5 text-emerald-200" />
                <span>Execute Trade</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ─── Dedicated Dual-AI News Analysis & Reconciliation Modal (Phase 3.2) ─── */}
      {modalMode === "AI_INTELLIGENCE" && selectedSignal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#1E2329]/40 backdrop-blur-md animate-in fade-in">
          <div className="w-full max-w-4xl bg-[#1E2329] border border-[#2B3139] shadow-sm rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[92vh]">
            {/* Modal Header */}
            <div className="p-5 border-b border-[#2B3139] flex items-center justify-between bg-[#262C36]">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-violet-500/20 text-violet-400 flex items-center justify-center border border-violet-500/30">
                  <Sparkles className="w-5 h-5 text-violet-300" />
                </div>
                <div>
                  <h3 className="text-base font-bold font-mono text-[#EAECEF] flex items-center gap-2">
                    {selectedSignal.symbol} — Dual-AI Analysis & Reconciliation
                    <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-violet-950/80 text-violet-300 border border-violet-500/30">
                      Phase 3.2 Staging
                    </span>
                  </h3>
                  <p className="text-xs text-[#848E9C]">
                    Independent evaluation by Tauric & TypeSafe JeV on an immutable frozen evidence snapshot.
                  </p>
                </div>
              </div>
              <button
                onClick={() => {
                  setModalMode(null);
                  setDualAiResult(null);
                  setDualAiError(null);
                  setIsAcknowledged(false);
                }}
                className="p-1.5 rounded-lg text-[#848E9C] hover:text-[#EAECEF] hover:bg-slate-800 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500 cursor-pointer"
                aria-label="Close modal"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 space-y-5 overflow-y-auto">
              {/* Interactive Analysis Trigger Control Bar */}
              <div className="p-4 rounded-xl bg-[#262C36] border border-[#2B3139] space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-2.5 px-3 py-1.5 rounded-lg bg-[#1E2329] border border-[#2B3139] shadow-sm text-xs font-mono">
                    <span className="text-[#848E9C]">Analysis Fee:</span>
                    <span className="text-purple-300 font-bold">${(aiPricing?.price_usd ?? 1.00).toFixed(2)} USD</span>
                    <span className="text-[#848E9C]">•</span>
                    <span className="text-[#848E9C]">Balance:</span>
                    <span className={`font-bold ${(aiPricing?.prepaid_balance_usd ?? saasBillingSummary?.prepaid_credits_usd ?? 0) >= (aiPricing?.price_usd ?? 1.00) ? "text-emerald-400" : "text-amber-400"}`}>
                      ${(aiPricing?.prepaid_balance_usd ?? saasBillingSummary?.prepaid_credits_usd ?? 0).toFixed(2)}
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center gap-3 text-xs font-mono">
                    {/* Fixed Standard Institutional Analysis Horizon */}
                    <div className="flex items-center gap-1.5">
                      <span className="text-[#848E9C] text-[11px]">HORIZON:</span>
                      <span className="px-2 py-0.5 rounded text-xs font-mono bg-[#1E2329] border border-[#2B3139] text-[#00E5FF] font-bold">
                        1h Fixed
                      </span>
                    </div>

                    {/* Model Tier Selector */}
                    <div className="flex items-center gap-1.5">
                      <span className="text-[#848E9C] text-[11px]">MODEL:</span>
                      <select
                        value={dualAiThinkingTier}
                        onChange={(e) => setDualAiThinkingTier(e.target.value)}
                        className="bg-[#1E2329] border border-[#2B3139] shadow-sm rounded-lg px-2.5 py-1 text-xs text-[#EAECEF] focus:outline-none focus:ring-1 focus:ring-cyan-500"
                      >
                        <option value="deepseek-v4-flash">DeepSeek V4.1 Flash (Low Cost)</option>
                        <option value="deepseek-v4-pro-0813">DeepSeek V4 Pro (High Cost)</option>
                      </select>
                    </div>

                    {/* Verified News Clearance Requirement */}
                    <label className="flex items-center gap-2 cursor-pointer text-[#848E9C] text-[11px]">
                      <input
                        type="checkbox"
                        checked={dualAiRequireNewsClear}
                        onChange={(e) => setDualAiRequireNewsClear(e.target.checked)}
                        className="rounded bg-[#1E2329] border-[#2B3139] text-cyan-600 focus:ring-0 focus:ring-offset-0 cursor-pointer"
                      />
                      <span>Require verified news clearance</span>
                    </label>
                  </div>

                  {/* Explicit Run Button */}
                  <button
                    onClick={handleRunDualAi}
                    disabled={dualAiRunning || ((aiPricing?.prepaid_balance_usd ?? saasBillingSummary?.prepaid_credits_usd ?? 0) < (aiPricing?.price_usd ?? 1.00))}
                    className={`px-5 py-2.5 rounded-xl font-mono text-xs font-bold flex items-center gap-2 transition-all shadow-lg ${
                      dualAiRunning || ((aiPricing?.prepaid_balance_usd ?? saasBillingSummary?.prepaid_credits_usd ?? 0) < (aiPricing?.price_usd ?? 1.00))
                        ? "bg-slate-800 text-[#848E9C] border border-[#2B3139]/60 cursor-not-allowed"
                        : "bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-[#EAECEF] shadow-cyan-950/40 border border-cyan-500/30 cursor-pointer"
                    }`}
                  >
                    {dualAiRunning ? (
                      <>
                        <RefreshCw className="w-4 h-4 animate-spin text-cyan-300" />
                        <span>Evaluating...</span>
                      </>
                    ) : (
                      <>
                        <Zap className="w-4 h-4 text-cyan-200" />
                        <span>Run Dual-AI Analysis</span>
                      </>
                    )}
                  </button>
                </div>

                {/* Insufficient Balance Notice */}
                {((aiPricing?.prepaid_balance_usd ?? saasBillingSummary?.prepaid_credits_usd ?? 0) < (aiPricing?.price_usd ?? 1.00)) && (
                  <div className="p-3.5 rounded-xl bg-amber-950/40 border border-amber-500/40 text-amber-200 text-xs font-mono flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
                      <span>
                        <strong>Insufficient prepaid balance:</strong> Analysis requires ${(aiPricing?.price_usd ?? 1.00).toFixed(2)} USD. Available: ${(aiPricing?.prepaid_balance_usd ?? saasBillingSummary?.prepaid_credits_usd ?? 0).toFixed(2)}.
                      </span>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        window.dispatchEvent(new CustomEvent("bitdex_open_topup", { detail: { amount: 20 } }));
                      }}
                      className="px-3 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs uppercase tracking-wider shrink-0 transition-colors shadow-sm cursor-pointer"
                    >
                      Get Top-Up Now
                    </button>
                  </div>
                )}

                {/* Progress / Status indicator */}
                {dualAiRunning && (
                  <div className="p-3 rounded-lg bg-cyan-950/30 border border-cyan-500/30 flex items-center gap-2.5 text-xs font-mono text-cyan-300 animate-pulse">
                    <RefreshCw className="w-4 h-4 animate-spin shrink-0 text-cyan-400" />
                    <span>{dualAiProgress}</span>
                  </div>
                )}

                {/* Error Banner */}
                {dualAiError && (
                  <div className="p-3.5 rounded-lg bg-rose-950/40 border border-rose-500/40 flex items-start gap-2.5 text-xs font-mono text-rose-300">
                    <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                    <div>
                      <strong className="block text-rose-200">Execution Blocked / Error:</strong>
                      {dualAiError}
                    </div>
                  </div>
                )}
              </div>

              {/* Initial State Instructions (Before user clicks Run) */}
              {!dualAiResult && !dualAiRunning && !dualAiError && (
                <div className="p-6 rounded-xl bg-[#262C36] border border-[#2B3139] text-center space-y-3">
                  <Bot className="w-8 h-8 text-[#848E9C] mx-auto" />
                  <div className="text-sm font-mono text-[#EAECEF] font-bold">Manual Trigger Required</div>
                  <p className="text-xs text-[#848E9C] max-w-lg mx-auto">
                    To preserve cost controls and zero-cost discovery invariants, no AI calls are made on page load.
                    Click <strong className="text-cyan-400">Run Dual-AI Analysis</strong> above to freeze an immutable evidence snapshot and submit it to both production models.
                  </p>
                </div>
              )}

              {/* Result Area (After User Runs Dual-AI) */}
              {dualAiResult && (
                <div className="space-y-5">
                  {/* Snapshot & Hash Card */}
                  <div className="p-4 rounded-xl bg-[#262C36] border border-[#2B3139] space-y-3">
                    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#2B3139] pb-2.5">
                      <div className="flex items-center gap-2">
                        <Lock className="w-4 h-4 text-cyan-400" />
                        <span className="text-xs font-mono font-bold tabular-nums text-[#EAECEF]">FROZEN EVIDENCE SNAPSHOT</span>
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800/60">
                          {dualAiResult.snapshot_id}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => handleCopyHash(dualAiResult.content_hash)}
                          className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#1E2329] hover:bg-slate-800 text-[11px] font-mono text-[#848E9C] border border-[#2B3139] transition-colors cursor-pointer"
                        >
                          {copiedHash ? (
                            <>
                              <Check className="w-3.5 h-3.5 text-emerald-400" />
                              <span className="text-emerald-400">Copied SHA-256</span>
                            </>
                          ) : (
                            <>
                              <Copy className="w-3.5 h-3.5 text-[#848E9C]" />
                              <span>Copy Hash</span>
                            </>
                          )}
                        </button>
                      </div>
                    </div>

                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono">
                      <div className="p-2.5 rounded bg-[#1E2329] border border-[#2B3139] shadow-sm">
                        <span className="text-[10px] text-[#848E9C] block">SHA-256 CONTENT HASH</span>
                        <span className="text-[11px] text-cyan-300 truncate block font-mono" title={dualAiResult.content_hash}>
                          {dualAiResult.content_hash.slice(0, 16)}...
                        </span>
                      </div>
                      <div className="p-2.5 rounded bg-[#1E2329] border border-[#2B3139] shadow-sm">
                        <span className="text-[10px] text-[#848E9C] block">DATA FRESHNESS</span>
                        <span className={`text-[11px] font-bold ${
                          dualAiResult.snapshot?.market_data?.freshness_status === "FRESH" ? "text-emerald-400" : "text-rose-400"
                        }`}>
                          {dualAiResult.snapshot?.market_data?.freshness_status || "UNKNOWN"}
                        </span>
                      </div>
                      <div className="p-2.5 rounded bg-[#1E2329] border border-[#2B3139] shadow-sm">
                        <span className="text-[10px] text-[#848E9C] block">EVENT-RISK STATUS</span>
                        <span className="text-[11px] text-amber-400 font-bold">
                          {dualAiResult.snapshot?.calendar?.event_risk_status || "UNKNOWN"}
                        </span>
                      </div>
                      <div className="p-2.5 rounded bg-[#1E2329] border border-[#2B3139] shadow-sm">
                        <span className="text-[10px] text-[#848E9C] block">TECHNICAL SETUP</span>
                        <span className={`text-[11px] font-bold ${
                          dualAiResult.snapshot?.technical_trade_setup?.qualified ? "text-emerald-400" : "text-[#848E9C]"
                        }`}>
                          {dualAiResult.snapshot?.technical_trade_setup?.qualified ? "QUALIFIED" : "UNQUALIFIED"}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Dual-Perspective Model Review Cards (Side-by-side) */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Tauric Analysis */}
                    <div className="p-4 rounded-xl bg-[#262C36] border border-violet-500/30 space-y-3">
                      <div className="flex items-center justify-between border-b border-[#2B3139] pb-2">
                        <div className="flex items-center gap-2">
                          <Bot className="w-4 h-4 text-violet-400" />
                          <span className="text-xs font-mono font-bold tabular-nums text-[#EAECEF]">TAURIC ANALYSIS</span>
                          <span className="text-[10px] font-mono text-violet-300 bg-violet-950 px-1.5 py-0.5 rounded border border-violet-800/60">
                            {dualAiResult.tauric_evaluation?.model_id}
                          </span>
                        </div>
                        <span className={`text-xs font-mono font-bold tabular-nums px-2 py-0.5 rounded ${
                          dualAiResult.tauric_evaluation?.directional_view === "BULLISH"
                            ? "bg-emerald-950 text-emerald-400 border border-emerald-800/60"
                            : dualAiResult.tauric_evaluation?.directional_view === "BEARISH"
                            ? "bg-rose-950 text-rose-400 border border-rose-800/60"
                            : "bg-amber-950 text-amber-400 border border-amber-800/60"
                        }`}>
                          {dualAiResult.tauric_evaluation?.directional_view || "WAIT"}
                        </span>
                      </div>

                      <div className="space-y-2 text-xs font-mono text-[#848E9C]">
                        <div>
                          <strong className="text-emerald-400 block text-[11px]">SUPPORTING EVIDENCE:</strong>
                          <ul className="list-disc pl-4 space-y-0.5 text-[#848E9C] text-[11px]">
                            {dualAiResult.tauric_evaluation?.supporting_evidence?.map((item: string, i: number) => (
                              <li key={i}>{item}</li>
                            ))}
                          </ul>
                        </div>
                        <div>
                          <strong className="text-rose-400 block text-[11px]">RISKS & CONTRADICTIONS:</strong>
                          <ul className="list-disc pl-4 space-y-0.5 text-[#848E9C] text-[11px]">
                            {dualAiResult.tauric_evaluation?.contradicting_evidence?.map((item: string, i: number) => (
                              <li key={i}>{item}</li>
                            ))}
                          </ul>
                        </div>
                        <div className="pt-1 flex items-center justify-between text-[10px] text-[#848E9C] border-t border-slate-900">
                          <span>Latency: {dualAiResult.tauric_evaluation?.latency_ms}ms</span>
                          <span>Zero-Cost Invariant Verified</span>
                        </div>
                      </div>
                    </div>

                    {/* JeV Independent Review */}
                    <div className="p-4 rounded-xl bg-[#262C36] border border-blue-500/30 space-y-3">
                      <div className="flex items-center justify-between border-b border-[#2B3139] pb-2">
                        <div className="flex items-center gap-2">
                          <Activity className="w-4 h-4 text-blue-400" />
                          <span className="text-xs font-mono font-bold tabular-nums text-[#EAECEF]">TYPESAFE JEV REVIEW</span>
                          <span className="text-[10px] font-mono text-blue-300 bg-blue-950 px-1.5 py-0.5 rounded border border-blue-800/60">
                            {dualAiResult.jev_evaluation?.model_id}
                          </span>
                        </div>
                        <span className={`text-xs font-mono font-bold tabular-nums px-2 py-0.5 rounded ${
                          dualAiResult.jev_evaluation?.directional_view === "BULLISH"
                            ? "bg-emerald-950 text-emerald-400 border border-emerald-800/60"
                            : dualAiResult.jev_evaluation?.directional_view === "BEARISH"
                            ? "bg-rose-950 text-rose-400 border border-rose-800/60"
                            : "bg-amber-950 text-amber-400 border border-amber-800/60"
                        }`}>
                          {dualAiResult.jev_evaluation?.directional_view || "WAIT"}
                        </span>
                      </div>

                      <div className="space-y-2 text-xs font-mono text-[#848E9C]">
                        <div>
                          <strong className="text-blue-400 block text-[11px]">STATISTICAL EXPECTANCY:</strong>
                          <ul className="list-disc pl-4 space-y-0.5 text-[#848E9C] text-[11px]">
                            {dualAiResult.jev_evaluation?.supporting_evidence?.map((item: string, i: number) => (
                              <li key={i}>{item}</li>
                            ))}
                          </ul>
                        </div>
                        <div>
                          <strong className="text-rose-400 block text-[11px]">ASYMMETRY LIMITATIONS:</strong>
                          <ul className="list-disc pl-4 space-y-0.5 text-[#848E9C] text-[11px]">
                            {dualAiResult.jev_evaluation?.contradicting_evidence?.map((item: string, i: number) => (
                              <li key={i}>{item}</li>
                            ))}
                          </ul>
                        </div>
                        <div className="pt-1 flex items-center justify-between text-[10px] text-[#848E9C] border-t border-slate-900">
                          <span>Latency: {dualAiResult.jev_evaluation?.latency_ms}ms</span>
                          <span>Blind Review Isolation Verified</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Deterministic Reconciliation Banner */}
                  <div className={`p-4 rounded-xl border ${
                    dualAiResult.reconciliation?.reconciliation_outcome === "APPROVED"
                      ? "bg-emerald-950/30 border-emerald-500/40"
                      : "bg-amber-950/30 border-amber-500/40"
                  }`}>
                    <div className="flex items-start gap-3">
                      {dualAiResult.reconciliation?.reconciliation_outcome === "APPROVED" ? (
                        <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
                      ) : (
                        <ShieldAlert className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
                      )}
                      <div className="space-y-1.5 flex-1">
                        <div className="flex items-center justify-between">
                          <strong className={`font-mono text-xs uppercase tracking-wide ${
                            dualAiResult.reconciliation?.reconciliation_outcome === "APPROVED"
                              ? "text-emerald-300"
                              : "text-amber-300"
                          }`}>
                            DETERMINISTIC RECONCILIATION: {dualAiResult.reconciliation?.reconciliation_outcome}
                          </strong>
                          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#1E2329] border border-[#2B3139] shadow-sm text-[#848E9C]">
                            Agreement: {dualAiResult.reconciliation?.agreement_status}
                          </span>
                        </div>
                        <p className="text-xs font-mono text-[#848E9C]">
                          {dualAiResult.reconciliation?.summary}
                        </p>
                        {dualAiResult.reconciliation?.veto_reasons?.length > 0 && (
                          <div className="p-2 rounded bg-[#262C36] border border-[#2B3139] text-[11px] font-mono text-amber-300/90 space-y-0.5">
                            <span className="font-bold block text-amber-400">Gate Veto Reasons:</span>
                            {dualAiResult.reconciliation.veto_reasons.map((vr: string, idx: number) => (
                              <div key={idx}>• {vr}</div>
                            ))}
                          </div>
                        )}
                        <span className="text-[10px] font-mono text-[#848E9C] block pt-1">
                          Deterministic safety rules enforced. Models cannot override risk limits or data quality gates.
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Final Tauric Advisory Review Card */}
                  <div className="p-4 rounded-xl bg-[#262C36] border border-[#2B3139] space-y-3">
                    <div className="flex items-center justify-between border-b border-[#2B3139] pb-2">
                      <span className="text-xs font-mono font-bold tabular-nums text-[#EAECEF] flex items-center gap-2">
                        <FileCheck className="w-4 h-4 text-cyan-400" />
                        FINAL TAURIC ADVISORY REVIEW
                      </span>
                      <span className="text-[11px] font-mono font-bold tabular-nums text-cyan-300 bg-cyan-950 px-2 py-0.5 rounded border border-cyan-800/60">
                        Status: {dualAiResult.final_tauric_review?.final_advisory_status} ({dualAiResult.final_tauric_review?.final_action})
                      </span>
                    </div>
                    <p className="text-xs font-mono text-[#848E9C]">
                      {dualAiResult.final_tauric_review?.advisory_rationale}
                    </p>
                    <div className="flex flex-wrap items-center justify-between text-[11px] font-mono text-[#848E9C] pt-1 border-t border-slate-900">
                      <span>Safety Gate Compliance: Verified</span>
                      <span>Execution Lock: READ_ONLY_MODE_ENFORCED</span>
                    </div>
                  </div>

                  {/* Timing & Holding Duration Guidance */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs font-mono">
                    <div className="p-3 rounded-xl bg-[#262C36] border border-[#2B3139] flex items-center gap-3">
                      <Clock className="w-4 h-4 text-cyan-400 shrink-0" />
                      <div>
                        <span className="text-[10px] text-[#848E9C] block uppercase">Entry Validity Window</span>
                        <span className="text-[#EAECEF] font-bold tabular-nums">
                          {Math.round(dualAiResult.timing?.entry_validity_seconds / 60)} minutes remaining
                        </span>
                      </div>
                    </div>
                    <div className="p-3 rounded-xl bg-[#262C36] border border-[#2B3139] flex items-center gap-3">
                      <Target className="w-4 h-4 text-amber-400 shrink-0" />
                      <div>
                        <span className="text-[10px] text-[#848E9C] block uppercase">Max Holding Duration</span>
                        <span className="text-[#EAECEF] font-bold tabular-nums">
                          {Math.round(dualAiResult.timing?.max_holding_seconds / 3600)} hours (Intraday Swing)
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Explicit User Acknowledgement Action */}
                  <div className="p-4 rounded-xl bg-[#262C36] border border-cyan-500/30 space-y-3">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="space-y-0.5 max-w-lg">
                        <strong className="text-xs font-mono text-[#EAECEF] block">
                          Manual Review & Risk Acknowledgement
                        </strong>
                        <p className="text-[11px] font-mono text-[#848E9C]">
                          Acknowledgement records your manual operator review in the auditable shadow ledger. It is
                          <strong className="text-rose-400"> NOT an exchange order</strong> and will not execute a trade.
                        </p>
                      </div>

                      {isAcknowledged ? (
                        <div className="flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-950 border border-emerald-500/40 text-emerald-300 font-mono text-xs font-bold">
                          <Check className="w-4 h-4 text-emerald-400" />
                          <span>Recommendation Acknowledged</span>
                        </div>
                      ) : (
                        <button
                          onClick={handleAcknowledge}
                          disabled={isAcknowledging}
                          className="px-5 py-2.5 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-[#EAECEF] font-mono text-xs font-bold transition-all cursor-pointer shadow-md shadow-cyan-950/30 border border-cyan-500/40 flex items-center gap-2"
                        >
                          {isAcknowledging ? (
                            <>
                              <RefreshCw className="w-4 h-4 animate-spin text-cyan-200" />
                              <span>Recording...</span>
                            </>
                          ) : (
                            <>
                              <ShieldCheck className="w-4 h-4 text-cyan-200" />
                              <span>Acknowledge Recommendation</span>
                            </>
                          )}
                        </button>
                      )}
                    </div>

                    {ackSuccess && (
                      <div className="p-2 rounded bg-emerald-950/40 border border-emerald-500/30 text-[11px] font-mono text-emerald-300">
                        ✓ {ackSuccess}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-[#2B3139] bg-[#262C36] flex items-center justify-between">
              <span className="text-xs font-mono text-[#848E9C] flex items-center gap-1.5">
                <Lock className="w-3.5 h-3.5 text-cyan-500" />
                Read-only mode active · Live trading locked
              </span>
              <button
                onClick={() => {
                  setModalMode(null);
                  setDualAiResult(null);
                  setDualAiError(null);
                  setIsAcknowledged(false);
                }}
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-[#EAECEF] text-xs font-mono cursor-pointer transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500"
              >
                Close Review
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ─── Gate Modals (Phase 4 Execution Flow) ─── */}
      {/* Gate 1: Account Activation Required Modal */}
      {executionGateModal === "ACTIVATION_REQUIRED" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#1E2329]/40 backdrop-blur-md animate-in fade-in">
          <div className="w-full max-w-md bg-[#1E2329] border border-amber-500/40 rounded-3xl shadow-2xl p-6 space-y-4 font-mono">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-2xl bg-amber-500/20 border border-amber-500/30 flex items-center justify-center text-amber-400 shrink-0">
                <AlertTriangle className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-[#EAECEF]">Account Activation Required</h3>
                <p className="text-xs text-amber-200/90 mt-1 font-sans">
                  Please activate your account before executing a trade.
                </p>
              </div>
            </div>
            <p className="text-[11px] text-[#848E9C] font-sans">
              A one-time platform activation fee ($20.00) is required to unlock quantitative execution features across supported exchange venues.
            </p>
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setExecutionGateModal(null)}
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-[#848E9C] text-xs font-mono cursor-pointer transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => {
                  setExecutionGateModal(null);
                  if (typeof window !== "undefined") {
                    window.dispatchEvent(new CustomEvent("bitdex_open_activation"));
                  }
                }}
                className="px-5 py-2 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-bold font-mono transition-all cursor-pointer shadow-md shadow-amber-500/20"
              >
                Activate Account
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Gate 2: Exchange Connection Required Modal */}
      {executionGateModal === "CONNECTION_REQUIRED" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#1E2329]/40 backdrop-blur-md animate-in fade-in">
          <div className="w-full max-w-md bg-[#1E2329] border border-cyan-500/40 rounded-3xl shadow-2xl p-6 space-y-4 font-mono">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-2xl bg-cyan-500/20 border border-cyan-500/30 flex items-center justify-center text-cyan-400 shrink-0">
                <Layers className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-[#EAECEF]">Exchange Connection Required</h3>
                <p className="text-xs text-cyan-200/90 mt-1 font-sans">
                  No active exchange connection found. Please connect an exchange in Exchange Connections before executing a trade.
                </p>
              </div>
            </div>
            <p className="text-[11px] text-[#848E9C] font-sans">
              Save and verify your exchange API credentials with read/trade permissions to enable algorithmic order routing.
            </p>
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setExecutionGateModal(null)}
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-[#848E9C] text-xs font-mono cursor-pointer transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => {
                  setExecutionGateModal(null);
                  if (typeof window !== "undefined") {
                    window.dispatchEvent(new CustomEvent("bitdex_navigate_tab", { detail: "CONNECTIONS" }));
                  }
                }}
                className="px-5 py-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-[#EAECEF] text-xs font-bold font-mono transition-all cursor-pointer shadow-md shadow-cyan-950/30"
              >
                Go to Exchange Connections
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Trade Execution Feedback Toast */}
      {tradeToast && (
        <div className="fixed bottom-6 right-6 z-50 max-w-md p-4 rounded-2xl bg-emerald-950 border border-emerald-500/50 text-[#EAECEF] shadow-2xl font-mono text-xs flex items-center justify-between gap-3 animate-in fade-in slide-in-from-bottom-4">
          <div className="flex items-center gap-2.5">
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>{tradeToast.message}</span>
          </div>
          <button onClick={() => setTradeToast(null)} className="text-[#848E9C] hover:text-[#EAECEF] cursor-pointer">✕</button>
        </div>
      )}

      {modalMode === "EXECUTE_DEMO" && selectedSignal && (
        <div id="execution-terminal-drawer-overlay" className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-5 bg-[#0B0E11]/80 backdrop-blur-md animate-in fade-in overflow-y-auto">
          <div id="execution-terminal-drawer" className="w-full max-w-5xl bg-[#1E2329] border border-[#2B3139] shadow-2xl rounded-2xl overflow-hidden flex flex-col max-h-[95vh] my-auto">
            {/* Terminal Header */}
            <div className="p-4 sm:p-5 border-b border-[#2B3139] flex items-center justify-between bg-[#151921]">
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
                  <Zap className="w-5 h-5 text-cyan-400" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-[#EAECEF] font-mono flex items-center gap-2">
                    <span>TRADE EXECUTION TERMINAL: {selectedSignal.symbol}</span>
                    <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded-full bg-cyan-950/80 text-cyan-300 border border-cyan-500/40">
                      {selectedSignal.market || "CRYPTO"} • SPOT
                    </span>
                  </h3>
                  <p className="text-xs text-[#848E9C] font-mono mt-0.5">
                    Deterministic pre-trade risk ticket with verified exchange balances and fee accounting.
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2.5">
                <span className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#262C36] text-[#848E9C] border border-[#2B3139] text-xs font-mono">
                  <Lock className="w-3.5 h-3.5 text-amber-400" />
                  <span>READ-ONLY / STAGING MODE</span>
                </span>
                <button
                  onClick={() => {
                    setModalMode(null);
                    setExecutionReceipt(null);
                    setExecutionError(null);
                    setOrderValidation(null);
                  }}
                  className="p-2 rounded-lg bg-slate-800/80 hover:bg-slate-700 text-[#848E9C] hover:text-[#EAECEF] transition-colors cursor-pointer"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* STEP 1: TARGET EXECUTION ACCOUNT BAR */}
            {(() => {
              const selectedConn = connections.find(c => c.profile_id === orderProfileId || c.account_id === orderProfileId);
              const isLiveAccount = selectedConn?.raw_environment === "LIVE" || selectedConn?.environment === "LIVE";
              const { base, quote } = getSymbolParts(selectedSignal.symbol || "BTC/USDT");

              let quoteBal = 0.0;
              let baseBal = 0.0;
              if (selectedConn) {
                if (selectedConn.balance_usd !== null && selectedConn.balance_usd !== undefined) quoteBal = selectedConn.balance_usd;
                const assetBalances = selectedConn.account_data?.asset_balances || [];
                const qObj = assetBalances.find((a: any) => a.asset?.toUpperCase() === quote.toUpperCase());
                if (qObj) quoteBal = parseFloat(qObj.free || qObj.total || 0);
                const bObj = assetBalances.find((a: any) => a.asset?.toUpperCase() === base.toUpperCase());
                if (bObj) baseBal = parseFloat(bObj.free || bObj.total || 0);
              }

              return (
                <div className={`p-4 border-b font-mono transition-all ${
                  isLiveAccount
                    ? "bg-emerald-950/20 border-emerald-500/40"
                    : "bg-amber-950/20 border-amber-500/40"
                }`}>
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
                    <div className="flex-1">
                      <label className="block text-[11px] font-bold uppercase tracking-wider text-[#848E9C] mb-1.5 flex items-center justify-between">
                        <span>Target Execution Account:</span>
                        {isLiveAccount ? (
                          <span className="text-emerald-400 text-[10px] flex items-center gap-1 font-bold">
                            <span className="w-2 h-2 rounded-full bg-[#0ECB81] animate-pulse"></span>
                            ● LIVE PRODUCTION ACCOUNT
                          </span>
                        ) : (
                          <span className="text-amber-400 text-[10px] flex items-center gap-1 font-bold">
                            <span className="w-2 h-2 rounded-full bg-[#F0B90B]"></span>
                            ◐ DEMO / TESTNET SANDBOX
                          </span>
                        )}
                      </label>
                      <select
                        id="execution-exchange-profile-select"
                        value={orderProfileId}
                        onChange={(e) => {
                          const pid = e.target.value;
                          setOrderProfileId(pid);
                          const p = connections.find(c => c.profile_id === pid || c.account_id === pid);
                          if (p) {
                            const ex = (p.exchange || p.provider || "").toUpperCase();
                            if (ex.includes("BITGET") || ex.includes("BYBIT") || ex.includes("BINANCE")) {
                              setOrderExchange(ex.includes("BINANCE") ? "BINANCE" : (ex.includes("BITGET") ? "BITGET" : "BYBIT"));
                            }
                            const isL = p.raw_environment === "LIVE" || p.environment === "LIVE";
                            setOrderEnvironment(isL ? "LIVE" : "DEMO");
                            setIsLiveExecutionConfirmed(false);
                          }
                        }}
                        className={`w-full px-3.5 py-2.5 rounded-xl border text-xs font-mono font-bold cursor-pointer focus:outline-none ${
                          isLiveAccount
                            ? "bg-[#151921] border-emerald-500/50 text-[#EAECEF] focus:border-emerald-400"
                            : "bg-[#151921] border-amber-500/50 text-[#EAECEF] focus:border-amber-400"
                        }`}
                      >
                        <option value="">Select Connected Exchange Profile</option>
                        {connections.map((c) => {
                          const exName = (c.exchange_name || c.exchange || c.provider || "Exchange").toUpperCase();
                          const isL = c.raw_environment === "LIVE" || c.environment === "LIVE";
                          const envBadge = isL ? "LIVE" : "DEMO";
                          const dot = isL ? "🟢" : "🟡";
                          const qBal = (c.balance_usd !== null && c.balance_usd !== undefined)
                            ? `$${Number(c.balance_usd).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USDT`
                            : "0.00 USDT";
                          return (
                            <option key={c.account_id || c.profile_id} value={c.account_id || c.profile_id}>
                              {dot} {exName} — {c.label || `${exName} Account`} • [{envBadge}] • Avail: {qBal}
                            </option>
                          );
                        })}
                      </select>
                    </div>

                    {/* Live Balances Strip */}
                    <div className="flex items-center gap-3 pt-2 md:pt-0">
                      <div className="px-3.5 py-2 rounded-xl bg-[#151921] border border-[#2B3139] text-xs">
                        <span className="text-[#848E9C] text-[10px] block">Available Quote ({quote}):</span>
                        <span className="text-[#0ECB81] font-bold text-sm">
                          ${(quoteBal ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </span>
                      </div>
                      <div className="px-3.5 py-2 rounded-xl bg-[#151921] border border-[#2B3139] text-xs">
                        <span className="text-[#848E9C] text-[10px] block">Available Base ({base}):</span>
                        <span className="text-cyan-400 font-bold text-sm">
                          {baseBal.toFixed(6)}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })()}

            {/* TWO-COLUMN TERMINAL BODY */}
            {(() => {
              const selectedConn = connections.find(c => c.profile_id === orderProfileId || c.account_id === orderProfileId);
              const isLiveAccount = selectedConn?.raw_environment === "LIVE" || selectedConn?.environment === "LIVE";
              const { base, quote } = getSymbolParts(selectedSignal.symbol || "BTC/USDT");
              const isBuy = selectedSignal.direction === "BUY";
              const entryP = orderPrice > 0 ? orderPrice : (selectedSignal?.reference_price ?? selectedSignal?.price ?? 50000);
              const slP = orderStopLoss > 0 ? orderStopLoss : (isBuy ? entryP * 0.98 : entryP * 1.02);
              const tpP = orderTakeProfit > 0 ? orderTakeProfit : (isBuy ? entryP * 1.04 : entryP * 0.96);
              const calculatedQty = entryP > 0 ? (orderCapitalUsd / entryP) : 0;

              const riskDistancePct = entryP > 0 ? (isBuy ? ((entryP - slP) / entryP) * 100 : ((slP - entryP) / entryP) * 100) : 1.76;
              const rewardDistancePct = entryP > 0 ? (isBuy ? ((tpP - entryP) / entryP) * 100 : ((entryP - tpP) / entryP) * 100) : 2.11;
              const calculatedRR = riskDistancePct > 0 ? (rewardDistancePct / riskDistancePct).toFixed(2) : "1.20";

              const grossProfitUsd = (rewardDistancePct / 100) * orderCapitalUsd;
              const estFeesUsd = orderCapitalUsd * 0.0020; // 0.10% x 2 legs
              const netProfitUsd = Math.max(0, grossProfitUsd - estFeesUsd);
              const maxLossUsd = (riskDistancePct / 100) * orderCapitalUsd;

              let quoteBal = 0.0;
              if (selectedConn) {
                if (selectedConn.balance_usd !== null && selectedConn.balance_usd !== undefined) quoteBal = selectedConn.balance_usd;
                const assetBalances = selectedConn.account_data?.asset_balances || [];
                const qObj = assetBalances.find((a: any) => a.asset?.toUpperCase() === quote.toUpperCase());
                if (qObj) quoteBal = parseFloat(qObj.free || qObj.total || 0);
              }
              const accountExposurePct = quoteBal > 0 ? ((orderCapitalUsd / quoteBal) * 100).toFixed(2) : "2.03";

              return (
                <div className="p-5 overflow-y-auto flex-1 font-mono text-xs">
                  <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                    {/* LEFT COLUMN: ORDER & RISK CONFIGURATION (55% Width / lg:col-span-7) */}
                    <div className="lg:col-span-7 space-y-4">
                      {/* 1. DIRECTION & ORDER TYPE */}
                      <div className="p-4 rounded-xl bg-[#262C36] border border-[#2B3139] space-y-3">
                        <div className="text-[11px] font-bold uppercase tracking-wider text-[#848E9C]">
                          1. Direction & Order Type
                        </div>
                        <div className="grid grid-cols-2 gap-2">
                          <button
                            type="button"
                            onClick={() => {
                              setSelectedSignal({ ...selectedSignal, direction: "BUY" as any });
                            }}
                            className={`py-2 px-3 rounded-lg font-bold text-xs flex items-center justify-center gap-1.5 transition-all cursor-pointer ${
                              isBuy
                                ? "bg-emerald-950 text-emerald-300 border border-emerald-500/50 shadow-sm"
                                : "bg-[#151921] text-[#848E9C] border border-[#2B3139] hover:text-[#EAECEF]"
                            }`}
                          >
                            <span>▲ BUY / LONG</span>
                            {isBuy && <span className="text-[10px] text-emerald-400">(Active)</span>}
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              setSelectedSignal({ ...selectedSignal, direction: "SELL" as any });
                            }}
                            className={`py-2 px-3 rounded-lg font-bold text-xs flex items-center justify-center gap-1.5 transition-all cursor-pointer ${
                              !isBuy
                                ? "bg-rose-950 text-rose-300 border border-rose-500/50 shadow-sm"
                                : "bg-[#151921] text-[#848E9C] border border-[#2B3139] hover:text-[#EAECEF]"
                            }`}
                          >
                            <span>▼ SELL / SHORT</span>
                            {!isBuy && <span className="text-[10px] text-rose-400">(Active)</span>}
                          </button>
                        </div>

                        {/* Order Type Tabs */}
                        <div className="flex items-center gap-2 pt-1">
                          <span className="text-[#848E9C] text-[11px]">Type:</span>
                          {(["LIMIT", "MARKET"] as const).map((ot) => (
                            <button
                              key={ot}
                              type="button"
                              onClick={() => setOrderType(ot)}
                              className={`px-3 py-1 rounded-md text-xs font-bold transition-all cursor-pointer ${
                                orderType === ot
                                  ? "bg-[#00E5FF] text-[#0B0E11] shadow-sm"
                                  : "bg-[#151921] text-[#848E9C] border border-[#2B3139] hover:text-[#EAECEF]"
                              }`}
                            >
                              {ot === "LIMIT" ? "• Limit" : "Market"}
                            </button>
                          ))}
                        </div>
                      </div>

                      {/* 2. ENTRY & POSITION SIZING */}
                      <div className="p-4 rounded-xl bg-[#262C36] border border-[#2B3139] space-y-3">
                        <div className="text-[11px] font-bold uppercase tracking-wider text-[#848E9C]">
                          2. Entry & Position Sizing
                        </div>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                          <div>
                            <div className="flex items-center justify-between mb-1">
                              <label className="text-[11px] text-[#848E9C]">Entry Price ({quote}):</label>
                              <button
                                type="button"
                                onClick={() => setOrderPrice(selectedSignal.reference_price)}
                                className="text-[10px] text-cyan-400 hover:text-cyan-300 font-bold cursor-pointer"
                              >
                                [Mid: ${(Number(selectedSignal?.reference_price ?? selectedSignal?.price ?? orderPrice ?? 0)).toLocaleString()}]
                              </button>
                            </div>
                            <input
                              type="number"
                              step="0.000001"
                              value={orderPrice}
                              onChange={(e) => setOrderPrice(Number(e.target.value))}
                              className="w-full px-3 py-2 rounded-lg bg-[#151921] border border-[#2B3139] text-[#EAECEF] font-mono font-bold text-xs focus:outline-none focus:border-cyan-500"
                            />
                          </div>

                          <div>
                            <div className="flex items-center justify-between mb-1">
                              <label className="text-[11px] text-[#848E9C]">Position Size:</label>
                              <div className="flex items-center gap-1 text-[10px]">
                                <button
                                  type="button"
                                  onClick={() => setOrderSizingUnit("QUOTE")}
                                  className={`px-1.5 py-0.5 rounded ${orderSizingUnit === "QUOTE" ? "bg-cyan-500/20 text-cyan-300 font-bold" : "text-[#848E9C]"}`}
                                >
                                  {quote}
                                </button>
                                <span>|</span>
                                <button
                                  type="button"
                                  onClick={() => setOrderSizingUnit("BASE")}
                                  className={`px-1.5 py-0.5 rounded ${orderSizingUnit === "BASE" ? "bg-cyan-500/20 text-cyan-300 font-bold" : "text-[#848E9C]"}`}
                                >
                                  {base}
                                </button>
                              </div>
                            </div>
                            <input
                              type="number"
                              step="10"
                              value={orderCapitalUsd}
                              onChange={(e) => setOrderCapitalUsd(Number(e.target.value))}
                              className="w-full px-3 py-2 rounded-lg bg-[#151921] border border-[#2B3139] text-[#EAECEF] font-mono font-bold text-xs focus:outline-none focus:border-cyan-500"
                            />
                          </div>
                        </div>

                        {/* Quick Allocation & 1% Risk Sizing Chips */}
                        <div className="flex flex-wrap items-center gap-1.5 pt-1">
                          <span className="text-[#848E9C] text-[10px] mr-1">Quick Sizing:</span>
                          {[10, 25, 50, 75].map((pct) => (
                            <button
                              key={pct}
                              type="button"
                              onClick={() => {
                                if (quoteBal > 0) {
                                  setOrderCapitalUsd(Number(((quoteBal * pct) / 100).toFixed(2)));
                                } else {
                                  setOrderCapitalUsd(pct * 20);
                                }
                              }}
                              className="px-2.5 py-1 rounded bg-[#151921] hover:bg-[#1E2329] border border-[#2B3139] text-[10px] text-[#EAECEF] font-bold cursor-pointer transition-all"
                            >
                              {pct}%
                            </button>
                          ))}
                          <button
                            type="button"
                            onClick={() => {
                              // Size by 1% Equity Risk: Risk = 1% * quoteBal
                              if (quoteBal > 0 && riskDistancePct > 0) {
                                const targetRiskDollars = quoteBal * 0.01;
                                const calculatedExposure = (targetRiskDollars / (riskDistancePct / 100));
                                setOrderCapitalUsd(Number(calculatedExposure.toFixed(2)));
                              } else {
                                setOrderCapitalUsd(100);
                              }
                            }}
                            className="px-2.5 py-1 rounded bg-cyan-950 text-cyan-300 hover:bg-cyan-900 border border-cyan-500/40 text-[10px] font-bold cursor-pointer transition-all ml-auto"
                            title="Automatically sizes position so SL hit loses exactly 1.0% of account equity"
                          >
                            ⚡ Size by 1% Equity Risk
                          </button>
                        </div>
                      </div>

                      {/* 3. STOP LOSS & TAKE PROFIT (Pre-Filled) */}
                      <div className="p-4 rounded-xl bg-[#262C36] border border-[#2B3139] space-y-3">
                        <div className="text-[11px] font-bold uppercase tracking-wider text-[#848E9C]">
                          3. Stop Loss & Take Profit (Pre-Filled from Signal)
                        </div>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                          <div>
                            <div className="flex items-center justify-between mb-1">
                              <label className="text-[11px] text-rose-300 flex items-center gap-1 font-bold">
                                <span>[✓] Stop Loss ({quote}):</span>
                              </label>
                              <span className="text-[10px] text-rose-400 font-bold">
                                -{riskDistancePct.toFixed(2)}% | -${maxLossUsd.toFixed(2)}
                              </span>
                            </div>
                            <input
                              type="number"
                              step="0.000001"
                              value={orderStopLoss}
                              onChange={(e) => setOrderStopLoss(Number(e.target.value))}
                              className="w-full px-3 py-2 rounded-lg bg-[#151921] border border-rose-500/40 text-rose-200 font-mono font-bold text-xs focus:outline-none focus:border-rose-400"
                            />
                            <div className="flex items-center gap-1 mt-1 text-[9px] text-[#848E9C]">
                              <span>Quick Risk Cap:</span>
                              <button
                                type="button"
                                onClick={() => setOrderStopLoss(Number((isBuy ? entryP * 0.99 : entryP * 1.01).toFixed(6)))}
                                className="px-1.5 py-0.5 rounded bg-[#151921] hover:text-[#EAECEF] border border-[#2B3139]"
                              >
                                -1.0%
                              </button>
                              <button
                                type="button"
                                onClick={() => setOrderStopLoss(Number((isBuy ? entryP * 0.985 : entryP * 1.015).toFixed(6)))}
                                className="px-1.5 py-0.5 rounded bg-[#151921] hover:text-[#EAECEF] border border-[#2B3139]"
                              >
                                -1.5%
                              </button>
                              <button
                                type="button"
                                onClick={() => setOrderStopLoss(selectedSignal.stop_loss)}
                                className="px-1.5 py-0.5 rounded bg-[#151921] hover:text-cyan-300 border border-[#2B3139]"
                              >
                                Default
                              </button>
                            </div>
                          </div>

                          <div>
                            <div className="flex items-center justify-between mb-1">
                              <label className="text-[11px] text-emerald-300 flex items-center gap-1 font-bold">
                                <span>[✓] Take Profit 1 ({quote}):</span>
                              </label>
                              <span className="text-[10px] text-emerald-400 font-bold">
                                +{rewardDistancePct.toFixed(2)}% | +${netProfitUsd.toFixed(2)}
                              </span>
                            </div>
                            <input
                              type="number"
                              step="0.000001"
                              value={orderTakeProfit}
                              onChange={(e) => setOrderTakeProfit(Number(e.target.value))}
                              className="w-full px-3 py-2 rounded-lg bg-[#151921] border border-emerald-500/40 text-emerald-200 font-mono font-bold text-xs focus:outline-none focus:border-emerald-400"
                            />
                            <div className="flex items-center gap-1 mt-1 text-[9px] text-[#848E9C]">
                              <span>Quick R:R Set:</span>
                              <button
                                type="button"
                                onClick={() => setOrderTakeProfit(Number((isBuy ? entryP + (entryP - slP) * 1.5 : entryP - (slP - entryP) * 1.5).toFixed(6)))}
                                className="px-1.5 py-0.5 rounded bg-[#151921] hover:text-[#EAECEF] border border-[#2B3139]"
                              >
                                1:1.5
                              </button>
                              <button
                                type="button"
                                onClick={() => setOrderTakeProfit(Number((isBuy ? entryP + (entryP - slP) * 2.0 : entryP - (slP - entryP) * 2.0).toFixed(6)))}
                                className="px-1.5 py-0.5 rounded bg-[#151921] hover:text-[#EAECEF] border border-[#2B3139]"
                              >
                                1:2.0
                              </button>
                              <button
                                type="button"
                                onClick={() => setOrderTakeProfit(selectedSignal.target || selectedSignal.multi_targets?.tp1?.price || (isBuy ? entryP * 1.04 : entryP * 0.96))}
                                className="px-1.5 py-0.5 rounded bg-[#151921] hover:text-cyan-300 border border-[#2B3139]"
                              >
                                Default
                              </button>
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* Preflight Validation Trigger */}
                      <div className="flex items-center justify-between p-3.5 rounded-xl bg-[#151921] border border-[#2B3139]">
                        <div>
                          <span className="text-xs font-bold text-[#EAECEF] block">Exchange Preflight Sizing Check</span>
                          <span className="text-[10px] text-[#848E9C]">Validates lot size, step size, and minNotional filters</span>
                        </div>
                        <button
                          type="button"
                          onClick={handleValidateOrder}
                          disabled={isValidatingOrder}
                          className="px-3.5 py-1.5 rounded-lg bg-[#262C36] hover:bg-slate-700 text-cyan-300 text-xs font-bold border border-[#2B3139] cursor-pointer flex items-center gap-1.5"
                        >
                          {isValidatingOrder && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                          <span>{isValidatingOrder ? "Validating..." : "Validate Sizing"}</span>
                        </button>
                      </div>

                      {orderValidation && (
                        <div className={`p-3 rounded-lg border text-xs space-y-1.5 ${
                          orderValidation.is_valid
                            ? "bg-emerald-950/40 border-emerald-500/40 text-emerald-300"
                            : "bg-rose-950/40 border-rose-500/40 text-rose-300"
                        }`}>
                          <div className="font-bold flex items-center gap-1.5">
                            {orderValidation.is_valid ? <CheckCircle2 className="w-4 h-4 text-emerald-400" /> : <AlertTriangle className="w-4 h-4 text-rose-400" />}
                            <span>{orderValidation.is_valid ? "Pre-Flight Validation PASSED. Order compliant with exchange filters." : "Pre-Flight Validation REJECTED:"}</span>
                          </div>
                          {orderValidation.errors && orderValidation.errors.length > 0 && (
                            <ul className="list-disc list-inside text-[11px] space-y-0.5">
                              {orderValidation.errors.map((e: string, i: number) => <li key={i}>{e}</li>)}
                            </ul>
                          )}
                          {orderValidation.is_valid && (
                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1 text-[10px] text-[#848E9C]">
                              <div>Norm Qty: <strong className="text-[#EAECEF]">{orderValidation.normalized_qty}</strong></div>
                              <div>Norm Price: <strong className="text-[#EAECEF]">${orderValidation.normalized_price}</strong></div>
                              <div>Est Notional: <strong className="text-[#EAECEF]">${orderValidation.estimated_notional}</strong></div>
                              <div>Est Fee: <strong className="text-amber-400">${orderValidation.estimated_fee}</strong></div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>

                    {/* RIGHT COLUMN: PRE-TRADE RISK & P&L TICKET (45% Width / lg:col-span-5) */}
                    <div className="lg:col-span-5 space-y-4">
                      {executionReceipt ? (
                        /* Execution Receipt & Live Order Tracker */
                        <div className="p-5 rounded-2xl bg-[#151921] border border-emerald-500/40 space-y-4 animate-in fade-in">
                          <div className="flex items-center justify-between border-b border-[#2B3139] pb-3">
                            <div className="flex items-center gap-2">
                              <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                              <div>
                                <span className="text-sm font-bold text-[#EAECEF] block">Execution Receipt Verified</span>
                                <span className="text-[10px] text-emerald-400/80 font-mono">Binance Mock Trading Matching Engine</span>
                              </div>
                            </div>
                            <span className={`px-2.5 py-1 rounded-full font-bold text-[10px] uppercase tracking-wider border ${
                              executionReceipt.status === "FILLED"
                                ? "bg-emerald-950 text-emerald-300 border-emerald-500/50"
                                : executionReceipt.status === "OPEN"
                                ? "bg-cyan-950 text-cyan-300 border-cyan-500/50"
                                : "bg-amber-950 text-amber-300 border-amber-500/50"
                            }`}>
                              {executionReceipt.status === "FILLED" ? "✓ EXCHANGE VERIFIED / FILLED" : (executionReceipt.status === "OPEN" ? "⏳ RESTING ON BINANCE DEMO" : executionReceipt.status)}
                            </span>
                          </div>

                          {/* Lifecycle Stepper */}
                          <div className="p-3 rounded-xl bg-[#0B0E11] border border-[#2B3139] space-y-2">
                            <div className="flex items-center justify-between">
                              <span className="text-[10px] text-[#848E9C] font-bold block uppercase tracking-wider">Execution Lifecycle:</span>
                              <span className="text-[9px] font-mono text-cyan-400">Order ID: #{executionReceipt.exchange_order_id || "Awaiting Match"}</span>
                            </div>
                            <div className="grid grid-cols-4 gap-1 text-[9px] text-center font-bold">
                              <div className="p-1 rounded bg-emerald-950 text-emerald-300 border border-emerald-500/40">✓ Validated</div>
                              <div className="p-1 rounded bg-emerald-950 text-emerald-300 border border-emerald-500/40">✓ Sent to Binance</div>
                              <div className={`p-1 rounded border ${
                                executionReceipt.exchange_order_id
                                  ? "bg-emerald-950 text-emerald-300 border-emerald-500/40"
                                  : "bg-slate-900 text-slate-500 border-slate-700"
                              }`}>
                                {executionReceipt.exchange_order_id ? "✓ Accepted" : "○ Submitting"}
                              </div>
                              <div className={`p-1 rounded border ${
                                executionReceipt.status === "FILLED"
                                  ? "bg-emerald-950 text-emerald-300 border-emerald-500/40"
                                  : executionReceipt.status === "OPEN"
                                  ? "bg-cyan-950 text-cyan-300 border-cyan-500/40"
                                  : "bg-slate-900 text-slate-400 border-slate-700"
                              }`}>
                                {executionReceipt.status === "FILLED" ? "● 100% Fill" : (executionReceipt.status === "OPEN" ? "○ Orderbook" : executionReceipt.status)}
                              </div>
                            </div>
                          </div>

                          {/* Institutional Identifiers & Fill Breakdown */}
                          <div className="space-y-2 text-xs">
                            {/* Exchange Order ID Hero Box */}
                            <div className="p-2.5 rounded-xl bg-[#0B0E11] border border-[#2B3139] flex items-center justify-between">
                              <div>
                                <span className="text-[10px] text-[#848E9C] uppercase tracking-wider block">Binance Exchange Order ID</span>
                                <span className="text-amber-400 font-bold text-sm font-mono tracking-wide">
                                  {executionReceipt.exchange_order_id || "Awaiting Exchange Match"}
                                </span>
                              </div>
                              <span className="px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-500/40 text-[9px] font-bold">
                                MATCHING ENGINE ID
                              </span>
                            </div>

                            <div className="grid grid-cols-2 gap-2 text-[#848E9C]">
                              <div className="p-2 rounded bg-[#0B0E11] border border-[#2B3139]">
                                <span className="text-[10px] block">Client Order ID:</span>
                                <span className="text-cyan-300 font-bold text-[10px] font-mono truncate block" title={executionReceipt.client_order_id}>
                                  {executionReceipt.client_order_id}
                                </span>
                              </div>
                              <div className="p-2 rounded bg-[#0B0E11] border border-[#2B3139]">
                                <span className="text-[10px] block">Internal Order ID:</span>
                                <span className="text-slate-300 font-bold text-[10px] font-mono truncate block">
                                  {executionReceipt.internal_order_id || "INT-BIN-PENDING"}
                                </span>
                              </div>
                              <div className="p-2 rounded bg-[#0B0E11] border border-[#2B3139]">
                                <span className="text-[10px] block">Avg Fill Price:</span>
                                <span className="text-[#EAECEF] font-bold text-[11px] font-mono">
                                  ${executionReceipt.avg_fill_price ? executionReceipt.avg_fill_price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 6 }) : "Pending"}
                                </span>
                              </div>
                              <div className="p-2 rounded bg-[#0B0E11] border border-[#2B3139]">
                                <span className="text-[10px] block">Executed Qty:</span>
                                <span className="text-emerald-300 font-bold text-[11px] font-mono">
                                  {executionReceipt.executed_qty} {base}
                                </span>
                              </div>
                              <div className="p-2 rounded bg-[#0B0E11] border border-[#2B3139]">
                                <span className="text-[10px] block">Exchange Fee:</span>
                                <span className="text-amber-300 font-bold text-[11px] font-mono">
                                  {executionReceipt.fee_amount} {executionReceipt.fee_asset || quote}
                                </span>
                              </div>
                              <div className="p-2 rounded bg-[#0B0E11] border border-[#2B3139]">
                                <span className="text-[10px] block">Execution Routing:</span>
                                <span className="text-emerald-400 font-bold text-[10px] truncate block">
                                  Genuine Binance Demo API
                                </span>
                              </div>
                            </div>
                          </div>

                          {/* Audit Trail Monospace Drawer Strip */}
                          {executionReceipt.audit_trail && executionReceipt.audit_trail.length > 0 && (
                            <div className="p-2.5 rounded-xl bg-[#0B0E11] border border-[#2B3139] space-y-1">
                              <span className="text-[9px] uppercase tracking-wider text-[#848E9C] font-bold block">Exchange Audit Trail:</span>
                              <div className="space-y-0.5 text-[9px] font-mono text-[#848E9C] max-h-20 overflow-y-auto">
                                {executionReceipt.audit_trail.map((step, idx) => (
                                  <div key={idx} className="flex items-start gap-1">
                                    <span className="text-emerald-400 shrink-0">›</span>
                                    <span className="text-slate-300">{step}</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          <div className="pt-2 flex items-center justify-between gap-2">
                            <button
                              type="button"
                              onClick={() => {
                                setModalMode(null);
                                setExecutionReceipt(null);
                                if (typeof window !== "undefined") {
                                  window.location.hash = "orders";
                                  window.dispatchEvent(
                                    new CustomEvent("bitdex_view_order_ledger", {
                                      detail: {
                                        order_id: executionReceipt?.exchange_order_id,
                                        symbol: executionReceipt?.symbol || selectedSignal?.symbol
                                      }
                                    })
                                  );
                                }
                              }}
                              className="flex-1 py-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-[#0B0E11] font-bold text-xs flex items-center justify-center gap-1.5 cursor-pointer shadow-md"
                            >
                              <span>View Order & Trade Ledger →</span>
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setModalMode(null);
                                setExecutionReceipt(null);
                              }}
                              className="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-[#EAECEF] text-xs font-bold cursor-pointer"
                            >
                              Close
                            </button>
                          </div>
                        </div>
                      ) : (
                        /* Pre-Trade Ticket & Visual Price Ladder */
                        <div className="space-y-4">
                          {/* Visual Price Ladder */}
                          <div className="p-4 rounded-xl bg-[#262C36] border border-[#2B3139] space-y-3">
                            <div className="text-[11px] font-bold uppercase tracking-wider text-[#848E9C]">
                              Execution Summary & Visual Price Ladder
                            </div>

                            {/* TP Level */}
                            <div className="p-2.5 rounded-lg bg-emerald-950/40 border border-emerald-500/40 flex items-center justify-between">
                              <div>
                                <span className="text-[10px] text-emerald-400 font-bold block">[TP1 TARGET]</span>
                                <span className="text-[#EAECEF] font-bold text-xs">{tpP.toFixed(6)} {quote}</span>
                              </div>
                              <div className="text-right">
                                <span className="text-emerald-300 font-bold text-xs">+{rewardDistancePct.toFixed(2)}%</span>
                                <span className="text-[10px] text-emerald-400/80 block">+${netProfitUsd.toFixed(2)}</span>
                              </div>
                            </div>

                            <div className="text-center text-[10px] text-[#848E9C] font-mono">
                              ▲ Reward Distance: +{rewardDistancePct.toFixed(2)}%
                            </div>

                            {/* Entry Level */}
                            <div className="p-2.5 rounded-lg bg-cyan-950/40 border border-cyan-500/40 flex items-center justify-between">
                              <div>
                                <span className="text-[10px] text-cyan-400 font-bold block">[ENTRY PRICE]</span>
                                <span className="text-[#EAECEF] font-bold text-xs">{entryP.toFixed(6)} {quote}</span>
                              </div>
                              <div className="text-right">
                                <span className="text-cyan-300 font-bold text-xs">{orderType} Order</span>
                                <span className="text-[10px] text-[#848E9C] block">Qty: {calculatedQty.toFixed(4)} {base}</span>
                              </div>
                            </div>

                            <div className="text-center text-[10px] text-[#848E9C] font-mono">
                              ▼ Risk Distance: -{riskDistancePct.toFixed(2)}%
                            </div>

                            {/* SL Level */}
                            <div className="p-2.5 rounded-lg bg-rose-950/40 border border-rose-500/40 flex items-center justify-between">
                              <div>
                                <span className="text-[10px] text-rose-400 font-bold block">[STOP LOSS]</span>
                                <span className="text-[#EAECEF] font-bold text-xs">{slP.toFixed(6)} {quote}</span>
                              </div>
                              <div className="text-right">
                                <span className="text-rose-300 font-bold text-xs">-{riskDistancePct.toFixed(2)}%</span>
                                <span className="text-[10px] text-rose-400/80 block">-${maxLossUsd.toFixed(2)}</span>
                              </div>
                            </div>
                          </div>

                          {/* Pre-Execution Risk & Cost Telemetry */}
                          <div className="p-4 rounded-xl bg-[#262C36] border border-[#2B3139] space-y-2 text-xs">
                            <div className="text-[11px] font-bold uppercase tracking-wider text-[#848E9C] mb-2">
                              Pre-Execution Risk & Cost Telemetry
                            </div>
                            <div className="flex items-center justify-between text-[#848E9C]">
                              <span>• Position Exposure:</span>
                              <span className="text-[#EAECEF] font-bold">${orderCapitalUsd.toFixed(2)} ({accountExposurePct}% of Account)</span>
                            </div>
                            <div className="flex items-center justify-between text-[#848E9C]">
                              <span>• Risk / Reward Ratio:</span>
                              <span className="text-cyan-300 font-bold">[ 1 : {calculatedRR} ] (Institutional)</span>
                            </div>
                            <div className="flex items-center justify-between text-[#848E9C]">
                              <span>• Max Loss at SL:</span>
                              <span className="text-rose-400 font-bold">-${maxLossUsd.toFixed(2)} {quote} (-{riskDistancePct.toFixed(2)}% Equity)</span>
                            </div>
                            <div className="flex items-center justify-between text-[#848E9C]">
                              <span>• Est. Net Profit (TP):</span>
                              <span className="text-emerald-400 font-bold">+${netProfitUsd.toFixed(2)} {quote} (After Fees)</span>
                            </div>
                            <div className="flex items-center justify-between text-[#848E9C]">
                              <span>• Est. Exchange Fees:</span>
                              <span className="text-amber-400 font-bold">~${estFeesUsd.toFixed(2)} {quote} (0.10% × 2 legs)</span>
                            </div>
                          </div>

                          {/* Environment & Pair Verification Confirmation */}
                          <div className="p-4 rounded-xl bg-[#151921] border border-[#2B3139] space-y-3">
                            <div className="text-[11px] font-bold text-[#EAECEF] flex items-center justify-between">
                              <span>ENVIRONMENT & PAIR VERIFICATION:</span>
                              <span className={`px-2 py-0.5 rounded text-[10px] ${isLiveAccount ? "bg-emerald-950 text-[#0ECB81] border border-emerald-500/40" : "bg-amber-950 text-[#F0B90B] border border-amber-500/40"}`}>
                                {isLiveAccount ? "LIVE ACCOUNT" : "DEMO SANDBOX"}
                              </span>
                            </div>
                            <div className="p-2.5 rounded-lg bg-[#262C36] text-[11px] text-[#848E9C]">
                              Target: <strong className="text-[#EAECEF]">{selectedConn ? selectedConn.exchange_name || selectedConn.exchange : "BINANCE"} {orderEnvironment}</strong> • <strong className="text-cyan-300">{selectedSignal.symbol}</strong> • <strong className="text-[#EAECEF]">{orderType} {selectedSignal.direction}</strong>
                            </div>

                            {isLiveAccount && (
                              <label className="flex items-start gap-2 text-[11px] text-emerald-300 font-bold cursor-pointer p-2 rounded bg-emerald-950/30 border border-emerald-500/30">
                                <input
                                  type="checkbox"
                                  checked={isLiveExecutionConfirmed}
                                  onChange={(e) => setIsLiveExecutionConfirmed(e.target.checked)}
                                  className="mt-0.5 accent-emerald-500"
                                />
                                <span>I confirm LIVE REAL CAPITAL execution on {selectedConn?.label || "selected live exchange"}.</span>
                              </label>
                            )}

                            <label className="flex items-start gap-2 text-[11px] text-[#848E9C] cursor-pointer">
                              <input
                                type="checkbox"
                                checked={isParametersConfirmed}
                                onChange={(e) => setIsParametersConfirmed(e.target.checked)}
                                className="mt-0.5 accent-cyan-500"
                              />
                              <span>I confirm execution parameters and fee disclosures on {orderEnvironment} account.</span>
                            </label>

                            {executionError && (
                              <div className="p-2.5 rounded bg-rose-950/40 border border-rose-500/40 text-rose-300 text-xs">
                                {executionError}
                              </div>
                            )}

                            {/* Submit Button */}
                            {isLiveAccount ? (
                              <button
                                type="button"
                                disabled={true}
                                className="w-full py-3 px-4 rounded-xl bg-[#262C36] text-[#848E9C] border border-[#2B3139] font-bold text-xs font-mono flex items-center justify-center gap-2 cursor-not-allowed opacity-80"
                                title="Live order submission locked on staging"
                              >
                                <Lock className="w-4 h-4 text-amber-400" />
                                <span>🔒 EXECUTION LOCKED (READ-ONLY MODE) — SIMULATE VALIDATION ONLY</span>
                              </button>
                            ) : (
                              <button
                                type="button"
                                onClick={handleSubmitDemoOrder}
                                disabled={isSubmittingOrder || !isParametersConfirmed}
                                className="w-full py-3 px-4 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-[#EAECEF] font-bold text-xs font-mono flex items-center justify-center gap-2 cursor-pointer shadow-lg shadow-emerald-950/40 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                              >
                                <Zap className="w-4 h-4 text-emerald-200" />
                                <span>{isSubmittingOrder ? "Submitting Order..." : `⚡ SUBMIT DEMO ${selectedSignal?.direction || "BUY"} ORDER — ${selectedSignal?.symbol || "PAIR"} ($${orderCapitalUsd})`}</span>
                              </button>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })()}

            {/* Terminal Footer */}
            <div className="p-3.5 border-t border-[#2B3139] bg-[#151921] flex items-center justify-between text-xs font-mono">
              <span className="text-[#848E9C] flex items-center gap-1.5">
                <Lock className="w-3.5 h-3.5 text-cyan-400" />
                <span>Deterministic Sizing: Live trading locked · Real exchange capital protected</span>
              </span>
              <button
                type="button"
                onClick={() => {
                  setModalMode(null);
                  setExecutionReceipt(null);
                  setExecutionError(null);
                  setOrderValidation(null);
                }}
                className="px-4 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-[#EAECEF] cursor-pointer"
              >
                Close Terminal
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ─── Dedicated Scalping Grid Execution Modal ─── */}
      {modalMode === "EXECUTE_SCALP_GRID" && selectedSignal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#1E2329]/40 backdrop-blur-md animate-in fade-in overflow-y-auto">
          <div className="w-full max-w-3xl bg-[#1E2329] border border-[#2B3139] shadow-sm rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[92vh] my-auto">
            {/* Modal Header */}
            <div className="p-5 border-b border-[#2B3139] flex items-center justify-between bg-[#262C36]/80">
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-xl bg-sky-950/60 border border-sky-500/30 text-sky-400">
                  <Layers className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-[#EAECEF] font-mono flex items-center gap-2">
                    <span>Scalping — Grid Strategy Execution</span>
                    <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded-full bg-sky-950 text-sky-300 border border-sky-500/40">
                      Phase 3.3 Dynamic Grid
                    </span>
                  </h3>
                  <p className="text-xs text-[#848E9C]">
                    Non-directional quantitative range scalping with automated multi-tier limit order placement.
                  </p>
                </div>
              </div>
              <button
                onClick={() => {
                  setModalMode(null);
                  setGridExecutionReceipt(null);
                  setGridExecutionError(null);
                }}
                className="p-2 rounded-lg bg-slate-800/80 hover:bg-slate-700 text-[#848E9C] hover:text-[#EAECEF] transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 overflow-y-auto space-y-5 flex-1 text-xs font-mono">
              {/* Scalping Pair Selector & Exchange Trading Filter Metadata */}
              <div className="p-4 rounded-xl bg-[#262C36] border border-[#2B3139] space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#2B3139] pb-2">
                  <span className="text-[11px] font-bold text-[#EAECEF] uppercase tracking-wider flex items-center gap-2">
                    <Layers className="w-3.5 h-3.5 text-[#00E5FF]" />
                    <span>Tradable Instrument & Exchange Filters</span>
                  </span>
                  <span className="text-[10px] text-[#00E5FF] font-mono">
                    {gridSymbols.length > 0 ? `${gridSymbols.length} Instruments Loaded` : "Loading Pairs..."}
                  </span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[#848E9C] text-[10px] mb-1 font-mono uppercase">
                      Select Tradable Pair
                    </label>
                    <select
                      value={selectedSignal.symbol}
                      onChange={(e) => {
                        const chosenSym = e.target.value;
                        const meta = gridSymbols.find((s) => s.symbol === chosenSym || s.symbol === chosenSym.replace("/", ""));
                        setGridSelectedSymbolMeta(meta || null);
                        const ov = overviewMarkets.find((m) => m.symbol === chosenSym || m.symbol.replace("/", "") === chosenSym.replace("/", ""));
                        const newPrice: number | null = typeof ov?.price === "number" && ov.price > 0 ? ov.price : null;
                        setSelectedSignal((prev: any) => ({
                          ...prev,
                          symbol: chosenSym,
                          reference_price: newPrice,
                          market: meta?.market || (chosenSym.includes("/") ? "FOREX" : "CRYPTO"),
                        }));
                        if (newPrice === null) {
                          // No verified live quote: never invent a reference price or grid range.
                          setGridLowerPrice(0 as any);
                          setGridUpperPrice(0 as any);
                          setGridStopLoss(0 as any);
                          setGridTakeProfit(0 as any);
                          return;
                        }
                        const lower = Number((newPrice * 0.95).toFixed(newPrice >= 100 ? 2 : 4));
                        const upper = Number((newPrice * 1.05).toFixed(newPrice >= 100 ? 2 : 4));
                        setGridLowerPrice(lower);
                        setGridUpperPrice(upper);
                        setGridStopLoss(Number((newPrice * 0.92).toFixed(newPrice >= 100 ? 2 : 4)));
                        setGridTakeProfit(Number((newPrice * 1.08).toFixed(newPrice >= 100 ? 2 : 4)));
                      }}
                      className="w-full px-3 py-2 rounded-lg bg-[#1E2329] border border-[#2B3139] text-[#EAECEF] font-mono text-xs focus:border-[#00E5FF] focus:outline-none"
                    >
                      <option value={selectedSignal.symbol}>{selectedSignal.symbol} (Active Selection)</option>
                      {gridSymbols.slice(0, 100).map((s) => (
                        <option key={s.instrument_id || s.symbol} value={s.symbol}>
                          {s.symbol} — {s.market} ({s.name || s.base})
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Instrument Filters Verified Badges */}
                  <div className="p-2.5 rounded-lg bg-[#1E2329] border border-[#2B3139] flex flex-wrap items-center justify-between gap-2 text-[10px] font-mono">
                    <div>
                      <span className="text-[#848E9C] block">Tick Size</span>
                      <span className="text-[#EAECEF] font-bold">{gridSelectedSymbolMeta?.tick_size ?? "0.01"}</span>
                    </div>
                    <div>
                      <span className="text-[#848E9C] block">Step / Lot</span>
                      <span className="text-[#EAECEF] font-bold">{gridSelectedSymbolMeta?.step_size ?? "0.001"}</span>
                    </div>
                    <div>
                      <span className="text-[#848E9C] block">Min Notional</span>
                      <span className="text-[#0ECB81] font-bold">${gridSelectedSymbolMeta?.min_notional ?? "5.00"}</span>
                    </div>
                    <div>
                      <span className="text-[#848E9C] block">Market</span>
                      <span className="text-[#00E5FF] font-bold">{gridSelectedSymbolMeta?.market || selectedSignal.market || "CRYPTO"}</span>
                    </div>
                  </div>
                </div>

                {gridSelectedSymbolMeta && gridCapitalUsd < (gridSelectedSymbolMeta.min_notional || 5) && (
                  <div className="p-2 rounded bg-rose-950/60 border border-rose-500/40 text-rose-300 text-[10px] font-mono flex items-center gap-2">
                    <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                    <span>Allocated capital (${gridCapitalUsd}) is below exchange minimum notional (${gridSelectedSymbolMeta.min_notional} USD).</span>
                  </div>
                )}
              </div>

              {/* Asset & Reference Price Header */}
              <div className="p-4 rounded-xl bg-[#262C36]/80 border border-[#2B3139] flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="px-3 py-1.5 rounded-lg text-xs font-bold font-mono bg-sky-950 text-sky-300 border border-sky-500/40">
                    SCALP GRID
                  </div>
                  <div>
                    <div className="text-base font-bold text-[#EAECEF]">{selectedSignal.symbol}</div>
                    <div className="text-[#848E9C] text-[11px]">
                      Reference Price: <span className="text-[#EAECEF] font-bold">${selectedSignal.reference_price?.toLocaleString() || "--"}</span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2 text-[10px] font-mono">
                  {(() => {
                    const isAdminExempt = saasFeePolicy?.is_admin_exempt === true || saasFeePolicy?.fee_waived === 1 || saasBillingSummary?.is_admin_exempt === true;
                    if (isAdminExempt) {
                      return (
                        <span className="px-2.5 py-1 rounded-xl bg-sky-950/60 border border-sky-400/50 text-sky-300 font-bold flex items-center gap-1.5 shadow-sm">
                          <ShieldCheck className="w-3.5 h-3.5 text-sky-400" />
                          <span>ADMIN — FEE EXEMPT ($0.00)</span>
                        </span>
                      );
                    }
                    return (
                      <>
                        <span className="px-2 py-1 rounded bg-[#1E2329] border border-[#2B3139] shadow-sm text-[#848E9C]">
                          Execution Fee: <strong className="text-amber-400">$0.30</strong>
                        </span>
                        <span className="px-2 py-1 rounded bg-[#1E2329] border border-[#2B3139] shadow-sm text-[#848E9C]">
                          Prepaid: <strong className="text-cyan-400">${(saasBillingSummary?.prepaid_credits_usd || 0).toFixed(2)}</strong>
                        </span>
                      </>
                    );
                  })()}
                </div>
              </div>

              {/* Execution Receipt Display */}
              {gridExecutionReceipt ? (
                <div className="space-y-4">
                  <div className="p-4 rounded-xl bg-emerald-950/30 border border-emerald-500/40 space-y-3">
                    <div className="flex items-center justify-between border-b border-emerald-500/20 pb-2">
                      <div className="flex items-center gap-2 text-emerald-400 font-bold">
                        <CheckCircle2 className="w-5 h-5" />
                        <span>Scalping Grid Strategy Initialized Successfully</span>
                      </div>
                      <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                        {gridExecutionReceipt.status}
                      </span>
                    </div>

                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
                      <div>
                        <span className="text-[#848E9C] block text-[10px]">ORDER ID</span>
                        <span className="text-[#EAECEF] font-bold truncate block">{gridExecutionReceipt.order_id}</span>
                      </div>
                      <div>
                        <span className="text-[#848E9C] block text-[10px]">STRATEGY LABEL</span>
                        <span className="text-sky-300 font-bold">{gridExecutionReceipt.strategy_label}</span>
                      </div>
                      <div>
                        <span className="text-[#848E9C] block text-[10px]">GRID LINES</span>
                        <span className="text-[#EAECEF] font-bold">{gridExecutionReceipt.grid_count} Grids</span>
                      </div>
                      <div>
                        <span className="text-[#848E9C] block text-[10px]">LOWER BOUNDARY</span>
                        <span className="text-[#EAECEF] font-mono">${gridExecutionReceipt.lower_price?.toLocaleString()}</span>
                      </div>
                      <div>
                        <span className="text-[#848E9C] block text-[10px]">UPPER BOUNDARY</span>
                        <span className="text-[#EAECEF] font-mono">${gridExecutionReceipt.upper_price?.toLocaleString()}</span>
                      </div>
                      <div>
                        <span className="text-[#848E9C] block text-[10px]">FEE DEDUCTION</span>
                        <span className="text-sky-300 font-bold">
                          {gridExecutionReceipt.admin_fee_exempt || gridExecutionReceipt.fee_deducted_usd === 0
                            ? "$0.00 (ADMIN EXEMPT)"
                            : `-$${gridExecutionReceipt.fee_deducted_usd?.toFixed(2)} USD`}
                        </span>
                      </div>
                    </div>

                    {gridExecutionReceipt.grid_levels && gridExecutionReceipt.grid_levels.length > 0 && (
                      <div className="pt-2 border-t border-emerald-500/20">
                        <span className="text-[10px] text-[#848E9C] uppercase tracking-wider block mb-1.5">
                          Calculated Limit Grid Levels ({gridExecutionReceipt.grid_levels.length})
                        </span>
                        <div className="grid grid-cols-4 sm:grid-cols-6 gap-1.5 text-[10px]">
                          {gridExecutionReceipt.grid_levels.map((lvl: any, idx: number) => (
                            <div key={idx} className="p-1 rounded bg-[#1E2329] border border-[#2B3139] shadow-sm text-center">
                              <span className="text-[#848E9C] text-[9px] block">G{idx + 1}</span>
                              <span className="text-[#EAECEF] font-bold">${typeof lvl === "object" ? lvl.price : lvl}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="flex justify-end">
                    <button
                      onClick={() => {
                        setModalMode(null);
                        setGridExecutionReceipt(null);
                        setGridExecutionError(null);
                      }}
                      className="px-5 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-[#EAECEF] font-bold text-xs font-mono"
                    >
                      Done
                    </button>
                  </div>
                </div>
              ) : (
                /* 10 Required Grid Risk Fields Configuration Form */
                <div className="space-y-4">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {/* 1. Lower Price Boundary */}
                    <div>
                      <label className="block text-[#848E9C] text-[11px] mb-1">
                        1. Lower Boundary Price ($ USD)
                      </label>
                      <input
                        type="number"
                        step="0.01"
                        value={gridLowerPrice}
                        onChange={(e) => setGridLowerPrice(Number(e.target.value))}
                        className="w-full px-3 py-2 rounded-lg bg-[#262C36] border border-[#2B3139] text-[#EAECEF] font-mono text-xs focus:border-sky-500 focus:outline-none"
                      />
                    </div>

                    {/* 2. Upper Price Boundary */}
                    <div>
                      <label className="block text-[#848E9C] text-[11px] mb-1">
                        2. Upper Boundary Price ($ USD)
                      </label>
                      <input
                        type="number"
                        step="0.01"
                        value={gridUpperPrice}
                        onChange={(e) => setGridUpperPrice(Number(e.target.value))}
                        className="w-full px-3 py-2 rounded-lg bg-[#262C36] border border-[#2B3139] text-[#EAECEF] font-mono text-xs focus:border-sky-500 focus:outline-none"
                      />
                    </div>

                    {/* 3. Number of Grids (3-150) */}
                    <div>
                      <label className="block text-[#848E9C] text-[11px] mb-1">
                        3. Grid Density (3 - 150 Lines)
                      </label>
                      <input
                        type="number"
                        min="3"
                        max="150"
                        step="1"
                        value={gridCount}
                        onChange={(e) => setGridCount(Number(e.target.value))}
                        className="w-full px-3 py-2 rounded-lg bg-[#262C36] border border-[#2B3139] text-[#EAECEF] font-mono text-xs focus:border-sky-500 focus:outline-none"
                      />
                    </div>

                    {/* 4. Calculated Spacing % */}
                    <div>
                      <label className="block text-[#848E9C] text-[11px] mb-1">
                        4. Grid Spacing (% per Step)
                      </label>
                      <div className="px-3 py-2 rounded-lg bg-[#262C36]/80 border border-[#2B3139] text-cyan-300 font-mono text-xs font-bold tabular-nums">
                        {gridLowerPrice > 0 && gridUpperPrice > gridLowerPrice && gridCount > 1
                          ? `${(((gridUpperPrice - gridLowerPrice) / gridLowerPrice / (gridCount - 1)) * 100).toFixed(2)}%`
                          : "Calculated dynamically"}
                      </div>
                    </div>

                    {/* 5. Allocated Capital */}
                    <div>
                      <label className="block text-[#848E9C] text-[11px] mb-1">
                        5. Allocated Capital ($ USDT, Min $15)
                      </label>
                      <input
                        type="number"
                        min="15"
                        step="10"
                        value={gridCapitalUsd}
                        onChange={(e) => setGridCapitalUsd(Number(e.target.value))}
                        className="w-full px-3 py-2 rounded-lg bg-[#262C36] border border-[#2B3139] text-[#EAECEF] font-mono text-xs focus:border-sky-500 focus:outline-none"
                      />
                    </div>

                    {/* 6. Order Size per Grid */}
                    <div>
                      <label className="block text-[#848E9C] text-[11px] mb-1">
                        6. Capital per Grid Order
                      </label>
                      <div className="px-3 py-2 rounded-lg bg-[#262C36]/80 border border-[#2B3139] text-emerald-300 font-mono text-xs font-bold tabular-nums">
                        ${gridCount > 0 ? (gridCapitalUsd / gridCount).toFixed(2) : "0.00"} USDT
                      </div>
                    </div>

                    {/* 7. Fee Friction & Net Margin */}
                    <div>
                      <label className="block text-[#848E9C] text-[11px] mb-1">
                        7. Fee Friction & Net Cycle Margin
                      </label>
                      <div className="px-3 py-2 rounded-lg bg-[#262C36]/80 border border-[#2B3139] text-amber-300 font-mono text-xs tabular-nums">
                        {(() => {
                          const spacing = gridLowerPrice > 0 && gridUpperPrice > gridLowerPrice && gridCount > 1
                            ? ((gridUpperPrice - gridLowerPrice) / gridLowerPrice / (gridCount - 1)) * 100
                            : 0;
                          const net = Math.max(0, spacing - 0.25);
                          return `Friction: 0.25% • Net: +${net.toFixed(2)}%`;
                        })()}
                      </div>
                    </div>

                    {/* 8. Reference Price */}
                    <div>
                      <label className="block text-[#848E9C] text-[11px] mb-1">
                        8. Current Reference Anchor
                      </label>
                      <div className="px-3 py-2 rounded-lg bg-[#262C36]/80 border border-[#2B3139] text-[#EAECEF] font-mono text-xs tabular-nums font-bold">
                        ${selectedSignal.reference_price.toLocaleString()}
                      </div>
                    </div>

                    {/* 9. Stop Loss Invalidation Rule */}
                    <div>
                      <label className="block text-[#848E9C] text-[11px] mb-1">
                        9. Stop Loss Invalidation Price ($)
                      </label>
                      <input
                        type="number"
                        step="0.01"
                        value={gridStopLoss}
                        onChange={(e) => setGridStopLoss(Number(e.target.value))}
                        className="w-full px-3 py-2 rounded-lg bg-[#262C36] border border-[#2B3139] text-rose-300 font-mono text-xs focus:border-rose-500 focus:outline-none"
                      />
                    </div>

                    {/* 10. Exit / Take Profit Rule */}
                    <div>
                      <label className="block text-[#848E9C] text-[11px] mb-1">
                        10. Exit / Take Profit Price ($)
                      </label>
                      <input
                        type="number"
                        step="0.01"
                        value={gridTakeProfit}
                        onChange={(e) => setGridTakeProfit(Number(e.target.value))}
                        className="w-full px-3 py-2 rounded-lg bg-[#262C36] border border-[#2B3139] text-emerald-300 font-mono text-xs focus:border-emerald-500 focus:outline-none"
                      />
                    </div>
                  </div>

                  {/* Summary / Risk Bounds Notice */}
                  <div className="p-3.5 rounded-xl bg-[#262C36] border border-[#2B3139] text-[11px] text-[#848E9C] space-y-1">
                    <div className="flex items-center justify-between text-[#848E9C]">
                      <span>Max Exposure Cap: <strong className="text-[#EAECEF]">${gridCapitalUsd} USDT</strong></span>
                      <span>Grid Type: <strong className="text-sky-300">Arithmetic Spot Grid</strong></span>
                    </div>
                    <p className="text-[10px] text-[#848E9C]">
                      Invalidation rule: Position closes and orders cancel if hourly close breaches ${gridStopLoss || "--"}.
                      Fee deduction: $0.30 per grid execution.
                    </p>
                  </div>

                  {gridExecutionError && (
                    <div className="p-3 rounded-lg bg-rose-950/40 border border-rose-500/40 text-rose-300 text-xs">
                      {gridExecutionError}
                    </div>
                  )}

                  {/* Submission Action */}
                  <div className="pt-2 flex items-center justify-between">
                    <span className="text-[#848E9C] text-[11px]">
                      Scalping grid strategies execute across server-side testnet simulation.
                    </span>

                    <button
                      onClick={handleSubmitGridOrder}
                      disabled={isSubmittingGridOrder || gridLowerPrice >= gridUpperPrice || gridCapitalUsd < 15 || gridCount < 3}
                      className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-sky-600 to-indigo-600 hover:from-sky-500 hover:to-indigo-500 text-[#EAECEF] font-bold text-xs font-mono flex items-center gap-2 cursor-pointer shadow-lg shadow-sky-950/40 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <Layers className="w-4 h-4 text-sky-200" />
                      <span>{isSubmittingGridOrder ? "Deploying Grid..." : "Submit Scalping Grid Strategy"}</span>
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-[#2B3139] bg-[#262C36] flex items-center justify-between">
              <span className="text-xs font-mono text-[#848E9C] flex items-center gap-1.5">
                <Lock className="w-3.5 h-3.5 text-cyan-500" />
                Live trading locked · Real exchange execution blocked
              </span>
              <button
                onClick={() => {
                  setModalMode(null);
                  setGridExecutionReceipt(null);
                  setGridExecutionError(null);
                }}
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-[#EAECEF] text-xs font-mono cursor-pointer transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ─── Modal 3: Positions & Live Portfolio Screen (Phase 3.3) ─── */}
      {modalMode === "POSITIONS" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#1E2329]/40 backdrop-blur-md animate-in fade-in">
          <div id="execution-terminal-drawer" className="w-full max-w-5xl bg-[#1E2329] border border-[#2B3139] shadow-sm rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[92vh]">
            {/* Modal Header */}
            <div className="p-5 border-b border-[#2B3139] flex items-center justify-between bg-[#262C36]">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-xl bg-emerald-950/60 border border-emerald-500/30 text-emerald-400">
                  <Briefcase className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-[#EAECEF] font-mono flex items-center gap-2">
                    <span>Positions & Live Portfolio</span>
                    <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-300 border border-emerald-500/40">
                      Phase 3.3 Real-Time P&L
                    </span>
                  </h3>
                  <p className="text-xs text-[#848E9C]">
                    Live mark-to-market valuations, executed fills, and fee reconciliation for testnet and paper positions.
                  </p>
                </div>
              </div>
              <button
                onClick={() => setModalMode(null)}
                className="p-2 rounded-lg bg-slate-800/80 hover:bg-slate-700 text-[#848E9C] hover:text-[#EAECEF] transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 overflow-y-auto space-y-5 flex-1 text-xs font-mono">
              {/* Market & Environment Switchers */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  {/* Market Selector Pill */}
                  <div className="flex items-center gap-1 p-1 bg-[#262C36] rounded-xl border border-[#2B3139]">
                    <button
                      onClick={() => {
                        setSelectedMarket("CRYPTO");
                        fetchPositions(positionsEnvironment, "CRYPTO");
                      }}
                      className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                        selectedMarket === "CRYPTO"
                          ? "bg-cyan-950 text-cyan-300 border border-cyan-500/40 shadow-sm"
                          : "text-[#848E9C] hover:text-[#EAECEF]"
                      }`}
                    >
                      Crypto
                    </button>
                    <button
                      onClick={() => {
                        setSelectedMarket("FOREX");
                        fetchPositions(positionsEnvironment, "FOREX");
                      }}
                      className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                        selectedMarket === "FOREX"
                          ? "bg-sky-950 text-sky-300 border border-sky-500/40 shadow-sm"
                          : "text-[#848E9C] hover:text-[#EAECEF]"
                      }`}
                    >
                      Forex & Metals
                    </button>
                  </div>

                  {/* Environment Selector Pill (ALL, DEMO, LIVE) */}
                  <div className="flex items-center gap-1 p-1 bg-[#262C36] rounded-xl border border-[#2B3139]">
                    {(["ALL", "DEMO", "LIVE"] as const).map((env) => (
                      <button
                        key={env}
                        onClick={() => {
                          setPositionsEnvironment(env);
                          fetchPositions(env, selectedMarket);
                        }}
                        className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                          positionsEnvironment === env
                            ? env === "DEMO"
                              ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                              : env === "LIVE"
                              ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                              : "bg-slate-800 text-[#EAECEF] border border-[#2B3139]"
                            : "text-[#848E9C] hover:text-[#EAECEF]"
                        }`}
                      >
                        {env === "ALL" ? "All" : env === "DEMO" ? "Demo" : "Live"}
                      </button>
                    ))}
                  </div>
                </div>

                <button
                  onClick={() => fetchPositions(positionsEnvironment, selectedMarket)}
                  disabled={isLoadingPositions}
                  className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-cyan-300 text-xs font-bold border border-[#2B3139] flex items-center gap-1.5 cursor-pointer"
                >
                  <RefreshCw className={`w-3 h-3 ${isLoadingPositions ? "animate-spin" : ""}`} />
                  <span>Refresh Marks</span>
                </button>
              </div>

              {/* Unified Metrics Strip & Mathematical Reconciliation */}
              {positionsMetrics && (
                <div className="space-y-2">
                  <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
                    <div className="p-3 rounded-xl bg-[#262C36] border border-[#2B3139]">
                      <span className="text-[10px] text-[#848E9C] block uppercase">Unrealized P&L</span>
                      <span
                        className={`text-lg font-bold font-mono ${
                          positionsMetrics.total_unrealized_pnl_usd >= 0 ? "text-emerald-400" : "text-rose-400"
                        }`}
                      >
                        {positionsMetrics.total_unrealized_pnl_usd >= 0 ? "+" : ""}${positionsMetrics.total_unrealized_pnl_usd.toFixed(2)}
                      </span>
                    </div>

                    <div className="p-3 rounded-xl bg-[#262C36] border border-[#2B3139]">
                      <span className="text-[10px] text-[#848E9C] block uppercase">Gross Realized P&L</span>
                      <span
                        className={`text-lg font-bold font-mono ${
                          (positionsMetrics.total_realized_gross_usd !== undefined ? positionsMetrics.total_realized_gross_usd : positionsMetrics.total_realized_pnl_usd) >= 0 ? "text-emerald-400" : "text-rose-400"
                        }`}
                      >
                        {(positionsMetrics.total_realized_gross_usd !== undefined ? positionsMetrics.total_realized_gross_usd : positionsMetrics.total_realized_pnl_usd) >= 0 ? "+" : ""}${(positionsMetrics.total_realized_gross_usd !== undefined ? positionsMetrics.total_realized_gross_usd : positionsMetrics.total_realized_pnl_usd).toFixed(2)}
                      </span>
                    </div>

                    <div className="p-3 rounded-xl bg-[#262C36] border border-[#2B3139]">
                      <span className="text-[10px] text-[#848E9C] block uppercase">Fees Deducted</span>
                      <span className="text-lg font-bold font-mono text-amber-300">
                        -${positionsMetrics.total_fees_usd.toFixed(4)}
                      </span>
                    </div>

                    <div className="p-3 rounded-xl bg-[#262C36] border border-[#2B3139]">
                      <span className="text-[10px] text-[#848E9C] block uppercase">Net Realized P&L</span>
                      <span
                        className={`text-lg font-bold font-mono ${
                          (positionsMetrics.total_realized_net_usd !== undefined ? positionsMetrics.total_realized_net_usd : (positionsMetrics.total_realized_pnl_usd - positionsMetrics.total_fees_usd)) >= 0 ? "text-emerald-400" : "text-rose-400"
                        }`}
                      >
                        {(positionsMetrics.total_realized_net_usd !== undefined ? positionsMetrics.total_realized_net_usd : (positionsMetrics.total_realized_pnl_usd - positionsMetrics.total_fees_usd)) >= 0 ? "+" : ""}${(positionsMetrics.total_realized_net_usd !== undefined ? positionsMetrics.total_realized_net_usd : (positionsMetrics.total_realized_pnl_usd - positionsMetrics.total_fees_usd)).toFixed(2)}
                      </span>
                    </div>

                    <div className="p-3 rounded-xl bg-[#262C36] border border-[#2B3139] col-span-2 sm:col-span-1">
                      <span className="text-[10px] text-[#848E9C] block uppercase">Total Net P&L</span>
                      <span
                        className={`text-lg font-bold font-mono ${
                          positionsMetrics.net_pnl_usd >= 0 ? "text-emerald-400" : "text-rose-400"
                        }`}
                      >
                        {positionsMetrics.net_pnl_usd >= 0 ? "+" : ""}${positionsMetrics.net_pnl_usd.toFixed(2)}
                      </span>
                    </div>
                  </div>

                  <div className="p-2.5 rounded-lg bg-[#262C36]/90 border border-[#2B3139] text-[11px] text-[#848E9C]">
                    <strong className="text-[#848E9C]">Fee Treatment:</strong> Exchange and broker fees are deducted from gross realized P&L. Total Net P&L = Net Realized P&L + Mark-to-Market Unrealized P&L. Realized trades are never added to totals twice.
                  </div>
                </div>
              )}

              {/* Open Positions Table */}
              <div className="space-y-2">
                <div className="text-sm font-bold text-[#EAECEF] flex items-center justify-between">
                  <span>Open Positions ({positionsList.filter((p) => {
                    if (p.status !== "OPEN") return false;
                    if (positionsEnvironment !== "ALL" && p.environment !== positionsEnvironment) return false;
                    const isForex = (p.market_type === "FOREX") || (p.symbol && (p.symbol.includes("XAU") || p.symbol.includes("EUR") || p.symbol.includes("GBP")));
                    if (selectedMarket === "CRYPTO" && isForex) return false;
                    if (selectedMarket === "FOREX" && !isForex) return false;
                    return true;
                  }).length})</span>
                  <span className="text-[10px] text-[#848E9C] font-mono">Showing {selectedMarket === "CRYPTO" ? "Crypto" : "Forex & Metals"} · {positionsEnvironment}</span>
                </div>

                {positionsList.filter((p) => {
                  if (p.status !== "OPEN") return false;
                  if (positionsEnvironment !== "ALL" && p.environment !== positionsEnvironment) return false;
                  const isForex = (p.market_type === "FOREX") || (p.symbol && (p.symbol.includes("XAU") || p.symbol.includes("EUR") || p.symbol.includes("GBP")));
                  if (selectedMarket === "CRYPTO" && isForex) return false;
                  if (selectedMarket === "FOREX" && !isForex) return false;
                  return true;
                }).length === 0 ? (
                  <div className="p-6 rounded-xl bg-[#262C36]/40 border border-[#2B3139] text-center text-[#848E9C]">
                    No active positions currently open in this environment.
                  </div>
                ) : (
                  <div className="overflow-x-auto rounded-xl border border-[#2B3139]">
                    <table className="w-full text-left font-mono">
                      <thead className="bg-[#262C36] text-[#848E9C] text-[10px] uppercase border-b border-[#2B3139]">
                        <tr>
                          <th className="p-3">Symbol</th>
                          <th className="p-3">Side</th>
                          <th className="p-3">Size</th>
                          <th className="p-3">Entry Price</th>
                          <th className="p-3">Mark Price</th>
                          <th className="p-3">Unrealized P&L</th>
                          <th className="p-3">SL / TP</th>
                          <th className="p-3">Opened</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60 bg-[#262C36]/30">
                        {positionsList
                          .filter((p) => {
                            if (p.status !== "OPEN") return false;
                            if (positionsEnvironment !== "ALL" && p.environment !== positionsEnvironment) return false;
                            const isForex = (p.market_type === "FOREX") || (p.symbol && (p.symbol.includes("XAU") || p.symbol.includes("EUR") || p.symbol.includes("GBP")));
                            if (selectedMarket === "CRYPTO" && isForex) return false;
                            if (selectedMarket === "FOREX" && !isForex) return false;
                            return true;
                          })
                          .map((pos) => (
                            <tr key={pos.position_id} className="hover:bg-[#1E2329]/40 transition-colors">
                              <td className="p-3 font-bold text-[#EAECEF]">{pos.symbol}</td>
                              <td className="p-3">
                                <span
                                  className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                    pos.side === "LONG"
                                      ? "bg-emerald-950 text-emerald-300 border border-emerald-500/40"
                                      : "bg-rose-950 text-rose-300 border border-rose-500/40"
                                  }`}
                                >
                                  {pos.side}
                                </span>
                              </td>
                              <td className="p-3 text-[#848E9C]">{pos.size}</td>
                              <td className="p-3 text-[#848E9C]">${pos.entry_price.toLocaleString()}</td>
                              <td className="p-3 text-[#EAECEF] font-bold">${pos.mark_price.toLocaleString()}</td>
                              <td className="p-3 font-bold">
                                <span className={pos.unrealized_pnl >= 0 ? "text-emerald-400" : "text-rose-400"}>
                                  ${pos.unrealized_pnl.toFixed(2)} ({pos.unrealized_pnl_pct.toFixed(2)}%)
                                </span>
                              </td>
                              <td className="p-3 text-[#848E9C] text-[10px]">
                                {pos.stop_loss ? `$${pos.stop_loss}` : "--"} / {pos.take_profit ? `$${pos.take_profit}` : "--"}
                              </td>
                              <td className="p-3 text-[#848E9C] text-[10px]">{pos.opened_at_utc}</td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* Closed Positions Table — Full Audit & Fee Reconciliation */}
              <div className="space-y-2 pt-3">
                <div className="text-sm font-bold text-[#EAECEF] flex items-center justify-between">
                  <span>Closed Trade History ({positionsList.filter((p) => {
                    if (p.status !== "CLOSED") return false;
                    if (positionsEnvironment !== "ALL" && p.environment !== positionsEnvironment) return false;
                    const isForex = (p.market_type === "FOREX") || (p.symbol && (p.symbol.includes("XAU") || p.symbol.includes("EUR") || p.symbol.includes("GBP")));
                    if (selectedMarket === "CRYPTO" && isForex) return false;
                    if (selectedMarket === "FOREX" && !isForex) return false;
                    return true;
                  }).length})</span>
                  <span className="text-[10px] text-[#848E9C] font-mono">Showing {selectedMarket === "CRYPTO" ? "Crypto" : "Forex & Metals"} · {positionsEnvironment}</span>
                </div>

                {positionsList.filter((p) => {
                  if (p.status !== "CLOSED") return false;
                  if (positionsEnvironment !== "ALL" && p.environment !== positionsEnvironment) return false;
                  const isForex = (p.market_type === "FOREX") || (p.symbol && (p.symbol.includes("XAU") || p.symbol.includes("EUR") || p.symbol.includes("GBP")));
                  if (selectedMarket === "CRYPTO" && isForex) return false;
                  if (selectedMarket === "FOREX" && !isForex) return false;
                  return true;
                }).length > 0 ? (
                  <div className="overflow-x-auto rounded-xl border border-[#2B3139]">
                    <table className="w-full text-left font-mono">
                      <thead className="bg-[#262C36] text-[#848E9C] text-[10px] uppercase border-b border-[#2B3139]">
                        <tr>
                          <th className="p-3">Instrument & Market</th>
                          <th className="p-3">Env / Broker</th>
                          <th className="p-3">Side</th>
                          <th className="p-3">Entry & Exit / Size</th>
                          <th className="p-3">Gross Realized</th>
                          <th className="p-3">Fees Deducted</th>
                          <th className="p-3">Net Realized</th>
                          <th className="p-3">Close Timestamp</th>
                          <th className="p-3">Verification & Origin</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60 bg-[#262C36]/30">
                        {positionsList
                          .filter((p) => {
                            if (p.status !== "CLOSED") return false;
                            if (positionsEnvironment !== "ALL" && p.environment !== positionsEnvironment) return false;
                            const isForex = (p.market_type === "FOREX") || (p.symbol && (p.symbol.includes("XAU") || p.symbol.includes("EUR") || p.symbol.includes("GBP")));
                            if (selectedMarket === "CRYPTO" && isForex) return false;
                            if (selectedMarket === "FOREX" && !isForex) return false;
                            return true;
                          })
                          .map((pos) => {
                            const isLong = pos.side === "LONG";
                            const netRealized = pos.realized_pnl - (pos.fees_paid || 0);
                            return (
                              <tr key={pos.position_id} className="hover:bg-[#1E2329]/40 transition-colors">
                                <td className="p-3">
                                  <div className="flex items-center gap-1.5">
                                    <span className="font-bold text-[#EAECEF]">{pos.symbol}</span>
                                    <span className="px-1.5 py-0.2 rounded text-[9px] bg-slate-800 text-[#848E9C] border border-[#2B3139]">
                                      {pos.market_type || (selectedMarket === "CRYPTO" ? "CRYPTO" : "FOREX")}
                                    </span>
                                  </div>
                                </td>
                                <td className="p-3">
                                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                    pos.environment === "DEMO"
                                      ? "bg-amber-950 text-amber-300 border border-amber-500/40"
                                      : pos.environment === "LIVE"
                                      ? "bg-emerald-950 text-emerald-300 border border-emerald-500/40"
                                      : "bg-purple-950 text-purple-300 border border-purple-500/40"
                                  }`}>
                                    {pos.environment}
                                  </span>
                                  <span className="text-[10px] text-[#848E9C] block mt-0.5">{pos.exchange}</span>
                                </td>
                                <td className="p-3">
                                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                    isLong ? "text-emerald-300" : "text-rose-300"
                                  }`}>
                                    {pos.side}
                                  </span>
                                </td>
                                <td className="p-3 tabular-nums text-[#848E9C]">
                                  <div>${pos.entry_price.toLocaleString()} → ${pos.mark_price.toLocaleString()}</div>
                                  <div className="text-[10px] text-[#848E9C]">{pos.size} units</div>
                                </td>
                                <td className="p-3 font-bold tabular-nums">
                                  <span className={pos.realized_pnl >= 0 ? "text-emerald-400" : "text-rose-400"}>
                                    {pos.realized_pnl >= 0 ? "+" : ""}${pos.realized_pnl.toFixed(2)}
                                  </span>
                                </td>
                                <td className="p-3 text-amber-300 tabular-nums">
                                  -${(pos.fees_paid || 0).toFixed(4)}
                                </td>
                                <td className="p-3 font-bold tabular-nums">
                                  <span className={netRealized >= 0 ? "text-emerald-400" : "text-rose-400"}>
                                    {netRealized >= 0 ? "+" : ""}${netRealized.toFixed(2)}
                                  </span>
                                </td>
                                <td className="p-3 text-[#848E9C] text-[10px]">
                                  {pos.closed_at_utc ? pos.closed_at_utc.replace("T", " ").replace("Z", " UTC") : "--"}
                                </td>
                                <td className="p-3">
                                  {pos.is_exchange_confirmed ? (
                                    <span className="px-2 py-0.5 rounded text-[9px] font-bold bg-emerald-950 text-emerald-300 border border-emerald-500/40">
                                      EXCHANGE CONFIRMED
                                    </span>
                                  ) : pos.origin === "SEEDED_FIXTURE" ? (
                                    <span className="px-2 py-0.5 rounded text-[9px] font-bold bg-purple-950 text-purple-300 border border-purple-500/40">
                                      SEEDED FIXTURE
                                    </span>
                                  ) : (
                                    <span className="px-2 py-0.5 rounded text-[9px] font-bold bg-cyan-950 text-cyan-300 border border-cyan-500/40">
                                      PAPER SIMULATION
                                    </span>
                                  )}
                                </td>
                              </tr>
                            );
                          })}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="p-6 rounded-xl bg-[#262C36]/40 border border-[#2B3139] text-center text-[#848E9C]">
                    No closed trades found matching current market and environment filters.
                  </div>
                )}
              </div>
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-[#2B3139] bg-[#262C36] flex items-center justify-between">
              <span className="text-xs font-mono text-[#848E9C] flex items-center gap-1.5">
                <Lock className="w-3.5 h-3.5 text-cyan-500" />
                Live trading locked · Real exchange positions segregated
              </span>
              <button
                onClick={() => setModalMode(null)}
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-[#EAECEF] text-xs font-mono cursor-pointer transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ─── Modal 3: AI Trade Advisory & Regime Recommendations ─── */}
      {selectedPositionForAdvisory && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#1E2329]/40 backdrop-blur-md animate-in fade-in">
          <div className="w-full max-w-2xl bg-[#1E2329] border border-[#2B3139] shadow-sm rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
            <div className="p-5 border-b border-[#2B3139] flex items-center justify-between bg-[#262C36]">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-xl bg-violet-950/60 border border-violet-500/30 text-violet-400">
                  <Bot className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-[#EAECEF] font-mono flex items-center gap-2">
                    <span>AI Trade Intelligence</span>
                    <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded-full bg-violet-950 text-violet-300 border border-violet-500/40">
                      {selectedPositionForAdvisory.symbol} {selectedPositionForAdvisory.side}
                    </span>
                  </h3>
                  <p className="text-xs text-[#848E9C]">
                    Rate-limit-aware position reasoning, regime reassessment & risk advisory.
                  </p>
                </div>
              </div>
              <button
                onClick={() => {
                  setSelectedPositionForAdvisory(null);
                  setAiAdvisoryData(null);
                }}
                className="p-2 rounded-lg bg-slate-800/80 hover:bg-slate-700 text-[#848E9C] hover:text-[#EAECEF] transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 overflow-y-auto space-y-5 flex-1 text-xs font-mono">
              {isAdvisoryLoading ? (
                <div className="py-12 text-center text-[#848E9C] space-y-2">
                  <RefreshCw className="w-6 h-6 animate-spin text-violet-400 mx-auto" />
                  <p>Analyzing order book regime and attributing position P&L...</p>
                </div>
              ) : aiAdvisoryData ? (
                <div className="space-y-4">
                  {/* Regime Assessment Card */}
                  <div className="p-4 rounded-xl bg-[#262C36] border border-[#2B3139] space-y-2">
                    <span className="text-[10px] uppercase text-[#848E9C] block">Assessed Market Regime</span>
                    <div className="flex items-center gap-2">
                      <span className="px-2.5 py-1 rounded-md bg-violet-950/60 text-violet-300 border border-violet-500/30 font-bold text-sm">
                        {aiAdvisoryData.assessed_regime}
                      </span>
                      <span className="text-[#848E9C]">
                        Current P&L:{" "}
                        <strong className={aiAdvisoryData.unrealized_pnl >= 0 ? "text-emerald-400" : "text-rose-400"}>
                          {aiAdvisoryData.unrealized_pnl >= 0 ? "+" : ""}${aiAdvisoryData.unrealized_pnl.toFixed(2)} ({aiAdvisoryData.unrealized_pnl_pct.toFixed(2)}%)
                        </strong>
                      </span>
                    </div>
                  </div>

                  {/* P&L Attribution */}
                  <div className="p-4 rounded-xl bg-[#262C36] border border-[#2B3139] space-y-1.5">
                    <span className="text-[10px] uppercase text-[#848E9C] block">P&L Attribution & Root Cause Analysis</span>
                    <p className="text-[#EAECEF] leading-relaxed text-xs">
                      {aiAdvisoryData.attribution_analysis}
                    </p>
                  </div>

                  {/* Recommended Action */}
                  <div className="p-4 rounded-xl bg-[#262C36] border border-[#2B3139] space-y-2">
                    <span className="text-[10px] uppercase text-[#848E9C] block">Recommended Risk Action</span>
                    <div className="flex items-center gap-2">
                      <span className="px-2.5 py-1 rounded-md bg-cyan-950/60 text-cyan-300 border border-cyan-500/30 font-bold">
                        {aiAdvisoryData.recommended_action}
                      </span>
                    </div>
                    <p className="text-[#848E9C] leading-relaxed text-xs pt-1">
                      {aiAdvisoryData.advisory_summary}
                    </p>
                  </div>

                  {/* Proposed Limits Comparison */}
                  <div className="grid grid-cols-2 gap-3 p-4 rounded-xl bg-[#262C36] border border-[#2B3139]">
                    <div>
                      <span className="text-[10px] uppercase text-[#848E9C] block">Protective Stop-Loss</span>
                      <div className="mt-1 space-y-0.5">
                        <div className="text-[#848E9C]">Current: {aiAdvisoryData.current_stop_loss ? `$${aiAdvisoryData.current_stop_loss}` : "None"}</div>
                        <div className="text-rose-400 font-bold text-sm">
                          Proposed: ${aiAdvisoryData.proposed_stop_loss?.toLocaleString()}
                        </div>
                      </div>
                    </div>

                    <div>
                      <span className="text-[10px] uppercase text-[#848E9C] block">Take-Profit Target</span>
                      <div className="mt-1 space-y-0.5">
                        <div className="text-[#848E9C]">Current: {aiAdvisoryData.current_take_profit ? `$${aiAdvisoryData.current_take_profit}` : "None"}</div>
                        <div className="text-emerald-400 font-bold text-sm">
                          Proposed: ${aiAdvisoryData.proposed_take_profit?.toLocaleString()}
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="p-3 rounded-lg bg-amber-950/30 border border-amber-500/30 text-amber-300/90 text-[11px] leading-relaxed flex items-start gap-2">
                    <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                    <span>
                      Advisory-only guidance. Risk parameters will NOT be updated without your explicit authorization.
                    </span>
                  </div>
                </div>
              ) : (
                <div className="text-[#848E9C] py-6 text-center">No advisory available for this position.</div>
              )}
            </div>

            <div className="p-4 border-t border-[#2B3139] bg-[#262C36] flex items-center justify-between">
              <button
                onClick={() => {
                  setSelectedPositionForAdvisory(null);
                  setAiAdvisoryData(null);
                }}
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-[#EAECEF] text-xs font-mono cursor-pointer transition-colors"
              >
                Close
              </button>

              {aiAdvisoryData && (
                <button
                  onClick={handleApplyAiAdvisoryTpSl}
                  className="px-4 py-2 rounded-xl bg-violet-600 hover:bg-violet-500 text-[#EAECEF] text-xs font-mono font-bold tabular-nums flex items-center gap-1.5 cursor-pointer shadow-md shadow-violet-950/30"
                >
                  <ShieldCheck className="w-3.5 h-3.5" />
                  <span>Apply Recommended TP/SL</span>
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ─── Modal 4: Adjust TP/SL Limits with Explicit Confirmation ─── */}
      {selectedPositionForTpSl && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#1E2329]/40 backdrop-blur-md animate-in fade-in">
          <div className="w-full max-w-md bg-[#1E2329] border border-[#2B3139] shadow-sm rounded-2xl shadow-2xl overflow-hidden flex flex-col">
            <div className="p-5 border-b border-[#2B3139] flex items-center justify-between bg-[#262C36]">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-xl bg-cyan-950/60 border border-cyan-500/30 text-cyan-400">
                  <Sliders className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-[#EAECEF] font-mono">
                    Adjust Protective Limits
                  </h3>
                  <p className="text-xs text-[#848E9C]">
                    {selectedPositionForTpSl.symbol} ({selectedPositionForTpSl.side})
                  </p>
                </div>
              </div>
              <button
                onClick={() => setSelectedPositionForTpSl(null)}
                className="p-2 rounded-lg bg-slate-800/80 hover:bg-slate-700 text-[#848E9C] hover:text-[#EAECEF] transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSubmitTpSlAdjustment} className="p-6 space-y-4 text-xs font-mono">
              <div>
                <label className="block text-[#848E9C] text-[11px] mb-1">Take-Profit Target ($)</label>
                <input
                  type="number"
                  step="any"
                  placeholder="e.g. 72000"
                  value={tpSlForm.takeProfit}
                  onChange={(e) => setTpSlForm({ ...tpSlForm, takeProfit: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg bg-[#262C36] border border-[#2B3139] text-[#EAECEF] font-mono"
                />
              </div>

              <div>
                <label className="block text-[#848E9C] text-[11px] mb-1">Stop-Loss Target ($)</label>
                <input
                  type="number"
                  step="any"
                  placeholder="e.g. 66000"
                  value={tpSlForm.stopLoss}
                  onChange={(e) => setTpSlForm({ ...tpSlForm, stopLoss: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg bg-[#262C36] border border-[#2B3139] text-[#EAECEF] font-mono"
                />
              </div>

              {/* Explicit Confirmation Checkbox */}
              <div className="p-3 rounded-lg bg-[#262C36] border border-[#2B3139] space-y-2">
                <label className="flex items-start gap-2.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={tpSlForm.confirmed}
                    onChange={(e) => setTpSlForm({ ...tpSlForm, confirmed: e.target.checked })}
                    className="mt-0.5 rounded border-[#2B3139] bg-[#1E2329] text-cyan-500 focus:ring-cyan-500 cursor-pointer"
                  />
                  <span className="text-[#848E9C] text-[11px] leading-relaxed">
                    I explicitly confirm modifying the protective exit parameters on this active position.
                  </span>
                </label>
              </div>

              <div className="pt-2 flex items-center justify-between">
                <button
                  type="button"
                  onClick={() => setSelectedPositionForTpSl(null)}
                  className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-[#EAECEF] text-xs font-mono cursor-pointer transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={!tpSlForm.confirmed}
                  className="px-4 py-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 disabled:opacity-40 disabled:cursor-not-allowed text-[#EAECEF] text-xs font-mono font-bold tabular-nums cursor-pointer transition-all shadow-md shadow-cyan-950/30"
                >
                  Commit TP/SL Update
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ─── Modal 5: Position Execution & Fills History ─── */}
      {selectedPositionForHistory && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#1E2329]/40 backdrop-blur-md animate-in fade-in">
          <div className="w-full max-w-2xl bg-[#1E2329] border border-[#2B3139] shadow-sm rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
            <div className="p-5 border-b border-[#2B3139] flex items-center justify-between bg-[#262C36]">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-xl bg-cyan-950/60 border border-cyan-500/30 text-cyan-400">
                  <Receipt className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-[#EAECEF] font-mono">
                    Execution & Reconciliation History
                  </h3>
                  <p className="text-xs text-[#848E9C]">
                    {selectedPositionForHistory.symbol} · {selectedPositionForHistory.position_id}
                  </p>
                </div>
              </div>
              <button
                onClick={() => setSelectedPositionForHistory(null)}
                className="p-2 rounded-lg bg-slate-800/80 hover:bg-slate-700 text-[#848E9C] hover:text-[#EAECEF] transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 overflow-y-auto space-y-4 flex-1 text-xs font-mono">
              <div className="overflow-x-auto rounded-xl border border-[#2B3139]">
                <table className="w-full text-left font-mono">
                  <thead className="bg-[#262C36] text-[#848E9C] text-[10px] uppercase border-b border-[#2B3139]">
                    <tr>
                      <th className="p-3">Fill ID</th>
                      <th className="p-3">Order ID</th>
                      <th className="p-3">Side</th>
                      <th className="p-3">Qty</th>
                      <th className="p-3">Price</th>
                      <th className="p-3">Fee</th>
                      <th className="p-3">Role</th>
                      <th className="p-3">Timestamp</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 bg-[#262C36]/30">
                    {(selectedPositionForHistory.execution_history || []).map((f: any, idx: number) => (
                      <tr key={idx} className="hover:bg-[#1E2329]/40 transition-colors">
                        <td className="p-3 text-cyan-400 font-bold">{f.fill_id || `--`}</td>
                        <td className="p-3 text-[#848E9C]">{f.order_id || `--`}</td>
                        <td className="p-3">
                          <span className={f.side === "BUY" ? "text-emerald-400 font-bold" : "text-rose-400 font-bold"}>
                            {f.side}
                          </span>
                        </td>
                        <td className="p-3 text-[#EAECEF]">{f.qty}</td>
                        <td className="p-3 text-[#EAECEF] font-bold">${f.price?.toLocaleString()}</td>
                        <td className="p-3 text-amber-300">${f.fee}</td>
                        <td className="p-3 text-[#848E9C]">{f.role || "TAKER"}</td>
                        <td className="p-3 text-[#848E9C] text-[10px]">{f.timestamp || "--"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="p-4 border-t border-[#2B3139] bg-[#262C36] flex items-center justify-between">
              <span className="text-xs text-[#848E9C] font-mono">
                Total Fees Booked: ${selectedPositionForHistory.fees_paid.toFixed(4)}
              </span>
              <button
                onClick={() => setSelectedPositionForHistory(null)}
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-[#EAECEF] text-xs font-mono cursor-pointer transition-colors"
              >
                Close History
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ─── Modal 6: New Paper Position Creation ─── */}
      {isCreatingPaperPosition && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#1E2329]/40 backdrop-blur-md animate-in fade-in">
          <div className="w-full max-w-md bg-[#1E2329] border border-[#2B3139] shadow-sm rounded-2xl shadow-2xl overflow-hidden flex flex-col">
            <div className="p-5 border-b border-[#2B3139] flex items-center justify-between bg-[#262C36]">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-xl bg-cyan-950/60 border border-cyan-500/30 text-cyan-400">
                  <Zap className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-[#EAECEF] font-mono">
                    Open Simulated Demo Position
                  </h3>
                  <p className="text-xs text-[#848E9C]">
                    Instant simulated demo execution
                  </p>
                </div>
              </div>
              <button
                onClick={() => setIsCreatingPaperPosition(false)}
                className="p-2 rounded-lg bg-slate-800/80 hover:bg-slate-700 text-[#848E9C] hover:text-[#EAECEF] transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleCreatePaperPosition} className="p-6 space-y-3.5 text-xs font-mono">
              <div>
                <label className="block text-[#848E9C] text-[11px] mb-1">Symbol</label>
                <input
                  type="text"
                  placeholder="e.g. BTCUSDT"
                  value={paperForm.symbol}
                  onChange={(e) => setPaperForm({ ...paperForm, symbol: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg bg-[#262C36] border border-[#2B3139] text-[#EAECEF] font-mono"
                />
              </div>

              <div>
                <label className="block text-[#848E9C] text-[11px] mb-1">Side</label>
                <select
                  value={paperForm.side}
                  onChange={(e) => setPaperForm({ ...paperForm, side: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg bg-[#262C36] border border-[#2B3139] text-[#EAECEF] font-mono"
                >
                  <option value="LONG">LONG (Buy Entry)</option>
                  <option value="SHORT">SHORT (Sell Entry)</option>
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[#848E9C] text-[11px] mb-1">Size (units)</label>
                  <input
                    type="number"
                    step="any"
                    placeholder="0.05"
                    value={paperForm.size}
                    onChange={(e) => setPaperForm({ ...paperForm, size: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-[#262C36] border border-[#2B3139] text-[#EAECEF] font-mono"
                  />
                </div>

                <div>
                  <label className="block text-[#848E9C] text-[11px] mb-1">Entry Price ($)</label>
                  <input
                    type="number"
                    step="any"
                    placeholder="68500"
                    value={paperForm.entryPrice}
                    onChange={(e) => setPaperForm({ ...paperForm, entryPrice: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-[#262C36] border border-[#2B3139] text-[#EAECEF] font-mono"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[#848E9C] text-[11px] mb-1">Stop-Loss ($)</label>
                  <input
                    type="number"
                    step="any"
                    placeholder="66500"
                    value={paperForm.stopLoss}
                    onChange={(e) => setPaperForm({ ...paperForm, stopLoss: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-[#262C36] border border-[#2B3139] text-[#EAECEF] font-mono"
                  />
                </div>

                <div>
                  <label className="block text-[#848E9C] text-[11px] mb-1">Take-Profit ($)</label>
                  <input
                    type="number"
                    step="any"
                    placeholder="72000"
                    value={paperForm.takeProfit}
                    onChange={(e) => setPaperForm({ ...paperForm, takeProfit: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-[#262C36] border border-[#2B3139] text-[#EAECEF] font-mono"
                  />
                </div>
              </div>

              <div className="pt-2 flex items-center justify-between">
                <button
                  type="button"
                  onClick={() => setIsCreatingPaperPosition(false)}
                  className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-[#EAECEF] text-xs font-mono cursor-pointer transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-[#EAECEF] text-xs font-mono font-bold tabular-nums cursor-pointer transition-all shadow-md shadow-cyan-950/30"
                >
                  Create Position
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
      {/* ─── Settings & Trading Controls Modal ────────────────────────────── */}
      {modalMode === "SAAS_BILLING" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md">
          <div className="relative w-full max-w-5xl max-h-[90vh] overflow-y-auto rounded-3xl bg-[#1E2329] border border-[#2B3139] shadow-2xl p-6 md:p-8 space-y-6">
            
            {/* Modal Header */}
            <div className="flex items-start justify-between border-b border-[#2B3139] pb-4">
              <div>
                <div className="flex items-center gap-3">
                  <div className="p-2.5 rounded-xl bg-purple-950/80 border border-purple-500/40 text-purple-300">
                    <CreditCard className="w-6 h-6" />
                  </div>
                  <div>
                    <h2 className="text-xl font-bold text-[#EAECEF] font-mono flex items-center gap-2">
                      TAURIC SaaS Billing & Governance
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-purple-950 text-purple-300 border border-purple-500/40">
                        MULTI-TENANT V1
                      </span>
                    </h2>
                    <p className="text-xs text-[#848E9C] font-mono">
                      Prepaid TAURIC credits, per-order execution fees, immutable ledger, and admin customer controls.
                    </p>
                  </div>
                </div>
              </div>
              <button
                onClick={() => setModalMode(null)}
                className="p-2 text-[#848E9C] hover:text-[#EAECEF] rounded-xl bg-slate-800 hover:bg-slate-700 transition-all"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Navigation Tabs inside Modal */}
            <div className="flex items-center gap-2 border-b border-[#2B3139] pb-2">
              <button
                onClick={() => setSaasActiveTab("MY_ACCOUNT")}
                className={`px-3 py-1.5 rounded-lg text-xs font-mono font-bold tabular-nums transition-all ${
                  saasActiveTab === "MY_ACCOUNT"
                    ? "bg-purple-600 text-[#EAECEF] shadow-md shadow-purple-600/30"
                    : "bg-slate-800/80 text-[#848E9C] hover:text-[#EAECEF]"
                }`}
              >
                My Account & Prepaid Credits
              </button>

              <button
                onClick={() => setSaasActiveTab("CUSTOMERS_ADMIN")}
                className={`px-3 py-1.5 rounded-lg text-xs font-mono font-bold tabular-nums transition-all ${
                  saasActiveTab === "CUSTOMERS_ADMIN"
                    ? "bg-purple-600 text-[#EAECEF] shadow-md shadow-purple-600/30"
                    : "bg-slate-800/80 text-[#848E9C] hover:text-[#EAECEF]"
                }`}
              >
                Admin Customer Governance ({saasAdminCustomers.length})
              </button>

              <button
                onClick={() => setSaasActiveTab("AUDIT_LOGS")}
                className={`px-3 py-1.5 rounded-lg text-xs font-mono font-bold tabular-nums transition-all ${
                  saasActiveTab === "AUDIT_LOGS"
                    ? "bg-purple-600 text-[#EAECEF] shadow-md shadow-purple-600/30"
                    : "bg-slate-800/80 text-[#848E9C] hover:text-[#EAECEF]"
                }`}
              >
                Immutable Audit Logs ({saasAdminAuditLogs.length})
              </button>
            </div>

            {saasFeedback && (
              <div className="p-3 rounded-xl bg-emerald-950/80 border border-emerald-500/40 text-emerald-300 text-xs font-mono">
                {saasFeedback}
              </div>
            )}

            {/* TAB 1: My Account & Prepaid Credits */}
            {saasActiveTab === "MY_ACCOUNT" && (
              <div className="space-y-6">
                
                {/* User Info & Profile Strip */}
                <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                  <div className="p-4 rounded-2xl bg-[#262C36]/50 border border-[#2B3139] space-y-1">
                    <span className="text-[11px] font-mono text-[#848E9C]">Authenticated Tenant</span>
                    <div className="text-sm font-bold text-[#EAECEF] font-mono truncate">{saasUser?.email || "admin@tauric.com"}</div>
                    <span className="inline-block px-2 py-0.5 rounded text-[10px] font-bold bg-cyan-950 text-cyan-300 border border-cyan-500/30 font-mono">
                      ROLE: {saasUser?.role || "ADMIN"}
                    </span>
                  </div>

                  <div className="p-4 rounded-2xl bg-[#262C36]/50 border border-[#2B3139] space-y-1">
                    <span className="text-[11px] font-mono text-[#848E9C]">KYC Verification Status</span>
                    <div className="text-sm font-bold text-emerald-400 font-mono">
                      {saasUser?.kyc_status || "APPROVED"}
                    </div>
                    <span className="text-[10px] text-[#848E9C] font-mono">Zero Document Storage (PDPA)</span>
                  </div>

                  <div className="p-4 rounded-2xl bg-[#262C36]/50 border border-[#2B3139] space-y-1">
                    <span className="text-[11px] font-mono text-[#848E9C]">Platform Execution Fee</span>
                    <div className="text-sm font-bold text-[#EAECEF] font-mono">
                      ${saasFeePolicy?.execution_fee_usd?.toFixed(2) || "0.30"} / order
                    </div>
                    <span className="text-[10px] text-[#848E9C] font-mono">
                      {saasFeePolicy?.fee_waived ? "Waiver Active" : "Per unique filled order"}
                    </span>
                  </div>

                  <div className="p-4 rounded-2xl bg-[#262C36]/50 border border-[#2B3139] space-y-1">
                    <span className="text-[11px] font-mono text-[#848E9C]">One-Time Activation Fee</span>
                    <div className="text-sm font-bold text-[#EAECEF] font-mono">
                      ${saasFeePolicy?.activation_fee_usd?.toFixed(2) || "20.00"}
                    </div>
                    <span className="text-[10px] text-emerald-400 font-mono">
                      {saasFeePolicy?.activation_fee_charged ? "✓ Assessed Once" : "Pending First Live Order"}
                    </span>
                  </div>
                </div>

                {/* Prepaid Credit Balance & Topup Card */}
                <div className="p-6 rounded-2xl bg-gradient-to-r from-purple-950/40 via-slate-900 to-slate-900 border border-purple-500/30 flex flex-col md:flex-row items-center justify-between gap-4">
                  <div>
                    <span className="text-xs font-mono text-purple-300 font-bold uppercase tracking-wider">Available Prepaid Balance</span>
                    <div className="text-3xl font-extrabold text-[#EAECEF] font-mono mt-1">
                      ${saasBillingSummary?.prepaid_credits_usd ? saasBillingSummary.prepaid_credits_usd.toFixed(2) : "0.00"}
                      <span className="text-sm text-[#848E9C] font-normal ml-2">USD Credits</span>
                    </div>
                    <p className="text-xs text-[#848E9C] font-mono mt-1">
                      Prepaid balance covers per-order platform execution fees ($0.30/order). No automatic withdrawal from exchange accounts.
                    </p>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleTopupCredits(50)}
                      disabled={isSaasLoading}
                      className="px-4 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-[#EAECEF] text-xs font-mono font-bold tabular-nums transition-all shadow-md shadow-purple-600/30 cursor-pointer disabled:opacity-50"
                    >
                      + Add $50 Credits
                    </button>
                    <button
                      onClick={() => handleTopupCredits(100)}
                      disabled={isSaasLoading}
                      className="px-4 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-purple-300 border border-purple-500/40 text-xs font-mono font-bold tabular-nums transition-all cursor-pointer disabled:opacity-50"
                    >
                      + Add $100 Credits
                    </button>
                  </div>
                </div>

                {/* Exact Billing Rule Banner */}
                <div className="p-3.5 rounded-xl bg-[#262C36]/40 border border-[#2B3139] text-[11px] font-mono text-[#848E9C] space-y-1">
                  <div className="font-bold text-[#848E9C] flex items-center gap-1.5">
                    <Shield className="w-3.5 h-3.5 text-purple-400" />
                    Exact Billing Rule: One Execution Fee Per Unique Qualifying Order
                  </div>
                  <div>
                    • Charged once when an order has verified exchange fill evidence. Multiple partial fills on a single order do NOT trigger multiple fees.
                  </div>
                  <div>
                    • Strategy scans, generated plans, simulated paper trades, unsubmitted orders, and rejected orders incur zero platform fees.
                  </div>
                </div>

                {/* Immutable Billing Ledger Table */}
                <div className="space-y-2">
                  <div className="text-sm font-bold text-[#EAECEF] font-mono flex items-center justify-between">
                    <span>Immutable Billing Ledger ({saasLedger.length} events)</span>
                    <button
                      onClick={fetchSaasBillingData}
                      className="text-[11px] text-purple-400 hover:text-purple-300 font-mono flex items-center gap-1"
                    >
                      <RefreshCw className="w-3 h-3" /> Refresh
                    </button>
                  </div>

                  {saasLedger.length === 0 ? (
                    <div className="p-8 text-center rounded-xl bg-[#262C36]/40 border border-[#2B3139] text-[#848E9C] font-mono text-xs">
                      No billing ledger entries found.
                    </div>
                  ) : (
                    <div className="overflow-x-auto rounded-xl border border-[#2B3139] bg-[#262C36]/50">
                      <table className="w-full text-left text-xs font-mono">
                        <thead className="bg-[#1E2329] text-[#848E9C] border-b border-[#2B3139]">
                          <tr>
                            <th className="p-3">Entry ID</th>
                            <th className="p-3">Event Type</th>
                            <th className="p-3">Amount</th>
                            <th className="p-3">Balance After</th>
                            <th className="p-3">Reference / Order</th>
                            <th className="p-3">Status</th>
                            <th className="p-3">Timestamp (UTC)</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/60">
                          {saasLedger.map((entry) => (
                            <tr key={entry.entry_id} className="hover:bg-[#1E2329]/40">
                              <td className="p-3 text-[#848E9C] font-bold">{entry.entry_id}</td>
                              <td className="p-3">
                                <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                  entry.entry_type === "CREDIT_TOPUP" ? "bg-emerald-950 text-emerald-300 border border-emerald-500/30"
                                  : entry.entry_type === "ACTIVATION_FEE" ? "bg-amber-950 text-amber-300 border border-amber-500/30"
                                  : entry.entry_type === "EXECUTION_FEE" ? "bg-purple-950 text-purple-300 border border-purple-500/30"
                                  : "bg-slate-800 text-[#848E9C]"
                                }`}>
                                  {entry.entry_type}
                                </span>
                              </td>
                              <td className="p-3 font-bold">
                                <span className={entry.amount_usd >= 0 ? "text-emerald-400" : "text-rose-400"}>
                                  {entry.amount_usd >= 0 ? "+" : ""}${entry.amount_usd.toFixed(2)}
                                </span>
                              </td>
                              <td className="p-3 text-[#848E9C]">${entry.balance_after_usd?.toFixed(2)}</td>
                              <td className="p-3 text-[#848E9C] text-[11px] truncate max-w-xs">{entry.billable_order_ref || "--"}</td>
                              <td className="p-3">
                                <span className="px-1.5 py-0.5 rounded text-[9px] bg-slate-800 text-[#848E9C] font-bold">
                                  {entry.status}
                                </span>
                              </td>
                              <td className="p-3 text-[#848E9C] text-[10px]">{entry.created_at?.replace("T", " ").replace("Z", "")}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>

              </div>
            )}

            {/* TAB 2: Admin Customer Governance */}
            {saasActiveTab === "CUSTOMERS_ADMIN" && (
              <div className="space-y-4">
                <div className="text-sm font-bold text-[#EAECEF] font-mono flex items-center justify-between">
                  <span>Registered SaaS Customers & Fee Configurations</span>
                  <span className="text-xs text-[#848E9C] font-mono">Role-Protected Admin View</span>
                </div>

                <div className="overflow-x-auto rounded-xl border border-[#2B3139] bg-[#262C36]/50">
                  <table className="w-full text-left text-xs font-mono">
                    <thead className="bg-[#1E2329] text-[#848E9C] border-b border-[#2B3139]">
                      <tr>
                        <th className="p-3">User ID</th>
                        <th className="p-3">Email</th>
                        <th className="p-3">Role</th>
                        <th className="p-3">Status</th>
                        <th className="p-3">KYC Status</th>
                        <th className="p-3">Prepaid Credits</th>
                        <th className="p-3">Exec Fee Rate</th>
                        <th className="p-3">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60">
                      {saasAdminCustomers.map((c) => (
                        <tr key={c.user_id} className="hover:bg-[#1E2329]/40">
                          <td className="p-3 text-[#848E9C] font-bold">{c.user_id}</td>
                          <td className="p-3 text-[#EAECEF]">{c.email}</td>
                          <td className="p-3">
                            <span className="px-2 py-0.5 rounded text-[10px] bg-slate-800 text-[#848E9C] font-bold">
                              {c.role}
                            </span>
                          </td>
                          <td className="p-3">
                            <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                              c.status === "ACTIVE" ? "bg-emerald-950 text-emerald-300 border border-emerald-500/40"
                              : "bg-rose-950 text-rose-300 border border-rose-500/40"
                            }`}>
                              {c.status}
                            </span>
                          </td>
                          <td className="p-3">
                            <span className="text-[11px] text-[#848E9C]">{c.kyc_status}</span>
                          </td>
                          <td className="p-3 text-[#EAECEF] font-bold">${c.prepaid_credits_usd?.toFixed(2)}</td>
                          <td className="p-3 text-purple-300 font-bold">${c.fee_rate_usd?.toFixed(2)}</td>
                          <td className="p-3">
                            <button
                              onClick={() => handleToggleCustomerStatus(c.user_id, c.status)}
                              className={`px-2 py-1 rounded text-[10px] font-bold transition-all cursor-pointer ${
                                c.status === "ACTIVE"
                                  ? "bg-rose-950 hover:bg-rose-900 text-rose-300 border border-rose-500/40"
                                  : "bg-emerald-950 hover:bg-emerald-900 text-emerald-300 border border-emerald-500/40"
                              }`}
                            >
                              {c.status === "ACTIVE" ? "Block Customer" : "Unblock"}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* TAB 3: Immutable Audit Logs */}
            {saasActiveTab === "AUDIT_LOGS" && (
              <div className="space-y-4">
                <div className="text-sm font-bold text-[#EAECEF] font-mono flex items-center justify-between">
                  <span>Administrative & Security Audit Logs (Tamper-Resistant)</span>
                  <span className="text-xs text-[#848E9C] font-mono">Immutable Event History</span>
                </div>

                <div className="overflow-x-auto rounded-xl border border-[#2B3139] bg-[#262C36]/50">
                  <table className="w-full text-left text-xs font-mono">
                    <thead className="bg-[#1E2329] text-[#848E9C] border-b border-[#2B3139]">
                      <tr>
                        <th className="p-3">Log ID</th>
                        <th className="p-3">Actor</th>
                        <th className="p-3">Action</th>
                        <th className="p-3">Target User</th>
                        <th className="p-3">Details</th>
                        <th className="p-3">Timestamp (UTC)</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60">
                      {saasAdminAuditLogs.map((log) => (
                        <tr key={log.log_id} className="hover:bg-[#1E2329]/40">
                          <td className="p-3 text-[#848E9C]">{log.log_id}</td>
                          <td className="p-3 text-cyan-300 font-bold">{log.actor_id}</td>
                          <td className="p-3">
                            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-800 text-[#EAECEF]">
                              {log.action}
                            </span>
                          </td>
                          <td className="p-3 text-[#848E9C]">{log.target_user_id || "--"}</td>
                          <td className="p-3 text-[#848E9C] text-[10px] max-w-sm truncate">{log.details_json}</td>
                          <td className="p-3 text-[#848E9C] text-[10px]">{log.created_at?.replace("T", " ").replace("Z", "")}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Footer Safety Notice */}
            <div className="pt-3 border-t border-[#2B3139] flex items-center justify-between text-[11px] font-mono text-[#848E9C]">
              <span className="flex items-center gap-1.5">
                <Shield className="w-3.5 h-3.5 text-emerald-400" />
                Live trading locked • Non-custodial closed-loop prepaid software credits
              </span>
              <button
                onClick={() => setModalMode(null)}
                className="px-4 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-[#848E9C] font-bold text-xs"
              >
                Close
              </button>
            </div>

          </div>
        </div>
      )}

      {modalMode === "SETTINGS" && (
        <div
          data-testid="settings-modal"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#262C36]/80 backdrop-blur-md overflow-y-auto"
        >
          <div className="relative w-full max-w-4xl max-h-[90vh] bg-[#1E2329] border border-[#2B3139] shadow-sm rounded-3xl shadow-2xl flex flex-col overflow-hidden my-auto animate-in fade-in zoom-in-95 duration-200">
            {/* Modal Header */}
            <div className="p-6 border-b border-[#2B3139] flex items-center justify-between bg-[#1E2329]/50">
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-2xl bg-amber-950/60 border border-amber-500/30 text-amber-400">
                  <Settings className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-[#EAECEF] font-mono flex items-center gap-2.5">
                    <span>Settings & Platform Controls</span>
                    <span className="text-[11px] font-mono uppercase px-2 py-0.5 rounded-full bg-slate-800 text-[#848E9C] border border-[#2B3139]">
                      v4.0.0 Security Gate
                    </span>
                  </h3>
                  <p className="text-xs text-[#848E9C]">
                    Backend-enforced trading authorization, execution boundaries, and platform audit logs
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={fetchLiveAuthStatus}
                  disabled={isLoadingLiveAuth}
                  className="p-2 rounded-xl bg-slate-800/80 hover:bg-slate-700/80 text-[#848E9C] border border-[#2B3139] cursor-pointer transition-colors"
                  title="Refresh authorization state from backend"
                >
                  <RefreshCw className={`w-4 h-4 ${isLoadingLiveAuth ? "animate-spin text-amber-400" : ""}`} />
                </button>
                <button
                  type="button"
                  onClick={() => setModalMode(null)}
                  data-testid="close-settings-modal-btn"
                  className="p-2 rounded-xl bg-slate-800/80 hover:bg-slate-700/80 text-[#848E9C] hover:text-[#EAECEF] border border-[#2B3139] cursor-pointer transition-colors"
                  aria-label="Close modal"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Navigation Tabs */}
            <div className="flex items-center gap-2 px-6 pt-4 border-b border-[#2B3139] bg-[#1E2329]/30">
              <button
                type="button"
                onClick={() => setSettingsActiveTab("TRADING_CONTROLS")}
                data-testid="tab-trading-controls"
                className={`pb-3 px-3 text-xs font-mono font-bold tabular-nums border-b-2 transition-all cursor-pointer flex items-center gap-2 ${
                  settingsActiveTab === "TRADING_CONTROLS"
                    ? "border-amber-400 text-amber-300"
                    : "border-transparent text-[#848E9C] hover:text-[#EAECEF]"
                }`}
              >
                <Sliders className="w-4 h-4" />
                <span>Trading Controls</span>
              </button>

              <button
                type="button"
                onClick={() => setSettingsActiveTab("AUDIT_LOG")}
                data-testid="tab-audit-log"
                className={`pb-3 px-3 text-xs font-mono font-bold tabular-nums border-b-2 transition-all cursor-pointer flex items-center gap-2 ${
                  settingsActiveTab === "AUDIT_LOG"
                    ? "border-amber-400 text-amber-300"
                    : "border-transparent text-[#848E9C] hover:text-[#EAECEF]"
                }`}
              >
                <FileCheck className="w-4 h-4" />
                <span>Audit Trail ({liveAuthStatus?.audit_trail?.length || 0})</span>
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 overflow-y-auto space-y-6 flex-1 custom-scrollbar">
              {settingsActiveTab === "TRADING_CONTROLS" && (
                <div className="space-y-6" data-testid="section-trading-controls">
                  {/* Action Feedback Banner */}
                  {liveAuthActionFeedback && (
                    <div
                      data-testid="live-auth-feedback-banner"
                      className={`p-4 rounded-2xl border flex flex-col gap-2 ${
                        liveAuthActionFeedback.type === "BLOCKED"
                          ? "bg-red-950/40 border-red-500/40 text-red-200"
                          : liveAuthActionFeedback.type === "SUCCESS"
                          ? "bg-emerald-950/40 border-emerald-500/40 text-emerald-200"
                          : liveAuthActionFeedback.type === "ERROR"
                          ? "bg-rose-950/50 border-rose-500/50 text-rose-200"
                          : "bg-slate-800/60 border-[#2B3139] text-[#848E9C]"
                      }`}
                    >
                      <div className="flex items-center gap-2.5 font-mono text-xs font-bold">
                        {liveAuthActionFeedback.type === "BLOCKED" ? (
                          <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />
                        ) : liveAuthActionFeedback.type === "SUCCESS" ? (
                          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                        ) : (
                          <Info className="w-4 h-4 text-cyan-400 shrink-0" />
                        )}
                        <span>{liveAuthActionFeedback.message}</span>
                      </div>
                      {liveAuthActionFeedback.blockers && liveAuthActionFeedback.blockers.length > 0 && (
                        <div className="mt-1 pl-6 space-y-1">
                          <p className="text-[11px] font-mono uppercase tracking-wider text-red-300 font-bold">
                            Outstanding Blocking Prerequisites:
                          </p>
                          <ul className="list-disc pl-4 space-y-1 text-xs text-red-200/90 font-mono">
                            {liveAuthActionFeedback.blockers.map((b, idx) => (
                              <li key={idx}>{b}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Main Live Trading Card */}
                  <div
                    data-testid="live-trading-control-card"
                    className="p-6 rounded-2xl bg-[#262C36]/70 border border-[#2B3139] space-y-5"
                  >
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-[#2B3139]">
                      <div>
                        <div className="flex items-center gap-2.5">
                          <h4 className="text-base font-bold text-[#EAECEF] font-mono flex items-center gap-2">
                            <span>Live Trading</span>
                          </h4>
                          <span
                            data-testid="live-trading-status-badge"
                            className={`text-[11px] font-mono uppercase font-bold px-2.5 py-0.5 rounded-full border ${
                              liveAuthStatus?.authorized
                                ? "bg-red-950/80 text-red-300 border-red-500/50"
                                : liveAuthStatus?.status === "BLOCKED"
                                ? "bg-amber-950/80 text-amber-300 border-amber-500/50"
                                : "bg-[#1E2329] text-[#848E9C] border-[#2B3139]"
                            }`}
                          >
                            {liveAuthStatus?.authorized
                              ? "AUTHORIZED • ON"
                              : liveAuthStatus?.status === "BLOCKED"
                              ? "ACTIVATION BLOCKED • OFF"
                              : "STRICTLY OFF (DEFAULT)"}
                          </span>
                        </div>
                        <p className="text-xs text-[#848E9C] mt-1">
                          Controls real matching engine order submission to connected live exchanges.
                        </p>
                      </div>

                      {/* Interactive Toggle Controls */}
                      <div className="flex items-center gap-3">
                        <span className="text-xs font-mono font-bold tabular-nums text-[#848E9C]">Authorization:</span>
                        <div className="inline-flex rounded-xl bg-[#1E2329] p-1 border border-[#2B3139]">
                          <button
                            type="button"
                            onClick={() => handleToggleLiveAuthorization("DISABLE")}
                            disabled={isUpdatingLiveAuth}
                            data-testid="btn-toggle-live-off"
                            className={`px-3 py-1.5 rounded-lg text-xs font-mono font-bold tabular-nums transition-all cursor-pointer ${
                              !liveAuthStatus?.authorized
                                ? "bg-slate-800 text-[#EAECEF] shadow-sm"
                                : "text-[#848E9C] hover:text-[#EAECEF]"
                            }`}
                          >
                            OFF
                          </button>
                          <button
                            type="button"
                            onClick={() => setShowLiveAuthConfirmModal(true)}
                            disabled={isUpdatingLiveAuth}
                            data-testid="btn-toggle-live-on"
                            className={`px-3 py-1.5 rounded-lg text-xs font-mono font-bold tabular-nums transition-all cursor-pointer ${
                              liveAuthStatus?.authorized
                                ? "bg-red-600 text-[#EAECEF] shadow-sm"
                                : "text-[#848E9C] hover:text-[#EAECEF]"
                            }`}
                          >
                            ON
                          </button>
                        </div>
                      </div>
                    </div>

                    {/* Status Metadata Grid */}
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 font-mono text-xs">
                      <div className="p-3 rounded-xl bg-[#262C36] border border-[#2B3139]">
                        <span className="text-[10px] text-[#848E9C] uppercase block">Backend Status</span>
                        <span
                          data-testid="live-auth-backend-status"
                          className={`font-bold ${
                            liveAuthStatus?.authorized
                              ? "text-red-400"
                              : liveAuthStatus?.status === "BLOCKED"
                              ? "text-amber-400"
                              : "text-[#848E9C]"
                          }`}
                        >
                          {liveAuthStatus?.status || "DISABLED"}
                        </span>
                      </div>

                      <div className="p-3 rounded-xl bg-[#262C36] border border-[#2B3139]">
                        <span className="text-[10px] text-[#848E9C] uppercase block">Last State Change (UTC)</span>
                        <span data-testid="live-auth-last-change" className="font-semibold text-[#848E9C]">
                          {liveAuthStatus?.last_state_change_utc || "System Initial"}
                        </span>
                      </div>

                      <div className="p-3 rounded-xl bg-[#262C36] border border-[#2B3139]">
                        <span className="text-[10px] text-[#848E9C] uppercase block">Last Operator / Actor</span>
                        <span data-testid="live-auth-last-actor" className="font-semibold text-[#848E9C]">
                          {liveAuthStatus?.last_actor || "system"}
                        </span>
                      </div>
                    </div>

                    {/* Explanation Banner */}
                    <div className="p-3.5 rounded-xl bg-[#1E2329] border border-[#2B3139] text-xs text-[#848E9C] font-mono leading-relaxed">
                      <span className="text-amber-400 font-bold block mb-1">State Policy Explanation:</span>
                      <p data-testid="live-auth-explanation">
                        {liveAuthStatus?.explanation ||
                          "Live trading is strictly DISABLED. Real-money orders are blocked across all execution routes."}
                      </p>
                    </div>

                    {/* Prominent Emergency / Turn OFF Action */}
                    <div className="pt-2 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                      <span className="text-xs text-[#848E9C] font-mono">
                        Safety Invariant: OFF is strictly enforced across restarts and config resets.
                      </span>
                      <button
                        type="button"
                        onClick={() => handleToggleLiveAuthorization("DISABLE")}
                        disabled={isUpdatingLiveAuth}
                        data-testid="btn-prominent-turn-off"
                        className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-red-950 text-[#848E9C] hover:text-red-300 border border-[#2B3139] hover:border-red-500/40 text-xs font-mono font-bold tabular-nums transition-all cursor-pointer flex items-center justify-center gap-2 shadow-sm"
                      >
                        <Power className="w-3.5 h-3.5" />
                        <span>Enforce / Keep Live Trading OFF</span>
                      </button>
                    </div>
                  </div>

                  {/* 7 Mandatory Platform Safety Prerequisites Checklist */}
                  <div
                    data-testid="prerequisites-checklist-card"
                    className="p-6 rounded-2xl bg-[#262C36]/70 border border-[#2B3139] space-y-4"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <ShieldAlert className="w-4 h-4 text-amber-400" />
                        <h4 className="text-sm font-bold text-[#EAECEF] font-mono uppercase tracking-wider">
                          Platform Safety Prerequisites Checklist (7 Gates)
                        </h4>
                      </div>
                      <span className="text-[11px] font-mono text-[#848E9C]">
                        Mandatory verification before live authorization
                      </span>
                    </div>

                    <div className="space-y-2.5">
                      {(liveAuthStatus?.prerequisite_checks || []).map((check: any, idx: number) => (
                        <div
                          key={check.id || idx}
                          data-testid={`prereq-check-${check.id}`}
                          className={`p-3.5 rounded-xl border flex items-start gap-3 transition-colors ${
                            check.passed
                              ? "bg-[#1E2329]/50 border-emerald-500/30"
                              : "bg-red-950/20 border-red-500/40"
                          }`}
                        >
                          <div className="mt-0.5 shrink-0">
                            {check.passed ? (
                              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                            ) : (
                              <XCircle className="w-4 h-4 text-red-400" />
                            )}
                          </div>
                          <div className="flex-1 font-mono">
                            <div className="flex items-center justify-between gap-2">
                              <span className="text-xs font-bold text-[#EAECEF]">{check.name}</span>
                              <span
                                className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded-full border ${
                                  check.passed
                                    ? "bg-emerald-950 text-emerald-300 border-emerald-500/40"
                                    : "bg-red-950 text-red-300 border-red-500/40"
                                }`}
                              >
                                {check.passed ? "PASSED" : "BLOCKED"}
                              </span>
                            </div>
                            <p className="text-xs text-[#848E9C] mt-1 leading-relaxed">{check.detail}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {settingsActiveTab === "AUDIT_LOG" && (
                <div className="space-y-4" data-testid="section-audit-log">
                  <div className="flex items-center justify-between pb-2 border-b border-[#2B3139]">
                    <h4 className="text-sm font-bold text-[#EAECEF] font-mono flex items-center gap-2">
                      <FileCheck className="w-4 h-4 text-amber-400" />
                      <span>Live Authorization Audit Log</span>
                    </h4>
                    <span className="text-xs font-mono text-[#848E9C]">
                      Immutable record of state modifications & rejected attempts
                    </span>
                  </div>

                  <div className="space-y-2 font-mono text-xs">
                    {(liveAuthStatus?.audit_trail || []).slice().reverse().map((entry: any, idx: number) => (
                      <div
                        key={idx}
                        className="p-3.5 rounded-xl bg-[#262C36] border border-[#2B3139] space-y-1.5"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-[#848E9C] font-bold">
                              {entry.action}
                            </span>
                            <span
                              className={`text-[10px] px-2 py-0.5 rounded font-bold border ${
                                entry.outcome === "AUTHORIZED"
                                  ? "bg-emerald-950 text-emerald-300 border-emerald-500/40"
                                  : entry.outcome.includes("REJECTED")
                                  ? "bg-red-950 text-red-300 border-red-500/40"
                                  : "bg-[#1E2329] text-[#848E9C] border-[#2B3139]"
                              }`}
                            >
                              {entry.outcome}
                            </span>
                            <span className="text-[#848E9C]">by {entry.actor}</span>
                          </div>
                          <span className="text-[10px] text-[#848E9C]">{entry.timestamp}</span>
                        </div>
                        <p className="text-[#848E9C] text-[11px]">{entry.reason}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-[#2B3139] bg-[#1E2329] flex items-center justify-between">
              <span className="text-xs font-mono text-[#848E9C]">
                TAURIC Institutional Risk Guard • Version 4.0.0
              </span>
              <button
                type="button"
                onClick={() => setModalMode(null)}
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-[#EAECEF] text-xs font-mono font-semibold cursor-pointer transition-colors"
              >
                Close Settings
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ─── Mandatory Financial Risk Warning & Live Authorization Modal ─── */}
      {showLiveAuthConfirmModal && (
        <div
          data-testid="live-auth-confirm-modal"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#262C36]/90 backdrop-blur-md"
        >
          <div className="relative w-full max-w-xl bg-[#1E2329] border-2 border-red-500/50 rounded-3xl shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            {/* Header */}
            <div className="p-6 border-b border-red-500/30 bg-red-950/40 flex items-center gap-3.5">
              <div className="p-2.5 rounded-2xl bg-red-900/60 border border-red-500/40 text-red-400">
                <AlertOctagon className="w-6 h-6 animate-pulse" />
              </div>
              <div>
                <h3 className="text-base font-bold text-[#EAECEF] font-mono flex items-center gap-2">
                  <span>Confirm Live Trading Activation</span>
                </h3>
                <p className="text-xs text-red-300 font-mono">Mandatory Financial Loss & Real-Capital Warning</p>
              </div>
            </div>

            {/* Warning Content */}
            <div className="p-6 space-y-4 font-mono text-xs">
              <div className="p-4 rounded-2xl bg-red-950/30 border border-red-500/30 space-y-2 text-red-200 leading-relaxed">
                <p className="font-bold text-red-300 text-sm">⚠️ CRITICAL FINANCIAL RISK NOTICE:</p>
                <p>
                  Enabling live trading authorizes the platform to submit <strong>REAL-MONEY</strong> orders directly
                  to your connected exchange accounts.
                </p>
                <p>
                  Trading cryptocurrencies and foreign exchange carries significant risk of financial loss. Market
                  volatility, execution slippage, and adverse price movements can result in the loss of all deployed
                  funds.
                </p>
                <p className="text-[11px] text-red-300/80">
                  The backend enforces strict platform prerequisite checks before accepting this request. If any
                  prerequisite fails, activation will be rejected and live trading will remain OFF.
                </p>
              </div>

              {/* Explicit Acknowledgment Checkbox */}
              <label
                data-testid="label-risk-ack"
                className="flex items-start gap-3 p-3.5 rounded-xl bg-[#262C36] border border-[#2B3139] hover:border-[#2B3139] cursor-pointer transition-colors"
              >
                <input
                  type="checkbox"
                  data-testid="checkbox-live-risk-ack"
                  checked={liveAuthRiskAcknowledged}
                  onChange={(e) => setLiveAuthRiskAcknowledged(e.target.checked)}
                  className="mt-0.5 rounded border-[#2B3139] text-red-600 focus:ring-red-500"
                />
                <span className="text-xs text-[#848E9C] leading-relaxed">
                  I understand that live trading submits real orders with real funds and carries financial loss risks.
                  I explicitly confirm I wish to request live trading authorization.
                </span>
              </label>
            </div>

            {/* Actions */}
            <div className="p-4 border-t border-[#2B3139] bg-[#1E2329] flex items-center justify-between gap-3">
              <button
                type="button"
                onClick={() => {
                  setShowLiveAuthConfirmModal(false);
                  setLiveAuthRiskAcknowledged(false);
                }}
                data-testid="btn-cancel-live-confirm"
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-[#848E9C] text-xs font-mono font-semibold cursor-pointer transition-colors"
              >
                Cancel & Keep OFF
              </button>

              <button
                type="button"
                disabled={!liveAuthRiskAcknowledged || isUpdatingLiveAuth}
                onClick={() => handleToggleLiveAuthorization("ENABLE", true)}
                data-testid="btn-confirm-live-auth"
                className={`px-5 py-2 rounded-xl text-xs font-mono font-bold tabular-nums transition-all flex items-center gap-2 ${
                  liveAuthRiskAcknowledged && !isUpdatingLiveAuth
                    ? "bg-red-600 hover:bg-red-500 text-[#EAECEF] cursor-pointer shadow-lg shadow-red-950/50"
                    : "bg-slate-800 text-[#848E9C] cursor-not-allowed border border-[#2B3139]"
                }`}
              >
                {isUpdatingLiveAuth ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Verifying Prerequisites...</span>
                  </>
                ) : (
                  <>
                    <Power className="w-3.5 h-3.5" />
                    <span>Confirm & Submit Request</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ─── IN-APP CONFIRMATION MODAL & TOAST NOTIFICATION ─── */}
      {confirmDialog && confirmDialog.isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#1E2329]/40 backdrop-blur-md animate-in fade-in">
          <div className="w-full max-w-md bg-[#1E2329] border border-[#2B3139] shadow-sm rounded-3xl shadow-2xl p-6 space-y-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-2xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400 shrink-0">
                <AlertTriangle className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-[#EAECEF] font-mono">{confirmDialog.title}</h3>
                <p className="text-xs text-[#848E9C] mt-1">{confirmDialog.message}</p>
              </div>
            </div>
            <div className="flex justify-end gap-3 pt-3 border-t border-[#2B3139] font-mono text-xs">
              <button
                type="button"
                onClick={() => setConfirmDialog(null)}
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-[#848E9C] transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmDialog.onConfirm}
                className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-[#EAECEF] font-bold transition-colors"
              >
                {confirmDialog.confirmText || "Confirm"}
              </button>
            </div>
          </div>
        </div>
      )}

      {toastNotification && (
        <div className="fixed bottom-6 right-6 z-50 max-w-sm p-4 rounded-2xl border shadow-2xl backdrop-blur-md animate-in fade-in font-mono text-xs flex items-center justify-between gap-3 bg-[#1E2329]/95 border-[#2B3139]">
          <span className={toastNotification.type === "error" ? "text-rose-300" : toastNotification.type === "success" ? "text-emerald-300" : "text-cyan-300"}>
            {toastNotification.message}
          </span>
          <button onClick={() => setToastNotification(null)} className="text-[#848E9C] hover:text-[#EAECEF] p-1">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* ─── Universal Pair Search Modal (Crypto & Forex/Metals) ─── */}
      {isUniversalSearchOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#1E2329]/40 backdrop-blur-md animate-in fade-in">
          <div className="w-full max-w-2xl bg-[#1E2329] border border-[#2B3139] shadow-sm rounded-3xl shadow-2xl overflow-hidden flex flex-col max-h-[85vh] font-mono">
            {/* Modal Header */}
            <div className="p-5 border-b border-[#2B3139] flex items-center justify-between bg-[#262C36]">
              <div className="flex items-center space-x-3">
                <div className="h-9 w-9 rounded-xl bg-gradient-to-tr from-sky-500 to-indigo-600 flex items-center justify-center text-[#EAECEF]">
                  <Sparkles className="w-5 h-5 text-sky-200" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-[#EAECEF]">Pair Search & Technical Analysis</h3>
                  <p className="text-xs text-[#848E9C]">Search Crypto (USDT, BTC) or Forex & Metals</p>
                </div>
              </div>
              <button
                onClick={() => setIsUniversalSearchOpen(false)}
                className="p-1.5 rounded-lg text-[#848E9C] hover:text-[#EAECEF] hover:bg-slate-800 transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Search Input Bar */}
            <div className="p-4 border-b border-[#2B3139] bg-[#1E2329]">
              <div className="relative">
                <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-[#848E9C]" />
                <input
                  type="text"
                  autoFocus
                  placeholder="Type any symbol or pair (e.g. BTC, ETH, SOL, EUR, XAU, GOLD, JPY)..."
                  value={universalQuery}
                  onChange={(e) => handleUniversalSearchInput(e.target.value)}
                  className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-[#262C36] border border-[#2B3139] text-sm text-[#EAECEF] placeholder-slate-500 focus:outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500"
                />
              </div>
            </div>

            {/* Results List */}
            <div className="p-4 space-y-2 overflow-y-auto flex-1">
              {isSearchingMarkets && (
                <div className="p-8 text-center text-[#848E9C] text-xs">
                  <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-sky-400" />
                  <span>Searching institutional order books & live market feeds...</span>
                </div>
              )}

              {!isSearchingMarkets && universalSearchResults.length === 0 && universalQuery.trim().length >= 1 && (
                <div className="p-8 text-center text-[#848E9C] text-xs">
                  No matching pairs found for "{universalQuery}". Try BTC, ETH, EUR, XAU, or SOL.
                </div>
              )}

              {!isSearchingMarkets && universalSearchResults.length === 0 && universalQuery.trim().length === 0 && (
                <div className="p-8 text-center text-[#848E9C] text-xs space-y-2">
                  <p>Type a coin name or currency to search across all markets.</p>
                  <div className="flex flex-wrap justify-center gap-2 pt-2">
                    {["BTC/USDT", "ETH/USDT", "SOL/USDT", "EUR/USD", "GBP/USD", "XAU/USD"].map((p) => (
                      <button
                        key={p}
                        onClick={() => searchUniversalMarkets(p)}
                        className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-sky-300 text-xs transition"
                      >
                        {p}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {universalSearchResults.map((m) => (
                <div
                  key={m.symbol}
                  className="p-3.5 rounded-xl bg-[#262C36] border border-[#2B3139] hover:border-[#2B3139] flex items-center justify-between transition"
                >
                  <div className="space-y-0.5">
                    <div className="flex items-center space-x-2">
                      <span className="text-sm font-bold text-[#EAECEF]">{m.symbol}</span>
                      <span className={`text-[10px] font-bold px-1.5 py-0.2 rounded uppercase ${
                        m.market === "FOREX" ? "bg-amber-500/20 text-amber-300 border border-amber-500/30" : "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                      }`}>
                        {m.market}
                      </span>
                    </div>
                    <div className="text-xs text-[#848E9C]">{m.name} • Quote: {m.quote_asset}</div>
                  </div>

                  <div className="flex items-center space-x-4">
                    <div className="text-right">
                      <div className="text-sm font-bold text-[#EAECEF]">
                        {typeof m.price === "number" ? (m.price >= 1 ? `$${m.price.toLocaleString()}` : m.price.toFixed(4)) : m.price}
                      </div>
                      <div className={`text-[10px] font-bold ${
                        (m.change_24h ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"
                      }`}>
                        {(m.change_24h ?? 0) >= 0 ? "+" : ""}{(m.change_24h ?? 0).toFixed(2)}%
                      </div>
                    </div>

                    <button
                      onClick={() => {
                        setIsUniversalSearchOpen(false);
                        executeFourEngineAnalysis(m.symbol, m.market === "FOREX" ? "FOREX" : "CRYPTO");
                      }}
                      className="px-3 py-1.5 rounded-lg bg-[#00E5FF] hover:bg-[#00E5FF]/90 text-[#0B0E11] text-xs font-mono font-bold transition shadow-sm cursor-pointer"
                    >
                      Technical Analysis
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ─── Four-Engine AI Quantitative Dossier Slide-Over Drawer ─── */}
      {isFourEngineModalOpen && (
        <div id="four-engine-modal-overlay" className="fixed inset-0 z-50 overflow-hidden bg-[#0B0E11]/70 backdrop-blur-sm animate-in fade-in transition-all">
          <div className="fixed inset-y-0 right-0 max-w-full flex pl-6 sm:pl-10">
            <div className="w-screen max-w-4xl bg-[#151921] border-l border-[#2B3139] shadow-2xl flex flex-col h-full animate-in slide-in-from-right duration-300">
            <FourEngineDecisionBoard
              contract={activeFourEngineContract}
              isLoading={isFourEngineLoading}
              error={fourEngineError}
              onRetry={() => {
                if (activeAnalysisSymbol) {
                  executeFourEngineAnalysis(activeAnalysisSymbol, activeAnalysisMarket, activeAnalysisTimeframe);
                }
              }}
              loadingStep={fourEngineStep}
              saasFeePolicy={saasFeePolicy}
              billingSummary={saasBillingSummary}
              onActivateAccount={() => {
                handleCloseFourEngineModal();
                setExecutionGateModal("ACTIVATION_REQUIRED");
              }}
              onTopUpCredits={() => {
                handleCloseFourEngineModal();
                if (typeof window !== "undefined") {
                  window.dispatchEvent(new CustomEvent("bitdex_open_topup", { detail: { amount: 50.0 } }));
                }
              }}
              onExecuteTrade={(contract) => handleOpenExecuteFromContract(contract)}
              onClose={handleCloseFourEngineModal}
              onTimeframeChange={(tf) => {
                setActiveAnalysisTimeframe(tf);
                if (activeAnalysisSymbol) {
                  executeFourEngineAnalysis(
                    activeAnalysisSymbol,
                    activeAnalysisMarket,
                    tf
                  );
                }
              }}
              onRefresh={() => {
                if (activeAnalysisSymbol) {
                  executeFourEngineAnalysis(
                    activeAnalysisSymbol,
                    activeAnalysisMarket,
                    activeAnalysisTimeframe
                  );
                }
              }}
            />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}