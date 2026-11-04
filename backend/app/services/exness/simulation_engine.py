"""
BITDEX Exness HFT Quantitative Simulation Framework (Isolated Research Engine)
Phase 2.4.1 Forensic Remediation:
- Strict single-deduction accounting for spread, slippage, commission, and swap.
- Dynamic instrument contract specifications (XAUUSDm, BTCUSDm, EURUSDm, GBPUSDm).
- Duration-based prorated swap accumulation based on broker specifications.
- Bar-by-bar mark-to-market floating P&L and equity curve tracking.
- Conservative intrabar execution resolution for simultaneous TP/SL candle breaches.
- True final unrealized P&L reporting (mark-to-market of remaining open positions).
- Residual directional exposure modeling for unhedged legs.
- Strict isolation: All metrics explicitly labeled SIMULATED. Zero broker execution.
"""

import math
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timezone


class MarketRegime(str, Enum):
    RANGE = "RANGE"                    # Mean-reverting, low ADX (<20), low-medium volatility
    TRANSITION = "TRANSITION"          # Volatility expanding, 20 <= ADX < 25
    TRENDING_BULL = "TRENDING_BULL"    # Strong upward trend, ADX >= 25, +DI > -DI
    TRENDING_BEAR = "TRENDING_BEAR"    # Strong downward trend, ADX >= 25, -DI > +DI
    EXTREME_VOLATILITY = "EXTREME_VOLATILITY"  # News spikes, ATR outlier, wide spreads


@dataclass
class CostModelConfig:
    spread_points: float = 16.0          # e.g. 16 points ($0.16 for Gold, 0.8 pips for EURUSD)
    contract_size: float = 100.0         # Contract size: 100 for XAUUSD, 1 for BTC, 100000 for FX
    commission_per_lot_round: float = 0.0 # Standard account = $0.0; Raw Spread = $3.50/side ($7.00 round)
    swap_long_points_per_day: float = -8.5  # Daily swap on BUY in points
    swap_short_points_per_day: float = 2.1  # Daily swap on SELL in points
    point_value: float = 1.0             # Value of 1 point per lot in USD
    point_size: float = 0.01             # Price increment per point (e.g. 0.01 for Gold, 0.0001 for EURUSD, 1.0 for BTC)
    slippage_base_pips: float = 0.5      # Expected execution slippage in points
    latency_ms: float = 45.0             # Estimated round-trip latency to Exness server
    timeframe_seconds: int = 60          # Default 1m bar = 60s


# Canonical instrument contract specifications
SYMBOL_SPECS: Dict[str, Dict[str, Any]] = {
    "XAUUSDm": {
        "contract_size": 100.0,
        "point_size": 0.01,
        "point_value": 1.0,
        "typical_spread_points": 16.0,
        "commission_round": 0.0,
        "swap_long_pts": -8.5,
        "swap_short_pts": 2.1,
    },
    "BTCUSDm": {
        "contract_size": 1.0,
        "point_size": 1.0,
        "point_value": 1.0,
        "typical_spread_points": 12.5,
        "commission_round": 0.0,
        "swap_long_pts": -25.0,
        "swap_short_pts": -10.0,
    },
    "EURUSDm": {
        "contract_size": 100000.0,
        "point_size": 0.00001,
        "point_value": 1.0,
        "typical_spread_points": 8.0,
        "commission_round": 0.0,
        "swap_long_pts": -6.2,
        "swap_short_pts": 1.8,
    },
    "GBPUSDm": {
        "contract_size": 100000.0,
        "point_size": 0.00001,
        "point_value": 1.0,
        "typical_spread_points": 12.0,
        "commission_round": 0.0,
        "swap_long_pts": -4.5,
        "swap_short_pts": 0.5,
    },
}


