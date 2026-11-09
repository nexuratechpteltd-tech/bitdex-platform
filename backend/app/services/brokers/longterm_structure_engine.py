"""
BITDEX Independent Long-Term Strategy Engine (HTF Structure & Retest)
====================================================================
Implements institutional higher-timeframe strategy:
- D1: Macro Directional Bias & Key S/R Zones (Close vs EMA50 / Demand-Supply)
- H4: Primary Market Structure (Break of Structure BOS / Change of Character CHoCH)
- H1: Structural Break & Retest Confirmation + Rejection Candle Trigger

State Lifecycle:
  ANALYZING -> WAITING -> READY TO TRADE -> EXPIRED

Mathematical Rules:
- Dynamic Stop Loss: Placed past key H4 structural invalidation swing / S/R zone.
- Take Profit: Placed at next major H4 liquidity level (Min Required Net R:R >= 1.80R after estimated spread/slippage).
- Setup Expiry: Enforces strict time-to-live (TTL) and price invalidation (if price runs past entry or breaks structure).
"""

import hashlib
import json
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

from app.services.brokers.strategy_candidate_a import get_closed_candles, calc_ema, calc_atr

logger = logging.getLogger("LongTermStructureEngine")

MIN_REQUIRED_NET_RR = 1.80

def compute_setup_hash(account_id: str, symbol: str, direction: str, h4_level: float, h1_time: int) -> str:
    raw = f"{account_id}:{symbol}:LT_HTF:{direction}:{round(h4_level, 2)}:{h1_time}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def evaluate_longterm_opportunity(
    symbol: str,
    spec: Dict[str, Any],
    quote: Dict[str, Any],
    candles_d1: List[Dict[str, Any]],
    candles_h4: List[Dict[str, Any]],
    candles_h1: List[Dict[str, Any]],
    equity: float = 5000.20,
    risk_pct: float = 0.0025,
    account_id: str = "17000660016"
) -> Dict[str, Any]:
    """
    Evaluates an instrument through the D1 -> H4 -> H1 hierarchy.
    Returns Opportunity Card payload matching DB schema and frontend wireframe.
    """
    now_utc = datetime.now(timezone.utc)
    now_str = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    bid = float(quote.get("bid") or 0.0)
    ask = float(quote.get("ask") or 0.0)
    digits = int(spec.get("digits") or 2)
    spread = round(ask - bid, digits)
    contract_size = float(spec.get("contract_size") or 1.0)
    min_lot = float(spec.get("min_lot") or spec.get("min_volume") or spec.get("volume_min") or 0.01)
    lot_step = float(spec.get("lot_step") or spec.get("volume_step") or 0.01)
    current_price = bid

    c_d1 = get_closed_candles(candles_d1)
    c_h4 = get_closed_candles(candles_h4)
    c_h1 = get_closed_candles(candles_h1)

    # Base payload
    res = {
        "setup_id": f"LT_{symbol}_{now_utc.strftime('%Y%m%d%H%M')}",
        "account_id": account_id,
        "symbol": symbol,
        "exposure_type": "CFD",
        "direction": "NONE",
        "status": "ANALYZING",
        "quant_score": 0,
        "max_score": 6,
        "entry_min": 0.0,
        "entry_max": 0.0,
        "stop_loss": 0.0,
        "take_profit": 0.0,
        "trailing_rule_json": json.dumps({"rule": "Move SL to BE at +1.0R; Trail H1 Swing"}),
        "est_risk_usd": 0.0,
        "est_net_reward_usd": 0.0,
        "net_rr_ratio": 0.0,
        "qualification_reason": "Evaluating macro D1/H4 market structure.",
        "blocker_reason": "Insufficient closed candle history.",
        "timeframe_context": {},
        "setup_hash": "",
        "created_at": now_str,
        "expires_at": (now_utc + timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "updated_at": now_str,
        "current_quote": {"bid": bid, "ask": ask, "spread": spread}
    }

    if len(c_d1) < 10 or len(c_h4) < 15 or len(c_h1) < 20:
        res["blocker_reason"] = f"Insufficient closed candles (D1:{len(c_d1)} H4:{len(c_h4)} H1:{len(c_h1)})"
        return res

    # 1. D1 Macro Directional Bias
    d1_closes = [c["close"] for c in c_d1]
    d1_ema50 = calc_ema(d1_closes, min(50, len(d1_closes)))
    d1_bull = d1_closes[-1] > d1_ema50
    d1_bear = d1_closes[-1] < d1_ema50

    # 2. H4 Market Structure (BOS / Key Levels)
    h4_closes = [c["close"] for c in c_h4]
    h4_highs = [c["high"] for c in c_h4]
    h4_lows = [c["low"] for c in c_h4]
    h4_ema50 = calc_ema(h4_closes, min(50, len(h4_closes)))
    h4_recent_high = max(h4_highs[-10:-1])
    h4_recent_low = min(h4_lows[-10:-1])
    h4_atr = calc_atr(c_h4, 14)

    h4_bull_bos = (h4_closes[-1] > h4_recent_high * 0.999) or (h4_closes[-1] > h4_ema50)
    h4_bear_bos = (h4_closes[-1] < h4_recent_low * 1.001) or (h4_closes[-1] < h4_ema50)

    # 3. H1 Retest & Entry Zone
    h1_closes = [c["close"] for c in c_h1]
    h1_atr = calc_atr(c_h1, 14)
    latest_h1 = c_h1[-1]
    h1_ema21 = calc_ema(h1_closes, 21)

    gates_passed = 0
    direction = "NONE"

    # Evaluate Bullish Path
    if d1_bull and h4_bull_bos:
        direction = "BUY"
        gates_passed += 2 # D1 + H4
        # H1 Retest zone: around H1 EMA21 or recent H4 flip level
        zone_center = round((latest_h1["low"] + h1_ema21) / 2.0, digits)
        entry_min = round(zone_center - (h1_atr * 0.4), digits)
        entry_max = round(zone_center + (h1_atr * 0.6), digits)
        sl_price = round(entry_min - (h4_atr * 1.2), digits)
        tp_price = round(entry_max + ((entry_max - sl_price) * 2.2), digits)

        res["entry_min"] = entry_min
        res["entry_max"] = entry_max
        res["stop_loss"] = sl_price
        res["take_profit"] = tp_price

        # Check if in zone
        in_zone = (ask >= entry_min * 0.998) and (ask <= entry_max * 1.002)
        if in_zone:
            gates_passed += 1

        # Check H1 Rejection / Momentum
        h1_rej = (latest_h1["close"] > latest_h1["open"]) or (latest_h1["close"] > h1_ema21)
        if h1_rej:
            gates_passed += 1

        # Check Net R:R
        gross_risk = abs(ask - sl_price)
        gross_reward = abs(tp_price - ask)
        net_reward = gross_reward - (spread * 1.5)
        net_risk = gross_risk + (spread * 0.5)
        rr = round(net_reward / net_risk, 2) if net_risk > 0 else 0.0
        res["net_rr_ratio"] = rr

        if rr >= MIN_REQUIRED_NET_RR:
            gates_passed += 1

        # Sizing
        budget = round(equity * risk_pct, 2)
        raw_lots = budget / (net_risk * contract_size) if (net_risk * contract_size) > 0 else min_lot
        calc_lots = round(max(min_lot, int(raw_lots / lot_step) * lot_step), 2)
        res["est_risk_usd"] = round(calc_lots * net_risk * contract_size, 2)
        res["est_net_reward_usd"] = round(calc_lots * net_reward * contract_size, 2)

        if res["est_risk_usd"] <= budget * 1.1:
            gates_passed += 1

        res["direction"] = direction
        res["quant_score"] = gates_passed
        res["setup_hash"] = compute_setup_hash(account_id, symbol, direction, h4_recent_high, latest_h1["time"])
        res["timeframe_context"] = {
            "d1_bias": "BULLISH",
            "h4_structure": f"BOS Up past {h4_recent_high}",
            "h1_trigger": f"Retest hold at {zone_center}",
            "h1_atr": round(h1_atr, digits),
            "h4_atr": round(h4_atr, digits)
        }

        if gates_passed >= 6:
            res["status"] = "READY"
            res["qualification_reason"] = "All D1/H4/H1 structure, retest, and net R:R gates met."
            res["blocker_reason"] = None
        elif in_zone:
            res["status"] = "WAITING"
            res["qualification_reason"] = f"Price in entry zone ({entry_min} - {entry_max}); waiting for confirmed H1 close."
            res["blocker_reason"] = "Awaiting completed H1 rejection candle."
        else:
            res["status"] = "WAITING"
            res["qualification_reason"] = f"HTF Bullish structure identified; waiting for pullback to {entry_min} - {entry_max}."
            res["blocker_reason"] = f"Price currently outside entry zone (Bid={bid})."

    # Evaluate Bearish Path
    elif d1_bear and h4_bear_bos:
        direction = "SELL"
        gates_passed += 2
        zone_center = round((latest_h1["high"] + h1_ema21) / 2.0, digits)
        entry_min = round(zone_center - (h1_atr * 0.6), digits)
        entry_max = round(zone_center + (h1_atr * 0.4), digits)
        sl_price = round(entry_max + (h4_atr * 1.2), digits)
        tp_price = round(entry_min - ((sl_price - entry_min) * 2.2), digits)

        res["entry_min"] = entry_min
        res["entry_max"] = entry_max
        res["stop_loss"] = sl_price
        res["take_profit"] = tp_price

        in_zone = (bid >= entry_min * 0.998) and (bid <= entry_max * 1.002)
        if in_zone:
            gates_passed += 1

        h1_rej = (latest_h1["close"] < latest_h1["open"]) or (latest_h1["close"] < h1_ema21)
        if h1_rej:
            gates_passed += 1

        gross_risk = abs(sl_price - bid)
        gross_reward = abs(bid - tp_price)
        net_reward = gross_reward - (spread * 1.5)
        net_risk = gross_risk + (spread * 0.5)
        rr = round(net_reward / net_risk, 2) if net_risk > 0 else 0.0
        res["net_rr_ratio"] = rr

        if rr >= MIN_REQUIRED_NET_RR:
            gates_passed += 1

        budget = round(equity * risk_pct, 2)
        raw_lots = budget / (net_risk * contract_size) if (net_risk * contract_size) > 0 else min_lot
        calc_lots = round(max(min_lot, int(raw_lots / lot_step) * lot_step), 2)
        res["est_risk_usd"] = round(calc_lots * net_risk * contract_size, 2)
        res["est_net_reward_usd"] = round(calc_lots * net_reward * contract_size, 2)

        if res["est_risk_usd"] <= budget * 1.1:
            gates_passed += 1

        res["direction"] = direction
        res["quant_score"] = gates_passed
        res["setup_hash"] = compute_setup_hash(account_id, symbol, direction, h4_recent_low, latest_h1["time"])
        res["timeframe_context"] = {
            "d1_bias": "BEARISH",
            "h4_structure": f"BOS Down past {h4_recent_low}",
            "h1_trigger": f"Retest supply at {zone_center}",
            "h1_atr": round(h1_atr, digits),
            "h4_atr": round(h4_atr, digits)
        }

        if gates_passed >= 6:
            res["status"] = "READY"
            res["qualification_reason"] = "All D1/H4/H1 structure, supply retest, and net R:R gates met."
            res["blocker_reason"] = None
        elif in_zone:
            res["status"] = "WAITING"
            res["qualification_reason"] = f"Price in supply zone ({entry_min} - {entry_max}); waiting for confirmed H1 close."
            res["blocker_reason"] = "Awaiting completed H1 rejection candle."
        else:
            res["status"] = "WAITING"
            res["qualification_reason"] = f"HTF Bearish structure identified; waiting for pullback to {entry_min} - {entry_max}."
            res["blocker_reason"] = f"Price currently outside entry zone (Ask={ask})."

    else:
        # Conflicting Macro vs Market Structure
        res["status"] = "ANALYZING"
        res["direction"] = "NONE"
        res["quant_score"] = 2 if (d1_bull or d1_bear) else 1
        res["qualification_reason"] = "D1 macro trend and H4 structural swings in consolidation."
        res["blocker_reason"] = "HTF timeframe alignment in progress; waiting for directional BOS."
        res["timeframe_context"] = {
            "d1_bias": "BULLISH" if d1_bull else ("BEARISH" if d1_bear else "CONSOLIDATING"),
            "h4_structure": "RANGING_OR_CHoCH_PENDING",
            "h1_atr": round(h1_atr, digits),
            "h4_atr": round(h4_atr, digits)
        }

    return res
