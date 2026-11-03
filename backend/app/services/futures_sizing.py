"""
BITDEX Dynamic Futures Position Sizing & Leverage Engine
=========================================================
Calculates risk-bounded position size and leverage for the SCALP_ONE_DOLLAR strategy:
- Respects dynamic ATR and symbol filters (stepSize, tickSize, minNotional).
- Enforces 2.0% equity dollar-risk ceiling.
- Enforces $5,000 aggregate exposure cap.
- Caps leverage strictly between 1x and 10x.
- Rejects proposed sizing if economics cannot achieve $1.00 net profit safely.
"""

import math
import logging
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger("bitdex.futures.sizing")


class FuturesSizingEngine:
    """Calculates position size, leverage, and margin requirements."""

    MAX_LEVERAGE_CAP = 10
    MAX_EQUITY_RISK_RATIO = 0.02       # 2% equity risk cap
    MAX_AGGREGATE_NOTIONAL_USD = 5000.0 # $5,000 max exposure limit
    COMMISSION_ROUND_TRIP = 0.0008     # 0.08% round-trip taker fees

    @classmethod
    def calculate_scalp_sizing(
        cls,
        symbol: str,
        price: float,
        atr: float,
        stop_price: float,
        available_balance: float,
        equity: float,
        symbol_filters: Dict[str, Any],
        target_net_usd: float = 1.00,
        slippage_buffer_usd: float = 0.05,
        order_type: str = "MARKET",
        maker_fee: bool = False,
    ) -> Dict[str, Any]:
        """
        Solves for position size and dynamic leverage:
        1. Evaluates required price move to achieve $1 net
        2. Clamps to step_size precision
        3. Enforces 2% dollar risk, $5k exposure, and available margin
        """
        min_qty = float(symbol_filters.get("min_qty", 0.001))
        max_qty = float(symbol_filters.get("max_qty", 1000.0))
        step_size = float(symbol_filters.get("step_size", 0.001))
        min_notional = float(symbol_filters.get("min_notional", 5.0))

        # 1. Stop distance and dynamic leverage
        stop_dist = abs(price - stop_price)
        stop_dist_ratio = stop_dist / price if price > 0 else 0.01

        # Dynamic leverage capped at 10x: tighter stops allow higher leverage within cap
        if stop_dist_ratio <= 0.005:  # <= 0.5% stop
            selected_leverage = 10
        elif stop_dist_ratio <= 0.010:  # <= 1.0% stop
            selected_leverage = 7
        elif stop_dist_ratio <= 0.020:  # <= 2.0% stop
            selected_leverage = 5
        else:
            selected_leverage = 3
        selected_leverage = min(cls.MAX_LEVERAGE_CAP, max(1, selected_leverage))

        # 2. Expected favorable price movement during a 5m scalp (~0.6x ATR)
        expected_move = max(price * 0.0015, atr * 0.6)  # at least 15 bps or 0.6 ATR

        is_maker = maker_fee or (order_type.upper() in ("POST_ONLY", "LIMIT_MAKER"))
        active_commission_rate = 0.0006 if is_maker else cls.COMMISSION_ROUND_TRIP

        # Required profit: Net PnL = qty * (expected_move - active_commission_rate * price) - slippage = $1.00
        effective_gain_per_unit = expected_move - (active_commission_rate * price)
        if effective_gain_per_unit <= 0.0:
            return {
                "feasible": False,
                "rejection_reason": "VOLATILITY_TOO_LOW_TO_OVERCOME_COMMISSION_FRICTION",
                "quantity": 0.0,
                "leverage": selected_leverage
            }

        target_total_profit = target_net_usd + slippage_buffer_usd
        raw_qty = target_total_profit / effective_gain_per_unit

        # 3. Precision clamping to step_size
        if step_size > 0:
            decimals = max(0, int(round(-math.log10(step_size))))
            clamped_qty = math.floor(raw_qty / step_size) * step_size
            clamped_qty = round(clamped_qty, decimals)
        else:
            clamped_qty = raw_qty

        # Ensure at least min_qty
        if clamped_qty < min_qty:
            clamped_qty = min_qty

        # Check min_notional
        notional = clamped_qty * price
        if notional < min_notional:
            # Scale up to min_notional + 10%
            needed_qty = (min_notional * 1.10) / price
            decimals = max(0, int(round(-math.log10(step_size)))) if step_size > 0 else 4
            clamped_qty = round(math.ceil(needed_qty / step_size) * step_size, decimals)
            notional = clamped_qty * price

        # 4. Risk constraints checks
        # A. Dollar risk check (max 2% equity)
        dollar_risk = stop_dist * clamped_qty
        max_allowed_risk = equity * cls.MAX_EQUITY_RISK_RATIO
        if dollar_risk > max_allowed_risk:
            # Scale down quantity to fit max allowed risk
            reduced_qty = max_allowed_risk / stop_dist
            if step_size > 0:
                decimals = max(0, int(round(-math.log10(step_size))))
                clamped_qty = round(math.floor(reduced_qty / step_size) * step_size, decimals)
            else:
                clamped_qty = reduced_qty
            notional = clamped_qty * price
            dollar_risk = stop_dist * clamped_qty

            if notional < min_notional:
                return {
                    "feasible": False,
                    "rejection_reason": f"REJECTED_MIN_NOTIONAL_EXCEEDS_RISK_CAP: Dollar risk (${dollar_risk:.2f}) required for min notional exceeds 2% equity risk ceiling (${max_allowed_risk:.2f}) [DOLLAR_RISK_CAP_CONFLICT_WITH_MIN_NOTIONAL]",
                    "quantity": 0.0,
                    "leverage": selected_leverage
                }

        # B. Aggregate exposure check (max $5,000)
        if notional > cls.MAX_AGGREGATE_NOTIONAL_USD:
            max_qty_for_exposure = cls.MAX_AGGREGATE_NOTIONAL_USD / price
            if step_size > 0:
                decimals = max(0, int(round(-math.log10(step_size))))
                clamped_qty = round(math.floor(max_qty_for_exposure / step_size) * step_size, decimals)
            else:
                clamped_qty = max_qty_for_exposure
            notional = clamped_qty * price

        # C. Margin check
        margin_required = notional / selected_leverage
        if margin_required > available_balance:
            return {
                "feasible": False,
                "rejection_reason": f"INSUFFICIENT_MARGIN_FOR_SCALP (Required ${margin_required:.2f} > Available ${available_balance:.2f})",
                "quantity": 0.0,
                "leverage": selected_leverage
            }

        # D. Verify final estimated economics with clamped quantity
        est_gross = clamped_qty * expected_move
        est_fees = notional * cls.COMMISSION_ROUND_TRIP
        est_net = est_gross - est_fees - slippage_buffer_usd
        if est_net < (target_net_usd * 0.70):  # Must achieve at least 70% of target under conservative move
            return {
                "feasible": False,
                "rejection_reason": f"NET_PROFIT_BELOW_THRESHOLD_AFTER_CLAMPING (Est Net: ${est_net:.2f})",
                "quantity": 0.0,
                "leverage": selected_leverage
            }

        return {
            "feasible": True,
            "quantity": clamped_qty,
            "notional": round(notional, 2),
            "leverage": selected_leverage,
            "margin_required": round(margin_required, 2),
            "dollar_risk": round(dollar_risk, 2),
            "max_allowed_risk": round(max_allowed_risk, 2),
            "expected_move_usd": round(expected_move, 4),
            "estimated_gross_usd": round(est_gross, 4),
            "estimated_fees_usd": round(est_fees, 4),
            "estimated_net_usd": round(est_net, 4),
        }