def get_symbol_cost_config(symbol: str, timeframe: str = "1m") -> CostModelConfig:
    """Builds CostModelConfig calibrated to specific broker symbol specifications."""
    spec = SYMBOL_SPECS.get(symbol, SYMBOL_SPECS["XAUUSDm"])
    tf_secs = 60
    if timeframe in ("5m", "M5"):
        tf_secs = 300
    elif timeframe in ("15m", "M15"):
        tf_secs = 900
    elif timeframe in ("1h", "H1"):
        tf_secs = 3600
    elif timeframe in ("1d", "D1"):
        tf_secs = 86400

    return CostModelConfig(
        spread_points=spec["typical_spread_points"],
        contract_size=spec["contract_size"],
        commission_per_lot_round=spec["commission_round"],
        swap_long_points_per_day=spec["swap_long_pts"],
        swap_short_points_per_day=spec["swap_short_pts"],
        point_value=spec["point_value"],
        point_size=spec["point_size"],
        slippage_base_pips=0.5,
        latency_ms=45.0,
        timeframe_seconds=tf_secs,
    )


@dataclass
class RegimeAnalysis:
    regime: MarketRegime
    adx: float
    atr: float
    bb_width_pct: float
    plus_di: float
    minus_di: float
    is_safe_for_hedging: bool
    rationale: str


class QuantitativeRegimeClassifier:
    """
    Classifies market conditions based on multi-timeframe volatility and trend strength.
    Warns if paired hedging is vulnerable to runaway directional drift.
    """

    @staticmethod
    def compute_atr(candles: List[Dict[str, Any]], period: int = 14) -> float:
        if len(candles) < period + 1:
            return 0.0
        tr_list = []
        for i in range(1, len(candles)):
            h = float(candles[i]["high"])
            l = float(candles[i]["low"])
            prev_c = float(candles[i - 1]["close"])
            tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
            tr_list.append(tr)
        return sum(tr_list[-period:]) / period if tr_list else 0.0

    @staticmethod
    def classify(candles: List[Dict[str, Any]]) -> RegimeAnalysis:
        if len(candles) < 20:
            return RegimeAnalysis(
                regime=MarketRegime.TRANSITION,
                adx=0.0,
                atr=0.0,
                bb_width_pct=0.0,
                plus_di=0.0,
                minus_di=0.0,
                is_safe_for_hedging=False,
                rationale="Insufficient candle history for regime determination (minimum 20 required).",
            )

        closes = [float(c["close"]) for c in candles]
        highs = [float(c["high"]) for c in candles]
        lows = [float(c["low"]) for c in candles]

        # 1. ATR(14)
        atr14 = QuantitativeRegimeClassifier.compute_atr(candles, period=14)

        # 2. Approximate ADX & Directional Indicators
        pos_dm = 0.0
        neg_dm = 0.0
        tr_sum = 0.0
        period = min(14, len(candles) - 1)

        for i in range(len(candles) - period, len(candles)):
            up_move = highs[i] - highs[i - 1]
            down_move = lows[i - 1] - lows[i]
            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
            tr_sum += tr

            if up_move > down_move and up_move > 0:
                pos_dm += up_move
            if down_move > up_move and down_move > 0:
                neg_dm += down_move

        plus_di = (pos_dm / tr_sum * 100) if tr_sum > 0 else 0.0
        minus_di = (neg_dm / tr_sum * 100) if tr_sum > 0 else 0.0
        di_diff = abs(plus_di - minus_di)
        di_sum = plus_di + minus_di
        dx = (di_diff / di_sum * 100) if di_sum > 0 else 0.0
        adx = dx

        # 3. Bollinger Bands (20, 2)
        n = min(20, len(closes))
        window_closes = closes[-n:]
        sma = sum(window_closes) / n
        variance = sum((x - sma) ** 2 for x in window_closes) / n
        std = math.sqrt(variance)
        upper_bb = sma + 2 * std
        lower_bb = sma - 2 * std
        bb_width_pct = ((upper_bb - lower_bb) / sma * 100) if sma > 0 else 0.0

        # Classification Logic
        if atr14 > (sma * 0.015):
            return RegimeAnalysis(
                regime=MarketRegime.EXTREME_VOLATILITY,
                adx=round(adx, 2),
                atr=round(atr14, 4),
                bb_width_pct=round(bb_width_pct, 3),
                plus_di=round(plus_di, 2),
                minus_di=round(minus_di, 2),
                is_safe_for_hedging=False,
                rationale="Extreme volatility detected. High risk of slippage, widening spreads, and liquidity gaps.",
            )

        if adx >= 25.0:
            if plus_di > minus_di:
                return RegimeAnalysis(
                    regime=MarketRegime.TRENDING_BULL,
                    adx=round(adx, 2),
                    atr=round(atr14, 4),
                    bb_width_pct=round(bb_width_pct, 3),
                    plus_di=round(plus_di, 2),
                    minus_di=round(minus_di, 2),
                    is_safe_for_hedging=False,
                    rationale="Strong Bullish Trend. Paired hedging prohibited: SELL leg will incur severe unhedged floating drawdown.",
                )
            else:
                return RegimeAnalysis(
                    regime=MarketRegime.TRENDING_BEAR,
                    adx=round(adx, 2),
                    atr=round(atr14, 4),
                    bb_width_pct=round(bb_width_pct, 3),
                    plus_di=round(plus_di, 2),
                    minus_di=round(minus_di, 2),
                    is_safe_for_hedging=False,
                    rationale="Strong Bearish Trend. Paired hedging prohibited: BUY leg will incur severe unhedged floating drawdown.",
                )

        if adx < 20.0 and bb_width_pct < 1.0:
            return RegimeAnalysis(
                regime=MarketRegime.RANGE,
                adx=round(adx, 2),
                atr=round(atr14, 4),
                bb_width_pct=round(bb_width_pct, 3),
                plus_di=round(plus_di, 2),
                minus_di=round(minus_di, 2),
                is_safe_for_hedging=True,
                rationale="Consolidating Range. Mean-reverting scalping with tight stop-losses is viable.",
            )

        return RegimeAnalysis(
            regime=MarketRegime.TRANSITION,
            adx=round(adx, 2),
            atr=round(atr14, 4),
            bb_width_pct=round(bb_width_pct, 3),
            plus_di=round(plus_di, 2),
            minus_di=round(minus_di, 2),
            is_safe_for_hedging=False,
            rationale="Market in transition. Breakout potential is high; position sizing must be constrained.",
        )


