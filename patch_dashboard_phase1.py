#!/usr/bin/env python3
"""
TAURIC Platform — Phase 1 Dashboard UI Update
Adds Product/Account Category selection and error classification guidance
to /opt/tauric-platform-staging/dashboard/src/components/UnifiedSignalDashboard.tsx
"""

import sys

DASHBOARD_FILE = "/opt/tauric-platform-staging/dashboard/src/components/UnifiedSignalDashboard.tsx"

print("--- Patching UnifiedSignalDashboard.tsx ---")
with open(DASHBOARD_FILE, "r") as f:
    content = f.read()

# 1. Update newConn state to include productType
state_target = '''  const [newConn, setNewConn] = useState({
    marketType: "CRYPTO" as "CRYPTO" | "FOREX",
    exchange: "BITGET",
    customExchangeName: "",
    environment: "DEMO" as "DEMO" | "LIVE",
    environmentPreference: "DEMO" as "DEMO" | "LIVE",'''

state_replacement = '''  const [newConn, setNewConn] = useState({
    marketType: "CRYPTO" as "CRYPTO" | "FOREX",
    exchange: "BITGET",
    productType: "FUTURES_USDT",
    customExchangeName: "",
    environment: "DEMO" as "DEMO" | "LIVE",
    environmentPreference: "DEMO" as "DEMO" | "LIVE",'''

if "productType: \"FUTURES_USDT\"" not in content:
    if state_target in content:
        content = content.replace(state_target, state_replacement, 1)
        print("✓ Added productType to newConn state")
    else:
        print("✗ Target for newConn state not found")
        sys.exit(1)

# 2. Update buildCustomConfig to include product_type
config_target = '''    if (newConn.exchange === "BITGET" && !newConn.baseUrl) {
      return {
        exchange_name: "BITGET",
        market_type: "CRYPTO",
        environment: newConn.environment,
        base_url: "https://api.bitget.com",
        auth_method: "HMAC_SHA256_BASE64",
        key_header: "ACCESS-KEY",
        sign_header: "ACCESS-SIGN",
        time_header: "ACCESS-TIMESTAMP",
        passphrase_header: "ACCESS-PASSPHRASE",
        sign_placement: "HEADER",
        ping_path: "/api/v2/public/time",
        symbols_path: "/api/v2/spot/public/symbols",
        ticker_path: "/api/v2/spot/market/tickers?symbol=BTCUSDT",
        account_path: "/api/v2/spot/account/assets",
        balances_path: "/api/v2/spot/account/assets",
        test_symbol: "BTCUSDT",
      };
    }'''

config_replacement = '''    if (newConn.exchange === "BITGET" && !newConn.baseUrl) {
      const isFutures = (newConn.productType || "FUTURES_USDT") === "FUTURES_USDT";
      return {
        exchange_name: "BITGET",
        market_type: "CRYPTO",
        product_type: newConn.productType || "FUTURES_USDT",
        environment: newConn.environment,
        base_url: "https://api.bitget.com",
        auth_method: "HMAC_SHA256_BASE64",
        key_header: "ACCESS-KEY",
        sign_header: "ACCESS-SIGN",
        time_header: "ACCESS-TIMESTAMP",
        passphrase_header: "ACCESS-PASSPHRASE",
        sign_placement: "HEADER",
        ping_path: "/api/v2/public/time",
        symbols_path: isFutures ? "/api/v2/mix/market/contracts?productType=USDT-FUTURES" : "/api/v2/spot/public/symbols",
        ticker_path: isFutures ? "/api/v2/mix/market/ticker?symbol=BTCUSDT&productType=USDT-FUTURES" : "/api/v2/spot/market/tickers?symbol=BTCUSDT",
        account_path: isFutures ? "/api/v2/mix/account/accounts?productType=USDT-FUTURES" : "/api/v2/spot/account/assets",
        balances_path: isFutures ? "/api/v2/mix/account/accounts?productType=USDT-FUTURES" : "/api/v2/spot/account/assets",
        test_symbol: "BTCUSDT",
      };
    }'''

if config_target in content:
    content = content.replace(config_target, config_replacement, 1)
    print("✓ Updated buildCustomConfig for Bitget product types")
else:
    print("✗ Target for buildCustomConfig not found")
    sys.exit(1)

# 3. Update handleSaveConnection to include product_type in POST & PUT
save_post_target = '''            exchange: effectiveExch,
            market_type: newConn.marketType,
            environment: newConn.environment,
            environment_preference: newConn.environmentPreference,
            is_read_only: newConn.isReadOnly,
            intended_permissions: newConn.intendedPermissions,
            label: newConn.label,
            api_key: newConn.apiKey,
            api_secret: newConn.apiSecret,
            passphrase: newConn.passphrase || undefined,
            custom_config: customConfig,'''

save_post_replacement = '''            exchange: effectiveExch,
            market_type: newConn.marketType,
            product_type: newConn.productType,
            environment: newConn.environment,
            environment_preference: newConn.environmentPreference,
            is_read_only: newConn.isReadOnly,
            intended_permissions: newConn.intendedPermissions,
            label: newConn.label,
            api_key: newConn.apiKey,
            api_secret: newConn.apiSecret,
            passphrase: newConn.passphrase || undefined,
            custom_config: customConfig,'''

