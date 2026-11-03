"""
BITDEX Pricing Service — global defaults + per-customer overrides.

PRECEDENCE (enforced here, consumed by the billing engine):
    1. A valid (ACTIVE, started, not expired) customer-specific override
    2. Otherwise the CURRENT global default from platform_pricing_config

The global default is read live, so changing it immediately affects every customer
without an override; no per-customer copies of the default are made.

Historical charges are never rewritten: billing_ledger / ai_analysis_runs store the amount
that was actually charged. Every price change is written to pricing_change_log and audit_logs.
"""
from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from .saas_db import get_db_connection

SERVICES: Dict[str, Dict[str, str]] = {
    "AI_ANALYSIS": {
        "name": "AI Market Intelligence Analysis",
        "billing_unit": "per analysis run",
        "global_col": "ai_analysis_price_usd",
        "policy_col": "ai_research_fee_usd",
    },
    "STRATEGY_EXECUTION": {
        "name": "Strategy Execution Fee",
        "billing_unit": "per qualifying order",
        "global_col": "default_execution_fee_usd",
        "policy_col": "execution_fee_usd",
    },
    "PLATFORM_ACTIVATION": {
        "name": "Platform Activation Fee",
        "billing_unit": "one-time",
        "global_col": "default_activation_fee_usd",
        "policy_col": "activation_fee_usd",
    },
}
CURRENCY = "USD"
MAX_PRICE_USD = 1000.0
MATERIAL_CHANGE_RATIO = 0.25  # >25% change requires explicit confirmation


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ddl(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS customer_pricing_overrides (
            override_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            service_id TEXT NOT NULL,
            price_usd REAL NOT NULL CHECK (price_usd >= 0),
            currency TEXT NOT NULL DEFAULT 'USD',
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            effective_from TEXT NOT NULL,
            expires_at TEXT,
            reason TEXT NOT NULL,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            revoked_by TEXT,
            revoked_at TEXT,
            revoke_reason TEXT
        )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cpo_lookup ON customer_pricing_overrides (user_id, service_id, status)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pricing_change_log (
            change_id TEXT PRIMARY KEY,
            scope TEXT NOT NULL,              -- GLOBAL | CUSTOMER
            user_id TEXT,
            service_id TEXT NOT NULL,
            old_price_usd REAL,
            new_price_usd REAL,
            action TEXT NOT NULL,             -- SET_GLOBAL | SET_OVERRIDE | REVOKE_OVERRIDE | EXPIRE
            reason TEXT,
            actor_id TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pcl_user ON pricing_change_log (user_id, created_at)")


def get_global(conn: sqlite3.Connection) -> Dict[str, float]:
    row = conn.execute("SELECT * FROM platform_pricing_config WHERE config_key = 'GLOBAL_DEFAULT'").fetchone()
    if not row:
        return {"AI_ANALYSIS": 1.00, "STRATEGY_EXECUTION": 0.30, "PLATFORM_ACTIVATION": 20.00}
    return {sid: round(float(row[meta["global_col"]]), 2) for sid, meta in SERVICES.items()}


def resolve(user_id: str, service_id: str, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
    """Return the effective price + where it came from. Pure read."""
    if service_id not in SERVICES:
        raise HTTPException(status_code=400, detail=f"Unknown priceable service '{service_id}'.")
    own = conn is None
    if own:
        conn = get_db_connection()
    try:
        now = _now()
        glob = get_global(conn)[service_id]
        ov = conn.execute("""
            SELECT * FROM customer_pricing_overrides
            WHERE user_id = ? AND service_id = ? AND status = 'ACTIVE'
              AND effective_from <= ? AND (expires_at IS NULL OR expires_at > ?)
            ORDER BY created_at DESC LIMIT 1
        """, (user_id, service_id, now, now)).fetchone()
        meta = SERVICES[service_id]
        base = {
            "service_id": service_id,
            "name": meta["name"],
            "billing_unit": meta["billing_unit"],
            "currency": CURRENCY,
            "global_price_usd": glob,
        }
        if ov:
            return {**base, "price_usd": round(float(ov["price_usd"]), 2), "source": "OVERRIDE",
                    "override_id": ov["override_id"], "effective_from": ov["effective_from"],
                    "expires_at": ov["expires_at"]}
        return {**base, "price_usd": glob, "source": "GLOBAL", "override_id": None,
                "effective_from": None, "expires_at": None}
    finally:
        if own:
            conn.close()


def resolve_all(user_id: str, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Dict[str, Any]]:
    return {sid: resolve(user_id, sid, conn) for sid in SERVICES}


def apply_effective(policy_row: Any, user_id: str, conn: Optional[sqlite3.Connection] = None) -> Optional[Dict[str, Any]]:
    """Overlay effective prices onto a fee_policies row so the billing engine charges the right amount."""
    if policy_row is None:
        return None
    d = dict(policy_row)
    for sid, meta in SERVICES.items():
        eff = resolve(user_id, sid, conn)
        d[meta["policy_col"]] = eff["price_usd"]
        d[f"_price_source_{sid}"] = eff["source"]
        d[f"_override_id_{sid}"] = eff["override_id"]
    d["ai_research_fee_cents"] = int(round(float(d["ai_research_fee_usd"]) * 100))
    return d


def _validate_price(price: Any) -> float:
    try:
        p = round(float(price), 2)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Price must be a number.")
    if p != p or p < 0:
        raise HTTPException(status_code=400, detail="Price cannot be negative or invalid.")
    if p > MAX_PRICE_USD:
        raise HTTPException(status_code=400, detail=f"Price exceeds the maximum allowed (${MAX_PRICE_USD:,.2f}).")
    return p


def _material(old: float, new: float) -> bool:
    if old <= 0:
        return new > 0
    return abs(new - old) / old > MATERIAL_CHANGE_RATIO


def preview_override(user_id: str, service_id: str, price: Any) -> Dict[str, Any]:
    p = _validate_price(price)
    cur = resolve(user_id, service_id)
    return {
        "service_id": service_id,
        "current_effective_price_usd": cur["price_usd"],
        "current_source": cur["source"],
        "global_price_usd": cur["global_price_usd"],
        "new_effective_price_usd": p,
        "delta_usd": round(p - cur["price_usd"], 2),
        "requires_confirmation": _material(cur["price_usd"], p),
        "currency": CURRENCY,
    }


def set_override(conn: sqlite3.Connection, actor_id: str, user_id: str, service_id: str, price: Any,
                 reason: str, confirm: bool = False, effective_from: Optional[str] = None,
                 expires_at: Optional[str] = None) -> Dict[str, Any]:
    from .admin_ops import audit  # local import: avoid cycle
    if service_id not in SERVICES:
        raise HTTPException(status_code=400, detail="Unknown priceable service.")
    p = _validate_price(price)
    if not reason or len(reason.strip()) < 3:
        raise HTTPException(status_code=400, detail="A reason (min 3 characters) is required for price changes.")
    u = conn.execute("SELECT user_id, role, status FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if not u:
        raise HTTPException(status_code=404, detail="Customer not found.")
    if u["role"] != "CUSTOMER":
        raise HTTPException(status_code=400, detail="Price overrides apply to customer accounts only.")
    if u["status"] == "DELETED":
        raise HTTPException(status_code=400, detail="Customer has been deleted.")
    now = _now()
    eff_from = effective_from or now
    if expires_at and expires_at <= eff_from:
        raise HTTPException(status_code=400, detail="Expiry must be after the activation date.")
    cur = resolve(user_id, service_id, conn)
    if _material(cur["price_usd"], p) and not confirm:
        raise HTTPException(status_code=409, detail={
            "code": "CONFIRMATION_REQUIRED",
            "message": f"Material price change (${cur['price_usd']:.2f} -> ${p:.2f}). Resend with confirm=true.",
            "current_effective_price_usd": cur["price_usd"], "new_price_usd": p})
    conn.execute("""UPDATE customer_pricing_overrides SET status='REVOKED', revoked_by=?, revoked_at=?,
                    revoke_reason='Superseded by newer override'
                    WHERE user_id=? AND service_id=? AND status='ACTIVE'""", (actor_id, now, user_id, service_id))
    oid = f"OVR-{secrets.token_hex(5).upper()}"
    conn.execute("""INSERT INTO customer_pricing_overrides
        (override_id,user_id,service_id,price_usd,currency,status,effective_from,expires_at,reason,created_by,created_at)
        VALUES (?,?,?,?,?,'ACTIVE',?,?,?,?,?)""",
        (oid, user_id, service_id, p, CURRENCY, eff_from, expires_at, reason.strip(), actor_id, now))
    conn.execute("""INSERT INTO pricing_change_log
        (change_id,scope,user_id,service_id,old_price_usd,new_price_usd,action,reason,actor_id,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (f"PCH-{secrets.token_hex(5).upper()}", "CUSTOMER", user_id, service_id, cur["price_usd"], p,
         "SET_OVERRIDE", reason.strip(), actor_id, now))
    audit(conn, actor_id, "CUSTOMER_PRICE_OVERRIDE_SET", user_id, {
        "service_id": service_id, "old_price_usd": cur["price_usd"], "new_price_usd": p,
        "global_price_usd": cur["global_price_usd"], "override_id": oid, "reason": reason.strip(),
        "effective_from": eff_from, "expires_at": expires_at})
    policy_col = SERVICES[service_id]["policy_col"]
    conn.execute(f"UPDATE fee_policies SET {policy_col} = ?, updated_at = ? WHERE user_id = ?", (p, now, user_id))
    if service_id == "AI_ANALYSIS":
        conn.execute("UPDATE fee_policies SET ai_research_fee_cents = ? WHERE user_id = ?", (int(round(p * 100)), user_id))
    return resolve(user_id, service_id, conn)


def revoke_override(conn: sqlite3.Connection, actor_id: str, user_id: str, service_id: str, reason: str) -> Dict[str, Any]:
    from .admin_ops import audit
    if not reason or len(reason.strip()) < 3:
        raise HTTPException(status_code=400, detail="A reason (min 3 characters) is required.")
    cur = resolve(user_id, service_id, conn)
    if cur["source"] != "OVERRIDE":
        raise HTTPException(status_code=404, detail="No active override to revoke.")
    now = _now()
    conn.execute("""UPDATE customer_pricing_overrides SET status='REVOKED', revoked_by=?, revoked_at=?, revoke_reason=?
                    WHERE override_id=?""", (actor_id, now, reason.strip(), cur["override_id"]))
    new = resolve(user_id, service_id, conn)
    conn.execute("""INSERT INTO pricing_change_log
        (change_id,scope,user_id,service_id,old_price_usd,new_price_usd,action,reason,actor_id,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (f"PCH-{secrets.token_hex(5).upper()}", "CUSTOMER", user_id, service_id, cur["price_usd"],
         new["price_usd"], "REVOKE_OVERRIDE", reason.strip(), actor_id, now))
    audit(conn, actor_id, "CUSTOMER_PRICE_OVERRIDE_REVOKED", user_id, {
        "service_id": service_id, "old_price_usd": cur["price_usd"], "new_price_usd": new["price_usd"],
        "override_id": cur["override_id"], "reason": reason.strip()})
    policy_col = SERVICES[service_id]["policy_col"]
    conn.execute(f"UPDATE fee_policies SET {policy_col} = ?, updated_at = ? WHERE user_id = ?", (new["price_usd"], now, user_id))
    if service_id == "AI_ANALYSIS":
        conn.execute("UPDATE fee_policies SET ai_research_fee_cents = ? WHERE user_id = ?", (int(round(new["price_usd"] * 100)), user_id))
    return new


def set_global(conn: sqlite3.Connection, actor_id: str, changes: Dict[str, Any], reason: str,
               confirm: bool) -> Dict[str, Any]:
    """Update global defaults. Always requires confirm=true (affects every non-override customer)."""
    from .admin_ops import audit
    if not changes:
        raise HTTPException(status_code=400, detail="No pricing changes supplied.")
    if not reason or len(reason.strip()) < 3:
        raise HTTPException(status_code=400, detail="A reason (min 3 characters) is required for global price changes.")
    current = get_global(conn)
    new_vals: Dict[str, float] = {}
    for sid, val in changes.items():
        if sid not in SERVICES:
            raise HTTPException(status_code=400, detail=f"Unknown priceable service '{sid}'.")
        p = _validate_price(val)
        if p != current[sid]:
            new_vals[sid] = p
    if not new_vals:
        return {"changed": [], "global": current}
    if not confirm:
        raise HTTPException(status_code=409, detail={
            "code": "CONFIRMATION_REQUIRED",
            "message": "Global default changes apply to every customer without an override. Resend with confirm=true.",
            "changes": {k: {"old": current[k], "new": v} for k, v in new_vals.items()}})
    now = _now()
    for sid, p in new_vals.items():
        col = SERVICES[sid]["global_col"]
        conn.execute(f"UPDATE platform_pricing_config SET {col} = ?, updated_by = ?, updated_at = ? WHERE config_key = 'GLOBAL_DEFAULT'",
                     (p, actor_id, now))
        if sid == "AI_ANALYSIS":
            conn.execute("UPDATE platform_pricing_config SET ai_analysis_price_cents = ? WHERE config_key = 'GLOBAL_DEFAULT'",
                         (int(round(p * 100)),))
        conn.execute("""INSERT INTO pricing_change_log
            (change_id,scope,user_id,service_id,old_price_usd,new_price_usd,action,reason,actor_id,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (f"PCH-{secrets.token_hex(5).upper()}", "GLOBAL", None, sid, current[sid], p, "SET_GLOBAL",
             reason.strip(), actor_id, now))
    audit(conn, actor_id, "GLOBAL_PRICING_CHANGED", "GLOBAL", {
        "changes": {k: {"old": current[k], "new": v} for k, v in new_vals.items()}, "reason": reason.strip()})
    return {"changed": list(new_vals), "global": get_global(conn)}


def list_overrides(conn: sqlite3.Connection, user_id: str) -> List[Dict[str, Any]]:
    rows = conn.execute("SELECT * FROM customer_pricing_overrides WHERE user_id = ? ORDER BY created_at DESC",
                        (user_id,)).fetchall()
    return [dict(r) for r in rows]


def change_history(conn: sqlite3.Connection, user_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    if user_id:
        rows = conn.execute("SELECT * FROM pricing_change_log WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                            (user_id, limit)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM pricing_change_log ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]
