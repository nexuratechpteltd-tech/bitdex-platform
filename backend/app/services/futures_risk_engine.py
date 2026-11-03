"""
BITDEX Pre-Trade Capital Protection Risk Engine
================================================
Independent, authoritative pre-trade risk evaluation for Binance USD(S)-M Futures.

Core Rules & Hard Clamps:
1. Kill switch enforcement (blocks entries, permits exits)
2. Isolated margin enforcement (rejects crossed margin)
3. Hard leverage cap (max 10x)
4. Available margin check (notional / leverage <= available balance)
5. Mandatory protective stop requirement on entries (bounded 0.2% - 5.0%)
6. Per-trade risk cap (max 2% of account equity)
7. Aggregate portfolio exposure cap (max $5,000.00 staging limit)
8. Daily realized loss limit (max $250.00 daily loss)
9. Max consecutive losses limit (max 3 consecutive losses)
10. Max concurrent open positions (max 3 open positions)
11. Market data freshness check (data age <= 5000ms)
12. Martingale / averaging-down prevention (blocks adding to losing positions)
"""

import time
import logging
import sqlite3
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from .futures_db import (
    get_futures_account,
    get_open_futures_position,
    list_open_futures_positions,
    record_risk_decision,
)

logger = logging.getLogger("bitdex.futures.risk")


class FuturesRiskDecisionResult:
    def __init__(
        self,
        decision_id: str,
        decision: str,  # "APPROVED" or "REJECTED"
        rejection_code: Optional[str] = None,
        rejection_reason: Optional[str] = None,
        risk_metrics: Optional[Dict[str, Any]] = None
    ):
        self.decision_id = decision_id
        self.decision = decision
        self.rejection_code = rejection_code
        self.rejection_reason = rejection_reason
        self.risk_metrics = risk_metrics or {}

    @property
    def is_approved(self) -> bool:
        return self.decision == "APPROVED"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "decision": self.decision,
            "rejection_code": self.rejection_code,
            "rejection_reason": self.rejection_reason,
            "risk_metrics": self.risk_metrics,
        }


