"""
BITDEX Demo Forward-Test Audit & Execution Tracker (Phase 5)
=============================================================
Provides structured persistence, query, and analysis for all forward-testing activities:
- Strategy evaluations and directional decisions
- 10-gate qualification results and scoring
- Risk rejections and clamp enforcement
- Customer-approved executions
- Broker operation IDs and asynchronous state transitions
- Fill prices, execution prices, spread, slippage
- SL/TP attachments and modifications
- Position closures (partial and full)
- Realized and floating P&L tracking
- API & reconciliation latency telemetry
- WebSocket and connection lifecycle events

Enforces multi-tenant isolation: every record is strictly scoped by user_id and account_id.
"""

import json
import sqlite3
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def ensure_forward_test_tables(conn: sqlite3.Connection) -> None:
    """Ensures the demo forward test audit table and indexes exist."""
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS demo_forward_test_records (
                record_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                account_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                event_type TEXT NOT NULL,
                direction TEXT,
                score REAL,
                entry_qualified INTEGER DEFAULT 0,
                rejection_reason TEXT,
                operation_id TEXT,
                position_id TEXT,
                execution_price REAL,
                sl_price REAL,
                tp_price REAL,
                spread REAL,
                slippage REAL,
                realized_pnl REAL,
                floating_pnl REAL,
                latency_ms REAL,
                details_json TEXT,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_forward_test_user_acct ON demo_forward_test_records(user_id, account_id, created_at);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_forward_test_event_type ON demo_forward_test_records(event_type);")


class DemoForwardTestTracker:
    """
    Structured tracker for Demo Forward-Testing operations.
    """

    @classmethod
    def record_event(
        cls,
        conn: sqlite3.Connection,
        user_id: str,
        account_id: str,
        symbol: str,
        event_type: str,
        direction: Optional[str] = None,
        score: Optional[float] = None,
        entry_qualified: bool = False,
        rejection_reason: Optional[str] = None,
        operation_id: Optional[str] = None,
        position_id: Optional[str] = None,
        execution_price: Optional[float] = None,
        sl_price: Optional[float] = None,
        tp_price: Optional[float] = None,
        spread: Optional[float] = None,
        slippage: Optional[float] = None,
        realized_pnl: Optional[float] = None,
        floating_pnl: Optional[float] = None,
        latency_ms: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> str:
        ensure_forward_test_tables(conn)
        record_id = f"FWD-{secrets.token_hex(8).upper()}"
        now_iso = datetime.now(timezone.utc).isoformat()

        with conn:
            conn.execute(
                """
                INSERT INTO demo_forward_test_records (
                    record_id, user_id, account_id, symbol, event_type,
                    direction, score, entry_qualified, rejection_reason,
                    operation_id, position_id, execution_price, sl_price, tp_price,
                    spread, slippage, realized_pnl, floating_pnl, latency_ms,
                    details_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record_id,
                    str(user_id),
                    str(account_id),
                    str(symbol).upper(),
                    str(event_type),
                    direction.upper() if direction else None,
                    float(score) if score is not None else None,
                    1 if entry_qualified else 0,
                    rejection_reason,
                    str(operation_id) if operation_id else None,
                    str(position_id) if position_id else None,
                    float(execution_price) if execution_price is not None else None,
                    float(sl_price) if sl_price is not None else None,
                    float(tp_price) if tp_price is not None else None,
                    float(spread) if spread is not None else None,
                    float(slippage) if slippage is not None else None,
                    float(realized_pnl) if realized_pnl is not None else None,
                    float(floating_pnl) if floating_pnl is not None else None,
                    float(latency_ms) if latency_ms is not None else None,
                    json.dumps(details or {}, default=str),
                    now_iso,
                ),
            )
        return record_id

    @classmethod
    def get_records(
        cls,
        conn: sqlite3.Connection,
        user_id: str,
        account_id: Optional[str] = None,
        symbol: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        ensure_forward_test_tables(conn)
        query = "SELECT * FROM demo_forward_test_records WHERE user_id = ?"
        params: List[Any] = [str(user_id)]

        if account_id:
            query += " AND account_id = ?"
            params.append(str(account_id))
        if symbol:
            query += " AND symbol = ?"
            params.append(str(symbol).upper())

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))

        rows = conn.execute(query, tuple(params)).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            try:
                d["details"] = json.loads(d.get("details_json") or "{}")
            except Exception:
                d["details"] = {}
            results.append(d)
        return results

    @classmethod
    def get_summary_statistics(
        cls,
        conn: sqlite3.Connection,
        user_id: str,
        account_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        ensure_forward_test_tables(conn)
        where = "WHERE user_id = ?"
        params: List[Any] = [str(user_id)]
        if account_id:
            where += " AND account_id = ?"
            params.append(str(account_id))

        total_evaluations = conn.execute(f"SELECT COUNT(*) FROM demo_forward_test_records {where} AND event_type = 'STRATEGY_QUALIFICATION'", tuple(params)).fetchone()[0]
        qualified_entries = conn.execute(f"SELECT COUNT(*) FROM demo_forward_test_records {where} AND event_type = 'STRATEGY_QUALIFICATION' AND entry_qualified = 1", tuple(params)).fetchone()[0]
        risk_rejections = conn.execute(f"SELECT COUNT(*) FROM demo_forward_test_records {where} AND event_type = 'RISK_REJECTION'", tuple(params)).fetchone()[0]
        executed_orders = conn.execute(f"SELECT COUNT(*) FROM demo_forward_test_records {where} AND event_type = 'ORDER_FILLED'", tuple(params)).fetchone()[0]
        closed_positions = conn.execute(f"SELECT COUNT(*) FROM demo_forward_test_records {where} AND event_type = 'POSITION_CLOSED'", tuple(params)).fetchone()[0]
        avg_latency = conn.execute(f"SELECT AVG(latency_ms) FROM demo_forward_test_records {where} AND latency_ms IS NOT NULL", tuple(params)).fetchone()[0] or 0.0

        return {
            "total_strategy_evaluations": total_evaluations,
            "qualified_signals": qualified_entries,
            "qualification_rate_pct": round((qualified_entries / total_evaluations * 100.0), 1) if total_evaluations > 0 else 0.0,
            "risk_rejections": risk_rejections,
            "broker_executed_orders": executed_orders,
            "closed_positions": closed_positions,
            "average_latency_ms": round(float(avg_latency), 2),
        }
