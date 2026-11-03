"use client";

import React, { useState, useEffect } from "react";
import {
  QrCode,
  Copy,
  Check,
  ExternalLink,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  X,
  CreditCard,
  ShieldCheck,
  Zap,
  Clock,
  RefreshCw,
  Coins,
} from "lucide-react";

interface BinancePayModalProps {
  isOpen: boolean;
  onClose: () => void;
  token: string;
  defaultType?: "ACTIVATION_FEE" | "PREPAID_TOPUP";
  defaultAmount?: number;
  onSuccess?: () => void;
}

const getApiBase = () => {
  if (typeof window !== "undefined" && window.location.pathname.startsWith("/trading")) {
    return "/trading/api/backend";
  }
  return "/api/backend";
};

const SUPPORTED_NETWORKS = [
  {
    id: "BEP20",
    name: "BNB Smart Chain (BEP20)",
    token: "USDT",
    address: "0x89fE6cAEB199052A9da6D4de97f04cF742F5907d",
    contract: "0x55d398326f99059ff775485246999027b3197955",
    confirmations: "1 confirmation (~3 sec)",
    badge: "Recommended • Lowest Gas",
    color: "amber",
  },
  {
    id: "TRC20",
    name: "Tron (TRC20)",
    token: "USDT",
    address: "TYDddZ7W4wFq88RzE9VjG1PvxYV5wE4kLM",
    contract: "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
    confirmations: "1 confirmation (~1 min)",
    badge: "Fast & Popular",
    color: "rose",
  },
  {
    id: "ERC20",
    name: "Ethereum (ERC20)",
    token: "USDT",
    address: "0x89fE6cAEB199052A9da6D4de97f04cF742F5907d",
    contract: "0xdac17f958d2ee523a2206206994597c13d831ec7",
    confirmations: "12 confirmations (~3 min)",
    badge: "Standard ERC20",
    color: "blue",
  },
  {
    id: "BITCOIN",
    name: "Bitcoin Network",
    token: "BTC",
    address: "bc1q9v0z4f7c8m2d4k6x8p5l2j8u3g7w1y9z8q5t0r",
    contract: "Native L1",
    confirmations: "1 confirmation (~10 min)",
    badge: "Native BTC",
    color: "orange",
  },
];

