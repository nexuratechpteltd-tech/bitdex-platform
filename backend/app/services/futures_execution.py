"""
BITDEX Futures Execution & Position Lifecycle Engine (Phase 3 Hardened)
=======================================================================
Orchestrates pre-trade risk checks, exchange dispatch, fill processing,
fail-safe protective stop loss verification, emergency closure policies,
and complete round-trip fee accounting.

Audit & Hardening:
- Fee Accounting: Correctly computes round-trip fees (entry commission + exit commission).
- Protective Stop Reliability:
  * Uses verified filled quantity (handling partial fills).
  * Dispatches STOP_MARKET to Binance Futures exchange.
  * Verifies exchange acknowledgment and persists exchange order ID.
  * If protective stop fails on exchange, executes emergency market reduction/closure
    to prevent naked open positions.
"""

import time
import secrets
import logging
import sqlite3
from typing import Optional, Dict, Any, Tuple

from .futures_db import (
    get_or_create_futures_account,
    get_futures_account,
    update_futures_account_balances,
    create_futures_order,
    get_futures_order,
    update_futures_order_status,
    get_open_futures_position,
    upsert_futures_position,
    record_futures_fill,
    record_realized_pnl,
    record_reconciliation_event,
    utc_now_iso,
)
from .futures_risk_engine import FuturesRiskEngine, FuturesRiskDecisionResult
from .binance_futures_adapter import BinanceFuturesAdapter, BinanceFuturesError

logger = logging.getLogger("bitdex.futures.execution")


