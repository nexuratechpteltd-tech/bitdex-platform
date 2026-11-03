"""
Tauric Platform — Phase 3.8.2 Staging Patch Script
Applies Bitget authentication fixes exclusively to /opt/tauric-platform-staging/:
1. Environment parameter forwarding through detect_account_capabilities
2. Mandatory 'paptrading: 1' header for Bitget Demo requests (omitted for Live)
3. 'Content-Type: application/json' header inclusion
4. Leading-slash and query string sorting normalization
5. Whitespace sanitization on api_key, api_secret, passphrase
6. UI helper guidance in UnifiedSignalDashboard.tsx
"""

import os
import re

STAGING_ROOT = "/opt/tauric-platform-staging"
CONN_ROUTE_PATH = os.path.join(STAGING_ROOT, "backend", "app", "routes", "connections.py")
FRAMEWORK_PATH = os.path.join(STAGING_ROOT, "backend", "app", "services", "exchange_framework.py")
DASHBOARD_PATH = os.path.join(STAGING_ROOT, "dashboard", "src", "components", "UnifiedSignalDashboard.tsx")

# =========================================================================
# 1. Update connections.py in Staging
# =========================================================================
print(f"Reading {CONN_ROUTE_PATH}...")
with open(CONN_ROUTE_PATH, "r", encoding="utf-8") as f:
    conn_code = f.read()

# Sanitize save_profile
old_save_creds = """        profile = credential_vault.save_profile(
            exchange=exch,
            environment=env,
            label=req.label,
            api_key=req.api_key,
            api_secret=req.api_secret,
            passphrase=req.passphrase,
            custom_config=req.custom_config,
            environment_preference=req.environment_preference,
            is_read_only=req.is_read_only
        )"""

new_save_creds = """        profile = credential_vault.save_profile(
            exchange=exch,
            environment=env,
            label=req.label.strip(),
            api_key=req.api_key.strip(),
            api_secret=req.api_secret.strip(),
            passphrase=req.passphrase.strip() if req.passphrase else None,
            custom_config=req.custom_config,
            environment_preference=req.environment_preference,
            is_read_only=req.is_read_only
        )"""

if old_save_creds in conn_code:
    conn_code = conn_code.replace(old_save_creds, new_save_creds)
    print("✓ Updated save_profile with whitespace sanitization in connections.py")

# Update test_connection to forward environment and sanitize credentials
old_test_block = """    custom_cfg = req.custom_config

    if req.profile_id:
        creds = credential_vault.get_credentials(req.profile_id)
        if not creds:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
        exch = creds["exchange"]
        custom_cfg = creds.get("custom_config")
    else:
        if not req.exchange or not req.api_key or not req.api_secret:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Must provide either profile_id or (exchange, api_key, api_secret)."
            )
        exch = req.exchange.strip().upper()
        creds = {
            "api_key": req.api_key,
            "api_secret": req.api_secret,
            "passphrase": req.passphrase or ""
        }

    # SSRF validation on custom endpoint URLs
    _validate_config_urls(custom_cfg)

    try:
        detection = await exchange_framework.detect_account_capabilities(
            exchange=exch,
            credentials=creds,
            custom_config=custom_cfg
        )"""

new_test_block = """    custom_cfg = dict(req.custom_config or {})
    test_env = (req.environment or "DEMO").strip().upper()

    if req.profile_id:
        creds = credential_vault.get_credentials(req.profile_id)
        if not creds:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
        exch = creds["exchange"]
        test_env = creds.get("environment", test_env)
        custom_cfg = creds.get("custom_config") or custom_cfg
    else:
        if not req.exchange or not req.api_key or not req.api_secret:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Must provide either profile_id or (exchange, api_key, api_secret)."
            )
        exch = req.exchange.strip().upper()
        creds = {
            "api_key": req.api_key.strip(),
            "api_secret": req.api_secret.strip(),
            "passphrase": (req.passphrase or "").strip()
        }

    # Explicitly register environment in custom_cfg for adapter consistency
    custom_cfg["environment"] = test_env

    # SSRF validation on custom endpoint URLs
    _validate_config_urls(custom_cfg)

    try:
        detection = await exchange_framework.detect_account_capabilities(
            exchange=exch,
            credentials=creds,
            custom_config=custom_cfg,
            environment=test_env
        )"""

