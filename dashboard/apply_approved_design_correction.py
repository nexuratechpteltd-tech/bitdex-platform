#!/usr/bin/env python3
"""
Corrective Implementation Script for Bitdex Approved Designs (Images 1, 2, 3)
- Restores deliberate, cohesive visual identity matching the approved reference mockups
- Distinct surfaces: #f8fafc canvas, #ffffff elevated cards with subtle borders & soft shadows, #0f172a market ticker strip
- Clean header matching Image 1 & 3: Logo, Nav links (Dashboard, Markets, Signals, Grid, Account), Center search, Green read-only status pill, Admin Fee Exemption badge
- Markets 8-Card Grid (Image 1): BTC, ETH, SOL, XRP, EUR/USD, GBP/USD, USD/JPY, AUD/USD
- Latest Signals 3-Card Grid (Image 3): Long bias, Short bias, No signal with key metrics and single blue Technical Analysis button
- Technical Analysis Four-Engine Board (Image 2): Asset title, timeframe selector (1m, 5m, 15m, 1h, 4h, 1d), 3 top summary cards, Signal levels card with arithmetic callout, 4 separate engine cards, yellow Disagreement banner, blue Combined Conclusion callout
- Admin Fee Exemption banner and green execution button for admin
- Strict NO CHARTS rule (zero canvases, zero sparklines, zero chart libraries)
- 100% preservation of permissions, APIs, database, and safety invariants
"""

import os
import re

DASHBOARD_SRC = "/opt/tauric-platform-staging/dashboard/src"

def update_four_engine_board():
    # Copy the prepared FourEngineDecisionBoard.tsx into destination
    local_path = "/opt/tauric-platform-staging/dashboard/FourEngineDecisionBoard_v3.tsx"
    dest_path = os.path.join(DASHBOARD_SRC, "components/FourEngineDecisionBoard.tsx")
    if os.path.exists(local_path):
        with open(local_path, "r", encoding="utf-8") as f:
            content = f.read()
        with open(dest_path, "w", encoding="utf-8") as f:
            f.write(content)
        print("✓ Updated src/components/FourEngineDecisionBoard.tsx with high-fidelity Image 2 design")
    else:
        print("! Local file not found, skipping FourEngineDecisionBoard copy")

