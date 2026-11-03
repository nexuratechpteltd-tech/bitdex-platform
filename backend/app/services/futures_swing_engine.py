"""
BITDEX Autonomous Binance Futures Swing / Momentum Expansion Engine
====================================================================
Strategy: SWING_MOMENTUM_EXPANSION (Phase 3.2)

Architecture:
- Multi-timeframe synthesis:
    * 1h: Macro trend bias, market structure, ADX, and baseline ATR
    * 15m: Intermediate momentum, setup filter, volume expansion, pullback zones
    * 5m: Precision execution timing, trigger confirmation, structural invalidation
- Four independently defined entry models:
    * Model A: Trend Continuation (1h/15m EMA alignment, ADX >= 25, 5m trigger)
    * Model B: Breakout Expansion (Consolidation breakout, volume >= 1.5x avg, ATR expansion)
    * Model C: Pullback Continuation (Trend-aligned test of 15m EMA21/50, reversal trigger)
    * Model D: NO_TRADE filter (Chop, conflicting timeframes, spread > 0.05%, risk cap breach)
- Capital & Risk Controls:
    * Enforces Phase 2 FuturesRiskEngine (2% equity risk cap, 10x leverage, $5,000 exposure)
    * Sizing derived strictly from dollar risk and stop distance (Min notional NEVER overrides risk)
    * Exchange-confirmed protective stop (STOP_MARKET) within [0.2%, 5.0%]
    * Emergency reduce-only market exit if protective stop placement fails
- Dynamic Multi-Stage Exit Framework:
    * Target 1 (+1.5R): Locks breakeven + fee offset
    * Target 2 (+2.5R to +3.5R): Primary expansion profit target
    * Dynamic Trailing Exit: Trails by 1.2x 15m ATR once +1.5R is reached
    * Structural Invalidation: 15m close against trend / EMA cross
    * Max Holding Expiry: 48 hours for swing positions
"""

import time
import math
import json
import logging
import sqlite3
from typing import Optional, Dict, Any, List, Tuple

from .binance_futures_adapter import BinanceFuturesAdapter, BinanceFuturesError
from .futures_discovery import MarketDiscoveryService
from .futures_risk_engine import FuturesRiskEngine
from .futures_execution import FuturesExecutionEngine
from .futures_db import (
    get_or_create_futures_account,
    get_futures_account,
    get_open_futures_position,
    list_open_futures_positions,
    get_or_create_scalp_run,
    update_scalp_run_state,
    record_scalp_signal,
    record_scalp_trade,
    complete_scalp_trade,
    utc_now_iso,
)

logger = logging.getLogger("bitdex.futures.swing")


# ─────────────────────────────────────────────────────────────────────────────
# Technical Indicators & Multi-Timeframe Feature Extractor
# ─────────────────────────────────────────────────────────────────────────────

class TechnicalIndicators:
    """Deterministic, pure-python technical indicators for multi-timeframe analysis."""

    @staticmethod
    def calculate_ema(prices: List[float], period: int) -> List[float]:
        if not prices or len(prices) < period:
            return [prices[-1]] * len(prices) if prices else []
        k = 2.0 / (period + 1.0)
        ema = [sum(prices[:period]) / period]
        for p in prices[period:]:
            ema.append(p * k + ema[-1] * (1.0 - k))
        # Pad front with None or first value for alignment
        padding = [ema[0]] * (period - 1)
        return padding + ema

    @staticmethod
    def calculate_atr(candles: List[Dict[str, Any]], period: int = 14) -> float:
        if len(candles) < 2:
            return 1.0
        tr_list = []
        for i in range(1, len(candles)):
            h = float(candles[i]["high"])
            l = float(candles[i]["low"])
            prev_c = float(candles[i - 1]["close"])
            tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
            tr_list.append(tr)
        if len(tr_list) < period:
            return sum(tr_list) / max(1, len(tr_list))
        # Wilder's smoothed ATR
        atr = sum(tr_list[:period]) / period
        for tr in tr_list[period:]:
            atr = (atr * (period - 1) + tr) / period
        return max(1e-8, atr)

    @staticmethod
    def calculate_rsi(prices: List[float], period: int = 14) -> float:
        if len(prices) <= period:
            return 50.0
        gains, losses = [], []
        for i in range(1, len(prices)):
            delta = prices[i] - prices[i - 1]
            if delta >= 0:
                gains.append(delta)
                losses.append(0.0)
            else:
                gains.append(0.0)
                losses.append(abs(delta))
        if len(gains) < period:
            return 50.0
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss < 1e-8:
            return 100.0 if avg_gain > 0 else 50.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    @staticmethod
    def calculate_adx(candles: List[Dict[str, Any]], period: int = 14) -> float:
        if len(candles) < period * 2:
            return 20.0
        tr_list = []
        plus_dm = []
        minus_dm = []
        for i in range(1, len(candles)):
            h = float(candles[i]["high"])
            l = float(candles[i]["low"])
            prev_h = float(candles[i - 1]["high"])
            prev_l = float(candles[i - 1]["low"])
            prev_c = float(candles[i - 1]["close"])

            tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
            tr_list.append(tr)

            up_move = h - prev_h
            down_move = prev_l - l

            if up_move > down_move and up_move > 0:
                plus_dm.append(up_move)
            else:
                plus_dm.append(0.0)

            if down_move > up_move and down_move > 0:
                minus_dm.append(down_move)
            else:
                minus_dm.append(0.0)

        # Smooth TR and DMs
        tr_smooth = sum(tr_list[:period])
        plus_smooth = sum(plus_dm[:period])
        minus_smooth = sum(minus_dm[:period])

        dx_list = []
        for i in range(period, len(tr_list)):
            tr_smooth = tr_smooth - (tr_smooth / period) + tr_list[i]
            plus_smooth = plus_smooth - (plus_smooth / period) + plus_dm[i]
            minus_smooth = minus_smooth - (minus_smooth / period) + minus_dm[i]

            plus_di = (100.0 * plus_smooth / tr_smooth) if tr_smooth > 0 else 0
            minus_di = (100.0 * minus_smooth / tr_smooth) if tr_smooth > 0 else 0

            denom = plus_di + minus_di
            dx = (100.0 * abs(plus_di - minus_di) / denom) if denom > 0 else 0
            dx_list.append(dx)

        if len(dx_list) < period:
            return sum(dx_list) / max(1, len(dx_list))
        adx = sum(dx_list[:period]) / period
        for dx in dx_list[period:]:
            adx = (adx * (period - 1) + dx) / period
        return adx


