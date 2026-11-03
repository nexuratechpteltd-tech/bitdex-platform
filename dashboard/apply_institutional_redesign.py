#!/usr/bin/env python3
"""
Comprehensive Institutional UI/UX Redesign Script for Bitdex Staging.
Applies Navy Deep-Slate palette across all frontend components:
  --background: #0b0f19
  --surface-card: #151e32 (border: #263554)
  --surface-well: #0c1322 (border: #1e2c47)
  Text: High-contrast white / #f8fafc and #cbd5e1 (WCAG AA compliant)
  NO CHARTS: Preserves purely tabular/matrix/badge data.
"""

import os
import re
import sys

DASHBOARD_SRC = "/opt/tauric-platform-staging/dashboard/src"

def patch_layout():
    path = os.path.join(DASHBOARD_SRC, "app/layout.tsx")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    content = content.replace('themeColor: "#090d16"', 'themeColor: "#0b0f19"')
    content = content.replace('bg-[#090d16] text-slate-100', 'bg-[#0b0f19] text-slate-100')
    content = content.replace('selection:bg-purple-600', 'selection:bg-sky-500')

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("✓ Patched src/app/layout.tsx")

def patch_binance_pay_modal():
    path = os.path.join(DASHBOARD_SRC, "components/BinancePayModal.tsx")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Outer modal card
    content = content.replace(
        'w-full max-w-lg bg-slate-900 border border-slate-800 rounded-3xl p-6 sm:p-7 shadow-2xl relative max-h-[92vh] overflow-y-auto',
        'w-full max-w-lg bg-[#151e32] border border-[#263554] rounded-3xl p-6 sm:p-7 shadow-2xl relative max-h-[92vh] overflow-y-auto'
    )
    # Buttons and wells
    content = content.replace('bg-slate-950/60 border-slate-800 text-slate-400 hover:bg-slate-800/60', 'bg-[#0c1322] border border-[#1e2c47] text-slate-300 hover:border-[#3b507a]')
    content = content.replace('bg-slate-950/80 border border-slate-800', 'bg-[#0c1322] border border-[#1e2c47]')
    content = content.replace('bg-slate-950 border border-slate-800', 'bg-[#0c1322] border border-[#1e2c47]')
    content = content.replace('bg-slate-950 border border-slate-700', 'bg-[#0c1322] border border-[#263554]')
    content = content.replace('bg-slate-900 border border-slate-800', 'bg-[#151e32] border border-[#263554]')
    content = content.replace('text-slate-400 hover:text-white transition-colors cursor-pointer p-1 rounded-lg hover:bg-slate-800', 'text-slate-400 hover:text-white transition-colors cursor-pointer p-1 rounded-lg hover:bg-[#1e2c47]')

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("✓ Patched src/components/BinancePayModal.tsx")

def patch_public_landing():
    path = os.path.join(DASHBOARD_SRC, "components/PublicLandingPage.tsx")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Canvas and header
    content = content.replace('min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-purple-500 selection:text-white', 'min-h-screen bg-[#0b0f19] text-slate-100 flex flex-col font-sans selection:bg-sky-500 selection:text-white')
    content = content.replace('sticky top-0 z-40 w-full border-b border-slate-800/80 bg-slate-950/90 backdrop-blur-md', 'sticky top-0 z-40 w-full border-b border-[#263554] bg-[#0b0f19]/90 backdrop-blur-md')
    content = content.replace('hover:text-white hover:bg-slate-900 border border-slate-800', 'hover:text-white hover:bg-[#151e32] border border-[#263554]')
    content = content.replace('bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-200', 'bg-[#151e32] hover:bg-[#1a2642] border border-[#263554] text-slate-200')

    # Hero & feature cards
    content = content.replace('bg-slate-900/60 border border-slate-800', 'bg-[#151e32] border border-[#263554] shadow-lg')
    content = content.replace('bg-slate-900/20', 'bg-[#0b0f19]')
    content = content.replace('bg-slate-900 border border-slate-800', 'bg-[#151e32] border border-[#263554] shadow-xl')
    content = content.replace('bg-slate-900 border border-slate-700 shadow-2xl', 'bg-[#151e32] border border-[#263554] shadow-2xl')
    content = content.replace('bg-slate-950 border border-slate-700', 'bg-[#0c1322] border border-[#263554]')
    content = content.replace('bg-slate-950 border border-slate-800', 'bg-[#0c1322] border border-[#1e2c47]')

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("✓ Patched src/components/PublicLandingPage.tsx")

