"""
BITDEX Central Strategy Registry Service (Command 8 — Staging Only)
Enforces lifecycle: RESEARCH -> VALIDATED -> APPROVED -> ENABLED
Enforces Permanent Broker DEMO Policy: NO SIMULATED PAPER TRADING; REAL TRADING — LOCKED.
"""
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import os, sqlite3
import pandas as pd

STRATEGIES: Dict[str, Dict[str, Any]] = {
    "LT_STRUCTURE_EURUSD_A": {
        "strategy_number": "STR-001",
        "strategy_id": "LT_STRUCTURE_EURUSD_A",
        "name": "EURUSD Multi-Timeframe Structure (Long-Only)",
        "version": "1.0",
        "market_type": "FOREX",
        "strategy_style": "LONG_TERM",
        "supported_instruments": ["EURUSD"],
        "supported_brokers": ["Exness DEMO (17000694512, dx.2.trial.raw)"],
        "direction_support": ["BUY"],
        "lifecycle_status": "RESEARCH",
        "validation_status": "INCOMPLETE_SAMPLE_SIZE",
        "approval_status": "NOT_APPROVED",
        "execution_eligible": False,
        "execution_policy_label": "HISTORICAL BACKTEST ONLY — BROKER DEMO EXECUTION REQUIRES EXPLICIT APPROVAL (REAL TRADING — LOCKED)",
        "risk_profile": {
            "max_risk_per_trade_pct": 0.5,
            "max_risk_per_trade_usd": 10.0,
            "max_open_positions": 1,
            "max_stop_pips": 45.0,
            "target_rr": 2.0,
            "post_sl_cooldown_bars": 24,
        },
        "historical_backtest": {
            "label": "HISTORICAL BACKTEST (Exness Bid/Ask H1 2023-2026)",
            "oos_3_folds": {"trades": 9, "wins": 3, "losses": 6, "win_rate_pct": 33.33, "profit_factor": 0.95, "net_pnl_usd": -2.28, "expectancy_r": -0.032, "max_dd_usd": 17.61},
            "holdout_6m": {"trades": 4, "wins": 2, "losses": 2, "win_rate_pct": 50.0, "profit_factor": 1.98, "net_pnl_usd": 17.49, "expectancy_r": 0.429, "max_dd_usd": 17.79},
            "long_short_split": {"long_trades": 13, "short_trades": 0, "long_net_usd": 15.21, "short_net_usd": 0.0},
            "bootstrap_95_ci_r": [-0.579, 0.803],
        },
    },
    "LT_STRUCTURE_EURUSD_A2": {
        "strategy_number": "STR-002",
        "strategy_id": "LT_STRUCTURE_EURUSD_A2",
        "name": "EURUSD Symmetrical Structure A2 (Long & Short)",
        "version": "2.0",
        "market_type": "FOREX",
        "strategy_style": "LONG_TERM",
        "supported_instruments": ["EURUSD"],
        "supported_brokers": ["Exness DEMO (17000694512, dx.2.trial.raw)"],
        "direction_support": ["BUY", "SELL"],
        "lifecycle_status": "RESEARCH — BROKER DEMO APPROVAL PENDING",
        "validation_status": "INCONCLUSIVE_STATISTICAL_CONFIDENCE",
        "approval_status": "NOT_APPROVED",
        "execution_eligible": False,
        "execution_policy_label": "HISTORICAL BACKTEST ONLY — BROKER DEMO EXECUTION REQUIRES EXPLICIT APPROVAL (REAL TRADING — LOCKED)",
        "risk_profile": {
            "max_risk_per_trade_pct": 0.5,
            "max_risk_per_trade_usd": 10.0,
            "max_open_positions": 1,
            "max_stop_pips": 45.0,
            "target_rr": 2.0,
            "post_sl_cooldown_bars": 24,
        },
        "historical_backtest": {
            "label": "HISTORICAL BACKTEST (Exness Bid/Ask H1 2023-2026, ER20>=0.20)",
            "oos_3_folds": {"trades": 31, "wins": 12, "losses": 19, "win_rate_pct": 38.71, "profit_factor": 1.16, "net_pnl_usd": 26.82, "expectancy_r": 0.123, "max_dd_usd": 73.73},
            "holdout_6m": {"trades": 5, "wins": 2, "losses": 3, "win_rate_pct": 40.0, "profit_factor": 1.42, "net_pnl_usd": 10.83, "expectancy_r": 0.156, "max_dd_usd": 16.63},
            "long_short_split": {"long_trades": 12, "short_trades": 24, "long_net_usd": 14.10, "short_net_usd": 23.55},
            "bootstrap_95_ci_r": [-0.286, 0.623],
        },
    },
    "LT_STRUCTURE_EURUSD_B": {
        "strategy_number": "STR-003",
        "strategy_id": "LT_STRUCTURE_EURUSD_B",
        "name": "EURUSD H4/H1 EMA20 + ADX Momentum B",
        "version": "1.0",
        "market_type": "FOREX",
        "strategy_style": "MOMENTUM",
        "supported_instruments": ["EURUSD"],
        "supported_brokers": ["Exness DEMO (17000694512, dx.2.trial.raw)"],
        "direction_support": ["BUY", "SELL"],
        "lifecycle_status": "RETIRED_RESEARCH",
        "validation_status": "FAILED_OOS_EXPECTANCY",
        "approval_status": "RETIRED",
        "execution_eligible": False,
        "execution_policy_label": "RETIRED_RESEARCH — EXECUTION DISABLED",
        "risk_profile": {
            "max_risk_per_trade_pct": 0.5,
            "max_risk_per_trade_usd": 10.0,
            "max_open_positions": 1,
            "max_stop_pips": 60.0,
            "target_rr": 2.0,
            "post_sl_cooldown_bars": 12,
        },
        "historical_backtest": {
            "label": "HISTORICAL BACKTEST (Exness Bid/Ask H1 2023-2026)",
            "oos_3_folds": {"trades": 331, "wins": 114, "losses": 217, "win_rate_pct": 34.44, "profit_factor": 0.96, "net_pnl_usd": -80.56, "expectancy_r": -0.025, "max_dd_usd": 292.42},
            "holdout_6m": {"trades": 126, "wins": 42, "losses": 84, "win_rate_pct": 33.33, "profit_factor": 0.89, "net_pnl_usd": -88.35, "expectancy_r": -0.083, "max_dd_usd": 277.37},
            "long_short_split": {"long_trades": 227, "short_trades": 230, "long_net_usd": -11.07, "short_net_usd": -157.84},
            "bootstrap_95_ci_r": [-0.168, 0.094],
        },
    },
    "EURUSD_DONCHIAN_BENCHMARK": {
        "strategy_number": "STR-004",
        "strategy_id": "EURUSD_DONCHIAN_BENCHMARK",
        "name": "EURUSD 20-Bar Donchian Breakout Benchmark",
        "version": "1.0",
        "market_type": "FOREX",
        "strategy_style": "LONG_TERM",
        "supported_instruments": ["EURUSD"],
        "supported_brokers": ["Exness DEMO (17000694512, dx.2.trial.raw)"],
        "direction_support": ["BUY", "SELL"],
        "lifecycle_status": "RETIRED_RESEARCH",
        "validation_status": "FAILED_BENCHMARK",
        "approval_status": "RETIRED",
        "execution_eligible": False,
        "execution_policy_label": "RETIRED_RESEARCH — BENCHMARK ONLY, EXECUTION DISABLED",
        "risk_profile": {
            "max_risk_per_trade_pct": 0.5,
            "max_risk_per_trade_usd": 10.0,
            "max_open_positions": 1,
            "max_stop_pips": 60.0,
            "target_rr": 1.67,
            "post_sl_cooldown_bars": 4,
        },
        "historical_backtest": {
            "label": "HISTORICAL BACKTEST (Exness Bid/Ask H1 2023-2026)",
            "oos_3_folds": {"trades": 442, "wins": 166, "losses": 276, "win_rate_pct": 37.56, "profit_factor": 0.88, "net_pnl_usd": -321.15, "expectancy_r": -0.084, "max_dd_usd": 427.49},
            "holdout_6m": {"trades": 152, "wins": 48, "losses": 104, "win_rate_pct": 31.58, "profit_factor": 0.67, "net_pnl_usd": -337.89, "expectancy_r": -0.248, "max_dd_usd": 405.99},
            "long_short_split": {"long_trades": 298, "short_trades": 296, "long_net_usd": -310.12, "short_net_usd": -348.92},
            "bootstrap_95_ci_r": [-0.195, -0.042],
        },
    },
}

