import asyncio
import time
import json
import httpx
from datetime import datetime

from app.services.telemetry_manager import telemetry_manager
from app.services.jev_client import jev_client
from app.services.market_data import fetch_live_market_data
from app.services.spot_grid_engine import spot_grid_engine

async def detailed_step_trace():
    print("=" * 80)
    print("FORENSIC TRACE OF SCAN PIPELINE:", datetime.now().isoformat())
    print("=" * 80)
    
    # 1. Step 0: Binance live market data
    t0 = time.time()
    mkts = await fetch_live_market_data()
    t_mkt = time.time() - t0
    print("\n[STEP 0] Binance Market Data Fetch:")
    print("  Provider: Binance Public API (https://api.binance.com/api/v3/ticker/24hr)")
    print(f"  Duration: {t_mkt*1000:.1f}ms")
    print(f"  Tokens Consumed: 0 (Public REST API)")
    print(f"  Symbols received: {list(mkts.keys())}")
    
    # 2. Step 1 & 2: Deterministic Engine Evaluations
    t0 = time.time()
    evaluated = []
    target_pairs = ["SOL", "ETH", "BTC", "BNB", "ADA", "AVAX", "DOGE"]
    for sym in target_pairs:
        p_data = mkts.get(sym, {})
        res = await spot_grid_engine.evaluate_pair_for_grid(
            symbol=f"{sym}USDT",
            current_price=p_data.get("price", 100.0),
            change_24h=p_data.get("change_24h", 0.0),
            high_24h=p_data.get("high_24h", 103.0),
            low_24h=p_data.get("low_24h", 97.0),
            volume_24h=p_data.get("volume_24h", 20000000),
            user_capital=100.0,
            strategy_type="LONGER_TERM"
        )
        if res.get("status") != "REJECTED":
            evaluated.append(res)
    t_engine = time.time() - t0
    print("\n[STEP 1 & 2] Deterministic Engine Evaluations:")
    print("  Provider: Local SpotGridEngine + Binance klines & exchangeInfo REST calls")
    print(f"  Duration: {t_engine*1000:.1f}ms")
    print(f"  Tokens Consumed: 0 (Deterministic Math & Binance REST)")
    print(f"  Candidates passed Gate 0 & Cost Floor: {len(evaluated)}")
    for e in evaluated[:4]:
        sym_name = e.get('symbol')
        gc = e.get('grid_count')
        net = e.get('net_per_completed_grid_cycle')
        st = e.get('status')
        print(f"    - {sym_name}: Grids={gc}, Net/Cycle={net}%, Status={st}")
        
    # 3. Step 3: Jev Batch Fast Screening Call
    print("\n[STEP 3] Jev Batch Fast Screening Call:")
    t0 = time.time()
    jev_tel_before = telemetry_manager.get_telemetry()["jev"]
    print(f"  Jev Telemetry Before: Reqs={jev_tel_before['request_count']}, KnownTokens={jev_tel_before['known_tokens']}")
    
    with telemetry_manager.track_request("jev", operation="Batch Fast Screening"):
        jev_res = await jev_client.batch_fast_screening(evaluated)
        
    t_jev = time.time() - t0
    jev_tel_after = telemetry_manager.get_telemetry()["jev"]
    print(f"  Endpoint Called: {jev_client.endpoint}")
    print(f"  Model: {jev_res.get('model', jev_client.model)}")
    print(f"  Duration: {t_jev*1000:.1f}ms")
    print(f"  Jev Response Status: {jev_res.get('status')}")
    print(f"  Jev Answers: {json.dumps(jev_res.get('answers'), indent=2)}")
    print(f"  Jev Telemetry After: Reqs={jev_tel_after['request_count']}, KnownTokens={jev_tel_after['known_tokens']}, TokensDisplay={jev_tel_after['tokens_display']}")
    
    # 4. Step 4: Tauric / Venice Call check
    print("\n[STEP 4] Tauric / Venice LLM Call Check:")
    print("  Was Tauric/DeepSeek called during /scan? NO (Stage 4 rule: Tauric multi-agent research runs only on candidate selection for /analyze)")
    tauric_tel = telemetry_manager.get_telemetry()["tauric"]
    print(f"  Tauric Reqs Count: {tauric_tel['request_count']}, Tauric is_active: {tauric_tel['is_active']}")

asyncio.run(detailed_step_trace())
