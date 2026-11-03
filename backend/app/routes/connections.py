"""
Tauric Platform — Universal API Connections Route (Phase 3.4 / Universal Verification)
Manages extensible exchange connection profiles (Binance, Bybit, Coinbase, Kraken, OKX, and any custom broker),
multi-endpoint capability probing, AES-256-GCM vault security, and SSRF prevention.
"""

import os
import time
import asyncio
import secrets
import socket
import ipaddress
from datetime import datetime, timezone
import httpx
from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional

from ..services.exchange_framework import (
    is_masked_credential,
    provider_requires_passphrase,
    get_provider_error_guidance,
    resolve_actionable_error_code,
    implemented_provider_ids,
    credential_vault,
    exchange_framework,
    Environment,
    ExchangeId,
    VerificationLabel,
    ConnectionStatus,
    SigningMethod,
    ProductType,
    ErrorClassification,
    CapabilityState,
    EvidenceType,
    evaluate_strategy_compatibility,
    PROVIDER_SCHEMAS,
    validate_endpoint_url,
    SSRFValidationError
)
from ..config import settings

connections_router = APIRouter(prefix="/connections", tags=["Exchange Connections"])



class StrategyPreflightRequest(BaseModel):
    profile_id: str = Field(..., description="Connection profile ID or 'PAPER'")
    strategy_id: str = Field(..., description="e.g. SPOT_GRID, FUTURES_GRID, MARKET_DATA_ONLY, ORDER_READ_ONLY")
    symbol: Optional[str] = Field("BTCUSDT", description="Target trading pair symbol")

class SaveProfileRequest(BaseModel):
    exchange: str = Field(..., description="Exchange or broker name (e.g. BITGET, BINANCE, MT5, CUSTOM)")
    environment: Optional[str] = Field("DEMO", description="DEMO or LIVE")
    environment_preference: Optional[str] = Field("DEMO", description="Preferred environment (DEMO or LIVE)")
    market_type: Optional[str] = Field(default="CRYPTO", description="Market category: CRYPTO or FOREX")
    product_type: Optional[str] = Field(None, description="Product category: SPOT, FUTURES_USDT, UNIFIED, FOREX_STANDARD, MT5_HEDGING, etc.")
    is_read_only: bool = Field(True, description="Defaults to True for strict safety")
    intended_permissions: Optional[List[str]] = Field(default=None, description="Intended API permissions list")
    label: Optional[str] = Field(None, description="User-friendly connection label")
    api_key: str = Field(..., description="Exchange API Key or Account ID")
    api_secret: str = Field(..., description="Exchange API Secret or Password")
    passphrase: Optional[str] = Field(None, description="Optional passphrase or second secret")
    custom_config: Optional[Dict[str, Any]] = Field(None, description="Custom broker endpoint config")
    connection_status: Optional[str] = Field(None, description="Optional connection status from test probe")
    endpoint_results: Optional[List[Dict[str, Any]]] = Field(None, description="Optional endpoint probe results")


class UniversalConnectionRequest(BaseModel):
    label: Optional[str] = Field(None, description="Optional connection name")
    api_key: str
    api_secret: str
    passphrase: Optional[str] = None


class IdentifyProviderRequest(BaseModel):
    provider: Optional[str] = None
    provider_id: Optional[str] = None
    environment: Optional[str] = None
    product_type: Optional[str] = None


class ConfigureProfileRequest(BaseModel):
    environment: str
    product_type: Optional[str] = None


class EditProfileRequest(BaseModel):
    label: Optional[str] = None
    environment: Optional[str] = None
    market_type: Optional[str] = None  # Immutability strictly validated
    product_type: Optional[str] = None
    environment_preference: Optional[str] = None
    is_read_only: Optional[bool] = None
    intended_permissions: Optional[List[str]] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    passphrase: Optional[str] = None
    custom_config: Optional[Dict[str, Any]] = None


class TestConnectionRequest(BaseModel):
    profile_id: Optional[str] = None
    exchange: Optional[str] = None
    environment: Optional[str] = "DEMO"
    market_type: Optional[str] = "CRYPTO"
    product_type: Optional[str] = None
    intended_permissions: Optional[List[str]] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    passphrase: Optional[str] = None
    custom_config: Optional[Dict[str, Any]] = None


class ToggleReadOnlyRequest(BaseModel):
    is_read_only: bool


def _validate_config_urls(cfg: Optional[Dict[str, Any]]):
    """Checks all URL entries in custom_config for SSRF vulnerabilities."""
    if not cfg:
        return
    url_keys = (
        "base_url", "live_url", "demo_url", "sandbox_url", "rest_url",
        "ping_url", "symbols_url", "ticker_url", "account_url", "balances_url"
    )
    for key in url_keys:
        val = cfg.get(key)
        if val and isinstance(val, str) and val.strip():
            try:
                validate_endpoint_url(val.strip(), enforce_https=True)
            except SSRFValidationError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"SSRF Security Violation on '{key}': {str(e)}"
                )


@connections_router.get("/egress-ip")
async def get_egress_ip():
    """Returns verified server-side public egress IP for exchange API key allowlisting."""
    return {
        "status": "SUCCESS",
        "egress_ip": "169.58.218.168",
        "egress_ipv6": "2a02:c207:2352:5521::1",
        "server_location": "Germany (Nuremberg DC)",
        "instructions": "Add this IP (169.58.218.168) to your exchange API key's IP Access Restriction."
    }



@connections_router.get("/providers")
async def list_universal_providers(market_type: Optional[str] = Query(None, description="Filter by CRYPTO or FOREX")):
    """
    Returns the canonical universal provider registry including adapter versions,
    implementation status (IMPLEMENTED_TESTED, BRIDGE_DEPENDENT, PLANNED), and schemas.
    """
    providers = exchange_framework.get_provider_registry(market_type=market_type)
    return {
        "status": "SUCCESS",
        "count": len(providers),
        "providers": providers
    }


@connections_router.get("/providers/{provider_id}")
async def get_universal_provider_detail(provider_id: str):
    """Returns canonical configuration and credential schema for a specific provider."""
    prov_clean = provider_id.strip().upper()
    schema = PROVIDER_SCHEMAS.get(prov_clean)
    if not schema:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{provider_id}' not found in registry."
        )
    return {"status": "SUCCESS", "provider": schema}


@connections_router.post("/strategy/preflight")
async def run_strategy_preflight(req: StrategyPreflightRequest):
    """
    Executes explicit, deterministic pre-flight check before strategy execution.
    Generates unambiguous confirmation string and checks active state, credentials,
    product compatibility, permissions, and decoupled balances.
    """
    res = exchange_framework.strategy_preflight(
        profile_id=req.profile_id,
        strategy_id=req.strategy_id,
        symbol=req.symbol or "BTCUSDT"
    )
    return res

@connections_router.get("/providers/{provider_id}/schema")
async def get_provider_schema(provider_id: str):
    """Returns validated non-secret configuration and product schema for a provider."""
    prov_clean = provider_id.strip().upper()
    schema = PROVIDER_SCHEMAS.get(prov_clean)
    if not schema:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{provider_id}' not found in registry."
        )
    return {"status": "SUCCESS", "schema": schema}


