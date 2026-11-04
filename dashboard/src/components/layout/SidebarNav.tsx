"use client";

import React from "react";
import {
  LayoutGrid,
  TrendingUp,
  ArrowLeftRight,
  Compass,
  Zap,
  Link2,
  Wallet,
  Layers,
  Sliders,
  LifeBuoy,
  ChevronLeft,
  ChevronRight,
  ShieldCheck,
  LogOut,
  X,
} from "lucide-react";

export type NavDestination =
  | "OVERVIEW"
  | "TERMINAL"
  | "LONG_TERM"
  | "HFT"
  | "CONNECTIONS"
  | "FUNDING"
  | "BALANCES"
  | "ORDERS"
  | "SETTINGS"
  | "SUPPORT";

interface SidebarNavProps {
  currentNav: NavDestination;
  onNavigate: (dest: NavDestination) => void;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  isMobileDrawerOpen: boolean;
  onCloseMobileDrawer: () => void;
  hftBotState?: string;
  activeSignalsCount?: number;
  openOrdersCount?: number;
  exnessConnected?: boolean;
  userEmail?: string;
  userRole?: string;
  onSignOut?: () => void;
  onSwitchPortal?: () => void;
}

export default function SidebarNav({
  currentNav,
  onNavigate,
  isCollapsed,
  onToggleCollapse,
  isMobileDrawerOpen,
  onCloseMobileDrawer,
  hftBotState = "IDLE",
  activeSignalsCount = 19,
  openOrdersCount = 0,
  exnessConnected = false,
  userEmail,
  userRole = "CUSTOMER",
  onSignOut,
  onSwitchPortal,
}: SidebarNavProps) {
  const navItems = [
    {
      id: "OVERVIEW" as NavDestination,
      label: "Overview",
      hash: "overview",
      icon: LayoutGrid,
      group: "MAIN NAVIGATION",
      badge: null,
    },
    {
      id: "TERMINAL" as NavDestination,
      label: "Trading Dashboard",
      hash: "terminal",
      icon: TrendingUp,
      group: "MAIN NAVIGATION",
      badge: <span className="text-[9px] font-mono font-bold px-1.5 py-0.2 rounded bg-[#38BDF8]/15 text-[#38BDF8] border border-[#38BDF8]/30">LIVE</span>,
    },
    {
      id: "LONG_TERM" as NavDestination,
      label: "Long-Term Strategy",
      hash: "long-term",
      icon: Compass,
      group: "MAIN NAVIGATION",
      badge: <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-[#10B981]/15 text-[#10B981]">{activeSignalsCount}</span>,
    },
    {
      id: "HFT" as NavDestination,
      label: "High-Frequency Trading",
      hash: "hft",
      icon: Zap,
      group: "MAIN NAVIGATION",
      badge: (
        <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-[#00E5FF]/15 text-[#00E5FF] border border-[#00E5FF]/30">
          SIMULATED
        </span>
      ),
    },
    {
      id: "CONNECTIONS" as NavDestination,
      label: "Exchange Connections",
      hash: "connections",
      icon: Link2,
      group: "ACCOUNT & BROKER",
      badge: exnessConnected ? (
        <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-[#10B981]/15 text-[#10B981]">CONNECTED</span>
      ) : (
        <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-[#EF4444]/15 text-[#EF4444]">DISCONNECTED</span>
      ),
    },
    {
      id: "FUNDING" as NavDestination,
      label: "Funding & Transfers",
      hash: "funding",
      icon: ArrowLeftRight,
      group: "ACCOUNT & BROKER",
      badge: <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-[#38BDF8]/15 text-[#38BDF8] border border-[#38BDF8]/30">EXNESS</span>,
    },
    {
      id: "BALANCES" as NavDestination,
      label: "Balances",
      hash: "balances",
      icon: Wallet,
      group: "ACCOUNT & BROKER",
      badge: null,
    },
    {
      id: "ORDERS" as NavDestination,
      label: "Orders & Holdings",
      hash: "orders",
      icon: Layers,
      group: "ACCOUNT & BROKER",
      badge: openOrdersCount > 0 ? (
        <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-[#38BDF8]/20 text-[#38BDF8]">{openOrdersCount}</span>
      ) : null,
    },
    {
      id: "SETTINGS" as NavDestination,
      label: "Customer Settings",
      hash: "settings",
      icon: Sliders,
      group: "SYSTEM",
      badge: null,
    },
    {
      id: "SUPPORT" as NavDestination,
      label: "Help & Support",
      hash: "support",
      icon: LifeBuoy,
      group: "SYSTEM",
      badge: null,
    },
  ];

  return (
    <>
      {/* ─── DESKTOP SIDEBAR (>= 1024px) ────────────────────────────── */}
      <aside
        className={`hidden lg:flex flex-col bg-[#0E131B] border-r border-[#1E2736] transition-all duration-300 select-none z-30 shrink-0 ${
          isCollapsed ? "w-[68px]" : "w-64"
        }`}
      >
        {/* Brand & Collapse Header */}
        <div className="h-16 px-4 flex items-center justify-between border-b border-[#1E2736]">
          {!isCollapsed ? (
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-[#38BDF8]/10 border border-[#38BDF8]/30 flex items-center justify-center shadow-sm">
                <span className="font-mono font-black text-sm text-[#38BDF8]">B</span>
              </div>
              <div className="flex flex-col">
                <span className="font-mono font-black text-base text-[#F1F5F9] tracking-wider leading-none">
                  BIT<span className="text-[#38BDF8]">DEX</span>
                </span>
                <span className="text-[9px] font-mono text-[#64748B] tracking-widest mt-0.5">
                  INSTITUTIONAL
                </span>
              </div>
            </div>
          ) : (
            <div className="w-8 h-8 mx-auto rounded-lg bg-[#38BDF8]/10 border border-[#38BDF8]/30 flex items-center justify-center">
              <span className="font-mono font-black text-sm text-[#38BDF8]">B</span>
            </div>
          )}

          <button
            onClick={onToggleCollapse}
            aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            className="p-1.5 rounded-lg text-[#94A3B8] hover:text-[#F1F5F9] hover:bg-[#151C28] transition-colors cursor-pointer"
          >
            {isCollapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
          </button>
        </div>

        {/* Navigation Items List */}
        <div className="flex-1 py-4 px-2 space-y-5 overflow-y-auto font-mono">
          {["MAIN NAVIGATION", "ACCOUNT & BROKER", "SYSTEM"].map((grp) => {
            const items = navItems.filter((i) => i.group === grp);
            return (
              <div key={grp} className="space-y-1">
                {!isCollapsed && (
                  <div className="px-3 py-1 text-[10px] font-bold text-[#64748B] tracking-wider uppercase">
                    {grp}
                  </div>
                )}
                {items.map((item) => {
                  const isActive = currentNav === item.id;
                  const Icon = item.icon;
                  return (
                    <button
                      key={item.id}
                      onClick={() => onNavigate(item.id)}
                      title={isCollapsed ? item.label : undefined}
                      className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs font-semibold transition-all group ${
                        isActive
                          ? "bg-[#151C28] text-[#F1F5F9] border-l-2 border-[#38BDF8] shadow-sm"
                          : "text-[#94A3B8] hover:text-[#F1F5F9] hover:bg-[#151C28]/60 border-l-2 border-transparent"
                      }`}
                    >
                      <Icon
                        className={`w-4 h-4 shrink-0 transition-colors ${
                          isActive ? "text-[#38BDF8]" : "text-[#94A3B8] group-hover:text-[#F1F5F9]"
                        }`}
                      />
                      {!isCollapsed && (
                        <span className="flex-1 text-left truncate">{item.label}</span>
                      )}
                      {!isCollapsed && item.badge}
                    </button>
                  );
                })}
              </div>
            );
          })}
        </div>

        {/* Desktop Sidebar Footer */}
        <div className="p-3 border-t border-[#1E2736] bg-[#080B10]/40 text-xs font-mono">
          {!isCollapsed ? (
            <div className="space-y-2">
              <div className="flex items-center justify-between text-[11px] text-[#94A3B8]">
                <span className="truncate">{userEmail || "customer@bitdex.ltd"}</span>
                <span className="text-[10px] text-[#10B981] font-bold">ACTIVE</span>
              </div>
              <div className="flex items-center justify-between pt-1 border-t border-[#1E2736]">
                {onSwitchPortal && (
                  <button
                    onClick={onSwitchPortal}
                    className="text-[10px] text-purple-400 hover:text-purple-300 flex items-center gap-1 cursor-pointer"
                  >
                    <ShieldCheck className="w-3 h-3" />
                    <span>Admin</span>
                  </button>
                )}
                {onSignOut && (
                  <button
                    id="btn-customer-sign-out"
                    onClick={onSignOut}
                    className="text-[10px] text-rose-400 hover:text-rose-300 flex items-center gap-1 cursor-pointer ml-auto"
                  >
                    <LogOut className="w-3 h-3" />
                    <span>Sign Out</span>
                  </button>
                )}
              </div>
            </div>
          ) : (
            <div className="flex justify-center">
              <div
                className={`w-2 h-2 rounded-full ${exnessConnected ? "bg-[#10B981]" : "bg-[#EF4444]"}`}
                title={exnessConnected ? "Exness Connected" : "Exness Disconnected"}
              />
            </div>
          )}
        </div>
      </aside>

      {/* ─── MOBILE OFF-CANVAS DRAWER (< 1024px) ────────────────────── */}
      {isMobileDrawerOpen && (
        <div className="fixed inset-0 z-50 flex lg:hidden">
          <div
            className="fixed inset-0 bg-[#080B10]/80 backdrop-blur-sm animate-in fade-in duration-200"
            onClick={onCloseMobileDrawer}
          />
          <div className="relative w-72 max-w-[85vw] bg-[#0E131B] border-r border-[#1E2736] flex flex-col h-full shadow-2xl z-10 p-4">
            {/* Drawer Header */}
            <div className="flex items-center justify-between pb-4 border-b border-[#1E2736]">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-lg bg-[#38BDF8]/10 border border-[#38BDF8]/30 flex items-center justify-center">
                  <span className="font-mono font-black text-xs text-[#38BDF8]">B</span>
                </div>
                <span className="font-mono font-black text-sm text-[#F1F5F9] tracking-wider">
                  BIT<span className="text-[#38BDF8]">DEX</span>
                </span>
              </div>
              <button
                onClick={onCloseMobileDrawer}
                className="p-1.5 rounded-lg text-[#94A3B8] hover:text-[#F1F5F9] hover:bg-[#151C28]"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Mobile Nav Links */}
            <div className="flex-1 py-4 space-y-4 overflow-y-auto font-mono text-xs">
              {["MAIN NAVIGATION", "ACCOUNT & BROKER", "SYSTEM"].map((grp) => {
                const items = navItems.filter((i) => i.group === grp);
                return (
                  <div key={grp} className="space-y-1">
                    <div className="px-3 py-1 text-[10px] font-bold text-[#64748B] tracking-wider uppercase">
                      {grp}
                    </div>
                    {items.map((item) => {
                      const isActive = currentNav === item.id;
                      const Icon = item.icon;
                      return (
                        <button
                          key={item.id}
                          onClick={() => {
                            onNavigate(item.id);
                            onCloseMobileDrawer();
                          }}
                          className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-xs font-semibold transition-all ${
                            isActive
                              ? "bg-[#151C28] text-[#F1F5F9] border-l-2 border-[#38BDF8]"
                              : "text-[#94A3B8] hover:bg-[#151C28]/60 hover:text-[#F1F5F9]"
                          }`}
                        >
                          <div className="flex items-center gap-2.5 min-w-0">
                            <Icon className={`w-4 h-4 ${isActive ? "text-[#38BDF8]" : "text-[#94A3B8]"}`} />
                            <span className="truncate">{item.label}</span>
                          </div>
                          {item.badge}
                        </button>
                      );
                    })}
                  </div>
                );
              })}
            </div>

            {/* Mobile Drawer Footer */}
            <div className="pt-4 border-t border-[#1E2736] text-[11px] font-mono text-[#94A3B8] space-y-2">
              <div className="truncate">{userEmail || "customer@bitdex.ltd"}</div>
              <div className="flex items-center justify-between">
                {onSwitchPortal && (
                  <button
                    onClick={() => {
                      onCloseMobileDrawer();
                      onSwitchPortal();
                    }}
                    className="text-purple-400 hover:text-purple-300 font-bold"
                  >
                    Admin Portal
                  </button>
                )}
                {onSignOut && (
                  <button
                    onClick={() => {
                      onCloseMobileDrawer();
                      onSignOut();
                    }}
                    className="text-rose-400 hover:text-rose-300 font-bold ml-auto"
                  >
                    Sign Out
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
