"""
Bitdex Institutional Order History, Trade Ledger & Spot Holdings Router
Endpoints for 4-Zone Workspace:
- Open Orders (Working orders on book)
- Order History (Permanent instruction ledger with nested fills)
- Trade History (Granular execution fills ledger with net double-entry impact)
- Spot Asset Holdings (Live exchange wallet inventory)
- Slide-Over Execution Audit Dossier
- Exchange Synchronization Engine
- Server-Side CSV Streaming Exports
"""

import io
import csv
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..services.auth_manager import AuthManager, get_current_user
from ..services.ledger_db import (
    get_db_connection,
    query_open_orders,
    query_order_history,
    query_trade_history,
    query_spot_holdings,
    get_order_audit_dossier,
    sync_binance_account,
    init_ledger_tables,
)

ledger_router = APIRouter(prefix="/ledger", tags=["Institutional Order & Trade Ledger"])


def require_authenticated_user(request: Request) -> Dict[str, Any]:
    """
    Enforces strict Bearer authentication for sensitive ledger routes.
    Never falls back to an admin identity or mock customer.
    Raises HTTP 401 if token is missing, invalid, or expired.
    """
    user = get_current_user(request)
    if not user or not user.get("user_id"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide a valid Bearer token."
        )
    return user


def assert_account_ownership(user: Dict[str, Any], account_id: Optional[str]) -> None:
    """
    Validates that the authenticated customer owns the requested exchange account/profile.
    Admins and Owners have system-wide visibility.
    """
    if not account_id or account_id.upper() in ("ALL", ""):
        return
    if user.get("role") in ("ADMIN", "OWNER"):
        return
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT user_id FROM user_exchange_connections WHERE account_id = ?",
            (account_id,)
        ).fetchone()
        if not row or row["user_id"] != user["user_id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Exchange connection '{account_id}' does not belong to your account."
            )


class SyncExchangeRequest(BaseModel):
    account_id: str = Field(..., description="Exchange Profile ID (Required)")
    environment: Optional[str] = Field(default="DEMO", description="DEMO or LIVE")
    tracked_symbols: Optional[List[str]] = Field(default=None, description="Additional symbols to synchronize")


@ledger_router.get("/orders/open")
async def get_open_orders(
    request: Request,
    account_id: Optional[str] = Query(None, description="Profile ID filter"),
    environment: Optional[str] = Query("ALL", description="DEMO, LIVE, or ALL"),
    symbol: Optional[str] = Query(None, description="Symbol filter, e.g. BTCUSDT or BCH/USDT")
):
    """
    Returns working orders resting on the exchange orderbook (status NEW or PARTIALLY_FILLED).
    Strictly scoped to authenticated customer or admin.
    """
    user = require_authenticated_user(request)
    assert_account_ownership(user, account_id)
    target_user_id = user["user_id"] if user.get("role") not in ("ADMIN", "OWNER") else None

    orders = query_open_orders(
        user_id=target_user_id,
        account_id=account_id if account_id and account_id != "ALL" else None,
        environment=environment,
        symbol=symbol
    )
    return {
        "status": "SUCCESS",
        "count": len(orders),
        "orders": orders
    }


@ledger_router.get("/orders/history")
async def get_order_history(
    request: Request,
    environment: Optional[str] = Query("ALL"),
    exchange: Optional[str] = Query("ALL"),
    account_id: Optional[str] = Query("ALL"),
    symbol: Optional[str] = Query("ALL"),
    side: Optional[str] = Query("ALL"),
    status: Optional[str] = Query("ALL"),
    search: Optional[str] = Query(None),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200)
):
    """
    Returns permanent completed and working order instruction history.
    Includes nested individual fill details for expandable table rows.
    Strictly isolated by customer identity.
    """
    user = require_authenticated_user(request)
    assert_account_ownership(user, account_id)
    target_user_id = user["user_id"] if user.get("role") not in ("ADMIN", "OWNER") else None

    offset = (page - 1) * page_size
    orders, total = query_order_history(
        user_id=target_user_id,
        environment=environment,
        exchange=exchange,
        account_id=account_id,
        symbol=symbol,
        side=side,
        status_filter=status,
        search=search,
        start_time_utc=start_time,
        end_time_utc=end_time,
        limit=page_size,
        offset=offset
    )
    return {
        "status": "SUCCESS",
        "total": total,
        "page": page,
        "page_size": page_size,
        "orders": orders
    }


