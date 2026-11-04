"use client";

import React, { useState } from "react";
import {
  ShieldCheck,
  AlertTriangle,
  Lock,
  Layers,
  RefreshCw,
  ExternalLink,
  Server,
  KeyRound,
  FileText,
  XCircle,
} from "lucide-react";

interface ExchangeConnectionsViewProps {
  exnessConnected?: boolean;
  onRefresh?: () => void;
}

export default function ExchangeConnectionsView({
  exnessConnected = false,
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
            Authoritative broker gateway connectivity and cryptographic credential vault.
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

      {/* ─── PRIMARY VENUE: EXNESS MT5 BROKER CARD (TRUTHFUL UNCONNECTED STATE) ─ */}
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
                  EXNESS MT5 BROKER GATEWAY
                </h2>
                <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-[#38BDF8]/15 text-[#38BDF8] border border-[#38BDF8]/30 font-bold">
                  PRIMARY TARGET VENUE
                </span>
              </div>
              <p className="text-xs font-mono text-[#94A3B8] mt-0.5">
                Multi-Asset CFD &amp; Forex Execution Gateway
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono font-bold bg-[#EF4444]/15 text-[#EF4444] border border-[#EF4444]/30">
              <span className="w-2 h-2 rounded-full bg-[#EF4444]" />
              <span>EXNESS GATEWAY NOT CONNECTED</span>
            </span>
            <span className="text-[10px] font-mono px-2 py-1 rounded bg-[#F59E0B]/15 text-[#F59E0B] border border-[#F59E0B]/30 font-bold">
              GATEWAY OFFLINE
            </span>
          </div>
        </div>

        {/* Card Body: Truthful Account & Telemetry Details */}
        <div className="p-4 sm:p-6 space-y-6">
          {/* Spec Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs font-mono">
            <div className="p-3.5 rounded-xl bg-[#151C28] border border-[#1E2736] space-y-1">
              <span className="text-[10px] text-[#64748B] block uppercase">Account Identifier</span>
              <span className="font-bold text-[#94A3B8] text-sm tabular-nums">UNAVAILABLE</span>
              <span className="text-[10px] text-[#64748B] block">No Active MT5 Session</span>
            </div>

            <div className="p-3.5 rounded-xl bg-[#151C28] border border-[#1E2736] space-y-1">
              <span className="text-[10px] text-[#64748B] block uppercase">Server Target</span>
              <span className="font-bold text-[#94A3B8] text-sm tabular-nums">NOT CONFIGURED</span>
              <span className="text-[10px] text-[#64748B] block">Requires Windows MT5 Gateway</span>
            </div>

            <div className="p-3.5 rounded-xl bg-[#151C28] border border-[#1E2736] space-y-1">
              <span className="text-[10px] text-[#64748B] block uppercase">Account Balance / Equity</span>
              <span className="font-bold text-[#94A3B8] text-sm tabular-nums">UNAVAILABLE</span>
              <span className="text-[10px] text-[#64748B] block">Awaiting Gateway Handshake</span>
            </div>

            <div className="p-3.5 rounded-xl bg-[#151C28] border border-[#1E2736] space-y-1">
              <span className="text-[10px] text-[#64748B] block uppercase">Margin &amp; Leverage</span>
              <span className="font-bold text-[#94A3B8] text-sm tabular-nums">UNAVAILABLE</span>
              <span className="text-[10px] text-[#64748B] block">Dynamic upon Connection</span>
            </div>
          </div>

          {/* Permissions & Security Strip */}
          <div className="p-4 rounded-xl bg-[#080B10] border border-[#1E2736] flex flex-wrap items-center justify-between gap-4 text-xs font-mono">
            <div className="space-y-1">
              <span className="text-[11px] font-bold text-[#F1F5F9] block">
                Authoritative Gateway Permissions:
              </span>
              <div className="flex flex-wrap items-center gap-2 text-[10px]">
                <span className="px-2 py-0.5 rounded bg-[#64748B]/15 text-[#94A3B8] border border-[#64748B]/30">
                  ✕ Real-time Tick Streaming (Disconnected)
                </span>
                <span className="px-2 py-0.5 rounded bg-[#64748B]/15 text-[#94A3B8] border border-[#64748B]/30">
                  ✕ Historical Bar Ingestion (Disconnected)
                </span>
                <span className="px-2 py-0.5 rounded bg-[#64748B]/15 text-[#94A3B8] border border-[#64748B]/30">
                  ✕ Order Margin Calculation (Disconnected)
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
                className="px-3.5 py-1.5 rounded-lg bg-[#38BDF8]/10 hover:bg-[#38BDF8] text-[#38BDF8] hover:text-[#080B10] font-bold border border-[#38BDF8]/30 transition-all cursor-pointer text-xs"
              >
                Poll Gateway Daemon
              </button>
            </div>
          </div>

          {/* Infrastructure Notice */}
          <div className="p-4 rounded-xl bg-[#151C28]/40 border border-[#1E2736] space-y-2 text-xs font-mono">
            <div className="flex items-center gap-2 text-[#38BDF8] font-bold">
              <Server className="w-4 h-4" />
              <span>Windows MT5 Gateway Deployment Requirements</span>
            </div>
            <p className="text-[#94A3B8] text-[11px] leading-relaxed">
              Exness MT5 broker connectivity requires the BITDEX MT5 Gateway service running on a dedicated Windows VPS co-located near Exness trading servers. The gateway daemon communicates with the Linux backend over an encrypted private WireGuard/TLS tunnel. Authoritative broker balances and demo execution telemetry will bind to this interface once the Windows gateway service is authenticated.
            </p>
            <div className="pt-1 flex items-center gap-2 text-[10px] text-[#64748B]">
              <FileText className="w-3.5 h-3.5 text-[#38BDF8]" />
              <span>Runbook Reference: <code className="text-[#F1F5F9]">docs/EXNESS_MT5_GATEWAY_INTEGRATION_RUNBOOK.md</code></span>
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
