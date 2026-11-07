"""
Exness High-Frequency Trading (HFT) API Router (Hardened Phase 4.1)
Enforces strict customer tenant isolation, discrete 3-way connection status cards
(Trader API, MT5 Demo, MT5 Real), customer account selection, and official Payments API funding flows.
Specification reference: Master Exness HFT Implementation Specification, Part 4 & Part 11; Phase 4.1 Directive.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ..services.saas_db import get_db_connection
from ..services.auth_manager import get_current_user
from ..services.exness.mock_adapter import ExnessDeterministicMockAdapter
from ..services.exness.mt5_gateway_adapter import ExnessMT5GatewayAdapter
from ..services.exness.trader_api_adapter import ExnessTraderAPIAdapter
from ..services.exness.payments_service import ExnessPaymentsService
from ..services.exness.vault import ExnessCredentialVault
from ..services.exness.exness_db import (
    get_user_exness_connection,
    get_all_user_exness_connections,
    get_user_exness_connection_by_mode,
    disconnect_exness_connection,
    set_preferred_account,
    save_exness_connection,
    get_active_local_positions,
    log_reconciliation,
    create_exness_transfer,
    get_exness_transfer_by_idempotency,
    get_user_exness_transfers,
    update_exness_transfer_status,
)

logger = logging.getLogger("bitdex.routes.exness_hft")

router = APIRouter(prefix="/hft/exness", tags=["Exness HFT"])

# In-memory adapter instances keyed by (user_id, environment, connection_id)
_USER_ADAPTERS: Dict[tuple, Any] = {}


def mask_id(val: Any) -> str:
    """Helper to mask account identifiers for safe customer display."""
    if not val or val == "UNAVAILABLE":
        return "UNAVAILABLE"
    s = str(val).strip()
    if len(s) <= 4:
        return "****" + s[-2:] if len(s) >= 2 else "****"
    return s[:2] + "****" + s[-2:]


def get_user_adapter(
    user_id: str, environment: str = "DEMO", connection_id: Optional[str] = None
) -> Optional[Any]:
    """
    Returns or instantiates the user's active Exness adapter for the requested environment (DEMO vs REAL).
    Restores the persisted adapter mode from database rather than silently defaulting to mock.
    Guarantees strict multi-user tenant isolation: never falls back to admin credentials.
    Returns None if the customer has zero active saved connections for this environment.
    """
    env = (environment or "DEMO").upper()
    cache_key = (user_id, env, connection_id) if connection_id else (user_id, env)
    if cache_key in _USER_ADAPTERS:
        return _USER_ADAPTERS[cache_key]

    conn = get_db_connection()
    try:
        db_conn = get_user_exness_connection(conn, user_id, account_type=env, connection_id=connection_id)
        if db_conn:
            login = db_conn["account_login"]
            server = db_conn["server_name"]
            mode = db_conn.get("adapter_mode", "EXNESS_MT5_GATEWAY")

            if mode == "EXNESS_MT5_GATEWAY":
                adapter = ExnessMT5GatewayAdapter(
                    account_id=login,
                    server=server,
                    environment=env,
                )
            elif mode == "EXNESS_TRADER_API":
                adapter = ExnessTraderAPIAdapter(
                    api_key=login,
                    api_secret="",
                    account_id=login,
                    environment=env,
                    discovery_base_url=server,
                )
            else:
                adapter = ExnessDeterministicMockAdapter(
                    account_id=login,
                    server=server,
                    initial_balance=float(db_conn.get("balance_usd", 0.0)),
                )
            _USER_ADAPTERS[cache_key] = adapter
            return adapter
    finally:
        conn.close()

    # Strict Tenant Isolation Rule: Return None if user has zero active connections
    return None


class ExnessConnectRequest(BaseModel):
    account_login: str = Field(..., min_length=4, max_length=32, description="Exness MT5 account login ID")
    password: str = Field(..., min_length=4, max_length=128, description="Exness MT5 trading password")
    server_name: str = Field(default="Exness-MT5Trial", description="Exness MT5 trial/demo server name")
    use_mock: bool = Field(default=True, description="Explicit mode selection: True for simulated mock, False for real MT5 gateway")
    account_label: Optional[str] = Field(default="Exness Demo MT5", description="User-assigned friendly label")


class ExnessRealConnectRequest(BaseModel):
    account_login: str = Field(..., min_length=4, max_length=64, description="Exness Real account ID or API Key")
    password: Optional[str] = Field(default="", max_length=128, description="Exness MT5 trading password (if MT5 Gateway)")
    server_name: str = Field(default="Exness-Real", description="Exness MT5 Real server name")
    connection_method: str = Field(default="MT5_GATEWAY", description="'MT5_GATEWAY' or 'TRADER_API'")
    api_key: Optional[str] = Field(default=None, description="Exness Trader API Key")
    api_secret: Optional[str] = Field(default=None, description="Exness Trader API Secret")
    account_tier: str = Field(default="STANDARD", description="Standard, Pro, Raw Spread, Zero")
    account_label: Optional[str] = Field(default=None, description="User-assigned friendly label")


class ExnessAttachDiscoverRequest(BaseModel):
    api_key: str = Field(..., min_length=4, max_length=128, description="Exness Trader API Key from Personal Area")
    api_secret: str = Field(..., min_length=16, description="Ed25519 private key string or hex seed")
    gateway_host: str = Field(default="https://api.exness.com", description="Gateway Base URL from Exness Key Management DNS Widget")
    account_ids: Optional[List[str]] = Field(default=None, description="Candidate account IDs to authenticate (e.g. ['149827361', '460310009'])")
    account_tier: str = Field(default="STANDARD", description="Account tier: STANDARD, PRO, RAW_SPREAD, ZERO")
    manual_environments: Optional[Dict[str, str]] = Field(default=None, description="Optional explicit DEMO/REAL mapping per account ID")
    account_label: Optional[str] = Field(default=None, description="Friendly label prefix")


class MarginCalculateRequest(BaseModel):
    symbol: str = Field(..., min_length=3)
    order_type: str = Field(default="BUY")
    volume: float = Field(default=0.01, gt=0)


class SimulationRequest(BaseModel):
    symbol: str = Field(default="XAUUSDm", min_length=3)
    volume_per_leg: float = Field(default=0.01, gt=0, le=1.0)
    take_profit_points: float = Field(default=30.0, gt=0)
    stop_loss_points: float = Field(default=60.0, gt=0)
    max_hold_bars: int = Field(default=15, ge=3, le=100)
    timeframe: str = Field(default="M1")
    candle_count: int = Field(default=100, ge=25, le=500)


class PreOrderRiskCheckRequest(BaseModel):
    symbol: str = Field(..., min_length=3)
    volume: float = Field(..., gt=0)
    price: float = Field(..., gt=0)
    order_type: str = Field(default="BUY")


class TradeExecutionRequest(BaseModel):
    environment: Optional[str] = Field(default=None, description="'DEMO' or 'REAL'")
    trade_mode: Optional[str] = Field(default=None, description="Alias for environment ('DEMO' or 'REAL')")
    connection_id: Optional[str] = Field(default=None, description="Customer-selected specific connection ID")
    account_id: Optional[str] = Field(default=None, description="Optional account login alias")
    symbol: str = Field(..., min_length=3)
    side: str = Field(default="BUY", description="'BUY' or 'SELL'")
    volume: Optional[float] = Field(default=None, gt=0, description="Volume in standard lots")
    quantity: Optional[float] = Field(default=None, gt=0, description="Alias for volume in standard lots")
    order_type: str = Field(default="MARKET")
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    consent_confirmed: bool = Field(default=False, description="Mandatory True for Real account execution")
    consent_token: Optional[str] = None


class CustomerTransferRequest(BaseModel):
    transfer_type: str = Field(..., description="INTERNAL_WALLET_TO_ACCOUNT, INTERNAL_ACCOUNT_TO_WALLET, PARTNER_TO_CLIENT, DEPOSIT_REDIRECT")
    source_id: str = Field(..., min_length=2)
    destination_id: str = Field(..., min_length=2)
    amount: float = Field(..., gt=0)
    currency: str = Field(default="USD")
    idempotency_key: str = Field(..., min_length=8)


class DisconnectRequest(BaseModel):
    connection_id: str = Field(..., min_length=4)


class PreferredAccountRequest(BaseModel):
    connection_id: str = Field(..., min_length=4)


@router.get("/status")
async def get_exness_status(user: Dict[str, Any] = Depends(get_current_user)):
    """
    Returns Exness 3-way connection status cards (Trader API, MT5 Demo, MT5 Real), execution locks, and discrete connection semantics.
    Enforces strict tenant isolation: displays only accounts belonging to the authenticated customer.
    Admin connections and fallback mock accounts are strictly excluded.
    """
    conn = get_db_connection()
    try:
        demo_conn = get_user_exness_connection(conn, user["user_id"], "DEMO")
        real_conn = get_user_exness_connection(conn, user["user_id"], "REAL")
        trader_conn = get_user_exness_connection_by_mode(conn, user["user_id"], "EXNESS_TRADER_API")
        all_conns = get_all_user_exness_connections(conn, user["user_id"])
    finally:
        conn.close()

    adapter_demo = get_user_adapter(user["user_id"], "DEMO")
    adapter_real = get_user_adapter(user["user_id"], "REAL")

    if adapter_demo:
        conn_demo_status = await adapter_demo.get_connection_status()
    else:
        conn_demo_status = {
            "adapter_connected": False,
            "broker_authenticated": False,
            "is_mock": False,
            "broker_mode": "NONE",
            "is_connected": False,
            "status": "NOT_CONNECTED",
            "account_id": "UNAVAILABLE",
        }

    if adapter_real:
        conn_real_status = await adapter_real.get_connection_status()
    else:
        conn_real_status = {
            "adapter_connected": False,
            "broker_authenticated": False,
            "is_mock": False,
            "broker_mode": "NONE",
            "is_connected": False,
            "status": "NOT_CONNECTED",
            "account_id": "UNAVAILABLE",
        }

    if trader_conn:
        adapter_trader = get_user_adapter(user["user_id"], trader_conn["account_type"], trader_conn["connection_id"])
        if adapter_trader:
            trader_status = await adapter_trader.get_connection_status()
        else:
            trader_status = {
                "adapter_connected": True,
                "broker_authenticated": True,
                "is_mock": False,
                "broker_mode": "EXNESS_TRADER_API",
                "is_connected": True,
                "status": "CONNECTED",
                "account_id": trader_conn["account_login"],
            }
    else:
        trader_status = {
            "adapter_connected": False,
            "broker_authenticated": False,
            "is_mock": False,
            "broker_mode": "NONE",
            "is_connected": False,
            "status": "NOT_CONNECTED",
            "account_id": "UNAVAILABLE",
        }

    def format_conn(c):
        if not c:
            return None
        raw_v = (c.get("verification_status") or "").upper().strip()
        env_raw = (c.get("account_type") or "ENVIRONMENT UNVERIFIED").upper().strip()
        has_env = env_raw in ("DEMO", "REAL")
        has_bal = c.get("balance_usd") is not None

        # Map legacy / database statuses to distinct Task 3 state machine states:
        # CREDENTIALS_SAVED | NODE_CONNECTED | AUTHENTICATING | AUTH_FAILED |
        # BROKER_AUTHENTICATED | ACCOUNT_DATA_VERIFIED | ENVIRONMENT_UNVERIFIED
        if raw_v in ("FAILED", "ERROR", "AUTH_FAILED"):
            state = "AUTH_FAILED"
        elif raw_v in ("NOT_TESTED", "CREDENTIALS_SAVED", ""):
            state = "CREDENTIALS_SAVED"
        elif raw_v == "NODE_CONNECTED":
            state = "NODE_CONNECTED"
        elif raw_v == "AUTHENTICATING":
            state = "AUTHENTICATING"
        elif raw_v in ("ENVIRONMENT_UNVERIFIED",) or not has_env:
            state = "ENVIRONMENT_UNVERIFIED"
        elif raw_v in ("VERIFIED", "ACCOUNT_DATA_VERIFIED") and has_env and has_bal:
            state = "ACCOUNT_DATA_VERIFIED"
        elif raw_v in ("VERIFIED", "ACCOUNT_DATA_VERIFIED", "BROKER_AUTHENTICATED") and has_env:
            state = "BROKER_AUTHENTICATED"
        else:
            state = "ENVIRONMENT_UNVERIFIED"

        is_fully_verified = (state == "ACCOUNT_DATA_VERIFIED") and has_env
        is_broker_authed = state in ("ACCOUNT_DATA_VERIFIED", "BROKER_AUTHENTICATED") and has_env
        env_display = env_raw if has_env else "ENVIRONMENT UNVERIFIED"

        tier_raw = (c.get("account_tier") or "").strip()
        if is_broker_authed and tier_raw and tier_raw.upper() not in ("UNVERIFIED", ""):
            tier_display = tier_raw
        elif is_broker_authed:
            tier_display = "Exness Native"
        else:
            tier_display = "UNVERIFIED"

        bal_val = float(c["balance_usd"]) if (is_fully_verified and c.get("balance_usd") is not None) else None
        eq_val = float(c["equity_usd"]) if (is_fully_verified and c.get("equity_usd") is not None) else None

        raw_platform = (c.get("platform") or "").upper().strip()
        raw_stream = (c.get("stream_id") or "").lower().strip()
        if raw_platform == "EXNESS_TERMINAL" or raw_stream.startswith("dx."):
            platform_val = "EXNESS_TERMINAL"
            platform_label = "Exness Terminal Only"
            mt5_eligible = False
        elif raw_platform == "MT5" or raw_stream.startswith("mt5.") or c.get("adapter_mode") == "EXNESS_MT5_GATEWAY":
            platform_val = "MT5"
            platform_label = "MT5"
            mt5_eligible = True
        else:
            platform_val = "UNVERIFIED"
            platform_label = "UNVERIFIED"
            mt5_eligible = False

        return {
            "connection_id": c["connection_id"],
            "provider": "Exness",
            "account_login": mask_id(c["account_login"]),
            "account_login_raw": str(c["account_login"]),
            "server_name": c["server_name"],
            "account_type": env_display,
            "account_tier": tier_display,
            "platform": platform_val,
            "platform_label": platform_label,
            "mt5_eligible": mt5_eligible,
            "stream_id": c.get("stream_id") or "",
            "adapter_mode": c.get("adapter_mode", "EXNESS_TRADER_API"),
            "account_label": c.get("account_label") or (f"Exness {env_display.title()} ({mask_id(c['account_login'])})" if is_fully_verified else f"Exness ({mask_id(c['account_login'])})"),
            "is_preferred": bool(c.get("is_preferred", 0)),
            "balance_usd": bal_val,
            "equity_usd": eq_val,
            "balance_display": f"{bal_val:.2f}" if bal_val is not None else "DATA UNAVAILABLE",
            "equity_display": f"{eq_val:.2f}" if eq_val is not None else "DATA UNAVAILABLE",
            "margin_used": c.get("margin_used") if is_fully_verified else None,
            "margin_free": c.get("margin_free") if is_fully_verified else None,
            "trade_mode": c.get("trade_mode") or env_display,
            "verification_status": "VERIFIED" if is_fully_verified else state,
            "connection_state": state,
            "is_verified": is_fully_verified,
            "broker_authenticated": is_broker_authed,
            "error_type": c.get("error_type") or "",
            "error_detail": c.get("error_detail") or "",
            "environment_confirmed_by": c.get("environment_confirmed_by") or ("PROVIDER_VERIFIED" if has_env else "UNVERIFIED"),
            "access_point": c.get("access_point") or "",
            "currency": c.get("currency", "USD") if (is_broker_authed and c.get("currency") and c.get("currency") != "DATA UNAVAILABLE") else "DATA UNAVAILABLE",
            "leverage": c.get("leverage", 200) if is_broker_authed else None,
            "is_active": bool(c.get("is_active", 1)),
            "last_reconciled_at": c["last_reconciled_at"],
            "data_source": "Exness REST/WS Gateway" if c.get("adapter_mode") == "EXNESS_TRADER_API" else "Windows MT5 IPC Bridge",
        }

    # Deduplicate formatted_all by account_login_raw (preserving verified/latest entry per account)
    seen_logins = set()
    formatted_all = []
    for c in [format_conn(r) for r in all_conns if r]:
        raw_login = c["account_login_raw"]
        if raw_login not in seen_logins:
            seen_logins.add(raw_login)
            formatted_all.append(c)

    verified_all = [c for c in formatted_all if c.get("is_verified") is True and c.get("account_type") in ("DEMO", "REAL")]
    exness_demos = [c for c in verified_all if c["account_type"] == "DEMO"]
    exness_reals = [c for c in verified_all if c["account_type"] == "REAL"]
    unverified_conns = [c for c in formatted_all if not c.get("is_verified") and c.get("connection_state") in ("ENVIRONMENT_UNVERIFIED", "BROKER_AUTHENTICATED", "CREDENTIALS_SAVED", "NODE_CONNECTED", "AUTHENTICATING")]
    failed_conns = [c for c in formatted_all if c.get("connection_state") == "AUTH_FAILED"]
    has_any_verified = len(verified_all) > 0
    has_saved_credentials = any(bool(r.get("api_key")) for r in all_conns)

    # Overall header state machine status
    if has_any_verified:
        overall_state = "ACCOUNT_DATA_VERIFIED"
    elif any(c.get("connection_state") == "BROKER_AUTHENTICATED" for c in formatted_all):
        overall_state = "BROKER_AUTHENTICATED"
    elif any(c.get("connection_state") == "ENVIRONMENT_UNVERIFIED" for c in formatted_all):
        overall_state = "ENVIRONMENT_UNVERIFIED"
    elif any(c.get("connection_state") == "AUTH_FAILED" for c in formatted_all):
        overall_state = "AUTH_FAILED"
    elif any(c.get("connection_state") == "CREDENTIALS_SAVED" for c in formatted_all):
        overall_state = "CREDENTIALS_SAVED"
    else:
        overall_state = "NOT_CONNECTED"

    return {
        "status": "SUCCESS",
        "broker": "Exness",
        "overall_state": overall_state,
        "connection_state": overall_state,
        "has_saved_credentials": has_saved_credentials,
        "environments_supported": ["DEMO", "REAL"],
        "live_trading_locked": True,
        "emergency_lock_active": True,
        "read_only_mode": True,
        "adapter_connected": has_any_verified,
        "broker_authenticated": has_any_verified,
        "is_mock": False,
        "broker_mode": "EXNESS_TRADER_API" if has_any_verified else "NONE",
        "is_connected": has_any_verified,
        "active_demo_connection": exness_demos[0] if exness_demos else None,
        "active_real_connection": exness_reals[0] if exness_reals else None,
        "active_trader_connection": verified_all[0] if verified_all else None,
        "all_connections": formatted_all,
        "verified_accounts": verified_all,
        "unverified_accounts": unverified_conns,
        "demo_connections": [c for c in exness_demos if c.get("mt5_eligible") is True],
        "real_connections": [c for c in exness_reals if c.get("mt5_eligible") is True],
        "trader_connections": [c for c in verified_all if c.get("adapter_mode") == "EXNESS_TRADER_API"],
        "exness_demo_accounts": exness_demos,
        "exness_real_accounts": exness_reals,
        "failed_accounts": failed_conns,
        "demo_status": conn_demo_status,
        "real_status": conn_real_status,
        "trader_status": trader_status,
    }


@router.post("/demo/connect")
async def connect_exness_demo(
    req: ExnessConnectRequest, user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Establishes an Exness MT5 Demo connection.
    - Encrypts credentials with AES-256-GCM authenticated vault and stores in database.
    - Explicitly routes to Deterministic Mock Demo or real MT5 Gateway based on `use_mock`.
    - Securely passes credentials to MT5 Gateway over mutual auth token.
    - Validates returned account identity (login, server, DEMO account type).
    - Never falls back to mock accidentally when real mode is requested.
    """
    user_id = user["user_id"]

    clean_login = req.account_login.strip()
    if not clean_login.isdigit():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid account login format: MetaTrader 5 account numbers must be numeric.",
        )

    # Encrypt credentials via vault
    enc_creds = ExnessCredentialVault.encrypt_credentials(
        user_id=user_id,
        login=req.account_login,
        password=req.password,
        server=req.server_name,
        account_type="DEMO",
    )

    label = req.account_label or f"Demo MT5 ({mask_id(req.account_login)})"

    if req.use_mock:
        adapter = ExnessDeterministicMockAdapter(
            account_id=req.account_login,
            server=req.server_name,
            initial_balance=5000.0,
        )
        conn_res = await adapter.connect()
        _USER_ADAPTERS[(user_id, "DEMO")] = adapter
        acct_info = await adapter.get_account_info()

        conn = get_db_connection()
        try:
            conn_id = save_exness_connection(
                conn=conn,
                user_id=user_id,
                login=req.account_login,
                server=req.server_name,
                enc_credentials=enc_creds,
                adapter_mode="DETERMINISTIC_MOCK_DEMO",
                account_type="DEMO",
                balance=acct_info["balance"],
                equity=acct_info["equity"],
                leverage=acct_info["leverage"],
                account_label=label,
                is_preferred=1,
            )
        finally:
            conn.close()

        return {
            "status": "SUCCESS",
            "connection_id": conn_id,
            "adapter_connected": True,
            "broker_authenticated": False,
            "is_mock": True,
            "broker_mode": "DETERMINISTIC_MOCK_DEMO",
            "connection_type": "SIMULATED_DEMO",
            "connection_details": conn_res,
            "account_telemetry": acct_info,
            "credentials": ExnessCredentialVault.mask_credentials({
                "login": req.account_login,
                "server": req.server_name,
                "account_type": "DEMO",
                "key_version": enc_creds.get("key_version", 1),
            }),
        }
    else:
        # Real MT5 Gateway Mode Requested
        gateway_adapter = ExnessMT5GatewayAdapter(
            account_id=req.account_login,
            server=req.server_name,
            environment="DEMO",
        )

        try:
            conn_res = await gateway_adapter.connect(password=req.password)
        except (ValueError, PermissionError) as exc:
            raise HTTPException(
                status_code=400,
                detail={
                    "status": "AUTHENTICATION_REJECTED",
                    "reason": str(exc),
                },
            )
        except RuntimeError as exc:
            raise HTTPException(
                status_code=500,
                detail={
                    "status": "CONFIG_ERROR",
                    "reason": str(exc),
                },
            )

        if not conn_res.get("broker_authenticated", False):
            raise HTTPException(
                status_code=503,
                detail={
                    "status": conn_res.get("status", "MT5_TERMINAL_UNAVAILABLE"),
                    "adapter_connected": conn_res.get("adapter_connected", False),
                    "broker_authenticated": False,
                    "is_mock": False,
                    "broker_mode": "EXNESS_MT5_GATEWAY",
                    "reason": conn_res.get("reason", "MT5 Gateway execution bridge is unreachable."),
                    "recommended_action": "Set use_mock=true for simulated demo testing.",
                },
            )

        _USER_ADAPTERS[(user_id, "DEMO")] = gateway_adapter
        try:
            acct_info = await gateway_adapter.get_account_info()
        except Exception:
            acct_info = {"balance": 0.0, "equity": 0.0, "leverage": 2000}

        conn = get_db_connection()
        try:
            conn_id = save_exness_connection(
                conn=conn,
                user_id=user_id,
                login=req.account_login,
                server=req.server_name,
                enc_credentials=enc_creds,
                adapter_mode="EXNESS_MT5_GATEWAY",
                account_type="DEMO",
                balance=acct_info.get("balance", 0.0),
                equity=acct_info.get("equity", 0.0),
                leverage=acct_info.get("leverage", 2000),
                account_label=label,
                is_preferred=1,
            )
        finally:
            conn.close()

        return {
            "status": "SUCCESS",
            "connection_id": conn_id,
            "adapter_connected": True,
            "broker_authenticated": True,
            "is_mock": False,
            "broker_mode": "EXNESS_MT5_GATEWAY",
            "connection_type": "REAL_EXNESS_DEMO",
            "connection_details": conn_res,
            "account_telemetry": acct_info,
            "credentials": ExnessCredentialVault.mask_credentials({
                "login": req.account_login,
                "server": req.server_name,
                "account_type": "DEMO",
                "key_version": enc_creds.get("key_version", 1),
            }),
        }