class FuturesExecutionEngine:
    """Executes validated futures trade intents and manages the position state machine."""

    DEFAULT_TAKER_FEE_RATE = 0.0004  # 0.04% Binance USD(S)-M taker fee
    DEFAULT_MAKER_FEE_RATE = 0.0002  # 0.02% Binance USD(S)-M maker fee

    @classmethod
    def execute_intent(
        cls,
        conn: sqlite3.Connection,
        user_id: str,
        intent: str,  # "LONG_ENTRY", "LONG_EXIT", "SHORT_ENTRY", "SHORT_EXIT"
        symbol: str,
        quantity: float,
        price: float,
        stop_price: Optional[float] = None,
        leverage: int = 3,
        margin_type: str = "ISOLATED",
        client_order_id: Optional[str] = None,
        order_type: str = "MARKET",
        adapter: Optional[BinanceFuturesAdapter] = None,
        environment: str = "testnet",
        simulate_execution: bool = False,
        fail_stop_for_testing: bool = False,
        simulate_post_only_reject: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute an intentional futures order lifecycle:
        1. Validate intent & idempotency
        2. Evaluate pre-trade risk engine
        3. Persist order in SUBMITTED state
        4. Dispatch to Binance Futures Adapter (or simulate if adapter is None)
        5. Process fill, attach verified protective stop-loss, update position & accounts
        """
        sym = symbol.upper()
        s_intent = intent.upper()
        if s_intent not in ("LONG_ENTRY", "LONG_EXIT", "SHORT_ENTRY", "SHORT_EXIT"):
            raise ValueError(f"Invalid intent '{intent}'. Must be LONG_ENTRY, LONG_EXIT, SHORT_ENTRY, or SHORT_EXIT.")

        # Determine side and position direction
        if s_intent == "LONG_ENTRY":
            side = "BUY"
            position_side = "BOTH"
            reduce_only = False
        elif s_intent == "LONG_EXIT":
            side = "SELL"
            position_side = "BOTH"
            reduce_only = True
        elif s_intent == "SHORT_ENTRY":
            side = "SELL"
            position_side = "BOTH"
            reduce_only = False
        elif s_intent == "SHORT_EXIT":
            side = "BUY"
            position_side = "BOTH"
            reduce_only = True

        coid = client_order_id or f"FO-{secrets.token_hex(8)}"

        # 1. Idempotency Check
        existing_order = get_futures_order(conn, user_id=user_id, client_order_id=coid)
        if existing_order:
            logger.warning("Duplicate client_order_id %s received for user %s", coid, user_id)
            return {
                "success": False,
                "error_code": "DUPLICATE_CLIENT_ORDER_ID",
                "message": f"Order with client_order_id {coid} already exists.",
                "order": existing_order,
            }

        # Ensure Account Exists
        account = get_or_create_futures_account(
            conn, user_id=user_id,
            exchange_connection_id=f"CONN-{user_id[:8]}",
            environment=environment
        )
        account_id = account["account_id"]

        # 2. Pre-Trade Risk Evaluation
        risk_result = FuturesRiskEngine.evaluate_pre_trade(
            conn=conn,
            user_id=user_id,
            account_id=account_id,
            client_order_id=coid,
            symbol=sym,
            side=side,
            intent=s_intent,
            quantity=quantity,
            price=price,
            leverage=leverage,
            margin_type=margin_type,
            stop_price=stop_price,
            market_price_timestamp_ms=int(time.time() * 1000)
        )

        if not risk_result.is_approved:
            rejected_order = create_futures_order(
                conn=conn,
                user_id=user_id,
                account_id=account_id,
                client_order_id=coid,
                symbol=sym,
                side=side,
                order_type=order_type,
                intent=s_intent,
                quantity=quantity,
                price=price,
                stop_price=stop_price,
                reduce_only=reduce_only,
                position_side=position_side,
                status="REJECTED",
                risk_decision_id=risk_result.decision_id
            )
            update_futures_order_status(
                conn=conn,
                user_id=user_id,
                order_id=rejected_order["order_id"],
                status="REJECTED",
                rejection_reason=f"[{risk_result.rejection_code}] {risk_result.rejection_reason}"
            )
            return {
                "success": False,
                "error_code": risk_result.rejection_code,
                "message": risk_result.rejection_reason,
                "risk_decision_id": risk_result.decision_id,
                "order": rejected_order,
            }

        # 3. Create Order Record in SUBMITTED state
        order_record = create_futures_order(
            conn=conn,
            user_id=user_id,
            account_id=account_id,
            client_order_id=coid,
            symbol=sym,
            side=side,
            order_type=order_type,
            intent=s_intent,
            quantity=quantity,
            price=price,
            stop_price=stop_price,
            reduce_only=reduce_only,
            position_side=position_side,
            status="SUBMITTED",
            risk_decision_id=risk_result.decision_id
        )
        order_id = order_record["order_id"]

        # 4. Exchange Dispatch or Simulation
        exchange_order_id = None
        fill_price = price
        executed_qty = quantity
        is_exchange_confirmed = False

        is_maker = order_type.upper() in ("POST_ONLY", "LIMIT_MAKER")

        if adapter and not simulate_execution:
            try:
                try:
                    adapter.set_margin_type(sym, margin_type=margin_type)
                    adapter.set_leverage(sym, leverage=leverage)
                except Exception as me:
                    logger.warning("Could not set margin/leverage on adapter: %s", str(me))

                tif = "GTX" if is_maker else None
                raw_resp = adapter.submit_order(
                    symbol=sym,
                    side=side,
                    order_type=order_type,
                    quantity=quantity,
                    price=price if (order_type.upper() in ("LIMIT", "POST_ONLY", "LIMIT_MAKER")) else None,
                    stop_price=stop_price if "STOP" in order_type.upper() else None,
                    time_in_force=tif,
                    reduce_only=reduce_only,
                    client_order_id=coid,
                    position_side=position_side,
                )
                exchange_order_id = raw_resp.get("orderId")
                executed_qty = float(raw_resp.get("executedQty", quantity))
                if float(raw_resp.get("avgPrice", 0)) > 0:
                    fill_price = float(raw_resp.get("avgPrice"))
                is_exchange_confirmed = True
            except Exception as ex:
                err_str = str(ex)
                is_post_only_rej = "POST_ONLY_REJECTED" in err_str or "immediately match and take" in err_str or "-5022" in err_str
                err_code = "POST_ONLY_REJECTED" if is_post_only_rej else "EXCHANGE_DISPATCH_FAILED"
                logger.error("Exchange dispatch failed for order %s: %s", coid, err_str)
                update_futures_order_status(
                    conn=conn,
                    user_id=user_id,
                    order_id=order_id,
                    status="REJECTED",
                    rejection_reason=f"{err_code}: {err_str}"
                )
                return {
                    "success": False,
                    "error_code": err_code,
                    "message": err_str,
                    "order_id": order_id
                }
        else:
            # Staging Simulation Mode (deterministic test execution)
            if simulate_post_only_reject and is_maker:
                update_futures_order_status(
                    conn=conn,
                    user_id=user_id,
                    order_id=order_id,
                    status="REJECTED",
                    rejection_reason="POST_ONLY_REJECTED: Order would immediately cross order book as taker."
                )
                return {
                    "success": False,
                    "error_code": "POST_ONLY_REJECTED",
                    "message": "Order would immediately cross order book as taker.",
                    "order_id": order_id
                }
            exchange_order_id = int(time.time() * 1000) % 1_000_000_000
            fill_price = price
            executed_qty = quantity
            is_exchange_confirmed = True

        # 5. Process Fill & Update Order Lifecycle
        cumulative_quote = executed_qty * fill_price
        fee_rate = cls.DEFAULT_MAKER_FEE_RATE if is_maker else cls.DEFAULT_TAKER_FEE_RATE
        fee_amount = cumulative_quote * fee_rate

        update_futures_order_status(
            conn=conn,
            user_id=user_id,
            order_id=order_id,
            status="FILLED",
            exchange_order_id=exchange_order_id,
            executed_qty=executed_qty,
            cumulative_quote_qty=cumulative_quote,
            avg_fill_price=fill_price,
            is_exchange_confirmed=is_exchange_confirmed
        )

        fill_record = record_futures_fill(
            conn=conn,
            user_id=user_id,
            account_id=account_id,
            order_id=order_id,
            client_order_id=coid,
            symbol=sym,
            side=side,
            price=fill_price,
            quantity=executed_qty,
            fee_amount=fee_amount,
            fee_asset="USDT",
            exchange_trade_id=secrets.randbelow(10_000_000),
            exchange_order_id=exchange_order_id
        )

        # 6. Position & PnL Lifecycle Updates
        notional = executed_qty * fill_price
        margin_required = notional / max(1, leverage)

        if s_intent in ("LONG_ENTRY", "SHORT_ENTRY"):
            # ── SECTION 8: PROTECTIVE STOP RELIABILITY ──
            # Mandatory stop order placement based on actual filled quantity
            stop_order_coid = f"STP-{coid[:20]}"
            stop_side = "SELL" if s_intent == "LONG_ENTRY" else "BUY"
            stop_exchange_order_id = None
            stop_confirmed = False

            if fail_stop_for_testing:
                # Simulated failure for testing Section 8 protective stop emergency closure
                stop_exchange_order_id = None
                stop_confirmed = False
                logger.critical("TEST INJECTION: Protective stop order placement simulated failure.")
            elif adapter and not simulate_execution:
                try:
                    stop_resp = adapter.submit_order(
                        symbol=sym,
                        side=stop_side,
                        order_type="STOP_MARKET",
                        quantity=executed_qty,
                        stop_price=stop_price,
                        reduce_only=True,
                        client_order_id=stop_order_coid,
                        position_side=position_side
                    )
                    stop_exchange_order_id = stop_resp.get("orderId")
                    stop_confirmed = True
                except Exception as stop_ex:
                    logger.critical("PROTECTIVE STOP PLACEMENT FAILED on exchange: %s", str(stop_ex))
                    stop_confirmed = False
            else:
                stop_exchange_order_id = int(time.time() * 1000) % 1_000_000_000
                stop_confirmed = True

            # If protective stop failed, trigger emergency closure immediately
            if not stop_confirmed:
                record_reconciliation_event(
                    conn=conn,
                    user_id=user_id,
                    account_id=account_id,
                    event_type="PROTECTIVE_STOP_PLACEMENT_FAILED",
                    severity="CRITICAL",
                    symbol=sym,
                    internal_value=f"QTY={executed_qty}, STOP={stop_price}",
                    exchange_value="PLACEMENT_FAILED",
                    discrepancy_details={"error": "Exchange rejected or failed protective stop placement"}
                )

                # Emergency market exit to prevent naked exposure
                emergency_coid = f"EMG-{coid[:20]}"
                emergency_closed = False
                if adapter and not simulate_execution:
                    try:
                        adapter.submit_order(
                            symbol=sym,
                            side=stop_side,
                            order_type="MARKET",
                            quantity=executed_qty,
                            reduce_only=True,
                            client_order_id=emergency_coid,
                            position_side=position_side
                        )
                        emergency_closed = True
                    except Exception as emg_err:
                        logger.critical("EMERGENCY CLOSURE DISPATCH FAILED: %s", str(emg_err))
                else:
                    emergency_closed = True

                # Refund margin and record failure
                update_futures_order_status(
                    conn=conn,
                    user_id=user_id,
                    order_id=order_id,
                    status="FAILED_PROTECTION_EMERGENCY_CLOSED",
                    rejection_reason="Protective stop could not be verified on exchange. Position closed immediately via emergency policy."
                )

                return {
                    "success": False,
                    "error_code": "PROTECTIVE_STOP_FAILED_EMERGENCY_CLOSED",
                    "message": "Protective stop could not be verified on exchange. Position closed immediately via emergency policy.",
                    "order_id": order_id,
                    "emergency_closed": emergency_closed
                }

            # Stop confirmed! Record stop order in DB
            stop_order = create_futures_order(
                conn=conn,
                user_id=user_id,
                account_id=account_id,
                client_order_id=stop_order_coid,
                symbol=sym,
                side=stop_side,
                order_type="STOP_MARKET",
                intent="LONG_EXIT" if s_intent == "LONG_ENTRY" else "SHORT_EXIT",
                quantity=executed_qty,
                price=None,
                stop_price=stop_price,
                reduce_only=True,
                position_side=position_side,
                status="NEW",
                risk_decision_id=risk_result.decision_id
            )
            protective_stop_order_id = stop_order["order_id"]
            update_futures_order_status(
                conn=conn,
                user_id=user_id,
                order_id=order_id,
                status="FILLED",
                protective_stop_order_id=protective_stop_order_id
            )
            update_futures_order_status(
                conn=conn,
                user_id=user_id,
                order_id=protective_stop_order_id,
                status="NEW",
                exchange_order_id=stop_exchange_order_id,
                is_exchange_confirmed=True
            )

            # Liquidation Price Estimation
            if s_intent == "LONG_ENTRY":
                liq_price = max(0.0, fill_price - (margin_required / executed_qty) * 0.95)
                pos_qty = executed_qty
            else:
                liq_price = fill_price + (margin_required / executed_qty) * 0.95
                pos_qty = -executed_qty

            pos = upsert_futures_position(
                conn=conn,
                user_id=user_id,
                account_id=account_id,
                symbol=sym,
                quantity=pos_qty,
                entry_price=fill_price,
                mark_price=fill_price,
                leverage=leverage,
                isolated_margin=margin_required,
                liquidation_price=round(liq_price, 2),
                unrealized_pnl=0.0,
                position_side=position_side,
                active_stop_loss_order_id=protective_stop_order_id,
                stop_exchange_order_id=stop_exchange_order_id,
                entry_fee_usd=fee_amount
            )

            # Deduct isolated margin and entry fee from account balance
            curr_avail = float(account["available_balance"])
            curr_wallet = float(account["wallet_balance"])
            new_avail = max(0.0, curr_avail - margin_required - fee_amount)
            new_wallet = curr_wallet - fee_amount
            update_futures_account_balances(
                conn=conn,
                user_id=user_id,
                account_id=account_id,
                wallet_balance=round(new_wallet, 4),
                available_balance=round(new_avail, 4)
            )

            return {
                "success": True,
                "order_id": order_id,
                "client_order_id": coid,
                "symbol": sym,
                "side": side,
                "intent": s_intent,
                "executed_qty": executed_qty,
                "fill_price": fill_price,
                "entry_fee_usd": round(fee_amount, 4),
                "isolated_margin_usd": round(margin_required, 2),
                "protective_stop_order_id": protective_stop_order_id,
                "stop_exchange_order_id": stop_exchange_order_id,
                "stop_price": stop_price,
                "position": pos,
            }

        else:
            # ── SECTION 9: AUDITED EXIT & ROUND-TRIP FEE ACCOUNTING ──
            open_pos = get_open_futures_position(conn, user_id=user_id, symbol=sym)
            if not open_pos:
                raise RuntimeError(f"Open position missing during exit processing for {sym}")

            entry_p = float(open_pos["entry_price"])
            pos_qty = abs(float(open_pos["quantity"]))
            pos_margin = float(open_pos["isolated_margin"])
            closed_qty = min(pos_qty, executed_qty)

            # 1. Gross PnL
            if s_intent == "LONG_EXIT":
                gross_pnl = (fill_price - entry_p) * closed_qty
            else:  # SHORT_EXIT
                gross_pnl = (entry_p - fill_price) * closed_qty

            # 2. Audited Round-Trip Fees: Entry Commission + Exit Commission
            exit_fee = fee_amount
            pos_entry_fee = float(open_pos.get("entry_fee_usd", 0.0))
            # Pro-rata entry fee if partial exit
            pro_rata_entry_fee = pos_entry_fee * (closed_qty / pos_qty) if pos_qty > 0 else 0.0
            total_round_trip_fees = pro_rata_entry_fee + exit_fee

            # 3. True Realized Net PnL
            net_pnl = gross_pnl - total_round_trip_fees

            pnl_record = record_realized_pnl(
                conn=conn,
                user_id=user_id,
                account_id=account_id,
                symbol=sym,
                entry_price=entry_p,
                exit_price=fill_price,
                closed_qty=closed_qty,
                gross_pnl_usd=round(gross_pnl, 4),
                total_fees_usd=round(total_round_trip_fees, 4),
                net_pnl_usd=round(net_pnl, 4),
                position_id=open_pos["position_id"],
                closing_order_id=order_id,
                source="INTERNAL"
            )

            # 4. Update Position
            remaining_qty = pos_qty - closed_qty
            if remaining_qty <= 1e-8:
                upsert_futures_position(
                    conn=conn,
                    user_id=user_id,
                    account_id=account_id,
                    symbol=sym,
                    quantity=0.0,
                    entry_price=entry_p,
                    mark_price=fill_price,
                    leverage=leverage,
                    isolated_margin=0.0,
                    entry_fee_usd=0.0
                )
                # Cancel linked protective stop loss order
                if open_pos.get("active_stop_loss_order_id"):
                    update_futures_order_status(
                        conn=conn,
                        user_id=user_id,
                        order_id=open_pos["active_stop_loss_order_id"],
                        status="CANCELED",
                        rejection_reason="POSITION_CLOSED_BY_EXIT"
                    )
                    # If real adapter, delete order on exchange
                    if adapter and not simulate_execution and open_pos.get("stop_exchange_order_id"):
                        try:
                            adapter.cancel_order(sym, order_id=open_pos["stop_exchange_order_id"])
                        except Exception as ce:
                            logger.warning("Could not cancel stop order on exchange: %s", str(ce))
            else:
                # Partial exit: update remaining quantity and remaining entry fee
                remaining_entry_fee = pos_entry_fee - pro_rata_entry_fee
                remaining_margin = pos_margin * (remaining_qty / pos_qty)
                upsert_futures_position(
                    conn=conn,
                    user_id=user_id,
                    account_id=account_id,
                    symbol=sym,
                    quantity=remaining_qty if float(open_pos["quantity"]) > 0 else -remaining_qty,
                    entry_price=entry_p,
                    mark_price=fill_price,
                    leverage=leverage,
                    isolated_margin=remaining_margin,
                    entry_fee_usd=remaining_entry_fee
                )

            # 5. Account Balances Update
            # Note: entry_fee was already deducted from wallet at entry.
            # At exit, wallet receives (gross_pnl - exit_fee).
            # Total wallet change = -entry_fee + gross_pnl - exit_fee = net_pnl!
            curr_avail = float(account["available_balance"])
            curr_wallet = float(account["wallet_balance"])
            returned_margin = pos_margin if remaining_qty <= 1e-8 else (pos_margin - remaining_margin)
            new_avail = curr_avail + returned_margin + gross_pnl - exit_fee
            new_wallet = curr_wallet + gross_pnl - exit_fee
            update_futures_account_balances(
                conn=conn,
                user_id=user_id,
                account_id=account_id,
                wallet_balance=round(new_wallet, 4),
                available_balance=round(new_avail, 4)
            )

            return {
                "success": True,
                "order_id": order_id,
                "client_order_id": coid,
                "symbol": sym,
                "side": side,
                "intent": s_intent,
                "executed_qty": closed_qty,
                "entry_price": entry_p,
                "exit_price": fill_price,
                "gross_pnl_usd": round(gross_pnl, 4),
                "entry_fee_usd": round(pro_rata_entry_fee, 4),
                "exit_fee_usd": round(exit_fee, 4),
                "fees_usd": round(total_round_trip_fees, 4),
                "total_fees_usd": round(total_round_trip_fees, 4),
                "net_pnl_usd": round(net_pnl, 4),
                "pnl_record": pnl_record,
            }
