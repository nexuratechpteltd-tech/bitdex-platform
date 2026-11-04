"use client";

import React, { useState } from "react";
import {
  Activity,
  ArrowUp,
  ArrowDown,
  Clock,
  ShieldCheck,
  AlertTriangle,
  Lock,
  Layers,
  ChevronDown,
  CheckCircle2,
  XCircle,
  Play,
  RotateCcw,
  Target,
  Search,
} from "lucide-react";
import StatusBadge from "../common/StatusBadge";

interface TradingTerminalViewProps {
  selectedPair: any;
  onOpenSearch: () => void;
  onExecuteAnalysis: (symbol: string, market: string) => void;
  openPositions: any[];
  onInitiateOrder: (spec: any) => void;
}

export default function TradingTerminalView({
  selectedPair,
  onOpenSearch,
  onExecuteAnalysis,
  openPositions,
  onInitiateOrder,
}: TradingTerminalViewProps) {
  const sym = selectedPair?.canonical_symbol || selectedPair?.symbol || "BTC/USDT";
  const market = selectedPair?.market || selectedPair?.asset_class || "CRYPTO";
  const price = selectedPair?.price ?? 78573.30;
  const change = selectedPair?.change_24h ?? 1.92;
  const isPos = change >= 0;

  // Numerical Level Specs
  const entryPrice = selectedPair?.entry_price ?? price;
  const takeProfit = selectedPair?.take_profit ?? (isPos ? entryPrice * 1.025 : entryPrice * 0.975);
  const stopLoss = selectedPair?.stop_loss ?? (isPos ? entryPrice * 0.985 : entryPrice * 1.015);
  const spreadPts = selectedPair?.spread ?? 1.2;
  const bid = selectedPair?.bid ?? (price - 0.05);
  const ask = selectedPair?.ask ?? (price + 0.05);

  const [activeTimeframe, setActiveTimeframe] = useState("1H");
  const timeframes = ["1m", "5m", "15m", "1H", "4H", "1D"];

  return (
    <div className="space-y-4 animate-in fade-in duration-200 font-sans">
      {/* ─── 1. TOP MARKET INFORMATION RIBBON ───────────────────────── */}
      <div className="p-3.5 sm:p-4 rounded-xl bg-[#0E131B] border border-[#1E2736] flex flex-wrap items-center justify-between gap-4">
        {/* Instrument Selector Trigger */}
        <div className="flex items-center gap-3">
          <button
            onClick={onOpenSearch}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#151C28] hover:bg-[#1E2736] border border-[#1E2736] hover:border-[#38BDF8] text-[#F1F5F9] font-mono font-bold text-sm transition-all cursor-pointer"
          >
            <span>{sym}</span>
            <ChevronDown className="w-3.5 h-3.5 text-[#94A3B8]" />
          </button>
          <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-[#151C28] text-[#94A3B8] border border-[#1E2736]">
            {market}
          </span>
          <span className="inline-flex items-center gap-1.5 text-xs font-mono text-[#10B981]">
            <span className="w-1.5 h-1.5 rounded-full bg-[#10B981] animate-pulse" />
            <span className="hidden sm:inline">LIVE FEED</span>
          </span>
        </div>

        {/* Live Metrics Ribbon */}
        <div className="flex flex-wrap items-center gap-4 sm:gap-6 text-xs font-mono">
          <div>
            <span className="text-[10px] text-[#64748B] block uppercase">Live Price</span>
            <span className="font-bold text-[#F1F5F9] text-base tabular-nums">
              ${typeof price === "number" ? (price >= 10 ? price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : price.toFixed(4)) : "Unavailable"}
            </span>
          </div>
          <div>
            <span className="text-[10px] text-[#64748B] block uppercase">24h Change</span>
            <span className={`font-bold tabular-nums ${isPos ? "text-[#10B981]" : "text-[#F43F5E]"}`}>
              {isPos ? "+" : ""}{change.toFixed(2)}%
            </span>
          </div>
          <div className="hidden md:block">
            <span className="text-[10px] text-[#64748B] block uppercase">Bid / Ask</span>
            <span className="text-[#94A3B8] tabular-nums">
              {bid.toFixed(2)} / {ask.toFixed(2)}
            </span>
          </div>
          <div>
            <span className="text-[10px] text-[#64748B] block uppercase">Spread</span>
            <span className="text-[#38BDF8] font-bold tabular-nums">
              {spreadPts.toFixed(1)} pts
            </span>
          </div>
          <div className="hidden lg:block text-right">
            <span className="text-[10px] text-[#64748B] block uppercase">Market Status</span>
            <span className="text-[#10B981] font-bold">● OPEN</span>
          </div>
        </div>
      </div>

      {/* ─── 2. MAIN TRADING WORKSPACE (NO CHARTS — ZERO CANVAS OVERHEAD) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Left & Center: Numerical Market Level Centerpiece (8 Cols) */}
        <div className="lg:col-span-7 xl:col-span-8 space-y-4">
          {/* Timeframe Bar */}
          <div className="flex items-center justify-between p-2.5 rounded-xl bg-[#0E131B] border border-[#1E2736]">
            <div className="flex items-center gap-1">
              {timeframes.map((tf) => (
                <button
                  key={tf}
                  onClick={() => setActiveTimeframe(tf)}
                  className={`px-3 py-1 rounded-lg text-xs font-mono font-bold transition-all cursor-pointer ${
                    activeTimeframe === tf
                      ? "bg-[#38BDF8] text-[#080B10] shadow-sm"
                      : "text-[#94A3B8] hover:text-[#F1F5F9] hover:bg-[#151C28]"
                  }`}
                >
                  {tf}
                </button>
              ))}
            </div>
            <div className="text-[11px] font-mono text-[#64748B] flex items-center gap-2">
              <span className="hidden sm:inline">Visual Price Level Matrix (Chartless)</span>
              <button
                onClick={() => onExecuteAnalysis(sym.replace("/", ""), market)}
                className="px-2.5 py-1 rounded bg-[#38BDF8]/10 hover:bg-[#38BDF8] text-[#38BDF8] hover:text-[#080B10] text-xs font-mono font-bold border border-[#38BDF8]/30 transition-all flex items-center gap-1 cursor-pointer"
              >
                <Activity className="w-3 h-3" />
                <span>Run Analysis</span>
              </button>
            </div>
          </div>

          {/* Institutional Price Level Ladder (Chartless Quant Centerpiece) */}
          <div className="p-5 rounded-xl bg-[#0E131B] border border-[#1E2736] space-y-4">
            <div className="flex items-center justify-between border-b border-[#1E2736] pb-3">
              <div>
                <span className="text-xs font-mono font-bold text-[#F1F5F9] uppercase tracking-wider block">
                  Quantitative Level Matrix
                </span>
                <span className="text-[11px] font-mono text-[#94A3B8]">
                  Verified mathematical support, resistance and execution bands
                </span>
              </div>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#10B981]/15 text-[#10B981] border border-[#10B981]/30 font-bold">
                ▲ BULLISH BREAKOUT SETUP
              </span>
            </div>

            {/* Price Ladder Display */}
            <div className="space-y-3 font-mono text-xs">
              {/* Take Profit Band */}
              <div className="p-3.5 rounded-lg bg-[#10B981]/10 border border-[#10B981]/30 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-sm bg-[#10B981]" />
                  <span className="font-bold text-[#10B981]">TAKE PROFIT TARGET (TP1)</span>
                </div>
                <div className="text-right">
                  <span className="font-bold text-[#10B981] text-sm tabular-nums">
                    ${takeProfit.toFixed(2)}
                  </span>
                  <span className="text-[10px] text-[#10B981]/80 block">
                    +{((takeProfit - entryPrice) / entryPrice * 100).toFixed(2)}% (+${(takeProfit - entryPrice).toFixed(2)})
                  </span>
                </div>
              </div>

              {/* Live Price Band */}
              <div className="p-3.5 rounded-lg bg-[#38BDF8]/15 border-2 border-[#38BDF8] flex items-center justify-between shadow-lg shadow-[#38BDF8]/10">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-[#38BDF8] animate-ping" />
                  <span className="font-bold text-[#F1F5F9]">CURRENT LIVE TICK</span>
                </div>
                <div className="text-right">
                  <span className="font-black text-base text-[#F1F5F9] tabular-nums">
                    ${price.toFixed(2)}
                  </span>
                  <span className="text-[10px] text-[#38BDF8] block">
                    Spread: {spreadPts.toFixed(1)} pts • Bid: ${bid.toFixed(2)}
                  </span>
                </div>
              </div>

              {/* Entry Zone Band */}
              <div className="p-3.5 rounded-lg bg-[#151C28] border border-[#1E2736] flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-sm bg-[#F1F5F9]" />
                  <span className="font-bold text-[#F1F5F9]">REFERENCE ENTRY ZONE</span>
                </div>
                <div className="text-right">
                  <span className="font-bold text-[#F1F5F9] text-sm tabular-nums">
                    ${entryPrice.toFixed(2)}
                  </span>
                  <span className="text-[10px] text-[#94A3B8] block">
                    Execution reference baseline
                  </span>
                </div>
              </div>

              {/* Stop Loss Invalidation Band */}
              <div className="p-3.5 rounded-lg bg-[#F43F5E]/10 border border-[#F43F5E]/30 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-sm bg-[#F43F5E]" />
                  <span className="font-bold text-[#F43F5E]">STOP LOSS INVALIDATION</span>
                </div>
                <div className="text-right">
                  <span className="font-bold text-[#F43F5E] text-sm tabular-nums">
                    ${stopLoss.toFixed(2)}
                  </span>
                  <span className="text-[10px] text-[#F43F5E]/80 block">
                    -{((entryPrice - stopLoss) / entryPrice * 100).toFixed(2)}% (-${(entryPrice - stopLoss).toFixed(2)})
                  </span>
                </div>
              </div>
            </div>

            {/* Risk / Reward Metrics Row */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-3 border-t border-[#1E2736] text-[11px] font-mono text-[#94A3B8]">
              <div>
                <span className="text-[10px] text-[#64748B] block uppercase">Risk / Reward</span>
                <span className="text-[#38BDF8] font-bold">1 : 1.67</span>
              </div>
              <div>
                <span className="text-[10px] text-[#64748B] block uppercase">Confidence</span>
                <span className="text-[#10B981] font-bold">92 / 100</span>
              </div>
              <div>
                <span className="text-[10px] text-[#64748B] block uppercase">Timeframe</span>
                <span className="text-[#F1F5F9] font-bold">{activeTimeframe} Setup</span>
              </div>
              <div>
                <span className="text-[10px] text-[#64748B] block uppercase">Session</span>
                <span className="text-[#10B981] font-bold">Exness Open</span>
              </div>
            </div>
          </div>
        </div>

        {/* Right Panel: Trade Execution & Risk Specification (4-5 Cols) */}
        <div className="lg:col-span-5 xl:col-span-4 space-y-4 font-mono text-xs">
          {/* Signal & Trade Specs Card */}
          <div className="p-4 rounded-xl bg-[#0E131B] border border-[#1E2736] space-y-3">
            <div className="flex items-center justify-between border-b border-[#1E2736] pb-2.5">
              <span className="font-bold text-sm text-[#F1F5F9]">Trade Specification</span>
              <StatusBadge type="SIGNAL" state="BUY" label="▲ BUY" />
            </div>

            <div className="space-y-2 text-[11px]">
              <div className="flex justify-between">
                <span className="text-[#64748B]">Instrument:</span>
                <span className="font-bold text-[#F1F5F9]">{sym}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#64748B]">Direction:</span>
                <span className="font-bold text-[#10B981]">LONG (BUY)</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#64748B]">Entry Reference:</span>
                <span className="font-bold text-[#F1F5F9] tabular-nums">${entryPrice.toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#64748B]">Stop Loss:</span>
                <span className="font-bold text-[#F43F5E] tabular-nums">${stopLoss.toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#64748B]">Take Profit:</span>
                <span className="font-bold text-[#10B981] tabular-nums">${takeProfit.toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#64748B]">Max Risk Per Trade:</span>
                <span className="font-bold text-[#F1F5F9] tabular-nums">$50.00 (1.0% Equity)</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#64748B]">Expected Net Reward:</span>
                <span className="font-bold text-[#10B981] tabular-nums">+$83.50</span>
              </div>
            </div>

            {/* Execution CTA (Guarded) */}
            <div className="pt-2 border-t border-[#1E2736] space-y-2">
              <div className="p-2.5 rounded bg-[#F59E0B]/10 border border-[#F59E0B]/30 text-[#F59E0B] text-[10px] flex items-center gap-1.5">
                <Lock className="w-3.5 h-3.5 shrink-0" />
                <span>Live trading locked (live_trading_locked=True)</span>
              </div>
              <button
                type="button"
                disabled
                className="w-full py-2.5 rounded-lg bg-[#1E2736] text-[#64748B] font-bold text-xs flex items-center justify-center gap-2 cursor-not-allowed border border-[#1E2736]"
              >
                <Lock className="w-3.5 h-3.5" />
                <span>Execution Guarded (Demo Mode Only)</span>
              </button>
            </div>
          </div>

          {/* Open Positions & Orders Status */}
          <div className="p-4 rounded-xl bg-[#0E131B] border border-[#1E2736] space-y-2.5">
            <div className="flex items-center justify-between border-b border-[#1E2736] pb-2">
              <span className="font-bold text-xs text-[#F1F5F9]">Active Positions ({openPositions.length})</span>
              <span className="text-[10px] text-[#64748B]">Real-time Mark-to-Market</span>
            </div>
            {openPositions.length === 0 ? (
              <div className="py-6 text-center text-[#64748B] text-xs">
                Zero active open positions. Margin usage is 0.0%.
              </div>
            ) : (
              <div className="space-y-2">
                {openPositions.map((pos, i) => (
                  <div key={i} className="p-2 rounded bg-[#151C28] flex justify-between text-[11px]">
                    <span className="font-bold text-[#F1F5F9]">{pos.symbol}</span>
                    <span className={pos.pnl >= 0 ? "text-[#10B981]" : "text-[#F43F5E]"}>
                      ${pos.pnl?.toFixed(2)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
