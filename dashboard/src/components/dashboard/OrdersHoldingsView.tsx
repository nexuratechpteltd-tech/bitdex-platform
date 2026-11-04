"use client";

import React, { useState } from "react";
import { Layers, Clock, CheckCircle2, AlertCircle, RefreshCw } from "lucide-react";
import StatusBadge from "../common/StatusBadge";

interface Position {
  ticket: string;
  symbol: string;
  direction: "BUY" | "SELL";
  entry_price: number;
  current_price: number;
  stop_loss?: number;
  take_profit?: number;
  volume_lots: number;
  pnl_usd: number;
  open_time: string;
  close_time?: string;
  status: "OPEN" | "PENDING" | "CLOSED";
}

interface OrdersHoldingsViewProps {
  openPositions?: Position[];
  pendingOrders?: Position[];
  closedPositions?: Position[];
  onRefresh?: () => void;
}

export default function OrdersHoldingsView({
  openPositions = [],
  pendingOrders = [],
  closedPositions = [],
  onRefresh,
}: OrdersHoldingsViewProps) {
  const [activeTab, setActiveTab] = useState<"OPEN" | "PENDING" | "CLOSED">("OPEN");

  const currentList =
    activeTab === "OPEN"
      ? openPositions
      : activeTab === "PENDING"
      ? pendingOrders
      : closedPositions;

  return (
    <div className="space-y-6 font-sans animate-in fade-in duration-200">
      {/* ─── HEADER ─────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-2 border-b border-[#1E2736]">
        <div>
          <h1 className="text-xl sm:text-2xl font-mono font-bold text-[#F1F5F9] tracking-tight">
            Orders &amp; Holdings
          </h1>
          <p className="text-xs font-mono text-[#94A3B8] mt-1">
            Real-time verified execution ledger, pending orders, and historical trade audits.
          </p>
        </div>
        {onRefresh && (
          <button
            onClick={onRefresh}
            className="self-start sm:self-auto px-3.5 py-1.5 rounded-lg bg-[#151C28] hover:bg-[#1E2736] text-[#F1F5F9] text-xs font-mono font-bold border border-[#1E2736] hover:border-[#38BDF8] flex items-center gap-2 transition-all cursor-pointer"
          >
            <RefreshCw className="w-3.5 h-3.5 text-[#38BDF8]" />
            <span>Refresh Ledger</span>
          </button>
        )}
      </div>

      {/* ─── SEGMENTED TAB BAR ───────────────────────────────────────── */}
      <div className="flex items-center gap-2 border-b border-[#1E2736] pb-3 text-xs font-mono">
        <button
          onClick={() => setActiveTab("OPEN")}
          className={`px-4 py-2 rounded-xl font-bold transition-all cursor-pointer flex items-center gap-2 ${
            activeTab === "OPEN"
              ? "bg-[#38BDF8] text-[#080B10] shadow-md shadow-[#38BDF8]/20"
              : "text-[#94A3B8] hover:text-[#F1F5F9] hover:bg-[#151C28]"
          }`}
        >
          <span>Open Positions</span>
          <span className={`text-[10px] px-1.5 py-0.2 rounded-full ${activeTab === "OPEN" ? "bg-[#080B10] text-[#38BDF8]" : "bg-[#1E2736] text-[#94A3B8]"}`}>
            {openPositions.length}
          </span>
        </button>

        <button
          onClick={() => setActiveTab("PENDING")}
          className={`px-4 py-2 rounded-xl font-bold transition-all cursor-pointer flex items-center gap-2 ${
            activeTab === "PENDING"
              ? "bg-[#38BDF8] text-[#080B10] shadow-md shadow-[#38BDF8]/20"
              : "text-[#94A3B8] hover:text-[#F1F5F9] hover:bg-[#151C28]"
          }`}
        >
          <span>Pending Orders</span>
          <span className={`text-[10px] px-1.5 py-0.2 rounded-full ${activeTab === "PENDING" ? "bg-[#080B10] text-[#38BDF8]" : "bg-[#1E2736] text-[#94A3B8]"}`}>
            {pendingOrders.length}
          </span>
        </button>

        <button
          onClick={() => setActiveTab("CLOSED")}
          className={`px-4 py-2 rounded-xl font-bold transition-all cursor-pointer flex items-center gap-2 ${
            activeTab === "CLOSED"
              ? "bg-[#38BDF8] text-[#080B10] shadow-md shadow-[#38BDF8]/20"
              : "text-[#94A3B8] hover:text-[#F1F5F9] hover:bg-[#151C28]"
          }`}
        >
          <span>Closed Positions</span>
          <span className={`text-[10px] px-1.5 py-0.2 rounded-full ${activeTab === "CLOSED" ? "bg-[#080B10] text-[#38BDF8]" : "bg-[#1E2736] text-[#94A3B8]"}`}>
            {closedPositions.length}
          </span>
        </button>
      </div>

      {/* ─── DATA CONTENT ────────────────────────────────────────────── */}
      {currentList.length === 0 ? (
        <div className="p-12 text-center rounded-2xl bg-[#0E131B] border border-[#1E2736] text-xs font-mono text-[#64748B] space-y-2">
          <Layers className="w-8 h-8 mx-auto text-[#64748B]" />
          <p className="font-bold text-[#F1F5F9]">Zero {activeTab.toLowerCase()} positions in this cycle</p>
          <p className="text-[11px] text-[#475569]">
            Broker execution locks remain active (`live_trading_locked=True`).
          </p>
        </div>
      ) : (
        <>
          {/* DESKTOP TABLE (>= 1024px) */}
          <div className="hidden lg:block rounded-xl bg-[#0E131B] border border-[#1E2736] overflow-hidden">
            <table className="w-full text-left font-mono text-xs">
              <thead className="bg-[#151C28] text-[#94A3B8] text-[10px] uppercase border-b border-[#1E2736]">
                <tr>
                  <th className="py-3 px-4">Ticket</th>
                  <th className="py-3 px-4">Instrument</th>
                  <th className="py-3 px-4">Direction</th>
                  <th className="py-3 px-4 text-right">Volume (Lots)</th>
                  <th className="py-3 px-4 text-right">Entry Price</th>
                  <th className="py-3 px-4 text-right">Current Price</th>
                  <th className="py-3 px-4 text-right">Stop Loss</th>
                  <th className="py-3 px-4 text-right">Take Profit</th>
                  <th className="py-3 px-4 text-right">P&amp;L (USD)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1E2736]">
                {currentList.map((pos) => {
                  const isBuy = pos.direction === "BUY";
                  const isPos = pos.pnl_usd >= 0;
                  return (
                    <tr key={pos.ticket} className="hover:bg-[#151C28]/60 transition-colors">
                      <td className="py-3.5 px-4 text-[#94A3B8]">{pos.ticket}</td>
                      <td className="py-3.5 px-4 font-bold text-[#F1F5F9]">{pos.symbol}</td>
                      <td className="py-3.5 px-4">
                        <StatusBadge type="SIGNAL" state={pos.direction} />
                      </td>
                      <td className="py-3.5 px-4 text-right tabular-nums">{pos.volume_lots.toFixed(2)}</td>
                      <td className="py-3.5 px-4 text-right tabular-nums text-[#F1F5F9]">
                        ${pos.entry_price.toFixed(2)}
                      </td>
                      <td className="py-3.5 px-4 text-right tabular-nums text-[#F1F5F9]">
                        ${pos.current_price.toFixed(2)}
                      </td>
                      <td className="py-3.5 px-4 text-right tabular-nums text-[#F43F5E]">
                        {pos.stop_loss ? `$${pos.stop_loss.toFixed(2)}` : <span className="text-[#64748B]">Unavailable</span>}
                      </td>
                      <td className="py-3.5 px-4 text-right tabular-nums text-[#10B981]">
                        {pos.take_profit ? `$${pos.take_profit.toFixed(2)}` : <span className="text-[#64748B]">Unavailable</span>}
                      </td>
                      <td className={`py-3.5 px-4 text-right font-bold tabular-nums ${isPos ? "text-[#10B981]" : "text-[#F43F5E]"}`}>
                        {isPos ? "+" : ""}${pos.pnl_usd.toFixed(2)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* MOBILE RESPONSIVE CARDS (< 1024px) */}
          <div className="lg:hidden space-y-3 font-mono text-xs">
            {currentList.map((pos) => {
              const isPos = pos.pnl_usd >= 0;
              return (
                <div key={pos.ticket} className="p-4 rounded-xl bg-[#0E131B] border border-[#1E2736] space-y-2.5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-sm text-[#F1F5F9]">{pos.symbol}</span>
                      <StatusBadge type="SIGNAL" state={pos.direction} />
                    </div>
                    <span className={`font-bold text-sm tabular-nums ${isPos ? "text-[#10B981]" : "text-[#F43F5E]"}`}>
                      {isPos ? "+" : ""}${pos.pnl_usd.toFixed(2)}
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-[11px] p-2.5 rounded-lg bg-[#151C28] border border-[#1E2736]">
                    <div>
                      <span className="text-[#64748B] block">Entry Price:</span>
                      <span className="font-bold text-[#F1F5F9] tabular-nums">${pos.entry_price.toFixed(2)}</span>
                    </div>
                    <div>
                      <span className="text-[#64748B] block">Current Tick:</span>
                      <span className="font-bold text-[#F1F5F9] tabular-nums">${pos.current_price.toFixed(2)}</span>
                    </div>
                    <div>
                      <span className="text-[#64748B] block">Stop Loss:</span>
                      <span className="font-bold text-[#F43F5E] tabular-nums">
                        {pos.stop_loss ? `$${pos.stop_loss.toFixed(2)}` : "Unavailable"}
                      </span>
                    </div>
                    <div>
                      <span className="text-[#64748B] block">Take Profit:</span>
                      <span className="font-bold text-[#10B981] tabular-nums">
                        {pos.take_profit ? `$${pos.take_profit.toFixed(2)}` : "Unavailable"}
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
