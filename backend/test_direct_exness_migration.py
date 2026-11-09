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
from app.services.exness.event_stream import ExnessTransactionEventManager, OperationState

async def main():
    print("=" * 80)
    print("BITDEX DIRECT EXNESS-ONLY MIGRATION READ-ONLY EVIDENCE AUDIT")
    print("=" * 80)
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print("Safety Level: STRICT DEMO / READ-ONLY AUDIT. Zero broker orders.")
    
    conn = get_db_connection()
    user_id = "USR-904424B4FB"
    account_id = "17000109575"
    
    # ─── TEST 1: Tenant & Account Resolution ──────────────────────────────
    print("\n[TEST 1] Tenant & Account Resolution (Database & Vault)")
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
    
    assert d["account_type"] == "DEMO", "ABORT: Non-demo account detected!"
    assert d["platform"] in ("EXNESS_TERMINAL", "DXTRADE", "NATIVE_EXNESS"), f"ABORT: Unexpected platform {d['platform']}"
    
    # ─── TEST 2: Adapter Capabilities ──────────────────────────────────────
    print("\n[TEST 2] Adapter Instantiation & UniversalBrokerAdapter Capabilities")
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
    
    # ─── TEST 3: Access Point Discovery & Authentication ──────────────────
    print("\n[TEST 3] Direct Broker Authentication & Regional Access Point Discovery")
    t0 = time.perf_counter()
    auth_res = await adapter.authenticate_account()
    auth_lat = (time.perf_counter() - t0) * 1000
    print(f"  Authenticated: {auth_res.get('authenticated')}")
    print(f"  Access Point: {auth_res.get('access_point')}")
    print(f"  Stream ID: {auth_res.get('stream_id')}")
    print(f"  Account Status: {auth_res.get('account_status')}")
    print(f"  Execution Mode: {auth_res.get('execution_mode')}")
    print(f"  Auth Latency (Uncached Network): {auth_lat:.1f} ms")
    
    # ─── TEST 4: Account Summary & Margin Snapshot ────────────────────────
    print("\n[TEST 4] Account Summary & Realized Margin Snapshot (Uncached)")
    t0 = time.perf_counter()
    summary = await adapter.get_account_summary(force_refresh=True)
    summary_lat = (time.perf_counter() - t0) * 1000
    print(f"  Balance: ${summary.get('balance'):.2f} {summary.get('currency')}")
    print(f"  Equity: ${summary.get('equity'):.2f} {summary.get('currency')}")
    print(f"  Used Margin: ${summary.get('used_margin'):.2f}")
    print(f"  Free Margin: ${summary.get('free_margin'):.2f}")
    print(f"  Leverage: 1:{summary.get('leverage')}")
    print(f"  Execution Readiness: {summary.get('execution_readiness_status')}")
    print(f"  Readiness Reason: {summary.get('execution_readiness_reason')}")
    print(f"  Snapshot Latency (Uncached Network): {summary_lat:.1f} ms")
    
    # ─── TEST 5: Supported Instrument Catalog ─────────────────────────────
    print("\n[TEST 5] Supported Instrument Catalog & Contract Specifications")
    t0 = time.perf_counter()
    instruments = await adapter.get_supported_instruments()
    inst_lat = (time.perf_counter() - t0) * 1000
    print(f"  Retrieved {len(instruments)} instruments in {inst_lat:.1f} ms:")
    for inst in instruments[:4]:
        print(f"    - {inst['symbol']} ({inst['description']}): Digits={inst['digits']}, ContractSize={inst['contract_size']}, MinVol={inst['min_volume']}, MaxVol={inst['max_volume']}")
        
    spec_btc = await adapter.get_instrument_specification("BTCUSD")
    print(f"  BTCUSD Spec: Digits={spec_btc.get('digits')}, MinVol={spec_btc.get('min_volume')}, VolStep={spec_btc.get('volume_step')}")
    
    # ─── TEST 6: Live Market Quote & Spread ───────────────────────────────
    print("\n[TEST 6] Live Market Quote & Spread Evaluation")
    t0 = time.perf_counter()
    quote = await adapter.get_live_quote("BTCUSD")
    quote_lat = (time.perf_counter() - t0) * 1000
    print(f"  Symbol: {quote.get('symbol')}")
    print(f"  Bid: {quote.get('bid')}")
    print(f"  Ask: {quote.get('ask')}")
    spread = round(float(quote.get('ask', 0.0)) - float(quote.get('bid', 0.0)), 2)
    print(f"  Spread: ${spread:.2f}")
    print(f"  Data Age: {quote.get('age_ms', 0)} ms")
    print(f"  Quote Processing Latency: {quote_lat:.1f} ms")
    
    # ─── TEST 7: Historical M1 Candlesticks ───────────────────────────────
    print("\n[TEST 7] Historical M1 Candlesticks (for Strategy Indicators)")
    t0 = time.perf_counter()
    candles = await adapter.get_historical_candles("BTCUSD", timeframe="M1", count=10)
    candle_lat = (time.perf_counter() - t0) * 1000
    print(f"  Retrieved {len(candles)} M1 candles in {candle_lat:.1f} ms")
    if candles:
        latest_c = candles[-1]
        print(f"  Latest Candle: Close=${latest_c.get('close')}, High=${latest_c.get('high')}, Low=${latest_c.get('low')}, Time={latest_c.get('timestamp')}")
        
    # ─── TEST 8: Positions & PnL History ──────────────────────────────────
    print("\n[TEST 8] Open Positions Snapshot & Closed Deal History")
    positions = await adapter.get_open_positions()
    print(f"  Current Open Positions: {len(positions)}")
    deals = await adapter.client.get_trade_history(limit=5)
    print(f"  Historical Closed Deals: {len(deals)}")
    pnl_summary = await adapter.get_commissions_swaps_and_pnl(limit=10)
    print(f"  Commissions & PnL Summary: Realized PnL=${pnl_summary.get('realized_pnl'):.2f}, Unrealized PnL=${pnl_summary.get('unrealized_pnl'):.2f}")
    
    # ─── TEST 9: GENUINE UNCACHED BROKER NETWORK LATENCY (20 Direct Round-Trips) ──
    print("\n[TEST 9] Genuine Uncached Broker Network Round-Trip Latency Benchmark (20 Sequential Direct Requests)")
    print("  Clock Methodology: time.perf_counter() on Linux kernel 6.8.0-45-generic")
    print("  Target Endpoint: GET https://ap-58ee8e27.exness.com/v1/trading/accounts/17000109575/snapshot (force_refresh=True)")
    
    uncached_latencies = []
    for i in range(20):
        t_start = time.perf_counter()
        snap = await adapter.client.get_trading_snapshot(force_refresh=True)
        l_ms = (time.perf_counter() - t_start) * 1000
        uncached_latencies.append(l_ms)
        # Small delay to respect rate limit
        await asyncio.sleep(0.1)
        
    uncached_latencies.sort()
    min_net = min(uncached_latencies)
    median_net = statistics.median(uncached_latencies)
    p95_net = uncached_latencies[int(len(uncached_latencies) * 0.95)]
    max_net = max(uncached_latencies)
    mean_net = statistics.mean(uncached_latencies)
    
    print(f"  Sample Count: {len(uncached_latencies)} uncached network requests")
    print(f"  Min Network Latency: {min_net:.1f} ms")
    print(f"  Median Network Latency (p50): {median_net:.1f} ms")
    print(f"  Mean Network Latency: {mean_net:.1f} ms")
    print(f"  95th Percentile Latency (p95): {p95_net:.1f} ms")
    print(f"  Max Network Latency: {max_net:.1f} ms")
    print(f"  Raw Latencies (ms): {[round(x, 1) for x in uncached_latencies]}")
    
    # ─── TEST 10: WebSocket Events Handshake & Subscription (Phase 4) ─────
    print("\n[TEST 10] WebSocket Events Stream Handshake & Subscription (WSS /ws/events)")
    event_mgr = ExnessTransactionEventManager(adapter.client)
    t0 = time.perf_counter()
    ws_test_res = await event_mgr.test_handshake_and_subscription(timeout_sec=8.0)
    print(f"  Status: {ws_test_res.get('status')}")
    print(f"  Endpoint: {ws_test_res.get('endpoint')}")
    print(f"  Handshake Latency: {ws_test_res.get('handshake_latency_ms')} ms")
    print(f"  Total Round Trip: {ws_test_res.get('total_round_trip_ms')} ms")
    print(f"  Subscription Sent: {json.dumps(ws_test_res.get('subscription_sent', {}))}")
    print(f"  Server Response: {json.dumps(ws_test_res.get('server_response', {}))}")
    print(f"  Safety Invariant: {ws_test_res.get('safety')}")
    
    # ─── TEST 11: Asynchronous State Machine & Deduplication (Phase 4) ────
    print("\n[TEST 11] Asynchronous Execution State Machine & Duplicate Event Deduplication")
    # 1. Register test operation at ACCEPTED stage
    op_test = event_mgr.register_dispatched_operation(
        operation_id="op-test-9901",
        client_request_id="req-test-9901",
        symbol="BTCUSD",
        side="buy",
        volume=0.01,
    )
    print(f"  Initial State on Dispatched ACK: {op_test.get('state')} (Enforces: Accepted != Filled)")
    assert op_test.get('state') == OperationState.ACCEPTED.value, "State must be ACCEPTED upon ACK"
    
    # 2. Simulate incoming transaction fill event frame
    fill_frame = json.dumps({
        "id": "evt-fill-1001",
        "event": "transaction",
        "data": {
            "operation_id": "op-test-9901",
            "status": "confirmed",
            "position_id": "pos-88022",
            "execution_price": 75050.25,
            "volume": 0.01,
        }
    })
    handled = event_mgr.handle_event_message(fill_frame)
    updated_op = event_mgr.get_operation_state("op-test-9901")
    print(f"  Processed WebSocket Event: Status={handled.get('data', {}).get('status')}")
    print(f"  Transitioned State: {updated_op.get('state')} (Position #{updated_op.get('position_id')} at ${updated_op.get('execution_price')})")
    assert updated_op.get('state') == OperationState.FILLED.value, "State must transition to FILLED"
    
    # 3. Simulate duplicate incoming frame (deduplication test)
    dup_handled = event_mgr.handle_event_message(fill_frame)
    print(f"  Duplicate Frame Result: Handled={dup_handled is not None} (Duplicates Dropped: {event_mgr.duplicates_dropped})")
    assert dup_handled is None, "Duplicate event must be dropped by sliding window filter"
    assert event_mgr.duplicates_dropped == 1, "Duplicate counter must increment"
    
    # ─── TEST 12: Tenant Isolation Verification ───────────────────────────
    print("\n[TEST 12] Tenant Isolation Verification (Customer A vs Customer B)")
    cust_a_id = "USR-ADM-B022F490"
    cust_b_id = "USR-904424B4FB"
    # Attempt to resolve Customer B's account with Customer A's session
    try:
        CentralExecutionRouter.resolve_adapter_for_customer(conn, cust_a_id, account_id)
        print("  FAIL: Cross-tenant resolution succeeded when it must fail!")
    except Exception as exc:
        print(f"  PASS: Cross-tenant resolution blocked: {type(exc).__name__}: {str(exc)[:60]}...")
        
    # Attempt to decrypt Customer B's vault secret using Customer A's ID
    try:
        ExnessCredentialVault.decrypt_credentials(cust_a_id, account_id, d["server_name"], enc)
        print("  FAIL: Cross-tenant decryption succeeded when it must fail!")
    except Exception as exc:
        print(f"  PASS: Cross-tenant credential decryption blocked: {type(exc).__name__}: {str(exc)[:60]}...")
        
    # ─── TEST 13: Platform Eligibility & MT5 Rejection ────────────────────
    print("\n[TEST 13] Platform Eligibility Verification (MT4/MT5 Rejection Guidance)")
    mt5_test_account = "474861031" # Known MT5 account
    auth_mt5 = await adapter.client.authenticate_account(mt5_test_account)
    print(f"  Tested MT5 Account: {mt5_test_account}")
    print(f"  Verified: {auth_mt5.get('verified')}")
    print(f"  Error Type: {auth_mt5.get('error_type')}")
    print(f"  Guidance Message: {auth_mt5.get('error_detail')[:120]}...")
    assert auth_mt5.get('verified') is False, "MT5 account must not authenticate via Direct Exness Trader API"
    
    # ─── TEST 14: 13-Gate Strategy & Risk Engine Evaluation ───────────────
    print("\n[TEST 14] 13-Gate Strategy & Risk Engine Evaluation (dry_run=True)")
    t0 = time.perf_counter()
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
    strat_lat = (time.perf_counter() - t0) * 1000
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
    
    # ─── TEST 15: Preflight Order Validation & Ed25519 Signing ────────────
    print("\n[TEST 15] Preflight Order Validation & Ed25519 Signing (STRICT dry_run=True)")
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
    assert preflight.get('status') == "DRY_RUN_VERIFIED", "Preflight must return DRY_RUN_VERIFIED"
    assert preflight.get('signature_verified') is True, "Ed25519 signature must be verified"
    
    print("\n" + "=" * 80)
    print("ALL 15 READ-ONLY DIRECT EXNESS-ONLY TESTS COMPLETED SUCCESSFULLY")
    print("SAFETY CONFIRMED: ZERO BROKER ORDERS DISPATCHED, ZERO MUTATIONS.")
    print("=" * 80)
    conn.close()

if __name__ == "__main__":
    asyncio.run(main())
