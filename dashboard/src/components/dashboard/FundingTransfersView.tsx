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
} from "lucide-react";
import StatusBadge from "../common/StatusBadge";

interface FundingTransfersViewProps {
  token?: string;
  user?: any;
}

export default function FundingTransfersView({ token, user }: FundingTransfersViewProps) {
  const [transferType, setTransferType] = useState<string>("INTERNAL_WALLET_TO_ACCOUNT");
  const [sourceId, setSourceId] = useState<string>("WLT-PRIMARY-USD");
  const [destId, setDestId] = useState<string>("ACC-REAL-5842");
  const [amount, setAmount] = useState<string>("");
  const [currency, setCurrency] = useState<string>("USD");
  const [isLoadingBalances, setIsLoadingBalances] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [balancesData, setBalancesData] = useState<any>(null);
  const [transfersHistory, setTransfersHistory] = useState<any[]>([]);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [showConfirmModal, setShowConfirmModal] = useState<boolean>(false);

  const fetchBalancesAndHistory = async () => {
    setIsLoadingBalances(true);
    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;

      // 1. Balances
      const resBal = await fetch("/api/v1/hft/exness/payments/balances", { headers });
      if (resBal.ok) {
        const dBal = await resBal.json();
        setBalancesData(dBal);
      }

      // 2. History
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
    fetchBalancesAndHistory();
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

    // Generate unique client idempotency key
    const idempotencyKey = `idemp-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;

    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;

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
        throw new Error(data.detail || "Transfer request rejected by Exness Payments API.");
      }

      setActionSuccess(data.message || `Successfully transferred $${numAmt.toFixed(2)} ${currency}.`);
      setAmount("");
      setShowConfirmModal(false);
      fetchBalancesAndHistory();
    } catch (err: any) {
      setActionError(err.message || "Failed to execute transfer.");
      setShowConfirmModal(false);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Direct MT4/MT5 transfer check
  const isDirectMTTransfer =
    (sourceId.includes("ACC") || sourceId.includes("MT")) &&
    (destId.includes("ACC") || destId.includes("MT")) &&
    transferType.includes("ACCOUNT");

  return (
    <div className="space-y-5 animate-in fade-in duration-150">
      {/* View Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[#1E2736] pb-4">
        <div>
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-[#38BDF8]/10 border border-[#38BDF8]/30 flex items-center justify-center">
              <ArrowLeftRight className="w-4 h-4 text-[#38BDF8]" />
            </div>
            <div>
              <h1 className="text-base font-bold text-[#F1F5F9] tracking-wide font-mono flex items-center gap-2">
                <span>Funding & Transfers</span>
                <span className="text-[10px] px-2 py-0.5 rounded bg-[#38BDF8]/10 text-[#38BDF8] border border-[#38BDF8]/20">
                  EXNESS PAYMENTS API
                </span>
              </h1>
              <p className="text-xs text-[#64748B] font-mono">
                Institutional fund movement across Exness Wallets, Trading Accounts, and Partner Portals
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={fetchBalancesAndHistory}
            disabled={isLoadingBalances}
            className="px-3 py-1.5 rounded-lg bg-[#151C28] hover:bg-[#1E2736] text-[#94A3B8] hover:text-[#F1F5F9] font-mono text-xs border border-[#1E2736] flex items-center gap-1.5 transition-all cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoadingBalances ? "animate-spin text-[#38BDF8]" : ""}`} />
            <span>Sync Balances</span>
          </button>

          <a
            href="https://my.exness.com/pa/deposit"
            target="_blank"
            rel="noopener noreferrer"
            className="px-3 py-1.5 rounded-lg bg-[#38BDF8]/15 hover:bg-[#38BDF8] text-[#38BDF8] hover:text-[#080B10] font-mono text-xs font-bold border border-[#38BDF8]/30 flex items-center gap-1.5 transition-all cursor-pointer"
          >
            <span>Exness Personal Area</span>
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        </div>
      </div>

      {/* Balance Summary Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 font-mono">
        {/* Wallet 1: Primary USD */}
        <div className="p-4 rounded-xl bg-[#0E131B] border border-[#1E2736] space-y-2">
          <div className="flex items-center justify-between text-[#64748B] text-xs">
            <span className="flex items-center gap-1.5">
              <Wallet className="w-3.5 h-3.5 text-[#38BDF8]" />
              <span>Primary USD Wallet</span>
            </span>
            <span className="text-[10px] text-[#10B981] font-bold">SETTLED</span>
          </div>
          <div className="text-xl font-bold text-[#F1F5F9] tabular-nums">
            $12,500.00
          </div>
          <div className="text-[10px] text-[#94A3B8] flex justify-between pt-1 border-t border-[#1E2736]">
            <span>Available for Transfer:</span>
            <span className="text-[#38BDF8] font-bold">$12,500.00</span>
          </div>
        </div>

        {/* Wallet 2: Partner Reward Wallet */}
        <div className="p-4 rounded-xl bg-[#0E131B] border border-[#1E2736] space-y-2">
          <div className="flex items-center justify-between text-[#64748B] text-xs">
            <span className="flex items-center gap-1.5">
              <Building className="w-3.5 h-3.5 text-purple-400" />
              <span>Partner Reward Wallet</span>
            </span>
            <span className="text-[10px] text-purple-400 font-bold">PARTNER</span>
          </div>
          <div className="text-xl font-bold text-[#F1F5F9] tabular-nums">
            $3,420.50
          </div>
          <div className="text-[10px] text-[#94A3B8] flex justify-between pt-1 border-t border-[#1E2736]">
            <span>Client Transfer Cap:</span>
            <span className="text-purple-400 font-bold">$3,420.50</span>
          </div>
        </div>

        {/* Account 1: Demo MT5 Account */}
        <div className="p-4 rounded-xl bg-[#0E131B] border border-[#1E2736] space-y-2">
          <div className="flex items-center justify-between text-[#64748B] text-xs">
            <span>Demo MT5 Account</span>
            <span className="text-[10px] text-[#38BDF8] font-bold">SIMULATED</span>
          </div>
          <div className="text-xl font-bold text-[#F1F5F9] tabular-nums">
            $5,000.00
          </div>
          <div className="text-[10px] text-[#94A3B8] flex justify-between pt-1 border-t border-[#1E2736]">
            <span>Server:</span>
            <span>Exness-MT5Trial</span>
          </div>
        </div>

        {/* Account 2: Real MT5 Account */}
        <div className="p-4 rounded-xl bg-[#0E131B] border border-[#1E2736] space-y-2">
          <div className="flex items-center justify-between text-[#64748B] text-xs">
            <span>Real MT5 Account</span>
            <span className="text-[10px] text-[#F59E0B] font-bold">LIVE GATEWAY</span>
          </div>
          <div className="text-xl font-bold text-[#F1F5F9] tabular-nums">
            $0.00
          </div>
          <div className="text-[10px] text-[#94A3B8] flex justify-between pt-1 border-t border-[#1E2736]">
            <span>Server:</span>
            <span>Exness-Real</span>
          </div>
        </div>
      </div>

      {/* Main Content Grid: Transfer Form & Info (2 cols) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 font-mono text-xs">
        {/* Left Column: Transfer Initiation Panel (7 cols) */}
        <div className="lg:col-span-7 space-y-4">
          <div className="p-5 rounded-2xl bg-[#0E131B] border border-[#1E2736] space-y-4">
            <div className="flex items-center justify-between border-b border-[#1E2736] pb-3">
              <span className="font-bold text-sm text-[#F1F5F9] flex items-center gap-2">
                <ArrowLeftRight className="w-4 h-4 text-[#38BDF8]" />
                <span>Initiate Customer Transfer</span>
              </span>
              <span className="text-[10px] text-[#64748B]">Instant API Settlement</span>
            </div>

            {/* Transfer Type Selector */}
            <div>
              <label className="text-[10px] text-[#64748B] uppercase block mb-1.5 font-bold">
                Transfer Method
              </label>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {[
                  { id: "INTERNAL_WALLET_TO_ACCOUNT", label: "Wallet → Trading Account", badge: "Internal" },
                  { id: "INTERNAL_ACCOUNT_TO_WALLET", label: "Trading Account → Wallet", badge: "Internal" },
                  { id: "PARTNER_TO_CLIENT", label: "Partner Wallet → Client Account", badge: "Partner API" },
                  { id: "DEPOSIT_REDIRECT", label: "Deposit to Exness (Hosted)", badge: "Personal Area" },
                ].map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => {
                      setTransferType(t.id);
                      if (t.id === "PARTNER_TO_CLIENT") {
                        setSourceId("WLT-PARTNER-USD");
                        setDestId("ACC-CLIENT-EXT");
                      } else if (t.id === "INTERNAL_ACCOUNT_TO_WALLET") {
                        setSourceId("ACC-REAL-5842");
                        setDestId("WLT-PRIMARY-USD");
                      } else {
                        setSourceId("WLT-PRIMARY-USD");
                        setDestId("ACC-REAL-5842");
                      }
                    }}
                    className={`p-2.5 rounded-xl text-left border transition-all ${
                      transferType === t.id
                        ? "bg-[#151C28] border-[#38BDF8] text-[#F1F5F9] shadow-sm"
                        : "bg-[#080B10] border-[#1E2736] text-[#64748B] hover:text-[#94A3B8]"
                    }`}
                  >
                    <div className="font-bold text-xs">{t.label}</div>
                    <div className="text-[10px] text-[#38BDF8] mt-0.5">{t.badge}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* Source and Destination Pickers */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="text-[10px] text-[#64748B] uppercase block mb-1 font-bold">
                  Source Entity
                </label>
                <select
                  value={sourceId}
                  onChange={(e) => setSourceId(e.target.value)}
                  className="w-full px-3 py-2 bg-[#080B10] border border-[#1E2736] rounded-lg text-[#F1F5F9] focus:outline-none focus:border-[#38BDF8]"
                >
                  <option value="WLT-PRIMARY-USD">Exness Primary USD Wallet ($12,500.00)</option>
                  <option value="WLT-PARTNER-USD">Partner Reward Wallet ($3,420.50)</option>
                  <option value="ACC-REAL-5842">Exness Real MT5 Account (#5842)</option>
                  <option value="ACC-DEMO-9912">Exness Demo MT5 Account (#9912)</option>
                </select>
              </div>

              <div>
                <label className="text-[10px] text-[#64748B] uppercase block mb-1 font-bold">
                  Destination Entity
                </label>
                <select
                  value={destId}
                  onChange={(e) => setDestId(e.target.value)}
                  className="w-full px-3 py-2 bg-[#080B10] border border-[#1E2736] rounded-lg text-[#F1F5F9] focus:outline-none focus:border-[#38BDF8]"
                >
                  <option value="ACC-REAL-5842">Exness Real MT5 Account (#5842)</option>
                  <option value="WLT-PRIMARY-USD">Exness Primary USD Wallet</option>
                  <option value="ACC-CLIENT-EXT">External Exness Client ID</option>
                  <option value="ACC-DEMO-9912">Exness Demo MT5 Account (#9912)</option>
                </select>
              </div>
            </div>

            {/* Direct MT4/MT5 Restriction Notice */}
            {isDirectMTTransfer && (
              <div className="p-3.5 rounded-xl bg-[#F59E0B]/10 border border-[#F59E0B]/30 space-y-2 text-[#F59E0B]">
                <div className="flex items-center gap-2 font-bold text-xs">
                  <AlertTriangle className="w-4 h-4 shrink-0" />
                  <span>Exness Payments API Constraint Notice</span>
                </div>
                <p className="text-[11px] text-[#F59E0B]/90 leading-relaxed">
                  Direct transfers between MT4/MT5 trading accounts are not supported by the Exness Payments API.
                  Transfers must either route via an Exness Wallet intermediary or be executed directly in the official Exness Personal Area.
                </p>
                <a
                  href="https://my.exness.com/pa/deposit"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 px-3 py-1 rounded bg-[#F59E0B] text-[#080B10] font-bold text-xs hover:bg-[#D97706] transition-all"
                >
                  <span>Open Exness Personal Area Deposit</span>
                  <ExternalLink className="w-3 h-3" />
                </a>
              </div>
            )}

            {/* Amount & Currency */}
            <div>
              <div className="flex justify-between items-center mb-1">
                <label className="text-[10px] text-[#64748B] uppercase font-bold">
                  Transfer Amount
                </label>
                <span className="text-[10px] text-[#94A3B8]">Zero broker fee</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="relative flex-1">
                  <span className="absolute left-3 top-2.5 text-[#64748B] font-bold">$</span>
                  <input
                    type="number"
                    min="1"
                    step="any"
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                    placeholder="0.00"
                    className="w-full pl-7 pr-3 py-2 bg-[#080B10] border border-[#1E2736] rounded-lg text-[#F1F5F9] focus:outline-none focus:border-[#38BDF8]"
                  />
                </div>
                <select
                  value={currency}
                  onChange={(e) => setCurrency(e.target.value)}
                  className="px-3 py-2 bg-[#080B10] border border-[#1E2736] rounded-lg text-[#F1F5F9] focus:outline-none focus:border-[#38BDF8]"
                >
                  <option value="USD">USD</option>
                  <option value="EUR">EUR</option>
                  <option value="USDT">USDT</option>
                </select>
              </div>

              {/* Quick Amount Chips */}
              <div className="grid grid-cols-4 gap-2 mt-2">
                {[100, 500, 1000, 5000].map((chip) => (
                  <button
                    key={chip}
                    type="button"
                    onClick={() => setAmount(chip.toString())}
                    className="py-1 rounded bg-[#151C28] hover:bg-[#1E2736] text-[#94A3B8] hover:text-[#F1F5F9] border border-[#1E2736] text-[11px] font-bold transition-all"
                  >
                    +${chip}
                  </button>
                ))}
              </div>
            </div>

            {/* Irreversibility & Policy Notice */}
            <div className="p-3 rounded-lg bg-[#151C28] border border-[#1E2736] text-[11px] text-[#94A3B8] space-y-1">
              <div className="flex items-center gap-1.5 text-[#F1F5F9] font-bold">
                <Info className="w-3.5 h-3.5 text-[#38BDF8]" />
                <span>Irreversible Execution Guarantee</span>
              </div>
              <p>
                All Exness Payments API operations execute immediately and settle in real time.
                Transfers cannot be recalled, reversed, or halted once submitted.
              </p>
            </div>

            {/* Error & Success Alerts */}
            {actionError && (
              <div className="p-3 rounded-lg bg-[#F43F5E]/10 border border-[#F43F5E]/30 text-[#F43F5E] text-xs flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 shrink-0" />
                <span>{actionError}</span>
              </div>
            )}

            {actionSuccess && (
              <div className="p-3 rounded-lg bg-[#10B981]/10 border border-[#10B981]/30 text-[#10B981] text-xs flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 shrink-0" />
                <span>{actionSuccess}</span>
              </div>
            )}

            {/* Action CTA */}
            <button
              type="button"
              onClick={() => setShowConfirmModal(true)}
              disabled={isSubmitting || !amount || parseFloat(amount) <= 0 || isDirectMTTransfer}
              className={`w-full py-2.5 rounded-xl font-bold flex items-center justify-center gap-2 transition-all ${
                !amount || parseFloat(amount) <= 0 || isDirectMTTransfer
                  ? "bg-[#1E2736] text-[#64748B] cursor-not-allowed border border-[#1E2736]"
                  : "bg-[#38BDF8] hover:bg-[#0284C7] text-[#080B10] shadow-lg shadow-[#38BDF8]/20 cursor-pointer"
              }`}
            >
              <ArrowLeftRight className="w-4 h-4" />
              <span>Review & Execute Transfer</span>
            </button>
          </div>
        </div>

        {/* Right Column: API Protocol Details & Limits (5 cols) */}
        <div className="lg:col-span-5 space-y-4">
          <div className="p-5 rounded-2xl bg-[#0E131B] border border-[#1E2736] space-y-3.5">
            <span className="font-bold text-sm text-[#F1F5F9] block border-b border-[#1E2736] pb-2">
              Payments API Specifications
            </span>

            <div className="space-y-2 text-[11px]">
              <div className="flex justify-between">
                <span className="text-[#64748B]">Protocol:</span>
                <span className="text-[#F1F5F9]">REST / Idempotent JSON</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#64748B]">Idempotency Guard:</span>
                <span className="text-[#10B981] font-bold">MANDATORY UUID</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#64748B]">Settlement Latency:</span>
                <span className="text-[#38BDF8] font-bold">&lt; 250ms (Instant)</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#64748B]">Partner Scope:</span>
                <span className="text-[#F1F5F9]">partner:transfers</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#64748B]">Internal Broker Fee:</span>
                <span className="text-[#10B981] font-bold">$0.00 (0.0%)</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#64748B]">Daily Transfer Cap:</span>
                <span className="text-[#F1F5F9]">$50,000.00 / 24h</span>
              </div>
            </div>

            <div className="pt-3 border-t border-[#1E2736] text-[10px] text-[#64748B] space-y-2 leading-relaxed">
              <p>
                <strong>Exness Compliance Requirement:</strong> External deposits require redirecting to the official Exness hosted Personal Area to complete 3D Secure / PSP identity verification.
              </p>
              <p>
                Bitdex never stores card details or primary banking credentials directly on server disk.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Customer Transfer History Ledger */}
      <div className="p-5 rounded-2xl bg-[#0E131B] border border-[#1E2736] space-y-3 font-mono text-xs">
        <div className="flex items-center justify-between border-b border-[#1E2736] pb-2.5">
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4 text-[#38BDF8]" />
            <span className="font-bold text-sm text-[#F1F5F9]">Transfer History Ledger</span>
          </div>
          <span className="text-[10px] text-[#64748B]">
            {transfersHistory.length} total entries
          </span>
        </div>

        {transfersHistory.length === 0 ? (
          <div className="py-8 text-center text-[#64748B]">
            Zero transfers initiated. Completed Exness Payments API transactions will appear in this ledger.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-[#1E2736] text-[10px] text-[#64748B] uppercase">
                  <th className="py-2 px-3">Transfer ID</th>
                  <th className="py-2 px-3">Type</th>
                  <th className="py-2 px-3">Routing (Source → Dest)</th>
                  <th className="py-2 px-3">Amount</th>
                  <th className="py-2 px-3">Broker Reference</th>
                  <th className="py-2 px-3">Status</th>
                  <th className="py-2 px-3">Timestamp</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1E2736]/60 text-[11px]">
                {transfersHistory.map((trf, idx) => (
                  <tr key={trf.transfer_id || idx} className="hover:bg-[#151C28]/40 transition-colors">
                    <td className="py-2.5 px-3 font-bold text-[#F1F5F9]">
                      {trf.transfer_id}
                    </td>
                    <td className="py-2.5 px-3 text-[#94A3B8]">
                      {trf.transfer_type}
                    </td>
                    <td className="py-2.5 px-3 text-[#64748B]">
                      <span className="text-[#F1F5F9]">{trf.source_id}</span> → <span className="text-[#38BDF8]">{trf.destination_id}</span>
                    </td>
                    <td className="py-2.5 px-3 font-bold text-[#10B981] tabular-nums">
                      ${typeof trf.amount === "number" ? trf.amount.toFixed(2) : trf.amount} {trf.currency}
                    </td>
                    <td className="py-2.5 px-3 text-[#64748B] font-mono">
                      {trf.broker_transfer_id || "N/A"}
                    </td>
                    <td className="py-2.5 px-3">
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-[#10B981]/15 text-[#10B981] border border-[#10B981]/30">
                        {trf.status}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-[#64748B]">
                      {trf.created_at}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Confirmation Modal */}
      {showConfirmModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#080B10]/80 backdrop-blur-md animate-in fade-in duration-150">
          <div className="w-full max-w-md bg-[#0E131B] border border-[#1E2736] rounded-2xl shadow-2xl p-5 font-mono text-xs space-y-4">
            <div className="flex items-center justify-between border-b border-[#1E2736] pb-3">
              <span className="font-bold text-sm text-[#F1F5F9] flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-[#F59E0B]" />
                <span>Confirm Irreversible Transfer</span>
              </span>
              <button
                onClick={() => setShowConfirmModal(false)}
                className="text-[#64748B] hover:text-[#F1F5F9]"
              >
                ✕
              </button>
            </div>

            <div className="space-y-2 text-[11px]">
              <div className="flex justify-between">
                <span className="text-[#64748B]">Method:</span>
                <span className="text-[#F1F5F9] font-bold">{transferType}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#64748B]">Source:</span>
                <span className="text-[#F1F5F9]">{sourceId}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#64748B]">Destination:</span>
                <span className="text-[#38BDF8]">{destId}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#64748B]">Amount:</span>
                <span className="text-[#10B981] font-bold text-sm">${parseFloat(amount).toFixed(2)} {currency}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#64748B]">Broker Fee:</span>
                <span className="text-[#10B981] font-bold">$0.00</span>
              </div>
            </div>

            <div className="p-3 rounded-lg bg-[#F59E0B]/10 border border-[#F59E0B]/30 text-[#F59E0B] text-[10px] leading-relaxed">
              <strong>Notice:</strong> This transfer will execute immediately via Exness Payments API and cannot be cancelled or reversed.
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-[#1E2736]">
              <button
                type="button"
                onClick={() => setShowConfirmModal(false)}
                className="px-4 py-2 rounded-lg bg-[#151C28] hover:bg-[#1E2736] text-[#94A3B8] font-bold"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleInitiateTransfer}
                disabled={isSubmitting}
                className="px-4 py-2 rounded-lg bg-[#38BDF8] hover:bg-[#0284C7] text-[#080B10] font-bold flex items-center gap-1.5 cursor-pointer shadow-lg shadow-[#38BDF8]/20"
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Processing...</span>
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    <span>Confirm & Transfer</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
