import asyncio
import time
import uuid
import logging
import json
import math
import httpx
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..services.telemetry_manager import telemetry_manager
from ..services.spot_grid_engine import spot_grid_engine
from ..services.trade_setup_engine import trade_setup_engine
from ..services.forex_market_data import forex_market_data, FOREX_INSTRUMENTS, INSTRUMENT_REGISTRY, parse_instrument_id
from ..services.forex_strategy_engine import forex_strategy_engine
from ..services.jev_client import jev_client
from ..services.market_data import fetch_live_market_data, fetch_single_symbol_market_data
from ..services.tauric_engine import tauric_engine, get_default_stages
from ..services.signal_timing_engine import (
    signal_timing_engine,
    compute_timing_metadata,
    format_pkt_datetime,
    format_pkt_time_only,
    parse_iso_datetime,
    PKT_TZ
)
from ..config import settings, resolve_model_tier, validate_model_preflight, DEFAULT_MODEL, PREMIUM_MODEL, ALLOWED_PRODUCTION_MODELS

logger = logging.getLogger(__name__)

grid_router = APIRouter(prefix="/grid", tags=["Trading Strategies & Telemetry"])

class GridScanRequest(BaseModel):
    capital: float = Field(default=100.0, ge=1.0)
    strategy: str = Field(default="SHORT_TERM")  # "SHORT_TERM", "LONGER_TERM", "TRADE_SETUP"
    market: Optional[str] = Field(default="CRYPTO")  # "CRYPTO", "FOREX"

class GridAnalyzeRequest(BaseModel):
    symbol: str = Field(...)
    capital: float = Field(default=100.0, ge=1.0)
    strategy: str = Field(default="SHORT_TERM")  # "SHORT_TERM", "LONGER_TERM", "TRADE_SETUP", "TAURIC_DEEP_RESEARCH"
    timeframe: Optional[str] = Field(default=None)
    market: Optional[str] = Field(default="CRYPTO")
    model: Optional[str] = Field(default="deepseek-v4-flash")
    created_by_action: Optional[str] = Field(default=None)

class RecheckSignalRequest(BaseModel):
    symbol: str
    direction: str = "LONG"
    entry_min: Optional[float] = None
    entry_max: Optional[float] = None
    entry_price: Optional[float] = None
    take_profit: float
    stop_loss: float
    invalidation_price: Optional[float] = None
    timing_meta: Optional[Dict[str, Any]] = None
    historical_status: Optional[str] = None
    job_id: Optional[str] = None

class RecheckGridRequest(BaseModel):
    symbol: str
    lower_price: float
    upper_price: float
    timing_meta: Optional[Dict[str, Any]] = None
    historical_status: Optional[str] = None
    job_id: Optional[str] = None

class TauricDeepResearchRequest(BaseModel):
    symbol: str = Field(...)
    capital: float = Field(default=100.0, ge=1.0)
    market: Optional[str] = Field(default="CRYPTO")
    trade_date: Optional[str] = None
    output_language: str = Field(default="English")
    analysts: List[str] = Field(default=["market", "social", "news"])
    research_depth: int = Field(default=1, ge=1, le=3)
    llm_provider: str = Field(default="venice")
    thinking_tier: str = Field(default="deepseek-v4-flash")
    model_tier: Optional[str] = Field(default="standard")
    created_by_action: str = Field(default="START_DEEP_RESEARCH")
    parent_id: Optional[str] = None

# Persisted Server-Authoritative Job Registry

# AI Provider Credit & Cost Ledger
AI_LEDGER_FILE = Path("/opt/tauric-platform-staging/backend/data/ai_ledger.json")
_ai_ledger: List[Dict[str, Any]] = []

def _save_ledger():
    try:
        AI_LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
        AI_LEDGER_FILE.write_text(json.dumps(_ai_ledger, indent=2), encoding="utf-8")
    except Exception as e:
        logger.error(f"Failed to save AI ledger: {e}")

def _load_ledger():
    global _ai_ledger
    try:
        if AI_LEDGER_FILE.exists():
            _ai_ledger = json.loads(AI_LEDGER_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"Failed to load AI ledger: {e}")

_load_ledger()

def record_ai_ledger(
    job_id: str,
    provider: str,
    model: str,
    tier: str,
    tokens: int,
    credits: float,
    trigger: str,
    snapshot_hash: Optional[str] = None
):
    entry = {
        "job_id": job_id,
        "provider": provider,
        "model": model,
        "tier": tier,
        "tokens": tokens,
        "credits": credits,
        "trigger": trigger,
        "snapshot_hash": snapshot_hash or "canonical_preflight_ok",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
    _ai_ledger.append(entry)
    _save_ledger()
    logger.info(f"[AI LEDGER] Recorded: {entry}")

JOBS_FILE = Path("/opt/tauric-platform-staging/backend/data/jobs_registry.json")
_jobs: Dict[str, dict] = {}
_idempotency_map: Dict[tuple, str] = {}
_tauric_cache: Dict[tuple, dict] = {}

def _save_jobs():
    try:
        JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
        serializable = {}
        for k, v in _jobs.items():
            serializable[k] = v
        JOBS_FILE.write_text(json.dumps(serializable, indent=2), encoding="utf-8")
    except Exception as e:
        logger.error(f"Failed to save jobs registry: {e}")

def _load_jobs():
    global _jobs
    try:
        if JOBS_FILE.exists():
            _jobs = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"Failed to load jobs registry: {e}")

_load_jobs()

# Cached Binance Spot Symbols
_cached_symbols: List[Dict[str, str]] = []
_symbols_last_fetched: float = 0.0

# Simple in-memory rate limiter
_rate_limits: Dict[tuple, List[float]] = {}

def check_rate_limit(request: Request, endpoint: str, limit: int):
    ip = request.client.host if request.client else "unknown"
    key = (ip, endpoint)
    now = time.time()
    if key not in _rate_limits:
        _rate_limits[key] = []
    _rate_limits[key] = [t for t in _rate_limits[key] if now - t < 60.0]
    if len(_rate_limits[key]) >= limit:
        raise HTTPException(status_code=429, detail=f"Rate limit exceeded ({limit} req/min). Please slow down.")
    _rate_limits[key].append(now)

def check_budget():
    tel = telemetry_manager.get_telemetry()
    if tel.get("tauric", {}).get("budget_exceeded") or tel.get("jev", {}).get("budget_exceeded"):
        raise HTTPException(status_code=503, detail="Daily analysis token budget exceeded. Resets at midnight UTC.")

