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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ExtendedMarketMonitor")

TARGET_INSTRUMENT = "XAUUSD"
USER_ID = "USR-ADM-B022F490"
ACCOUNT_ID = "17000660016"

async def monitor_open_position(adapter, pos_id, timeout=600):
    logger.info(f"Monitoring open position #{pos_id} until closed (timeout={timeout}s)...")
    start = time.time()
    while time.time() - start < timeout:
        positions = await adapter.get_open_positions()
        match = [p for p in positions if str(p.get("position_id")) == str(pos_id)]
        if not match:
            logger.info(f"Position #{pos_id} has closed.")
            await asyncio.sleep(2.0)
            history = await adapter.client.get_trade_history(limit=50)
            closed_deals = [d for d in history if str(d.get("deal", {}).get("position_id")) == str(pos_id) and d.get("deal", {}).get("type") == "close"]
            pnl = sum(float(d.get("deal", {}).get("profit", {}).get("amount", 0.0)) for d in closed_deals)
            return {"status": "CLOSED", "realized_pnl_usd": round(pnl, 2), "closed_deals": closed_deals}
        await asyncio.sleep(3.0)
    return {"status": "TIMEOUT", "realized_pnl_usd": 0.0, "closed_deals": []}

async def main(max_evaluations=60, poll_seconds=20):
    logger.info("=" * 80)
    logger.info("  BITDEX — EXTENDED MARKET MONITORING & QUALIFIED DEMO TRADE PROTOCOL")
    logger.info("=" * 80)
    logger.info(f"  Account ID: {ACCOUNT_ID} (DEMO ONLY)")
    logger.info(f"  Target Instrument: {TARGET_INSTRUMENT}")
    logger.info(f"  Permanent Real Lock: {REAL_TRADING_PERMANENTLY_LOCKED}")
    logger.info("=" * 80)

    conn = get_db_connection()
    adapter, ctx, doc = CentralExecutionRouter.resolve_adapter_for_customer(conn, USER_ID, ACCOUNT_ID)
    await adapter.verify_ownership_and_environment(USER_ID)
    policy = RiskPolicy(risk_pct_per_trade=0.25, daily_loss_limit_pct=1.00)

    pre_summary = await adapter.get_account_summary(force_refresh=True)
    start_equity = float(pre_summary.get("equity") or 5000.2)
    start_time_iso = datetime.now(timezone.utc).isoformat()
    logger.info(f"Start Time: {start_time_iso} | Initial Equity: ${start_equity:.2f}")

    unique_evaluations = []
    last_m5_candle_time = None
    executed_trade = None
    rejection_stats = {}

    eval_count = 0
    while eval_count < max_evaluations:
        await asyncio.sleep(poll_seconds)
        now_ts = time.time()
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        # 1. Fetch multi-timeframe candles
        try:
            h1 = await adapter.get_historical_candles(TARGET_INSTRUMENT, "H1", 100)
            await asyncio.sleep(0.3)
            m15 = await adapter.get_historical_candles(TARGET_INSTRUMENT, "M15", 100)
            await asyncio.sleep(0.3)
            m5 = await adapter.get_historical_candles(TARGET_INSTRUMENT, "M5", 100)
            quote = await adapter.get_live_quote(TARGET_INSTRUMENT)
            spec = await adapter.get_instrument_specification(TARGET_INSTRUMENT)
        except Exception as e:
            logger.error(f"Broker market data fetch failed: {e}. Retrying...")
            continue

        h1_c = get_closed_candles(h1, now_ts)
        m15_c = get_closed_candles(m15, now_ts)
        m5_c = get_closed_candles(m5, now_ts)

        if not m5_c:
            logger.warning("No closed M5 candles received. Retrying...")
            continue

        current_m5_time = m5_c[-1]["time"]
        # Rule 8: Do not repeatedly count the same candle snapshot as a new independent evaluation
        is_new_candle = (current_m5_time != last_m5_candle_time)
        if not is_new_candle:
            # Same candle snapshot; wait for new closed candle
            continue

        last_m5_candle_time = current_m5_time
        eval_count += 1

        candle_time_str = datetime.fromtimestamp(current_m5_time, timezone.utc).strftime("%H:%M:%S UTC")
        bid, ask = float(quote.get("bid") or 0.0), float(quote.get("ask") or 0.0)
        spread = round(ask - bid, 3)

        summary = await adapter.get_account_summary(force_refresh=True)
        equity = float(summary.get("equity") or 5000.2)
        balance = float(summary.get("balance") or equity)
        history = await adapter.client.get_trade_history(limit=500)
        stats = broker_account_stats(history, balance, policy)
        risk_budget = round(equity * policy.risk_pct_per_trade / 100.0, 2)

        logger.info(f"\n--- [Evaluation #{eval_count}/{max_evaluations}] Time: {now_iso} ---")
        logger.info(f"Latest Closed M5 Candle Open: {candle_time_str} | Close: {m5_c[-1]['close']}")
        logger.info(f"Live Quote: Bid={bid:.3f} Ask={ask:.3f} Spread={spread:.3f} | Equity: ${equity:.2f} | Risk Budget (0.25%): ${risk_budget:.2f}")

        # Evaluate CentralRiskGate
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

        record = {
            "evaluation_index": eval_count,
            "timestamp_utc": now_iso,
            "m5_candle_open_utc": candle_time_str,
            "m5_close_price": m5_c[-1]["close"],
            "bid": bid,
            "ask": ask,
            "spread": spread,
            "equity": equity,
            "risk_budget_usd": risk_budget,
            "passed": eval_res.get("passed", False),
            "error_code": eval_res.get("error_code"),
            "detail": eval_res.get("detail"),
        }
        unique_evaluations.append(record)

        if not eval_res.get("passed"):
            code = eval_res.get("error_code")
            det = eval_res.get("detail")
            rejection_stats[code] = rejection_stats.get(code, 0) + 1
            logger.info(f"[OUTCOME: NO TRADE] Gate rejected: {code} - {det}")

            if code in ("ERR_COOLDOWN_ACTIVE", "ERR_DAILY_LOSS_LIMIT_REACHED"):
                logger.warning(f"Critical safety circuit breaker tripped ({code}). Stopping monitoring.")
                break
            continue

        # Setup Qualified! Execute maximum ONE trade
        op = eval_res["order_parameters"]
        logger.info(f"\n*** [GENUINE SETUP QUALIFIED!] ***")
        logger.info(f"Direction: {op['direction']} | Entry: {op['entry_price']} | SL: {op['sl_price']} | TP: {op['tp_price']}")
        logger.info(f"Volume: {op['volume']} | Planned Risk: ${op['total_monetary_risk_usd']} | Net R:R: {op['expected_net_rr']}")

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
        logger.info(f"Order Executed! Broker Position ID: #{pos_id}")
        logger.info(f"SL attached at submission: {order_res['sl_attached_at_submission']}")
        logger.info(f"Confirmed broker SL: {order_res['broker_sl']} | TP: {order_res['broker_tp']}")

        # Monitor position until closed
        mon = await monitor_open_position(adapter, pos_id, timeout=600)
        pnl = mon["realized_pnl_usd"]
        post_sum = await adapter.get_account_summary(force_refresh=True)
        cur_eq = float(post_sum.get("equity") or post_sum.get("balance") or 5000.2)
        TradingStateManager.record_trade_result(conn, ACCOUNT_ID, pnl, cur_eq)

        executed_trade = {
            "order_parameters": op,
            "execution_result": order_res,
            "settlement": mon,
            "post_trade_equity": cur_eq,
        }
        logger.info(f"Trade settled! Realized P&L: ${pnl:+.2f} USD. New Equity: ${cur_eq:.2f} USD")
        logger.info("Stopping runner immediately after single completed trade.")
        break

    post_summary = await adapter.get_account_summary(force_refresh=True)
    end_time_iso = datetime.now(timezone.utc).isoformat()
    end_equity = float(post_summary.get("equity") or 5000.2)

    final_report = {
        "monitoring_start_utc": start_time_iso,
        "monitoring_end_utc": end_time_iso,
        "session": "London / New York Transition",
        "total_unique_evaluations": len(unique_evaluations),
        "rejection_statistics": rejection_stats,
        "executed_trade": executed_trade,
        "initial_equity": start_equity,
        "final_equity": end_equity,
        "pnl_usd": round(end_equity - start_equity, 2),
        "evaluations_log": unique_evaluations,
    }

    with open("/tmp/extended_market_monitoring_result.json", "w") as f:
        json.dump(final_report, f, indent=2)

    logger.info("=" * 80)
    logger.info(f"MONITORING COMPLETE. Unique Evaluations: {len(unique_evaluations)}")
    logger.info(f"Rejection Statistics: {rejection_stats}")
    logger.info(f"Trade Executed: {bool(executed_trade)}")
    logger.info("=" * 80)

asyncio.run(main(max_evaluations=12, poll_seconds=20))