def patch_institutional_console():
    path = os.path.join(DASHBOARD_SRC, "components/InstitutionalConsole.tsx")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Active job banner & forex bar
    content = content.replace('bg-slate-950 border-b border-amber-500/30', 'bg-[#151e32] border-b border-amber-500/40')
    content = content.replace('bg-slate-900/80 border-b border-purple-500/20', 'bg-[#0c1322] border-b border-purple-500/30')
    content = content.replace('bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl', 'bg-[#151e32] border border-[#263554] rounded-2xl shadow-2xl')
    content = content.replace('bg-slate-950/70', 'bg-[#0c1322]')
    content = content.replace('bg-slate-950 border border-slate-800', 'bg-[#0c1322] border border-[#1e2c47]')
    content = content.replace('bg-slate-900 border border-slate-800', 'bg-[#151e32] border border-[#263554]')

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("✓ Patched src/components/InstitutionalConsole.tsx")

def patch_customer_portal():
    path = os.path.join(DASHBOARD_SRC, "components/CustomerPortal.tsx")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Replace outer container cards (bg-slate-900 border border-slate-800) with Navy Deep-Slate elevated cards
    content = content.replace("bg-slate-900 border border-slate-800", "bg-[#151e32] border border-[#263554] shadow-xl")
    content = content.replace("bg-slate-900/60 border border-slate-800", "bg-[#151e32] border border-[#263554] shadow-lg")

    # 2. Replace nested wells (bg-slate-950 border border-slate-800/80, etc.)
    content = content.replace("bg-slate-950 border border-slate-800/80", "bg-[#0c1322] border border-[#1e2c47]")
    content = content.replace("bg-slate-950/70 border border-slate-800/80", "bg-[#0c1322] border border-[#1e2c47]")
    content = content.replace("bg-slate-950 border border-slate-800", "bg-[#0c1322] border border-[#1e2c47]")
    content = content.replace("bg-slate-950/80 border border-slate-800", "bg-[#0c1322] border border-[#1e2c47]")

    # 3. Replace inputs
    content = content.replace("bg-slate-950 border border-slate-700", "bg-[#0c1322] border border-[#263554]")

    # 4. Dividers
    content = content.replace("border-b border-slate-800", "border-b border-[#263554]")
    content = content.replace("border-t border-slate-800", "border-t border-[#263554]")
    content = content.replace("divide-y divide-slate-800/60", "divide-y divide-[#1e2c47]")
    content = content.replace("divide-y divide-slate-800", "divide-y divide-[#1e2c47]")

    # 5. Muted labels to readable
    content = re.sub(r'text-slate-500 font-mono text-\[10px\]', 'text-slate-300 font-semibold font-mono text-[10px]', content)
    content = re.sub(r'text-slate-500 font-mono text-\[11px\]', 'text-slate-300 font-semibold font-mono text-[11px]', content)
    content = re.sub(r'text-\[11px\] text-slate-500 font-mono', 'text-[11px] text-slate-300 font-semibold font-mono', content)
    content = re.sub(r'text-\[10px\] text-slate-500 font-mono', 'text-[10px] text-slate-300 font-semibold font-mono', content)

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("✓ Patched src/components/CustomerPortal.tsx")

def patch_admin_panel():
    path = os.path.join(DASHBOARD_SRC, "components/AdminPanel.tsx")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Replace outer container cards
    content = content.replace("bg-slate-900 border border-slate-800", "bg-[#151e32] border border-[#263554] shadow-xl")
    content = content.replace("bg-slate-900/60 border border-slate-800", "bg-[#151e32] border border-[#263554] shadow-lg")

    # 2. Replace nested wells
    content = content.replace("bg-slate-950 border border-slate-800", "bg-[#0c1322] border border-[#1e2c47]")
    content = content.replace("bg-slate-950/70 border border-slate-800", "bg-[#0c1322] border border-[#1e2c47]")

    # 3. Replace inputs
    content = content.replace("bg-slate-950 border border-slate-700", "bg-[#0c1322] border border-[#263554]")

    # 4. Dividers and table lines
    content = content.replace("border-b border-slate-800", "border-b border-[#263554]")
    content = content.replace("border-t border-slate-800", "border-t border-[#263554]")
    content = content.replace("divide-y divide-slate-800/60", "divide-y divide-[#1e2c47]")
    content = content.replace("divide-y divide-slate-800", "divide-y divide-[#1e2c47]")

    # 5. Table rows hover
    content = content.replace("hover:bg-slate-950/40", "hover:bg-[#0c1322]/80")
    content = content.replace("hover:bg-slate-950/60", "hover:bg-[#0c1322]/80")

    # 6. Table headers
    content = content.replace("text-[11px] text-slate-400 border-b border-[#263554]", "text-[11px] text-slate-300 font-bold uppercase border-b border-[#263554]")

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("✓ Patched src/components/AdminPanel.tsx")

if __name__ == "__main__":
    patch_layout()
    patch_binance_pay_modal()
    patch_public_landing()
    patch_institutional_console()
    patch_customer_portal()
    patch_admin_panel()
    print("=== All components successfully upgraded to Navy Deep-Slate palette ===")
