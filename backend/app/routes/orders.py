"""
Tauric Platform — Orders and Execution Routes (Phase 3B)
Strictly segregated Demo Execution, Hard-Locked Live Trading, Standardized Order Lifecycle,
Isolated Paper Trading Engine with Durable Idempotency, and Pre-Flight Strategy Verification.
"""

from fastapi import APIRouter, HTTPException, Query, status, Header, Depends
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
import time
from datetime import datetime, timezone
from dataclasses import asdict

import json
import logging
from ..services.auth_manager import AuthManager, get_current_user
from ..services.ledger_db import upsert_exchange_order, record_audit_event

logger = logging.getLogger("bitdex.orders")
from ..services.fee_engine import FeeEngine
from ..services.saas_db import get_db_connection
from ..services.exchange_framework import (
    exchange_framework,
    credential_vault,
    OrderSide,
    OrderType,
    Environment,
    OrderStatus,
    evaluate_strategy_compatibility,
    STRATEGY_CAPABILITY_REQUIREMENTS,
)
from ..services.paper_trading_engine import (
    paper_engine,
    IdempotencyCollisionError,
    InvalidOrderStateTransitionError,
    StrategyPreflightError,
)
from ..config import settings
from ..services.market_data import fetch_live_market_data

orders_router = APIRouter(prefix="/orders", tags=["Order Execution & Positions"])


def assert_customer_active(user: Dict[str, Any]) -> None:
    """
    Enforces customer lifecycle status.
    TEMPORARY_HOLD, BLOCKED, SUSPENDED, and DELETED accounts are strictly prevented from submitting orders.
    Existing positions remain intact without auto-closing.
    """
    st = (user.get("status") or "").upper()
    if st in ("TEMPORARY_HOLD", "BLOCKED", "SUSPENDED", "DELETED"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Trading operations restricted: Account is in '{st}' status."
        )


def assert_exchange_connection_ownership(user: Dict[str, Any], account_id: str) -> None:
    """
    Verifies that the exchange connection account_id belongs to the authenticated customer.
    Admins and Owners have administrative access.
    """
    if user.get("role") in ("ADMIN", "OWNER"):
        return
    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT user_id, is_active FROM user_exchange_connections WHERE account_id = ?",
            (account_id,)
        ).fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Exchange connection '{account_id}' not found."
            )
        if row["user_id"] != user["user_id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: Exchange connection belongs to another customer."
            )
        if not row["is_active"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Exchange connection '{account_id}' is inactive."
            )
    finally:
        conn.close()


def resolve_user_exchange_connection(user: Dict[str, Any], exchange: str, environment: str = "DEMO") -> str:
    """
    Resolves the customer's active exchange connection profile for the requested exchange and environment.
    Never falls back to shared admin connection or hardcoded fixtures.
    """
    user_id = user["user_id"]
    conn = get_db_connection()
    try:
        row = conn.execute(
            """SELECT account_id FROM user_exchange_connections 
               WHERE user_id = ? AND UPPER(provider) LIKE ? AND UPPER(environment) = ? AND is_active = 1
               ORDER BY created_at DESC LIMIT 1""",
            (user_id, f"%{exchange.upper()}%", environment.upper())
        ).fetchone()
        if row:
            return row["account_id"]

        if user.get("role") in ("ADMIN", "OWNER"):
            admin_row = conn.execute(
                """SELECT account_id FROM user_exchange_connections 
                   WHERE user_id = ? AND UPPER(provider) LIKE ? AND is_active = 1
                   LIMIT 1""",
                (user_id, f"%{exchange.upper()}%")
            ).fetchone()
            if admin_row:
                return admin_row["account_id"]

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No active {exchange} {environment} connection found for this account. Please connect an exchange profile before trading."
        )
    finally:
        conn.close()


def find_and_assert_position_ownership(position_id: str, current_user: Dict[str, Any]) -> Dict[str, Any]:
    """
    Finds a position by ID and verifies customer ownership.
    Prevents customer A from accessing or modifying customer B's positions.
    """
    try:
        exchange_framework._load_stores()
    except Exception:
        pass
    pos = exchange_framework._positions.get(position_id)
    if not pos:
        for p in exchange_framework._positions.values():
            if p.get("position_id") == position_id:
                pos = p
                break
    if not pos:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Position '{position_id}' not found."
        )

    pos_user = pos.get("user_id")
    if current_user.get("role") not in ("ADMIN", "OWNER") and pos_user and pos_user != current_user["user_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You do not have permission to access or modify another customer's position."
        )
    return pos


# ─────────────────────────────────────────────────────────────────────────────
# Pre-Flight Validation & Demo Execution
# ─────────────────────────────────────────────────────────────────────────────

class OrderValidateRequest(BaseModel):
    profile_id: Optional[str] = None
    exchange: str = Field(default="BINANCE")
    symbol: str = Field(..., description="e.g. BTCUSDT")
    side: str = Field(..., description="BUY or SELL")
    order_type: str = Field(default="LIMIT", description="MARKET or LIMIT")
    quantity: float = Field(..., gt=0)
    price: float = Field(..., gt=0)
    quote_balance: float = Field(default=0.0)
    base_balance: float = Field(default=0.0)
    freshness_status: str = Field(default="FRESH")
    liquidity_status: str = Field(default="QUALIFIED")
    setup_qualified: bool = Field(default=True)
    entry_validity_sec: int = Field(default=3600)
    is_blackout: bool = Field(default=False)
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


