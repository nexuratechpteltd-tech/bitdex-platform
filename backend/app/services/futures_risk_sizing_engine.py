"""
BITDEX Standalone Risk-First Position Sizing & Accounting Engine (R2 Specification).
Implements pure risk-budget-first position sizing, conservative leverage clamping (max 5x for Engine B),
strict minimum-notional conflict rejection (zero inflating), fee & funding drag accounting,
and partial-fill realized net P&L reconciliation.
"""

import math
import logging
from typing import Dict, Any, Optional, Tuple, List

logger = logging.getLogger("bitdex.futures.risk_sizing")


class FuturesRiskSizingEngine:
    """
    Standalone mathematical risk and sizing engine for BITDEX USD(S)-M Futures.
    Enforces risk-first sizing where risk budget dictates notional, never leverage.
    """

    MAX_ENGINE_B_LEVERAGE = 5          # Hard 5x leverage ceiling for Engine B
    DEFAULT_RISK_PER_TRADE = 0.01      # 1% equity risk default
    MAX_RISK_PER_TRADE = 0.02          # 2% equity risk hard cap
    MAKER_FEE_RATE = 0.0002            # 0.02% Binance Futures Maker Fee (VIP 0)
    TAKER_FEE_RATE = 0.0004            # 0.04% Binance Futures Taker Fee (VIP 0)
    DEFAULT_SLIPPAGE_RATE = 0.0005     # 0.05% baseline conservative slippage buffer

    @classmethod
    def calculate_risk_first_sizing(
        cls,
        equity: float,
        available_balance: float,
        entry_price: float,
        stop_price: float,
        symbol_filters: Dict[str, Any],
        risk_pct: float = DEFAULT_RISK_PER_TRADE,
        max_leverage: int = MAX_ENGINE_B_LEVERAGE,
        is_maker: bool = True,
        spread_pct: float = 0.0002,
        funding_rate: float = 0.0001,
        holding_hours_est: float = 0.1667,  # 10 minutes default holding time
    ) -> Dict[str, Any]:
        """
        Calculates position size and leverage from risk budget:
        1. Validates inputs & boundaries
        2. Computes dollar risk budget = equity * clamped_risk_pct
        3. Computes stop distance ratio = |entry - stop| / entry
        4. Calculates target notional = dollar_risk / (stop_distance + slippage)
        5. Clamps quantity to symbol step_size and validates min_qty
        6. REJECTS if resulting notional < exchange min_notional (PROHIBITS INFLATION)
        7. Enforces leverage clamp <= 5x and verifies margin requirement <= available_balance
        8. Returns full itemized fee, funding, and risk breakdown
        """
        # 1. Input Boundary Validations
        if equity <= 0.0:
            return {"approved": False, "rejection_code": "REJECTED_ZERO_OR_NEGATIVE_EQUITY", "rejection_reason": f"Account equity (${equity:.2f}) must be positive."}
        if available_balance <= 0.0:
            return {"approved": False, "rejection_code": "REJECTED_ZERO_AVAILABLE_BALANCE", "rejection_reason": f"Available balance (${available_balance:.2f}) must be positive."}
        if entry_price <= 0.0 or stop_price <= 0.0:
            return {"approved": False, "rejection_code": "REJECTED_INVALID_PRICE", "rejection_reason": "Entry and stop prices must be positive."}
        if math.isclose(entry_price, stop_price, rel_tol=1e-5):
            return {"approved": False, "rejection_code": "REJECTED_ZERO_STOP_DISTANCE", "rejection_reason": "Stop price cannot equal entry price."}

        # 2. Risk Budget Calculation
        clamped_risk_pct = min(cls.MAX_RISK_PER_TRADE, max(0.001, risk_pct))
        dollar_risk_budget = equity * clamped_risk_pct

        # 3. Stop Distance & Dynamic Slippage Allowance
        stop_dist_usd = abs(entry_price - stop_price)
        stop_dist_ratio = stop_dist_usd / entry_price
        if stop_dist_ratio < 0.001:  # < 0.1% stop is too tight for realistic futures spreads
            return {"approved": False, "rejection_code": "REJECTED_STOP_TOO_TIGHT", "rejection_reason": f"Stop distance ({stop_dist_ratio*100:.3f}%) is tighter than 0.10% spread minimum."}
        if stop_dist_ratio > 0.15:   # > 15% stop is excessive for high-frequency scalping
            return {"approved": False, "rejection_code": "REJECTED_STOP_TOO_WIDE", "rejection_reason": f"Stop distance ({stop_dist_ratio*100:.2f}%) exceeds 15% maximum risk horizon."}

        # Estimated slippage allowance scales with spread
        slippage_rate = max(cls.DEFAULT_SLIPPAGE_RATE, spread_pct * 0.5)
        total_risk_loss_ratio = stop_dist_ratio + slippage_rate

        # 4. Target Notional Based Strictly on Risk Budget
        target_notional = dollar_risk_budget / total_risk_loss_ratio

        # 5. Extract & Sanitize Exchange Symbol Filters
        min_qty = float(symbol_filters.get("min_qty", 0.001))
        max_qty = float(symbol_filters.get("max_qty", 10000.0))
        step_size = float(symbol_filters.get("step_size", 0.001))
        min_notional = float(symbol_filters.get("min_notional", 5.0))
        tick_size = float(symbol_filters.get("tick_size", 0.01))

        # Precision Clamping
        raw_qty = target_notional / entry_price
        if step_size > 0:
            decimals = max(0, int(round(-math.log10(step_size))))
            clamped_qty = math.floor(raw_qty / step_size) * step_size
            clamped_qty = round(clamped_qty, decimals)
        else:
            clamped_qty = raw_qty

        if clamped_qty > max_qty:
            clamped_qty = max_qty

        # 6. Exchange Filter Compliance & ZERO-INFLATION Rule
        actual_notional = clamped_qty * entry_price

        # Check if quantity < min_qty or actual_notional < min_notional
        if clamped_qty < min_qty or actual_notional < min_notional:
            # We strictly REJECT instead of artificially inflating the position!
            return {
                "approved": False,
                "rejection_code": "REJECTED_MIN_NOTIONAL_EXCEEDS_RISK_BUDGET",
                "rejection_reason": (
                    f"Target notional (${actual_notional:.2f}) required by risk budget (${dollar_risk_budget:.2f}) "
                    f"is below exchange minimum notional (${min_notional:.2f}). "
                    f"Inflating position size is strictly prohibited by risk policy."
                ),
                "calculated_notional": round(actual_notional, 2),
                "min_notional_required": min_notional,
                "dollar_risk_budget": round(dollar_risk_budget, 2)
            }

        # 7. Conservative Leverage Determination (Clamped <= 5x)
        clamped_leverage = min(cls.MAX_ENGINE_B_LEVERAGE, max(1, int(max_leverage)))
        margin_required = actual_notional / clamped_leverage

        if margin_required > available_balance:
            # Check if increasing leverage within 5x cap helps, else scale down or reject
            max_possible_notional = available_balance * clamped_leverage
            if max_possible_notional < min_notional:
                return {
                    "approved": False,
                    "rejection_code": "REJECTED_INSUFFICIENT_AVAILABLE_MARGIN",
                    "rejection_reason": f"Required margin ${margin_required:.2f} exceeds available balance ${available_balance:.2f}.",
                    "margin_required": round(margin_required, 2),
                    "available_balance": round(available_balance, 2)
                }
            # Scale down to fit available margin
            clamped_qty = math.floor((max_possible_notional / entry_price) / step_size) * step_size
            clamped_qty = round(clamped_qty, decimals if step_size > 0 else 4)
            actual_notional = clamped_qty * entry_price
            margin_required = actual_notional / clamped_leverage

        # 8. Fee, Funding & Expected Cost Deductions
        entry_fee_rate = cls.MAKER_FEE_RATE if is_maker else cls.TAKER_FEE_RATE
        exit_fee_rate = cls.TAKER_FEE_RATE  # Stops are executed as market taker
        est_entry_fee = actual_notional * entry_fee_rate
        est_exit_fee = actual_notional * exit_fee_rate
        est_total_commission = est_entry_fee + est_exit_fee

        # Funding rate cost = notional * rate * (holding_hours / 8h)
        est_funding_fee = actual_notional * abs(funding_rate) * (holding_hours_est / 8.0)
        est_slippage_usd = actual_notional * slippage_rate
        est_total_friction = est_total_commission + est_funding_fee + est_slippage_usd

        # Recalculate true worst-case dollar risk including fees & slippage
        actual_dollar_risk = (clamped_qty * stop_dist_usd) + est_total_friction

        return {
            "approved": True,
            "quantity": clamped_qty,
            "notional_usd": round(actual_notional, 2),
            "leverage": clamped_leverage,
            "margin_required_usd": round(margin_required, 2),
            "dollar_risk_budget_usd": round(dollar_risk_budget, 2),
            "actual_max_loss_usd": round(actual_dollar_risk, 2),
            "stop_distance_pct": round(stop_dist_ratio * 100, 3),
            "fee_breakdown": {
                "is_maker_entry": is_maker,
                "entry_fee_usd": round(est_entry_fee, 4),
                "exit_fee_usd": round(est_exit_fee, 4),
                "total_commission_usd": round(est_total_commission, 4),
                "est_funding_fee_usd": round(est_funding_fee, 4),
                "est_slippage_usd": round(est_slippage_usd, 4),
                "total_friction_usd": round(est_total_friction, 4)
            }
        }

    @classmethod
    def calculate_realized_net_pnl(
        cls,
        side: str,              # 'BUY' (LONG) or 'SELL' (SHORT)
        entry_fills: List[Dict[str, float]],  # List of {'price': float, 'qty': float, 'fee': float}
        exit_fills: List[Dict[str, float]],   # List of {'price': float, 'qty': float, 'fee': float}
        funding_fees_paid: float = 0.0
    ) -> Dict[str, Any]:
        """
        Computes exact realized net P&L from actual fill executions,
        properly accounting for partial fills, maker/taker commissions, and funding.
        """
        total_entry_qty = sum(f["qty"] for f in entry_fills)
        total_exit_qty = sum(f["qty"] for f in exit_fills)
        if total_entry_qty <= 0 or total_exit_qty <= 0:
            return {"net_pnl_usd": 0.0, "gross_pnl_usd": 0.0, "total_fees_usd": 0.0, "status": "NO_FILLS"}

        # Weighted average entry price
        total_entry_cost = sum(f["price"] * f["qty"] for f in entry_fills)
        avg_entry_price = total_entry_cost / total_entry_qty
        total_entry_fees = sum(f.get("fee", 0.0) for f in entry_fills)

        # Weighted average exit price
        total_exit_proceeds = sum(f["price"] * f["qty"] for f in exit_fills)
        avg_exit_price = total_exit_proceeds / total_exit_qty
        total_exit_fees = sum(f.get("fee", 0.0) for f in exit_fills)

        matched_qty = min(total_entry_qty, total_exit_qty)

        # Gross P&L
        if side.upper() in ("BUY", "LONG"):
            gross_pnl = matched_qty * (avg_exit_price - avg_entry_price)
        else:
            gross_pnl = matched_qty * (avg_entry_price - avg_exit_price)

        total_commission = total_entry_fees + total_exit_fees
        total_fees = total_commission + abs(funding_fees_paid)
        net_pnl = gross_pnl - total_fees

        return {
            "matched_qty": round(matched_qty, 6),
            "avg_entry_price": round(avg_entry_price, 4),
            "avg_exit_price": round(avg_exit_price, 4),
            "gross_pnl_usd": round(gross_pnl, 4),
            "total_commission_usd": round(total_commission, 4),
            "funding_fees_usd": round(funding_fees_paid, 4),
            "total_fees_usd": round(total_fees, 4),
            "net_pnl_usd": round(net_pnl, 4),
            "is_profitable": net_pnl > 0.0,
            "is_partial": not math.isclose(total_entry_qty, total_exit_qty, rel_tol=1e-5)
        }

    @classmethod
    def assert_no_martingale_escalation(
        cls,
        base_risk_usd: float,
        proposed_risk_usd: float,
        last_trade_loss: bool
    ) -> None:
        """
        Strict anti-martingale assertion:
        If last trade was a loss, proposed risk budget must NEVER exceed base risk budget.
        """
        if last_trade_loss and (proposed_risk_usd > (base_risk_usd * 1.01)):
            raise ValueError(
                f"MARTINGALE_PROHIBITED: Proposed risk ${proposed_risk_usd:.2f} exceeds base risk ${base_risk_usd:.2f} "
                f"following a losing trade. Loss-based risk or leverage escalation is strictly blocked."
            )