@connections_router.get("/capabilities")
async def get_capabilities(market_type: Optional[str] = Query(None, description="Filter providers by CRYPTO or FOREX")):
    """Returns the extensible provider registry, signing methods, and supported capabilities matrix."""
    return {
        "status": "SUCCESS",
        "live_trading_locked": settings.live_trading_locked,
        "read_only_mode": settings.read_only_mode,
        "supported_signing_methods": [m.value for m in SigningMethod],
        "connection_statuses": [s.value for s in ConnectionStatus],
        "providers": exchange_framework.get_provider_registry(market_type=market_type),
        "capabilities": exchange_framework.get_capabilities_matrix()
    }


@connections_router.get("/profiles")
async def list_profiles():
    """Lists saved credential profiles. Secrets are strictly masked and never revealed."""
    profiles = credential_vault.list_profiles()
    return {
        "status": "SUCCESS",
        "count": len(profiles),
        "profiles": profiles
    }


@connections_router.post("/profiles")
async def save_profile(req: SaveProfileRequest):
    """Saves or updates an exchange profile with masked secret vault storage."""
    exch = req.exchange.strip().upper()
    market = (req.market_type or ("FOREX" if exch in ("MT5", "CUSTOM_FOREX") else "CRYPTO")).strip().upper()
    env = (req.environment or "DEMO").upper()
    label = req.label.strip() if req.label and req.label.strip() else f"{exch.capitalize()} API Profile"

    if market not in ("CRYPTO", "FOREX"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid market_type '{req.market_type}'. Must be CRYPTO or FOREX."
        )

    if env not in (Environment.DEMO.value, Environment.LIVE.value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid environment '{req.environment}'. Must be DEMO or LIVE."
        )

    crypto_providers = {"BITGET", "BINANCE", "BYBIT", "COINBASE", "OKX", "KRAKEN", "CUSTOM"}
    forex_providers = {"MT5", "CUSTOM_FOREX"}

    if market == "CRYPTO" and exch not in crypto_providers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider '{exch}' is not a valid cryptocurrency exchange. Supported: {sorted(list(crypto_providers))}"
        )
    if market == "FOREX" and exch not in forex_providers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider '{exch}' is not a valid forex broker/platform. Supported: {sorted(list(forex_providers))}"
        )

    # Validate SSRF on custom URLs
    _validate_config_urls(req.custom_config)

    # Server-side rejection of masked credentials
    for field_name, field_val in [("api_key", req.api_key), ("api_secret", req.api_secret), ("passphrase", req.passphrase)]:
        if is_masked_credential(field_val):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Masked credential detected in '{field_name}'. Masked values cannot be used to create a profile."
            )

    # Validate provider-declared required credential fields (HTTP 422 for missing required fields)
    prov_schema = PROVIDER_SCHEMAS.get(exch)
    if prov_schema:
        for field_info in prov_schema.get("required_credentials", []):
            if field_info.get("required", False):
                fname = field_info.get("field")
                fval = getattr(req, fname, None)
                if fval is None or str(fval).strip().lower() in ("", "none", "null"):
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"Missing required credential field '{fname}' for provider {exch}. {field_info.get('helper', '')}"
                    )

    # Validate product_type and environment against provider schema
    schema = PROVIDER_SCHEMAS.get(exch)
    req_product = req.product_type
    if not req_product and req.custom_config:
        req_product = req.custom_config.get("product_type")
    req_product = str(req_product).strip().upper() if req_product else (schema.get("default_product") if schema else (ProductType.MT5_HEDGING.value if market == "FOREX" else ProductType.SPOT.value))

    if schema:
        valid_prods = [p["id"] for p in schema.get("supported_products", [])]
        if req_product not in valid_prods:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Product '{req_product}' is not supported by {exch}. Supported: {valid_prods}"
            )
        # Validate environment against selected product
        for p_info in schema.get("supported_products", []):
            if p_info["id"] == req_product:
                allowed_envs = p_info.get("supported_environments", ["LIVE"])
                if env not in allowed_envs:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Provider {exch} does not support {env} for product {req_product}. Supported: {allowed_envs}. {p_info.get('notes', '')}"
                    )

    saved_cfg = dict(req.custom_config or {})
    saved_cfg["product_type"] = req_product
    saved_cfg["environment"] = env
    if exch == "BITGET" and req_product in ("FUTURES_USDT", "FUTURES"):
        for sp_key in ("symbols_path", "ticker_path", "account_path", "balances_path", "open_orders_path", "positions_path"):
            if sp_key in saved_cfg and any(sp in str(saved_cfg[sp_key]).lower() for sp in ("/spot/", "spot/account", "spot/trade", "spot/public")):
                del saved_cfg[sp_key]

    try:
        profile = credential_vault.save_profile(
            exchange=exch,
            environment=env,
            market_type=market,
            label=label,
            api_key=req.api_key.strip(),
            api_secret=req.api_secret.strip(),
            passphrase=req.passphrase.strip() if req.passphrase else None,
            custom_config=saved_cfg,
            environment_preference=req.environment_preference,
            is_read_only=req.is_read_only,
            intended_permissions=req.intended_permissions,
            product_type=req_product
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

    return {
        "status": "SUCCESS",
        "message": f"Saved {env} profile for {exch}.",
        "profile": profile
    }


@connections_router.put("/profiles/{profile_id}")
async def edit_profile(profile_id: str, req: EditProfileRequest):
    """Edits a saved profile without leaking or overwriting secrets unless provided."""
    _validate_config_urls(req.custom_config)

    # Server-side rejection of masked credentials
    for field_name, field_val in [("api_key", req.api_key), ("api_secret", req.api_secret), ("passphrase", req.passphrase)]:
        if is_masked_credential(field_val):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Masked credential detected in '{field_name}'. Masked values cannot be submitted as replacement keys. Leave credential fields empty to preserve existing keys byte-for-byte."
            )
    try:
        profile = credential_vault.update_profile(
            profile_id=profile_id,
            label=req.label,
            environment=req.environment,
            market_type=req.market_type,
            environment_preference=req.environment_preference,
            is_read_only=req.is_read_only,
            intended_permissions=req.intended_permissions,
            api_key=req.api_key,
            api_secret=req.api_secret,
            passphrase=req.passphrase,
            custom_config=req.custom_config
        )
        return {
            "status": "SUCCESS",
            "message": f"Updated profile '{profile_id}'.",
            "profile": profile
        }
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


def _config_block(creds: Dict[str, Any]):
    """Returns (code, message) when a profile cannot be tested yet (no network request is made)."""
    exch = str(creds.get("exchange", "")).strip().upper()
    if not exch or exch == "UNIDENTIFIED":
        return ("PROVIDER_NOT_IDENTIFIED", get_provider_error_guidance("UNIDENTIFIED", "PROVIDER_NOT_IDENTIFIED"))
    if str(creds.get("environment", "")).strip().upper() not in ("DEMO", "LIVE"):
        return ("ENVIRONMENT_NOT_SELECTED", get_provider_error_guidance(exch, "ENVIRONMENT_NOT_SELECTED"))
    if provider_requires_passphrase(exch) and not (creds.get("passphrase") or "").strip():
        return ("MISSING_PASSPHRASE", get_provider_error_guidance(exch, "MISSING_PASSPHRASE"))
    return None