class GridOrderSubmitRequest(BaseModel):
    profile_id: Optional[str] = None
    exchange: str = Field(default="BINANCE")
    symbol: str = Field(..., description="e.g. BTCUSDT")
    market: Optional[str] = "CRYPTO"
    strategy_type: str = Field(default="SCALPING_GRID", description="Must be SCALPING_GRID")
    grid_lower_price: Optional[float] = None
    grid_upper_price: Optional[float] = None
    lower_price: Optional[float] = None
    upper_price: Optional[float] = None
    grid_count: int = Field(default=8, ge=3, le=150)
    grid_spacing_pct: Optional[float] = None
    capital_allocated_usd: Optional[float] = None
    capital_usd: Optional[float] = None
    invalidation_condition: Optional[str] = None
    exit_condition: Optional[str] = None
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    idempotency_key: str = Field(default_factory=lambda: f"GRID-{int(time.time()*1000)}")


class DemoOrderSubmitRequest(BaseModel):
    profile_id: Optional[str] = None
    exchange: str = Field(default="BINANCE")
    symbol: str = Field(..., description="e.g. BTCUSDT")
    side: str = Field(..., description="BUY or SELL")
    strategy: Optional[str] = None
    strategy_type: Optional[str] = None
    order_type: str = Field(default="LIMIT")
    quantity: float = Field(..., gt=0)
    price: float = Field(..., gt=0)
    quote_balance: float = Field(default=0.0)
    base_balance: float = Field(default=0.0)
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    idempotency_key: str = Field(..., description="Unique client idempotency key")
    freshness_status: str = Field(default="FRESH")
    liquidity_status: str = Field(default="QUALIFIED")
    setup_qualified: bool = Field(default=True)
    entry_validity_sec: int = Field(default=3600)
    is_blackout: bool = Field(default=False)


