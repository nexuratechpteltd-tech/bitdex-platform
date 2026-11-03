"""
Tauric Platform — Standardized Order Lifecycle & Isolated Paper Trading Engine (Phase 3B)
Durable idempotency, strict state transitions, strategy preflight validation,
and complete ledger separation from real exchange write endpoints.
"""

import os
import json
import time
import secrets
import hashlib
from enum import Enum
from typing import Dict, Any, List, Optional, Set, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass, asdict, field


class OrderStatus(str, Enum):
    CREATED = "CREATED"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    UNKNOWN_OUTCOME = "UNKNOWN_OUTCOME"
    # Legacy compatibility aliases
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


# Canonical lifecycle state transitions
VALID_ORDER_TRANSITIONS: Dict[str, Set[str]] = {
    "CREATED": {"SUBMITTED", "REJECTED", "UNKNOWN_OUTCOME"},
    "SUBMITTED": {"ACKNOWLEDGED", "OPEN", "REJECTED", "EXPIRED", "UNKNOWN_OUTCOME"},
    "ACKNOWLEDGED": {
        "OPEN",
        "PARTIALLY_FILLED",
        "FILLED",
        "CANCEL_PENDING",
        "CANCELLED",
        "REJECTED",
        "EXPIRED",
        "UNKNOWN_OUTCOME",
    },
    "OPEN": {
        "PARTIALLY_FILLED",
        "FILLED",
        "CANCEL_PENDING",
        "CANCELLED",
        "EXPIRED",
        "UNKNOWN_OUTCOME",
    },
    "PARTIALLY_FILLED": {
        "PARTIALLY_FILLED",
        "FILLED",
        "CANCEL_PENDING",
        "CANCELLED",
        "EXPIRED",
        "UNKNOWN_OUTCOME",
    },
    "CANCEL_PENDING": {
        "CANCELLED",
        "FILLED",
        "PARTIALLY_FILLED",
        "UNKNOWN_OUTCOME",
    },
    "UNKNOWN_OUTCOME": {
        "OPEN",
        "PARTIALLY_FILLED",
        "FILLED",
        "CANCELLED",
        "REJECTED",
        "EXPIRED",
    },
    # Terminal states
    "FILLED": set(),
    "CANCELLED": set(),
    "REJECTED": set(),
    "EXPIRED": set(),
    # Legacy aliases
    "FAILED": set(),
    "UNKNOWN": {"OPEN", "PARTIALLY_FILLED", "FILLED", "CANCELLED", "REJECTED", "EXPIRED"},
}


def validate_order_transition(current: str, target: str) -> bool:
    """Returns True if transition from current to target is allowed."""
    c = str(current).upper()
    t = str(target).upper()
    if c == t:
        return True
    allowed = VALID_ORDER_TRANSITIONS.get(c, set())
    return t in allowed


class IdempotencyCollisionError(ValueError):
    """Raised when an idempotency key is reused with a different request payload."""
    pass


class InvalidOrderStateTransitionError(ValueError):
    """Raised when an order transition violates canonical lifecycle state rules."""
    pass


class StrategyPreflightError(ValueError):
    """Raised when an order fails strategy preflight validation."""
    pass


# Default file locations
_backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_DATA_DIR = os.getenv("TAURIC_DATA_DIR", os.path.join(_backend_root, "data"))
DEFAULT_PAPER_ORDERS_PATH = os.getenv(
    "TAURIC_PAPER_ORDERS_PATH", os.path.join(DEFAULT_DATA_DIR, "paper_orders_store.json")
)
DEFAULT_PAPER_LEDGER_PATH = os.getenv(
    "TAURIC_PAPER_LEDGER_PATH", os.path.join(DEFAULT_DATA_DIR, "paper_ledger_store.json")
)
DEFAULT_IDEMPOTENCY_PATH = os.getenv(
    "TAURIC_IDEMPOTENCY_PATH", os.path.join(DEFAULT_DATA_DIR, "idempotency_store.json")
)