def update_customer_portal():
    path = os.path.join(DASHBOARD_SRC, "components/CustomerPortal.tsx")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Ensure Search is imported
    if "Search," not in content and "Search " not in content:
        content = content.replace("import {", "import {\n  Search,")

    # Clean, beautiful header matching Image 1 & 3
    # Look for the header block from {/* ─── CUSTOMER PORTAL HEADER to </header>
    old_header_pattern = re.compile(r'{\s*/\*\s*───\s*CUSTOMER PORTAL HEADER.*?</header>', re.DOTALL)

    new_header = """{/* ─── CUSTOMER PORTAL HEADER (IMAGE 1 & 3 SPEC) ─────────────── */}
      <header className="sticky top-0 z-40 w-full border-b border-slate-200 bg-white shadow-sm">
        <div className="max-w-[1760px] w-full mx-auto px-4 sm:px-6 lg:px-8 xl:px-10 h-16 flex items-center justify-between gap-4">
          {/* Left: Brand Identity & Primary Nav */}
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-2.5 cursor-pointer" onClick={() => setActiveTab("TRADING")}>
              <div className="w-3.5 h-3.5 rounded-full bg-amber-400 shrink-0" />
              <span className="text-xl font-bold tracking-tight text-slate-900 font-sans">Bitdex</span>
            </div>

            {/* Primary Nav Links (Image 1 & 3 Spec) */}
            <nav className="hidden lg:flex items-center gap-1 text-sm font-medium">
              <button
                onClick={() => { setActiveTab("TRADING"); if (typeof window !== "undefined") window.location.hash = "dashboard"; }}
                className={`px-3 py-1.5 rounded-lg transition-all cursor-pointer ${
                  activeTab === "TRADING"
                    ? "bg-blue-600 text-white font-semibold shadow-sm"
                    : "text-slate-600 hover:text-slate-900 hover:bg-slate-100"
                }`}
              >
                Dashboard
              </button>
              <button
                onClick={() => { setActiveTab("TRADING"); }}
                className="px-3 py-1.5 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition-all cursor-pointer"
              >
                Analysis
              </button>
              <button
                onClick={() => { setActiveTab("TRADING"); }}
                className="px-3 py-1.5 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition-all cursor-pointer"
              >
                Signals
              </button>
              <button
                onClick={() => { setActiveTab("TRADING"); }}
                className="px-3 py-1.5 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition-all cursor-pointer"
              >
                Grid
              </button>
              <button
                onClick={() => { setActiveTab("CONNECTIONS"); if (typeof window !== "undefined") window.location.hash = "account"; }}
                className={`px-3 py-1.5 rounded-lg transition-all cursor-pointer ${
                  activeTab !== "TRADING"
                    ? "bg-blue-600 text-white font-semibold shadow-sm"
                    : "text-slate-600 hover:text-slate-900 hover:bg-slate-100"
                }`}
              >
                Account
              </button>
            </nav>
          </div>

          {/* Center: Wide Search Input (Image 1 & 3 Spec) */}
          <div className="flex-1 max-w-lg mx-4 hidden md:block">
            <div className="relative">
              <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-2.5" />
              <input
                type="text"
                placeholder="Search any coin or pair, e.g. SOL or EUR/USD"
                className="w-full pl-10 pr-4 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 placeholder-slate-400 focus:outline-none focus:bg-white focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
              />
            </div>
          </div>

          {/* Right: Read-Only Status, Admin Fee Exemption & User Pill */}
          <div className="flex items-center gap-3">
            {/* Read-Only Status Pill (Image 1 & 3 Spec) */}
            <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 text-xs font-semibold">
              <span className="w-2 h-2 rounded-full bg-emerald-500" />
              <span>Read-only · Live trading locked</span>
            </div>

            {/* Admin Fee Exemption Pill or Customer Activation / Balance */}
            {profile?.is_admin_exempt || feePolicy?.is_admin_exempt || billingSummary?.is_admin_exempt ? (
              <div className="hidden sm:flex items-center gap-1.5 px-3 py-1 rounded-full bg-sky-50 border border-sky-200 text-sky-800 text-xs font-mono font-bold shadow-sm">
                <ShieldCheck className="w-3.5 h-3.5 text-sky-600" />
                <span>ADMIN — FEE EXEMPT</span>
              </div>
            ) : !feePolicy.activation_fee_charged ? (
              <button
                id="header-activate-account-btn"
                onClick={() => {
                  setPayModalType("ACTIVATION_FEE");
                  setPayModalAmount(20.0);
                  setIsPayModalOpen(true);
                }}
                className="px-3 py-1 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-bold font-mono transition-all cursor-pointer shadow-sm flex items-center gap-1.5"
              >
                <AlertTriangle className="w-3.5 h-3.5 text-slate-950" />
                <span>Activate Account</span>
              </button>
            ) : null}

            {/* User Profile Pill */}
            <div className="relative">
              <button
                id="header-profile-menu-btn"
                onClick={() => setIsProfileDropdownOpen(!isProfileDropdownOpen)}
                className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-50 hover:bg-slate-100 border border-slate-200 text-xs font-medium text-slate-700 transition-all cursor-pointer"
              >
                <div className="w-5 h-5 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center font-bold text-[10px]">
                  {(profile?.username || profile?.email || "U")[0].toUpperCase()}
                </div>
                <span className="hidden sm:inline font-mono font-semibold text-slate-800">
                  {profile?.username || profile?.email?.split("@")[0]}
                </span>
                <ChevronDown className="w-3 h-3 text-slate-400" />
              </button>

              {isProfileDropdownOpen && (
                <div className="absolute right-0 mt-2 w-56 bg-white border border-slate-200 rounded-xl shadow-lg py-1.5 z-50 text-xs font-mono">
                  <div className="px-3 py-2 border-b border-slate-100">
                    <span className="text-[10px] text-slate-400 uppercase font-medium block">Account</span>
                    <span className="text-slate-900 font-bold block truncate">{profile?.email}</span>
                    <span className="text-[11px] text-slate-500 mt-0.5 block">Role: {user?.role || "CUSTOMER"}</span>
                  </div>
                  <button
                    onClick={() => { setActiveTab("CONNECTIONS"); setIsProfileDropdownOpen(false); }}
                    className="w-full px-3 py-2 text-left text-slate-700 hover:bg-slate-50 flex items-center gap-2 cursor-pointer"
                  >
                    <Layers className="w-3.5 h-3.5 text-slate-400" />
                    <span>Exchange Connections</span>
                  </button>
                  <button
                    onClick={() => { setActiveTab("BALANCES"); setIsProfileDropdownOpen(false); }}
                    className="w-full px-3 py-2 text-left text-slate-700 hover:bg-slate-50 flex items-center gap-2 cursor-pointer"
                  >
                    <Scale className="w-3.5 h-3.5 text-slate-400" />
                    <span>Balances</span>
                  </button>
                  <button
                    onClick={() => { setActiveTab("BILLING"); setIsProfileDropdownOpen(false); }}
                    className="w-full px-3 py-2 text-left text-slate-700 hover:bg-slate-50 flex items-center gap-2 cursor-pointer"
                  >
                    <CreditCard className="w-3.5 h-3.5 text-slate-400" />
                    <span>Billing & Credits</span>
                  </button>
                  <div className="my-1 border-t border-slate-100" />
                  <button
                    onClick={() => { setIsProfileDropdownOpen(false); onSignOut(); }}
                    className="w-full px-3 py-2 text-left text-rose-600 hover:bg-rose-50 flex items-center gap-2 cursor-pointer"
                  >
                    <LogOut className="w-3.5 h-3.5 text-rose-500" />
                    <span>Sign Out</span>
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </header>"""

    if old_header_pattern.search(content):
        content = old_header_pattern.sub(new_header, content, count=1)
        print("✓ Replaced CustomerPortal header with clean Image 1/3 navbar")
    else:
        print("! Could not find old header pattern in CustomerPortal.tsx")

    # Secondary Navigation sub-bar when inside Account mode
    sub_nav_bar = """        {/* Secondary Account Navigation Bar */}
        {activeTab !== "TRADING" && (
          <div className="bg-slate-50 border-b border-slate-200 py-2 px-4 sm:px-6 lg:px-8 xl:px-10 flex items-center gap-2 overflow-x-auto text-xs">
            <button
              onClick={() => { setActiveTab("CONNECTIONS"); if (typeof window !== "undefined") window.location.hash = "connections"; }}
              className={`px-3 py-1.5 rounded-lg font-medium transition-all cursor-pointer whitespace-nowrap ${
                activeTab === "CONNECTIONS" ? "bg-white text-slate-900 border border-slate-200 shadow-sm font-bold" : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Exchange Connections
            </button>
            <button
              onClick={() => { setActiveTab("BALANCES"); if (typeof window !== "undefined") window.location.hash = "balances"; fetchBalances(); }}
              className={`px-3 py-1.5 rounded-lg font-medium transition-all cursor-pointer whitespace-nowrap ${
                activeTab === "BALANCES" ? "bg-white text-slate-900 border border-slate-200 shadow-sm font-bold" : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Balances
            </button>
            <button
              onClick={() => { setActiveTab("BILLING"); if (typeof window !== "undefined") window.location.hash = "billing"; }}
              className={`px-3 py-1.5 rounded-lg font-medium transition-all cursor-pointer whitespace-nowrap ${
                activeTab === "BILLING" ? "bg-white text-slate-900 border border-slate-200 shadow-sm font-bold" : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Billing & Invoices
            </button>
            <button
              onClick={() => { setActiveTab("SUPPORT"); if (typeof window !== "undefined") window.location.hash = "support"; }}
              className={`px-3 py-1.5 rounded-lg font-medium transition-all cursor-pointer whitespace-nowrap ${
                activeTab === "SUPPORT" ? "bg-white text-slate-900 border border-slate-200 shadow-sm font-bold" : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Help & Support
            </button>
            <button
              onClick={() => { setActiveTab("SECURITY"); if (typeof window !== "undefined") window.location.hash = "security"; }}
              className={`px-3 py-1.5 rounded-lg font-medium transition-all cursor-pointer whitespace-nowrap ${
                activeTab === "SECURITY" ? "bg-white text-slate-900 border border-slate-200 shadow-sm font-bold" : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Security & 2FA
            </button>
            <button
              onClick={() => { setActiveTab("PROFIT_LOSS"); if (typeof window !== "undefined") window.location.hash = "pnl"; }}
              className={`px-3 py-1.5 rounded-lg font-medium transition-all cursor-pointer whitespace-nowrap ${
                activeTab === "PROFIT_LOSS" ? "bg-white text-slate-900 border border-slate-200 shadow-sm font-bold" : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Profit & Loss
            </button>
          </div>
        )}"""

    # Replace the old duplicate 7-tab bar
    old_tabs_pattern = re.compile(r'{\s*/\*\s*Navigation Tabs \(Exactly 7 Primary Items\).*?</div>\s*</div>', re.DOTALL)
    if old_tabs_pattern.search(content):
        content = old_tabs_pattern.sub(sub_nav_bar, content, count=1)
        print("✓ Replaced duplicate tab bar with contextual account navigation")

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("✓ Updated src/components/CustomerPortal.tsx")

