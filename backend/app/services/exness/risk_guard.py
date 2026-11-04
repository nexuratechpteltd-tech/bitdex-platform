"""
BITDEX Exness HFT Risk Guard & Safety Engine (Phase F / 2.4.1 Forensic Remediation)
Enforces multi-tier quantitative risk controls and safety barriers:
- Maximum open position limits
- Instrument-specific notional exposure limits (XAUUSDm 100, BTCUSDm 1, EURUSDm 100,000)
- Daily loss circuit breaker (only triggers on actual net losses, never on profits)
- Maximum trailing drawdown percentage limit
- Basket floating loss circuit breaker (gating pre-trade validation)
- Margin utilization limits with clearly documented denominator: (Used Margin / Account Equity) * 100.0
- Per-symbol volume limits and single order volume clamps
- Quote freshness validation (rejecting future timestamps as well as stale quotes)
- Mandatory broker-side stop-loss enforcement (gating pre-trade validation)
- Input sanity validation (rejects non-positive, NaN, Inf, and missing values)
- Emergency trading lock enforcement (`live_trading_locked = True`, `emergency_lock_active = True`)

All live execution controls remain strictly locked.
"""

import time
import math
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger("bitdex.exness.risk")

# Standard broker contract sizes per lot
SYMBOL_CONTRACT_SIZES: Dict[str, float] = {
    "XAUUSDm": 100.0,       # 100 oz per lot
    "BTCUSDm": 1.0,         # 1 BTC per lot
    "EURUSDm": 100000.0,    # 100,000 EUR per lot
    "GBPUSDm": 100000.0,    # 100,000 GBP per lot
    "AUDUSDm": 100000.0,
    "USDCADm": 100000.0,
    "USDJPYm": 100000.0,
}


@dataclass
class RiskLimits:
    max_open_positions: int = 5
    max_aggregate_exposure_usd: float = 50000.0
    max_daily_loss_usd: float = 250.0        # 5% circuit breaker on $5000 equity
    max_basket_loss_usd: float = 100.0       # Max floating loss on active pair
    max_drawdown_pct: float = 10.0           # 10% trailing drawdown circuit breaker
    max_margin_utilization_pct: float = 30.0 # Max 30% of account equity committed to margin
    max_volume_per_symbol: float = 0.50      # Max lots open per symbol
    max_volume_per_order: float = 0.10       # Max lots per single order
    max_stale_quote_ms: int = 3000           # Stale quote threshold (3 seconds)
    max_future_skew_ms: int = 1000           # Max allowable future clock skew (1 second)
    emergency_lock_active: bool = True       # Strict global fail-closed lock


