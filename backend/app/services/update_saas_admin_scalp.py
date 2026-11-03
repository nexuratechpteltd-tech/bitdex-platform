"""
Script to add Phase 3 Scalping Engine Admin routes to saas_admin.py
"""

TARGET = "/opt/tauric-platform-staging/backend/app/routes/saas_admin.py"

with open(TARGET, "r", encoding="utf-8") as f:
    content = f.read()

MODEL_CODE = """
class ScalpControlRequest(BaseModel):
    user_id: str
    reason: Optional[str] = "Admin action"
"""

if "class ScalpControlRequest" not in content:
    marker = "class FuturesKillSwitchRequest(BaseModel):"
    idx = content.find(marker)
    if idx != -1:
        next_class_idx = content.find("class ", idx + len(marker))
        content = content[:next_class_idx] + MODEL_CODE + "\n" + content[next_class_idx:]

ROUTES_CODE = """

# ─── Phase 3: Autonomous Scalping Engine Admin Routes ───

@admin_router.get("/futures/scalp/state")
async def get_scalp_engine_state(
    user_id: Optional[str] = None,
    admin_user = Depends(get_admin_user)
):
    \"\"\"View current state of the autonomous scalping engine.\"\"\"
    conn = get_db_connection()
    try:
        query = "SELECT * FROM futures_scalp_runs"
        params = []
        if user_id:
            query += " WHERE user_id = ?"
            params.append(user_id)
        query += " ORDER BY updated_at DESC LIMIT 10"
        rows = conn.execute(query, tuple(params)).fetchall()
        return {
            "status": "SUCCESS",
            "strategy": "SCALP_ONE_DOLLAR",
            "target_net_profit_usd": 1.00,
            "preferred_holding_duration_seconds": 300,
            "maximum_holding_duration_seconds": 600,
            "runs": [dict(r) for r in rows]
        }
    finally:
        conn.close()

@admin_router.post("/futures/scalp/start")
async def start_scalp_engine(
    req: ScalpControlRequest,
    admin_user = Depends(get_admin_user)
):
    \"\"\"Start autonomous scalping engine for a staging account.\"\"\"
    from ..services.futures_scalping_engine import AutonomousScalpingEngine
    from ..services.admin_ops import audit
    conn = get_db_connection()
    try:
        engine = AutonomousScalpingEngine(conn, user_id=req.user_id)
        result = engine.start()
        audit(conn, actor_id=admin_user["user_id"], action="FUTURES_SCALPING_ENGINE_STARTED",
              target_user_id=req.user_id, details={"reason": req.reason})
        return result
    finally:
        conn.close()

@admin_router.post("/futures/scalp/pause")
async def pause_scalp_engine(
    req: ScalpControlRequest,
    admin_user = Depends(get_admin_user)
):
    \"\"\"Pause autonomous scalping engine.\"\"\"
    from ..services.futures_scalping_engine import AutonomousScalpingEngine
    from ..services.admin_ops import audit
    conn = get_db_connection()
    try:
        engine = AutonomousScalpingEngine(conn, user_id=req.user_id)
        result = engine.pause()
        audit(conn, actor_id=admin_user["user_id"], action="FUTURES_SCALPING_ENGINE_PAUSED",
              target_user_id=req.user_id, details={"reason": req.reason})
        return result
    finally:
        conn.close()

@admin_router.post("/futures/scalp/resume")
async def resume_scalp_engine(
    req: ScalpControlRequest,
    admin_user = Depends(get_admin_user)
):
    \"\"\"Resume autonomous scalping engine.\"\"\"
    from ..services.futures_scalping_engine import AutonomousScalpingEngine
    from ..services.admin_ops import audit
    conn = get_db_connection()
    try:
        engine = AutonomousScalpingEngine(conn, user_id=req.user_id)
        result = engine.resume()
        audit(conn, actor_id=admin_user["user_id"], action="FUTURES_SCALPING_ENGINE_RESUMED",
              target_user_id=req.user_id, details={"reason": req.reason})
        return result
    finally:
        conn.close()

@admin_router.post("/futures/scalp/stop")
async def stop_scalp_engine(
    req: ScalpControlRequest,
    admin_user = Depends(get_admin_user)
):
    \"\"\"Stop autonomous scalping engine.\"\"\"
    from ..services.futures_scalping_engine import AutonomousScalpingEngine
    from ..services.admin_ops import audit
    conn = get_db_connection()
    try:
        engine = AutonomousScalpingEngine(conn, user_id=req.user_id)
        result = engine.stop(reason=req.reason or "ADMIN_STOP")
        audit(conn, actor_id=admin_user["user_id"], action="FUTURES_SCALPING_ENGINE_STOPPED",
              target_user_id=req.user_id, details={"reason": req.reason})
        return result
    finally:
        conn.close()

@admin_router.post("/futures/scalp/emergency-shutdown")
async def emergency_shutdown_scalp_engine(
    req: ScalpControlRequest,
    admin_user = Depends(get_admin_user)
):
    \"\"\"Emergency shutdown for autonomous scalping engine.\"\"\"
    from ..services.futures_scalping_engine import AutonomousScalpingEngine
    from ..services.admin_ops import audit
    conn = get_db_connection()
    try:
        engine = AutonomousScalpingEngine(conn, user_id=req.user_id)
        result = engine.emergency_shutdown()
        audit(conn, actor_id=admin_user["user_id"], action="FUTURES_SCALPING_EMERGENCY_SHUTDOWN",
              target_user_id=req.user_id, details={"reason": req.reason})
        return result
    finally:
        conn.close()

@admin_router.get("/futures/scalp/signals")
async def get_scalp_signals(
    user_id: Optional[str] = None,
    symbol: Optional[str] = None,
    limit: int = 50,
    admin_user = Depends(get_admin_user)
):
    \"\"\"Query recent autonomous scalping candidate signals and rejection reasons.\"\"\"
    conn = get_db_connection()
    try:
        query = "SELECT * FROM futures_scalp_signals WHERE 1=1"
        params = []
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol.upper())
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(min(limit, 200))
        rows = conn.execute(query, tuple(params)).fetchall()
        return {
            "status": "SUCCESS",
            "count": len(rows),
            "signals": [dict(r) for r in rows]
        }
    finally:
        conn.close()

@admin_router.get("/futures/scalp/trades")
async def get_scalp_trades(
    user_id: Optional[str] = None,
    symbol: Optional[str] = None,
    limit: int = 50,
    admin_user = Depends(get_admin_user)
):
    \"\"\"Query completed scalping trades, holding durations, and verified P&L.\"\"\"
    conn = get_db_connection()
    try:
        query = "SELECT * FROM futures_scalp_trades WHERE 1=1"
        params = []
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol.upper())
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(min(limit, 200))
        rows = conn.execute(query, tuple(params)).fetchall()
        return {
            "status": "SUCCESS",
            "count": len(rows),
            "trades": [dict(r) for r in rows]
        }
    finally:
        conn.close()

@admin_router.get("/futures/scalp/performance")
async def get_scalp_performance(
    user_id: Optional[str] = None,
    admin_user = Depends(get_admin_user)
):
    \"\"\"Calculate performance analytics for SCALP_ONE_DOLLAR strategy.\"\"\"
    conn = get_db_connection()
    try:
        query = "SELECT * FROM futures_scalp_trades WHERE exit_time IS NOT NULL"
        params = []
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        rows = conn.execute(query, tuple(params)).fetchall()
        
        trades = [dict(r) for r in rows]
        total_trades = len(trades)
        if total_trades == 0:
            return {
                "status": "SUCCESS",
                "total_trades": 0,
                "win_rate_pct": 0.0,
                "target_hit_rate_pct": 0.0,
                "total_gross_pnl_usd": 0.0,
                "total_fees_usd": 0.0,
                "total_net_pnl_usd": 0.0,
                "average_holding_duration_seconds": 0.0,
            }
            
        winning_trades = sum(1 for t in trades if float(t.get("net_pnl_usd", 0.0)) > 0)
        target_hits = sum(1 for t in trades if int(t.get("target_hit", 0)) == 1 or float(t.get("net_pnl_usd", 0.0)) >= 0.95)
        total_gross = sum(float(t.get("gross_pnl_usd", 0.0)) for t in trades)
        total_fees = sum(float(t.get("total_fees_usd", 0.0)) for t in trades)
        total_net = sum(float(t.get("net_pnl_usd", 0.0)) for t in trades)
        avg_hold = sum(float(t.get("holding_duration_seconds", 0.0)) for t in trades) / total_trades
        
        return {
            "status": "SUCCESS",
            "strategy": "SCALP_ONE_DOLLAR",
            "total_trades": total_trades,
            "win_rate_pct": round((winning_trades / total_trades) * 100, 2),
            "target_hit_rate_pct": round((target_hits / total_trades) * 100, 2),
            "total_gross_pnl_usd": round(total_gross, 4),
            "total_fees_usd": round(total_fees, 4),
            "total_net_pnl_usd": round(total_net, 4),
            "average_holding_duration_seconds": round(avg_hold, 1),
        }
    finally:
        conn.close()
"""

if "@admin_router.get(\"/futures/scalp/state\")" not in content:
    content = content.rstrip() + "\n" + ROUTES_CODE

with open(TARGET, "w", encoding="utf-8") as f:
    f.write(content)

print("saas_admin.py updated with Phase 3 Scalping routes successfully.")
