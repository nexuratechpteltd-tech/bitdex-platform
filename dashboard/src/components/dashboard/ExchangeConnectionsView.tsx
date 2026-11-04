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
  Plus,
  Cpu,
  CheckCircle2,
  X,
  Loader2,
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
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [modalEnv, setModalEnv] = useState<"DEMO" | "REAL">("DEMO");
  const [connMethod, setConnMethod] = useState<"MT5_GATEWAY" | "TRADER_API">("MT5_GATEWAY");

  // Form states
  const [accountLogin, setAccountLogin] = useState("");
  const [password, setPassword] = useState("");
  const [serverName, setServerName] = useState("Exness-MT5Trial");
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [accountTier, setAccountTier] = useState("STANDARD");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [statusMsg, setStatusMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const handleSync = async () => {
    setIsSyncing(true);
    if (onRefresh) await onRefresh();
    setTimeout(() => setIsSyncing(false), 800);
  };

  const handleOpenConnect = (env: "DEMO" | "REAL") => {
    setModalEnv(env);
    setServerName(env === "REAL" ? "Exness-Real" : "Exness-MT5Trial");
    setStatusMsg(null);
    setIsModalOpen(true);
  };

  const handleSubmitConnection = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setStatusMsg(null);

    try {
      const endpoint = modalEnv === "REAL" ? "/api/v1/hft/exness/real/connect" : "/api/v1/hft/exness/demo/connect";
      const payload: any = {
        connection_method: connMethod,
        server_name: serverName,
      };

      if (modalEnv === "REAL") {
        if (connMethod === "TRADER_API") {
          payload.account_login = accountLogin;
          payload.api_key = apiKey;
          payload.api_secret = apiSecret;
          payload.account_tier = accountTier;
        } else {
          payload.account_login = accountLogin;
          payload.password = password;
        }
      } else {
        payload.account_login = accountLogin || "149827361";
        payload.password = password || "DemoPassword123!";
        payload.use_mock = connMethod === "TRADER_API" ? false : true;
      }

      const res = await fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(payload),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Connection failed.");
      }

      setStatusMsg({
        type: "success",
        text: `Successfully registered Exness ${modalEnv} connection (${connMethod}).`,
      });
      setTimeout(() => {
        setIsModalOpen(false);
        if (onRefresh) onRefresh();
      }, 1200);
    } catch (err: any) {
      setStatusMsg({ type: "error", text: err.message || "Failed to establish broker connection." });
    } finally {
      setIsSubmitting(false);
    }
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
            Dual Exness Architecture: Demo Strategy Validation &amp; Real Capital Execution.
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

      {/* ─── VENUE 1: EXNESS DEMO ACCOUNT CARD ─────────────────────── */}
      <div className="rounded-2xl bg-[#0E131B] border border-[#1E2736] overflow-hidden shadow-xl">
        <div className="p-4 sm:p-5 bg-[#151C28]/60 border-b border-[#1E2736] flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-[#38BDF8]/15 border border-[#38BDF8]/30 flex items-center justify-center font-mono font-black text-lg text-[#38BDF8]">
              EX
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-mono font-bold text-[#F1F5F9]">
                  EXNESS DEMO ACCOUNT
                </h2>
                <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-[#38BDF8]/15 text-[#38BDF8] border border-[#38BDF8]/30 font-bold">
                  SIMULATION &amp; VALIDATION
                </span>
              </div>
              <p className="text-xs font-mono text-[#94A3B8] mt-0.5">
                Simulated MetaTrader 5 &amp; Trader API Gateway
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono font-bold bg-[#EF4444]/15 text-[#EF4444] border border-[#EF4444]/30">
              <span className="w-2 h-2 rounded-full bg-[#EF4444]" />
              <span>EXNESS GATEWAY NOT CONNECTED</span>
            </span>
            <button
              onClick={() => handleOpenConnect("DEMO")}
              className="px-3 py-1 rounded-lg bg-[#38BDF8]/15 hover:bg-[#38BDF8] text-[#38BDF8] hover:text-[#080B10] font-mono font-bold text-xs border border-[#38BDF8]/30 transition-all flex items-center gap-1.5 cursor-pointer"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Connect Demo</span>
            </button>
          </div>
        </div>

        <div className="p-4 sm:p-6 space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs font-mono">
            <div className="p-3.5 rounded-xl bg-[#151C28] border border-[#1E2736] space-y-1">
              <span className="text-[10px] text-[#64748B] block uppercase">Account Identifier</span>
              <span className="font-bold text-[#94A3B8] text-sm tabular-nums">UNAVAILABLE</span>
              <span className="text-[10px] text-[#64748B] block">Awaiting Demo Authentication</span>
            </div>

            <div className="p-3.5 rounded-xl bg-[#151C28] border border-[#1E2736] space-y-1">
              <span className="text-[10px] text-[#64748B] block uppercase">Server Target</span>
              <span className="font-bold text-[#94A3B8] text-sm tabular-nums">Exness-MT5Trial</span>
              <span className="text-[10px] text-[#64748B] block">Trial / Simulation Server</span>
            </div>

            <div className="p-3.5 rounded-xl bg-[#151C28] border border-[#1E2736] space-y-1">
              <span className="text-[10px] text-[#64748B] block uppercase">Simulated Equity</span>
              <span className="font-bold text-[#38BDF8] text-sm tabular-nums">$5,000.00</span>
              <span className="text-[10px] text-[#64748B] block">Virtual Balance Allocation</span>
            </div>

            <div className="p-3.5 rounded-xl bg-[#151C28] border border-[#1E2736] space-y-1">
              <span className="text-[10px] text-[#64748B] block uppercase">Max Leverage</span>
              <span className="font-bold text-[#F1F5F9] text-sm tabular-nums">1:2000</span>
              <span className="text-[10px] text-[#64748B] block">Unlimited / High Margin</span>
            </div>
          </div>
        </div>
      </div>

      {/* ─── VENUE 2: EXNESS REAL ACCOUNT CARD ─────────────────────── */}
      <div className="rounded-2xl bg-[#0E131B] border border-[#1E2736] overflow-hidden shadow-xl">
        <div className="p-4 sm:p-5 bg-[#151C28]/60 border-b border-[#1E2736] flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-[#F59E0B]/15 border border-[#F59E0B]/30 flex items-center justify-center font-mono font-black text-lg text-[#F59E0B]">
              EX
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-mono font-bold text-[#F1F5F9]">
                  EXNESS REAL ACCOUNT
                </h2>
                <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-[#F43F5E]/15 text-[#F43F5E] border border-[#F43F5E]/30 font-bold">
                  LIVE CAPITAL EXECUTION
                </span>
              </div>
              <p className="text-xs font-mono text-[#94A3B8] mt-0.5">
                Exness Real Terminal (Windows MT5 Gateway &amp; Official Trader REST API)
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono font-bold bg-[#EF4444]/15 text-[#EF4444] border border-[#EF4444]/30">
              <span className="w-2 h-2 rounded-full bg-[#EF4444]" />
              <span>REAL GATEWAY NOT CONNECTED</span>
            </span>
            <button
              onClick={() => handleOpenConnect("REAL")}
              className="px-3 py-1 rounded-lg bg-[#F59E0B]/15 hover:bg-[#F59E0B] text-[#F59E0B] hover:text-[#080B10] font-mono font-bold text-xs border border-[#F59E0B]/30 transition-all flex items-center gap-1.5 cursor-pointer"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Connect Real</span>
            </button>
          </div>
        </div>

        <div className="p-4 sm:p-6 space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs font-mono">
            <div className="p-3.5 rounded-xl bg-[#151C28] border border-[#1E2736] space-y-1">
              <span className="text-[10px] text-[#64748B] block uppercase">Live Account ID</span>
              <span className="font-bold text-[#94A3B8] text-sm tabular-nums">UNAVAILABLE</span>
              <span className="text-[10px] text-[#64748B] block">No Active Real Session</span>
            </div>

            <div className="p-3.5 rounded-xl bg-[#151C28] border border-[#1E2736] space-y-1">
              <span className="text-[10px] text-[#64748B] block uppercase">Live Server</span>
              <span className="font-bold text-[#94A3B8] text-sm tabular-nums">Exness-Real</span>
              <span className="text-[10px] text-[#64748B] block">Production Execution Node</span>
            </div>

            <div className="p-3.5 rounded-xl bg-[#151C28] border border-[#1E2736] space-y-1">
              <span className="text-[10px] text-[#64748B] block uppercase">Real Balance / Equity</span>
              <span className="font-bold text-[#94A3B8] text-sm tabular-nums">UNAVAILABLE</span>
              <span className="text-[10px] text-[#64748B] block">Awaiting Live Handshake</span>
            </div>

            <div className="p-3.5 rounded-xl bg-[#151C28] border border-[#1E2736] space-y-1">
              <span className="text-[10px] text-[#64748B] block uppercase">Leverage &amp; Safety</span>
              <span className="font-bold text-[#F59E0B] text-sm tabular-nums">1:200 Clamped</span>
              <span className="text-[10px] text-[#F59E0B] block">Institutional Cap Applied</span>
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

      {/* ─── CONNECTION MODAL ───────────────────────────────────────── */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#080B10]/80 backdrop-blur-md animate-in fade-in duration-150">
          <div className="w-full max-w-lg bg-[#0E131B] border border-[#1E2736] rounded-2xl shadow-2xl p-5 font-mono text-xs space-y-4">
            <div className="flex items-center justify-between border-b border-[#1E2736] pb-3">
              <div className="flex items-center gap-2">
                <Cpu className="w-4 h-4 text-[#38BDF8]" />
                <span className="font-bold text-sm text-[#F1F5F9]">
                  Connect Exness {modalEnv} Account
                </span>
              </div>
              <button
                onClick={() => setIsModalOpen(false)}
                className="text-[#64748B] hover:text-[#F1F5F9]"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Protocol Selector */}
            <div>
              <label className="text-[10px] text-[#64748B] uppercase block mb-1.5 font-bold">
                Connection Protocol
              </label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setConnMethod("MT5_GATEWAY")}
                  className={`py-2 px-3 rounded-lg border text-left transition-all ${
                    connMethod === "MT5_GATEWAY"
                      ? "bg-[#151C28] border-[#38BDF8] text-[#F1F5F9]"
                      : "bg-[#080B10] border-[#1E2736] text-[#64748B]"
                  }`}
                >
                  <div className="font-bold">Windows MT5 Gateway</div>
                  <div className="text-[10px] text-[#38BDF8]">Login &amp; Password</div>
                </button>
                <button
                  type="button"
                  onClick={() => setConnMethod("TRADER_API")}
                  className={`py-2 px-3 rounded-lg border text-left transition-all ${
                    connMethod === "TRADER_API"
                      ? "bg-[#151C28] border-[#38BDF8] text-[#F1F5F9]"
                      : "bg-[#080B10] border-[#1E2736] text-[#64748B]"
                  }`}
                >
                  <div className="font-bold">Exness Trader API</div>
                  <div className="text-[10px] text-[#38BDF8]">API Key &amp; Secret</div>
                </button>
              </div>
            </div>

            {/* Form */}
            <form onSubmit={handleSubmitConnection} className="space-y-3">
              {connMethod === "MT5_GATEWAY" ? (
                <>
                  <div>
                    <label className="text-[10px] text-[#64748B] uppercase block mb-1">
                      MT5 Account Login ID
                    </label>
                    <input
                      type="text"
                      required
                      placeholder="e.g. 149827361"
                      value={accountLogin}
                      onChange={(e) => setAccountLogin(e.target.value)}
                      className="w-full px-3 py-2 bg-[#080B10] border border-[#1E2736] rounded-lg text-[#F1F5F9] focus:outline-none focus:border-[#38BDF8]"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-[#64748B] uppercase block mb-1">
                      MT5 Trading Password
                    </label>
                    <input
                      type="password"
                      required
                      placeholder="••••••••••••"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className="w-full px-3 py-2 bg-[#080B10] border border-[#1E2736] rounded-lg text-[#F1F5F9] focus:outline-none focus:border-[#38BDF8]"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-[#64748B] uppercase block mb-1">
                      Server Name
                    </label>
                    <input
                      type="text"
                      required
                      value={serverName}
                      onChange={(e) => setServerName(e.target.value)}
                      className="w-full px-3 py-2 bg-[#080B10] border border-[#1E2736] rounded-lg text-[#F1F5F9] focus:outline-none focus:border-[#38BDF8]"
                    />
                  </div>
                </>
              ) : (
                <>
                  <div>
                    <label className="text-[10px] text-[#64748B] uppercase block mb-1">
                      Account Login / Identifier
                    </label>
                    <input
                      type="text"
                      required
                      placeholder="Account ID"
                      value={accountLogin}
                      onChange={(e) => setAccountLogin(e.target.value)}
                      className="w-full px-3 py-2 bg-[#080B10] border border-[#1E2736] rounded-lg text-[#F1F5F9] focus:outline-none focus:border-[#38BDF8]"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-[#64748B] uppercase block mb-1">
                      Exness Trader API Key
                    </label>
                    <input
                      type="text"
                      required
                      placeholder="API Key from Personal Area"
                      value={apiKey}
                      onChange={(e) => setApiKey(e.target.value)}
                      className="w-full px-3 py-2 bg-[#080B10] border border-[#1E2736] rounded-lg text-[#F1F5F9] focus:outline-none focus:border-[#38BDF8]"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-[#64748B] uppercase block mb-1">
                      Exness Trader API Secret
                    </label>
                    <input
                      type="password"
                      required
                      placeholder="••••••••••••"
                      value={apiSecret}
                      onChange={(e) => setApiSecret(e.target.value)}
                      className="w-full px-3 py-2 bg-[#080B10] border border-[#1E2736] rounded-lg text-[#F1F5F9] focus:outline-none focus:border-[#38BDF8]"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-[#64748B] uppercase block mb-1">
                      Account Tier
                    </label>
                    <select
                      value={accountTier}
                      onChange={(e) => setAccountTier(e.target.value)}
                      className="w-full px-3 py-2 bg-[#080B10] border border-[#1E2736] rounded-lg text-[#F1F5F9] focus:outline-none focus:border-[#38BDF8]"
                    >
                      <option value="STANDARD">Standard</option>
                      <option value="PRO">Pro</option>
                      <option value="RAW_SPREAD">Raw Spread</option>
                      <option value="ZERO">Zero</option>
                    </select>
                  </div>
                </>
              )}

              {statusMsg && (
                <div
                  className={`p-3 rounded-lg text-xs flex items-center gap-2 ${
                    statusMsg.type === "success"
                      ? "bg-[#10B981]/15 text-[#10B981] border border-[#10B981]/30"
                      : "bg-[#F43F5E]/15 text-[#F43F5E] border border-[#F43F5E]/30"
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

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-[#1E2736]">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 rounded-lg bg-[#151C28] text-[#94A3B8] font-bold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-4 py-2 rounded-lg bg-[#38BDF8] text-[#080B10] font-bold flex items-center gap-1.5 cursor-pointer"
                >
                  {isSubmitting ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      <span>Encrypting &amp; Validating...</span>
                    </>
                  ) : (
                    <span>Authenticate &amp; Save</span>
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
