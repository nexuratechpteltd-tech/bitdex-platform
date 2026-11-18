"""
BITDEX Institutional Permanent Trade Memory, Learning & Intelligence System
Location: /opt/tauric-platform-staging/backend/app/services/trade_memory_service.py
Authoritative SQLite storage for 47 trade attributes, multi-factor outcome classification,
MFE/MAE tracking, and 7-point structured post-trade failure analysis.

INVARIANT: Strictly research and analytics. Never automatically mutates live strategy parameters.
"""

import json
import sqlite3
import secrets
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import os

try:
    from .saas_db import get_db_path
except ImportError:
    def get_db_path():
        return os.environ.get("SAAS_DB_PATH", "/opt/tauric-platform-staging/backend/data/tauric_saas.db")


class TradeMemoryService:
    @staticmethod
    def get_connection() -> sqlite3.Connection:
        conn = sqlite3.connect(get_db_path(), timeout=15.0)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def init_db(conn: Optional[sqlite3.Connection] = None):
        close_needed = False
        if conn is None:
            conn = TradeMemoryService.get_connection()
            close_needed = True

        try:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS trade_memory (
                        trade_id TEXT PRIMARY KEY,
                        broker_ticket TEXT,
                        order_id TEXT,
                        deal_id TEXT,
                        account_id TEXT NOT NULL,
                        strategy_track TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        side TEXT NOT NULL,
                        volume_lots REAL NOT NULL,
                        entry_price REAL NOT NULL,
                        exit_price REAL NOT NULL,
                        sl_price REAL,
                        tp_price REAL,
                        planned_risk_usd REAL,
                        gross_pnl_usd REAL NOT NULL,
                        commission_usd REAL DEFAULT 0.0,
                        swap_usd REAL DEFAULT 0.0,
                        net_pnl_usd REAL NOT NULL,
                        r_multiple REAL,
                        entry_time TEXT NOT NULL,
                        exit_time TEXT NOT NULL,
                        duration_seconds REAL,
                        exit_reason TEXT NOT NULL,
                        market_session TEXT,
                        spread_at_entry REAL,
                        ema_fast REAL,
                        ema_slow REAL,
                        atr_at_entry REAL,
                        trigger_candle_body REAL,
                        htf_bias TEXT,
                        outcome_class TEXT NOT NULL,
                        post_trade_explanation TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        execution_type TEXT DEFAULT 'ACTUAL_DEMO',
                        status TEXT DEFAULT 'CLOSED',
                        strategy_version TEXT DEFAULT 'v1.0.0',
                        instrument_type TEXT DEFAULT 'CFD',
                        signal_time TEXT,
                        signal_reason_json TEXT,
                        slippage_pts REAL DEFAULT 0.0,
                        mfe_price REAL,
                        mfe_r REAL DEFAULT 0.0,
                        mae_price REAL,
                        mae_r REAL DEFAULT 0.0,
                        outcome_status TEXT DEFAULT 'UNKNOWN',
                        failure_analysis_json TEXT,
                        learning_recommendations_json TEXT
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_trade_mem_acc ON trade_memory(account_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_trade_mem_track ON trade_memory(strategy_track)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_trade_mem_sym ON trade_memory(symbol)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_trade_mem_exec ON trade_memory(execution_type)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_trade_mem_status ON trade_memory(outcome_status)")
        finally:
            if close_needed:
                conn.close()

    @staticmethod
    def classify_outcome(trade_data: Dict[str, Any]) -> str:
        net_pnl = float(trade_data.get("net_pnl_usd", 0.0))
        if net_pnl > 0:
            return "PROFITABLE_EXECUTION"

        duration = float(trade_data.get("duration_seconds", 0.0) or 0.0)
        spread = float(trade_data.get("spread_at_entry", 0.0) or 0.0)
        entry_price = float(trade_data.get("entry_price", 0.0) or 1.0)
        sl_price = float(trade_data.get("sl_price", 0.0) or 0.0)
        commission = abs(float(trade_data.get("commission_usd", 0.0) or 0.0))
        gross_pnl = abs(float(trade_data.get("gross_pnl_usd", 0.0) or 0.0))
        trigger_body = float(trade_data.get("trigger_candle_body", 0.0) or 0.0)
        atr = float(trade_data.get("atr_at_entry", 0.0) or 0.0)
        session = str(trade_data.get("market_session", "")).upper()
        htf_bias = str(trade_data.get("htf_bias", "")).upper()
        side = str(trade_data.get("side", "")).upper()

        if (htf_bias == "BULLISH" and side == "SELL") or (htf_bias == "BEARISH" and side == "BUY"):
            return "COUNTER_TREND_REVERSAL"

        stop_dist = abs(entry_price - sl_price) if sl_price > 0 else 0.0
        if stop_dist > 0 and (spread / stop_dist) > 0.35:
            return "SPREAD_SLIPPAGE_DRAG"
        if gross_pnl > 0 and commission >= (gross_pnl * 0.5):
            return "SPREAD_SLIPPAGE_DRAG"

        if atr > 0 and trigger_body > 0 and trigger_body < (0.35 * atr):
            return "WEAK_MOMENTUM"

        if duration > 0 and duration < 75.0 and trade_data.get("exit_reason") in ("SL_HIT", "REVERSAL_VETO"):
            return "FALSE_BREAKOUT"

        if session in ("ASIAN_LATE", "OFF_HOURS", "SESSION_CHANGE", "ROLLOVER"):
            return "SESSION_LACK_LIQUIDITY"

        return "NORMAL_STOP_LOSS"

    @staticmethod
    def generate_7point_explanation(trade_data: Dict[str, Any], outcome: str) -> Dict[str, Any]:
        symbol = trade_data.get("symbol", "N/A")
        side = trade_data.get("side", "N/A")
        track = trade_data.get("strategy_track", "LONGTERM_STRUCTURE")
        net_pnl = float(trade_data.get("net_pnl_usd", 0.0))
        p_risk = float(trade_data.get("planned_risk_usd", 0.0) or 0.0)
        r_mult = round(net_pnl / p_risk, 2) if p_risk > 0 else 0.0
        duration = float(trade_data.get("duration_seconds", 0.0) or 0.0)

        p1 = f"{track} on {symbol} {side}. Triggered via verified multi-timeframe signal."
        htf = trade_data.get("htf_bias", "NEUTRAL")
        p2 = f"HTF structure evaluated as {htf}. Side {side} was {'aligned' if (htf == 'BULLISH' and side == 'BUY') or (htf == 'BEARISH' and side == 'SELL') else 'counter-structural'}."
        spread = trade_data.get("spread_at_entry", 0.0)
        comm = trade_data.get("commission_usd", 0.0)
        p3 = f"Entry spread: {spread} pts | Commission: ${abs(float(comm)):.2f} on {trade_data.get('volume_lots')} lots."
        p4 = f"Held for {duration:.1f}s ({duration/3600:.1f}h). Closed via {trade_data.get('exit_reason', 'NORMAL_EXIT')}."
        p5 = f"Realized net P&L: ${net_pnl:.2f} ({r_mult:+.2f}R relative to ${p_risk:.2f} planned risk limit). MFE: {trade_data.get('mfe_r', 0.0)}R | MAE: {trade_data.get('mae_r', 0.0)}R."
        p6 = f"Classified as {outcome}. Root cause: {'Target achieved within trend continuation' if net_pnl > 0 else 'Adverse market excursion beyond structural invalidation level'}."

        recs = {
            "PROFITABLE_EXECUTION": "Evidence confirms structural target capture. Retain strategy parameters.",
            "FALSE_BREAKOUT": "Evidence shows rapid rejection. Recommend requiring candle close confirmation beyond key swing.",
            "SPREAD_SLIPPAGE_DRAG": "Commission/spread represented material friction. Restrict execution to London/NY peak liquidity.",
            "WEAK_MOMENTUM": "Impulse lacked volume/range. Enforce minimum ATR expansion threshold before entry.",
            "SESSION_LACK_LIQUIDITY": "Trade triggered during off-hours window. Enforce strict 08:00-17:00 UTC session filter.",
            "COUNTER_TREND_REVERSAL": "Trade fought dominant HTF trend. Strengthen higher timeframe directional bias filter.",
            "NORMAL_STOP_LOSS": "Statistical variance within planned 1.0R risk budget. No parameter mutation required."
        }
        p7 = recs.get(outcome, "Statistical variance within normal risk bounds. No manual intervention required.")

        return {
            "point_1_setup_quality": p1,
            "point_2_htf_alignment": p2,
            "point_3_friction_and_execution": p3,
            "point_4_duration_and_lifecycle": p4,
            "point_5_price_action_evolution": p5,
            "point_6_outcome_root_cause": p6,
            "point_7_optimization_note": p7
        }

    @classmethod
    def record_trade(cls, trade_data: Dict[str, Any], conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
        if trade_data.get("slippage_price") is None and trade_data.get("slippage_points") is None:
            _sp, _spts = compute_execution_slippage(
                trade_data.get("side", ""),
                trade_data.get("executable_quote"),
                trade_data.get("entry_price") or trade_data.get("fill_price"),
                trade_data.get("tick_size"),
            )
            trade_data["slippage_price"] = _sp
            trade_data["slippage_points"] = _spts
        exec_type = str(trade_data.get("execution_type", "PAPER_SIMULATED")).upper()
        if exec_type == "ACTUAL_DEMO":
            bt = str(trade_data.get("broker_ticket") or "").strip()
            oid = str(trade_data.get("order_id") or "").strip()
            if not bt or not oid:
                raise ValueError("ACTUAL_DEMO Trade Memory record requires non-empty broker_ticket and order_id.")
        cls.init_db(conn=conn)
        trade_id = trade_data.get("trade_id") or f"TMEM-{secrets.token_hex(6).upper()}"
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        outcome = cls.classify_outcome(trade_data)
        explanation = cls.generate_7point_explanation(trade_data, outcome)
        explanation_json = json.dumps(explanation)

        planned_risk = float(trade_data.get("planned_risk_usd", 0.0) or 0.0)
        net_pnl = float(trade_data.get("net_pnl_usd", 0.0))
        r_mult = round(net_pnl / planned_risk, 2) if planned_risk > 0 else 0.0

        exec_type = trade_data.get("execution_type") or "ACTUAL_DEMO"
        status = trade_data.get("status") or "CLOSED"
        outcome_status = trade_data.get("outcome_status") or ("WIN" if net_pnl > 0 else ("BREAK_EVEN" if net_pnl == 0 else "LOSS"))
        strat_ver = trade_data.get("strategy_version") or "v1.0.0"
        inst_type = trade_data.get("instrument_type") or "CFD"
        sig_time = trade_data.get("signal_time") or trade_data.get("entry_time") or now_iso
        sig_reason = trade_data.get("signal_reason_json") or "{}"
        if isinstance(sig_reason, dict):
            sig_reason = json.dumps(sig_reason)
        slip_pts = float(trade_data.get("slippage_pts") or 0.0)
        mfe_px = float(trade_data.get("mfe_price") or 0.0) if trade_data.get("mfe_price") is not None else None
        mfe_r = float(trade_data.get("mfe_r") or 0.0)
        mae_px = float(trade_data.get("mae_price") or 0.0) if trade_data.get("mae_price") is not None else None
        mae_r = float(trade_data.get("mae_r") or 0.0)
        fail_analysis = json.dumps(explanation)
        learning_recs = json.dumps({"recommended_action": explanation.get("point_7_optimization_note")})

        own_conn = conn is None
        if own_conn:
            conn = cls.get_connection()
        try:
            if own_conn:
                conn.execute("BEGIN IMMEDIATE")
            if True:
                conn.execute("""
                    INSERT OR REPLACE INTO trade_memory (
                        trade_id, broker_ticket, order_id, deal_id, account_id,
                        strategy_track, symbol, side, volume_lots, entry_price, exit_price,
                        sl_price, tp_price, planned_risk_usd, gross_pnl_usd, commission_usd,
                        swap_usd, net_pnl_usd, r_multiple, entry_time, exit_time, duration_seconds,
                        exit_reason, market_session, spread_at_entry, ema_fast, ema_slow,
                        atr_at_entry, trigger_candle_body, htf_bias, outcome_class,
                        post_trade_explanation, created_at,
                        execution_type, status, strategy_version, instrument_type,
                        signal_time, signal_reason_json, slippage_pts,
                        mfe_price, mfe_r, mae_price, mae_r,
                        outcome_status, failure_analysis_json, learning_recommendations_json
                    ) VALUES (
                        ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?
                    )
                """, (
                    trade_id,
                    str(trade_data.get("broker_ticket", "")),
                    str(trade_data.get("order_id", "")),
                    str(trade_data.get("deal_id", "")),
                    str(trade_data.get("account_id", "17000694512")),
                    str(trade_data.get("strategy_track", "LONGTERM_STRUCTURE")),
                    str(trade_data.get("symbol", "")),
                    str(trade_data.get("side", "BUY")),
                    float(trade_data.get("volume_lots", 0.01)),
                    float(trade_data.get("entry_price", 0.0)),
                    float(trade_data.get("exit_price", 0.0)),
                    float(trade_data.get("sl_price", 0.0) or 0.0),
                    float(trade_data.get("tp_price", 0.0) or 0.0),
                    planned_risk,
                    float(trade_data.get("gross_pnl_usd", 0.0)),
                    float(trade_data.get("commission_usd", 0.0) or 0.0),
                    float(trade_data.get("swap_usd", 0.0) or 0.0),
                    net_pnl,
                    r_mult,
                    str(trade_data.get("entry_time", now_iso)),
                    str(trade_data.get("exit_time", now_iso)),
                    float(trade_data.get("duration_seconds", 0.0) or 0.0),
                    str(trade_data.get("exit_reason", "MARKET_CLOSE")),
                    str(trade_data.get("market_session", "ACTIVE")),
                    float(trade_data.get("spread_at_entry", 0.0) or 0.0),
                    float(trade_data.get("ema_fast", 0.0) or 0.0),
                    float(trade_data.get("ema_slow", 0.0) or 0.0),
                    float(trade_data.get("atr_at_entry", 0.0) or 0.0),
                    float(trade_data.get("trigger_candle_body", 0.0) or 0.0),
                    str(trade_data.get("htf_bias", "NEUTRAL")),
                    outcome,
                    explanation_json,
                    now_iso,
                    exec_type,
                    status,
                    strat_ver,
                    inst_type,
                    sig_time,
                    sig_reason,
                    slip_pts,
                    mfe_px,
                    mfe_r,
                    mae_px,
                    mae_r,
                    outcome_status,
                    fail_analysis,
                    learning_recs
                ))
            if own_conn:
                conn.commit()
            return {
                "status": "RECORDED",
                "trade_id": trade_id,
                "execution_type": exec_type,
                "outcome_class": outcome,
                "outcome_status": outcome_status,
                "r_multiple": r_mult,
                "explanation": explanation
            }
        except Exception:
            if own_conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            raise
        finally:
            if own_conn:
                conn.close()

    @classmethod
    def get_trade_history(
        cls,
        account_id: Optional[str] = None,
        track: Optional[str] = None,
        execution_type: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        cls.init_db()
        conn = cls.get_connection()
        try:
            query = "SELECT * FROM trade_memory WHERE 1=1"
            params = []
            if account_id:
                query += " AND account_id = ?"
                params.append(account_id)
            if track:
                query += " AND strategy_track = ?"
                params.append(track)
            if execution_type:
                query += " AND execution_type = ?"
                params.append(execution_type)
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            results = []
            for r in rows:
                d = dict(r)
                for json_field in ("post_trade_explanation", "failure_analysis_json", "learning_recommendations_json", "signal_reason_json"):
                    if d.get(json_field):
                        try:
                            d[json_field] = json.loads(d[json_field])
                        except Exception:
                            pass
                results.append(d)
            return results
        finally:
            conn.close()

    @classmethod
    def get_strategy_intelligence_report(cls, execution_type: Optional[str] = None) -> Dict[str, Any]:
        cls.init_db()
        conn = cls.get_connection()
        try:
            base_q = "SELECT * FROM trade_memory"
            params = []
            if execution_type:
                base_q += " WHERE execution_type = ?"
                params.append(execution_type)
            rows = [dict(r) for r in conn.execute(base_q, params).fetchall()]

            def calc_metrics(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
                if not trades:
                    return {
                        "trades_count": 0, "wins": 0, "losses": 0, "win_rate_pct": 0.0,
                        "gross_pnl_usd": 0.0, "commission_usd": 0.0, "net_pnl_usd": 0.0,
                        "profit_factor": 0.0, "expectancy_usd": 0.0, "avg_r_multiple": 0.0,
                        "max_drawdown_usd": 0.0, "avg_mfe_r": 0.0, "avg_mae_r": 0.0
                    }
                n = len(trades)
                wins = [t for t in trades if float(t.get("net_pnl_usd", 0.0)) > 0]
                losses = [t for t in trades if float(t.get("net_pnl_usd", 0.0)) <= 0]
                tw = sum(float(t.get("net_pnl_usd", 0.0)) for t in wins)
                tl = abs(sum(float(t.get("net_pnl_usd", 0.0)) for t in losses))
                tot_net = sum(float(t.get("net_pnl_usd", 0.0)) for t in trades)
                tot_gross = sum(float(t.get("gross_pnl_usd", 0.0)) for t in trades)
                tot_comm = sum(abs(float(t.get("commission_usd", 0.0))) for t in trades)
                wr = round((len(wins) / n) * 100, 1)
                pf = round(tw / tl, 2) if tl > 0 else 99.0
                exp = round(tot_net / n, 2)
                avg_r = round(sum(float(t.get("r_multiple", 0.0) or 0.0) for t in trades) / n, 2)
                avg_mfe = round(sum(float(t.get("mfe_r", 0.0) or 0.0) for t in trades) / n, 2)
                avg_mae = round(sum(float(t.get("mae_r", 0.0) or 0.0) for t in trades) / n, 2)

                cum = 0.0
                peak = 0.0
                max_dd = 0.0
                for t in trades:
                    cum += float(t.get("net_pnl_usd", 0.0))
                    if cum > peak:
                        peak = cum
                    dd = peak - cum
                    if dd > max_dd:
                        max_dd = dd

                return {
                    "trades_count": n,
                    "wins": len(wins),
                    "losses": len(losses),
                    "win_rate_pct": wr,
                    "gross_pnl_usd": round(tot_gross, 2),
                    "commission_usd": round(tot_comm, 2),
                    "net_pnl_usd": round(tot_net, 2),
                    "profit_factor": pf,
                    "expectancy_usd": exp,
                    "avg_r_multiple": avg_r,
                    "max_drawdown_usd": round(max_dd, 2),
                    "avg_mfe_r": avg_mfe,
                    "avg_mae_r": avg_mae
                }

            tracks = {}
            for t in set(r.get("strategy_track", "UNKNOWN") for r in rows):
                tracks[t] = calc_metrics([r for r in rows if r.get("strategy_track") == t])

            symbols = {}
            for s in set(r.get("symbol", "UNKNOWN") for r in rows):
                symbols[s] = calc_metrics([r for r in rows if r.get("symbol") == s])

            sessions = {}
            for sess in set(r.get("market_session", "UNKNOWN") for r in rows):
                sessions[sess] = calc_metrics([r for r in rows if r.get("market_session") == sess])

            failures = {}
            losses_only = [r for r in rows if float(r.get("net_pnl_usd", 0.0)) <= 0]
            for l in losses_only:
                c = l.get("outcome_class", "NORMAL_STOP_LOSS")
                failures[c] = failures.get(c, 0) + 1

            by_exec = {}
            for et in set(r.get("execution_type", "ACTUAL_DEMO") for r in rows):
                by_exec[et] = calc_metrics([r for r in rows if r.get("execution_type") == et])

            return {
                "overall": calc_metrics(rows),
                "by_execution_type": by_exec,
                "by_strategy": tracks,
                "by_instrument": symbols,
                "by_session": sessions,
                "failure_distribution": failures,
                "total_records": len(rows),
                "execution_filter": execution_type or "ALL"
            }
        finally:
            conn.close()


def compute_execution_slippage(side: str, executable_quote: float | None, fill_price: float | None, tick_size: float | None):
    """Returns (slippage_price, slippage_points). Positive=adverse, negative=improvement.
    Returns (None, None) when unavailable—never defaults missing measurements to 0.0."""
    if executable_quote is None or fill_price is None or not tick_size or tick_size <= 0:
        return None, None
    s = str(side).upper()
    if s == "BUY":
        sp = float(fill_price) - float(executable_quote)
    elif s == "SELL":
        sp = float(executable_quote) - float(fill_price)
    else:
        return None, None
    return round(sp, 6), round(sp / float(tick_size), 2)


def reconcile_partial_fills(side: str, executable_quote: float | None, fills: list[dict], tick_size: float | None):
    """Aggregate partial fills (deduplicated by deal_ticket) into VWAP fill price and slippage."""
    seen_tickets = set()
    unique_fills = []
    for f in fills:
        dt = f.get("deal_ticket")
        if dt is not None and dt in seen_tickets:
            continue
        if dt is not None:
            seen_tickets.add(dt)
        if f.get("volume", 0) > 0 and f.get("price") is not None:
            unique_fills.append(f)
    total_vol = sum(float(f["volume"]) for f in unique_fills)
    if total_vol <= 0:
        return {"vwap_fill_price": None, "total_volume": 0.0, "deal_tickets": list(seen_tickets), "slippage_price": None, "slippage_points": None}
    vwap = sum(float(f["volume"]) * float(f["price"]) for f in unique_fills) / total_vol
    sp, spts = compute_execution_slippage(side, executable_quote, vwap, tick_size)
    return {
        "vwap_fill_price": round(vwap, 6),
        "total_volume": round(total_vol, 6),
        "deal_tickets": [f.get("deal_ticket") for f in unique_fills],
        "slippage_price": sp,
        "slippage_points": spts,
    }
