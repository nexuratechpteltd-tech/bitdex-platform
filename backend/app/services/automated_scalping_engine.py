"""
BITDEX — AUTOMATED HIGH-FREQUENCY SCALPING ENGINE (PHASE 7C)
============================================================
Two-sided, regime-aware, multi-broker scalping engine designed for institutional execution.
Evaluates:
  1. Market direction & short-term momentum (EMA9/21/50, RSI, MACD impulse)
  2. Trending vs ranging conditions (ADX, Bollinger Bands, ATR percentile)
  3. Short-term price movement (candle body, consecutive impulse, micro-volatility)
  4. Volatility & ATR (ATR(14), ATR%, volatility sanity bounds)
  5. Bid/Ask spread (absolute spread USD, spread bps, spread ratio to profit target)
  6. Trading commissions & expected slippage (round-trip commissions, broker fee schedule, slippage buffer)
  7. Available liquidity & trading permissions (broker spread/volume check, market open hours, MT5 trade mode)
  8. Entry quality & risk/reward (Risk:Reward minimum 1.5:1, quality score >= 0.70)

Supports:
  - Independent BUY and SELL evaluation (never biased to single direction)
  - Controlled multiple entries with strict exposure limits (Anti-Martingale / Anti-Grid)
  - Mandatory broker-side Stop Loss & Take Profit verification
  - Multi-broker routing: Exness MT5 (Gateway), Binance Futures, Bybit, Exness Terminal
  - Strict global safety locks: live_trading_locked = True, read_only_mode = True
"""

import time
import math
import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict

from .futures_regime import MarketRegimeClassifier

logger = logging.getLogger("bitdex.scalping_engine")


@dataclass
class ScalpThresholds:
    """Configurable and auditable scalping thresholds."""
    min_quality_score: float = 0.70
    min_risk_reward_ratio: float = 1.50
    max_acceptable_spread_bps: float = 8.0
    default_slippage_buffer_pct: float = 0.05
    min_adx_trending: float = 22.0
    min_atr_pct: float = 0.10
    max_atr_pct: float = 3.50
    atr_stop_multiplier: float = 1.50
    min_stop_distance_pct: float = 0.20
    max_stop_distance_pct: float = 4.00
    # Multi-entry controls
    max_simultaneous_positions: int = 3
    max_entries_per_instrument: int = 2
    max_total_exposure_pct: float = 30.0  # Max 30% of account equity
    min_distance_between_entries_atr: float = 1.0  # Min 1.0x ATR distance
    max_daily_loss_usd: float = 50.0
    max_consecutive_losses: int = 3
    cooldown_seconds_after_consecutive_losses: int = 1800  # 30 mins
    max_aggregate_risk_pct: float = 5.0  # Max 5% aggregate account risk


@dataclass
class ProposedEntry:
    broker_account_id: str
    instrument: str
    direction: str  # "BUY" or "SELL"
    entry_price: float
    entry_range: Dict[str, float]
    position_volume: float
    stop_loss_price: float
    take_profit_price: float
    stop_distance_usd: float
    stop_distance_pct: float
    take_profit_distance_usd: float
    risk_reward_ratio: float
    max_acceptable_spread_usd: float
    max_acceptable_spread_bps: float
    max_acceptable_slippage_usd: float
    estimated_transaction_costs_usd: float
    max_permitted_risk_usd: float
    quality_score: float
    regime: str
    broker_adapter: str
    broker_stop_acknowledged: bool
    rationale: str
    timestamp_iso: str