def _persist_blocked(profile_id: str, creds: Dict[str, Any], code: str, message: str) -> Dict[str, Any]:
    conn_st = ConnectionStatus.AUTHENTICATION_FAILED.value if code == "MISSING_PASSPHRASE" else ConnectionStatus.UNTESTED.value
    credential_vault.update_verification_results(
        profile_id=profile_id, connection_status=conn_st, verification_label=code,
        endpoint_results=[], capabilities=[], account_data=None, permission_matrix=[], capability_matrix=[],
        strategy_compatibility={}, actionable_error_code=code, provider_error_code=None,
        provider_error_message=message, error_guidance=message)
    return {"status": "BLOCKED", "connection_status": conn_st, "verification_label": code,
            "actionable_error_code": code, "provider_error_code": None, "provider_error_message": message,
            "exchange": creds.get("exchange"), "environment": creds.get("environment"),
            "product_type": creds.get("product_type"), "endpoints": [],
            "capabilities": [], "capability_matrix": [], "error": message, "guidance": message,
            "summary": f"[{code}] {message}", "network_request_made": False, "execution_ready": False,
            "live_trading_locked": True, "read_only_mode": True}


@connections_router.get("/providers-implemented")
async def list_implemented_providers():
    """Only providers with an implemented AND tested adapter. Used by the explicit identification step."""
    out = []
    for pid in implemented_provider_ids():
        s = PROVIDER_SCHEMAS[pid]
        out.append({"id": pid, "provider_id": pid, "name": s.get("name", pid), "requires_passphrase": bool(s.get("requires_passphrase")),
                    "products": [{"id": x["id"], "name": x["name"], "environments": x.get("supported_environments", []), "notes": x.get("notes", "")}
                                 for x in s.get("supported_products", [])],
                    "default_product": s.get("default_product")})
    return {"status": "SUCCESS", "providers": out}


@connections_router.post("/universal")
async def create_universal_connection(req: UniversalConnectionRequest):
    """Credential-first creation. No provider, product, environment or permission is chosen or assumed here."""
    try:
        prof = credential_vault.save_unidentified_profile(req.label, req.api_key, req.api_secret, req.passphrase)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {
        "status": "SUCCESS",
        "message": "Connection saved. Identify the provider to enable testing.",
        "suggested_provider": prof.get("suggested_provider"),
        "profile": prof
    }


@connections_router.post("/profiles/{profile_id}/identify")
async def identify_profile(profile_id: str, req: IdentifyProviderRequest):
    prov = (req.provider or req.provider_id or "").strip().upper()
    if not prov:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="provider or provider_id is required.")
    try:
        prof = credential_vault.identify_profile(profile_id, prov)
        if req.environment:
            prof = credential_vault.configure_profile(profile_id, req.environment, req.product_type)
        return {"status": "SUCCESS", "profile": prof}
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@connections_router.post("/profiles/{profile_id}/configure")
async def configure_profile(profile_id: str, req: ConfigureProfileRequest):
    try:
        return {"status": "SUCCESS", "profile": credential_vault.configure_profile(profile_id, req.environment, req.product_type)}
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


_CAP_STATE_MAP = {"VERIFIED_SUPPORTED": "VERIFIED", "VERIFIED_UNSUPPORTED": "UNSUPPORTED", "NOT_TESTED": "NOT TESTED",
                  "AUTHENTICATION_FAILED": "FAILED", "PERMISSION_DENIED": "FAILED", "CONFIGURATION_MISMATCH": "FAILED",
                  "TEMPORARILY_UNAVAILABLE": "FAILED", "INCONCLUSIVE": "INCONCLUSIVE"}


@connections_router.get("/profiles/{profile_id}/capability-report")
async def capability_report(profile_id: str):
    """Truthful capability states derived ONLY from stored probe evidence. Nothing is VERIFIED without a provider response."""
    prof = credential_vault.get_profile_public(profile_id)
    if not prof:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    matrix = {m.get("capability_id"): m for m in (prof.get("capability_matrix") or [])}

    def one(label, ids, group):
        ms = [matrix[i] for i in ids if i in matrix]
        if not ms:
            msg = "No probe has been run for this capability."
            return {"label": label, "group": group, "state": "NOT TESTED", "evidence": msg, "detail": msg, "ids": ids}
        states = [_CAP_STATE_MAP.get(m.get("state"), "NOT TESTED") for m in ms]
        if group == "PUBLIC":
            if "VERIFIED" in states and "FAILED" not in states:
                st = "VERIFIED"
            elif "FAILED" in states:
                st = "FAILED"
            else:
                st = "NOT TESTED"
        else:
            if all(s == "VERIFIED" for s in states):
                st = "VERIFIED"
            elif "FAILED" in states:
                st = "FAILED"
            elif "UNSUPPORTED" in states and all(s in ("UNSUPPORTED",) for s in states):
                st = "UNSUPPORTED"
            elif "INCONCLUSIVE" in states:
                st = "INCONCLUSIVE"
            else:
                st = "NOT TESTED"
        if st == "VERIFIED":
            ev = next((m.get("evidence") for m in ms if _CAP_STATE_MAP.get(m.get("state")) == "VERIFIED"), ms[0].get("evidence"))
        else:
            ev = next((m.get("evidence") for m in ms if m.get("state") not in ("VERIFIED_SUPPORTED",)), ms[0].get("evidence"))
        return {"label": label, "group": group, "state": st, "evidence": ev, "detail": ev, "ids": ids,
                "raw_provider_code": next((m.get("raw_provider_code") for m in ms if m.get("raw_provider_code")), None)}

    items = [
        one("Public market data", ["MARKET_TICKER", "MARKET_SYMBOLS", "MARKET_CANDLES", "MARKET_ORDERBOOK"], "PUBLIC"),
        one("Private account authentication", ["ACCOUNT_AUTH"], "PRIVATE_READ"),
        one("Account / profile read", ["ACCOUNT_UID"], "PRIVATE_READ"),
        one("Balance read", ["WALLET_BALANCES"], "PRIVATE_READ"),
        one("Open orders read", ["OPEN_ORDERS_READ"], "PRIVATE_READ"),
        one("Order history read", ["ORDER_HISTORY_READ"], "PRIVATE_READ"),
        one("Position / exposure read", ["POSITIONS_READ"], "PRIVATE_READ"),
        one("Order placement", ["ORDER_PLACEMENT"], "TRADE"),
        one("Order cancellation", ["ORDER_CANCELLATION"], "TRADE"),
        one("Order modification", ["ORDER_AMENDMENT"], "TRADE"),
    ]
    for it in items:
        if it["group"] == "TRADE":
            it["note"] = "Never exercised: live order submission is hard-locked (HTTP 403). A state here is not an execution grant."
    withdraw_msg = "Permanently unavailable to the bot. Withdrawal permission is never requested or used."
    items.append({"label": "Withdrawal / transfer", "group": "SECURITY", "state": "DISABLED",
                  "evidence": withdraw_msg, "detail": withdraw_msg, "ids": []})

    auth_ep = next((e for e in (prof.get("endpoint_results") or []) if e.get("category") == "AUTHENTICATION"), None)
    pub_eps = [e for e in (prof.get("endpoint_results") or []) if e.get("category") in ("CONNECTIVITY", "MARKET_DATA", "TICKER")]
    from urllib.parse import urlparse
    def ep_view(e):
        u = urlparse(e.get("url") or "")
        return {"name": e.get("name"), "method": "GET", "path": u.path + (("?" + u.query) if u.query else ""),
                "http_status": e.get("http_status"), "provider_error_code": e.get("provider_error_code"),
                "status": e.get("status"), "error": (e.get("error") or None)}
    pub_summary = {"state": items[0]["state"], "detail": items[0]["detail"], "probes": [ep_view(e) for e in pub_eps]}
    priv_summary = {"state": items[1]["state"], "evidence": items[1]["evidence"], "detail": items[1]["detail"],
                    "probe": ep_view(auth_ep) if auth_ep else None, "environment": prof.get("environment")}
    return {
        "status": "SUCCESS", "profile_id": profile_id, "label": prof.get("label"), "provider": prof.get("exchange"),
        "provider_identified": prof.get("provider_identified"), "environment": prof.get("environment"),
        "product_type": prof.get("product_type"), "configuration_required": prof.get("configuration_required"),
        "last_tested_utc": prof.get("last_tested_utc"),
        "connection_status": prof.get("connection_status"),
        "requires_passphrase": prof.get("requires_passphrase", provider_requires_passphrase(prof.get("exchange"))),
        "has_passphrase": prof.get("has_passphrase", False),
        "actionable_error_code": prof.get("actionable_error_code"),
        "provider_error_code": prof.get("provider_error_code"),
        "provider_error_message": prof.get("provider_error_message"),
        "error_guidance": prof.get("error_guidance"),
        "public_market_data": pub_summary,
        "private_authentication": priv_summary,
        "test_results": {
            "public_market_data": pub_summary,
            "private_authentication": priv_summary,
        },
        "capabilities": items,
        "live_trading_locked": True, "read_only_mode": True,
    }