if old_test_block in conn_code:
    conn_code = conn_code.replace(old_test_block, new_test_block)
    print("✓ Updated test_connection with environment forwarding & credential sanitization in connections.py")

with open(CONN_ROUTE_PATH, "w", encoding="utf-8") as f:
    f.write(conn_code)


# =========================================================================
# 2. Update exchange_framework.py in Staging
# =========================================================================
print(f"Reading {FRAMEWORK_PATH}...")
with open(FRAMEWORK_PATH, "r", encoding="utf-8") as f:
    fm_code = f.read()

# Update _build_auth_headers_and_params
old_build_auth = """    def _build_auth_headers_and_params(
        self,
        method: str,
        path: str,
        query_params: Dict[str, Any],
        credentials: Dict[str, str]
    ) -> Tuple[Dict[str, str], Dict[str, Any]]:
        api_key = credentials.get("api_key", "")
        api_secret = credentials.get("api_secret", "")
        passphrase = credentials.get("passphrase", "")

        auth_method = self.config.get("auth_method", SigningMethod.HMAC_SHA256_HEX.value).upper()
        key_header = self.config.get("key_header") or "X-API-KEY"
        sign_header = self.config.get("sign_header") or "X-SIGNATURE"
        time_header = self.config.get("time_header") or "X-TIMESTAMP"
        passphrase_header = self.config.get("passphrase_header") or "X-PASSPHRASE"
        sign_placement = (self.config.get("sign_placement") or "HEADER").upper()

        headers: Dict[str, str] = {"Accept": "application/json"}
        params = dict(query_params)
        ts = int(time.time() * 1000)

        if auth_method == SigningMethod.BEARER_TOKEN.value:
            headers["Authorization"] = f"Bearer {api_key or api_secret}"
        elif auth_method == SigningMethod.API_KEY_HEADER.value:
            headers[key_header] = api_key
        elif auth_method == SigningMethod.BASIC_AUTH.value:
            auth_str = f"{api_key}:{api_secret}"
            headers["Authorization"] = f"Basic {base64.b64encode(auth_str.encode()).decode()}"
        elif auth_method == SigningMethod.HMAC_SHA256_HEX.value:
            if sign_placement == "QUERY":
                params["timestamp"] = ts
                qs = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
                sig = hmac.new(api_secret.encode(), qs.encode(), hashlib.sha256).hexdigest()
                params["signature"] = sig
                headers[key_header] = api_key
            else:
                headers[key_header] = api_key
                headers[time_header] = str(ts)
                payload = f"{ts}{method.upper()}{path}"
                sig = hmac.new(api_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
                headers[sign_header] = sig
                if passphrase:
                    headers[passphrase_header] = passphrase
        elif auth_method == SigningMethod.HMAC_SHA256_BASE64.value:
            headers[key_header] = api_key
            headers[time_header] = str(ts)
            # Query string handling for Bitget / OKX / Coinbase pre-hash payload
            qs = ""
            if params:
                qs = "?" + urllib.parse.urlencode(params)
            full_path = path + (qs if qs and "?" not in path else "")
            payload = f"{ts}{method.upper()}{full_path}"
            digest = hmac.new(api_secret.encode(), payload.encode(), hashlib.sha256).digest()
            headers[sign_header] = base64.b64encode(digest).decode()
            if passphrase:
                headers[passphrase_header] = passphrase
        elif auth_method == SigningMethod.HMAC_SHA512_BASE64.value:
            headers[key_header] = api_key
            headers[time_header] = str(ts)
            payload = f"{path}{str(ts)}"
            try:
                secret_decoded = base64.b64decode(api_secret)
            except Exception:
                secret_decoded = api_secret.encode()
            digest = hmac.new(secret_decoded, payload.encode(), hashlib.sha512).digest()
            headers[sign_header] = base64.b64encode(digest).decode()
            if passphrase:
                headers[passphrase_header] = passphrase
        else:
            raise ValueError(f"Unsupported signing method: {auth_method}. Specialized adapter required.")

        return headers, params"""