class HFTPairedSimulationEngine:
    """
    Simulates paired BUY/SELL High-Frequency Trading execution across historical candle data.
    Enforces honest, non-redundant, mark-to-market accounting:
    - Deducts spread, slippage, commission, and swap exactly once.
    - Resolves simultaneous TP/SL candle breaches conservatively (assumes Stop Loss triggered first).
    - Accumulates swap based on actual duration held and broker instrument parameters.
    - Calculates floating P&L bar-by-bar and tracks true peak equity and maximum drawdown.
    - Models residual exposure for the opposing leg until closed.
    - Returns true final unrealized P&L and distinguishes realized, gross, and net P&L.
    """

    def __init__(self, config: Optional[CostModelConfig] = None):
        self.config = config or CostModelConfig()

    def run_simulation(
        self,
        symbol: str,
        candles: List[Dict[str, Any]],
        volume_per_leg: float = 0.01,
        take_profit_points: float = 30.0,
        stop_loss_points: float = 60.0,
        max_hold_bars: int = 15,
    ) -> Dict[str, Any]:
        """
        Runs an isolated, non-executing simulation of paired BUY+SELL HFT cycles.
        """
        if len(candles) < 25:
            return {
                "status": "INSUFFICIENT_DATA",
                "is_simulated": True,
                "error": "At least 25 historical candles required for simulation.",
            }

        # Automatically align config contract size and point size if known
        if symbol in SYMBOL_SPECS:
            spec = SYMBOL_SPECS[symbol]
            self.config.contract_size = spec["contract_size"]
            self.config.point_size = spec["point_size"]

        # 1. Pre-simulation regime check
        regime_eval = QuantitativeRegimeClassifier.classify(candles[:20])

        initial_balance = 5000.0
        current_balance = initial_balance
        peak_equity = initial_balance
        max_drawdown_usd = 0.0

        total_gross_profit = 0.0
        total_gross_loss = 0.0
        total_spread_costs = 0.0
        total_slippage_costs = 0.0
        total_commission_costs = 0.0
        total_swap_costs = 0.0

        winning_cycles = 0
        losing_cycles = 0
        total_cycles = 0

        # Unhedged residual tracking
        unhedged_cycles_count = 0
        total_unhedged_bars = 0
        max_unhedged_bars = 0
        total_unhedged_drift_usd = 0.0

        equity_curve: List[float] = [initial_balance]
        final_unrealized_pnl = 0.0

        pt_size = self.config.point_size
        c_size = self.config.contract_size

        # Step through candles
        step = 5  # Evaluate trade cycle every 5 bars
        for idx in range(20, len(candles) - max_hold_bars, step):
            entry_candle = candles[idx]
            entry_price = float(entry_candle["close"])

            # ─── Friction Costs for the Cycle (2 legs: BUY + SELL) ───
            # Spread cost: paid at market entry on both legs
            cycle_spread_cost = (
                self.config.spread_points * pt_size * volume_per_leg * c_size * 2.0
            )
            # Slippage cost: modeled on execution of both legs
            cycle_slippage_cost = (
                self.config.slippage_base_pips * pt_size * volume_per_leg * c_size * 2.0
            )
            # Commission cost: round-trip commission for 2 legs
            cycle_commission_cost = (
                self.config.commission_per_lot_round * (volume_per_leg * 2.0)
            )

            # Accumulate entry friction
            total_spread_costs += cycle_spread_cost
            total_slippage_costs += cycle_slippage_cost
            total_commission_costs += cycle_commission_cost

            # Price target levels
            buy_tp = entry_price + (take_profit_points * pt_size)
            buy_sl = entry_price - (stop_loss_points * pt_size)

            sell_tp = entry_price - (take_profit_points * pt_size)
            sell_sl = entry_price + (stop_loss_points * pt_size)

            buy_closed = False
            sell_closed = False
            buy_gross_pnl = 0.0
            sell_gross_pnl = 0.0

            buy_bars_held = 0
            sell_bars_held = 0

            # Evaluate bars during the hold period
            hold_window = candles[idx + 1 : idx + 1 + max_hold_bars]

            for bar_offset, bar in enumerate(hold_window, start=1):
                high = float(bar["high"])
                low = float(bar["low"])
                close = float(bar["close"])

                # --- BUY Leg Check ---
                if not buy_closed:
                    buy_bars_held = bar_offset
                    tp_breached = high >= buy_tp
                    sl_breached = low <= buy_sl

                    if tp_breached and sl_breached:
                        # Conservative Intrabar Resolution: Assume adverse Stop-Loss hit first
                        buy_closed = True
                        buy_gross_pnl = (buy_sl - entry_price) * volume_per_leg * c_size
                    elif sl_breached:
                        buy_closed = True
                        buy_gross_pnl = (buy_sl - entry_price) * volume_per_leg * c_size
                    elif tp_breached:
                        buy_closed = True
                        buy_gross_pnl = (buy_tp - entry_price) * volume_per_leg * c_size

                # --- SELL Leg Check ---
                if not sell_closed:
                    sell_bars_held = bar_offset
                    tp_breached = low <= sell_tp
                    sl_breached = high >= sell_sl

                    if tp_breached and sl_breached:
                        # Conservative Intrabar Resolution: Assume adverse Stop-Loss hit first
                        sell_closed = True
                        sell_gross_pnl = (entry_price - sell_sl) * volume_per_leg * c_size
                    elif sl_breached:
                        sell_closed = True
                        sell_gross_pnl = (entry_price - sell_sl) * volume_per_leg * c_size
                    elif tp_breached:
                        sell_closed = True
                        sell_gross_pnl = (entry_price - sell_tp) * volume_per_leg * c_size

                # --- Floating P&L & Mark-to-Market Equity throughout the candle ---
                floating_buy = (
                    (close - entry_price) * volume_per_leg * c_size
                    if not buy_closed
                    else buy_gross_pnl
                )
                floating_sell = (
                    (entry_price - close) * volume_per_leg * c_size
                    if not sell_closed
                    else sell_gross_pnl
                )

                # Prorated swap during the bar
                sec_per_bar = self.config.timeframe_seconds
                day_frac = sec_per_bar / 86400.0
                bar_swap = (
                    (self.config.swap_long_points_per_day * pt_size * volume_per_leg * c_size * day_frac if not buy_closed else 0.0) +
                    (self.config.swap_short_points_per_day * pt_size * volume_per_leg * c_size * day_frac if not sell_closed else 0.0)
                )

                interim_equity = (
                    current_balance
                    + floating_buy
                    + floating_sell
                    - (cycle_spread_cost + cycle_slippage_cost + cycle_commission_cost)
                    + bar_swap
                )

                if interim_equity > peak_equity:
                    peak_equity = interim_equity

                drawdown_usd = peak_equity - interim_equity
                if drawdown_usd > max_drawdown_usd:
                    max_drawdown_usd = drawdown_usd

                # If both closed, cycle concludes
                if buy_closed and sell_closed:
                    break

            # If legs still open at expiration of hold window, close at final candle's close price
            exit_price = float(hold_window[-1]["close"])
            if not buy_closed:
                buy_bars_held = len(hold_window)
                buy_gross_pnl = (exit_price - entry_price) * volume_per_leg * c_size
                buy_closed = True
            if not sell_closed:
                sell_bars_held = len(hold_window)
                sell_gross_pnl = (entry_price - exit_price) * volume_per_leg * c_size
                sell_closed = True

            # Swap calculation based on exact duration each leg was held
            sec_per_bar = self.config.timeframe_seconds
            buy_swap_usd = (
                self.config.swap_long_points_per_day
                * pt_size
                * volume_per_leg
                * c_size
                * ((buy_bars_held * sec_per_bar) / 86400.0)
            )
            sell_swap_usd = (
                self.config.swap_short_points_per_day
                * pt_size
                * volume_per_leg
                * c_size
                * ((sell_bars_held * sec_per_bar) / 86400.0)
            )
            # Note: Negative swap is a cost; positive swap is a credit
            cycle_swap_pnl = buy_swap_usd + sell_swap_usd
            cycle_swap_cost = -cycle_swap_pnl  # Expressed as friction cost (positive = expense)
            total_swap_costs += cycle_swap_cost

            # Residual unhedged exposure analysis
            if buy_bars_held != sell_bars_held:
                unhedged_cycles_count += 1
                unhedged_bars = abs(buy_bars_held - sell_bars_held)
                total_unhedged_bars += unhedged_bars
                if unhedged_bars > max_unhedged_bars:
                    max_unhedged_bars = unhedged_bars

                # Drift of the remaining unhedged leg
                if buy_bars_held < sell_bars_held:
                    # BUY closed early, SELL was left open unhedged
                    total_unhedged_drift_usd += sell_gross_pnl
                else:
                    # SELL closed early, BUY was left open unhedged
                    total_unhedged_drift_usd += buy_gross_pnl

            # ─── True Cycle Accounting ───
            cycle_gross_pnl = buy_gross_pnl + sell_gross_pnl
            cycle_total_friction = (
                cycle_spread_cost
                + cycle_slippage_cost
                + cycle_commission_cost
                + cycle_swap_cost
            )
            # Net realized PnL = Gross price PnL minus total friction (deducted exactly once)
            cycle_net_pnl = cycle_gross_pnl - cycle_total_friction

            total_cycles += 1
            if cycle_gross_pnl > 0:
                total_gross_profit += cycle_gross_pnl
            else:
                total_gross_loss += abs(cycle_gross_pnl)

            if cycle_net_pnl > 0:
                winning_cycles += 1
            else:
                losing_cycles += 1

            current_balance += cycle_net_pnl
            current_equity = current_balance  # All legs closed at end of cycle
            if current_equity > peak_equity:
                peak_equity = current_equity

            equity_curve.append(round(current_equity, 2))

        # Overall summary metrics
        total_friction_usd = (
            total_spread_costs
            + total_slippage_costs
            + total_commission_costs
            + total_swap_costs
        )
        total_realized_gross_pnl = total_gross_profit - total_gross_loss
        total_realized_net_pnl = current_balance - initial_balance

        win_rate = (winning_cycles / total_cycles * 100.0) if total_cycles > 0 else 0.0
        profit_factor = (
            round(total_gross_profit / total_gross_loss, 2)
            if total_gross_loss > 0
            else (999.0 if total_gross_profit > 0 else 0.0)
        )
        avg_win = round(total_gross_profit / winning_cycles, 2) if winning_cycles > 0 else 0.0
        avg_loss = round(total_gross_loss / losing_cycles, 2) if losing_cycles > 0 else 0.0

        avg_unhedged_bars = (
            total_unhedged_bars / unhedged_cycles_count
            if unhedged_cycles_count > 0
            else 0.0
        )

        return {
            "status": "COMPLETED",
            "is_simulated": True,
            "simulation_disclaimer": "SIMULATED QUANTITATIVE RESEARCH ONLY. NOT ACTUAL BROKER TRADING RESULTS.",
            "symbol": symbol,
            "candle_count": len(candles),
            "simulated_cycles": total_cycles,
            "winning_cycles": winning_cycles,
            "losing_cycles": losing_cycles,
            "win_rate_pct": round(win_rate, 2),
            "profit_factor": profit_factor,
            "initial_balance_usd": initial_balance,
            "final_balance_usd": round(current_balance, 2),
            "final_equity_usd": round(current_balance + final_unrealized_pnl, 2),
            "peak_equity_usd": round(peak_equity, 2),
            "gross_profit_usd": round(total_gross_profit, 2),
            "gross_loss_usd": round(total_gross_loss, 2),
            "realized_gross_pnl_usd": round(total_realized_gross_pnl, 2),
            "realized_net_pnl_usd": round(total_realized_net_pnl, 2),
            "unrealized_pnl_usd": round(final_unrealized_pnl, 2),
            "net_simulated_pnl_usd": round(total_realized_net_pnl + final_unrealized_pnl, 2),
            "average_win_usd": avg_win,
            "average_loss_usd": avg_loss,
            "max_drawdown_usd": round(max_drawdown_usd, 2),
            "max_drawdown_pct": round(
                (max_drawdown_usd / peak_equity * 100.0) if peak_equity > 0 else 0.0, 2
            ),
            "cost_breakdown": {
                "total_spread_cost_usd": round(total_spread_costs, 2),
                "total_slippage_cost_usd": round(total_slippage_costs, 2),
                "total_commission_cost_usd": round(total_commission_costs, 2),
                "total_swap_cost_usd": round(total_swap_costs, 2),
                "total_friction_usd": round(total_friction_usd, 2),
            },
            "residual_directional_exposure": {
                "typical_unhedged_delta_lots": volume_per_leg,
                "exposure_state": "ASYMMETRIC_SINGLE_LEG" if unhedged_cycles_count > 0 else "FLAT",
                "unhedged_cycles_count": unhedged_cycles_count,
                "avg_unhedged_duration_bars": round(avg_unhedged_bars, 1),
                "max_unhedged_duration_bars": max_unhedged_bars,
                "total_unhedged_drift_usd": round(total_unhedged_drift_usd, 2),
                "risk_warning": "When one leg hits Take Profit, the opposing leg is left unhedged with 100% directional exposure until stop-out or expiration.",
            },
            "regime_at_start": {
                "regime": regime_eval.regime.value,
                "adx": regime_eval.adx,
                "atr": regime_eval.atr,
                "safe_for_hedging": regime_eval.is_safe_for_hedging,
                "rationale": regime_eval.rationale,
            },
            "risk_assessment": (
                "ACCEPTABLE: Drawdown within 5% limit."
                if max_drawdown_usd < 250.0
                else "HIGH_RISK: Drawdown exceeds risk budget. Paired hedging during directional expansion causes severe drift."
            ),
        }