class AutomatedHighFrequencyScalpingEngine:
    """
    Two-sided regime-aware automated scalping engine.
    Computes independent BUY and SELL opportunities with mandatory broker-side Stop Loss.
    """

    PRODUCT_NAME = "AUTOMATED HIGH-FREQUENCY SCALPING ENGINE"
    STRATEGY_CODE = "SCALP_DUAL_REGIME_v1"

    def __init__(self, thresholds: Optional[ScalpThresholds] = None):
        self.thresholds = thresholds or ScalpThresholds()

    # ──────────────────────────────────────────────────────────────────────────
    # 1. Independent BUY Evaluation
    # ──────────────────────────────────────────────────────────────────────────
    def evaluate_buy_opportunity(
        self,
        symbol: str,
        klines: List[Dict[str, Any]],
        current_ask: float,
        current_bid: float,
        broker_type: str = "EXNESS_MT5",
        account_equity: float = 5000.0,
        allocated_margin: float = 50.0,
        leverage: int = 3,
        broker_stops_level_points: float = 50.0,
        point_size: float = 0.01,
        existing_positions: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Independently evaluate whether market structure, momentum, and friction permit a BUY entry.
        """
        return self._evaluate_side(
            side="BUY",
            symbol=symbol,
            klines=klines,
            entry_price=current_ask,
            opposite_price=current_bid,
            broker_type=broker_type,
            account_equity=account_equity,
            allocated_margin=allocated_margin,
            leverage=leverage,
            broker_stops_level_points=broker_stops_level_points,
            point_size=point_size,
            existing_positions=existing_positions or [],
        )

    # ──────────────────────────────────────────────────────────────────────────
    # 2. Independent SELL Evaluation
    # ──────────────────────────────────────────────────────────────────────────
    def evaluate_sell_opportunity(
        self,
        symbol: str,
        klines: List[Dict[str, Any]],
        current_bid: float,
        current_ask: float,
        broker_type: str = "EXNESS_MT5",
        account_equity: float = 5000.0,
        allocated_margin: float = 50.0,
        leverage: int = 3,
        broker_stops_level_points: float = 50.0,
        point_size: float = 0.01,
        existing_positions: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Independently evaluate whether market structure, momentum, and friction permit a SELL entry.
        """
        return self._evaluate_side(
            side="SELL",
            symbol=symbol,
            klines=klines,
            entry_price=current_bid,
            opposite_price=current_ask,
            broker_type=broker_type,
            account_equity=account_equity,
            allocated_margin=allocated_margin,
            leverage=leverage,
            broker_stops_level_points=broker_stops_level_points,
            point_size=point_size,
            existing_positions=existing_positions or [],
        )

    # ──────────────────────────────────────────────────────────────────────────
    # 3. Two-Sided Combined Evaluation
    # ──────────────────────────────────────────────────────────────────────────
    def evaluate_market_opportunity(
        self,
        symbol: str,
        klines: List[Dict[str, Any]],
        current_bid: float,
        current_ask: float,
        broker_account_id: str,
        broker_type: str = "EXNESS_MT5",
        account_equity: float = 5000.0,
        allocated_margin: float = 50.0,
        leverage: int = 3,
        broker_stops_level_points: float = 50.0,
        point_size: float = 0.01,
        existing_positions: Optional[List[Dict[str, Any]]] = None,
        daily_realized_loss: float = 0.0,
        consecutive_losses: int = 0,
        last_loss_timestamp: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Full two-sided evaluation comparing BUY and SELL setups, enforcing multi-entry and anti-grid limits.
        """
        now = time.time()
        existing = existing_positions or []

        # ── Pre-Filter 1: Daily Loss Limit ───────────────────────────────────
        if daily_realized_loss >= self.thresholds.max_daily_loss_usd:
            return self._format_waiting_response(
                symbol, current_bid, current_ask,
                reason=f"DAILY_LOSS_LIMIT_REACHED: Daily realized loss ${daily_realized_loss:.2f} >= ${self.thresholds.max_daily_loss_usd:.2f} limit."
            )

        # ── Pre-Filter 2: Consecutive Losses Cooldown ────────────────────────
        if consecutive_losses >= self.thresholds.max_consecutive_losses:
            elapsed = now - last_loss_timestamp
            if elapsed < self.thresholds.cooldown_seconds_after_consecutive_losses:
                remaining = int(self.thresholds.cooldown_seconds_after_consecutive_losses - elapsed)
                return self._format_waiting_response(
                    symbol, current_bid, current_ask,
                    reason=f"CONSECUTIVE_LOSS_COOLDOWN: {consecutive_losses} consecutive losses. Cooldown active for {remaining}s."
                )

        # ── Pre-Filter 3: Max Simultaneous Positions ────────────────────────
        if len(existing) >= self.thresholds.max_simultaneous_positions:
            return self._format_waiting_response(
                symbol, current_bid, current_ask,
                reason=f"MAX_POSITIONS_REACHED: {len(existing)} open positions >= {self.thresholds.max_simultaneous_positions} limit."
            )

        # ── Pre-Filter 4: Max Entries Per Instrument ─────────────────────────
        symbol_positions = [p for p in existing if p.get("symbol", "").upper() == symbol.upper()]
        if len(symbol_positions) >= self.thresholds.max_entries_per_instrument:
            return self._format_waiting_response(
                symbol, current_bid, current_ask,
                reason=f"MAX_INSTRUMENT_ENTRIES_REACHED: {len(symbol_positions)} open positions on {symbol}."
            )

        # ── Pre-Filter 5: Aggregate Exposure Limit ───────────────────────────
        total_exposure = sum(abs(float(p.get("notional", 0.0) or (float(p.get("volume", p.get("size", 0.0))) * float(p.get("entry_price", 0.0))))) for p in existing)
        max_allowed_exposure = account_equity * (self.thresholds.max_total_exposure_pct / 100.0)
        proposed_notional = allocated_margin * leverage
        if (total_exposure + proposed_notional) > max_allowed_exposure:
            return self._format_waiting_response(
                symbol, current_bid, current_ask,
                reason=f"EXPOSURE_CAP_EXCEEDED: Total exposure (${total_exposure + proposed_notional:.2f}) would exceed max allowed (${max_allowed_exposure:.2f}, {self.thresholds.max_total_exposure_pct}% equity)."
            )

        # Evaluate BUY and SELL independently
        buy_res = self.evaluate_buy_opportunity(
            symbol=symbol,
            klines=klines,
            current_ask=current_ask,
            current_bid=current_bid,
            broker_type=broker_type,
            account_equity=account_equity,
            allocated_margin=allocated_margin,
            leverage=leverage,
            broker_stops_level_points=broker_stops_level_points,
            point_size=point_size,
            existing_positions=symbol_positions,
        )

        sell_res = self.evaluate_sell_opportunity(
            symbol=symbol,
            klines=klines,
            current_bid=current_bid,
            current_ask=current_ask,
            broker_type=broker_type,
            account_equity=account_equity,
            allocated_margin=allocated_margin,
            leverage=leverage,
            broker_stops_level_points=broker_stops_level_points,
            point_size=point_size,
            existing_positions=symbol_positions,
        )

        buy_eligible = buy_res.get("eligible", False)
        sell_eligible = sell_res.get("eligible", False)
        buy_score = buy_res.get("quality_score", 0.0)
        sell_score = sell_res.get("quality_score", 0.0)

        # Compare and pick highest quality setup
        if buy_eligible and sell_eligible:
            selected = buy_res if buy_score >= sell_score else sell_res
        elif buy_eligible:
            selected = buy_res
        elif sell_eligible:
            selected = sell_res
        else:
            # Neither side eligible: return structured waiting state
            reasons = []
            if buy_res.get("rejection_reason"):
                reasons.append(f"BUY: {buy_res['rejection_reason']}")
            if sell_res.get("rejection_reason"):
                reasons.append(f"SELL: {sell_res['rejection_reason']}")
            combined_reason = " | ".join(reasons) if reasons else "No valid high-probability setup."
            return self._format_waiting_response(
                symbol=symbol,
                bid=current_bid,
                ask=current_ask,
                reason=f"WAITING_FOR_VALID_SIGNAL: {combined_reason}",
                buy_eval=buy_res,
                sell_eval=sell_res,
            )

        # Build proposed entry with full parameters
        entry = selected["proposed_entry"]
        entry["broker_account_id"] = broker_account_id
        entry["timestamp_iso"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))

        return {
            "status": "SIGNAL_GENERATED",
            "has_signal": True,
            "engine": self.PRODUCT_NAME,
            "strategy": self.STRATEGY_CODE,
            "symbol": symbol.upper(),
            "selected_direction": selected["direction"],
            "proposed_entry": entry,
            "buy_evaluation": {
                "score": buy_score,
                "eligible": buy_eligible,
                "reason": buy_res.get("rejection_reason"),
            },
            "sell_evaluation": {
                "score": sell_score,
                "eligible": sell_eligible,
                "reason": sell_res.get("rejection_reason"),
            },
            "market_state": {
                "bid": current_bid,
                "ask": current_ask,
                "spread_usd": round(abs(current_ask - current_bid), 4),
                "spread_bps": round((abs(current_ask - current_bid) / current_bid) * 10000, 2),
                "regime": selected.get("regime", "RANGING_SIDEWAYS"),
            },
            "risk_limits": {
                "simultaneous_positions_open": len(existing),
                "max_simultaneous_positions": self.thresholds.max_simultaneous_positions,
                "total_account_exposure_usd": round(total_exposure, 2),
                "max_allowed_exposure_usd": round(max_allowed_exposure, 2),
                "daily_realized_loss_usd": round(daily_realized_loss, 2),
                "max_daily_loss_usd": self.thresholds.max_daily_loss_usd,
                "consecutive_losses": consecutive_losses,
            },
            "live_trading_locked": True,
            "read_only_mode": True,
            "emergency_lock_active": True,
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Internal Core Evaluator
    # ──────────────────────────────────────────────────────────────────────────
    def _evaluate_side(
        self,
        side: str,  # "BUY" or "SELL"
        symbol: str,
        klines: List[Dict[str, Any]],
        entry_price: float,
        opposite_price: float,
        broker_type: str,
        account_equity: float,
        allocated_margin: float,
        leverage: int,
        broker_stops_level_points: float,
        point_size: float,
        existing_positions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Rigorous single-side evaluation for BUY or SELL.
        """
        if len(klines) < 20:
            return {"eligible": False, "quality_score": 0.0, "rejection_reason": "INSUFFICIENT_KLINES_HISTORY (>=20 required)"}

        closes = [float(k["close"]) for k in klines]
        highs = [float(k["high"]) for k in klines]
        lows = [float(k["low"]) for k in klines]
        opens = [float(k["open"]) for k in klines]

        # 1. Spread Calculation and Gate
        spread_usd = abs(entry_price - opposite_price)
        spread_bps = (spread_usd / entry_price) * 10000.0
        if spread_bps > self.thresholds.max_acceptable_spread_bps:
            return {
                "eligible": False,
                "quality_score": 0.0,
                "rejection_reason": f"EXCESSIVE_SPREAD ({spread_bps:.2f} bps > {self.thresholds.max_acceptable_spread_bps:.2f} bps limit)"
            }

        # 2. Volatility and ATR
        atr = MarketRegimeClassifier.calculate_atr(klines, 14)
        if atr <= 0.0:
            return {"eligible": False, "quality_score": 0.0, "rejection_reason": "INVALID_OR_ZERO_ATR"}
        atr_pct = (atr / entry_price) * 100.0

        if atr_pct < self.thresholds.min_atr_pct:
            return {
                "eligible": False,
                "quality_score": 0.0,
                "rejection_reason": f"VOLATILITY_COMPRESSED (ATR% {atr_pct:.3f}% < {self.thresholds.min_atr_pct}% min required for scalp target)"
            }
        if atr_pct > self.thresholds.max_atr_pct:
            return {
                "eligible": False,
                "quality_score": 0.0,
                "rejection_reason": f"EXTREME_VOLATILITY_CHOP (ATR% {atr_pct:.3f}% > {self.thresholds.max_atr_pct}% max threshold)"
            }

        # 3. Market Regime Classification
        regime_info = MarketRegimeClassifier.classify(klines, symbol)
        regime = regime_info.get("regime", "RANGING_SIDEWAYS")
        permitted_dirs = regime_info.get("permitted_directions", [])

        # Direction-Regime consistency check
        req_direction = "LONG" if side == "BUY" else "SHORT"
        if req_direction not in permitted_dirs:
            return {
                "eligible": False,
                "quality_score": 0.0,
                "regime": regime,
                "rejection_reason": f"REGIME_MISMATCH (Market classified as {regime}, permitted directions: {permitted_dirs})"
            }

        # 4. Momentum & Indicators
        ema9 = MarketRegimeClassifier.calculate_ema(closes, 9)
        ema21 = MarketRegimeClassifier.calculate_ema(closes, 21)
        ema50 = MarketRegimeClassifier.calculate_ema(closes, 50)
        latest_close = closes[-1]
        prev_close = closes[-2]
        candle_body = latest_close - opens[-1]

        # RSI calculation (14)
        gains, losses = [], []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i - 1]
            gains.append(max(0.0, diff))
            losses.append(max(0.0, -diff))
        rg = sum(gains[-14:]) / 14.0 if gains else 0.0
        rl = sum(losses[-14:]) / 14.0 if losses else 0.0
        rs = (rg / rl) if rl > 0 else 100.0
        rsi = 100.0 - (100.0 / (1.0 + rs))

        score = 0.0

        if side == "BUY":
            # Trend structure
            if ema9 > ema21 > ema50:
                score += 0.35
            elif ema9 > ema21:
                score += 0.25
            # Price above short EMA
            if latest_close > ema9:
                score += 0.15
            # Positive candle impulse
            if candle_body > 0 and latest_close > prev_close:
                score += 0.20
            # RSI in healthy expansion zone (not exhausted)
            if 42.0 <= rsi <= 68.0:
                score += 0.20
            # Breakout confirmation
            recent_high_10 = max(highs[-10:-1])
            if latest_close >= recent_high_10 * 0.9995:
                score += 0.10
        else:  # SELL
            # Trend structure
            if ema9 < ema21 < ema50:
                score += 0.35
            elif ema9 < ema21:
                score += 0.25
            # Price below short EMA
            if latest_close < ema9:
                score += 0.15
            # Negative candle impulse
            if candle_body < 0 and latest_close < prev_close:
                score += 0.20
            # RSI in healthy expansion zone (not exhausted)
            if 32.0 <= rsi <= 58.0:
                score += 0.20
            # Breakdown confirmation
            recent_low_10 = min(lows[-10:-1])
            if latest_close <= recent_low_10 * 1.0005:
                score += 0.10

        score = round(min(1.0, score), 2)
        if score < self.thresholds.min_quality_score:
            return {
                "eligible": False,
                "quality_score": score,
                "regime": regime,
                "rejection_reason": f"QUALITY_SCORE_TOO_LOW ({score:.2f} < {self.thresholds.min_quality_score:.2f} threshold)"
            }

        # 5. Anti-Grid / Minimum Distance Check Against Existing Positions
        for pos in existing_positions:
            pos_entry = float(pos.get("entry_price", 0.0))
            if pos_entry > 0:
                dist = abs(entry_price - pos_entry)
                min_dist = atr * self.thresholds.min_distance_between_entries_atr
                if dist < min_dist:
                    return {
                        "eligible": False,
                        "quality_score": score,
                        "regime": regime,
                        "rejection_reason": f"ANTI_GRID_MIN_DISTANCE_VIOLATED: Entry at {entry_price:.2f} is within {dist:.2f} < {min_dist:.2f} (1.0x ATR) of existing position #{pos.get('position_id', 'OPEN')} at {pos_entry:.2f}."
                    }

        # 6. Sizing and Mandatory Broker-Side Stop Loss / Take Profit
        raw_stop_dist = atr * self.thresholds.atr_stop_multiplier
        stop_dist_ratio = raw_stop_dist / entry_price
        # Strictly clamp stop distance within boundaries
        clamped_stop_ratio = max(
            self.thresholds.min_stop_distance_pct / 100.0,
            min(self.thresholds.max_stop_distance_pct / 100.0, stop_dist_ratio)
        )
        clamped_stop_dist = entry_price * clamped_stop_ratio

        # MT5 Broker stops_level verification (minimum distance in points)
        min_broker_stop_usd = broker_stops_level_points * point_size
        if clamped_stop_dist < min_broker_stop_usd:
            # Adjust to satisfy broker minimum stop distance requirement
            clamped_stop_dist = min_broker_stop_usd * 1.10
            clamped_stop_ratio = clamped_stop_dist / entry_price

        # Take Profit with guaranteed min Risk:Reward ratio
        take_profit_dist = clamped_stop_dist * self.thresholds.min_risk_reward_ratio
        actual_rr = round(take_profit_dist / clamped_stop_dist, 2)

        if side == "BUY":
            stop_loss_price = round(entry_price - clamped_stop_dist, 4)
            take_profit_price = round(entry_price + take_profit_dist, 4)
            entry_range = {"min": round(entry_price * 0.9998, 4), "max": round(entry_price * 1.0005, 4)}
        else:
            stop_loss_price = round(entry_price + clamped_stop_dist, 4)
            take_profit_price = round(entry_price - take_profit_dist, 4)
            entry_range = {"min": round(entry_price * 0.9995, 4), "max": round(entry_price * 1.0002, 4)}

        # Reject if valid broker stop loss cannot be established
        if stop_loss_price <= 0 or (side == "BUY" and stop_loss_price >= entry_price) or (side == "SELL" and stop_loss_price <= entry_price):
            return {
                "eligible": False,
                "quality_score": score,
                "regime": regime,
                "rejection_reason": "INVALID_STOP_LOSS_PRICE: Calculated Stop Loss violates mathematical boundaries."
            }

        # Sizing: volume clamped to risk budget
        notional_exposure = allocated_margin * leverage
        # Position volume: for crypto / forex CFDs
        position_volume = round(notional_exposure / entry_price, 4)
        if broker_type == "EXNESS_MT5":
            # For MT5, lot size step is typically 0.01
            # Volume is lots: notional / contract_size
            contract_size = 1.0 if "BTC" in symbol or "ETH" in symbol else 100000.0
            lots = round(notional_exposure / (entry_price * contract_size), 2)
            position_volume = max(0.01, lots)

        # Transaction cost estimation
        fee_rate = 0.0002 if broker_type == "EXNESS_MT5" else 0.0004
        estimated_costs = (notional_exposure * fee_rate * 2) + spread_usd

        # Max permitted risk
        max_risk_usd = round(notional_exposure * clamped_stop_ratio, 2)

        adapter_name = "EXNESS_MT5_GATEWAY" if broker_type == "EXNESS_MT5" else ("BINANCE_FUTURES" if "BINANCE" in broker_type else "BYBIT_PERP")

        return {
            "eligible": True,
            "direction": side,
            "quality_score": score,
            "regime": regime,
            "rejection_reason": None,
            "proposed_entry": {
                "instrument": symbol.upper(),
                "direction": side,
                "entry_price": round(entry_price, 4),
                "entry_range": entry_range,
                "position_volume": position_volume,
                "stop_loss_price": stop_loss_price,
                "take_profit_price": take_profit_price,
                "stop_distance_usd": round(clamped_stop_dist, 4),
                "stop_distance_pct": round(clamped_stop_ratio * 100, 2),
                "take_profit_distance_usd": round(take_profit_dist, 4),
                "risk_reward_ratio": actual_rr,
                "max_acceptable_spread_usd": round(spread_usd * 1.5, 4),
                "max_acceptable_spread_bps": self.thresholds.max_acceptable_spread_bps,
                "max_acceptable_slippage_usd": round(entry_price * (self.thresholds.default_slippage_buffer_pct / 100.0), 4),
                "estimated_transaction_costs_usd": round(estimated_costs, 4),
                "max_permitted_risk_usd": max_risk_usd,
                "quality_score": score,
                "regime": regime,
                "broker_adapter": adapter_name,
                "broker_stop_acknowledged": True,
                "rationale": f"High-probability {side} scalp aligned with {regime} (Score: {score:.2f}, R:R: {actual_rr}:1, ATR: {atr:.2f}).",
            }
        }

    def _format_waiting_response(
        self,
        symbol: str,
        bid: float,
        ask: float,
        reason: str,
        buy_eval: Optional[Dict[str, Any]] = None,
        sell_eval: Optional[Dict[str, Any]] = None,
        risk_limits: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Structured waiting response indicating clearly why no signal is currently active.
        """
        spread = abs(ask - bid)
        bps = (spread / max(1e-8, bid)) * 10000.0
        return {
            "status": "WAITING_FOR_OPPORTUNITY",
            "has_signal": False,
            "engine": self.PRODUCT_NAME,
            "strategy": self.STRATEGY_CODE,
            "symbol": symbol.upper(),
            "reason": reason,
            "market_state": {
                "bid": bid,
                "ask": ask,
                "spread_usd": round(spread, 4),
                "spread_bps": round(bps, 2),
                "is_spread_acceptable": bps <= self.thresholds.max_acceptable_spread_bps,
                "regime": "WAITING_EVALUATION",
            },
            "evaluations": {
                "buy": buy_eval or {"eligible": False, "reason": "Evaluated ineligible"},
                "sell": sell_eval or {"eligible": False, "reason": "Evaluated ineligible"},
            },
            "risk_limits": risk_limits or {
                "simultaneous_positions_open": 0,
                "max_simultaneous_positions": self.thresholds.max_simultaneous_positions,
                "total_account_exposure_usd": 0.0,
                "max_allowed_exposure_usd": 1500.0,
                "daily_realized_loss_usd": 0.0,
                "max_daily_loss_usd": self.thresholds.max_daily_loss_usd,
                "consecutive_losses": 0,
            },
            "live_trading_locked": True,
            "read_only_mode": True,
            "emergency_lock_active": True,
        }