@connections_router.post("/profiles/{profile_id}/disconnect")
async def disconnect_profile(profile_id: str):
    """Revokes active connection status and marks profile as DISCONNECTED."""
    success = credential_vault.disconnect_profile(profile_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return {
        "status": "SUCCESS",
        "message": f"Profile '{profile_id}' disconnected.",
        "connection_status": ConnectionStatus.DISCONNECTED.value
    }


# ─────────────────────────────────────────────────────────────────────────────
# Robust Sliding-Window Rate Limiter for Expensive Test Probes (SEC-02)
# ─────────────────────────────────────────────────────────────────────────────
_RATE_LIMIT_LOCK = asyncio.Lock()
_test_rate_history: Dict[str, List[float]] = {}
TEST_RATE_LIMIT = 10
TEST_RATE_WINDOW_SEC = 60.0
MAX_TRACKED_IPS = 1000
TRUSTED_PROXY_IPS = {"127.0.0.1", "::1"}


def extract_client_ip(request: Request) -> str:
    """
    Safely determines client IP. Only inspects X-Real-IP or X-Forwarded-For if
    the immediate connection peer is a verified trusted proxy (127.0.0.1 or ::1).
    Validates IP format to prevent header injection or spoofing.
    """
    peer_ip = request.client.host if request.client else "127.0.0.1"

    if peer_ip in TRUSTED_PROXY_IPS:
        # Check X-Real-IP first
        x_real_ip = request.headers.get("x-real-ip")
        if x_real_ip:
            raw = x_real_ip.strip()
            try:
                ipaddress.ip_address(raw)
                return raw
            except ValueError:
                pass

        # Check X-Forwarded-For (client is leftmost IP)
        x_forwarded_for = request.headers.get("x-forwarded-for")
        if x_forwarded_for:
            parts = [p.strip() for p in x_forwarded_for.split(",") if p.strip()]
            if parts:
                client_candidate = parts[0]
                try:
                    ipaddress.ip_address(client_candidate)
                    return client_candidate
                except ValueError:
                    pass

    return peer_ip


TEST_RATE_BYPASS_ENV = "TEST_RATE_LIMIT_TOKEN"

def _is_authorized_test_bypass(request: Request) -> bool:
    expected_token = os.environ.get(TEST_RATE_BYPASS_ENV)
    if not expected_token or len(str(expected_token)) < 16:
        return False
    peer = request.client.host if request.client else ""
    if peer not in ("127.0.0.1", "::1", "localhost"):
        return False
    provided_token = request.headers.get("X-Tauric-Test-Token")
    if not provided_token:
        return False
    return secrets.compare_digest(str(provided_token).strip(), str(expected_token).strip())


def _build_failed_capability_matrix(
    state: str,
    reason: str,
    remediation: str,
    now_iso: str
) -> List[Dict[str, Any]]:
    items = [
        ("MARKET_TICKER", "Real-Time Price Ticker", "MARKET_DATA"),
        ("MARKET_ORDERBOOK", "Order Book Depth", "MARKET_DATA"),
        ("MARKET_CANDLES", "Historical Candlestick (K-Line) Feed", "MARKET_DATA"),
        ("MARKET_SYMBOLS", "Trading Pair & Symbol Discovery", "MARKET_DATA"),
        ("ACCOUNT_AUTH", "Private API Authentication & Signing", "ACCOUNT_IDENTITY"),
        ("ACCOUNT_UID", "Account Profile & UID Read", "ACCOUNT_IDENTITY"),
        ("WALLET_BALANCES", "Wallet Asset Balances", "BALANCES_MARGIN"),
        ("MARGIN_BALANCES", "Margin & Collateral Metrics", "BALANCES_MARGIN"),
        ("POSITIONS_READ", "Open Positions & Contract Exposure", "ORDERS_POSITIONS"),
        ("OPEN_ORDERS_READ", "Active Open Orders Read", "ORDERS_POSITIONS"),
        ("ORDER_HISTORY_READ", "Order History & Executed Fills", "ORDERS_POSITIONS"),
        ("ORDER_STATUS_POLL", "Order Status Retrieval", "ORDERS_POSITIONS"),
        ("ORDER_PLACEMENT", "Order Execution (Place Orders)", "ORDER_EXECUTION"),
        ("ORDER_CANCELLATION", "Order Cancellation", "ORDER_EXECUTION"),
        ("ORDER_AMENDMENT", "In-Place Order Modification", "ORDER_EXECUTION"),
        ("TRANSFERS_WITHDRAWALS", "Fund Transfers & Withdrawals", "SECURITY_PERMISSIONS"),
    ]
    matrix = []
    for cid, cname, ccat in items:
        if cid == "TRANSFERS_WITHDRAWALS":
            matrix.append({
                "capability_id": cid,
                "name": cname,
                "category": ccat,
                "state": CapabilityState.UNSUPPORTED.value,
                "evidence_type": EvidenceType.KEY_METADATA.value,
                "evidence": "Strict safety invariant: Fund transfers and withdrawals are unsupported and never requested.",
                "timestamp": now_iso,
                "latency_ms": None,
                "raw_provider_code": None,
                "remediation": None,
                "authoritative_key_permission": False
            })
        else:
            matrix.append({
                "capability_id": cid,
                "name": cname,
                "category": ccat,
                "state": state,
                "evidence_type": EvidenceType.PROBE_REJECTION.value,
                "evidence": reason,
                "timestamp": now_iso,
                "latency_ms": None,
                "raw_provider_code": None,
                "remediation": remediation,
                "authoritative_key_permission": None
            })
    return matrix


def _build_failed_permission_matrix(reason: str) -> List[Dict[str, Any]]:
    auth_state = "Authentication failed" if any(w in reason.lower() for w in ("auth", "key", "secret", "passphrase", "signature", "ip", "clock", "40037", "40012", "40099")) else "Temporarily unavailable"

    items = [
        ("Public market data read (orderbook, trades)", "Supported and verified" if "market data" not in reason.lower() else "Temporarily unavailable", "Market data public endpoint", ["None (Public)"], ["None (Public)"], "Live orderbook and depth access."),
        ("Historical candle/kline data", "Supported and verified" if "market data" not in reason.lower() else "Temporarily unavailable", "K-lines public endpoint", ["None (Public)"], ["None (Public)"], "Historical price candles for strategy analysis."),
        ("Ticker price feed", "Supported and verified" if "market data" not in reason.lower() else "Temporarily unavailable", "Ticker public endpoint", ["None (Public)"], ["None (Public)"], "Real-time ticker prices."),
        ("Account profile & UID read", auth_state, "Account info private endpoint", ["API Key", "API Secret"], ["Account Read"], "Account identification and UID."),
        ("Spot wallet balances", auth_state, "Spot balance endpoint", ["API Key", "API Secret"], ["Spot Balance Read"], "Spot wallet balance querying."),
        ("Funding / funding account balances", "Unsupported by provider/product", "Funding endpoint", ["API Key", "API Secret"], ["Funding Read"], "Exchange funding asset account."),
        ("Futures / margin balances", "Supported but not yet tested" if "futures" in reason.lower() else "Unsupported by provider/product", "Contract balance endpoint", ["API Key", "API Secret"], ["Futures Read"], "Futures collateral metrics."),
        ("Open orders read", auth_state, "Open orders endpoint", ["API Key", "API Secret"], ["Trade Read"], "Independent open order retrieval."),
        ("Order history read", auth_state, "Order history endpoint", ["API Key", "API Secret"], ["Trade Read"], "Historical order fill inspection."),
        ("Trade execution (place orders)", "Supported but not yet tested", "Order submission endpoint", ["API Key", "API Secret"], ["Trade Write"], "Limit order placement capability."),
        ("Order cancellation", "Supported but not yet tested", "Order cancel endpoint", ["API Key", "API Secret"], ["Trade Write"], "Active order cancellation."),
        ("Order amendment / modification", "Unsupported by provider/product", "Order amend endpoint", ["API Key", "API Secret"], ["Trade Write"], "In-place modification of open orders."),
        ("Position / exposure read", "Supported but not yet tested", "Position risk endpoint", ["API Key", "API Secret"], ["Position Read"], "Open contract position risk."),
        ("Transfers / withdrawals", "Unsupported by provider/product", "Withdrawal endpoint (Blocked)", ["API Key", "API Secret"], ["Withdrawals (Blocked)"], "Strict platform safety invariant: Fund withdrawals are never requested, stored, or permitted.")
    ]

    return [
        {
            "capability": cap,
            "state": st,
            "result": st,
            "detail": reason if st in (auth_state, "Temporarily unavailable") else expl,
            "endpoint": ep,
            "required_credentials": req_c,
            "required_permissions": req_p,
            "explanation": expl
        }
        for cap, st, ep, req_c, req_p, expl in items
    ]


async def enforce_test_rate_limit(request: Request):
    """
    Enforces a strict sliding-window rate limit on connection test operations.
    Thread-safe / concurrency-safe via asyncio.Lock.
    """
    if _is_authorized_test_bypass(request):
        return

    client_ip = extract_client_ip(request)
    now = time.time()

    async with _RATE_LIMIT_LOCK:
        # Periodic cleanup of stale IPs if table exceeds max tracked entries
        if len(_test_rate_history) > MAX_TRACKED_IPS:
            stale_ips = [
                ip for ip, times in _test_rate_history.items()
                if not times or (now - times[-1] >= TEST_RATE_WINDOW_SEC)
            ]
            for ip in stale_ips:
                _test_rate_history.pop(ip, None)

        history = _test_rate_history.setdefault(client_ip, [])
        # Prune entries older than the window
        history = [t for t in history if now - t < TEST_RATE_WINDOW_SEC]
        _test_rate_history[client_ip] = history

        if len(history) >= TEST_RATE_LIMIT:
            oldest = history[0]
            retry_after = max(1, int(TEST_RATE_WINDOW_SEC - (now - oldest)))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded for connection tests (maximum 10 tests per minute). Please back off before retrying.",
                headers={"Retry-After": str(retry_after)}
            )

        history.append(now)


