"""
BITDEX Candidate A: Hierarchical Multi-Timeframe Trend Pullback Strategy (Phases 1 & 2)
======================================================================================
Strict non-compensatory hierarchical strategy replacing legacy additive scoring.

Hierarchy:
1. H1 (Overall Trend):
   - BUY: EMA21 > EMA50, positive slope, established trend
   - SELL: EMA21 < EMA50, negative slope, established trend
   - Flat/conflicting -> NO TRADE
2. M15 (Market Structure):
   - BUY: Price strictly above M15 EMA50
   - SELL: Price strictly below M15 EMA50
   - Failure -> NO TRADE
3. M5 (Execution & Value Zone Confirmation - MANDATORY):
   - BUY: M5 EMA9 > EMA21; completed candle touched value zone and formed bullish rejection; not extended
   - SELL: M5 EMA9 < EMA21; completed candle touched value zone and formed bearish rejection; not extended
   - Failure -> NO TRADE (Strict veto; higher timeframes CANNOT override)
4. Dynamic Volatility Stops & Risk Sizing:
   - SL = max(1.5 * M5_ATR, swing_structure_distance)
   - TP >= 1.5:1 reward-to-risk after spread and slippage
   - If minimum lot (0.01) risk exceeds approved risk budget -> ERR_MIN_LOT_EXCEEDS_BUDGET (NO TRADE)
"""

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


def calc_ema(values: List[float], period: int) -> float:
    if not values:
        return 0.0
    if len(values) < period:
        return sum(values) / len(values)
    k = 2.0 / (period + 1.0)
    ema = values[0]
    for v in values[1:]:
        ema = (v * k) + (ema * (1.0 - k))
    return ema


def calc_atr(candles: List[Dict[str, Any]], period: int = 14) -> float:
    if len(candles) < 2:
        return 2.0  # Safe default for Gold
    trs = []
    for i in range(1, len(candles)):
        h = float(candles[i]["high"])
        l = float(candles[i]["low"])
        prev_c = float(candles[i - 1]["close"])
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr)
    if not trs:
        return 2.0
    if len(trs) < period:
        return sum(trs) / len(trs)
    return sum(trs[-period:]) / float(period)


