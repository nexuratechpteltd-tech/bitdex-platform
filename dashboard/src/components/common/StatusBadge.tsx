"use client";

import React from "react";
import {
  Clock,
  ArrowUp,
  ArrowDown,
  ShieldCheck,
  AlertTriangle,
  Lock,
  Activity,
  CheckCircle2,
  XCircle,
} from "lucide-react";

export type HftState =
  | "ANALYSING"
  | "WAITING"
  | "BUY_OPPORTUNITY"
  | "SELL_OPPORTUNITY"
  | "POSITION_OPEN"
  | "PROFIT_SECURED"
  | "RISK_WARNING"
  | "EMERGENCY_LOCK";

export interface StatusBadgeProps {
  type: "HFT" | "SIGNAL" | "AVAILABILITY" | "ENVIRONMENT";
  state?: HftState | string;
  label?: string;
  className?: string;
}

export default function StatusBadge({ type, state, label, className = "" }: StatusBadgeProps) {
  if (type === "HFT") {
    switch (state) {
      case "ANALYSING":
        return (
          <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-mono font-bold bg-[#38BDF8]/10 text-[#38BDF8] border border-[#38BDF8]/30 ${className}`}>
            <span className="w-1.5 h-1.5 rounded-full bg-[#38BDF8] animate-pulse" />
            <span>ANALYSING MARKET</span>
          </span>
        );
      case "WAITING":
        return (
          <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-mono font-bold bg-[#1E2736] text-[#94A3B8] border border-[#1E2736] ${className}`}>
            <Clock className="w-3 h-3 text-[#94A3B8]" />
            <span>WAITING FOR OPPORTUNITY</span>
          </span>
        );
      case "BUY_OPPORTUNITY":
        return (
          <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-mono font-bold bg-[#10B981]/15 text-[#10B981] border border-[#10B981]/30 ${className}`}>
            <ArrowUp className="w-3 h-3" />
            <span>BUY OPPORTUNITY</span>
          </span>
        );
      case "SELL_OPPORTUNITY":
        return (
          <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-mono font-bold bg-[#F43F5E]/15 text-[#F43F5E] border border-[#F43F5E]/30 ${className}`}>
            <ArrowDown className="w-3 h-3" />
            <span>SELL OPPORTUNITY</span>
          </span>
        );
      case "POSITION_OPEN":
        return (
          <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-mono font-bold bg-[#06B6D4]/15 text-[#06B6D4] border border-[#06B6D4]/30 ${className}`}>
            <span className="w-1.5 h-1.5 rounded-full bg-[#06B6D4] animate-ping" />
            <span>POSITION OPEN</span>
          </span>
        );
      case "PROFIT_SECURED":
        return (
          <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-mono font-bold bg-[#10B981]/20 text-[#10B981] border border-[#10B981] ${className}`}>
            <ShieldCheck className="w-3 h-3" />
            <span>PROFIT SECURED</span>
          </span>
        );
      case "RISK_WARNING":
        return (
          <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-mono font-bold bg-[#F59E0B]/15 text-[#F59E0B] border border-[#F59E0B]/30 ${className}`}>
            <AlertTriangle className="w-3 h-3" />
            <span>RISK WARNING</span>
          </span>
        );
      case "EMERGENCY_LOCK":
      default:
        return (
          <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-mono font-bold bg-[#EF4444]/20 text-[#EF4444] border border-[#EF4444]/40 ${className}`}>
            <Lock className="w-3 h-3" />
            <span>EMERGENCY LOCK</span>
          </span>
        );
    }
  }

  if (type === "SIGNAL") {
    const s = (state || label || "").toUpperCase();
    if (s.includes("BUY")) {
      return (
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-[#10B981]/15 text-[#10B981] border border-[#10B981]/30 ${className}`}>
          <span>▲</span>
          <span>{label || "BUY"}</span>
        </span>
      );
    }
    if (s.includes("SELL")) {
      return (
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-[#F43F5E]/15 text-[#F43F5E] border border-[#F43F5E]/30 ${className}`}>
          <span>▼</span>
          <span>{label || "SELL"}</span>
        </span>
      );
    }
    return (
      <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-[#1E2736] text-[#94A3B8] border border-[#1E2736] ${className}`}>
        {label || state || "NEUTRAL"}
      </span>
    );
  }

  if (type === "AVAILABILITY") {
    if (!state || state === "UNAVAILABLE" || state === "null" || state === "undefined") {
      return (
        <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-[#151C28] text-[#64748B] border border-[#1E2736] ${className}`}>
          Unavailable
        </span>
      );
    }
    return (
      <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono font-semibold text-[#F1F5F9] ${className}`}>
        {state}
      </span>
    );
  }

  if (type === "ENVIRONMENT") {
    const isLive = state === "LIVE";
    return (
      <span
        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-bold border ${
          isLive
            ? "bg-[#10B981]/15 text-[#10B981] border-[#10B981]/30"
            : "bg-[#F59E0B]/15 text-[#F59E0B] border-[#F59E0B]/30"
        } ${className}`}
      >
        <span className={`w-1.5 h-1.5 rounded-full ${isLive ? "bg-[#10B981]" : "bg-[#F59E0B]"}`} />
        <span>{isLive ? "REAL BROKER" : "SIMULATED / DEMO"}</span>
      </span>
    );
  }

  return null;
}
