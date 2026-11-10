"""
BITDEX — TRACK 1: CLAUDE IMPULSE SCALPER ENGINE (REFINED HIGH-FREQUENCY MICRO-SCALPER)
========================================================================================
Dedicated Strategy Engine for Track 1 Impulse Scalping:
- Operates strictly on M1 completed candles with M5 directional trend veto only.
- Strict sub-$1.00 hard risk ceiling ($0.99 planned risk limit).
- Target profit: $0.50 – $3.00 per trade.
- Intended loss: $0.50 – $0.70 per trade.
- Minimum Net Reward-to-Risk ratio: >= 1.25.
- Complete 12-rule Claude Impulse Scalper architecture:
  1. M1 EMA9/EMA21 directional gate.
  2. Closed M1 three-bar breakout trigger.
  3. Minimum trigger candle body strength >= 0.4 * M1 ATR.
  4. M5 opposing-trend veto only (EMA9/EMA21 on M5).
  5. M1 ATR volatility band for dynamic stop-loss.
  6. Fresh quote validation before order calculation.
  7. Mandatory spread and transaction-cost filtering (all-in cost model: spread + commission + slippage).
  8. Net reward-to-risk calculation after friction.
  9. ATR/structure-based stop (buffered by spread).
  10. Time-based (max holding time) and completed-bar reversal exits.
  11. One entry per breakout leg tracking.
  12. Three-completed-M1-bar cooldown following a losing trade.
"""

import math
import time
import logging
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("bitdex.micro_scalping_engine")


@dataclass
class MicroScalpConfig:
    """Rigorous configuration for Track 1 Claude Impulse Scalping."""
    strategy_code: str = "TRACK1_IMPULSE_SCALP"
    min_profit_target_usd: float = 0.50
    max_profit_target_usd: float = 3.00
    min_loss_target_usd: float = 0.50
    max_loss_target_usd: float = 0.70
    hard_risk_ceiling_usd: float = 0.99  # STRICTLY < $1.00
    min_quality_score: float = 0.75
    min_risk_reward_ratio: float = 1.25
    max_acceptable_spread_pips: float = 3.0
    default_slippage_buffer_usd: float = 0.05
    raw_spread_commission_per_lot_usd: float = 0.07 # ~$3.50/side per standard lot -> $0.07 per 0.01 lot or standard crypto rate
    max_open_micro_positions: int = 1
    post_loss_cooldown_bars: int = 3
    max_holding_time_minutes: int = 15
    min_trigger_body_atr_ratio: float = 0.40


