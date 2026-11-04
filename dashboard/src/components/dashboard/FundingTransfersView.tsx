"use client";

import React, { useState, useEffect } from "react";
import {
  Wallet,
  ArrowLeftRight,
  ExternalLink,
  CheckCircle2,
  AlertTriangle,
  Clock,
  ShieldCheck,
  RefreshCw,
  Plus,
  Lock,
  DollarSign,
  Info,
  Loader2,
  FileText,
  Building,
  Coins,
  ShieldAlert,
  ArrowUpRight,
  HelpCircle,
  Radio,
  Check,
  X,
} from "lucide-react";

interface FundingTransfersViewProps {
  token?: string;
  user?: any;
}

export default function FundingTransfersView({ token, user }: FundingTransfersViewProps) {
  const [activeSection, setActiveSection] = useState<"TRANSFERS" | "TOP_UP">("TRANSFERS");
  const [transferType, setTransferType] = useState<string>("INTERNAL_WALLET_TO_ACCOUNT");
  const [sourceId, setSourceId] = useState<string>("WLT-PRIMARY-USD");
  const [destId, setDestId] = useState<string>("ACC-DEFAULT");
  const [amount, setAmount] = useState<string>("");
  const [currency, setCurrency] = useState<string>("USD");

  const [isLoadingBalances, setIsLoadingBalances] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [balancesData, setBalancesData] = useState<any>(null);
  const [depositOptionsData, setDepositOptionsData] = useState<any>(null);
  const [transfersHistory, setTransfersHistory] = useState<any[]>([]);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [showConfirmModal, setShowConfirmModal] = useState<boolean>(false);
  const [showDepositModal, setShowDepositModal] = useState<boolean>(false);

  const fetchFundingData = async () => {
    setIsLoadingBalances(true);
    try {
      const authToken = token || (typeof window !== "undefined" ? localStorage.getItem("tauric_session_token") || localStorage.getItem("tauric_token") || localStorage.getItem("bitdex_token") : null);
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (authToken) headers["Authorization"] = `Bearer ${authToken}`;

      // 1. Balances & Funding Status
      const resBal = await fetch("/api/v1/hft/exness/payments/balances", { headers });
      if (resBal.ok) {
        const dBal = await resBal.json();
        setBalancesData(dBal);
      }

      // 2. Deposit Options & Crypto Investigation
      const resDep = await fetch("/api/v1/hft/exness/payments/deposit-options", { headers });
      if (resDep.ok) {
        const dDep = await resDep.json();
        setDepositOptionsData(dDep);
      }

      // 3. History
      const resHist = await fetch("/api/v1/hft/exness/payments/history", { headers });
      if (resHist.ok) {
        const dHist = await resHist.json();
        setTransfersHistory(dHist.transfers || []);
      }
    } catch (err: any) {
      console.error("Failed to load Exness funding data:", err);
    } finally {
      setIsLoadingBalances(false);
    }
  };

  useEffect(() => {
    fetchFundingData();
  }, [token]);

  const handleInitiateTransfer = async () => {
    const numAmt = parseFloat(amount);
    if (!numAmt || numAmt <= 0) {
      setActionError("Please enter a valid positive transfer amount.");
      return;
    }

    setIsSubmitting(true);
    setActionError(null);
    setActionSuccess(null);

    const idempotencyKey = `idemp-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;

    try {
      const authToken = token || (typeof window !== "undefined" ? localStorage.getItem("tauric_session_token") || localStorage.getItem("tauric_token") || localStorage.getItem("bitdex_token") : null);
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (authToken) headers["Authorization"] = `Bearer ${authToken}`;

      const res = await fetch("/api/v1/hft/exness/payments/transfer", {
        method: "POST",
        headers,
        body: JSON.stringify({
          transfer_type: transferType,
          source_id: sourceId,
          destination_id: destId,
          amount: numAmt,
          currency: currency,
          idempotency_key: idempotencyKey,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Transfer submission failed.");
      }

      setActionSuccess(data.message || "Transfer initiated successfully.");
      setAmount("");
      setShowConfirmModal(false);
      fetchFundingData();
    } catch (err: any) {
      setActionError(err.message || "Failed to execute transfer.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const fundingStatus = balancesData?.funding_status || "NOT_CONNECTED";

  // Status Badge Colors & Labels
  const getStatusBadge = (st: string) => {
    switch (st) {
      case "CONNECTED":
        return { label: "CONNECTED", bg: "bg-[#10B981]/15 text-[#10B981] border-[#10B981]/30" };
      case "AWAITING_AUTHENTICATION":
        return { label: "AWAITING AUTHENTICATION", bg: "bg-[#F59E0B]/15 text-[#F59E0B] border-[#F59E0B]/30" };
      case "DEPOSIT_PENDING":
        return { label: "DEPOSIT PENDING", bg: "bg-[#38BDF8]/15 text-[#38BDF8] border-[#38BDF8]/30" };
      case "DEPOSIT_COMPLETED":
        return { label: "DEPOSIT COMPLETED", bg: "bg-[#10B981]/15 text-[#10B981] border-[#10B981]/30" };
      case "DEPOSIT_REJECTED":
        return { label: "DEPOSIT REJECTED", bg: "bg-[#EF4444]/15 text-[#EF4444] border-[#EF4444]/30" };
      case "TRANSFER_PENDING":
        return { label: "TRANSFER PENDING", bg: "bg-[#F59E0B]/15 text-[#F59E0B] border-[#F59E0B]/30" };
      case "TRANSFER_COMPLETED":
        return { label: "TRANSFER COMPLETED", bg: "bg-[#10B981]/15 text-[#10B981] border-[#10B981]/30" };
      case "TRANSFER_REJECTED":
        return { label: "TRANSFER REJECTED", bg: "bg-[#EF4444]/15 text-[#EF4444] border-[#EF4444]/30" };
      case "NOT_CONNECTED":
      default:
        return { label: "NOT CONNECTED", bg: "bg-[#EF4444]/15 text-[#EF4444] border-[#EF4444]/30" };
    }
  };

  const statusBadge = getStatusBadge(fundingStatus);

  return (
    <div className="space-y-6 font-mono text-xs animate-in fade-in duration-200">
      {/* ─── HEADER & AUTHORITATIVE STATUS BANNER ────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-5 rounded-2xl bg-[#0E131B] border border-[#1E2736]">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-bold text-[#F1F5F9] uppercase tracking-wider">
              Exness Funding &amp; Transfers
            </h1>
            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-[#38BDF8]/10 text-[#38BDF8] border border-[#38BDF8]/30">
              PAYMENTS API
            </span>
          </div>
          <p className="text-xs text-[#94A3B8] mt-1">
            Official Exness Payments API transfers and direct Personal Area deposit top-up gateway.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#080B10] border border-[#1E2736]">
            <span className="text-[10px] text-[#64748B] uppercase">Funding State:</span>
            <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${statusBadge.bg}`}>
              {statusBadge.label}
            </span>
          </div>

          <button
            onClick={() => setShowDepositModal(true)}
            className="px-3 py-1.5 rounded-lg bg-[#F59E0B] hover:bg-[#F59E0B]/90 text-[#080B10] font-bold transition-all flex items-center gap-1.5 cursor-pointer shadow-sm"
          >
            <Coins className="w-3.5 h-3.5" />
            <span>TOP UP EXNESS ACCOUNT</span>
          </button>

          <button
            onClick={fetchFundingData}
            disabled={isLoadingBalances}
            className="p-2 rounded-lg bg-[#151C28] hover:bg-[#1E2736] text-[#94A3B8] hover:text-[#F1F5F9] border border-[#1E2736] transition-colors"
            title="Refresh Ledger"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoadingBalances ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {/* ─── SECTION SELECTOR TABS ─────────────────────────────────── */}
      <div className="flex items-center gap-2 p-1 rounded-xl bg-[#0E131B] border border-[#1E2736] w-fit">
        <button
          onClick={() => setActiveSection("TRANSFERS")}
          className={`px-4 py-2 rounded-lg font-bold transition-all flex items-center gap-2 ${
            activeSection === "TRANSFERS"
              ? "bg-[#38BDF8] text-[#080B10]"
              : "text-[#94A3B8] hover:text-[#F1F5F9]"
          }`}
        >
          <ArrowLeftRight className="w-4 h-4" />
          <span>Section A: Exness Internal Transfers</span>
        </button>

        <button
          onClick={() => setActiveSection("TOP_UP")}
          className={`px-4 py-2 rounded-lg font-bold transition-all flex items-center gap-2 ${
            activeSection === "TOP_UP"
              ? "bg-[#F59E0B] text-[#080B10]"
              : "text-[#94A3B8] hover:text-[#F1F5F9]"
          }`}
        >
          <Coins className="w-4 h-4" />
          <span>Section B: Deposit / Top Up &amp; Crypto</span>
        </button>
      </div>

      {/* ─── BALANCES OVERVIEW CARDS ─────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Primary Wallet */}
        <div className="p-4 rounded-xl bg-[#0E131B] border border-[#1E2736] space-y-1">
          <div className="flex items-center justify-between text-[#64748B]">
            <span className="uppercase text-[10px]">Primary USD Wallet</span>
            <Wallet className="w-3.5 h-3.5 text-[#38BDF8]" />
          </div>
          <div className="text-base font-bold text-[#F1F5F9] tabular-nums">
            ${balancesData?.wallets?.[0]?.balance?.toFixed(2) || "0.00"}
          </div>
          <span className="text-[10px] text-[#64748B] block">Exness Cash Balance</span>
        </div>

        {/* Partner Wallet */}
        <div className="p-4 rounded-xl bg-[#0E131B] border border-[#1E2736] space-y-1">
          <div className="flex items-center justify-between text-[#64748B]">
            <span className="uppercase text-[10px]">Partner Reward Wallet</span>
            <Building className="w-3.5 h-3.5 text-[#10B981]" />
          </div>
          <div className="text-base font-bold text-[#10B981] tabular-nums">
            ${balancesData?.wallets?.[1]?.balance?.toFixed(2) || "0.00"}
          </div>
          <span className="text-[10px] text-[#64748B] block">Transfer-Eligible Rebates</span>
        </div>

        {/* Customer Demo Account */}
        <div className="p-4 rounded-xl bg-[#0E131B] border border-[#1E2736] space-y-1">
          <div className="flex items-center justify-between text-[#64748B]">
            <span className="uppercase text-[10px]">Customer Demo Account</span>
            <ShieldCheck className="w-3.5 h-3.5 text-[#38BDF8]" />
          </div>
          <div className="text-base font-bold text-[#38BDF8] tabular-nums">
            {balancesData?.demo_accounts?.length > 0
              ? `$${balancesData.demo_accounts[0].balance.toFixed(2)}`
              : "UNAVAILABLE"}
          </div>
          <span className="text-[10px] text-[#64748B] block">
            {balancesData?.demo_accounts?.length > 0
              ? `Login: ${balancesData.demo_accounts[0].account_login}`
              : "No Demo Connected"}
          </span>
        </div>

        {/* Customer Real Account */}
        <div className="p-4 rounded-xl bg-[#0E131B] border border-[#1E2736] space-y-1">
          <div className="flex items-center justify-between text-[#64748B]">
            <span className="uppercase text-[10px]">Customer Real Account</span>
            <Lock className="w-3.5 h-3.5 text-[#F59E0B]" />
          </div>
          <div className="text-base font-bold text-[#F59E0B] tabular-nums">
            {balancesData?.real_accounts?.length > 0
              ? `$${balancesData.real_accounts[0].balance.toFixed(2)}`
              : "UNAVAILABLE"}
          </div>
          <span className="text-[10px] text-[#64748B] block">
            {balancesData?.real_accounts?.length > 0
              ? `Login: ${balancesData.real_accounts[0].account_login}`
              : "No Real Connected"}
          </span>
        </div>
      </div>

      {/* ─── SECTION A: INTERNAL TRANSFERS ──────────────────────────── */}
      {activeSection === "TRANSFERS" && (
        <div className="space-y-4">
          {/* Critical Broker Constraint Warning Callout */}
          <div className="p-4 rounded-xl bg-[#080B10] border border-[#F59E0B]/30 flex items-start gap-3 text-[#F59E0B]">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-[#F59E0B]" />
            <div className="space-y-1 text-xs">
              <span className="font-bold text-[#F1F5F9] block">
                Exness Payments API Architectural Rule: Direct MT4/MT5 Account Transfers Are Restricted
              </span>
              <p className="text-[#94A3B8] leading-relaxed">
                The official Exness Payments API only supports transfers between your <strong>Exness Wallets and Trading Accounts</strong>, or authorized <strong>Partner Reward Wallet</strong> transfers to clients. Direct account-to-account transfers between two MT4/MT5 trading account numbers are rejected by the API. If you need to reallocate balance between two MT5 terminals, execute the transfer directly inside your official Exness Personal Area.
              </p>
              <a
                href="https://my.exness.com/pa/deposit"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 font-bold text-[#38BDF8] hover:underline pt-1"
              >
                <span>Open Exness Personal Area Transfers &rarr;</span>
              </a>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Transfer Initiation Form */}
            <div className="p-5 rounded-2xl bg-[#0E131B] border border-[#1E2736] space-y-4">
              <div className="flex items-center justify-between border-b border-[#1E2736] pb-3">
                <span className="font-bold text-[#F1F5F9] uppercase">
                  Initiate Customer Transfer
                </span>
                <span className="text-[10px] text-[#64748B]">Zero Broker Fee &bull; Instant</span>
              </div>

              {actionSuccess && (
                <div className="p-3 rounded-lg bg-[#10B981]/10 border border-[#10B981]/30 text-[#10B981] flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 shrink-0" />
                  <span>{actionSuccess}</span>
                </div>
              )}

              {actionError && (
                <div className="p-3 rounded-lg bg-[#EF4444]/10 border border-[#EF4444]/30 text-[#EF4444] flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 shrink-0" />
                  <span>{actionError}</span>
                </div>
              )}

              <div className="space-y-1">
                <label className="text-[10px] uppercase text-[#64748B] block">Transfer Type</label>
                <select
                  value={transferType}
                  onChange={(e) => setTransferType(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-[#151C28] border border-[#1E2736] text-[#F1F5F9] focus:outline-none focus:border-[#38BDF8]"
                >
                  <option value="INTERNAL_WALLET_TO_ACCOUNT">Exness Primary Wallet &rarr; Trading Account</option>
                  <option value="INTERNAL_ACCOUNT_TO_WALLET">Trading Account &rarr; Exness Primary Wallet</option>
                  <option value="PARTNER_TO_CLIENT">Partner Reward Wallet &rarr; Client Transfer</option>
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-[10px] uppercase text-[#64748B] block">Source Account</label>
                  <input
                    type="text"
                    value={sourceId}
                    onChange={(e) => setSourceId(e.target.value)}
                    placeholder="e.g. WLT-PRIMARY-USD"
                    className="w-full px-3 py-2 rounded-lg bg-[#151C28] border border-[#1E2736] text-[#F1F5F9] focus:outline-none focus:border-[#38BDF8]"
                  />
                </div>

                <div className="space-y-1">
                  <label className="text-[10px] uppercase text-[#64748B] block">Destination Account</label>
                  <input
                    type="text"
                    value={destId}
                    onChange={(e) => setDestId(e.target.value)}
                    placeholder="e.g. ACC-DEMO or ACC-REAL"
                    className="w-full px-3 py-2 rounded-lg bg-[#151C28] border border-[#1E2736] text-[#F1F5F9] focus:outline-none focus:border-[#38BDF8]"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-[10px] uppercase text-[#64748B] block">Transfer Amount (USD)</label>
                  <input
                    type="number"
                    step="0.01"
                    min="1.00"
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                    placeholder="min $10.00"
                    className="w-full px-3 py-2 rounded-lg bg-[#151C28] border border-[#1E2736] text-[#F1F5F9] font-bold focus:outline-none focus:border-[#38BDF8]"
                  />
                </div>

                <div className="space-y-1">
                  <label className="text-[10px] uppercase text-[#64748B] block">Currency</label>
                  <select
                    value={currency}
                    onChange={(e) => setCurrency(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-[#151C28] border border-[#1E2736] text-[#F1F5F9] focus:outline-none focus:border-[#38BDF8]"
                  >
                    <option value="USD">USD (United States Dollar)</option>
                    <option value="EUR">EUR (Euro)</option>
                  </select>
                </div>
              </div>

              <div className="p-3 rounded-lg bg-[#080B10] border border-[#1E2736] text-[10px] text-[#64748B] space-y-1">
                <div className="flex justify-between">
                  <span>Transfer Fee:</span>
                  <span className="font-bold text-[#10B981]">0.00% (Free)</span>
                </div>
                <div className="flex justify-between">
                  <span>Settlement Speed:</span>
                  <span className="font-bold text-[#F1F5F9]">Instantaneous</span>
                </div>
                <div className="flex justify-between">
                  <span>Reversibility:</span>
                  <span className="font-bold text-[#EF4444]">Irreversible via API</span>
                </div>
              </div>

              <button
                type="button"
                onClick={() => setShowConfirmModal(true)}
                disabled={!amount || parseFloat(amount) <= 0}
                className="w-full py-2.5 rounded-xl bg-[#38BDF8] text-[#080B10] font-bold hover:bg-[#38BDF8]/90 transition-all flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <ArrowLeftRight className="w-4 h-4" />
                <span>Review &amp; Confirm Transfer</span>
              </button>
            </div>

            {/* Transfer Policy & Guidelines */}
            <div className="p-5 rounded-2xl bg-[#0E131B] border border-[#1E2736] space-y-3 flex flex-col justify-between">
              <div>
                <span className="font-bold text-[#F1F5F9] uppercase block border-b border-[#1E2736] pb-3">
                  Exness Payments API Transfer Policies
                </span>
                <div className="space-y-2.5 pt-3 text-[11px] text-[#94A3B8]">
                  <div className="flex items-start gap-2">
                    <CheckCircle2 className="w-4 h-4 text-[#38BDF8] shrink-0 mt-0.5" />
                    <p>
                      <strong>Idempotency Enforcement:</strong> Every API transfer generates an authoritative UUIDv4 idempotency key. Resubmitting an identical transfer request returns the original ticket without double-charging funds.
                    </p>
                  </div>
                  <div className="flex items-start gap-2">
                    <CheckCircle2 className="w-4 h-4 text-[#38BDF8] shrink-0 mt-0.5" />
                    <p>
                      <strong>Partner Wallet Permissions:</strong> Transfers from Partner Reward Wallets require verified partner authorization scope.
                    </p>
                  </div>
                  <div className="flex items-start gap-2">
                    <CheckCircle2 className="w-4 h-4 text-[#38BDF8] shrink-0 mt-0.5" />
                    <p>
                      <strong>Account Ownership Validation:</strong> All transfers must be initiated by and routed to accounts owned by the authenticated customer.
                    </p>
                  </div>
                </div>
              </div>

              <div className="p-3 rounded-lg bg-[#151C28] border border-[#1E2736] text-[10px] text-[#64748B]">
                Need direct MT4/MT5 internal transfer? Log into your{" "}
                <a
                  href="https://my.exness.com/pa"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[#38BDF8] hover:underline font-bold"
                >
                  Exness Personal Area &rarr; Internal Transfers
                </a>
                .
              </div>
            </div>
          </div>

          {/* Audit History Ledger */}
          <div className="rounded-2xl bg-[#0E131B] border border-[#1E2736] overflow-hidden">
            <div className="p-4 bg-[#151C28]/60 border-b border-[#1E2736] flex items-center justify-between">
              <span className="font-bold text-[#F1F5F9] uppercase flex items-center gap-2">
                <Clock className="w-4 h-4 text-[#38BDF8]" />
                <span>Customer Transfer History Audit Ledger</span>
              </span>
              <span className="text-[10px] text-[#64748B]">
                {transfersHistory.length} Total Dispatches
              </span>
            </div>

            {transfersHistory.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-[11px]">
                  <thead>
                    <tr className="border-b border-[#1E2736] bg-[#080B10]/40 text-[#64748B] uppercase text-[10px]">
                      <th className="p-3">Timestamp</th>
                      <th className="p-3">Transfer Ref</th>
                      <th className="p-3">Type</th>
                      <th className="p-3">Source &rarr; Dest</th>
                      <th className="p-3">Amount</th>
                      <th className="p-3">Broker Reference</th>
                      <th className="p-3">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#1E2736] text-[#94A3B8]">
                    {transfersHistory.map((t: any) => (
                      <tr key={t.transfer_id} className="hover:bg-[#151C28]/30 transition-colors">
                        <td className="p-3 tabular-nums">{t.created_at}</td>
                        <td className="p-3 font-bold text-[#F1F5F9]">{t.transfer_id}</td>
                        <td className="p-3">{t.transfer_type}</td>
                        <td className="p-3">{t.source_id} &rarr; {t.destination_id}</td>
                        <td className="p-3 font-bold text-[#F1F5F9] tabular-nums">${t.amount?.toFixed(2)} {t.currency}</td>
                        <td className="p-3 text-[#38BDF8]">{t.broker_transfer_id || "Awaiting Broker ID"}</td>
                        <td className="p-3">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                              t.status === "COMPLETED"
                                ? "bg-[#10B981]/15 text-[#10B981]"
                                : t.status === "REJECTED"
                                ? "bg-[#EF4444]/15 text-[#EF4444]"
                                : "bg-[#F59E0B]/15 text-[#F59E0B]"
                            }`}
                          >
                            {t.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="p-6 text-center text-[#64748B]">
                No customer transfer dispatches recorded in audit ledger.
              </div>
            )}
          </div>
        </div>
      )}

      {/* ─── SECTION B: DEPOSIT / TOP UP EXNESS ──────────────────────── */}
      {activeSection === "TOP_UP" && (
        <div className="space-y-4">
          <div className="p-5 rounded-2xl bg-[#0E131B] border border-[#1E2736] space-y-4">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-[#1E2736] pb-4">
              <div>
                <h3 className="text-sm font-bold text-[#F1F5F9] uppercase flex items-center gap-2">
                  <Coins className="w-4 h-4 text-[#F59E0B]" />
                  <span>Deposit &amp; Top Up Exness Trading Capital</span>
                </h3>
                <p className="text-xs text-[#94A3B8] mt-1">
                  BITDEX does not collect or process deposits. All customer deposits must be made directly through your personal Exness Personal Area.
                </p>
              </div>

              <a
                href="https://my.exness.com/pa/deposit"
                target="_blank"
                rel="noopener noreferrer"
                className="px-5 py-2.5 rounded-xl bg-[#F59E0B] hover:bg-[#F59E0B]/90 text-[#080B10] font-bold transition-all flex items-center gap-2 cursor-pointer shadow-lg shrink-0"
              >
                <span>TOP UP IN PERSONAL AREA</span>
                <ArrowUpRight className="w-4 h-4" />
              </a>
            </div>

            {/* Core Anti-Intermediary Disclosure */}
            <div className="p-4 rounded-xl bg-[#080B10] border border-[#1E2736] space-y-2 text-xs">
              <span className="font-bold text-[#F1F5F9] block uppercase text-[11px]">
                Strict Customer Deposit Separation Standard
              </span>
              <ul className="space-y-1.5 text-[#94A3B8] text-[11px]">
                <li className="flex items-start gap-2">
                  <span className="text-[#38BDF8]">&bull;</span>
                  <span>BITDEX is a trading software terminal and NEVER acts as a money transmitter or payment processor.</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-[#38BDF8]">&bull;</span>
                  <span>BITDEX will never ask you to send cryptocurrency or fiat to a company bank account or wallet.</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-[#38BDF8]">&bull;</span>
                  <span>Payments API does not accept external card or third-party deposits; all external funding routes through official Exness checkout.</span>
                </li>
              </ul>
            </div>

            {/* Crypto & Binance Pay Investigation Panel */}
            <div className="space-y-3 pt-2">
              <div className="flex items-center justify-between">
                <span className="font-bold text-[#F1F5F9] uppercase text-xs flex items-center gap-2">
                  <Radio className="w-3.5 h-3.5 text-[#38BDF8]" />
                  <span>Crypto &amp; Alternative Payment Investigation Findings</span>
                </span>
                <span className="text-[10px] text-[#64748B]">Regional Exness Availability</span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {/* Method 1: USDT */}
                <div className="p-4 rounded-xl bg-[#151C28] border border-[#1E2736] space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-[#F1F5F9]">USDT (Tether)</span>
                    <span className="text-[9px] px-1.5 py-0.5 rounded bg-[#10B981]/15 text-[#10B981] font-bold">
                      TRC20 / ERC20
                    </span>
                  </div>
                  <div className="space-y-1 text-[11px] text-[#94A3B8]">
                    <div className="flex justify-between">
                      <span>Exness Commission:</span>
                      <strong className="text-[#10B981]">0.00% (No Broker Fee)</strong>
                    </div>
                    <div className="flex justify-between">
                      <span>Network Gas Fee:</span>
                      <strong className="text-[#F1F5F9]">Variable (Network standard)</strong>
                    </div>
                    <div className="flex justify-between">
                      <span>Minimum Deposit:</span>
                      <strong className="text-[#F1F5F9]">~$10.00 USD</strong>
                    </div>
                    <div className="flex justify-between">
                      <span>Availability:</span>
                      <strong className="text-[#38BDF8]">Region Dependent (PA)</strong>
                    </div>
                  </div>
                </div>

                {/* Method 2: BTC */}
                <div className="p-4 rounded-xl bg-[#151C28] border border-[#1E2736] space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-[#F1F5F9]">Bitcoin (BTC)</span>
                    <span className="text-[9px] px-1.5 py-0.5 rounded bg-[#F59E0B]/15 text-[#F59E0B] font-bold">
                      Bitcoin Core
                    </span>
                  </div>
                  <div className="space-y-1 text-[11px] text-[#94A3B8]">
                    <div className="flex justify-between">
                      <span>Exness Commission:</span>
                      <strong className="text-[#10B981]">0.00% (No Broker Fee)</strong>
                    </div>
                    <div className="flex justify-between">
                      <span>Miner Network Fee:</span>
                      <strong className="text-[#F1F5F9]">Standard Bitcoin miner fee</strong>
                    </div>
                    <div className="flex justify-between">
                      <span>Confirmations:</span>
                      <strong className="text-[#F1F5F9]">3 to 6 block confirms</strong>
                    </div>
                    <div className="flex justify-between">
                      <span>Availability:</span>
                      <strong className="text-[#38BDF8]">Region Dependent (PA)</strong>
                    </div>
                  </div>
                </div>

                {/* Method 3: Binance Pay */}
                <div className="p-4 rounded-xl bg-[#151C28] border border-[#1E2736] space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-[#F1F5F9]">Binance Pay</span>
                    <span className="text-[9px] px-1.5 py-0.5 rounded bg-[#F59E0B]/15 text-[#F59E0B] font-bold">
                      Instant App Pay
                    </span>
                  </div>
                  <div className="space-y-1 text-[11px] text-[#94A3B8]">
                    <div className="flex justify-between">
                      <span>Exness Commission:</span>
                      <strong className="text-[#10B981]">0.00% (No Broker Fee)</strong>
                    </div>
                    <div className="flex justify-between">
                      <span>Binance Internal Fee:</span>
                      <strong className="text-[#10B981]">0.00%</strong>
                    </div>
                    <div className="flex justify-between">
                      <span>Processing Speed:</span>
                      <strong className="text-[#10B981]">Instantaneous</strong>
                    </div>
                    <div className="flex justify-between">
                      <span>Eligibility:</span>
                      <strong className="text-[#38BDF8]">Country Registered (PA)</strong>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Critical Security Warning */}
            <div className="p-4 rounded-xl bg-[#EF4444]/10 border border-[#EF4444]/30 flex items-start gap-3 text-[#EF4444]">
              <ShieldAlert className="w-4 h-4 shrink-0 mt-0.5" />
              <div className="space-y-1 text-xs">
                <span className="font-bold uppercase block text-[#EF4444]">
                  Zero Private Key / Seed Phrase Policy
                </span>
                <p className="text-[#94A3B8] leading-relaxed">
                  NEVER share your cryptocurrency private key, recovery seed phrase, or Exness Personal Area credentials with anyone. BITDEX representatives will NEVER request your seed phrase, ask you to transfer crypto to a BITDEX wallet, or provide an unofficial deposit address.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ─── CONFIRM TRANSFER MODAL ─────────────────────────────────── */}
      {showConfirmModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#080B10]/80 backdrop-blur-md animate-in fade-in duration-200">
          <div className="relative w-full max-w-md bg-[#0E131B] border border-[#1E2736] rounded-2xl p-5 shadow-2xl font-mono text-xs space-y-4">
            <div className="flex items-center justify-between border-b border-[#1E2736] pb-3">
              <span className="font-bold text-[#F1F5F9] uppercase flex items-center gap-2">
                <ArrowLeftRight className="w-4 h-4 text-[#38BDF8]" />
                <span>Confirm Payments API Transfer</span>
              </span>
              <button
                onClick={() => setShowConfirmModal(false)}
                className="p-1 rounded text-[#64748B] hover:text-[#F1F5F9]"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-2 p-3 rounded-xl bg-[#151C28] border border-[#1E2736]">
              <div className="flex justify-between text-[#94A3B8]">
                <span>Transfer Type:</span>
                <strong className="text-[#F1F5F9]">{transferType}</strong>
              </div>
              <div className="flex justify-between text-[#94A3B8]">
                <span>Source:</span>
                <strong className="text-[#F1F5F9]">{sourceId}</strong>
              </div>
              <div className="flex justify-between text-[#94A3B8]">
                <span>Destination:</span>
                <strong className="text-[#F1F5F9]">{destId}</strong>
              </div>
              <div className="flex justify-between text-[#94A3B8]">
                <span>Amount:</span>
                <strong className="text-[#38BDF8] text-sm tabular-nums">${parseFloat(amount || "0").toFixed(2)} {currency}</strong>
              </div>
            </div>

            <div className="p-3 rounded-lg bg-[#F59E0B]/10 border border-[#F59E0B]/30 text-[#F59E0B] text-[11px] leading-relaxed">
              <strong>Notice:</strong> Payments API transfers are settled immediately and are irreversible. Resubmitting with an identical idempotency key will not create a duplicate charge.
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setShowConfirmModal(false)}
                className="px-4 py-2 rounded-xl bg-[#151C28] hover:bg-[#1E2736] text-[#94A3B8] transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleInitiateTransfer}
                disabled={isSubmitting}
                className="px-5 py-2 rounded-xl bg-[#38BDF8] text-[#080B10] font-bold hover:bg-[#38BDF8]/90 transition-all flex items-center gap-1.5"
              >
                {isSubmitting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
                <span>Confirm &amp; Execute</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ─── DIRECT TOP-UP MODAL ─────────────────────────────────────── */}
      {showDepositModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#080B10]/80 backdrop-blur-md animate-in fade-in duration-200">
          <div className="relative w-full max-w-lg bg-[#0E131B] border border-[#1E2736] rounded-2xl p-5 shadow-2xl font-mono text-xs space-y-4">
            <div className="flex items-center justify-between border-b border-[#1E2736] pb-3">
              <span className="font-bold text-[#F1F5F9] uppercase flex items-center gap-2">
                <Coins className="w-4 h-4 text-[#F59E0B]" />
                <span>Exness Official Deposit Checkout</span>
              </span>
              <button
                onClick={() => setShowDepositModal(false)}
                className="p-1 rounded text-[#64748B] hover:text-[#F1F5F9]"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-2 text-[#94A3B8] leading-relaxed">
              <p>
                To top up your Exness trading capital, you will be redirected to the secure official <strong>Exness Personal Area</strong> checkout.
              </p>
              <div className="p-3 rounded-xl bg-[#151C28] border border-[#1E2736] text-[11px] space-y-1">
                <div>&bull; <strong>Verified URL:</strong> <code className="text-[#38BDF8]">https://my.exness.com/pa/deposit</code></div>
                <div>&bull; <strong>Supported Methods:</strong> Crypto (USDT, BTC), Binance Pay, Bank Wire, Local Transfer (Region-dependent).</div>
                <div>&bull; <strong>BITDEX Policy:</strong> Zero customer funds or private keys handled.</div>
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setShowDepositModal(false)}
                className="px-4 py-2 rounded-xl bg-[#151C28] hover:bg-[#1E2736] text-[#94A3B8] transition-colors"
              >
                Cancel
              </button>
              <a
                href="https://my.exness.com/pa/deposit"
                target="_blank"
                rel="noopener noreferrer"
                onClick={() => setShowDepositModal(false)}
                className="px-5 py-2 rounded-xl bg-[#F59E0B] hover:bg-[#F59E0B]/90 text-[#080B10] font-bold transition-all flex items-center gap-1.5 shadow-md"
              >
                <span>Continue to Exness Deposit &rarr;</span>
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
