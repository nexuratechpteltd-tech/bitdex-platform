"""
Exness High-Frequency Trading (HFT) API Router (Hardened Phase 2.2)
Enforces strict broker connection semantics, separate authentication fields,
persisted adapter mode restoration (no accidental mock fallback on restart),
secure password pass-through to gateway, and authoritative multi-field reconciliation.
Specification reference: Master Exness HFT Implementation Specification, Part 4 & Part 11.
"""

import json
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..services.saas_db import get_db_connection
from ..services.auth_manager import get_current_user
from ..services.exness.mock_adapter import ExnessDeterministicMockAdapter
from ..services.exness.mt5_gateway_adapter import ExnessMT5GatewayAdapter
from ..services.exness.vault import ExnessCredentialVault
from ..services.exness.exness_db import (
    get_user_exness_connection,
    save_exness_connection,
    get_active_local_positions,
    log_reconciliation,
)

logger = logging.getLogger("bitdex.routes.exness_hft")

router = APIRouter(prefix="/hft/exness", tags=["Exness HFT"])

# In-memory adapter instances keyed by user_id
_USER_ADAPTERS: Dict[str, Any] = {}


def get_user_adapter(user_id: str) -> Any:
    """
    Returns or instantiates the user's active Exness adapter.
    Restores the persisted adapter mode from database rather than silently defaulting to mock.
    Guarantees multi-user isolation.
    """
    if user_id in _USER_ADAPTERS:
        return _USER_ADAPTERS[user_id]

    conn = get_db_connection()
    try:
        db_conn = get_user_exness_connection(conn, user_id)
        if db_conn:
            login = db_conn["account_login"]
            server = db_conn["server_name"]
            mode = db_conn.get("adapter_mode", "DETERMINISTIC_MOCK_DEMO")

            if mode == "EXNESS_MT5_GATEWAY":
                adapter = ExnessMT5GatewayAdapter(
                    account_id=login,
                    server=server,
                )
            else:
                adapter = ExnessDeterministicMockAdapter(
                    account_id=login,
                    server=server,
                    initial_balance=float(db_conn.get("balance_usd", 5000.0)),
                )
            _USER_ADAPTERS[user_id] = adapter
            return adapter
    finally:
        conn.close()

    # Default fallback only when user has zero saved connections
    adapter = ExnessDeterministicMockAdapter(
        account_id="149827361",
        server="Exness-MT5Trial",
        initial_balance=5000.0,
    )
    _USER_ADAPTERS[user_id] = adapter
    return adapter


class ExnessConnectRequest(BaseModel):
    account_login: str = Field(..., min_length=4, max_length=32, description="Exness MT5 account login ID")
    password: str = Field(..., min_length=4, max_length=128, description="Exness MT5 trading password")
    server_name: str = Field(default="Exness-MT5Trial", description="Exness MT5 trial/demo server name")
    use_mock: bool = Field(default=True, description="Explicit mode selection: True for simulated mock, False for real MT5 gateway")


class MarginCalculateRequest(BaseModel):
    symbol: str = Field(..., min_length=3)
    order_type: str = Field(default="BUY")
    volume: float = Field(default=0.01, gt=0)


@router.get("/status")
async def get_exness_status(user: Dict[str, Any] = Depends(get_current_user)):
    """
    Returns Exness HFT subsystem status, execution locks, and discrete connection semantics.
    Separates adapter connection from broker authentication.
    """
    adapter = get_user_adapter(user["user_id"])
    conn_status = await adapter.get_connection_status()

    conn = get_db_connection()
    try:
        db_conn = get_user_exness_connection(conn, user["user_id"])
    finally:
        conn.close()

    return {
        "status": "SUCCESS",
        "broker": "Exness MT5",
        "environment": "DEMO_ONLY",
        "live_trading_locked": True,
        "adapter_connected": conn_status.get("adapter_connected", False),
        "broker_authenticated": conn_status.get("broker_authenticated", False),
        "is_mock": conn_status.get("is_mock", True),
        "broker_mode": conn_status.get("broker_mode", "DETERMINISTIC_MOCK_DEMO"),
        "connection_type": conn_status.get("connection_type", "SIMULATED_DEMO"),
        "is_connected": conn_status.get("is_connected", False),
        "active_connection": (
            {
                "connection_id": db_conn["connection_id"],
                "account_login": db_conn["account_login"],
                "server_name": db_conn["server_name"],
                "account_type": db_conn["account_type"],
                "adapter_mode": db_conn.get("adapter_mode", "DETERMINISTIC_MOCK_DEMO"),
                "balance_usd": db_conn["balance_usd"],
                "equity_usd": db_conn["equity_usd"],
                "last_reconciled_at": db_conn["last_reconciled_at"],
            }
            if db_conn
            else None
        ),
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

    # Encrypt credentials via vault
    enc_creds = ExnessCredentialVault.encrypt_credentials(
        user_id=user_id,
        login=req.account_login,
        password=req.password,
        server=req.server_name,
        account_type="DEMO",
    )

    if req.use_mock:
        # Deterministic Mock Demo Mode (Simulated)
        adapter = ExnessDeterministicMockAdapter(
            account_id=req.account_login,
            server=req.server_name,
            initial_balance=5000.0,
        )
        conn_res = await adapter.connect()
        _USER_ADAPTERS[user_id] = adapter
        acct_info = await adapter.get_account_info()

        # Save to database with persisted adapter_mode
        conn = get_db_connection()
        try:
            conn_id = save_exness_connection(
                conn=conn,
                user_id=user_id,
                login=req.account_login,
                server=req.server_name,
                enc_credentials=enc_creds,
                adapter_mode="DETERMINISTIC_MOCK_DEMO",
                balance=acct_info["balance"],
                equity=acct_info["equity"],
                leverage=acct_info["leverage"],
            )
        finally:
            conn.close()

        return {
            "status": "SUCCESS",
            "connection_id": conn_id,
            "adapter_connected": True,
            "broker_authenticated": False,  # Explicitly simulated
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
        )

        try:
            conn_res = await gateway_adapter.connect(password=req.password)
        except (ValueError, PermissionError) as exc:
            # Identity mismatch or non-demo account rejection
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

        # If gateway is offline or unauthenticated, fail closed without accidental mock fallback
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

        _USER_ADAPTERS[user_id] = gateway_adapter
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
                balance=acct_info.get("balance", 0.0),
                equity=acct_info.get("equity", 0.0),
                leverage=acct_info.get("leverage", 2000),
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


@router.get("/account")
async def get_exness_account(user: Dict[str, Any] = Depends(get_current_user)):
    """Retrieves verified demo account equity, free margin, and leverage."""
    adapter = get_user_adapter(user["user_id"])
    try:
        acct_info = await adapter.get_account_info()
        return {"status": "SUCCESS", "account": acct_info}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/symbols")
async def list_exness_symbols(user: Dict[str, Any] = Depends(get_current_user)):
    """Returns available Exness MT5 demo instruments."""
    adapter = get_user_adapter(user["user_id"])
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