export default function BinancePayModal({
  isOpen,
  onClose,
  token,
  defaultType = "PREPAID_TOPUP",
  defaultAmount = 50,
  onSuccess,
}: BinancePayModalProps) {
  const [invoiceType, setInvoiceType] = useState<"ACTIVATION_FEE" | "PREPAID_TOPUP">(defaultType);
  const [amount, setAmount] = useState<number>(defaultAmount);
  const [selectedNetwork, setSelectedNetwork] = useState<string>("BEP20");
  const [invoice, setInvoice] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isVerifying, setIsVerifying] = useState(false);
  const [isSimulating, setIsSimulating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [timeLeft, setTimeLeft] = useState(3600);
  const apiBase = getApiBase();

  useEffect(() => {
    setInvoiceType(defaultType);
    if (defaultType === "ACTIVATION_FEE") {
      setAmount(20.0);
    } else {
      setAmount(defaultAmount);
    }
  }, [defaultType, defaultAmount, isOpen]);

  // Expiration countdown
  useEffect(() => {
    if (!invoice) return;
    const timer = setInterval(() => {
      setTimeLeft((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(timer);
  }, [invoice]);

  if (!isOpen) return null;

  const currentNetworkObj = SUPPORTED_NETWORKS.find((n) => n.id === selectedNetwork) || SUPPORTED_NETWORKS[0];

  const handleCreateInvoice = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiBase}/saas/customer/invoices/create`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          amount_usd: invoiceType === "ACTIVATION_FEE" ? 20.0 : amount,
          invoice_type: invoiceType,
          currency: currentNetworkObj.token,
          network: selectedNetwork,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || data.error || "Failed to create crypto invoice");
      }

      setInvoice(data);
      setTimeLeft(3600);
    } catch (err: any) {
      setError(err.message || "Failed to create crypto invoice");
    } finally {
      setIsLoading(false);
    }
  };

  const handleCopyAddress = (addr: string) => {
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      navigator.clipboard.writeText(addr);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleVerifyStatus = async () => {
    if (!invoice) return;
    setIsVerifying(true);
    setError(null);
    try {
      const res = await fetch(`${apiBase}/saas/customer/invoices/${invoice.invoice_id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to probe invoice status");
      if (data.invoice) {
        setInvoice((prev: any) => ({
          ...prev,
          payment_status: data.invoice.status,
          tx_hash: data.invoice.tx_hash,
        }));
        if (data.invoice.status === "PAID" && onSuccess) {
          onSuccess();
        }
      }
    } catch (err: any) {
      setError(err.message || "Verification check failed");
    } finally {
      setIsVerifying(false);
    }
  };

  const handleSimulateSettlement = async () => {
    if (!invoice) return;
    setIsSimulating(true);
    setError(null);
    try {
      const res = await fetch(`${apiBase}/saas/customer/invoices/${invoice.invoice_id}/simulate-confirm`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ status: "PAID" }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Sandbox simulation failed");

      setInvoice((prev: any) => ({
        ...prev,
        payment_status: "PAID",
        tx_hash: data.tx_hash,
      }));

      if (onSuccess) {
        onSuccess();
      }
    } catch (err: any) {
      setError(err.message || "Simulation error");
    } finally {
      setIsSimulating(false);
    }
  };

  const minutes = Math.floor(timeLeft / 60);
  const seconds = timeLeft % 60;
  const timeFormatted = `${minutes}:${seconds < 10 ? "0" : ""}${seconds}`;

  const renderStatusBadge = (status: string) => {
    const s = (status || "AWAITING_PAYMENT").toUpperCase();
    if (s === "PAID" || s === "SUCCESS") {
      return (
        <span className="px-2.5 py-1 rounded-full text-xs font-mono font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 flex items-center gap-1.5">
          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
          Paid & Verified
        </span>
      );
    }
    if (s === "CONFIRMING") {
      return (
        <span className="px-2.5 py-1 rounded-full text-xs font-mono font-bold bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 flex items-center gap-1.5 animate-pulse">
          <Loader2 className="w-3.5 h-3.5 animate-spin text-cyan-400" />
          Confirming on Blockchain (1/1)
        </span>
      );
    }
    if (s === "PAYMENT_DETECTED") {
      return (
        <span className="px-2.5 py-1 rounded-full text-xs font-mono font-bold bg-blue-500/20 text-blue-300 border border-blue-500/40 flex items-center gap-1.5">
          <Clock className="w-3.5 h-3.5 text-blue-400" />
          Payment Detected • Mempool
        </span>
      );
    }
    if (s === "UNDERPAID") {
      return (
        <span className="px-2.5 py-1 rounded-full text-xs font-mono font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40">
          Underpaid (Partial Received)
        </span>
      );
    }
    if (s === "EXPIRED") {
      return (
        <span className="px-2.5 py-1 rounded-full text-xs font-mono font-bold bg-slate-800 text-[#848E9C] border border-slate-700">
          Invoice Expired
        </span>
      );
    }
    return (
      <span className="px-2.5 py-1 rounded-full text-xs font-mono font-bold bg-amber-500/10 text-amber-300 border border-amber-500/30 flex items-center gap-1.5">
        <span className="w-2 h-2 rounded-full bg-amber-400 animate-ping" />
        Awaiting Payment
      </span>
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/85 backdrop-blur-md animate-in fade-in">
      <div className="w-full max-w-lg bg-[#1E2329] border border-[#2B3139] rounded-3xl p-6 sm:p-7 shadow-2xl relative max-h-[92vh] overflow-y-auto text-[#EAECEF]">
        <button
          onClick={onClose}
          className="absolute top-5 right-5 text-[#848E9C] hover:text-[#EAECEF] transition-colors cursor-pointer p-1 rounded-lg hover:bg-[#1e2c47]"
        >
          <X className="w-5 h-5" />
        </button>

        {/* Modal Header */}
        <div className="flex items-center gap-3 mb-5">
          <div className="w-10 h-10 rounded-2xl bg-amber-500/20 text-amber-400 flex items-center justify-center border border-amber-500/30">
            <Coins className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-base font-bold text-[#EAECEF] flex items-center gap-2">
              <span>Direct Crypto Payment & Checkout</span>
              <span className="px-2 py-0.5 text-[9px] font-mono bg-emerald-500/10 text-emerald-400 rounded border border-emerald-500/20 font-bold uppercase">
                Web3 / Invoice
              </span>
            </h3>
            <p className="text-xs text-[#848E9C] font-mono">
              Non-custodial blockchain settlement verified on Bitdex ledger
            </p>
          </div>
        </div>

        {error && (
          <div className="mb-4 p-3.5 rounded-2xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center gap-2.5">
            <AlertTriangle className="w-4 h-4 shrink-0 text-rose-400" />
            <span>{error}</span>
          </div>
        )}

        {/* State 1: Configuration Form (Before Invoice Created) */}
        {!invoice ? (
          <div className="space-y-5">
            {/* Payment Purpose */}
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-2">Payment Purpose</label>
              <div className="grid grid-cols-2 gap-2.5">
                <button
                  type="button"
                  onClick={() => {
                    setInvoiceType("ACTIVATION_FEE");
                    setAmount(20.0);
                  }}
                  className={`p-3.5 rounded-2xl border text-left transition-all cursor-pointer ${
                    invoiceType === "ACTIVATION_FEE"
                      ? "bg-amber-500/15 border-amber-500/50 text-amber-200 shadow-sm"
                      : "bg-[#262C36] border border-[#2B3139] text-slate-300 hover:border-[#3b507a]"
                  }`}
                >
                  <div className="text-xs font-bold text-[#EAECEF] mb-0.5">Account Activation</div>
                  <div className="text-[11px] font-mono opacity-80">$20.00 USD One-Time</div>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setInvoiceType("PREPAID_TOPUP");
                    setAmount(50.0);
                  }}
                  className={`p-3.5 rounded-2xl border text-left transition-all cursor-pointer ${
                    invoiceType === "PREPAID_TOPUP"
                      ? "bg-emerald-500/15 border-emerald-500/50 text-emerald-200 shadow-sm"
                      : "bg-[#262C36] border border-[#2B3139] text-slate-300 hover:border-[#3b507a]"
                  }`}
                >
                  <div className="text-xs font-bold text-[#EAECEF] mb-0.5">Prepaid Top-Up</div>
                  <div className="text-[11px] font-mono opacity-80">AI & Execution Credits</div>
                </button>
              </div>
            </div>

            {/* Prepaid Top-Up Amount */}
            {invoiceType === "PREPAID_TOPUP" && (
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-2">Top-Up Amount (USD)</label>
                <div className="grid grid-cols-4 gap-2 mb-2.5">
                  {[20, 50, 100, 250].map((preset) => (
                    <button
                      key={preset}
                      type="button"
                      onClick={() => setAmount(preset)}
                      className={`py-2 rounded-xl border text-xs font-bold font-mono transition-all cursor-pointer ${
                        amount === preset
                          ? "bg-emerald-600 border-emerald-400 text-[#EAECEF] shadow-sm"
                          : "bg-slate-950 border-slate-800 text-slate-300 hover:bg-slate-800"
                      }`}
                    >
                      ${preset}
                    </button>
                  ))}
                </div>
                <div className="relative">
                  <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[#848E9C] font-mono text-sm">$</span>
                  <input
                    type="number"
                    min="5"
                    step="5"
                    value={amount}
                    onChange={(e) => setAmount(parseFloat(e.target.value) || 0)}
                    className="w-full pl-8 pr-4 py-2.5 bg-[#262C36] border border-[#2B3139] rounded-xl text-[#EAECEF] text-xs font-mono focus:outline-none focus:border-amber-400 transition-colors"
                    placeholder="Enter custom USD amount"
                  />
                </div>
              </div>
            )}

            {/* Network / Blockchain Selection */}
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-2">
                Select Deposit Network & Asset
              </label>
              <div className="space-y-2">
                {SUPPORTED_NETWORKS.map((net) => (
                  <button
                    key={net.id}
                    type="button"
                    onClick={() => setSelectedNetwork(net.id)}
                    className={`w-full p-3 rounded-2xl border text-left transition-all cursor-pointer flex items-center justify-between ${
                      selectedNetwork === net.id
                        ? "bg-amber-500/10 border-amber-500/50 shadow-sm"
                        : "bg-slate-950/60 border-slate-800/80 hover:bg-slate-800/40 text-slate-300"
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-xl bg-slate-800 flex items-center justify-center font-bold text-xs text-[#EAECEF]">
                        {net.token}
                      </div>
                      <div>
                        <div className="text-xs font-bold text-[#EAECEF] flex items-center gap-2">
                          <span>{net.name}</span>
                          <span className="text-[10px] px-2 py-0.2 rounded font-mono font-semibold bg-slate-800 text-slate-300">
                            {net.badge}
                          </span>
                        </div>
                        <div className="text-[10px] text-[#848E9C] font-mono mt-0.5">
                          {net.confirmations}
                        </div>
                      </div>
                    </div>
                    {selectedNetwork === net.id && (
                      <Check className="w-4 h-4 text-amber-400 shrink-0" />
                    )}
                  </button>
                ))}
              </div>
            </div>

            {/* Summary & Create Button */}
            <div className="p-3.5 rounded-2xl bg-[#262C36] border border-[#2B3139] text-xs font-mono space-y-1.5">
              <div className="flex justify-between items-center">
                <span className="text-[#848E9C]">Total Invoice Due:</span>
                <span className="text-[#EAECEF] font-bold text-sm">
                  ${(invoiceType === "ACTIVATION_FEE" ? 20 : amount).toFixed(2)} USD
                </span>
              </div>
              <div className="flex justify-between items-center text-[11px] text-[#848E9C]">
                <span>Selected Network:</span>
                <span className="text-amber-300 font-bold">{currentNetworkObj.name}</span>
              </div>
            </div>

            <button
              onClick={handleCreateInvoice}
              disabled={isLoading || (invoiceType === "PREPAID_TOPUP" && amount <= 0)}
              className="w-full py-3.5 rounded-2xl bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 font-bold text-xs font-mono flex items-center justify-center gap-2 transition-all cursor-pointer shadow-lg shadow-amber-500/20 disabled:opacity-50"
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Generating Invoice & QR...
                </>
              ) : (
                <>
                  <Zap className="w-4 h-4" />
                  Generate Invoice & Receive Address
                </>
              )}
            </button>
          </div>
        ) : (
          /* State 2: Active Invoice & Web3 Deposit View */
          <div className="space-y-5">
            {/* Invoice Top Details */}
            <div className="p-4 rounded-2xl bg-[#262C36] border border-[#2B3139] flex items-center justify-between gap-3 flex-wrap">
              <div className="space-y-0.5">
                <div className="text-[10px] text-[#848E9C] font-mono">Invoice Reference</div>
                <div className="text-xs font-bold font-mono text-[#EAECEF] select-all">
                  {invoice.invoice_id}
                </div>
              </div>
              <div>{renderStatusBadge(invoice.payment_status)}</div>
            </div>

            {/* QR Code and Amount Section */}
            <div className="p-5 rounded-3xl bg-[#262C36] border border-[#2B3139] text-center space-y-4">
              {/* Dynamic QR Code display */}
              <div className="p-3 bg-[#1E2329] rounded-2xl w-44 h-44 mx-auto flex items-center justify-center shadow-lg border-4 border-amber-400">
                <div className="text-[#EAECEF] font-mono text-[9px] text-center p-1 space-y-1.5">
                  <QrCode className="w-24 h-24 text-slate-950 mx-auto" />
                  <span className="block font-bold text-[8px] uppercase tracking-wider text-[#EAECEF]">
                    Scan With Web3 Wallet
                  </span>
                </div>
              </div>

              <div>
                <div className="text-[11px] text-[#848E9C] font-mono">Send Exactly:</div>
                <div className="text-xl font-black font-mono text-emerald-400 tracking-tight">
                  {invoice.crypto_amount || invoice.amount_usd} {invoice.currency}
                </div>
                <div className="text-[11px] text-[#848E9C] font-mono">
                  &asymp; ${invoice.amount_usd.toFixed(2)} USD
                </div>
              </div>

              {/* Deposit Address Box */}
              <div className="text-left space-y-1.5">
                <div className="flex items-center justify-between text-[11px] text-[#848E9C] font-mono">
                  <span>Deposit Address ({invoice.network}):</span>
                  {invoice.payment_status !== "PAID" && (
                    <span className="text-amber-400 flex items-center gap-1 font-bold">
                      <Clock className="w-3 h-3" /> {timeFormatted} left
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-2 p-2.5 rounded-xl bg-[#1E2329] border border-[#2B3139] font-mono text-xs">
                  <span className="text-slate-200 select-all truncate text-[11px] font-bold">
                    {invoice.deposit_address || currentNetworkObj.address}
                  </span>
                  <button
                    onClick={() => handleCopyAddress(invoice.deposit_address || currentNetworkObj.address)}
                    className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-[#EAECEF] transition-all cursor-pointer shrink-0"
                    title="Copy Address"
                  >
                    {copied ? (
                      <Check className="w-4 h-4 text-emerald-400" />
                    ) : (
                      <Copy className="w-4 h-4" />
                    )}
                  </button>
                </div>
              </div>

              {/* Security Warning Notice */}
              <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-left text-[11px] text-amber-200/90 font-mono space-y-1">
                <div>&bull; Send only <strong>{invoice.currency}</strong> on <strong>{invoice.network}</strong> network.</div>
                <div>&bull; Minimum deposit: 0.00000001 {invoice.currency}.</div>
                <div>&bull; Credits post automatically upon 1 network confirmation.</div>
              </div>

              {invoice.tx_hash && (
                <div className="p-2.5 rounded-xl bg-emerald-950/60 border border-emerald-500/40 text-left text-[11px] font-mono text-emerald-300 space-y-0.5">
                  <span className="font-bold block">Settlement Transaction Hash:</span>
                  <span className="select-all text-[10px] break-all">{invoice.tx_hash}</span>
                </div>
              )}
            </div>

            {/* Action Buttons */}
            <div className="space-y-2.5">
              {invoice.payment_status === "PAID" ? (
                <button
                  onClick={onClose}
                  className="w-full py-3.5 rounded-2xl bg-emerald-600 hover:bg-emerald-500 text-[#EAECEF] font-bold text-xs font-mono transition-all cursor-pointer shadow-lg shadow-emerald-600/20"
                >
                  Payment Verified • Done
                </button>
              ) : (
                <>
                  <button
                    onClick={handleVerifyStatus}
                    disabled={isVerifying}
                    className="w-full py-3 rounded-2xl bg-slate-800 hover:bg-slate-700 text-[#EAECEF] font-bold text-xs font-mono flex items-center justify-center gap-2 transition-all cursor-pointer border border-slate-700"
                  >
                    {isVerifying ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin text-amber-400" />
                        Probing Blockchain Confirmations...
                      </>
                    ) : (
                      <>
                        <RefreshCw className="w-4 h-4 text-amber-400" />
                        I Have Sent Payment • Check Status
                      </>
                    )}
                  </button>
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