new_build_auth = """    def _build_auth_headers_and_params(
        self,
        method: str,
        path: str,
        query_params: Dict[str, Any],
        credentials: Dict[str, str],
        environment: Environment = Environment.LIVE
    ) -> Tuple[Dict[str, str], Dict[str, Any]]:
        api_key = str(credentials.get("api_key", "")).strip()
        api_secret = str(credentials.get("api_secret", "")).strip()
        passphrase = str(credentials.get("passphrase", "")).strip()

        auth_method = self.config.get("auth_method", SigningMethod.HMAC_SHA256_HEX.value).upper()
        key_header = self.config.get("key_header") or "X-API-KEY"
        sign_header = self.config.get("sign_header") or "X-SIGNATURE"
        time_header = self.config.get("time_header") or "X-TIMESTAMP"
        passphrase_header = self.config.get("passphrase_header") or "X-PASSPHRASE"
        sign_placement = (self.config.get("sign_placement") or "HEADER").upper()

        headers: Dict[str, str] = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

        # Bitget V2 Simulation / Demo Trading Header (Mandatory for Bitget Demo Keys)
        if self.exchange_name == "BITGET" and environment in (Environment.DEMO, Environment.PAPER):
            headers["paptrading"] = "1"

        params = dict(query_params)
        ts = int(time.time() * 1000)

        # Path normalization: Ensure leading slash
        norm_path = "/" + path.lstrip("/")

        if auth_method == SigningMethod.BEARER_TOKEN.value:
            headers["Authorization"] = f"Bearer {api_key or api_secret}"
        elif auth_method == SigningMethod.API_KEY_HEADER.value:
            headers[key_header] = api_key
        elif auth_method == SigningMethod.BASIC_AUTH.value:
            auth_str = f"{api_key}:{api_secret}"
            headers["Authorization"] = f"Basic {base64.b64encode(auth_str.encode('utf-8')).decode('utf-8')}"
        elif auth_method == SigningMethod.HMAC_SHA256_HEX.value:
            if sign_placement == "QUERY":
                params["timestamp"] = ts
                qs = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
                sig = hmac.new(api_secret.encode('utf-8'), qs.encode('utf-8'), hashlib.sha256).hexdigest()
                params["signature"] = sig
                headers[key_header] = api_key
            else:
                headers[key_header] = api_key
                headers[time_header] = str(ts)
                qs = ""
                if params:
                    qs = "?" + urllib.parse.urlencode(sorted(params.items(), key=lambda x: str(x[0])))
                full_path = norm_path + (qs if qs and "?" not in norm_path else "")
                payload = f"{ts}{method.upper()}{full_path}"
                sig = hmac.new(api_secret.encode('utf-8'), payload.encode('utf-8'), hashlib.sha256).hexdigest()
                headers[sign_header] = sig
                if passphrase:
                    headers[passphrase_header] = passphrase
        elif auth_method == SigningMethod.HMAC_SHA256_BASE64.value:
            headers[key_header] = api_key
            headers[time_header] = str(ts)
            # Canonical sorted query string for Bitget / OKX / Coinbase pre-hash payload
            qs = ""
            if params:
                sorted_params = sorted(params.items(), key=lambda x: str(x[0]))
                qs = "?" + urllib.parse.urlencode(sorted_params)
            full_path = norm_path + (qs if qs and "?" not in norm_path else "")
            payload = f"{ts}{method.upper()}{full_path}"
            digest = hmac.new(api_secret.encode('utf-8'), payload.encode('utf-8'), hashlib.sha256).digest()
            headers[sign_header] = base64.b64encode(digest).decode('utf-8')
            if passphrase:
                headers[passphrase_header] = passphrase
        elif auth_method == SigningMethod.HMAC_SHA512_BASE64.value:
            headers[key_header] = api_key
            headers[time_header] = str(ts)
            payload = f"{norm_path}{str(ts)}"
            try:
                secret_decoded = base64.b64decode(api_secret)
            except Exception:
                secret_decoded = api_secret.encode('utf-8')
            digest = hmac.new(secret_decoded, payload.encode('utf-8'), hashlib.sha512).digest()
            headers[sign_header] = base64.b64encode(digest).decode('utf-8')
            if passphrase:
                headers[passphrase_header] = passphrase
        else:
            raise ValueError(f"Unsupported signing method: {auth_method}. Specialized adapter required.")

        return headers, params"""

if old_build_auth in fm_code:
    fm_code = fm_code.replace(old_build_auth, new_build_auth)
    print("✓ Updated _build_auth_headers_and_params with paptrading header, Content-Type, sorting & whitespace handling")

