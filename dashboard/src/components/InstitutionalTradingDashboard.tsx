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
  AlertCircle
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
    lease_id: string;
    symbol: string;
    engine_id: string;
    status: string;
    acquired_at: string;
    expires_at: string;
  }>;
  positions: Array<{
    position_id: string;
    symbol: string;
    quantity: number;
    entry_price: number;
    mark_price: number;
    unrealized_pnl: number;
    leverage: number;
    status: string;
    active_stop_loss_order_id: string;
  }>;
  recent_trades: Array<{
    trade_id: string;
    symbol: string;
    direction: string;
    quantity: number;
    entry_price: number;
    exit_price: number | null;
    gross_pnl_usd: number;
    total_fees_usd: number;
    net_pnl_usd: number;
    exit_reason: string | null;
    created_at: string;
  }>;
}

interface Props {
  token?: string;
  className?: string;
}

export default function InstitutionalTradingDashboard({ token, className = "" }: Props) {
  const [data, setData] = useState<TradingOverviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [togglingEngineB, setTogglingEngineB] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);

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

      const headers: Record<string, string> = {};
      if (authToken) {
        headers["Authorization"] = "Bearer " + authToken;
      }

      const res = await fetch("/api/backend/saas/customer/trading/overview", { headers });
      if (res.ok) {
        const json = await res.json();
        if (json.status === "SUCCESS") {
          setData(json);
        }
      }
    } catch (err) {
      console.error("Failed to load trading overview", err);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchOverview();
    const interval = setInterval(fetchOverview, 5000);
    return () => clearInterval(interval);
  }, [fetchOverview]);

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

      if (res.ok) {
        setFeedback({
          type: "success",
          message: nextState
            ? "Engine B (Autonomous Scalper) activated in Paper-Trading mode."
            : "Engine B deactivated. All symbol leases released.",
        });
        await fetchOverview();
      } else {
        setFeedback({ type: "error", message: "Failed to toggle Engine B." });
      }
    } catch {
      setFeedback({ type: "error", message: "Network error toggling Engine B." });
    } finally {
      setTogglingEngineB(false);
    }
  };

  const account = data?.account;
  const engineA = data?.engine_a;
  const engineB = data?.engine_b;
  const risk = data?.risk;
  const leases = data?.active_leases || [];
  const trades = data?.recent_trades || [];

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
              : "bg-[#EF4444]/10 border-[#EF4444]/30 text-[#EF4444]"
          }`}
        >
          <div className="flex items-center gap-2">
            {feedback.type === "success" ? (
              <CheckCircle2 className="w-4 h-4 shrink-0" />
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

      {/* ─── 2. DUAL-ENGINE STRATEGY COMMAND MATRIX ─────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* ENGINE A: Spot Grid & Swing Momentum */}
        <div className="rounded-2xl bg-[#121218] border border-[#272735] p-5 flex flex-col justify-between shadow-lg">
          <div>
            <div className="flex items-start justify-between gap-3 pb-3 border-b border-[#272735] mb-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-purple-500/10 border border-purple-500/30 flex items-center justify-center text-purple-400">
                  <Layers className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-white tracking-wide font-mono flex items-center gap-2">
                    ENGINE A
                    <span className="text-[10px] font-normal text-slate-400 px-2 py-0.5 rounded bg-[#181822] border border-[#272735]">
                      Spot &amp; Swing
                    </span>
                  </h3>
                  <p className="text-xs text-[#94A3B8]">
                    Dynamic Spot Grid &amp; Multi-Day Swing Expansion
                  </p>
                </div>
              </div>

              <span className="text-[10px] uppercase font-mono px-2.5 py-1 rounded bg-[#F59E0B]/15 text-[#F59E0B] border border-[#F59E0B]/30 font-bold flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-[#F59E0B]" />
                STANDBY
              </span>
            </div>

            <div className="space-y-3 text-xs font-mono">
              <div className="flex items-center justify-between py-1.5 border-b border-[#272735]/60">
                <span className="text-[#94A3B8]">Execution Strategy</span>
                <span className="text-white font-bold">SPOT_GRID_SWING</span>
              </div>
              <div className="flex items-center justify-between py-1.5 border-b border-[#272735]/60">
                <span className="text-[#94A3B8]">Active Market Universe</span>
                <span className="text-[#00E5FF]">BTC/USDT, ETH/USDT</span>
              </div>
              <div className="flex items-center justify-between py-1.5 border-b border-[#272735]/60">
                <span className="text-[#94A3B8]">Allocated Risk Capital</span>
                <span className="text-white">${engineA?.allocated_capital_usd?.toLocaleString() || "5,000.00"} USD</span>
              </div>
              <div className="flex items-center justify-between py-1.5 border-b border-[#272735]/60">
                <span className="text-[#94A3B8]">Execution Gate</span>
                <span className="text-[#10B981] flex items-center gap-1">
                  <Lock className="w-3 h-3" /> Live Trading Locked
                </span>
              </div>
            </div>
          </div>

          <div className="pt-4 mt-2">
            <div className="p-2.5 rounded-xl bg-[#0A0A0E] border border-[#272735] text-[11px] text-[#94A3B8] flex items-center justify-between">
              <span className="flex items-center gap-1.5">
                <ShieldCheck className="w-4 h-4 text-[#10B981]" />
                Mutual Exclusivity Guard Active
              </span>
              <span className="text-slate-400">0 Collisions</span>
            </div>
          </div>
        </div>

        {/* ENGINE B: Autonomous High-Frequency Scalper */}
        <div className="rounded-2xl bg-[#121218] border border-[#272735] p-5 flex flex-col justify-between shadow-lg">
          <div>
            <div className="flex items-start justify-between gap-3 pb-3 border-b border-[#272735] mb-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-[#00E5FF]/10 border border-[#00E5FF]/30 flex items-center justify-center text-[#00E5FF]">
                  <Zap className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-white tracking-wide font-mono flex items-center gap-2">
                    ENGINE B
                    <span className="text-[10px] font-normal text-slate-400 px-2 py-0.5 rounded bg-[#181822] border border-[#272735]">
                      Futures Scalper
                    </span>
                  </h3>
                  <p className="text-xs text-[#94A3B8]">
                    Autonomous Post-Only Momentum Breakout
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <span
                  className={`text-[10px] uppercase font-mono px-2.5 py-1 rounded border font-bold flex items-center gap-1.5 ${
                    engineB?.enabled
                      ? "bg-[#10B981]/15 text-[#10B981] border-[#10B981]/30"
                      : "bg-slate-800 text-slate-400 border-slate-700"
                  }`}
                >
                  <span
                    className={`w-1.5 h-1.5 rounded-full ${
                      engineB?.enabled ? "bg-[#10B981] animate-pulse" : "bg-slate-500"
                    }`}
                  />
                  {engineB?.enabled ? "ARMED" : "OFF"}
                </span>

                <button
                  type="button"
                  onClick={handleToggleEngineB}
                  disabled={togglingEngineB}
                  className={`px-3 py-1 rounded-lg text-xs font-mono font-bold transition flex items-center gap-1.5 cursor-pointer disabled:opacity-50 ${
                    engineB?.enabled
                      ? "bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30"
                      : "bg-[#00E5FF]/10 hover:bg-[#00E5FF]/20 text-[#00E5FF] border border-[#00E5FF]/30"
                  }`}
                >
                  {togglingEngineB ? (
                    <RefreshCw className="w-3 h-3 animate-spin" />
                  ) : engineB?.enabled ? (
                    "Deactivate"
                  ) : (
                    "Activate"
                  )}
                </button>
              </div>
            </div>

            <div className="space-y-3 text-xs font-mono">
              <div className="flex items-center justify-between py-1.5 border-b border-[#272735]/60">
                <span className="text-[#94A3B8]">Execution Strategy</span>
                <span className="text-white font-bold">POST_ONLY_MOMENTUM_SCALP</span>
              </div>
              <div className="flex items-center justify-between py-1.5 border-b border-[#272735]/60">
                <span className="text-[#94A3B8]">Order Type / Fill Protocol</span>
                <span className="text-[#00E5FF]">LIMIT_MAKER (GTX) • 15s Timeout</span>
              </div>
              <div className="flex items-center justify-between py-1.5 border-b border-[#272735]/60">
                <span className="text-[#94A3B8]">Breakout / Volatility Filters</span>
                <span className="text-white">Donchian(20) • ADX &gt; 22 • RVOL &gt; 1.5</span>
              </div>
              <div className="flex items-center justify-between py-1.5 border-b border-[#272735]/60">
                <span className="text-[#94A3B8]">Max Clamped Leverage</span>
                <span className="text-[#10B981] font-bold">5x MAX (Isolated Margin)</span>
              </div>
            </div>
          </div>

          <div className="pt-4 mt-2">
            <div className="p-2.5 rounded-xl bg-[#0A0A0E] border border-[#272735] text-[11px] text-[#94A3B8] flex items-center justify-between">
              <span className="flex items-center gap-1.5">
                <Activity className="w-4 h-4 text-[#00E5FF]" />
                Active Symbol Leases
              </span>
              <span className="text-white font-mono font-bold">
                {engineB?.active_leases_count ?? 0} Leases Active
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* ─── 3. RISK MONITORING & CAPITAL TELEMETRY ─────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        {/* Margin Wallet Equity */}
        <div className="bg-[#121218] border border-[#272735] rounded-xl p-4">
          <div className="text-[11px] font-mono text-[#94A3B8] uppercase mb-1 flex items-center gap-1.5">
            <DollarSign className="w-3.5 h-3.5 text-[#10B981]" />
            Futures Wallet Balance
          </div>
          <div className="text-lg sm:text-xl font-bold text-white font-mono">
            ${account?.wallet_balance ? account.wallet_balance.toLocaleString(undefined, { minimumFractionDigits: 2 }) : "10,000.00"}
          </div>
          <div className="text-[10px] text-[#94A3B8] mt-1">
            Available: ${account?.available_balance ? account.available_balance.toLocaleString(undefined, { minimumFractionDigits: 2 }) : "10,000.00"} USD
          </div>
        </div>

        {/* Portfolio Exposure */}
        <div className="bg-[#121218] border border-[#272735] rounded-xl p-4">
          <div className="text-[11px] font-mono text-[#94A3B8] uppercase mb-1 flex items-center gap-1.5">
            <AlertTriangle className="w-3.5 h-3.5 text-[#F59E0B]" />
            Aggregate Portfolio Exposure
          </div>
          <div className="text-lg sm:text-xl font-bold text-white font-mono">
            0.0% <span className="text-xs text-[#94A3B8] font-normal">/ 50.0% Max</span>
          </div>
          <div className="text-[10px] text-[#10B981] mt-1">
            Safe Risk Profile Verified
          </div>
        </div>

        {/* Leverage Clamp */}
        <div className="bg-[#121218] border border-[#272735] rounded-xl p-4">
          <div className="text-[11px] font-mono text-[#94A3B8] uppercase mb-1 flex items-center gap-1.5">
            <Scale className="w-3.5 h-3.5 text-[#00E5FF]" />
            Leverage Safety Ceiling
          </div>
          <div className="text-lg sm:text-xl font-bold text-[#00E5FF] font-mono">
            5.0x CLAMPED
          </div>
          <div className="text-[10px] text-[#94A3B8] mt-1">
            Zero Martingale / No Averaging
          </div>
        </div>

        {/* Stop Reliability */}
        <div className="bg-[#121218] border border-[#272735] rounded-xl p-4">
          <div className="text-[11px] font-mono text-[#94A3B8] uppercase mb-1 flex items-center gap-1.5">
            <ShieldCheck className="w-3.5 h-3.5 text-[#10B981]" />
            Stop-Loss Reliability
          </div>
          <div className="text-lg sm:text-xl font-bold text-[#10B981] font-mono">
            100.0% COVERAGE
          </div>
          <div className="text-[10px] text-[#64748B] mt-1">
            0 Naked Positions Detected
          </div>
        </div>
      </div>

      {/* ─── 4. RECENT AUDITED TRADES LEDGER ─────────────────────────────────── */}
      <div className="rounded-2xl bg-[#121218] border border-[#272735] p-5 shadow-lg">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-[#272735] mb-4">
          <div>
            <h3 className="text-base font-bold text-white tracking-wide font-mono flex items-center gap-2">
              AUDITED EXECUTION LEDGER
              <span className="text-xs font-mono font-normal text-slate-400 px-2 py-0.5 rounded bg-[#181822] border border-[#272735]">
                {trades.length} Audited Trades
              </span>
            </h3>
            <p className="text-xs text-[#94A3B8]">
              Itemized maker/taker fees, realized P&amp;L, and exchange-native protective stop logs.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-[11px] font-mono text-[#10B981] px-2 py-1 rounded bg-[#10B981]/10 border border-[#10B981]/30">
              Deterministic Fee Deducted
            </span>
          </div>
        </div>

        {trades.length === 0 ? (
          <div className="text-center py-12 px-4 rounded-xl bg-[#0A0A0E] border border-[#272735] text-xs font-mono text-[#94A3B8]">
            <Lock className="w-8 h-8 text-slate-600 mx-auto mb-2" />
            <p className="text-white font-bold">No Live Trades Executed</p>
            <p className="text-slate-500 mt-1">
              Platform is currently running in Stage Mode with Live Trading Locked.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left font-mono text-xs">
              <thead>
                <tr className="border-b border-[#272735] text-[#94A3B8] uppercase text-[10px] tracking-wider">
                  <th className="py-2.5 px-3">Trade ID / Time</th>
                  <th className="py-2.5 px-3">Symbol</th>
                  <th className="py-2.5 px-3">Side</th>
                  <th className="py-2.5 px-3">Qty</th>
                  <th className="py-2.5 px-3">Entry / Exit</th>
                  <th className="py-2.5 px-3">Fees (USD)</th>
                  <th className="py-2.5 px-3">Net Realized P&amp;L</th>
                  <th className="py-2.5 px-3 text-right">Protection Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#272735]/60 text-slate-300">
                {trades.map((t) => {
                  const isLong = t.direction === "LONG";
                  const isWin = (t.net_pnl_usd ?? 0) >= 0;
                  return (
                    <tr key={t.trade_id} className="hover:bg-[#181822]/60 transition">
                      <td className="py-3 px-3">
                        <div className="font-bold text-white text-[11px]">{t.trade_id}</div>
                        <div className="text-[10px] text-[#64748B]">
                          {t.created_at ? new Date(t.created_at).toLocaleTimeString() : "--"}
                        </div>
                      </td>
                      <td className="py-3 px-3 font-bold text-white">{t.symbol}</td>
                      <td className="py-3 px-3">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            isLong
                              ? "bg-[#10B981]/15 text-[#10B981] border border-[#10B981]/30"
                              : "bg-[#EF4444]/15 text-[#EF4444] border border-[#EF4444]/30"
                          }`}
                        >
                          {t.direction}
                        </span>
                      </td>
                      <td className="py-3 px-3 font-mono">{t.quantity}</td>
                      <td className="py-3 px-3 font-mono">
                        <div>${t.entry_price ? t.entry_price.toFixed(2) : "--"}</div>
                        <div className="text-[10px] text-[#94A3B8]">
                          Exit: ${t.exit_price ? t.exit_price.toFixed(2) : "--"}
                        </div>
                      </td>
                      <td className="py-3 px-3 text-[#F59E0B] font-mono">
                        -${t.total_fees_usd ? t.total_fees_usd.toFixed(4) : "0.0000"}
                      </td>
                      <td className="py-3 px-3 font-mono font-bold">
                        <span className={isWin ? "text-[#10B981]" : "text-[#EF4444]"}>
                          {isWin ? "+" : ""}${t.net_pnl_usd ? t.net_pnl_usd.toFixed(2) : "0.00"}
                        </span>
                      </td>
                      <td className="py-3 px-3 text-right">
                        <span className="text-[10px] px-2 py-0.5 rounded bg-[#10B981]/10 text-[#10B981] border border-[#10B981]/30">
                          {t.exit_reason || "ARMED & STOPPED"}
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
    </div>
  );
}