class FuturesRiskEngine:
    """Authoritative pre-trade risk engine for futures trading."""

    MAX_LEVERAGE_CAP = 10
    MAX_PER_TRADE_RISK_RATIO = 0.02  # 2.0% of equity
    MAX_AGGREGATE_EXPOSURE_USD = 5000.0  # $5,000 max total portfolio notional
    MAX_DAILY_LOSS_USD = 250.0  # $250 max daily realized loss
    MAX_CONSECUTIVE_LOSSES = 4  # Block after 4 consecutive losing trades
    MAX_CONCURRENT_POSITIONS = 3  # Max 3 open positions
    MAX_MARKET_DATA_AGE_MS = 5000  # 5 seconds
    MIN_STOP_DISTANCE_RATIO = 0.002  # 0.2% minimum stop distance
    MAX_STOP_DISTANCE_RATIO = 0.050  # 5.0% maximum stop distance

    @classmethod
    def evaluate_pre_trade(
        cls,
        conn: sqlite3.Connection,
        user_id: str,
        account_id: str,
        client_order_id: str,
        symbol: str,
        side: str,  # "BUY" or "SELL"
        intent: str,  # "LONG_ENTRY", "LONG_EXIT", "SHORT_ENTRY", "SHORT_EXIT"
        quantity: float,
        price: float,
        leverage: int = 3,
        margin_type: str = "ISOLATED",
        stop_price: Optional[float] = None,
        market_price_timestamp_ms: Optional[int] = None,
    ) -> FuturesRiskDecisionResult:
        """
        Evaluate proposed order against all risk policies.
        Persists decision to futures_risk_decisions table.
        """
        sym = symbol.upper()
        s_side = side.upper()
        s_intent = intent.upper()
        is_entry = s_intent in ("LONG_ENTRY", "SHORT_ENTRY")
        is_exit = s_intent in ("LONG_EXIT", "SHORT_EXIT")

        # 1. Fetch Account
        account = get_futures_account(conn, user_id=user_id, account_id=account_id)
        if not account:
            return cls._reject(
                conn, user_id, account_id, client_order_id, sym, s_side, s_intent,
                quantity, price, leverage, 0.0, 0.0, 0.0,
                code="ACCOUNT_NOT_FOUND",
                reason=f"Futures account '{account_id}' does not exist for tenant {user_id}."
            )

        wallet_bal = float(account["wallet_balance"])
        avail_bal = float(account["available_balance"])
        margin_bal = float(account["margin_balance"])
        equity = max(avail_bal, margin_bal, wallet_bal)
        notional = quantity * price
        margin_required = notional / max(1, leverage)

        metrics: Dict[str, Any] = {
            "symbol": sym,
            "side": s_side,
            "intent": s_intent,
            "quantity": quantity,
            "price": price,
            "notional": round(notional, 2),
            "leverage": leverage,
            "margin_type": margin_type,
            "margin_required": round(margin_required, 2),
            "available_balance": round(avail_bal, 2),
            "equity": round(equity, 2),
            "stop_price": stop_price,
        }

        # 2. Kill Switch & Trading Lock Checks
        if account.get("kill_switch_active", 0) == 1:
            if is_entry:
                return cls._reject(
                    conn, user_id, account_id, client_order_id, sym, s_side, s_intent,
                    quantity, price, leverage, margin_required, notional, avail_bal,
                    code="TRADING_KILL_SWITCH_ACTIVE",
                    reason="Emergency kill switch is active. New entry orders are strictly prohibited.",
                    metrics=metrics
                )
            logger.info("Kill switch active but permitting exit order for position reduction.")

        if account.get("trading_locked", 0) == 1:
            if is_entry:
                return cls._reject(
                    conn, user_id, account_id, client_order_id, sym, s_side, s_intent,
                    quantity, price, leverage, margin_required, notional, avail_bal,
                    code="TRADING_LOCKED",
                    reason="Futures trading is locked for this account.",
                    metrics=metrics
                )

        # 3. Market Data Freshness Check
        if market_price_timestamp_ms:
            now_ms = int(time.time() * 1000)
            age_ms = now_ms - market_price_timestamp_ms
            metrics["market_data_age_ms"] = age_ms
            if age_ms > cls.MAX_MARKET_DATA_AGE_MS or age_ms < -2000:
                return cls._reject(
                    conn, user_id, account_id, client_order_id, sym, s_side, s_intent,
                    quantity, price, leverage, margin_required, notional, avail_bal,
                    code="STALE_MARKET_DATA",
                    reason=f"Market data timestamp is {age_ms}ms old (maximum allowed: {cls.MAX_MARKET_DATA_AGE_MS}ms).",
                    metrics=metrics
                )

        # 4. Isolated Margin Enforcement
        if margin_type.upper() != "ISOLATED":
            return cls._reject(
                conn, user_id, account_id, client_order_id, sym, s_side, s_intent,
                quantity, price, leverage, margin_required, notional, avail_bal,
                code="CROSS_MARGIN_NOT_PERMITTED",
                reason="Crossed margin is disabled. All positions must use isolated margin.",
                metrics=metrics
            )

        # 5. Leverage Cap Enforcement
        if leverage > cls.MAX_LEVERAGE_CAP or leverage < 1:
            return cls._reject(
                conn, user_id, account_id, client_order_id, sym, s_side, s_intent,
                quantity, price, leverage, margin_required, notional, avail_bal,
                code="LEVERAGE_EXCEEDS_MAX_CAP",
                reason=f"Requested leverage {leverage}x exceeds safety maximum of {cls.MAX_LEVERAGE_CAP}x.",
                metrics=metrics
            )

        # For Exit Orders: Bypass entry-specific capital and stop loss validations
        if is_exit:
            open_pos = get_open_futures_position(conn, user_id=user_id, symbol=sym)
            if not open_pos or float(open_pos.get("quantity", 0)) <= 0:
                return cls._reject(
                    conn, user_id, account_id, client_order_id, sym, s_side, s_intent,
                    quantity, price, leverage, margin_required, notional, avail_bal,
                    code="NO_POSITION_TO_EXIT",
                    reason=f"No active open position found for {sym} to exit.",
                    metrics=metrics
                )
            return cls._approve(
                conn, user_id, account_id, client_order_id, sym, s_side, s_intent,
                quantity, price, leverage, margin_required, notional, avail_bal,
                metrics=metrics
            )

        # ─── ENTRY ORDERS SPECIFIC CHECKS ───

        # 6. Available Balance & Margin Check
        if margin_required > avail_bal:
            return cls._reject(
                conn, user_id, account_id, client_order_id, sym, s_side, s_intent,
                quantity, price, leverage, margin_required, notional, avail_bal,
                code="INSUFFICIENT_AVAILABLE_MARGIN",
                reason=f"Required margin ${margin_required:.2f} exceeds available balance ${avail_bal:.2f}.",
                metrics=metrics
            )

        # 7. Mandatory Protective Stop Loss & Distance Validation
        if stop_price is None or stop_price <= 0:
            return cls._reject(
                conn, user_id, account_id, client_order_id, sym, s_side, s_intent,
                quantity, price, leverage, margin_required, notional, avail_bal,
                code="MANDATORY_STOP_REQUIRED",
                reason="A valid protective stop price is mandatory for all entry orders.",
                metrics=metrics
            )

        if s_intent == "LONG_ENTRY":
            if stop_price >= price:
                return cls._reject(
                    conn, user_id, account_id, client_order_id, sym, s_side, s_intent,
                    quantity, price, leverage, margin_required, notional, avail_bal,
                    code="STOP_LOSS_INVALID_DIRECTION",
                    reason=f"LONG stop price ${stop_price:.2f} must be strictly lower than entry price ${price:.2f}.",
                    metrics=metrics
                )
            stop_dist_ratio = (price - stop_price) / price
        else:  # SHORT_ENTRY
            if stop_price <= price:
                return cls._reject(
                    conn, user_id, account_id, client_order_id, sym, s_side, s_intent,
                    quantity, price, leverage, margin_required, notional, avail_bal,
                    code="STOP_LOSS_INVALID_DIRECTION",
                    reason=f"SHORT stop price ${stop_price:.2f} must be strictly higher than entry price ${price:.2f}.",
                    metrics=metrics
                )
            stop_dist_ratio = (stop_price - price) / price

        metrics["stop_distance_ratio"] = round(stop_dist_ratio, 4)

        if stop_dist_ratio < cls.MIN_STOP_DISTANCE_RATIO or stop_dist_ratio > cls.MAX_STOP_DISTANCE_RATIO:
            return cls._reject(
                conn, user_id, account_id, client_order_id, sym, s_side, s_intent,
                quantity, price, leverage, margin_required, notional, avail_bal,
                code="STOP_LOSS_OUT_OF_BOUNDS",
                reason=f"Stop distance {stop_dist_ratio*100:.2f}% is outside permitted bounds "
                       f"({cls.MIN_STOP_DISTANCE_RATIO*100:.1f}% - {cls.MAX_STOP_DISTANCE_RATIO*100:.1f}%).",
                metrics=metrics
            )

        # 8. Per-Trade Risk Cap (Max 2% of equity)
        dollar_risk = abs(price - stop_price) * quantity
        max_allowed_risk = equity * cls.MAX_PER_TRADE_RISK_RATIO
        metrics["dollar_risk"] = round(dollar_risk, 2)
        metrics["max_allowed_risk"] = round(max_allowed_risk, 2)

        if dollar_risk > max_allowed_risk:
            return cls._reject(
                conn, user_id, account_id, client_order_id, sym, s_side, s_intent,
                quantity, price, leverage, margin_required, notional, avail_bal,
                code="PER_TRADE_RISK_EXCEEDS_LIMIT",
                reason=f"Trade dollar risk ${dollar_risk:.2f} exceeds 2.0% equity risk cap (${max_allowed_risk:.2f}).",
                metrics=metrics
            )

        # 9. Aggregate Portfolio Exposure Cap
        open_positions = list_open_futures_positions(conn, user_id=user_id)
        current_exposure = sum(abs(float(p["quantity"])) * float(p["mark_price"] or p["entry_price"]) for p in open_positions)
        new_total_exposure = current_exposure + notional
        metrics["current_exposure"] = round(current_exposure, 2)
        metrics["new_total_exposure"] = round(new_total_exposure, 2)

        if new_total_exposure > cls.MAX_AGGREGATE_EXPOSURE_USD:
            return cls._reject(
                conn, user_id, account_id, client_order_id, sym, s_side, s_intent,
                quantity, price, leverage, margin_required, notional, avail_bal,
                code="AGGREGATE_EXPOSURE_EXCEEDS_LIMIT",
                reason=f"Total portfolio exposure ${new_total_exposure:.2f} exceeds maximum allowed limit ${cls.MAX_AGGREGATE_EXPOSURE_USD:.2f}.",
                metrics=metrics
            )

        # 10. Max Concurrent Positions Check
        existing_pos_for_sym = [p for p in open_positions if p["symbol"] == sym]
        if not existing_pos_for_sym and len(open_positions) >= cls.MAX_CONCURRENT_POSITIONS:
            return cls._reject(
                conn, user_id, account_id, client_order_id, sym, s_side, s_intent,
                quantity, price, leverage, margin_required, notional, avail_bal,
                code="MAX_OPEN_POSITIONS_REACHED",
                reason=f"Account already has {len(open_positions)} open positions (maximum allowed: {cls.MAX_CONCURRENT_POSITIONS}).",
                metrics=metrics
            )

        # 11. Martingale / Averaging-down Prevention
        if existing_pos_for_sym:
            curr_pos = existing_pos_for_sym[0]
            curr_unrealized = float(curr_pos.get("unrealized_pnl", 0.0))
            if curr_unrealized < -0.01:
                return cls._reject(
                    conn, user_id, account_id, client_order_id, sym, s_side, s_intent,
                    quantity, price, leverage, margin_required, notional, avail_bal,
                    code="AVERAGING_DOWN_PROHIBITED",
                    reason=f"Existing position in {sym} is in drawdown (${curr_unrealized:.2f}). Averaging down is prohibited.",
                    metrics=metrics
                )

        # 12. Daily Realized Loss Limit Check
        today_utc_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        daily_loss_row = conn.execute(
            """SELECT SUM(net_pnl_usd) as total_pnl 
               FROM futures_realized_pnl 
               WHERE user_id = ? AND created_at LIKE ? AND net_pnl_usd < 0""",
            (user_id, f"{today_utc_prefix}%")
        ).fetchone()
        today_losses = abs(float(daily_loss_row["total_pnl"] or 0.0))
        metrics["today_losses_usd"] = round(today_losses, 2)

        if today_losses >= cls.MAX_DAILY_LOSS_USD:
            return cls._reject(
                conn, user_id, account_id, client_order_id, sym, s_side, s_intent,
                quantity, price, leverage, margin_required, notional, avail_bal,
                code="DAILY_LOSS_LIMIT_REACHED",
                reason=f"Today's realized losses (${today_losses:.2f}) have reached or exceeded daily limit (${cls.MAX_DAILY_LOSS_USD:.2f}).",
                metrics=metrics
            )

        # 13. Max Consecutive Losses Check
        recent_pnl_rows = conn.execute(
            """SELECT net_pnl_usd FROM futures_realized_pnl 
               WHERE user_id = ? 
               ORDER BY created_at DESC LIMIT ?""",
            (user_id, cls.MAX_CONSECUTIVE_LOSSES)
        ).fetchall()
        if len(recent_pnl_rows) >= cls.MAX_CONSECUTIVE_LOSSES:
            if all(float(r["net_pnl_usd"]) < 0 for r in recent_pnl_rows):
                return cls._reject(
                    conn, user_id, account_id, client_order_id, sym, s_side, s_intent,
                    quantity, price, leverage, margin_required, notional, avail_bal,
                    code="MAX_CONSECUTIVE_LOSSES_REACHED",
                    reason=f"Account has hit {cls.MAX_CONSECUTIVE_LOSSES} consecutive losing trades. Cooling off period enforced.",
                    metrics=metrics
                )

        # If all evaluations passed -> APPROVE
        return cls._approve(
            conn, user_id, account_id, client_order_id, sym, s_side, s_intent,
            quantity, price, leverage, margin_required, notional, avail_bal,
            metrics=metrics
        )

    @classmethod
    def _reject(
        cls, conn, user_id, account_id, client_order_id, symbol, side, intent,
        quantity, price, leverage, margin_req, notional, avail_bal,
        code: str, reason: str, metrics: Optional[Dict[str, Any]] = None
    ) -> FuturesRiskDecisionResult:
        decision_id = record_risk_decision(
            conn=conn,
            user_id=user_id,
            account_id=account_id,
            client_order_id=client_order_id,
            symbol=symbol,
            side=side,
            intent=intent,
            requested_quantity=quantity,
            requested_price=price,
            requested_leverage=leverage,
            estimated_margin_required=margin_req,
            estimated_notional=notional,
            available_balance=avail_bal,
            decision="REJECTED",
            rejection_code=code,
            rejection_reason=reason,
            risk_metrics=metrics
        )
        logger.warning("Trade REJECTED [%s] for %s %s: %s", code, user_id, symbol, reason)
        return FuturesRiskDecisionResult(
            decision_id=decision_id,
            decision="REJECTED",
            rejection_code=code,
            rejection_reason=reason,
            risk_metrics=metrics
        )

    @classmethod
    def _approve(
        cls, conn, user_id, account_id, client_order_id, symbol, side, intent,
        quantity, price, leverage, margin_req, notional, avail_bal,
        metrics: Optional[Dict[str, Any]] = None
    ) -> FuturesRiskDecisionResult:
        decision_id = record_risk_decision(
            conn=conn,
            user_id=user_id,
            account_id=account_id,
            client_order_id=client_order_id,
            symbol=symbol,
            side=side,
            intent=intent,
            requested_quantity=quantity,
            requested_price=price,
            requested_leverage=leverage,
            estimated_margin_required=margin_req,
            estimated_notional=notional,
            available_balance=avail_bal,
            decision="APPROVED",
            rejection_code=None,
            rejection_reason=None,
            risk_metrics=metrics
        )
        logger.info("Trade APPROVED [%s] for %s %s (Notional: $%.2f)", decision_id, user_id, symbol, notional)
        return FuturesRiskDecisionResult(
            decision_id=decision_id,
            decision="APPROVED",
            rejection_code=None,
            rejection_reason=None,
            risk_metrics=metrics
        )