if save_post_target in content:
    content = content.replace(save_post_target, save_post_replacement, 1)
    print("✓ Added product_type to save connection payload")
else:
    print("✗ Target for save_post_target not found")
    sys.exit(1)

# In handleTestConnection payload:
test_payload_target = '''      const payload: any = profileId ? { profile_id: profileId, environment: rawEnv || newConn.environment } : {
        exchange: effectiveExch,
        environment: rawEnv || newConn.environment,
        market_type: newConn.marketType,
        intended_permissions: newConn.intendedPermissions,
        api_key: newConn.apiKey.trim(),
        api_secret: newConn.apiSecret.trim(),
        passphrase: newConn.passphrase ? newConn.passphrase.trim() : undefined,
        custom_config: customConfig,
      };'''

test_payload_replacement = '''      const payload: any = profileId ? { profile_id: profileId, environment: rawEnv || newConn.environment, product_type: newConn.productType } : {
        exchange: effectiveExch,
        environment: rawEnv || newConn.environment,
        market_type: newConn.marketType,
        product_type: newConn.productType,
        intended_permissions: newConn.intendedPermissions,
        api_key: newConn.apiKey.trim(),
        api_secret: newConn.apiSecret.trim(),
        passphrase: newConn.passphrase ? newConn.passphrase.trim() : undefined,
        custom_config: customConfig,
      };'''

if test_payload_target in content:
    content = content.replace(test_payload_target, test_payload_replacement, 1)
    print("✓ Added product_type to test connection payload")
else:
    print("✗ Target for test_payload_target not found")
    sys.exit(1)

# 4. Insert Product Category selector in the form
form_target = '''                  {/* STEP 3 & 4: Environment & Intended Permissions */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">'''

form_replacement = '''                  {/* Product Category Selector */}
                  <div>
                    <label className="block text-slate-300 text-xs font-bold uppercase tracking-wider font-mono mb-1.5 flex items-center justify-between">
                      <span className="flex items-center gap-1.5">
                        <span className="w-4 h-4 rounded-full bg-cyan-950 border border-cyan-500/50 text-cyan-300 flex items-center justify-center text-[10px]">P</span>
                        <span>Product / Account Category</span>
                      </span>
                    </label>
                    <select
                      value={newConn.productType}
                      onChange={(e) => setNewConn({ ...newConn, productType: e.target.value })}
                      className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-800 text-white font-mono text-xs"
                    >
                      {newConn.exchange === "BITGET" ? (
                        <>
                          <option value="FUTURES_USDT">USDT-M Futures (Supports Official Demo & Live)</option>
                          <option value="SPOT">Spot V2 (Live Only — No Demo Support)</option>
                        </>
                      ) : newConn.exchange === "BINANCE" ? (
                        <>
                          <option value="SPOT">Spot Trading (Demo & Live)</option>
                          <option value="FUTURES_USDT">USDT-M Futures (Demo & Live)</option>
                        </>
                      ) : newConn.exchange === "BYBIT" ? (
                        <>
                          <option value="UNIFIED">Unified Trading Account - UTA (Demo & Live)</option>
                          <option value="SPOT">Classic Spot (Demo & Live)</option>
                          <option value="FUTURES_USDT">USDT Perpetual (Demo & Live)</option>
                        </>
                      ) : newConn.exchange === "OKX" ? (
                        <>
                          <option value="UNIFIED">Unified Trading Account (Demo & Live)</option>
                        </>
                      ) : newConn.exchange === "MT5" ? (
                        <>
                          <option value="MT5_HEDGING">Hedging Account (Demo & Live)</option>
                          <option value="MT5_NETTING">Netting Account (Demo & Live)</option>
                        </>
                      ) : newConn.exchange === "CUSTOM_FOREX" ? (
                        <>
                          <option value="FOREX_STANDARD">Standard Spread Account (Demo & Live)</option>
                          <option value="FOREX_RAW_SPREAD">Raw Spread / ECN Account (Demo & Live)</option>
                        </>
                      ) : (
                        <option value="SPOT">Spot Trading</option>
                      )}
                    </select>

                    {newConn.exchange === "BITGET" && newConn.productType === "SPOT" && newConn.environment === "DEMO" && (
                      <span className="text-[10px] text-amber-400 block mt-1.5 p-2 rounded bg-amber-950/40 border border-amber-500/40 font-mono">
                        ⚠️ <strong>Notice:</strong> Bitget does not provide paper trading for Spot. Switch to <strong>USDT-M Futures</strong> to test with demo funds, or change environment to <strong>LIVE</strong>.
                      </span>
                    )}
                  </div>

                  {/* STEP 3 & 4: Environment & Intended Permissions */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">'''

if "Product / Account Category" not in content:
    if form_target in content:
        content = content.replace(form_target, form_replacement, 1)
        print("✓ Inserted Product Category selector in connection form")
    else:
        print("✗ Target for form_target not found")
        sys.exit(1)

with open(DASHBOARD_FILE, "w") as f:
    f.write(content)
print("✓ Successfully saved UnifiedSignalDashboard.tsx")
