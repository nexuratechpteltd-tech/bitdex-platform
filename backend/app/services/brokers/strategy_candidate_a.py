"""
BITDEX Candidate A: Hierarchical Multi-Timeframe Trend Pullback Strategy (v2)
============================================================================
Strict non-compensatory gates. Any failed gate -> NO_TRADE. No additive scoring.

1. H1 trend  : EMA21 vs EMA50 + EMA21 slope over 3 closed bars + separation >= 0.2 x H1 ATR.
2. M15 struct: last closed M15 close above (BUY) / below (SELL) M15 EMA50.
3. M5 entry  : EMA9/EMA21 aligned with H1; pullback into EMA9-EMA21 value zone in the last
               3 closed bars; last CLOSED bar is a rejection candle closing back beyond EMA21;
               entry not more than 1.0 x ATR beyond the zone.
4. Stops     : SL = max(1.5 x M5 ATR, swing distance + 0.3 x ATR). Rejected (never tightened)
               if SL > 3 x ATR.
5. Target    : net 2.0R if no opposing M15 swing level lies inside it, otherwise net 1.5R floor.
6. Sizing    : percentage-of-equity budget via risk_policy.compute_position_size.

Only CLOSED candles are used: a candle is closed when open_time + timeframe <= now.
"""

from typing import Any, Dict, List, Optional
import time as _time

from .risk_policy import (
    RiskPolicy, compute_position_size, tp_distance_for_net_rr, net_rr, value_per_price_unit_per_lot,
)

MIN_CLOSED_H1 = 60
MIN_CLOSED_M15 = 60
MIN_CLOSED_M5 = 30


def ema_series(values: List[float], period: int) -> List[float]:
    if not values:
        return []
    k = 2.0 / (period + 1.0)
    seed_n = min(period, len(values))
    ema = sum(values[:seed_n]) / seed_n
    out = [ema] * seed_n
    for v in values[seed_n:]:
        ema = v * k + ema * (1.0 - k)
        out.append(ema)
    return out


def calc_ema(values: List[float], period: int) -> float:
    s = ema_series(values, period)
    return s[-1] if s else 0.0


def calc_atr(candles: List[Dict[str, Any]], period: int = 14) -> float:
    trs = []
    for i in range(1, len(candles)):
        h, l = float(candles[i]["high"]), float(candles[i]["low"])
        pc = float(candles[i - 1]["close"])
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if not trs:
        return 0.0
    window = trs[-period:]
    return sum(window) / len(window)


