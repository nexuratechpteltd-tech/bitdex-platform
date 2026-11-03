"""
BITDEX Autonomous Futures Scalping Signal Engine
=================================================
Implements the SCALP_ONE_DOLLAR strategy:
- Target net profit: $1.00 after round-trip commissions, execution friction, and slippage.
- Holding duration: Preferred ~5 min, Max ~10 min.
- Decides: LONG, SHORT, or NO_TRADE.
- Calculates exact protective stop (ATR-based, strictly bounded 0.2% - 5.0%).
- Calculates target exit price required to guarantee >= $1.00 net profit.
- Rejects signals where economics cannot achieve $1.00 net profit safely.
"""

import math
import time
import logging
from typing import Dict, Any, List, Optional, Tuple

from .futures_regime import MarketRegimeClassifier

logger = logging.getLogger("bitdex.futures.signal")


class FuturesSignalEngine:
    """Generates structured scalp signals for SCALP_ONE_DOLLAR profile."""

    STRATEGY_NAME = "SCALP_ONE_DOLLAR"
    TARGET_NET_PROFIT_USD = 1.00
    COMMISSION_RATE_PER_SIDE = 0.0004  # 0.04% Binance Futures taker commission
    MAKER_COMMISSION_RATE = 0.0002     # 0.02% Binance Futures maker commission
    DEFAULT_SLIPPAGE_BUFFER_USD = 0.05 # $0.05 estimated slippage buffer
    MIN_SIGNAL_QUALITY_SCORE = 0.70    # Minimum quality score required to trade (Phase 3.1 hardened)

    @classmethod
    def calculate_target_exit(
        cls,
        direction: str,
        entry_price: float,
        quantity: float,
        target_net_usd: float = 1.00,
        slippage_buffer_usd: float = 0.05,
        fee_rate_entry: Optional[float] = None,
        fee_rate_exit: Optional[float] = None
    ) -> Tuple[float, float, float, float]:
        """
        Solves for the exact exit price required to realize target_net_usd after all friction.
        Supports distinct maker/taker fee rates for entry and exit.
        
        Returns: (target_exit_price, gross_pnl, total_fees, expected_net_pnl)
        """
        fee_in = fee_rate_entry if fee_rate_entry is not None else cls.COMMISSION_RATE_PER_SIDE
        fee_out = fee_rate_exit if fee_rate_exit is not None else cls.COMMISSION_RATE_PER_SIDE
        target_friction_sum = target_net_usd + slippage_buffer_usd

        if direction.upper() == "LONG":
            numerator = target_friction_sum + (entry_price * quantity * (1.0 + fee_in))
            denominator = quantity * (1.0 - fee_out)
            exit_price = numerator / max(1e-8, denominator)
            gross_pnl = (exit_price - entry_price) * quantity
        else:  # SHORT
            numerator = (entry_price * quantity * (1.0 - fee_in)) - target_friction_sum
            denominator = quantity * (1.0 + fee_out)
            exit_price = max(0.01, numerator / max(1e-8, denominator))
            gross_pnl = (entry_price - exit_price) * quantity

        entry_fee = entry_price * quantity * fee_in
        exit_fee = exit_price * quantity * fee_out
        total_fees = entry_fee + exit_fee
        expected_net = gross_pnl - total_fees - slippage_buffer_usd

        return exit_price, gross_pnl, total_fees, expected_net

    @classmethod
    def evaluate_signal(
        cls,
        symbol: str,
        klines: List[Dict[str, Any]],
        current_market_price: float,
        proposed_quantity: float,
        equity: float = 1000.0,
        regime_data: Optional[Dict[str, Any]] = None,
        spread_ratio: float = 0.0002,
        exit_model: str = "FIXED_1_DOLLAR",
        is_maker: bool = False,
        klines_15m: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate market structure, ATR, and momentum to produce a structured trading decision:
        LONG_ENTRY, SHORT_ENTRY, or NO_TRADE.
        """
        now_ms = int(time.time() * 1000)

        # 1. Classify regime if not provided
        regime = regime_data or MarketRegimeClassifier.classify(klines, symbol)
        regime_name = regime.get("regime", "UNSTABLE")

        if not regime.get("trade_eligible", False):
            return cls._no_trade(
                symbol, current_market_price, regime_name,
                reason=f"MARKET_REGIME_INELIGIBLE: {regime.get('reason')}"
            )

        if len(klines) < 15:
            return cls._no_trade(symbol, current_market_price, regime_name, reason="INSUFFICIENT_MARKET_HISTORY")

        closes = [k["close"] for k in klines]
        highs = [k["high"] for k in klines]
        lows = [k["low"] for k in klines]
        atr = regime.get("atr") or MarketRegimeClassifier.calculate_atr(klines, 14)

        if atr <= 0.0:
            return cls._no_trade(symbol, current_market_price, regime_name, reason="ZERO_OR_INVALID_ATR")

        # 2. Momentum & Price Action Indicators
        ema9 = MarketRegimeClassifier.calculate_ema(closes, 9)
        ema21 = MarketRegimeClassifier.calculate_ema(closes, 21)
        prev_close = closes[-2]
        latest_close = closes[-1]
        candle_body = latest_close - klines[-1]["open"]

        # RSI (14) calculation
        gains, losses = [], []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i - 1]
            gains.append(max(0.0, diff))
            losses.append(max(0.0, -diff))
        recent_gains = sum(gains[-14:]) / 14.0 if gains else 0.0
        recent_losses = sum(losses[-14:]) / 14.0 if losses else 0.0
        rs = (recent_gains / recent_losses) if recent_losses > 0 else 100.0
        rsi = 100.0 - (100.0 / (1.0 + rs))

        # 3. Directional Bias & Scoring
        long_score = 0.0
        short_score = 0.0

        # Trend alignment
        if ema9 > ema21:
            long_score += 0.35
        elif ema9 < ema21:
            short_score += 0.35

        # Momentum confirmation
        if latest_close > prev_close and candle_body > 0:
            long_score += 0.25
        elif latest_close < prev_close and candle_body < 0:
            short_score += 0.25

        # RSI filter (avoid overbought / oversold exhaustion)
        if 45.0 <= rsi <= 65.0:
            long_score += 0.20
        elif 35.0 <= rsi <= 55.0:
            short_score += 0.20

        # Breakout / Pullback alignment
        recent_high_10 = max(highs[-10:-1])
        recent_low_10 = min(lows[-10:-1])
        if latest_close >= recent_high_10 * 0.999:
            long_score += 0.20
        elif latest_close <= recent_low_10 * 1.001:
            short_score += 0.20

        # Filter against permitted regime directions
        permitted = regime.get("permitted_directions", [])
        if "LONG" not in permitted:
            long_score = 0.0
        if "SHORT" not in permitted:
            short_score = 0.0

        # Determine winning direction
        best_direction = "NO_TRADE"
        best_score = 0.0
        if long_score > short_score and long_score >= cls.MIN_SIGNAL_QUALITY_SCORE:
            best_direction = "LONG"
            best_score = round(long_score, 2)
        elif short_score > long_score and short_score >= cls.MIN_SIGNAL_QUALITY_SCORE:
            best_direction = "SHORT"
            best_score = round(short_score, 2)
        else:
            return cls._no_trade(
                symbol, current_market_price, regime_name,
                reason=f"SIGNAL_SCORE_BELOW_THRESHOLD (Long: {long_score:.2f}, Short: {short_score:.2f}, Required: {cls.MIN_SIGNAL_QUALITY_SCORE})"
            )

        # Section 3: Multi-Timeframe (15m) Trend Confirmation
        if klines_15m and len(klines_15m) >= 15:
            closes_15m = [k["close"] for k in klines_15m]
            ema9_15m = MarketRegimeClassifier.calculate_ema(closes_15m, 9)
            ema21_15m = MarketRegimeClassifier.calculate_ema(closes_15m, 21)
            if best_direction == "LONG" and ema9_15m < ema21_15m:
                return cls._no_trade(
                    symbol, current_market_price, regime_name,
                    reason=f"REJECTED_MTF_CONFLICT_BEARISH_15M (15m EMA9 {ema9_15m:.2f} < EMA21 {ema21_15m:.2f})"
                )
            elif best_direction == "SHORT" and ema9_15m > ema21_15m:
                return cls._no_trade(
                    symbol, current_market_price, regime_name,
                    reason=f"REJECTED_MTF_CONFLICT_BULLISH_15M (15m EMA9 {ema9_15m:.2f} > EMA21 {ema21_15m:.2f})"
                )

        # 4. Stop-Loss Calculation (ATR-based, bounded strictly by 0.2% - 5.0%)
        stop_mult = 1.8  # 1.8x ATR scalp stop distance
        raw_stop_dist = atr * stop_mult
        raw_stop_ratio = raw_stop_dist / current_market_price

        # Clamp stop distance strictly within Phase 2 risk rules: 0.2% <= dist <= 5.0%
        clamped_stop_ratio = max(0.0025, min(0.045, raw_stop_ratio))
        clamped_stop_dist = current_market_price * clamped_stop_ratio

        if best_direction == "LONG":
            stop_price = current_market_price - clamped_stop_dist
        else:
            stop_price = current_market_price + clamped_stop_dist

        # 5. Target Exit Price computation based on selected exit model
        target_net = cls.TARGET_NET_PROFIT_USD
        if exit_model.upper() == "ATR_SCALED":
            # ATR-scaled model: target scales with volatility to expand payoff ratio
            scaled_gross = 1.2 * atr * proposed_quantity
            target_net = max(1.00, scaled_gross - (current_market_price * proposed_quantity * 0.0008) - cls.DEFAULT_SLIPPAGE_BUFFER_USD)

        fee_in = cls.MAKER_COMMISSION_RATE if is_maker else cls.COMMISSION_RATE_PER_SIDE
        fee_out = cls.MAKER_COMMISSION_RATE if is_maker else cls.COMMISSION_RATE_PER_SIDE

        target_exit_price, gross_pnl, total_fees, expected_net_pnl = cls.calculate_target_exit(
            direction=best_direction,
            entry_price=current_market_price,
            quantity=proposed_quantity,
            target_net_usd=target_net,
            slippage_buffer_usd=cls.DEFAULT_SLIPPAGE_BUFFER_USD,
            fee_rate_entry=fee_in,
            fee_rate_exit=fee_out
        )

        # Verify net profitability meets $1.00 preferred target
        if expected_net_pnl < (cls.TARGET_NET_PROFIT_USD - 0.01):
            return cls._no_trade(
                symbol, current_market_price, regime_name,
                reason=f"UNFEASIBLE_TARGET_NET_PROFIT (Expected Net: ${expected_net_pnl:.2f} < ${cls.TARGET_NET_PROFIT_USD:.2f})"
            )

        # 6. Verify required price move is economically realistic (within 1.5x ATR)
        price_move_required = abs(target_exit_price - current_market_price)
        if price_move_required > (atr * 2.0):
            return cls._no_trade(
                symbol, current_market_price, regime_name,
                reason=f"REQUIRED_MOVE_EXCEEDS_VOLATILITY (Required move ${price_move_required:.2f} > 2x ATR ${atr*2:.2f})"
            )

        intent = "LONG_ENTRY" if best_direction == "LONG" else "SHORT_ENTRY"

        return {
            "decision": "TRADE",
            "intent": intent,
            "direction": best_direction,
            "symbol": symbol.upper(),
            "signal_timestamp_ms": now_ms,
            "market_price": round(current_market_price, 4),
            "entry_reference_price": round(current_market_price, 4),
            "protective_stop_price": round(stop_price, 4),
            "stop_distance_pct": round(clamped_stop_ratio * 100, 2),
            "target_exit_price": round(target_exit_price, 4),
            "expected_gross_pnl_usd": round(gross_pnl, 4),
            "estimated_fees_usd": round(total_fees, 4),
            "estimated_slippage_usd": round(cls.DEFAULT_SLIPPAGE_BUFFER_USD, 4),
            "expected_net_pnl_usd": round(expected_net_pnl, 4),
            "signal_score": best_score,
            "regime": regime_name,
            "rsi": round(rsi, 2),
            "atr": round(atr, 4),
            "rejection_reason": None,
        }

    @classmethod
    def _no_trade(cls, symbol: str, price: float, regime: str, reason: str) -> Dict[str, Any]:
        return {
            "decision": "NO_TRADE",
            "intent": "NO_TRADE",
            "direction": "NO_TRADE",
            "symbol": symbol.upper(),
            "signal_timestamp_ms": int(time.time() * 1000),
            "market_price": round(price, 4),
            "entry_reference_price": round(price, 4),
            "protective_stop_price": 0.0,
            "stop_distance_pct": 0.0,
            "target_exit_price": 0.0,
            "expected_gross_pnl_usd": 0.0,
            "estimated_fees_usd": 0.0,
            "estimated_slippage_usd": 0.0,
            "expected_net_pnl_usd": 0.0,
            "signal_score": 0.0,
            "regime": regime,
            "rsi": 0.0,
            "atr": 0.0,
            "rejection_reason": reason,
        }