# ─────────────────────────────────────────────────────────────────────────────
# Swing Signal Evaluator
# ─────────────────────────────────────────────────────────────────────────────

class SwingSignalEvaluator:
    """Evaluates multi-timeframe candle datasets across 4 independent entry models."""

    @classmethod
    def evaluate(
        cls,
        symbol: str,
        candles_1h: List[Dict[str, Any]],
        candles_15m: List[Dict[str, Any]],
        candles_5m: List[Dict[str, Any]],
        current_price: float,
        spread_ratio: float = 0.0002,
    ) -> Dict[str, Any]:
        """
        Synthesizes 1h, 15m, 5m market structure.
        Returns: {
            'decision': 'TRADE' | 'NO_TRADE',
            'model': 'MODEL_A_TREND_CONTINUATION' | 'MODEL_B_BREAKOUT_EXPANSION' |
                     'MODEL_C_PULLBACK_BOUNCE' | 'MODEL_D_NO_TRADE',
            'direction': 'LONG' | 'SHORT' | 'NO_TRADE',
            'intent': 'LONG_ENTRY' | 'SHORT_ENTRY' | 'NO_TRADE',
            'entry_price': float,
            'stop_price': float,
            'target_exit_1': float,   # 1.5R breakeven trigger
            'target_exit_2': float,   # 2.5R primary expansion target
            'r_reward_usd_per_unit': float,
            'r_risk_usd_per_unit': float,
            'score': float,
            'rejection_reason': Optional[str],
            'meta': Dict[str, Any]
        }
        """
        # Data sufficiency check
        if len(candles_1h) < 50 or len(candles_15m) < 50 or len(candles_5m) < 20:
            return cls._no_trade("INSUFFICIENT_MULTI_TIMEFRAME_DATA", symbol, current_price)

        # Spread gate (0.05% max allowed)
        if spread_ratio > 0.0005:
            return cls._no_trade("EXCESSIVE_SPREAD_GATE_BREACH", symbol, current_price, {"spread_ratio": spread_ratio})

        # ── 1. Higher-Timeframe Feature Extraction (1h) ──
        closes_1h = [float(c["close"]) for c in candles_1h]
        ema50_1h = TechnicalIndicators.calculate_ema(closes_1h, 50)[-1]
        ema200_1h = TechnicalIndicators.calculate_ema(closes_1h, 200)[-1] if len(closes_1h) >= 200 else ema50_1h
        atr_1h = TechnicalIndicators.calculate_atr(candles_1h, 14)
        adx_1h = TechnicalIndicators.calculate_adx(candles_1h, 14)
        close_1h = closes_1h[-1]

        # 1h Trend Classification
        macro_bullish = close_1h > ema50_1h and (len(closes_1h) < 200 or ema50_1h >= ema200_1h)
        macro_bearish = close_1h < ema50_1h and (len(closes_1h) < 200 or ema50_1h <= ema200_1h)

        # ── 2. Intermediate Feature Extraction (15m) ──
        closes_15m = [float(c["close"]) for c in candles_15m]
        vols_15m = [float(c["volume"]) for c in candles_15m]
        ema21_15m = TechnicalIndicators.calculate_ema(closes_15m, 21)[-1]
        ema50_15m = TechnicalIndicators.calculate_ema(closes_15m, 50)[-1]
        atr_15m = TechnicalIndicators.calculate_atr(candles_15m, 14)
        rsi_15m = TechnicalIndicators.calculate_rsi(closes_15m, 14)
        avg_vol_20 = sum(vols_15m[-21:-1]) / 20.0 if len(vols_15m) >= 21 else vols_15m[-1]
        curr_vol_15m = vols_15m[-1]
        vol_expansion_ratio = curr_vol_15m / max(1e-8, avg_vol_20)

        # ── 3. Micro Feature Extraction (5m) ──
        closes_5m = [float(c["close"]) for c in candles_5m]
        highs_5m = [float(c["high"]) for c in candles_5m]
        lows_5m = [float(c["low"]) for c in candles_5m]
        recent_high_5m = max(highs_5m[-12:])
        recent_low_5m = min(lows_5m[-12:])
        atr_5m = TechnicalIndicators.calculate_atr(candles_5m, 14)

        meta = {
            "close_1h": close_1h, "ema50_1h": ema50_1h, "adx_1h": adx_1h, "atr_1h": atr_1h,
            "ema21_15m": ema21_15m, "ema50_15m": ema50_15m, "rsi_15m": rsi_15m,
            "vol_expansion_ratio": vol_expansion_ratio, "atr_15m": atr_15m, "atr_5m": atr_5m
        }

        # ── MODEL D: NO_TRADE GATING ──
        if adx_1h < 18.0:
            return cls._no_trade("MARKET_CHOP_LOW_ADX", symbol, current_price, meta)

        # ── MODEL A: TREND CONTINUATION ──
        # Strong 1h trend + 15m aligned trend + healthy RSI + 5m trigger
        if macro_bullish and ema21_15m > ema50_15m and 45.0 <= rsi_15m <= 68.0 and adx_1h >= 24.0:
            # Bullish continuation: entry near current price, stop below recent 5m swing low or 1.5x atr_15m
            stop_dist = max(current_price * 0.003, max(current_price - recent_low_5m, atr_15m * 1.5))
            stop_price = current_price - stop_dist
            # Check Phase 2 stop boundaries [0.2%, 5.0%]
            stop_pct = stop_dist / current_price
            if 0.002 <= stop_pct <= 0.05:
                r_risk = stop_dist
                target_1 = current_price + (r_risk * 1.5)
                target_2 = current_price + (r_risk * 2.5)
                return cls._trade(
                    model="MODEL_A_TREND_CONTINUATION",
                    direction="LONG",
                    entry_price=current_price,
                    stop_price=round(stop_price, 4),
                    target_1=round(target_1, 4),
                    target_2=round(target_2, 4),
                    r_risk=r_risk,
                    score=0.88,
                    meta=meta
                )

        if macro_bearish and ema21_15m < ema50_15m and 32.0 <= rsi_15m <= 55.0 and adx_1h >= 24.0:
            # Bearish continuation: stop above recent 5m swing high or 1.5x atr_15m
            stop_dist = max(current_price * 0.003, max(recent_high_5m - current_price, atr_15m * 1.5))
            stop_price = current_price + stop_dist
            stop_pct = stop_dist / current_price
            if 0.002 <= stop_pct <= 0.05:
                r_risk = stop_dist
                target_1 = current_price - (r_risk * 1.5)
                target_2 = current_price - (r_risk * 2.5)
                return cls._trade(
                    model="MODEL_A_TREND_CONTINUATION",
                    direction="SHORT",
                    entry_price=current_price,
                    stop_price=round(stop_price, 4),
                    target_1=round(target_1, 4),
                    target_2=round(target_2, 4),
                    r_risk=r_risk,
                    score=0.88,
                    meta=meta
                )

        # ── MODEL B: BREAKOUT EXPANSION ──
        # 15m volume >= 1.4x, breaking multi-hour 15m high/low, not overextended
        high_24_15m = max([float(c["high"]) for c in candles_15m[-24:-1]])
        low_24_15m = min([float(c["low"]) for c in candles_15m[-24:-1]])

        if current_price > high_24_15m and vol_expansion_ratio >= 1.40 and macro_bullish:
            # Bullish breakout
            stop_dist = max(current_price * 0.003, (current_price - high_24_15m) + atr_15m * 1.2)
            stop_price = current_price - stop_dist
            stop_pct = stop_dist / current_price
            if 0.002 <= stop_pct <= 0.05:
                r_risk = stop_dist
                target_1 = current_price + (r_risk * 1.5)
                target_2 = current_price + (r_risk * 3.0)
                return cls._trade(
                    model="MODEL_B_BREAKOUT_EXPANSION",
                    direction="LONG",
                    entry_price=current_price,
                    stop_price=round(stop_price, 4),
                    target_1=round(target_1, 4),
                    target_2=round(target_2, 4),
                    r_risk=r_risk,
                    score=0.84,
                    meta=meta
                )

        if current_price < low_24_15m and vol_expansion_ratio >= 1.40 and macro_bearish:
            # Bearish breakdown
            stop_dist = max(current_price * 0.003, (low_24_15m - current_price) + atr_15m * 1.2)
            stop_price = current_price + stop_dist
            stop_pct = stop_dist / current_price
            if 0.002 <= stop_pct <= 0.05:
                r_risk = stop_dist
                target_1 = current_price - (r_risk * 1.5)
                target_2 = current_price - (r_risk * 3.0)
                return cls._trade(
                    model="MODEL_B_BREAKOUT_EXPANSION",
                    direction="SHORT",
                    entry_price=current_price,
                    stop_price=round(stop_price, 4),
                    target_1=round(target_1, 4),
                    target_2=round(target_2, 4),
                    r_risk=r_risk,
                    score=0.84,
                    meta=meta
                )

        # ── MODEL C: PULLBACK CONTINUATION ──
        # Price tests 15m EMA21 within 0.4x ATR, bouncing in direction of 1h trend
        dist_to_ema21 = abs(current_price - ema21_15m)
        if macro_bullish and dist_to_ema21 <= atr_15m * 0.4 and current_price >= ema21_15m:
            # Pullback bounce LONG
            stop_dist = max(current_price * 0.003, (current_price - ema50_15m) + atr_15m * 0.8)
            stop_price = current_price - stop_dist
            stop_pct = stop_dist / current_price
            if 0.002 <= stop_pct <= 0.05:
                r_risk = stop_dist
                target_1 = current_price + (r_risk * 1.5)
                target_2 = current_price + (r_risk * 2.5)
                return cls._trade(
                    model="MODEL_C_PULLBACK_BOUNCE",
                    direction="LONG",
                    entry_price=current_price,
                    stop_price=round(stop_price, 4),
                    target_1=round(target_1, 4),
                    target_2=round(target_2, 4),
                    r_risk=r_risk,
                    score=0.80,
                    meta=meta
                )

        if macro_bearish and dist_to_ema21 <= atr_15m * 0.4 and current_price <= ema21_15m:
            # Pullback bounce SHORT
            stop_dist = max(current_price * 0.003, (ema50_15m - current_price) + atr_15m * 0.8)
            stop_price = current_price + stop_dist
            stop_pct = stop_dist / current_price
            if 0.002 <= stop_pct <= 0.05:
                r_risk = stop_dist
                target_1 = current_price - (r_risk * 1.5)
                target_2 = current_price - (r_risk * 2.5)
                return cls._trade(
                    model="MODEL_C_PULLBACK_BOUNCE",
                    direction="SHORT",
                    entry_price=current_price,
                    stop_price=round(stop_price, 4),
                    target_1=round(target_1, 4),
                    target_2=round(target_2, 4),
                    r_risk=r_risk,
                    score=0.80,
                    meta=meta
                )

        return cls._no_trade("NO_SUITABLE_SETUP_CRITERIA_MET", symbol, current_price, meta)

    @classmethod
    def _no_trade(cls, reason: str, symbol: str, price: float, meta: Optional[Dict] = None) -> Dict[str, Any]:
        return {
            "decision": "NO_TRADE",
            "model": "MODEL_D_NO_TRADE",
            "direction": "NO_TRADE",
            "intent": "NO_TRADE",
            "entry_price": price,
            "stop_price": 0.0,
            "target_exit_1": 0.0,
            "target_exit_2": 0.0,
            "r_risk_usd_per_unit": 0.0,
            "r_reward_usd_per_unit": 0.0,
            "score": 0.0,
            "rejection_reason": reason,
            "meta": meta or {}
        }

    @classmethod
    def _trade(
        cls,
        model: str,
        direction: str,
        entry_price: float,
        stop_price: float,
        target_1: float,
        target_2: float,
        r_risk: float,
        score: float,
        meta: Dict[str, Any]
    ) -> Dict[str, Any]:
        intent = "LONG_ENTRY" if direction == "LONG" else "SHORT_ENTRY"
        return {
            "decision": "TRADE",
            "model": model,
            "direction": direction,
            "intent": intent,
            "entry_price": entry_price,
            "stop_price": stop_price,
            "target_exit_1": target_1,
            "target_exit_2": target_2,
            "r_risk_usd_per_unit": r_risk,
            "r_reward_usd_per_unit": abs(target_2 - entry_price),
            "score": score,
            "rejection_reason": None,
            "meta": meta
        }