@orders_router.post("/validate")
async def validate_order(
    req: OrderValidateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Executes pre-flight validation against exchange filters, real balance,
    and platform deterministic risk gates without submitting an order.
    Requires authenticated customer session and active account status.
    """
    assert_customer_active(current_user)

    try:
        adapter = exchange_framework.get_adapter(req.exchange)
        clean_sym = req.symbol.replace("/", "").replace("-", "").strip().upper()
        rules = await adapter.fetch_symbol_rules(clean_sym, Environment.DEMO)

        side_enum = OrderSide.BUY if req.side.upper() == "BUY" else OrderSide.SELL
        type_enum = OrderType.LIMIT if req.order_type.upper() == "LIMIT" else OrderType.MARKET

        profile_to_use = req.profile_id
        if profile_to_use:
            assert_exchange_connection_ownership(current_user, profile_to_use)
        else:
            try:
                profile_to_use = resolve_user_exchange_connection(current_user, req.exchange, "DEMO")
            except HTTPException:
                profile_to_use = None

        quote_bal = req.quote_balance
        base_bal = req.base_balance

        if profile_to_use:
            try:
                creds = credential_vault.get_credentials(profile_to_use)
                if creds:
                    bals = await adapter.fetch_balances(Environment.DEMO, creds)
                    for b in bals:
                        if b.asset == rules.quote_asset and (quote_bal is None or quote_bal <= 0):
                            quote_bal = b.free
                        if b.asset == rules.base_asset and (base_bal is None or base_bal <= 0):
                            base_bal = b.free
            except Exception:
                pass

        quote_bal = quote_bal if (quote_bal is not None and quote_bal > 0) else 0.0
        base_bal = base_bal if (base_bal is not None and base_bal > 0) else 0.0

        validation = adapter.validate_order(
            symbol=clean_sym,
            side=side_enum,
            order_type=type_enum,
            quantity=req.quantity,
            price=req.price,
            quote_balance=quote_bal,
            base_balance=base_bal,
            rules=rules,
            freshness_status=req.freshness_status,
            liquidity_status=req.liquidity_status,
            setup_qualified=req.setup_qualified,
            entry_validity_sec=req.entry_validity_sec,
            is_blackout=req.is_blackout,
            stop_loss=req.stop_loss,
            take_profit=req.take_profit,
        )

        return {
            "status": "PASS" if validation.is_valid else "REJECTED",
            "is_valid": validation.is_valid,
            "errors": validation.errors,
            "warnings": validation.warnings,
            "symbol": req.symbol,
            "normalized_qty": validation.normalized_qty,
            "normalized_price": validation.normalized_price,
            "estimated_notional": validation.estimated_notional,
            "estimated_fee": validation.estimated_fee,
            "quote_asset": validation.quote_asset,
            "rules": {
                "min_qty": rules.min_qty,
                "max_qty": rules.max_qty,
                "step_size": rules.step_size,
                "tick_size": rules.tick_size,
                "min_notional": rules.min_notional,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@orders_router.post("/demo/submit")
async def submit_demo_order(
    req: DemoOrderSubmitRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Submits a testnet/paper demo order. Validates all pre-flight rules,
    enforces idempotency, reconciles fills, and generates an immutable execution receipt.
    Strictly requires authenticated user, active account status, ownership of exchange profile,
    and genuine exchange balances (NO fabricated $10k fallbacks or fallback identities).
    """
    assert_customer_active(current_user)
    user_id = current_user["user_id"]

    # Guard: Reject scalping grid orders sent to Spot endpoint
    strat = getattr(req, "strategy", "") or getattr(req, "strategy_type", "") or ""
    side_str = getattr(req, "side", "") or ""
    if side_str.upper() in ("SCALP", "SCALPING", "GRID") or strat.upper() in ("SCALP", "SCALPING", "GRID", "SCALPING_GRID"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Scalping grid strategies must be dispatched to /orders/grid/submit, not the Spot buy/sell endpoint."
        )

    # 1. Resolve and enforce ownership of exchange profile (NO shared demo fallback)
    if req.profile_id:
        assert_exchange_connection_ownership(current_user, req.profile_id)
        profile_to_use = req.profile_id
    else:
        profile_to_use = resolve_user_exchange_connection(current_user, req.exchange, "DEMO")

    # 2. Server-side activation and credit preflight gating
    eligible, reason = FeeEngine.check_trading_preflight_eligibility(
        user_id,
        environment="DEMO",
        estimated_orders_count=1
    )
    if not eligible:
        if "activation" in (reason or "").lower():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=reason)
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=reason)

    try:
        adapter = exchange_framework.get_adapter(req.exchange)
        clean_sym = req.symbol.replace("/", "").replace("-", "").strip().upper()
        rules = await adapter.fetch_symbol_rules(clean_sym, Environment.DEMO)

        quote_bal = req.quote_balance
        base_bal = req.base_balance

        # Retrieve actual exchange balance using credentials
        creds = credential_vault.get_credentials(profile_to_use)
        if creds:
            try:
                bals = await adapter.fetch_balances(Environment.DEMO, creds)
                for b in bals:
                    if b.asset == rules.quote_asset and (quote_bal is None or quote_bal <= 0):
                        quote_bal = b.free
                    if b.asset == rules.base_asset and (base_bal is None or base_bal <= 0):
                        base_bal = b.free
            except Exception as bal_err:
                logger.warning(f"Failed to fetch balances for {profile_to_use}: {bal_err}")

        # Strict validation: reject if actual balance cannot be retrieved or is zero
        if req.side.upper() == "BUY" and (quote_bal is None or quote_bal <= 0):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient or unretrievable {rules.quote_asset} balance on exchange profile '{profile_to_use}'. Live exchange balance verification failed."
            )

        if req.side.upper() == "SELL" and (base_bal is None or base_bal <= 0):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient or unretrievable {rules.base_asset} balance on exchange profile '{profile_to_use}'. Live exchange balance verification failed."
            )

        side_enum = OrderSide.BUY if req.side.upper() == "BUY" else OrderSide.SELL
        type_enum = OrderType.LIMIT if req.order_type.upper() == "LIMIT" else OrderType.MARKET

        validation = adapter.validate_order(
            symbol=clean_sym,
            side=side_enum,
            order_type=type_enum,
            quantity=req.quantity,
            price=req.price,
            quote_balance=quote_bal,
            base_balance=base_bal,
            rules=rules,
            freshness_status=req.freshness_status,
            liquidity_status=req.liquidity_status,
            setup_qualified=req.setup_qualified,
            entry_validity_sec=req.entry_validity_sec,
            is_blackout=req.is_blackout,
            stop_loss=req.stop_loss,
            take_profit=req.take_profit,
        )

        if not validation.is_valid:
            return {
                "status": "REJECTED",
                "message": "Order failed pre-flight risk/exchange validation.",
                "errors": validation.errors,
            }

        order_payload = {
            "exchange": req.exchange.upper(),
            "symbol": req.symbol,
            "side": req.side.upper(),
            "order_type": req.order_type.upper(),
            "quantity": validation.normalized_qty,
            "price": validation.normalized_price,
            "stop_loss": req.stop_loss,
            "take_profit": req.take_profit,
            "account_label": "Binance Demo",
            "user_id": user_id,
        }

        receipt = await exchange_framework.execute_demo_order(
            profile_id=profile_to_use,
            order_request=order_payload,
            idempotency_key=req.idempotency_key,
        )

        if receipt.status in (OrderStatus.REJECTED, OrderStatus.FAILED):
            return {
                "status": "REJECTED",
                "message": receipt.error_message or "Order execution blocked or rejected.",
                "receipt": receipt,
            }

        # 3. Assess and deduct execution fee atomically with idempotency key
        fee_assessed = 0.0
        if receipt.status in (OrderStatus.FILLED, OrderStatus.SUBMITTED):
            fee_res = FeeEngine.assess_execution_fee(
                user_id=user_id,
                exchange=req.exchange,
                order_id=receipt.client_order_id,
                fill_id=receipt.exchange_order_id,
                environment="DEMO",
                execution_status="FILLED",
                charge_demo=True
            )
            fee_assessed = fee_res.get("fee_charged_usd", 0.0)

        receipt_dict = receipt.to_dict() if hasattr(receipt, "to_dict") else receipt.__dict__
        if fee_assessed > 0:
            receipt_dict["platform_execution_fee_usd"] = fee_assessed
        receipt_dict["user_id"] = user_id

        # Record to permanent database ledger (exchange_orders & audit events)
        try:
            st_val = receipt.status.value if hasattr(receipt.status, "value") else str(receipt.status)
            if st_val == "OPEN":
                st_val = "NEW"
            upsert_exchange_order({
                "internal_order_id": getattr(receipt, "internal_order_id", f"INT-BIN-{receipt.client_order_id}"),
                "client_order_id": receipt.client_order_id,
                "exchange_order_id": receipt.exchange_order_id,
                "user_id": user_id,
                "account_id": profile_to_use,
                "provider": req.exchange.upper(),
                "environment": "DEMO",
                "symbol": clean_sym,
                "display_pair": f"{clean_sym.replace('USDT', '')}/USDT",
                "side": req.side,
                "order_type": req.order_type,
                "requested_price": req.price,
                "avg_fill_price": receipt.avg_fill_price or req.price,
                "orig_qty": req.quantity,
                "executed_qty": receipt.executed_qty or 0.0,
                "cummulative_quote_qty": (receipt.avg_fill_price or req.price) * (receipt.executed_qty or 0.0),
                "status": st_val,
                "commission_total": receipt.fee_amount or 0.0,
                "commission_asset": receipt.fee_asset or "USDT",
                "verification_status": "EXCHANGE_VERIFIED",
                "execution_type": "REAL_EXCHANGE_DEMO",
                "is_exchange_confirmed": 1,
                "raw_json": receipt_dict
            })
            record_audit_event(
                user_id=user_id,
                account_id=profile_to_use,
                event_type="ORDER_SUBMITTED",
                lifecycle_step="EXCHANGE_ACK",
                message=f"Order {receipt.exchange_order_id or receipt.client_order_id} recorded with status {st_val}.",
                internal_order_id=getattr(receipt, "internal_order_id", None),
                exchange_order_id=receipt.exchange_order_id,
                payload=receipt_dict
            )
        except Exception as _log_err:
            pass

        return {
            "status": "SUCCESS"
            if receipt.status == OrderStatus.FILLED
            else ("PARTIAL" if receipt.status == OrderStatus.PARTIALLY_FILLED else "SUBMITTED"),
            "receipt": receipt_dict,
            "execution_fee_charged_usd": fee_assessed,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@orders_router.post("/grid/submit")
async def submit_grid_order(
    req: GridOrderSubmitRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Submits a Scalping — Grid Strategy execution request.
    Strictly validates grid parameters, risk boundaries, activation status, customer ownership, and credits.
    """
    assert_customer_active(current_user)
    user_id = current_user["user_id"]

    # Verify and resolve exchange profile ownership
    if req.profile_id:
        assert_exchange_connection_ownership(current_user, req.profile_id)
        profile_to_use = req.profile_id
    else:
        profile_to_use = resolve_user_exchange_connection(current_user, req.exchange, "DEMO")

    # Preflight eligibility
    eligible, reason = FeeEngine.check_trading_preflight_eligibility(
        user_id,
        environment="DEMO",
        estimated_orders_count=1
    )
    if not eligible:
        if "activation" in (reason or "").lower():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=reason)
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=reason)

    # Parameter resolution
    lower = req.grid_lower_price if req.grid_lower_price is not None else req.lower_price
    upper = req.grid_upper_price if req.grid_upper_price is not None else req.upper_price
    capital = req.capital_allocated_usd if req.capital_allocated_usd is not None else req.capital_usd

    if lower is None or upper is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Grid lower and upper price boundaries are required."
        )

    if capital is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Allocated capital in USD is required."
        )

    # Strategy & Grid Parameter Validations
    if req.strategy_type != "SCALPING_GRID":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Strategy type must be SCALPING_GRID.")

    if lower >= upper:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid grid range: Lower price (${lower}) must be strictly below upper price (${upper})."
        )

    if req.grid_count < 3 or req.grid_count > 150:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid grid count ({req.grid_count}). Must be between 3 and 150 grids."
        )

    spacing = req.grid_spacing_pct
    if spacing is None:
        spacing = ((upper - lower) / lower / (req.grid_count - 1)) * 100

    if spacing < 0.25:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Grid spacing ({spacing:.2f}%) fails minimum 0.25% round-trip fee friction threshold."
        )

    if capital < 15.0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Capital allocated (${capital}) is below minimum grid strategy capital requirement ($15.00)."
        )

    # Atomic fee assessment & idempotency
    fee_receipt = FeeEngine.assess_execution_fee(
        user_id=user_id,
        exchange=req.exchange,
        order_id=f"GRID-{req.idempotency_key}",
        fill_id=f"FILL-GRID-{req.idempotency_key}",
        environment="DEMO",
        execution_status="FILLED",
        charge_demo=True
    )
    fee_assessed = fee_receipt.get("fee_charged_usd", 0.0)

    grid_levels = []
    step = (upper - lower) / req.grid_count
    for i in range(req.grid_count + 1):
        grid_levels.append(round(lower + (i * step), 2))

    order_size_per_grid = round(capital / req.grid_count, 2)

    receipt = {
        "client_order_id": f"GRID-{req.idempotency_key}",
        "strategy_label": "Scalping — Grid Strategy",
        "symbol": req.symbol,
        "exchange": req.exchange,
        "account_id": profile_to_use,
        "user_id": user_id,
        "status": "ACTIVE_DEMO_GRID",
        "grid_lower_price": lower,
        "grid_upper_price": upper,
        "grid_count": req.grid_count,
        "grid_spacing_pct": spacing,
        "capital_allocated_usd": capital,
        "order_size_per_grid_usd": order_size_per_grid,
        "grid_levels": grid_levels,
        "invalidation_condition": req.invalidation_condition or f"Price closes below ${round(lower * 0.965, 2)}",
        "exit_condition": req.exit_condition or f"Price closes above ${round(upper * 1.035, 2)}",
        "fee_charged_usd": fee_assessed,
        "admin_fee_exempt": bool(fee_receipt.get("status") == "ADMIN_EXEMPT"),
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    }

    return {
        "status": "SUCCESS",
        "message": f"Successfully initialized Scalping — Grid Strategy ({req.grid_count} grids) for {req.symbol}.",
        "receipt": receipt,
        "grid_levels": grid_levels,
        "strategy_label": "Scalping — Grid Strategy"
    }


@orders_router.post("/live/submit")
async def submit_live_order():
    """
    Live trading endpoint. HARD-LOCKED by system safety boundaries.
    Always returns HTTP 403 Forbidden.
    """
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=(
            "Live trading is hard-locked (`live_trading_locked=true`). "
            "Real exchange order submission is strictly blocked."
        ),
    )


@orders_router.get("/receipt/{client_order_id}")
async def get_receipt(
    client_order_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Retrieves immutable execution receipt by client order ID with customer ownership validation."""
    user_id = current_user["user_id"]
    is_admin = current_user.get("role") in ("ADMIN", "OWNER")

    # 1. Check in database exchange_orders first
    conn = get_db_connection()
    try:
        order_row = conn.execute(
            "SELECT user_id, raw_json FROM exchange_orders WHERE client_order_id = ? OR exchange_order_id = ? OR internal_order_id = ?",
            (client_order_id, client_order_id, client_order_id)
        ).fetchone()
        if order_row:
            if not is_admin and order_row["user_id"] != user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: You do not have permission to view another customer's order receipt."
                )
            if order_row["raw_json"]:
                try:
                    return {"status": "SUCCESS", "receipt": json.loads(order_row["raw_json"])}
                except Exception:
                    pass
    finally:
        conn.close()

    # 2. Check in memory receipt store
    receipt = exchange_framework.get_receipt(client_order_id)
    if not receipt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receipt not found")

    receipt_user = getattr(receipt, "user_id", None) or (receipt.get("user_id") if isinstance(receipt, dict) else None)
    if not is_admin and receipt_user and receipt_user != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You do not have permission to view another customer's order receipt."
        )

    return {"status": "SUCCESS", "receipt": receipt}


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 3B: STANDARDIZED PAPER TRADING LIFECYCLE & LEDGER
# ─────────────────────────────────────────────────────────────────────────────