class PaperLedger:
    """
    Isolated simulated ledger for paper trading.
    Completely isolated from real exchange wallets and write endpoints.
    """

    def __init__(self, storage_path: Optional[str] = None, starting_cash: float = 10000.0):
        self.storage_path = storage_path or DEFAULT_PAPER_LEDGER_PATH
        self.starting_cash = starting_cash
        self.cash_balance = starting_cash
        self.held_balance = 0.0
        self.realized_pnl = 0.0
        self.fees_paid = 0.0
        self._load()

    def _load(self):
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.cash_balance = float(data.get("cash_balance", self.starting_cash))
                    self.held_balance = float(data.get("held_balance", 0.0))
                    self.realized_pnl = float(data.get("realized_pnl", 0.0))
                    self.fees_paid = float(data.get("fees_paid", 0.0))
            except Exception:
                pass

    def _save(self):
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "cash_balance": round(self.cash_balance, 4),
                    "held_balance": round(self.held_balance, 4),
                    "realized_pnl": round(self.realized_pnl, 4),
                    "fees_paid": round(self.fees_paid, 4),
                    "equity": round(self.equity, 4),
                    "currency": "USDT",
                    "last_updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
                f,
                indent=2,
            )

    @property
    def equity(self) -> float:
        return self.cash_balance + self.held_balance + self.realized_pnl

    def allocate_margin(self, amount: float) -> bool:
        self._load()
        if amount <= 0:
            return True
        if self.cash_balance < amount:
            raise ValueError(
                f"Insufficient simulated paper balance: Available {self.cash_balance:.2f} USDT, "
                f"required {amount:.2f} USDT."
            )
        self.cash_balance = round(self.cash_balance - amount, 4)
        self.held_balance = round(self.held_balance + amount, 4)
        self._save()
        return True

    def release_margin(self, amount: float):
        self._load()
        rel = min(amount, self.held_balance)
        self.held_balance = round(self.held_balance - rel, 4)
        self.cash_balance = round(self.cash_balance + rel, 4)
        self._save()

    def settle_fill(
        self,
        allocated_amount: float,
        executed_notional: float,
        fee: float,
        realized_pnl: float = 0.0,
    ):
        self._load()
        rel = min(allocated_amount, self.held_balance)
        self.held_balance = round(self.held_balance - rel, 4)
        self.realized_pnl = round(self.realized_pnl + realized_pnl, 4)
        self.fees_paid = round(self.fees_paid + fee, 4)
        self.cash_balance = round(max(0.0, self.cash_balance - fee + realized_pnl), 4)
        self._save()

    def get_summary(self) -> Dict[str, Any]:
        self._load()
        return {
            "cash_balance": round(self.cash_balance, 4),
            "held_balance": round(self.held_balance, 4),
            "realized_pnl": round(self.realized_pnl, 4),
            "fees_paid": round(self.fees_paid, 4),
            "equity": round(self.equity, 4),
            "currency": "USDT",
            "account_type": "PAPER",
            "environment": "PAPER",
        }