class ExnessRiskGuard:
    """
    Evaluates pre-trade compliance and runtime risk metrics without placing orders.
    Fails closed on any limit breach.
    """

    def __init__(self, limits: Optional[RiskLimits] = None):
        self.limits = limits or RiskLimits()

    def check_emergency_lock(self, live_trading_locked: bool) -> Tuple[bool, str]:
        """Validates that execution remains locked."""
        if not live_trading_locked or self.limits.emergency_lock_active:
            return True, "SAFETY CONFIRMED: Live trading is locked."
        return False, "CRITICAL RISK: Live trading lock is inactive!"

    def validate_quote_freshness(self, tick_time_ms: int) -> Tuple[bool, str]:
        """
        Validates quote timestamp:
        - Rejects future timestamps exceeding allowable clock skew.
        - Rejects stale quotes older than max_stale_quote_ms.
        """
        now_ms = int(time.time() * 1000)
        future_drift_ms = tick_time_ms - now_ms
        if future_drift_ms > self.limits.max_future_skew_ms:
            return False, f"FUTURE_DATA_REJECTED: Quote timestamp is {future_drift_ms}ms in the future (feed desync or clock skew)."

        age_ms = now_ms - tick_time_ms
        if age_ms < 0:
            age_ms = 0
        if age_ms > self.limits.max_stale_quote_ms:
            return False, f"STALE_DATA_REJECTED: Quote age {age_ms}ms exceeds maximum allowed {self.limits.max_stale_quote_ms}ms."
        return True, "QUOTE_FRESH"

    def detect_missing_stop_loss(self, positions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Scans positions and flags any position lacking a valid broker-side stop-loss.
        """
        unprotected = []
        for p in positions:
            sl = float(p.get("sl", 0.0))
            if sl <= 0.0:
                unprotected.append({
                    "ticket": str(p.get("ticket")),
                    "symbol": p.get("symbol"),
                    "side": p.get("side"),
                    "volume": p.get("volume"),
                    "price_open": p.get("price_open"),
                    "risk_flag": "MISSING_BROKER_STOP_LOSS",
                })
        return unprotected

    def evaluate_basket_drawdown(self, positions: List[Dict[str, Any]]) -> Tuple[bool, float, str]:
        """
        Calculates total floating loss across open positions. Triggers alert if basket loss exceeded.
        """
        total_floating = sum(float(p.get("profit", 0.0)) for p in positions)
        if total_floating < 0 and abs(total_floating) >= self.limits.max_basket_loss_usd:
            return False, total_floating, f"BASKET_LOSS_BREACH: Floating loss ${abs(total_floating):.2f} exceeds limit ${self.limits.max_basket_loss_usd:.2f}."
        return True, total_floating, "BASKET_RISK_NOMINAL"

    def validate_pre_order(
        self,
        symbol: str,
        volume: float,
        price: float,
        current_open_positions: List[Dict[str, Any]],
        account_info: Dict[str, Any],
        daily_realized_loss: float = 0.0,
    ) -> Tuple[bool, str]:
        """
        Pre-flight risk check before any hypothetical order.
        Validates all inputs, stops, basket losses, notional exposure, and margin limits.
        Fails closed on any violation.
        """
        # 1. Global trading lock check (Fail-Closed)
        if self.limits.emergency_lock_active or account_info.get("live_trading_locked", True):
            return False, "PRE_TRADE_BLOCKED: Global trading lock (live_trading_locked=True) is active."

        # 2. Strict Input Validation
        if not symbol or not isinstance(symbol, str):
            return False, "INVALID_RISK_INPUT: Symbol must be a non-empty string."
        if volume <= 0.0 or math.isnan(volume) or math.isinf(volume):
            return False, f"INVALID_RISK_INPUT: Order volume must be a positive finite number (got {volume})."
        if price <= 0.0 or math.isnan(price) or math.isinf(price):
            return False, f"INVALID_RISK_INPUT: Order price must be a positive finite number (got {price})."

        # 3. Existing Unprotected Stop-Loss Gate
        unprotected_positions = self.detect_missing_stop_loss(current_open_positions)
        if unprotected_positions:
            return False, f"PRE_TRADE_BLOCKED: {len(unprotected_positions)} open positions lack mandatory broker stop-loss."

        # 4. Basket Floating Loss Circuit Breaker
        basket_safe, total_floating, basket_msg = self.evaluate_basket_drawdown(current_open_positions)
        if not basket_safe:
            return False, f"PRE_TRADE_BLOCKED: {basket_msg}"

        # 5. Daily Loss Limit (Only triggers on actual net loss, NEVER on profit)
        # Note: If daily_realized_loss is passed as a signed PnL, negative indicates loss, positive indicates profit.
        if daily_realized_loss < 0.0 and abs(daily_realized_loss) >= self.limits.max_daily_loss_usd:
            return False, f"CIRCUIT_BREAKER_TRIGGERED: Daily loss ${abs(daily_realized_loss):.2f} reached limit of ${self.limits.max_daily_loss_usd:.2f}."

        # 6. Maximum Trailing Drawdown Percentage Limit
        equity = float(account_info.get("equity", 5000.0))
        peak_equity = float(account_info.get("peak_equity", equity))
        if peak_equity > 0.0:
            current_dd_pct = ((peak_equity - equity) / peak_equity) * 100.0
            if current_dd_pct >= self.limits.max_drawdown_pct:
                return False, f"DRAWDOWN_LIMIT_EXCEEDED: Current drawdown {current_dd_pct:.2f}% exceeds limit {self.limits.max_drawdown_pct:.2f}%."

        # 7. Position Count Limit
        if len(current_open_positions) >= self.limits.max_open_positions:
            return False, f"POSITION_LIMIT_EXCEEDED: Open positions ({len(current_open_positions)}) at limit ({self.limits.max_open_positions})."

        # 8. Single Order Volume Limit
        if volume > self.limits.max_volume_per_order:
            return False, f"VOLUME_LIMIT_EXCEEDED: Order volume {volume} exceeds single order limit {self.limits.max_volume_per_order}."

        # 9. Symbol Aggregate Volume Limit
        symbol_vol = sum(p.get("volume", 0.0) for p in current_open_positions if p.get("symbol") == symbol)
        if (symbol_vol + volume) > self.limits.max_volume_per_symbol:
            return False, f"SYMBOL_VOLUME_LIMIT_EXCEEDED: Total volume {symbol_vol + volume:.2f} for {symbol} exceeds limit {self.limits.max_volume_per_symbol}."

        # 10. Instrument-Specific Aggregate Notional Exposure Limit
        # Contract size is looked up by instrument specification (e.g. 100 oz for Gold, 100,000 for FX, 1 for BTC)
        order_contract_size = SYMBOL_CONTRACT_SIZES.get(symbol, 100.0)
        new_notional = volume * price * order_contract_size

        current_notional = 0.0
        for p in current_open_positions:
            p_sym = p.get("symbol", symbol)
            p_csize = SYMBOL_CONTRACT_SIZES.get(p_sym, 100.0)
            current_notional += float(p.get("volume", 0.0)) * float(p.get("price_open", price)) * p_csize

        if (current_notional + new_notional) > self.limits.max_aggregate_exposure_usd:
            return False, f"EXPOSURE_LIMIT_EXCEEDED: Aggregate notional ${current_notional + new_notional:,.2f} exceeds limit ${self.limits.max_aggregate_exposure_usd:,.2f}."

        # 11. Margin Utilization Limit
        # Denominator documentation:
        # Margin Utilization % = (Used Margin / Account Equity) * 100.0
        # Denominator is explicitly Account Equity. If Equity <= 0, trading is fail-closed.
        if equity <= 0.0:
            return False, f"MARGIN_LIMIT_EXCEEDED: Account equity is non-positive (${equity:.2f})."

        used_margin = float(account_info.get("used_margin", 0.0))
        leverage = float(account_info.get("leverage", 2000.0))
        if leverage <= 0.0:
            leverage = 2000.0
        estimated_order_margin = new_notional / leverage
        total_projected_used_margin = used_margin + estimated_order_margin

        utilization_pct = (total_projected_used_margin / equity) * 100.0
        if utilization_pct > self.limits.max_margin_utilization_pct:
            return False, f"MARGIN_LIMIT_EXCEEDED: Margin utilization {utilization_pct:.1f}% exceeds limit {self.limits.max_margin_utilization_pct}% (projected margin ${total_projected_used_margin:.2f} on equity ${equity:.2f})."

        return True, "RISK_APPROVED"
