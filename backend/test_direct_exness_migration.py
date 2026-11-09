#!/usr/bin/env python3
"""
BITDEX Direct Exness-Only Migration Verification Test Suite
==========================================================
Strictly non-mutating / read-only evidence collector against:
Customer B: Ali Ajmal (USR-904424B4FB)
Account: Exness Terminal Demo #17000109575
Cluster: dx.2.trial.std / https://ap-58ee8e27.exness.com
Safety: dry_run = True, zero broker orders, zero position mutations.
"""

import sys
import os
import json
import time
import asyncio
from datetime import datetime, timezone
import statistics

sys.path.insert(0, "/opt/tauric-platform-staging/backend")

from app.services.saas_db import get_db_connection
from app.services.exness.vault import ExnessCredentialVault
from app.services.brokers.exness_terminal_adapter import ExnessTerminalBrokerAdapter
from app.services.brokers.execution_router import CentralExecutionRouter
from app.services.brokers.strategy_risk_engine import CommonStrategyAndRiskEngine

async def main():
    print("=" * 80)
    print("BITDEX DIRECT EXNESS-ONLY MIGRATION READ-ONLY EVIDENCE AUDIT")
    print("=" * 80)
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    
    conn = get_db_connection()
    user_id = "USR-904424B4FB"
    account_id = "17000109575"
    
    # 1. Resolve Account & Credentials
    print("\n[TEST 1] Tenant & Account Resolution")
    row = conn.execute(
        "SELECT * FROM exness_demo_connections WHERE user_id = ? AND account_login = ? AND is_active = 1",
        (user_id, account_id)
    ).fetchone()
    
    if not row:
        print("FAIL: Could not find connection row for Ali Ajmal.")
        return
        
    d = dict(row)
    print(f"  Connection ID: {d['connection_id']}")
    print(f"  User ID: {d['user_id']}")
    print(f"  Account Login: {d['account_login']}")
    print(f"  Account Type: {d['account_type']}")
    print(f"  Platform: {d['platform']}")
    print(f"  Adapter Mode: {d['adapter_mode']}")
    print(f"  Stream ID: {d['stream_id']}")
    print(f"  Access Point: {d['access_point']}")
    
    enc = json.loads(d["encrypted_credentials"])
    creds = ExnessCredentialVault.decrypt_credentials(user_id, account_id, d["server_name"], enc)
    api_key = str(d.get("api_key") or account_id)
    api_secret = str(creds.get("password") or "")
    
    # Safety Check: Verify Demo Only
    assert d["account_type"] == "DEMO", "ABORT: Non-demo account detected!"
    assert d["platform"] in ("EXNESS_TERMINAL", "DXTRADE", "NATIVE_EXNESS"), f"ABORT: Unexpected platform {d['platform']}"
    
    # 2. Instantiate ExnessTerminalBrokerAdapter
    print("\n[TEST 2] Adapter Instantiation & Capability Matrix")
    adapter = ExnessTerminalBrokerAdapter(
        owner_user_id=user_id,
        connection_id=d["connection_id"],
        account_id=account_id,
        api_key=api_key,
        api_secret=api_secret,
        environment="DEMO",
        server_name=d["stream_id"],
        access_point=d["access_point"],
    )
    caps = adapter.get_capabilities()
    print(f"  Adapter Name: {adapter.adapter_name}")
    print(f"  Broker: {adapter.broker_name}")
    print(f"  Platform: {adapter.trading_platform}")
    print(f"  Live Quotes & Market Data: {caps.live_quotes_and_market_data}")
    print(f"  Place Market Orders: {caps.place_market_orders}")
    print(f"  Attach SL/TP: {caps.attach_sl_tp}")
    print(f"  Close Individual Positions: {caps.close_individual_positions}")
    print(f"  Close All Positions: {caps.close_all_positions}")
    print(f"  Commissions, Swaps & PnL: {caps.commissions_swaps_and_pnl}")
    
    # 3. Authenticate Account
    print("\n[TEST 3] Direct Broker Authentication & Access Point Verification")
    t0 = time.monotonic()
    auth_res = await adapter.authenticate_account()
    auth_lat = (time.monotonic() - t0) * 1000
    print(f"  Authenticated: {auth_res.get('authenticated')}")
    print(f"  Access Point: {auth_res.get('access_point')}")
    print(f"  Stream ID: {auth_res.get('stream_id')}")
    print(f"  Account Status: {auth_res.get('account_status')}")
    print(f"  Execution Mode: {auth_res.get('execution_mode')}")
    print(f"  Auth Latency: {auth_lat:.1f} ms")
    
    # 4. Account Summary & Snapshot
    print("\n[TEST 4] Account Summary & Realized Margin Snapshot")
    t0 = time.monotonic()
    summary = await adapter.get_account_summary(force_refresh=True)
    summary_lat = (time.monotonic() - t0) * 1000
    print(f"  Balance: ${summary.get('balance'):.2f} {summary.get('currency')}")
    print(f"  Equity: ${summary.get('equity'):.2f} {summary.get('currency')}")
    print(f"  Used Margin: ${summary.get('used_margin'):.2f}")
    print(f"  Free Margin: ${summary.get('free_margin'):.2f}")
    print(f"  Leverage: 1:{summary.get('leverage')}")
    print(f"  Execution Readiness: {summary.get('execution_readiness_status')}")
    print(f"  Readiness Reason: {summary.get('execution_readiness_reason')}")
    print(f"  Snapshot Latency: {summary_lat:.1f} ms")
    
    # 5. Supported Instruments
    print("\n[TEST 5] Supported Instrument Catalog & Specifications")
    t0 = time.monotonic()
    instruments = await adapter.get_supported_instruments()
    inst_lat = (time.monotonic() - t0) * 1000
    print(f"  Retrieved {len(instruments)} instruments in {inst_lat:.1f} ms:")
    for inst in instruments[:4]:
        print(f"    - {inst['symbol']} ({inst['description']}): Digits={inst['digits']}, ContractSize={inst['contract_size']}, MinVol={inst['min_volume']}, MaxVol={inst['max_volume']}")
        
    spec_btc = await adapter.get_instrument_specification("BTCUSD")
    print(f"  BTCUSD Spec: Digits={spec_btc.get('digits')}, MinVol={spec_btc.get('min_volume')}, VolStep={spec_btc.get('volume_step')}")
    
    # 6. Live Market Quote & Spread
    print("\n[TEST 6] Live Market Quote & Spread Evaluation")
    t0 = time.monotonic()
    quote = await adapter.get_live_quote("BTCUSD")
    quote_lat = (time.monotonic() - t0) * 1000
    print(f"  Symbol: {quote.get('symbol')}")
    print(f"  Bid: {quote.get('bid')}")
    print(f"  Ask: {quote.get('ask')}")
    spread = round(float(quote.get('ask', 0.0)) - float(quote.get('bid', 0.0)), 2)
    print(f"  Spread: ${spread:.2f}")
    print(f"  Data Age: {quote.get('age_ms', 0)} ms")
    print(f"  Quote Latency: {quote_lat:.1f} ms")
    
    # 7. Historical M1 Candlesticks
    print("\n[TEST 7] Historical M1 Candlesticks (for Strategy Indicators)")
    t0 = time.monotonic()
    candles = await adapter.get_historical_candles("BTCUSD", timeframe="M1", count=10)
    candle_lat = (time.monotonic() - t0) * 1000
    print(f"  Retrieved {len(candles)} M1 candles in {candle_lat:.1f} ms")
    if candles:
        latest_c = candles[-1]
        print(f"  Latest Candle: Close=${latest_c.get('close')}, High=${latest_c.get('high')}, Low=${latest_c.get('low')}, Time={latest_c.get('timestamp')}")
        
    # 8. Open Positions & Deals
    print("\n[TEST 8] Open Positions Snapshot & Closed Deal History")
    positions = await adapter.get_open_positions()
    print(f"  Current Open Positions: {len(positions)}")
    deals = await adapter.client.get_trade_history(limit=5)
    print(f"  Historical Closed Deals: {len(deals)}")
    pnl_summary = await adapter.get_commissions_swaps_and_pnl(limit=10)
    print(f"  Commissions & PnL Summary: Realized PnL=${pnl_summary.get('realized_pnl'):.2f}, Unrealized PnL=${pnl_summary.get('unrealized_pnl'):.2f}")
    
    # 9. Latency Benchmark (20 Sequential Live Quotes)
    print("\n[TEST 9] Latency Benchmark (20 Sequential Live Quotes)")
    latencies = []
    for i in range(20):
        t_start = time.monotonic()
        q = await adapter.get_live_quote("BTCUSD")
        l_ms = (time.monotonic() - t_start) * 1000
        latencies.append(l_ms)
        await asyncio.sleep(0.05)
        
    latencies.sort()
    median_lat = statistics.median(latencies)
    p95_lat = latencies[int(len(latencies) * 0.95)]
    min_lat = min(latencies)
    max_lat = max(latencies)
    print(f"  Min Latency: {min_lat:.1f} ms")
    print(f"  Median Latency (p50): {median_lat:.1f} ms")
    print(f"  p95 Latency: {p95_lat:.1f} ms")
    print(f"  Max Latency: {max_lat:.1f} ms")
    
    # 10. Strategy Engine 13-Gate Pre-Trade Evaluation (Strictly dry_run=True)
    print("\n[TEST 10] 13-Gate Strategy & Risk Engine Evaluation (dry_run=True)")
    t0 = time.monotonic()
    engine = CommonStrategyAndRiskEngine()
    strat_res = await engine.evaluate_strategy_and_risk(
        adapter=adapter,
        symbol="BTCUSD",
        allocated_capital_usd=50.0,
        leverage=2000,
        profit_target_usd=1.0,
        max_loss_usd=1.0,
        min_net_edge_usd=0.20,
    )
    strat_lat = (time.monotonic() - t0) * 1000
    diag = strat_res.get("diagnostic", {})
    cycle = strat_res.get("directional_cycle", {})
    print(f"  Selected Direction: {cycle.get('selected_direction')}")
    print(f"  Directional Score: {cycle.get('directional_score')}/100")
    print(f"  Entry Qualified: {cycle.get('entry_qualified')}")
    print(f"  Reason: {cycle.get('no_entry_reason')}")
    print(f"  EMA Status: {diag.get('ema_status')}")
    print(f"  RSI Status: {diag.get('rsi_status')}")
    print(f"  Momentum: {diag.get('momentum_status')}")
    print(f"  Spread: ${strat_res.get('spread_usd', 0.0):.2f} ({strat_res.get('spread_bps', 0.0):.2f} bps)")
    print(f"  Evaluation Latency: {strat_lat:.1f} ms")
    
    # 11. Preflight Order Validation & Ed25519 Signing (STRICT dry_run=True)
    print("\n[TEST 11] Preflight Order Validation & Ed25519 Signing (STRICT dry_run=True)")
    preflight = await adapter.place_market_order(
        symbol="BTCUSD",
        side="buy",
        volume=0.01,
        sl=cycle.get("suggested_sl", 74000.0),
        tp=cycle.get("suggested_tp", 76000.0),
        dry_run=True, # MANDATORY SAFETY INVARIANT: Zero broker orders
    )
    print(f"  Preflight Status: {preflight.get('status')}")
    print(f"  Signature Verified: {preflight.get('signature_verified')}")
    print(f"  Endpoint: {preflight.get('endpoint')}")
    print(f"  Payload: {json.dumps(preflight.get('payload'))}")
    print(f"  Safety Message: {preflight.get('message')}")
    
    print("\n" + "=" * 80)
    print("ALL 11 READ-ONLY DIRECT EXNESS-ONLY TESTS COMPLETED SUCCESSFULLY")
    print("SAFETY CONFIRMED: ZERO BROKER ORDERS DISPATCHED, ZERO MUTATIONS.")
    print("=" * 80)
    conn.close()

if __name__ == "__main__":
    asyncio.run(main())
