"""
BITDEX Independent Protection Supervisor & Watchdog Engine (R3 Specification).
Operates as Layer 2 catastrophic protection decoupled from the main API process.
Monitors exchange positions, detects naked positions, stop mismatches, liquidation proximity,
and executes scoped emergency flattens without touching Engine A or manual orders.
"""

import json
import time
import logging
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("bitdex.protection.watchdog")


class ProtectionWatchdog:
    """
    Autonomous watchdog engine providing continuous position supervision,
    exchange stop reconciliation, and emergency risk containment.
    """

    EMERGENCY_LIQUIDATION_BUFFER_PCT = 0.08  # 8% liquidation distance threshold
    CRITICAL_LIQUIDATION_BUFFER_PCT = 0.03   # 3% immediate flatten threshold
    DEFAULT_CHECK_INTERVAL_SECONDS = 1.5

    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @classmethod
    def audit_reconciliation_event(
        cls,
        conn: sqlite3.Connection,
        account_id: str,
        user_id: str,
        symbol: str,
        event_type: str,
        severity: str,
        details: Dict[str, Any]
    ) -> str:
        """Record reconciliation and protection events in database."""
        event_id = f"REC-{secrets.token_hex(6).upper()}"
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO futures_reconciliation_events
            (event_id, user_id, account_id, symbol, event_type, severity, internal_value, exchange_value, discrepancy_details_json, resolution_status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id, user_id, account_id, symbol, event_type, severity,
                details.get("internal", ""), details.get("exchange", ""),
                json.dumps(details), "OPEN", cls.now_iso()
            )
        )
        return event_id

    @classmethod
    def trip_circuit_breaker(
        cls,
        conn: sqlite3.Connection,
        account_id: str,
        reason: str
    ) -> None:
        """Trip Engine B circuit breaker: locks trading on account immediately."""
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE futures_accounts SET trading_locked = 1, engine_b_enabled = 0, updated_at = ? WHERE account_id = ?",
            (cls.now_iso(), account_id)
        )
        logger.critical("[CIRCUIT_BREAKER_TRIPPED] Account %s locked: %s", account_id, reason)

    @classmethod
    def reconcile_and_protect_position(
        cls,
        conn: sqlite3.Connection,
        account_id: str,
        user_id: str,
        symbol: str,
        position_record: Dict[str, Any],
        exchange_open_orders: List[Dict[str, Any]],
        mark_price: float,
        adapter: Optional[Any] = None,
        simulate: bool = False
    ) -> Dict[str, Any]:
        """
        Reconciles a single open position against active exchange orders:
        1. Confirms whether a valid exchange-native STOP_MARKET order exists.
        2. Detects quantity mismatch between stop order and active position.
        3. Detects dangerous liquidation proximity.
        4. Dispatches repair stop or emergency flatten order if protection is broken.
        """
        sym = symbol.upper()
        pos_qty = abs(float(position_record.get("quantity", 0.0)))
        pos_side = position_record.get("position_side", "BOTH")
        entry_price = float(position_record.get("entry_price", 0.0))
        liq_price = float(position_record.get("liquidation_price", 0.0))
        direction = "LONG" if float(position_record.get("quantity", 0.0)) > 0 else "SHORT"

        if pos_qty <= 0.0:
            return {"status": "FLAT", "protected": True, "action_taken": None}

        # Liquidation distance calculation
        liq_dist_pct = 1.0
        if liq_price > 0.0 and mark_price > 0.0:
            liq_dist_pct = abs(mark_price - liq_price) / mark_price

        # Find active STOP_MARKET order belonging to this position
        active_stop = None
        for o in exchange_open_orders:
            o_sym = o.get("symbol", "").upper()
            o_type = o.get("type", "").upper()
            o_coid = o.get("clientOrderId", "")
            # Filter strictly by symbol and STOP_MARKET type
            if o_sym == sym and o_type in ("STOP_MARKET", "STOP"):
                # Must be reduce_only or an EBS-* order
                if o.get("reduceOnly") or o_coid.startswith("EBS-") or o_coid.startswith("STP-"):
                    active_stop = o
                    break

        # Scenario 1: Critical Liquidation Proximity (< 3%) -> Emergency Immediate Flatten
        if liq_dist_pct < cls.CRITICAL_LIQUIDATION_BUFFER_PCT:
            cls.audit_reconciliation_event(
                conn, account_id, user_id, sym,
                "CRITICAL_LIQUIDATION_PROXIMITY", "CRITICAL",
                {"mark_price": mark_price, "liq_price": liq_price, "dist_pct": liq_dist_pct}
            )
            flatten_res = cls._execute_emergency_flatten(
                conn, account_id, user_id, sym, pos_qty, direction,
                "Critical liquidation proximity detected (<3%)", adapter, simulate
            )
            cls.trip_circuit_breaker(conn, account_id, f"Critical liquidation proximity on {sym}")
            return {"status": "EMERGENCY_FLATTENED", "protected": False, "reason": "CRITICAL_LIQUIDATION", "details": flatten_res}

        # Scenario 2: Naked Position (Zero Stop Orders Found on Exchange)
        if not active_stop:
            cls.audit_reconciliation_event(
                conn, account_id, user_id, sym,
                "NAKED_POSITION_DETECTED", "HIGH",
                {"pos_qty": pos_qty, "mark_price": mark_price, "error": "No active STOP_MARKET order on exchange"}
            )
            # Attempt safe repair
            repair_ok, repair_details = cls._attempt_stop_repair(
                conn, account_id, user_id, sym, pos_qty, direction, entry_price, mark_price, adapter, simulate
            )
            if repair_ok:
                return {"status": "REPAIRED", "protected": True, "action_taken": "STOP_ORDER_REPLACED", "details": repair_details}
            else:
                # Repair failed -> Must emergency flatten to prevent catastrophic naked exposure!
                cls.audit_reconciliation_event(
                    conn, account_id, user_id, sym,
                    "STOP_REPAIR_FAILED_EMERGENCY_FLATTEN", "CRITICAL",
                    {"repair_error": repair_details}
                )
                flatten_res = cls._execute_emergency_flatten(
                    conn, account_id, user_id, sym, pos_qty, direction,
                    "Stop repair failed on exchange", adapter, simulate
                )
                cls.trip_circuit_breaker(conn, account_id, f"Stop repair failed for {sym}")
                return {"status": "EMERGENCY_FLATTENED", "protected": False, "reason": "REPAIR_FAILED", "details": flatten_res}

        # Scenario 3: Stop Quantity Mismatch (Partial scale-out or fill mismatch)
        stop_qty = float(active_stop.get("origQty", 0.0))
        if not math_isclose(stop_qty, pos_qty, rel_tol=1e-4):
            cls.audit_reconciliation_event(
                conn, account_id, user_id, sym,
                "STOP_QUANTITY_MISMATCH", "MEDIUM",
                {"stop_qty": stop_qty, "pos_qty": pos_qty}
            )
            # Cancel mismatched stop and replace with exact position quantity
            if adapter and not simulate:
                try:
                    adapter.cancel_order(sym, order_id=active_stop.get("orderId"))
                except Exception as ce:
                    logger.warning("Could not cancel mismatched stop order: %s", str(ce))

            repair_ok, repair_details = cls._attempt_stop_repair(
                conn, account_id, user_id, sym, pos_qty, direction, entry_price, mark_price, adapter, simulate
            )
            if repair_ok:
                return {"status": "REPAIRED", "protected": True, "action_taken": "STOP_QUANTITY_RESYNCHRONIZED", "details": repair_details}

        # Scenario 4: Stop is active, valid, and matches position quantity
        return {
            "status": "HEALTHY",
            "protected": True,
            "action_taken": None,
            "active_stop_order_id": active_stop.get("orderId"),
            "stop_price": active_stop.get("stopPrice"),
            "liquidation_distance_pct": round(liq_dist_pct * 100, 2)
        }

    @classmethod
    def _attempt_stop_repair(
        cls,
        conn: sqlite3.Connection,
        account_id: str,
        user_id: str,
        symbol: str,
        quantity: float,
        direction: str,
        entry_price: float,
        mark_price: float,
        adapter: Optional[Any],
        simulate: bool
    ) -> Tuple[bool, Any]:
        """Places an exchange-confirmed replacement STOP_MARKET order."""
        stop_side = "SELL" if direction == "LONG" else "BUY"
        # Standard conservative 1.5% protective stop distance from entry
        if direction == "LONG":
            repair_stop_price = round(entry_price * 0.985, 2)
            if repair_stop_price >= mark_price:  # If price already breached stop, set just below mark
                repair_stop_price = round(mark_price * 0.995, 2)
        else:
            repair_stop_price = round(entry_price * 1.015, 2)
            if repair_stop_price <= mark_price:
                repair_stop_price = round(mark_price * 1.005, 2)

        stop_coid = f"EBS-{secrets.token_hex(6)}"

        if adapter and not simulate:
            try:
                resp = adapter.submit_order(
                    symbol=symbol,
                    side=stop_side,
                    order_type="STOP_MARKET",
                    quantity=quantity,
                    stop_price=repair_stop_price,
                    reduce_only=True,
                    client_order_id=stop_coid,
                    position_side="BOTH"
                )
                logger.info("[WATCHDOG_STOP_REPAIRED] Placed %s stop on %s at ${repair_stop_price}", stop_side, symbol)
                return True, resp
            except Exception as ex:
                logger.error("[WATCHDOG_STOP_REPAIR_FAILED] %s: %s", symbol, str(ex))
                return False, str(ex)
        else:
            sim_resp = {"orderId": int(time.time() * 1000) % 1_000_000_000, "status": "NEW", "stopPrice": repair_stop_price, "clientOrderId": stop_coid}
            return True, sim_resp

    @classmethod
    def _execute_emergency_flatten(
        cls,
        conn: sqlite3.Connection,
        account_id: str,
        user_id: str,
        symbol: str,
        quantity: float,
        direction: str,
        reason: str,
        adapter: Optional[Any],
        simulate: bool
    ) -> Dict[str, Any]:
        """Executes scoped emergency market closure to flatten position."""
        exit_side = "SELL" if direction == "LONG" else "BUY"
        emg_coid = f"EMG-EB-{secrets.token_hex(6)}"

        logger.critical("[EMERGENCY_FLATTEN_DISPATCHED] Account: %s, Symbol: %s, Qty: %s, Reason: %s", account_id, symbol, quantity, reason)

        if adapter and not simulate:
            try:
                resp = adapter.submit_order(
                    symbol=symbol,
                    side=exit_side,
                    order_type="MARKET",
                    quantity=quantity,
                    reduce_only=True,
                    client_order_id=emg_coid,
                    position_side="BOTH"
                )
                return {"success": True, "order_id": resp.get("orderId"), "coid": emg_coid, "reason": reason}
            except Exception as ex:
                logger.critical("[EMERGENCY_FLATTEN_FAILED] %s: %s", symbol, str(ex))
                return {"success": False, "error": str(ex), "coid": emg_coid, "reason": reason}
        else:
            return {"success": True, "simulated": True, "order_id": 999999999, "coid": emg_coid, "reason": reason}


def math_isclose(a: float, b: float, rel_tol: float = 1e-4) -> bool:
    return abs(a - b) <= max(rel_tol * max(abs(a), abs(b)), 0.0)
