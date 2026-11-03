"""
Tauric Platform — Universal Strategy Orchestration Router
==========================================================
API endpoints for:
- Provider Registry & Implementation Status
- Eligible Profile Discovery
- Real-time Account Balance & Capital Sizing ('money from account')
- 5-Point Universal Strategy Preflight
- Multi-Exchange Independent Strategy Run Lifecycle (Launch, Pause, Resume, Stop, Query)
- Verifiable Read-Only Exchange Reconciliation & Execution Integrity Audit
"""

from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.config import settings
from app.services.exchange_framework import credential_vault, exchange_framework
from app.services.strategy_orchestrator import (
    strategy_orchestrator,
    PROVIDER_IMPLEMENTATION_STATUS,
    ProviderImplementationStatus,
)

orchestration_router = APIRouter(prefix="/orchestration", tags=["Strategy Orchestration"])


class StrategyPreflightRequest(BaseModel):
    asset: str = Field(..., description="e.g. SOL/USDT, BTC/USDT")
    strategy_id: str = Field(..., description="e.g. SPOT_GRID, FUTURES_GRID, CRYPTO_MOMENTUM")
    profile_id: str = Field(..., description="Connection profile ID or 'PAPER'")
    investment_amount: float = Field(..., description="Capital in quote currency (USD / USDT)")
    environment: str = Field("DEMO", description="DEMO, PAPER, or LIVE")
    risk_config: Optional[Dict[str, Any]] = Field(default_factory=dict)


class StrategyLaunchRequest(BaseModel):
    asset: str = Field(..., description="e.g. SOL/USDT, BTC/USDT")
    strategy_id: str = Field(..., description="e.g. SPOT_GRID, FUTURES_GRID, CRYPTO_MOMENTUM")
    profile_id: str = Field(..., description="Connection profile ID or 'PAPER'")
    investment_amount: float = Field(..., description="Capital in quote currency (USD / USDT)")
    environment: str = Field("DEMO", description="DEMO, PAPER, or LIVE")
    parameters: Optional[Dict[str, Any]] = Field(default_factory=dict)
    risk_config: Optional[Dict[str, Any]] = Field(default_factory=dict)
    idempotency_key: Optional[str] = Field(None, description="Optional idempotency key")
    is_test: Optional[bool] = Field(False, description="Flag indicating automated test execution")


@orchestration_router.get("/providers")
async def list_orchestration_providers():
    """
    Returns the comprehensive provider registry with implementation categorization.
    Distinguishes IMPLEMENTED_TESTED, BRIDGE_DEPENDENT, and PLANNED providers.
    """
    base_providers = exchange_framework.get_provider_registry()
    annotated = []
    for p in base_providers:
        pid = (p.get("provider_id") or p.get("provider") or p.get("id") or "").upper()
        impl_stat = strategy_orchestrator.get_provider_implementation_status(pid)
        item = dict(p)
        item["implementation_status"] = impl_stat
        annotated.append(item)
    return {
        "status": "SUCCESS",
        "live_trading_locked": settings.live_trading_locked,
        "read_only_mode": settings.read_only_mode,
        "providers": annotated,
    }


@orchestration_router.get("/profiles/eligible")
async def list_eligible_profiles(
    strategy_id: Optional[str] = Query(None, description="Optional strategy filter"),
    market_type: Optional[str] = Query(None, description="CRYPTO or FOREX"),
):
    """
    Returns only active, enabled connection profiles eligible for strategy execution.
    Excludes disabled (is_active === false) profiles. Excludes internal simulator from wizard.
    """
    all_profiles = credential_vault.list_profiles()
    eligible = []

    for p in all_profiles:
        # Strictly require is_active != False
        if p.get("is_active") is False:
            continue

        if market_type and p.get("market_type", "").upper() != market_type.upper():
            continue

        pid = p.get("exchange", "").upper()
        impl_stat = strategy_orchestrator.get_provider_implementation_status(pid)

        item = dict(p)
        item["implementation_status"] = impl_stat
        item["eligible"] = (impl_stat == ProviderImplementationStatus.IMPLEMENTED_TESTED.value)
        eligible.append(item)

    return {
        "status": "SUCCESS",
        "count": len(eligible),
        "profiles": eligible,
    }


@orchestration_router.get("/profiles/{profile_id}/balance")
async def get_profile_balance(
    profile_id: str,
    asset: Optional[str] = Query(None, description="Optional asset context e.g. SOL/USDT"),
):
    """
    Fetches real money / capital allocated and available in the target profile ('money from account').
    Used by the Strategy Launch Wizard to validate investment sizing against actual available funds.
    """
    cap_info = await strategy_orchestrator.get_profile_available_capital(profile_id, asset)
    return {"status": "SUCCESS", "capital": cap_info}


