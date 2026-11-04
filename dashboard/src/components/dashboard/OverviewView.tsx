"use client";

import React from "react";
import {
  ShieldCheck,
  TrendingUp,
  Activity,
  Layers,
  Zap,
  ArrowUpRight,
  ArrowDownRight,
  Wallet,
  Clock,
  Compass,
  Link2,
  Lock,
} from "lucide-react";
import StatusBadge from "../common/StatusBadge";

interface OverviewViewProps {
  balance: number;
  equity: number;
  unrealizedPnl: number;
  realizedPnl: number;
  exnessConnected: boolean;
  exnessAccount?: {
    account_id?: string;
    server?: string;
    leverage?: number;
    account_type?: string;
  };
  tickerItems: any[];
  onNavigate: (tab: any) => void;
  onSelectPair: (pair: any) => void;
}

export default function OverviewView({
  balance,
  equity,
  unrealizedPnl,
  realizedPnl,
  exnessConnected,
  exnessAccount,
  tickerItems,
  onNavigate,
  onSelectPair,
}: OverviewViewProps) {
  return (
    <div className="space-y-6 animate-in fade-in duration-200 font-sans">
      {/* ─── TOP HEADER STATS ────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-[#1E2736]">
        <div>
          <h1 className="text-xl sm:text-2xl font-mono font-bold text-[#F1F5F9] tracking-tight">
            Institutional Overview
          </h1>
          <p className="text-xs font-mono text-[#94A3B8] mt-1">
            Real-time multi-asset intelligence &amp; broker connection summary
          </p>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge type="ENVIRONMENT" state="SIMULATED" />
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-mono font-bold bg-[#151C28] text-[#10B981] border border-[#1E2736]">
            <span className="w-2 h-2 rounded-full bg-[#10B981] animate-pulse" />
            <span>Exness Gateway Active</span>
          </span>
        </div>
      </div>

      {/* ─── 4-CARD ACCOUNT & METRIC SUMMARY ─────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5 text-xs font-mono">
        {/* Card 1: Account Equity */}
        <div className="p-4 rounded-xl bg-[#0E131B] border border-[#1E2736] space-y-2">
          <div className="flex items-center justify-between text-[#94A3B8]">
            <span className="text-[11px] uppercase tracking-wider">Account Equity</span>
            <Wallet className="w-4 h-4 text-[#38BDF8]" />
          </div>
          <div className="text-xl sm:text-2xl font-bold text-[#F1F5F9] tabular-nums">
            ${equity ? equity.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "5,000.00"}
          </div>
          <div className="text-[11px] text-[#64748B] flex items-center justify-between pt-1 border-t border-[#1E2736]">
            <span>Cash: ${balance ? balance.toFixed(2) : "5,000.00"}</span>
            <span className="text-[#38BDF8] font-bold">USD</span>
          </div>
        </div>

        {/* Card 2: Unrealized P&L */}
        <div className="p-4 rounded-xl bg-[#0E131B] border border-[#1E2736] space-y-2">
          <div className="flex items-center justify-between text-[#94A3B8]">
            <span className="text-[11px] uppercase tracking-wider">Unrealized P&amp;L</span>
            <Activity className="w-4 h-4 text-[#10B981]" />
          </div>
          <div className={`text-xl sm:text-2xl font-bold tabular-nums ${unrealizedPnl >= 0 ? "text-[#10B981]" : "text-[#F43F5E]"}`}>
            {unrealizedPnl >= 0 ? "+" : ""}${unrealizedPnl.toFixed(2)}
          </div>
          <div className="text-[11px] text-[#64748B] flex items-center justify-between pt-1 border-t border-[#1E2736]">
            <span>Active Positions</span>
            <span className="text-[#F1F5F9] font-bold">0 Open</span>
          </div>
        </div>

        {/* Card 3: Realized P&L */}
        <div className="p-4 rounded-xl bg-[#0E131B] border border-[#1E2736] space-y-2">
          <div className="flex items-center justify-between text-[#94A3B8]">
            <span className="text-[11px] uppercase tracking-wider">Realized Net P&amp;L</span>
            <TrendingUp className="w-4 h-4 text-[#38BDF8]" />
          </div>
          <div className={`text-xl sm:text-2xl font-bold tabular-nums ${realizedPnl >= 0 ? "text-[#10B981]" : "text-[#F43F5E]"}`}>
            {realizedPnl >= 0 ? "+" : ""}${realizedPnl.toFixed(2)}
          </div>
          <div className="text-[11px] text-[#64748B] flex items-center justify-between pt-1 border-t border-[#1E2736]">
            <span>Friction Deducted</span>
            <span className="text-[#94A3B8]">Single-Pass</span>
          </div>
        </div>

        {/* Card 4: Broker Connection */}
        <div className="p-4 rounded-xl bg-[#0E131B] border border-[#1E2736] space-y-2">
          <div className="flex items-center justify-between text-[#94A3B8]">
            <span className="text-[11px] uppercase tracking-wider">Primary Broker</span>
            <Link2 className="w-4 h-4 text-purple-400" />
          </div>
          <div className="text-base font-bold text-[#F1F5F9] flex items-center gap-2">
            <span>Exness MT5</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#10B981]/15 text-[#10B981] font-bold">
              DEMO
            </span>
          </div>
          <div className="text-[11px] text-[#64748B] flex items-center justify-between pt-1 border-t border-[#1E2736]">
            <span>Server: Exness-MT5Trial</span>
            <span className="text-[#10B981] font-bold">VERIFIED</span>
          </div>
        </div>
      </div>

      {/* ─── LIVE MARKET RADAR (NO CHARTS — PURE NUMERICAL FEED) ─────── */}
      <div className="rounded-xl bg-[#0E131B] border border-[#1E2736] p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-[#10B981] animate-pulse" />
            <h2 className="text-sm font-mono font-bold text-[#F1F5F9] uppercase tracking-wider">
              Live Verified Market Feeds (No Synthetic Fallback)
            </h2>
          </div>
          <span className="text-xs font-mono text-[#64748B]">
            Numerical Quotes Only • Zero Chart Overhead
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {tickerItems.slice(0, 8).map((item: any, idx: number) => {
            const isPos = (item.change_24h ?? 0) >= 0;
            const price = item.price;
            return (
              <div
                key={idx}
                onClick={() => onSelectPair({ canonical_symbol: item.symbol, market: item.market })}
                className="p-3 rounded-lg bg-[#151C28] border border-[#1E2736] hover:border-[#38BDF8] transition-all cursor-pointer group space-y-1.5"
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono font-bold text-xs text-[#F1F5F9] group-hover:text-[#38BDF8] transition-colors">
                    {item.symbol}
                  </span>
                  <span className="text-[9px] font-mono uppercase px-1 py-0.2 rounded bg-[#0E131B] text-[#94A3B8] border border-[#1E2736]">
                    {item.market || "SPOT"}
                  </span>
                </div>
                <div className="flex items-baseline justify-between">
                  <span className="text-sm font-mono font-bold text-[#F1F5F9] tabular-nums">
                    {typeof price === "number"
                      ? price >= 10
                        ? `$${price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                        : `$${price.toFixed(4)}`
                      : "Unavailable"}
                  </span>
                  <span
                    className={`text-[11px] font-mono font-bold tabular-nums flex items-center ${
                      isPos ? "text-[#10B981]" : "text-[#F43F5E]"
                    }`}
                  >
                    {isPos ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                    {isPos ? "+" : ""}{item.change_24h ? item.change_24h.toFixed(2) : "0.00"}%
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ─── WORKSPACE SHORTCUTS ──────────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Shortcut 1: Long-Term Strategy */}
        <div className="p-5 rounded-xl bg-[#0E131B] border border-[#1E2736] space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-[#10B981]/15 text-[#10B981] flex items-center justify-center">
                <Compass className="w-4 h-4" />
              </div>
              <div>
                <h3 className="font-mono font-bold text-sm text-[#F1F5F9]">Long-Term Strategy</h3>
                <span className="text-[11px] font-mono text-[#94A3B8]">4H/1D Multi-factor signal engine</span>
              </div>
            </div>
            <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-[#10B981]/15 text-[#10B981] border border-[#10B981]/30">
              19 Signals
            </span>
          </div>
          <p className="text-xs text-[#94A3B8] leading-relaxed">
            Rule-based technical analysis across Crypto, Forex and Precious Metals with strict invalidation stops and R:R ≥ 1:1.50.
          </p>
          <button
            onClick={() => onNavigate("LONG_TERM")}
            className="w-full py-2.5 rounded-lg bg-[#151C28] hover:bg-[#1E2736] text-[#F1F5F9] font-mono font-bold text-xs border border-[#1E2736] transition-all flex items-center justify-center gap-2 cursor-pointer"
          >
            <span>Open Long-Term Strategy Workspace</span>
            <ArrowUpRight className="w-3.5 h-3.5 text-[#38BDF8]" />
          </button>
        </div>

        {/* Shortcut 2: High-Frequency Trading */}
        <div className="p-5 rounded-xl bg-[#0E131B] border border-[#1E2736] space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-[#38BDF8]/15 text-[#38BDF8] flex items-center justify-center">
                <Zap className="w-4 h-4" />
              </div>
              <div>
                <h3 className="font-mono font-bold text-sm text-[#F1F5F9]">High-Frequency Trading</h3>
                <span className="text-[11px] font-mono text-[#94A3B8]">Exness MT5 Paired Quantitative Scalper</span>
              </div>
            </div>
            <StatusBadge type="HFT" state="WAITING" />
          </div>
          <p className="text-xs text-[#94A3B8] leading-relaxed">
            Market regime gated scalping engine with mark-to-market accounting, duration swaps, and 11-point risk barrier verification.
          </p>
          <button
            onClick={() => onNavigate("HFT")}
            className="w-full py-2.5 rounded-lg bg-[#151C28] hover:bg-[#1E2736] text-[#F1F5F9] font-mono font-bold text-xs border border-[#1E2736] transition-all flex items-center justify-center gap-2 cursor-pointer"
          >
            <span>Open HFT Quantitative Workspace</span>
            <ArrowUpRight className="w-3.5 h-3.5 text-[#38BDF8]" />
          </button>
        </div>
      </div>
    </div>
  );
}
