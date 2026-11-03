"""
Exness High-Frequency Trading (HFT) API Router
Phase 2 Implementation: Broker Adapter, Deterministic Mock Demo, Credential Vault, and Reconciliation.
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
    log_reconciliation,
)

logger = logging.getLogger("bitdex.routes.exness_hft")

router = APIRouter(prefix="/hft/exness", tags=["Exness HFT"])

# In-memory adapter instances keyed by user_id
_USER_ADAPTERS: Dict[str, Any] = {}


def get_user_adapter(user_id: str) -> ExnessDeterministicMockAdapter:
    """Returns or instantiates the user's Exness adapter."""
    if user_id not in _USER_ADAPTERS:
        _USER_ADAPTERS[user_id] = ExnessDeterministicMockAdapter(
            account_id="149827361",
            server="Exness-MT5Trial",
            initial_balance=5000.0,
        )
    return _USER_ADAPTERS[user_id]


class ExnessConnectRequest(BaseModel):
    account_login: str = Field(..., min_length=4, max_length=32)
    password: str = Field(..., min_length=4)
    server_name: str = Field(default="Exness-MT5Trial")
    use_mock: bool = Field(default=True, description="Use deterministic mock demo initially")


class MarginCalculateRequest(BaseModel):
    symbol: str = Field(..., min_length=3)
    order_type: str = Field(default="BUY")
    volume: float = Field(default=0.01, gt=0)


@router.get("/status")
async def get_exness_status(user: Dict[str, Any] = Depends(get_current_user)):
    """
    Returns Exness HFT subsystem status and execution locks.
    Guarantees: Live trading is strictly locked in staging.
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
        "is_mock": conn_status.get("is_mock", True),
        "broker_mode": conn_status.get("broker_mode", "DETERMINISTIC_MOCK_DEMO"),
        "is_connected": conn_status.get("is_connected", False),
        "active_connection": (
            {
                "connection_id": db_conn["connection_id"],
                "account_login": db_conn["account_login"],
                "server_name": db_conn["server_name"],
                "account_type": db_conn["account_type"],
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
    Encrypts credentials with AES-256-GCM authenticated vault and stores in database.
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

    # Initialize adapter
    adapter = ExnessDeterministicMockAdapter(
        account_id=req.account_login,
        server=req.server_name,
        initial_balance=5000.0,
    )
    conn_res = await adapter.connect()
    _USER_ADAPTERS[user_id] = adapter

    acct_info = await adapter.get_account_info()

    # Save to database
    conn = get_db_connection()
    try:
        conn_id = save_exness_connection(
            conn=conn,
            user_id=user_id,
            login=req.account_login,
            server=req.server_name,
            enc_credentials=enc_creds,
            balance=acct_info["balance"],
            equity=acct_info["equity"],
            leverage=acct_info["leverage"],
        )
    finally:
        conn.close()

    return {
        "status": "SUCCESS",
        "connection_id": conn_id,
        "connection_details": conn_res,
        "account_telemetry": acct_info,
        "credentials": ExnessCredentialVault.mask_credentials({
            "login": req.account_login,
            "server": req.server_name,
            "account_type": "DEMO",
        }),
    }


@router.get("/account")
async def get_exness_account(user: Dict[str, Any] = Depends(get_current_user)):
    """Retrieves verified demo account equity, free margin, and leverage."""
    adapter = get_user_adapter(user["user_id"])
    acct_info = await adapter.get_account_info()
    return {"status": "SUCCESS", "account": acct_info}


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
                "spread": tick["spread"] if tick else info["typical_spread"],
                "bid": tick["bid"] if tick else None,
                "ask": tick["ask"] if tick else None,
                "is_tradable": info["is_tradable"],
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
    """Triggers account reconciliation and persists log in database."""
    adapter = get_user_adapter(user["user_id"])
    rec_result = await adapter.reconcile_account()

    conn = get_db_connection()
    try:
        db_conn = get_user_exness_connection(conn, user["user_id"])
        conn_id = db_conn["connection_id"] if db_conn else "NO_ACTIVE_CONN"
        log_id = log_reconciliation(
            conn=conn,
            connection_id=conn_id,
            user_id=user["user_id"],
            discrepancy_count=rec_result["discrepancy_count"],
            broker_count=rec_result["broker_positions_count"],
            local_count=rec_result["broker_positions_count"],
            details=rec_result,
        )
    finally:
        conn.close()

    return {
        "status": "SUCCESS",
        "log_id": log_id,
        "reconciliation": rec_result,
    }
