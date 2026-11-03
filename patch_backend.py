import re
import os
import sys

# ─────────────────────────────────────────────────────────────────────────────
# 1. PATCH exchange_framework.py
# ─────────────────────────────────────────────────────────────────────────────
EF_PATH = "/opt/tauric-platform-staging/backend/app/services/exchange_framework.py"
with open(EF_PATH, "r", encoding="utf-8") as f:
    c = f.read()

# A. Add MarketType enum if missing
if "class MarketType" not in c:
    market_type_code = '''class MarketType(str, Enum):
    CRYPTO = "CRYPTO"
    FOREX = "FOREX"


'''
    c = c.replace("class ExchangeId(str, Enum):", market_type_code + "class ExchangeId(str, Enum):")

# B. Add MT5 and CUSTOM_FOREX to ExchangeId
if 'MT5 = "MT5"' not in c:
    c = c.replace('CUSTOM = "CUSTOM"', 'CUSTOM = "CUSTOM"\n    MT5 = "MT5"\n    CUSTOM_FOREX = "CUSTOM_FOREX"')

# C. Update CredentialVault.save_profile
old_save_sig = '''    def save_profile(
        self,
        exchange: str,
        environment: str = "DEMO",
        label: str = "",
        api_key: str = "",
        api_secret: str = "",
        passphrase: Optional[str] = None,
        custom_config: Optional[Dict[str, Any]] = None,
        environment_preference: Optional[str] = None,
        is_read_only: bool = True
    ) -> Dict[str, Any]:'''

new_save_sig = '''    def save_profile(
        self,
        exchange: str,
        environment: str = "DEMO",
        label: str = "",
        api_key: str = "",
        api_secret: str = "",
        passphrase: Optional[str] = None,
        custom_config: Optional[Dict[str, Any]] = None,
        environment_preference: Optional[str] = None,
        is_read_only: bool = True,
        market_type: str = "CRYPTO",
        intended_permissions: Optional[List[str]] = None
    ) -> Dict[str, Any]:'''

if old_save_sig in c:
    c = c.replace(old_save_sig, new_save_sig)

old_save_body = '''        # Validate master key availability
        get_vault_master_key()

        exchange_clean = exchange.upper()
        environment_clean = environment.upper()
        pref_clean = (environment_preference or environment_clean).upper()'''

new_save_body = '''        # Validate master key availability
        get_vault_master_key()

        market_type_clean = (market_type or "CRYPTO").strip().upper()
        if market_type_clean not in ("CRYPTO", "FOREX"):
            raise ValueError(f"Invalid market_type '{market_type}'. Must be CRYPTO or FOREX.")

        exchange_clean = exchange.upper()
        crypto_exchanges = {"BITGET", "BINANCE", "BYBIT", "COINBASE", "OKX", "KRAKEN", "CUSTOM"}
        forex_brokers = {"MT5", "CUSTOM_FOREX"}

        if market_type_clean == "CRYPTO" and exchange_clean not in crypto_exchanges:
            raise ValueError(f"Provider '{exchange_clean}' is not a supported cryptocurrency exchange.")
        if market_type_clean == "FOREX" and exchange_clean not in forex_brokers:
            raise ValueError(f"Provider '{exchange_clean}' is not a supported forex broker/platform.")

        environment_clean = environment.upper()
        pref_clean = (environment_preference or environment_clean).upper()'''

if old_save_body in c:
    c = c.replace(old_save_body, new_save_body)

old_profile_dict = '''        self._profiles[profile_id] = {
            "profile_id": profile_id,
            "exchange": exchange_clean,
            "environment": environment_clean,
            "environment_preference": pref_clean,
            "label": label or f"{exchange_clean} Profile",
            "api_key_masked": _mask_key(api_key),
            "_credentials_enc": enc_payload,
            "custom_config": custom_config or {},
            "is_read_only": is_read_only,
            "connection_status": ConnectionStatus.UNTESTED.value,
            "verification_label": ConnectionStatus.UNTESTED.value,
            "demo_verified": False,
            "live_verified": False,
            "created_at_utc": now_iso,
            "last_tested_utc": None,
            "last_status": ConnectionStatus.UNTESTED.value,
            "capabilities_verified": [],
            "endpoint_results": []
        }'''