def list_strategies_for_customer(user_id: str) -> List[Dict[str, Any]]:
    out = []
    for k, v in STRATEGIES.items():
        ms = evaluate_market_suitability(k)
        out.append({**v, "market_suitability": ms, "customer_user_id": user_id})
    return out

def get_strategy_for_customer(strategy_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    st = STRATEGIES.get(strategy_id)
    if not st:
        return None
    return {**st, "market_suitability": evaluate_market_suitability(strategy_id), "customer_user_id": user_id}

def evaluate_market_suitability(strategy_id: str) -> Dict[str, Any]:
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    st = STRATEGIES.get(strategy_id)
    if not st:
        return {"status": "NO_TRADE", "reason": "UNKNOWN_STRATEGY", "evaluated_at_utc": now_iso}
    if st["lifecycle_status"] == "RETIRED_RESEARCH":
        return {"status": "DISABLED", "reason": "Strategy is marked RETIRED_RESEARCH and permanently disabled for execution.", "evaluated_at_utc": now_iso}
    h1_path = "/opt/bitdex-research-v2/data/cleaned/EURUSD_H1_exness_clean.csv"
    if not os.path.exists(h1_path):
        return {"status": "INSUFFICIENT_DATA", "reason": "Cleaned EURUSD H1 dataset not found.", "evaluated_at_utc": now_iso}
    try:
        df = pd.read_csv(h1_path).tail(50)
        last_ts = pd.to_datetime(df["time"].iloc[-1], utc=True)
        age_hours = (datetime.now(timezone.utc) - last_ts).total_seconds() / 3600.0
        last_spread_pips = round(float(df["spread_close"].iloc[-1]) * 10000.0, 2)
        if age_hours > 4.0:
            return {
                "status": "INSUFFICIENT_DATA",
                "reason": f"Latest verified dataset candle is {round(age_hours, 1)}h old; live execution disabled pending explicit BROKER DEMO approval.",
                "last_candle_utc": str(df["time"].iloc[-1]),
                "spread_pips": last_spread_pips,
                "execution_action": "NO_TRADE",
                "evaluated_at_utc": now_iso,
            }
        return {
            "status": "WAITING_FOR_CONFIRMATION",
            "reason": "Strategy is in RESEARCH status (not yet APPROVED for BROKER DEMO execution). Waiting for H4/H1 structural pullback confirmation.",
            "last_candle_utc": str(df["time"].iloc[-1]),
            "spread_pips": last_spread_pips,
            "execution_action": "NO_TRADE",
            "evaluated_at_utc": now_iso,
        }
    except Exception as e:
        return {"status": "INSUFFICIENT_DATA", "reason": f"Market data evaluation error: {e}", "evaluated_at_utc": now_iso}

def get_customer_strategy_activity(conn: sqlite3.Connection, user_id: str, strategy_id: str) -> Dict[str, Any]:
    """Strictly customer-scoped activity lookup (enforces tenant isolation)."""
    st = STRATEGIES.get(strategy_id)
    if not st:
        return {"strategy_id": strategy_id, "records": []}
    # Query only connections owned by this exact customer user_id
    acct_rows = conn.execute(
        "SELECT account_id FROM user_exchange_connections WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    acct_ids = [str(r[0]) for r in acct_rows if r[0]]
    records = []
    if acct_ids:
        placeholders = ",".join("?" for _ in acct_ids)
        q = f"SELECT trade_id, broker_ticket, symbol, side, volume_lots, entry_price, exit_price, net_pnl_usd, entry_time, exit_time, execution_type FROM trade_memory WHERE account_id IN ({placeholders}) AND execution_type = \x27ACTUAL_DEMO\x27 ORDER BY entry_time DESC LIMIT 25"
        for r in conn.execute(q, tuple(acct_ids)).fetchall():
            records.append(dict(r))
    return {
        "strategy_id": strategy_id,
        "customer_user_id": user_id,
        "execution_eligible": False,
        "policy": "BROKER DEMO EXECUTION ONLY WHEN EXPLICITLY APPROVED — NO SIMULATED PAPER TRADING",
        "broker_demo_records": records,
    }