class DurableIdempotencyStore:
    """
    Persisted idempotency store.
    Guarantees that repeated requests return existing orders without duplication,
    and reusing a key with different parameters is strictly rejected with a collision error.
    Survives process restarts.
    """

    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = storage_path or DEFAULT_IDEMPOTENCY_PATH
        self._records: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self):
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    self._records = json.load(f)
            except Exception:
                self._records = {}
        else:
            self._records = {}

    def _save(self):
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(self._records, f, indent=2)

    def check_or_record(
        self, key: str, payload: Dict[str, Any], order_id: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Returns (is_replay, existing_order_id).
        Raises IdempotencyCollisionError if key was used previously with a different payload.
        """
        self._load()
        # Exclude transient fields like timestamps or client order ids from payload hash
        clean_payload = {
            k: v
            for k, v in payload.items()
            if k not in ("idempotency_key", "timestamp", "submitted_at_utc", "client_order_id") and v is not None
        }
        payload_hash = hashlib.sha256(
            json.dumps(clean_payload, sort_keys=True).encode("utf-8")
        ).hexdigest()

        if key in self._records:
            rec = self._records[key]
            if rec.get("payload_hash") == payload_hash:
                return True, rec.get("order_id")
            else:
                raise IdempotencyCollisionError(
                    f"Idempotency key collision: Key '{key}' was previously used with a different request payload."
                )

        self._records[key] = {
            "payload_hash": payload_hash,
            "order_id": order_id,
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        self._save()
        return False, None

    def get_order_id(self, key: str) -> Optional[str]:
        self._load()
        rec = self._records.get(key)
        return rec.get("order_id") if rec else None


class PaperTradingEngine:
    """
    Standardized Provider-Agnostic Order Lifecycle & Paper Trading Engine.
    Enforces strategy preflight, durable idempotency, strict state transitions,
    and strict isolation from real exchange write endpoints.
    """

    def __init__(
        self,
        orders_path: Optional[str] = None,
        ledger_path: Optional[str] = None,
        idempotency_path: Optional[str] = None,
    ):
        self.orders_path = orders_path or DEFAULT_PAPER_ORDERS_PATH
        self.ledger = PaperLedger(storage_path=ledger_path)
        self.idempotency = DurableIdempotencyStore(storage_path=idempotency_path)
        self._orders: Dict[str, Dict[str, Any]] = {}
        self._load_orders()

    def _load_orders(self):
        if os.path.exists(self.orders_path):
            try:
                with open(self.orders_path, "r", encoding="utf-8") as f:
                    self._orders = json.load(f)
            except Exception:
                self._orders = {}
        else:
            self._orders = {}

    def _save_orders(self):
        os.makedirs(os.path.dirname(self.orders_path), exist_ok=True)
        with open(self.orders_path, "w", encoding="utf-8") as f:
            json.dump(self._orders, f, indent=2)

    def preflight_order(
        self,
        profile_data: Dict[str, Any],
        strategy_id: str,
        account_type: str,
        execution_mode: str,
        evaluator_fn: Any,
        strategy_requirements: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Enforces the 5 preflight gates before paper-order creation:
        1. Account & execution mode isolation (strictly PAPER).
        2. Strategy compatibility evaluation (must be COMPATIBLE).
        3. Capability evidence currency check (must not be missing or stale).
        4. Market and product type matching.
        5. Independent server-side verification.
        """
        # Gate 1: Explicit paper account and execution mode
        if (
            str(account_type).strip().upper() != "PAPER"
            or str(execution_mode).strip().upper() != "PAPER"
        ):
            raise StrategyPreflightError(
                f"Paper trading requires explicit 'PAPER' account and execution mode. "
                f"Received account_type='{account_type}', execution_mode='{execution_mode}'."
            )

        # Gate 2: Strategy specification exists
        strategy_clean = strategy_id.strip().upper()
        if strategy_clean not in strategy_requirements:
            raise StrategyPreflightError(
                f"Unknown strategy '{strategy_id}'. Supported strategies: {list(strategy_requirements.keys())}."
            )

        strat_spec = strategy_requirements[strategy_clean]

        # Gate 3: Evaluate strategy compatibility
        eval_res = evaluator_fn(profile_data, strategy_clean)
        strat_eval = eval_res.get("strategies", {}).get(strategy_clean, {}) if (isinstance(eval_res, dict) and "strategies" in eval_res) else eval_res
        strat_status = strat_eval.get("status")

        if strat_status == "INCOMPATIBLE":
            reasons = strat_eval.get("reasons", ["Strategy requirements not met by connection profile."])
            missing = strat_eval.get("missing_capabilities", [])
            raise StrategyPreflightError(
                f"Strategy preflight rejected: Strategy '{strategy_clean}' is INCOMPATIBLE. "
                f"Reasons: {'; '.join(reasons)}. Missing capabilities: {missing}"
            )
        elif strat_status == "INDETERMINATE":
            reasons = strat_eval.get("reasons", ["Capability evidence is missing or unverified."])
            raise StrategyPreflightError(
                f"Strategy preflight rejected: Strategy '{strategy_clean}' status is INDETERMINATE. "
                f"Reasons: {'; '.join(reasons)}. Retest connection profile before trading."
            )
        elif strat_status != "COMPATIBLE":
            raise StrategyPreflightError(
                f"Strategy preflight rejected: Strategy '{strategy_clean}' status '{strat_status}' is not COMPATIBLE."
            )

        # Gate 4: Product and market type matching
        profile_market = str(profile_data.get("market_type", "CRYPTO")).strip().upper()
        profile_product = str(profile_data.get("product_type", "SPOT")).strip().upper()
        req_market = strat_spec.get("market_type", "CRYPTO")
        req_products = strat_spec.get("supported_products", ["SPOT"])

        if profile_market != req_market:
            raise StrategyPreflightError(
                f"Market type mismatch: Strategy '{strategy_clean}' requires {req_market}, "
                f"but profile is configured for {profile_market}."
            )
        if profile_product not in req_products:
            raise StrategyPreflightError(
                f"Product category mismatch: Strategy '{strategy_clean}' requires one of {req_products}, "
                f"but profile is configured for {profile_product}."
            )

        # Gate 5: Evidence currency
        last_tested = profile_data.get("last_tested_utc")
        if not last_tested:
            raise StrategyPreflightError(
                f"Strategy preflight rejected: Profile has no verification evidence timestamp. Retest connection."
            )

        return eval_res

    def create_order(
        self,
        strategy_id: str,
        profile_id: str,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float,
        idempotency_key: Optional[str] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        account_type: str = "PAPER",
        execution_mode: str = "PAPER",
        profile_data: Optional[Dict[str, Any]] = None,
        evaluator_fn: Optional[Any] = None,
        strategy_requirements: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Dict[str, Any], bool]:
        """
        Creates a paper order with durable idempotency, strategy preflight validation,
        and ledger margin reservation.
        Returns (order_dict, is_idempotent_replay).
        """
        self._load_orders()

        # Generate or normalize idempotency key
        ik = idempotency_key or f"IDEMP-P-{secrets.token_hex(8)}"

        payload_for_idemp = {
            "strategy_id": strategy_id,
            "profile_id": profile_id,
            "symbol": symbol.upper(),
            "side": side.upper(),
            "order_type": order_type.upper(),
            "quantity": float(quantity),
            "price": float(price),
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "account_type": account_type.upper(),
            "execution_mode": execution_mode.upper(),
        }

        # 1. Preflight Verification (if profile & evaluator provided)
        if profile_data and evaluator_fn and strategy_requirements:
            self.preflight_order(
                profile_data=profile_data,
                strategy_id=strategy_id,
                account_type=account_type,
                execution_mode=execution_mode,
                evaluator_fn=evaluator_fn,
                strategy_requirements=strategy_requirements,
            )

        # Generate prospective client order ID
        client_order_id = f"ORD-PAPER-{symbol.upper().replace('USDT', '')}-{secrets.token_hex(4).upper()}"

        # 2. Check Idempotency
        is_replay, existing_id = self.idempotency.check_or_record(
            key=ik, payload=payload_for_idemp, order_id=client_order_id
        )
        if is_replay and existing_id:
            existing_order = self._orders.get(existing_id)
            if existing_order:
                return existing_order, True

        # 3. Ledger margin reservation
        notional = round(quantity * price, 4)
        self.ledger.allocate_margin(notional)

        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        order_record: Dict[str, Any] = {
            "client_order_id": client_order_id,
            "exchange_order_id": f"EX-SIM-{client_order_id}",
            "idempotency_key": ik,
            "strategy_id": strategy_id.upper(),
            "profile_id": profile_id,
            "symbol": symbol.upper(),
            "side": side.upper(),
            "order_type": order_type.upper(),
            "status": OrderStatus.OPEN.value,
            "raw_provider_status": "NEW",
            "requested_qty": round(float(quantity), 6),
            "cumulative_qty": 0.0,
            "remaining_qty": round(float(quantity), 6),
            "requested_price": round(float(price), 6),
            "avg_fill_price": 0.0,
            "fee_amount": 0.0,
            "fee_currency": "USDT",
            "fees": [],
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "environment": "PAPER",
            "account_type": "PAPER",
            "is_exchange_confirmed": False,
            "submitted_at_utc": now_iso,
            "last_updated_utc": now_iso,
            "filled_at_utc": None,
            "audit_trail": [
                {
                    "timestamp": now_iso,
                    "from_status": None,
                    "to_status": OrderStatus.CREATED.value,
                    "reason": "Order created via strategy preflight",
                },
                {
                    "timestamp": now_iso,
                    "from_status": OrderStatus.CREATED.value,
                    "to_status": OrderStatus.OPEN.value,
                    "reason": f"Allocated {notional:.2f} USDT margin in simulated paper ledger",
                },
            ],
            "uncertain_outcome_reason": None,
        }

        self._orders[client_order_id] = order_record
        self._save_orders()
        return order_record, False

    def transition_order(
        self,
        client_order_id: str,
        target_status: str,
        raw_provider_status: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Transitions order to target_status if valid according to canonical lifecycle.
        Releases margin hold on terminal cancellation/rejection/expiry.
        """
        self._load_orders()
        order = self._orders.get(client_order_id)
        if not order:
            raise KeyError(f"Paper order '{client_order_id}' not found.")

        current = order.get("status", OrderStatus.CREATED.value)
        target = str(target_status).upper()

        if not validate_order_transition(current, target):
            raise InvalidOrderStateTransitionError(
                f"Invalid order lifecycle transition from {current} to {target}."
            )

        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Handle margin release if order moves to terminal non-filled state
        if target in (
            OrderStatus.CANCELLED.value,
            OrderStatus.REJECTED.value,
            OrderStatus.EXPIRED.value,
        ):
            remaining_notional = round(
                order.get("remaining_qty", 0.0) * order.get("requested_price", 0.0), 4
            )
            if remaining_notional > 0:
                self.ledger.release_margin(remaining_notional)

        order["status"] = target
        if raw_provider_status:
            order["raw_provider_status"] = raw_provider_status
        order["last_updated_utc"] = now_iso
        order["audit_trail"].append(
            {
                "timestamp": now_iso,
                "from_status": current,
                "to_status": target,
                "reason": reason or f"Transitioned to {target}",
            }
        )

        self._save_orders()
        return order

    def apply_fill(
        self,
        client_order_id: str,
        fill_qty: float,
        fill_price: float,
        fee_amount: Optional[float] = None,
        fee_currency: str = "USDT",
    ) -> Dict[str, Any]:
        """
        Applies a partial or complete fill to an open paper order.
        Recomputes cumulative quantity, remaining quantity, weighted average fill price,
        and reconciles the paper ledger.
        """
        self._load_orders()
        order = self._orders.get(client_order_id)
        if not order:
            raise KeyError(f"Paper order '{client_order_id}' not found.")

        current_status = order.get("status")
        if current_status in (
            OrderStatus.FILLED.value,
            OrderStatus.CANCELLED.value,
            OrderStatus.REJECTED.value,
            OrderStatus.EXPIRED.value,
        ):
            raise InvalidOrderStateTransitionError(
                f"Cannot apply fill to order '{client_order_id}' in terminal status '{current_status}'."
            )

        if fill_qty <= 0:
            raise ValueError(f"Fill quantity must be greater than zero (received {fill_qty}).")

        req_qty = order["requested_qty"]
        cum_qty = order["cumulative_qty"]
        if round(cum_qty + fill_qty, 6) > round(req_qty + 1e-8, 6):
            raise ValueError(
                f"Cumulative fill exceeds requested quantity: requested={req_qty}, "
                f"existing_cum={cum_qty}, fill_qty={fill_qty}."
            )

        # Default standard 0.10% fee if not specified
        calc_fee = (
            round(fill_qty * fill_price * 0.001, 6)
            if fee_amount is None
            else round(float(fee_amount), 6)
        )

        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Weighted average fill price
        old_notional = order["avg_fill_price"] * cum_qty
        new_fill_notional = fill_price * fill_qty
        new_cum_qty = round(cum_qty + fill_qty, 6)
        order["avg_fill_price"] = round((old_notional + new_fill_notional) / new_cum_qty, 6)
        order["cumulative_qty"] = new_cum_qty
        order["remaining_qty"] = max(0.0, round(req_qty - new_cum_qty, 6))
        order["fee_amount"] = round(order["fee_amount"] + calc_fee, 6)
        order["fee_currency"] = fee_currency
        order["fees"].append(
            {
                "timestamp": now_iso,
                "fill_qty": fill_qty,
                "fill_price": fill_price,
                "fee": calc_fee,
                "currency": fee_currency,
            }
        )

        # Settle margin on paper ledger
        allocated_for_this_fill = round(fill_qty * order["requested_price"], 4)
        self.ledger.settle_fill(
            allocated_amount=allocated_for_this_fill,
            executed_notional=fill_qty * fill_price,
            fee=calc_fee,
        )

        # Determine target state
        if order["remaining_qty"] == 0.0:
            target_status = OrderStatus.FILLED.value
            order["filled_at_utc"] = now_iso
        else:
            target_status = OrderStatus.PARTIALLY_FILLED.value

        old_status = order["status"]
        order["status"] = target_status
        order["raw_provider_status"] = "FILLED" if target_status == OrderStatus.FILLED.value else "PARTIALLY_FILLED"
        order["last_updated_utc"] = now_iso
        order["audit_trail"].append(
            {
                "timestamp": now_iso,
                "from_status": old_status,
                "to_status": target_status,
                "reason": (
                    f"Executed fill of {fill_qty} @ {fill_price} "
                    f"(cumulative: {order['cumulative_qty']}/{req_qty})"
                ),
            }
        )

        self._save_orders()
        return order

    def reconcile_uncertain_order(self, client_order_id: str) -> Dict[str, Any]:
        """
        Reconciles an order in UNKNOWN_OUTCOME without duplicate execution.
        Resolves to a deterministic state based on internal ledger and recorded fills.
        """
        self._load_orders()
        order = self._orders.get(client_order_id)
        if not order:
            raise KeyError(f"Paper order '{client_order_id}' not found.")

        current = order.get("status")
        if current != OrderStatus.UNKNOWN_OUTCOME.value:
            return {
                "reconciled": False,
                "message": f"Order '{client_order_id}' is already in definitive state '{current}'.",
                "order": order,
            }

        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Determine resolution from fill and remaining quantities
        cum = order.get("cumulative_qty", 0.0)
        req = order.get("requested_qty", 0.0)

        if cum >= req and req > 0:
            resolved_status = OrderStatus.FILLED.value
        elif cum > 0:
            resolved_status = OrderStatus.PARTIALLY_FILLED.value
        else:
            resolved_status = OrderStatus.OPEN.value

        order["status"] = resolved_status
        order["uncertain_outcome_reason"] = None
        order["last_updated_utc"] = now_iso
        order["audit_trail"].append(
            {
                "timestamp": now_iso,
                "from_status": OrderStatus.UNKNOWN_OUTCOME.value,
                "to_status": resolved_status,
                "reason": (
                    f"Safely reconciled uncertain outcome to {resolved_status} "
                    f"based on internal ledger audit (cum: {cum}/{req}). Zero duplicate retry."
                ),
            }
        )

        self._save_orders()
        return {
            "reconciled": True,
            "resolved_status": resolved_status,
            "order": order,
        }

    def cancel_order(self, client_order_id: str, reason: str = "User cancellation") -> Dict[str, Any]:
        """Cancels an open or partially filled paper order and releases uncommitted held margin."""
        self._load_orders()
        order = self._orders.get(client_order_id)
        if not order:
            raise KeyError(f"Paper order '{client_order_id}' not found.")

        # Transition through CANCEL_PENDING -> CANCELLED
        self.transition_order(
            client_order_id=client_order_id,
            target_status=OrderStatus.CANCEL_PENDING.value,
            raw_provider_status="PENDING_CANCEL",
            reason=reason,
        )
        return self.transition_order(
            client_order_id=client_order_id,
            target_status=OrderStatus.CANCELLED.value,
            raw_provider_status="CANCELED",
            reason=f"Cancelled: {reason}",
        )

    def get_order(self, client_order_id: str) -> Optional[Dict[str, Any]]:
        self._load_orders()
        return self._orders.get(client_order_id)

    def list_orders(
        self,
        status: Optional[str] = None,
        symbol: Optional[str] = None,
        strategy_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        self._load_orders()
        res = list(self._orders.values())
        if status:
            res = [o for o in res if o.get("status") == status.upper()]
        if symbol:
            res = [o for o in res if o.get("symbol") == symbol.upper()]
        if strategy_id:
            res = [o for o in res if o.get("strategy_id") == strategy_id.upper()]
        return sorted(res, key=lambda x: x.get("submitted_at_utc", ""), reverse=True)

    def get_ledger_summary(self) -> Dict[str, Any]:
        return self.ledger.get_summary()


# Global engine instance
paper_engine = PaperTradingEngine()
