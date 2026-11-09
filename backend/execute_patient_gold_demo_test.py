#!/usr/bin/env python3
"""
BITDEX — Candidate A Hierarchical Multi-Timeframe XAUUSD Demo Execution Runner (Phase 6)
========================================================================================
Refactored official test runner routed through CentralExecutionRouter & CentralRiskGate.
- Zero execution bypass: all orders pass through CentralRiskGate.
- Strict Candidate A hierarchical strategy (H1 -> M15 -> closed M5 confirmation).
- Dynamic ATR stops and risk-based sizing (no hardcoded SL/TP distances).
- 19 mandatory pre-execution checks and fail-safe Stop Loss verification.
- Persistent account-scoped trading state, consecutive-loss cooldown, and daily drawdown limit.
- One position at a time.
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

sys.path.insert(0, "/opt/tauric-platform-staging/backend")

from app.services.brokers.execution_router import CentralExecutionRouter
from app.services.brokers.central_risk_gate import CentralRiskGate, REAL_TRADING_PERMANENTLY_LOCKED
from app.services.brokers.strategy_candidate_a import CandidateAStrategy
from app.services.brokers.trading_state_manager import TradingStateManager
from app.services.saas_db import get_db_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("bitdex.patient_runner")

DEFAULT_USER_ID = "USR-ADM-B022F490"
DEFAULT_ACCOUNT_ID = "17000660016"
TARGET_INSTRUMENT = "XAUUSD"


async def monitor_position_until_closed(
    adapter: Any,
    position_id: str,
    poll_interval_sec: float = 3.0,
    max_wait_seconds: int = 1800,
) -> Dict[str, Any]:
    """
    Monitors open position strictly until closed at broker side via Stop Loss or Take Profit.
    Removes arbitrary floating profit exits (e.g. cur_fp >= 0.70).
    """
    logger.info(f"Monitoring Position #{position_id} until closed at broker side (Stop Loss / Take Profit)...")
    start_time = time.time()
    last_fp = 0.0

    while (time.time() - start_time) < max_wait_seconds:
        positions = await adapter.get_open_positions()
        pos = next((p for p in positions if str(p.get("position_id", p.get("id", ""))) == str(position_id)), None)

        if not pos:
            logger.info(f"Position #{position_id} has closed at broker side!")
            break

        cur_fp = float(pos.get("unrealized_pnl", pos.get("profit", 0.0)) or 0.0)
        last_fp = cur_fp
        sl = pos.get("sl", pos.get("stop_loss", 0.0))
        tp = pos.get("tp", pos.get("take_profit", 0.0))
        elapsed = int(time.time() - start_time)
        print(f"  [Pos #{position_id} +{elapsed}s] Floating PnL: ${cur_fp:+.2f} USD | SL: {sl} | TP: {tp}")

        await asyncio.sleep(poll_interval_sec)

    # Reconcile closing deal from broker trade history
    await asyncio.sleep(1.0)
    history = await adapter.client.get_trade_history(limit=20)
    close_deal = next(
        (
            d for d in history
            if str(d.get("position_id", "")) == str(position_id)
            and d.get("entry_type", d.get("entry", "")) in ("out", "1", 1)
        ),
        None,
    )
    open_deal = next(
        (
            d for d in history
            if str(d.get("position_id", "")) == str(position_id)
            and d.get("entry_type", d.get("entry", "")) in ("in", "0", 0)
        ),
        None,
    )

    realized_pnl = 0.0
    close_price = 0.0
    close_deal_id = None
    open_deal_id = None

    if close_deal:
        close_deal_id = str(close_deal.get("deal_id", close_deal.get("id", "")))
        prof = close_deal.get("profit")
        if isinstance(prof, dict):
            realized_pnl = float(prof.get("amount", 0.0))
        elif prof is not None:
            realized_pnl = float(prof)
        close_price = float(close_deal.get("price", 0.0))
    else:
        realized_pnl = last_fp

    if open_deal:
        open_deal_id = str(open_deal.get("deal_id", open_deal.get("id", "")))

    duration_s = int(time.time() - start_time)
    logger.info(
        f"Position #{position_id} reconciled: Realized PnL: ${realized_pnl:+.2f} USD "
        f"(Open Deal #{open_deal_id}, Close Deal #{close_deal_id}, Duration: {duration_s}s)"
    )

    return {
        "position_id": position_id,
        "open_deal_id": open_deal_id,
        "close_deal_id": close_deal_id,
        "realized_pnl_usd": round(realized_pnl, 2),
        "close_price": close_price,
        "holding_time_seconds": duration_s,
    }


async def run_controlled_demo_cycle(
    user_id: str,
    account_id: str,
    max_trades: int = 2,
    approved_risk_budget_usd: float = 1.00,
    dry_run: bool = True,
    poll_market_attempts: int = 10,
    poll_spacing_sec: float = 15.0,
) -> Dict[str, Any]:
    """
    Executes a strictly limited Demo validation cycle.
    """
    print("\n" + "=" * 80)
    print("  BITDEX — CONTROLLED CANDIDATE A DEMO VALIDATION ENGINE")
    print("=" * 80)
    print(f"  User ID:                 {user_id}")
    print(f"  Account ID:              {account_id} (DEMO ONLY)")
    print(f"  Instrument:              {TARGET_INSTRUMENT}")
    print(f"  Maximum Trades:          {max_trades} (Sequential)")
    print(f"  Approved Risk Budget:    ${approved_risk_budget_usd:.2f} USD")
    print(f"  Execution Mode:          {'DRY RUN (Simulation)' if dry_run else 'ACTUAL BROKER DEMO EXECUTION'}")
    print(f"  Real Trading Lock:       {REAL_TRADING_PERMANENTLY_LOCKED} (PERMANENTLY LOCKED)")
    print("=" * 80 + "\n")

    conn = get_db_connection()
    try:
        adapter, ctx, doc = CentralExecutionRouter.resolve_adapter_for_customer(conn, user_id, account_id)
        await adapter.verify_ownership_and_environment(user_id)

        executed_trades = []
        trade_count = 0

        for cycle in range(1, poll_market_attempts + 1):
            if trade_count >= max_trades:
                print(f"\n[INFO] Reached authorized maximum trades ({max_trades}). Stopping cycle.")
                break

            print(f"\n>>> [Cycle {cycle}/{poll_market_attempts}] Analyzing live {TARGET_INSTRUMENT} market conditions...")
            
            # Fetch fresh quote and spec
            quote = await adapter.get_live_quote(TARGET_INSTRUMENT)
            spec = await adapter.get_instrument_specification(TARGET_INSTRUMENT)

            # Fetch multi-timeframe completed candles
            h1_c = await adapter.get_historical_candles(TARGET_INSTRUMENT, timeframe="H1", count=30)
            await asyncio.sleep(0.3)
            m15_c = await adapter.get_historical_candles(TARGET_INSTRUMENT, timeframe="M15", count=30)
            await asyncio.sleep(0.3)
            m5_c = await adapter.get_historical_candles(TARGET_INSTRUMENT, timeframe="M5", count=30)

            # Pre-evaluate Candidate A and Central Risk Gate
            pre_eval = await CentralRiskGate.evaluate_full_gate(
                conn=conn,
                adapter=adapter,
                authenticated_user_id=user_id,
                account_id=adapter.account_id,
                symbol=TARGET_INSTRUMENT,
                approved_risk_budget_usd=approved_risk_budget_usd,
                h1_candles=h1_c,
                m15_candles=m15_c,
                m5_candles=m5_c,
                quote=quote,
                spec=spec,
                dry_run=dry_run,
            )

            if not pre_eval.get("passed"):
                err_code = pre_eval.get("error_code")
                detail = pre_eval.get("detail")
                print(f"  [RESULT: NO TRADE] Gate rejected: {err_code}")
                print(f"  [DETAIL] {detail}")
                
                # Check if account in cooldown or daily loss exceeded
                if err_code in ("ERR_COOLDOWN_ACTIVE", "ERR_DAILY_LOSS_LIMIT_REACHED"):
                    print(f"  [HALT] Critical safety gate active ({err_code}). Ceasing validation.")
                    break

                if cycle < poll_market_attempts:
                    print(f"  Waiting {poll_spacing_sec}s for market structure to develop...")
                    await asyncio.sleep(poll_spacing_sec)
                continue

            # A trade setup is qualified!
            order_params = pre_eval["order_parameters"]
            direction = order_params["direction"]
            entry_est = order_params["entry_price"]
            sl_price = order_params["sl_price"]
            tp_price = order_params["tp_price"]
            sl_dist = order_params["sl_distance_pts"]
            tp_dist = order_params["tp_distance_pts"]
            vol = order_params["volume"]
            risk_usd = order_params["total_monetary_risk_usd"]
            atr_m5 = order_params["atr_m5"]
            spread = order_params["spread_pts"]
            fingerprint = pre_eval["setup_fingerprint"]

            print("\n" + "*" * 70)
            print(f"  QUALIFYING CANDIDATE A SETUP IDENTIFIED: {direction}")
            print("*" * 70)
            print(f"  Direction:                 {direction}")
            print(f"  Entry Price:               {entry_est:.3f}")
            print(f"  Stop Loss:                 {sl_price:.3f} (Distance: {sl_dist:.2f} pts = {sl_dist/atr_m5:.2f}x ATR)")
            print(f"  Take Profit:               {tp_price:.3f} (Distance: {tp_dist:.2f} pts, R:R = {order_params['reward_risk_ratio']:.2f})")
            print(f"  Volume:                    {vol} lots")
            print(f"  Spread / Friction:         {spread:.3f} pts")
            print(f"  Estimated Max Risk:        ${risk_usd:.2f} USD (Approved Budget: ${approved_risk_budget_usd:.2f})")
            print(f"  Setup Fingerprint:         {fingerprint}")
            print("*" * 70 + "\n")

            trade_count += 1
            idem_key = f"bitdex-cda-t{trade_count}-{int(time.time())}"

            # Execute order with fail-safe protection
            order_result = await CentralRiskGate.execute_order_with_fail_safe_protection(
                conn=conn,
                adapter=adapter,
                authenticated_user_id=user_id,
                account_id=adapter.account_id,
                symbol=TARGET_INSTRUMENT,
                approved_risk_budget_usd=approved_risk_budget_usd,
                h1_candles=h1_c,
                m15_candles=m15_c,
                m5_candles=m5_c,
                quote=quote,
                spec=spec,
                comment=f"BITDEX-CDA-T{trade_count}",
                idempotency_key=idem_key,
                dry_run=dry_run,
            )

            if not order_result.get("passed"):
                print(f"  [EXECUTION FAILED] Reason: {order_result.get('error_code')} - {order_result.get('detail')}")
                continue

            if dry_run:
                print("  [DRY RUN VERIFIED] Preflight verified successfully with zero broker order placement.")
                executed_trades.append({
                    "trade_number": trade_count,
                    "mode": "DRY_RUN",
                    "direction": direction,
                    "order_parameters": order_params,
                    "result": order_result,
                })
            else:
                pos_id = order_result["position_id"]
                print(f"  [TRADE #{trade_count} EXECUTED] Broker Position ID: #{pos_id}")
                print(f"  [FILL RECONCILED] Execution Price: ${order_result['execution_price']:.3f}")
                print(f"  [PROTECTION CONFIRMED] Exact SL: {order_result['exact_sl']} | Exact TP: {order_result['exact_tp']}")

                # Monitor position until closed
                close_info = await monitor_position_until_closed(adapter, pos_id)
                realized_pnl = close_info["realized_pnl_usd"]

                # Update persistent state manager
                summary_after = await adapter.get_account_summary()
                cur_eq = float(summary_after.get("equity") or summary_after.get("balance") or 5000.0)
                TradingStateManager.record_trade_result(conn, adapter.account_id, realized_pnl, cur_eq)

                if realized_pnl < 0:
                    # Invalidate setup fingerprint after stop out
                    TradingStateManager.invalidate_setup(
                        conn=conn,
                        account_id=adapter.account_id,
                        symbol=TARGET_INSTRUMENT,
                        direction=direction,
                        fingerprint=fingerprint,
                        reason="STOPPED_OUT",
                    )

                trade_record = {
                    "trade_number": trade_count,
                    "account_id": adapter.account_id,
                    "position_id": pos_id,
                    "direction": direction,
                    "volume": vol,
                    "execution_price": order_result["execution_price"],
                    "close_price": close_info["close_price"],
                    "sl": order_result["exact_sl"],
                    "tp": order_result["exact_tp"],
                    "realized_pnl_usd": realized_pnl,
                    "open_deal_id": close_info["open_deal_id"],
                    "close_deal_id": close_info["close_deal_id"],
                    "holding_time_seconds": close_info["holding_time_seconds"],
                    "setup_fingerprint": fingerprint,
                    "strategy_qualification": pre_eval["strategy_evaluation"],
                }
                executed_trades.append(trade_record)

                print(f"  [TRADE #{trade_count} COMPLETED] Realized PnL: ${realized_pnl:+.2f} USD")

            if trade_count < max_trades and not dry_run:
                print("\nWaiting 10 seconds before evaluating second trade setup...")
                await asyncio.sleep(10.0)

        return {
            "status": "COMPLETED",
            "account_id": adapter.account_id,
            "total_trades_executed": len(executed_trades),
            "trades": executed_trades,
            "dry_run": dry_run,
        }
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BITDEX Candidate A Execution Runner")
    parser.add_argument("--user-id", default=DEFAULT_USER_ID, help="Authenticated user ID")
    parser.add_argument("--account-id", default=DEFAULT_ACCOUNT_ID, help="Broker account ID")
    parser.add_argument("--max-trades", type=int, default=2, help="Maximum sequential trades")
    parser.add_argument("--risk-budget", type=float, default=1.00, help="Approved risk budget in USD")
    parser.add_argument("--execute-real-demo", action="store_true", help="Execute real demo trades (not dry run)")
    args = parser.parse_args()

    dry_run = not args.execute_real_demo
    asyncio.run(
        run_controlled_demo_cycle(
            user_id=args.user_id,
            account_id=args.account_id,
            max_trades=args.max_trades,
            approved_risk_budget_usd=args.risk_budget,
            dry_run=dry_run,
        )
    )
