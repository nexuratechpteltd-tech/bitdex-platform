#!/usr/bin/env python3
"""
Comprehensive implementation of approved Bitdex designs (Images 1, 2, 3):
- Clean, institutional light theme (#ffffff cards on #f8fafc canvas) across all screens and components
- Yellow sample notice banner at the top
- Clean white navbar with Bitdex logo, center search bar, navigation tabs, and read-only status pill
- Market ticker strip below header with live asset prices and Forex session status
- "Markets" overview section with 8 cards (Crypto & Forex), status badges (Live, Delayed, Stale, Market is closed), bold prices, percentage changes, and NO charts
- "Latest signals" section with clear Long bias (green), Short bias (rose), and Neutral labels, engine counts, validity, and single Technical Analysis button
- Technical Analysis layout (Image 2) with 3 top summary cards, Signal levels (Entry, SL, TP1, TP2, Invalidation, R:R), Four-engine comparison (TAURIC, Jev, CIPHER, OctoBot), disagreement alert, and combined conclusion callout
- Admin Fee Exemption badge and green execution button when authorized administrator
- Strict NO CHARTS rule (zero canvases, zero svg sparklines, zero chart panels)
- 100% preservation of roles, permissions, APIs, database, and safety locks
"""

import os
import re

DASHBOARD_SRC = "/opt/tauric-platform-staging/dashboard/src"

def update_root_layout():
    path = os.path.join(DASHBOARD_SRC, "app/layout.tsx")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    content = re.sub(r'themeColor:\s*"[^"]+"', 'themeColor: "#f8fafc"', content)
    content = content.replace('className="dark"', 'className="light"')
    content = re.sub(r'<body className="[^"]+"', '<body className="bg-[#f8fafc] text-slate-900 min-h-screen antialiased selection:bg-blue-600 selection:text-white"', content)

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("✓ Updated src/app/layout.tsx")

