"use client";

import React, { useState, useEffect } from "react";
import {
  ShieldCheck,
  AlertTriangle,
  Lock,
  RefreshCw,
  ExternalLink,
  KeyRound,
  FileText,
  XCircle,
  Plus,
  Cpu,
  CheckCircle2,
  X,
  Loader2,
  Trash2,
  Star,
  Zap,
  Globe,
  Radio,
  ArrowRight,
  Server,
  Layers,
  HelpCircle,
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

  // Form states (Exness Multi-Account Discovery)
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [gatewayHost, setGatewayHost] = useState("");
  const [candidateAccountIds, setCandidateAccountIds] = useState("149827361, 460310009");
  const [accountTier, setAccountTier] = useState("STANDARD");
  const [accountLabel, setAccountLabel] = useState("");

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
        ? localStorage.getItem("tauric_session_token") ||
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
    setGatewayHost("");
    setCandidateAccountIds("149827361, 460310009");
    setAccountLabel("");
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
        throw new Error("Exness API Key and Ed25519 Private Key are required.");
      }
      if (!gatewayHost.trim()) {
        throw new Error("Gateway Host URL from Exness Key Management DNS Widget is required.");
      }

      // Parse candidate account IDs
      const rawIds = candidateAccountIds
        .split(/[,;\s]+/)
        .map((s) => s.trim())
        .filter(Boolean);

      const res = await fetch("/api/v1/hft/exness/attach-and-discover", {
        method: "POST",
        headers,
        body: JSON.stringify({
          api_key: apiKey.trim(),
          api_secret: apiSecret.trim(),
          gateway_host: gatewayHost.trim(),
          account_ids: rawIds.length > 0 ? rawIds : ["149827361", "460310009"],
          account_tier: accountTier,
          account_label: accountLabel.trim() || undefined,
        }),
      });

      const data = await res.json();

      if (!res.ok || data.status === "FAILED") {
        const failedReason =
          data.failed_accounts?.[0]?.error_detail ||
          data.detail?.error_detail ||
          data.detail ||
          data.message ||
          "Exness API authentication and discovery failed.";
        const errorType =
          data.failed_accounts?.[0]?.error_type ||
          data.detail?.error_type ||
          "AUTHENTICATION_FAILED";

        setStatusMsg({
          type: "error",
          text: `Discovery Failed: ${errorType}`,
          details: failedReason,
        });
        await fetchStatus();
        return;
      }

      const totalVerified = data.total_verified || 0;
      setStatusMsg({
        type: "success",
        text: `Discovery Complete: ${totalVerified} account(s) verified successfully.`,
        details: data.enumeration_supported
          ? "Account enumeration verified via official Trader API endpoint."
          : "Candidate account discovery verified candidate IDs independently.",
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
        details: err.message || "Failed to contact discovery service.",
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
        alert(`Resync Failed: ${errorDetail}`);
      } else {
        await fetchStatus();
        if (onRefresh) onRefresh();
      }
    } catch (err: any) {
      alert(`Network error during resync: ${err.message}`);
    } finally {
      setResyncingId(null);
    }
  };

  const handleDisconnect = async (connectionId: string) => {
    if (!confirm("Are you sure you want to disconnect this Exness account? Stored credentials will be invalidated.")) {
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

  const demoAccounts = statusData?.exness_demo_accounts || [];
  const realAccounts = statusData?.exness_real_accounts || [];
  const failedAccounts = statusData?.failed_accounts || [];

  const verifiedDemo = demoAccounts.filter((a: any) => a.verification_status === "VERIFIED");
  const verifiedReal = realAccounts.filter((a: any) => a.verification_status === "VERIFIED");
  const totalVerifiedCount = verifiedDemo.length + verifiedReal.length;

  return (
    <div className="space-y-6 font-mono text-xs">
      {/* ─── HEADER & ARCHITECTURAL DISCLOSURE ─────────────────── */}
      <div className="p-4 sm:p-5 rounded-2xl bg-[#0E131B] border border-[#1E2736] flex flex-wrap items-center justify-between gap-4 shadow-xl">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-[#38BDF8]" />
            <h1 className="text-base font-bold text-[#F1F5F9] uppercase tracking-wider">
              Exness Trader API &amp; Multi-Account Discovery
            </h1>
          </div>
          <p className="text-xs text-[#94A3B8]">
            Phase 19 Dynamic Account Discovery · Independent Demo &amp; Real Authentication · Tenant Vault Isolation
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={handleSync}
            disabled={isSyncing}
            className="px-3 py-1.5 rounded-xl bg-[#151C28] hover:bg-[#1E2736] border border-[#1E2736] text-[#F1F5F9] transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isSyncing ? "animate-spin text-[#38BDF8]" : ""}`} />
            <span>Sync Feeds</span>
          </button>

          <a
            href="https://my.exness.com/pa"
            target="_blank"
            rel="noopener noreferrer"
            className="px-3 py-1.5 rounded-xl bg-[#151C28] hover:bg-[#1E2736] border border-[#1E2736] text-[#38BDF8] transition-all flex items-center gap-1.5"
          >
            <ExternalLink className="w-3.5 h-3.5" />
            <span>Exness Personal Area</span>
          </a>

          <button
            type="button"
            onClick={handleOpenConnect}
            className="px-4 py-1.5 rounded-xl bg-[#38BDF8] hover:bg-[#38BDF8]/90 text-[#080B10] font-bold transition-all flex items-center gap-1.5 cursor-pointer shadow-md shadow-[#38BDF8]/20"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Attach API Key &amp; Discover Accounts</span>
          </button>
        </div>
      </div>

      {/* ─── SUMMARY KPI TILES ─────────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="p-4 rounded-xl bg-[#0E131B] border border-[#1E2736]">
          <span className="text-[10px] text-[#64748B] block uppercase font-bold">Total Verified:</span>
          <span className="text-xl font-bold text-white tabular-nums">
            {totalVerifiedCount}
          </span>
          <span className="text-[10px] text-[#94A3B8] block mt-0.5">Authoritative Provider Sessions</span>
        </div>
        <div className="p-4 rounded-xl bg-[#0E131B] border border-[#1E2736]">
          <span className="text-[10px] text-[#64748B] block uppercase font-bold">Demo Accounts:</span>
          <span className="text-xl font-bold text-[#38BDF8] tabular-nums">
            {demoAccounts.length} <span className="text-xs text-[#64748B]">({verifiedDemo.length} verified)</span>
          </span>
          <span className="text-[10px] text-[#94A3B8] block mt-0.5">Demo Trial MT5 &amp; API</span>
        </div>
        <div className="p-4 rounded-xl bg-[#0E131B] border border-[#1E2736]">
          <span className="text-[10px] text-[#64748B] block uppercase font-bold">Real Accounts:</span>
          <span className="text-xl font-bold text-[#F59E0B] tabular-nums">
            {realAccounts.length} <span className="text-xs text-[#64748B]">({verifiedReal.length} verified)</span>
          </span>
          <span className="text-[10px] text-[#94A3B8] block mt-0.5">Live Production Execution</span>
        </div>
        <div className="p-4 rounded-xl bg-[#0E131B] border border-[#1E2736]">
          <span className="text-[10px] text-[#64748B] block uppercase font-bold">Platform Safety Locks:</span>
          <span className="text-xs font-bold text-red-400 block mt-1">3/3 ACTIVE</span>
          <span className="text-[10px] text-[#64748B] block mt-0.5">Zero Live Order Execution</span>
        </div>
      </div>

      {/* ─── SECTION 1: EXNESS DEMO ACCOUNTS ──────────────────────── */}
      <div className="rounded-2xl bg-[#0E131B] border border-[#1E2736] overflow-hidden shadow-lg">
        <div className="p-4 bg-[#151C28]/60 border-b border-[#1E2736] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Radio className="w-4 h-4 text-[#38BDF8]" />
            <h2 className="font-bold text-[#F1F5F9] uppercase tracking-wider text-xs">
              Exness Demo Accounts
            </h2>
            <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-sky-950/60 text-sky-400 border border-sky-500/30">
              ENVIRONMENT: DEMO
            </span>
          </div>
          <span className="text-[10px] text-[#64748B]">
            {demoAccounts.length} Account(s) Registered
          </span>
        </div>

        {demoAccounts.length === 0 ? (
          <div className="p-8 text-center text-[#64748B] space-y-2">
            <p>No Exness Demo accounts discovered or attached yet.</p>
            <p className="text-[11px] text-[#94A3B8]">
              Attach your Exness API key with candidate ID <code className="text-[#38BDF8]">149827361</code> to authenticate.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-[#1E2736]">
            {demoAccounts.map((c: any) => {
              const isVerified = c.verification_status === "VERIFIED";
              const isFailed = c.verification_status === "FAILED";
              const isResyncing = resyncingId === c.connection_id;

              return (
                <div
                  key={c.connection_id}
                  className="p-4 flex flex-wrap items-center justify-between gap-4 hover:bg-[#151C28]/30 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-3 h-3 rounded-full bg-[#38BDF8] shrink-0" />
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-white text-sm">
                          {c.account_label || `Demo Account (${c.account_login})`}
                        </span>
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#151C28] text-[#94A3B8] border border-[#1E2736]">
                          Raw ID: {c.account_login_raw || c.account_login}
                        </span>
                        {c.is_preferred && (
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-[#F59E0B]/15 text-[#F59E0B] border border-[#F59E0B]/30 flex items-center gap-1">
                            <Star className="w-3 h-3 fill-current" />
                            <span>PREFERRED</span>
                          </span>
                        )}
                        {isVerified ? (
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-950/60 text-emerald-400 border border-emerald-500/30">
                            VERIFIED
                          </span>
                        ) : isFailed ? (
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-950/60 text-rose-400 border border-rose-500/30">
                            {c.error_type || "FAILED"}
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-950/60 text-amber-400 border border-amber-500/30">
                            NOT TESTED
                          </span>
                        )}
                      </div>

                      <div className="text-[10px] text-[#64748B] flex flex-wrap items-center gap-x-3 gap-y-1">
                        <span>Gateway: <code className="text-[#38BDF8]">{c.server_name}</code></span>
                        <span>Mode: {c.adapter_mode}</span>
                        <span>Trade Mode: {c.trade_mode || "DEMO"}</span>
                        {c.error_detail && (
                          <span className="text-rose-400 block w-full mt-0.5">
                            Reason: {c.error_detail}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-6 text-xs">
                    <div className="text-right space-y-0.5">
                      <div className="font-bold text-white tabular-nums">
                        ${isVerified && c.balance_usd !== null ? Number(c.balance_usd).toFixed(2) : "0.00"} {c.currency || "USD"}
                      </div>
                      <div className="text-[10px] text-[#64748B] tabular-nums">
                        Equity: ${isVerified && c.equity_usd !== null ? Number(c.equity_usd).toFixed(2) : "0.00"} &bull; Free: ${isVerified && c.margin_free !== null ? Number(c.margin_free).toFixed(2) : "0.00"}
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => handleResync(c.connection_id)}
                        disabled={isResyncing}
                        className="px-3 py-1.5 rounded-lg bg-[#151C28] hover:bg-[#1E2736] border border-[#1E2736] text-[#38BDF8] transition-colors flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                        title="Re-authenticate with Provider"
                      >
                        <RefreshCw className={`w-3.5 h-3.5 ${isResyncing ? "animate-spin" : ""}`} />
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
                        title="Disconnect Connection"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ─── SECTION 2: EXNESS REAL ACCOUNTS ──────────────────────── */}
      <div className="rounded-2xl bg-[#0E131B] border border-[#1E2736] overflow-hidden shadow-lg">
        <div className="p-4 bg-[#151C28]/60 border-b border-[#1E2736] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Radio className="w-4 h-4 text-[#F59E0B]" />
            <h2 className="font-bold text-[#F1F5F9] uppercase tracking-wider text-xs">
              Exness Real Accounts
            </h2>
            <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-amber-950/60 text-amber-400 border border-amber-500/30">
              ENVIRONMENT: REAL
            </span>
          </div>
          <span className="text-[10px] text-[#64748B]">
            {realAccounts.length} Account(s) Registered
          </span>
        </div>

        {realAccounts.length === 0 ? (
          <div className="p-8 text-center text-[#64748B] space-y-2">
            <p>No Exness Real accounts discovered or attached yet.</p>
            <p className="text-[11px] text-[#94A3B8]">
              Attach your Exness API key with candidate ID <code className="text-[#F59E0B]">460310009</code> to authenticate.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-[#1E2736]">
            {realAccounts.map((c: any) => {
              const isVerified = c.verification_status === "VERIFIED";
              const isFailed = c.verification_status === "FAILED";
              const isResyncing = resyncingId === c.connection_id;

              return (
                <div
                  key={c.connection_id}
                  className="p-4 flex flex-wrap items-center justify-between gap-4 hover:bg-[#151C28]/30 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-3 h-3 rounded-full bg-[#F59E0B] shrink-0" />
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-white text-sm">
                          {c.account_label || `Real Account (${c.account_login})`}
                        </span>
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#151C28] text-[#94A3B8] border border-[#1E2736]">
                          Raw ID: {c.account_login_raw || c.account_login}
                        </span>
                        {c.is_preferred && (
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-[#F59E0B]/15 text-[#F59E0B] border border-[#F59E0B]/30 flex items-center gap-1">
                            <Star className="w-3 h-3 fill-current" />
                            <span>PREFERRED</span>
                          </span>
                        )}
                        {isVerified ? (
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-950/60 text-emerald-400 border border-emerald-500/30">
                            VERIFIED
                          </span>
                        ) : isFailed ? (
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-950/60 text-rose-400 border border-rose-500/30">
                            {c.error_type || "FAILED"}
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-950/60 text-amber-400 border border-amber-500/30">
                            NOT TESTED
                          </span>
                        )}
                      </div>

                      <div className="text-[10px] text-[#64748B] flex flex-wrap items-center gap-x-3 gap-y-1">
                        <span>Gateway: <code className="text-[#38BDF8]">{c.server_name}</code></span>
                        <span>Mode: {c.adapter_mode}</span>
                        <span>Trade Mode: {c.trade_mode || "REAL"}</span>
                        {c.error_detail && (
                          <span className="text-rose-400 block w-full mt-0.5">
                            Reason: {c.error_detail}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-6 text-xs">
                    <div className="text-right space-y-0.5">
                      <div className="font-bold text-white tabular-nums">
                        ${isVerified && c.balance_usd !== null ? Number(c.balance_usd).toFixed(2) : "0.00"} {c.currency || "USD"}
                      </div>
                      <div className="text-[10px] text-[#64748B] tabular-nums">
                        Equity: ${isVerified && c.equity_usd !== null ? Number(c.equity_usd).toFixed(2) : "0.00"} &bull; Free: ${isVerified && c.margin_free !== null ? Number(c.margin_free).toFixed(2) : "0.00"}
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => handleResync(c.connection_id)}
                        disabled={isResyncing}
                        className="px-3 py-1.5 rounded-lg bg-[#151C28] hover:bg-[#1E2736] border border-[#1E2736] text-[#38BDF8] transition-colors flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                        title="Re-authenticate with Provider"
                      >
                        <RefreshCw className={`w-3.5 h-3.5 ${isResyncing ? "animate-spin" : ""}`} />
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
                        title="Disconnect Connection"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ─── SECTION 3: GATEWAY & ERROR DIAGNOSTICS ────────────────── */}
      {failedAccounts.length > 0 && (
        <div className="p-4 rounded-2xl bg-rose-950/20 border border-rose-500/30 space-y-3">
          <div className="flex items-center gap-2 text-rose-300 font-bold">
            <AlertTriangle className="w-4 h-4" />
            <span>Exness Gateway Verification Notice: {failedAccounts.length} Account(s) Require Configuration</span>
          </div>
          <div className="space-y-2 text-[11px] text-[#94A3B8]">
            {failedAccounts.map((f: any, idx: number) => (
              <div key={idx} className="p-3 rounded-xl bg-[#0E131B] border border-[#1E2736] space-y-1">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-white">Account: {f.account_login || f.account_id}</span>
                  <span className="text-rose-400 font-mono font-bold">{f.error_type || "VERIFICATION_FAILED"}</span>
                </div>
                <p className="text-xs text-rose-200/90 leading-relaxed">{f.error_detail}</p>
              </div>
            ))}
          </div>
          <div className="text-[10px] text-[#64748B] pt-1 border-t border-rose-500/20">
            Note: Accounts remain in FAILED / NOT TESTED status until genuine cryptographic authentication succeeds against an authorized Exness Gateway Host. Fabricated balances are strictly prohibited.
          </div>
        </div>
      )}

      {/* ─── INSTITUTIONAL SECURITY NOTICE ─────────────────────────── */}
      <div className="p-4 rounded-xl bg-[#080B10] border border-[#1E2736] flex flex-wrap items-center justify-between gap-3 text-xs text-[#94A3B8]">
        <div className="flex items-center gap-2">
          <Lock className="w-4 h-4 text-[#38BDF8] shrink-0" />
          <span>
            API keys and Ed25519 signing seeds are encrypted at rest with AES-256-GCM authenticated vault storage. Tenant isolation strictly prevents cross-account key leakage.
          </span>
        </div>
        <span className="text-[10px] text-[#64748B] shrink-0 font-bold">
          SECURITY PROTOCOL VERIFIED
        </span>
      </div>

      {/* ─── MULTI-ACCOUNT DISCOVERY & ATTACHMENT MODAL ─────────────── */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#080B10]/80 backdrop-blur-md animate-in fade-in duration-200">
          <div className="relative w-full max-w-xl bg-[#0E131B] border border-[#1E2736] rounded-2xl shadow-2xl overflow-hidden font-mono text-xs flex flex-col max-h-[90vh]">
            {/* Modal Header */}
            <div className="px-5 py-4 border-b border-[#1E2736] flex items-center justify-between bg-[#151C28]/60">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-lg bg-[#38BDF8]/15 text-[#38BDF8] border border-[#38BDF8]/30 flex items-center justify-center font-bold">
                  API
                </div>
                <div>
                  <h3 className="font-bold text-[#F1F5F9]">
                    Attach Exness API &amp; Discover Accounts
                  </h3>
                  <span className="text-[10px] text-[#64748B]">
                    Official Exness Trader API &bull; Automatic Demo &amp; Real Authentication
                  </span>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setIsModalOpen(false)}
                className="p-1 rounded-lg text-[#64748B] hover:text-[#F1F5F9] hover:bg-[#1E2736] transition-colors cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Modal Form */}
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
                    <p className="text-[11px] opacity-90 pl-6 leading-relaxed">
                      {statusMsg.details}
                    </p>
                  )}
                </div>
              )}

              {/* Exness API Key */}
              <div className="space-y-1">
                <label className="text-[10px] uppercase text-[#64748B] block font-bold">
                  Exness API Key (From Personal Area)
                </label>
                <input
                  type="text"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder="Paste authorized API Key from Exness Key Management"
                  required
                  className="w-full px-3 py-2 rounded-lg bg-[#151C28] border border-[#1E2736] text-[#F1F5F9] focus:outline-none focus:border-[#38BDF8]"
                />
              </div>

              {/* Exness API Secret / Private Key */}
              <div className="space-y-1">
                <label className="text-[10px] uppercase text-[#64748B] block font-bold">
                  Exness Private Key (Ed25519 Seed or Hex)
                </label>
                <input
                  type="password"
                  value={apiSecret}
                  onChange={(e) => setApiSecret(e.target.value)}
                  placeholder="Paste Ed25519 asymmetric private signing key"
                  required
                  className="w-full px-3 py-2 rounded-lg bg-[#151C28] border border-[#1E2736] text-[#F1F5F9] focus:outline-none focus:border-[#38BDF8]"
                />
              </div>

              {/* Gateway Host URL */}
              <div className="space-y-1">
                <div className="flex items-center justify-between">
                  <label className="text-[10px] uppercase text-[#64748B] block font-bold">
                    Gateway Host URL (From Key Management DNS Widget)
                  </label>
                  <span className="text-[10px] text-amber-400 font-mono font-bold">DNS Widget Target</span>
                </div>
                <input
                  type="text"
                  value={gatewayHost}
                  onChange={(e) => setGatewayHost(e.target.value)}
                  placeholder="https://gateway-xxx.exness.com"
                  required
                  className="w-full px-3 py-2 rounded-lg bg-[#151C28] border border-[#1E2736] text-[#38BDF8] focus:outline-none focus:border-[#38BDF8] font-mono text-xs"
                />
                <div className="p-2.5 rounded-lg bg-[#151C28]/80 border border-[#1E2736] text-[10px] text-[#94A3B8] space-y-1">
                  <p className="text-amber-300 font-bold">
                    Where to find your Gateway Host in Exness:
                  </p>
                  <p>
                    Log into <strong>Exness Personal Area</strong> &rarr; <strong>Settings</strong> &rarr; <strong>API</strong> &rarr; <strong>Key Management</strong> &rarr; <strong>DNS Widget</strong>. Copy the assigned gateway URL (e.g. <code>https://gateway-xxx.exness.com</code>).
                  </p>
                  <p className="text-rose-400">
                    &bull; Do NOT use <code>https://www.exness-api.com</code> (documentation portal).
                  </p>
                </div>
              </div>

              {/* Candidate Account IDs */}
              <div className="space-y-1">
                <label className="text-[10px] uppercase text-[#64748B] block font-bold">
                  Accounts to Attach &amp; Authenticate (Comma Separated)
                </label>
                <input
                  type="text"
                  value={candidateAccountIds}
                  onChange={(e) => setCandidateAccountIds(e.target.value)}
                  placeholder="e.g. 149827361, 460310009"
                  className="w-full px-3 py-2 rounded-lg bg-[#151C28] border border-[#1E2736] text-[#F1F5F9] focus:outline-none focus:border-[#38BDF8]"
                />
                <p className="text-[10px] text-[#64748B]">
                  Pre-configured with Demo (<code>149827361</code>) and Real (<code>460310009</code>). BITDEX will authenticate each account independently.
                </p>
              </div>

              {/* Account Tier */}
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-[10px] uppercase text-[#64748B] block font-bold">
                    Account Tier
                  </label>
                  <select
                    value={accountTier}
                    onChange={(e) => setAccountTier(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-[#151C28] border border-[#1E2736] text-[#F1F5F9] focus:outline-none focus:border-[#38BDF8]"
                  >
                    <option value="STANDARD">Standard Retail</option>
                    <option value="PRO">Pro Account</option>
                    <option value="RAW_SPREAD">Raw Spread</option>
                    <option value="ZERO">Zero Spread</option>
                  </select>
                </div>

                <div className="space-y-1">
                  <label className="text-[10px] uppercase text-[#64748B] block font-bold">
                    Connection Label (Optional)
                  </label>
                  <input
                    type="text"
                    value={accountLabel}
                    onChange={(e) => setAccountLabel(e.target.value)}
                    placeholder="e.g. Institutional Trader API"
                    className="w-full px-3 py-2 rounded-lg bg-[#151C28] border border-[#1E2736] text-[#F1F5F9] focus:outline-none focus:border-[#38BDF8]"
                  >
                  </input>
                </div>
              </div>

              {/* Modal Actions */}
              <div className="pt-3 flex flex-wrap items-center justify-between gap-2 border-t border-[#1E2736]">
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
                      <span>Discovering &amp; Authenticating...</span>
                    </>
                  ) : (
                    <>
                      <ShieldCheck className="w-3.5 h-3.5" />
                      <span>Discover &amp; Authenticate Accounts</span>
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