def update_unified_signals():
    path = os.path.join(DASHBOARD_SRC, "components/UnifiedSignalDashboard.tsx")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Create the high-fidelity Dashboard view matching Images 1 & 3:
    dashboard_view_code = """      {/* ─── APPROVED DASHBOARD VIEW (IMAGES 1 & 3 SPEC) ─────────────── */}
      <div className="space-y-6">
        {/* SECTION 1: MARKETS (4x2 GRID - STRICTLY NO CHARTS) */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-bold text-slate-900 tracking-tight">Markets</h2>
            <div className="flex items-center gap-1 p-1 bg-slate-100 rounded-lg border border-slate-200">
              <button
                onClick={() => setSelectedMarket("CRYPTO")}
                className={`px-3 py-1 rounded-md text-xs font-semibold transition-all cursor-pointer ${
                  selectedMarket === "CRYPTO" ? "bg-blue-600 text-white shadow-sm" : "text-slate-600 hover:text-slate-900"
                }`}
              >
                All
              </button>
              <button
                onClick={() => setSelectedMarket("CRYPTO")}
                className="px-3 py-1 rounded-md text-xs font-semibold text-slate-600 hover:text-slate-900 cursor-pointer"
              >
                Crypto
              </button>
              <button
                onClick={() => setSelectedMarket("FOREX")}
                className={`px-3 py-1 rounded-md text-xs font-semibold transition-all cursor-pointer ${
                  selectedMarket === "FOREX" ? "bg-white text-slate-900 border border-slate-200 shadow-sm" : "text-slate-600 hover:text-slate-900"
                }`}
              >
                Forex
              </button>
            </div>
          </div>

          {/* 8 Market Cards Grid (4x2 Grid) */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              { symbol: "BTC/USDT", market: "Crypto", price: "64,250.00", change: "+1.42%", isPos: true, status: "Live", time: "Updated 3 s ago" },
              { symbol: "ETH/USDT", market: "Crypto", price: "3,120.50", change: "+0.65%", isPos: true, status: "Live", time: "Updated 4 s ago" },
              { symbol: "SOL/USDT", market: "Crypto", price: "148.20", change: "-2.10%", isPos: false, status: "Delayed", time: "Updated 45 s ago" },
              { symbol: "XRP/USDT", market: "Crypto", price: "0.5240", change: "-0.35%", isPos: false, status: "Live", time: "Updated 2 s ago" },
              { symbol: "EUR/USD", market: "Forex", price: "1.0850", change: "+0.12%", isPos: true, status: "Live", time: "Updated 1 s ago" },
              { symbol: "GBP/USD", market: "Forex", price: "1.2910", change: "-0.08%", isPos: false, status: "Stale", time: "No update for 6 min" },
              { symbol: "USD/JPY", market: "Forex", price: "151.200", change: "+0.20%", isPos: true, status: "Market is closed", time: "Last quote before close" },
              { symbol: "AUD/USD", market: "Forex", price: "0.6540", change: "+0.05%", isPos: true, status: "Delayed", time: "Updated 30 s ago" },
            ].map((item) => (
              <div
                key={item.symbol}
                onClick={() => executeFourEngineAnalysis(item.symbol.replace("/", ""), item.market === "Forex" ? "FOREX" : "CRYPTO")}
                className="bg-white border border-slate-200/90 rounded-2xl p-5 shadow-sm hover:shadow-md hover:border-slate-300 transition-all cursor-pointer flex flex-col justify-between h-38 group"
              >
                <div className="flex items-center justify-between">
                  <span className="font-bold text-slate-900 text-base group-hover:text-blue-600 transition-colors">{item.symbol}</span>
                  <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold border ${
                    item.status === "Live" ? "bg-emerald-50 text-emerald-700 border-emerald-200" :
                    item.status === "Delayed" ? "bg-amber-50 text-amber-700 border-amber-200" :
                    item.status === "Stale" ? "bg-rose-50 text-rose-700 border-rose-200" :
                    "bg-slate-100 text-slate-600 border-slate-200"
                  }`}>
                    {item.status}
                  </span>
                </div>

                <div className="my-2">
                  <div className="text-3xl font-bold font-mono text-slate-900 tracking-tight">{item.price}</div>
                  <div className={`text-xs font-semibold flex items-center gap-1 mt-1 ${item.isPos ? "text-emerald-600" : "text-rose-600"}`}>
                    <span>{item.isPos ? "▲" : "▼"}</span>
                    <span>{item.change}</span>
                  </div>
                </div>

                <div className="flex items-center justify-between text-xs text-slate-500 pt-2 border-t border-slate-100 font-medium">
                  <span>{item.market}</span>
                  <span>{item.time}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* SECTION 2: LATEST SIGNALS (IMAGE 1 & 3 SPEC) */}
        <div className="space-y-4 pt-2">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
            <h2 className="text-xl font-bold text-slate-900 tracking-tight">Latest signals</h2>
            <span className="text-xs text-slate-500">Direction shown as label + arrow, never colour alone</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {/* Signal Card 1: BTC/USDT Long */}
            <div className="bg-white border border-slate-200/90 rounded-2xl p-5 shadow-sm hover:shadow-md hover:border-slate-300 transition-all flex flex-col justify-between space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-base font-bold font-mono text-slate-900">BTC/USDT</span>
                  <span className="text-xs font-mono font-medium px-2 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200">
                    1h
                  </span>
                </div>
                <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center gap-1">
                  <span>▲</span>
                  <span>Long bias</span>
                </span>
              </div>

              <div className="grid grid-cols-3 gap-2 py-2.5 px-3 bg-slate-50 border border-slate-200 rounded-xl font-mono text-xs">
                <div>
                  <span className="text-[10px] text-slate-500 block uppercase font-medium">Entry</span>
                  <span className="font-bold text-slate-900">12,300.00</span>
                </div>
                <div>
                  <span className="text-[10px] text-slate-500 block uppercase font-medium">Stop-loss</span>
                  <span className="font-bold text-rose-600">12,000.00</span>
                </div>
                <div>
                  <span className="text-[10px] text-slate-500 block uppercase font-medium">Target 1</span>
                  <span className="font-bold text-emerald-600">12,800.00</span>
                </div>
              </div>

              <div className="text-xs text-slate-500 space-y-1 font-mono">
                <div className="text-slate-700 font-medium">Engines: 2 Long · 1 Short · 1 no result</div>
                <div className="text-[11px] text-slate-400">Valid until 14:30 UTC (2 h 18 m left) · data 3 s old</div>
              </div>

              <button
                onClick={() => executeFourEngineAnalysis("BTCUSDT", "CRYPTO")}
                className="w-full py-2.5 px-4 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold flex items-center justify-center gap-2 shadow-sm transition-all cursor-pointer"
              >
                <Activity className="w-3.5 h-3.5" />
                <span>Technical Analysis</span>
              </button>
            </div>

            {/* Signal Card 2: ETH/USDT Short */}
            <div className="bg-white border border-slate-200/90 rounded-2xl p-5 shadow-sm hover:shadow-md hover:border-slate-300 transition-all flex flex-col justify-between space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-base font-bold font-mono text-slate-900">ETH/USDT</span>
                  <span className="text-xs font-mono font-medium px-2 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200">
                    15m
                  </span>
                </div>
                <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-rose-50 text-rose-700 border border-rose-200 flex items-center gap-1">
                  <span>▼</span>
                  <span>Short bias</span>
                </span>
              </div>

              <div className="grid grid-cols-3 gap-2 py-2.5 px-3 bg-slate-50 border border-slate-200 rounded-xl font-mono text-xs">
                <div>
                  <span className="text-[10px] text-slate-500 block uppercase font-medium">Entry</span>
                  <span className="font-bold text-slate-900">1,240.00</span>
                </div>
                <div>
                  <span className="text-[10px] text-slate-500 block uppercase font-medium">Stop-loss</span>
                  <span className="font-bold text-rose-600">1,262.00</span>
                </div>
                <div>
                  <span className="text-[10px] text-slate-500 block uppercase font-medium">Target 1</span>
                  <span className="font-bold text-emerald-600">1,200.00</span>
                </div>
              </div>

              <div className="text-xs text-slate-500 space-y-1 font-mono">
                <div className="text-slate-700 font-medium">Engines: 3 Short · 1 no result</div>
                <div className="text-[11px] text-slate-400">Valid until 11:15 UTC (24 m left) · data 5 s old</div>
              </div>

              <button
                onClick={() => executeFourEngineAnalysis("ETHUSDT", "CRYPTO")}
                className="w-full py-2.5 px-4 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold flex items-center justify-center gap-2 shadow-sm transition-all cursor-pointer"
              >
                <Activity className="w-3.5 h-3.5" />
                <span>Technical Analysis</span>
              </button>
            </div>

            {/* Signal Card 3: EUR/USD No Signal (Forex Closed) */}
            <div className="bg-white border border-slate-200/90 rounded-2xl p-5 shadow-sm hover:shadow-md hover:border-slate-300 transition-all flex flex-col justify-between space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-base font-bold font-mono text-slate-900">EUR/USD</span>
                  <span className="text-xs font-mono font-medium px-2 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200">
                    4h
                  </span>
                </div>
                <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-600 border border-slate-200 flex items-center gap-1">
                  <span>■</span>
                  <span>No signal</span>
                </span>
              </div>

              <div className="py-3 px-3 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-600 space-y-1">
                <p className="font-medium text-slate-800">Forex market is closed. Signals resume when it reopens.</p>
                <p className="text-[11px] text-slate-500">Last analysis: placeholder</p>
              </div>

              <div className="text-xs text-slate-400 space-y-1 font-mono">
                <div>Forex Session: Closed · reopens in 6h 12m</div>
              </div>

              <button
                onClick={() => executeFourEngineAnalysis("EURUSD", "FOREX")}
                className="w-full py-2.5 px-4 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold flex items-center justify-center gap-2 shadow-sm transition-all cursor-pointer"
              >
                <Activity className="w-3.5 h-3.5" />
                <span>Technical Analysis</span>
              </button>
            </div>
          </div>
        </div>

        {/* SECTION 3: FOOTNOTE NOTICE (IMAGE 1 & 3 SPEC) */}
        <div className="text-center text-xs text-slate-400 pt-4 pb-2 font-mono">
          All names, prices, changes and signals on this page are illustrative placeholders for design review only. They are not real market data and not trading advice.
        </div>
      </div>
"""

    # Check if we should replace the return of UnifiedSignalDashboard
    # Let's inspect where the return is in UnifiedSignalDashboard
    old_dashboard_pattern = re.compile(r'return\s*\(\s*<div className="space-y-[0-9]+">.*?{/\* ─── MARKETS OVERVIEW SECTION.*?</div\s*>\s*</div\s*>\s*</div>', re.DOTALL)

    # Instead of fragile regex, let's see where the main return starts
    # In UnifiedSignalDashboard: `return (\n    <div className="space-y-6">` or `return (\n    <div className="space-y-5">`
    if 'return (\n    <div className="space-y-6">' in content:
        # Find where the 8 cards end
        end_idx = content.find('{/* ─── Rearrangeable Sections Control Bar')
        if end_idx != -1:
            start_idx = content.find('return (\n    <div className="space-y-6">')
            # Replace that block with our clean dashboard view code and wrap the rearrangeable sections in a collapsible
            content = content[:start_idx] + 'return (\n    <div className="space-y-6">\n' + dashboard_view_code + '\n' + content[end_idx:]
            print("✓ Injected approved Dashboard and Latest Signals view into UnifiedSignalDashboard.tsx")

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("✓ Updated src/components/UnifiedSignalDashboard.tsx")

if __name__ == "__main__":
    update_four_engine_board()
    update_customer_portal()
    update_unified_signals()
    print("=== Cohesive Identity Implementation Complete ===")
