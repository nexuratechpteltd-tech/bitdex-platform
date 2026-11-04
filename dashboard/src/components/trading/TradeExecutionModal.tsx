"use client";

import React, { useState } from "react";
import {
  X,
  ShieldAlert,
  AlertTriangle,
  Lock,
  CheckCircle2,
  TrendingUp,
  TrendingDown,
  Info,
  DollarSign,
  Percent,
  Cpu,
  Loader2,
  ExternalLink,
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
  const estimatedSpreadFrictionUsd = (price * 0.0002) * volumeLots * contractSize;

  const handleExecute = async () => {
    if (selectedEnv === "REAL" && !realConsentChecked) {
      setErrorMessage("Please check the mandatory real capital risk acknowledgement.");
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);
    setExecutionResult(null);

    try {
      const res = await fetch("/api/v1/hft/exness/trade/execute", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          environment: selectedEnv,
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
                Dual Exness Gateway: Demo Simulation & Real Execution
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

          {/* REAL ACCOUNT Warning Banner */}
          {selectedEnv === "REAL" && (
            <div className="p-3.5 rounded-xl bg-[#F43F5E]/10 border border-[#F43F5E]/30 space-y-1.5 animate-in fade-in duration-150">
              <div className="flex items-center gap-2 text-[#F43F5E] font-bold text-xs">
                <ShieldAlert className="w-4 h-4 shrink-0" />
                <span>CRITICAL: REAL MONEY EXECUTION DISCLOSURE</span>
              </div>
              <p className="text-[11px] text-[#FDA4AF] leading-relaxed">
                You are preparing to submit an order to an authenticated <strong>Exness Real Account</strong>.
                Real capital will be committed to the broker order book. All losses are final and capital is exposed to live market volatility, slippage, and spread friction.
              </p>
              <div className="text-[10px] text-[#94A3B8] pt-1 border-t border-[#F43F5E]/20 flex justify-between">
                <span>Account: Exness-Real (1:200 Leverage)</span>
                <span className="text-[#F59E0B] font-bold">Safety Override Active</span>
              </div>
            </div>
          )}

          {/* Order Configuration Form */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Left Column: Order Parameters */}
            <div className="space-y-3">
              <div>
                <label className="text-[10px] text-[#64748B] uppercase block mb-1.5">
                  Order Direction
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setOrderSide("BUY")}
                    className={`py-2 rounded-lg font-bold flex items-center justify-center gap-1.5 border transition-all ${
                      orderSide === "BUY"
                        ? "bg-[#10B981]/20 border-[#10B981] text-[#10B981]"
                        : "bg-[#151C28] border-[#1E2736] text-[#64748B] hover:text-[#94A3B8]"
                    }`}
                  >
                    <TrendingUp className="w-3.5 h-3.5" />
                    <span>BUY / LONG</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setOrderSide("SELL")}
                    className={`py-2 rounded-lg font-bold flex items-center justify-center gap-1.5 border transition-all ${
                      orderSide === "SELL"
                        ? "bg-[#F43F5E]/20 border-[#F43F5E] text-[#F43F5E]"
                        : "bg-[#151C28] border-[#1E2736] text-[#64748B] hover:text-[#94A3B8]"
                    }`}
                  >
                    <TrendingDown className="w-3.5 h-3.5" />
                    <span>SELL / SHORT</span>
                  </button>
                </div>
              </div>

              <div>
                <div className="flex justify-between items-center mb-1.5">
                  <label className="text-[10px] text-[#64748B] uppercase">Volume (Lots)</label>
                  <span className="text-[10px] text-[#94A3B8]">Min: 0.01 / Max: 10.0</span>
                </div>
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  max="10.0"
                  value={volumeLots}
                  onChange={(e) => setVolumeLots(Math.max(0.01, parseFloat(e.target.value) || 0.01))}
                  className="w-full px-3 py-2 bg-[#080B10] border border-[#1E2736] rounded-lg text-[#F1F5F9] focus:outline-none focus:border-[#38BDF8]"
                />
                <div className="grid grid-cols-4 gap-1.5 mt-1.5">
                  {[0.01, 0.05, 0.10, 0.50].map((v) => (
                    <button
                      key={v}
                      type="button"
                      onClick={() => setVolumeLots(v)}
                      className={`py-1 text-[10px] rounded border ${
                        volumeLots === v
                          ? "bg-[#38BDF8]/20 border-[#38BDF8] text-[#38BDF8]"
                          : "bg-[#151C28] border-[#1E2736] text-[#94A3B8] hover:text-[#F1F5F9]"
                      }`}
                    >
                      {v.toFixed(2)}
                    </button>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-[10px] text-[#64748B] uppercase block mb-1">
                    Stop Loss ($)
                  </label>
                  <input
                    type="number"
                    step="any"
                    value={slValue}
                    onChange={(e) => setSlValue(e.target.value)}
                    placeholder={slNum.toFixed(2)}
                    className="w-full px-2.5 py-1.5 bg-[#080B10] border border-[#1E2736] rounded-lg text-[#F43F5E] focus:outline-none focus:border-[#F43F5E]"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-[#64748B] uppercase block mb-1">
                    Take Profit ($)
                  </label>
                  <input
                    type="number"
                    step="any"
                    value={tpValue}
                    onChange={(e) => setTpValue(e.target.value)}
                    placeholder={tpNum.toFixed(2)}
                    className="w-full px-2.5 py-1.5 bg-[#080B10] border border-[#1E2736] rounded-lg text-[#10B981] focus:outline-none focus:border-[#10B981]"
                  />
                </div>
              </div>
            </div>

            {/* Right Column: Financial Exposure & Risk Matrix */}
            <div className="p-3.5 rounded-xl bg-[#080B10] border border-[#1E2736] space-y-2.5">
              <div className="flex items-center justify-between border-b border-[#1E2736] pb-2">
                <span className="font-bold text-[#F1F5F9]">Quantitative Matrix</span>
                <span className="text-[10px] text-[#38BDF8]">Mark-to-Market</span>
              </div>

              <div className="space-y-1.5 text-[11px]">
                <div className="flex justify-between">
                  <span className="text-[#64748B]">Reference Price:</span>
                  <span className="font-bold text-[#F1F5F9] tabular-nums">${price.toFixed(2)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[#64748B]">Notional Value:</span>
                  <span className="font-bold text-[#F1F5F9] tabular-nums">${notionalUsd.toFixed(2)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[#64748B]">Required Margin ({leverage}:1):</span>
                  <span className="font-bold text-[#38BDF8] tabular-nums">${requiredMargin.toFixed(2)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[#64748B]">Max Dollar Risk (SL):</span>
                  <span className="font-bold text-[#F43F5E] tabular-nums">-${riskAmountUsd.toFixed(2)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[#64748B]">Expected Reward (TP):</span>
                  <span className="font-bold text-[#10B981] tabular-nums">+${estRewardUsd.toFixed(2)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[#64748B]">Spread / Friction Buffer:</span>
                  <span className="font-bold text-[#94A3B8] tabular-nums">${estimatedSpreadFrictionUsd.toFixed(2)}</span>
                </div>
                <div className="flex justify-between pt-1 border-t border-[#1E2736]">
                  <span className="text-[#64748B]">Risk / Reward Ratio:</span>
                  <span className="font-bold text-[#F1F5F9]">
                    1 : {riskAmountUsd > 0 ? (estRewardUsd / riskAmountUsd).toFixed(2) : "N/A"}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* REAL ACCOUNT Mandatory Consent Checkbox */}
          {selectedEnv === "REAL" && (
            <div className="p-3 rounded-xl bg-[#151C28] border border-[#F43F5E]/30 space-y-2">
              <label className="flex items-start gap-2.5 cursor-pointer">
                <input
                  type="checkbox"
                  checked={realConsentChecked}
                  onChange={(e) => setRealConsentChecked(e.target.checked)}
                  className="mt-0.5 rounded border-[#1E2736] text-[#F43F5E] focus:ring-0 focus:outline-none"
                />
                <span className="text-[11px] text-[#E2E8F0] leading-snug">
                  I acknowledge that this order risks <strong>real capital</strong> on an Exness Real account.
                  I accept full financial responsibility and understand market execution risks, slippage, and spread friction.
                </span>
              </label>
            </div>
          )}

          {/* Feedback & Result Message */}
          {errorMessage && (
            <div className="p-3 rounded-lg bg-[#F43F5E]/10 border border-[#F43F5E]/30 text-[#F43F5E] text-xs flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>{errorMessage}</span>
            </div>
          )}

          {executionResult && (
            <div className={`p-3 rounded-xl border text-xs space-y-2 ${
              executionResult.status === "FILLED"
                ? "bg-[#10B981]/10 border-[#10B981]/30 text-[#10B981]"
                : "bg-[#F59E0B]/10 border-[#F59E0B]/30 text-[#F59E0B]"
            }`}>
              <div className="flex items-center justify-between font-bold">
                <span className="flex items-center gap-1.5">
                  {executionResult.status === "FILLED" ? (
                    <CheckCircle2 className="w-4 h-4 text-[#10B981]" />
                  ) : (
                    <Lock className="w-4 h-4 text-[#F59E0B]" />
                  )}
                  <span>
                    {executionResult.status === "FILLED"
                      ? "DEMO ORDER FILLED"
                      : "EXECUTION LOCKED BY INSTITUTIONAL SAFETY BARRIER"}
                  </span>
                </span>
                <span className="text-[10px] text-[#94A3B8]">
                  {executionResult.executed_at || executionResult.timestamp}
                </span>
              </div>
              <p className="text-[11px] text-[#F1F5F9]/90">
                {executionResult.message}
              </p>
              {executionResult.ticket && (
                <div className="text-[10px] text-[#94A3B8] flex justify-between pt-1 border-t border-[#1E2736]">
                  <span>Ticket: {executionResult.ticket}</span>
                  <span>Fill: ${executionResult.fill_price}</span>
                  <span>Spread Deducted: {executionResult.spread_points} pts</span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="px-5 py-3.5 border-t border-[#1E2736] bg-[#151C28]/60 flex items-center justify-between">
          <div className="text-[11px] text-[#64748B]">
            {selectedEnv === "DEMO" ? (
              <span className="text-[#38BDF8]">● Demo Simulated Execution</span>
            ) : (
              <span className="text-[#F43F5E]">▲ Live Real Account Selected</span>
            )}
          </div>
          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-lg bg-[#151C28] hover:bg-[#1E2736] text-[#94A3B8] hover:text-[#F1F5F9] font-bold transition-all"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleExecute}
              disabled={isSubmitting || (selectedEnv === "REAL" && !realConsentChecked)}
              className={`px-5 py-2 rounded-lg font-bold flex items-center gap-2 transition-all ${
                selectedEnv === "REAL"
                  ? realConsentChecked
                    ? "bg-[#F43F5E] hover:bg-[#E11D48] text-white shadow-lg shadow-[#F43F5E]/20 cursor-pointer"
                    : "bg-[#1E2736] text-[#64748B] cursor-not-allowed border border-[#1E2736]"
                  : "bg-[#38BDF8] hover:bg-[#0284C7] text-[#080B10] shadow-lg shadow-[#38BDF8]/20 cursor-pointer"
              }`}
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Submitting Order...</span>
                </>
              ) : selectedEnv === "REAL" ? (
                <>
                  <AlertTriangle className="w-3.5 h-3.5" />
                  <span>CONFIRM LIVE TRADE</span>
                </>
              ) : (
                <>
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  <span>CONFIRM DEMO ORDER</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
