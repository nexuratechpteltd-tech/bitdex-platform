import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from app.services.saas_db import get_db_connection
from app.services.brokers.execution_router import CentralExecutionRouter
from app.services.brokers.central_risk_gate import CentralRiskGate, REAL_TRADING_PERMANENTLY_LOCKED
from app.services.brokers.risk_policy import RiskPolicy, broker_account_stats
from app.services.brokers.trading_state_manager import TradingStateManager
from app.services.brokers.strategy_candidate_a import get_closed_candles

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/tmp/qualified_demo_trade_execution.log", mode="a")
    ]
)
logger = logging.getLogger("QualifiedDemoTradeRunner")

TARGET_INSTRUMENT = "XAUUSD"
USER_ID = "USR-ADM-B022F490"
ACCOUNT_ID = "17000660016"

async def monitor_position_until_settled(adapter, pos_id, timeout_sec=3600):
    logger.info(f"Monitoring open position #{pos_id} until natural settlement (timeout={timeout_sec}s)...")
    start_t = time.time()
    while time.time() - start_t < timeout_sec:
        try:
            positions = await adapter.get_open_positions()
            matched = [p for p in positions if str(p.get("position_id")) == str(pos_id)]
            if not matched:
                logger.info(f"Position #{pos_id} has closed at broker.")
                await asyncio.sleep(2.0)
                history = await adapter.client.get_trade_history(limit=50)
                closed_deals = [
                    d for d in history
                    if str(d.get("deal", {}).get("position_id")) == str(pos_id)
                    and d.get("deal", {}).get("type") == "close"
                ]
                pnl = sum(float(d.get("deal", {}).get("profit", {}).get("amount", 0.0)) for d in closed_deals)
                close_price = float(closed_deals[0].get("deal", {}).get("price", 0.0)) if closed_deals else 0.0
                return {
                    "status": "CLOSED",
                    "realized_pnl_usd": round(pnl, 2),
                    "close_price": close_price,
                    "closed_deals": closed_deals,
                }
            cur_p = matched[0]
            logger.debug(f"Position #{pos_id} still open: current PnL=${cur_p.get('unrealized_pnl')} SL={cur_p.get('sl')} TP={cur_p.get('tp')}")
        except Exception as e:
            logger.error(f"Error checking position #{pos_id}: {e}")
        await asyncio.sleep(5.0)

    logger.warning(f"Position monitoring timed out after {timeout_sec}s.")
    return {"status": "TIMEOUT", "realized_pnl_usd": 0.0, "closed_deals": []}