def get_closed_candles(candles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Returns only completed candles.
    Filters out any bar explicitly marked as unclosed (`is_closed=False` or `closed=False`).
    If no explicit flag is present, conservatively excludes the last active bar.
    """
    if not candles:
        return []
    has_flag = any("is_closed" in c or "closed" in c for c in candles)
    if has_flag:
        return [c for c in candles if c.get("is_closed", c.get("closed", True)) is not False]
    if len(candles) <= 1:
        return candles
    return candles[:-1]


class CandidateAStrategy:
    """
    Hierarchical Trend Pullback Strategy with strict veto gating.
    """

    @classmethod
    def evaluate(
        cls,
        h1_candles: List[Dict[str, Any]],
        m15_candles: List[Dict[str, Any]],
        m5_candles: List[Dict[str, Any]],
        current_bid: float,
        current_ask: float,
        approved_risk_budget_usd: float,
        account_equity: float,
        spec: Optional[Dict[str, Any]] = None,
        estimated_slippage_pts: float = 0.15,
    ) -> Dict[str, Any]:
        """
        Executes Candidate A evaluation.
        Returns a structured dictionary with outcome: 'BUY', 'SELL', or 'NO_TRADE'.
        """
        spec = spec or {}
        contract_size = float(spec.get("contract_size") or 100.0)
        digits = int(spec.get("digits", 3))
        min_volume = float(spec.get("min_volume") or 0.01)
        volume_step = float(spec.get("volume_step") or 0.01)

        spread = round(current_ask - current_bid, digits)
        mid_price = (current_bid + current_ask) / 2.0

        # Extract strictly completed candles
        closed_h1 = get_closed_candles(h1_candles)
        closed_m15 = get_closed_candles(m15_candles)
        closed_m5 = get_closed_candles(m5_candles)

        if len(closed_h1) < 25 or len(closed_m15) < 25 or len(closed_m5) < 20:
            return {
                "outcome": "NO_TRADE",
                "direction": "NONE",
                "error_code": "INSUFFICIENT_HISTORICAL_DATA",
                "detail": f"Insufficient completed candles: H1={len(closed_h1)}, M15={len(closed_m15)}, M5={len(closed_m5)} (min 25/25/20 required)",
                "passed_gates": [],
                "failed_gate": "DATA_COMPLETENESS",
            }

        # ─── GATE 1: H1 Trend Direction ───────────────────────────────────────────
        h1_closes = [float(c["close"]) for c in closed_h1]
        h1_ema21 = calc_ema(h1_closes, 21)
        h1_ema50 = calc_ema(h1_closes, 50)
        h1_ema21_prev = calc_ema(h1_closes[:-1], 21)

        h1_slope = (h1_ema21 - h1_ema21_prev) / h1_ema21_prev if h1_ema21_prev > 0 else 0.0
        h1_slope_pct = h1_slope * 100.0

        h1_trend: str = "FLAT"
        if h1_ema21 > h1_ema50 and h1_slope > 0:
            h1_trend = "BULLISH"
        elif h1_ema21 < h1_ema50 and h1_slope < 0:
            h1_trend = "BEARISH"
        else:
            return {
                "outcome": "NO_TRADE",
                "direction": "NONE",
                "error_code": "H1_TREND_NOT_ESTABLISHED",
                "detail": f"H1 trend is flat or conflicting (EMA21={h1_ema21:.3f}, EMA50={h1_ema50:.3f}, slope={h1_slope_pct:+.4f}%).",
                "passed_gates": [],
                "failed_gate": "H1_TREND",
                "telemetry": {
                    "h1_ema21": h1_ema21, "h1_ema50": h1_ema50, "h1_slope": h1_slope,
                }
            }

        candidate_direction = "BUY" if h1_trend == "BULLISH" else "SELL"

        # ─── GATE 2: M15 Market Structure ─────────────────────────────────────────
        m15_closes = [float(c["close"]) for c in closed_m15]
        m15_ema50 = calc_ema(m15_closes, 50)
        m15_last_close = m15_closes[-1]

        if candidate_direction == "BUY" and m15_last_close <= m15_ema50:
            return {
                "outcome": "NO_TRADE",
                "direction": "NONE",
                "error_code": "M15_MARKET_STRUCTURE_BEARISH",
                "detail": f"M15 structure fails: Last close ({m15_last_close:.3f}) is below M15 EMA50 ({m15_ema50:.3f}) for BUY setup.",
                "passed_gates": ["H1_TREND"],
                "failed_gate": "M15_STRUCTURE",
                "telemetry": {"h1_trend": h1_trend, "m15_ema50": m15_ema50, "m15_last_close": m15_last_close}
            }
        elif candidate_direction == "SELL" and m15_last_close >= m15_ema50:
            return {
                "outcome": "NO_TRADE",
                "direction": "NONE",
                "error_code": "M15_MARKET_STRUCTURE_BULLISH",
                "detail": f"M15 structure fails: Last close ({m15_last_close:.3f}) is above M15 EMA50 ({m15_ema50:.3f}) for SELL setup.",
                "passed_gates": ["H1_TREND"],
                "failed_gate": "M15_STRUCTURE",
                "telemetry": {"h1_trend": h1_trend, "m15_ema50": m15_ema50, "m15_last_close": m15_last_close}
            }

        # ─── GATE 3: M5 Execution & Value Zone Confirmation (MANDATORY) ───────────
        m5_closes = [float(c["close"]) for c in closed_m5]
        m5_highs = [float(c["high"]) for c in closed_m5]
        m5_lows = [float(c["low"]) for c in closed_m5]
        m5_opens = [float(c["open"]) for c in closed_m5]

        m5_ema9 = calc_ema(m5_closes, 9)
        m5_ema21 = calc_ema(m5_closes, 21)
        atr_m5 = calc_atr(closed_m5, 14)

        vz_top = max(m5_ema9, m5_ema21)
        vz_bottom = min(m5_ema9, m5_ema21)

        # Mandatory M5 EMA alignment check (strict veto)
        if candidate_direction == "BUY" and m5_ema9 <= m5_ema21:
            return {
                "outcome": "NO_TRADE",
                "direction": "NONE",
                "error_code": "M5_DOWNTREND_ACTIVE_EMA9_BELOW_EMA21",
                "detail": f"M5 execution veto: M5 EMA9 ({m5_ema9:.3f}) <= EMA21 ({m5_ema21:.3f}). Counter-trend BUY forbidden.",
                "passed_gates": ["H1_TREND", "M15_STRUCTURE"],
                "failed_gate": "M5_EMA_ALIGNMENT",
                "telemetry": {"m5_ema9": m5_ema9, "m5_ema21": m5_ema21, "atr_m5": atr_m5}
            }
        elif candidate_direction == "SELL" and m5_ema9 >= m5_ema21:
            return {
                "outcome": "NO_TRADE",
                "direction": "NONE",
                "error_code": "M5_UPTREND_ACTIVE_EMA9_ABOVE_EMA21",
                "detail": f"M5 execution veto: M5 EMA9 ({m5_ema9:.3f}) >= EMA21 ({m5_ema21:.3f}). Counter-trend SELL forbidden.",
                "passed_gates": ["H1_TREND", "M15_STRUCTURE"],
                "failed_gate": "M5_EMA_ALIGNMENT",
                "telemetry": {"m5_ema9": m5_ema9, "m5_ema21": m5_ema21, "atr_m5": atr_m5}
            }

        # Check pullback to value zone in the last 3 completed M5 candles
        recent_lows = m5_lows[-3:]
        recent_highs = m5_highs[-3:]

        touched_value_zone = False
        if candidate_direction == "BUY":
            # Price must have pulled back into or through the value zone
            touched_value_zone = min(recent_lows) <= (vz_top + 0.25 * atr_m5)
        else:
            touched_value_zone = max(recent_highs) >= (vz_bottom - 0.25 * atr_m5)

        if not touched_value_zone:
            return {
                "outcome": "NO_TRADE",
                "direction": "NONE",
                "error_code": "M5_NO_VALUE_ZONE_PULLBACK",
                "detail": f"M5 pullback missing: Price has not retraced to EMA9-EMA21 value zone [{vz_bottom:.2f} - {vz_top:.2f}].",
                "passed_gates": ["H1_TREND", "M15_STRUCTURE", "M5_EMA_ALIGNMENT"],
                "failed_gate": "M5_VALUE_ZONE_PULLBACK",
                "telemetry": {"vz_bottom": vz_bottom, "vz_top": vz_top, "atr_m5": atr_m5}
            }

        # Completed trigger candle rejection confirmation
        trigger_bar = closed_m5[-1]
        t_open = float(trigger_bar["open"])
        t_high = float(trigger_bar["high"])
        t_low = float(trigger_bar["low"])
        t_close = float(trigger_bar["close"])
        t_body = abs(t_close - t_open)
        t_range = max(0.01, t_high - t_low)

        rejection_confirmed = False
        if candidate_direction == "BUY":
            lower_wick = min(t_open, t_close) - t_low
            is_bullish_body = t_close > t_open
            has_long_lower_wick = lower_wick >= 0.40 * t_range
            closed_in_upper_half = t_close >= (t_low + 0.50 * t_range)
            rejection_confirmed = (is_bullish_body or has_long_lower_wick) and closed_in_upper_half
        else:
            upper_wick = t_high - max(t_open, t_close)
            is_bearish_body = t_close < t_open
            has_long_upper_wick = upper_wick >= 0.40 * t_range
            closed_in_lower_half = t_close <= (t_low + 0.50 * t_range)
            rejection_confirmed = (is_bearish_body or has_long_upper_wick) and closed_in_lower_half

        if not rejection_confirmed:
            return {
                "outcome": "NO_TRADE",
                "direction": "NONE",
                "error_code": "M5_CANDLE_REJECTION_NOT_CONFIRMED",
                "detail": f"Completed M5 candle does not confirm rejection at value zone (open={t_open:.2f}, high={t_high:.2f}, low={t_low:.2f}, close={t_close:.2f}).",
                "passed_gates": ["H1_TREND", "M15_STRUCTURE", "M5_EMA_ALIGNMENT", "M5_VALUE_ZONE_PULLBACK"],
                "failed_gate": "M5_CANDLE_REJECTION",
                "telemetry": {"trigger_candle": trigger_bar}
            }

        # Extension check: entry not excessively extended from value zone
        entry_est = current_ask if candidate_direction == "BUY" else current_bid
        if candidate_direction == "BUY" and (entry_est - vz_top) > (1.5 * atr_m5):
            return {
                "outcome": "NO_TRADE",
                "direction": "NONE",
                "error_code": "M5_ENTRY_EXCESSIVELY_EXTENDED",
                "detail": f"Entry price ({entry_est:.2f}) is overextended from EMA9 ({vz_top:.2f}) by > 1.5x ATR.",
                "passed_gates": ["H1_TREND", "M15_STRUCTURE", "M5_EMA_ALIGNMENT", "M5_VALUE_ZONE_PULLBACK", "M5_CANDLE_REJECTION"],
                "failed_gate": "M5_EXTENSION",
                "telemetry": {"entry_est": entry_est, "vz_top": vz_top, "atr_m5": atr_m5}
            }
        elif candidate_direction == "SELL" and (vz_bottom - entry_est) > (1.5 * atr_m5):
            return {
                "outcome": "NO_TRADE",
                "direction": "NONE",
                "error_code": "M5_ENTRY_EXCESSIVELY_EXTENDED",
                "detail": f"Entry price ({entry_est:.2f}) is overextended from EMA9 ({vz_bottom:.2f}) by > 1.5x ATR.",
                "passed_gates": ["H1_TREND", "M15_STRUCTURE", "M5_EMA_ALIGNMENT", "M5_VALUE_ZONE_PULLBACK", "M5_CANDLE_REJECTION"],
                "failed_gate": "M5_EXTENSION",
                "telemetry": {"entry_est": entry_est, "vz_bottom": vz_bottom, "atr_m5": atr_m5}
            }

        # ─── GATE 4: Dynamic Stop Loss & Take Profit Calculation ──────────────────
        lookback = min(15, len(closed_m5))
        swing_buffer = 0.30 * atr_m5

        if candidate_direction == "BUY":
            swing_low = min(m5_lows[-lookback:])
            swing_distance = max(0.5, (entry_est - swing_low) + swing_buffer)
            atr_stop_distance = 1.50 * atr_m5
            sl_distance = max(atr_stop_distance, swing_distance)
            sl_distance = max(sl_distance, 1.50 * atr_m5)  # Enforce at least 1.5x ATR
            sl_price = round(entry_est - sl_distance, digits)

            # Minimum 1.5:1 reward-to-risk after spread and slippage
            friction_pts = spread + estimated_slippage_pts
            net_sl_distance = sl_distance + friction_pts
            tp_distance = round(1.50 * net_sl_distance + friction_pts, digits)
            tp_price = round(entry_est + tp_distance, digits)
        else:
            swing_high = max(m5_highs[-lookback:])
            swing_distance = max(0.5, (swing_high - entry_est) + swing_buffer)
            atr_stop_distance = 1.50 * atr_m5
            sl_distance = max(atr_stop_distance, swing_distance)
            sl_distance = max(sl_distance, 1.50 * atr_m5)  # Enforce at least 1.5x ATR
            sl_price = round(entry_est + sl_distance, digits)

            friction_pts = spread + estimated_slippage_pts
            net_sl_distance = sl_distance + friction_pts
            tp_distance = round(1.50 * net_sl_distance + friction_pts, digits)
            tp_price = round(entry_est - tp_distance, digits)

        reward_risk_ratio = round(tp_distance / sl_distance, 2)

        # ─── GATE 5: Risk Feasibility & Position Sizing ───────────────────────────
        friction_total_pts = sl_distance + spread + estimated_slippage_pts
        risk_per_min_lot_usd = friction_total_pts * min_volume * contract_size

        if risk_per_min_lot_usd > approved_risk_budget_usd:
            return {
                "outcome": "NO_TRADE",
                "direction": candidate_direction,
                "error_code": "ERR_MIN_LOT_EXCEEDS_BUDGET",
                "detail": (
                    f"Minimum lot ({min_volume} lots) monetary risk (${risk_per_min_lot_usd:.2f} USD) "
                    f"exceeds approved risk budget (${approved_risk_budget_usd:.2f} USD). "
                    f"SL distance ({sl_distance:.2f} pts = {sl_distance / atr_m5:.2f}x ATR) cannot be safely compressed."
                ),
                "passed_gates": [
                    "H1_TREND", "M15_STRUCTURE", "M5_EMA_ALIGNMENT",
                    "M5_VALUE_ZONE_PULLBACK", "M5_CANDLE_REJECTION", "M5_EXTENSION", "DYNAMIC_STOPS"
                ],
                "failed_gate": "RISK_BUDGET_FEASIBILITY",
                "risk_feasibility": {
                    "approved_risk_budget_usd": approved_risk_budget_usd,
                    "risk_per_min_lot_usd": risk_per_min_lot_usd,
                    "min_volume": min_volume,
                    "sl_distance": sl_distance,
                    "atr_m5": atr_m5,
                }
            }

        # Calculate volume rounded down to volume_step
        raw_volume = approved_risk_budget_usd / (friction_total_pts * contract_size)
        volume = math.floor(raw_volume / volume_step) * volume_step
        volume = round(max(min_volume, volume), 2)
        total_monetary_risk_usd = round(friction_total_pts * volume * contract_size, 2)

        trigger_time = trigger_bar.get("time") or trigger_bar.get("timestamp") or 0

        return {
            "outcome": candidate_direction,
            "direction": candidate_direction,
            "error_code": None,
            "detail": f"Qualified Candidate A {candidate_direction} pullback setup.",
            "passed_gates": [
                "H1_TREND", "M15_STRUCTURE", "M5_EMA_ALIGNMENT",
                "M5_VALUE_ZONE_PULLBACK", "M5_CANDLE_REJECTION", "M5_EXTENSION",
                "DYNAMIC_STOPS", "RISK_BUDGET_FEASIBILITY"
            ],
            "failed_gate": None,
            "order_parameters": {
                "direction": candidate_direction,
                "entry_price": entry_est,
                "sl_price": sl_price,
                "tp_price": tp_price,
                "sl_distance_pts": sl_distance,
                "tp_distance_pts": tp_distance,
                "volume": volume,
                "spread_pts": spread,
                "atr_m5": atr_m5,
                "sl_atr_ratio": round(sl_distance / atr_m5, 2),
                "reward_risk_ratio": reward_risk_ratio,
                "estimated_friction_pts": friction_pts,
                "total_monetary_risk_usd": total_monetary_risk_usd,
                "approved_risk_budget_usd": approved_risk_budget_usd,
                "trigger_candle_time": trigger_time,
            },
            "telemetry": {
                "h1_ema21": h1_ema21, "h1_ema50": h1_ema50, "h1_slope": h1_slope,
                "m15_ema50": m15_ema50, "m15_close": m15_last_close,
                "m5_ema9": m5_ema9, "m5_ema21": m5_ema21, "atr_m5": atr_m5,
            }
        }
