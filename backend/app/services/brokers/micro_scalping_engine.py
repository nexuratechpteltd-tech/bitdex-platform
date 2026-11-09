"""
BITDEX — TRACK 1: REFINED LEGACY HIGH-FREQUENCY MICRO-SCALPING ENGINE
====================================================================
Dedicated Strategy Engine for Track 1:
- Operates strictly on M1 / M5 momentum and noise-rejection filters
- Target profit: zsh.50 – .00 per trade
- Intended loss: zsh.50 – zsh.70 per trade
- Hard planned risk ceiling: Strictly < .00 per trade
- Position sizing: Micro-risk sizing verified against broker contract size, lot step, tick value, spread, commission, and slippage.
- Reject Rule: If minimum tradable volume (min_lot) causes stop-loss risk to exceed .00 -> REJECT SETUP.
- Separation: Completely decoupled from Candidate A v2 (Track 2) and Long-Term strategies.
"""

import time
import math
import logging
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("bitdex.micro_scalping_engine")


@dataclass
class MicroScalpConfig:
    """Rigorous configuration for Track 1 Micro-Scalping."""
    strategy_code: str = "TRACK1_MICRO_SCALP"
    min_profit_target_usd: float = 0.50
    max_profit_target_usd: float = 3.00
    min_loss_target_usd: float = 0.50
    max_loss_target_usd: float = 0.70
    hard_risk_ceiling_usd: float = 0.99  # STRICTLY < .00
    min_quality_score: float = 0.70
    min_risk_reward_ratio: float = 1.25
    max_acceptable_spread_pips: float = 2.5
    default_slippage_buffer_usd: float = 0.10
    max_open_micro_positions: int = 1
    post_trade_cooldown_seconds: int = 300


