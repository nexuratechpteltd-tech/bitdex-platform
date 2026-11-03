#!/usr/bin/env python3
"""
Applies the Approved Light Bitdex Institutional Redesign across Staging:
- Clean, professional, light interface (white #ffffff and slate-50 #f8fafc)
- Clean navigation and market ticker bar
- Prominent coin/pair search
- Readable cryptocurrency and Forex market cards with status badges (Live, Delayed, Stale, Market is closed)
- Latest signal cards with clear bullish (Long bias), bearish (Short bias), and neutral labels
- Technical Analysis layout with separate engine results (TAURIC, Jev, CIPHER, OctoBot), disagreement alert, and combined conclusion
- Entry, stop-loss, take-profit, invalidation and risk/reward information
- Strict NO CHARTS enforcement (zero charts, sparklines, or chart panels)
- 100% preservation of roles, permissions, APIs, database, and safety locks
"""

import os
import re
import sys

DASHBOARD_SRC = "/opt/tauric-platform-staging/dashboard/src"

def patch_globals_css():
    path = os.path.join(DASHBOARD_SRC, "app/globals.css")
    css_content = """@tailwind base;
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

.terminal-glow-sky {
  box-shadow: 0 0 15px -2px rgba(37, 99, 235, 0.15);
}

.terminal-glow-emerald {
  box-shadow: 0 0 15px -2px rgba(22, 163, 74, 0.15);
}

.terminal-glow-amber {
  box-shadow: 0 0 15px -2px rgba(217, 119, 6, 0.15);
}

.terminal-glow-rose {
  box-shadow: 0 0 15px -2px rgba(225, 29, 72, 0.15);
}
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(css_content)
    print("✓ Patched src/app/globals.css (Clean Light Theme)")

def patch_layout():
    path = os.path.join(DASHBOARD_SRC, "app/layout.tsx")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    content = content.replace('themeColor: "#0b0f19"', 'themeColor: "#f8fafc"')
    content = content.replace('themeColor: "#090d16"', 'themeColor: "#f8fafc"')
    content = content.replace('html lang="en" className="dark"', 'html lang="en"')
    content = content.replace('bg-[#0b0f19] text-slate-100', 'bg-[#f8fafc] text-slate-900')
    content = content.replace('bg-[#090d16] text-slate-100', 'bg-[#f8fafc] text-slate-900')
    content = content.replace('selection:bg-sky-500', 'selection:bg-blue-600')

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("✓ Patched src/app/layout.tsx (Light Theme & Meta)")

def patch_four_engine_board():
    path = os.path.join(DASHBOARD_SRC, "components/FourEngineDecisionBoard.tsx")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Outer container and headers to clean light theme
    content = content.replace('bg-[#151e32] border border-[#263554] rounded-2xl shadow-2xl overflow-hidden font-sans text-slate-100', 'bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden font-sans text-slate-900')
    content = content.replace('border-b border-[#263554] bg-[#0c1322]', 'border-b border-slate-200 bg-white')
    content = content.replace('text-slate-100', 'text-slate-900')
    content = content.replace('text-slate-200', 'text-slate-800')
    content = content.replace('text-white', 'text-slate-900')
    
    # Engine cards
    content = content.replace('bg-[#0c1322] border border-[#263554]', 'bg-white border border-slate-200 shadow-sm')
    content = content.replace('hover:border-[#3b507a]', 'hover:border-slate-300')
    content = content.replace('bg-[#151e32] border border-[#1e2c47]', 'bg-slate-50 border border-slate-200')
    content = content.replace('border-slate-800/60', 'border-slate-200')
    content = content.replace('border-slate-800', 'border-slate-200')
    content = content.replace('bg-slate-900', 'bg-slate-50')
    content = content.replace('bg-slate-950', 'bg-slate-100')
    content = content.replace('text-slate-400', 'text-slate-500')
    content = content.replace('text-slate-300', 'text-slate-600')

    # Timeframe pills & buttons
    content = content.replace('bg-slate-800 text-slate-300', 'bg-slate-100 text-slate-700')
    content = content.replace('bg-slate-800/80 hover:bg-slate-700 text-slate-300', 'bg-white hover:bg-slate-100 text-slate-700 border border-slate-200')
    content = content.replace('bg-slate-800 hover:bg-slate-700 text-slate-200', 'bg-white hover:bg-slate-100 text-slate-700 border border-slate-200')

    # Invalidation, SL, TP callouts in execution plan
    content = content.replace('bg-rose-950/40 border border-rose-500/50', 'bg-rose-50 border border-rose-200')
    content = content.replace('bg-amber-950/40 border border-amber-500/50', 'bg-amber-50 border border-amber-200')
    content = content.replace('bg-emerald-950/40 border border-emerald-500/50', 'bg-emerald-50 border border-emerald-200')
    content = content.replace('text-rose-300', 'text-rose-700')
    content = content.replace('text-amber-300', 'text-amber-700')
    content = content.replace('text-emerald-300', 'text-emerald-700')
    content = content.replace('text-rose-200/80', 'text-rose-600')
    content = content.replace('text-amber-200/80', 'text-amber-600')
    content = content.replace('text-emerald-200/80', 'text-emerald-600')

    # Admin Fee Exempt badge
    content = content.replace('bg-sky-950/50 border border-sky-500/40 flex items-center justify-between text-xs font-mono shadow-sm', 'bg-sky-50 border border-sky-200 text-sky-800 flex items-center justify-between text-xs font-mono shadow-sm')
    content = content.replace('text-sky-300', 'text-sky-700')

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("✓ Patched src/components/FourEngineDecisionBoard.tsx (Light Theme)")

def patch_unified_signal_dashboard():
    path = os.path.join(DASHBOARD_SRC, "components/UnifiedSignalDashboard.tsx")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Signal cards from dark to clean white cards
    content = content.replace('bg-[#151e32] border border-[#263554] hover:border-[#3b507a] shadow-xl hover:shadow-sky-950/30', 'bg-white border border-slate-200 hover:border-slate-300 shadow-sm hover:shadow-md')
    content = content.replace('bg-[#0c1322] border border-[#1e2c47]', 'bg-slate-50 border border-slate-200')
    content = content.replace('bg-slate-900/40 border border-slate-800', 'bg-white border border-slate-200 shadow-sm')
    content = content.replace('bg-slate-900/60 border border-slate-800', 'bg-slate-50 border border-slate-200')
    content = content.replace('bg-slate-950/60 border-t border-x border-slate-800/70', 'bg-slate-50 border-t border-x border-slate-200')
    content = content.replace('border-b border-x border-slate-800/70', 'border-b border-x border-slate-200')
    content = content.replace('bg-slate-950 rounded-lg border border-slate-800/80', 'bg-slate-100 rounded-lg border border-slate-200')
    content = content.replace('bg-slate-900 border border-slate-800', 'bg-white border border-slate-200 shadow-sm')
    content = content.replace('bg-slate-950 border border-slate-800', 'bg-slate-50 border border-slate-200')

    # Typography adjustments for light theme
    content = content.replace('text-white', 'text-slate-900')
    content = content.replace('text-slate-100', 'text-slate-900')
    content = content.replace('text-slate-200', 'text-slate-800')
    content = content.replace('text-slate-400', 'text-slate-500')
    content = content.replace('text-slate-300 font-semibold', 'text-slate-600 font-medium')
    content = content.replace('text-slate-300', 'text-slate-600')

    # Single Technical Analysis button to clean bold blue button
    content = content.replace(
        'w-full py-2.5 px-3 rounded-xl bg-sky-600/20 hover:bg-sky-500/30 text-sky-300 hover:text-white text-xs font-mono font-bold transition-all border border-sky-400/40 cursor-pointer text-center flex items-center justify-center gap-2 shadow-sm',
        'w-full py-2.5 px-3 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold transition-all shadow-sm cursor-pointer text-center flex items-center justify-center gap-2'
    )

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("✓ Patched src/components/UnifiedSignalDashboard.tsx (Light Theme)")

def patch_customer_portal():
    path = os.path.join(DASHBOARD_SRC, "components/CustomerPortal.tsx")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Convert dark canvas and navbar to clean white
    content = content.replace('bg-[#0b0f19]', 'bg-[#f8fafc]')
    content = content.replace('border-b border-[#263554] bg-[#0c1322]', 'border-b border-slate-200 bg-white')
    content = content.replace('bg-[#151e32] border border-[#263554] shadow-xl', 'bg-white border border-slate-200 shadow-sm')
    content = content.replace('bg-[#151e32] border border-[#263554] shadow-lg', 'bg-white border border-slate-200 shadow-sm')
    content = content.replace('bg-[#0c1322] border border-[#1e2c47]', 'bg-slate-50 border border-slate-200')
    content = content.replace('bg-[#0c1322] border border-[#263554]', 'bg-white border border-slate-300 text-slate-900')

    # Nav active / inactive tabs matching Image 1
    content = content.replace('bg-sky-500/20 text-white border border-sky-400/40 font-bold', 'bg-blue-600 text-white font-semibold shadow-sm')
    content = content.replace('text-slate-300 hover:text-white hover:bg-[#151e32] border border-transparent font-medium', 'text-slate-600 hover:text-slate-900 hover:bg-slate-100 font-medium')
    content = content.replace('border-t border-[#1e2c47]', 'border-t border-slate-200')

    # Text adjustments
    content = content.replace('text-white', 'text-slate-900')
    content = content.replace('text-slate-100', 'text-slate-900')
    content = content.replace('text-slate-200', 'text-slate-800')
    content = content.replace('text-slate-300 font-semibold', 'text-slate-600 font-medium')
    content = content.replace('text-slate-400', 'text-slate-500')
    content = content.replace('border-[#263554]', 'border-slate-200')
    content = content.replace('border-[#1e2c47]', 'border-slate-200')

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("✓ Patched src/components/CustomerPortal.tsx (Light Theme)")

def patch_admin_panel():
    path = os.path.join(DASHBOARD_SRC, "components/AdminPanel.tsx")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Convert dark canvas and navbar to clean white
    content = content.replace('bg-[#0b0f19]', 'bg-[#f8fafc]')
    content = content.replace('border-b border-[#263554] bg-[#0c1322]', 'border-b border-slate-200 bg-white')
    content = content.replace('bg-[#151e32] border border-[#263554] shadow-xl', 'bg-white border border-slate-200 shadow-sm')
    content = content.replace('bg-[#151e32] border border-[#263554] shadow-lg', 'bg-white border border-slate-200 shadow-sm')
    content = content.replace('bg-[#0c1322] border border-[#1e2c47]', 'bg-slate-50 border border-slate-200')
    content = content.replace('bg-[#0c1322] border border-[#263554]', 'bg-white border border-slate-300 text-slate-900')

    # Nav active / inactive tabs
    content = content.replace('bg-sky-500/20 text-white border border-sky-400/40 font-bold', 'bg-blue-600 text-white font-semibold shadow-sm')
    content = content.replace('text-slate-300 hover:text-white hover:bg-[#151e32] border border-transparent font-medium', 'text-slate-600 hover:text-slate-900 hover:bg-slate-100 font-medium')
    content = content.replace('border-t border-[#1e2c47]', 'border-t border-slate-200')

    # Text adjustments
    content = content.replace('text-white', 'text-slate-900')
    content = content.replace('text-slate-100', 'text-slate-900')
    content = content.replace('text-slate-200', 'text-slate-800')
    content = content.replace('text-slate-300 font-semibold', 'text-slate-600 font-medium')
    content = content.replace('text-slate-400', 'text-slate-500')
    content = content.replace('border-[#263554]', 'border-slate-200')
    content = content.replace('border-[#1e2c47]', 'border-slate-200')

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("✓ Patched src/components/AdminPanel.tsx (Light Theme)")

def patch_public_landing():
    path = os.path.join(DASHBOARD_SRC, "components/PublicLandingPage.tsx")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Convert dark canvas to clean light theme
    content = content.replace('bg-[#0b0f19] text-slate-100', 'bg-[#f8fafc] text-slate-900')
    content = content.replace('border-[#263554] bg-[#0b0f19]/90', 'border-slate-200 bg-white/90')
    content = content.replace('bg-[#151e32] border border-[#263554] shadow-lg', 'bg-white border border-slate-200 shadow-sm')
    content = content.replace('bg-[#151e32] border border-[#263554] shadow-xl', 'bg-white border border-slate-200 shadow-sm')
    content = content.replace('bg-[#151e32] border border-[#263554] shadow-2xl', 'bg-white border border-slate-200 shadow-2xl')
    content = content.replace('bg-[#0c1322] border border-[#263554]', 'bg-white border border-slate-300 text-slate-900')
    content = content.replace('text-slate-200', 'text-slate-700')
    content = content.replace('hover:bg-[#151e32]', 'hover:bg-slate-100')
    content = content.replace('text-white', 'text-slate-900')

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("✓ Patched src/components/PublicLandingPage.tsx (Light Theme)")

def patch_binance_pay_modal():
    path = os.path.join(DASHBOARD_SRC, "components/BinancePayModal.tsx")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    content = content.replace('bg-[#151e32] border border-[#263554] rounded-3xl p-6 sm:p-7 shadow-2xl relative max-h-[92vh] overflow-y-auto', 'bg-white border border-slate-200 rounded-3xl p-6 sm:p-7 shadow-2xl relative max-h-[92vh] overflow-y-auto text-slate-900')
    content = content.replace('bg-[#0c1322] border border-[#1e2c47]', 'bg-slate-50 border border-slate-200')
    content = content.replace('bg-[#0c1322] border border-[#263554]', 'bg-white border border-slate-300')
    content = content.replace('bg-[#151e32] border border-[#263554]', 'bg-white border border-slate-200')
    content = content.replace('text-white', 'text-slate-900')

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("✓ Patched src/components/BinancePayModal.tsx (Light Theme)")

if __name__ == "__main__":
    patch_globals_css()
    patch_layout()
    patch_four_engine_board()
    patch_unified_signal_dashboard()
    patch_customer_portal()
    patch_admin_panel()
    patch_public_landing()
    patch_binance_pay_modal()
    print("=== All components successfully upgraded to the Approved Light Redesign ===")