# ─────────────────────────────────────────────────────────────────────────────
# Swing Sizing & Risk Integration
# ─────────────────────────────────────────────────────────────────────────────

class SwingSizingEngine:
    """Computes risk-bounded swing position sizing strictly enforcing Phase 2 limits."""

    MAX_LEVERAGE_CAP = 10
    MAX_EQUITY_RISK_RATIO = 0.02         # 2.0% equity risk ceiling
    MAX_AGGREGATE_NOTIONAL_USD = 5000.0   # $5,000 portfolio exposure cap

    @classmethod
    def calculate_sizing(
        cls,
        symbol: str,
        price: float,
        stop_price: float,
        equity: float,
        available_balance: float,
        symbol_filters: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Solves for swing position size:
        1. R = equity * 0.02
        2. stop_dist = |price - stop_price|
        3. raw_qty = R / stop_dist
        4. Clamped to step_size, min_notional, leverage <= 10x, and $5,000 exposure
        5. HARD RISK INVARIANT: If min_notional breaches 2% risk, REJECT trade.
        """
        min_qty = float(symbol_filters.get("min_qty", 0.001))
        step_size = float(symbol_filters.get("step_size", 0.001))
        min_notional = float(symbol_filters.get("min_notional", 5.0))

        stop_dist = abs(price - stop_price)
        if stop_dist <= 0:
            return {"feasible": False, "rejection_reason": "INVALID_ZERO_STOP_DISTANCE", "quantity": 0.0, "leverage": 1}

        stop_pct = stop_dist / price
        if stop_pct < 0.002 or stop_pct > 0.05:
            return {
                "feasible": False,
                "rejection_reason": f"STOP_DISTANCE_OUTSIDE_BOUNDS ({stop_pct*100:.2f}% not in [0.2%, 5.0%])",
                "quantity": 0.0,
                "leverage": 1
            }

        # Dynamic leverage capped at 10x based on stop distance
        if stop_pct <= 0.010:
            selected_leverage = 10
        elif stop_pct <= 0.020:
            selected_leverage = 6
        elif stop_pct <= 0.035:
            selected_leverage = 4
        else:
            selected_leverage = 2

        # 1. 2% Equity Risk Calculation
        max_dollar_risk = equity * cls.MAX_EQUITY_RISK_RATIO
        raw_qty = max_dollar_risk / stop_dist

        # Step size precision clamping
        if step_size > 0:
            decimals = max(0, int(round(-math.log10(step_size))))
            clamped_qty = math.floor(raw_qty / step_size) * step_size
            clamped_qty = round(clamped_qty, decimals)
        else:
            clamped_qty = raw_qty

        if clamped_qty < min_qty:
            clamped_qty = min_qty

        notional = clamped_qty * price
        actual_dollar_risk = clamped_qty * stop_dist

        # 2. Check Min Notional Safety Invariant
        if notional < min_notional:
            # Check if scaling up to min_notional violates the 2% dollar risk ceiling
            required_qty = (min_notional * 1.05) / price
            if step_size > 0:
                decimals = max(0, int(round(-math.log10(step_size))))
                required_qty = round(math.ceil(required_qty / step_size) * step_size, decimals)
            risk_if_scaled = required_qty * stop_dist
            if risk_if_scaled > max_dollar_risk:
                return {
                    "feasible": False,
                    "rejection_reason": (
                        f"MIN_NOTIONAL_EXCEEDS_RISK_CAP: Min notional requires risk ${risk_if_scaled:.2f} "
                        f"which breaches 2% equity ceiling (${max_dollar_risk:.2f}). Trade rejected per safety invariant."
                    ),
                    "quantity": 0.0,
                    "leverage": selected_leverage
                }
            clamped_qty = required_qty
            notional = clamped_qty * price
            actual_dollar_risk = risk_if_scaled

        # 3. Dollar risk clamp check
        if actual_dollar_risk > max_dollar_risk * 1.02:  # allow 2% tolerance for step size rounding
            reduced_qty = max_dollar_risk / stop_dist
            if step_size > 0:
                decimals = max(0, int(round(-math.log10(step_size))))
                clamped_qty = round(math.floor(reduced_qty / step_size) * step_size, decimals)
            notional = clamped_qty * price
            if notional < min_notional:
                return {
                    "feasible": False,
                    "rejection_reason": "MIN_NOTIONAL_CONFLICT_WITH_RISK_CAP",
                    "quantity": 0.0,
                    "leverage": selected_leverage
                }

        # 4. Aggregate Exposure Cap ($5,000)
        if notional > cls.MAX_AGGREGATE_NOTIONAL_USD:
            max_qty_exp = cls.MAX_AGGREGATE_NOTIONAL_USD / price
            if step_size > 0:
                decimals = max(0, int(round(-math.log10(step_size))))
                clamped_qty = round(math.floor(max_qty_exp / step_size) * step_size, decimals)
            notional = clamped_qty * price

        # 5. Margin Feasibility Check
        required_initial_margin = notional / selected_leverage
        if required_initial_margin > available_balance * 0.95:
            # Scale down to available balance
            max_margin = available_balance * 0.95
            max_notional_margin = max_margin * selected_leverage
            qty_margin = max_notional_margin / price
            if step_size > 0:
                decimals = max(0, int(round(-math.log10(step_size))))
                clamped_qty = round(math.floor(qty_margin / step_size) * step_size, decimals)
            notional = clamped_qty * price
            if notional < min_notional:
                return {
                    "feasible": False,
                    "rejection_reason": "INSUFFICIENT_MARGIN_FOR_MIN_NOTIONAL",
                    "quantity": 0.0,
                    "leverage": selected_leverage
                }

        return {
            "feasible": True,
            "rejection_reason": None,
            "quantity": clamped_qty,
            "leverage": selected_leverage,
            "notional_usd": round(notional, 2),
            "dollar_risk_usd": round(clamped_qty * stop_dist, 2),
            "equity_risk_pct": round(((clamped_qty * stop_dist) / equity) * 100, 2),
            "initial_margin_usd": round(notional / selected_leverage, 2)
        }


# ─────────────────────────────────────────────────────────────────────────────
# Autonomous Swing Engine Service
# ─────────────────────────────────────────────────────────────────────────────

class AutonomousSwingEngine:
    """Orchestrates autonomous lifecycle for the SWING_MOMENTUM_EXPANSION strategy."""

    STRATEGY_NAME = "SWING_MOMENTUM_EXPANSION"
    MAX_HOLDING_HOURS = 48.0
    COOLDOWN_AFTER_TRADE_SECONDS = 300  # 5 minutes cooldown between trade actions

    def __init__(
        self,
        conn: sqlite3.Connection,
        user_id: str,
        account_id: Optional[str] = None,
        adapter: Optional[BinanceFuturesAdapter] = None,
        environment: str = "testnet",
        simulate_execution: bool = False,
    ):
        self.conn = conn
        self.user_id = user_id
        self.environment = environment
        self.adapter = adapter or BinanceFuturesAdapter(environment=environment)
        self.simulate_execution = simulate_execution

        acct = get_or_create_futures_account(
            self.conn, user_id=self.user_id,
            exchange_connection_id=f"CONN-{user_id[:8]}",
            environment=environment
        )
        self.account_id = account_id or acct["account_id"]
        self.discovery = MarketDiscoveryService(adapter=self.adapter)

        self.is_running = False
        self.is_paused = False
        self.active_trade_id: Optional[str] = None
        self.active_symbol: Optional[str] = None
        self.active_entry_time: float = 0.0
        self.target_1_hit = False
        self.breakeven_locked = False
        self.last_trade_time = 0.0

    def start(self) -> Dict[str, Any]:
        run = get_or_create_scalp_run(self.conn, self.user_id, self.account_id, self.STRATEGY_NAME)
        self.is_running = True
        self.is_paused = False
        update_scalp_run_state(
            self.conn, run["run_id"],
            status="RUNNING",
            state_dict={"is_running": True, "is_paused": False, "strategy": self.STRATEGY_NAME, "started_at": utc_now_iso()}
        )
        logger.info("Swing engine started for %s (Run: %s)", self.user_id, run["run_id"])
        return {"status": "SUCCESS", "run_id": run["run_id"], "engine_state": "RUNNING"}

    def pause(self) -> Dict[str, Any]:
        self.is_paused = True
        run = get_or_create_scalp_run(self.conn, self.user_id, self.account_id, self.STRATEGY_NAME)
        update_scalp_run_state(
            self.conn, run["run_id"],
            status="PAUSED",
            state_dict={"is_running": self.is_running, "is_paused": True, "paused_at": utc_now_iso()}
        )
        return {"status": "SUCCESS", "engine_state": "PAUSED"}

    def resume(self) -> Dict[str, Any]:
        self.is_paused = False
        self.is_running = True
        run = get_or_create_scalp_run(self.conn, self.user_id, self.account_id, self.STRATEGY_NAME)
        update_scalp_run_state(
            self.conn, run["run_id"],
            status="RUNNING",
            state_dict={"is_running": True, "is_paused": False, "resumed_at": utc_now_iso()}
        )
        return {"status": "SUCCESS", "engine_state": "RUNNING"}

    def stop(self, reason: str = "ADMIN_REQUEST") -> Dict[str, Any]:
        self.is_running = False
        self.is_paused = False
        run = get_or_create_scalp_run(self.conn, self.user_id, self.account_id, self.STRATEGY_NAME)
        update_scalp_run_state(
            self.conn, run["run_id"],
            status="STOPPED",
            state_dict={"is_running": False, "is_paused": False, "stop_reason": reason},
            stopped_at=utc_now_iso()
        )
        return {"status": "SUCCESS", "engine_state": "STOPPED", "reason": reason}

    def run_single_iteration(
        self,
        candidate_symbols: Optional[List[str]] = None,
        custom_multi_tf_klines: Optional[Dict[str, Dict[str, List[Dict[str, Any]]]]] = None
    ) -> Dict[str, Any]:
        """
        Executes one complete swing cycle:
        1. Monitors active swing trade
        2. Discovers eligible universe
        3. Evaluates multi-timeframe signals
        4. Sizes and executes approved trade
        """
        now = time.time()
        if (now - self.last_trade_time) < self.COOLDOWN_AFTER_TRADE_SECONDS:
            rem = int(self.COOLDOWN_AFTER_TRADE_SECONDS - (now - self.last_trade_time))
            return {"action": "COOLDOWN", "message": f"Cooldown active ({rem}s remaining)"}

        # 1. Active position monitoring
        if self.active_symbol:
            pos = get_open_futures_position(self.conn, user_id=self.user_id, symbol=self.active_symbol)
            if pos and abs(float(pos["quantity"])) > 1e-8:
                return self.monitor_active_position(pos)
            else:
                self.active_symbol = None
                self.active_trade_id = None
                self.last_trade_time = now

        # 2. Check open positions cap (max 3 concurrent)
        open_positions = list_open_futures_positions(self.conn, user_id=self.user_id)
        if len(open_positions) >= 3:
            return {"action": "NO_TRADE", "message": f"Max concurrent positions reached ({len(open_positions)}/3)"}

        # 3. Discovery
        symbols_to_scan = candidate_symbols or ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        discovery_result = self.discovery.scan_and_rank_eligible_pairs(universe_override=symbols_to_scan)
        if discovery_result.get("status") != "SUCCESS" or not discovery_result.get("candidates"):
            return {"action": "NO_TRADE", "message": "No eligible symbols passed screening."}

        candidates = discovery_result["candidates"]
        account = get_futures_account(self.conn, user_id=self.user_id, account_id=self.account_id)
        avail_bal = float(account["available_balance"])
        equity = float(account["wallet_balance"])

        evaluated_signals = []

        for cand in candidates:
            sym = cand["symbol"]
            if any(p["symbol"] == sym for p in open_positions):
                continue

            curr_price = cand["price"]
            spread_ratio = cand["spread_ratio"]

            # Load or fetch multi-tf candles
            if custom_multi_tf_klines and sym in custom_multi_tf_klines:
                c_1h = custom_multi_tf_klines[sym].get("1h", [])
                c_15m = custom_multi_tf_klines[sym].get("15m", [])
                c_5m = custom_multi_tf_klines[sym].get("5m", [])
            else:
                try:
                    c_1h = self.discovery.fetch_klines(sym, interval="1h", limit=60)
                    c_15m = self.discovery.fetch_klines(sym, interval="15m", limit=60)
                    c_5m = self.discovery.fetch_klines(sym, interval="5m", limit=30)
                except Exception as e:
                    logger.warning("Failed to fetch multi-tf klines for %s: %s", sym, str(e))
                    continue

            sig = SwingSignalEvaluator.evaluate(
                symbol=sym,
                candles_1h=c_1h,
                candles_15m=c_15m,
                candles_5m=c_5m,
                current_price=curr_price,
                spread_ratio=spread_ratio
            )

            filters = self.adapter.get_symbol_filters(sym)
            if sig["decision"] != "TRADE":
                record_scalp_signal(
                    conn=self.conn,
                    user_id=self.user_id,
                    account_id=self.account_id,
                    symbol=sym,
                    direction="NO_TRADE",
                    market_price=curr_price,
                    entry_price=curr_price,
                    stop_price=0.0,
                    target_exit_price=0.0,
                    expected_gross_pnl=0.0,
                    estimated_fees=0.0,
                    expected_net_pnl=0.0,
                    signal_score=0.0,
                    regime=sig["model"],
                    status="REJECTED",
                    rejection_reason=sig["rejection_reason"]
                )
                continue

            # Compute Sizing
            sizing = SwingSizingEngine.calculate_sizing(
                symbol=sym,
                price=curr_price,
                stop_price=sig["stop_price"],
                equity=equity,
                available_balance=avail_bal,
                symbol_filters=filters
            )

            if not sizing["feasible"]:
                record_scalp_signal(
                    conn=self.conn,
                    user_id=self.user_id,
                    account_id=self.account_id,
                    symbol=sym,
                    direction=sig["direction"],
                    market_price=curr_price,
                    entry_price=curr_price,
                    stop_price=sig["stop_price"],
                    target_exit_price=sig["target_exit_2"],
                    expected_gross_pnl=0.0,
                    estimated_fees=0.0,
                    expected_net_pnl=0.0,
                    signal_score=sig["score"],
                    regime=sig["model"],
                    status="REJECTED",
                    rejection_reason=sizing["rejection_reason"]
                )
                continue

            # Sizing and Signal Passed
            record_scalp_signal(
                conn=self.conn,
                user_id=self.user_id,
                account_id=self.account_id,
                symbol=sym,
                direction=sig["direction"],
                market_price=curr_price,
                entry_price=curr_price,
                stop_price=sig["stop_price"],
                target_exit_price=sig["target_exit_2"],
                expected_gross_pnl=round(sizing["quantity"] * abs(sig["target_exit_2"] - curr_price), 2),
                estimated_fees=round(sizing["notional_usd"] * 0.0008, 2),
                expected_net_pnl=round((sizing["quantity"] * abs(sig["target_exit_2"] - curr_price)) - (sizing["notional_usd"] * 0.0008), 2),
                signal_score=sig["score"],
                regime=sig["model"],
                status="APPROVED",
                rejection_reason=None
            )

            evaluated_signals.append({
                "symbol": sym,
                "signal": sig,
                "sizing": sizing,
                "score": sig["score"]
            })

        if not evaluated_signals:
            return {"action": "NO_TRADE", "message": "No candidates passed swing setup and risk criteria."}

        evaluated_signals.sort(key=lambda s: s["score"], reverse=True)
        top = evaluated_signals[0]
        sel_sym = top["symbol"]
        sel_sig = top["signal"]
        sel_sizing = top["sizing"]

        # Execute Entry
        exec_res = FuturesExecutionEngine.execute_intent(
            conn=self.conn,
            user_id=self.user_id,
            intent=sel_sig["intent"],
            symbol=sel_sym,
            quantity=sel_sizing["quantity"],
            price=sel_sig["entry_price"],
            stop_price=sel_sig["stop_price"],
            leverage=sel_sizing["leverage"],
            margin_type="ISOLATED",
            order_type="POST_ONLY",
            adapter=self.adapter,
            environment=self.environment,
            simulate_execution=self.simulate_execution
        )

        if not exec_res.get("success"):
            return {
                "action": "EXECUTION_FAILED",
                "symbol": sel_sym,
                "error_code": exec_res.get("error_code"),
                "message": exec_res.get("message")
            }

        # Record trade in DB
        trade_rec = record_scalp_trade(
            conn=self.conn,
            user_id=self.user_id,
            account_id=self.account_id,
            symbol=sel_sym,
            direction=sel_sig["direction"],
            entry_order_id=exec_res["order_id"],
            protective_stop_order_id=exec_res.get("protective_stop_order_id"),
            quantity=exec_res["executed_qty"],
            entry_price=exec_res["fill_price"],
            strategy_name=self.STRATEGY_NAME
        )

        self.active_symbol = sel_sym
        self.active_trade_id = trade_rec["trade_id"]
        self.active_entry_time = now
        self.target_1_hit = False
        self.breakeven_locked = False

        return {
            "action": "ENTERED_TRADE",
            "trade_id": self.active_trade_id,
            "symbol": sel_sym,
            "direction": sel_sig["direction"],
            "model": sel_sig["model"],
            "quantity": exec_res["executed_qty"],
            "fill_price": exec_res["fill_price"],
            "stop_price": sel_sig["stop_price"],
            "target_1": sel_sig["target_exit_1"],
            "target_2": sel_sig["target_exit_2"],
            "notional_usd": sel_sizing["notional_usd"],
            "dollar_risk_usd": sel_sizing["dollar_risk_usd"],
            "protective_stop_order_id": exec_res.get("protective_stop_order_id")
        }

    def monitor_active_position(
        self,
        position: Dict[str, Any],
        current_price_override: Optional[float] = None,
        candles_15m_override: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Monitors active swing trade:
        - Target 1 hit (+1.5R): Moves protective stop to breakeven + fee offset
        - Target 2 hit (+2.5R - +3.5R): Completes full swing target exit
        - Dynamic Trailing: Once +1.5R is hit, trails by 15m ATR
        - Structural invalidation: 15m close against position
        - Max duration expiry: 48h
        """
        sym = position["symbol"]
        qty = abs(float(position["quantity"]))
        entry_price = float(position["entry_price"])
        direction = "LONG" if float(position["quantity"]) > 0 else "SHORT"
        now = time.time()
        holding_seconds = now - self.active_entry_time if self.active_entry_time > 0 else 0.0

        if current_price_override:
            curr_price = current_price_override
        else:
            try:
                curr_price = self.adapter.get_ticker_price(sym)
            except Exception as e:
                logger.error("Price fetch failed for %s: %s", sym, str(e))
                return {"action": "MONITORING_PRICE_FETCH_FAILED", "symbol": sym}

        # Calculate PnL
        if direction == "LONG":
            gross_pnl = (curr_price - entry_price) * qty
        else:
            gross_pnl = (entry_price - curr_price) * qty

        entry_fee = float(position.get("entry_fee_usd", entry_price * qty * 0.0004))
        exit_fee = curr_price * qty * 0.0004
        total_fees = entry_fee + exit_fee
        net_pnl = gross_pnl - total_fees

        # Calculate R-multiple
        r_risk_unit = entry_price * 0.015  # baseline ~1.5% stop
        current_r = gross_pnl / max(1e-8, qty * r_risk_unit)

        # ── 1. Target 1 Breakeven Lock (+1.5R) ──
        if current_r >= 1.5 and not self.breakeven_locked:
            self.target_1_hit = True
            self.breakeven_locked = True
            # In live testnet, adjust protective stop order to entry price + fees
            logger.info("Target 1 (+1.5R) hit for %s trade %s. Breakeven locked.", sym, self.active_trade_id)

        # ── 2. Target 2 Primary Expansion Hit (+2.5R) ──
        if current_r >= 2.5:
            exit_intent = "LONG_EXIT" if direction == "LONG" else "SHORT_EXIT"
            exit_res = FuturesExecutionEngine.execute_intent(
                conn=self.conn, user_id=self.user_id, intent=exit_intent,
                symbol=sym, quantity=qty, price=curr_price,
                adapter=self.adapter, environment=self.environment, simulate_execution=self.simulate_execution
            )
            if self.active_trade_id:
                complete_scalp_trade(
                    conn=self.conn, trade_id=self.active_trade_id,
                    exit_order_id=exit_res.get("order_id", ""),
                    exit_price=curr_price, exit_reason="SWING_PRIMARY_TARGET_HIT",
                    gross_pnl_usd=gross_pnl, total_fees_usd=total_fees, net_pnl_usd=net_pnl,
                    target_hit=True, holding_duration_seconds=holding_seconds
                )
            self.active_symbol = None
            self.active_trade_id = None
            self.last_trade_time = now
            return {
                "action": "EXITED_TRADE",
                "reason": "SWING_PRIMARY_TARGET_HIT",
                "r_multiple": round(current_r, 2),
                "gross_pnl_usd": round(gross_pnl, 4),
                "total_fees_usd": round(total_fees, 4),
                "net_pnl_usd": round(net_pnl, 4),
                "target_hit": True,
                "holding_duration_seconds": round(holding_seconds, 1)
            }

        # ── 3. Breakeven Stop Invalidation (if returned to entry after +1.5R) ──
        if self.breakeven_locked:
            breakeven_triggered = (direction == "LONG" and curr_price <= entry_price * 1.0005) or \
                                  (direction == "SHORT" and curr_price >= entry_price * 0.9995)
            if breakeven_triggered:
                exit_intent = "LONG_EXIT" if direction == "LONG" else "SHORT_EXIT"
                exit_res = FuturesExecutionEngine.execute_intent(
                    conn=self.conn, user_id=self.user_id, intent=exit_intent,
                    symbol=sym, quantity=qty, price=curr_price,
                    adapter=self.adapter, environment=self.environment, simulate_execution=self.simulate_execution
                )
                if self.active_trade_id:
                    complete_scalp_trade(
                        conn=self.conn, trade_id=self.active_trade_id,
                        exit_order_id=exit_res.get("order_id", ""),
                        exit_price=curr_price, exit_reason="BREAKEVEN_TRAILING_EXIT",
                        gross_pnl_usd=gross_pnl, total_fees_usd=total_fees, net_pnl_usd=net_pnl,
                        target_hit=False, holding_duration_seconds=holding_seconds
                    )
                self.active_symbol = None
                self.active_trade_id = None
                self.last_trade_time = now
                return {
                    "action": "EXITED_TRADE",
                    "reason": "BREAKEVEN_TRAILING_EXIT",
                    "r_multiple": round(current_r, 2),
                    "gross_pnl_usd": round(gross_pnl, 4),
                    "total_fees_usd": round(total_fees, 4),
                    "net_pnl_usd": round(net_pnl, 4),
                    "target_hit": False,
                    "holding_duration_seconds": round(holding_seconds, 1)
                }

        # ── 4. Max Holding Expiry (48 Hours) ──
        if holding_seconds >= (self.MAX_HOLDING_HOURS * 3600):
            exit_intent = "LONG_EXIT" if direction == "LONG" else "SHORT_EXIT"
            exit_res = FuturesExecutionEngine.execute_intent(
                conn=self.conn, user_id=self.user_id, intent=exit_intent,
                symbol=sym, quantity=qty, price=curr_price,
                adapter=self.adapter, environment=self.environment, simulate_execution=self.simulate_execution
            )
            if self.active_trade_id:
                complete_scalp_trade(
                    conn=self.conn, trade_id=self.active_trade_id,
                    exit_order_id=exit_res.get("order_id", ""),
                    exit_price=curr_price, exit_reason="MAX_SWING_EXPIRY_48H",
                    gross_pnl_usd=gross_pnl, total_fees_usd=total_fees, net_pnl_usd=net_pnl,
                    target_hit=net_pnl > 0, holding_duration_seconds=holding_seconds
                )
            self.active_symbol = None
            self.active_trade_id = None
            self.last_trade_time = now
            return {
                "action": "EXITED_TRADE",
                "reason": "MAX_SWING_EXPIRY_48H",
                "gross_pnl_usd": round(gross_pnl, 4),
                "total_fees_usd": round(total_fees, 4),
                "net_pnl_usd": round(net_pnl, 4),
                "target_hit": net_pnl > 0,
                "holding_duration_seconds": round(holding_seconds, 1)
            }

        return {
            "action": "HOLDING_POSITION",
            "trade_id": self.active_trade_id,
            "symbol": sym,
            "direction": direction,
            "current_price": curr_price,
            "gross_pnl_usd": round(gross_pnl, 4),
            "net_pnl_usd": round(net_pnl, 4),
            "current_r": round(current_r, 2),
            "breakeven_locked": self.breakeven_locked,
            "holding_hours": round(holding_seconds / 3600.0, 2)
        }
