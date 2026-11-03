"use client";

import React, { useEffect, useState, useCallback, useMemo } from "react";
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
  Info
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

interface ChecklistItem {
  id: string;
  name: string;
  passed: boolean;
  critical: boolean;
  detail: string;
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
      const res = await fetch(`/api/backend/saas/customer/trading/hft/validation?symbol=${sym}`, {
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
  }, [getAuthToken]);

  useEffect(() => {
    fetchOverview();
    fetchHftPairs();
    const interval = setInterval(fetchOverview, 10000);
    return () => clearInterval(interval);
  }, [fetchOverview, fetchHftPairs]);

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

  // Live Break-Even Calculator for Strategy Config
  const breakEvenMath = useMemo(() => {
    const margin = strategyConfig.margin_allocation_usd;
    const lev = strategyConfig.leverage;
    const notional = margin * lev;
    const makerFeePct = 0.02; // Binance USD(S)-M Maker Tier
    const roundTripFeePct = makerFeePct * 2; // 0.04%
    const bufferPct = 0.01; // 0.01% funding/buffer
    const totalFrictionPct = roundTripFeePct + bufferPct; // 0.05%
    const targetPct = strategyConfig.net_profit_target_pct;
    const netReturnPct = Math.max(0, targetPct - totalFrictionPct);
    const estDollarProfit = (notional * (netReturnPct / 100));
    const estFeeDollar = notional * (totalFrictionPct / 100);

    return {
      notional,
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
        throw new Error(resJson.detail || "Failed to save strategy configuration.");
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
        throw new Error(resJson.detail || "Failed to arm HFT session.");
      }

      setSessionState("ACTIVE");
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

        <div className="flex items-center gap-3">
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
                      ${pair.price >= 1 ? pair.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : pair.price.toFixed(4)}
                    </span>
                    <span className={`text-xs font-bold tabular-nums flex items-center ${isPositive ? "text-[#10B981]" : "text-[#F6465D]"}`}>
                      {isPositive ? <ArrowUpRight className="w-3 h-3 mr-0.5" /> : <ArrowDownRight className="w-3 h-3 mr-0.5" />}
                      {pair.price_change_pct_24h > 0 ? "+" : ""}{pair.price_change_pct_24h.toFixed(2)}%
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-1.5 text-[10px] text-[#94A3B8] pt-2 border-t border-[#181822]">
                    <div>
                      <span className="text-[#64748B] block">24h Vol:</span>
                      <span className="text-white font-medium">
                        ${(pair.quote_volume_24h / 1e6).toFixed(1)}M
                      </span>
                    </div>
                    <div>
                      <span className="text-[#64748B] block">Spread:</span>
                      <span className="text-[#00E5FF] font-medium">
                        {pair.spread_bps.toFixed(1)} bps
                      </span>
                    </div>
                    <div>
                      <span className="text-[#64748B] block">Funding:</span>
                      <span className="text-white font-medium">
                        {(pair.funding_rate * 100).toFixed(4)}%
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
                onClick={() => setIsConfigModalOpen(true)}
                className="px-3 py-1.5 rounded-lg bg-[#00E5FF]/15 hover:bg-[#00E5FF] border border-[#00E5FF]/40 text-[#00E5FF] hover:text-[#0B0E11] text-xs font-mono font-bold transition-all flex items-center gap-1.5 cursor-pointer"
              >
                <Sliders className="w-3.5 h-3.5" />
                <span>Configure Strategy</span>
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
                <span className="font-bold text-white">${strategyConfig.margin_allocation_usd.toFixed(2)}</span>
              </div>
              <div className="p-2.5 rounded-xl bg-[#0A0A0E] border border-[#272735]">
                <span className="text-[10px] text-[#64748B] block">Isolated Leverage:</span>
                <span className="font-bold text-[#00E5FF]">{strategyConfig.leverage}x</span>
              </div>
              <div className="p-2.5 rounded-xl bg-[#0A0A0E] border border-[#272735]">
                <span className="text-[10px] text-[#64748B] block">Net Target (TP):</span>
                <span className="font-bold text-[#10B981]">+{strategyConfig.net_profit_target_pct.toFixed(2)}%</span>
              </div>
              <div className="p-2.5 rounded-xl bg-[#0A0A0E] border border-[#272735]">
                <span className="text-[10px] text-[#64748B] block">Max Loss (SL):</span>
                <span className="font-bold text-[#F6465D]">-{strategyConfig.max_loss_pct.toFixed(2)}%</span>
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
                <span className="font-bold text-white">${breakEvenMath.notional.toFixed(2)}</span>
              </div>
              <div className="flex items-center justify-between text-[#94A3B8]">
                <span>Estimated Maker Friction (0.04% + Buffer):</span>
                <span className="font-bold text-[#00E5FF]">+{breakEvenMath.totalFrictionPct.toFixed(3)}% (~${breakEvenMath.estFeeDollar.toFixed(3)})</span>
              </div>
              <div className="flex items-center justify-between text-[#94A3B8] border-t border-[#181822] pt-1.5">
                <span className="text-[#10B981]">Net Target Return at Fill:</span>
                <span className="font-bold text-[#10B981]">+{breakEvenMath.netReturnPct.toFixed(2)}% (~+${breakEvenMath.estDollarProfit.toFixed(2)}/cycle)</span>
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
                onClick={handleStartSession}
                disabled={!isReady || sessionActionLoading}
                className={`px-5 py-2.5 rounded-xl font-bold transition-all flex items-center gap-2 ${
                  isReady && !sessionActionLoading
                    ? "bg-[#10B981] hover:bg-[#10B981]/90 text-[#0B0E11] cursor-pointer shadow-lg shadow-[#10B981]/20"
                    : "bg-[#181822] text-[#64748B] border border-[#272735] cursor-not-allowed opacity-60"
                }`}
              >
                {sessionActionLoading ? (
                  <RefreshCw className="w-4 h-4 animate-spin" />
                ) : (
                  <Play className="w-4 h-4 fill-current" />
                )}
                <span>Arm &amp; Start Session</span>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* ─── STEP 5: LIVE EXECUTION MONITOR & TRADE JOURNAL ─────────────────── */}
      <div className="p-4 sm:p-5 rounded-2xl bg-[#121218] border border-[#272735] space-y-4 shadow-lg font-mono">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#272735] pb-3">
          <div className="flex items-center gap-2">
            <span className="w-5 h-5 rounded-full bg-[#00E5FF]/20 text-[#00E5FF] text-xs font-bold flex items-center justify-center">
              5
            </span>
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">
              Live Execution &amp; Position Monitor ({selectedPair})
            </h3>
          </div>

          <span className="text-[10px] text-[#64748B] flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-[#10B981] animate-pulse" />
            Distinguishing live estimates from exchange-confirmed fills
          </span>
        </div>

        {/* Telemetry Metrics Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 text-xs">
          <div className="p-3 rounded-xl bg-[#0A0A0E] border border-[#272735]">
            <span className="text-[10px] text-[#64748B] block">Market Price:</span>
            <span className="font-bold text-white tabular-nums">
              ${activePairObj?.price ? activePairObj.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "---"}
            </span>
          </div>

          <div className="p-3 rounded-xl bg-[#0A0A0E] border border-[#272735]">
            <span className="text-[10px] text-[#64748B] block">Position Size:</span>
            <span className="font-bold text-white tabular-nums">
              {positions.length > 0 ? `${positions[0].quantity} (${positions[0].symbol})` : "0.00 (Flat)"}
            </span>
          </div>

          <div className="p-3 rounded-xl bg-[#0A0A0E] border border-[#272735]">
            <span className="text-[10px] text-[#64748B] block">Unrealized P&amp;L:</span>
            <span className="font-bold text-[#94A3B8] tabular-nums">
              ${positions.length > 0 ? positions[0].unrealized_pnl.toFixed(2) : "0.00"} (Est)
            </span>
          </div>

          <div className="p-3 rounded-xl bg-[#0A0A0E] border border-[#272735]">
            <span className="text-[10px] text-[#64748B] block">Confirmed Fills Realized:</span>
            <span className="font-bold text-[#10B981] tabular-nums">
              ${account?.unrealized_pnl ? account.unrealized_pnl.toFixed(2) : "0.00"}
            </span>
          </div>

          <div className="p-3 rounded-xl bg-[#0A0A0E] border border-[#272735]">
            <span className="text-[10px] text-[#64748B] block">Stop-Loss Order:</span>
            <span className="font-bold text-white">
              {positions.length > 0 && positions[0].stop_exchange_order_id
                ? `#${positions[0].stop_exchange_order_id}`
                : "STANDBY (FLAT)"}
            </span>
          </div>

          <div className="p-3 rounded-xl bg-[#0A0A0E] border border-[#272735]">
            <span className="text-[10px] text-[#64748B] block">Take-Profit Target:</span>
            <span className="font-bold text-[#10B981]">
              +{strategyConfig.net_profit_target_pct.toFixed(2)}%
            </span>
          </div>
        </div>

        {/* Recent Audited Scalp Executions Table */}
        <div className="space-y-2 pt-2">
          <div className="flex items-center justify-between text-xs text-[#94A3B8]">
            <span>Recent Audited Trades ({recentTrades.length} Confirmed)</span>
            <span>Fee Deductions Net-of-Maker Rebate</span>
          </div>

          {recentTrades.length === 0 ? (
            <div className="text-center py-6 text-xs text-[#64748B] bg-[#0A0A0E] rounded-xl border border-[#272735]">
              No confirmed executions recorded for this account. Controlled validation mode prevents live order dispatch.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-[#272735] text-[#64748B] text-[10px] uppercase">
                    <th className="py-2 px-3">Trade ID</th>
                    <th className="py-2 px-3">Symbol</th>
                    <th className="py-2 px-3">Side</th>
                    <th className="py-2 px-3">Qty</th>
                    <th className="py-2 px-3">Entry</th>
                    <th className="py-2 px-3">Exit</th>
                    <th className="py-2 px-3">Fee ($)</th>
                    <th className="py-2 px-3">Net P&amp;L</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#181822]">
                  {recentTrades.slice(0, 5).map((t) => (
                    <tr key={t.trade_id} className="hover:bg-[#151921]">
                      <td className="py-2 px-3 text-[#94A3B8]">{t.trade_id}</td>
                      <td className="py-2 px-3 font-bold text-white">{t.symbol}</td>
                      <td className={`py-2 px-3 font-bold ${t.side === "BUY" ? "text-[#10B981]" : "text-[#F6465D]"}`}>
                        {t.side}
                      </td>
                      <td className="py-2 px-3 tabular-nums">{t.quantity}</td>
                      <td className="py-2 px-3 tabular-nums">${t.entry_price.toFixed(2)}</td>
                      <td className="py-2 px-3 tabular-nums">${t.exit_price.toFixed(2)}</td>
                      <td className="py-2 px-3 tabular-nums text-[#94A3B8]">${t.fee_usd.toFixed(4)}</td>
                      <td className={`py-2 px-3 tabular-nums font-bold ${t.realized_pnl >= 0 ? "text-[#10B981]" : "text-[#F6465D]"}`}>
                        ${t.realized_pnl.toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
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
                  <span className="text-[#00E5FF] font-bold">${strategyConfig.margin_allocation_usd.toFixed(2)}</span>
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
                  Notional position: ${(strategyConfig.margin_allocation_usd * strategyConfig.leverage).toFixed(2)} USD.
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
                    <span className="font-bold text-[#00E5FF] block">+{breakEvenMath.requiredMovePct.toFixed(3)}%</span>
                  </div>
                  <div>
                    <span>Net Gain at Target:</span>
                    <span className="font-bold text-[#10B981] block">
                      +${breakEvenMath.estDollarProfit.toFixed(2)} (+{breakEvenMath.netReturnPct.toFixed(2)}%)
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
    </div>
  );
}