async def run_monitoring_and_execution_daemon(max_hours=8, poll_interval_sec=20):
    logger.info("=" * 80)
    logger.info("  BITDEX QUALIFIED DEMO TRADE EXECUTION DAEMON (MAX 1 TRADE)")
    logger.info("=" * 80)
    logger.info(f"  Account ID: {ACCOUNT_ID} (DEMO ONLY)")
    logger.info(f"  Target Instrument: {TARGET_INSTRUMENT}")
    logger.info(f"  Permanent Real Lock: {REAL_TRADING_PERMANENTLY_LOCKED}")
    logger.info(f"  Max Runtime: {max_hours} hours | Poll Interval: {poll_interval_sec}s")
    logger.info("=" * 80)

    conn = get_db_connection()
    adapter, ctx, doc = CentralExecutionRouter.resolve_adapter_for_customer(conn, USER_ID, ACCOUNT_ID)
    await adapter.verify_ownership_and_environment(USER_ID)
    policy = RiskPolicy(risk_pct_per_trade=0.25, daily_loss_limit_pct=1.00)

    pre_summary = await adapter.get_account_summary(force_refresh=True)
    start_equity = float(pre_summary.get("equity") or 5000.2)
    start_time_iso = datetime.now(timezone.utc).isoformat()
    start_ts = time.time()
    max_duration_sec = max_hours * 3600

    last_evaluated_m5_time = None
    evaluation_count = 0
    executed_trade_record = None
    rejection_summary = {}

    while (time.time() - start_ts) < max_duration_sec:
        await asyncio.sleep(poll_interval_sec)
        now_ts = time.time()
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        # 1. Fetch fresh multi-timeframe candles
        try:
            h1 = await adapter.get_historical_candles(TARGET_INSTRUMENT, "H1", 100)
            await asyncio.sleep(0.3)
            m15 = await adapter.get_historical_candles(TARGET_INSTRUMENT, "M15", 100)
            await asyncio.sleep(0.3)
            m5 = await adapter.get_historical_candles(TARGET_INSTRUMENT, "M5", 100)
            quote = await adapter.get_live_quote(TARGET_INSTRUMENT)
            spec = await adapter.get_instrument_specification(TARGET_INSTRUMENT)
        except Exception as e:
            logger.error(f"Error fetching market data from Exness: {e}. Waiting next interval...")
            continue

        h1_c = get_closed_candles(h1, now_ts)
        m15_c = get_closed_candles(m15, now_ts)
        m5_c = get_closed_candles(m5, now_ts)

        if not m5_c:
            continue

        latest_closed_m5_time = m5_c[-1]["time"]
        # Rule: Only evaluate when a genuinely new closed M5 bar appears
        if latest_closed_m5_time == last_evaluated_m5_time:
            continue

        last_evaluated_m5_time = latest_closed_m5_time
        evaluation_count += 1

        candle_open_str = datetime.fromtimestamp(latest_closed_m5_time, timezone.utc).strftime("%H:%M:%S UTC")
        bid, ask = float(quote.get("bid") or 0.0), float(quote.get("ask") or 0.0)
        spread = round(ask - bid, 3)

        summary = await adapter.get_account_summary(force_refresh=True)
        equity = float(summary.get("equity") or 5000.2)
        balance = float(summary.get("balance") or equity)
        history = await adapter.client.get_trade_history(limit=500)
        stats = broker_account_stats(history, balance, policy)
        risk_budget = round(equity * policy.risk_pct_per_trade / 100.0, 2)

        logger.info(f"\n>>> [Evaluation #{evaluation_count}] Time: {now_iso} | Closed M5 Bar: {candle_open_str} Close={m5_c[-1]['close']}")
        logger.info(f"    Quote: Bid={bid:.3f} Ask={ask:.3f} Spread={spread:.3f} | Equity: ${equity:.2f} | Dynamic Risk Budget: ${risk_budget:.2f}")

        # Evaluate through CentralRiskGate (checks all 17 gates)
        eval_res = await CentralRiskGate.evaluate_full_gate(
            conn=conn,
            adapter=adapter,
            authenticated_user_id=USER_ID,
            account_id=ACCOUNT_ID,
            symbol=TARGET_INSTRUMENT,
            h1_candles=h1,
            m15_candles=m15,
            m5_candles=m5,
            quote=quote,
            spec=spec,
            dry_run=False,
            policy=policy,
            trade_history=history,
        )

        if not eval_res.get("passed"):
            err_code = eval_res.get("error_code")
            detail = eval_res.get("detail")
            rejection_summary[err_code] = rejection_summary.get(err_code, 0) + 1
            logger.info(f"    [OUTCOME: NO TRADE] Gate rejected: {err_code} - {detail}")

            if err_code in ("ERR_COOLDOWN_ACTIVE", "ERR_DAILY_LOSS_LIMIT_REACHED"):
                logger.warning(f"Critical safety circuit breaker active ({err_code}). Stopping daemon.")
                break
            continue

        # Setup Qualified! Execute maximum ONE trade
        op = eval_res["order_parameters"]
        logger.info("=" * 80)
        logger.info(f"*** GENUINE QUALIFIED SETUP TRIGGERED! ***")
        logger.info(f"Direction: {op['direction']} | Entry Price: {op['entry_price']}")
        logger.info(f"Stop Loss: {op['sl_price']} ({op['sl_distance_pts']:.3f} pts, {op['sl_atr_ratio']}x ATR)")
        logger.info(f"Take Profit: {op['tp_price']} ({op['tp_distance_pts']:.3f} pts)")
        logger.info(f"Volume: {op['volume']} lots | Planned Monetary Risk: ${op['total_monetary_risk_usd']} USD")
        logger.info(f"Expected Net R:R: {op['expected_net_rr']}:1 (Friction: Spread={op['spread_pts']} Slip={op['slippage_pts_budget']})")
        logger.info("=" * 80)

        order_res = await CentralRiskGate.execute_order_with_fail_safe_protection(
            conn=conn,
            adapter=adapter,
            authenticated_user_id=USER_ID,
            account_id=ACCOUNT_ID,
            symbol=TARGET_INSTRUMENT,
            h1_candles=h1,
            m15_candles=m15,
            m5_candles=m5,
            quote=quote,
            spec=spec,
            dry_run=False,
            policy=policy,
        )

        if not order_res.get("passed"):
            logger.error(f"[EXECUTION FAILED] {order_res.get('error_code')}: {order_res.get('detail')}")
            break

        pos_id = order_res["position_id"]
        logger.info(f"[EXECUTION CONFIRMED] Broker Position ID: #{pos_id}")
        logger.info(f"  Execution Price: ${order_res['execution_price']:.3f}")
        logger.info(f"  Broker Confirmed SL: {order_res['broker_sl']} | TP: {order_res['broker_tp']}")
        logger.info(f"  SL Attached at Submission: {order_res['sl_attached_at_submission']}")
        logger.info(f"  Broker Operation ID: {order_res.get('broker_operation_id')}")

        # Monitor position until natural close (SL or TP hit)
        mon_res = await monitor_position_until_settled(adapter, pos_id, timeout_sec=7200)
        realized_pnl = mon_res["realized_pnl_usd"]

        post_summary = await adapter.get_account_summary(force_refresh=True)
        cur_eq = float(post_summary.get("equity") or post_summary.get("balance") or 5000.2)
        TradingStateManager.record_trade_result(conn, ACCOUNT_ID, realized_pnl, cur_eq)

        executed_trade_record = {
            "order_parameters": op,
            "execution_result": order_res,
            "settlement": mon_res,
            "post_trade_equity": cur_eq,
            "realized_pnl_usd": realized_pnl,
        }

        logger.info("=" * 80)
        logger.info(f"TRADE COMPLETED & RECONCILED")
        logger.info(f"  Position ID: #{pos_id}")
        logger.info(f"  Realized P&L: ${realized_pnl:+.2f} USD")
        logger.info(f"  Post-Trade Account Equity: ${cur_eq:.2f} USD")
        logger.info("  Stopping daemon immediately after single completed trade.")
        logger.info("=" * 80)
        break

    post_final_summary = await adapter.get_account_summary(force_refresh=True)
    final_eq = float(post_final_summary.get("equity") or 5000.2)
    end_time_iso = datetime.now(timezone.utc).isoformat()

    full_report = {
        "start_time_utc": start_time_iso,
        "end_time_utc": end_time_iso,
        "total_unique_evaluations": evaluation_count,
        "rejection_summary": rejection_summary,
        "executed_trade": executed_trade_record,
        "initial_equity": start_equity,
        "final_equity": final_eq,
        "total_pnl_usd": round(final_eq - start_equity, 2),
        "real_trading_locked": REAL_TRADING_PERMANENTLY_LOCKED,
    }

    with open("/tmp/qualified_demo_trade_report.json", "w") as f:
        json.dump(full_report, f, indent=2)

    logger.info(f"Daemon finished. Unique evaluations: {evaluation_count}. Trade executed: {bool(executed_trade_record)}.")
    logger.info(f"Evidence report written to /tmp/qualified_demo_trade_report.json")

if __name__ == "__main__":
    asyncio.run(run_monitoring_and_execution_daemon(max_hours=8, poll_interval_sec=20))