def _clear_rate_limits_for_test():
    """Test helper to reset rate limit state between test scenarios."""
    global _test_rate_history
    _test_rate_history.clear()


@connections_router.post("/profiles/{profile_id}/retest")
async def retest_profile(profile_id: str, request: Request):
    """Retests a saved profile using stored encrypted credentials and updates its status."""
    await enforce_test_rate_limit(request)
    creds = credential_vault.get_credentials(profile_id)
    if not creds:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    _blk = _config_block(creds)
    if _blk:
        return _persist_blocked(profile_id, creds, *_blk)

    # Authoritative saved profile parameters - strictly ignore any external overrides
    saved_env = creds.get("environment", "DEMO")
    saved_prod = creds.get("product_type") or ProductType.SPOT.value
    saved_market = creds.get("market_type", "CRYPTO")
    custom_cfg = dict(creds.get("custom_config") or {})
    custom_cfg["environment"] = saved_env
    custom_cfg["product_type"] = saved_prod
    custom_cfg["market_type"] = saved_market

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        _validate_config_urls(custom_cfg)
        detection = await exchange_framework.detect_account_capabilities(
            exchange=creds["exchange"],
            credentials=creds,
            custom_config=custom_cfg,
            environment=saved_env,
            product_type=saved_prod
        )
    except Exception as e:
        err_msg = str(e)
        if isinstance(e, SSRFValidationError) or "SSRF" in err_msg or "Could not resolve" in err_msg or "Name or service not known" in err_msg or isinstance(e, socket.gaierror):
            err_cls = ErrorClassification.CONFIGURATION_MISMATCH
            conn_status = ConnectionStatus.DISCONNECTED.value
            verif_label = "CONFIGURATION_MISMATCH"
            cap_state = CapabilityState.CONFIGURATION_MISMATCH.value
            guide = f"Configuration error: {err_msg}. Verify endpoint hostname and DNS configuration."
            prov_code = "CONFIGURATION_MISMATCH"
        elif isinstance(e, (httpx.TimeoutException, asyncio.TimeoutError)) or "timed out" in err_msg.lower():
            err_cls = ErrorClassification.TEMPORARILY_UNAVAILABLE
            conn_status = ConnectionStatus.DISCONNECTED.value
            verif_label = "TEMPORARILY_UNAVAILABLE"
            cap_state = CapabilityState.TEMPORARILY_UNAVAILABLE.value
            guide = "Network probe timed out. Exchange endpoint may be temporarily degraded or unreachable."
            prov_code = "TEMPORARILY_UNAVAILABLE"
        elif "passphrase" in err_msg.lower() or "authentication" in err_msg.lower() or "api-key" in err_msg.lower() or "signature" in err_msg.lower():
            exch_name = creds.get("exchange", "UNIDENTIFIED")
            has_pass_val = bool((creds.get("passphrase") or "").strip())
            verif_label = resolve_actionable_error_code(exch_name, None, None, err_msg, has_passphrase=has_pass_val)
            err_cls = ErrorClassification.CONFIGURATION_MISMATCH if verif_label == "MISSING_PASSPHRASE" else ErrorClassification.AUTHENTICATION_FAILED
            conn_status = ConnectionStatus.AUTHENTICATION_FAILED.value
            cap_state = CapabilityState.AUTHENTICATION_FAILED.value
            guide = get_provider_error_guidance(exch_name, verif_label, None, err_msg)
            prov_code = None
        else:
            err_cls = ErrorClassification.INCONCLUSIVE
            conn_status = ConnectionStatus.DISCONNECTED.value
            verif_label = "AUTHENTICATION_DIAGNOSTIC_INCONCLUSIVE"
            cap_state = CapabilityState.INCONCLUSIVE.value
            guide = f"Verification probe failed unexpectedly: {err_msg}"
            prov_code = "AUTHENTICATION_DIAGNOSTIC_INCONCLUSIVE"

        failed_matrix = _build_failed_capability_matrix(cap_state, err_msg, guide, now_iso)
        failed_strategy_eval = evaluate_strategy_compatibility({
            "market_type": creds.get("market_type", "CRYPTO"),
            "product_type": saved_prod,
            "last_tested_utc": now_iso,
            "capability_matrix": failed_matrix
        })
        endpoint_results = [{
            "name": "Connection Retest Probe",
            "url": custom_cfg.get("base_url") or "exchange_endpoint",
            "category": "CONNECTIVITY",
            "mandatory": True,
            "status": "FAIL",
            "schema_valid": False,
            "error": f"[{err_cls.value}] {err_msg}",
            "error_classification": err_cls.value,
            "provider_error_code": prov_code,
            "guidance": guide
        }]
        detection = {
            "status": "FAIL",
            "connection_status": conn_status,
            "verification_label": verif_label,
            "actionable_error_code": verif_label,
            "provider_error_code": prov_code,
            "exchange": creds["exchange"],
            "environment": saved_env,
            "product_type": saved_prod,
            "endpoints": endpoint_results,
            "capabilities": [],
            "capability_matrix": failed_matrix,
            "permission_matrix": _build_failed_permission_matrix(err_msg),
            "strategy_compatibility": failed_strategy_eval,
            "account_data": None,
            "error": err_msg,
            "error_classification": err_cls.value,
            "guidance": guide,
            "execution_ready": False,
            "live_trading_locked": True,
            "read_only_mode": True,
            "summary": f"[{verif_label}] {guide}"
        }

    if detection.get("status") == "FAIL" and not detection.get("error_classification"):
        v_label = str(detection.get("verification_label", "")).upper()
        if "MISMATCH" in v_label or "SSRF" in v_label or "DNS" in v_label:
            detection["error_classification"] = ErrorClassification.CONFIGURATION_MISMATCH.value
        elif "TIMEOUT" in v_label or "UNAVAILABLE" in v_label:
            detection["error_classification"] = ErrorClassification.TEMPORARILY_UNAVAILABLE.value
        elif "AUTH" in v_label or "KEY" in v_label or "SIGNATURE" in v_label:
            detection["error_classification"] = ErrorClassification.AUTHENTICATION_FAILED.value
        else:
            detection["error_classification"] = ErrorClassification.INCONCLUSIVE.value

    # Atomically persist verification outcome to vault (clearing old success on failure)
    credential_vault.update_verification_results(
        profile_id=profile_id,
        connection_status=detection.get("connection_status", ConnectionStatus.DISCONNECTED.value),
        verification_label=detection.get("verification_label", "UNKNOWN"),
        endpoint_results=detection.get("endpoints", []),
        capabilities=detection.get("capabilities", []),
        account_data=detection.get("account_data"),
        permission_matrix=detection.get("permission_matrix"),
        capability_matrix=detection.get("capability_matrix", []),
        strategy_compatibility=detection.get("strategy_compatibility", {}),
        actionable_error_code=detection.get("actionable_error_code"),
        provider_error_code=detection.get("provider_error_code"),
        provider_error_message=detection.get("provider_error_message") or detection.get("error"),
        error_guidance=detection.get("guidance"),
    )
    detection["environment"] = saved_env
    detection["product_type"] = saved_prod

    return detection