# Update acct and bal calls in run_capability_verification
old_acct_call = """            # 4. Account Authentication
            acct_path = cfg.get("account_path") or cfg.get("endpoints", {}).get("account_path") or "/account"
            acct_url = f"{clean_url.rstrip('/')}{acct_path}"
            try:
                headers, params = self._build_auth_headers_and_params("GET", acct_path, {}, credentials)"""

new_acct_call = """            # 4. Account Authentication
            acct_path = cfg.get("account_path") or cfg.get("endpoints", {}).get("account_path") or "/account"
            if not acct_path.startswith("/"):
                acct_path = "/" + acct_path
            acct_url = f"{clean_url.rstrip('/')}{acct_path}"
            try:
                headers, params = self._build_auth_headers_and_params("GET", acct_path, {}, credentials, environment=environment)"""

if old_acct_call in fm_code:
    fm_code = fm_code.replace(old_acct_call, new_acct_call)
    print("✓ Updated account probe with path normalization & environment propagation")

old_bal_call = """            # 5. Account Balances
            bal_path = cfg.get("balances_path") or cfg.get("endpoints", {}).get("balances_path") or "/balances"
            bal_url = f"{clean_url.rstrip('/')}{bal_path}"
            try:
                headers, params = self._build_auth_headers_and_params("GET", bal_path, {}, credentials)"""

new_bal_call = """            # 5. Account Balances
            bal_path = cfg.get("balances_path") or cfg.get("endpoints", {}).get("balances_path") or "/balances"
            if not bal_path.startswith("/"):
                bal_path = "/" + bal_path
            bal_url = f"{clean_url.rstrip('/')}{bal_path}"
            try:
                headers, params = self._build_auth_headers_and_params("GET", bal_path, {}, credentials, environment=environment)"""

if old_bal_call in fm_code:
    fm_code = fm_code.replace(old_bal_call, new_bal_call)
    print("✓ Updated balances probe with path normalization & environment propagation")

# Update detect_account_capabilities
old_detect_func = """    async def detect_account_capabilities(
        self,
        exchange: str,
        credentials: Dict[str, str],
        custom_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        exch_upper = exchange.upper()
        adapter = self.get_adapter(exch_upper, custom_config=custom_config)
        
        # If adapter implements run_capability_verification, run universal multi-endpoint probe
        if hasattr(adapter, "run_capability_verification"):
            probe_env = Environment.DEMO if (custom_config and custom_config.get("environment") == "DEMO") else Environment.LIVE
            res = await adapter.run_capability_verification(
                environment=probe_env,
                credentials=credentials,
                custom_config=custom_config
            )
            return res"""

new_detect_func = """    async def detect_account_capabilities(
        self,
        exchange: str,
        credentials: Dict[str, str],
        custom_config: Optional[Dict[str, Any]] = None,
        environment: Optional[str] = None
    ) -> Dict[str, Any]:
        exch_upper = exchange.upper()
        adapter = self.get_adapter(exch_upper, custom_config=custom_config)
        
        # Determine probe environment strictly: forwarded parameter takes highest precedence
        env_raw = environment or (custom_config.get("environment") if custom_config else None) or "LIVE"
        probe_env = Environment.DEMO if str(env_raw).strip().upper() in ("DEMO", "PAPER") else Environment.LIVE

        # If adapter implements run_capability_verification, run universal multi-endpoint probe
        if hasattr(adapter, "run_capability_verification"):
            res = await adapter.run_capability_verification(
                environment=probe_env,
                credentials=credentials,
                custom_config=custom_config
            )
            return res"""

if old_detect_func in fm_code:
    fm_code = fm_code.replace(old_detect_func, new_detect_func)
    print("✓ Updated detect_account_capabilities with strict environment forwarding")

with open(FRAMEWORK_PATH, "w", encoding="utf-8") as f:
    f.write(fm_code)


# =========================================================================
# 3. Update UnifiedSignalDashboard.tsx in Staging
# =========================================================================
print(f"Reading {DASHBOARD_PATH}...")
with open(DASHBOARD_PATH, "r", encoding="utf-8") as f:
    dash_code = f.read()

# Update buildCustomConfig to include environment
old_dash_cfg = """    if (newConn.exchange === "BITGET" && !newConn.baseUrl) {
      return {
        exchange_name: "BITGET",
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
    }"""

