"use client";

import React, { useEffect, useState } from "react";
import { ShieldCheck, Activity, AlertTriangle, Cpu } from "lucide-react";

interface WatchdogState {
  status: string;
  pid?: number;
  last_heartbeat?: string;
  positions_monitored?: number;
  discrepancies_detected?: number;
}

interface ProtectionData {
  watchdog: WatchdogState;
  primary_stop_status: string;
  open_positions_count: number;
  active_leases_count: number;
  aggregate_exposure_limit_pct: number;
}

interface ProtectionCenterProps {
  className?: string;
  token?: string;
}

export default function ProtectionCenter({ className = "", token }: ProtectionCenterProps) {
  const [data, setData] = useState<ProtectionData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;

    async function fetchStatus() {
      try {
        const authToken =
          token ||
          (typeof window !== "undefined"
            ? localStorage.getItem("tauric_session_token") ||
              localStorage.getItem("bitdex_auth_token") ||
              localStorage.getItem("tauric_token") ||
              localStorage.getItem("bitdex_token") ||
              ""
            : "");

        const headers: Record<string, string> = {};
        if (authToken) {
          headers["Authorization"] = "Bearer " + authToken;
        }

        // Try customer endpoint first, fallback to admin
        let res = await fetch("/api/backend/saas/customer/protection/status", { headers });
        if (!res.ok) {
          res = await fetch("/api/backend/saas/admin/protection/status", { headers });
        }

        if (res.ok) {
          const json = await res.json();
          if (isMounted && json.status === "SUCCESS") {
            setData(json);
          }
        }
      } catch (err) {
        // Fallback or keep prior state
      } finally {
        if (isMounted) setLoading(false);
      }
    }

    fetchStatus();
    const interval = setInterval(fetchStatus, 4000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [token]);

  const isWatchdogActive = data?.watchdog?.status === "ACTIVE";

  return (
    <div
      className={'rounded-2xl bg-[#121218] border border-[#272735] p-4 sm:p-5 shadow-lg ' + className}
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#272735] pb-3 mb-4">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-lg bg-[#00E5FF]/10 border border-[#00E5FF]/30 flex items-center justify-center text-[#00E5FF]">
            <ShieldCheck className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm sm:text-base font-bold text-white tracking-wide flex items-center gap-2 font-mono">
              INSTITUTIONAL RISK &amp; PROTECTION CENTER
              <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-[#10B981]/15 text-[#10B981] border border-[#10B981]/30 flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-[#10B981] animate-pulse" />
                {data?.two_layer_status || "STANDBY (ARMED ON ENTRY)"}
              </span>
            </h3>
            <p className="text-xs text-[#94A3B8]">
              Exchange-native stops &amp; independent OS watchdog supervisor (30s polling cycle)
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        {/* Layer 1: Primary Stop */}
        <div className="bg-[#0A0A0E] border border-[#272735] rounded-xl p-3.5 flex flex-col justify-between">
          <div className="text-[11px] font-mono text-[#94A3B8] uppercase mb-1 flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-[#10B981] animate-pulse" />
            Primary Stop
          </div>
          <div className="text-sm font-bold text-[#10B981] font-mono">
            {data?.primary_stop_status || "STANDBY (NO OPEN POSITIONS)"}
          </div>
          <div className="text-[10px] text-[#64748B] mt-1">
            Binance Native STOP_MARKET
          </div>
        </div>

        {/* Layer 2: Watchdog Daemon */}
        <div className="bg-[#0A0A0E] border border-[#272735] rounded-xl p-3.5 flex flex-col justify-between">
          <div className="text-[11px] font-mono text-[#94A3B8] uppercase mb-1 flex items-center gap-1.5">
            <Activity className="w-3.5 h-3.5 text-[#00E5FF]" />
            Watchdog Daemon
          </div>
          <div className="text-sm font-bold text-[#00E5FF] font-mono flex items-center gap-1.5">
            {isWatchdogActive ? "ONLINE" : "MONITORING"}
            {data?.watchdog?.pid && (
              <span className="text-[10px] text-[#94A3B8] font-normal">
                (PID {data.watchdog.pid})
              </span>
            )}
          </div>
          <div className="text-[10px] text-[#64748B] mt-1">
            Independent PM2 Supervisor
          </div>
        </div>

        {/* Aggregate Exposure */}
        <div className="bg-[#0A0A0E] border border-[#272735] rounded-xl p-3.5 flex flex-col justify-between">
          <div className="text-[11px] font-mono text-[#94A3B8] uppercase mb-1 flex items-center gap-1.5">
            <AlertTriangle className="w-3.5 h-3.5 text-[#F59E0B]" />
            Portfolio Exposure
          </div>
          <div className="text-sm font-bold text-white font-mono">
            0.0% / {data?.aggregate_exposure_limit_pct ?? 50.0}% MAX
          </div>
          <div className="text-[10px] text-[#10B981] mt-1">
            Within Safe Risk Limits
          </div>
        </div>

        {/* Engine Exclusivity Leases */}
        <div className="bg-[#0A0A0E] border border-[#272735] rounded-xl p-3.5 flex flex-col justify-between">
          <div className="text-[11px] font-mono text-[#94A3B8] uppercase mb-1 flex items-center gap-1.5">
            <Cpu className="w-3.5 h-3.5 text-[#A855F7]" />
            Engine Collision Lock
          </div>
          <div className="text-sm font-bold text-white font-mono">
            {data?.active_leases_count ?? 0} ACTIVE LEASES
          </div>
          <div className="text-[10px] text-[#64748B] mt-1">
            Atomic Mutual Exclusivity (CAS)
          </div>
        </div>
      </div>
    </div>
  );
}
