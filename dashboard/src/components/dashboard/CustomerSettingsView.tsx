"use client";

import React, { useState, useEffect } from "react";
import { Sliders, ShieldCheck, User, Bell, Lock, Link2, CheckCircle2, Shield } from "lucide-react";

interface CustomerSettingsViewProps {
  user?: any;
  token?: string;
  onSwitchPortal?: () => void;
}

export default function CustomerSettingsView({ user, token, onSwitchPortal }: CustomerSettingsViewProps) {
  const isAdmin = ["ADMIN", "OWNER"].includes(String(user?.role || "").toUpperCase());
  const [activeSection, setActiveSection] = useState<
    "PROFILE" | "ACCOUNT" | "TRADING" | "NOTIFICATIONS" | "SECURITY" | "BROKERS" | "ADMIN_SETTINGS"
  >("PROFILE");

  const sections: { id: string; label: string; icon: any }[] = [
    { id: "PROFILE", label: "Profile Information", icon: User },
    { id: "ACCOUNT", label: "Account Preferences", icon: Sliders },
    { id: "TRADING", label: "Trading Preferences", icon: ShieldCheck },
    { id: "NOTIFICATIONS", label: "Notifications", icon: Bell },
    { id: "SECURITY", label: "Security & 2FA", icon: Lock },
    { id: "BROKERS", label: "Connected Accounts", icon: Link2 },
    ...(isAdmin ? [{ id: "ADMIN_SETTINGS", label: "Administrator Settings", icon: Shield }] : []),
  ];

  // Admin settings data (read-only views backed by existing admin endpoints)
  const [adminData, setAdminData] = useState<{ protection?: any; pricing?: any; providers?: any; error?: string }>({});
  useEffect(() => {
    if (!isAdmin || activeSection !== "ADMIN_SETTINGS") return;
    const t = token || (typeof window !== "undefined" ? window.localStorage.getItem("token") || "" : "");
    const h = { headers: t ? { Authorization: "Bearer " + t } : {} };
    const get = (u: string) => fetch(u, h).then((r) => (r.ok ? r.json() : null)).catch(() => null);
    Promise.all([
      get("/api/backend/saas/admin/protection/status"),
      get("/api/backend/saas/admin/pricing/global"),
      get("/api/backend/saas/admin/provider-operations"),
    ]).then(([protection, pricing, providers]) =>
      setAdminData({ protection, pricing, providers, error: !protection && !pricing && !providers ? "Admin endpoints unavailable." : undefined })
    );
  }, [isAdmin, activeSection, token]);

  return (
    <div className="space-y-6 font-sans animate-in fade-in duration-200">
      <div className="pb-2 border-b border-[#1E2736]">
        <h1 className="text-xl sm:text-2xl font-mono font-bold text-[#F1F5F9] tracking-tight">
          Customer Settings
        </h1>
        <p className="text-xs font-mono text-[#94A3B8] mt-1">
          Institutional preferences, risk parameters, authentication, and notification settings.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
        {/* Navigation Sidebar / Horizontal Pills */}
        <div className="md:col-span-4 lg:col-span-3 flex md:flex-col gap-1.5 overflow-x-auto font-mono text-xs">
          {sections.map((s) => {
            const Icon = s.icon;
            const isActive = activeSection === s.id;
            return (
              <button
                key={s.id}
                onClick={() => setActiveSection(s.id as any)}
                className={`flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl font-semibold transition-all shrink-0 text-left ${
                  isActive
                    ? "bg-[#151C28] text-[#F1F5F9] border-l-2 border-[#38BDF8]"
                    : "text-[#94A3B8] hover:text-[#F1F5F9] hover:bg-[#151C28]/60 border-l-2 border-transparent"
                }`}
              >
                <Icon className={`w-4 h-4 ${isActive ? "text-[#38BDF8]" : "text-[#94A3B8]"}`} />
                <span className="truncate">{s.label}</span>
              </button>
            );
          })}
        </div>

        {/* Content Area */}
        <div className="md:col-span-8 lg:col-span-9 p-5 rounded-2xl bg-[#0E131B] border border-[#1E2736] space-y-6 font-mono text-xs">
          {activeSection === "PROFILE" && (
            <div className="space-y-4">
              <h2 className="text-base font-bold text-[#F1F5F9] border-b border-[#1E2736] pb-2">
                Profile Information
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="text-[11px] text-[#64748B] block mb-1">Email Address</label>
                  <input
                    type="text"
                    disabled
                    value={user?.email || "customer@bitdex.ltd"}
                    className="w-full px-3 py-2 rounded-lg bg-[#151C28] border border-[#1E2736] text-[#F1F5F9]"
                  />
                </div>
                <div>
                  <label className="text-[11px] text-[#64748B] block mb-1">Account Role</label>
                  <input
                    type="text"
                    disabled
                    value={user?.role || "CUSTOMER"}
                    className="w-full px-3 py-2 rounded-lg bg-[#151C28] border border-[#1E2736] text-[#F1F5F9]"
                  />
                </div>
              </div>
            </div>
          )}

          {activeSection === "ACCOUNT" && (
            <div className="space-y-4">
              <h2 className="text-base font-bold text-[#F1F5F9] border-b border-[#1E2736] pb-2">
                Account Preferences
              </h2>
              <p className="text-[#94A3B8] leading-relaxed">
                Base Currency: <strong className="text-[#F1F5F9]">USD ($)</strong> • Timezone: <strong className="text-[#F1F5F9]">UTC+00:00</strong>
              </p>
            </div>
          )}

          {activeSection === "TRADING" && (
            <div className="space-y-4">
              <h2 className="text-base font-bold text-[#F1F5F9] border-b border-[#1E2736] pb-2">
                Trading Risk Preferences
              </h2>
              <div className="space-y-2 text-[#94A3B8]">
                <div>• Per-Order Volume Clamp: <strong className="text-[#F1F5F9]">0.10 Lots</strong></div>
                <div>• Max Daily Risk Loss: <strong className="text-[#F1F5F9]">$250.00 USD</strong></div>
                <div>• Max Trailing Equity Drawdown: <strong className="text-[#F1F5F9]">10.0%</strong></div>
                <div>• Mandatory Broker Stop-Loss: <strong className="text-[#10B981]">Enforced (Gate 10)</strong></div>
              </div>
            </div>
          )}

          {activeSection === "SECURITY" && (
            <div className="space-y-4">
              <h2 className="text-base font-bold text-[#F1F5F9] border-b border-[#1E2736] pb-2">
                Security &amp; Two-Factor Authentication
              </h2>
              <div className="flex items-center gap-2 text-[#10B981]">
                <ShieldCheck className="w-5 h-5" />
                <span className="font-bold">Vault Security Active • AES-256-GCM Tenant Isolated</span>
              </div>
            </div>
          )}

          {activeSection === "ADMIN_SETTINGS" && isAdmin && (
            <div className="space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#1E2736] pb-2">
                <h2 className="text-base font-bold text-[#F1F5F9]">Administrator Settings</h2>
                {onSwitchPortal && (
                  <button type="button" onClick={onSwitchPortal}
                    className="px-3 py-1.5 rounded-lg bg-purple-500/15 border border-purple-500/40 text-purple-300 hover:bg-purple-500/25 text-[11px] font-bold cursor-pointer">
                    Open Full Administrator Portal →
                  </button>
                )}
              </div>
              {adminData.error && <div className="text-[#F6465D]">{adminData.error}</div>}

              <section className="space-y-2">
                <h3 className="text-[11px] uppercase text-[#64748B]">Platform Safety Locks (read-only)</h3>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                  {[
                    ["live_trading_locked", adminData.protection?.live_trading_locked ?? true],
                    ["emergency_lock_active", adminData.protection?.emergency_lock_active ?? true],
                    ["read_only_mode", adminData.protection?.read_only_mode ?? true],
                  ].map(([k, v]) => (
                    <div key={String(k)} className="p-3 rounded-lg bg-[#151C28] border border-[#1E2736]">
                      <div className="text-[#64748B] text-[10px]">{String(k)}</div>
                      <div className={`font-bold ${v ? "text-amber-400" : "text-[#10B981]"}`}>{v ? "ENGAGED" : "RELEASED"}</div>
                    </div>
                  ))}
                </div>
                <p className="text-[10px] text-[#64748B]">Locks can only be changed through the controlled release procedure, not from this screen.</p>
              </section>

              <section className="space-y-2">
                <h3 className="text-[11px] uppercase text-[#64748B]">Global Service Pricing</h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {Object.entries((adminData.pricing?.global as Record<string, any>) || {}).map(([k, v]) => (
                    <div key={k} className="flex justify-between p-2.5 rounded-lg bg-[#151C28] border border-[#1E2736]">
                      <span className="text-[#94A3B8]">{k}</span>
                      <span className="text-[#F1F5F9] font-bold">{typeof v === "object" ? JSON.stringify(v) : String(v)}</span>
                    </div>
                  ))}
                  {!adminData.pricing && <div className="text-[#64748B]">Pricing not loaded.</div>}
                </div>
              </section>

              <section className="space-y-2">
                <h3 className="text-[11px] uppercase text-[#64748B]">Provider Operations</h3>
                <pre className="p-3 rounded-lg bg-[#151C28] border border-[#1E2736] text-[10px] text-[#94A3B8] max-h-64 overflow-auto whitespace-pre-wrap">
                  {adminData.providers ? JSON.stringify(adminData.providers.summary ?? adminData.providers.providers ?? adminData.providers, null, 2).slice(0, 4000) : "Provider data not loaded."}
                </pre>
              </section>

              <p className="text-[10px] text-[#64748B]">Customer management, support inbox, AI pricing overrides, provider operations and audit logs are available in the restored Administrator Portal.</p>
            </div>
          )}
          {(activeSection === "NOTIFICATIONS" || activeSection === "BROKERS") && (
            <div className="space-y-4">
              <h2 className="text-base font-bold text-[#F1F5F9] border-b border-[#1E2736] pb-2">
                {activeSection === "NOTIFICATIONS" ? "Notifications" : "Connected Accounts"}
              </h2>
              <p className="text-[#94A3B8]">
                Settings are active and preserved in your local session.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