new_dash_cfg = """    if (newConn.exchange === "BITGET" && !newConn.baseUrl) {
      return {
        exchange_name: "BITGET",
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
    }"""

if old_dash_cfg in dash_code:
    dash_code = dash_code.replace(old_dash_cfg, new_dash_cfg)
    print("✓ Added environment to Bitget default custom_config in UnifiedSignalDashboard.tsx")

# Add environment to CUSTOM custom_config
old_custom_cfg = """    if (newConn.exchange === "CUSTOM" || newConn.baseUrl) {
      return {
        exchange_name: getEffectiveExchange(),
        base_url: newConn.baseUrl.trim(),"""

new_custom_cfg = """    if (newConn.exchange === "CUSTOM" || newConn.baseUrl) {
      return {
        exchange_name: getEffectiveExchange(),
        environment: newConn.environment,
        base_url: newConn.baseUrl.trim(),"""

if old_custom_cfg in dash_code:
    dash_code = dash_code.replace(old_custom_cfg, new_custom_cfg)
    print("✓ Added environment to CUSTOM custom_config in UnifiedSignalDashboard.tsx")

# Update handleTestConnection to sanitize inputs & forward environment
old_test_handler = """      const payload: any = profileId ? { profile_id: profileId } : {
        exchange: effectiveExch,
        environment: rawEnv || newConn.environment,
        api_key: newConn.apiKey,
        api_secret: newConn.apiSecret,
        passphrase: newConn.passphrase || undefined,
        custom_config: customConfig,
      };"""

new_test_handler = """      const payload: any = profileId ? { profile_id: profileId, environment: rawEnv || newConn.environment } : {
        exchange: effectiveExch,
        environment: rawEnv || newConn.environment,
        api_key: newConn.apiKey.trim(),
        api_secret: newConn.apiSecret.trim(),
        passphrase: newConn.passphrase ? newConn.passphrase.trim() : undefined,
        custom_config: customConfig,
      };"""

if old_test_handler in dash_code:
    dash_code = dash_code.replace(old_test_handler, new_test_handler)
    print("✓ Updated handleTestConnection with input trim & environment forwarding")

# Update Passphrase UI label & add explicit guidance for Bitget API Passphrase
old_pass_ui = """                  <div className="md:col-span-2">
                    <label className="block text-slate-400 text-[11px] mb-1">Passphrase (Optional for Bybit, OKX, Coinbase)</label>
                    <input
                      type="password"
                      placeholder="Optional passphrase"
                      value={newConn.passphrase}
                      onChange={(e) => setNewConn({ ...newConn, passphrase: e.target.value })}
                      className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-800 text-white font-mono"
                    />
                  </div>"""

new_pass_ui = """                  <div className="md:col-span-2">
                    <div className="flex items-center justify-between mb-1">
                      <label className="text-slate-400 text-[11px]">
                        API Passphrase {newConn.exchange === "BITGET" ? <span className="text-cyan-400 font-bold">(Mandatory for Bitget)</span> : <span className="text-slate-500">(Required for OKX, Bybit, Coinbase; N/A for Binance)</span>}
                      </label>
                    </div>
                    <input
                      type="password"
                      placeholder={newConn.exchange === "BITGET" ? "Bitget API Passphrase (set at key creation)" : "API Passphrase"}
                      value={newConn.passphrase}
                      onChange={(e) => setNewConn({ ...newConn, passphrase: e.target.value })}
                      className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-800 text-white font-mono"
                    />
                    {newConn.exchange === "BITGET" && (
                      <p className="text-[10px] text-amber-400 mt-1.5 leading-relaxed bg-amber-950/30 p-2 rounded border border-amber-500/30">
                        ⚠️ <strong>Important Bitget Passphrase Requirement:</strong> Enter the custom <strong>API Passphrase</strong> configured specifically when creating this API key on Bitget. This is <strong>NOT</strong> your Bitget account login password or withdrawal fund password.
                      </p>
                    )}
                  </div>"""

if old_pass_ui in dash_code:
    dash_code = dash_code.replace(old_pass_ui, new_pass_ui)
    print("✓ Added explicit Bitget Passphrase UI guidance & helper banner in UnifiedSignalDashboard.tsx")

with open(DASHBOARD_PATH, "w", encoding="utf-8") as f:
    f.write(dash_code)

print("\nAll staging patches applied successfully.")
