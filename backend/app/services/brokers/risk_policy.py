"""
BITDEX Dynamic Percentage-Based Risk Policy
===========================================
Single source of truth for per-trade and per-day risk limits.

- Risk per trade is a PERCENTAGE of current broker equity (never a fixed dollar amount).
- The monetary budget is recalculated from live equity before every trade.
- Volume is derived from broker contract specs (tick_value / tick_size), SL distance and
  estimated costs, rounded DOWN to the broker volume step.
- If the broker minimum volume exceeds the budget -> ERR_MIN_LOT_EXCEEDS_BUDGET.
- Daily loss ceiling and consecutive-loss cooldown are derived from BROKER deal history
  (source of truth), so they apply regardless of which process placed the trades.

Defaults can be overridden with environment variables (documented below), but there is no
fixed-dollar risk anywhere in this module.
"""

import math
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class RiskPolicy:
    risk_pct_per_trade: float = 0.25        # % of current equity (BITDEX_RISK_PCT_PER_TRADE)
    daily_loss_limit_pct: float = 1.00      # % of day's starting equity (BITDEX_DAILY_LOSS_LIMIT_PCT)
    min_net_rr: float = 1.5                 # minimum net reward:risk after costs
    preferred_net_rr: float = 2.0           # used when market structure leaves room
    max_consecutive_losses: int = 3
    cooldown_minutes: int = 60
    max_open_positions: int = 1
    est_slippage_pts_per_side: float = 0.15  # XAUUSD price units per fill (conservative estimate)
    max_sl_atr_multiple: float = 3.0        # wider structural stops are rejected, never tightened

    @classmethod
    def load(cls) -> "RiskPolicy":
        return cls(
            risk_pct_per_trade=_env_float("BITDEX_RISK_PCT_PER_TRADE", 0.25),
            daily_loss_limit_pct=_env_float("BITDEX_DAILY_LOSS_LIMIT_PCT", 1.00),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def value_per_price_unit_per_lot(spec: Dict[str, Any]) -> float:
    """USD P&L for a 1.0 price move on 1.0 lot, from broker tick_value / tick_size."""
    tick_size = float(spec.get("tick_size") or 0.0)
    tick_value = float(spec.get("tick_value") or 0.0)
    if tick_size > 0 and tick_value > 0:
        return tick_value / tick_size
    return float(spec.get("contract_size") or 0.0)


def compute_position_size(
    equity: float,
    risk_pct: float,
    sl_distance: float,
    spread: float,
    slippage_per_side: float,
    spec: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Planned loss per lot = (SL distance + spread buffer + entry & exit slippage) * value/unit/lot
                           + round-trip commission per lot.
    The spread buffer is conservative: with entry at ask and SL triggered on bid the spread is
    already inside |entry - SL|; we add it again as a safety margin.
    """
    vpu = value_per_price_unit_per_lot(spec)
    min_vol = float(spec.get("min_volume") or 0.01)
    max_vol = float(spec.get("max_volume") or 100.0)
    step = float(spec.get("volume_step") or 0.01)
    commission_per_lot_rt = 2.0 * float(spec.get("commission_per_lot") or 0.0)

    budget = round(equity * risk_pct / 100.0, 2)
    loss_pts = sl_distance + spread + 2.0 * slippage_per_side
    loss_per_lot = loss_pts * vpu + commission_per_lot_rt

    result = {
        "equity_usd": round(equity, 2),
        "risk_pct": risk_pct,
        "risk_budget_usd": budget,
        "value_per_price_unit_per_lot": vpu,
        "sl_distance": round(sl_distance, 3),
        "spread": round(spread, 3),
        "slippage_per_side": slippage_per_side,
        "loss_pts_incl_costs": round(loss_pts, 3),
        "loss_per_lot_usd": round(loss_per_lot, 2),
        "min_volume": min_vol,
        "volume_step": step,
        "commission_round_trip_per_lot": commission_per_lot_rt,
    }

    if vpu <= 0 or loss_per_lot <= 0 or equity <= 0:
        result.update(feasible=False, error_code="ERR_INVALID_SPECIFICATION", volume=0.0, planned_loss_usd=0.0)
        return result

    min_lot_loss = loss_per_lot * min_vol
    result["min_lot_loss_usd"] = round(min_lot_loss, 2)
    if min_lot_loss > budget:
        result.update(feasible=False, error_code="ERR_MIN_LOT_EXCEEDS_BUDGET", volume=0.0, planned_loss_usd=0.0)
        return result

    decimals = max(0, -int(math.floor(math.log10(step)))) if step < 1 else 0
    raw = budget / loss_per_lot
    vol = math.floor(raw / step + 1e-9) * step
    vol = round(min(max_vol, vol), decimals)
    planned = round(loss_per_lot * vol, 2)
    result.update(
        feasible=True,
        error_code=None,
        raw_volume=round(raw, 5),
        volume=vol,
        planned_loss_usd=planned,
        planned_loss_pct_of_equity=round(planned / equity * 100.0, 4),
    )
    return result


def tp_distance_for_net_rr(target_rr: float, loss_pts: float, slippage_per_side: float,
                           commission_rt_per_lot: float, vpu: float) -> float:
    """TP distance (from entry fill side) such that net reward / planned loss == target_rr."""
    comm_pts = (commission_rt_per_lot / vpu) if vpu > 0 else 0.0
    return target_rr * loss_pts + slippage_per_side + comm_pts


def net_rr(tp_distance: float, loss_pts: float, slippage_per_side: float,
           commission_rt_per_lot: float, vpu: float) -> float:
    comm_pts = (commission_rt_per_lot / vpu) if vpu > 0 else 0.0
    net_reward = tp_distance - slippage_per_side - comm_pts
    return round(net_reward / loss_pts, 3) if loss_pts > 0 else 0.0


# ─── Broker-derived account statistics (source of truth) ────────────────────────────────

def _deal_amount(v: Any) -> float:
    if isinstance(v, dict):
        v = v.get("amount", 0.0)
    try:
        return float(v or 0.0)
    except (TypeError, ValueError):
        return 0.0


def extract_deals(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Exness returns [{'event_time':..., 'deal': {...}}]; normalise and sort chronologically."""
    deals = []
    for h in history or []:
        d = h.get("deal", h) if isinstance(h, dict) else None
        if isinstance(d, dict):
            deals.append(d)
    deals.sort(key=lambda d: str(d.get("create_time") or ""))
    return deals


def broker_account_stats(history: List[Dict[str, Any]], current_balance: float,
                         policy: RiskPolicy, now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    deals = extract_deals(history)
    closes = [d for d in deals if str(d.get("type", "")).lower() == "close"]

    def pnl(d):
        return _deal_amount(d.get("profit")) + _deal_amount(d.get("swap")) - abs(_deal_amount(d.get("commission")))

    today_closes = [d for d in closes if str(d.get("create_time", "")).startswith(today)]
    today_realized = round(sum(pnl(d) for d in today_closes), 2)
    # Day-start balance = current balance minus today's realized trading P&L (deposits excluded).
    day_start_balance = round(current_balance - today_realized, 2)
    daily_limit_usd = round(day_start_balance * policy.daily_loss_limit_pct / 100.0, 2)

    streak = 0
    last_loss_time = None
    for d in reversed(closes):
        if pnl(d) < 0:
            streak += 1
            if last_loss_time is None:
                last_loss_time = str(d.get("create_time"))
        else:
            break

    cooldown_active = False
    cooldown_until = None
    if streak >= policy.max_consecutive_losses and last_loss_time:
        try:
            t = datetime.fromisoformat(last_loss_time.replace("Z", "+00:00"))
            until = t + timedelta(minutes=policy.cooldown_minutes)
            if now < until:
                cooldown_active = True
                cooldown_until = until.strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            cooldown_active = True  # fail closed on unparseable broker timestamp

    return {
        "today_utc": today,
        "today_closed_trades": len(today_closes),
        "today_realized_pnl_usd": today_realized,
        "day_start_balance_usd": day_start_balance,
        "daily_loss_limit_usd": daily_limit_usd,
        "daily_limit_reached": today_realized <= -daily_limit_usd,
        "trailing_consecutive_losses": streak,
        "last_loss_time": last_loss_time,
        "cooldown_active": cooldown_active,
        "cooldown_until": cooldown_until,
    }
