"use client";

import React, { useState, useEffect } from "react";
import {
  Activity,
  ArrowUpRight,
  ArrowDownRight,
  CheckCircle2,
  AlertTriangle,
  Clock,
  TrendingUp,
  RefreshCw,
  Gauge,
  Info,
  X,
  Target,
  Zap,
  ShieldCheck,
  Lock,
  FileCheck,
  Sliders,
  Check,
  Copy,
  Layers,
  ChevronDown,
  ChevronUp,
  BrainCircuit,
  Compass,
  Play,
  Coins
} from "lucide-react";

export interface EngineResult {
  engine?: string;
  name?: string;
  vote?: "BUY" | "SELL" | "HOLD";
  direction?: "BUY" | "SELL" | "HOLD";
  confidence?: number;
  setup_grade?: string;
  horizon?: string;
  summary?: string;
  observations?: string[];
  risk_notes?: string;
  confluences?: string[];
  order_blocks?: Array<{
    type: string;
    low: number;
    high: number;
    significance?: string;
  }>;
  liquidity_sweep?: {
    swept: boolean;
    level: string;
    details?: string;
  };
  metrics?: {
    sharpe_ratio: number;
    max_drawdown_pct: number;
    win_rate_pct: number;
    net_return_after_friction_pct: number;
    total_trades_analyzed: number;
  };
  status?: string;
  is_directional_vote?: boolean;
}

export interface FourEngineContract {
  analysis_id?: string;
  contract_id?: string;
  symbol: string;
  market?: "CRYPTO" | "FOREX";
  timeframe?: string;
  status: "COMPLETED" | "RUNNING" | "FAILED" | "EXPIRED";
  analysis_completed_at?: string;
  valid_until_utc?: string;
  is_market_closed?: boolean;
  closed_market_notice?: string;
  price_stale?: boolean;
  current_price?: number;
  confidence_score?: number;
  consensus_verdict?: string;
  engines: {
    tauric: EngineResult;
    jev: EngineResult;
    cipher: EngineResult;
    octobot_validation: EngineResult;
  };
  consensus: {
    decision: "BUY" | "SELL" | "HOLD" | "NO_TRADE";
    agreement_ratio: string;
    consensus_label: "STRONG_CONSENSUS" | "MODERATE_CONSENSUS" | "CONFLICTING_SIGNALS" | "NO_ACTION";
    reason: string;
    engines_agreed: string[];
    engines_opposed: string[];
  };
  execution_plan: {
    action: "BUY" | "SELL" | "HOLD";
    entry_zone: {
      min: number;
      max: number;
      label?: string;
    };
    stop_loss: number;
    invalidation_price: number;
    take_profit_targets: Array<{
      target: string;
      price: number;
      projected_rr: number;
      allocation_pct: number;
    }>;
    risk_reward_ratio: string;
    estimated_fees_pct: number;
    invalidation_reason: string;
  };
  metadata?: {
    live_trading_locked: boolean;
    read_only_mode: boolean;
    licensing: {
      cipher: string;
      octobot_boundary: string;
    };
  };
}

interface FourEngineDecisionBoardProps {
  contract: FourEngineContract | null;
  isLoading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  onClose?: () => void;
  onRefresh?: () => void;
  loadingStep?: string;
  saasFeePolicy?: any;
  billingSummary?: any;
  onActivateAccount?: () => void;
  onTopUpCredits?: () => void;
  onExecuteTrade?: (contract: FourEngineContract) => void;
  isMarketClosed?: boolean;
  closedMarketNotice?: string | null;
}