@ledger_router.get("/trades/fills")
async def get_trade_fills(
    request: Request,
    environment: Optional[str] = Query("ALL"),
    exchange: Optional[str] = Query("ALL"),
    account_id: Optional[str] = Query("ALL"),
    symbol: Optional[str] = Query("ALL"),
    side: Optional[str] = Query("ALL"),
    search: Optional[str] = Query(None),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200)
):
    """
    Returns granular execution fills ledger with exact commission and double-entry net wallet impact.
    Strictly isolated by customer identity.
    """
    user = require_authenticated_user(request)
    assert_account_ownership(user, account_id)
    target_user_id = user["user_id"] if user.get("role") not in ("ADMIN", "OWNER") else None

    offset = (page - 1) * page_size
    trades, total = query_trade_history(
        user_id=target_user_id,
        environment=environment,
        exchange=exchange,
        account_id=account_id,
        symbol=symbol,
        side=side,
        search=search,
        start_time_utc=start_time,
        end_time_utc=end_time,
        limit=page_size,
        offset=offset
    )
    return {
        "status": "SUCCESS",
        "total": total,
        "page": page,
        "page_size": page_size,
        "trades": trades
    }


@ledger_router.get("/holdings/spot")
async def get_spot_holdings(
    request: Request,
    account_id: Optional[str] = Query(None),
    environment: Optional[str] = Query("DEMO")
):
    """
    Returns dedicated Spot Asset Holdings (inventory) with live valuations.
    Strictly scoped to authenticated customer or admin.
    """
    user = require_authenticated_user(request)
    assert_account_ownership(user, account_id)
    target_user_id = user["user_id"] if user.get("role") not in ("ADMIN", "OWNER") else None

    holdings = query_spot_holdings(
        user_id=target_user_id or user["user_id"],
        account_id=account_id if account_id and account_id != "ALL" else None,
        environment=environment
    )
    total_val = sum(float(h.get("valuation_usd", 0.0)) for h in holdings)
    return {
        "status": "SUCCESS",
        "total_valuation_usd": round(total_val, 2),
        "holdings_count": len(holdings),
        "holdings": holdings
    }


@ledger_router.get("/orders/{order_id}/dossier")
async def get_order_dossier(order_id: str, request: Request):
    """
    Returns complete 5-section execution audit dossier for an individual order.
    Enforces that customer A cannot inspect customer B's order dossier.
    """
    user = require_authenticated_user(request)
    dossier = get_order_audit_dossier(user_id=user["user_id"], order_id_or_client_id=order_id)
    if not dossier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Order {order_id} not found in ledger.")

    # Authorization boundary: Customers can only access their own orders
    if user.get("role") not in ("ADMIN", "OWNER") and dossier.get("user_id") != user["user_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You do not have permission to view this order dossier."
        )

    return {
        "status": "SUCCESS",
        "dossier": dossier
    }


@ledger_router.post("/sync")
async def sync_exchange(req: SyncExchangeRequest, request: Request):
    """
    Triggers historical reconciliation and balance synchronization with Binance Demo API.
    Upserts missing orders and trades idempotently without creating duplicates.
    Requires customer ownership of the specified exchange connection.
    """
    user = require_authenticated_user(request)
    assert_account_ownership(user, req.account_id)

    try:
        res = await sync_binance_account(
            account_id=req.account_id,
            user_id=user["user_id"],
            tracked_symbols=req.tracked_symbols
        )
        return res
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Exchange sync failed: {str(e)}")


