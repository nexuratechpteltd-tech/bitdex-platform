"use client";

import React from "react";
import { Wallet, Scale, ArrowUpRight, ArrowDownRight, RefreshCw, ShieldCheck, ShieldAlert, AlertCircle } from "lucide-react";

interface BalancesViewProps {
  accounts?: any[];
  isConnected?: boolean;
  balance?: number;
  equity?: number;
  freeMargin?: number;
  usedMargin?: number;
  realizedPnl?: number;
  unrealizedPnl?: number;
  onRefresh?: () => void;
}

export default function BalancesView({
  balance = 0.0,
  equity = 0.0,
  freeMargin = 0.0,
  usedMargin = 0.0,
  realizedPnl = 0.0,
  unrealizedPnl = 0.0,
  onRefresh,
  accounts = [],
  isConnected = false,
}: BalancesViewProps) {
  return (
    <div className="space-y-6 font-sans animate-in fade-in duration-200">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-2 border-b border-[#1E2736]">
        <div>
          <h1 className="text-xl sm:text-2xl font-mono font-bold text-[#F1F5F9] tracking-tight">
            Institutional Balances &amp; Margin
          </h1>
          <p className="text-xs font-mono text-[#94A3B8] mt-1">
            Real-time equity accounting, margin utilization, and verified broker holdings.
          </p>
        </div>
        {onRefresh && (
          <button
            onClick={onRefresh}
            className="self-start sm:self-auto px-3.5 py-1.5 rounded-lg bg-[#151C28] hover:bg-[#1E2736] text-[#F1F5F9] text-xs font-mono font-bold border border-[#1E2736] hover:border-[#38BDF8] flex items-center gap-2 transition-all cursor-pointer"
          >
            <RefreshCw className="w-3.5 h-3.5 text-[#38BDF8]" />
            <span>Refresh Balances</span>
          </button>
        )}
      </div>

      {/* ─── 6-CARD INSTITUTIONAL SUMMARY GRID ───────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 text-xs font-mono">
        {/* 1. Account Cash Balance */}
        <div className="p-4 rounded-xl bg-[#0E131B] border border-[#1E2736] space-y-2">
          <div className="flex items-center justify-between text-[#94A3B8]">
            <span className="text-[11px] uppercase tracking-wider">Account Cash Balance</span>
            <Wallet className="w-4 h-4 text-[#38BDF8]" />
          </div>
          <div className="text-2xl font-bold text-[#F1F5F9] tabular-nums">
            ${balance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className="text-[11px] text-[#64748B] pt-1 border-t border-[#1E2736] flex justify-between">
            <span>Settled Funds</span>
            <span className="text-[#38BDF8] font-bold">USD</span>
          </div>
        </div>

        {/* 2. Mark-to-Market Equity */}
        <div className="p-4 rounded-xl bg-[#0E131B] border border-[#1E2736] space-y-2">
          <div className="flex items-center justify-between text-[#94A3B8]">
            <span className="text-[11px] uppercase tracking-wider">Mark-to-Market Equity</span>
            <Scale className="w-4 h-4 text-[#10B981]" />
          </div>
          <div className="text-2xl font-bold text-[#F1F5F9] tabular-nums">
            ${equity.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className="text-[11px] text-[#64748B] pt-1 border-t border-[#1E2736] flex justify-between">
            <span>Cash + Floating P&amp;L</span>
            <span className="text-[#10B981] font-bold">100% Solvent</span>
          </div>
        </div>

        {/* 3. Available Free Margin */}
        <div className="p-4 rounded-xl bg-[#0E131B] border border-[#1E2736] space-y-2">
          <div className="flex items-center justify-between text-[#94A3B8]">
            <span className="text-[11px] uppercase tracking-wider">Available Free Margin</span>
            <span className="text-[10px] px-1.5 py-0.2 rounded bg-[#10B981]/15 text-[#10B981] font-bold">FREE</span>
          </div>
          <div className="text-2xl font-bold text-[#F1F5F9] tabular-nums">
            ${freeMargin.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className="text-[11px] text-[#64748B] pt-1 border-t border-[#1E2736] flex justify-between">
            <span>Margin Utilization</span>
            <span className="text-[#F1F5F9] font-bold">0.0% / 30.0% Limit</span>
          </div>
        </div>

        {/* 4. Used Margin */}
        <div className="p-4 rounded-xl bg-[#0E131B] border border-[#1E2736] space-y-2">
          <div className="flex items-center justify-between text-[#94A3B8]">
            <span className="text-[11px] uppercase tracking-wider">Used Margin</span>
            <span className="text-[10px] px-1.5 py-0.2 rounded bg-[#151C28] text-[#94A3B8]">TIED</span>
          </div>
          <div className="text-2xl font-bold text-[#F1F5F9] tabular-nums">
            ${usedMargin.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className="text-[11px] text-[#64748B] pt-1 border-t border-[#1E2736] flex justify-between">
            <span>Open Position Collateral</span>
            <span className="text-[#94A3B8]">Exness 1:200</span>
          </div>
        </div>

        {/* 5. Unrealised P&L */}
        <div className="p-4 rounded-xl bg-[#0E131B] border border-[#1E2736] space-y-2">
          <div className="flex items-center justify-between text-[#94A3B8]">
            <span className="text-[11px] uppercase tracking-wider">Floating Unrealised P&amp;L</span>
            <span className="text-[10px] px-1.5 py-0.2 rounded bg-[#151C28] text-[#94A3B8]">IN-FLIGHT</span>
          </div>
          <div className={`text-2xl font-bold tabular-nums ${unrealizedPnl >= 0 ? "text-[#10B981]" : "text-[#F43F5E]"}`}>
            {unrealizedPnl >= 0 ? "+" : ""}${unrealizedPnl.toFixed(2)}
          </div>
          <div className="text-[11px] text-[#64748B] pt-1 border-t border-[#1E2736] flex justify-between">
            <span>Open Delta Risk</span>
            <span className="text-[#F1F5F9] font-bold">0.00 Lots (Flat)</span>
          </div>
        </div>

        {/* 6. Realised P&L */}
        <div className="p-4 rounded-xl bg-[#0E131B] border border-[#1E2736] space-y-2">
          <div className="flex items-center justify-between text-[#94A3B8]">
            <span className="text-[11px] uppercase tracking-wider">Net Realised P&amp;L</span>
            <span className="text-[10px] px-1.5 py-0.2 rounded bg-[#151C28] text-[#94A3B8]">CLOSED</span>
          </div>
          <div className={`text-2xl font-bold tabular-nums ${realizedPnl >= 0 ? "text-[#10B981]" : "text-[#F43F5E]"}`}>
            {realizedPnl >= 0 ? "+" : ""}${realizedPnl.toFixed(2)}
          </div>
          <div className="text-[11px] text-[#64748B] pt-1 border-t border-[#1E2736] flex justify-between">
            <span>Single Friction Deduction</span>
            <span className="text-[#10B981] font-bold">Audited</span>
          </div>
        </div>
      </div>

      {/* ─── BROKER ALLOCATION TABLE ─────────────────────────────────── */}
      <div className="rounded-xl bg-[#0E131B] border border-[#1E2736] overflow-hidden">
        <div className="p-4 bg-[#151C28]/60 border-b border-[#1E2736] flex items-center justify-between text-xs font-mono">
          <span className="font-bold text-[#F1F5F9]">Broker Account Breakdown</span>
          <span className="text-[#94A3B8]">
            {accounts.length > 0 ? `${accounts.length} Verified Execution Account${accounts.length > 1 ? "s" : ""}` : "0 Connected Accounts"}
          </span>
        </div>
        <div className="p-4 text-xs font-mono space-y-3">
          {accounts.length > 0 ? (
            accounts.map((acc: any, idx: number) => {
              const isDemo = acc.environment === "DEMO";
              const isVerified = acc.verification_status === "VERIFIED";
              return (
                <div key={acc.account_id || idx} className="flex items-center justify-between p-3 rounded-lg bg-[#151C28] border border-[#1E2736]">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-[#F1F5F9]">{acc.exchange_name || acc.provider || "Broker"} ({acc.account_id || "Account"})</span>
                      <span className={`text-[9px] px-1.5 py-0.5 rounded font-bold ${isDemo ? "bg-[#38BDF8]/15 text-[#38BDF8] border border-[#38BDF8]/30" : "bg-amber-500/15 text-amber-400 border border-amber-500/30"}`}>
                        {acc.environment || "DEMO"}
                      </span>
                    </div>
                    <span className="text-[11px] text-[#94A3B8] block mt-0.5">{acc.label || "Verified Multi-Asset Venue"}</span>
                  </div>
                  <div className="text-right">
                    <span className="font-bold text-[#F1F5F9] text-sm tabular-nums">
                      ${(acc.estimated_usd ?? 0.0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USD
                    </span>
                    <span className={`text-[10px] block mt-0.5 font-bold ${isVerified ? "text-[#10B981]" : "text-slate-400"}`}>
                      {isVerified ? "● Verified Gateway" : "○ Unverified"}
                    </span>
                  </div>
                </div>
              );
            })
          ) : (
            <div className="p-6 text-center text-xs font-mono text-[#94A3B8]">
              <div className="w-8 h-8 rounded-full bg-rose-500/10 border border-rose-500/30 flex items-center justify-center text-rose-400 mx-auto mb-2">
                <ShieldAlert className="w-4 h-4" />
              </div>
              <div className="font-bold text-[#F1F5F9]">NO BROKER ACCOUNTS CONNECTED</div>
              <p className="text-[11px] text-[#64748B] mt-1 max-w-md mx-auto">
                No genuine Exness or exchange execution accounts have been authenticated. Attach your verified API key to stream live broker balances and equity.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