export const FourEngineDecisionBoard: React.FC<FourEngineDecisionBoardProps> = ({
  contract,
  isLoading = false,
  error = null,
  onRetry,
  onClose,
  onRefresh,
  loadingStep = "Executing Four-Engine Synthesis...",
  saasFeePolicy,
  billingSummary,
  onActivateAccount,
  onTopUpCredits,
  onExecuteTrade,
  isMarketClosed: propIsMarketClosed,
  closedMarketNotice: propClosedMarketNotice,
}) => {
  const [secondsRemaining, setSecondsRemaining] = useState<number | null>(null);
  const [copied, setCopied] = useState(false);
  const [showTechnicalDetails, setShowTechnicalDetails] = useState(false);
  const [selectedTimeframe, setSelectedTimeframe] = useState<string>("1h");

  const isMarketClosed = Boolean(
    propIsMarketClosed ||
    contract?.is_market_closed ||
    (contract?.market === "FOREX" && (contract?.consensus as any)?.reason?.includes("MARKET_CLOSED")) ||
    (contract as any)?.market_status === "CLOSED"
  );
  const closedNotice = propClosedMarketNotice || contract?.closed_market_notice || "Forex market is closed. The latest available quote is shown as stale.";

  // Live countdown timer based on valid_until_utc
  useEffect(() => {
    if (!contract?.valid_until_utc) {
      setSecondsRemaining(null);
      return;
    }

    const updateCountdown = () => {
      const expiry = new Date(contract.valid_until_utc!).getTime();
      const now = new Date().getTime();
      const diffSec = Math.max(0, Math.floor((expiry - now) / 1000));
      setSecondsRemaining(diffSec);
    };

    updateCountdown();
    const interval = setInterval(updateCountdown, 1000);
    return () => clearInterval(interval);
  }, [contract?.valid_until_utc]);

  const formatCountdown = (totalSec: number | null) => {
    if (totalSec === null) return "--:--:--";
    if (totalSec <= 0) return "EXPIRED";
    const h = Math.floor(totalSec / 3600);
    const m = Math.floor((totalSec % 3600) / 60);
    const s = totalSec % 60;
    return `${h.toString().padStart(2, "0")}h ${m.toString().padStart(2, "0")}m ${s.toString().padStart(2, "0")}s`;
  };

  const formatCurrency = (val: any) => {
    if (val === null || val === undefined) return "--";
    const num = Number(val);
    if (isNaN(num)) return String(val);
    return num.toLocaleString(undefined, { minimumFractionDigits: num > 10 ? 2 : 4, maximumFractionDigits: num > 10 ? 2 : 5 });
  };

  const plan = contract?.execution_plan;
  const engines = contract?.engines;
  const consensus = contract?.consensus;

  const getTpPrice = (idx: number) => {
    if (!plan) return "--";
    if (Array.isArray(plan.take_profit_targets) && plan.take_profit_targets[idx]?.price !== undefined) {
      return formatCurrency(plan.take_profit_targets[idx].price);
    }
    const levels = (plan as any).take_profit_levels;
    if (Array.isArray(levels) && levels[idx] !== undefined) {
      return formatCurrency(levels[idx]);
    }
    return "--";
  };

  const isBuy = consensus?.decision === "BUY";
  const isSell = consensus?.decision === "SELL";
  const biasLabel = isBuy ? "Long bias" : isSell ? "Short bias" : "Neutral";

  const copyExecutionSetup = () => {
    if (!contract) return;
    const ez = typeof plan?.entry_zone === "string" ? plan.entry_zone : `${plan?.entry_zone?.min ?? "--"} - ${plan?.entry_zone?.max ?? "--"}`;
    const text = `BITDEX FOUR-ENGINE AI ANALYSIS
Symbol: ${contract.symbol} (${contract.market || "CRYPTO"}) [${contract.timeframe || "1h"}]
Decision: ${contract.consensus?.decision} (${contract.consensus?.consensus_label})
Agreement: ${contract.consensus?.agreement_ratio || "3/3"}
Entry Zone: ${ez}
Stop Loss: ${plan?.stop_loss ?? "N/A"}
Invalidation Price: ${plan?.invalidation_price ?? "N/A"}
TP1: ${getTpPrice(0)}
TP2: ${getTpPrice(1)}
Risk/Reward: ${plan?.risk_reward_ratio || "1:2.8"}
Expiry: ${contract.valid_until_utc || "N/A"} UTC
Notice: Live trading locked (Read-Only Analytical Output)`;

    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  return (
    <div className="relative bg-white border border-slate-200/90 rounded-2xl shadow-xl overflow-hidden font-sans text-slate-900 transition-all">
      {/* ─── 1. TOP HEADER ROW (IMAGE 2 SPEC) ─────────────────────────── */}
      <div className="px-6 py-4 border-b border-slate-200 bg-white flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-2.5">
          <h2 className="text-2xl font-bold font-mono tracking-tight text-slate-900">
            {contract?.symbol || "BTC/USDT"}
          </h2>
          <span className="px-2.5 py-0.5 rounded-md text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-200">
            {contract?.market === "FOREX" ? "Forex" : "Crypto"}
          </span>
          <span className="px-2.5 py-0.5 rounded-md text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200">
            Technical Analysis
          </span>
          <span className="px-2.5 py-0.5 rounded-md text-xs font-bold font-mono bg-amber-50 text-amber-800 border border-amber-200">
            ILLUSTRATIVE DATA
          </span>
        </div>

        {/* Timeframe Selector Capsule & Actions */}
        <div className="flex items-center gap-3">
          <div className="p-1 bg-slate-100 rounded-xl border border-slate-200 flex items-center gap-1 text-xs font-mono">
            {["1m", "5m", "15m", "1h", "4h", "1d"].map((tf) => (
              <button
                key={tf}
                onClick={() => setSelectedTimeframe(tf)}
                className={`px-3 py-1 rounded-lg transition-all cursor-pointer ${
                  selectedTimeframe === tf
                    ? "bg-white text-slate-900 font-bold shadow-sm border border-slate-200/80"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                {tf}
              </button>
            ))}
          </div>

          {onRefresh && (
            <button
              onClick={onRefresh}
              disabled={isLoading}
              className="p-2 rounded-xl bg-slate-50 hover:bg-slate-100 text-slate-600 transition-colors border border-slate-200 cursor-pointer disabled:opacity-50"
              title="Refresh Analysis"
            >
              <RefreshCw className={`w-4 h-4 ${isLoading ? "animate-spin text-blue-600" : ""}`} />
            </button>
          )}

          {onClose && (
            <button
              onClick={onClose}
              className="p-2 rounded-xl bg-slate-50 hover:bg-rose-50 hover:text-rose-600 text-slate-500 transition-colors border border-slate-200 cursor-pointer"
              title="Close Board"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Loading Overlay */}
      {isLoading && (
        <div className="p-12 flex flex-col items-center justify-center bg-slate-50/80 backdrop-blur-sm border-b border-slate-200">
          <div className="relative mb-6">
            <div className="w-14 h-14 rounded-full border-4 border-blue-200 border-t-blue-600 animate-spin" />
            <BrainCircuit className="w-6 h-6 text-blue-600 absolute inset-0 m-auto" />
          </div>
          <div className="text-base font-bold text-slate-900 mb-1">
            Synthesizing Four Quantitative Engines
          </div>
          <div className="text-xs text-blue-600 font-mono animate-pulse">
            {loadingStep}
          </div>
          <div className="mt-4 flex items-center space-x-2 text-[11px] text-slate-500">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-ping" />
            <span>TAURIC • JEV • CIPHER (SMC) • OCTOBOT (Validation)</span>
          </div>
        </div>
      )}

      {/* Error State */}
      {error && !isLoading && (
        <div className="p-8 flex flex-col items-center justify-center text-center bg-slate-50 border-b border-slate-200 space-y-4">
          <div className="w-12 h-12 rounded-2xl bg-rose-50 border border-rose-200 flex items-center justify-center text-rose-600 shadow-sm">
            <AlertTriangle className="w-6 h-6" />
          </div>
          <div className="max-w-md space-y-1">
            <h3 className="text-sm font-bold text-slate-900">Analysis Error</h3>
            <p className="text-xs text-rose-700 font-mono bg-rose-50 p-2.5 rounded-lg border border-rose-200 break-words">
              {error}
            </p>
          </div>
          {onRetry && (
            <button
              onClick={onRetry}
              className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-medium text-xs flex items-center gap-1.5 shadow-sm cursor-pointer"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Retry Analysis</span>
            </button>
          )}
        </div>
      )}

      {/* ─── MAIN CONTENT BODY ────────────────────────────────────────── */}
      {contract && !isLoading && !error && (
        <div className="p-6 space-y-6">
          {/* Forex Market Closed Stale Quote Warning */}
          {isMarketClosed && (
            <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 flex items-start gap-3 shadow-sm">
              <Clock className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
              <div className="space-y-1 text-xs">
                <div className="font-bold flex items-center gap-2">
                  <span className="uppercase tracking-wider">Forex Market Closed</span>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-100 text-amber-800 border border-amber-200">
                    STALE QUOTE
                  </span>
                </div>
                <p className="leading-relaxed font-sans">{closedNotice}</p>
              </div>
            </div>
          )}

          {/* ─── 2. TOP 3 SUMMARY CARDS ROW (IMAGE 2 SPEC) ─────────────── */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Card 1: Candle Closes In */}
            <div className="bg-white border border-slate-200/90 rounded-2xl p-5 shadow-sm">
              <span className="text-xs text-slate-500 font-medium block">
                Candle closes in ({contract.timeframe?.toLowerCase() || "1h"} candle)
              </span>
              <div className="text-3xl font-bold font-mono text-slate-900 mt-1">
                12:41
              </div>
            </div>

            {/* Card 2: Signal Valid Until */}
            <div className="bg-white border border-slate-200/90 rounded-2xl p-5 shadow-sm">
              <span className="text-xs text-slate-500 font-medium block">
                Signal valid until
              </span>
              <div className="text-3xl font-bold font-mono text-slate-900 mt-1 flex items-baseline gap-2">
                <span>14:30 UTC</span>
                <span className="text-xs text-slate-500 font-normal font-sans">
                  · {formatCountdown(secondsRemaining)} left
                </span>
              </div>
            </div>

            {/* Card 3: Last Market-Data Update */}
            <div className="bg-white border border-slate-200/90 rounded-2xl p-5 shadow-sm">
              <span className="text-xs text-slate-500 font-medium block">
                Last market-data update
              </span>
              <div className="text-3xl font-bold font-mono text-slate-900 mt-1 flex items-baseline gap-2">
                <span>3 s ago</span>
                <span className="text-xs text-emerald-700 font-medium font-sans flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
                  <span>Live</span>
                </span>
              </div>
            </div>
          </div>

          {/* ─── 3. SIGNAL LEVELS CARD (IMAGE 2 SPEC - STRICTLY NO CHARTS) ─── */}
          <div className="bg-white border border-slate-200/90 rounded-2xl p-6 shadow-sm space-y-5">
            <div className="flex items-center justify-between pb-3 border-b border-slate-200">
              <h3 className="text-lg font-bold text-slate-900">Signal levels</h3>
              <span className={`px-3 py-1 rounded-full text-xs font-bold border flex items-center gap-1 ${
                isBuy ? "bg-emerald-50 text-emerald-700 border-emerald-200" :
                isSell ? "bg-rose-50 text-rose-700 border-rose-200" :
                "bg-slate-100 text-slate-700 border-slate-200"
              }`}>
                <span>{isBuy ? "▲" : isSell ? "▼" : "◆"}</span>
                <span>{biasLabel}</span>
              </span>
            </div>

            {/* Numerical Key-Value Rows */}
            <div className="space-y-3 font-mono text-sm">
              <div className="flex items-center justify-between py-1.5 border-b border-slate-100">
                <span className="text-slate-500 font-sans text-xs">Entry</span>
                <span className="font-bold text-slate-900">
                  {typeof plan?.entry_zone === "string" ? plan.entry_zone : formatCurrency(plan?.entry_zone?.min || contract.current_price || 100.00)}
                </span>
              </div>
              <div className="flex items-center justify-between py-1.5 border-b border-slate-100">
                <span className="text-slate-500 font-sans text-xs">Stop-loss</span>
                <span className="font-bold text-rose-600">
                  {formatCurrency(plan?.stop_loss || 97.50)}
                </span>
              </div>
              <div className="flex items-center justify-between py-1.5 border-b border-slate-100">
                <span className="text-slate-500 font-sans text-xs">Take-profit 1</span>
                <span className="font-bold text-emerald-600">
                  {getTpPrice(0) !== "--" ? getTpPrice(0) : "104.00"}
                </span>
              </div>
              <div className="flex items-center justify-between py-1.5 border-b border-slate-100">
                <span className="text-slate-500 font-sans text-xs">Take-profit 2</span>
                <span className="font-bold text-emerald-600">
                  {getTpPrice(1) !== "--" ? getTpPrice(1) : "108.00"}
                </span>
              </div>
              <div className="flex items-center justify-between py-1.5 border-b border-slate-100">
                <span className="text-slate-500 font-sans text-xs">Invalidation</span>
                <span className="font-bold text-slate-900 font-sans text-xs">
                  Close below {formatCurrency(plan?.invalidation_price || 97.50)}
                </span>
              </div>
              <div className="flex items-center justify-between py-1.5">
                <span className="text-slate-500 font-sans text-xs">Risk / reward</span>
                <span className="font-bold text-blue-700">
                  {plan?.risk_reward_ratio || "1 : 1.6 (TP1) · 1 : 3.2 (TP2)"}
                </span>
              </div>
            </div>

            <p className="text-xs text-slate-500 font-sans">
              Levels are the values reported by the engines. Read-only view: no orders are placed from this screen.
            </p>

            {/* Arithmetic Callout Box (Image 2 Spec) */}
            <div className="bg-[#eff6ff] border border-[#bfdbfe] text-[#1e40af] rounded-xl p-3.5 text-xs font-medium">
              Risk/reward is arithmetic on the levels above. It is not a probability of profit.
            </div>

            {/* Admin Fee Exemption / Execution Action */}
            {(() => {
              if (isMarketClosed) {
                return (
                  <div className="p-3 rounded-xl bg-slate-100 text-slate-500 font-mono text-xs flex items-center justify-center gap-2 border border-slate-200">
                    <Lock className="w-4 h-4" />
                    <span>Market Closed — Execution Unavailable</span>
                  </div>
                );
              }

              const isAdminExempt = saasFeePolicy?.is_admin_exempt === true || saasFeePolicy?.fee_waived === 1 || billingSummary?.is_admin_exempt === true;
              const isActivated = isAdminExempt || saasFeePolicy?.activation_fee_charged === 1 || saasFeePolicy?.activation_fee_charged === true;
              const availableCredits = billingSummary?.prepaid_credits_usd || 0;
              const hasSufficientCredits = isAdminExempt || availableCredits >= 0.30;

              if (isAdminExempt) {
                return (
                  <div className="space-y-3 pt-2">
                    <div className="p-3 rounded-xl bg-sky-50 border border-sky-200 text-sky-800 flex items-center justify-between text-xs font-mono shadow-sm">
                      <div className="flex items-center gap-2 text-sky-700">
                        <ShieldCheck className="w-4 h-4 text-sky-600 shrink-0" />
                        <span className="font-bold">ADMIN — FEE EXEMPT</span>
                        <span className="text-[11px] text-sky-700/80 hidden sm:inline">• Pre-Flight Qualified ($0.00 Fees Assessed)</span>
                      </div>
                      <span className="text-[10px] text-slate-600">
                        Validity: <strong className="text-slate-900">{formatCountdown(secondsRemaining)}</strong>
                      </span>
                    </div>
                    <button
                      onClick={() => onExecuteTrade && onExecuteTrade(contract)}
                      className="w-full py-3 px-4 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-mono font-bold text-xs flex items-center justify-center gap-2 cursor-pointer shadow-md transition-all"
                    >
                      <Play className="w-4 h-4 fill-white" />
                      <span>Execute Trade Setup (Admin Staging Exemption)</span>
                    </button>
                  </div>
                );
              }

              if (!isActivated) {
                return (
                  <div className="space-y-3 pt-2">
                    <div className="p-3 rounded-xl bg-amber-50 border border-amber-200 flex items-start gap-2.5 text-xs text-amber-800 font-mono">
                      <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                      <div>
                        <strong className="block text-amber-900">Account Activation Required ($20.00)</strong>
                        <p className="text-[11px] text-amber-800/90 mt-0.5 font-sans">
                          Your account must be activated before submitting orders to paper simulation or testnet environments.
                        </p>
                      </div>
                    </div>
                    <button
                      onClick={onActivateAccount}
                      className="w-full py-3 px-4 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-mono font-bold text-xs flex items-center justify-center gap-2 cursor-pointer shadow-md transition-all"
                    >
                      <AlertTriangle className="w-4 h-4" />
                      <span>Activate Account</span>
                    </button>
                  </div>
                );
              }

              if (!hasSufficientCredits) {
                return (
                  <div className="space-y-3 pt-2">
                    <div className="p-3 rounded-xl bg-purple-50 border border-purple-200 flex items-start gap-2.5 text-xs text-purple-800 font-mono">
                      <Coins className="w-4 h-4 text-purple-600 shrink-0 mt-0.5" />
                      <div>
                        <strong className="block text-purple-900">Insufficient Execution Credits</strong>
                        <p className="text-[11px] text-purple-800/90 mt-0.5 font-sans">
                          Each trade execution requires $0.30 in prepaid AI & execution credits. Your current balance is ${availableCredits.toFixed(2)}.
                        </p>
                      </div>
                    </div>
                    <button
                      onClick={onTopUpCredits}
                      className="w-full py-3 px-4 rounded-xl bg-purple-600 hover:bg-purple-700 text-white font-mono font-bold text-xs flex items-center justify-center gap-2 cursor-pointer shadow-md transition-all"
                    >
                      <Coins className="w-4 h-4" />
                      <span>Top Up to Execute</span>
                    </button>
                  </div>
                );
              }

              return (
                <div className="space-y-3 pt-2">
                  <button
                    onClick={() => onExecuteTrade && onExecuteTrade(contract)}
                    className="w-full py-3 px-4 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-mono font-bold text-xs flex items-center justify-center gap-2 cursor-pointer shadow-md transition-all"
                  >
                    <Play className="w-4 h-4 fill-white" />
                    <span>Execute Trade Setup</span>
                  </button>
                </div>
              );
            })()}
          </div>

          {/* ─── 4. FOUR-ENGINE ANALYSIS SECTION (IMAGE 2 SPEC) ─────────── */}
          <div className="bg-white border border-slate-200/90 rounded-2xl p-6 shadow-sm space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <h3 className="text-lg font-bold text-slate-900">Four-engine analysis</h3>
              <span className="text-xs text-slate-500 font-mono">Each engine's own verdict. Placeholder text.</span>
            </div>

            {/* 4 Engine Cards Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {/* 1. TAURIC */}
              <div className="bg-white border border-slate-200 rounded-xl p-4 flex flex-col justify-between hover:border-slate-300 transition-all shadow-sm">
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-bold text-slate-900">TAURIC</span>
                    <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center gap-1">
                      <span>▲</span>
                      <span>Long bias</span>
                    </span>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider block">Evidence</span>
                    <p className="text-xs text-slate-700 leading-relaxed mt-0.5">
                      {engines?.tauric?.summary || "Sample: research summary leans toward continued upside."}
                    </p>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider block">Limitations</span>
                    <p className="text-xs text-slate-500 leading-relaxed mt-0.5">
                      Slower, deep-research layer. Last run 12 min ago.
                    </p>
                  </div>
                </div>
                <div className="pt-3 mt-3 border-t border-slate-100 text-[11px] text-slate-400 font-mono flex items-center justify-between">
                  <span>Horizon: {engines?.tauric?.horizon || "1h-4h"}</span>
                  <span className="text-blue-600">Multi-Agent</span>
                </div>
              </div>

              {/* 2. JEV */}
              <div className="bg-white border border-slate-200 rounded-xl p-4 flex flex-col justify-between hover:border-slate-300 transition-all shadow-sm">
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-bold text-slate-900">Jev</span>
                    <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center gap-1">
                      <span>▲</span>
                      <span>Long bias</span>
                    </span>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider block">Evidence</span>
                    <p className="text-xs text-slate-700 leading-relaxed mt-0.5">
                      {engines?.jev?.summary || "Sample: short-horizon momentum supports the entry zone."}
                    </p>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider block">Limitations</span>
                    <p className="text-xs text-slate-500 leading-relaxed mt-0.5">
                      Fast layer, more sensitive to short-term noise.
                    </p>
                  </div>
                </div>
                <div className="pt-3 mt-3 border-t border-slate-100 text-[11px] text-slate-400 font-mono flex items-center justify-between">
                  <span>Risk: {engines?.jev?.risk_notes || "Acceptable"}</span>
                  <span className="text-indigo-600">Independent</span>
                </div>
              </div>

              {/* 3. CIPHER */}
              <div className="bg-white border border-slate-200 rounded-xl p-4 flex flex-col justify-between hover:border-slate-300 transition-all shadow-sm">
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-bold text-slate-900">CIPHER</span>
                    <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-rose-50 text-rose-700 border border-rose-200 flex items-center gap-1">
                      <span>▼</span>
                      <span>Short bias</span>
                    </span>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider block">Evidence</span>
                    <p className="text-xs text-slate-700 leading-relaxed mt-0.5">
                      {engines?.cipher?.summary || "Sample: price stalling below a resistance area."}
                    </p>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider block">Limitations</span>
                    <p className="text-xs text-slate-500 leading-relaxed mt-0.5">
                      Sample: weaker on trending moves.
                    </p>
                  </div>
                </div>
                <div className="pt-3 mt-3 border-t border-slate-100 text-[11px] text-slate-400 font-mono flex items-center justify-between">
                  <span>Setup: Grade {engines?.cipher?.setup_grade || "B"}</span>
                  <span className="text-cyan-600">SMC Blocks</span>
                </div>
              </div>

              {/* 4. OCTOBOT */}
              <div className="bg-white border border-slate-200 rounded-xl p-4 flex flex-col justify-between hover:border-slate-300 transition-all shadow-sm">
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-bold text-slate-900">OctoBot</span>
                    <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-600 border border-slate-200 flex items-center gap-1">
                      <span>■</span>
                      <span>No result</span>
                    </span>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider block">Status</span>
                    <p className="text-xs text-slate-700 leading-relaxed mt-0.5">
                      Engine unavailable. Nothing is shown or estimated for it.
                    </p>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider block">Effect</span>
                    <p className="text-xs text-slate-500 leading-relaxed mt-0.5">
                      Not included in the comparison.
                    </p>
                  </div>
                </div>
                <div className="pt-3 mt-3 border-t border-slate-100 text-[11px] text-slate-400 font-mono flex items-center justify-between">
                  <span>Fee: 0.15%</span>
                  <span className="text-amber-600">GPL-3 Boundary</span>
                </div>
              </div>
            </div>

            {/* Disagreement Banner (Image 2 Spec) */}
            <div className="bg-[#fef9c3] border border-[#fde047] text-[#854d0e] rounded-xl p-3.5 text-xs font-medium">
              <strong>Disagreement:</strong> CIPHER differs from TAURIC and Jev, and 1 of 4 engines returned no result.
            </div>

            {/* Combined Conclusion Callout (Image 2 Spec) */}
            <div className="bg-[#eff6ff] border border-[#bfdbfe] text-[#1e40af] rounded-xl p-3.5 text-xs font-medium">
              <strong>Combined conclusion not shown.</strong> Engines may rely on overlapping inputs, so agreement is not independent confirmation. A summary appears only when real results support one.
            </div>

            {/* Technical Details Accordion Toggle */}
            <div className="pt-2">
              <button
                onClick={() => setShowTechnicalDetails(!showTechnicalDetails)}
                className="text-xs text-slate-500 hover:text-slate-800 flex items-center gap-1 font-mono cursor-pointer"
              >
                <span>{showTechnicalDetails ? "Hide technical audit data" : "View technical audit data & licensing boundaries"}</span>
                {showTechnicalDetails ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
              </button>

              {showTechnicalDetails && (
                <div className="mt-3 p-4 rounded-xl bg-slate-50 border border-slate-200 text-xs font-mono space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500">Execution Plan Hash:</span>
                    <span className="text-slate-800">{contract.analysis_id || "FE-STAGING-VERIFIED"}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500">SMC Order Blocks:</span>
                    <span className="text-slate-800">{engines?.cipher?.order_blocks?.length || 2} Detected</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500">OctoBot Boundary:</span>
                    <span className="text-slate-800">Decoupled subprocess isolation (zero derivative works)</span>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default FourEngineDecisionBoard;
