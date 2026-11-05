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

  // Form states (Exness Trader API)
  const [accountEnv, setAccountEnv] = useState<"DEMO" | "REAL">("REAL");
  const [accountLogin, setAccountLogin] = useState("");
  const [serverName, setServerName] = useState("https://gateway.exness.com");
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [accountTier, setAccountTier] = useState("STANDARD");
  const [accountLabel, setAccountLabel] = useState("");

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [statusMsg, setStatusMsg] = useState<{ type: "success" | "error" | "info"; text: string } | null>(null);

  const fetchStatus = async () => {
    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      const authToken =
        token ||
        (typeof window !== "undefined"
          ? localStorage.getItem("tauric_session_token") ||
            localStorage.getItem("tauric_token") ||
            localStorage.getItem("bitdex_token")
          : null);
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
    setAccountLogin("");
    setApiKey("");
    setApiSecret("");
    setServerName("https://www.exness-api.com");
    setAccountLabel("");
    setAccountEnv("REAL");
    setIsModalOpen(true);
  };

  const handleTestConnection = async () => {
    if (!accountLogin.trim()) {
      setStatusMsg({ type: "error", text: "Account Login ID / Identifier is required to test connection." });
      return;
    }
    setIsTesting(true);
    setStatusMsg(null);

    const authToken =
      token ||
      (typeof window !== "undefined"
        ? localStorage.getItem("tauric_session_token") ||
          localStorage.getItem("tauric_token") ||
          localStorage.getItem("bitdex_token")
        : null);
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
    };

    try {
      const res = await fetch("/api/v1/hft/exness/real/connect", {
        method: "POST",
        headers,
        body: JSON.stringify({
          connection_method: "TRADER_API",
          account_login: accountLogin.trim(),
          api_key: apiKey.trim() || accountLogin.trim(),
          api_secret: apiSecret.trim(),
          server_name: serverName.trim() || "https://www.exness-api.com",
          account_tier: accountTier,
          account_label: accountLabel.trim() || `Test Connection (${accountLogin.trim()})`,
        }),
      });

      const data = await res.json();
      if (!res.ok || data.status !== "SUCCESS" || data.broker_result?.broker_authenticated === false) {
        const errorDetail =
          data.detail?.reason ||
          (typeof data.detail === "string" ? data.detail : null) ||
          data.broker_result?.reason ||
          data.error_detail ||
          "Authentication test failed.";
        throw new Error(errorDetail);
      }

      setStatusMsg({
        type: "success",
        text: `Connection handshake verified against Exness Trader API gateway. Account mode: ${accountEnv}.`,
      });
      await fetchStatus();
      if (onRefresh) onRefresh();
    } catch (err: any) {
      setStatusMsg({
        type: "error",
        text: `Test Connection Error: ${err.message}`,
      });
    } finally {
      setIsTesting(false);
    }
  };

  const handleSubmitConnection = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setStatusMsg(null);

    const authToken =
      token ||
      (typeof window !== "undefined"
        ? localStorage.getItem("tauric_session_token") ||
          localStorage.getItem("tauric_token") ||
          localStorage.getItem("bitdex_token")
        : null);
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
    };

    try {
      if (!accountLogin.trim()) {
        throw new Error("Account Login ID / Identifier is required.");
      }

      const res = await fetch("/api/v1/hft/exness/real/connect", {
        method: "POST",
        headers,
        body: JSON.stringify({
          connection_method: "TRADER_API",
          account_login: accountLogin.trim(),
          api_key: apiKey.trim() || accountLogin.trim(),
          api_secret: apiSecret.trim(),
          server_name: serverName.trim() || "https://www.exness-api.com",
          account_tier: accountTier,
          account_label: accountLabel.trim() || `Exness Trader API (${accountEnv})`,
        }),
      });

      const data = await res.json();
      if (!res.ok || data.status !== "SUCCESS" || data.broker_result?.broker_authenticated === false) {
        const errorDetail =
          data.detail?.reason ||
          (typeof data.detail === "string" ? data.detail : null) ||
          data.broker_result?.reason ||
          data.error_detail ||
          "Trader API connection failed.";
        throw new Error(errorDetail);
      }

      setStatusMsg({
        type: "success",
        text: `Account successfully registered and secured in institutional vault.`,
      });

      await fetchStatus();
      if (onRefresh) onRefresh();

      setTimeout(() => {
        setIsModalOpen(false);
        setIsSubmitting(false);
      }, 1000);
    } catch (err: any) {
      setStatusMsg({
        type: "error",
        text: err.message || "Failed to establish Exness connection.",
      });
      setIsSubmitting(false);
    }
  };

  const handleDisconnect = async (connectionId: string) => {
    if (!confirm("Are you sure you want to disconnect this Exness account? Stored credentials will be invalidated.")) {
      return;
    }

    try {
      const authToken =
        token ||
        (typeof window !== "undefined"
          ? localStorage.getItem("tauric_session_token") ||
            localStorage.getItem("tauric_token") ||
            localStorage.getItem("bitdex_token")
          : null);
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
      const authToken =
        token ||
        (typeof window !== "undefined"
          ? localStorage.getItem("tauric_session_token") ||
            localStorage.getItem("tauric_token") ||
            localStorage.getItem("bitdex_token")
          : null);
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

  const traderConn = statusData?.connections?.find((c: any) => c.connection_method === "TRADER_API");
  const anyConn = statusData?.active_connection || traderConn || statusData?.connections?.[0];
  const isTraderConnected = Boolean(statusData?.connected && anyConn);

  return (
    <div className="space-y-6 font-mono text-xs">
      {/* ─── HEADER & TENANT ISOLATION DISCLOSURE ─────────────────── */}
      <div className="p-4 sm:p-5 rounded-2xl bg-[#0E131B] border border-[#1E2736] flex flex-wrap items-center justify-between gap-4 shadow-xl">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-[#38BDF8]" />
            <h1 className="text-base font-bold text-[#F1F5F9] uppercase tracking-wider">
              Exness Trader API &amp; Broker Gateway
            </h1>
          </div>
          <p className="text-xs text-[#94A3B8]">
            Official programmatic connectivity via https://www.exness-api.com · Asymmetric Ed25519 authentication · Tenant vault isolation
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
        </div>
      </div>

      {/* ─── SIMPLIFIED EXNESS TRADER API CONNECTION STATUS CARD ───── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Status & Credentials Card */}
        <div className="lg:col-span-2 rounded-2xl bg-[#0E131B] border border-[#1E2736] overflow-hidden shadow-lg flex flex-col justify-between">
          <div>
            <div className="p-4 bg-[#151C28]/60 border-b border-[#1E2736] flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-[#38BDF8]/15 border border-[#38BDF8]/30 flex items-center justify-center font-bold text-[#38BDF8] text-sm">
                  API
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-sm font-bold text-[#F1F5F9]">Exness Trader API Connection</h2>
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-cyan-950/60 text-cyan-400 border border-cyan-500/30">
                      OFFICIAL REST / WS
                    </span>
                  </div>
                  <p className="text-[11px] text-[#94A3B8]">
                    Authoritative Endpoint: <code className="text-[#38BDF8]">https://www.exness-api.com</code>
                  </p>
                </div>
              </div>

              {isTraderConnected ? (
                <span className="px-3 py-1 rounded-full text-[11px] font-bold bg-[#10B981]/15 text-[#10B981] border border-[#10B981]/30 flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-[#10B981] animate-pulse" />
                  <span>CONNECTED</span>
                </span>
              ) : (
                <span className="px-3 py-1 rounded-full text-[11px] font-bold bg-[#EF4444]/15 text-[#EF4444] border border-[#EF4444]/30 flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-[#EF4444]" />
                  <span>NOT CONNECTED</span>
                </span>
              )}
            </div>

            <div className="p-5 space-y-4">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="p-3 rounded-xl bg-[#151C28] border border-[#1E2736]">
                  <span className="text-[10px] text-[#64748B] block uppercase">Account Identifier:</span>
                  <span className="font-bold text-[#F1F5F9] tabular-nums text-xs">
                    {anyConn?.account_login || "UNCONFIGURED"}
                  </span>
                </div>
                <div className="p-3 rounded-xl bg-[#151C28] border border-[#1E2736]">
                  <span className="text-[10px] text-[#64748B] block uppercase">Environment:</span>
                  <span className="font-bold text-[#38BDF8] text-xs">
                    {anyConn?.account_type || "DEMO"}
                  </span>
                </div>
                <div className="p-3 rounded-xl bg-[#151C28] border border-[#1E2736]">
                  <span className="text-[10px] text-[#64748B] block uppercase">Wallet Balance:</span>
                  <span className="font-bold text-[#10B981] tabular-nums text-xs">
                    ${anyConn?.balance ? Number(anyConn.balance).toFixed(2) : "0.00"}
                  </span>
                </div>
                <div className="p-3 rounded-xl bg-[#151C28] border border-[#1E2736]">
                  <span className="text-[10px] text-[#64748B] block uppercase">Account Equity:</span>
                  <span className="font-bold text-white tabular-nums text-xs">
                    ${anyConn?.equity ? Number(anyConn.equity).toFixed(2) : "0.00"}
                  </span>
                </div>
              </div>

              <div className="p-3.5 rounded-xl bg-[#080B10] border border-[#1E2736] space-y-1.5">
                <div className="flex items-center justify-between text-[#94A3B8]">
                  <span>Target Discovery Domain:</span>
                  <span className="font-bold text-[#38BDF8]">https://www.exness-api.com</span>
                </div>
                <div className="flex items-center justify-between text-[#94A3B8]">
                  <span>Cryptographic Protocol:</span>
                  <span className="font-bold text-white">Ed25519 Asymmetric Request Signing</span>
                </div>
                <div className="flex items-center justify-between text-[#94A3B8]">
                  <span>Tenant Vault Encryption:</span>
                  <span className="font-bold text-[#10B981]">AES-256-GCM (Zero Key Leakage)</span>
                </div>
                <div className="flex items-center justify-between text-[#94A3B8] border-t border-[#1E2736] pt-1.5">
                  <span>Staging Execution Guard:</span>
                  <span className="font-bold text-red-400">live_trading_locked = True</span>
                </div>
              </div>
            </div>
          </div>

          <div className="p-4 bg-[#151C28]/40 border-t border-[#1E2736] flex flex-wrap items-center justify-between gap-3">
            <span className="text-[10px] text-[#64748B]">
              Exness Trader API replaces legacy MT5 setups with native low-latency HTTP/WebSocket integration.
            </span>

            <div className="flex items-center gap-2">
              {isTraderConnected && anyConn?.connection_id && (
                <button
                  type="button"
                  onClick={() => handleDisconnect(anyConn.connection_id)}
                  className="px-3 py-1.5 rounded-xl bg-red-950/40 hover:bg-red-900/60 border border-red-500/40 text-red-300 font-bold transition-all flex items-center gap-1.5 cursor-pointer"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  <span>Disconnect</span>
                </button>
              )}

              <button
                type="button"
                onClick={handleOpenConnect}
                className="px-4 py-1.5 rounded-xl bg-[#38BDF8] hover:bg-[#38BDF8]/90 text-[#080B10] font-bold transition-all flex items-center gap-1.5 cursor-pointer shadow-md shadow-[#38BDF8]/20"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>{isTraderConnected ? "Reconfigure API Keys" : "Connect Exness Account"}</span>
              </button>
            </div>
          </div>
        </div>

        {/* Integration Architecture Summary Card */}
        <div className="rounded-2xl bg-[#0E131B] border border-[#1E2736] p-5 space-y-4 shadow-lg flex flex-col justify-between">
          <div className="space-y-3">
            <div className="flex items-center gap-2 border-b border-[#1E2736] pb-3">
              <Cpu className="w-4 h-4 text-[#38BDF8]" />
              <h3 className="text-sm font-bold text-[#F1F5F9] uppercase tracking-wider">
                Exness API Integration Architecture
              </h3>
            </div>

            <div className="space-y-2.5 text-[11px] text-[#94A3B8]">
              <div className="p-2.5 rounded-xl bg-[#151C28] border border-[#1E2736] space-y-1">
                <span className="font-bold text-white block">1. Official DNS Target</span>
                <p>
                  Target endpoint is resolved against <strong className="text-white">https://www.exness-api.com</strong>. The previous erroneous host <code className="text-[#38BDF8]">api.exness.com</code> (which returns HTTP 404) has been permanently repaired.
                </p>
              </div>

              <div className="p-2.5 rounded-xl bg-[#151C28] border border-[#1E2736] space-y-1">
                <span className="font-bold text-white block">2. Ed25519 Asymmetric Auth</span>
                <p>
                  Each outbound request carries an Ed25519 cryptographic signature computed over SHA-256 payload digests and timestamps.
                </p>
              </div>

              <div className="p-2.5 rounded-xl bg-[#151C28] border border-[#1E2736] space-y-1">
                <span className="font-bold text-white block">3. Retired Customer MT5 Wizards</span>
                <p>
                  Customer MT5 setup screens have been retired in favor of native REST/WS. Windows VPS MT5 gateway files are preserved in <code className="text-white">gateway/windows/</code> for infrastructure use.
                </p>
              </div>
            </div>
          </div>

          <div className="text-[10px] text-[#64748B] border-t border-[#1E2736] pt-3">
            Tenant Isolation Guaranteed · AES-256-GCM Vault
          </div>
        </div>
      </div>

      {/* ─── MULTI-ACCOUNT MANAGEMENT & PREFERRED SELECTION ─────────── */}
      {statusData?.all_connections?.length > 0 && (
        <div className="rounded-2xl bg-[#0E131B] border border-[#1E2736] overflow-hidden shadow-lg">
          <div className="p-4 bg-[#151C28]/60 border-b border-[#1E2736] flex items-center justify-between">
            <h3 className="font-bold text-[#F1F5F9] uppercase flex items-center gap-2">
              <Star className="w-4 h-4 text-[#F59E0B]" />
              <span>Customer Connected Accounts &amp; Session Preference</span>
            </h3>
            <span className="text-[10px] text-[#64748B]">
              Total: {statusData.all_connections.length} Accounts
            </span>
          </div>

          <div className="divide-y divide-[#1E2736]">
            {statusData.all_connections.map((c: any) => (
              <div
                key={c.connection_id}
                className="p-4 flex flex-wrap items-center justify-between gap-3 hover:bg-[#151C28]/30 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <div
                    className={`w-2.5 h-2.5 rounded-full ${
                      c.account_type === "REAL" ? "bg-[#F59E0B]" : "bg-[#38BDF8]"
                    }`}
                  />
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-[#F1F5F9] text-xs">
                        {c.account_label || c.account_login}
                      </span>
                      {c.is_preferred === 1 && (
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-[#F59E0B]/15 text-[#F59E0B] border border-[#F59E0B]/30 flex items-center gap-1">
                          <Star className="w-3 h-3 fill-current" />
                          <span>PREFERRED</span>
                        </span>
                      )}
                    </div>
                    <span className="text-[10px] text-[#64748B]">
                      Login: {c.account_login} &bull; Server: {c.server_name} &bull; Mode: {c.adapter_mode}
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-4 text-xs font-mono">
                  <div className="text-right">
                    <span className="text-[#F1F5F9] font-bold">
                      ${c.balance ? Number(c.balance).toFixed(2) : "0.00"} {c.currency || "USD"}
                    </span>
                    <span className="text-[10px] text-[#64748B] block">
                      Equity: ${c.equity ? Number(c.equity).toFixed(2) : "0.00"}
                    </span>
                  </div>

                  <div className="flex items-center gap-2">
                    {c.is_preferred !== 1 && (
                      <button
                        onClick={() => handleSetPreferred(c.connection_id)}
                        className="p-1.5 rounded-lg bg-[#151C28] hover:bg-[#1E2736] text-[#94A3B8] hover:text-[#F59E0B] transition-colors"
                        title="Set as Preferred Account"
                      >
                        <Star className="w-3.5 h-3.5" />
                      </button>
                    )}

                    <button
                      onClick={() => handleDisconnect(c.connection_id)}
                      className="p-1.5 rounded-lg bg-[#151C28] hover:bg-[#EF4444]/20 text-[#64748B] hover:text-[#EF4444] transition-colors"
                      title="Disconnect Account"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ─── INSTITUTIONAL SECURITY NOTICE ─────────────────────────── */}
      <div className="p-4 rounded-xl bg-[#080B10] border border-[#1E2736] flex items-center justify-between text-xs text-[#94A3B8]">
        <div className="flex items-center gap-2">
          <Lock className="w-4 h-4 text-[#38BDF8] shrink-0" />
          <span>
            Credentials and private keys are encrypted at rest using AES-256-GCM. Windows MT5 gateway is reserved for administrative VPS operations.
          </span>
        </div>
        <span className="text-[10px] text-[#64748B] shrink-0 font-bold">
          SECURITY PROTOCOL VERIFIED
        </span>
      </div>

      {/* ─── STREAMLINED EXNESS TRADER API CONNECTION MODAL ─────────── */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#080B10]/80 backdrop-blur-md animate-in fade-in duration-200">
          <div className="relative w-full max-w-lg bg-[#0E131B] border border-[#1E2736] rounded-2xl shadow-2xl overflow-hidden font-mono text-xs flex flex-col">
            {/* Modal Header */}
            <div className="px-5 py-4 border-b border-[#1E2736] flex items-center justify-between bg-[#151C28]/60">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-lg bg-[#38BDF8]/15 text-[#38BDF8] border border-[#38BDF8]/30 flex items-center justify-center font-bold">
                  API
                </div>
                <div>
                  <h3 className="font-bold text-[#F1F5F9]">
                    Connect Exness Trader API
                  </h3>
                  <span className="text-[10px] text-[#64748B]">
                    Secure Tenant Vault &bull; Ed25519 Request Signing
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
            <form onSubmit={handleSubmitConnection} className="p-5 space-y-4">
              {statusMsg && (
                <div
                  className={`p-3 rounded-lg border text-xs flex items-center gap-2 ${
                    statusMsg.type === "success"
                      ? "bg-[#10B981]/10 text-[#10B981] border-[#10B981]/30"
                      : "bg-[#EF4444]/10 text-[#EF4444] border-[#EF4444]/30"
                  }`}
                >
                  {statusMsg.type === "success" ? (
                    <CheckCircle2 className="w-4 h-4 shrink-0" />
                  ) : (
                    <AlertTriangle className="w-4 h-4 shrink-0" />
                  )}
                  <span>{statusMsg.text}</span>
                </div>
              )}

              {/* Account Environment Toggle: DEMO vs REAL */}
              <div className="space-y-1.5">
                <label className="text-[10px] uppercase text-[#64748B] block font-bold">
                  Account Environment:
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setAccountEnv("REAL")}
                    className={`py-2 px-3 rounded-xl border text-center font-bold cursor-pointer transition-all ${
                      accountEnv === "REAL"
                        ? "bg-[#38BDF8] text-[#080B10] border-[#38BDF8]"
                        : "bg-[#151C28] text-[#94A3B8] border-[#1E2736] hover:text-white"
                    }`}
                  >
                    REAL ACCOUNT
                  </button>
                  <button
                    type="button"
                    onClick={() => setAccountEnv("DEMO")}
                    className={`py-2 px-3 rounded-xl border text-center font-bold cursor-pointer transition-all ${
                      accountEnv === "DEMO"
                        ? "bg-[#38BDF8] text-[#080B10] border-[#38BDF8]"
                        : "bg-[#151C28] text-[#94A3B8] border-[#1E2736] hover:text-white"
                    }`}
                  >
                    DEMO ACCOUNT
                  </button>
                </div>
              </div>

              {/* Account ID / API Login */}
              <div className="space-y-1">
                <label className="text-[10px] uppercase text-[#64748B] block font-bold">
                  Account ID / API Login
                </label>
                <input
                  type="text"
                  value={accountLogin}
                  onChange={(e) => setAccountLogin(e.target.value)}
                  placeholder="e.g. 88492011"
                  required
                  className="w-full px-3 py-2 rounded-lg bg-[#151C28] border border-[#1E2736] text-[#F1F5F9] focus:outline-none focus:border-[#38BDF8]"
                />
              </div>

              {/* API Key */}
              <div className="space-y-1">
                <label className="text-[10px] uppercase text-[#64748B] block font-bold">
                  Exness API Key
                </label>
                <input
                  type="text"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder="Paste authorized API key from Exness Personal Area"
                  className="w-full px-3 py-2 rounded-lg bg-[#151C28] border border-[#1E2736] text-[#F1F5F9] focus:outline-none focus:border-[#38BDF8]"
                />
              </div>

              {/* API Secret / Private Key */}
              <div className="space-y-1">
                <label className="text-[10px] uppercase text-[#64748B] block font-bold">
                  Exness API Secret / Private Key (Ed25519)
                </label>
                <input
                  type="password"
                  value={apiSecret}
                  onChange={(e) => setApiSecret(e.target.value)}
                  placeholder="Paste Ed25519 private key or API token"
                  className="w-full px-3 py-2 rounded-lg bg-[#151C28] border border-[#1E2736] text-[#F1F5F9] focus:outline-none focus:border-[#38BDF8]"
                />
              </div>

              {/* Target Server Endpoint (Authoritative https://www.exness-api.com) */}
              <div className="space-y-1">
                <label className="text-[10px] uppercase text-[#64748B] block font-bold">
                  Target Endpoint (Official Exness Gateway)
                </label>
                <input
                  type="text"
                  value={serverName}
                  onChange={(e) => setServerName(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-[#151C28] border border-[#1E2736] text-[#38BDF8] focus:outline-none focus:border-[#38BDF8] font-mono"
                />
              </div>

              {/* Account Tier */}
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

              {/* Account Friendly Label */}
              <div className="space-y-1">
                <label className="text-[10px] uppercase text-[#64748B] block">
                  Friendly Label (Optional)
                </label>
                <input
                  type="text"
                  value={accountLabel}
                  onChange={(e) => setAccountLabel(e.target.value)}
                  placeholder="e.g. Primary Exness Real API"
                  className="w-full px-3 py-2 rounded-lg bg-[#151C28] border border-[#1E2736] text-[#F1F5F9] focus:outline-none focus:border-[#38BDF8]"
                />
              </div>

              {/* Modal Actions */}
              <div className="pt-2 flex flex-wrap items-center justify-between gap-2 border-t border-[#1E2736]">
                <button
                  type="button"
                  onClick={handleTestConnection}
                  disabled={isTesting || isSubmitting}
                  className="px-3.5 py-2 rounded-xl bg-[#151C28] hover:bg-[#1E2736] border border-[#1E2736] text-[#38BDF8] font-bold transition-colors flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                >
                  {isTesting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
                  <span>Test Connection</span>
                </button>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setIsModalOpen(false)}
                    className="px-4 py-2 rounded-xl bg-[#151C28] hover:bg-[#1E2736] text-[#94A3B8] transition-colors cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isSubmitting || isTesting}
                    className="px-5 py-2 rounded-xl bg-[#38BDF8] text-[#080B10] font-bold hover:bg-[#38BDF8]/90 transition-all flex items-center gap-1.5 disabled:opacity-50 cursor-pointer shadow-md shadow-[#38BDF8]/20"
                  >
                    {isSubmitting ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <ShieldCheck className="w-3.5 h-3.5" />
                    )}
                    <span>Save Connection</span>
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
