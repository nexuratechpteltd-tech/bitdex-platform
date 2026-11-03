"""
BITDEX Futures Reconciliation & Accounting Engine
==================================================
Authoritative state synchronization between internal database records and
Binance USD(S)-M Futures exchange endpoints.

Capabilities:
1. Reconcile open positions against GET /fapi/v2/positionRisk
2. Reconcile active orders against GET /fapi/v1/openOrders & GET /fapi/v1/order
3. Sync income statements (funding fees, realized PnL, commissions) from GET /fapi/v1/income
4. Log any detected discrepancies into futures_reconciliation_events
"""

import time
import logging
import sqlite3
from typing import Optional, Dict, Any, List

from .futures_db import (
    list_open_futures_positions,
    get_open_futures_position,
    upsert_futures_position,
    update_futures_order_status,
    record_reconciliation_event,
    record_funding_payment,
    record_realized_pnl,
    get_futures_account,
    update_futures_account_balances,
)
from .binance_futures_adapter import BinanceFuturesAdapter, BinanceFuturesError

logger = logging.getLogger("bitdex.futures.reconciliation")


class FuturesReconciliationEngine:
    """Authoritative reconciliation between internal SQLite state and Binance Futures."""

    @classmethod
    def reconcile_positions(
        cls,
        conn: sqlite3.Connection,
        user_id: str,
        account_id: str,
        adapter: BinanceFuturesAdapter,
    ) -> Dict[str, Any]:
        """
        Compare internal futures_positions against Binance /fapi/v2/positionRisk.
        Detects ghost positions, unrecorded exchange liquidations, or untracked stop-loss fills.
        """
        internal_positions = list_open_futures_positions(conn, user_id=user_id)
        internal_by_sym = {p["symbol"].upper(): p for p in internal_positions}
        
        try:
            exchange_positions = adapter.get_position_risk()
        except BinanceFuturesError as bfe:
            logger.error("Failed to fetch exchange positions for user %s: %s", user_id, str(bfe))
            return {"status": "FAILED", "error": str(bfe)}

        active_exchange_by_sym = {}
        for ep in exchange_positions:
            qty = float(ep.get("positionAmt", 0.0))
            if abs(qty) > 1e-8:
                sym = ep.get("symbol", "").upper()
                active_exchange_by_sym[sym] = {
                    "symbol": sym,
                    "quantity": qty,
                    "entry_price": float(ep.get("entryPrice", 0.0)),
                    "mark_price": float(ep.get("markPrice", 0.0)),
                    "liquidation_price": float(ep.get("liquidationPrice", 0.0)),
                    "unrealized_pnl": float(ep.get("unRealizedProfit", 0.0)),
                    "isolated_margin": float(ep.get("isolatedMargin", 0.0)),
                    "leverage": int(ep.get("leverage", 1)),
                }

        discrepancies: List[Dict[str, Any]] = []
        synced: List[str] = []

        # 1. Check all internal positions against exchange
        for sym, ipos in internal_by_sym.items():
            iqty = float(ipos["quantity"])
            if sym not in active_exchange_by_sym:
                # Discrepancy: Internal says OPEN, but exchange has NO open position!
                # (e.g. Stop-loss was triggered on exchange while backend was offline)
                discrepancy = {
                    "symbol": sym,
                    "type": "POSITION_CLOSED_ON_EXCHANGE",
                    "internal_quantity": iqty,
                    "exchange_quantity": 0.0,
                }
                discrepancies.append(discrepancy)
                record_reconciliation_event(
                    conn=conn,
                    user_id=user_id,
                    account_id=account_id,
                    event_type="POSITION_DESYNC",
                    severity="CRITICAL",
                    symbol=sym,
                    internal_value=f"QTY={iqty}",
                    exchange_value="QTY=0.0",
                    discrepancy_details=discrepancy
                )
                # Auto-heal: Mark internal position as CLOSED
                upsert_futures_position(
                    conn=conn,
                    user_id=user_id,
                    account_id=account_id,
                    symbol=sym,
                    quantity=0.0,
                    entry_price=float(ipos["entry_price"]),
                    mark_price=float(ipos["mark_price"]),
                    leverage=int(ipos["leverage"]),
                    isolated_margin=0.0
                )
            else:
                epos = active_exchange_by_sym[sym]
                eqty = epos["quantity"]
                # Compare quantities
                if abs(iqty - eqty) > 1e-6:
                    discrepancy = {
                        "symbol": sym,
                        "type": "QUANTITY_MISMATCH",
                        "internal_quantity": iqty,
                        "exchange_quantity": eqty,
                    }
                    discrepancies.append(discrepancy)
                    record_reconciliation_event(
                        conn=conn,
                        user_id=user_id,
                        account_id=account_id,
                        event_type="QUANTITY_MISMATCH",
                        severity="WARNING",
                        symbol=sym,
                        internal_value=str(iqty),
                        exchange_value=str(eqty),
                        discrepancy_details=discrepancy
                    )
                else:
                    # Healthy sync: update mark price & unrealized PnL from exchange
                    upsert_futures_position(
                        conn=conn,
                        user_id=user_id,
                        account_id=account_id,
                        symbol=sym,
                        quantity=iqty,
                        entry_price=float(ipos["entry_price"]),
                        mark_price=epos["mark_price"],
                        leverage=epos["leverage"],
                        isolated_margin=epos["isolated_margin"] or float(ipos["isolated_margin"]),
                        liquidation_price=epos["liquidation_price"],
                        unrealized_pnl=epos["unrealized_pnl"]
                    )
                    synced.append(sym)

        # 2. Check for exchange positions untracked internally
        for sym, epos in active_exchange_by_sym.items():
            if sym not in internal_by_sym:
                discrepancy = {
                    "symbol": sym,
                    "type": "UNTRACKED_EXCHANGE_POSITION",
                    "internal_quantity": 0.0,
                    "exchange_quantity": epos["quantity"],
                }
                discrepancies.append(discrepancy)
                record_reconciliation_event(
                    conn=conn,
                    user_id=user_id,
                    account_id=account_id,
                    event_type="UNTRACKED_POSITION",
                    severity="CRITICAL",
                    symbol=sym,
                    internal_value="QTY=0.0",
                    exchange_value=f"QTY={epos['quantity']}",
                    discrepancy_details=discrepancy
                )

        return {
            "status": "COMPLETED",
            "internal_open_count": len(internal_positions),
            "exchange_open_count": len(active_exchange_by_sym),
            "synced_symbols": synced,
            "discrepancies": discrepancies,
        }

    @classmethod
    def reconcile_orders(
        cls,
        conn: sqlite3.Connection,
        user_id: str,
        account_id: str,
        adapter: BinanceFuturesAdapter,
        symbol: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Reconcile active orders (status in ('NEW', 'SUBMITTED', 'PARTIALLY_FILLED')).
        Queries Binance openOrders and specific orders to ensure lifecycle states match.
        """
        # Query internal non-terminal orders
        query = """SELECT * FROM futures_orders 
                   WHERE user_id = ? AND status IN ('NEW', 'SUBMITTED', 'PARTIALLY_FILLED')"""
        params = [user_id]
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol.upper())
            
        rows = conn.execute(query, tuple(params)).fetchall()
        open_internal_orders = [dict(r) for r in rows]

        try:
            exchange_open_orders = adapter.get_open_orders(symbol=symbol)
            exchange_order_ids = {int(eo["orderId"]) for eo in exchange_open_orders if "orderId" in eo}
        except BinanceFuturesError as bfe:
            logger.error("Failed to query open orders on exchange: %s", str(bfe))
            return {"status": "FAILED", "error": str(bfe)}

        updated_orders = []
        for io in open_internal_orders:
            eoid = io.get("exchange_order_id")
            if not eoid:
                continue

            if int(eoid) not in exchange_order_ids:
                # Order is no longer open on exchange! Query its final status.
                try:
                    order_status_resp = adapter.query_order(symbol=io["symbol"], order_id=int(eoid))
                    x_status = order_status_resp.get("status")
                    if x_status == "FILLED":
                        update_futures_order_status(
                            conn=conn,
                            user_id=user_id,
                            order_id=io["order_id"],
                            status="FILLED",
                            executed_qty=float(order_status_resp.get("executedQty", io["quantity"])),
                            avg_fill_price=float(order_status_resp.get("avgPrice", io["price"] or 0.0)),
                            is_exchange_confirmed=True
                        )
                        updated_orders.append({"order_id": io["order_id"], "new_status": "FILLED"})
                    elif x_status in ("CANCELED", "EXPIRED", "REJECTED"):
                        update_futures_order_status(
                            conn=conn,
                            user_id=user_id,
                            order_id=io["order_id"],
                            status=x_status,
                            rejection_reason=f"EXCHANGE_FINAL_STATUS_{x_status}"
                        )
                        updated_orders.append({"order_id": io["order_id"], "new_status": x_status})
                except Exception as qe:
                    logger.warning("Could not query order %s on exchange: %s", eoid, str(qe))

        return {
            "status": "COMPLETED",
            "scanned_count": len(open_internal_orders),
            "updated_orders": updated_orders
        }

    @classmethod
    def sync_income_and_funding(
        cls,
        conn: sqlite3.Connection,
        user_id: str,
        account_id: str,
        adapter: BinanceFuturesAdapter,
        symbol: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """
        Fetch income ledger from GET /fapi/v1/income.
        Deduplicates via exchange_tran_id and records funding fees & realized PnL.
        """
        try:
            records = adapter.get_income_history(symbol=symbol, limit=limit)
        except BinanceFuturesError as bfe:
            logger.error("Failed to query income history: %s", str(bfe))
            return {"status": "FAILED", "error": str(bfe)}

        funding_saved = 0
        pnl_synced = 0
        total_funding_usd = 0.0

        for r in records:
            itype = r.get("incomeType")
            income_usd = float(r.get("income", 0.0))
            sym = r.get("symbol", "")
            tran_id = r.get("tranId")
            tran_time = r.get("time")

            if itype == "FUNDING_FEE":
                f_rec = record_funding_payment(
                    conn=conn,
                    user_id=user_id,
                    account_id=account_id,
                    symbol=sym,
                    funding_rate=0.0,
                    position_qty_at_funding=0.0,
                    payment_amount_usd=income_usd,
                    exchange_tran_id=int(tran_id) if tran_id else None
                )
                if f_rec:
                    funding_saved += 1
                    total_funding_usd += income_usd

            elif itype == "REALIZED_PNL":
                # Check if this realized PnL was already recorded
                existing = conn.execute(
                    "SELECT pnl_id FROM futures_realized_pnl WHERE user_id = ? AND symbol = ? AND net_pnl_usd = ?",
                    (user_id, sym, income_usd)
                ).fetchone()
                if not existing:
                    record_realized_pnl(
                        conn=conn,
                        user_id=user_id,
                        account_id=account_id,
                        symbol=sym,
                        entry_price=0.0,
                        exit_price=0.0,
                        closed_qty=0.0,
                        gross_pnl_usd=income_usd,
                        total_fees_usd=0.0,
                        net_pnl_usd=income_usd,
                        source="EXCHANGE_INCOME_SYNC"
                    )
                    pnl_synced += 1

        # Adjust account wallet balance if new funding was recorded
        if funding_saved > 0:
            acct = get_futures_account(conn, user_id=user_id, account_id=account_id)
            if acct:
                w_bal = float(acct["wallet_balance"]) + total_funding_usd
                a_bal = float(acct["available_balance"]) + total_funding_usd
                update_futures_account_balances(
                    conn=conn,
                    user_id=user_id,
                    account_id=account_id,
                    wallet_balance=round(w_bal, 2),
                    available_balance=round(a_bal, 2)
                )

        return {
            "status": "COMPLETED",
            "scanned_records": len(records),
            "funding_records_saved": funding_saved,
            "external_pnl_synced": pnl_synced,
            "total_funding_usd": round(total_funding_usd, 4),
        }