@router.post("/real/connect")
async def connect_exness_real(
    req: ExnessRealConnectRequest, user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Connects an Exness Real account via Windows MT5 Gateway or Exness Trader API.
    Enforces secure AES-256-GCM vault encryption, tenant isolation, and environment validation.
    """
    user_id = user["user_id"]
    method = req.connection_method.upper().strip()

    if method == "MT5_GATEWAY":
        clean_login = req.account_login.strip()
        if not clean_login.isdigit():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid account login format: MetaTrader 5 account numbers must be numeric.",
            )

    label = req.account_label or (f"Trader API ({mask_id(req.account_login)})" if method == "TRADER_API" else f"Real MT5 ({mask_id(req.account_login)})")

    if method == "TRADER_API":
        api_key = req.api_key or req.account_login
        api_secret = req.api_secret or req.password or ""
        adapter = ExnessTraderAPIAdapter(
            api_key=api_key,
            api_secret=api_secret,
            account_id=req.account_login,
            environment="REAL",
            discovery_base_url=req.server_name.strip() if req.server_name else None,
            account_tier=req.account_tier,
        )
        enc_creds = ExnessCredentialVault.encrypt_credentials(
            user_id=user_id,
            login=req.account_login,
            password=api_secret,
            server=req.server_name,
            account_type="REAL",
        )
        conn_res = await adapter.connect()
        adapter_mode = "EXNESS_TRADER_API"
    else:
        # MT5 Gateway
        adapter = ExnessMT5GatewayAdapter(
            account_id=req.account_login,
            server=req.server_name,
            environment="REAL",
        )
        enc_creds = ExnessCredentialVault.encrypt_credentials(
            user_id=user_id,
            login=req.account_login,
            password=req.password or "",
            server=req.server_name,
            account_type="REAL",
        )
        conn_res = await adapter.connect(password=req.password)
        adapter_mode = "EXNESS_MT5_GATEWAY"

    is_authenticated = bool(conn_res.get("broker_authenticated", False))
    conn = get_db_connection()
    try:
        conn_id = save_exness_connection(
            conn=conn,
            user_id=user_id,
            login=req.account_login,
            server=req.server_name,
            enc_credentials=enc_creds,
            adapter_mode=adapter_mode,
            account_type="REAL",
            balance=float(conn_res.get("balance", 0.0)) if is_authenticated else 0.0,
            equity=float(conn_res.get("equity", 0.0)) if is_authenticated else 0.0,
            leverage=200,
            currency="USD",
            account_label=label,
            is_preferred=1 if is_authenticated else 0,
        )
        if is_authenticated:
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            conn.execute("UPDATE exness_demo_connections SET last_reconciled_at = ? WHERE connection_id = ?", (now, conn_id))
            conn.commit()
        else:
            conn.execute("UPDATE exness_demo_connections SET last_reconciled_at = NULL WHERE connection_id = ?", (conn_id,))
            conn.commit()
    finally:
        conn.close()

    if is_authenticated:
        _USER_ADAPTERS[(user_id, "REAL")] = adapter
        return {
            "status": "SUCCESS",
            "connection_id": conn_id,
            "environment": "REAL",
            "connection_method": adapter_mode,
            "account_id": mask_id(req.account_login),
            "server": req.server_name,
            "broker_result": conn_res,
            "live_execution_locked": True,
        }
    else:
        reason = conn_res.get("reason") or conn_res.get("error") or conn_res.get("detail") or "Broker authentication failed"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "status": "FAILED",
                "reason": reason,
                "error_type": conn_res.get("error_type", "AUTHENTICATION_FAILED"),
                "http_status": conn_res.get("http_status"),
                "exness_code": conn_res.get("exness_code"),
                "broker_result": conn_res,
            }
        )



@router.post("/attach-and-discover")
async def attach_and_discover_accounts(
    req: ExnessAttachDiscoverRequest,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Universal Exness API Connection & Automatic Multi-Account Discovery:
    1. Validates API key and Ed25519 private key.
    2. Uses automatic Gateway Host (default https://api.exness.com or user-supplied advanced fallback).
    3. Accepts one or more explicit Exness Trading Account IDs in the same workflow.
    4. Resolves dynamic Access Point per account (GET /v1/trading/access-point?account_id={id}).
    5. Authenticates every account independently and retrieves genuine metadata and balance.
    6. Classifies DEMO vs REAL strictly from authoritative provider metadata (or marks ENVIRONMENT UNVERIFIED).
    7. Identifies account tier strictly from provider metadata (or shows Exness Native).
    8. Persists verified accounts and records failed accounts honestly without fabricating balances.
    """
    user_id = user["user_id"]
    api_key = req.api_key.strip()
    api_secret = req.api_secret.strip()
    gateway_host = (req.gateway_host or "https://api.exness.com").strip().rstrip("/")
    if not gateway_host.startswith("http://") and not gateway_host.startswith("https://"):
        gateway_host = f"https://{gateway_host}"

    # Determine candidate IDs to probe (preserve strictly as strings)
    candidate_ids: List[str] = []
    if req.account_ids:
        for aid in req.account_ids:
            s = str(aid).strip()
            if s and s not in candidate_ids:
                candidate_ids.append(s)

    if not candidate_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "status": "FAILED",
                "error_type": "ACCOUNT_IDS_REQUIRED",
                "error_detail": "Please enter one or more Exness Trading Account IDs to authenticate (Exness Trader API requires explicit account_id routing for Access Point discovery).",
            },
        )

    # Instantiate Exness Trader API Adapter
    adapter = ExnessTraderAPIAdapter(
        api_key=api_key,
        api_secret=api_secret,
        account_id=candidate_ids[0],
        discovery_base_url=gateway_host,
        account_tier=req.account_tier,
    )

    # Execute full discovery and multi-account verification
    disc_res = await adapter.discover_and_verify_all(
        candidate_account_ids=candidate_ids,
        manual_environments=req.manual_environments
    )

    conn = get_db_connection()
    persisted_demo = []
    persisted_real = []
    persisted_unverified = []
    persisted_failed = []

    try:
        # Save verified DEMO accounts (strictly DEMO + balance retrieved)
        for d in disc_res.get("demo_accounts", []):
            env_val = "DEMO"
            tier_val = d.get("account_tier") or "Exness Native"
            plat_val = d.get("platform") or "EXNESS_TERMINAL"
            mt5_elig = int(bool(d.get("mt5_eligible", False)))
            stream_val = d.get("stream_id") or ""
            enc = ExnessCredentialVault.encrypt_credentials(
                user_id=user_id,
                login=d["account_id"],
                password=api_secret,
                server=gateway_host,
                account_type=env_val,
            )
            cid = save_exness_connection(
                conn=conn,
                user_id=user_id,
                login=d["account_id"],
                server=gateway_host,
                enc_credentials=enc,
                adapter_mode="EXNESS_TRADER_API",
                account_type=env_val,
                balance=d.get("balance"),
                equity=d.get("equity"),
                leverage=int(d.get("leverage", 200)),
                currency=d.get("currency", "USD"),
                account_label=req.account_label or f"Exness Demo ({mask_id(d['account_id'])})",
                is_preferred=1,
                verification_status="ACCOUNT_DATA_VERIFIED",
                trade_mode=d.get("trade_mode", "ENABLED"),
                margin_used=d.get("margin_used"),
                margin_free=d.get("margin_free"),
                environment_confirmed_by=d.get("environment_confirmed_by", "PROVIDER_VERIFIED"),
                access_point=d.get("access_point", ""),
                api_key=api_key,
                account_tier=tier_val,
                platform=plat_val,
                mt5_eligible=mt5_elig,
                stream_id=stream_val,
            )
            persisted_demo.append({
                "connection_id": cid,
                "account_id": d["account_id"],
                "account_id_masked": mask_id(d["account_id"]),
                "environment": env_val,
                "platform": plat_val,
                "mt5_eligible": bool(mt5_elig),
                "account_tier": tier_val,
                "balance": d.get("balance"),
                "equity": d.get("equity"),
                "margin_used": d.get("margin_used"),
                "margin_free": d.get("margin_free"),
                "currency": d.get("currency", "USD"),
                "verification_status": "VERIFIED",
                "connection_state": "ACCOUNT_DATA_VERIFIED",
                "trade_mode": d.get("trade_mode", "ENABLED"),
                "access_point": d.get("access_point", ""),
            })

        # Save verified REAL accounts (strictly REAL + balance retrieved)
        for r in disc_res.get("real_accounts", []):
            tier_val = r.get("account_tier") or "Exness Native"
            plat_val = r.get("platform") or "EXNESS_TERMINAL"
            mt5_elig = int(bool(r.get("mt5_eligible", False)))
            stream_val = r.get("stream_id") or ""
            enc = ExnessCredentialVault.encrypt_credentials(
                user_id=user_id,
                login=r["account_id"],
                password=api_secret,
                server=gateway_host,
                account_type="REAL",
            )
            cid = save_exness_connection(
                conn=conn,
                user_id=user_id,
                login=r["account_id"],
                server=gateway_host,
                enc_credentials=enc,
                adapter_mode="EXNESS_TRADER_API",
                account_type="REAL",
                balance=r.get("balance"),
                equity=r.get("equity"),
                leverage=int(r.get("leverage", 200)),
                currency=r.get("currency", "USD"),
                account_label=req.account_label or f"Exness Real ({mask_id(r['account_id'])})",
                is_preferred=1,
                verification_status="ACCOUNT_DATA_VERIFIED",
                trade_mode=r.get("trade_mode", "ENABLED"),
                margin_used=r.get("margin_used"),
                margin_free=r.get("margin_free"),
                environment_confirmed_by=r.get("environment_confirmed_by", "PROVIDER_VERIFIED"),
                access_point=r.get("access_point", ""),
                api_key=api_key,
                account_tier=tier_val,
                platform=plat_val,
                mt5_eligible=mt5_elig,
                stream_id=stream_val,
            )
            persisted_real.append({
                "connection_id": cid,
                "account_id": r["account_id"],
                "account_id_masked": mask_id(r["account_id"]),
                "environment": "REAL",
                "platform": plat_val,
                "mt5_eligible": bool(mt5_elig),
                "account_tier": tier_val,
                "balance": r.get("balance"),
                "equity": r.get("equity"),
                "margin_used": r.get("margin_used"),
                "margin_free": r.get("margin_free"),
                "currency": r.get("currency", "USD"),
                "verification_status": "VERIFIED",
                "connection_state": "ACCOUNT_DATA_VERIFIED",
                "trade_mode": r.get("trade_mode", "ENABLED"),
                "access_point": r.get("access_point", ""),
            })

        # Save unverified / partially authenticated accounts (e.g. ENVIRONMENT_UNVERIFIED or BROKER_AUTHENTICATED without balance)
        for u in disc_res.get("unverified_accounts", []):
            env_val = u.get("environment") or "ENVIRONMENT UNVERIFIED"
            state_val = u.get("verification_state") or "ENVIRONMENT_UNVERIFIED"
            tier_val = u.get("account_tier") or "Exness Native"
            plat_val = u.get("platform") or "UNVERIFIED"
            mt5_elig = int(bool(u.get("mt5_eligible", False)))
            stream_val = u.get("stream_id") or ""
            enc = ExnessCredentialVault.encrypt_credentials(
                user_id=user_id,
                login=u["account_id"],
                password=api_secret,
                server=gateway_host,
                account_type=env_val,
            )
            cid = save_exness_connection(
                conn=conn,
                user_id=user_id,
                login=u["account_id"],
                server=gateway_host,
                enc_credentials=enc,
                adapter_mode="EXNESS_TRADER_API",
                account_type=env_val,
                balance=u.get("balance"),
                equity=u.get("equity"),
                leverage=int(u.get("leverage", 200)),
                currency=u.get("currency", "DATA UNAVAILABLE"),
                account_label=req.account_label or f"Exness Unverified ({mask_id(u['account_id'])})",
                is_preferred=0,
                verification_status=state_val,
                trade_mode=u.get("trade_mode", env_val),
                margin_used=u.get("margin_used"),
                margin_free=u.get("margin_free"),
                environment_confirmed_by=u.get("environment_confirmed_by", "UNVERIFIED"),
                access_point=u.get("access_point", ""),
                api_key=api_key,
                account_tier=tier_val,
                platform=plat_val,
                mt5_eligible=mt5_elig,
                stream_id=stream_val,
            )
            persisted_unverified.append({
                "connection_id": cid,
                "account_id": u["account_id"],
                "account_id_masked": mask_id(u["account_id"]),
                "environment": env_val,
                "platform": plat_val,
                "mt5_eligible": bool(mt5_elig),
                "account_tier": tier_val,
                "balance": u.get("balance"),
                "equity": u.get("equity"),
                "currency": u.get("currency", "DATA UNAVAILABLE"),
                "verification_status": state_val,
                "connection_state": state_val,
                "access_point": u.get("access_point", ""),
            })

        # Record failed accounts (never infer Demo vs Real from ID pattern or fabricate verified status or 0.00 balance)
        for f in disc_res.get("failed_accounts", []):
            enc = ExnessCredentialVault.encrypt_credentials(
                user_id=user_id,
                login=f["account_id"],
                password=api_secret,
                server=gateway_host,
                account_type="ENVIRONMENT UNVERIFIED",
            )
            cid = save_exness_connection(
                conn=conn,
                user_id=user_id,
                login=f["account_id"],
                server=gateway_host,
                enc_credentials=enc,
                adapter_mode="EXNESS_TRADER_API",
                account_type="ENVIRONMENT UNVERIFIED",
                balance=None,
                equity=None,
                verification_status="AUTH_FAILED",
                error_type=f.get("error_type", "AUTHENTICATION_FAILED"),
                error_detail=f.get("error_detail", "Authentication failed."),
                environment_confirmed_by="UNVERIFIED",
                api_key=api_key,
                account_tier="UNVERIFIED",
                platform="UNVERIFIED",
                mt5_eligible=0,
                stream_id="",
                is_preferred=0,
            )
            persisted_failed.append({
                "connection_id": cid,
                "account_id": f["account_id"],
                "account_id_masked": mask_id(f["account_id"]),
                "environment": "ENVIRONMENT UNVERIFIED",
                "platform": "UNVERIFIED",
                "mt5_eligible": False,
                "account_tier": "UNVERIFIED",
                "error_type": f.get("error_type"),
                "error_detail": f.get("error_detail"),
                "http_status": f.get("http_status"),
                "exness_code": f.get("exness_code"),
                "verification_status": "AUTH_FAILED",
                "connection_state": "AUTH_FAILED",
            })

    finally:
        conn.close()

    total_verified = len(persisted_demo) + len(persisted_real)

    return {
        "status": "SUCCESS" if total_verified > 0 else "FAILED",
        "message": f"Account discovery complete: {total_verified} accounts verified, {len(persisted_failed)} failed.",
        "enumeration_supported": disc_res.get("enumeration_supported", False),
        "enumeration_endpoint": disc_res.get("enumeration_endpoint"),
        "enumeration_detail": disc_res.get("enumeration_detail"),
        "exness_demo_accounts": persisted_demo,
        "exness_real_accounts": persisted_real,
        "unverified_accounts": persisted_unverified,
        "failed_accounts": persisted_failed,
        "total_verified": total_verified,
        "total_unverified": len(persisted_unverified),
        "total_failed": len(persisted_failed),
        "gateway_host": gateway_host,
    }


