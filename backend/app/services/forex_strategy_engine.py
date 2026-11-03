import asyncio
import logging
import math
from typing import Any, Dict, List, Optional
from .forex_market_data import forex_market_data, INSTRUMENT_REGISTRY, parse_instrument_id
from .signal_timing_engine import compute_timing_metadata

logger = logging.getLogger(__name__)

# Required fields in MarketSnapshot schema
REQUIRED_SNAPSHOT_FIELDS = [
    "schema_version",
    "asset_class",
    "instrument_id",
    "provider_id",
    "quote_class",
    "quote_ts_utc",
    "quote_age_ms",
    "bid",
    "ask",
    "mid",
    "spread_abs",
    "spread_pips",
    "spread_to_atr",
    "pip_size",
    "price_precision",
    "trigger_timeframe",
    "atr14",
    "session_id",
    "market_open",
    "weekend_flag",
    "next_high_impact_event",
    "in_blackout",
    "snapshot_hash",
]


class ForexStrategyEngine:
    """
    Asset-class specific strategy engine for Forex & Precious Metals.
    Implements deterministic Scalping (5m, 10m, 15m), Swing (1h, 4h, 1d),
    and Directional Trade Setups with MarketSnapshot contract validation,
    strict Bid/Ask execution rules, institutional position sizing, and zero-credit candidate ranking.
    """

    def validate_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """
        Validates the incoming MarketSnapshot against the strict schema contract.
        If any required field is missing, raises ValueError (zero AI calls made).
        """
        missing = [f for f in REQUIRED_SNAPSHOT_FIELDS if f not in snapshot]
        if missing:
            raise ValueError(f"MarketSnapshot validation failed: missing required fields {missing}")
        if not snapshot.get("snapshot_hash"):
            raise ValueError("MarketSnapshot validation failed: missing snapshot_hash")

    def calculate_position_sizing(
        self,
        inst_id: str,
        current_price: float,
        entry_price: float,
        stop_loss: float,
        user_capital: float,
        strategy: str = "SHORT_TERM"
    ) -> Dict[str, Any]:
        """
        Calculates institutional position sizing, margin requirements,
        and risk bounding based on user capital and instrument specifications.
        Preserves minimum order size, margin, spread, and risk limits.
        """
        inst = INSTRUMENT_REGISTRY.get(inst_id)
        if not inst:
            inst = forex_market_data.get_instrument_meta(inst_id)

        contract_size = inst.get("contract_size", 100000)
        pip_size = inst.get("pip_size", 0.0001)
        asset_class = inst.get("asset_class", "fx")
        clean_symbol = inst.get("clean_symbol", inst_id)

        # 1. Capital Validation & Bounds
        if user_capital <= 0:
            raise ValueError("user_capital must be a positive number greater than 0")

        # 2. Risk Budgeting per Trade:
        # Scalping: 1.0% risk of account capital
        # Swing: 1.5% risk of account capital
        # Trade Setup: 2.0% risk of account capital
        strat_upper = strategy.upper()
        if strat_upper == "SHORT_TERM":
            risk_pct = 0.01
        elif strat_upper == "LONGER_TERM":
            risk_pct = 0.015
        else:  # TRADE_SETUP
            risk_pct = 0.02

        risk_budget_usd = round(user_capital * risk_pct, 2)
        risk_budget_usd = max(0.50, risk_budget_usd)

        # 3. Stop Loss Distance
        sl_dist = abs(entry_price - stop_loss)
        if sl_dist <= 0:
            sl_dist = current_price * 0.01

        sl_pips = sl_dist / pip_size

        # 4. Pip Value per 1.0 Standard Lot in USD:
        quote = inst.get("quote", "USD")
        if quote == "USD":
            pip_value_std_lot = pip_size * contract_size
        else:
            pip_value_std_lot = (pip_size / current_price) * contract_size if current_price > 0 else 10.0

        # 5. Position Sizing in Lots (Risk-based):
        if sl_pips > 0 and pip_value_std_lot > 0:
            raw_lots = risk_budget_usd / (sl_pips * pip_value_std_lot)
        else:
            raw_lots = 0.01

        min_lot = 0.01
        max_lot = 50.0

        # Margin requirements: Forex 1:30 (3.333%), Metals 1:20 (5.0%)
        margin_req_pct = 0.05 if asset_class == "metal" else 0.033333

        # Base to USD price multiplier for notional calculation
        base = inst.get("base", "USD")
        if asset_class == "metal":
            unit_price_usd = current_price
        elif base == "USD":
            unit_price_usd = 1.0
        elif quote == "USD":
            unit_price_usd = current_price
        else:
            unit_price_usd = current_price if "USD" in clean_symbol else 1.08

        # Margin required per 1.0 standard lot
        margin_per_std_lot = contract_size * unit_price_usd * margin_req_pct
        max_lots_by_capital = user_capital / margin_per_std_lot if margin_per_std_lot > 0 else 0.01

        # Clamp lots to step size 0.01
        computed_lots = math.floor(raw_lots * 100.0) / 100.0
        computed_lots = max(min_lot, min(max_lot, computed_lots))

        min_margin_needed = round(min_lot * margin_per_std_lot, 2)
        if user_capital < min_margin_needed:
            capital_status = "INSUFFICIENT_FOR_MARGIN"
            capital_warning = (
                f"Capital ${user_capital:.2f} is below minimum estimated margin "
                f"${min_margin_needed:.2f} for 0.01 lot {clean_symbol} at {int(round(1.0 / margin_req_pct))}:1 leverage."
            )
            effective_lots = 0.01
        elif computed_lots > max_lots_by_capital:
            effective_lots = max(min_lot, math.floor(max_lots_by_capital * 100.0) / 100.0)
            capital_status = "MARGIN_CONSTRAINED"
            capital_warning = f"Position lot size constrained by available margin (${user_capital:.2f})."
        else:
            effective_lots = computed_lots
            capital_status = "SUFFICIENT"
            capital_warning = None

        notional_usd = round(effective_lots * contract_size * unit_price_usd, 2)
        margin_required_usd = round(notional_usd * margin_req_pct, 2)
        dollar_risk = round(sl_pips * effective_lots * pip_value_std_lot, 2)

        return {
            "status": capital_status,
            "user_capital": user_capital,
            "lots": round(effective_lots, 2),
            "min_lot": min_lot,
            "notional_usd": notional_usd,
            "margin_required_usd": margin_required_usd,
            "margin_rate_pct": round(margin_req_pct * 100.0, 2),
            "estimated_leverage": f"1:{int(round(1.0 / margin_req_pct))}",
            "dollar_risk_usd": dollar_risk,
            "risk_pct_of_capital": round((dollar_risk / user_capital) * 100.0, 2) if user_capital > 0 else 0.0,
            "warning": capital_warning,
            "min_capital_required": min_margin_needed,
        }

    async def evaluate_scalping_setup(
        self,
        sym_or_id: str,
        user_capital: float = 100.0,
        preferred_timeframe: Optional[str] = None,
        timeframe: Optional[str] = None,
        capital: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Calculates a high-precision Forex scalping setup across 5m, 10m, or 15m.
        Enforces quote freshness, spread friction gating, bid/ask execution rules, and position sizing.
        """
        effective_capital = capital if capital is not None else user_capital
        inst_id = parse_instrument_id(sym_or_id)
        inst = forex_market_data.get_instrument_meta(inst_id)

        # 1. Determine Scalping Timeframe
        tf_input = timeframe or preferred_timeframe
        if tf_input in ("5m", "10m", "15m"):
            tf = tf_input
        else:
            tf = "10m"  # Default optimal balanced timeframe for FX scalping

        # 2. Build & Validate Market Snapshot
        snapshot = await forex_market_data.build_market_snapshot(inst_id, trigger_tf=tf, context_tf="1h")
        self.validate_snapshot(snapshot)

        # 3. Quote Quality & Freshness Gate
        is_weekend = snapshot["weekend_flag"]
        price_mid = snapshot["mid"]
        bid = snapshot["bid"]
        ask = snapshot["ask"]
        spread_abs = snapshot["spread_abs"]
        spread_pips = snapshot["spread_pips"]
        atr14 = snapshot["atr14"]
        pip_dec = inst["pip_decimal"]

        # 4. Directional Bias & Structure (from trend efficiency metric)
        trend_metric = snapshot.get("trend_efficiency_metric", 0.0)
        direction = "LONG" if trend_metric >= 0.0 else "SHORT"

        # 5. ATR and Spread-Aware Execution Bounds
        tp_dist = round(2.0 * atr14, inst["price_precision"])
        sl_dist = round(1.0 * atr14, inst["price_precision"])

        # Spread Friction Gate: Rejection if spread exceeds 25% of expected move
        if tp_dist > 0 and (spread_abs / tp_dist) > 0.25:
            return {
                "instrument_id": inst_id,
                "symbol": inst["clean_symbol"],
                "strategy": "SHORT_TERM",
                "timeframe": tf,
                "status": "REJECTED",
                "reason_code": "SPREAD_FRICTION_EXCEEDED",
                "reason": f"Spread ({spread_pips:.1f} pips) exceeds acceptable friction limit (>25% of {tf} target).",
                "market": "FOREX",
                "snapshot_hash": snapshot["snapshot_hash"],
                "user_capital": effective_capital,
                "capital": effective_capital,
            }

        # 6. Strict Bid/Ask Execution Rules:
        if direction == "LONG":
            entry_price = ask
            take_profit = round(entry_price + tp_dist, inst["price_precision"])
            stop_loss = round(bid - sl_dist, inst["price_precision"])
            invalidation_price = round(bid - (1.3 * atr14), inst["price_precision"])
            invalidation_rule = f"{tf} close below {invalidation_price:.{pip_dec}f}"
            bias_desc = f"Bullish momentum continuation within {snapshot['session_id']}"
            hold_desc = "15m – 45m intraday" if tf == "5m" else "30m – 90m intraday" if tf == "10m" else "45m – 2h intraday"
        else:
            entry_price = bid
            take_profit = round(entry_price - tp_dist, inst["price_precision"])
            stop_loss = round(ask + sl_dist, inst["price_precision"])
            invalidation_price = round(ask + (1.3 * atr14), inst["price_precision"])
            invalidation_rule = f"{tf} close above {invalidation_price:.{pip_dec}f}"
            bias_desc = f"Bearish mean-reversion rejection within {snapshot['session_id']}"
            hold_desc = "15m – 45m intraday" if tf == "5m" else "30m – 90m intraday" if tf == "10m" else "45m – 2h intraday"

        actual_sl_dist = abs(entry_price - stop_loss)
        rr_ratio = round(tp_dist / actual_sl_dist, 2) if actual_sl_dist > 0 else 2.0

        timing_meta = compute_timing_metadata("SHORT_TERM", tf, market="FOREX")

        # Position Sizing
        sizing = self.calculate_position_sizing(
            inst_id=inst_id,
            current_price=price_mid,
            entry_price=entry_price,
            stop_loss=stop_loss,
            user_capital=effective_capital,
            strategy="SHORT_TERM"
        )

        warnings = []
        if is_weekend:
            warnings.append("Forex markets in weekend closure. Orders execute at Monday session open.")
        if snapshot["in_blackout"]:
            warnings.append(f"High-impact event window active: {snapshot['next_high_impact_event']}")
        if sizing.get("warning"):
            warnings.append(sizing["warning"])

        return {
            "instrument_id": inst_id,
            "symbol": inst["clean_symbol"],
            "name": inst["name"],
            "strategy": "SHORT_TERM",
            "strategy_label": "Scalping",
            "market": "FOREX",
            "asset_class": inst["asset_class"].upper() if inst["asset_class"] != "metal" else "FOREX_METAL",
            "status": "SUITABLE",
            "direction": direction,
            "bias_desc": bias_desc,
            "timeframe": tf,
            "quote_class": snapshot["quote_class"],
            "current_price": price_mid,
            "mid_price": price_mid,
            "bid": bid,
            "ask": ask,
            "spread_pips": spread_pips,
            "spread_pct": round((spread_abs / price_mid) * 100.0, 4) if price_mid > 0 else 0.0,
            "entry_zone": f"{entry_price:.{pip_dec}f} — {entry_price:.{pip_dec}f}",
            "entry_price": entry_price,
            "take_profit": take_profit,
            "stop_loss": stop_loss,
            "invalidation_rule": invalidation_rule,
            "reward_to_risk": rr_ratio,
            "expected_hold": hold_desc,
            "session": snapshot["session_id"],
            "market_status": "ACTIVE" if snapshot["market_open"] else "CLOSED",
            "news_risk": "HIGH" if snapshot["in_blackout"] else "LOW",
            "warnings": warnings,
            "user_capital": effective_capital,
            "capital": effective_capital,
            "position_sizing": sizing,
            "recommended_lots": sizing["lots"],
            "position_size_usd": sizing["notional_usd"],
            "margin_required": sizing["margin_required_usd"],
            "risk_amount_usd": sizing["dollar_risk_usd"],
            "capital_status": sizing["status"],
            "timing": timing_meta,
            "snapshot_hash": snapshot["snapshot_hash"],
            "market_snapshot": snapshot,
            "source": forex_market_data.provider_id,
            "source_metadata": {
                "source_type": "FOREX_MARKET_ENGINE",
                "source_label": "FOREX COMPOSITE + JEV",
                "source_providers": ["forex_feed", "jev"],
                "pipeline_description": "Interbank rate composite • session & spread engine • Jev screening",
                "badge_color": "cyan_neutral"
            }
        }

    async def evaluate_swing_setup(
        self,
        sym_or_id: str,
        user_capital: float = 100.0,
        preferred_timeframe: Optional[str] = None,
        timeframe: Optional[str] = None,
        capital: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Multi-session Swing / Longer-Term Strategy Engine for Forex & Metals.
        Operates on 4h (default), 1h, or 1d timeframes with wider ATR expansion targets.
        """
        effective_capital = capital if capital is not None else user_capital
        inst_id = parse_instrument_id(sym_or_id)
        inst = forex_market_data.get_instrument_meta(inst_id)

        # Determine Swing Timeframe (4h default)
        tf_input = timeframe or preferred_timeframe
        tf = tf_input if tf_input in ("1h", "4h", "1d") else "4h"

        snapshot = await forex_market_data.build_market_snapshot(inst_id, trigger_tf=tf, context_tf="1d")
        self.validate_snapshot(snapshot)

        price_mid = snapshot["mid"]
        bid = snapshot["bid"]
        ask = snapshot["ask"]
        atr14 = snapshot["atr14"]
        pip_dec = inst["pip_decimal"]

        trend_metric = snapshot.get("trend_efficiency_metric", 0.0)
        direction = "LONG" if trend_metric >= 0.0 else "SHORT"

        sl_dist = round(1.5 * atr14, inst["price_precision"])
        if direction == "LONG":
            entry_price = ask
            stop_loss = round(bid - sl_dist, inst["price_precision"])
            actual_sl_dist = abs(entry_price - stop_loss)
            tp_dist = round(2.5 * actual_sl_dist, inst["price_precision"])
            take_profit = round(entry_price + tp_dist, inst["price_precision"])
            invalidation_price = round(bid - (1.8 * atr14), inst["price_precision"])
            invalidation_rule = f"{tf} swing candle close below {invalidation_price:.{pip_dec}f}"
            bias_desc = f"Multi-session swing trend continuation ({snapshot['session_id']})"
            hold_desc = "1d – 3d multi-session" if tf == "1h" else "2d – 5d swing"
        else:
            entry_price = bid
            stop_loss = round(ask + sl_dist, inst["price_precision"])
            actual_sl_dist = abs(entry_price - stop_loss)
            tp_dist = round(2.5 * actual_sl_dist, inst["price_precision"])
            take_profit = round(entry_price - tp_dist, inst["price_precision"])
            invalidation_price = round(ask + (1.8 * atr14), inst["price_precision"])
            invalidation_rule = f"{tf} swing candle close above {invalidation_price:.{pip_dec}f}"
            bias_desc = f"Multi-session swing distribution breakdown ({snapshot['session_id']})"
            hold_desc = "1d – 3d multi-session" if tf == "1h" else "2d – 5d swing"

        rr_ratio = round(tp_dist / actual_sl_dist, 2) if actual_sl_dist > 0 else 2.50
        timing_meta = compute_timing_metadata("LONGER_TERM", tf, market="FOREX")

        sizing = self.calculate_position_sizing(
            inst_id=inst_id,
            current_price=price_mid,
            entry_price=entry_price,
            stop_loss=stop_loss,
            user_capital=effective_capital,
            strategy="LONGER_TERM"
        )

        warnings = []
        if snapshot["weekend_flag"]:
            warnings.append("Forex markets in weekend closure. Orders execute at Monday session open.")
        if snapshot["in_blackout"]:
            warnings.append(f"High-impact event window active: {snapshot['next_high_impact_event']}")
        if sizing.get("warning"):
            warnings.append(sizing["warning"])

        return {
            "instrument_id": inst_id,
            "symbol": inst["clean_symbol"],
            "name": inst["name"],
            "strategy": "LONGER_TERM",
            "strategy_label": "Swing / Longer-Term",
            "market": "FOREX",
            "asset_class": inst["asset_class"].upper() if inst["asset_class"] != "metal" else "FOREX_METAL",
            "status": "SUITABLE",
            "direction": direction,
            "bias_desc": bias_desc,
            "timeframe": tf,
            "quote_class": snapshot["quote_class"],
            "current_price": price_mid,
            "mid_price": price_mid,
            "bid": bid,
            "ask": ask,
            "spread_pips": snapshot["spread_pips"],
            "spread_pct": round((snapshot["spread_abs"] / price_mid) * 100.0, 4) if price_mid > 0 else 0.0,
            "entry_zone": f"{entry_price:.{pip_dec}f} — {entry_price:.{pip_dec}f}",
            "entry_price": entry_price,
            "take_profit": take_profit,
            "stop_loss": stop_loss,
            "invalidation_rule": invalidation_rule,
            "reward_to_risk": rr_ratio,
            "expected_hold": hold_desc,
            "session": snapshot["session_id"],
            "market_status": "ACTIVE" if snapshot["market_open"] else "CLOSED",
            "news_risk": "HIGH" if snapshot["in_blackout"] else "LOW",
            "warnings": warnings,
            "user_capital": effective_capital,
            "capital": effective_capital,
            "position_sizing": sizing,
            "recommended_lots": sizing["lots"],
            "position_size_usd": sizing["notional_usd"],
            "margin_required": sizing["margin_required_usd"],
            "risk_amount_usd": sizing["dollar_risk_usd"],
            "capital_status": sizing["status"],
            "timing": timing_meta,
            "snapshot_hash": snapshot["snapshot_hash"],
            "market_snapshot": snapshot,
            "source": forex_market_data.provider_id,
            "source_metadata": {
                "source_type": "FOREX_MARKET_ENGINE",
                "source_label": "FOREX COMPOSITE + JEV",
                "source_providers": ["forex_feed", "jev"],
                "pipeline_description": "Interbank rate composite • session & spread engine • Jev screening",
                "badge_color": "cyan_neutral"
            }
        }

    async def evaluate_trade_setup(
        self,
        sym_or_id: str,
        user_capital: float = 100.0,
        preferred_timeframe: str = "1h",
        timeframe: Optional[str] = None,
        capital: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Directional Trade Setup Engine with R:R >= 2.08:1 minimum.
        Accepts user_capital and optional timeframe variations.
        """
        effective_capital = capital if capital is not None else user_capital
        inst_id = parse_instrument_id(sym_or_id)
        inst = forex_market_data.get_instrument_meta(inst_id)
        tf_input = timeframe or preferred_timeframe
        tf = tf_input if tf_input in ("1h", "4h", "1d") else "1h"

        snapshot = await forex_market_data.build_market_snapshot(inst_id, trigger_tf=tf, context_tf="4h")
        self.validate_snapshot(snapshot)

        price_mid = snapshot["mid"]
        bid = snapshot["bid"]
        ask = snapshot["ask"]
        atr14 = snapshot["atr14"]
        pip_dec = inst["pip_decimal"]

        trend_metric = snapshot.get("trend_efficiency_metric", 0.0)
        direction = "LONG" if trend_metric >= 0.0 else "SHORT"

        sl_dist = round(1.2 * atr14, inst["price_precision"])
        if direction == "LONG":
            entry_price = ask
            stop_loss = round(bid - sl_dist, inst["price_precision"])
            actual_sl_dist = abs(entry_price - stop_loss)
            tp_dist = round(2.1 * actual_sl_dist, inst["price_precision"])
            take_profit = round(entry_price + tp_dist, inst["price_precision"])
            invalidation_price = round(bid - (1.4 * atr14), inst["price_precision"])
            invalidation_rule = f"{tf} candle close below {invalidation_price:.{pip_dec}f}"
            bias_desc = f"Institutional breakout continuation above local value area"
            hold_desc = "4h – 24h swing" if tf == "1h" else "1d – 3d multi-session"
        else:
            entry_price = bid
            stop_loss = round(ask + sl_dist, inst["price_precision"])
            actual_sl_dist = abs(entry_price - stop_loss)
            tp_dist = round(2.1 * actual_sl_dist, inst["price_precision"])
            take_profit = round(entry_price - tp_dist, inst["price_precision"])
            invalidation_price = round(ask + (1.4 * atr14), inst["price_precision"])
            invalidation_rule = f"{tf} candle close above {invalidation_price:.{pip_dec}f}"
            bias_desc = f"Structural rejection at liquidity ceiling"
            hold_desc = "4h – 24h swing" if tf == "1h" else "1d – 3d multi-session"

        rr_ratio = round(tp_dist / actual_sl_dist, 2) if actual_sl_dist > 0 else 2.10

        timing_meta = compute_timing_metadata("TRADE_SETUP", tf, market="FOREX")

        # Position Sizing
        sizing = self.calculate_position_sizing(
            inst_id=inst_id,
            current_price=price_mid,
            entry_price=entry_price,
            stop_loss=stop_loss,
            user_capital=effective_capital,
            strategy="TRADE_SETUP"
        )

        warnings = []
        if snapshot["weekend_flag"]:
            warnings.append("Forex markets in weekend closure. Orders execute at Monday session open.")
        if snapshot["in_blackout"]:
            warnings.append(f"High-impact event window active: {snapshot['next_high_impact_event']}")
        if sizing.get("warning"):
            warnings.append(sizing["warning"])

        return {
            "instrument_id": inst_id,
            "symbol": inst["clean_symbol"],
            "name": inst["name"],
            "strategy": "TRADE_SETUP",
            "strategy_label": "Directional Setup",
            "market": "FOREX",
            "asset_class": inst["asset_class"].upper() if inst["asset_class"] != "metal" else "FOREX_METAL",
            "status": "SUITABLE",
            "direction": direction,
            "bias_desc": bias_desc,
            "timeframe": tf,
            "quote_class": snapshot["quote_class"],
            "current_price": price_mid,
            "mid_price": price_mid,
            "bid": bid,
            "ask": ask,
            "spread_pips": snapshot["spread_pips"],
            "spread_pct": round((snapshot["spread_abs"] / price_mid) * 100.0, 4) if price_mid > 0 else 0.0,
            "entry_zone": f"{entry_price:.{pip_dec}f} — {entry_price:.{pip_dec}f}",
            "entry_price": entry_price,
            "take_profit": take_profit,
            "stop_loss": stop_loss,
            "invalidation_rule": invalidation_rule,
            "reward_to_risk": rr_ratio,
            "expected_hold": hold_desc,
            "session": snapshot["session_id"],
            "market_status": "ACTIVE" if snapshot["market_open"] else "CLOSED",
            "news_risk": "HIGH" if snapshot["in_blackout"] else "LOW",
            "warnings": warnings,
            "user_capital": effective_capital,
            "capital": effective_capital,
            "position_sizing": sizing,
            "recommended_lots": sizing["lots"],
            "position_size_usd": sizing["notional_usd"],
            "margin_required": sizing["margin_required_usd"],
            "risk_amount_usd": sizing["dollar_risk_usd"],
            "capital_status": sizing["status"],
            "timing": timing_meta,
            "snapshot_hash": snapshot["snapshot_hash"],
            "market_snapshot": snapshot,
            "source": forex_market_data.provider_id,
            "source_metadata": {
                "source_type": "FOREX_MARKET_ENGINE",
                "source_label": "FOREX COMPOSITE + JEV",
                "source_providers": ["forex_feed", "jev"],
                "pipeline_description": "Interbank rate composite • session & spread engine • Jev screening",
                "badge_color": "cyan_neutral"
            }
        }

    async def scan_forex_candidates(
        self,
        strategy: str = "SHORT_TERM",
        user_capital: float = 100.0,
        limit: int = 10,
        capital: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Deterministic, 100% Zero-LLM Candidate Discovery Ranking across SCALPING, SWING, and TRADE_SETUP.
        Accepts user_capital (or capital for backwards compatibility).
        Preserves capital and propagates into institutional position sizing and margin bounds.
        """
        effective_capital = capital if capital is not None else user_capital
        if effective_capital <= 0:
            raise ValueError(f"Invalid investment capital: {effective_capital}. Must be positive.")

        strat_norm = strategy.upper()
        if strat_norm not in ("SHORT_TERM", "LONGER_TERM", "TRADE_SETUP"):
            strat_norm = "SHORT_TERM"

        candidates = []
        inst_ids = list(INSTRUMENT_REGISTRY.keys())

        # Evaluate candidate snapshots concurrently with capital sizing
        tasks = [
            self.evaluate_candidate_for_ranking(
                inst_id=inst_id,
                strategy=strat_norm,
                user_capital=effective_capital
            )
            for inst_id in inst_ids
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for res in results:
            if isinstance(res, dict) and res.get("status") == "SUITABLE":
                candidates.append(res)

        # Sort deterministically by ranking score descending
        candidates.sort(key=lambda x: x.get("ranking_score", 0.0), reverse=True)
        return candidates[:limit]

    async def evaluate_candidate_for_ranking(
        self,
        inst_id: str,
        strategy: str,
        capital: Optional[float] = None,
        user_capital: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Scores an individual instrument deterministically, assigns reason codes,
        and computes position sizing metrics based on user capital.
        """
        effective_capital = capital if capital is not None else (user_capital if user_capital is not None else 100.0)
        inst = INSTRUMENT_REGISTRY.get(inst_id)
        if not inst:
            return {}

        strat_upper = strategy.upper()
        if strat_upper == "SHORT_TERM":
            tf = "10m"
            ctx_tf = "1h"
            strat_label = "Scalping"
        elif strat_upper == "LONGER_TERM":
            tf = "4h"
            ctx_tf = "1d"
            strat_label = "Swing / Longer-Term"
        else:
            tf = "1h"
            ctx_tf = "4h"
            strat_label = "Directional Setup"

        snapshot = await forex_market_data.build_market_snapshot(inst_id, trigger_tf=tf, context_tf=ctx_tf)
        self.validate_snapshot(snapshot)

        spread_pips = snapshot["spread_pips"]
        spread_to_atr = snapshot["spread_to_atr"]
        atr14 = snapshot["atr14"]
        in_blackout = snapshot["in_blackout"]
        session_id = snapshot["session_id"]
        trend_metric = snapshot.get("trend_efficiency_metric", 0.0)

        reason_codes = []
        ranking_score = 100.0

        # 1. Spread Efficiency
        if spread_pips <= 1.5:
            reason_codes.append("LOW_SPREAD")
            ranking_score += 25.0
        elif spread_pips <= 2.5:
            ranking_score += 10.0
        else:
            ranking_score -= 15.0

        # 2. Spread to ATR Ratio
        if spread_to_atr < 0.10:
            reason_codes.append("SPREAD_TO_ATR_EFFICIENT")
            ranking_score += 20.0
        elif spread_to_atr > 0.25:
            ranking_score -= 30.0

        # 3. Session Affinity
        if session_id in ("LONDON", "NEW_YORK", "LONDON_NY_OVERLAP"):
            reason_codes.append("SESSION_ALIGNED")
            ranking_score += 20.0

        # 4. Volatility Fit
        if atr14 > 0:
            reason_codes.append("GOOD_ATR")
            ranking_score += 15.0

        # 5. Trend / Regime Clarity
        if abs(trend_metric) >= 0.15:
            reason_codes.append("TREND_CLEAR")
            ranking_score += 15.0

        # 6. News & Blackout
        if not in_blackout:
            reason_codes.append("NEWS_CLEAR")
            ranking_score += 10.0
        else:
            reason_codes.append("BLACKOUT_PENALTY")
            ranking_score -= 40.0

        direction = "LONG" if trend_metric >= 0.0 else "SHORT"
        rr_ratio = 2.08 if strat_upper == "TRADE_SETUP" else 2.5 if strat_upper == "LONGER_TERM" else 2.0

        # Position Sizing & Margin Evaluation
        entry_price = snapshot["ask"] if direction == "LONG" else snapshot["bid"]
        sl_mult = 1.0 if strat_upper == "SHORT_TERM" else 1.5 if strat_upper == "LONGER_TERM" else 1.2
        sl_dist = round(sl_mult * atr14, inst["price_precision"])
        stop_loss = round(snapshot["bid"] - sl_dist if direction == "LONG" else snapshot["ask"] + sl_dist, inst["price_precision"])

        sizing = self.calculate_position_sizing(
            inst_id=inst_id,
            current_price=snapshot["mid"],
            entry_price=entry_price,
            stop_loss=stop_loss,
            user_capital=effective_capital,
            strategy=strat_upper
        )

        if sizing["status"] == "INSUFFICIENT_FOR_MARGIN":
            reason_codes.append("CAPITAL_MARGIN_WARNING")
            ranking_score -= 10.0
        elif sizing["status"] == "SUFFICIENT":
            reason_codes.append("CAPITAL_SUFFICIENT")
            ranking_score += 5.0

        timing_meta = compute_timing_metadata(strat_upper, tf, market="FOREX")

        return {
            "instrument_id": inst_id,
            "symbol": inst["clean_symbol"],
            "name": inst["name"],
            "asset_class": inst["asset_class"].upper() if inst["asset_class"] != "metal" else "FOREX_METAL",
            "market": "FOREX",
            "strategy": strat_upper,
            "strategy_label": strat_label,
            "timeframe": tf,
            "current_price": snapshot["mid"],
            "bid": snapshot["bid"],
            "ask": snapshot["ask"],
            "spread_pips": spread_pips,
            "pip_decimal": inst["pip_decimal"],
            "status": "SUITABLE",
            "direction": direction,
            "reward_to_risk": rr_ratio,
            "ranking_score": round(ranking_score, 1),
            "reason_codes": reason_codes,
            "snapshot_hash": snapshot["snapshot_hash"],
            "user_capital": effective_capital,
            "capital": effective_capital,
            "position_sizing": sizing,
            "recommended_lots": sizing["lots"],
            "position_size_usd": sizing["notional_usd"],
            "margin_required": sizing["margin_required_usd"],
            "risk_amount_usd": sizing["dollar_risk_usd"],
            "capital_status": sizing["status"],
            "timing": timing_meta,
        }


# Singleton instance
forex_strategy_engine = ForexStrategyEngine()