def _infer_tf_seconds(candles: List[Dict[str, Any]]) -> Optional[int]:
    times = [int(c["time"]) for c in candles if isinstance(c.get("time"), (int, float))]
    if len(times) < 3:
        return None
    diffs = sorted(b - a for a, b in zip(times, times[1:]) if b > a)
    return diffs[len(diffs) // 2] if diffs else None


def get_closed_candles(candles: List[Dict[str, Any]], now_ts: Optional[float] = None) -> List[Dict[str, Any]]:
    """Explicit is_closed flags win; otherwise closed iff open_time + timeframe <= now."""
    if not candles:
        return []
    if any("is_closed" in c or "closed" in c for c in candles):
        return [c for c in candles if c.get("is_closed", c.get("closed", True)) is not False]
    tf = _infer_tf_seconds(candles)
    if tf is None:
        return candles[:-1]
    now_ts = _time.time() if now_ts is None else now_ts
    return [c for c in candles if int(c["time"]) + tf <= now_ts]


def _no_trade(code: str, detail: str, passed: List[str], failed: str, telemetry: Optional[Dict] = None,
              direction: str = "NONE", extra: Optional[Dict] = None) -> Dict[str, Any]:
    r = {"outcome": "NO_TRADE", "direction": direction, "error_code": code, "detail": detail,
         "passed_gates": list(passed), "failed_gate": failed, "telemetry": telemetry or {}}
    if extra:
        r.update(extra)
    return r


class CandidateAStrategy:
    STRATEGY_CODE = "CANDIDATE_A_HTF_PULLBACK_v2"

    @classmethod
    def evaluate(
        cls,
        h1_candles: List[Dict[str, Any]],
        m15_candles: List[Dict[str, Any]],
        m5_candles: List[Dict[str, Any]],
        current_bid: float,
        current_ask: float,
        account_equity: float,
        spec: Optional[Dict[str, Any]] = None,
        policy: Optional[RiskPolicy] = None,
        now_ts: Optional[float] = None,
        approved_risk_budget_usd: Optional[float] = None,  # deprecated; ignored (kept for API compat)
        estimated_slippage_pts: Optional[float] = None,
    ) -> Dict[str, Any]:
        policy = policy or RiskPolicy.load()
        spec = spec or {"contract_size": 100.0, "tick_size": 0.001, "tick_value": 0.1,
                        "min_volume": 0.01, "volume_step": 0.01, "max_volume": 200.0, "digits": 3}
        digits = int(spec.get("digits", 3))
        slip = policy.est_slippage_pts_per_side if estimated_slippage_pts is None else estimated_slippage_pts
        spread = round(current_ask - current_bid, digits)

        h1 = get_closed_candles(h1_candles, now_ts)
        m15 = get_closed_candles(m15_candles, now_ts)
        m5 = get_closed_candles(m5_candles, now_ts)
        if len(h1) < MIN_CLOSED_H1 or len(m15) < MIN_CLOSED_M15 or len(m5) < MIN_CLOSED_M5:
            return _no_trade("INSUFFICIENT_HISTORICAL_DATA",
                             f"Closed candles H1={len(h1)}, M15={len(m15)}, M5={len(m5)} "
                             f"(need {MIN_CLOSED_H1}/{MIN_CLOSED_M15}/{MIN_CLOSED_M5}).", [], "DATA_COMPLETENESS")

        # ── Gate 1: H1 trend ──
        h1c = [float(c["close"]) for c in h1]
        e21 = ema_series(h1c, 21)
        e50 = ema_series(h1c, 50)
        h1_atr = calc_atr(h1, 14)
        sep = e21[-1] - e50[-1]
        slope3 = e21[-1] - e21[-4]
        tel = {"h1_ema21": round(e21[-1], 3), "h1_ema50": round(e50[-1], 3), "h1_ema21_slope_3bar": round(slope3, 3),
               "h1_separation": round(sep, 3), "h1_atr": round(h1_atr, 3), "spread": spread}
        min_sep = 0.2 * h1_atr
        if sep > min_sep and slope3 > 0:
            direction = "BUY"
        elif sep < -min_sep and slope3 < 0:
            direction = "SELL"
        else:
            return _no_trade("H1_TREND_NOT_ESTABLISHED",
                             f"H1 EMA21={e21[-1]:.3f} EMA50={e50[-1]:.3f} sep={sep:+.3f} (need |sep|>{min_sep:.3f}) "
                             f"slope3={slope3:+.3f}: flat or conflicting.", [], "H1_TREND", tel)
        passed = ["H1_TREND"]

        # ── Gate 2: M15 structure ──
        m15c = [float(c["close"]) for c in m15]
        m15_e50 = calc_ema(m15c, 50)
        tel.update(m15_ema50=round(m15_e50, 3), m15_close=m15c[-1])
        if direction == "BUY" and m15c[-1] <= m15_e50:
            return _no_trade("M15_MARKET_STRUCTURE_BEARISH",
                             f"M15 close {m15c[-1]:.3f} <= M15 EMA50 {m15_e50:.3f} for BUY.", passed, "M15_STRUCTURE", tel)
        if direction == "SELL" and m15c[-1] >= m15_e50:
            return _no_trade("M15_MARKET_STRUCTURE_BULLISH",
                             f"M15 close {m15c[-1]:.3f} >= M15 EMA50 {m15_e50:.3f} for SELL.", passed, "M15_STRUCTURE", tel)
        passed.append("M15_STRUCTURE")

        # ── Gate 3: M5 confirmation (mandatory veto) ──
        m5c = [float(c["close"]) for c in m5]
        m5h = [float(c["high"]) for c in m5]
        m5l = [float(c["low"]) for c in m5]
        e9, e21m5 = calc_ema(m5c, 9), calc_ema(m5c, 21)
        atr = calc_atr(m5, 14)
        vz_top, vz_bot = max(e9, e21m5), min(e9, e21m5)
        tel.update(m5_ema9=round(e9, 3), m5_ema21=round(e21m5, 3), m5_atr=round(atr, 3),
                   value_zone=[round(vz_bot, 3), round(vz_top, 3)])
        if atr <= 0:
            return _no_trade("ERR_INVALID_ATR", "M5 ATR is zero.", passed, "M5_ATR", tel)
        if direction == "BUY" and e9 <= e21m5:
            return _no_trade("M5_DOWNTREND_ACTIVE_EMA9_BELOW_EMA21",
                             f"M5 EMA9 {e9:.3f} <= EMA21 {e21m5:.3f}; BUY vetoed.", passed, "M5_EMA_ALIGNMENT", tel)
        if direction == "SELL" and e9 >= e21m5:
            return _no_trade("M5_UPTREND_ACTIVE_EMA9_ABOVE_EMA21",
                             f"M5 EMA9 {e9:.3f} >= EMA21 {e21m5:.3f}; SELL vetoed.", passed, "M5_EMA_ALIGNMENT", tel)
        passed.append("M5_EMA_ALIGNMENT")

        touched = (min(m5l[-3:]) <= vz_top + 0.25 * atr) if direction == "BUY" else (max(m5h[-3:]) >= vz_bot - 0.25 * atr)
        if not touched:
            return _no_trade("M5_NO_VALUE_ZONE_PULLBACK",
                             f"No pullback into value zone [{vz_bot:.3f}, {vz_top:.3f}] in last 3 closed M5 bars.",
                             passed, "M5_VALUE_ZONE_PULLBACK", tel)
        passed.append("M5_VALUE_ZONE_PULLBACK")

        t = m5[-1]
        to, th, tl, tc = (float(t[k]) for k in ("open", "high", "low", "close"))
        rng = max(1e-6, th - tl)
        if direction == "BUY":
            wick = min(to, tc) - tl
            ok = (tc > to or wick >= 0.4 * rng) and tc >= tl + 0.5 * rng and tc > e21m5
        else:
            wick = th - max(to, tc)
            ok = (tc < to or wick >= 0.4 * rng) and tc <= tl + 0.5 * rng and tc < e21m5
        tel["trigger_candle"] = {"time": t.get("time"), "open": to, "high": th, "low": tl, "close": tc}
        if not ok:
            return _no_trade("M5_CANDLE_REJECTION_NOT_CONFIRMED",
                             f"Last closed M5 bar O={to} H={th} L={tl} C={tc} is not a {direction} rejection.",
                             passed, "M5_CANDLE_REJECTION", tel)
        passed.append("M5_CANDLE_REJECTION")

        entry = current_ask if direction == "BUY" else current_bid
        ext = (entry - vz_top) if direction == "BUY" else (vz_bot - entry)
        if ext > 1.0 * atr:
            return _no_trade("M5_ENTRY_EXCESSIVELY_EXTENDED",
                             f"Entry {entry:.3f} is {ext:.3f} beyond value zone (> 1.0 x ATR {atr:.3f}).",
                             passed, "M5_EXTENSION", tel)
        passed.append("M5_EXTENSION")

        # ── Gate 4: structural / ATR stop (never tightened) ──
        lookback = 12
        if direction == "BUY":
            swing = min(m5l[-lookback:])
            swing_dist = entry - swing + 0.3 * atr
        else:
            swing = max(m5h[-lookback:])
            swing_dist = swing - entry + 0.3 * atr
        sl_dist = round(max(1.5 * atr, swing_dist), digits)
        tel.update(swing_level=swing, swing_distance=round(swing_dist, 3), sl_atr_multiple=round(sl_dist / atr, 2))
        if sl_dist > policy.max_sl_atr_multiple * atr:
            return _no_trade("ERR_STRUCTURAL_STOP_TOO_WIDE",
                             f"Structural SL {sl_dist:.3f} = {sl_dist/atr:.2f} x ATR exceeds {policy.max_sl_atr_multiple} x ATR.",
                             passed, "DYNAMIC_STOPS", tel, direction)
        if sl_dist < 10 * max(spread, 0.0):
            return _no_trade("ERR_STOP_TOO_CLOSE_TO_SPREAD", f"SL {sl_dist:.3f} < 10 x spread {spread:.3f}.",
                             passed, "DYNAMIC_STOPS", tel, direction)
        passed.append("DYNAMIC_STOPS")

        # ── Gate 5: percentage-of-equity sizing ──
        sizing = compute_position_size(account_equity, policy.risk_pct_per_trade, sl_dist, spread, slip, spec)
        if not sizing["feasible"]:
            return _no_trade(sizing["error_code"],
                             f"Risk budget ${sizing['risk_budget_usd']:.2f} ({policy.risk_pct_per_trade}% of "
                             f"${account_equity:.2f}) vs min-lot loss ${sizing.get('min_lot_loss_usd', 0):.2f}. "
                             "SL is not tightened to force eligibility.",
                             passed, "RISK_BUDGET_FEASIBILITY", tel, direction, {"risk_sizing": sizing})
        passed.append("RISK_BUDGET_FEASIBILITY")

        # ── Gate 6: target / net R:R ──
        vpu = value_per_price_unit_per_lot(spec)
        comm = sizing["commission_round_trip_per_lot"]
        loss_pts = sizing["loss_pts_incl_costs"]
        tp2 = tp_distance_for_net_rr(policy.preferred_net_rr, loss_pts, slip, comm, vpu)
        tp15 = tp_distance_for_net_rr(policy.min_net_rr, loss_pts, slip, comm, vpu)
        recent = m15[-24:]
        if direction == "BUY":
            opp = max(float(c["high"]) for c in recent)
            blocks_2r = entry < opp < entry + tp2
        else:
            opp = min(float(c["low"]) for c in recent)
            blocks_2r = entry - tp2 < opp < entry
        tp_dist = round(tp15 if blocks_2r else tp2, digits)
        rr = net_rr(tp_dist, loss_pts, slip, comm, vpu)
        if rr + 1e-9 < policy.min_net_rr:
            return _no_trade("ERR_NET_RR_BELOW_MINIMUM", f"Net R:R {rr} < {policy.min_net_rr}.",
                             passed, "NET_REWARD_RISK", tel, direction)
        passed.append("NET_REWARD_RISK")

        if direction == "BUY":
            sl_price, tp_price = round(entry - sl_dist, digits), round(entry + tp_dist, digits)
        else:
            sl_price, tp_price = round(entry + sl_dist, digits), round(entry - tp_dist, digits)
        vol = sizing["volume"]
        exp_net_reward = round((tp_dist - slip) * vpu * vol - comm * vol, 2)

        return {
            "outcome": direction,
            "direction": direction,
            "error_code": None,
            "detail": f"Qualified {cls.STRATEGY_CODE} {direction} setup.",
            "passed_gates": passed,
            "failed_gate": None,
            "telemetry": tel,
            "risk_sizing": sizing,
            "order_parameters": {
                "direction": direction,
                "entry_price": entry,
                "sl_price": sl_price,
                "tp_price": tp_price,
                "stop_loss_price": sl_price,
                "take_profit_price": tp_price,
                "sl_distance_pts": sl_dist,
                "tp_distance_pts": tp_dist,
                "volume": vol,
                "spread_pts": spread,
                "atr_m5": round(atr, 3),
                "sl_atr_ratio": round(sl_dist / atr, 2),
                "target_rr_selected": policy.min_net_rr if blocks_2r else policy.preferred_net_rr,
                "structure_supports_2r": not blocks_2r,
                "opposing_m15_level": opp,
                "expected_net_rr": rr,
                "estimated_costs_usd": round((spread + 2 * slip) * vpu * vol + comm * vol, 2),
                "total_monetary_risk_usd": sizing["planned_loss_usd"],
                "expected_net_reward_usd": exp_net_reward,
                "risk_budget_usd": sizing["risk_budget_usd"],
                "risk_pct": policy.risk_pct_per_trade,
                "trigger_candle_time": t.get("time"),
            },
        }