new_profile_dict = '''        safe_permissions = [p for p in (intended_permissions or (["READ_ACCOUNT", "READ_MARKET"] if is_read_only else ["READ_ACCOUNT", "READ_MARKET", "PLACE_ORDERS", "CANCEL_ORDERS"])) if "WITHDRAW" not in p.upper() and "TRANSFER" not in p.upper()]

        self._profiles[profile_id] = {
            "profile_id": profile_id,
            "exchange": exchange_clean,
            "market_type": market_type_clean,
            "environment": environment_clean,
            "environment_preference": pref_clean,
            "label": label or f"{exchange_clean} Profile",
            "api_key_masked": _mask_key(api_key),
            "_credentials_enc": enc_payload,
            "custom_config": custom_config or {},
            "is_read_only": is_read_only,
            "intended_permissions": safe_permissions,
            "connection_status": ConnectionStatus.UNTESTED.value,
            "verification_label": ConnectionStatus.UNTESTED.value,
            "demo_verified": False,
            "live_verified": False,
            "created_at_utc": now_iso,
            "last_tested_utc": None,
            "last_status": ConnectionStatus.UNTESTED.value,
            "capabilities_verified": [],
            "endpoint_results": [],
            "account_data": None,
            "permission_matrix": None
        }'''

if old_profile_dict in c:
    c = c.replace(old_profile_dict, new_profile_dict)

# D. Update update_profile
old_update_sig = '''    def update_profile(
        self,
        profile_id: str,
        label: Optional[str] = None,
        environment: Optional[str] = None,
        environment_preference: Optional[str] = None,
        is_read_only: Optional[bool] = None,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        passphrase: Optional[str] = None,
        custom_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:'''

new_update_sig = '''    def update_profile(
        self,
        profile_id: str,
        label: Optional[str] = None,
        environment: Optional[str] = None,
        market_type: Optional[str] = None,
        environment_preference: Optional[str] = None,
        is_read_only: Optional[bool] = None,
        intended_permissions: Optional[List[str]] = None,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        passphrase: Optional[str] = None,
        custom_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:'''

if old_update_sig in c:
    c = c.replace(old_update_sig, new_update_sig)

old_update_guard = '''        p = self._profiles.get(profile_id)
        if not p:
            raise KeyError(f"Profile '{profile_id}' not found.")'''

new_update_guard = '''        p = self._profiles.get(profile_id)
        if not p:
            raise KeyError(f"Profile '{profile_id}' not found.")

        # Enforce market_type immutability
        cur_market = p.get("market_type", "CRYPTO")
        if market_type is not None:
            m_clean = market_type.strip().upper()
            if m_clean != cur_market:
                raise ValueError(
                    f"Market type is immutable for saved profiles (current: {cur_market}). "
                    f"To switch to {m_clean}, please create a new connection profile."
                )'''

if old_update_guard in c:
    c = c.replace(old_update_guard, new_update_guard)

old_update_apply = '''        if label:
            p["label"] = label
        p["environment"] = new_env
        p["environment_preference"] = (environment_preference or new_env).upper()
        if is_read_only is not None:
            p["is_read_only"] = is_read_only
        p["api_key_masked"] = _mask_key(new_key)
        p["custom_config"] = new_cfg'''

new_update_apply = '''        if label:
            p["label"] = label
        p["environment"] = new_env
        p["environment_preference"] = (environment_preference or new_env).upper()
        if is_read_only is not None:
            p["is_read_only"] = is_read_only
        if intended_permissions is not None:
            p["intended_permissions"] = [perm for perm in intended_permissions if "WITHDRAW" not in perm.upper() and "TRANSFER" not in perm.upper()]
        p["api_key_masked"] = _mask_key(new_key)
        p["custom_config"] = new_cfg'''

if old_update_apply in c:
    c = c.replace(old_update_apply, new_update_apply)

# E. Update update_verification_results
old_uvr = '''    def update_verification_results(
        self,
        profile_id: str,
        connection_status: str,
        verification_label: str,
        endpoint_results: List[Dict[str, Any]],
        capabilities: List[str]
    ):'''

new_uvr = '''    def update_verification_results(
        self,
        profile_id: str,
        connection_status: str,
        verification_label: str,
        endpoint_results: List[Dict[str, Any]],
        capabilities: List[str],
        account_data: Optional[Dict[str, Any]] = None,
        permission_matrix: Optional[List[Dict[str, Any]]] = None
    ):'''

if old_uvr in c:
    c = c.replace(old_uvr, new_uvr)

