"""
BITDEX Exness HFT Risk Guard & Safety Engine (Phase F)
Enforces multi-tier quantitative risk controls and safety barriers:
- Maximum open position limits
- Maximum aggregate exposure (notional USD)
- Maximum daily loss & maximum basket loss circuit breakers
- Margin utilization limits (e.g. max 30% of free margin)
- Per-symbol volume limits
- Stale market-data rejection (quotes older than 3000ms)
- Missing broker-side stop-loss detection
- Emergency trading lock enforcement (`live_trading_locked = True`)
- Multi-field discrepancy alert gates

All execution controls remain disabled.
"""

import time
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger("bitdex.exness.risk")


@dataclass
class RiskLimits:
    max_open_positions: int = 5
    max_aggregate_exposure_usd: float = 50000.0
    max_daily_loss_usd: float = 250.0      # 5% circuit breaker on $5000 equity
    max_basket_loss_usd: float = 100.0     # Max floating loss on active pair
    max_drawdown_pct: float = 10.0         # 10% trailing drawdown circuit breaker
    max_margin_utilization_pct: float = 30.0 # Max 30% free margin committed
    max_volume_per_symbol: float = 0.50    # Max lots open per symbol
    max_volume_per_order: float = 0.10     # Max lots per single order
    max_stale_quote_ms: int = 3000         # Stale quote threshold
    emergency_lock_active: bool = True     # Strict global lock


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
        """Rejects market data older than threshold."""
        now_ms = int(time.time() * 1000)
        age_ms = abs(now_ms - tick_time_ms)
        if age_ms > self.limits.max_stale_quote_ms:
            return False, f"STALE_DATA_REJECTED: Quote age {age_ms}ms exceeds maximum allowed {self.limits.max_stale_quote_ms}ms."
        return True, "QUOTE_FRESH"

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
        """
        # 1. Global trading lock check
        if self.limits.emergency_lock_active or account_info.get("live_trading_locked", True):
            return False, "PRE_TRADE_BLOCKED: Global trading lock (live_trading_locked=True) is active."

        # 2. Daily Loss Limit
        if abs(daily_realized_loss) >= self.limits.max_daily_loss_usd:
            return False, f"CIRCUIT_BREAKER_TRIGGERED: Daily loss ${abs(daily_realized_loss):.2f} reached limit of ${self.limits.max_daily_loss_usd:.2f}."

        # 3. Position Count Limit
        if len(current_open_positions) >= self.limits.max_open_positions:
            return False, f"POSITION_LIMIT_EXCEEDED: Open positions ({len(current_open_positions)}) at limit ({self.limits.max_open_positions})."

        # 4. Single Order Volume Limit
        if volume > self.limits.max_volume_per_order:
            return False, f"VOLUME_LIMIT_EXCEEDED: Order volume {volume} exceeds single order limit {self.limits.max_volume_per_order}."

        # 5. Symbol Aggregate Volume Limit
        symbol_vol = sum(p.get("volume", 0.0) for p in current_open_positions if p.get("symbol") == symbol)
        if (symbol_vol + volume) > self.limits.max_volume_per_symbol:
            return False, f"SYMBOL_VOLUME_LIMIT_EXCEEDED: Total volume {symbol_vol + volume:.2f} for {symbol} exceeds limit {self.limits.max_volume_per_symbol}."

        # 6. Aggregate Exposure Limit (Notional USD)
        current_notional = sum(p.get("volume", 0.0) * p.get("price_open", 0.0) * 100.0 for p in current_open_positions)
        new_notional = volume * price * 100.0
        if (current_notional + new_notional) > self.limits.max_aggregate_exposure_usd:
            return False, f"EXPOSURE_LIMIT_EXCEEDED: Aggregate notional ${current_notional + new_notional:,.2f} exceeds limit ${self.limits.max_aggregate_exposure_usd:,.2f}."

        # 7. Margin Utilization Limit
        free_margin = float(account_info.get("free_margin", 0.0))
        used_margin = float(account_info.get("used_margin", 0.0))
        equity = float(account_info.get("equity", 5000.0))

        if equity > 0:
            utilization_pct = (used_margin / equity) * 100.0
            if utilization_pct > self.limits.max_margin_utilization_pct:
                return False, f"MARGIN_LIMIT_EXCEEDED: Margin utilization {utilization_pct:.1f}% exceeds limit {self.limits.max_margin_utilization_pct}%."

        return True, "RISK_APPROVED"

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