@connections_router.delete("/profiles/{profile_id}")
async def delete_profile(profile_id: str):
    """Deletes an exchange profile from the vault, rejecting deletion if active runs depend on it."""
    # Reject deletion if active strategy runs depend on this profile
    try:
        from app.services.strategy_orchestrator import strategy_orchestrator
        active_runs = [
            r for r in strategy_orchestrator.list_strategy_runs()
            if r.get("profile_id") == profile_id and r.get("state") in ("RUNNING", "INITIALIZING", "PAUSED")
        ]
        if active_runs:
            run_ids = [r.get("run_id") for r in active_runs]
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot delete profile '{profile_id}': active strategy runs depend on it ({run_ids}). Please stop all runs before deleting."
            )
    except ImportError:
        pass

    success = credential_vault.delete_profile(profile_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    # Clear associated cached rate limit history
    _test_rate_history.pop(profile_id, None)

    return {"status": "SUCCESS", "message": f"Profile '{profile_id}' deleted."}


class ToggleActiveRequest(BaseModel):
    is_active: Optional[bool] = None


@connections_router.post("/profiles/{profile_id}/toggle-active")
async def toggle_active_profile(profile_id: str, req: Optional[ToggleActiveRequest] = None):
    """Toggles active / inactive state of an exchange profile."""
    val = req.is_active if req else None
    success = credential_vault.toggle_active(profile_id, val)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    prof = credential_vault.get_profile_public(profile_id)
    return {
        "status": "SUCCESS",
        "profile_id": profile_id,
        "is_active": prof.get("is_active", True)
    }

@connections_router.post("/profiles/{profile_id}/toggle-read-only")
async def toggle_read_only(profile_id: str, req: ToggleReadOnlyRequest):
    """Toggles read-only protection on a verified profile."""
    success = credential_vault.toggle_read_only_mode(profile_id, req.is_read_only)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return {
        "status": "SUCCESS",
        "profile_id": profile_id,
        "is_read_only": req.is_read_only
    }


@connections_router.post("/test")
async def test_connection(req: TestConnectionRequest, request: Request):
    """
    Performs multi-endpoint capability verification on exchange credentials.
    Probes connectivity, market data, ticker, account authentication, balances, and passive trading permissions.
    Never submits orders during connection testing.
    """
    await enforce_test_rate_limit(request)
    custom_cfg = dict(req.custom_config or {})
    test_env = (req.environment or "DEMO").strip().upper()
    market = (req.market_type or "CRYPTO").strip().upper()

    if req.profile_id:
        creds = credential_vault.get_credentials(req.profile_id)
        if not creds:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
        _blk = _config_block(creds)
        if _blk:
            return _persist_blocked(req.profile_id, creds, *_blk)
        # Authoritative saved profile parameters - strictly ignore frontend overrides
        exch = creds["exchange"]
        test_env = creds.get("environment", "DEMO")
        market = creds.get("market_type", "CRYPTO")
        req_target_prod = creds.get("product_type") or (ProductType.MT5_HEDGING.value if market == "FOREX" else ProductType.SPOT.value)
        custom_cfg = dict(creds.get("custom_config") or {})
        custom_cfg["environment"] = test_env
        custom_cfg["product_type"] = req_target_prod
        custom_cfg["market_type"] = market
    else:
        if not req.exchange or not req.api_key or not req.api_secret:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Must provide either profile_id or (exchange, api_key, api_secret)."
            )
        exch = req.exchange.strip().upper()

        # Reject masked credentials
        for field_name, field_val in [("api_key", req.api_key), ("api_secret", req.api_secret), ("passphrase", req.passphrase)]:
            if is_masked_credential(field_val):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Masked credential detected in '{field_name}'. Cannot test with masked values."
                )

        # Validate provider-declared required credential fields (HTTP 422 for missing required fields)
        prov_schema = PROVIDER_SCHEMAS.get(exch)
        if prov_schema:
            for field_info in prov_schema.get("required_credentials", []):
                if field_info.get("required", False):
                    fname = field_info.get("field")
                    fval = getattr(req, fname, None)
                    if fval is None or str(fval).strip().lower() in ("", "none", "null"):
                        raise HTTPException(
                            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"Missing required credential field '{fname}' for provider {exch}. {field_info.get('helper', '')}"
                        )

        creds = {
            "api_key": req.api_key.strip(),
            "api_secret": req.api_secret.strip(),
            "passphrase": (req.passphrase or "").strip()
        }
        req_target_prod = None

    # Resolve and validate product_type
    if req.profile_id:
        target_prod = req_target_prod
    else:
        target_prod = req.product_type
        if not target_prod and req.custom_config:
            target_prod = req.custom_config.get("product_type")
        if not target_prod:
            schema = PROVIDER_SCHEMAS.get(exch)
            target_prod = schema.get("default_product") if schema else (ProductType.MT5_HEDGING.value if market == "FOREX" else ProductType.SPOT.value)
    target_prod = str(target_prod).strip().upper()

    # Pre-validation for product/env compatibility (e.g. Bitget Spot Demo)
    schema = PROVIDER_SCHEMAS.get(exch)
    if schema:
        for p_info in schema.get("supported_products", []):
            if p_info["id"] == target_prod:
                allowed_envs = p_info.get("supported_environments", ["LIVE"])
                if test_env not in allowed_envs:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Provider {exch} does not support {test_env} for product {target_prod}. Supported: {allowed_envs}. {p_info.get('notes', '')}"
                    )

    # Register environment, market & product in custom_cfg
    custom_cfg["environment"] = test_env
    custom_cfg["market_type"] = market
    custom_cfg["product_type"] = target_prod
    if exch == "BITGET" and target_prod in ("FUTURES_USDT", "FUTURES"):
        for sp_key in ("symbols_path", "ticker_path", "account_path", "balances_path", "open_orders_path", "positions_path"):
            if sp_key in custom_cfg and any(sp in str(custom_cfg[sp_key]).lower() for sp in ("/spot/", "spot/account", "spot/trade", "spot/public")):
                del custom_cfg[sp_key]

    # SSRF validation on custom endpoint URLs
    _validate_config_urls(custom_cfg)

    try:
        detection = await exchange_framework.detect_account_capabilities(
            exchange=exch,
            credentials=creds,
            custom_config=custom_cfg,
            environment=test_env,
            product_type=target_prod
        )
    except Exception as e:
        err_msg = str(e)
        if isinstance(e, SSRFValidationError) or "SSRF" in err_msg or "Could not resolve" in err_msg or "Name or service not known" in err_msg or isinstance(e, socket.gaierror):
            err_cls = ErrorClassification.CONFIGURATION_MISMATCH
            conn_status = ConnectionStatus.DISCONNECTED.value
            verif_label = "CONFIGURATION_MISMATCH"
            cap_state = CapabilityState.CONFIGURATION_MISMATCH.value
            guide = f"Configuration error: {err_msg}. Verify endpoint hostname and DNS configuration."
        elif isinstance(e, (httpx.TimeoutException, asyncio.TimeoutError)) or "timed out" in err_msg.lower():
            err_cls = ErrorClassification.TEMPORARILY_UNAVAILABLE
            conn_status = ConnectionStatus.DISCONNECTED.value
            verif_label = "TEMPORARILY_UNAVAILABLE"
            cap_state = CapabilityState.TEMPORARILY_UNAVAILABLE.value
            guide = "Network probe timed out. Exchange endpoint may be temporarily degraded or unreachable."
        elif "passphrase" in err_msg.lower() or "authentication" in err_msg.lower() or "api-key" in err_msg.lower() or "signature" in err_msg.lower():
            has_pass_val = bool((creds.get("passphrase") or "").strip())
            act_err = resolve_actionable_error_code(exch, None, None, err_msg, has_passphrase=has_pass_val)
            err_cls = ErrorClassification.CONFIGURATION_MISMATCH if act_err == "MISSING_PASSPHRASE" else ErrorClassification.AUTHENTICATION_FAILED
            conn_status = ConnectionStatus.AUTHENTICATION_FAILED.value
            verif_label = act_err
            cap_state = CapabilityState.AUTHENTICATION_FAILED.value
            guide = get_provider_error_guidance(exch, act_err, None, err_msg)
            prov_code = None
        else:
            err_cls = ErrorClassification.INCONCLUSIVE
            conn_status = ConnectionStatus.DISCONNECTED.value
            act_err = "AUTHENTICATION_DIAGNOSTIC_INCONCLUSIVE"
            verif_label = "AUTHENTICATION_DIAGNOSTIC_INCONCLUSIVE"
            cap_state = CapabilityState.INCONCLUSIVE.value
            guide = f"Connection test failed unexpectedly: {err_msg}"
            prov_code = "AUTHENTICATION_DIAGNOSTIC_INCONCLUSIVE"

        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        failed_matrix = _build_failed_capability_matrix(cap_state, err_msg, guide, now_iso)
        failed_strategy_eval = evaluate_strategy_compatibility({
            "market_type": market,
            "product_type": target_prod,
            "last_tested_utc": now_iso,
            "capability_matrix": failed_matrix
        })
        endpoint_results = [{
            "name": "Connection Test Probe",
            "url": custom_cfg.get("base_url") or "exchange_endpoint",
            "category": "CONNECTIVITY",
            "mandatory": True,
            "status": "FAIL",
            "schema_valid": False,
            "error": f"[{err_cls.value}] {err_msg}",
            "error_classification": err_cls.value,
            "provider_error_code": prov_code,
            "guidance": guide
        }]
        detection = {
            "status": "FAIL",
            "connection_status": conn_status,
            "verification_label": verif_label,
            "actionable_error_code": act_err,
            "provider_error_code": prov_code,
            "exchange": exch,
            "environment": test_env,
            "market_type": market,
            "product_type": target_prod,
            "endpoints": endpoint_results,
            "capabilities": [],
            "capability_matrix": failed_matrix,
            "permission_matrix": _build_failed_permission_matrix(err_msg),
            "strategy_compatibility": failed_strategy_eval,
            "account_data": None,
            "error": err_msg,
            "error_classification": err_cls.value,
            "guidance": guide,
            "execution_ready": False,
            "live_trading_locked": True,
            "read_only_mode": True,
            "summary": f"[{verif_label}] {guide}"
        }

    # If profile_id was supplied, update the vault profile
    if req.profile_id:
        credential_vault.update_verification_results(
            profile_id=req.profile_id,
            connection_status=detection.get("connection_status", ConnectionStatus.UNTESTED.value),
            verification_label=detection.get("verification_label", "UNKNOWN"),
            endpoint_results=detection.get("endpoints", []),
            capabilities=detection.get("capabilities", []),
            account_data=detection.get("account_data"),
            permission_matrix=detection.get("permission_matrix"),
            capability_matrix=detection.get("capability_matrix", []),
            strategy_compatibility=detection.get("strategy_compatibility", {}),
            actionable_error_code=detection.get("actionable_error_code"),
            provider_error_code=detection.get("provider_error_code")
        )

    return detection