old_uvr_body = '''            p["endpoint_results"] = endpoint_results
            p["capabilities_verified"] = capabilities'''

new_uvr_body = '''            p["endpoint_results"] = endpoint_results
            p["capabilities_verified"] = capabilities
            if account_data is not None:
                p["account_data"] = account_data
            if permission_matrix is not None:
                p["permission_matrix"] = permission_matrix'''

if old_uvr_body in c:
    c = c.replace(old_uvr_body, new_uvr_body)

# F. Update _format_public
old_fmt = '''        return {
            "profile_id": p.get("profile_id", ""),
            "exchange": p.get("exchange", ""),
            "environment": p.get("environment", ""),
            "environment_preference": p.get("environment_preference", p.get("environment", "DEMO")),
            "label": p.get("label", ""),
            "api_key_masked": p.get("api_key_masked", "••••••••"),
            "is_read_only": p.get("is_read_only", True),
            "connection_status": p.get("connection_status", p.get("last_status", ConnectionStatus.UNTESTED.value)),
            "verification_label": p.get("verification_label", p.get("connection_status", "UNKNOWN")),
            "demo_verified": p.get("demo_verified", False),
            "live_verified": p.get("live_verified", False),
            "created_at_utc": p.get("created_at_utc", ""),
            "last_tested_utc": p.get("last_tested_utc"),
            "last_status": p.get("connection_status", p.get("last_status", "UNTESTED")),
            "capabilities_verified": p.get("capabilities_verified", []),
            "endpoint_results": p.get("endpoint_results", []),
            "custom_config": p.get("custom_config", {})
        }'''

new_fmt = '''        return {
            "profile_id": p.get("profile_id", ""),
            "exchange": p.get("exchange", ""),
            "market_type": p.get("market_type", "CRYPTO"),
            "environment": p.get("environment", ""),
            "environment_preference": p.get("environment_preference", p.get("environment", "DEMO")),
            "label": p.get("label", ""),
            "api_key_masked": p.get("api_key_masked", "••••••••"),
            "is_read_only": p.get("is_read_only", True),
            "intended_permissions": p.get("intended_permissions", ["READ_ACCOUNT", "READ_MARKET"] if p.get("is_read_only", True) else ["READ_ACCOUNT", "READ_MARKET", "PLACE_ORDERS", "CANCEL_ORDERS"]),
            "connection_status": p.get("connection_status", p.get("last_status", ConnectionStatus.UNTESTED.value)),
            "verification_label": p.get("verification_label", p.get("connection_status", "UNKNOWN")),
            "demo_verified": p.get("demo_verified", False),
            "live_verified": p.get("live_verified", False),
            "created_at_utc": p.get("created_at_utc", ""),
            "last_tested_utc": p.get("last_tested_utc"),
            "last_status": p.get("connection_status", p.get("last_status", "UNTESTED")),
            "capabilities_verified": p.get("capabilities_verified", []),
            "endpoint_results": p.get("endpoint_results", []),
            "account_data": p.get("account_data"),
            "permission_matrix": p.get("permission_matrix"),
            "custom_config": p.get("custom_config", {})
        }'''

if old_fmt in c:
    c = c.replace(old_fmt, new_fmt)

# G. Update get_credentials
old_get_creds = '''        return {
            "exchange": p["exchange"],
            "environment": p["environment"],
            "environment_preference": p.get("environment_preference", p["environment"]),
            "api_key": bundle.get("api_key", ""),
            "api_secret": bundle.get("api_secret", ""),
            "passphrase": bundle.get("passphrase") or None,
            "custom_config": bundle.get("custom_config") or p.get("custom_config") or {}
        }'''

new_get_creds = '''        return {
            "exchange": p["exchange"],
            "market_type": p.get("market_type", "CRYPTO"),
            "environment": p["environment"],
            "environment_preference": p.get("environment_preference", p["environment"]),
            "api_key": bundle.get("api_key", ""),
            "api_secret": bundle.get("api_secret", ""),
            "passphrase": bundle.get("passphrase") or None,
            "custom_config": bundle.get("custom_config") or p.get("custom_config") or {}
        }'''

if old_get_creds in c:
    c = c.replace(old_get_creds, new_get_creds)

with open(EF_PATH, "w", encoding="utf-8") as f:
    f.write(c)

print("✓ Successfully patched CredentialVault in exchange_framework.py")