@orchestration_router.post("/preflight")
async def run_strategy_preflight(req: StrategyPreflightRequest):
    """
    Executes the 5-point universal pre-flight gate.
    Validates profile state, capabilities, available account money, and live lock safety.
    """
    res = await strategy_orchestrator.preflight_strategy_launch(
        asset=req.asset,
        strategy_id=req.strategy_id,
        profile_id=req.profile_id,
        investment_amount=req.investment_amount,
        environment=req.environment,
        risk_config=req.risk_config,
    )
    return res


@orchestration_router.post("/runs/launch")
async def launch_strategy_run(req: StrategyLaunchRequest):
    """
    Launches an isolated strategy run enforcing execution integrity.
    Exchange mutations are kept disabled by safety policy (marked PLAN_ONLY or PAPER_SIMULATION).
    Zero synthetic order IDs.
    """
    res = await strategy_orchestrator.launch_strategy_run(
        asset=req.asset,
        strategy_id=req.strategy_id,
        profile_id=req.profile_id,
        investment_amount=req.investment_amount,
        environment=req.environment,
        parameters=req.parameters,
        risk_config=req.risk_config,
        idempotency_key=req.idempotency_key,
        is_test=bool(req.is_test),
    )

    if res.get("status") in ("PREFLIGHT_BLOCKED", "AUTHORIZATION_BLOCKED"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": res.get("message"),
                "blockers": res.get("blockers", []),
                "corrective_actions": res.get("corrective_actions", ["Configure and authorize live trading in Settings or select DEMO/PAPER."]),
            },
        )

    return res


@orchestration_router.get("/runs")
async def list_strategy_runs(
    provider: Optional[str] = Query(None),
    environment: Optional[str] = Query(None),
    asset: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    exclude_tests: bool = Query(True, description="Filter out automated test runs"),
):
    """
    Returns all strategy runs with optional filters.
    Evaluates worker liveness and excludes test runs by default.
    """
    runs = strategy_orchestrator.list_strategy_runs(
        provider=provider,
        environment=environment,
        asset=asset,
        status=status_filter,
        exclude_tests=exclude_tests,
    )
    return {
        "status": "SUCCESS",
        "count": len(runs),
        "strategy_runs": runs,
    }


@orchestration_router.get("/runs/{run_id}")
async def get_strategy_run_detail(run_id: str):
    """Returns complete state, order history, fills, fees, and P&L for a strategy run."""
    run = strategy_orchestrator.get_strategy_run(run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Strategy run '{run_id}' not found.",
        )
    return {"status": "SUCCESS", "strategy_run": run}


@orchestration_router.post("/runs/{run_id}/pause")
async def pause_strategy_run(run_id: str):
    """Pauses an active strategy run."""
    success = await strategy_orchestrator.pause_strategy_run(run_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot pause run '{run_id}' (must be RUNNING, PLAN_ONLY, or PAPER_SIMULATION).",
        )
    return {"status": "SUCCESS", "message": f"Strategy run '{run_id}' paused."}


@orchestration_router.post("/runs/{run_id}/resume")
async def resume_strategy_run(run_id: str):
    """Resumes a paused strategy run."""
    success = await strategy_orchestrator.resume_strategy_run(run_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot resume run '{run_id}' (must be PAUSED).",
        )
    return {"status": "SUCCESS", "message": f"Strategy run '{run_id}' resumed."}


@orchestration_router.post("/runs/{run_id}/stop")
async def stop_strategy_run(run_id: str):
    """
    Stops a strategy run with verifiable execution check.
    Zero unconfirmed claims: If exchange orders existed, marks STOP_UNCONFIRMED / RECONCILIATION_REQUIRED.
    If zero exchange orders existed, transitions directly to STOPPED with NO_EXCHANGE_ORDERS.
    """
    res = await strategy_orchestrator.stop_strategy_run(run_id)
    if res.get("status") == "NOT_FOUND":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=res.get("message"),
        )
    return res


@orchestration_router.post("/runs/{run_id}/reconcile")
async def reconcile_strategy_run(run_id: str):
    """
    Performs read-only exchange reconciliation for the specified strategy run.
    Queries the exchange to check for actual open orders without mutating state.
    """
    res = await strategy_orchestrator.reconcile_strategy_run(run_id)
    if res.get("status") == "NOT_FOUND":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=res.get("message"),
        )
    return res


@orchestration_router.post("/runs/reconcile-all")
async def reconcile_all_strategy_runs():
    """
    Performs read-only exchange reconciliation across all tracked strategy runs.
    """
    runs = strategy_orchestrator.list_strategy_runs(exclude_tests=False)
    results = []
    for r in runs:
        rid = r.get("run_id")
        if rid:
            res = await strategy_orchestrator.reconcile_strategy_run(rid)
            results.append(res)
    return {
        "status": "SUCCESS",
        "reconciled_count": len(results),
        "results": results,
    }


@orchestration_router.delete("/runs/{run_id}")
async def delete_strategy_run(run_id: str):
    """Archives and deletes a stopped strategy run."""
    success = await strategy_orchestrator.delete_strategy_run(run_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Strategy run '{run_id}' not found.",
        )
    return {"status": "SUCCESS", "message": f"Strategy run '{run_id}' removed."}
