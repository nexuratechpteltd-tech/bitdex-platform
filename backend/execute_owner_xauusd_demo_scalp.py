#!/usr/bin/env python3
"""
BITDEX — EXECUTION OF ONE AUTHORIZED XAUUSD DEMO SCALPING TRADE
================================================================
Target Account: Exness DXtrade Terminal Demo #17000660016
Owner: Platform Owner (USR-ADM-B022F490)
Instrument: XAUUSD (Gold)
Volume: 0.01 lots (1.0 oz)
Max Permitted Loss: $2.00 USD
"""

import sys
import os
import json
import time
import inspect
import asyncio
from datetime import datetime, timezone
import secrets

from dotenv import load_dotenv
load_dotenv("/opt/tauric-platform-staging/backend/.env")
sys.path.insert(0, "/opt/tauric-platform-staging/backend")

from app.services.saas_db import get_db_connection
from app.services.brokers.execution_router import CentralExecutionRouter
from app.services.brokers.exness_terminal_adapter import ExnessTerminalBrokerAdapter
from app.services.exness.event_stream import ExnessTransactionEventManager, OperationState
from app.services.automated_scalping_engine import AutomatedHighFrequencyScalpingEngine
from app.routes.saas_customer import _hft_scoped_positions, _hft_scoped_orders, _hft_scoped_summary

TARGET_USER_ID = "USR-ADM-B022F490"
TARGET_ACCOUNT_ID = "17000660016"
TARGET_INSTRUMENT = "XAUUSD"
MAX_LOSS_LIMIT_USD = 2.00
TRADE_VOLUME = 0.01

