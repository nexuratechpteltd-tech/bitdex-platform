"use client";

import React, { useState, useEffect } from "react";
import {
  X,
  AlertTriangle,
  Lock,
  CheckCircle2,
  Cpu,
  Loader2,
  ExternalLink,
  ShieldAlert,
  ArrowRight,
  UserCheck,
  ChevronDown,
} from "lucide-react";

interface TradeExecutionModalProps {
  isOpen: boolean;
  onClose: () => void;
  symbol: string;
  currentPrice: number | null;
  entryPrice: number | null;
  stopLoss: number | null;
  takeProfit: number | null;
  token?: string;
  onNavigateToConnections?: () => void;
}

export default function TradeExecutionModal({
  isOpen,
  onClose,
  symbol,
  currentPrice,
  entryPrice,
  stopLoss,
  takeProfit,
  token,
  onNavigateToConnections,
}: TradeExecutionModalProps) {
  const [selectedEnv, setSelectedEnv] = useState<"DEMO" | "REAL">("DEMO");
  const [orderSide, setOrderSide] = useState<"BUY" | "SELL">("BUY");
  const [volumeLots, setVolumeLots] = useState<number>(0.01);
  const [slValue, setSlValue] = useState<string>(stopLoss ? stopLoss.toString() : "");
  const [tpValue, setTpValue] = useState<string>(takeProfit ? takeProfit.toString() : "");
  const [realConsentChecked, setRealConsentChecked] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [executionResult, setExecutionResult] = useState<any>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Status & Accounts Data
  const [statusData, setStatusData] = useState<any>(null);
  const [selectedConnectionId, setSelectedConnectionId] = useState<string>("");

  useEffect(() => {
    if (!isOpen) return;

    const fetchStatus = async () => {
      try {
        const authToken = token || (typeof window !== "undefined" ? localStorage.getItem("tauric_token") || localStorage.getItem("bitdex_token") : null);
        const headers: Record<string, string> = { "Content-Type": "application/json" };
        if (authToken) headers["Authorization"] = `Bearer ${authToken}`;

        const res = await fetch("/api/v1/hft/exness/status", { headers });
        if (res.ok) {
          const d = await res.json();
          setStatusData(d);
        }
      } catch (err) {
        console.error("Failed to fetch connection status in modal:", err);
      }
    };

    fetchStatus();
  }, [isOpen, token]);

  // Available accounts based on environment
  const availableAccounts = selectedEnv === "DEMO"
    ? (statusData?.demo_connections || (statusData?.active_demo_connection ? [statusData.active_demo_connection] : []))
    : (statusData?.real_connections || (statusData?.active_real_connection ? [statusData.active_real_connection] : []));

  // Auto-select preferred or first account
  useEffect(() => {
    if (availableAccounts.length > 0) {
      const preferred = availableAccounts.find((a: any) => a.is_preferred);
      setSelectedConnectionId(preferred ? preferred.connection_id : availableAccounts[0].connection_id);
    } else {
      setSelectedConnectionId("");
    }
  }, [selectedEnv, statusData]);

  if (!isOpen) return null;

  const symClean = symbol.replace("/", "");
  const price = currentPrice || entryPrice || (symClean.includes("BTC") ? 78500 : symClean.includes("XAU") ? 2745 : 100);
  const slNum = parseFloat(slValue) || (price * 0.98);
  const tpNum = parseFloat(tpValue) || (price * 1.03);

  // Contract specs calculation
  const contractSize = symClean.includes("XAU") ? 100 : symClean.includes("EUR") ? 100000 : 1;
  const leverage = selectedEnv === "DEMO" ? 2000 : 200;
  const notionalUsd = volumeLots * contractSize * price;
  const requiredMargin = notionalUsd / leverage;
  const riskAmountUsd = Math.abs(price - slNum) * volumeLots * contractSize;
  const estRewardUsd = Math.abs(tpNum - price) * volumeLots * contractSize;

  const selectedAccount = availableAccounts.find((a: any) => a.connection_id === selectedConnectionId);
  const hasConnectedAccount = availableAccounts.length > 0;

  const handleExecute = async () => {
    if (!hasConnectedAccount) {
      setErrorMessage(`No connected Exness ${selectedEnv} account. Please connect your account first.`);
      return;
    }

    if (selectedEnv === "REAL" && !realConsentChecked) {
      setErrorMessage("Please check the mandatory real capital risk acknowledgement.");
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);
    setExecutionResult(null);

    try {
      const authToken = token || (typeof window !== "undefined" ? localStorage.getItem("tauric_token") || localStorage.getItem("bitdex_token") : null);
      const res = await fetch("/api/v1/hft/exness/trade/execute", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
        },
        body: JSON.stringify({
          environment: selectedEnv,
          connection_id: selectedConnectionId || undefined,
          symbol: symClean,
          side: orderSide,
          volume: volumeLots,
          price: price,
          stop_loss: slNum,
          take_profit: tpNum,
          consent_confirmed: selectedEnv === "REAL" ? realConsentChecked : false,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Trade execution failed");
      }
      setExecutionResult(data);
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to submit trade");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#080B10]/80 backdrop-blur-md animate-in fade-in duration-200">
      <div className="relative w-full max-w-2xl bg-[#0E131B] border border-[#1E2736] rounded-2xl shadow-2xl overflow-hidden font-mono text-xs flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="px-5 py-4 border-b border-[#1E2736] flex items-center justify-between bg-[#151C28]/60">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-[#38BDF8]/10 border border-[#38BDF8]/30 flex items-center justify-center">
              <Cpu className="w-4 h-4 text-[#38BDF8]" />
            </div>
            <div>
              <div className="text-sm font-bold text-[#F1F5F9] flex items-center gap-2">
                <span>Order Execution Terminal</span>
                <span className="text-[10px] px-2 py-0.5 rounded bg-[#1E2736] text-[#94A3B8]">
                  {symbol}
                </span>
              </div>
              <span className="text-[11px] text-[#64748B]">
                Customer-Owned Exness Execution Gateway &bull; Phase 4.1
              </span>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-[#64748B] hover:text-[#F1F5F9] hover:bg-[#1E2736] transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-5 space-y-4 overflow-y-auto flex-1">
          {/* Environment Selector Tabs */}
          <div className="grid grid-cols-2 p-1 rounded-xl bg-[#080B10] border border-[#1E2736]">
            <button
              type="button"
              onClick={() => {
                setSelectedEnv("DEMO");
                setExecutionResult(null);
                setErrorMessage(null);
              }}
              className={`py-2 rounded-lg font-bold text-xs flex items-center justify-center gap-2 transition-all ${
                selectedEnv === "DEMO"
                  ? "bg-[#151C28] text-[#38BDF8] border border-[#38BDF8]/40 shadow-sm"
                  : "text-[#64748B] hover:text-[#94A3B8]"
              }`}
            >
              <span>DEMO ACCOUNT</span>
              <span className="text-[9px] px-1.5 py-0.2 rounded bg-[#38BDF8]/10 text-[#38BDF8] border border-[#38BDF8]/20">
                SIMULATED
              </span>
            </button>

            <button
              type="button"
              onClick={() => {
                setSelectedEnv("REAL");
                setExecutionResult(null);
                setErrorMessage(null);
              }}
              className={`py-2 rounded-lg font-bold text-xs flex items-center justify-center gap-2 transition-all ${
                selectedEnv === "REAL"
                  ? "bg-[#F43F5E]/15 text-[#F43F5E] border border-[#F43F5E]/40 shadow-sm"
                  : "text-[#64748B] hover:text-[#94A3B8]"
              }`}
            >
              <AlertTriangle className="w-3.5 h-3.5 text-[#F43F5E]" />
              <span>REAL ACCOUNT</span>
              <span className="text-[9px] px-1.5 py-0.2 rounded bg-[#F43F5E]/15 text-[#F43F5E] border border-[#F43F5E]/30">
                LIVE CAPITAL
              </span>
            </button>
          </div>

          {/* Customer Account Selector Dropdown */}
          <div className="p-3.5 rounded-xl bg-[#151C28] border border-[#1E2736] space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[10px] uppercase text-[#64748B] flex items-center gap-1.5">
                <UserCheck className="w-3.5 h-3.5 text-[#38BDF8]" />
                <span>Selected Customer Account ({selectedEnv})</span>
              </span>
              <span className="text-[10px] text-[#64748B]">
                {availableAccounts.length} Connected Account(s)
              </span>
            </div>

            {hasConnectedAccount ? (
              <div className="relative">
                <select
                  value={selectedConnectionId}
                  onChange={(e) => setSelectedConnectionId(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-[#0E131B] border border-[#1E2736] text-[#F1F5F9] font-bold text-xs focus:outline-none focus:border-[#38BDF8] appearance-none cursor-pointer"
                >
                  {availableAccounts.map((a: any) => (
                    <option key={a.connection_id} value={a.connection_id}>
                      {a.account_label || a.account_login} &bull; Login: {a.account_login} &bull; {a.server_name}
                      {a.is_preferred ? " [Preferred]" : ""}
                    </option>
                  ))}
                </select>
                <ChevronDown className="w-4 h-4 text-[#64748B] absolute right-3 top-2.5 pointer-events-none" />
              </div>
            ) : (
              <div className="p-3 rounded-lg bg-[#EF4444]/10 border border-[#EF4444]/30 text-[#EF4444] space-y-1">
                <div className="flex items-center gap-1.5 font-bold">
                  <AlertTriangle className="w-4 h-4" />
                  <span>No Connected Exness {selectedEnv} Account</span>
                </div>
                <p className="text-[11px] text-[#94A3B8]">
                  Every BITDEX customer must connect their own independent Exness accounts. Admin credentials are never used as customer fallbacks.
                </p>
                <div className="pt-1">
                  <a
                    href="#connections"
                    onClick={() => {
                      onClose();
                      if (onNavigateToConnections) onNavigateToConnections();
                    }}
                    className="inline-flex items-center gap-1 text-[11px] font-bold text-[#38BDF8] hover:underline"
                  >
                    <span>Connect Account in Exchange Connections &rarr;</span>
                  </a>
                </div>
              </div>
            )}
          </div>

          {/* Real Money Risk Disclosure Banner (When REAL is active) */}
          {selectedEnv === "REAL" && (
            <div className="p-4 rounded-xl bg-[#F43F5E]/10 border border-[#F43F5E]/30 space-y-2 text-[#F43F5E]">
              <div className="flex items-center gap-2 font-bold text-xs">
                <ShieldAlert className="w-4 h-4 text-[#F43F5E]" />
                <span className="uppercase tracking-wider">Critical Real Money Risk Disclosure</span>
              </div>
              <p className="text-[11px] text-[#F1F5F9] leading-relaxed">
                You are preparing to place a trade on an Exness Real account using live financial capital. Positions are subject to market volatility, spread widening, slippage, and potential loss. Leveraged CFD trading involves significant risk of loss.
              </p>
              <div className="p-2.5 rounded-lg bg-[#080B10]/60 border border-[#F43F5E]/20 text-[10px] text-[#94A3B8] space-y-0.5">
                <div className="flex justify-between">
                  <span>Selected Real Account:</span>
                  <span className="font-bold text-[#F1F5F9]">{selectedAccount?.account_login || "UNAVAILABLE"} ({selectedAccount?.server_name || "Exness-Real"})</span>
                </div>
                <div className="flex justify-between">
                  <span>Institutional Risk Clamp:</span>
                  <span className="font-bold text-[#F59E0B]">1:200 Maximum Leverage Enforced</span>
                </div>
                <div className="flex justify-between">
                  <span>Execution Safeguard:</span>
                  <span className="font-bold text-[#38BDF8]">live_trading_locked=True (Staging Fail-Closed)</span>
                </div>
              </div>
            </div>
          )}

          {/* Trade Parameters Form */}
          <div className="grid grid-cols-2 gap-3">
            {/* Direction */}
            <div className="space-y-1">
              <label className="text-[10px] uppercase text-[#64748B] block">Order Side</label>
              <div className="grid grid-cols-2 gap-1.5">
                <button
                  type="button"
                  onClick={() => setOrderSide("BUY")}
                  className={`py-2 rounded-lg font-bold transition-all ${
                    orderSide === "BUY"
                      ? "bg-[#10B981] text-[#080B10]"
                      : "bg-[#151C28] text-[#94A3B8] hover:text-[#F1F5F9] border border-[#1E2736]"
                  }`}
                >
                  BUY / LONG
                </button>
                <button
                  type="button"
                  onClick={() => setOrderSide("SELL")}
                  className={`py-2 rounded-lg font-bold transition-all ${
                    orderSide === "SELL"
                      ? "bg-[#EF4444] text-[#080B10]"
                      : "bg-[#151C28] text-[#94A3B8] hover:text-[#F1F5F9] border border-[#1E2736]"
                  }`}
                >
                  SELL / SHORT
                </button>
              </div>
            </div>

            {/* Volume */}
            <div className="space-y-1">
              <label className="text-[10px] uppercase text-[#64748B] block">Volume (Lots)</label>
              <input
                type="number"
                step="0.01"
                min="0.01"
                max="10.0"
                value={volumeLots}
                onChange={(e) => setVolumeLots(parseFloat(e.target.value) || 0.01)}
                className="w-full px-3 py-2 rounded-lg bg-[#151C28] border border-[#1E2736] text-[#F1F5F9] font-bold focus:outline-none focus:border-[#38BDF8]"
              />
            </div>
          </div>

          {/* SL & TP Inputs */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-[10px] uppercase text-[#64748B] block">Stop Loss Price</label>
              <input
                type="number"
                step="0.01"
                value={slValue}
                onChange={(e) => setSlValue(e.target.value)}
                placeholder={slNum.toFixed(2)}
                className="w-full px-3 py-2 rounded-lg bg-[#151C28] border border-[#1E2736] text-[#EF4444] font-bold focus:outline-none focus:border-[#EF4444]"
              />
            </div>

            <div className="space-y-1">
              <label className="text-[10px] uppercase text-[#64748B] block">Take Profit Price</label>
              <input
                type="number"
                step="0.01"
                value={tpValue}
                onChange={(e) => setTpValue(e.target.value)}
                placeholder={tpNum.toFixed(2)}
                className="w-full px-3 py-2 rounded-lg bg-[#151C28] border border-[#1E2736] text-[#10B981] font-bold focus:outline-none focus:border-[#10B981]"
              />
            </div>
          </div>

          {/* Quantitative Risk Summary Matrix */}
          <div className="p-3.5 rounded-xl bg-[#151C28] border border-[#1E2736] space-y-2 text-[11px]">
            <span className="text-[10px] text-[#64748B] uppercase block">
              Quantitative Risk &amp; Margin Matrix
            </span>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <div className="p-2 rounded-lg bg-[#0E131B] border border-[#1E2736]">
                <span className="text-[10px] text-[#64748B] block">Notional Exposure</span>
                <span className="font-bold text-[#F1F5F9] tabular-nums">${notionalUsd.toFixed(2)}</span>
              </div>
              <div className="p-2 rounded-lg bg-[#0E131B] border border-[#1E2736]">
                <span className="text-[10px] text-[#64748B] block">Required Margin</span>
                <span className="font-bold text-[#38BDF8] tabular-nums">${requiredMargin.toFixed(2)}</span>
              </div>
              <div className="p-2 rounded-lg bg-[#0E131B] border border-[#1E2736]">
                <span className="text-[10px] text-[#64748B] block">Max Risk (SL)</span>
                <span className="font-bold text-[#EF4444] tabular-nums">-${riskAmountUsd.toFixed(2)}</span>
              </div>
              <div className="p-2 rounded-lg bg-[#0E131B] border border-[#1E2736]">
                <span className="text-[10px] text-[#64748B] block">Target Profit (TP)</span>
                <span className="font-bold text-[#10B981] tabular-nums">+${estRewardUsd.toFixed(2)}</span>
              </div>
            </div>
          </div>

          {/* Mandatory Unchecked Consent Checkbox (REAL only) */}
          {selectedEnv === "REAL" && (
            <div className="p-3.5 rounded-xl bg-[#080B10] border border-[#F43F5E]/30 flex items-start gap-3">
              <input
                type="checkbox"
                id="realConsent"
                checked={realConsentChecked}
                onChange={(e) => setRealConsentChecked(e.target.checked)}
                className="mt-0.5 w-4 h-4 rounded border-[#F43F5E] bg-[#151C28] text-[#F43F5E] focus:ring-0 cursor-pointer"
              />
              <label htmlFor="realConsent" className="text-xs text-[#F1F5F9] leading-relaxed cursor-pointer select-none">
                <span className="font-bold text-[#F43F5E] block uppercase">Mandatory Customer Real-Money Consent</span>
                I confirm that I am executing on my personal Exness Real account (<strong>{selectedAccount?.account_login || "UNAVAILABLE"}</strong>) with live capital. I acknowledge all quantitative financial risks and understand execution is irreversible.
              </label>
            </div>
          )}

          {/* Error Message */}
          {errorMessage && (
            <div className="p-3 rounded-lg bg-[#EF4444]/10 border border-[#EF4444]/30 text-[#EF4444] text-xs flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>{errorMessage}</span>
            </div>
          )}

          {/* Execution Result Feedback */}
          {executionResult && (
            <div
              className={`p-4 rounded-xl border text-xs space-y-2 ${
                executionResult.status === "BLOCKED_BY_SAFETY_LOCK"
                  ? "bg-[#F59E0B]/10 border-[#F59E0B]/30 text-[#F59E0B]"
                  : "bg-[#10B981]/10 border-[#10B981]/30 text-[#10B981]"
              }`}
            >
              <div className="flex items-center gap-2 font-bold">
                {executionResult.status === "BLOCKED_BY_SAFETY_LOCK" ? (
                  <Lock className="w-4 h-4" />
                ) : (
                  <CheckCircle2 className="w-4 h-4" />
                )}
                <span>
                  {executionResult.status === "BLOCKED_BY_SAFETY_LOCK"
                    ? "ORDER BLOCKED BY SAFETY LOCK (STAGING PROTECTED)"
                    : "DEMO SIMULATION ORDER FILLED"}
                </span>
              </div>
              <p className="text-[11px] text-[#F1F5F9]">{executionResult.message}</p>
              <div className="p-2 rounded bg-[#080B10]/60 border border-[#1E2736] text-[10px] text-[#94A3B8] space-y-0.5">
                <div>Account: <strong className="text-[#F1F5F9]">{executionResult.account_id}</strong> &bull; Server: <strong className="text-[#F1F5F9]">{executionResult.server}</strong></div>
                {executionResult.ticket && <div>Ticket: <strong className="text-[#38BDF8]">{executionResult.ticket}</strong></div>}
                <div>Symbol: {executionResult.symbol} &bull; Side: {executionResult.side} &bull; Lots: {executionResult.volume}</div>
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer Actions */}
        <div className="px-5 py-4 border-t border-[#1E2736] bg-[#151C28]/60 flex items-center justify-between">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-xl bg-[#151C28] hover:bg-[#1E2736] text-[#94A3B8] transition-colors"
          >
            Close Terminal
          </button>

          <button
            type="button"
            onClick={handleExecute}
            disabled={
              isSubmitting ||
              !hasConnectedAccount ||
              (selectedEnv === "REAL" && !realConsentChecked)
            }
            className={`px-6 py-2.5 rounded-xl font-bold flex items-center gap-2 transition-all cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed ${
              selectedEnv === "REAL"
                ? "bg-[#F43F5E] hover:bg-[#F43F5E]/90 text-white"
                : "bg-[#38BDF8] hover:bg-[#38BDF8]/90 text-[#080B10]"
            }`}
          >
            {isSubmitting ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : selectedEnv === "REAL" ? (
              <Lock className="w-4 h-4" />
            ) : (
              <CheckCircle2 className="w-4 h-4" />
            )}
            <span>
              {selectedEnv === "REAL" ? "EXECUTE LIVE ORDER" : "SUBMIT DEMO ORDER"}
            </span>
          </button>
        </div>
      </div>
    </div>
  );
}