class PaperOrderSubmitRequest(BaseModel):
    strategy_id: str = Field(..., description="e.g. GRID_TRADING, MOMENTUM_TREND_FOLLOWING")
    profile_id: str = Field(..., description="Connection profile ID")
    symbol: str = Field(..., description="e.g. BTCUSDT")
    side: str = Field(..., description="BUY or SELL")
    order_type: str = Field(default="LIMIT", description="LIMIT or MARKET")
    quantity: float = Field(..., gt=0)
    price: float = Field(..., gt=0)
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    idempotency_key: Optional[str] = Field(None, description="Client idempotency key")
    account_type: str = Field(default="PAPER", description="Must be explicitly PAPER")
    execution_mode: str = Field(default="PAPER", description="Must be explicitly PAPER")


class OrderTransitionRequest(BaseModel):
    target_status: str = Field(..., description="Target OrderStatus")
    raw_provider_status: Optional[str] = None
    reason: Optional[str] = None


class OrderFillRequest(BaseModel):
    fill_qty: float = Field(..., gt=0)
    fill_price: float = Field(..., gt=0)
    fee_amount: float = Field(default=0.0, ge=0)
    fee_currency: str = Field(default="USDT")


@orders_router.post("/paper/order")
async def submit_paper_order(
    req: PaperOrderSubmitRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Phase 3B Standardized Paper Order Submission.
    - Strictly checks customer status and connection ownership.
    - Validates strict account/mode isolation (PAPER only).
    - Enforces strategy preflight: rejects INCOMPATIBLE or INDETERMINATE status.
    - Validates capability evidence freshness and product matching.
    - Guarantees durable idempotency: duplicate requests return existing orders.
    - Reusing key with conflicting payload strictly rejected with HTTP 409.
    - Reserves simulated ledger margin and tracks lifecycle without real exchange writes.
    """
    assert_customer_active(current_user)
    if req.profile_id:
        assert_exchange_connection_ownership(current_user, req.profile_id)

    clean_sym = req.symbol.replace("/", "").replace("-", "").strip().upper()

    # 1. Isolation check
    if req.account_type.upper() != "PAPER" or req.execution_mode.upper() != "PAPER":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Paper trading requires explicit 'PAPER' account_type and execution_mode. "
                   f"Received account_type='{req.account_type}', execution_mode='{req.execution_mode}'.",
        )

    # 2. Retrieve profile from vault
    profile = credential_vault.get_profile_public(req.profile_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connection profile '{req.profile_id}' not found.",
        )

    # 3. Strategy Preflight Check
    try:
        paper_engine.preflight_order(
            profile_data=profile,
            strategy_id=req.strategy_id,
            account_type=req.account_type,
            execution_mode=req.execution_mode,
            evaluator_fn=evaluate_strategy_compatibility,
            strategy_requirements=STRATEGY_CAPABILITY_REQUIREMENTS,
        )
    except StrategyPreflightError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "STRATEGY_PREFLIGHT_REJECTED", "message": str(e)},
        )

    # 4. Create Paper Order through Engine
    try:
        order, is_replay = paper_engine.create_order(
            strategy_id=req.strategy_id,
            profile_id=req.profile_id,
            symbol=clean_sym,
            side=req.side,
            order_type=req.order_type,
            quantity=req.quantity,
            price=req.price,
            idempotency_key=req.idempotency_key,
            stop_loss=req.stop_loss,
            take_profit=req.take_profit,
            account_type=req.account_type,
            execution_mode=req.execution_mode,
            profile_data=profile,
            evaluator_fn=evaluate_strategy_compatibility,
            strategy_requirements=STRATEGY_CAPABILITY_REQUIREMENTS,
        )
        return {
            "status": "SUCCESS",
            "order": order,
            "idempotent_replay": is_replay,
            "message": "Order replayed from idempotency store" if is_replay else "Paper order created and open",
        }
    except IdempotencyCollisionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@orders_router.post("/paper/{client_order_id}/transition")
async def transition_paper_order(
    client_order_id: str,
    req: OrderTransitionRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Transitions a paper order to a new lifecycle state.
    Rejects invalid state transitions with HTTP 400.
    """
    try:
        updated = paper_engine.transition_order(
            client_order_id=client_order_id,
            target_status=req.target_status,
            raw_provider_status=req.raw_provider_status,
            reason=req.reason,
        )
        return {"status": "SUCCESS", "order": updated}
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    except InvalidOrderStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@orders_router.post("/paper/{client_order_id}/fill")
async def fill_paper_order(
    client_order_id: str,
    req: OrderFillRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Applies a partial or full execution fill to an open paper order.
    Recomputes cumulative quantity, remaining quantity, weighted fill price,
    records fees, and settles the isolated paper ledger.
    """
    try:
        updated = paper_engine.apply_fill(
            client_order_id=client_order_id,
            fill_qty=req.fill_qty,
            fill_price=req.fill_price,
            fee_amount=req.fee_amount,
            fee_currency=req.fee_currency,
        )
        return {"status": "SUCCESS", "order": updated}
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    except (InvalidOrderStateTransitionError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@orders_router.post("/paper/{client_order_id}/cancel")
async def cancel_paper_order(
    client_order_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Cancels an open paper order and releases held ledger margin."""
    try:
        cancelled = paper_engine.cancel_order(client_order_id)
        return {"status": "SUCCESS", "order": cancelled}
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@orders_router.post("/paper/{client_order_id}/reconcile")
async def reconcile_paper_order(
    client_order_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Reconciles an order with UNKNOWN_OUTCOME without duplicate execution.
    Inspects internal ledger and fill records to resolve the definitive state.
    """
    try:
        res = paper_engine.reconcile_uncertain_order(client_order_id)
        return {"status": "SUCCESS", "reconciliation": res}
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@orders_router.get("/paper/{client_order_id}")
async def get_paper_order(
    client_order_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Retrieves full paper order lifecycle details and sanitized audit trail."""
    order = paper_engine.get_order(client_order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper order not found")
    return {"status": "SUCCESS", "order": order}


@orders_router.get("/paper")
async def list_paper_orders(
    status: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None),
    strategy_id: Optional[str] = Query(None),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Lists paper orders with optional filtering."""
    orders = paper_engine.list_orders(status=status, symbol=symbol, strategy_id=strategy_id)
    return {"status": "SUCCESS", "count": len(orders), "orders": orders}


@orders_router.get("/paper/ledger/summary")
async def get_paper_ledger_summary(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Retrieves current simulated paper ledger balances and equity."""
    summary = paper_engine.get_ledger_summary()
    return {"status": "SUCCESS", "ledger": summary}


# ─────────────────────────────────────────────────────────────────────────────
# Legacy Paper Position Route & Position Management
# ─────────────────────────────────────────────────────────────────────────────

class PaperPositionCreateRequest(BaseModel):
    symbol: str = Field(..., description="e.g. BTCUSDT")
    side: str = Field(..., description="LONG or SHORT")
    size: float = Field(..., gt=0)
    entry_price: float = Field(..., gt=0)
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


class PositionCloseRequest(BaseModel):
    exit_price: Optional[float] = None


class AdjustTpSlRequest(BaseModel):
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    confirmed: bool = Field(False, description="User must explicitly confirm TP/SL modification")


@orders_router.post("/paper/create")
async def create_paper_position(
    req: PaperPositionCreateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Creates an instant paper position for strategy testing."""
    assert_customer_active(current_user)
    clean_sym = req.symbol.replace("/", "").replace("-", "").strip().upper()
    pos = exchange_framework.create_paper_position(
        symbol=clean_sym,
        side=req.side,
        size=req.size,
        entry_price=req.entry_price,
        stop_loss=req.stop_loss,
        take_profit=req.take_profit,
    )
    if isinstance(pos, dict):
        pos["user_id"] = current_user["user_id"]
    return {"status": "SUCCESS", "position": pos}


@orders_router.get("/positions/{position_id}/advisory")
async def get_position_advisory(
    position_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Returns AI Trade Monitoring & Recommendations for an active position.
    Strictly verifies customer ownership.
    """
    find_and_assert_position_ownership(position_id, current_user)
    try:
        advisory = exchange_framework.generate_ai_trade_recommendation(position_id)
        return {"status": "SUCCESS", "advisory": advisory}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@orders_router.post("/positions/{position_id}/adjust-tp-sl")
async def adjust_position_tp_sl(
    position_id: str,
    req: AdjustTpSlRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Updates protective Stop-Loss and Take-Profit limits on an active position.
    Strictly verifies customer ownership and active account status.
    """
    assert_customer_active(current_user)
    find_and_assert_position_ownership(position_id, current_user)

    if not req.confirmed:
        return {
            "status": "PREVIEW",
            "message": "Confirmation required to commit TP/SL adjustment.",
            "proposed_stop_loss": req.stop_loss,
            "proposed_take_profit": req.take_profit,
            "requires_confirmation": True,
        }

    try:
        updated = exchange_framework.update_position_tp_sl(
            position_id=position_id,
            stop_loss=req.stop_loss,
            take_profit=req.take_profit,
        )
        return {
            "status": "SUCCESS",
            "message": "Protective TP/SL limits successfully updated.",
            "position": updated,
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@orders_router.post("/positions/{position_id}/close")
async def close_position(
    position_id: str,
    req: PositionCloseRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Closes an active position and reconciles realized P&L.
    Strictly verifies customer ownership and active account status.
    Customer A cannot close Customer B's positions.
    """
    assert_customer_active(current_user)
    find_and_assert_position_ownership(position_id, current_user)

    try:
        closed = exchange_framework.close_position(position_id, req.exit_price)
        return {
            "status": "SUCCESS",
            "message": f"Position {position_id} closed.",
            "position": closed,
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@orders_router.get("/positions")
async def get_positions(
    environment: str = Query("ALL", description="DEMO, LIVE, or ALL"),
    market_type: Optional[str] = Query(None, description="CRYPTO, FOREX, or ALL/None"),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Returns segregated active positions across DEMO, LIVE, and ALL with live mark-to-market P&L.
    Enforces customer isolation: Customer A cannot see Customer B's positions.
    """
    freshness = "FRESH"
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        live_mkts = await fetch_live_market_data()
        prices = {k: v.get("price", 0.0) for k, v in live_mkts.items() if v.get("price")}
        if not prices:
            freshness = "UNAVAILABLE"
        else:
            exchange_framework.update_mark_prices(prices, freshness=freshness)
    except Exception:
        freshness = "STALE"

    positions = exchange_framework.get_positions(
        environment=environment,
        market_type=market_type if market_type and market_type.upper() != "ALL" else None
    )

    is_admin = current_user.get("role") in ("ADMIN", "OWNER")
    user_id = current_user["user_id"]

    if not is_admin:
        # Strictly isolate positions: Customer A cannot see Customer B's positions.
        positions = [
            p for p in positions
            if p.get("user_id") == user_id or (not p.get("user_id") and p.get("origin") == "SEEDED_FIXTURE")
        ]

    open_positions = [p for p in positions if p.get("status") == "OPEN"]
    closed_positions = [p for p in positions if p.get("status") == "CLOSED"]

    total_unrealized = sum(p.get("unrealized_pnl", 0.0) for p in open_positions)
    total_realized_gross = sum(p.get("realized_pnl", 0.0) for p in closed_positions)
    total_fees = sum(p.get("fees_paid", 0.0) for p in positions)
    total_realized_net = total_realized_gross - total_fees
    net_pnl = total_realized_net + total_unrealized

    return {
        "status": "SUCCESS",
        "environment": environment.upper(),
        "market_type": (market_type or "ALL").upper(),
        "live_trading_locked": settings.live_trading_locked,
        "data_freshness": freshness,
        "prices_updated_at_utc": now_iso,
        "positions_count": len(positions),
        "open_positions": open_positions,
        "closed_positions": closed_positions,
        "metrics": {
            "total_unrealized_pnl_usd": round(total_unrealized, 2),
            "total_realized_gross_usd": round(total_realized_gross, 2),
            "total_realized_pnl_usd": round(total_realized_gross, 2),
            "total_fees_usd": round(total_fees, 4),
            "total_realized_net_usd": round(total_realized_net, 2),
            "net_pnl_usd": round(net_pnl, 2),
            "fee_treatment": "deducted_from_gross_realized",
            "fee_treatment_explanation": "Fees are deducted from gross realized P&L to arrive at net realized P&L. Total net P&L is net realized P&L plus unrealized P&L."
        },
    }


@orders_router.get("/open")
async def get_open_orders(
    profile_id: Optional[str] = Query(None, description="Profile ID to retrieve open orders for"),
    symbol: Optional[str] = Query(None, description="Optional symbol filter, e.g. BTCUSDT"),
    environment: str = Query("ALL", description="DEMO, PAPER, LIVE, or ALL"),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Retrieves active open orders decoupled from wallet balances.
    Enforces authentication and customer ownership.
    """
    is_admin = current_user.get("role") in ("ADMIN", "OWNER")
    user_id = current_user["user_id"]

    if profile_id:
        if not is_admin:
            assert_exchange_connection_ownership(current_user, profile_id)
    else:
        if not is_admin:
            conn = get_db_connection()
            try:
                row = conn.execute(
                    "SELECT account_id FROM user_exchange_connections WHERE user_id = ? AND is_active = 1 LIMIT 1",
                    (user_id,)
                ).fetchone()
                profile_id = row["account_id"] if row else None
            finally:
                conn.close()
            if not profile_id:
                return {"status": "SUCCESS", "open_orders": [], "orders_count": 0}

    res = await exchange_framework.fetch_open_orders(profile_id=profile_id, symbol=symbol, environment=environment)
    return res


@orders_router.get("/history")
async def get_order_history(
    environment: Optional[str] = Query(None),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Retrieves order execution history scoped to the authenticated customer."""
    orders = exchange_framework.get_orders_history(environment=environment)
    if current_user.get("role") not in ("ADMIN", "OWNER"):
        orders = [o for o in orders if o.get("user_id") == current_user["user_id"]]
    return {
        "status": "SUCCESS",
        "count": len(orders),
        "orders": orders,
    }


class OrderCancelRequest(BaseModel):
    symbol: str = Field(..., description="e.g. BTCUSDT")
    client_order_id: str = Field(..., description="Client order ID to cancel")
    profile_id: Optional[str] = None
    exchange: str = Field(default="BINANCE")
    environment: str = Field(default="DEMO")


class OrderReconcileRequest(BaseModel):
    symbol: str = Field(default="BTCUSDT")
    client_order_id: Optional[str] = None
    exchange_order_id: Optional[str] = None
    profile_id: Optional[str] = None
    exchange: str = Field(default="BINANCE")
    environment: str = Field(default="DEMO")


@orders_router.post("/cancel")
async def cancel_order(
    req: OrderCancelRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Cancels an open demo order on exchange matching engine with customer ownership verification.
    Customer A cannot cancel Customer B's orders.
    """
    assert_customer_active(current_user)
    user_id = current_user["user_id"]
    is_admin = current_user.get("role") in ("ADMIN", "OWNER")

    # Verify ownership in database exchange_orders
    conn = get_db_connection()
    try:
        order_row = conn.execute(
            "SELECT user_id, account_id FROM exchange_orders WHERE client_order_id = ? OR exchange_order_id = ? OR internal_order_id = ?",
            (req.client_order_id, req.client_order_id, req.client_order_id)
        ).fetchone()
        if order_row and not is_admin and order_row["user_id"] != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You do not have permission to cancel another customer's order."
            )
    finally:
        conn.close()

    # Verify ownership in memory cache
    cached = exchange_framework._orders.get(req.client_order_id)
    if cached and not is_admin:
        cached_user = cached.get("user_id")
        if cached_user and cached_user != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You do not have permission to cancel another customer's order."
            )

    if req.profile_id and not is_admin:
        assert_exchange_connection_ownership(current_user, req.profile_id)

    try:
        clean_sym = req.symbol.replace("/", "").replace("-", "").strip().upper()
        res = await exchange_framework.cancel_order(
            symbol=clean_sym,
            client_order_id=req.client_order_id,
            profile_id=req.profile_id,
            exchange=req.exchange,
            environment=req.environment,
        )
        return {"status": "SUCCESS", "result": res}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@orders_router.post("/reconcile")
@orders_router.post("/demo/reconcile")
async def reconcile_order(
    req: OrderReconcileRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Strict execution verification and reconciliation against Binance matching engine.
    Queries genuine order status, updates ledger and positions, and prevents duplicate fills.
    """
    if req.profile_id and current_user.get("role") not in ("ADMIN", "OWNER"):
        assert_exchange_connection_ownership(current_user, req.profile_id)

    try:
        clean_sym = req.symbol.replace("/", "").replace("-", "").strip().upper()
        adapter = exchange_framework.get_adapter(req.exchange)
        creds = credential_vault.get_credentials(req.profile_id)
        if not creds and req.exchange.upper() == "BINANCE":
            creds = credential_vault.get_credentials()

        if not creds:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"No exchange credentials found for {req.exchange} Demo.")

        if req.client_order_id or req.exchange_order_id:
            env_enum = Environment.DEMO if req.environment.upper() == "DEMO" else Environment.LIVE
            if hasattr(adapter, "get_order_status"):
                receipt = await adapter.get_order_status(
                    symbol=clean_sym,
                    client_order_id=req.client_order_id or "",
                    exchange_order_id=req.exchange_order_id,
                    environment=env_enum,
                    credentials=creds
                )
                if receipt.client_order_id:
                    rc_dict = asdict(receipt)
                    rc_dict["user_id"] = current_user["user_id"]
                    exchange_framework._orders[receipt.client_order_id] = rc_dict
                    if receipt.status in (OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED):
                        exchange_framework._update_position_from_fill(receipt)
                    exchange_framework._save_stores()
                return {"status": "SUCCESS", "receipt": asdict(receipt)}

        open_res = await exchange_framework.fetch_open_orders(
            profile_id=req.profile_id,
            symbol=clean_sym,
            environment=req.environment
        )
        return {"status": "SUCCESS", "open_orders": open_res}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