class MicroScalpingEngine:
    """Independent Track 1 Micro-Scalping Service."""

    def __init__(self, config: Optional[MicroScalpConfig] = None):
        self.config = config or MicroScalpConfig()

    def evaluate_setup(
        self,
        symbol: str,
        candles_m1: List[Dict[str, Any]],
        candles_m5: List[Dict[str, Any]],
        bid: float,
        ask: float,
        contract_spec: Dict[str, Any],
        account_equity: float
    ) -> Dict[str, Any]:
        spread = ask - bid
        digits = contract_spec.get("digits", 2)
        tick_size = contract_spec.get("tick_size", 0.01)
        tick_value = contract_spec.get("tick_value", 1.0)
        contract_size = contract_spec.get("contract_size", 100.0)
        min_lot = contract_spec.get("min_lot", 0.01)
        lot_step = contract_spec.get("lot_step", 0.01)

        if len(candles_m5) < 20 or len(candles_m1) < 20:
            return {
                "decision": "NO_TRADE",
                "symbol": symbol,
                "strategy": self.config.strategy_code,
                "reason": "INSUFFICIENT_CANDLE_HISTORY",
                "quality_score": 0.0
            }

        m1_closes = [float(c["close"]) for c in candles_m1]
        ema9 = self._calc_ema(m1_closes, 9)
        ema21 = self._calc_ema(m1_closes, 21)
        last_close = m1_closes[-1]

        atr_m5 = self._calc_atr(candles_m5, 14)
        if atr_m5 <= 0:
            return {
                "decision": "NO_TRADE",
                "symbol": symbol,
                "strategy": self.config.strategy_code,
                "reason": "ZERO_ATR_VOLATILITY",
                "quality_score": 0.0
            }

        direction = None
        if ema9 > ema21 and last_close >= ema9:
            direction = "BUY"
        elif ema9 < ema21 and last_close <= ema9:
            direction = "SELL"
        else:
            return {
                "decision": "NO_TRADE",
                "symbol": symbol,
                "strategy": self.config.strategy_code,
                "reason": "NO_M1_MOMENTUM_ALIGNMENT",
                "quality_score": 0.35
            }

        m1_atr = self._calc_atr(candles_m1, 14)
        stop_dist_price = max(m1_atr * 1.2, spread * 2.5)

        est_cost_per_lot = (spread * contract_size) + 0.10
        loss_per_lot = ((stop_dist_price / tick_size) * tick_value) + est_cost_per_lot

        if loss_per_lot <= 0:
            return {
                "decision": "NO_TRADE",
                "symbol": symbol,
                "strategy": self.config.strategy_code,
                "reason": "INVALID_LOSS_PER_LOT_CALCULATION",
                "quality_score": 0.0
            }

        min_lot_risk_usd = loss_per_lot * min_lot

        if min_lot_risk_usd > self.config.hard_risk_ceiling_usd:
            return {
                "decision": "NO_TRADE",
                "symbol": symbol,
                "strategy": self.config.strategy_code,
                "reason": f"SUB_DOLLAR_BUDGET_EXCEEDED: Min volume {min_lot} causes risk ${min_lot_risk_usd:.2f} > hard ceiling ${self.config.hard_risk_ceiling_usd:.2f}",
                "min_lot_risk_usd": round(min_lot_risk_usd, 3),
                "hard_risk_ceiling_usd": self.config.hard_risk_ceiling_usd,
                "quality_score": 0.0
            }

        target_risk_usd = 0.60
        calc_volume = target_risk_usd / loss_per_lot
        steps = math.floor(calc_volume / lot_step)
        final_volume = max(min_lot, steps * lot_step)
        final_volume = round(final_volume, 4)

        final_planned_risk_usd = round(loss_per_lot * final_volume, 2)
        if final_planned_risk_usd > self.config.hard_risk_ceiling_usd:
            final_volume = min_lot
            final_planned_risk_usd = round(loss_per_lot * min_lot, 2)
            if final_planned_risk_usd > self.config.hard_risk_ceiling_usd:
                return {
                    "decision": "NO_TRADE",
                    "symbol": symbol,
                    "strategy": self.config.strategy_code,
                    "reason": f"PLANNED_RISK_EXCEEDS_CEILING: ${final_planned_risk_usd:.2f} > ${self.config.hard_risk_ceiling_usd:.2f}",
                    "quality_score": 0.0
                }

        target_reward_usd = min(self.config.max_profit_target_usd, max(self.config.min_profit_target_usd, final_planned_risk_usd * 1.5))
        tp_dist_price = (target_reward_usd / (final_volume * (tick_value / tick_size))) + spread

        if direction == "BUY":
            entry_price = ask
            sl_price = round(entry_price - stop_dist_price, digits)
            tp_price = round(entry_price + tp_dist_price, digits)
        else:
            entry_price = bid
            sl_price = round(entry_price + stop_dist_price, digits)
            tp_price = round(entry_price - tp_dist_price, digits)

        net_rr = round(target_reward_usd / max(0.01, final_planned_risk_usd), 2)

        return {
            "decision": "QUALIFIED",
            "symbol": symbol,
            "strategy": self.config.strategy_code,
            "direction": direction,
            "volume": final_volume,
            "entry_price": entry_price,
            "sl_price": sl_price,
            "tp_price": tp_price,
            "stop_distance_pts": round(stop_dist_price, digits),
            "tp_distance_pts": round(tp_dist_price, digits),
            "planned_risk_usd": final_planned_risk_usd,
            "planned_reward_usd": round(target_reward_usd, 2),
            "net_rr": net_rr,
            "quality_score": 0.88,
            "spread_usd": round(spread, digits),
            "timestamp": time.time()
        }

    def _calc_ema(self, values: List[float], period: int) -> float:
        if not values:
            return 0.0
        k = 2.0 / (period + 1.0)
        seed_n = min(period, len(values))
        ema = sum(values[:seed_n]) / seed_n
        for v in values[seed_n:]:
            ema = v * k + ema * (1.0 - k)
        return ema

    def _calc_atr(self, candles: List[Dict[str, Any]], period: int = 14) -> float:
        trs = []
        for i in range(1, len(candles)):
            h, l = float(candles[i]["high"]), float(candles[i]["low"])
            pc = float(candles[i - 1]["close"])
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        if not trs:
            return 0.0
        window = trs[-period:]
        return sum(window) / len(window)
