"""
BITDEX Market Regime Classifier
================================
Analyzes price structure, moving averages, trend strength (ADX),
and ATR volatility percentiles to classify market state.

Regimes:
- TRENDING_UP: Bullish trend structure (favors LONG entries)
- TRENDING_DOWN: Bearish trend structure (favors SHORT entries)
- RANGING_SIDEWAYS: Consolidation / mean-reverting (requires strict bounds)
- HIGH_VOLATILITY: Extreme volatility (tightens risk or forces NO_TRADE)
- LOW_VOLATILITY: Compressed ranges (rejects if $1 net target is unfeasible)
- UNSTABLE: Anomaly spikes, wide spreads, or data gaps (always NO_TRADE)
"""

import math
import logging
from typing import Dict, Any, List

logger = logging.getLogger("bitdex.futures.regime")


class MarketRegimeClassifier:
    """Classifies market regime from recent klines."""

    @classmethod
    def calculate_ema(cls, values: List[float], period: int) -> float:
        """Calculate Exponential Moving Average."""
        if not values:
            return 0.0
        if len(values) < period:
            return sum(values) / len(values)
        multiplier = 2.0 / (period + 1)
        ema = sum(values[:period]) / period
        for val in values[period:]:
            ema = (val - ema) * multiplier + ema
        return ema

    @classmethod
    def calculate_atr(cls, klines: List[Dict[str, Any]], period: int = 14) -> float:
        """Calculate ATR from klines."""
        if len(klines) < 2:
            return 0.0
        trs = []
        for i in range(1, len(klines)):
            h = klines[i]["high"]
            l = klines[i]["low"]
            pc = klines[i - 1]["close"]
            tr = max(h - l, abs(h - pc), abs(l - pc))
            trs.append(tr)
        if not trs:
            return 0.0
        recent = trs[-period:]
        return sum(recent) / len(recent)

    @classmethod
    def calculate_bollinger_bands(cls, values: List[float], period: int = 20, std_dev: float = 2.0) -> tuple:
        """Calculate Bollinger Bands: (lower_band, middle_band, upper_band)."""
        if len(values) < period:
            return 0.0, 0.0, 0.0
        recent = values[-period:]
        sma = sum(recent) / period
        variance = sum((x - sma) ** 2 for x in recent) / period
        std = math.sqrt(variance)
        return round(sma - (std_dev * std), 4), round(sma, 4), round(sma + (std_dev * std), 4)

    @classmethod
    def calculate_adx_estimate(cls, klines: List[Dict[str, Any]], period: int = 14) -> float:
        """
        Estimate Average Directional Index (ADX) from klines.
        Values > 25 indicate strong trend; <= 25 indicates ranging/sideways.
        """
        if len(klines) < period + 2:
            return 20.0  # Default neutral
        
        plus_dm_list = []
        minus_dm_list = []
        tr_list = []

        for i in range(1, len(klines)):
            up_move = klines[i]["high"] - klines[i - 1]["high"]
            down_move = klines[i - 1]["low"] - klines[i]["low"]

            plus_dm = up_move if (up_move > down_move and up_move > 0) else 0.0
            minus_dm = down_move if (down_move > up_move and down_move > 0) else 0.0

            h = klines[i]["high"]
            l = klines[i]["low"]
            pc = klines[i - 1]["close"]
            tr = max(h - l, abs(h - pc), abs(l - pc))

            plus_dm_list.append(plus_dm)
            minus_dm_list.append(minus_dm)
            tr_list.append(tr)

        if not tr_list or sum(tr_list) == 0:
            return 20.0

        sum_tr = sum(tr_list[-period:]) or 1.0
        sum_plus_dm = sum(plus_dm_list[-period:])
        sum_minus_dm = sum(minus_dm_list[-period:])

        plus_di = (sum_plus_dm / sum_tr) * 100.0
        minus_di = (sum_minus_dm / sum_tr) * 100.0
        di_diff = abs(plus_di - minus_di)
        di_sum = (plus_di + minus_di) or 1.0

        dx = (di_diff / di_sum) * 100.0
        return round(dx, 2)

    @classmethod
    def classify(cls, klines: List[Dict[str, Any]], symbol: str = "") -> Dict[str, Any]:
        """
        Classifies regime into:
        TRENDING_UP, TRENDING_DOWN, RANGING_SIDEWAYS, HIGH_VOLATILITY, LOW_VOLATILITY, UNSTABLE.
        """
        if len(klines) < 15:
            return {
                "regime": "UNSTABLE",
                "trade_eligible": False,
                "permitted_directions": [],
                "reason": "INSUFFICIENT_KLINES_FOR_REGIME_CLASSIFICATION",
                "adx": 0.0,
                "atr": 0.0,
                "atr_pct": 0.0,
            }

        closes = [k["close"] for k in klines]
        latest_close = closes[-1]
        latest_kline = klines[-1]

        # 1. Anomaly check: Single 5m candle price movement > 5%
        single_candle_change_pct = abs(latest_kline["high"] - latest_kline["low"]) / latest_kline["low"]
        if single_candle_change_pct > 0.05:
            return {
                "regime": "UNSTABLE",
                "trade_eligible": False,
                "permitted_directions": [],
                "reason": f"ANOMALOUS_CANDLE_SPIKE ({single_candle_change_pct*100:.2f}% > 5.0%)",
                "adx": 0.0,
                "atr": 0.0,
                "atr_pct": single_candle_change_pct * 100,
            }

        # Indicators
        ema9 = cls.calculate_ema(closes, 9)
        ema21 = cls.calculate_ema(closes, 21)
        ema50 = cls.calculate_ema(closes, min(len(closes), 50))
        atr = cls.calculate_atr(klines, 14)
        atr_pct = (atr / latest_close) if latest_close > 0 else 0.0
        adx = cls.calculate_adx_estimate(klines, 14)

        # 2. Extreme Volatility check (ATR% > 3.0% in 5m or ATR% < 0.05%)
        if atr_pct > 0.030:
            return {
                "regime": "HIGH_VOLATILITY",
                "trade_eligible": False,
                "permitted_directions": [],
                "reason": f"EXCESSIVE_VOLATILITY_CIRCUIT_BREAKER (ATR%={atr_pct*100:.2f}% > 3.0%)",
                "adx": adx,
                "atr": round(atr, 4),
                "atr_pct": round(atr_pct * 100, 3),
            }

        if atr_pct < 0.0005:  # Less than 0.05%
            return {
                "regime": "LOW_VOLATILITY",
                "trade_eligible": False,
                "permitted_directions": [],
                "reason": f"VOLATILITY_COMPRESSION_UNFEASIBLE_TARGET (ATR%={atr_pct*100:.3f}% < 0.05%)",
                "adx": adx,
                "atr": round(atr, 4),
                "atr_pct": round(atr_pct * 100, 3),
            }

        # 3. Trending vs Ranging classification
        # Section 3: ADX >= 28.0 required for trending structure
        if adx >= 28.0:
            if ema9 > ema21 and latest_close > ema21:
                return {
                    "regime": "TRENDING_UP",
                    "trade_eligible": True,
                    "permitted_directions": ["LONG"],
                    "reason": "STRONG_BULLISH_TREND_STRUCTURE",
                    "adx": adx,
                    "atr": round(atr, 4),
                    "atr_pct": round(atr_pct * 100, 3),
                    "ema9": round(ema9, 4),
                    "ema21": round(ema21, 4),
                    "ema50": round(ema50, 4),
                }
            elif ema9 < ema21 and latest_close < ema21:
                return {
                    "regime": "TRENDING_DOWN",
                    "trade_eligible": True,
                    "permitted_directions": ["SHORT"],
                    "reason": "STRONG_BEARISH_TREND_STRUCTURE",
                    "adx": adx,
                    "atr": round(atr, 4),
                    "atr_pct": round(atr_pct * 100, 3),
                    "ema9": round(ema9, 4),
                    "ema21": round(ema21, 4),
                    "ema50": round(ema50, 4),
                }

        # Section 3: RANGING_SIDEWAYS - Gated by Bollinger Bands outer edge
        lower_bb, mid_bb, upper_bb = cls.calculate_bollinger_bands(closes, 20, 2.0)
        band_width = upper_bb - lower_bb
        dist_ratio = (latest_close - lower_bb) / band_width if band_width > 0 else 0.5

        if band_width > 0 and dist_ratio <= 0.25:
            return {
                "regime": "RANGING_SIDEWAYS",
                "trade_eligible": True,
                "permitted_directions": ["LONG"],
                "reason": f"RANGING_OVERSOLD_MEAN_REVERSION (DistRatio={dist_ratio:.2f} <= 0.25)",
                "adx": adx,
                "atr": round(atr, 4),
                "atr_pct": round(atr_pct * 100, 3),
                "ema9": round(ema9, 4),
                "ema21": round(ema21, 4),
                "ema50": round(ema50, 4),
                "bollinger_lower": lower_bb,
                "bollinger_middle": mid_bb,
                "bollinger_upper": upper_bb,
            }
        elif band_width > 0 and dist_ratio >= 0.75:
            return {
                "regime": "RANGING_SIDEWAYS",
                "trade_eligible": True,
                "permitted_directions": ["SHORT"],
                "reason": f"RANGING_OVERBOUGHT_MEAN_REVERSION (DistRatio={dist_ratio:.2f} >= 0.75)",
                "adx": adx,
                "atr": round(atr, 4),
                "atr_pct": round(atr_pct * 100, 3),
                "ema9": round(ema9, 4),
                "ema21": round(ema21, 4),
                "ema50": round(ema50, 4),
                "bollinger_lower": lower_bb,
                "bollinger_middle": mid_bb,
                "bollinger_upper": upper_bb,
            }
        else:
            return {
                "regime": "RANGING_SIDEWAYS",
                "trade_eligible": False,
                "permitted_directions": [],
                "reason": f"RANGING_CHOP_MIDDLE_BAND (DistRatio={dist_ratio:.2f} in 0.25-0.75)",
                "adx": adx,
                "atr": round(atr, 4),
                "atr_pct": round(atr_pct * 100, 3),
                "ema9": round(ema9, 4),
                "ema21": round(ema21, 4),
                "ema50": round(ema50, 4),
                "bollinger_lower": lower_bb,
                "bollinger_middle": mid_bb,
                "bollinger_upper": upper_bb,
            }