@ledger_router.get("/orders/export.csv")
async def export_orders_csv(
    request: Request,
    environment: Optional[str] = Query("ALL"),
    exchange: Optional[str] = Query("ALL"),
    account_id: Optional[str] = Query("ALL"),
    symbol: Optional[str] = Query("ALL"),
    side: Optional[str] = Query("ALL"),
    status: Optional[str] = Query("ALL"),
    search: Optional[str] = Query(None),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None)
):
    """Streams server-side CSV export of filtered Order History for tax and audit compliance."""
    user = require_authenticated_user(request)
    assert_account_ownership(user, account_id)
    target_user_id = user["user_id"] if user.get("role") not in ("ADMIN", "OWNER") else None

    orders, _ = query_order_history(
        user_id=target_user_id,
        environment=environment,
        exchange=exchange,
        account_id=account_id,
        symbol=symbol,
        side=side,
        status_filter=status,
        search=search,
        start_time_utc=start_time,
        end_time_utc=end_time,
        limit=5000,
        offset=0
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Exchange Order ID", "Client Order ID", "Internal Order ID",
        "Submission Time UTC", "Pair", "Side", "Type",
        "Requested Price", "Average Fill Price", "Original Qty", "Executed Qty",
        "Remaining Qty", "Cumulative Quote USD", "Status",
        "Commission Paid", "Commission Asset", "Verification Status",
        "Environment", "Provider", "Account ID"
    ])

    for o in orders:
        writer.writerow([
            o.get("exchange_order_id") or "",
            o.get("client_order_id") or "",
            o.get("internal_order_id") or "",
            o.get("created_at_utc") or "",
            o.get("display_pair") or o.get("symbol") or "",
            o.get("side") or "",
            o.get("order_type") or "",
            o.get("requested_price") or 0.0,
            o.get("avg_fill_price") or 0.0,
            o.get("orig_qty") or 0.0,
            o.get("executed_qty") or 0.0,
            o.get("remaining_qty") or 0.0,
            o.get("cummulative_quote_qty") or 0.0,
            o.get("status") or "",
            o.get("commission_total") or 0.0,
            o.get("commission_asset") or "",
            o.get("verification_status") or "",
            o.get("environment") or "",
            o.get("provider") or "",
            o.get("account_id") or ""
        ])

    output.seek(0)
    filename = f"bitdex_orders_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@ledger_router.get("/trades/export.csv")
async def export_trades_csv(
    request: Request,
    environment: Optional[str] = Query("ALL"),
    exchange: Optional[str] = Query("ALL"),
    account_id: Optional[str] = Query("ALL"),
    symbol: Optional[str] = Query("ALL"),
    side: Optional[str] = Query("ALL"),
    search: Optional[str] = Query(None),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None)
):
    """Streams server-side CSV export of filtered Trade Fills for tax and audit compliance."""
    user = require_authenticated_user(request)
    assert_account_ownership(user, account_id)
    target_user_id = user["user_id"] if user.get("role") not in ("ADMIN", "OWNER") else None

    trades, _ = query_trade_history(
        user_id=target_user_id,
        environment=environment,
        exchange=exchange,
        account_id=account_id,
        symbol=symbol,
        side=side,
        search=search,
        start_time_utc=start_time,
        end_time_utc=end_time,
        limit=5000,
        offset=0
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Exchange Trade ID", "Parent Order ID", "Client Order ID",
        "Execution Time UTC", "Pair", "Side",
        "Execution Price", "Executed Qty", "Gross Value USD",
        "Commission", "Commission Asset", "Net Settlement Impact",
        "Maker/Taker", "Verification Status", "Environment", "Account ID"
    ])

    for t in trades:
        role = "MAKER" if t.get("is_maker") else "TAKER"
        writer.writerow([
            t.get("exchange_trade_id") or "",
            t.get("exchange_order_id") or "",
            t.get("client_order_id") or "",
            t.get("trade_time_utc") or "",
            t.get("display_pair") or t.get("symbol") or "",
            t.get("side") or "",
            t.get("price") or 0.0,
            t.get("qty") or 0.0,
            t.get("quote_qty") or 0.0,
            t.get("commission") or 0.0,
            t.get("commission_asset") or "",
            t.get("net_impact_str") or "",
            role,
            t.get("verification_status") or "",
            t.get("environment") or "",
            t.get("account_id") or ""
        ])

    output.seek(0)
    filename = f"bitdex_fills_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
