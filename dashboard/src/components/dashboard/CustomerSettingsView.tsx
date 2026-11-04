"use client";

import React, { useState } from "react";
import { Sliders, ShieldCheck, User, Bell, Lock, Link2, CheckCircle2 } from "lucide-react";

interface CustomerSettingsViewProps {
  user?: any;
}

export default function CustomerSettingsView({ user }: CustomerSettingsViewProps) {
  const [activeSection, setActiveSection] = useState<
    "PROFILE" | "ACCOUNT" | "TRADING" | "NOTIFICATIONS" | "SECURITY" | "BROKERS"
  >("PROFILE");

  const sections = [
    { id: "PROFILE", label: "Profile Information", icon: User },
    { id: "ACCOUNT", label: "Account Preferences", icon: Sliders },
    { id: "TRADING", label: "Trading Preferences", icon: ShieldCheck },
    { id: "NOTIFICATIONS", label: "Notifications", icon: Bell },
    { id: "SECURITY", label: "Security & 2FA", icon: Lock },
    { id: "BROKERS", label: "Connected Accounts", icon: Link2 },
  ];

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
