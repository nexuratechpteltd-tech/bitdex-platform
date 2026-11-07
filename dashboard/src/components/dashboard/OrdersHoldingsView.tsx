"use client";

import React, { useState } from "react";
import { Layers, RefreshCw, ShieldAlert, Clock, ArrowUpRight, ArrowDownRight } from "lucide-react";
import StatusBadge from "../common/StatusBadge";
import {
  normalizePosition,
  formatCurrencyValue,
  formatVolumeValue,
  formatPnlValue,
  NormalizedPosition,
} from "./ordersAdapter";

interface OrdersHoldingsViewProps {
  openPositions?: any[];
  pendingOrders?: any[];
  closedPositions?: any[];
  onRefresh?: () => void;
}

export default function OrdersHoldingsView({
  openPositions = [],
  pendingOrders = [],
  closedPositions = [],
  onRefresh,
}: OrdersHoldingsViewProps) {
  const [activeTab, setActiveTab] = useState<"OPEN" | "PENDING" | "CLOSED">("OPEN");

  // Safely normalize all positions through the typed adapter
  const normalizedOpen: NormalizedPosition[] = (Array.isArray(openPositions) ? openPositions : []).map(
    (pos) => normalizePosition(pos, "OPEN")
  );
  const normalizedPending: NormalizedPosition[] = (Array.isArray(pendingOrders) ? pendingOrders : []).map(
    (pos) => normalizePosition(pos, "PENDING")
  );
  const normalizedClosed: NormalizedPosition[] = (Array.isArray(closedPositions) ? closedPositions : []).map(
    (pos) => normalizePosition(pos, "CLOSED")
  );

  const currentList =
    activeTab === "OPEN"
      ? normalizedOpen
      : activeTab === "PENDING"
      ? normalizedPending
      : normalizedClosed;

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

      {/* ─── TAB NAVIGATION ─────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-2 p-1.5 rounded-2xl bg-[#0E131B] border border-[#1E2736] text-xs font-mono w-fit">
        <button
          onClick={() => setActiveTab("OPEN")}
          className={`px-4 py-2 rounded-xl font-bold transition-all cursor-pointer flex items-center gap-2 ${
            activeTab === "OPEN"
              ? "bg-[#38BDF8] text-[#080B10] shadow-md shadow-[#38BDF8]/20"
              : "text-[#94A3B8] hover:text-[#F1F5F9] hover:bg-[#151C28]"
          }`}
        >
          <span>Open Positions</span>
          <span
            className={`text-[10px] px-1.5 py-0.2 rounded-full ${
              activeTab === "OPEN"
                ? "bg-[#080B10] text-[#38BDF8]"
                : "bg-[#1E2736] text-[#94A3B8]"
            }`}
          >
            {normalizedOpen.length}
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
          <span
            className={`text-[10px] px-1.5 py-0.2 rounded-full ${
              activeTab === "PENDING"
                ? "bg-[#080B10] text-[#38BDF8]"
                : "bg-[#1E2736] text-[#94A3B8]"
            }`}
          >
            {normalizedPending.length}
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
          <span
            className={`text-[10px] px-1.5 py-0.2 rounded-full ${
              activeTab === "CLOSED"
                ? "bg-[#080B10] text-[#38BDF8]"
                : "bg-[#1E2736] text-[#94A3B8]"
            }`}
          >
            {normalizedClosed.length}
          </span>
        </button>
      </div>

      {/* ─── DATA CONTENT ────────────────────────────────────────────── */}
      {currentList.length === 0 ? (
        <div className="p-12 text-center rounded-2xl bg-[#0E131B] border border-[#1E2736] text-xs font-mono text-[#64748B] space-y-2">
          <Layers className="w-8 h-8 mx-auto text-[#64748B]" />
          <p className="font-bold text-[#F1F5F9]">Zero {activeTab.toLowerCase()} records in this cycle</p>
          <p className="text-[11px] text-[#475569]">
            Broker execution locks remain active (`live_trading_locked=True`).
          </p>
        </div>
      ) : (
        <>
          {/* DESKTOP TABLE (>= 1024px) */}
          <div className="hidden lg:block rounded-xl bg-[#0E131B] border border-[#1E2736] overflow-hidden shadow-xl">
            <table className="w-full text-left font-mono text-xs">
              <thead className="bg-[#151C28] text-[#94A3B8] text-[10px] uppercase border-b border-[#1E2736]">
                <tr>
                  <th className="py-3 px-3">Ticket</th>
                  <th className="py-3 px-3">Category</th>
                  <th className="py-3 px-3">Instrument</th>
                  <th className="py-3 px-3">Exchange &bull; Platform</th>
                  <th className="py-3 px-3">Direction</th>
                  <th className="py-3 px-3 text-right">Volume</th>
                  <th className="py-3 px-3 text-right">Entry Price</th>
                  <th className="py-3 px-3 text-right">Current Price</th>
                  <th className="py-3 px-3 text-right">P&amp;L (USD)</th>
                  <th className="py-3 px-3">Data Source</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1E2736]">
                {currentList.map((pos) => {
                  const pnl = formatPnlValue(pos.pnl_usd);
                  return (
                    <tr key={pos.ticket} className="hover:bg-[#151C28]/60 transition-colors">
                      <td className="py-3.5 px-3 text-[#94A3B8] font-bold">{pos.ticket}</td>
                      <td className="py-3.5 px-3">
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${
                          (pos as any).is_exchange_confirmed
                            ? "bg-emerald-950/60 text-emerald-400 border-emerald-500/40"
                            : (pos as any).origin === "SEEDED_FIXTURE" || (pos as any).origin === "SIMULATION"
                            ? "bg-purple-950/60 text-purple-400 border-purple-500/40"
                            : pos.status === "CLOSED"
                            ? "bg-slate-900 text-slate-400 border-slate-700"
                            : "bg-amber-950/60 text-amber-400 border-amber-500/40"
                        }`}>
                          {(pos as any).is_exchange_confirmed
                            ? "Verified Broker Position"
                            : (pos as any).origin === "SEEDED_FIXTURE" || (pos as any).origin === "SIMULATION"
                            ? "Simulated Strategy Position"
                            : pos.status === "CLOSED"
                            ? "Historical Position"
                            : "Unverified Position"}
                        </span>
                      </td>
                      <td className="py-3.5 px-3 font-bold text-[#F1F5F9]">
                        <span>{pos.symbol}</span>
                      </td>
                      <td className="py-3.5 px-3 text-[#94A3B8]">
                        <span className="text-white font-bold">{pos.exchange || "BINANCE"}</span>
                        <span className="text-[10px] text-[#64748B] block">{pos.market_type || "FUTURES"} &bull; {pos.status}</span>
                      </td>
                      <td className="py-3.5 px-3">
                        <StatusBadge type="SIGNAL" state={pos.direction} />
                      </td>
                      <td className="py-3.5 px-3 text-right tabular-nums text-[#F1F5F9]">
                        {pos.volume_lots !== null ? (
                          formatVolumeValue(pos.volume_lots)
                        ) : (
                          <span className="text-[#64748B] italic">Unavailable</span>
                        )}
                      </td>
                      <td className="py-3.5 px-3 text-right tabular-nums text-[#F1F5F9]">
                        {pos.entry_price !== null ? (
                          formatCurrencyValue(pos.entry_price)
                        ) : (
                          <span className="text-[#64748B] italic">Unavailable</span>
                        )}
                      </td>
                      <td className="py-3.5 px-3 text-right tabular-nums text-[#F1F5F9]">
                        {pos.current_price !== null ? (
                          formatCurrencyValue(pos.current_price)
                        ) : (
                          <span className="text-[#64748B] italic">Unavailable</span>
                        )}
                      </td>
                      <td
                        className={`py-3.5 px-3 text-right font-bold tabular-nums ${
                          pnl.isUnavailable
                            ? "text-[#64748B] italic"
                            : pnl.isPositive
                            ? "text-[#10B981]"
                            : "text-[#F43F5E]"
                        }`}
                      >
                        {pnl.text}
                      </td>
                      <td className="py-3.5 px-3 text-[11px] text-[#64748B]">
                        <span className="text-[#94A3B8] block">{(pos as any).origin_label || (pos as any).origin || "Ledger Store"}</span>
                        <span className="text-[9px] text-[#64748B] block truncate" title={pos.open_time || ""}>
                          Synced: {pos.open_time ? new Date(pos.open_time).toLocaleDateString() : "Live Feed"}
                        </span>
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
              const pnl = formatPnlValue(pos.pnl_usd);
              return (
                <div key={pos.ticket} className="p-4 rounded-xl bg-[#0E131B] border border-[#1E2736] space-y-2.5 shadow-md">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-sm text-[#F1F5F9]">{pos.symbol}</span>
                      <StatusBadge type="SIGNAL" state={pos.direction} />
                      {pos.exchange && (
                        <span className="text-[9px] px-1 py-0.2 rounded bg-[#1E2736] text-[#64748B]">
                          {pos.exchange}
                        </span>
                      )}
                    </div>
                    <span
                      className={`font-bold text-sm tabular-nums ${
                        pnl.isUnavailable
                          ? "text-[#64748B] italic"
                          : pnl.isPositive
                          ? "text-[#10B981]"
                          : "text-[#F43F5E]"
                      }`}
                    >
                      {pnl.text}
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-[11px] p-2.5 rounded-lg bg-[#151C28] border border-[#1E2736]">
                    <div>
                      <span className="text-[#64748B] block">Entry Price:</span>
                      <span className="font-bold text-[#F1F5F9] tabular-nums">
                        {pos.entry_price !== null ? (
                          formatCurrencyValue(pos.entry_price)
                        ) : (
                          <span className="text-[#64748B] italic">Unavailable</span>
                        )}
                      </span>
                    </div>
                    <div>
                      <span className="text-[#64748B] block">Current Tick:</span>
                      <span className="font-bold text-[#F1F5F9] tabular-nums">
                        {pos.current_price !== null ? (
                          formatCurrencyValue(pos.current_price)
                        ) : (
                          <span className="text-[#64748B] italic">Unavailable</span>
                        )}
                      </span>
                    </div>
                    <div>
                      <span className="text-[#64748B] block">Stop Loss:</span>
                      <span className="font-bold text-[#F43F5E] tabular-nums">
                        {pos.stop_loss !== null ? (
                          formatCurrencyValue(pos.stop_loss)
                        ) : (
                          <span className="text-[#64748B] italic">Unavailable</span>
                        )}
                      </span>
                    </div>
                    <div>
                      <span className="text-[#64748B] block">Take Profit:</span>
                      <span className="font-bold text-[#10B981] tabular-nums">
                        {pos.take_profit !== null ? (
                          formatCurrencyValue(pos.take_profit)
                        ) : (
                          <span className="text-[#64748B] italic">Unavailable</span>
                        )}
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center justify-between text-[10px] text-[#64748B] pt-1 border-t border-[#1E2736]/60">
                    <span>
                      Vol:{" "}
                      <b className="text-[#F1F5F9] font-normal">
                        {pos.volume_lots !== null ? formatVolumeValue(pos.volume_lots) : "Unavailable"}
                      </b>
                    </span>
                    <span>Ticket: {pos.ticket}</span>
                    {pos.open_time && (
                      <span className="truncate max-w-[120px]">
                        {pos.open_time.replace("T", " ").replace("Z", "")}
                      </span>
                    )}
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
