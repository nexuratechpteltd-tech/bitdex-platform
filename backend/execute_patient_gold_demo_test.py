#!/usr/bin/env python3
"""
BITDEX — Candidate A Dynamic Percentage-Based Demo Execution Runner (v2)
========================================================================
- Percentage-based risk policy (0.25% of current account equity per trade).
- 1.0% daily realized-loss ceiling based on day-start equity.
- Recalculates monetary budget from live broker equity before every trade.
- Derives volume from broker specs (tick_size/tick_value), SL distance and transaction costs.
- Enforces Candidate A's ATR/swing stop (never artificially tightened).
- Target: prefers 2:1 net R:R, accepts 1.5:1 floor when market structure allows.
- Zero execution bypass: passes through CentralExecutionRouter & CentralRiskGate.
- Broker-derived daily-loss and consecutive-loss cooldown.
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
from app.services.brokers.risk_policy import RiskPolicy, broker_account_stats
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
    """
    logger.info(f"Monitoring Position #{position_id} until closed at broker side (Stop Loss / Take Profit)...")
    start_time = time.time()
    last_fp = 0.0

    while (time.time() - start_time) < max_wait_seconds:
        positions = await adapter.get_open_positions()
        pos = next((p for p in positions if str(p.get("position_id") or p.get("id")) == str(position_id)), None)

        if not pos:
            logger.info(f"Position #{position_id} has closed at broker side!")
            break

        cur_fp = float(pos.get("unrealized_pnl") or pos.get("profit") or 0.0)
        last_fp = cur_fp
        sl = pos.get("sl") or pos.get("stop_loss_price")
        tp = pos.get("tp") or pos.get("take_profit_price")
        elapsed = int(time.time() - start_time)
        print(f"  [Pos #{position_id} +{elapsed}s] Floating PnL: ${cur_fp:+.2f} USD | SL: {sl} | TP: {tp}")

        await asyncio.sleep(poll_interval_sec)

    # Reconcile closing deal from broker trade history
    await asyncio.sleep(1.5)
    history = await adapter.client.get_trade_history(limit=50)
    deals = []
    for h in history or []:
        d = h.get("deal", h) if isinstance(h, dict) else None
        if isinstance(d, dict):
            deals.append(d)

    close_deal = next(
        (
            d for d in deals
            if str(d.get("position_id", "")) == str(position_id)
            and str(d.get("type", "")).lower() == "close"
        ),
        None,
    )
    open_deal = next(
        (
            d for d in deals
            if str(d.get("position_id", "")) == str(position_id)
            and str(d.get("type", "")).lower() == "open"
        ),
        None,
    )

    realized_pnl = 0.0
    close_price = 0.0
    close_deal_id = None
    open_deal_id = None

    if close_deal:
        close_deal_id = str(close_deal.get("deal_id") or close_deal.get("id", ""))
        prof = close_deal.get("profit")
        if isinstance(prof, dict):
            realized_pnl = float(prof.get("amount", 0.0))
        elif prof is not None:
            realized_pnl = float(prof)
        close_price = float(close_deal.get("price", 0.0))
    else:
        realized_pnl = last_fp

    if open_deal:
        open_deal_id = str(open_deal.get("deal_id") or open_deal.get("id", ""))

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
    risk_pct_per_trade: float = 0.25,
    daily_loss_limit_pct: float = 1.00,
    dry_run: bool = True,
    poll_market_attempts: int = 15,
    poll_spacing_sec: float = 12.0,
) -> Dict[str, Any]:
    """
    Executes a strictly limited Demo validation cycle under the percentage risk policy.
    """
    policy = RiskPolicy(
        risk_pct_per_trade=risk_pct_per_trade,
        daily_loss_limit_pct=daily_loss_limit_pct,
    )

    print("\n" + "=" * 80)
    print("  BITDEX — CANDIDATE A DYNAMIC PERCENTAGE-BASED RISK RUNNER")
    print("=" * 80)
    print(f"  User ID:                 {user_id}")
    print(f"  Account ID:              {account_id} (DEMO ONLY)")
    print(f"  Instrument:              {TARGET_INSTRUMENT}")
    print(f"  Max Sequential Trades:   {max_trades}")
    print(f"  Risk Policy:             {policy.risk_pct_per_trade}% of current live equity per trade")
    print(f"  Daily Realized Ceiling:  {policy.daily_loss_limit_pct}% of day's starting equity")
    print(f"  Min Net R:R:             {policy.min_net_rr}:1 (preferred: {policy.preferred_net_rr}:1)")
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

            print(f"\n>>> [Cycle {cycle}/{poll_market_attempts}] Evaluating live {TARGET_INSTRUMENT} market...")

            # 1. Fetch fresh account summary to dynamically recalculate monetary budget
            summary = await adapter.get_account_summary(force_refresh=True)
            equity = float(summary.get("equity") or summary.get("balance") or 5000.0)
            balance = float(summary.get("balance") or equity)
            monetary_budget = round(equity * policy.risk_pct_per_trade / 100.0, 2)
            print(f"  Account Equity:          ${equity:.2f} USD (Balance: ${balance:.2f} USD)")
            print(f"  Calculated Risk Budget:  ${monetary_budget:.2f} USD ({policy.risk_pct_per_trade}% of equity)")

            # 2. Fetch fresh quote and spec
            quote = await adapter.get_live_quote(TARGET_INSTRUMENT)
            spec = await adapter.get_instrument_specification(TARGET_INSTRUMENT)

            # 3. Fetch multi-timeframe candles (count=100 ensures enough closed bars for EMA50)
            h1_c = await adapter.get_historical_candles(TARGET_INSTRUMENT, timeframe="H1", count=100)
            await asyncio.sleep(0.4)
            m15_c = await adapter.get_historical_candles(TARGET_INSTRUMENT, timeframe="M15", count=100)
            await asyncio.sleep(0.4)
            m5_c = await adapter.get_historical_candles(TARGET_INSTRUMENT, timeframe="M5", count=100)

            # 4. Fetch trade history for broker-derived daily stats
            trade_history = await adapter.client.get_trade_history(limit=500)
            stats = broker_account_stats(trade_history, balance, policy)
            print(f"  Today's Realized P&L:    ${stats['today_realized_pnl_usd']:+.2f} USD (Day-start: ${stats['day_start_balance_usd']:.2f})")
            print(f"  Daily Loss Ceiling:      -${stats['daily_loss_limit_usd']:.2f} USD ({policy.daily_loss_limit_pct}% of day-start)")
            print(f"  Consecutive Losses:      {stats['trailing_consecutive_losses']} (Cooldown Active: {stats['cooldown_active']})")

            # 5. Pre-evaluate through CentralRiskGate
            pre_eval = await CentralRiskGate.evaluate_full_gate(
                conn=conn,
                adapter=adapter,
                authenticated_user_id=user_id,
                account_id=adapter.account_id,
                symbol=TARGET_INSTRUMENT,
                h1_candles=h1_c,
                m15_candles=m15_c,
                m5_candles=m5_c,
                quote=quote,
                spec=spec,
                dry_run=dry_run,
                policy=policy,
                trade_history=trade_history,
            )

            if not pre_eval.get("passed"):
                err_code = pre_eval.get("error_code")
                detail = pre_eval.get("detail")
                print(f"  [RESULT: NO TRADE] Gate rejected: {err_code}")
                print(f"  [DETAIL] {detail}")

                if err_code in ("ERR_COOLDOWN_ACTIVE", "ERR_DAILY_LOSS_LIMIT_REACHED"):
                    print(f"  [HALT] Critical safety limit active ({err_code}). Stopping validation.")
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
            net_rr = order_params["expected_net_rr"]
            target_rr = order_params["target_rr_selected"]
            fingerprint = pre_eval["setup_fingerprint"]

            print("\n" + "*" * 75)
            print(f"  QUALIFYING CANDIDATE A SETUP IDENTIFIED: {direction}")
            print("*" * 75)
            print(f"  Direction:                 {direction}")
            print(f"  Current Live Equity:       ${equity:.2f} USD")
            print(f"  Risk Budget ({policy.risk_pct_per_trade}%):       ${monetary_budget:.2f} USD")
            print(f"  Entry Price:               {entry_est:.3f}")
            print(f"  Stop Loss:                 {sl_price:.3f} (Distance: {sl_dist:.3f} pts = {order_params['sl_atr_ratio']:.2f}x ATR)")
            print(f"  Take Profit:               {tp_price:.3f} (Distance: {tp_dist:.3f} pts, Target R:R: {target_rr}:1)")
            print(f"  Expected Net R:R:          {net_rr:.2f}:1 (after spread & slippage)")
            print(f"  Position Lot Size:         {vol} lots (rounded down to step)")
            print(f"  Spread / Friction:         {spread:.3f} pts")
            print(f"  Planned Monetary Loss:     ${risk_usd:.2f} USD ({round(risk_usd/equity*100, 3)}% of equity)")
            print(f"  Expected Net Reward:       ${order_params['expected_net_reward_usd']:.2f} USD")
            print(f"  Setup Fingerprint:         {fingerprint}")
            print("*" * 75 + "\n")

            trade_count += 1
            idem_key = f"bitdex-cda-dyn-{trade_count}-{int(time.time())}"

            # Execute order with fail-safe protection
            order_result = await CentralRiskGate.execute_order_with_fail_safe_protection(
                conn=conn,
                adapter=adapter,
                authenticated_user_id=user_id,
                account_id=adapter.account_id,
                symbol=TARGET_INSTRUMENT,
                h1_candles=h1_c,
                m15_candles=m15_c,
                m5_candles=m5_c,
                quote=quote,
                spec=spec,
                comment=f"BITDEX-CDA-T{trade_count}",
                idempotency_key=idem_key,
                dry_run=dry_run,
                policy=policy,
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
                print(f"  [PROTECTION CONFIRMED] Broker SL: {order_result['broker_sl']} | Broker TP: {order_result['broker_tp']}")
                print(f"  [SL ATTACHED AT SUBMISSION] {order_result['sl_attached_at_submission']}")

                # Monitor position until closed
                close_info = await monitor_position_until_closed(adapter, pos_id)
                realized_pnl = close_info["realized_pnl_usd"]

                # Update persistent state manager
                summary_after = await adapter.get_account_summary(force_refresh=True)
                cur_eq = float(summary_after.get("equity") or summary_after.get("balance") or 5000.0)
                TradingStateManager.record_trade_result(conn, adapter.account_id, realized_pnl, cur_eq)

                if realized_pnl < 0:
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
                    "sl": order_result["broker_sl"],
                    "tp": order_result["broker_tp"],
                    "realized_pnl_usd": realized_pnl,
                    "planned_loss_usd": risk_usd,
                    "open_deal_id": close_info["open_deal_id"],
                    "close_deal_id": close_info["close_deal_id"],
                    "holding_time_seconds": close_info["holding_time_seconds"],
                    "setup_fingerprint": fingerprint,
                    "strategy_qualification": pre_eval["strategy_evaluation"],
                }
                executed_trades.append(trade_record)
                print(f"  [TRADE #{trade_count} COMPLETED] Realized PnL: ${realized_pnl:+.2f} USD (Planned Risk: ${risk_usd:.2f})")

            if trade_count < max_trades and not dry_run:
                print("\nWaiting 10 seconds before evaluating second trade setup...")
                await asyncio.sleep(10.0)

        return {
            "status": "COMPLETED",
            "account_id": adapter.account_id,
            "total_trades_executed": len(executed_trades),
            "trades": executed_trades,
            "dry_run": dry_run,
            "policy": policy.to_dict(),
        }
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BITDEX Candidate A Dynamic Percentage-Based Runner")
    parser.add_argument("--user-id", default=DEFAULT_USER_ID, help="Authenticated user ID")
    parser.add_argument("--account-id", default=DEFAULT_ACCOUNT_ID, help="Broker account ID")
    parser.add_argument("--max-trades", type=int, default=2, help="Maximum sequential trades")
    parser.add_argument("--risk-pct", type=float, default=0.25, help="Risk percentage of equity (default: 0.25 pct)")
    parser.add_argument("--daily-limit-pct", type=float, default=1.00, help="Daily loss ceiling pct (default: 1.00 pct)")
    parser.add_argument("--poll-interval", type=int, default=10, help="Seconds between market evaluations (default: 10)")
    parser.add_argument("--max-wait", type=int, default=1800, help="Maximum seconds to wait for a setup (default: 1800)")
    parser.add_argument("--execute-real-demo", action="store_true", help="Execute real demo trades (not dry run)")
    args = parser.parse_args()

    dry_run = not args.execute_real_demo
    poll_attempts = max(1, int(args.max_wait / max(1, args.poll_interval)))
    asyncio.run(
        run_controlled_demo_cycle(
            user_id=args.user_id,
            account_id=args.account_id,
            max_trades=args.max_trades,
            risk_pct_per_trade=args.risk_pct,
            daily_loss_limit_pct=args.daily_limit_pct,
            dry_run=dry_run,
            poll_market_attempts=poll_attempts,
            poll_spacing_sec=float(args.poll_interval),
        )
    )