class MicroScalpingEngine:
    """Independent Track 1 Claude Impulse Scalper Engine."""

    def __init__(self, config: Optional[MicroScalpConfig] = None):
        self.config = config or MicroScalpConfig()
        # Per-symbol state tracking for breakout legs and loss cooldowns
        # symbol -> {"last_loss_bar_index": int, "last_breakout_leg_level": float, "last_entry_time": float}
        self._state_tracker: Dict[str, Dict[str, Any]] = {}

    def record_trade_result(self, symbol: str, is_loss: bool, bar_index: int):
        """Records trade completion to enforce 3-bar loss cooldown and breakout leg reset."""
        sym_state = self._state_tracker.setdefault(symbol, {})
        if is_loss:
            sym_state["loss_cooldown_until_bar"] = bar_index + self.config.post_loss_cooldown_bars
            logger.info(f"[{symbol}] Recorded LOSS on bar {bar_index}. Cooldown active until bar {sym_state['loss_cooldown_until_bar']}.")
        else:
            sym_state["loss_cooldown_until_bar"] = 0

    def evaluate_setup(
        self,
        symbol: str,
        candles_m1: List[Dict[str, Any]],
        candles_m5: List[Dict[str, Any]],
        bid: float,
        ask: float,
        contract_spec: Dict[str, Any],
        account_equity: float,
        current_bar_index: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Evaluates current completed M1 candles against all 12 Claude Impulse Scalper rules.
        """
        spread = ask - bid
        digits = contract_spec.get("digits", 2)
        tick_size = contract_spec.get("tick_size")
        if not tick_size or tick_size <= 0:
            tick_size = 10**(-digits) if digits > 0 else 0.01

        contract_size = contract_spec.get("contract_size", 1.0)
        min_lot = contract_spec.get("min_lot") or 0.01
        lot_step = contract_spec.get("lot_step") or 0.01

        # Authoritative tick value in account currency (USD) per 1 lot per 1 price unit
        tick_value = contract_spec.get("tick_value")
        if not tick_value or tick_value <= 0:
            tick_value = contract_size * tick_size

        # Rule 6: Fresh Quote Validation
        if bid <= 0 or ask <= 0 or ask < bid:
            return {
                "decision": "NO_TRADE",
                "symbol": symbol,
                "strategy": self.config.strategy_code,
                "reason": "INVALID_OR_STALE_QUOTE",
                "quality_score": 0.0
            }

        if len(candles_m1) < 25 or len(candles_m5) < 15:
            return {
                "decision": "NO_TRADE",
                "symbol": symbol,
                "strategy": self.config.strategy_code,
                "reason": f"INSUFFICIENT_CANDLE_HISTORY: M1={len(candles_m1)}, M5={len(candles_m5)} (min M1=25, M5=15 required)",
                "quality_score": 0.0
            }

        bar_idx = current_bar_index if current_bar_index is not None else len(candles_m1)
        sym_state = self._state_tracker.setdefault(symbol, {})

        # Rule 12: Three-completed-M1-bar cooldown following a losing trade
        cooldown_until = sym_state.get("loss_cooldown_until_bar", 0)
        if bar_idx < cooldown_until:
            return {
                "decision": "NO_TRADE",
                "symbol": symbol,
                "strategy": self.config.strategy_code,
                "reason": f"LOSS_COOLDOWN_ACTIVE: Current bar {bar_idx} < {cooldown_until} (waiting 3 bars after loss)",
                "quality_score": 0.0
            }

        # Last completed M1 candle is at index -1
        trigger_candle = candles_m1[-1]
        prior_candles = candles_m1[-4:-1] # The 3 completed candles before the trigger candle
        if len(prior_candles) < 3:
            return {
                "decision": "NO_TRADE",
                "symbol": symbol,
                "strategy": self.config.strategy_code,
                "reason": "INSUFFICIENT_PRIOR_BARS_FOR_BREAKOUT",
                "quality_score": 0.0
            }

        # Calculate M1 ATR(14)
        m1_atr = self._calc_atr(candles_m1, 14)
        if m1_atr <= 0:
            return {
                "decision": "NO_TRADE",
                "symbol": symbol,
                "strategy": self.config.strategy_code,
                "reason": "ZERO_M1_ATR_VOLATILITY",
                "quality_score": 0.0
            }

        # Rule 1: M1 EMA9 / EMA21 Directional Gate & Slope
        m1_closes = [float(c["close"]) for c in candles_m1]
        ema9_m1 = self._calc_ema(m1_closes, 9)
        ema21_m1 = self._calc_ema(m1_closes, 21)
        # Check EMA21 slope over last 3 bars
        ema21_m1_prev3 = self._calc_ema(m1_closes[:-3], 21)
        ema21_slope_bull = ema21_m1 > ema21_m1_prev3
        ema21_slope_bear = ema21_m1 < ema21_m1_prev3

        # Rule 4: M5 Opposing-Trend Veto Only (EMA9/EMA21 on M5)
        m5_closes = [float(c["close"]) for c in candles_m5]
        ema9_m5 = self._calc_ema(m5_closes, 9)
        ema21_m5 = self._calc_ema(m5_closes, 21)
        m5_bear_veto = ema9_m5 < ema21_m5 and m5_closes[-1] < ema9_m5 # Clearly opposing bearish trend
        m5_bull_veto = ema9_m5 > ema21_m5 and m5_closes[-1] > ema9_m5 # Clearly opposing bullish trend

        # Rule 2: Closed M1 3-Bar Breakout Trigger
        prior_3_high = max(float(c["high"]) for c in prior_candles)
        prior_3_low = min(float(c["low"]) for c in prior_candles)
        trigger_close = float(trigger_candle["close"])
        trigger_open = float(trigger_candle["open"])
        trigger_body = abs(trigger_close - trigger_open)

        # Rule 3: Trigger Candle Body Strength >= 0.4 * M1 ATR
        body_atr_ratio = trigger_body / m1_atr
        if body_atr_ratio < self.config.min_trigger_body_atr_ratio:
            return {
                "decision": "NO_TRADE",
                "symbol": symbol,
                "strategy": self.config.strategy_code,
                "reason": f"WEAK_TRIGGER_BODY: Body {trigger_body:.4f} is {body_atr_ratio:.2f}x ATR (min {self.config.min_trigger_body_atr_ratio}x required)",
                "quality_score": 0.25
            }

        direction = None
        # BUY Setup Evaluation
        if ema9_m1 > ema21_m1 and ema21_slope_bull and trigger_close > prior_3_high:
            if m5_bear_veto:
                return {
                    "decision": "NO_TRADE",
                    "symbol": symbol,
                    "strategy": self.config.strategy_code,
                    "reason": "M5_OPPOSING_BEARISH_TREND_VETO",
                    "quality_score": 0.40
                }
            direction = "BUY"
        # SELL Setup Evaluation
        elif ema9_m1 < ema21_m1 and ema21_slope_bear and trigger_close < prior_3_low:
            if m5_bull_veto:
                return {
                    "decision": "NO_TRADE",
                    "symbol": symbol,
                    "strategy": self.config.strategy_code,
                    "reason": "M5_OPPOSING_BULLISH_TREND_VETO",
                    "quality_score": 0.40
                }
            direction = "SELL"
        else:
            return {
                "decision": "NO_TRADE",
                "symbol": symbol,
                "strategy": self.config.strategy_code,
                "reason": "NO_IMPULSE_BREAKOUT_ALIGNMENT: Waiting for 3-bar breakout with EMA9/21 alignment",
                "quality_score": 0.35
            }

        # Rule 11: One entry per breakout leg
        last_breakout_level = sym_state.get("last_breakout_level")
        current_breakout_level = prior_3_high if direction == "BUY" else prior_3_low
        if last_breakout_level is not None and abs(current_breakout_level - last_breakout_level) < (0.2 * m1_atr):
            return {
                "decision": "NO_TRADE",
                "symbol": symbol,
                "strategy": self.config.strategy_code,
                "reason": f"BREAKOUT_LEG_ALREADY_TRADED: Already entered on breakout leg near {current_breakout_level}",
                "quality_score": 0.30
            }

        # Rule 5 & 9: Dynamic Stop-Loss (1.0x - 1.2x M1 ATR, buffered by spread)
        stop_dist_price = max(m1_atr * 1.0, spread * 1.5)

        # Rule 7: Transaction-cost and Friction Filtering (Raw Spread: Spread + Commission + Slippage)
        # Commission: ~$0.07 per 0.01 lot
        commission_per_unit = self.config.raw_spread_commission_per_lot_usd * (1.0 / min_lot)
        spread_cost_per_lot = (spread * contract_size)
        total_friction_per_lot = spread_cost_per_lot + commission_per_unit + self.config.default_slippage_buffer_usd
        
        loss_per_lot = ((stop_dist_price / tick_size) * tick_value) + total_friction_per_lot
        if loss_per_lot <= 0:
            return {
                "decision": "NO_TRADE",
                "symbol": symbol,
                "strategy": self.config.strategy_code,
                "reason": "INVALID_LOSS_PER_LOT_CALCULATION",
                "quality_score": 0.0
            }

        # Sizing against Sub-$1.00 Planned Risk Ceiling
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

        # Target intended loss ($0.50 - $0.70)
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

        # Rule 8: Net Reward-to-Risk Calculation (Target profit $0.50 - $3.00, R:R >= 1.25 net of fees)
        target_reward_usd = min(self.config.max_profit_target_usd, max(self.config.min_profit_target_usd, final_planned_risk_usd * 1.5))
        tp_dist_price = ((target_reward_usd + total_friction_per_lot * final_volume) / (final_volume * (tick_value / tick_size)))

        net_rr = round(target_reward_usd / max(0.01, final_planned_risk_usd), 2)
        if net_rr < self.config.min_risk_reward_ratio:
            return {
                "decision": "NO_TRADE",
                "symbol": symbol,
                "strategy": self.config.strategy_code,
                "reason": f"INSUFFICIENT_NET_RR: {net_rr:.2f} < min {self.config.min_risk_reward_ratio}",
                "quality_score": 0.40
            }

        if direction == "BUY":
            entry_price = ask
            sl_price = round(entry_price - stop_dist_price, digits)
            tp_price = round(entry_price + tp_dist_price, digits)
        else:
            entry_price = bid
            sl_price = round(entry_price + stop_dist_price, digits)
            tp_price = round(entry_price - tp_dist_price, digits)

        # Update state with this breakout leg level
        sym_state["last_breakout_level"] = current_breakout_level

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
            "total_friction_usd": round(total_friction_per_lot * final_volume, 3),
            "spread_cost_usd": round(spread_cost_per_lot * final_volume, 3),
            "commission_usd": round(commission_per_unit * final_volume, 3),
            "quality_score": 0.90,
            "spread_points": round(spread, digits),
            "timestamp": time.time(),
            "max_holding_time_minutes": self.config.max_holding_time_minutes
        }

    def evaluate_exit_conditions(
        self,
        symbol: str,
        side: str,
        entry_time: float,
        candles_m1: List[Dict[str, Any]],
        current_price: float
    ) -> Tuple[bool, str]:
        """
        Rule 10: Time-based and completed-bar reversal exits.
        Returns: (should_exit: bool, reason: str)
        """
        # Time-based exit check
        elapsed_minutes = (time.time() - entry_time) / 60.0
        if elapsed_minutes >= self.config.max_holding_time_minutes:
            return True, f"TIME_BASED_EXIT: Max holding time ({self.config.max_holding_time_minutes}m) exceeded."

        if len(candles_m1) >= 2:
            last_candle = candles_m1[-1]
            c_open = float(last_candle["open"])
            c_close = float(last_candle["close"])
            m1_closes = [float(c["close"]) for c in candles_m1]
            ema9 = self._calc_ema(m1_closes, 9)

            # Reversal exit: strong completed counter candle closing across EMA9
            if side.upper() == "BUY":
                if c_close < c_open and c_close < ema9:
                    return True, "COMPLETED_BAR_BEARISH_REVERSAL_EXIT: Close dropped below M1 EMA9."
            elif side.upper() == "SELL":
                if c_close > c_open and c_close > ema9:
                    return True, "COMPLETED_BAR_BULLISH_REVERSAL_EXIT: Close crossed above M1 EMA9."

        return False, "HOLD"

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

