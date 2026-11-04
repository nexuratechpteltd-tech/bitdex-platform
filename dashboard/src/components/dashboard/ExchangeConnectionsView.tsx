"use client";

import React, { useState } from "react";
import {
  Link2,
  ShieldCheck,
  CheckCircle2,
  RefreshCw,
  Lock,
  AlertTriangle,
  Server,
  Layers,
  Key,
  Clock,
  ExternalLink,
} from "lucide-react";
import StatusBadge from "../common/StatusBadge";

interface ExchangeConnectionsViewProps {
  exnessConnected?: boolean;
  onRefresh?: () => void;
}

export default function ExchangeConnectionsView({
  exnessConnected = true,
  onRefresh,
}: ExchangeConnectionsViewProps) {
  const [isSyncing, setIsSyncing] = useState(false);

  const handleSync = async () => {
    setIsSyncing(true);
    if (onRefresh) await onRefresh();
    setTimeout(() => setIsSyncing(false), 800);
  };

  return (
    <div className="space-y-6 font-sans animate-in fade-in duration-200">
      {/* ─── HEADER ─────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-2 border-b border-[#1E2736]">
        <div>
          <h1 className="text-xl sm:text-2xl font-mono font-bold text-[#F1F5F9] tracking-tight">
            Exchange &amp; Broker Connections
          </h1>
          <p className="text-xs font-mono text-[#94A3B8] mt-1">
            Manage your verified institutional broker account connection and secure vault credentials.
          </p>
        </div>
        <button
          onClick={handleSync}
          disabled={isSyncing}
          className="self-start sm:self-auto px-3.5 py-1.5 rounded-lg bg-[#151C28] hover:bg-[#1E2736] text-[#F1F5F9] text-xs font-mono font-bold border border-[#1E2736] hover:border-[#38BDF8] flex items-center gap-2 transition-all cursor-pointer"
        >
          <RefreshCw className={`w-3.5 h-3.5 text-[#38BDF8] ${isSyncing ? "animate-spin" : ""}`} />
          <span>{isSyncing ? "Syncing..." : "Sync Broker State"}</span>
        </button>
      </div>

      {/* ─── PRIMARY VENUE: EXNESS MT5 BROKER CARD ───────────────────── */}
      <div className="rounded-2xl bg-[#0E131B] border border-[#1E2736] overflow-hidden shadow-xl">
        {/* Top Card Banner */}
        <div className="p-4 sm:p-5 bg-[#151C28]/60 border-b border-[#1E2736] flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-[#F59E0B]/15 border border-[#F59E0B]/30 flex items-center justify-center font-mono font-black text-lg text-[#F59E0B]">
              EX
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-mono font-bold text-[#F1F5F9]">
                  EXNESS MT5 BROKER CONNECTION
                </h2>
                <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-[#38BDF8]/15 text-[#38BDF8] border border-[#38BDF8]/30 font-bold">
                  PRIMARY VENUE
                </span>
              </div>
              <p className="text-xs font-mono text-[#94A3B8] mt-0.5">
                Multi-Asset CFD &amp; Forex Execution Gateway
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono font-bold bg-[#10B981]/15 text-[#10B981] border border-[#10B981]/30">
              <span className="w-2 h-2 rounded-full bg-[#10B981] animate-pulse" />
              <span>CONNECTED</span>
            </span>
            <span className="text-[10px] font-mono px-2 py-1 rounded bg-[#F59E0B]/15 text-[#F59E0B] border border-[#F59E0B]/30 font-bold">
              DEMO MODE
            </span>
          </div>
        </div>

        {/* Card Body: Account & Credentials Details */}
        <div className="p-4 sm:p-6 space-y-6">
          {/* Spec Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs font-mono">
            <div className="p-3.5 rounded-xl bg-[#151C28] border border-[#1E2736] space-y-1">
              <span className="text-[10px] text-[#64748B] block uppercase">Account Identifier</span>
              <span className="font-bold text-[#F1F5F9] text-sm tabular-nums">****5842</span>
              <span className="text-[10px] text-[#94A3B8] block">Server: Exness-MT5Trial</span>
            </div>

            <div className="p-3.5 rounded-xl bg-[#151C28] border border-[#1E2736] space-y-1">
              <span className="text-[10px] text-[#64748B] block uppercase">Account Balance / Equity</span>
              <span className="font-bold text-[#F1F5F9] text-sm tabular-nums">$5,000.00 USD</span>
              <span className="text-[10px] text-[#10B981] block">Equity: $5,000.00</span>
            </div>

            <div className="p-3.5 rounded-xl bg-[#151C28] border border-[#1E2736] space-y-1">
              <span className="text-[10px] text-[#64748B] block uppercase">Margin &amp; Leverage</span>
              <span className="font-bold text-[#F1F5F9] text-sm tabular-nums">1:200 Dynamic</span>
              <span className="text-[10px] text-[#94A3B8] block">Used: $0.00 (0.0%)</span>
            </div>

            <div className="p-3.5 rounded-xl bg-[#151C28] border border-[#1E2736] space-y-1">
              <span className="text-[10px] text-[#64748B] block uppercase">Vault Encryption</span>
              <span className="font-bold text-[#10B981] text-sm flex items-center gap-1">
                <ShieldCheck className="w-3.5 h-3.5" />
                <span>AES-256-GCM</span>
              </span>
              <span className="text-[10px] text-[#64748B] block">Credentials Hidden &amp; Isolated</span>
            </div>
          </div>

          {/* Permissions & Security Strip */}
          <div className="p-4 rounded-xl bg-[#080B10] border border-[#1E2736] flex flex-wrap items-center justify-between gap-4 text-xs font-mono">
            <div className="space-y-1">
              <span className="text-[11px] font-bold text-[#F1F5F9] block">
                Verified Gateway Permissions:
              </span>
              <div className="flex flex-wrap items-center gap-2 text-[10px]">
                <span className="px-2 py-0.5 rounded bg-[#10B981]/15 text-[#10B981] border border-[#10B981]/30">
                  ✓ Real-time Tick Streaming
                </span>
                <span className="px-2 py-0.5 rounded bg-[#10B981]/15 text-[#10B981] border border-[#10B981]/30">
                  ✓ Historical Bar Ingestion
                </span>
                <span className="px-2 py-0.5 rounded bg-[#10B981]/15 text-[#10B981] border border-[#10B981]/30">
                  ✓ Order Margin Calculation
                </span>
                <span className="px-2 py-0.5 rounded bg-[#F43F5E]/15 text-[#F43F5E] border border-[#F43F5E]/30">
                  ✕ Live Trading Disabled (Locked)
                </span>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleSync}
                className="px-3 py-1.5 rounded-lg bg-[#38BDF8]/10 hover:bg-[#38BDF8] text-[#38BDF8] hover:text-[#080B10] font-bold border border-[#38BDF8]/30 transition-all cursor-pointer"
              >
                Reconnect Gateway
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* ─── SECURITY NOTICE ────────────────────────────────────────── */}
      <div className="p-4 rounded-xl bg-[#0E131B] border border-[#1E2736] flex items-start gap-3 text-xs font-mono text-[#94A3B8]">
        <Lock className="w-4 h-4 text-[#38BDF8] shrink-0 mt-0.5" />
        <div className="space-y-1">
          <span className="text-[#F1F5F9] font-bold block">
            Institutional Vault Security Standard
          </span>
          <p className="leading-relaxed text-[#64748B]">
            All MT5 login credentials and gateway auth tokens are encrypted in the local SQLite vault using tenant-bound AES-256-GCM. Plaintext passwords or secrets are never exposed to browser sessions or transmitted over unauthenticated links.
          </p>
        </div>
      </div>
    </div>
  );
}