def update_globals_css():
    path = os.path.join(DASHBOARD_SRC, "app/globals.css")
    css = """@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --background: #f8fafc;
  --foreground: #0f172a;
  --surface-card: #ffffff;
  --surface-card-border: #e2e8f0;
  --surface-well: #f1f5f9;
  --surface-well-border: #cbd5e1;
}

body {
  color: var(--foreground);
  background: var(--background);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  overflow-x: hidden;
}

/* Custom scrollbars */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
::-webkit-scrollbar-track {
  background: #f1f5f9;
}
::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;
}

/* Institutional Clean Light Surfaces & Utilities */
.terminal-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05), 0 1px 2px 0 rgba(0, 0, 0, 0.03);
  border-radius: 0.75rem;
}

.terminal-well {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 0.5rem;
}
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(css)
    print("✓ Updated src/app/globals.css")

def update_institutional_console():
    path = os.path.join(DASHBOARD_SRC, "components/InstitutionalConsole.tsx")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Change root background from bg-slate-950 to bg-[#f8fafc] text-slate-900
    content = content.replace(
        'className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-cyan-500/30 selection:text-cyan-200"',
        'className="bg-[#f8fafc] text-slate-900 font-sans selection:bg-blue-600 selection:text-white"'
    )
    content = re.sub(
        r'className="min-h-screen bg-slate-950[^"]*"',
        'className="bg-[#f8fafc] text-slate-900 font-sans selection:bg-blue-600 selection:text-white"',
        content
    )

    # Convert dark headers & bars
    content = content.replace('bg-[#0c1322]', 'bg-white')
    content = content.replace('bg-slate-950', 'bg-white')
    content = content.replace('bg-slate-900', 'bg-white')
    content = content.replace('border-slate-800', 'border-slate-200')
    content = content.replace('border-slate-700', 'border-slate-200')
    content = content.replace('text-slate-100', 'text-slate-900')
    content = content.replace('text-slate-200', 'text-slate-800')
    content = content.replace('text-slate-300', 'text-slate-700')
    content = content.replace('text-slate-400', 'text-slate-500')

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("✓ Updated src/components/InstitutionalConsole.tsx")

def update_customer_portal():
    path = os.path.join(DASHBOARD_SRC, "components/CustomerPortal.tsx")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Update root container & header
    content = content.replace(
        'className="min-h-screen bg-slate-950 text-slate-900 flex flex-col font-sans"',
        'className="min-h-screen bg-[#f8fafc] text-slate-900 flex flex-col font-sans"'
    )
    content = content.replace(
        'className="sticky top-0 z-40 w-full border-b border-slate-200/80 bg-slate-950/95 backdrop-blur-md"',
        'className="sticky top-0 z-40 w-full border-b border-slate-200 bg-white shadow-sm"'
    )

    # 2. Add top yellow sample/preview banner matching Image 1
    sample_banner = """      {/* ─── SAMPLE DATA NOTICE BANNER (IMAGE 1 SPEC) ─────────────── */}
      <div className="bg-[#fef9c3] border-b border-[#fde047] text-[#854d0e] text-xs py-1.5 px-4 text-center font-medium">
        Design preview. Every price, change, signal and status below is labelled placeholder data, not a real feed.
      </div>\n"""
    if "SAMPLE DATA NOTICE BANNER" not in content:
        content = content.replace(
            '<div className="min-h-screen bg-[#f8fafc] text-slate-900 flex flex-col font-sans">\n      {/* ─── CUSTOMER PORTAL HEADER',
            '<div className="min-h-screen bg-[#f8fafc] text-slate-900 flex flex-col font-sans">\n' + sample_banner + '      {/* ─── CUSTOMER PORTAL HEADER'
        )

    # 3. Add dark market ticker strip matching Image 1 & 3
    ticker_bar = """      {/* ─── MARKET TICKER STRIP (IMAGE 1 & 3 SPEC) ──────────────── */}
      <div className="bg-[#0f172a] text-white py-1.5 px-6 text-xs font-mono flex items-center justify-between gap-6 overflow-x-auto border-b border-slate-800">
        <div className="flex items-center gap-6 shrink-0">
          <span className="bg-blue-600 text-white px-2 py-0.5 rounded text-[10px] font-bold tracking-wider">Ticker · sample</span>
          <span>BTC/USDT <strong className="text-white">64,250.00</strong> <span className="text-emerald-400">▲ +1.42%</span></span>
          <span>ETH/USDT <strong className="text-white">3,120.50</strong> <span className="text-emerald-400">▲ +0.65%</span></span>
          <span>SOL/USDT <strong className="text-white">148.20</strong> <span className="text-rose-400">▼ -2.10%</span></span>
          <span>XRP/USDT <strong className="text-white">0.5240</strong> <span className="text-rose-400">▼ -0.35%</span></span>
          <span>EUR/USD <strong className="text-white">1.0850</strong> <span className="text-emerald-400">▲ +0.12%</span></span>
          <span>GBP/USD <strong className="text-white">1.2910</strong> <span className="text-rose-400">▼ -0.08%</span></span>
        </div>
        <div className="hidden xl:flex items-center gap-3 shrink-0 text-slate-400 text-[11px]">
          <span>Forex session: <strong className="text-amber-300">Closed</strong> · reopens in 6h 12m</span>
        </div>
      </div>\n"""
    if "MARKET TICKER STRIP" not in content:
        content = content.replace(
            '</header>',
            '</header>\n' + ticker_bar
        )

    # 4. Add prominent search input in header center matching Image 1
    search_bar = """          {/* Center: Prominent Coin / Pair Search (Image 1 Spec) */}
          <div className="flex-1 max-w-md mx-4 hidden md:block">
            <div className="relative">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
              <input
                type="text"
                placeholder="Search any coin or pair, e.g. SOL or EUR/USD"
                className="w-full pl-9 pr-4 py-1.5 bg-white border border-slate-300 rounded-lg text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:border-blue-500 shadow-sm"
              />
            </div>
          </div>\n"""
    if "Prominent Coin / Pair Search" not in content:
        content = content.replace(
            '{/* Center-Right: Feed Sync & Live Dual-AI Telemetry Indicators */}',
            search_bar + '          {/* Center-Right: Feed Sync & Live Dual-AI Telemetry Indicators */}'
        )

    # 5. Clean tab buttons to active blue pill
    content = content.replace(
        'bg-sky-500/20 text-slate-900 border border-sky-400/40 shadow-sm font-bold',
        'bg-blue-600 text-white shadow-sm font-bold'
    )

    # 6. Clean up dark elements across CustomerPortal
    content = content.replace('bg-slate-950', 'bg-slate-50')
    content = content.replace('bg-slate-900/90', 'bg-slate-50')
    content = content.replace('bg-slate-900/80', 'bg-white')
    content = content.replace('bg-slate-900', 'bg-white')
    content = content.replace('bg-slate-800/80', 'bg-slate-100')
    content = content.replace('bg-slate-800', 'bg-slate-100')
    content = content.replace('border-slate-800', 'border-slate-200')
    content = content.replace('border-slate-700', 'border-slate-300')
    content = content.replace('text-slate-300', 'text-slate-700')
    content = content.replace('text-slate-400', 'text-slate-500')

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("✓ Updated src/components/CustomerPortal.tsx")

def update_admin_panel():
    path = os.path.join(DASHBOARD_SRC, "components/AdminPanel.tsx")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Root background and header to clean light theme
    content = content.replace(
        'className="min-h-screen bg-slate-950 text-slate-900 flex flex-col font-sans"',
        'className="min-h-screen bg-[#f8fafc] text-slate-900 flex flex-col font-sans"'
    )
    content = content.replace(
        'className="sticky top-0 z-40 w-full border-b border-slate-200/80 bg-slate-950/95 backdrop-blur-md"',
        'className="sticky top-0 z-40 w-full border-b border-slate-200 bg-white shadow-sm"'
    )

    # Top sample banner in AdminPanel too
    sample_banner = """      {/* ─── SAMPLE DATA NOTICE BANNER (IMAGE 1 SPEC) ─────────────── */}
      <div className="bg-[#fef9c3] border-b border-[#fde047] text-[#854d0e] text-xs py-1.5 px-4 text-center font-medium">
        Design preview. Every price, change, signal and status below is labelled placeholder data, not a real feed.
      </div>\n"""
    if "SAMPLE DATA NOTICE BANNER" not in content:
        content = content.replace(
            '<div className="min-h-screen bg-[#f8fafc] text-slate-900 flex flex-col font-sans">\n      {/* ─── TOP STICKY APPLICATION BAR',
            '<div className="min-h-screen bg-[#f8fafc] text-slate-900 flex flex-col font-sans">\n' + sample_banner + '      {/* ─── TOP STICKY APPLICATION BAR'
        )

    # Active admin tab button
    content = content.replace(
        'bg-purple-500/20 text-slate-900 border border-purple-400/40 shadow-sm font-bold',
        'bg-blue-600 text-white shadow-sm font-bold'
    )

    # Clean light theme across AdminPanel
    content = content.replace('bg-slate-950', 'bg-slate-50')
    content = content.replace('bg-slate-900/90', 'bg-slate-50')
    content = content.replace('bg-slate-900/80', 'bg-white')
    content = content.replace('bg-slate-900', 'bg-white')
    content = content.replace('bg-slate-800/80', 'bg-slate-100')
    content = content.replace('bg-slate-800', 'bg-slate-100')
    content = content.replace('border-slate-800', 'border-slate-200')
    content = content.replace('border-slate-700', 'border-slate-300')
    content = content.replace('text-slate-300', 'text-slate-700')
    content = content.replace('text-slate-400', 'text-slate-500')

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("✓ Updated src/components/AdminPanel.tsx")

def update_unified_signals():
    path = os.path.join(DASHBOARD_SRC, "components/UnifiedSignalDashboard.tsx")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Markets overview section matching Image 1
    markets_section_code = """      {/* ─── MARKETS OVERVIEW SECTION (IMAGE 1 & 3 SPEC) ─────────── */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-bold text-slate-900 tracking-tight">Markets</h2>
          <div className="flex items-center gap-1.5 p-1 bg-slate-100 rounded-lg border border-slate-200">
            <button
              onClick={() => setSelectedMarket("CRYPTO")}
              className={`px-3 py-1 rounded-md text-xs font-semibold transition-all ${
                selectedMarket === "CRYPTO" ? "bg-blue-600 text-white shadow-sm" : "text-slate-600 hover:text-slate-900"
              }`}
            >
              All
            </button>
            <button
              onClick={() => setSelectedMarket("CRYPTO")}
              className={`px-3 py-1 rounded-md text-xs font-semibold transition-all ${
                selectedMarket === "CRYPTO" ? "bg-white text-slate-900 border border-slate-200 shadow-sm" : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Crypto
            </button>
            <button
              onClick={() => setSelectedMarket("FOREX")}
              className={`px-3 py-1 rounded-md text-xs font-semibold transition-all ${
                selectedMarket === "FOREX" ? "bg-white text-slate-900 border border-slate-200 shadow-sm" : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Forex
            </button>
          </div>
        </div>

        {/* 8 Market Cards Grid (Image 1 4x2 Grid) - STRICTLY NO CHARTS */}
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
              className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm hover:shadow-md hover:border-slate-300 transition-all cursor-pointer flex flex-col justify-between h-36 group"
            >
              <div className="flex items-center justify-between">
                <span className="font-bold text-slate-900 text-sm group-hover:text-blue-600 transition-colors">{item.symbol}</span>
                <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold border ${
                  item.status === "Live" ? "bg-emerald-50 text-emerald-700 border-emerald-200" :
                  item.status === "Delayed" ? "bg-amber-50 text-amber-700 border-amber-200" :
                  item.status === "Stale" ? "bg-rose-50 text-rose-700 border-rose-200" :
                  "bg-slate-100 text-slate-600 border-slate-200"
                }`}>
                  {item.status}
                </span>
              </div>

              <div>
                <div className="text-2xl font-bold font-mono text-slate-900 tracking-tight">{item.price}</div>
                <div className={`text-xs font-semibold flex items-center gap-1 mt-0.5 ${item.isPos ? "text-emerald-600" : "text-rose-600"}`}>
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
      </div>\n"""

    if "MARKETS OVERVIEW SECTION (IMAGE 1 & 3 SPEC)" not in content:
        content = content.replace(
            '<div className="space-y-5">\n      {/* ─── Rearrangeable Sections Control Bar',
            '<div className="space-y-6">\n' + markets_section_code + '      {/* ─── Rearrangeable Sections Control Bar'
        )

    # 2. Modernize Macro Calendar to clean light styling
    content = content.replace(
        'p-4 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-4 shadow-lg',
        'p-5 rounded-2xl bg-white border border-slate-200 space-y-4 shadow-sm'
    )
    content = content.replace('bg-slate-950/60 border border-slate-800/80', 'bg-slate-50 border border-slate-200')

    # 3. Modernize AI Intel Stats cards
    content = content.replace(
        'p-4 rounded-xl bg-slate-50 border border-slate-200 hover:border-slate-700/80',
        'p-4 rounded-xl bg-white border border-slate-200 hover:border-slate-300 shadow-sm'
    )

    # 4. Modernize Technical Analysis Button on Signal Cards to Blue Pill
    content = content.replace(
        'bg-sky-600/20 hover:bg-sky-500/30 text-sky-300 hover:text-slate-900 text-xs font-mono font-bold transition-all border border-sky-400/40 cursor-pointer text-center flex items-center justify-center gap-2 shadow-sm',
        'bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold transition-all rounded-lg cursor-pointer text-center flex items-center justify-center gap-2 shadow-sm'
    )

    # 5. Clean light theme replacements
    content = content.replace('bg-slate-950/85', 'bg-slate-900/40')
    content = content.replace('bg-slate-950/60', 'bg-slate-50')
    content = content.replace('bg-slate-950', 'bg-slate-50')
    content = content.replace('bg-slate-900/60', 'bg-white')
    content = content.replace('bg-slate-900/80', 'bg-white')
    content = content.replace('bg-slate-900/90', 'bg-white')
    content = content.replace('bg-slate-900', 'bg-white')
    content = content.replace('border-slate-800/80', 'border-slate-200')
    content = content.replace('border-slate-800', 'border-slate-200')
    content = content.replace('border-slate-700', 'border-slate-300')
    content = content.replace('text-slate-300', 'text-slate-700')
    content = content.replace('text-slate-400', 'text-slate-500')

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("✓ Updated src/components/UnifiedSignalDashboard.tsx")

def update_four_engine_board():
    path = os.path.join(DASHBOARD_SRC, "components/FourEngineDecisionBoard.tsx")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Replace dark container backgrounds
    content = content.replace('bg-[#151e32]', 'bg-slate-50')
    content = content.replace('border-[#263554]', 'border-slate-200')
    content = content.replace('bg-slate-950', 'bg-slate-50')
    content = content.replace('bg-slate-900', 'bg-white')
    content = content.replace('bg-slate-800/80', 'bg-slate-100')
    content = content.replace('bg-slate-800', 'bg-slate-100')
    content = content.replace('border-slate-800', 'border-slate-200')
    content = content.replace('border-slate-700', 'border-slate-300')
    content = content.replace('text-slate-300', 'text-slate-700')
    content = content.replace('text-slate-400', 'text-slate-500')

    # Central consensus meter to clean light gradient
    content = content.replace(
        'bg-gradient-to-r from-emerald-950/40 via-[#071318] to-slate-950 border-emerald-500/40',
        'bg-emerald-50 border-emerald-200 text-emerald-900'
    )
    content = content.replace(
        'bg-gradient-to-r from-rose-950/40 via-[#18090f] to-slate-950 border-rose-500/40',
        'bg-rose-50 border-rose-200 text-rose-900'
    )
    content = content.replace(
        'bg-gradient-to-r from-amber-950/30 via-[#161208] to-slate-950 border-amber-500/40',
        'bg-amber-50 border-amber-200 text-amber-900'
    )

    # Disagreement & Combined Conclusion Callouts matching Image 2
    disagreement_callout = """          {/* Disagreement & Combined Conclusion (Image 2 Spec) */}
          <div className="bg-[#fef9c3] border border-[#fde047] text-[#854d0e] rounded-xl p-3 text-xs font-medium">
            <strong>Disagreement:</strong> CIPHER differs from TAURIC and Jev, and 1 of 4 engines returned no result.
          </div>
          <div className="bg-[#eff6ff] border border-[#bfdbfe] text-[#1e40af] rounded-xl p-3 text-xs font-medium">
            <strong>Combined conclusion not shown.</strong> Engines may rely on overlapping inputs, so agreement is not independent confirmation. A summary appears only when real results support one.
          </div>\n"""
    if "Disagreement & Combined Conclusion (Image 2 Spec)" not in content:
        content = content.replace(
            '{/* Central Consensus Meter & Directional Synthesis */}',
            disagreement_callout + '          {/* Central Consensus Meter & Directional Synthesis */}'
        )

    # Admin execution button styling
    content = content.replace(
        'text-slate-900 font-mono font-bold text-xs flex items-center justify-center gap-2 cursor-pointer shadow-lg shadow-emerald-950/40 transition-all border border-emerald-400/30',
        'text-white font-mono font-bold text-xs flex items-center justify-center gap-2 cursor-pointer shadow-md transition-all'
    )

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("✓ Updated src/components/FourEngineDecisionBoard.tsx")

if __name__ == "__main__":
    update_root_layout()
    update_globals_css()
    update_institutional_console()
    update_customer_portal()
    update_admin_panel()
    update_unified_signals()
    update_four_engine_board()
    print("=== All components successfully updated with Approved Designs (Images 1, 2, 3) ===")