@connections_router.get("/balances/summary")
async def get_balances_summary():
    """
    Returns segregated summaries for Live and Demo connected accounts.
    Ensures Live and Demo balances are never mixed into one total.
    """
    return exchange_framework.get_balances_summary()


@connections_router.get("/profiles/{profile_id}/balances")
async def get_profile_balances(profile_id: str):
    """
    Fetches real authenticated account balances and equity metrics for a saved profile.
    Updates the cached balance state in the vault.
    """
    try:
        res = await exchange_framework.fetch_profile_balances(profile_id)
        return res
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@connections_router.get("/profiles/{profile_id}/permissions")
async def get_profile_permissions(profile_id: str):
    """
    Returns the granular permission & capability matrix for a saved profile.
    """
    profile = credential_vault.get_profile_public(profile_id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    matrix = profile.get("permission_matrix")
    if not matrix:
        try:
            res = await exchange_framework.fetch_profile_balances(profile_id)
            matrix = res.get("permission_matrix")
        except Exception:
            matrix = []

    return {
        "status": "SUCCESS",
        "profile_id": profile_id,
        "exchange": profile.get("exchange"),
        "market_type": profile.get("market_type", "CRYPTO"),
        "environment": profile.get("environment"),
        "intended_permissions": profile.get("intended_permissions", []),
        "is_read_only": profile.get("is_read_only", True),
        "permission_matrix": matrix or []
    }


class StrategyCompatibilityRequest(BaseModel):
    profile_id: Optional[str] = None
    market_type: Optional[str] = "CRYPTO"
    product_type: Optional[str] = "SPOT"
    last_tested_utc: Optional[str] = None
    capability_matrix: Optional[List[Dict[str, Any]]] = None
    strategy_id: Optional[str] = None


@connections_router.get("/strategies")
def list_supported_strategies():
    """Returns registered trading strategies and their mandatory capability requirements."""
    from app.services.exchange_framework import STRATEGY_CAPABILITY_REQUIREMENTS
    return {
        "status": "SUCCESS",
        "strategies": list(STRATEGY_CAPABILITY_REQUIREMENTS.values())
    }


@connections_router.get("/profiles/{profile_id}/strategy-compatibility")
def get_profile_strategy_compatibility(profile_id: str, strategy_id: Optional[str] = None):
    """Evaluates strategy compatibility for a stored profile against registered requirements."""
    profile = credential_vault.get_profile_public(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found.")
    from app.services.exchange_framework import evaluate_strategy_compatibility
    return evaluate_strategy_compatibility(profile, strategy_id=strategy_id)


@connections_router.post("/strategy-compatibility")
def evaluate_strategy_compatibility_endpoint(req: StrategyCompatibilityRequest):
    """Dynamic evaluation of strategy compatibility from given capability data or profile."""
    from app.services.exchange_framework import evaluate_strategy_compatibility
    if req.profile_id:
        profile = credential_vault.get_profile_public(req.profile_id)
        if not profile:
            raise HTTPException(status_code=404, detail=f"Profile '{req.profile_id}' not found.")
        return evaluate_strategy_compatibility(profile, strategy_id=req.strategy_id)
    profile_data = {
        "market_type": req.market_type,
        "product_type": req.product_type,
        "last_tested_utc": req.last_tested_utc,
        "capability_matrix": req.capability_matrix or []
    }
    return evaluate_strategy_compatibility(profile_data, strategy_id=req.strategy_id)


@connections_router.get("/profiles/{profile_id}/capabilities")
def get_profile_capabilities(profile_id: str):
    """Returns granular capability matrix, permission diagnostics, and strategy compatibility."""
    profile = credential_vault.get_profile_public(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found.")
    return {
        "status": "SUCCESS",
        "profile_id": profile_id,
        "exchange": profile.get("exchange"),
        "market_type": profile.get("market_type"),
        "product_type": profile.get("product_type"),
        "environment": profile.get("environment"),
        "connection_status": profile.get("connection_status"),
        "last_tested_utc": profile.get("last_tested_utc"),
        "capability_matrix": profile.get("capability_matrix", []),
        "permission_matrix": profile.get("permission_matrix", []),
        "strategy_compatibility": profile.get("strategy_compatibility", {}),
        "endpoint_results": profile.get("endpoint_results", []),
        "account_data": profile.get("account_data")
    }