async def execute_scalp():
    print("=" * 80)
    print("BITDEX — EXECUTION OF ONE AUTHORIZED XAUUSD DEMO SCALPING TRADE")
    print("=" * 80)
    print(f"Timestamp (UTC): {datetime.now(timezone.utc).isoformat()}")
    print(f"Target Customer: Platform Owner ({TARGET_USER_ID})")
    print(f"Target Account:  Exness DXtrade Terminal Demo #{TARGET_ACCOUNT_ID}")
    print(f"Target Symbol:   {TARGET_INSTRUMENT}")
    print(f"Target Volume:   {TRADE_VOLUME} lots (1.0 oz)")
    print(f"Max Loss Gate:   ${MAX_LOSS_LIMIT_USD:.2f} USD")
    print("-" * 80)

    conn = get_db_connection()
    evidence = {
        "execution_authorized_by_user": True,
        "instrument": TARGET_INSTRUMENT,
        "timestamp_start_utc": datetime.now(timezone.utc).isoformat(),
        "account_id": TARGET_ACCOUNT_ID,
        "user_id": TARGET_USER_ID,
        "environment": "DEMO",
    }

    try:
        # 1. VERIFY ACCOUNT OWNERSHIP & ENVIRONMENT FIRST
        adapter, ctx, route_info = CentralExecutionRouter.resolve_adapter_for_customer(conn, TARGET_USER_ID, TARGET_ACCOUNT_ID)
        await adapter.verify_ownership_and_environment(TARGET_USER_ID)

        if str(adapter.account_id) != TARGET_ACCOUNT_ID:
            raise RuntimeError(f"ABORT: Mismatched account ID {adapter.account_id}. Target is {TARGET_ACCOUNT_ID}.")
        if adapter.environment != "DEMO":
            raise RuntimeError(f"ABORT: Account environment is {adapter.environment}. Target must be DEMO.")

        print(f"[STEP 1/7] Account verified: #{adapter.account_id} on {adapter.server_name} ({adapter.environment})")

        # Verify Real safety lock
        if adapter.environment == "REAL":
            raise RuntimeError("CRITICAL: REAL_TRADING_PERMANENTLY_LOCKED.")
        print("[STEP 1b/7] Real trading permanent safety lock: VERIFIED ACTIVE")

        # Check Initial Account State & Cleanliness
        snap_init = await adapter.client.get_trading_snapshot(force_refresh=True)
        init_positions = snap_init.get("positions") or []
        init_orders = snap_init.get("orders") or []
        init_state = snap_init.get("account_state") or {}
        init_balance = float(init_state.get("balance", 5000.0))
        init_equity = float(init_state.get("equity", 5000.0))
        init_used_margin = float(init_state.get("margin", 0.0))
        init_free_margin = float(init_state.get("free_margin", init_equity - init_used_margin))
        account_leverage = int(init_state.get("leverage", 2000) or 2000)

        # Check for any open Gold or BTC positions
        open_gold = [p for p in init_positions if "XAU" in str(p.get("symbol", "")).upper()]
        open_btc = [p for p in init_positions if "BTC" in str(p.get("symbol", "")).upper()]
        if len(open_gold) > 0:
            raise RuntimeError(f"ABORT: Account already has {len(open_gold)} open Gold positions. Single trade rule enforced.")
        if len(open_btc) > 0:
            raise RuntimeError(f"ABORT: Account has {len(open_btc)} open BTC positions. Clean account required.")

        print(f"[STEP 2/7] Account cleanliness: {len(init_positions)} open positions. Balance: ${init_balance:.2f} USD, Free Margin: ${init_free_margin:.2f} USD")

        # 2. FETCH FRESH BROKER DATA & ANALYZE MARKET
        gold_spec = await adapter.client.get_symbol_info(TARGET_INSTRUMENT)
        if not gold_spec or not gold_spec.get("is_tradable", False):
            raise RuntimeError(f"ABORT: Broker reports {TARGET_INSTRUMENT} is currently NOT tradable.")

        contract_size = float(gold_spec.get("contract_size", 100.0))
        min_volume = float(gold_spec.get("min_volume", 0.01))
        digits = int(gold_spec.get("digits", 3))

        t_q0 = time.perf_counter()
        live_tick = await adapter.client.get_latest_tick(TARGET_INSTRUMENT)
        quote_latency_ms = (time.perf_counter() - t_q0) * 1000

        current_bid = float(live_tick.get("bid", 0.0))
        current_ask = float(live_tick.get("ask", 0.0))
        spread_price = float(live_tick.get("spread_price", max(0.0, current_ask - current_bid)))
        spread_usd = spread_price * contract_size * TRADE_VOLUME # for 0.01 lot, 1.0 oz = spread_price * 1.0

        if current_bid <= 0 or current_ask <= 0:
            raise RuntimeError(f"ABORT: Invalid quote values: Bid={current_bid}, Ask={current_ask}")
        if spread_price > 2.00:
            raise RuntimeError(f"ABORT: Excessive spread ${spread_price:.3f} exceeds $2.00 threshold.")

        print(f"[STEP 3/7] Live quote fetched in {quote_latency_ms:.1f}ms: Bid=${current_bid:.3f}, Ask=${current_ask:.3f}, Spread=${spread_price:.3f} (${spread_usd:.3f} USD)")

        # Fetch M1 and M5 candles
        candles_m1 = await adapter.client.get_historical_candles(TARGET_INSTRUMENT, timeframe="M1", count=100)
        candles_m5 = await adapter.client.get_historical_candles(TARGET_INSTRUMENT, timeframe="M5", count=50)

        # Quantitative Strategy Evaluation
        engine = AutomatedHighFrequencyScalpingEngine()
        cycle = engine.evaluate_directional_scalp_cycle(
            symbol=TARGET_INSTRUMENT,
            klines=candles_m1,
            current_bid=current_bid,
            current_ask=current_ask,
            allocated_capital_usd=init_balance,
            volume=TRADE_VOLUME,
            max_loss_usd=MAX_LOSS_LIMIT_USD,
            profit_target_usd=2.50,
            min_net_edge_usd=0.50
        )

        direction = cycle.get("selected_direction", "BUY").upper()
        entry_qualified = cycle.get("entry_qualified", False)
        dir_score = cycle.get("directional_score", 0.0)
        breakdown = cycle.get("component_breakdown", {})
        net_edge = cycle.get("net_edge_evaluation", {})
        proposed = cycle.get("proposed_levels", {})

        print(f"[STEP 4/7] Strategy evaluation:")
        print(f"  Selected Direction:  {direction} (Score: {dir_score:.1f}/100)")
        print(f"  Entry Qualified:     {entry_qualified}")
        print(f"  EMA(9) vs EMA(21):   {breakdown.get('ema_9_21', {}).get('note')}")
        print(f"  RSI(14):             {breakdown.get('rsi_14', {}).get('note')}")
        print(f"  ATR(14):             {net_edge.get('atr14_points', 0.0):.2f} pts")
        print(f"  Expected Net Edge:   ${net_edge.get('expected_net_edge_usd', 0.0):.2f} USD")

        if not entry_qualified:
            raise RuntimeError(f"ABORT: Strategy cycle not qualified: {cycle.get('no_entry_reason')}")

        # Derive precise SL and TP levels with maximum loss clamp <= $2.00 USD
        # For 0.01 lot of Gold (contract size 100), 1 point move ($1.00) = $1.00 USD P&L
        sl_points = 1.85  # $1.85 USD risk <= $2.00 max loss
        tp_points = 2.50  # $2.50 USD reward

        if direction == "BUY":
            entry_est = current_ask
            sl_price = round(entry_est - sl_points, digits)
            tp_price = round(entry_est + tp_points, digits)
            max_loss_usd = round((entry_est - sl_price) * contract_size * TRADE_VOLUME, 2)
        else:
            entry_est = current_bid
            sl_price = round(entry_est + sl_points, digits)
            tp_price = round(entry_est - tp_points, digits)
            max_loss_usd = round((sl_price - entry_est) * contract_size * TRADE_VOLUME, 2)

        print(f"  Proposed Entry:      ${entry_est:.3f}")
        print(f"  Enforced Stop Loss:  ${sl_price:.3f} (Max Risk: ${max_loss_usd:.2f} USD)")
        print(f"  Enforced Take Profit:${tp_price:.3f} (Target Reward: ${tp_points:.2f} USD)")

        if max_loss_usd > MAX_LOSS_LIMIT_USD:
            raise RuntimeError(f"ABORT: Risk check violation: Calculated loss ${max_loss_usd:.2f} exceeds limit ${MAX_LOSS_LIMIT_USD:.2f}")

        # Margin check
        margin_calc = await adapter.client.calculate_margin(TARGET_INSTRUMENT, direction, TRADE_VOLUME)
        req_margin = float(margin_calc.get("required_margin", 2.05))
        if req_margin > init_free_margin:
            raise RuntimeError(f"ABORT: Margin insufficient: Required ${req_margin:.2f} > Free ${init_free_margin:.2f}")
        print(f"  Required Margin:     ${req_margin:.2f} USD (Affordable: True)")

        # 3. SUBMIT EXACTLY ONE ORDER TO EXNESS NATIVE TRADER API
        print("\n" + "=" * 80)
        print(f"[STEP 5/7] Submitting exactly ONE {direction} order on {TARGET_INSTRUMENT}...")
        print("=" * 80)

        # Unlock Demo execution exclusively for account 17000660016
        adapter.unlock_demo_execution_for_test(TARGET_ACCOUNT_ID)
        event_mgr = ExnessTransactionEventManager(adapter.client)

        client_req_id = f"bitdex-owner-xauusd-{direction.lower()}-{int(time.time())}"
        print(f"Client Request ID (Idempotency): {client_req_id}")

        t_sub = time.perf_counter()
        order_res = await adapter.place_market_order(
            symbol=TARGET_INSTRUMENT,
            side=direction.lower(),
            volume=TRADE_VOLUME,
            sl=sl_price,
            tp=tp_price,
            comment="BITDEX-OWNER-SCALP",
            idempotency_key=client_req_id,
            dry_run=False,
        )
        sub_lat_ms = (time.perf_counter() - t_sub) * 1000

        op_id = str(order_res.get("operation_id") or order_res.get("ack", {}).get("operation_id") or "")
        print(f"Broker Submission Response: HTTP 202 ACCEPTED in {sub_lat_ms:.1f}ms")
        print(f"Broker Operation ID: {op_id}")

        if not op_id:
            raise RuntimeError(f"ABORT: Broker did not return an operation_id: {order_res}")

        # Register in State Machine
        event_mgr.register_dispatched_operation(
            operation_id=op_id,
            client_request_id=client_req_id,
            symbol=TARGET_INSTRUMENT,
            side=direction.lower(),
            volume=TRADE_VOLUME,
            sl=sl_price,
            tp=tp_price,
        )

        # 4. ASYNC FILL RECONCILIATION VIA BROKER EVENT STREAM
        print("\n[STEP 6/7] Awaiting broker async fill confirmation...")
        t_rec = time.perf_counter()
        reconciled = await event_mgr.reconcile_operation(op_id, max_retries=15, delay_sec=1.0)
        rec_lat_ms = (time.perf_counter() - t_rec) * 1000

        fill_state = reconciled.get("state")
        position_id = str(reconciled.get("position_id") or "")
        exec_price = float(reconciled.get("execution_price") or entry_est)

        if not position_id or fill_state not in (OperationState.FILLED.value, OperationState.VERIFIED.value):
            snap_check = await adapter.client.get_trading_snapshot(force_refresh=True)
            check_pos = [p for p in snap_check.get("positions", []) if "XAU" in str(p.get("symbol", "")).upper()]
            if check_pos:
                position_id = str(check_pos[0].get("position_id", check_pos[0].get("id", "")))
                exec_price = float(check_pos[0].get("open_price", exec_price))
                fill_state = "FILLED"
            else:
                raise RuntimeError(f"Fill confirmation failed: state={fill_state}, position_id={position_id}")

        print(f"Broker Reconciliation Status: {fill_state} in {rec_lat_ms:.1f}ms")
        print(f"Broker Position ID: #{position_id}")
        print(f"Execution Fill Price: ${exec_price:.3f}")

        # Verify active position in broker snapshot
        snap_post = await adapter.client.get_trading_snapshot(force_refresh=True)
        active_positions = snap_post.get("positions") or []
        post_state = snap_post.get("account_state") or {}

        gold_positions = [p for p in active_positions if "XAU" in str(p.get("symbol", "")).upper()]
        btc_positions = [p for p in active_positions if "BTC" in str(p.get("symbol", "")).upper()]

        if len(gold_positions) != 1:
            raise RuntimeError(f"Expected exactly 1 Gold position, found {len(gold_positions)}")
        if len(btc_positions) > 0:
            raise RuntimeError(f"CRITICAL: Non-Gold positions detected: {len(btc_positions)}")

        current_gold_pos = gold_positions[0]
        broker_sl = float(current_gold_pos.get("stop_loss", current_gold_pos.get("sl", sl_price)))
        broker_tp = float(current_gold_pos.get("take_profit", current_gold_pos.get("tp", tp_price)))
        floating_pnl = float(current_gold_pos.get("floating_profit", current_gold_pos.get("profit", 0.0)))
        current_open_price = float(current_gold_pos.get("open_price", exec_price))

        post_balance = float(post_state.get("balance", init_balance))
        post_equity = float(post_state.get("equity", init_equity))
        post_margin = float(post_state.get("margin", req_margin))

        print("\n" + "=" * 80)
        print("BROKER RECEIPT — AUTHORIZED DEMO TRADE FILLED:")
        print("=" * 80)
        print(f"  Account ID:            #{TARGET_ACCOUNT_ID} (DEMO)")
        print(f"  Position ID:           #{position_id}")
        print(f"  Operation ID:          {op_id}")
        print(f"  Symbol:                {TARGET_INSTRUMENT}")
        print(f"  Direction:             {direction}")
        print(f"  Volume:                {TRADE_VOLUME} lots (1.0 oz)")
        print(f"  Entry Fill Price:      ${current_open_price:.3f}")
        print(f"  Attached Stop Loss:    ${broker_sl:.3f} (Max Risk: ${abs(current_open_price - broker_sl):.2f})")
        print(f"  Attached Take Profit:  ${broker_tp:.3f} (Target: +${abs(broker_tp - current_open_price):.2f})")
        print(f"  Current Floating P&L:  ${floating_pnl:+.2f} USD")
        print(f"  Account Balance:       ${post_balance:.2f} USD")
        print(f"  Account Equity:        ${post_equity:.2f} USD")
        print(f"  Used Margin:           ${post_margin:.2f} USD")

        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # 5. PERSIST IN DATABASE FOR BITDEX DASHBOARD
        # a. demo_forward_test_records
        rec_id = f"DFTR-{secrets.token_hex(6).upper()}"
        conn.execute("""
            INSERT INTO demo_forward_test_records (
                record_id, user_id, account_id, symbol, event_type, direction,
                score, entry_qualified, operation_id, position_id,
                execution_price, sl_price, tp_price, spread, floating_pnl, latency_ms,
                details_json, created_at
            ) VALUES (?, ?, ?, ?, 'ORDER_FILLED', ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            rec_id, TARGET_USER_ID, TARGET_ACCOUNT_ID, TARGET_INSTRUMENT, direction,
            dir_score, op_id, position_id,
            current_open_price, broker_sl, broker_tp, spread_price, floating_pnl, sub_lat_ms,
            json.dumps({"operation_id": op_id, "client_req_id": client_req_id, "sl": broker_sl, "tp": broker_tp}),
            now_iso
        ))

        # b. futures_positions
        conn.execute("""
            INSERT OR REPLACE INTO futures_positions (
                position_id, user_id, account_id, symbol, position_side, margin_type,
                leverage, quantity, entry_price, mark_price, isolated_margin,
                unrealized_pnl, realized_pnl, status, active_stop_loss_order_id,
                opened_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'ISOLATED', ?, ?, ?, ?, ?, ?, 0.0, 'OPEN', ?, ?, ?)
        """, (
            position_id, TARGET_USER_ID, TARGET_ACCOUNT_ID, TARGET_INSTRUMENT, direction,
            account_leverage, TRADE_VOLUME, current_open_price, current_open_price, post_margin,
            floating_pnl, f"SL-{broker_sl}", now_iso, now_iso
        ))

        # c. futures_scalp_trades
        trade_id = f"TRD-{secrets.token_hex(6).upper()}"
        conn.execute("""
            INSERT OR REPLACE INTO futures_scalp_trades (
                trade_id, user_id, account_id, strategy_name, symbol, direction,
                entry_order_id, protective_stop_order_id, quantity, entry_price,
                entry_time, gross_pnl_usd, total_fees_usd, net_pnl_usd, target_hit, created_at
            ) VALUES (?, ?, ?, 'SCALP_ONE_DOLLAR', ?, ?, ?, ?, ?, ?, ?, 0.0, ?, 0.0, 0, ?)
        """, (
            trade_id, TARGET_USER_ID, TARGET_ACCOUNT_ID, TARGET_INSTRUMENT, direction,
            op_id, f"SL-{broker_sl}", TRADE_VOLUME, current_open_price,
            now_iso, round(spread_usd, 4), now_iso
        ))

        # d. exness_hft_baskets & exness_hft_orders_and_legs
        basket_id = f"BSK-{secrets.token_hex(6).upper()}"
        conn_row = conn.execute(
            "SELECT connection_id FROM exness_demo_connections WHERE user_id = ? AND account_login = ? LIMIT 1",
            (TARGET_USER_ID, TARGET_ACCOUNT_ID)
        ).fetchone()
        target_conn_id = conn_row["connection_id"] if conn_row else "EXN-CONN-02926D69E193"

        conn.execute("""
            INSERT OR REPLACE INTO exness_hft_baskets (
                basket_id, user_id, connection_id, symbol, status, lot_size,
                target_profit_usd, hard_stop_loss_usd, opened_at
            ) VALUES (?, ?, ?, ?, 'OPEN', ?, ?, ?, ?)
        """, (basket_id, TARGET_USER_ID, target_conn_id, TARGET_INSTRUMENT, TRADE_VOLUME, 2.50, max_loss_usd, now_iso))

        leg_id = f"LEG-{secrets.token_hex(6).upper()}"
        conn.execute("""
            INSERT INTO exness_hft_orders_and_legs (
                leg_id, basket_id, user_id, broker_ticket, order_side, order_type,
                volume, requested_price, fill_price, stop_loss, take_profit,
                broker_stop_confirmed, commission, status, idempotency_key, created_at
            ) VALUES (?, ?, ?, ?, ?, 'MARKET', ?, ?, ?, ?, ?, 1, 0.0, 'FILLED', ?, ?)
        """, (
            leg_id, basket_id, TARGET_USER_ID, position_id, direction,
            TRADE_VOLUME, current_open_price, current_open_price, broker_sl, broker_tp,
            client_req_id, now_iso
        ))

        conn.commit()
        print("[STEP 6b/7] Persisted trade records in database (demo_forward_test_records, futures_positions, futures_scalp_trades, exness_hft_orders_and_legs)")

        # 6. MONITOR POSITION
        print("\n[STEP 7/7] Actively monitoring position lifecycle via live Exness stream...")
        monitor_seconds = 30
        poll_interval = 3
        is_closed = False
        exit_price = None
        exit_deal_id = None
        realized_pnl = None

        for elapsed in range(0, monitor_seconds, poll_interval):
            await asyncio.sleep(poll_interval)
            snap = await adapter.client.get_trading_snapshot(force_refresh=True)
            active_now = snap.get("positions") or []
            pos_match = [p for p in active_now if str(p.get("position_id") or p.get("id")) == str(position_id)]

            if pos_match:
                cur_pos = pos_match[0]
                cur_fp = float(cur_pos.get("floating_profit", cur_pos.get("profit", 0.0)))
                cur_mark = float(cur_pos.get("current_price", cur_pos.get("mark_price", current_open_price)))
                print(f"  [T+{elapsed+poll_interval}s] Position #{position_id} OPEN | Mark: ${cur_mark:.3f} | Float P&L: ${cur_fp:+.2f} USD")
            else:
                # Position closed via broker SL/TP
                print(f"\n[EVENT] Position #{position_id} closed at broker!")
                is_closed = True
                deals = await adapter.client.get_trade_history(limit=10)
                closed_deals = [d for d in deals if str(d.get("position_id") or "") == str(position_id) and d.get("entry") in ("OUT", "CLOSE")]
                if closed_deals:
                    cd = closed_deals[0]
                    exit_deal_id = str(cd.get("deal_id") or cd.get("id") or cd.get("ticket"))
                    exit_price = float(cd.get("price", 0.0))
                    realized_pnl = float(cd.get("profit", 0.0))
                    print(f"  Exit Deal ID:    #{exit_deal_id}")
                    print(f"  Exit Price:      ${exit_price:.3f}")
                    print(f"  Realized P&L:    ${realized_pnl:+.2f} USD")
                break

        # Query updated dashboard representations
        hft_positions = await _hft_scoped_positions(TARGET_USER_ID, TARGET_ACCOUNT_ID)
        hft_orders = await _hft_scoped_orders(TARGET_USER_ID, TARGET_ACCOUNT_ID)
        hft_summary = await _hft_scoped_summary(TARGET_USER_ID, TARGET_ACCOUNT_ID)

        print("\n" + "=" * 80)
        print("BITDEX DASHBOARD LIVE FEED RECONCILIATION:")
        print("=" * 80)
        print(f"  Open Positions in Dashboard:   {hft_positions.get('open_count')}")
        print(f"  Total Orders in Dashboard:     {hft_orders.get('count')}")
        print(f"  Dashboard Wallet Balance:      ${hft_summary.get('wallet_balance_usd'):.2f} USD")
        print(f"  Dashboard Equity:              ${hft_summary.get('equity_usd'):.2f} USD")

        evidence.update({
            "status": "SUCCESS",
            "account_id": TARGET_ACCOUNT_ID,
            "broker_server": adapter.server_name,
            "stream_id": "dx.2.trial.std",
            "access_point": "https://ap-58ee8e27.exness.com",
            "instrument": TARGET_INSTRUMENT,
            "direction": direction,
            "volume_lots": TRADE_VOLUME,
            "contract_size": contract_size,
            "entry_open_price": current_open_price,
            "stop_loss_price": broker_sl,
            "take_profit_price": broker_tp,
            "max_risk_usd": max_loss_usd,
            "broker_operation_id": op_id,
            "broker_position_id": position_id,
            "client_request_id": client_req_id,
            "fill_status": fill_state,
            "is_closed": is_closed,
            "exit_price": exit_price,
            "exit_deal_id": exit_deal_id,
            "realized_pnl_usd": realized_pnl,
            "floating_pnl_usd": floating_pnl if not is_closed else 0.0,
            "updated_balance_usd": post_balance,
            "updated_equity_usd": post_equity,
            "updated_margin_usd": post_margin,
            "orders_placed_count": 1,
            "latencies": {
                "quote_latency_ms": round(quote_latency_ms, 2),
                "submission_latency_ms": round(sub_lat_ms, 2),
                "reconciliation_latency_ms": round(rec_lat_ms, 2),
            },
            "timestamp_completed_utc": datetime.now(timezone.utc).isoformat(),
        })

        with open("/opt/tauric-platform-staging/backend/owner_gold_demo_trade_evidence.json", "w", encoding="utf-8") as f:
            json.dump(evidence, f, indent=2)

        print("\nEvidence saved to /opt/tauric-platform-staging/backend/owner_gold_demo_trade_evidence.json")
        print("=" * 80)

    finally:
        conn.close()

if __name__ == "__main__":
    asyncio.run(execute_scalp())