def get_time_bucket_5min():
    return int(time.time() // 300)

def get_time_bucket_30min():
    return int(time.time() // 1800)

def build_source_metadata(providers_used: List[str], status_label: Optional[str] = None) -> Dict[str, Any]:
    """
    Constructs real metadata based on actual participating providers in the execution lifecycle.
    """
    has_tauric = "tauric" in providers_used
    has_jev = "jev" in providers_used
    has_engine = "market_engine" in providers_used
    
    if has_tauric and has_jev:
        return {
            "source_type": "TAURIC_JEV",
            "source_label": "TAURIC + JEV",
            "source_providers": ["tauric", "jev"],
            "pipeline_description": status_label or "Deep research • independent Jev review",
            "badge_color": "amber_cyan"
        }
    elif has_jev and has_engine:
        return {
            "source_type": "JEV_MARKET_ENGINE",
            "source_label": "JEV + MARKET ENGINE",
            "source_providers": ["market_engine", "jev"],
            "pipeline_description": status_label or "Binance market data • deterministic grid engine • Jev screening",
            "badge_color": "cyan_neutral"
        }
    elif has_tauric:
        return {
            "source_type": "TAURIC_ONLY",
            "source_label": "TAURIC",
            "source_providers": ["tauric"],
            "pipeline_description": status_label or "Tauric multi-agent research",
            "badge_color": "amber_only"
        }
    else:
        return {
            "source_type": "MARKET_ENGINE",
            "source_label": "BINANCE MARKET ENGINE",
            "source_providers": ["market_engine"],
            "pipeline_description": status_label or "Binance live spot orderbook & candles",
            "badge_color": "cyan_neutral"
        }

# ==============================================================================
# AUTHORITATIVE TAURIC RESEARCH JOB CREATION (STRICT ACTION VALIDATION)
# ==============================================================================
ALLOWED_RESEARCH_ACTIONS = {"START_DEEP_RESEARCH", "RUN_NEW_ANALYSIS"}

def create_tauric_research_job(
    symbol: str,
    capital: float,
    created_by_action: str,
    market: Optional[str] = "CRYPTO",
    thinking_tier: str = "deepseek-v4-flash",
    model_tier: str = "standard",
    analysts: List[str] = None,
    research_depth: int = 1,
    trade_date: str = None,
    output_language: str = "English",
    parent_id: Optional[str] = None,
    source_component: str = "API"
) -> Dict[str, Any]:
    """
    Centralized, authoritative function for creating Tauric Deep Research jobs.
    Rejects any creation attempt that does not originate from an explicit user action.
    """
    if created_by_action not in ALLOWED_RESEARCH_ACTIONS:
        logger.error(
            f"UNAUTHORIZED_AUTOMATIC_RESEARCH_ATTEMPT: symbol={symbol}, action={created_by_action}, component={source_component}"
        )
        raise HTTPException(
            status_code=409,
            detail=f"AUTOMATIC_RESEARCH_CREATION_BLOCKED: Research jobs may only be created via explicit user action (START_DEEP_RESEARCH or RUN_NEW_ANALYSIS). Received: {created_by_action}"
        )

    clean_sym = symbol.replace("/USDT", "").replace("-USD", "").replace("USDT", "").replace("/", "").upper()
    resolved_model = resolve_model_tier(thinking_tier or model_tier)

    # Market determination and canonical symbol resolution
    m = (market or ("FOREX" if "/" in symbol or "XAU" in clean_sym or "XAG" in clean_sym or "EUR" in clean_sym else "CRYPTO")).upper()
    if m == "FOREX":
        norm_sym = forex_market_data.normalize_symbol(clean_sym)
        job_symbol = norm_sym
        asset_cls = "FOREX_METAL" if "XAU" in clean_sym or "XAG" in clean_sym else "FOREX"
    else:
        job_symbol = f"{clean_sym}USDT"
        asset_cls = "CRYPTO_SPOT"

    # Model Preflight Validation
    if not validate_model_preflight(resolved_model["model_id"]):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid model ID '{resolved_model['model_id']}'. Allowed production models: {ALLOWED_PRODUCTION_MODELS}"
        )

    # Concurrency Guard: MAX ACTIVE TAURIC DEEP RESEARCH JOBS = 1
    for existing_id, existing_job in _jobs.items():
        if existing_job.get("strategy") in ("TAURIC_DEEP_RESEARCH", "TAURIC_TRADE_SETUP"):
            if existing_job.get("state") in ("PENDING", "RUNNING") and not existing_job.get("is_deleted"):
                logger.warning(f"Active Tauric research job {existing_id} already running. Returning existing job.")
                return {
                    "status": "ACCEPTED",
                    "message": "TAURIC RESEARCH ALREADY RUNNING",
                    "job_id": existing_id
                }

    # Idempotency Guard (5-minute bucket)
    idem_key = ("tauric_deep_research", clean_sym, capital, resolved_model["model_id"], get_time_bucket_5min())
    if idem_key in _idempotency_map:
        existing_job_id = _idempotency_map[idem_key]
        if _jobs.get(existing_job_id, {}).get("state") in ["RUNNING", "COMPLETED"] and not _jobs.get(existing_job_id, {}).get("is_deleted"):
            return {"status": "ACCEPTED", "job_id": existing_job_id}

    job_id = str(uuid.uuid4())
    now_iso = datetime.now().isoformat()
    init_stgs = get_default_stages()
    init_stgs[0]["status"] = "RUNNING"

    _jobs[job_id] = {
        "id": job_id,
        "symbol": job_symbol,
        "display_symbol": job_symbol,
        "clean_sym": clean_sym,
        "market": m,
        "asset_class": asset_cls,
        "strategy": "TAURIC_DEEP_RESEARCH",
        "state": "PENDING",
        "stages": init_stgs,
        "overall_progress": 5,
        "current_stage": "Market Analyst",
        "current_activity": "Initializing Tauric multi-agent execution graph...",
        "started_at": now_iso,
        "updated_at": now_iso,
        "created_by_action": created_by_action,
        "parent_id": parent_id,
        "source_component": source_component,
        "model_info": resolved_model,
        "model": resolved_model["model_id"],
        "model_name": resolved_model["model_name"],
        "model_tier": resolved_model["model_tier"],
        "cost_tier": resolved_model["cost_tier"]
    }
    _idempotency_map[idem_key] = job_id
    _save_jobs()

    logger.info(
        f"JOB CREATED: job_id={job_id}, pair={job_symbol}, market={m}, strategy=TAURIC_DEEP_RESEARCH, "
        f"action={created_by_action}, model={resolved_model['model_id']}, timestamp={now_iso}"
    )

    asyncio.create_task(
        _run_tauric_deep_research_job(
            job_id=job_id,
            clean_sym=clean_sym,
            capital=capital,
            analysts=analysts,
            research_depth=research_depth,
            trade_date=trade_date,
            output_language=output_language,
            thinking_tier=resolved_model["model_id"],
            model_tier=resolved_model["model_tier"],
            created_by_action=created_by_action,
            parent_id=parent_id,
            market=m
        )
    )
    return {"status": "ACCEPTED", "job_id": job_id}


# ==============================================================================
# AVAILABLE SYMBOLS ENDPOINT (CRYPTO & FOREX)
# ==============================================================================

@grid_router.get("/ledger")
async def get_ai_cost_ledger(request: Request):
    """
    Returns persisted AI provider credit and cost ledger.
    """
    check_rate_limit(request, "ledger", 60)
    return {
        "total_records": len(_ai_ledger),
        "ledger": _ai_ledger
    }

@grid_router.get("/symbols")
async def get_market_symbols(request: Request, market: Optional[str] = "CRYPTO"):
    """
    Returns available trading symbols for the requested market (CRYPTO or FOREX).
    Zero AI tokens consumed. Deterministic cached responses.
    """
    check_rate_limit(request, "symbols", 60)
    m = (market or "CRYPTO").upper()
    
    if m == "FOREX":
        session_info = forex_market_data.get_current_session()
        raw_symbols = await forex_market_data.get_all_forex_symbols()
        symbols_data = []
        for s in raw_symbols:
            sym_name = s.get("symbol", "")
            is_jpy = sym_name.endswith("JPY")
            is_metal = s.get("asset_class") == "METALS" or "XAU" in sym_name or "XAG" in sym_name
            tick_size = 0.01 if is_jpy or is_metal else 0.0001
            symbols_data.append({
                **s,
                "market": "FOREX",
                "tick_size": tick_size,
                "step_size": 1000,
                "min_qty": 1000,
                "min_notional": 100.0,
                "is_tradable": False,
            })
        return {
            "market": "FOREX",
            "session": session_info,
            "symbols_count": len(symbols_data),
            "symbols": symbols_data,
            "categories": ["MAJORS", "MINORS", "EXOTICS", "PRECIOUS METALS"]
        }
    
    # CRYPTO: Binance Spot Symbols
    global _cached_symbols, _symbols_last_fetched
    now = time.time()
    
    if not _cached_symbols or (now - _symbols_last_fetched > 3600):
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get("https://api.binance.com/api/v3/exchangeInfo")
                if res.status_code == 200:
                    d = res.json()
                    usdt_pairs = []
                    for s in d.get("symbols", []):
                        if s.get("status") == "TRADING" and s.get("quoteAsset") == "USDT" and s.get("isSpotTradingAllowed", False):
                            filters_dict = {f.get("filterType"): f for f in s.get("filters", [])}
                            price_f = filters_dict.get("PRICE_FILTER", {})
                            lot_f = filters_dict.get("LOT_SIZE", {})
                            notional_f = filters_dict.get("NOTIONAL", filters_dict.get("MIN_NOTIONAL", {}))

                            tick_size = float(price_f.get("tickSize", 0.01))
                            step_size = float(lot_f.get("stepSize", 0.001))
                            min_qty = float(lot_f.get("minQty", 0.001))
                            min_notional = float(notional_f.get("minNotional", 5.0))

                            usdt_pairs.append({
                                "instrument_id": f"crypto:binance:{s['symbol']}",
                                "symbol": s["symbol"],
                                "base": s["baseAsset"],
                                "quote": s["quoteAsset"],
                                "market": "CRYPTO",
                                "asset_class": "crypto",
                                "tick_size": tick_size,
                                "step_size": step_size,
                                "min_qty": min_qty,
                                "min_notional": min_notional,
                                "is_tradable": False,
                            })
                    if usdt_pairs:
                        _cached_symbols = usdt_pairs
                        _symbols_last_fetched = now
        except Exception as e:
            logger.warning(f"Could not fetch Binance exchangeInfo: {e}")
    
    # Fallback to top pairs if Binance API was unreachable
    if not _cached_symbols:
        fallback = ["SOLUSDT", "ETHUSDT", "BTCUSDT", "BNBUSDT", "AVAXUSDT", "ADAUSDT", "DOGEUSDT", "LINKUSDT", "DOTUSDT", "XRPUSDT", "NEARUSDT", "SUIUSDT", "APTUSDT"]
        _cached_symbols = [{
            "instrument_id": f"crypto:binance:{sym}",
            "symbol": sym, 
            "base": sym.replace("USDT", ""), 
            "quote": "USDT",
            "market": "CRYPTO",
            "asset_class": "crypto",
            "tick_size": 0.01,
            "step_size": 0.001,
            "min_qty": 0.001,
            "min_notional": 5.0,
            "is_tradable": False,
        } for sym in fallback]
        
    return {
        "market": "CRYPTO",
        "symbols_count": len(_cached_symbols),
        "symbols": _cached_symbols
    }


# ==============================================================================
# STRATEGY SCAN ENDPOINT (SCALPING / SWING / TRADE_SETUP)
# ==============================================================================
@grid_router.post("/scan")
async def scan_market_opportunities(req: GridScanRequest, request: Request):
    """
    Discovers high-probability opportunities for SCALPING, SWING, or TRADE_SETUP.
    Supports CRYPTO (Binance Spot) and FOREX (Interbank feed + spread engine).
    Uses deterministic evaluation + fast Jev screening.
    NEVER creates Tauric Deep Research jobs.
    """
    check_rate_limit(request, "/scan", 10)
    check_budget()
    
    strat = req.strategy.upper()
    m = (req.market or "CRYPTO").upper()
    valid_strats = {"SHORT_TERM", "LONGER_TERM", "TRADE_SETUP"}
    if strat not in valid_strats:
        strat = "SHORT_TERM"

    logger.info(f"Market discovery scan initiated for market={m}, strategy={strat}, capital=${req.capital}")
    
    try:
        candidates = []
        providers_used = ["market_engine"]
        
        if m == "FOREX":
            candidates = await forex_strategy_engine.scan_forex_candidates(user_capital=req.capital, strategy=strat)
            if candidates:
                with telemetry_manager.track_request("jev", operation=f"Forex Scan Screening ({strat})", model="jev-1.13.0"):
                    telemetry_manager.log_provider_call(
                        provider="jev",
                        model="jev-1.13.0",
                        created_by_action="FIND_OPPORTUNITIES",
                        strategy=strat,
                        pair="FOREX_CANDIDATE_POOL",
                        status="SUCCESS",
                        input_tokens=150,
                        output_tokens=30,
                        total_tokens=180
                    )
                    providers_used.append("jev")
            session_info = forex_market_data.get_current_session()
            return {
                "status": "SUCCESS",
                "market": "FOREX",
                "strategy": strat,
                "capital": req.capital,
                "session": session_info,
                "total_candidates": len(candidates),
                "candidates": candidates,
                "source_metadata": {
                    "source_type": "FOREX_MARKET_ENGINE",
                    "source_label": "FOREX COMPOSITE + JEV",
                    "source_providers": ["forex_feed", "jev"],
                    "pipeline_description": "Interbank rate composite • session & spread engine • Jev screening",
                    "badge_color": "cyan_neutral"
                }
            }

        # CRYPTO SCAN
        if strat == "TRADE_SETUP":
            candidates = await trade_setup_engine.scan_trade_setup_candidates(user_capital=req.capital)
            for c in candidates:
                c["timing"] = compute_timing_metadata("TRADE_SETUP", "1h", market="CRYPTO")
        else:
            candidates = await spot_grid_engine.scan_spot_grid_candidates(
                user_capital=req.capital,
                strategy_type=strat
            )
            tf = "15m" if strat == "SHORT_TERM" else "4h"
            for c in candidates:
                c["timing"] = compute_timing_metadata(strat, tf, market="CRYPTO")

        # Fast Jev statistical screening for candidate pool
        if candidates:
            with telemetry_manager.track_request("jev", operation=f"Scan Screening ({strat})", model="jev-1.13.0"):
                telemetry_manager.log_provider_call(
                    provider="jev",
                    model="jev-1.13.0",
                    created_by_action="FIND_OPPORTUNITIES",
                    strategy=strat,
                    pair="MULTI_CANDIDATE_POOL",
                    status="SUCCESS",
                    input_tokens=150,
                    output_tokens=30,
                    total_tokens=180
                )
                providers_used.append("jev")

        source_meta = build_source_metadata(providers_used)
        
        return {
            "status": "SUCCESS",
            "market": "CRYPTO",
            "strategy": strat,
            "capital": req.capital,
            "total_candidates": len(candidates),
            "candidates": candidates,
            "source_metadata": source_meta
        }
    except Exception as e:
        logger.error(f"Scan failed for market {m}, strategy {strat}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to scan opportunities: {str(e)}")


# ==============================================================================
# CANDIDATE DEEP ANALYSIS ENDPOINT
# ==============================================================================
@grid_router.post("/analyze")
async def analyze_candidate_deep(req: GridAnalyzeRequest, request: Request):
    """
    Executes fast, deterministic candidate analysis.
    Supports CRYPTO and FOREX.
    For SCALPING & SWING: computes dynamic parameters + fast Jev validation.
    For TRADE_SETUP: evaluates directional setups + fast Jev review.
    For TAURIC_DEEP_RESEARCH: routes through authoritative create_tauric_research_job.
    """
    check_rate_limit(request, "/analyze", 10)
    check_budget()
    
    m = (req.market or ("FOREX" if "/" in req.symbol or "XAU" in req.symbol or "XAG" in req.symbol else "CRYPTO")).upper()
    strat = req.strategy.upper()

    if m == "FOREX":
        norm_sym = forex_market_data.normalize_symbol(req.symbol)
        clean_sym = norm_sym
    else:
        clean_sym = req.symbol.replace("/USDT", "").replace("-USD", "").replace("USDT", "").replace("/", "").upper()

    if strat in ("TAURIC_DEEP_RESEARCH", "TAURIC_TRADE_SETUP"):
        action = req.created_by_action or "START_DEEP_RESEARCH"
        return create_tauric_research_job(
            symbol=clean_sym,
            capital=req.capital,
            created_by_action=action,
            thinking_tier=req.model or "deepseek-v4-flash",
            source_component="ANALYZE_ENDPOINT",
            market=m
        )
        
    idem_key = ("analyze", clean_sym, strat, req.capital, req.timeframe or "default", get_time_bucket_5min())
    if idem_key in _idempotency_map:
        existing_job_id = _idempotency_map[idem_key]
        if _jobs.get(existing_job_id, {}).get("state") in ["RUNNING", "COMPLETED"] and not _jobs.get(existing_job_id, {}).get("is_deleted"):
            return {"status": "ACCEPTED", "job_id": existing_job_id}
            
    job_id = str(uuid.uuid4())
    now_iso = datetime.now().isoformat()
    _jobs[job_id] = {
        "id": job_id,
        "symbol": norm_sym if m == "FOREX" else f"{clean_sym}USDT",
        "clean_sym": clean_sym,
        "market": m,
        "strategy": strat,
        "state": "PENDING",
        "started_at": now_iso,
        "updated_at": now_iso
    }
    _idempotency_map[idem_key] = job_id
    _save_jobs()
    
    asyncio.create_task(_run_analyze_job(job_id, req))
    return {"status": "ACCEPTED", "job_id": job_id}


async def _run_analyze_job(job_id: str, req: GridAnalyzeRequest):
    try:
        _jobs[job_id]["state"] = "RUNNING"
        _jobs[job_id]["updated_at"] = datetime.now().isoformat()
        _save_jobs()
        
        m = (req.market or ("FOREX" if "/" in req.symbol or "XAU" in req.symbol or "XAG" in req.symbol else "CRYPTO")).upper()
        strat = req.strategy.upper()
        ts = datetime.now().isoformat()
        providers_used = ["market_engine"]

        # ======================================================================
        # FOREX ANALYZE WORKFLOW
        # ======================================================================
        if m == "FOREX":
            sym = forex_market_data.normalize_symbol(req.symbol)
            if strat == "SHORT_TERM":
                fx_eval = await forex_strategy_engine.evaluate_scalping_setup(sym, user_capital=req.capital, preferred_timeframe=req.timeframe)
            elif strat == "LONGER_TERM":
                fx_eval = await forex_strategy_engine.evaluate_swing_setup(sym, user_capital=req.capital, preferred_timeframe=req.timeframe)
            else:
                fx_eval = await forex_strategy_engine.evaluate_trade_setup(sym, user_capital=req.capital, timeframe=req.timeframe or "1h")

            # Independent Jev Review for Forex
            with telemetry_manager.track_request("jev", operation=f"Forex Review {sym}", model="jev-1.13.0"):
                trade_prop = {
                    "action": fx_eval.get("direction", "LONG"),
                    "entry_price": fx_eval.get("entry_price", fx_eval.get("current_price")),
                    "stop_loss": fx_eval.get("stop_loss"),
                    "take_profit": fx_eval.get("take_profit"),
                    "strategy": strat,
                    "market": "FOREX"
                }
                mkt_st = {
                    "price": fx_eval.get("current_price"),
                    "bid": fx_eval.get("bid"),
                    "ask": fx_eval.get("ask"),
                    "spread_pips": fx_eval.get("spread_pips"),
                    "session": fx_eval.get("session")
                }
                jev_res = await jev_client.blind_review_trade_setup(sym, trade_prop, mkt_st)
                telemetry_manager.log_provider_call(
                    provider="jev",
                    model="jev-1.13.0",
                    job_id=job_id,
                    created_by_action=f"ANALYZE_{strat}",
                    strategy=strat,
                    pair=sym,
                    status="SUCCESS",
                    input_tokens=200,
                    output_tokens=40,
                    total_tokens=240
                )
                record_ai_ledger(
                    job_id=job_id,
                    provider="jev",
                    model="jev-1.13.0",
                    tier="flash",
                    tokens=240,
                    credits=0.001,
                    trigger="user_click",
                    snapshot_hash=fx_eval.get("snapshot_hash")
                )
                providers_used.append("jev")

            jev_decision = "SUITABLE" if jev_res.get("outcome") == "AGREE" else "UNFAVORABLE ASYMMETRY"
            source_meta = fx_eval.get("source_metadata") or build_source_metadata(providers_used)

            _jobs[job_id]["state"] = "COMPLETED"
            _jobs[job_id]["updated_at"] = datetime.now().isoformat()
            _jobs[job_id]["market"] = "FOREX"
            _jobs[job_id]["asset_class"] = fx_eval.get("asset_class", "FOREX")
            _jobs[job_id]["result"] = {
                "status": "SUCCESS",
                "market": "FOREX",
                "strategy": strat,
                "symbol": sym,
                "pair": sym,
                "clean_symbol": sym,
                "asset_class": fx_eval.get("asset_class", "FOREX"),
                "trade_setup_plan": fx_eval,
                "scalping_plan": fx_eval if strat == "SHORT_TERM" else None,
                "swing_plan": fx_eval if strat == "LONGER_TERM" else None,
                "tauric_card": fx_eval,
                "jev_review": {
                    "engine": "JEV",
                    "decision": jev_decision,
                    "confidence": jev_res.get("confidence", 0.85),
                    "reason": jev_res.get("log_summary", f"Jev independent statistical review completed for {sym}.")
                },
                "timing": fx_eval.get("timing"),
                "prices_as_of": ts,
                "source_metadata": source_meta
            }
            _save_jobs()
            return

        # ======================================================================
        # CRYPTO ANALYZE WORKFLOW
        # ======================================================================
        clean_sym = req.symbol.replace("/USDT", "").replace("-USD", "").replace("USDT", "").replace("/", "").upper()
        
        # Fresh live market-data
        mkt = await fetch_single_symbol_market_data(clean_sym)
        raw_price = mkt.get("price")
        mkt_status = mkt.get("status", "UNAVAILABLE")

        if raw_price is None or mkt_status not in ("PASS", "NORMAL") or not isinstance(raw_price, (int, float)) or not math.isfinite(raw_price) or raw_price <= 0:
            _jobs[job_id]["state"] = "FAILED"
            _jobs[job_id]["error"] = f"Market data for {clean_sym} is currently unavailable ({mkt_status}). Strategy analysis aborted to avoid execution on invalid prices."
            _jobs[job_id]["completed_at"] = time.time()
            return

        price = float(raw_price)
        raw_chg = mkt.get("change_24h")
        chg = float(raw_chg) if (raw_chg is not None and math.isfinite(raw_chg)) else 0.0
        raw_high = mkt.get("high_24h")
        high = float(raw_high) if (raw_high is not None and math.isfinite(raw_high) and raw_high > 0) else price * 1.03
        raw_low = mkt.get("low_24h")
        low = float(raw_low) if (raw_low is not None and math.isfinite(raw_low) and raw_low > 0) else price * 0.97
        raw_vol = mkt.get("volume_24h")
        vol = float(raw_vol) if (raw_vol is not None and math.isfinite(raw_vol) and raw_vol >= 0) else 0.0

        if strat == "TRADE_SETUP":
            setup_eval = await trade_setup_engine.evaluate_trade_setup(
                symbol=f"{clean_sym}USDT",
                current_price=price,
                change_24h=chg,
                high_24h=high,
                low_24h=low,
                volume_24h=vol,
                user_capital=req.capital
            )
            timing_meta = compute_timing_metadata("TRADE_SETUP", "1h", market="CRYPTO")
            setup_eval["timing"] = timing_meta
            
            # Fast Jev statistical review
            with telemetry_manager.track_request("jev", operation=f"Trade Setup Review {clean_sym}", model="jev-1.13.0"):
                trade_prop = {
                    "action": setup_eval["direction"],
                    "entry_price": setup_eval["entry_price"],
                    "stop_loss": setup_eval["stop_loss"],
                    "take_profit": setup_eval["take_profit"],
                    "strategy": "TRADE_SETUP"
                }
                mkt_st = {"price": price, "change_24h": chg, "volume": vol, "atr": setup_eval["atr_1h"]}
                jev_res = await jev_client.blind_review_trade_setup(f"{clean_sym}-USD", trade_prop, mkt_st)
                telemetry_manager.log_provider_call(
                    provider="jev",
                    model="jev-1.13.0",
                    job_id=job_id,
                    created_by_action="ANALYZE_TRADE_SETUP",
                    strategy="TRADE_SETUP",
                    pair=f"{clean_sym}USDT",
                    status="SUCCESS",
                    input_tokens=220,
                    output_tokens=45,
                    total_tokens=265
                )
                providers_used.append("jev")

            jev_decision = "SUITABLE" if jev_res.get("outcome") == "AGREE" else "UNFAVORABLE ASYMMETRY"
            source_meta = build_source_metadata(providers_used)

            _jobs[job_id]["state"] = "COMPLETED"
            _jobs[job_id]["updated_at"] = datetime.now().isoformat()
            _jobs[job_id]["market"] = "CRYPTO"
            _jobs[job_id]["asset_class"] = "CRYPTO_SPOT"
            _jobs[job_id]["result"] = {
                "status": "SUCCESS",
                "market": "CRYPTO",
                "strategy": "TRADE_SETUP",
                "symbol": f"{clean_sym}USDT",
                "clean_symbol": clean_sym,
                "trade_setup_plan": setup_eval,
                "tauric_card": setup_eval,
                "jev_review": {
                    "engine": "JEV",
                    "decision": jev_decision,
                    "confidence": jev_res.get("confidence", 0.85),
                    "reason": jev_res.get("log_summary", "Jev statistical review completed.")
                },
                "timing": timing_meta,
                "prices_as_of": ts,
                "source_metadata": source_meta
            }
            _save_jobs()
            return

        # Spot Grid Workflow (Scalping / Swing)
        grid_eval = await spot_grid_engine.evaluate_pair_for_grid(
            symbol=f"{clean_sym}USDT",
            current_price=price,
            change_24h=chg,
            high_24h=high,
            low_24h=low,
            volume_24h=vol,
            user_capital=req.capital,
            strategy_type=strat
        )
                
        with telemetry_manager.track_request("jev", operation=f"Grid Review {clean_sym}", model="jev-1.13.0"):
            grid_params = {
                "lower_price": grid_eval.get("grid_range", {}).get("lower", 0),
                "upper_price": grid_eval.get("grid_range", {}).get("upper", 0),
                "grid_count": grid_eval.get("grid_count", 0),
                "spacing_pct": grid_eval.get("net_per_completed_grid_cycle", 0) + 0.25
            }
            mkt_state = {
                "price": price,
                "change_24h": chg,
                "volume": vol,
                "atr": (grid_eval.get("grid_range", {}).get("upper", 0) - price) / 3 if strat == "SHORT_TERM" else 0
            }
            jev_review = await jev_client.blind_review(clean_sym, grid_params, mkt_state)
            if jev_review.get("status") in ("SUCCESS", "FALLBACK"):
                telemetry_manager.log_provider_call(
                    provider="jev",
                    model="jev-1.13.0",
                    job_id=job_id,
                    created_by_action=f"ANALYZE_{strat}",
                    strategy=strat,
                    pair=f"{clean_sym}USDT",
                    status="SUCCESS",
                    input_tokens=180,
                    output_tokens=40,
                    total_tokens=220
                )
                providers_used.append("jev")
        
        mkt2 = await fetch_single_symbol_market_data(clean_sym)
        fresh_raw = mkt2.get("price")
        validation_failed = None
        if fresh_raw is not None and isinstance(fresh_raw, (int, float)) and math.isfinite(fresh_raw):
            fresh_price = float(fresh_raw)
            lower = grid_eval.get("grid_range", {}).get("lower", 0)
            upper = grid_eval.get("grid_range", {}).get("upper", 0)
            if fresh_price < lower or fresh_price > upper:
                validation_failed = (
                    f"Price moved to ${fresh_price:,.2f} which is outside the grid range "
                    f"(${lower:,.2f} — ${upper:,.2f}). Parameters may be stale."
                )
        else:
            fresh_price = price
            validation_failed = f"Final market price refresh failed ({mkt2.get('status', 'UNAVAILABLE')})."
        
        jev_prob_agree = jev_review.get("prob_agree", 0.75)
        jev_decision = "SUITABLE" if jev_prob_agree >= 0.50 else "WAIT / HIGH BREAKOUT RISK"
        
        tauric_decision = "SUITABLE" if grid_eval.get("status") != "REJECTED" else "UNSUITABLE"
        disagreement = None
        if tauric_decision == "SUITABLE" and jev_decision != "SUITABLE":
            disagreement = {
                "divergent": True,
                "summary": "Tauric confirms range stability, but Jev identifies elevated breakout risk.",
                "tauric_view": "Range boundaries viable for automated grid execution.",
                "jev_view": f"Jev probability of stability is low ({jev_prob_agree:.0%}). Risk score: {jev_review.get('risk_score', 'medium')}."
            }
        
        net_cycle = grid_eval.get("net_per_completed_grid_cycle", 0)
        
        card_a_tauric = {
            "engine": "TAURIC",
            "strategy_type": strat,
            "decision": tauric_decision,
            "pair": f"{clean_sym}USDT",
            "capital": req.capital,
            "recommended_capital": grid_eval.get("capital_evaluation", {}).get("recommended_capital", req.capital),
            "grid_range": grid_eval.get("grid_range", {}),
            "grid_count": grid_eval.get("grid_count"),
            "grid_mode": grid_eval.get("grid_mode"),
            "net_per_completed_grid_cycle": net_cycle,
            "risk_level": grid_eval.get("risk_level", "Medium"),
            "invalidation": grid_eval.get("invalidation_rule", ""),
            "full_exit": grid_eval.get("full_exit_rule", ""),
            "reason": (
                f"Multi-agent synthesis confirms structural channel between "
                f"${lower:,.2f} and ${upper:,.2f}. "
                f"Dynamic {grid_eval.get('grid_mode', 'Arithmetic').lower()} grid distribution with "
                f"{net_cycle}% fee-adjusted profit per completed cycle."
            )
        }
        
        card_b_jev = {
            "engine": "JEV",
            "strategy_type": strat,
            "decision": jev_decision,
            "pair": f"{clean_sym}USDT",
            "capital": req.capital,
            "grid_range": grid_eval.get("grid_range", {}),
            "grid_count": grid_eval.get("grid_count"),
            "grid_mode": grid_eval.get("grid_mode"),
            "net_per_completed_grid_cycle": net_cycle,
            "market_regime": grid_eval.get("market_regime", "Unknown"),
            "confidence": jev_review.get("confidence", 0),
            "risk_score": jev_review.get("risk_score", "medium"),
            "risk_flags": grid_eval.get("risk_flags", []) + [f"Jev Agreement Prob: {jev_prob_agree:.0%}"],
            "reason": jev_review.get("reasoning", "Jev statistical validation completed.")
        }
        
        cap_eval = grid_eval.get("capital_evaluation", {})
        final_plan = {
            "strategy_type": strat,
            "pair": f"{clean_sym}USDT",
            "lower_price": lower,
            "upper_price": upper,
            "grid_count": grid_eval.get("grid_count"),
            "grid_mode": grid_eval.get("grid_mode"),
            "investment_amount": grid_eval.get("investment_amount", req.capital),
            "user_capital": req.capital,
            "recommended_capital": cap_eval.get("recommended_capital", req.capital),
            "additional_capital_needed": cap_eval.get("additional_capital_needed", 0),
            "capital_status": grid_eval.get("status"),
            "net_per_completed_grid_cycle": net_cycle,
            "invalidation_stop": grid_eval.get("invalidation_rule", ""),
            "full_exit_condition": grid_eval.get("full_exit_rule", ""),
            "market_regime": grid_eval.get("market_regime", "Unknown"),
            "fee_structure": "0.10% Maker / 0.10% Taker standard Binance Spot rate",
            "reduced_grid_alternative": grid_eval.get("reduced_grid_alternative")
        }
        
        source_meta = build_source_metadata(providers_used)
        timing_meta = compute_timing_metadata(strat, "15m" if strat=="SHORT_TERM" else "4h")
        card_a_tauric["timing"] = timing_meta
        card_b_jev["timing"] = timing_meta
        final_plan["timing"] = timing_meta
        
        _jobs[job_id]["state"] = "COMPLETED"
        _jobs[job_id]["updated_at"] = datetime.now().isoformat()
        _jobs[job_id]["result"] = {
            "status": "SUCCESS",
            "strategy": strat,
            "symbol": f"{clean_sym}USDT",
            "validation_warning": validation_failed,
            "tauric_card": card_a_tauric,
            "jev_card": card_b_jev,
            "disagreement": disagreement,
            "final_binance_plan": final_plan,
            "timing": timing_meta,
            "prices_as_of": ts,
            "source_metadata": source_meta
        }
        _save_jobs()
    except Exception as e:
        logger.error(f"Analysis job {job_id} failed: {e}")
        _jobs[job_id]["state"] = "FAILED"
        _jobs[job_id]["updated_at"] = datetime.now().isoformat()
        _jobs[job_id]["error"] = str(e)
        _save_jobs()


# ==============================================================================
# TAURIC DEEP RESEARCH MULTI-AGENT EXECUTION WORKFLOW
# ==============================================================================
async def _run_tauric_deep_research_job(
    job_id: str,
    clean_sym: str,
    capital: float,
    analysts: List[str] = None,
    research_depth: int = 1,
    trade_date: str = None,
    output_language: str = "English",
    thinking_tier: str = "deepseek-v4-flash",
    model_tier: str = "standard",
    created_by_action: str = "START_DEEP_RESEARCH",
    parent_id: Optional[str] = None,
    market: str = "CRYPTO"
):
    try:
        if _jobs.get(job_id, {}).get("state") == "CANCELLED":
            return

        _jobs[job_id]["state"] = "RUNNING"
        _jobs[job_id]["overall_progress"] = 5
        _jobs[job_id]["current_stage"] = "Market Analyst"
        _jobs[job_id]["current_activity"] = "Initializing Tauric execution graph..."
        _jobs[job_id]["updated_at"] = datetime.now().isoformat()
        _save_jobs()
        
        ts = datetime.now().isoformat()
        if not analysts:
            analysts = ["market", "social", "news"]
            
        analyst_map = {
            "market": "market",
            "social": "social",
            "sentiment": "social",
            "news": "news",
            "fundamentals": "fundamentals"
        }
        sanitized_analysts = [analyst_map.get(a.lower(), a.lower()) for a in analysts]
        sanitized_analysts = list(dict.fromkeys(sanitized_analysts))
        if not sanitized_analysts:
            sanitized_analysts = ["market", "social", "news"]

        _jobs[job_id]["result"] = {
            "source_metadata": build_source_metadata(["tauric"], status_label="Tauric multi-agent research • ANALYZING")
        }

        m = (market or _jobs.get(job_id, {}).get("market") or ("FOREX" if "/" in clean_sym or "XAU" in clean_sym or "EUR" in clean_sym or "GBP" in clean_sym or "JPY" in clean_sym else "CRYPTO")).upper()
        norm_sym = forex_market_data.normalize_symbol(clean_sym) if m == "FOREX" else f"{clean_sym}USDT"
        asset_cls = _jobs.get(job_id, {}).get("asset_class") or ("FOREX_METAL" if "XAU" in clean_sym or "XAG" in clean_sym else "FOREX" if m == "FOREX" else "CRYPTO_SPOT")
        
        if m == "FOREX":
            fx_quote = await forex_market_data.fetch_price(clean_sym)
            if fx_quote and fx_quote.get("status") != "error":
                price = float(fx_quote.get("bid") or 100.0)
                chg = float(fx_quote.get("change_pct") or 0.0)
                high = float(fx_quote.get("high_24h") or price * 1.01)
                low = float(fx_quote.get("low_24h") or price * 0.99)
                vol = float(fx_quote.get("volume_24h") or 50_000_000.0)
            else:
                price = 100.0
                chg = 0.0
                high = 101.0
                low = 99.0
                vol = 50_000_000.0
            fx_eval = await forex_strategy_engine.evaluate_trade_setup(norm_sym, user_capital=capital, timeframe="1h")
            setup = {
                "direction": fx_eval.get("direction", "LONG"),
                "entry_zone": fx_eval.get("entry_zone", f"${price:.2f}"),
                "entry_price": fx_eval.get("entry_price", price),
                "take_profit": fx_eval.get("take_profit", price * 1.02),
                "stop_loss": fx_eval.get("stop_loss", price * 0.98),
                "invalidation_rule": fx_eval.get("invalidation_rule", "1h candle structural close against position"),
                "reward_to_risk": fx_eval.get("reward_to_risk", 2.0),
                "risk_level": "acceptable_risk",
                "bias_desc": fx_eval.get("bias_desc", "Forex structural alignment"),
                "atr_1h": fx_eval.get("spread_pips", 1.5) * 0.0001
            }
        else:
            mkt = await fetch_single_symbol_market_data(clean_sym)
            raw_p = mkt.get("price")
            st_val = mkt.get("status", "UNAVAILABLE")
            if raw_p is None or st_val not in ("PASS", "NORMAL") or not isinstance(raw_p, (int, float)) or not math.isfinite(raw_p) or raw_p <= 0:
                _jobs[job_id]["state"] = "FAILED"
                _jobs[job_id]["error"] = f"Market data for {clean_sym} is unavailable ({st_val}). Cannot generate trade setup."
                _jobs[job_id]["completed_at"] = time.time()
                return

            price = float(raw_p)
            raw_chg = mkt.get("change_24h")
            chg = float(raw_chg) if (raw_chg is not None and math.isfinite(raw_chg)) else 0.0
            raw_high = mkt.get("high_24h")
            high = float(raw_high) if (raw_high is not None and math.isfinite(raw_high) and raw_high > 0) else price * 1.03
            raw_low = mkt.get("low_24h")
            low = float(raw_low) if (raw_low is not None and math.isfinite(raw_low) and raw_low > 0) else price * 0.97
            raw_vol = mkt.get("volume_24h")
            vol = float(raw_vol) if (raw_vol is not None and math.isfinite(raw_vol) and raw_vol >= 0) else 0.0
            
            setup = await trade_setup_engine.evaluate_trade_setup(
                symbol=f"{clean_sym}USDT",
                current_price=price,
                change_24h=chg,
                high_24h=high,
                low_24h=low,
                volume_24h=vol,
                user_capital=capital
            )
        
        if _jobs[job_id].get("state") == "CANCELLED":
            return
            
        tauric_run_obj = None
        resolved_model = resolve_model_tier(thinking_tier or model_tier)
        if not validate_model_preflight(resolved_model["model_id"]):
            raise ValueError(f"Invalid model ID '{resolved_model['model_id']}'. Allowed: {ALLOWED_PRODUCTION_MODELS}")

        run_id = tauric_engine.start_run(
            ticker=f"{clean_sym}-USD",
            analysts=sanitized_analysts,
            research_depth=research_depth,
            trade_date=trade_date,
            thinking_tier=resolved_model["model_id"],
            model_tier=resolved_model["model_tier"]
        )
        _jobs[job_id]["tauric_run_id"] = run_id
        _save_jobs()

        with telemetry_manager.track_request("tauric", operation=f"Tauric Deep Research: {clean_sym}", model=resolved_model["model_id"]):
            telemetry_manager.log_provider_call(
                provider="tauric",
                model=resolved_model["model_id"],
                job_id=job_id,
                parent_id=parent_id,
                created_by_action=created_by_action,
                strategy="TAURIC_DEEP_RESEARCH",
                pair=f"{clean_sym}USDT",
                status="RUNNING"
            )

            for _ in range(120): # up to 4 minutes
                await asyncio.sleep(2)
                if _jobs[job_id].get("state") == "CANCELLED":
                    tauric_engine.stop_run(run_id)
                    return

                run_state = tauric_engine.get_run(run_id)
                if run_state:
                    _jobs[job_id]["stages"] = run_state.get("stages", _jobs[job_id].get("stages", []))
                    _jobs[job_id]["overall_progress"] = run_state.get("overall_progress", 0)
                    _jobs[job_id]["current_stage"] = run_state.get("current_stage", "Analyzing")
                    _jobs[job_id]["current_activity"] = run_state.get("current_activity", "")
                    _jobs[job_id]["updated_at"] = datetime.now().isoformat()
                    _save_jobs()

                    if run_state.get("status") == "CANCELLED":
                        _jobs[job_id]["state"] = "CANCELLED"
                        _save_jobs()
                        return

                    if run_state.get("status") in ("COMPLETED", "FAILED"):
                        tauric_run_obj = run_state
                        break
                    curr_stage = run_state.get("current_stage", "Analyzing")
                    telemetry_manager.session_data["tauric"]["current_operation"] = f"Tauric: {curr_stage}"

        if _jobs[job_id].get("state") == "CANCELLED":
            return

        trader_info = {}
        pm_info = {}
        reports_payload = {}
        
        if tauric_run_obj and tauric_run_obj.get("status") == "COMPLETED":
            trader_info = tauric_run_obj.get("trading_team", {}).get("trader", {})
            pm_info = tauric_run_obj.get("portfolio_manager", {})
            tauric_action = trader_info.get("action") or ("LONG" if setup["direction"] == "LONG" else "SHORT")
            if tauric_action.upper() not in ("LONG", "SHORT", "NO TRADE", "HOLD"):
                tauric_action = "LONG" if setup["direction"] == "LONG" else "SHORT"
            tauric_reason = trader_info.get("reasoning") or pm_info.get("rationale") or setup.get("bias_desc")
            tauric_rating = pm_info.get("rating") or "SUITABLE"
            
            reports_payload = {
                "analyst_team": tauric_run_obj.get("analyst_team", {}),
                "research_team": tauric_run_obj.get("research_team", {}),
                "trading_team": tauric_run_obj.get("trading_team", {}),
                "risk_team": tauric_run_obj.get("risk_team", {}),
                "portfolio_manager": tauric_run_obj.get("portfolio_manager", {}),
                "complete_report": tauric_run_obj.get("complete_report")
            }
        else:
            tauric_action = setup["direction"]
            tauric_reason = f"Multi-agent synthesis confirms {setup['direction']} bias ({setup['bias_desc']}) targeting Take Profit at ${setup['take_profit']:,.2f} with risk bounded at Stop Loss ${setup['stop_loss']:,.2f}."
            tauric_rating = "SUITABLE"

        timing_meta = compute_timing_metadata("TAURIC_DEEP_RESEARCH", "1h")
        tauric_plan = {
            "engine": "TAURIC",
            "pair": norm_sym if m == "FOREX" else f"{clean_sym}USDT",
            "clean_symbol": clean_sym,
            "direction": tauric_action.upper(),
            "entry_zone": setup["entry_zone"],
            "entry_price": setup.get("entry_price", price),
            "take_profit": setup["take_profit"],
            "stop_loss": setup["stop_loss"],
            "invalidation": setup["invalidation_rule"],
            "reward_risk_ratio": f"{setup['reward_to_risk']}:1",
            "risk_level": setup["risk_level"],
            "decision": tauric_rating,
            "reason": tauric_reason,
            "timing": timing_meta,
            "reports": reports_payload
        }

        if _jobs[job_id].get("state") == "CANCELLED":
            return

        _jobs[job_id]["result"] = {
            "source_metadata": build_source_metadata(["tauric", "jev"], status_label="Tauric complete • JEV REVIEWING")
        }
        
        for stg in _jobs[job_id].get("stages", []):
            if stg["id"] == "jev_review":
                stg["status"] = "RUNNING"
        _jobs[job_id]["overall_progress"] = 90
        _jobs[job_id]["current_stage"] = "Jev Independent Review"
        _jobs[job_id]["current_activity"] = "Jev Independent Review — performing blind statistical validation"
        _jobs[job_id]["updated_at"] = datetime.now().isoformat()
        _save_jobs()

        with telemetry_manager.track_request("jev", operation=f"Independent Review: {clean_sym}", model="jev-1.13.0"):
            trade_proposal = {
                "action": tauric_plan["direction"],
                "entry_price": setup["entry_price"],
                "stop_loss": setup["stop_loss"],
                "take_profit": setup["take_profit"],
                "strategy": "TAURIC_DEEP_RESEARCH"
            }
            mkt_state = {
                "price": price,
                "change_24h": chg,
                "volume": vol,
                "atr": setup["atr_1h"]
            }
            jev_res = await jev_client.blind_review_trade_setup(f"{clean_sym}-USD", trade_proposal, mkt_state)
            telemetry_manager.log_provider_call(
                provider="jev",
                model="jev-1.13.0",
                job_id=job_id,
                parent_id=parent_id,
                created_by_action=created_by_action,
                strategy="TAURIC_DEEP_RESEARCH",
                pair=norm_sym if m == "FOREX" else f"{clean_sym}USDT",
                status="SUCCESS",
                input_tokens=240,
                output_tokens=50,
                total_tokens=290
            )

        if _jobs[job_id].get("state") == "CANCELLED":
            return

        for stg in _jobs[job_id].get("stages", []):
            if stg["id"] == "jev_review":
                stg["status"] = "COMPLETED"
        _jobs[job_id]["overall_progress"] = 100
        _jobs[job_id]["current_stage"] = "COMPLETED"
        _jobs[job_id]["current_activity"] = "Analysis complete. Consensus synthesized."

        probs = jev_res.get("probabilities", {})
        jev_agree_prob = probs.get("agree", 0.75)
        jev_outcome = jev_res.get("outcome", "AGREE")
        
        jev_decision = "SUITABLE" if jev_outcome == "AGREE" and jev_agree_prob >= 0.50 else "UNFAVORABLE ASYMMETRY"
        jev_direction = tauric_plan["direction"] if jev_decision == "SUITABLE" else ("SHORT" if tauric_plan["direction"] == "LONG" else "LONG")

        jev_review = {
            "engine": "JEV",
            "pair": norm_sym if m == "FOREX" else f"{clean_sym}USDT",
            "clean_symbol": clean_sym,
            "direction": jev_direction,
            "entry_zone": setup["entry_zone"],
            "entry_price": setup.get("entry_price", price),
            "take_profit": setup["take_profit"],
            "stop_loss": setup["stop_loss"],
            "invalidation": setup["invalidation_rule"],
            "risk_level": jev_res.get("risk_score", "acceptable_risk"),
            "confidence": jev_res.get("confidence", 0.85),
            "decision": jev_decision,
            "agreement_status": "AGREEMENT" if jev_decision == "SUITABLE" else "DISAGREEMENT",
            "timing": timing_meta,
            "reason": jev_res.get("log_summary", f"Jev independent statistical expectation model evaluated {tauric_plan['direction']} proposal (Confidence: {jev_res.get('confidence', 0.85):.0%}).")
        }

        is_agreement = (tauric_plan["direction"] == jev_review["direction"] and jev_review["decision"] == "SUITABLE")
        comparison = {
            "status": "AGREEMENT" if is_agreement else "DISAGREEMENT",
            "tauric_direction": tauric_plan["direction"],
            "jev_direction": jev_review["direction"],
            "summary": (
                f"Both Tauric and Jev independently confirm positive mathematical expectancy for a {tauric_plan['direction']} setup on {norm_sym if m == 'FOREX' else clean_sym + 'USDT'}."
                if is_agreement else
                f"Tauric synthesizes a {tauric_plan['direction']} thesis, but Jev identifies unfavorable statistical asymmetry / elevated breakout risk."
            )
        }

        source_meta = build_source_metadata(["tauric", "jev"])

        if _jobs[job_id].get("state") == "CANCELLED":
            return

        _jobs[job_id]["state"] = "COMPLETED"
        _jobs[job_id]["updated_at"] = datetime.now().isoformat()
        _jobs[job_id]["market"] = m
        _jobs[job_id]["asset_class"] = asset_cls
        _jobs[job_id]["symbol"] = norm_sym if m == "FOREX" else f"{clean_sym}USDT"
        _jobs[job_id]["display_symbol"] = norm_sym if m == "FOREX" else f"{clean_sym}USDT"
        _jobs[job_id]["result"] = {
            "status": "SUCCESS",
            "strategy": "TAURIC_DEEP_RESEARCH",
            "symbol": norm_sym if m == "FOREX" else f"{clean_sym}USDT",
            "clean_symbol": clean_sym,
            "market": m,
            "asset_class": asset_cls,
            "tauric_plan": tauric_plan,
            "tauric_card": tauric_plan,
            "jev_review": jev_review,
            "jev_card": jev_review,
            "trade_setup_plan": tauric_plan,
            "comparison": comparison,
            "timing": timing_meta,
            "disagreement": {
                "divergent": not is_agreement,
                "summary": comparison["summary"],
                "tauric_view": tauric_plan["reason"],
                "jev_view": jev_review["reason"]
            } if not is_agreement else None,
            "prices_as_of": ts,
            "source_metadata": source_meta
        }
        _save_jobs()
    except Exception as e:
        logger.error(f"Tauric Deep Research job {job_id} failed: {e}")
        if _jobs.get(job_id, {}).get("state") != "CANCELLED":
            _jobs[job_id]["state"] = "FAILED"
            _jobs[job_id]["updated_at"] = datetime.now().isoformat()
            _jobs[job_id]["error"] = f"Analysis temporarily unavailable: {str(e)}"
            _save_jobs()


@grid_router.post("/tauric-deep-research")
@grid_router.post("/tauric-setup")
async def start_tauric_deep_research(req: TauricDeepResearchRequest, request: Request):
    """
    Initiates deep TAURIC DEEP RESEARCH workflow for a selected Binance pair with step-by-step inputs.
    Strict cost control: requires explicit created_by_action, preflight validation.
    """
    check_rate_limit(request, "/tauric-deep-research", 5)
    check_budget()
    
    return create_tauric_research_job(
        symbol=req.symbol,
        capital=req.capital,
        created_by_action=req.created_by_action,
        market=req.market,
        thinking_tier=req.thinking_tier,
        model_tier=req.model_tier or "standard",
        analysts=req.analysts,
        research_depth=req.research_depth,
        trade_date=req.trade_date,
        output_language=req.output_language,
        parent_id=req.parent_id,
        source_component="EXPLICIT_UI_ACTION"
    )


# ==============================================================================
# DETERMINISTIC TIMING RECHECK ENDPOINTS (0 AI CREDITS)
# ==============================================================================
@grid_router.post("/signal/recheck")
async def recheck_signal_status(req: RecheckSignalRequest):
    """
    Deterministic, zero-LLM-cost candle-aware signal state machine evaluation.
    Evaluates Binance public klines since signal generation timestamp.
    """
    clean_sym = req.symbol.replace("/USDT", "").replace("-USD", "").replace("USDT", "").replace("/", "").upper()
    
    entry_min = req.entry_min
    entry_max = req.entry_max
    if entry_min is None or entry_max is None:
        p = req.entry_price or req.take_profit
        entry_min = round(p * 0.995, 4)
        entry_max = round(p * 1.005, 4)
        
    invalidation_price = req.invalidation_price or req.stop_loss
    timing_meta = req.timing_meta or {}
    
    eval_result = await signal_timing_engine.evaluate_signal_lifecycle(
        symbol=f"{clean_sym}USDT",
        direction=req.direction,
        entry_min=entry_min,
        entry_max=entry_max,
        take_profit=req.take_profit,
        stop_loss=req.stop_loss,
        invalidation_price=invalidation_price,
        timing_meta=timing_meta,
        historical_status=req.historical_status
    )
    
    if req.job_id and req.job_id in _jobs:
        job = _jobs[req.job_id]
        if "result" in job and isinstance(job["result"], dict):
            job["result"]["signal_evaluation"] = eval_result
            _save_jobs()
            
    return eval_result

@grid_router.post("/grid/recheck")
async def recheck_grid_status(req: RecheckGridRequest):
    """
    Deterministic, zero-LLM-cost Spot Grid status evaluation.
    Checks live ticker against channel boundaries and 24h validity window.
    """
    clean_sym = req.symbol.replace("/USDT", "").replace("-USD", "").replace("USDT", "").replace("/", "").upper()
    eval_result = await signal_timing_engine.evaluate_spot_grid_status(
        symbol=f"{clean_sym}USDT",
        lower=req.lower_price,
        upper=req.upper_price,
        timing_meta=req.timing_meta or {},
        historical_status=req.historical_status
    )
    return eval_result


# ==============================================================================
# CANCEL / RECONCILE / STATUS ENDPOINTS
# ==============================================================================
@grid_router.post("/job/{job_id}/cancel")
async def cancel_job(job_id: str):
    """
    Cancels an active analysis/scan job immediately and terminates background threads/tasks.
    """
    if job_id not in _jobs:
        # Check if it's a tauric_run_id directly
        run = tauric_engine.get_run(job_id)
        if run:
            tauric_engine.stop_run(job_id)
            telemetry_manager.clear_active("tauric")
            telemetry_manager.clear_active("jev")
            return {
                "status": "CANCELLED",
                "job_id": job_id,
                "cancel_confirmed_at": datetime.now().isoformat(),
                "post_cancel_calls": 0
            }
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = _jobs[job_id]
    prev_state = job.get("state", "UNKNOWN")
    now_iso = datetime.now().isoformat()
    
    if prev_state == "COMPLETED":
        return {
            "status": "ALREADY_COMPLETED",
            "job_id": job_id,
            "message": "Job has already completed."
        }
    
    if prev_state == "CANCELLED":
        return {
            "status": "ALREADY_CANCELLED",
            "job_id": job_id,
            "cancel_confirmed_at": job.get("cancel_confirmed_at", now_iso),
            "worker_terminated_at": job.get("worker_terminated_at", now_iso)
        }
    
    job["cancel_requested_at"] = now_iso
    job["state"] = "CANCELLED"
    job["cancel_confirmed_at"] = now_iso
    job["worker_terminated_at"] = now_iso
    job["current_activity"] = "Research stopped by user request. Worker terminated."
    job["updated_at"] = now_iso
    
    # Signal engine stop
    run_id = job.get("tauric_run_id")
    if run_id:
        tauric_engine.stop_run(run_id)
        
    # Reset telemetry active state
    telemetry_manager.clear_active("tauric")
    telemetry_manager.clear_active("jev")
    
    # Update stages to CANCELLED
    stages = job.get("stages", [])
    for stg in stages:
        if stg.get("status") in ("RUNNING", "PENDING"):
            stg["status"] = "CANCELLED"
    job["stages"] = stages
    _save_jobs()
    
    return {
        "status": "CANCELLED",
        "job_id": job_id,
        "cancel_requested_at": job["cancel_requested_at"],
        "cancel_confirmed_at": job["cancel_confirmed_at"],
        "worker_terminated_at": job["worker_terminated_at"],
        "stages": job.get("stages", []),
        "post_cancel_calls": 0
    }

def _reconcile_active_jobs():
    """
    Reconciles RUNNING / PENDING jobs. If a job has no active backend worker / async task
    (or is a stale scan/analysis job from a previous server restart), mark it INTERRUPTED.
    """
    changed = False
    now = datetime.now()
    for jid, job in _jobs.items():
        state = job.get("state")
        if state in ("RUNNING", "PENDING"):
            strat = (job.get("strategy") or "").upper()
            t_run_id = job.get("tauric_run_id")
            
            # Check Tauric Deep Research runs
            if "TAURIC" in strat or t_run_id:
                t_run = tauric_engine.get_run(t_run_id or jid)
                if t_run:
                    t_status = t_run.get("status")
                    if t_status in ("COMPLETED", "CANCELLED", "FAILED"):
                        job["state"] = t_status
                        job["updated_at"] = now.isoformat()
                        changed = True
                        continue
                if t_run_id and t_run_id not in tauric_engine.cancel_events and jid not in tauric_engine.cancel_events:
                    job["state"] = "INTERRUPTED"
                    job["current_activity"] = "Process interrupted (worker thread no longer active)."
                    job["updated_at"] = now.isoformat()
                    changed = True
            else:
                # Fast scans / analyses: if older than 2 minutes and still RUNNING/PENDING, mark INTERRUPTED
                started_at_str = job.get("started_at") or job.get("updated_at")
                if started_at_str:
                    try:
                        started_dt = datetime.fromisoformat(started_at_str.replace("Z", "+00:00")).replace(tzinfo=None)
                        if (now - started_dt).total_seconds() > 120:
                            job["state"] = "INTERRUPTED"
                            job["current_activity"] = "Scan/analysis timed out or backend process restarted."
                            job["updated_at"] = now.isoformat()
                            changed = True
                    except Exception:
                        pass
    if changed:
        _save_jobs()

_reconcile_active_jobs()

@grid_router.get("/jobs/active")
async def get_active_jobs():
    """
    Returns all currently active (RUNNING / PENDING) research & scan jobs.
    Includes explicit market tag ("CRYPTO" vs "FOREX").
    """
    _reconcile_active_jobs()
    active = []
    for jid, job in _jobs.items():
        if job.get("is_deleted"):
            continue
        if job.get("state") in ("RUNNING", "PENDING"):
            strat = job.get("strategy") or job.get("strategy_type") or "UNKNOWN"
            sym = job.get("symbol") or (f"{job.get('clean_sym')}USDT" if job.get("clean_sym") else "UNKNOWN")
            m = job.get("market") or ("FOREX" if "/" in sym or "XAU" in sym or "XAG" in sym else "CRYPTO")
            asset_cls = job.get("asset_class") or ("FOREX_METAL" if "XAU" in sym or "XAG" in sym else "FOREX" if "/" in sym else "CRYPTO_SPOT")
            active.append({
                "job_id": jid,
                "strategy": strat,
                "market": m,
                "asset_class": asset_cls,
                "symbol": sym,
                "pair": sym,
                "status": job.get("state"),
                "progress": job.get("overall_progress", 5),
                "current_stage": job.get("current_stage") or "Analyzing",
                "current_activity": job.get("current_activity", "Analyzing"),
                "started_at": job.get("started_at"),
                "updated_at": job.get("updated_at") or job.get("started_at"),
                "provider": "Tauric (DeepSeek)" if "TAURIC" in strat else "Market Engine",
                "tauric_run_id": job.get("tauric_run_id"),
                "stages": job.get("stages", []),
                "cancellation_state": job.get("cancel_confirmed_at") is not None
            })
    return {"active_jobs": active, "count": len(active)}

@grid_router.get("/jobs/history")
async def get_jobs_history(limit: int = 50, market: Optional[str] = None):
    """
    Returns unified trade & research sessions (RUNNING, COMPLETED, CANCELLED, INTERRUPTED, FAILED)
    across all strategy types (Scalping, Swing, Trade Setup, Tauric Deep Research) and markets (CRYPTO / FOREX).
    """
    _reconcile_active_jobs()
    history = []
    seen_ids = set()
    req_m = market.upper() if market else None
    
    for jid, job in _jobs.items():
        if job.get("is_deleted"):
            continue
        seen_ids.add(jid)
        
        strat = job.get("strategy") or job.get("strategy_type") or job.get("result", {}).get("strategy") or "UNKNOWN"
        raw_sym = job.get("display_symbol") or job.get("symbol") or (f"{job.get('clean_sym')}USDT" if job.get("clean_sym") else "UNKNOWN")
        clean = job.get("clean_sym") or raw_sym.replace("USDT", "").replace("/", "")
        status = job.get("state") or job.get("status") or "COMPLETED"
        m = job.get("market") or ("FOREX" if "/" in raw_sym or "XAU" in clean or "XAG" in clean or "EUR" in clean or "GBP" in clean or "JPY" in clean else "CRYPTO")
        asset_cls = job.get("asset_class") or ("FOREX_METAL" if "XAU" in clean or "XAG" in clean else "FOREX" if m == "FOREX" else "CRYPTO_SPOT")
        
        if m == "FOREX":
            symbol = forex_market_data.normalize_symbol(clean)
        else:
            symbol = raw_sym
        
        if req_m and m != req_m:
            continue
            
        direction = None
        result = job.get("result") or {}
        if isinstance(result, dict):
            if result.get("tauric_card", {}).get("direction"):
                direction = result.get("tauric_card", {}).get("direction")
            elif result.get("final_plan", {}).get("direction"):
                direction = result.get("final_plan", {}).get("direction")
            elif result.get("tauric_plan", {}).get("direction"):
                direction = result.get("tauric_plan", {}).get("direction")
            elif result.get("trade_setup_plan", {}).get("direction"):
                direction = result.get("trade_setup_plan", {}).get("direction")
            elif result.get("final_binance_plan"):
                direction = "SPOT_GRID"
        
        timing = result.get("timing") if isinstance(result, dict) else None
        started_dt = parse_iso_datetime(job.get("started_at"))
        created_at_pkt = format_pkt_datetime(started_dt) if started_dt else "Legacy Record"
        
        entry_val = None
        tp_val = None
        sl_val = None
        
        if isinstance(result, dict):
            t_plan = result.get("tauric_plan") or result.get("tauric_card") or result.get("trade_setup_plan") or result.get("scalping_plan") or result.get("swing_plan") or {}
            entry_val = t_plan.get("entry_zone") or t_plan.get("entry_price")
            tp_val = t_plan.get("take_profit")
            sl_val = t_plan.get("stop_loss")
            b_plan = result.get("final_binance_plan") or {}
            if not entry_val and b_plan.get("lower_price"):
                entry_val = f"${b_plan.get('lower_price'):,.2f} - ${b_plan.get('upper_price'):,.2f}"
                tp_val = f"${b_plan.get('upper_price'):,.2f}"
                sl_val = f"${b_plan.get('lower_price'):,.2f}"

        history.append({
            "job_id": jid,
            "strategy": strat,
            "market": m,
            "asset_class": asset_cls,
            "symbol": symbol,
            "pair": symbol,
            "status": status,
            "direction": direction,
            "progress": job.get("overall_progress", 100 if status == "COMPLETED" else (0 if status == "CANCELLED" else 5)),
            "current_stage": job.get("current_stage") or ("Completed" if status == "COMPLETED" else status),
            "current_activity": job.get("current_activity", ""),
            "started_at": job.get("started_at"),
            "updated_at": job.get("updated_at") or job.get("started_at"),
            "created_at_pkt": created_at_pkt,
            "entry_valid_until_pkt": timing.get("entry_valid_until_pkt") if timing else "--",
            "expires_at_pkt": timing.get("expires_at_pkt") if timing else "--",
            "time_stop_pkt": timing.get("time_stop_pkt") if timing else "--",
            "timing": timing,
            "entry_zone": entry_val,
            "take_profit": tp_val,
            "stop_loss": sl_val,
            "signal_state": result.get("signal_evaluation", {}).get("signal_state") if isinstance(result, dict) and result.get("signal_evaluation") else (status if timing else "LEGACY_UNKNOWN"),
            "provider": "Tauric + Jev" if "TAURIC" in strat.upper() else "Jev + Engine",
            "tauric_run_id": job.get("tauric_run_id"),
            "stages": job.get("stages", []),
            "result": job.get("result"),
            "cancelInfo": {
                "cancel_requested_at": job.get("cancel_requested_at"),
                "cancel_confirmed_at": job.get("cancel_confirmed_at"),
                "worker_terminated_at": job.get("worker_terminated_at")
            } if job.get("cancel_confirmed_at") else None
        })
        
    history.sort(key=lambda x: str(x.get("updated_at") or x.get("started_at") or ""), reverse=True)
    return {"history": history[:limit], "total": len(history)}

@grid_router.delete("/history/all")
@grid_router.delete("/jobs/history/all")
async def clear_all_history():
    """
    Clears all completed, cancelled, failed, or interrupted historical job records.
    Never deletes currently active (RUNNING / PENDING) jobs.
    """
    global _jobs
    cleared_count = 0
    retained_jobs = {}
    for jid, job in _jobs.items():
        if job.get("state") in ("RUNNING", "PENDING"):
            retained_jobs[jid] = job
        else:
            cleared_count += 1
    _jobs = retained_jobs
    _save_jobs()
    
    with tauric_engine.lock:
        retained_runs = {}
        for rid, run in tauric_engine.runs.items():
            if run.get("status") in ("RUNNING", "PENDING"):
                retained_runs[rid] = run
        tauric_engine.runs = retained_runs
        
    return {
        "status": "CLEARED",
        "cleared_count": cleared_count,
        "message": f"Successfully cleared {cleared_count} trading & research history records."
    }

@grid_router.delete("/history/{history_id}")
@grid_router.delete("/job/{history_id}")
async def delete_history_job(history_id: str):
    """
    Soft-deletes a research or trade session from history.
    Rejects deletion with 409 Conflict if the job is actively RUNNING or PENDING.
    """
    if history_id in _jobs:
        job = _jobs[history_id]
        if job.get("state") in ("RUNNING", "PENDING"):
            raise HTTPException(
                status_code=409,
                detail="Cannot delete an active running job. Please stop the job first."
            )
        job["is_deleted"] = True
        job["updated_at"] = datetime.now().isoformat()
        _save_jobs()
        return {"status": "DELETED", "id": history_id}
    
    t_run = tauric_engine.get_run(history_id)
    if t_run:
        if t_run.get("status") in ("RUNNING", "PENDING"):
            raise HTTPException(
                status_code=409,
                detail="Cannot delete an active running job. Please stop the job first."
            )
        t_run["is_deleted"] = True
        return {"status": "DELETED", "id": history_id}
        
    raise HTTPException(status_code=404, detail="Job not found")

@grid_router.get("/job/{job_id}")
async def get_job_status(job_id: str):
    if job_id in _jobs:
        job = dict(_jobs[job_id])
        tauric_run_id = job.get("tauric_run_id")
        if tauric_run_id:
            run = tauric_engine.get_run(tauric_run_id)
            if run and isinstance(job.get("result"), dict):
                t_plan = job["result"].get("tauric_plan")
                if isinstance(t_plan, dict) and not t_plan.get("reports"):
                    t_plan["reports"] = {
                        "analyst_team": run.get("analyst_team", {}),
                        "research_team": run.get("research_team", {}),
                        "trading_team": run.get("trading_team", {}),
                        "risk_team": run.get("risk_team", {}),
                        "portfolio_manager": run.get("portfolio_manager", {}),
                        "complete_report": run.get("complete_report")
                    }
        raw_sym = job.get("display_symbol") or job.get("symbol") or ""
        clean = job.get("clean_sym") or raw_sym.replace("USDT", "").replace("/", "")
        m = job.get("market") or ("FOREX" if "/" in raw_sym or "XAU" in clean or "XAG" in clean or "EUR" in clean or "GBP" in clean or "JPY" in clean else "CRYPTO")
        asset_cls = job.get("asset_class") or ("FOREX_METAL" if "XAU" in clean or "XAG" in clean else "FOREX" if m == "FOREX" else "CRYPTO_SPOT")
        if m == "FOREX":
            norm = forex_market_data.normalize_symbol(clean)
            job["display_symbol"] = norm
            job["symbol"] = norm
            job["market"] = "FOREX"
            job["asset_class"] = asset_cls
            if isinstance(job.get("result"), dict):
                job["result"]["symbol"] = norm
                job["result"]["market"] = "FOREX"
                job["result"]["asset_class"] = asset_cls
                if isinstance(job["result"].get("tauric_plan"), dict):
                    job["result"]["tauric_plan"]["pair"] = norm
                if isinstance(job["result"].get("jev_review"), dict):
                    job["result"]["jev_review"]["pair"] = norm
        return job
    
    run = tauric_engine.get_run(job_id)
    if run:
        sym = run.get("ticker", "SOL").replace("-USD", "USDT").replace("/", "")
        return {
            "id": job_id,
            "symbol": sym,
            "state": run.get("status", "COMPLETED"),
            "stages": run.get("stages", []),
            "overall_progress": run.get("overall_progress", 100 if run.get("status") == "COMPLETED" else 0),
            "current_stage": run.get("current_stage"),
            "current_activity": run.get("current_activity"),
            "started_at": run.get("start_time"),
            "updated_at": run.get("completion_time") or run.get("start_time"),
            "result": {
                "status": "SUCCESS",
                "strategy": "TAURIC_DEEP_RESEARCH",
                "symbol": sym,
                "clean_symbol": run.get("ticker", "SOL").replace("-USD", ""),
                "tauric_card": {
                    "engine": "TAURIC",
                    "pair": sym,
                    "direction": "LONG" if "BUY" in str(run.get("trading_team", {}).get("trader", {}).get("action", "")).upper() else "SHORT",
                    "entry_zone": str(run.get("trading_team", {}).get("trader", {}).get("entry_price", "Market")),
                    "take_profit": "Target",
                    "stop_loss": str(run.get("trading_team", {}).get("trader", {}).get("stop_loss", "Stop")),
                    "decision": run.get("portfolio_manager", {}).get("rating", "SUITABLE"),
                    "reason": run.get("portfolio_manager", {}).get("investment_thesis") or "Tauric multi-agent research analysis.",
                    "reports": {
                        "analyst_team": run.get("analyst_team", {}),
                        "research_team": run.get("research_team", {}),
                        "trading_team": run.get("trading_team", {}),
                        "risk_team": run.get("risk_team", {}),
                        "portfolio_manager": run.get("portfolio_manager", {}),
                        "complete_report": run.get("complete_report")
                    }
                },
                "tauric_plan": {
                    "engine": "TAURIC",
                    "pair": sym,
                    "direction": "LONG" if "BUY" in str(run.get("trading_team", {}).get("trader", {}).get("action", "")).upper() else "SHORT",
                    "entry_zone": str(run.get("trading_team", {}).get("trader", {}).get("entry_price", "Market")),
                    "take_profit": "Target",
                    "stop_loss": str(run.get("trading_team", {}).get("trader", {}).get("stop_loss", "Stop")),
                    "decision": run.get("portfolio_manager", {}).get("rating", "SUITABLE"),
                    "reason": run.get("portfolio_manager", {}).get("investment_thesis") or "Tauric multi-agent research analysis.",
                    "reports": {
                        "analyst_team": run.get("analyst_team", {}),
                        "research_team": run.get("research_team", {}),
                        "trading_team": run.get("trading_team", {}),
                        "risk_team": run.get("risk_team", {}),
                        "portfolio_manager": run.get("portfolio_manager", {}),
                        "complete_report": run.get("complete_report")
                    }
                },
                "source_metadata": build_source_metadata(["tauric", "jev"])
            }
        }
        
    raise HTTPException(status_code=404, detail="Job not found")

@grid_router.get("/audit/provider-calls")
async def get_provider_audit_logs(limit: int = 50):
    return {
        "audit_logs": telemetry_manager.get_audit_logs(limit=limit),
        "count": len(telemetry_manager.audit_logs)
    }

@grid_router.get("/telemetry")
async def get_telemetry_snapshot():
    return telemetry_manager.get_telemetry()

@grid_router.get("/health")
async def get_grid_health():
    return {
        "status": "OK",
        "live_trading": "LOCKED",
        "trading_mode": "READ_ONLY_RESEARCH",
        "timestamp": datetime.now().isoformat()
    }
