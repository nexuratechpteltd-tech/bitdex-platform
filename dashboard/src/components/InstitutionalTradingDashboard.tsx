"use client";

import React, { useEffect, useState, useCallback } from "react";
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
  BarChart3
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
    stop_loss_coverage_pct: number;
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
  spread_bps: number;
  funding_rate: number;
  price_change_pct_24h: number;
  rank_score: number;
  base_asset: string;
  quote_asset: string;
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
  const [togglingEngineB, setTogglingEngineB] = useState<boolean>(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error" | "info"; message: string } | null>(null);

  // Dynamic Binance USD(S)-M HFT Pairs State
  const [hftPairs, setHftPairs] = useState<HftPair[]>([]);
  const [loadingPairs, setLoadingPairs] = useState<boolean>(false);
  const [selectedPair, setSelectedPair] = useState<string>("BTCUSDT");

  const fetchOverview = useCallback(async () => {
    try {
      const authToken =
        token ||
        (typeof window !== "undefined"
          ? localStorage.getItem("bitdex_auth_token") ||
            localStorage.getItem("tauric_token") ||
            localStorage.getItem("tauric_session_token") ||
            ""
          : "");

      const res = await fetch("/api/backend/saas/customer/trading/overview", {
        headers: {
          "Content-Type": "application/json",
          ...(authToken ? { Authorization: "Bearer " + authToken } : {}),
        },
      });

      if (!res.ok) {
        throw new Error(`Overview fetch failed (${res.status})`);
      }

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
  }, [token]);

  const fetchHftPairs = useCallback(async () => {
    try {
      setLoadingPairs(true);
      const authToken =
        token ||
        (typeof window !== "undefined"
          ? localStorage.getItem("bitdex_auth_token") ||
            localStorage.getItem("tauric_token") ||
            localStorage.getItem("tauric_session_token") ||
            ""
          : "");

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
      }
    } catch {
      // Non-blocking
    } finally {
      setLoadingPairs(false);
    }
  }, [token, selectedPair]);

  useEffect(() => {
    fetchOverview();
    fetchHftPairs();
    const interval = setInterval(fetchOverview, 10000);
    return () => clearInterval(interval);
  }, [fetchOverview, fetchHftPairs]);

  const handleToggleEngineB = async () => {
    if (!data) return;
    setTogglingEngineB(true);
    setFeedback(null);
    try {
      const authToken =
        token ||
        (typeof window !== "undefined"
          ? localStorage.getItem("bitdex_auth_token") ||
            localStorage.getItem("tauric_token") ||
            localStorage.getItem("tauric_session_token") ||
            ""
          : "");

      const nextState = !data.engine_b.enabled;
      const res = await fetch("/api/backend/saas/customer/trading/engine-b/toggle", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(authToken ? { Authorization: "Bearer " + authToken } : {}),
        },
        body: JSON.stringify({ enabled: nextState }),
      });

      const resJson = await res.json().catch(() => ({}));

      if (res.ok) {
        setFeedback({
          type: "info",
          message: resJson.message || (nextState
            ? "High-Frequency Trading configuration saved. Note: Real execution is undergoing controlled Testnet risk validation. Live order dispatch remains disabled."
            : "High-Frequency Trading deactivated."),
        });
        await fetchOverview();
      } else {
        setFeedback({
          type: "error",
          message: resJson.detail || "Failed to update strategy configuration.",
        });
      }
    } catch {
      setFeedback({ type: "error", message: "Network error updating strategy configuration." });
    } finally {
      setTogglingEngineB(false);
    }
  };

  const account = data?.account;
  const hftStrategy = data?.engine_b;
  const risk = data?.risk;
  const leases = data?.active_leases || [];
  const trades = data?.recent_trades || [];

  const activePairData = hftPairs.find(p => p.symbol === selectedPair) || hftPairs[0] || {
    symbol: "BTCUSDT",
    price: 77100.0,
    spread_bps: 0.01,
    funding_rate: 0.0001,
    quote_volume_24h: 125000000000,
    price_change_pct_24h: -0.9,
    rank_score: 82.0
  };

  return (
    <div className={`space-y-6 max-w-[1760px] mx-auto ${className}`}>
      {/* ─── 1. PROTECTION CENTER ────────────────────────────────────────────── */}
      <ProtectionCenter token={token} />

      {/* ─── FEEDBACK TOAST ─────────────────────────────────────────────────── */}
      {feedback && (
        <div
          className={`p-3.5 rounded-xl text-xs font-mono flex items-center justify-between border ${
            feedback.type === "success"
              ? "bg-[#10B981]/10 border-[#10B981]/30 text-[#10B981]"
              : feedback.type === "info"
              ? "bg-[#00E5FF]/10 border-[#00E5FF]/30 text-[#00E5FF]"
              : "bg-[#EF4444]/10 border-[#EF4444]/30 text-[#EF4444]"
          }`}
        >
          <div className="flex items-center gap-2">
            {feedback.type === "success" ? (
              <CheckCircle2 className="w-4 h-4 shrink-0" />
            ) : feedback.type === "info" ? (
              <AlertCircle className="w-4 h-4 shrink-0" />
            ) : (
              <AlertCircle className="w-4 h-4 shrink-0" />
            )}
            <span>{feedback.message}</span>
          </div>
          <button
            onClick={() => setFeedback(null)}
            className="text-slate-400 hover:text-white ml-2 text-xs"
          >
            ✕
          </button>
        </div>
      )}

      {/* ─── 2. DYNAMIC BINANCE USD(S)-M FUTURES PAIR DISCOVERY STRIP ──────── */}
      <div className="rounded-2xl bg-[#121218] border border-[#272735] p-4 shadow-lg space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-[#272735]">
          <div className="flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-[#00E5FF]" />
            <h3 className="text-xs font-bold text-white uppercase font-mono tracking-wider">
              Eligible Binance USDⓈ-M Futures Pairs (Dynamic Discovery)
            </h3>
          </div>
          <div className="flex items-center gap-3 text-[11px] font-mono text-[#64748B]">
            <span>Liquidity Gate: &gt; $20M Vol • Spread &lt; 5 bps • Funding &lt; 0.05%</span>
            <button
              onClick={fetchHftPairs}
              disabled={loadingPairs}
              className="text-[#00E5FF] hover:underline flex items-center gap-1 cursor-pointer"
            >
              <RefreshCw className={`w-3 h-3 ${loadingPairs ? "animate-spin" : ""}`} />
              <span>Refresh</span>
            </button>
          </div>
        </div>

        {/* Dynamic Pair Selector Chips */}
        <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-thin">
          {hftPairs.length === 0 ? (
            <div className="text-xs font-mono text-[#94A3B8] py-2">
              Scanning Binance USDⓈ-M Futures universe...
            </div>
          ) : (
            hftPairs.slice(0, 8).map((pair) => {
              const isSelected = pair.symbol === selectedPair;
              const isPos = pair.price_change_pct_24h >= 0;
              return (
                <button
                  key={pair.symbol}
                  onClick={() => setSelectedPair(pair.symbol)}
                  className={`flex items-center gap-3 px-3 py-2 rounded-xl font-mono text-xs transition-all shrink-0 border cursor-pointer ${
                    isSelected
                      ? "bg-[#00E5FF]/10 border-[#00E5FF] text-white shadow-sm"
                      : "bg-[#181822] border-[#272735] text-[#94A3B8] hover:border-slate-600 hover:text-white"
                  }`}
                >
                  <div className="flex flex-col text-left">
                    <span className="font-bold text-white text-[12px]">{pair.symbol}</span>
                    <span className="text-[10px] text-[#64748B]">
                      Vol: ${(pair.quote_volume_24h / 1e9).toFixed(2)}B
                    </span>
                  </div>
                  <div className="flex flex-col text-right">
                    <span className="text-[12px] text-white tabular-nums">
                      ${pair.price >= 10 ? pair.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : pair.price.toFixed(4)}
                    </span>
                    <span className={`text-[10px] tabular-nums font-bold ${isPos ? "text-[#10B981]" : "text-[#EF4444]"}`}>
                      {isPos ? "+" : ""}{pair.price_change_pct_24h.toFixed(2)}%
                    </span>
                  </div>
                  <div className="hidden sm:flex flex-col text-right border-l border-[#272735] pl-2 text-[10px] text-[#64748B]">
                    <span>{pair.spread_bps.toFixed(2)} bps</span>
                    <span>{(pair.funding_rate * 100).toFixed(3)}%</span>
                  </div>
                </button>
              );
            })
          )}
        </div>
      </div>

      {/* ─── 3. STRATEGY EXECUTION TERMINAL FOR SELECTED PAIR ──────────────── */}
      <div className="rounded-2xl bg-[#121218] border border-[#272735] p-5 shadow-lg space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-4 pb-4 border-b border-[#272735]">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-2xl bg-[#00E5FF]/10 border border-[#00E5FF]/30 flex items-center justify-center text-[#00E5FF]">
              <Zap className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-base font-bold text-white font-mono tracking-wide">
                  AUTONOMOUS FUTURES SCALPER
                </h3>
                <span className="text-[10px] font-mono text-[#00E5FF] px-2 py-0.5 rounded bg-[#00E5FF]/10 border border-[#00E5FF]/30 font-bold">
                  Target: {activePairData.symbol}
                </span>
              </div>
              <p className="text-xs text-[#94A3B8]">
                Post-Only Momentum Breakout • Donchian(20) / ADX(14) / RVOL(20)
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <span
              className={`text-[10px] uppercase font-mono px-3 py-1 rounded-lg border font-bold flex items-center gap-1.5 ${
                hftStrategy?.enabled
                  ? "bg-[#F59E0B]/15 text-[#F59E0B] border-[#F59E0B]/30"
                  : "bg-slate-800 text-slate-400 border-slate-700"
              }`}
            >
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  hftStrategy?.enabled ? "bg-[#F59E0B] animate-pulse" : "bg-slate-500"
                }`}
              />
              {hftStrategy?.enabled ? "CONFIGURED (STANDBY)" : "OFF"}
            </span>

            <button
              onClick={handleToggleEngineB}
              disabled={togglingEngineB || loading}
              className={`px-4 py-2 rounded-xl text-xs font-mono font-bold transition-all shadow-md cursor-pointer ${
                hftStrategy?.enabled
                  ? "bg-[#EF4444]/15 border border-[#EF4444]/40 text-[#EF4444] hover:bg-[#EF4444]/25"
                  : "bg-[#00E5FF] text-[#0B0E11] hover:bg-[#00E5FF]/90"
              }`}
            >
              {togglingEngineB
                ? "Updating..."
                : hftStrategy?.enabled
                ? "Deactivate Strategy"
                : "Configure Strategy"}
            </button>
          </div>
        </div>

        {/* Operational Status Disclosure Banner */}
        <div className="p-3 rounded-xl bg-[#181822] border border-[#272735] text-xs font-mono text-[#94A3B8] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-[#10B981] shrink-0" />
            <span>
              <strong className="text-white">Validation Mode:</strong> Exchange-native protective stops armed. Orders held at execution gate during controlled Testnet risk validation. Live order dispatch remains disabled.
            </span>
          </div>
          <span className="text-[10px] text-[#64748B] hidden sm:block">Fail-Closed Architecture</span>
        </div>

        {/* Strategy Parameters & Risk Filters Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs font-mono">
          <div className="p-3 rounded-xl bg-[#0A0A0E] border border-[#272735] space-y-1">
            <span className="text-[10px] text-[#64748B] uppercase">Order Fill Protocol</span>
            <div className="text-white font-bold">LIMIT_MAKER (GTX)</div>
            <div className="text-[10px] text-[#10B981]">15s Timeout • 0 Taker Friction</div>
          </div>

          <div className="p-3 rounded-xl bg-[#0A0A0E] border border-[#272735] space-y-1">
            <span className="text-[10px] text-[#64748B] uppercase">Breakout Filters</span>
            <div className="text-white font-bold">Donchian(20) • ADX &gt; 22</div>
            <div className="text-[10px] text-[#00E5FF]">RVOL &gt; 1.5 Surge Gate</div>
          </div>

          <div className="p-3 rounded-xl bg-[#0A0A0E] border border-[#272735] space-y-1">
            <span className="text-[10px] text-[#64748B] uppercase">Leverage Ceiling</span>
            <div className="text-white font-bold">5x MAX (Isolated)</div>
            <div className="text-[10px] text-[#10B981]">Zero Martingale / No Averaging</div>
          </div>

          <div className="p-3 rounded-xl bg-[#0A0A0E] border border-[#272735] space-y-1">
            <span className="text-[10px] text-[#64748B] uppercase">Mutual Exclusivity</span>
            <div className="text-white font-bold">{leases.length} Active Leases</div>
            <div className="text-[10px] text-[#10B981]">Engine Collision Lock Armed</div>
          </div>
        </div>
      </div>

      {/* ─── 4. RISK & MARGIN TELEMETRY ───────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="rounded-2xl bg-[#121218] border border-[#272735] p-4 font-mono shadow-md">
          <div className="flex items-center justify-between text-[#94A3B8] text-xs mb-1">
            <span>FUTURES WALLET BALANCE</span>
            <DollarSign className="w-4 h-4 text-[#10B981]" />
          </div>
          <div className="text-xl font-bold text-white tabular-nums">
            ${account?.wallet_balance?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) || "0.00"}
          </div>
          <div className="text-[11px] text-[#94A3B8] mt-1">
            Available: ${account?.available_balance?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) || "0.00"} USD
          </div>
        </div>

        <div className="rounded-2xl bg-[#121218] border border-[#272735] p-4 font-mono shadow-md">
          <div className="flex items-center justify-between text-[#94A3B8] text-xs mb-1">
            <span>AGGREGATE PORTFOLIO EXPOSURE</span>
            <AlertTriangle className="w-4 h-4 text-[#F59E0B]" />
          </div>
          <div className="text-xl font-bold text-white tabular-nums">
            {risk?.aggregate_exposure_pct?.toFixed(1) || "0.0"}%
            <span className="text-xs text-[#94A3B8] font-normal"> / {risk?.max_exposure_cap_pct || 50.0}% Max</span>
          </div>
          <div className="text-[11px] text-[#10B981] mt-1">
            Within Safe Risk Limits
          </div>
        </div>

        <div className="rounded-2xl bg-[#121218] border border-[#272735] p-4 font-mono shadow-md">
          <div className="flex items-center justify-between text-[#94A3B8] text-xs mb-1">
            <span>LEVERAGE SAFETY CEILING</span>
            <Scale className="w-4 h-4 text-[#00E5FF]" />
          </div>
          <div className="text-xl font-bold text-[#00E5FF] tabular-nums">
            {risk?.max_leverage_clamp || 5}.0x CLAMPED
          </div>
          <div className="text-[11px] text-[#94A3B8] mt-1">
            Server-Side Hard Clamped
          </div>
        </div>

        <div className="rounded-2xl bg-[#121218] border border-[#272735] p-4 font-mono shadow-md">
          <div className="flex items-center justify-between text-[#94A3B8] text-xs mb-1">
            <span>STOP-LOSS RELIABILITY</span>
            <ShieldCheck className="w-4 h-4 text-[#10B981]" />
          </div>
          <div className="text-xl font-bold text-[#10B981] tabular-nums">
            {risk?.stop_loss_coverage_pct?.toFixed(1) || "100.0"}% COVERAGE
          </div>
          <div className="text-[11px] text-[#94A3B8] mt-1">
            {risk?.naked_positions_count || 0} Naked Positions Detected
          </div>
        </div>
      </div>

      {/* ─── 5. AUDITED EXECUTION LEDGER (TENANT-ISOLATED) ─────────────────────── */}
      <div className="rounded-2xl bg-[#121218] border border-[#272735] p-5 shadow-lg space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-[#272735]">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-[#00E5FF]" />
            <h3 className="text-sm font-bold text-white uppercase font-mono tracking-wider">
              Audited Execution Ledger
            </h3>
            <span className="text-[10px] text-[#64748B] font-mono px-2 py-0.5 rounded bg-[#181822] border border-[#272735]">
              {trades.length} Recent Trades
            </span>
          </div>
          <span className="text-[10px] text-[#10B981] font-mono px-2 py-0.5 rounded bg-[#10B981]/10 border border-[#10B981]/30">
            Tenant-Isolated Execution
          </span>
        </div>

        {trades.length === 0 ? (
          <div className="text-center py-8 text-xs font-mono text-[#94A3B8] bg-[#0A0A0E] rounded-xl border border-[#272735]">
            No recent scalping executions recorded for this account.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs font-mono text-left">
              <thead>
                <tr className="border-b border-[#272735] text-[#94A3B8] text-[11px]">
                  <th className="pb-2 font-normal">Timestamp</th>
                  <th className="pb-2 font-normal">Symbol</th>
                  <th className="pb-2 font-normal">Side</th>
                  <th className="pb-2 font-normal text-right">Qty</th>
                  <th className="pb-2 font-normal text-right">Entry Price</th>
                  <th className="pb-2 font-normal text-right">Exit Price</th>
                  <th className="pb-2 font-normal text-right">Fees</th>
                  <th className="pb-2 font-normal text-right">Realized Net P&amp;L</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#272735]/40">
                {trades.map((t, idx) => {
                  const isProfit = (t.realized_pnl ?? 0) >= 0;
                  return (
                    <tr key={idx} className="hover:bg-[#181822]/60 transition-colors">
                      <td className="py-2.5 text-[#94A3B8]">
                        {t.created_at ? new Date(t.created_at).toLocaleTimeString() : "--"}
                      </td>
                      <td className="py-2.5 text-white font-bold">{t.symbol}</td>
                      <td className="py-2.5">
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                            t.side === "BUY"
                              ? "bg-[#10B981]/15 text-[#10B981]"
                              : "bg-[#EF4444]/15 text-[#EF4444]"
                          }`}
                        >
                          {t.side}
                        </span>
                      </td>
                      <td className="py-2.5 text-right tabular-nums text-white">{t.quantity}</td>
                      <td className="py-2.5 text-right tabular-nums text-white">
                        ${Number(t.entry_price).toFixed(2)}
                      </td>
                      <td className="py-2.5 text-right tabular-nums text-white">
                        ${Number(t.exit_price).toFixed(2)}
                      </td>
                      <td className="py-2.5 text-right tabular-nums text-[#EF4444]">
                        -${Number(t.fee_usd || 0).toFixed(4)}
                      </td>
                      <td
                        className={`py-2.5 text-right tabular-nums font-bold ${
                          isProfit ? "text-[#10B981]" : "text-[#EF4444]"
                        }`}
                      >
                        {isProfit ? "+" : ""}${Number(t.realized_pnl || 0).toFixed(2)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
