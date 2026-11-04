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
  const [activeStepTab, setActiveStepTab] = useState<"STEP_A" | "STEP_B" | "STEP_C">("STEP_A");
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [modalMethod, setModalMethod] = useState<"TRADER_API" | "MT5_DEMO" | "MT5_REAL">("TRADER_API");

  // Form states
  const [accountLogin, setAccountLogin] = useState("");
  const [password, setPassword] = useState("");
  const [serverName, setServerName] = useState("Exness-MT5Trial");
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [accountTier, setAccountTier] = useState("STANDARD");
  const [accountLabel, setAccountLabel] = useState("");
  const [useMockDemo, setUseMockDemo] = useState(true);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [statusMsg, setStatusMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const fetchStatus = async () => {
    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      const authToken = token || (typeof window !== "undefined" ? localStorage.getItem("tauric_token") || localStorage.getItem("bitdex_token") : null);
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

  const handleOpenConnect = (method: "TRADER_API" | "MT5_DEMO" | "MT5_REAL") => {
    setModalMethod(method);
    setStatusMsg(null);
    setAccountLogin("");
    setPassword("");
    setApiKey("");
    setApiSecret("");
    setAccountLabel("");

    if (method === "TRADER_API") {
      setServerName("api.exness.com");
      setAccountLabel("Exness Trader API Account");
    } else if (method === "MT5_DEMO") {
      setServerName("Exness-MT5Trial");
      setAccountLabel("Exness Demo MT5");
      setUseMockDemo(true);
    } else {
      setServerName("Exness-Real");
      setAccountLabel("Exness Real MT5");
    }

    setIsModalOpen(true);
  };

  const handleSubmitConnection = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setStatusMsg(null);

    const authToken = token || (typeof window !== "undefined" ? localStorage.getItem("tauric_token") || localStorage.getItem("bitdex_token") : null);
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
    };

    try {
      if (!accountLogin.trim()) {
        throw new Error("Account Login ID / Identifier is required.");
      }

      if (modalMethod === "TRADER_API") {
        const res = await fetch("/api/v1/hft/exness/real/connect", {
          method: "POST",
          headers,
          body: JSON.stringify({
            connection_method: "TRADER_API",
            account_login: accountLogin.trim(),
            api_key: apiKey.trim() || accountLogin.trim(),
            api_secret: apiSecret.trim(),
            server_name: "api.exness.com",
            account_tier: accountTier,
            account_label: accountLabel.trim() || "Exness Trader API",
          }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Trader API connection failed.");
      } else if (modalMethod === "MT5_DEMO") {
        if (!password.trim()) throw new Error("Trading password is required.");
        const res = await fetch("/api/v1/hft/exness/demo/connect", {
          method: "POST",
          headers,
          body: JSON.stringify({
            account_login: accountLogin.trim(),
            password: password.trim(),
            server_name: serverName.trim(),
            use_mock: useMockDemo,
            account_label: accountLabel.trim() || "Exness Demo MT5",
          }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail?.reason || data.detail || "Demo MT5 connection failed.");
      } else {
        // MT5 REAL
        if (!password.trim()) throw new Error("Trading password is required for MT5 Real Gateway.");
        const res = await fetch("/api/v1/hft/exness/real/connect", {
          method: "POST",
          headers,
          body: JSON.stringify({
            connection_method: "MT5_GATEWAY",
            account_login: accountLogin.trim(),
            password: password.trim(),
            server_name: serverName.trim(),
            account_label: accountLabel.trim() || "Exness Real MT5",
          }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail?.reason || data.detail || "Real MT5 connection failed.");
      }

      setStatusMsg({
        type: "success",
        text: `Account successfully registered and secured in institutional vault.`,
      });

      await fetchStatus();
      if (onRefresh) onRefresh();

      setTimeout(() => {
        setIsModalOpen(false);
      }, 1000);
    } catch (err: any) {
      setStatusMsg({ type: "error", text: err.message || "Failed to establish broker connection." });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDisconnect = async (connectionId: string) => {
    if (!confirm("Are you sure you want to disconnect this Exness account? Stored credentials will be invalidated.")) {
      return;
    }
    try {
      const authToken = token || (typeof window !== "undefined" ? localStorage.getItem("tauric_token") || localStorage.getItem("bitdex_token") : null);
      const res = await fetch("/api/v1/hft/exness/disconnect", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
        },
        body: JSON.stringify({ connection_id: connectionId }),
      });
      if (res.ok) {
        await fetchStatus();
        if (onRefresh) onRefresh();
      } else {
        const d = await res.json();
        alert(d.detail || "Failed to disconnect account.");
      }
    } catch (err) {
      console.error("Disconnect error:", err);
    }
  };

  const handleSetPreferred = async (connectionId: string) => {
    try {
      const authToken = token || (typeof window !== "undefined" ? localStorage.getItem("tauric_token") || localStorage.getItem("bitdex_token") : null);
      const res = await fetch("/api/v1/hft/exness/account/preferred", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
        },
        body: JSON.stringify({ connection_id: connectionId }),
      });
      if (res.ok) {
        await fetchStatus();
      }
    } catch (err) {
      console.error("Set preferred error:", err);
    }
  };

  // Card Status Helpers
  const traderConn = statusData?.active_trader_connection;
  const demoConn = statusData?.active_demo_connection;
  const realConn = statusData?.active_real_connection;

  const isTraderConnected = Boolean(traderConn && statusData?.trader_status?.is_connected);
  const isDemoConnected = Boolean(demoConn && (demoConn.adapter_mode === "DETERMINISTIC_MOCK_DEMO" || statusData?.demo_status?.is_connected));
  const isRealConnected = Boolean(realConn && statusData?.real_status?.is_connected);

  return (
    <div className="space-y-6 font-mono animate-in fade-in duration-200 text-xs">
      {/* ─── HEADER & TENANT ISOLATION DISCLOSURE ─────────────────── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-5 rounded-2xl bg-[#0E131B] border border-[#1E2736]">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-bold text-[#F1F5F9] uppercase tracking-wider">
              Exchange &amp; Broker Connections
            </h1>
            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-[#38BDF8]/10 text-[#38BDF8] border border-[#38BDF8]/30">
              PHASE 4.1
            </span>
          </div>
          <p className="text-xs text-[#94A3B8] mt-1">
            Connect and manage your independent Exness accounts. Admin credentials are strictly isolated.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <a
            href="https://my.exness.com/pa"
            target="_blank"
            rel="noopener noreferrer"
            className="px-3 py-1.5 rounded-lg bg-[#151C28] hover:bg-[#1E2736] text-[#94A3B8] hover:text-[#F1F5F9] border border-[#1E2736] transition-colors flex items-center gap-1.5"
          >
            <ExternalLink className="w-3.5 h-3.5" />
            <span>Exness Personal Area</span>
          </a>
          <button
            onClick={handleSync}
            disabled={isSyncing}
            className="px-3 py-1.5 rounded-lg bg-[#38BDF8]/15 hover:bg-[#38BDF8] text-[#38BDF8] hover:text-[#080B10] border border-[#38BDF8]/30 font-bold transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isSyncing ? "animate-spin" : ""}`} />
            <span>Sync Gateways</span>
          </button>
        </div>
      </div>

      {/* ─── ONBOARDING WORKFLOW (STEPS A, B, C) ────────────────────── */}
      <div className="rounded-2xl bg-[#0E131B] border border-[#1E2736] overflow-hidden">
        <div className="p-4 bg-[#151C28]/60 border-b border-[#1E2736] flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Cpu className="w-4 h-4 text-[#38BDF8]" />
            <span className="font-bold text-[#F1F5F9] uppercase">
              Customer Onboarding Workflow
            </span>
            <span className="text-[10px] text-[#64748B]">
              (3 Supported Integration Methods)
            </span>
          </div>

          <div className="flex items-center gap-1 bg-[#080B10] p-1 rounded-lg border border-[#1E2736]">
            <button
              onClick={() => setActiveStepTab("STEP_A")}
              className={`px-3 py-1 rounded text-[11px] font-bold transition-colors ${
                activeStepTab === "STEP_A"
                  ? "bg-[#38BDF8] text-[#080B10]"
                  : "text-[#94A3B8] hover:text-[#F1F5F9]"
              }`}
            >
              Step A: Trader API
            </button>
            <button
              onClick={() => setActiveStepTab("STEP_B")}
              className={`px-3 py-1 rounded text-[11px] font-bold transition-colors ${
                activeStepTab === "STEP_B"
                  ? "bg-[#38BDF8] text-[#080B10]"
                  : "text-[#94A3B8] hover:text-[#F1F5F9]"
              }`}
            >
              Step B: MT5 Demo
            </button>
            <button
              onClick={() => setActiveStepTab("STEP_C")}
              className={`px-3 py-1 rounded text-[11px] font-bold transition-colors ${
                activeStepTab === "STEP_C"
                  ? "bg-[#38BDF8] text-[#080B10]"
                  : "text-[#94A3B8] hover:text-[#F1F5F9]"
              }`}
            >
              Step C: MT5 Real
            </button>
          </div>
        </div>

        <div className="p-5">
          {activeStepTab === "STEP_A" && (
            <div className="space-y-4">
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-1">
                  <h3 className="text-sm font-bold text-[#F1F5F9] flex items-center gap-2">
                    <span className="text-[#38BDF8]">STEP A</span> — Connect Exness Trader REST &amp; WebSocket API
                  </h3>
                  <p className="text-xs text-[#94A3B8] leading-relaxed max-w-3xl">
                    Official programmatic interface for Standard, Pro, Raw Spread, and Zero account tiers. Exness enforces strict server-side authentication using authorized API credentials generated in your Exness Personal Area. Retail accounts do not use a public OAuth flow; credentials are encrypted in your private tenant vault using AES-256-GCM.
                  </p>
                </div>
                <button
                  onClick={() => handleOpenConnect("TRADER_API")}
                  className="px-4 py-2 rounded-xl bg-[#38BDF8] text-[#080B10] font-bold hover:bg-[#38BDF8]/90 transition-all shrink-0 flex items-center gap-2"
                >
                  <Plus className="w-4 h-4" />
                  <span>Connect Trader API</span>
                </button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-2 text-[11px]">
                <div className="p-3 rounded-xl bg-[#151C28] border border-[#1E2736]">
                  <span className="text-[#64748B] block uppercase text-[10px]">1. Obtain Credentials</span>
                  <p className="text-[#F1F5F9] mt-1">
                    Log in to Exness Personal Area &rarr; Settings &rarr; API Access to generate authorized API Key.
                  </p>
                </div>
                <div className="p-3 rounded-xl bg-[#151C28] border border-[#1E2736]">
                  <span className="text-[#64748B] block uppercase text-[10px]">2. Supported Tiers</span>
                  <p className="text-[#F1F5F9] mt-1">
                    Standard, Pro, Raw Spread, and Zero trading accounts are natively supported.
                  </p>
                </div>
                <div className="p-3 rounded-xl bg-[#151C28] border border-[#1E2736]">
                  <span className="text-[#64748B] block uppercase text-[10px]">3. AES-256 Vault</span>
                  <p className="text-[#F1F5F9] mt-1">
                    Secrets are encrypted at rest and never exposed to browser storage, URLs, or client logs.
                  </p>
                </div>
              </div>
            </div>
          )}

          {activeStepTab === "STEP_B" && (
            <div className="space-y-4">
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-1">
                  <h3 className="text-sm font-bold text-[#F1F5F9] flex items-center gap-2">
                    <span className="text-[#38BDF8]">STEP B</span> — Connect MetaTrader 5 Demo Account
                  </h3>
                  <p className="text-xs text-[#94A3B8] leading-relaxed max-w-3xl">
                    Connect your own Exness MT5 Demo account using your MT5 login ID, trading password, and trial server (e.g., <code className="text-[#38BDF8]">Exness-MT5Trial</code>). Validates account identity and paper trading conditions via the Windows MT5 Gateway bridge or simulated execution engine.
                  </p>
                </div>
                <button
                  onClick={() => handleOpenConnect("MT5_DEMO")}
                  className="px-4 py-2 rounded-xl bg-[#38BDF8] text-[#080B10] font-bold hover:bg-[#38BDF8]/90 transition-all shrink-0 flex items-center gap-2"
                >
                  <Plus className="w-4 h-4" />
                  <span>Connect MT5 Demo</span>
                </button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-2 text-[11px]">
                <div className="p-3 rounded-xl bg-[#151C28] border border-[#1E2736]">
                  <span className="text-[#64748B] block uppercase text-[10px]">1. MT5 Login &amp; Server</span>
                  <p className="text-[#F1F5F9] mt-1">
                    Copy your MT5 Account Number and Trial Server name from Exness Personal Area &rarr; My Accounts.
                  </p>
                </div>
                <div className="p-3 rounded-xl bg-[#151C28] border border-[#1E2736]">
                  <span className="text-[#64748B] block uppercase text-[10px]">2. Trading Password</span>
                  <p className="text-[#F1F5F9] mt-1">
                    Enter the trading password configured when creating your Exness MT5 Demo account.
                  </p>
                </div>
                <div className="p-3 rounded-xl bg-[#151C28] border border-[#1E2736]">
                  <span className="text-[#64748B] block uppercase text-[10px]">3. Paper Trading</span>
                  <p className="text-[#F1F5F9] mt-1">
                    Enables quantitative strategy validation with zero real capital risk.
                  </p>
                </div>
              </div>
            </div>
          )}

          {activeStepTab === "STEP_C" && (
            <div className="space-y-4">
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-1">
                  <h3 className="text-sm font-bold text-[#F1F5F9] flex items-center gap-2">
                    <span className="text-[#F59E0B]">STEP C</span> — Connect MetaTrader 5 Real Account
                  </h3>
                  <p className="text-xs text-[#94A3B8] leading-relaxed max-w-3xl">
                    Connect your own live Exness Real MT5 account using your live account number, trading password, and exact production server (e.g., <code className="text-[#F59E0B]">Exness-Real</code> or <code className="text-[#F59E0B]">Exness-Real2</code>). Governed by per-trade customer consent and strict quantitative safety barriers.
                  </p>
                </div>
                <button
                  onClick={() => handleOpenConnect("MT5_REAL")}
                  className="px-4 py-2 rounded-xl bg-[#F59E0B] text-[#080B10] font-bold hover:bg-[#F59E0B]/90 transition-all shrink-0 flex items-center gap-2"
                >
                  <Plus className="w-4 h-4" />
                  <span>Connect MT5 Real</span>
                </button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-2 text-[11px]">
                <div className="p-3 rounded-xl bg-[#151C28] border border-[#1E2736]">
                  <span className="text-[#64748B] block uppercase text-[10px]">1. Production Server</span>
                  <p className="text-[#F1F5F9] mt-1">
                    Matches your specific assigned Exness live cluster (e.g. Exness-Real, Exness-Real2).
                  </p>
                </div>
                <div className="p-3 rounded-xl bg-[#151C28] border border-[#1E2736]">
                  <span className="text-[#64748B] block uppercase text-[10px]">2. Risk Clamp (1:200)</span>
                  <p className="text-[#F1F5F9] mt-1">
                    Institutional risk guard caps effective leverage to 1:200 max for real capital protection.
                  </p>
                </div>
                <div className="p-3 rounded-xl bg-[#151C28] border border-[#1E2736]">
                  <span className="text-[#64748B] block uppercase text-[10px]">3. Fail-Closed Lock</span>
                  <p className="text-[#F1F5F9] mt-1">
                    On staging, <code className="text-[#38BDF8]">live_trading_locked=True</code> prevents accidental live market execution.
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ─── STEP D: 3 SEPARATE CONNECTION STATUS CARDS ─────────────── */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Radio className="w-4 h-4 text-[#38BDF8]" />
            <h2 className="text-sm font-bold text-[#F1F5F9] uppercase tracking-wider">
              Step D: Discrete Connection Status Cards
            </h2>
          </div>
          <span className="text-[10px] text-[#64748B]">
            Authoritative Telemetry &bull; No Simulated Overrides
          </span>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* ─── CARD 1: EXNESS TRADER API ─────────────────────────────── */}
          <div className="rounded-2xl bg-[#0E131B] border border-[#1E2736] flex flex-col justify-between overflow-hidden shadow-lg">
            <div className="p-4 bg-[#151C28]/60 border-b border-[#1E2736] flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-[#38BDF8]/15 border border-[#38BDF8]/30 flex items-center justify-center font-bold text-[#38BDF8]">
                  API
                </div>
                <div>
                  <h3 className="font-bold text-[#F1F5F9]">Exness Trader API</h3>
                  <span className="text-[10px] text-[#64748B]">Official REST / WebSocket</span>
                </div>
              </div>

              {isTraderConnected ? (
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-[#10B981]/15 text-[#10B981] border border-[#10B981]/30 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#10B981]" />
                  <span>CONNECTED</span>
                </span>
              ) : (
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-[#EF4444]/15 text-[#EF4444] border border-[#EF4444]/30 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#EF4444]" />
                  <span>NOT CONNECTED</span>
                </span>
              )}
            </div>

            <div className="p-4 space-y-3 flex-1">
              <div className="space-y-1">
                <span className="text-[10px] text-[#64748B] uppercase block">Account Identifier</span>
                <span className="font-bold text-[#F1F5F9] tabular-nums">
                  {traderConn ? traderConn.account_login : "UNAVAILABLE"}
                </span>
              </div>

              <div className="grid grid-cols-2 gap-2 text-[11px]">
                <div className="p-2.5 rounded-lg bg-[#151C28] border border-[#1E2736]">
                  <span className="text-[10px] text-[#64748B] block uppercase">Target Endpoint</span>
                  <span className="font-semibold text-[#94A3B8]">api.exness.com</span>
                </div>
                <div className="p-2.5 rounded-lg bg-[#151C28] border border-[#1E2736]">
                  <span className="text-[10px] text-[#64748B] block uppercase">Account Type</span>
                  <span className="font-semibold text-[#38BDF8]">
                    {traderConn ? traderConn.account_type : "UNAVAILABLE"}
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 text-[11px]">
                <div className="p-2.5 rounded-lg bg-[#151C28] border border-[#1E2736]">
                  <span className="text-[10px] text-[#64748B] block uppercase">Balance / Equity</span>
                  <span className="font-semibold text-[#F1F5F9] tabular-nums">
                    {traderConn ? `$${traderConn.balance_usd.toFixed(2)}` : "UNAVAILABLE"}
                  </span>
                </div>
                <div className="p-2.5 rounded-lg bg-[#151C28] border border-[#1E2736]">
                  <span className="text-[10px] text-[#64748B] block uppercase">Data Source</span>
                  <span className="font-semibold text-[#94A3B8]">
                    {traderConn ? traderConn.data_source : "None"}
                  </span>
                </div>
              </div>

              <div className="text-[10px] text-[#64748B] pt-1">
                Last Sync: {traderConn?.last_reconciled_at || "Never"}
              </div>
            </div>

            <div className="p-3 bg-[#151C28]/40 border-t border-[#1E2736] flex items-center justify-between">
              {traderConn ? (
                <div className="flex items-center justify-between w-full">
                  <span className="text-[10px] text-[#10B981] flex items-center gap-1">
                    <CheckCircle2 className="w-3 h-3" />
                    <span>Vault Authenticated</span>
                  </span>
                  <button
                    onClick={() => handleDisconnect(traderConn.connection_id)}
                    className="px-2.5 py-1 rounded bg-[#EF4444]/15 hover:bg-[#EF4444] text-[#EF4444] hover:text-[#080B10] font-bold text-[10px] transition-all flex items-center gap-1"
                  >
                    <Trash2 className="w-3 h-3" />
                    <span>Disconnect</span>
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => handleOpenConnect("TRADER_API")}
                  className="w-full py-1.5 rounded-lg bg-[#38BDF8]/15 hover:bg-[#38BDF8] text-[#38BDF8] hover:text-[#080B10] font-bold transition-all text-center"
                >
                  Connect Trader API
                </button>
              )}
            </div>
          </div>

          {/* ─── CARD 2: EXNESS MT5 DEMO ───────────────────────────────── */}
          <div className="rounded-2xl bg-[#0E131B] border border-[#1E2736] flex flex-col justify-between overflow-hidden shadow-lg">
            <div className="p-4 bg-[#151C28]/60 border-b border-[#1E2736] flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-[#38BDF8]/15 border border-[#38BDF8]/30 flex items-center justify-center font-bold text-[#38BDF8]">
                  MT5
                </div>
                <div>
                  <h3 className="font-bold text-[#F1F5F9]">Exness MT5 Demo</h3>
                  <span className="text-[10px] text-[#64748B]">Trial / Paper Simulation</span>
                </div>
              </div>

              {isDemoConnected ? (
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-[#10B981]/15 text-[#10B981] border border-[#10B981]/30 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#10B981]" />
                  <span>CONNECTED</span>
                </span>
              ) : (
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-[#EF4444]/15 text-[#EF4444] border border-[#EF4444]/30 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#EF4444]" />
                  <span>NOT CONNECTED</span>
                </span>
              )}
            </div>

            <div className="p-4 space-y-3 flex-1">
              <div className="space-y-1">
                <span className="text-[10px] text-[#64748B] uppercase block">Account Identifier</span>
                <span className="font-bold text-[#F1F5F9] tabular-nums">
                  {demoConn ? demoConn.account_login : "UNAVAILABLE"}
                </span>
              </div>

              <div className="grid grid-cols-2 gap-2 text-[11px]">
                <div className="p-2.5 rounded-lg bg-[#151C28] border border-[#1E2736]">
                  <span className="text-[10px] text-[#64748B] block uppercase">Server Name</span>
                  <span className="font-semibold text-[#94A3B8]">
                    {demoConn ? demoConn.server_name : "Exness-MT5Trial"}
                  </span>
                </div>
                <div className="p-2.5 rounded-lg bg-[#151C28] border border-[#1E2736]">
                  <span className="text-[10px] text-[#64748B] block uppercase">Account Type</span>
                  <span className="font-semibold text-[#38BDF8]">DEMO (TRIAL)</span>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 text-[11px]">
                <div className="p-2.5 rounded-lg bg-[#151C28] border border-[#1E2736]">
                  <span className="text-[10px] text-[#64748B] block uppercase">Simulated Equity</span>
                  <span className="font-semibold text-[#38BDF8] tabular-nums">
                    {demoConn ? `$${demoConn.balance_usd.toFixed(2)} (MOCK)` : "UNAVAILABLE"}
                  </span>
                </div>
                <div className="p-2.5 rounded-lg bg-[#151C28] border border-[#1E2736]">
                  <span className="text-[10px] text-[#64748B] block uppercase">Data Source</span>
                  <span className="font-semibold text-[#94A3B8]">
                    {demoConn ? demoConn.data_source : "None"}
                  </span>
                </div>
              </div>

              <div className="text-[10px] text-[#64748B] pt-1">
                Last Sync: {demoConn?.last_reconciled_at || "Never"}
              </div>
            </div>

            <div className="p-3 bg-[#151C28]/40 border-t border-[#1E2736] flex items-center justify-between">
              {demoConn ? (
                <div className="flex items-center justify-between w-full">
                  <span className="text-[10px] text-[#10B981] flex items-center gap-1">
                    <CheckCircle2 className="w-3 h-3" />
                    <span>Customer Demo Active</span>
                  </span>
                  <button
                    onClick={() => handleDisconnect(demoConn.connection_id)}
                    className="px-2.5 py-1 rounded bg-[#EF4444]/15 hover:bg-[#EF4444] text-[#EF4444] hover:text-[#080B10] font-bold text-[10px] transition-all flex items-center gap-1"
                  >
                    <Trash2 className="w-3 h-3" />
                    <span>Disconnect</span>
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => handleOpenConnect("MT5_DEMO")}
                  className="w-full py-1.5 rounded-lg bg-[#38BDF8]/15 hover:bg-[#38BDF8] text-[#38BDF8] hover:text-[#080B10] font-bold transition-all text-center"
                >
                  Connect MT5 Demo
                </button>
              )}
            </div>
          </div>

          {/* ─── CARD 3: EXNESS MT5 REAL ───────────────────────────────── */}
          <div className="rounded-2xl bg-[#0E131B] border border-[#1E2736] flex flex-col justify-between overflow-hidden shadow-lg">
            <div className="p-4 bg-[#151C28]/60 border-b border-[#1E2736] flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-[#F59E0B]/15 border border-[#F59E0B]/30 flex items-center justify-center font-bold text-[#F59E0B]">
                  LIVE
                </div>
                <div>
                  <h3 className="font-bold text-[#F1F5F9]">Exness MT5 Real</h3>
                  <span className="text-[10px] text-[#F59E0B]">Live Financial Capital</span>
                </div>
              </div>

              {isRealConnected ? (
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-[#10B981]/15 text-[#10B981] border border-[#10B981]/30 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#10B981]" />
                  <span>CONNECTED</span>
                </span>
              ) : (
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-[#EF4444]/15 text-[#EF4444] border border-[#EF4444]/30 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#EF4444]" />
                  <span>NOT CONNECTED</span>
                </span>
              )}
            </div>

            <div className="p-4 space-y-3 flex-1">
              <div className="space-y-1">
                <span className="text-[10px] text-[#64748B] uppercase block">Live Account Identifier</span>
                <span className="font-bold text-[#F1F5F9] tabular-nums">
                  {realConn ? realConn.account_login : "UNAVAILABLE"}
                </span>
              </div>

              <div className="grid grid-cols-2 gap-2 text-[11px]">
                <div className="p-2.5 rounded-lg bg-[#151C28] border border-[#1E2736]">
                  <span className="text-[10px] text-[#64748B] block uppercase">Live Server</span>
                  <span className="font-semibold text-[#94A3B8]">
                    {realConn ? realConn.server_name : "Exness-Real"}
                  </span>
                </div>
                <div className="p-2.5 rounded-lg bg-[#151C28] border border-[#1E2736]">
                  <span className="text-[10px] text-[#64748B] block uppercase">Max Leverage</span>
                  <span className="font-semibold text-[#F59E0B]">1:200 Clamped</span>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 text-[11px]">
                <div className="p-2.5 rounded-lg bg-[#151C28] border border-[#1E2736]">
                  <span className="text-[10px] text-[#64748B] block uppercase">Real Balance</span>
                  <span className="font-semibold text-[#F1F5F9] tabular-nums">
                    {realConn ? `$${realConn.balance_usd.toFixed(2)}` : "UNAVAILABLE"}
                  </span>
                </div>
                <div className="p-2.5 rounded-lg bg-[#151C28] border border-[#1E2736]">
                  <span className="text-[10px] text-[#64748B] block uppercase">Data Source</span>
                  <span className="font-semibold text-[#94A3B8]">
                    {realConn ? realConn.data_source : "None"}
                  </span>
                </div>
              </div>

              <div className="text-[10px] text-[#64748B] pt-1">
                Last Sync: {realConn?.last_reconciled_at || "Never"}
              </div>
            </div>

            <div className="p-3 bg-[#151C28]/40 border-t border-[#1E2736] flex items-center justify-between">
              {realConn ? (
                <div className="flex items-center justify-between w-full">
                  <span className="text-[10px] text-[#10B981] flex items-center gap-1">
                    <CheckCircle2 className="w-3 h-3" />
                    <span>Customer Real Active</span>
                  </span>
                  <button
                    onClick={() => handleDisconnect(realConn.connection_id)}
                    className="px-2.5 py-1 rounded bg-[#EF4444]/15 hover:bg-[#EF4444] text-[#EF4444] hover:text-[#080B10] font-bold text-[10px] transition-all flex items-center gap-1"
                  >
                    <Trash2 className="w-3 h-3" />
                    <span>Disconnect</span>
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => handleOpenConnect("MT5_REAL")}
                  className="w-full py-1.5 rounded-lg bg-[#F59E0B]/15 hover:bg-[#F59E0B] text-[#F59E0B] hover:text-[#080B10] font-bold transition-all text-center"
                >
                  Connect MT5 Real
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ─── MULTI-ACCOUNT MANAGEMENT & PREFERRED SELECTION ─────────── */}
      {statusData?.all_connections?.length > 0 && (
        <div className="rounded-2xl bg-[#0E131B] border border-[#1E2736] overflow-hidden">
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
                      <span className="font-bold text-[#F1F5F9]">
                        {c.account_label || c.account_login}
                      </span>
                      <span
                        className={`text-[9px] px-1.5 py-0.5 rounded uppercase font-bold ${
                          c.account_type === "REAL"
                            ? "bg-[#F59E0B]/15 text-[#F59E0B]"
                            : "bg-[#38BDF8]/15 text-[#38BDF8]"
                        }`}
                      >
                        {c.account_type}
                      </span>
                      {c.is_preferred && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded bg-[#10B981]/15 text-[#10B981] font-bold flex items-center gap-1">
                          <Star className="w-2.5 h-2.5 fill-current" />
                          <span>PREFERRED</span>
                        </span>
                      )}
                    </div>
                    <span className="text-[10px] text-[#64748B]">
                      Server: {c.server_name} &bull; Login: {c.account_login} &bull; Ref: {c.connection_id}
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  {!c.is_preferred && (
                    <button
                      onClick={() => handleSetPreferred(c.connection_id)}
                      className="px-2.5 py-1 rounded bg-[#151C28] hover:bg-[#1E2736] text-[#94A3B8] hover:text-[#F1F5F9] border border-[#1E2736] transition-colors"
                    >
                      Set Preferred
                    </button>
                  )}
                  <button
                    onClick={() => handleDisconnect(c.connection_id)}
                    className="p-1.5 rounded hover:bg-[#EF4444]/15 text-[#64748B] hover:text-[#EF4444] transition-colors"
                    title="Disconnect Account"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ─── INSTITUTIONAL SECURITY NOTICE ─────────────────────────── */}
      <div className="p-4 rounded-xl bg-[#0E131B] border border-[#1E2736] flex items-start gap-3 text-xs text-[#94A3B8]">
        <Lock className="w-4 h-4 text-[#38BDF8] shrink-0 mt-0.5" />
        <div className="space-y-1">
          <span className="text-[#F1F5F9] font-bold block">
            Multi-Tenant Vault Security Standard
          </span>
          <p className="leading-relaxed text-[#64748B]">
            All MT5 login credentials and gateway auth tokens are encrypted in the local SQLite vault using tenant-bound AES-256-GCM. Plaintext passwords or secrets are never exposed to browser sessions or transmitted over unauthenticated links. Each customer's data is isolated; administrator accounts are never used as customer fallbacks.
          </p>
        </div>
      </div>

      {/* ─── CONNECTION MODAL ───────────────────────────────────────── */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#080B10]/80 backdrop-blur-md animate-in fade-in duration-200">
          <div className="relative w-full max-w-lg bg-[#0E131B] border border-[#1E2736] rounded-2xl shadow-2xl overflow-hidden font-mono text-xs flex flex-col">
            <div className="px-5 py-4 border-b border-[#1E2736] flex items-center justify-between bg-[#151C28]/60">
              <div className="flex items-center gap-2">
                <div
                  className={`w-7 h-7 rounded-lg flex items-center justify-center font-bold ${
                    modalMethod === "MT5_REAL"
                      ? "bg-[#F59E0B]/15 text-[#F59E0B] border border-[#F59E0B]/30"
                      : "bg-[#38BDF8]/15 text-[#38BDF8] border border-[#38BDF8]/30"
                  }`}
                >
                  {modalMethod === "TRADER_API" ? "API" : "MT5"}
                </div>
                <div>
                  <h3 className="font-bold text-[#F1F5F9]">
                    {modalMethod === "TRADER_API"
                      ? "Connect Exness Trader API"
                      : modalMethod === "MT5_DEMO"
                      ? "Connect Exness MT5 Demo"
                      : "Connect Exness MT5 Real"}
                  </h3>
                  <span className="text-[10px] text-[#64748B]">
                    Secure Tenant Vault Registration
                  </span>
                </div>
              </div>
              <button
                onClick={() => setIsModalOpen(false)}
                className="p-1 rounded-lg text-[#64748B] hover:text-[#F1F5F9] hover:bg-[#1E2736] transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

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

              <div className="space-y-1">
                <label className="text-[10px] uppercase text-[#64748B] block">
                  Account Friendly Label (Optional)
                </label>
                <input
                  type="text"
                  value={accountLabel}
                  onChange={(e) => setAccountLabel(e.target.value)}
                  placeholder="e.g. Primary Trading Demo"
                  className="w-full px-3 py-2 rounded-lg bg-[#151C28] border border-[#1E2736] text-[#F1F5F9] focus:outline-none focus:border-[#38BDF8]"
                />
              </div>

              <div className="space-y-1">
                <label className="text-[10px] uppercase text-[#64748B] block">
                  {modalMethod === "TRADER_API" ? "Account ID / API Login" : "MT5 Login ID"}
                </label>
                <input
                  type="text"
                  value={accountLogin}
                  onChange={(e) => setAccountLogin(e.target.value)}
                  placeholder={modalMethod === "TRADER_API" ? "e.g. 88492011" : "e.g. 149827361"}
                  required
                  className="w-full px-3 py-2 rounded-lg bg-[#151C28] border border-[#1E2736] text-[#F1F5F9] focus:outline-none focus:border-[#38BDF8]"
                />
              </div>

              {modalMethod === "TRADER_API" ? (
                <>
                  <div className="space-y-1">
                    <label className="text-[10px] uppercase text-[#64748B] block">
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

                  <div className="space-y-1">
                    <label className="text-[10px] uppercase text-[#64748B] block">
                      Exness API Secret / Token
                    </label>
                    <input
                      type="password"
                      value={apiSecret}
                      onChange={(e) => setApiSecret(e.target.value)}
                      placeholder="Paste API secret token"
                      className="w-full px-3 py-2 rounded-lg bg-[#151C28] border border-[#1E2736] text-[#F1F5F9] focus:outline-none focus:border-[#38BDF8]"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-[10px] uppercase text-[#64748B] block">
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
                </>
              ) : (
                <>
                  <div className="space-y-1">
                    <label className="text-[10px] uppercase text-[#64748B] block">
                      MT5 Trading Password
                    </label>
                    <input
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="Trading password set in Personal Area"
                      required
                      className="w-full px-3 py-2 rounded-lg bg-[#151C28] border border-[#1E2736] text-[#F1F5F9] focus:outline-none focus:border-[#38BDF8]"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-[10px] uppercase text-[#64748B] block">
                      Exness Server Name
                    </label>
                    <input
                      type="text"
                      value={serverName}
                      onChange={(e) => setServerName(e.target.value)}
                      placeholder={modalMethod === "MT5_DEMO" ? "Exness-MT5Trial" : "Exness-Real"}
                      required
                      className="w-full px-3 py-2 rounded-lg bg-[#151C28] border border-[#1E2736] text-[#F1F5F9] focus:outline-none focus:border-[#38BDF8]"
                    />
                  </div>

                  {modalMethod === "MT5_DEMO" && (
                    <div className="flex items-center gap-2 pt-1">
                      <input
                        type="checkbox"
                        id="useMockDemo"
                        checked={useMockDemo}
                        onChange={(e) => setUseMockDemo(e.target.checked)}
                        className="rounded border-[#1E2736] bg-[#151C28] text-[#38BDF8]"
                      />
                      <label htmlFor="useMockDemo" className="text-[11px] text-[#94A3B8]">
                        Enable Deterministic Simulation Mode (Recommended when Windows MT5 bridge is offline)
                      </label>
                    </div>
                  )}
                </>
              )}

              <div className="pt-2 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 rounded-xl bg-[#151C28] hover:bg-[#1E2736] text-[#94A3B8] transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-5 py-2 rounded-xl bg-[#38BDF8] text-[#080B10] font-bold hover:bg-[#38BDF8]/90 transition-all flex items-center gap-1.5 disabled:opacity-50"
                >
                  {isSubmitting ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <ShieldCheck className="w-3.5 h-3.5" />
                  )}
                  <span>Save Connection</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
