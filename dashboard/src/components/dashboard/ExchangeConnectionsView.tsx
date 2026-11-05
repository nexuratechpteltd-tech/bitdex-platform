"use client";

import React, { useState, useEffect } from "react";
import {
  ShieldCheck,
  AlertTriangle,
  Lock,
  RefreshCw,
  ExternalLink,
  Plus,
  CheckCircle2,
  X,
  Loader2,
  Trash2,
  Star,
  Radio,
  ChevronRight,
} from "lucide-react";

interface ExchangeConnectionsViewProps {
  exnessConnected?: boolean;
  onRefresh?: () => void;
  token?: string;
}

export default function ExchangeConnectionsView({
  exnessConnected = false,
  onRefresh,
  token,
}: ExchangeConnectionsViewProps) {
  const [isSyncing, setIsSyncing] = useState(false);
  const [statusData, setStatusData] = useState<any>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  // Task 1A: Universal Exness Connection Workflow — ONLY 3 Required Inputs
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [candidateAccountIds, setCandidateAccountIds] = useState("");
  const [gatewayHost, setGatewayHost] = useState("https://api.exness.com");

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [resyncingId, setResyncingId] = useState<string | null>(null);
  const [statusMsg, setStatusMsg] = useState<{
    type: "success" | "error" | "info";
    text: string;
    details?: string;
  } | null>(null);

  const getAuthToken = () => {
    return (
      token ||
      (typeof window !== "undefined"
        ? localStorage.getItem("bitdex_auth_token") ||
          localStorage.getItem("tauric_session_token") ||
          localStorage.getItem("tauric_token") ||
          localStorage.getItem("bitdex_token")
        : null)
    );
  };

  const fetchStatus = async () => {
    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      const authToken = getAuthToken();
      if (authToken) headers["Authorization"] = `Bearer ${authToken}`;

      const res = await fetch("/api/v1/hft/exness/status", { headers });
      if (res.ok) {
        const d = await res.json();
        setStatusData(d);
      }
    } catch (err) {
      console.error("Failed to fetch Exness connection status:", err);
    }
  };

  useEffect(() => {
    fetchStatus();
  }, [token]);

  const handleSync = async () => {
    setIsSyncing(true);
    await fetchStatus();
    if (onRefresh) await onRefresh();
    setTimeout(() => setIsSyncing(false), 600);
  };

  const handleOpenConnect = () => {
    setStatusMsg(null);
    setApiKey("");
    setApiSecret("");
    setCandidateAccountIds("");
    setGatewayHost("https://api.exness.com");
    setIsModalOpen(true);
  };

  const handleDiscoverAndAttach = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setStatusMsg(null);

    const authToken = getAuthToken();
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
    };

    try {
      if (!apiKey.trim() || !apiSecret.trim()) {
        throw new Error("Exness API Key and Ed25519 Private Signing Key are required.");
      }

      const rawIds = candidateAccountIds
        .split(/[,;\s]+/)
        .map((s) => s.trim())
        .filter(Boolean);

      if (rawIds.length === 0) {
        throw new Error(
          "Please enter at least one Exness Trading Account ID. The Exness Trader API requires explicit account_id routing for Access Point discovery."
        );
      }

      const res = await fetch("/api/v1/hft/exness/attach-and-discover", {
        method: "POST",
        headers,
        body: JSON.stringify({
          api_key: apiKey.trim(),
          api_secret: apiSecret.trim(),
          gateway_host: (gatewayHost || "https://api.exness.com").trim(),
          account_ids: rawIds,
        }),
      });

      const data = await res.json();

      if (!res.ok || data.status === "FAILED") {
        const failedReason =
          data.failed_accounts?.[0]?.error_detail ||
          data.detail?.error_detail ||
          (typeof data.detail === "string" ? data.detail : null) ||
          data.message ||
          "Exness API authentication and Access Point discovery failed.";
        const errorType =
          data.failed_accounts?.[0]?.error_type ||
          data.detail?.error_type ||
          "AUTHENTICATION_FAILED";

        setStatusMsg({
          type: "error",
          text: `Authentication Failed: ${errorType}`,
          details: failedReason,
        });
        await fetchStatus();
        return;
      }

      const totalVerified = data.total_verified || 0;
      setStatusMsg({
        type: "success",
        text: `Authentication Complete: ${totalVerified} Exness account(s) verified.`,
        details:
          "Access Point resolved via GET /v1/trading/access-point and account telemetry authenticated via signed Ed25519 requests.",
      });

      await fetchStatus();
      if (onRefresh) onRefresh();

      setTimeout(() => {
        setIsModalOpen(false);
      }, 1500);
    } catch (err: any) {
      setStatusMsg({
        type: "error",
        text: "Error Attaching Exness Credentials",
        details: err.message || "Failed to contact Exness discovery service.",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleResync = async (connectionId: string) => {
    setResyncingId(connectionId);
    const authToken = getAuthToken();
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
    };

    try {
      const res = await fetch(`/api/v1/hft/exness/accounts/${connectionId}/resync`, {
        method: "POST",
        headers,
      });
      const data = await res.json();

      if (!res.ok) {
        const errorDetail =
          data.detail?.error_detail ||
          (typeof data.detail === "string" ? data.detail : "Resynchronization failed.");
        setStatusMsg({
          type: "error",
          text: `Resync Failed (${data.detail?.error_type || "AUTH_ERROR"})`,
          details: errorDetail,
        });
      } else {
        await fetchStatus();
        if (onRefresh) onRefresh();
      }
    } catch (err: any) {
      setStatusMsg({
        type: "error",
        text: "Network Error During Resync",
        details: err.message,
      });
    } finally {
      setResyncingId(null);
    }
  };

  const handleDisconnect = async (connectionId: string) => {
    if (
      !confirm(
        "Are you sure you want to disconnect this Exness account? Stored credentials will be invalidated."
      )
    ) {
      return;
    }

    try {
      const authToken = getAuthToken();
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
      };

      const res = await fetch("/api/v1/hft/exness/disconnect", {
        method: "POST",
        headers,
        body: JSON.stringify({ connection_id: connectionId }),
      });

      if (res.ok) {
        await fetchStatus();
        if (onRefresh) onRefresh();
      }
    } catch (err) {
      console.error("Disconnect error:", err);
    }
  };

  const handleSetPreferred = async (connectionId: string) => {
    try {
      const authToken = getAuthToken();
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
      };

      const res = await fetch("/api/v1/hft/exness/account/preferred", {
        method: "POST",
        headers,
        body: JSON.stringify({ connection_id: connectionId }),
      });

      if (res.ok) {
        await fetchStatus();
        if (onRefresh) onRefresh();
      }
    } catch (err) {
      console.error("Set preferred error:", err);
    }
  };

  const verifiedAccounts: any[] = statusData?.verified_accounts || [];
  const demoAccounts: any[] = statusData?.exness_demo_accounts || [];
  const realAccounts: any[] = statusData?.exness_real_accounts || [];
  const failedAccounts: any[] = statusData?.failed_accounts || [];

  return (
    <div className="space-y-6 font-mono text-xs">
      {/* ─── HEADER & UNIVERSAL CONNECTOR BAR ─────────────────── */}
      <div className="p-4 sm:p-5 rounded-2xl bg-[#0E131B] border border-[#1E2736] flex flex-wrap items-center justify-between gap-4 shadow-xl">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-[#38BDF8] shrink-0" />
            <h1 className="text-sm sm:text-base font-bold text-[#F1F5F9] uppercase tracking-wider">
              Universal Exness Trader API Connector
            </h1>
          </div>
          <p className="text-[11px] sm:text-xs text-[#94A3B8]">
            Two-Stage Access Point Discovery &bull; Ed25519 Payload Signing &bull; Automatic Demo &amp; Real Classification
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5 w-full sm:w-auto">
          <button
            onClick={handleSync}
            disabled={isSyncing}
            className="px-3 py-2 rounded-xl bg-[#151C28] hover:bg-[#1E2736] border border-[#1E2736] text-[#F1F5F9] transition-all flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-50 flex-1 sm:flex-initial"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isSyncing ? "animate-spin text-[#38BDF8]" : ""}`} />
            <span>Sync</span>
          </button>

          <a
            href="https://my.exness.com/pa"
            target="_blank"
            rel="noopener noreferrer"
            className="px-3 py-2 rounded-xl bg-[#151C28] hover:bg-[#1E2736] border border-[#1E2736] text-[#38BDF8] transition-all flex items-center justify-center gap-1.5 flex-1 sm:flex-initial"
          >
            <ExternalLink className="w-3.5 h-3.5" />
            <span>Personal Area</span>
          </a>

          <button
            type="button"
            onClick={handleOpenConnect}
            className="px-4 py-2 rounded-xl bg-[#38BDF8] hover:bg-[#38BDF8]/90 text-[#080B10] font-bold transition-all flex items-center justify-center gap-1.5 cursor-pointer shadow-md shadow-[#38BDF8]/20 w-full sm:w-auto"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Connect Exness API</span>
          </button>
        </div>
      </div>

      {/* ─── SUMMARY KPI TILES ─────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <div className="p-4 rounded-xl bg-[#0E131B] border border-[#1E2736]">
          <span className="text-[10px] text-[#64748B] block uppercase font-bold">Verified Accounts:</span>
          <span className="text-xl font-bold text-white tabular-nums">
            {verifiedAccounts.length}
          </span>
          <span className="text-[10px] text-[#94A3B8] block mt-0.5">Authenticated Sessions</span>
        </div>
        <div className="p-4 rounded-xl bg-[#0E131B] border border-[#1E2736]">
          <span className="text-[10px] text-[#64748B] block uppercase font-bold">Verified Demo:</span>
          <span className="text-xl font-bold text-[#38BDF8] tabular-nums">
            {demoAccounts.length}
          </span>
          <span className="text-[10px] text-[#94A3B8] block mt-0.5">Provider-Confirmed Demo</span>
        </div>
        <div className="p-4 rounded-xl bg-[#0E131B] border border-[#1E2736]">
          <span className="text-[10px] text-[#64748B] block uppercase font-bold">Verified Real:</span>
          <span className="text-xl font-bold text-[#F59E0B] tabular-nums">
            {realAccounts.length}
          </span>
          <span className="text-[10px] text-[#94A3B8] block mt-0.5">Provider-Confirmed Real</span>
        </div>
        <div className="p-4 rounded-xl bg-[#0E131B] border border-[#1E2736]">
          <span className="text-[10px] text-[#64748B] block uppercase font-bold">Platform Safety Locks:</span>
          <span className="text-xs font-bold text-emerald-400 block mt-1">3/3 ACTIVE (READ-ONLY)</span>
          <span className="text-[10px] text-[#64748B] block mt-0.5">Zero Live Order Placement</span>
        </div>
      </div>

      {/* ─── TASK 1E: UNIFIED VERIFIED EXNESS ACCOUNTS TABLE ───────── */}
      <div className="rounded-2xl bg-[#0E131B] border border-[#1E2736] overflow-hidden shadow-lg">
        <div className="p-4 bg-[#151C28]/60 border-b border-[#1E2736] flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Radio className="w-4 h-4 text-[#38BDF8]" />
            <h2 className="font-bold text-[#F1F5F9] uppercase tracking-wider text-xs">
              Verified Exness Trading Accounts
            </h2>
          </div>
          <span className="text-[10px] text-[#64748B]">
            {verifiedAccounts.length} Verified Account(s)
          </span>
        </div>

        {verifiedAccounts.length === 0 ? (
          <div className="p-8 text-center text-[#64748B] space-y-2">
            <p className="text-sm font-bold text-[#94A3B8]">
              NO VERIFIED TRADING ACCOUNTS CONNECTED
            </p>
            <p className="text-[11px] text-[#64748B] max-w-lg mx-auto">
              Click <strong>Connect Exness API</strong> and supply your active Exness API Key, Ed25519 Private Signing Key, and Trading Account ID(s) to authenticate. Unverified accounts are never displayed as connected trading accounts.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse bitdex-responsive-table-cards">
              <thead>
                <tr className="border-b border-[#1E2736] text-[10px] uppercase text-[#64748B] bg-[#080B10]/50">
                  <th className="py-3 px-4 font-bold">Account</th>
                  <th className="py-3 px-4 font-bold">Environment</th>
                  <th className="py-3 px-4 font-bold">Account type</th>
                  <th className="py-3 px-4 font-bold">Currency</th>
                  <th className="py-3 px-4 font-bold text-right">Balance</th>
                  <th className="py-3 px-4 font-bold text-right">Equity</th>
                  <th className="py-3 px-4 font-bold">Status</th>
                  <th className="py-3 px-4 font-bold text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1E2736] text-xs">
                {verifiedAccounts.map((c: any) => {
                  const isResyncing = resyncingId === c.connection_id;
                  const env = c.account_type || "ENVIRONMENT UNVERIFIED";
                  const tier = c.account_tier || "Exness Native";

                  return (
                    <tr
                      key={c.connection_id}
                      className="hover:bg-[#151C28]/40 transition-colors"
                    >
                      <td data-label="Account" className="py-3.5 px-4 font-bold text-white">
                        <div className="flex items-center gap-2">
                          <span>{c.account_login}</span>
                          {c.is_preferred && (
                            <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-[#F59E0B]/15 text-[#F59E0B] border border-[#F59E0B]/30 flex items-center gap-1">
                              <Star className="w-2.5 h-2.5 fill-current" />
                              <span>PREFERRED</span>
                            </span>
                          )}
                        </div>
                      </td>
                      <td data-label="Environment" className="py-3.5 px-4">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                            env === "REAL"
                              ? "bg-amber-950/60 text-amber-400 border-amber-500/30"
                              : env === "DEMO"
                              ? "bg-sky-950/60 text-sky-400 border-sky-500/30"
                              : "bg-slate-800 text-slate-300 border-slate-600"
                          }`}
                        >
                          {env}
                        </span>
                      </td>
                      <td data-label="Account type" className="py-3.5 px-4 text-[#94A3B8]">
                        {tier}
                      </td>
                      <td data-label="Currency" className="py-3.5 px-4 font-bold text-[#F1F5F9]">
                        {c.currency || "USD"}
                      </td>
                      <td data-label="Balance" className="py-3.5 px-4 text-right font-bold text-white tabular-nums">
                        {c.balance_usd !== null && c.balance_usd !== undefined
                          ? Number(c.balance_usd).toFixed(2)
                          : "—"}
                      </td>
                      <td data-label="Equity" className="py-3.5 px-4 text-right text-[#38BDF8] font-bold tabular-nums">
                        {c.equity_usd !== null && c.equity_usd !== undefined
                          ? Number(c.equity_usd).toFixed(2)
                          : "—"}
                      </td>
                      <td data-label="Status" className="py-3.5 px-4">
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-950/60 text-emerald-400 border border-emerald-500/30">
                          VERIFIED
                        </span>
                      </td>
                      <td data-label="Actions" className="py-3.5 px-4 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            type="button"
                            onClick={() => handleResync(c.connection_id)}
                            disabled={isResyncing}
                            className="px-2.5 py-1 rounded-lg bg-[#151C28] hover:bg-[#1E2736] border border-[#1E2736] text-[#38BDF8] transition-colors flex items-center gap-1 cursor-pointer disabled:opacity-50"
                            title="Re-authenticate with Exness"
                          >
                            <RefreshCw className={`w-3 h-3 ${isResyncing ? "animate-spin" : ""}`} />
                            <span>Resync</span>
                          </button>
                          {!c.is_preferred && (
                            <button
                              type="button"
                              onClick={() => handleSetPreferred(c.connection_id)}
                              className="p-1.5 rounded-lg bg-[#151C28] hover:bg-[#1E2736] text-[#94A3B8] hover:text-[#F59E0B] transition-colors"
                              title="Set as Preferred"
                            >
                              <Star className="w-3.5 h-3.5" />
                            </button>
                          )}
                          <button
                            type="button"
                            onClick={() => handleDisconnect(c.connection_id)}
                            className="p-1.5 rounded-lg bg-[#151C28] hover:bg-rose-950/40 text-[#64748B] hover:text-rose-400 transition-colors"
                            title="Disconnect Account"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ─── FAILED / UNVERIFIED AUTHENTICATION DIAGNOSTICS ────────── */}
      {failedAccounts.length > 0 && (
        <div className="p-4 rounded-2xl bg-rose-950/20 border border-rose-500/30 space-y-3">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div className="flex items-center gap-2 text-rose-300 font-bold">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>
                Unverified / Failed Authentication Attempts ({failedAccounts.length})
              </span>
            </div>
            <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-rose-950/80 text-rose-300 border border-rose-500/30">
              EXCLUDED FROM ACTIVE TRADING SELECTORS
            </span>
          </div>
          <div className="space-y-2 text-[11px] text-[#94A3B8]">
            {failedAccounts.slice(0, 4).map((f: any, idx: number) => (
              <div
                key={f.connection_id || idx}
                className="p-3 rounded-xl bg-[#0E131B] border border-[#1E2736] flex flex-wrap items-center justify-between gap-3"
              >
                <div className="space-y-1 flex-1 min-w-[220px]">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-bold text-white">
                      Account: {f.account_login || f.account_id_masked || f.account_id}
                    </span>
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-800 text-slate-300 border border-slate-700">
                      ENVIRONMENT UNVERIFIED
                    </span>
                    <span className="text-rose-400 font-mono font-bold">
                      {f.error_type || "AUTHENTICATION_FAILED"}
                    </span>
                  </div>
                  <p className="text-xs text-rose-200/90 leading-relaxed break-words">
                    {f.error_detail}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => handleDisconnect(f.connection_id)}
                    className="px-2.5 py-1 rounded-lg bg-[#151C28] hover:bg-rose-950/40 text-[#94A3B8] hover:text-rose-300 border border-[#1E2736] text-[10px] transition-colors cursor-pointer"
                  >
                    Remove Entry
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ─── INSTITUTIONAL SECURITY NOTICE ─────────────────────────── */}
      <div className="p-4 rounded-xl bg-[#080B10] border border-[#1E2736] flex flex-wrap items-center justify-between gap-3 text-xs text-[#94A3B8]">
        <div className="flex items-center gap-2">
          <Lock className="w-4 h-4 text-[#38BDF8] shrink-0" />
          <span>
            API keys and Ed25519 private signing keys are encrypted server-side using AES-256-GCM authenticated vault storage.
          </span>
        </div>
        <span className="text-[10px] text-[#64748B] shrink-0 font-bold">
          SERVER-SIDE VAULT ISOLATION
        </span>
      </div>

      {/* ─── TASK 1A: SIMPLIFIED UNIVERSAL EXNESS CONNECTION MODAL ──── */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-[#080B10]/85 backdrop-blur-md animate-in fade-in duration-200">
          <div className="relative w-full max-w-lg bg-[#0E131B] border border-[#1E2736] rounded-2xl shadow-2xl overflow-hidden font-mono text-xs flex flex-col max-h-[92vh]">
            {/* Modal Header */}
            <div className="px-5 py-4 border-b border-[#1E2736] flex items-center justify-between bg-[#151C28]/60">
              <div className="flex items-center gap-2.5">
                <div className="w-7 h-7 rounded-lg bg-[#38BDF8]/15 text-[#38BDF8] border border-[#38BDF8]/30 flex items-center justify-center font-bold shrink-0">
                  EXN
                </div>
                <div>
                  <h3 className="font-bold text-[#F1F5F9]">
                    Universal Exness API Connection
                  </h3>
                  <span className="text-[10px] text-[#64748B] block">
                    Automatic Gateway Discovery &bull; Demo &amp; Real Classification
                  </span>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setIsModalOpen(false)}
                className="p-1.5 rounded-lg text-[#64748B] hover:text-[#F1F5F9] hover:bg-[#1E2736] transition-colors cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Modal Form — Only 3 Required Inputs */}
            <form onSubmit={handleDiscoverAndAttach} className="p-5 space-y-4 overflow-y-auto">
              {statusMsg && (
                <div
                  className={`p-3.5 rounded-xl border text-xs space-y-1 ${
                    statusMsg.type === "success"
                      ? "bg-emerald-950/30 text-emerald-300 border-emerald-500/40"
                      : "bg-rose-950/30 text-rose-300 border-rose-500/40"
                  }`}
                >
                  <div className="flex items-center gap-2 font-bold">
                    {statusMsg.type === "success" ? (
                      <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-400" />
                    ) : (
                      <AlertTriangle className="w-4 h-4 shrink-0 text-rose-400" />
                    )}
                    <span>{statusMsg.text}</span>
                  </div>
                  {statusMsg.details && (
                    <p className="text-[11px] opacity-90 pl-6 leading-relaxed break-words">
                      {statusMsg.details}
                    </p>
                  )}
                </div>
              )}

              {/* Field 1: Exness API Key */}
              <div className="space-y-1.5">
                <label className="text-[10px] uppercase text-[#94A3B8] block font-bold">
                  1. Exness API Key
                </label>
                <input
                  type="text"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder="exnsk-..."
                  required
                  className="w-full px-3 py-2.5 rounded-lg bg-[#151C28] border border-[#1E2736] text-[#F1F5F9] focus:outline-none focus:border-[#38BDF8]"
                />
              </div>

              {/* Field 2: Ed25519 Private Signing Key */}
              <div className="space-y-1.5">
                <label className="text-[10px] uppercase text-[#94A3B8] block font-bold">
                  2. Ed25519 Private Signing Key
                </label>
                <input
                  type="password"
                  value={apiSecret}
                  onChange={(e) => setApiSecret(e.target.value)}
                  placeholder="Paste Ed25519 private signing key (Hex or PEM)"
                  required
                  className="w-full px-3 py-2.5 rounded-lg bg-[#151C28] border border-[#1E2736] text-[#F1F5F9] focus:outline-none focus:border-[#38BDF8]"
                />
              </div>

              {/* Field 3: Exness Trading Account ID(s) */}
              <div className="space-y-1.5">
                <label className="text-[10px] uppercase text-[#94A3B8] block font-bold">
                  3. Exness Trading Account ID(s)
                </label>
                <input
                  type="text"
                  value={candidateAccountIds}
                  onChange={(e) => setCandidateAccountIds(e.target.value)}
                  placeholder="Enter one or more Account IDs (comma-separated)"
                  required
                  className="w-full px-3 py-2.5 rounded-lg bg-[#151C28] border border-[#1E2736] text-[#F1F5F9] focus:outline-none focus:border-[#38BDF8]"
                />
                <p className="text-[10px] text-[#64748B] leading-relaxed">
                  BITDEX automatically resolves each account&apos;s Access Point, retrieves its genuine currency, balance, and equity, and classifies Demo vs Real from Exness metadata.
                </p>
              </div>

              {/* Optional Collapsed Advanced Fallback for Gateway Host */}
              <details className="rounded-xl bg-[#151C28]/50 border border-[#1E2736] p-3 text-[11px]">
                <summary className="cursor-pointer text-[#94A3B8] font-bold flex items-center justify-between select-none">
                  <span>Advanced Fallback: Gateway Host (Automatic Default: api.exness.com)</span>
                  <ChevronRight className="w-3.5 h-3.5 text-[#64748B]" />
                </summary>
                <div className="pt-3 space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setGatewayHost("https://api.exness.com")}
                      className={`px-2.5 py-1 rounded text-[10px] font-mono cursor-pointer ${
                        gatewayHost === "https://api.exness.com"
                          ? "bg-[#38BDF8]/20 text-[#38BDF8] border border-[#38BDF8]/40 font-bold"
                          : "bg-[#0E131B] text-[#94A3B8] border border-[#1E2736]"
                      }`}
                    >
                      Main DNS: api.exness.com
                    </button>
                    <button
                      type="button"
                      onClick={() => setGatewayHost("https://api.exness-api.com")}
                      className={`px-2.5 py-1 rounded text-[10px] font-mono cursor-pointer ${
                        gatewayHost === "https://api.exness-api.com"
                          ? "bg-[#38BDF8]/20 text-[#38BDF8] border border-[#38BDF8]/40 font-bold"
                          : "bg-[#0E131B] text-[#94A3B8] border border-[#1E2736]"
                      }`}
                    >
                      Alternative DNS: api.exness-api.com
                    </button>
                  </div>
                  <input
                    type="text"
                    value={gatewayHost}
                    onChange={(e) => setGatewayHost(e.target.value)}
                    placeholder="https://api.exness.com"
                    className="w-full px-3 py-2 rounded-lg bg-[#0E131B] border border-[#1E2736] text-[#38BDF8] focus:outline-none focus:border-[#38BDF8] font-mono text-xs"
                  />
                </div>
              </details>

              {/* Modal Actions */}
              <div className="pt-3 flex flex-wrap items-center justify-end gap-2.5 border-t border-[#1E2736]">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 rounded-xl bg-[#151C28] hover:bg-[#1E2736] text-[#94A3B8] transition-colors cursor-pointer"
                >
                  Cancel
                </button>

                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-5 py-2 rounded-xl bg-[#38BDF8] text-[#080B10] font-bold hover:bg-[#38BDF8]/90 transition-all flex items-center gap-1.5 disabled:opacity-50 cursor-pointer shadow-md shadow-[#38BDF8]/20"
                >
                  {isSubmitting ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      <span>Authenticating...</span>
                    </>
                  ) : (
                    <>
                      <ShieldCheck className="w-3.5 h-3.5" />
                      <span>Authenticate &amp; Connect</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