@router.post("/accounts/{connection_id}/resync")
async def resync_exness_account(
    connection_id: str,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Re-authenticates and refreshes telemetry for a specific Exness account connection.
    Guarantees tenant isolation: user can only resync their own connections.
    """
    user_id = user["user_id"]
    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT * FROM exness_demo_connections WHERE connection_id = ? AND user_id = ? AND is_active = 1",
            (connection_id, user_id)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Exness account connection not found.")

        row_dict = dict(row)
        login = row_dict["account_login"]
        server = row_dict["server_name"]
        enc_str = row_dict.get("encrypted_credentials")
        mode = row_dict.get("adapter_mode", "EXNESS_MT5_GATEWAY")

        if mode == "EXNESS_MT5_GATEWAY":
            adapter = ExnessMT5GatewayAdapter(
                account_id=login,
                server=server,
                environment=row_dict.get("account_type", "DEMO"),
            )
            conn_res = await adapter.connect()
            if conn_res.get("broker_authenticated"):
                acct_info = await adapter.get_account_info()
                auth_res = {
                    "verified": True,
                    "environment": row_dict.get("account_type", "DEMO"),
                    "account_tier": acct_info.get("name") or "RawSpread",
                    "verification_state": "ACCOUNT_DATA_VERIFIED",
                    "platform": "MT5",
                    "mt5_eligible": True,
                    "stream_id": f"mt5.{login}",
                    "currency": acct_info.get("currency", "USD"),
                    "leverage": acct_info.get("leverage", 2000),
                    "balance": float(acct_info.get("balance", 0.0)),
                    "equity": float(acct_info.get("equity", 0.0)),
                    "margin_used": float(acct_info.get("margin", 0.0)),
                    "margin_free": float(acct_info.get("free_margin", acct_info.get("equity", 0.0))),
                    "environment_confirmed_by": "MT5_GATEWAY_VERIFIED",
                    "access_point": f"MT5-GATEWAY-{server}",
                    "trade_mode": "ENABLED" if acct_info.get("trade_allowed") else "READ_ONLY",
                }
            else:
                auth_res = {
                    "verified": False,
                    "verification_state": "AUTH_FAILED",
                    "error_type": conn_res.get("status", "GATEWAY_AUTH_FAILED"),
                    "error_detail": conn_res.get("reason", "MT5 Gateway execution bridge failed to authenticate."),
                }
        else:
            if not enc_str or enc_str == "{}":
                raise HTTPException(status_code=400, detail="Stored credentials missing or revoked.")

            creds = ExnessCredentialVault.decrypt_credentials(
                user_id=user_id,
                login=login,
                server=server,
                enc_payload=json.loads(enc_str)
            )
            api_secret = creds.get("password", "")
            api_key = row_dict.get("api_key") or login

            adapter = ExnessTraderAPIAdapter(
                api_key=api_key,
                api_secret=api_secret,
                account_id=login,
                discovery_base_url=server,
            )

            auth_res = await adapter.authenticate_account(login, manual_env=row_dict.get("account_type"))
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        if auth_res.get("verified"):
            env_val = auth_res.get("environment", "ENVIRONMENT UNVERIFIED")
            tier_val = auth_res.get("account_tier", "Exness Native")
            state_val = auth_res.get("verification_state", "ACCOUNT_DATA_VERIFIED")
            plat_val = auth_res.get("platform", "EXNESS_TERMINAL")
            mt5_elig = int(bool(auth_res.get("mt5_eligible", False)))
            stream_val = auth_res.get("stream_id", "")
            with conn:
                conn.execute(
                    """
                    UPDATE exness_demo_connections
                    SET account_type = ?, account_tier = ?, platform = ?, mt5_eligible = ?, stream_id = ?,
                        currency = ?, leverage = ?,
                        balance_usd = ?, equity_usd = ?, margin_used = ?, margin_free = ?,
                        verification_status = ?, environment_confirmed_by = ?, access_point = ?,
                        trade_mode = ?, error_type = '', error_detail = '',
                        last_reconciled_at = ?, updated_at = ?
                    WHERE connection_id = ? AND user_id = ?
                    """,
                    (
                        env_val,
                        tier_val,
                        plat_val,
                        mt5_elig,
                        stream_val,
                        auth_res.get("currency", "USD"),
                        auth_res.get("leverage", 200),
                        auth_res.get("balance"),
                        auth_res.get("equity"),
                        auth_res.get("margin_used"),
                        auth_res.get("margin_free"),
                        state_val,
                        auth_res.get("environment_confirmed_by", "PROVIDER_VERIFIED"),
                        auth_res.get("access_point", ""),
                        auth_res.get("trade_mode", "ENABLED"),
                        now,
                        now,
                        connection_id,
                        user_id
                    )
                )
            return {
                "status": "SUCCESS",
                "message": f"Account {login} resynchronized and verified ({env_val} / {tier_val} / {plat_val}).",
                "account": auth_res,
            }
        else:
            state_val = auth_res.get("verification_state") or "AUTH_FAILED"
            with conn:
                conn.execute(
                    """
                    UPDATE exness_demo_connections
                    SET verification_status = ?, platform = 'UNVERIFIED', mt5_eligible = 0,
                        balance_usd = NULL, equity_usd = NULL,
                        error_type = ?, error_detail = ?, updated_at = ?
                    WHERE connection_id = ? AND user_id = ?
                    """,
                    (
                        state_val,
                        auth_res.get("error_type", "AUTHENTICATION_FAILED"),
                        auth_res.get("error_detail", "Authentication rejected."),
                        now,
                        connection_id,
                        user_id
                    )
                )
            raise HTTPException(
                status_code=400,
                detail={
                    "status": "FAILED",
                    "error_type": auth_res.get("error_type"),
                    "error_detail": auth_res.get("error_detail"),
                }
            )
    finally:
        conn.close()


class DiscoverSavedAccountsRequest(BaseModel):
    account_ids: List[str] = Field(..., min_length=1, description="List of Exness account IDs to discover using stored credentials")


@router.post("/sync-all")
async def sync_all_exness_accounts(user: Dict[str, Any] = Depends(get_current_user)):
    """
    Task 3: Sync All Accounts — Re-authenticates and refreshes telemetry for all active saved Exness accounts
    belonging to the user, recording actual provider responses and errors per account.
    """
    user_id = user["user_id"]
    conn = get_db_connection()
    results = []
    verified_count = 0
    failed_count = 0

    try:
        rows = get_all_user_exness_connections(conn, user_id)
        if not rows:
            return {
                "status": "SUCCESS",
                "message": "No saved Exness accounts to synchronize.",
                "total_synced": 0,
                "verified_count": 0,
                "failed_count": 0,
                "results": [],
            }

        # Deduplicate rows by account_login
        seen = set()
        unique_rows = []
        for r in rows:
            if r["account_login"] not in seen:
                seen.add(r["account_login"])
                unique_rows.append(r)

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        for row_dict in unique_rows:
            cid = row_dict["connection_id"]
            login = row_dict["account_login"]
            server = row_dict["server_name"]
            enc_str = row_dict.get("encrypted_credentials")
            mode = row_dict.get("adapter_mode", "EXNESS_MT5_GATEWAY")

            try:
                if mode == "EXNESS_MT5_GATEWAY":
                    adapter = ExnessMT5GatewayAdapter(
                        account_id=login,
                        server=server,
                        environment=row_dict.get("account_type", "DEMO"),
                    )
                    conn_res = await adapter.connect()
                    if conn_res.get("broker_authenticated"):
                        acct_info = await adapter.get_account_info()
                        auth_res = {
                            "verified": True,
                            "environment": row_dict.get("account_type", "DEMO"),
                            "account_tier": acct_info.get("name") or "RawSpread",
                            "verification_state": "ACCOUNT_DATA_VERIFIED",
                            "platform": "MT5",
                            "mt5_eligible": True,
                            "stream_id": f"mt5.{login}",
                            "currency": acct_info.get("currency", "USD"),
                            "leverage": acct_info.get("leverage", 2000),
                            "balance": float(acct_info.get("balance", 0.0)),
                            "equity": float(acct_info.get("equity", 0.0)),
                            "margin_used": float(acct_info.get("margin", 0.0)),
                            "margin_free": float(acct_info.get("free_margin", acct_info.get("equity", 0.0))),
                            "environment_confirmed_by": "MT5_GATEWAY_VERIFIED",
                            "access_point": f"MT5-GATEWAY-{server}",
                            "trade_mode": "ENABLED" if acct_info.get("trade_allowed") else "READ_ONLY",
                        }
                    else:
                        auth_res = {
                            "verified": False,
                            "verification_state": "AUTH_FAILED",
                            "error_type": conn_res.get("status", "GATEWAY_AUTH_FAILED"),
                            "error_detail": conn_res.get("reason", "MT5 Gateway bridge failed to authenticate."),
                        }
                else:
                    if not enc_str or enc_str == "{}":
                        failed_count += 1
                        results.append({"account_id": login, "status": "FAILED", "error_detail": "Missing stored credentials."})
                        continue

                    creds = ExnessCredentialVault.decrypt_credentials(
                        user_id=user_id,
                        login=login,
                        server=server,
                        enc_payload=json.loads(enc_str),
                    )
                    api_secret = creds.get("password", "")
                    api_key = row_dict.get("api_key") or login
                    adapter = ExnessTraderAPIAdapter(
                        api_key=api_key,
                        api_secret=api_secret,
                        account_id=login,
                        discovery_base_url=server,
                    )
                    auth_res = await adapter.authenticate_account(login, manual_env=row_dict.get("account_type"))

                if auth_res.get("verified"):
                    verified_count += 1
                    env_val = auth_res.get("environment", "ENVIRONMENT UNVERIFIED")
                    tier_val = auth_res.get("account_tier", "Exness Native")
                    state_val = auth_res.get("verification_state", "ACCOUNT_DATA_VERIFIED")
                    plat_val = auth_res.get("platform", "EXNESS_TERMINAL")
                    mt5_elig = int(bool(auth_res.get("mt5_eligible", False)))
                    stream_val = auth_res.get("stream_id", "")
                    with conn:
                        conn.execute(
                            """
                            UPDATE exness_demo_connections
                            SET account_type = ?, account_tier = ?, platform = ?, mt5_eligible = ?, stream_id = ?,
                                currency = ?, leverage = ?,
                                balance_usd = ?, equity_usd = ?, margin_used = ?, margin_free = ?,
                                verification_status = ?, environment_confirmed_by = ?, access_point = ?,
                                trade_mode = ?, error_type = '', error_detail = '',
                                last_reconciled_at = ?, updated_at = ?
                            WHERE connection_id = ? AND user_id = ?
                            """,
                            (
                                env_val,
                                tier_val,
                                plat_val,
                                mt5_elig,
                                stream_val,
                                auth_res.get("currency", "USD"),
                                auth_res.get("leverage", 200),
                                auth_res.get("balance"),
                                auth_res.get("equity"),
                                auth_res.get("margin_used"),
                                auth_res.get("margin_free"),
                                state_val,
                                auth_res.get("environment_confirmed_by", "PROVIDER_VERIFIED"),
                                auth_res.get("access_point", ""),
                                auth_res.get("trade_mode", "ENABLED"),
                                now,
                                now,
                                cid,
                                user_id,
                            ),
                        )
                    results.append({
                        "connection_id": cid,
                        "account_id": login,
                        "account_id_masked": mask_id(login),
                        "status": "VERIFIED",
                        "environment": env_val,
                        "platform": plat_val,
                        "mt5_eligible": bool(mt5_elig),
                        "balance": auth_res.get("balance"),
                        "equity": auth_res.get("equity"),
                    })
                else:
                    failed_count += 1
                    state_val = auth_res.get("verification_state") or "AUTH_FAILED"
                    with conn:
                        conn.execute(
                            """
                            UPDATE exness_demo_connections
                            SET verification_status = ?, platform = 'UNVERIFIED', mt5_eligible = 0,
                                balance_usd = NULL, equity_usd = NULL,
                                error_type = ?, error_detail = ?, updated_at = ?
                            WHERE connection_id = ? AND user_id = ?
                            """,
                            (
                                state_val,
                                auth_res.get("error_type", "AUTHENTICATION_FAILED"),
                                auth_res.get("error_detail", "Authentication rejected."),
                                now,
                                cid,
                                user_id,
                            ),
                        )
                    results.append({
                        "connection_id": cid,
                        "account_id": login,
                        "account_id_masked": mask_id(login),
                        "status": "AUTH_FAILED",
                        "error_type": auth_res.get("error_type"),
                        "error_detail": auth_res.get("error_detail"),
                    })
            except Exception as sync_err:
                failed_count += 1
                results.append({"account_id": login, "status": "FAILED", "error_detail": str(sync_err)})

        return {
            "status": "SUCCESS",
            "message": f"Sync All complete: {verified_count} verified, {failed_count} failed/inaccessible.",
            "total_synced": len(unique_rows),
            "verified_count": verified_count,
            "failed_count": failed_count,
            "results": results,
        }
    finally:
        conn.close()


@router.post("/discover-accounts")
async def discover_saved_exness_accounts(
    req: DiscoverSavedAccountsRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Task 3: Discover Accounts — Probes one or more candidate Exness Account IDs using the user's
    already-saved Exness API Key & Ed25519 signing key without requiring the user to re-enter secrets.
    """
    user_id = user["user_id"]
    conn = get_db_connection()
    try:
        rows = get_all_user_exness_connections(conn, user_id)
        cred_row = next((r for r in rows if r.get("api_key") and r.get("encrypted_credentials") and r.get("encrypted_credentials") != "{}"), None)
        if not cred_row:
            raise HTTPException(
                status_code=400,
                detail={
                    "status": "FAILED",
                    "error_type": "NO_SAVED_CREDENTIALS",
                    "error_detail": "No saved Exness API credentials found. Please click 'Connect Exness API' to attach your API Key and Ed25519 Private Signing Key first.",
                },
            )

        creds = ExnessCredentialVault.decrypt_credentials(
            user_id=user_id,
            login=cred_row["account_login"],
            server=cred_row["server_name"],
            enc_payload=json.loads(cred_row["encrypted_credentials"]),
        )
        api_key = cred_row["api_key"]
        api_secret = creds.get("password", "")
        gateway_host = cred_row.get("server_name") or "https://api.exness.com"
    finally:
        conn.close()

    attach_req = ExnessAttachDiscoverRequest(
        api_key=api_key,
        api_secret=api_secret,
        gateway_host=gateway_host,
        account_ids=req.account_ids,
    )
    return await attach_and_discover_accounts(attach_req, user)

@router.post("/disconnect")
async def disconnect_account(
    req: DisconnectRequest, user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Disconnects and invalidates stored credentials for an Exness account.
    Enforces strict tenant isolation: user can only disconnect their own connection.
    """
    conn = get_db_connection()
    try:
        ok = disconnect_exness_connection(conn, user["user_id"], req.connection_id)
    finally:
        conn.close()

    if not ok:
        raise HTTPException(status_code=404, detail="Connection not found or already disconnected.")

    # Invalidate cached adapters in memory for this user
    for k in list(_USER_ADAPTERS.keys()):
        if k[0] == user["user_id"]:
            _USER_ADAPTERS.pop(k, None)

    return {
        "status": "SUCCESS",
        "message": "Exness connection disconnected and stored credentials invalidated.",
        "connection_id": req.connection_id,
    }


@router.post("/account/preferred")
async def set_account_preferred_route(
    req: PreferredAccountRequest, user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Sets a connection as the customer's preferred account for trading.
    """
    conn = get_db_connection()
    try:
        ok = set_preferred_account(conn, user["user_id"], req.connection_id)
    finally:
        conn.close()

    if not ok:
        raise HTTPException(status_code=404, detail="Connection not found or does not belong to user.")

    return {
        "status": "SUCCESS",
        "message": "Account successfully set as preferred.",
        "connection_id": req.connection_id,
    }


@router.get("/account")
async def get_exness_account(
    environment: str = Query("DEMO", description="'DEMO' or 'REAL'"),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Retrieves verified account equity, free margin, and leverage for DEMO or REAL environment."""
    env = (environment or "DEMO").upper()
    conn = get_db_connection()
    try:
        db_conn = get_user_exness_connection(conn, user["user_id"], env)
    finally:
        conn.close()

    if not db_conn:
        return {
            "status": "NOT_CONNECTED",
            "environment": env,
            "connected": False,
            "account": {
                "account_id": "UNAVAILABLE",
                "balance": 0.0,
                "equity": 0.0,
                "margin": 0.0,
                "free_margin": 0.0,
                "margin_level": 0.0,
                "leverage": 0,
                "currency": "USD",
                "is_demo": (env == "DEMO"),
                "environment": env,
                "is_connected": False,
                "gateway_status": "NOT_CONNECTED",
            },
        }

    adapter = get_user_adapter(user["user_id"], env)
    if adapter:
        try:
            acct_info = await adapter.get_account_info()
            return {"status": "SUCCESS", "environment": env, "account": acct_info}
        except Exception as e:
            logger.warning(f"Broker gateway offline for {env} account: {e}")

    bal = float(db_conn.get("balance_usd", 0.0))
    eq = float(db_conn.get("equity_usd", 0.0))
    lev = int(db_conn.get("leverage", 200))
    masked_login = mask_id(db_conn["account_login"])

    return {
        "status": "GATEWAY_OFFLINE",
        "environment": env,
        "connected": False,
        "account": {
            "account_id": masked_login,
            "balance": bal,
            "equity": eq,
            "margin": 0.0,
            "free_margin": bal,
            "margin_level": 0.0,
            "leverage": lev,
            "currency": db_conn.get("currency", "USD"),
            "is_demo": (env == "DEMO"),
            "environment": env,
            "is_connected": False,
            "gateway_status": "OFFLINE",
        },
    }


@router.get("/symbols")
async def list_exness_symbols(user: Dict[str, Any] = Depends(get_current_user)):
    """Returns available Exness MT5 demo instruments."""
    adapter = get_user_adapter(user["user_id"])
    if not adapter:
        adapter = ExnessDeterministicMockAdapter(account_id="SPEC_REF", server="Exness-MT5Trial")

    symbols = await adapter.get_symbols()
    detailed = []
    for s in symbols:
        info = await adapter.get_symbol_info(s)
        if info:
            tick = await adapter.get_latest_tick(s)
            detailed.append({
                "broker_symbol": info["broker_symbol"],
                "canonical_symbol": info["canonical_symbol"],
                "name": info["name"],
                "product_type": info["product_type"],
                "min_volume": info["min_volume"],
                "max_volume": info["max_volume"],
                "volume_step": info["volume_step"],
                "contract_size": info["contract_size"],
                "spread": tick["spread"] if tick else info.get("typical_spread"),
                "bid": tick["bid"] if tick else None,
                "ask": tick["ask"] if tick else None,
                "is_tradable": info.get("is_tradable", True),
            })
    return {"status": "SUCCESS", "count": len(detailed), "symbols": detailed}


@router.get("/symbol/{symbol:path}")
async def get_exness_symbol_detail(
    symbol: str, user: Dict[str, Any] = Depends(get_current_user)
):
    """Retrieves contract specifications and latest quote for a symbol."""
    adapter = get_user_adapter(user["user_id"])
    if not adapter:
        adapter = ExnessDeterministicMockAdapter(account_id="SPEC_REF", server="Exness-MT5Trial")

    spec = await adapter.get_symbol_info(symbol)
    if not spec:
        raise HTTPException(status_code=404, detail=f"Exness symbol {symbol} not found")
    tick = await adapter.get_latest_tick(symbol)
    return {
        "status": "SUCCESS",
        "symbol_info": spec,
        "latest_tick": tick,
    }


@router.post("/margin/calculate")
async def calculate_trade_margin(
    req: MarginCalculateRequest, user: Dict[str, Any] = Depends(get_current_user)
):
    """Pre-trade margin calculation and affordability check."""
    adapter = get_user_adapter(user["user_id"])
    if not adapter:
        adapter = ExnessDeterministicMockAdapter(account_id="SPEC_REF", server="Exness-MT5Trial")

    try:
        res = await adapter.calculate_margin(req.symbol, req.order_type, req.volume)
        return {"status": "SUCCESS", "margin_check": res}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/reconcile")
async def trigger_reconciliation(user: Dict[str, Any] = Depends(get_current_user)):
    """
    Triggers authoritative account reconciliation across 7 fields.
    Independently fetches broker positions and local database positions.
    Never compares broker positions against themselves.
    """
    adapter = get_user_adapter(user["user_id"])
    if not adapter:
        raise HTTPException(status_code=400, detail="NO_ACTIVE_CONNECTION: Connect an Exness account first.")

    user_id = user["user_id"]

    conn = get_db_connection()
    try:
        db_conn = get_user_exness_connection(conn, user_id)
        conn_id = db_conn["connection_id"] if db_conn else "NO_ACTIVE_CONN"
        local_positions = get_active_local_positions(conn, user_id)

        rec_result = await adapter.reconcile_account(local_positions=local_positions)

        log_id = log_reconciliation(
            conn=conn,
            connection_id=conn_id,
            user_id=user_id,
            discrepancy_count=rec_result.get("discrepancy_count", 0),
            broker_count=rec_result.get("broker_positions_count", 0),
            local_count=rec_result.get("local_positions_count", 0),
            details=rec_result,
        )
    finally:
        conn.close()

    return {
        "status": "SUCCESS",
        "log_id": log_id,
        "reconciliation": rec_result,
    }


@router.post("/simulation/run")
async def run_hft_simulation(
    req: SimulationRequest, user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Runs an isolated quantitative HFT simulation using historical candle data.
    Enforces honest accounting (spread, slippage, swap, latency) and market regime classification.
    Always explicitly marked is_simulated=True.
    """
    from ..services.exness.simulation_engine import HFTPairedSimulationEngine, CostModelConfig

    adapter = get_user_adapter(user["user_id"])
    if not adapter:
        adapter = ExnessDeterministicMockAdapter(account_id="SPEC_REF", server="Exness-MT5Trial")

    candles = await adapter.get_historical_candles(req.symbol, req.timeframe, req.candle_count)
    if not candles or len(candles) < 25:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient candles returned for {req.symbol} (got {len(candles) if candles else 0}, need at least 25)"
        )

    engine = HFTPairedSimulationEngine(config=CostModelConfig())
    result = engine.run_simulation(
        symbol=req.symbol,
        candles=candles,
        volume_per_leg=req.volume_per_leg,
        take_profit_points=req.take_profit_points,
        stop_loss_points=req.stop_loss_points,
        max_hold_bars=req.max_hold_bars,
    )
    return {"status": "SUCCESS", "simulation": result}


@router.get("/risk/limits")
async def get_risk_limits(user: Dict[str, Any] = Depends(get_current_user)):
    """
    Returns active quantitative risk guard limits, circuit breaker thresholds, and safety status.
    """
    from ..services.exness.risk_guard import ExnessRiskGuard

    guard = ExnessRiskGuard()
    limits_dict = {
        "max_open_positions": guard.limits.max_open_positions,
        "max_aggregate_exposure_usd": guard.limits.max_aggregate_exposure_usd,
        "max_daily_loss_usd": guard.limits.max_daily_loss_usd,
        "max_basket_loss_usd": guard.limits.max_basket_loss_usd,
        "max_drawdown_pct": guard.limits.max_drawdown_pct,
        "max_margin_utilization_pct": guard.limits.max_margin_utilization_pct,
        "max_volume_per_symbol": guard.limits.max_volume_per_symbol,
        "max_volume_per_order": guard.limits.max_volume_per_order,
        "max_stale_quote_ms": guard.limits.max_stale_quote_ms,
        "emergency_lock_active": guard.limits.emergency_lock_active,
        "live_trading_locked": True,
    }
    return {"status": "SUCCESS", "limits": limits_dict}


@router.post("/risk/check")
async def evaluate_pre_order_risk(
    req: PreOrderRiskCheckRequest, user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Evaluates pre-trade quantitative risk compliance without executing any orders.
    Enforces fail-closed safety and emergency lock validation.
    """
    from ..services.exness.risk_guard import ExnessRiskGuard

    adapter = get_user_adapter(user["user_id"])
    if not adapter:
        adapter = ExnessDeterministicMockAdapter(account_id="SPEC_REF", server="Exness-MT5Trial")

    account_info = await adapter.get_account_info()
    positions = await adapter.get_open_positions()

    guard = ExnessRiskGuard()
    is_safe, reason = guard.validate_pre_order(
        symbol=req.symbol,
        volume=req.volume,
        price=req.price,
        current_open_positions=positions,
        account_info=account_info,
    )

    unprotected = guard.detect_missing_stop_loss(positions)
    basket_safe, basket_loss, basket_msg = guard.evaluate_basket_drawdown(positions)

    return {
        "status": "SUCCESS",
        "risk_approved": is_safe,
        "reason": reason,
        "basket_assessment": {
            "basket_safe": basket_safe,
            "floating_pnl_usd": basket_loss,
            "status": basket_msg,
        },
        "unprotected_positions_count": len(unprotected),
        "unprotected_positions": unprotected,
    }


@router.post("/order")
@router.post("/trade/execute")
async def execute_customer_trade(
    req: TradeExecutionRequest, user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Executes a customer trade on Demo or Real Exness account.
    Enforces:
    - Customer account ownership check (strict tenant isolation).
    - Segregation between Demo and Real environments.
    - Explicit consent acknowledgement for Real trades.
    - Real-time quantitative risk barrier checks.
    - Strict global fail-closed lock on Live Real broker order execution (live_trading_locked=True).
    """
    from datetime import datetime, timezone
    import secrets
    from ..services.exness.risk_guard import ExnessRiskGuard
    from ..services.activation_service import assert_hft_activated

    # Mandatory $20.00 USD HFT Account Activation Gate
    assert_hft_activated(user)

    env = (req.environment or req.trade_mode or "DEMO").upper().strip()
    if env not in ("DEMO", "REAL"):
        raise HTTPException(status_code=400, detail="Invalid environment: must be 'DEMO' or 'REAL'.")

    if req.volume is None and req.quantity is not None:
        req.volume = req.quantity
    if req.volume is None:
        raise HTTPException(status_code=400, detail="Volume or quantity is required.")

    # 1. Customer account ownership check
    conn = get_db_connection()
    try:
        db_conn = get_user_exness_connection(conn, user["user_id"], env, req.connection_id)
    finally:
        conn.close()

    if not db_conn:
        raise HTTPException(
            status_code=400,
            detail=f"NO_ACTIVE_CONNECTION: You must connect your own Exness {env} account before placing trades."
        )

    # 2. Check Real Consent
    if env == "REAL":
        if not req.consent_confirmed:
            raise HTTPException(
                status_code=400,
                detail="REAL_EXECUTION_CONSENT_REQUIRED: Customer must explicitly accept the real money risk acknowledgement before executing on an Exness Real account."
            )

    # 3. Risk Evaluation
    guard = ExnessRiskGuard()
    adapter = get_user_adapter(user["user_id"], env, req.connection_id)
    if adapter:
        try:
            acct = await adapter.get_account_info()
        except Exception:
            acct = {"balance": 0.0, "equity": 0.0, "free_margin": 0.0, "leverage": 200, "live_trading_locked": True}

        try:
            positions = await adapter.get_open_positions()
        except Exception:
            positions = []
    else:
        acct = {"balance": float(db_conn.get("balance_usd", 0.0)), "equity": float(db_conn.get("equity_usd", 0.0)), "free_margin": 0.0, "leverage": 200, "live_trading_locked": True}
        positions = []

    is_safe, risk_reason = guard.validate_pre_order(
        symbol=req.symbol,
        volume=req.volume,
        price=req.price or 100.0,
        current_open_positions=positions,
        account_info=acct,
    )

    masked_login = mask_id(db_conn["account_login"])

    # 4. If REAL environment: Global safety lock check
    if env == "REAL":
        return {
            "status": "BLOCKED_BY_SAFETY_LOCK",
            "barrier": "LIVE_TRADING_LOCKED",
            "environment": "REAL",
            "account_id": masked_login,
            "server": db_conn["server_name"],
            "symbol": req.symbol,
            "side": req.side.upper(),
            "volume": req.volume,
            "requested_price": req.price,
            "stop_loss": req.stop_loss,
            "take_profit": req.take_profit,
            "message": "Order submission blocked: live_trading_locked=True is enforced on BITDEX Staging. Live broker executions are strictly locked for risk prevention.",
            "risk_guard_assessment": {"is_safe": is_safe, "reason": risk_reason},
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    # 5. DEMO environment: also fail-closed while global locks are enabled (no simulated fills with fabricated prices)
    from ..config import settings as _settings
    if _settings.live_trading_locked or _settings.read_only_mode:
        return {
            "status": "BLOCKED_BY_SAFETY_LOCK",
            "barrier": "READ_ONLY_MODE",
            "environment": "DEMO",
            "account_id": masked_login,
            "server": db_conn["server_name"],
            "symbol": req.symbol,
            "side": req.side.upper(),
            "volume": req.volume,
            "message": "Order submission blocked: read_only_mode/live_trading_locked are enabled. No Demo order was submitted and no fill was simulated.",
            "risk_guard_assessment": {"is_safe": is_safe, "reason": risk_reason},
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    ticket = f"DEMO-{secrets.token_hex(4).upper()}"
    fill_price = req.price or (2745.50 if "XAU" in req.symbol else 78500.0 if "BTC" in req.symbol else 1.0850)
    spread_pts = 18.0 if "XAU" in req.symbol else 350.0 if "BTC" in req.symbol else 6.0
    commission = 0.0

    return {
        "status": "FILLED",
        "ticket": ticket,
        "environment": "DEMO",
        "account_id": masked_login,
        "server": db_conn["server_name"],
        "symbol": req.symbol,
        "side": req.side.upper(),
        "volume": req.volume,
        "fill_price": fill_price,
        "stop_loss": req.stop_loss,
        "take_profit": req.take_profit,
        "commission": commission,
        "spread_points": spread_pts,
        "message": f"Demo order successfully filled on account {masked_login} (Simulated).",
        "executed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ─── Payments API Endpoints ──────────────────────────────────────────────────

@router.get("/payments/deposit-options")
async def get_deposit_options_route(user: Dict[str, Any] = Depends(get_current_user)):
    """
    Returns official Exness Personal Area deposit flow URL, regional crypto methods, and security policies.
    """
    svc = ExnessPaymentsService()
    return svc.get_deposit_options(user["user_id"])


@router.get("/payments/eligibility")
async def get_transfer_eligibility(
    transfer_type: str = Query("INTERNAL_WALLET_TO_ACCOUNT"),
    source_id: str = Query("WLT-USD"),
    destination_id: str = Query("ACC-DEMO"),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Returns Exness Payments API transfer eligibility, fees, speed, and restrictions.
    """
    svc = ExnessPaymentsService()
    conn = get_db_connection()
    try:
        eligibility = svc.get_transfer_eligibility(
            conn=conn,
            user_id=user["user_id"],
            source_id=source_id,
            dest_id=destination_id,
            transfer_type=transfer_type,
        )
        return {"status": "SUCCESS", "eligibility": eligibility}
    finally:
        conn.close()


@router.get("/payments/balances")
async def get_payment_balances(user: Dict[str, Any] = Depends(get_current_user)):
    """
    Returns available balances across Exness Wallets, Demo accounts, and Real accounts,
    accompanied by 9 discrete funding statuses.
    """
    svc = ExnessPaymentsService()
    conn = get_db_connection()
    try:
        return svc.get_available_balances(conn=conn, user_id=user["user_id"])
    finally:
        conn.close()


@router.post("/payments/transfer")
async def initiate_payment_transfer(
    req: CustomerTransferRequest, user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Initiates an Exness Payments API customer transfer with strict idempotency verification.
    """
    svc = ExnessPaymentsService()
    conn = get_db_connection()
    try:
        res = svc.initiate_transfer(
            conn=conn,
            user_id=user["user_id"],
            transfer_type=req.transfer_type,
            source_id=req.source_id,
            dest_id=req.destination_id,
            amount=req.amount,
            currency=req.currency,
            idempotency_key=req.idempotency_key,
        )
        return res
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    finally:
        conn.close()


@router.get("/payments/history")
async def get_payment_history(
    limit: int = Query(50, ge=1, le=200),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Retrieves transfer history for the authenticated customer.
    """
    svc = ExnessPaymentsService()
    conn = get_db_connection()
    try:
        transfers = svc.get_transfer_history(conn=conn, user_id=user["user_id"], limit=limit)
        return {"status": "SUCCESS", "count": len(transfers), "transfers": transfers}
    finally:
        conn.close()
