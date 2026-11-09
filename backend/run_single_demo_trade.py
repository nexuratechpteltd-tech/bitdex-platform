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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SingleDemoTradeValidation")

TARGET_INSTRUMENT = "XAUUSD"
USER_ID = "USR-ADM-B022F490"
ACCOUNT_ID = "17000660016"

async def monitor_position(adapter, pos_id, timeout=600):
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

async def main():
    logger.info("=" * 80)
    logger.info("  STARTING BITDEX SINGLE-TRADE DEMO VALIDATION PROTOCOL (MAX 1 TRADE)")
    logger.info("=" * 80)
    
    conn = get_db_connection()
    adapter, ctx, doc = CentralExecutionRouter.resolve_adapter_for_customer(conn, USER_ID, ACCOUNT_ID)
    await adapter.verify_ownership_and_environment(USER_ID)
    
    policy = RiskPolicy(risk_pct_per_trade=0.25, daily_loss_limit_pct=1.00)
    executed_trade = None
    cycles = 0
    max_cycles = 15  # observation window of 15 cycles (~3.5 minutes)
    
    pre_summary = await adapter.get_account_summary(force_refresh=True)
    logger.info(f"Initial Account: Balance=${pre_summary.get('balance')} Equity=${pre_summary.get('equity')} Free=${pre_summary.get('free_margin')}")
    
    while cycles < max_cycles:
        cycles += 1
        logger.info(f"\n--- [Cycle {cycles}/{max_cycles}] Checking market conditions for XAUUSD ---")
        
        summary = await adapter.get_account_summary(force_refresh=True)
        equity = float(summary.get('equity') or 5000.0)
        balance = float(summary.get('balance') or equity)
        quote = await adapter.get_live_quote(TARGET_INSTRUMENT)
        spec = await adapter.get_instrument_specification(TARGET_INSTRUMENT)
        
        h1 = await adapter.get_historical_candles(TARGET_INSTRUMENT, 'H1', 100)
        await asyncio.sleep(0.3)
        m15 = await adapter.get_historical_candles(TARGET_INSTRUMENT, 'M15', 100)
        await asyncio.sleep(0.3)
        m5 = await adapter.get_historical_candles(TARGET_INSTRUMENT, 'M5', 100)
        history = await adapter.client.get_trade_history(limit=500)
        
        stats = broker_account_stats(history, balance, policy)
        risk_budget = round(equity * policy.risk_pct_per_trade / 100.0, 2)
        logger.info(f"Live Equity: ${equity:.2f} | Dynamic Risk Budget (0.25%): ${risk_budget:.2f} | Daily Loss Ceiling: -${stats['daily_loss_limit_usd']:.2f}")
        logger.info(f"Bid: {quote['bid']} Ask: {quote['ask']} Spread: {quote['ask']-quote['bid']:.3f}")
        
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
        
        if not eval_res.get("passed"):
            code = eval_res.get("error_code")
            det = eval_res.get("detail")
            logger.info(f"[OUTCOME: NO TRADE] Gate rejected: {code} - {det}")
            if code in ("ERR_COOLDOWN_ACTIVE", "ERR_DAILY_LOSS_LIMIT_REACHED"):
                logger.warning(f"Critical safety limit reached ({code}). Stopping.")
                break
            await asyncio.sleep(12.0)
            continue
            
        # If passed, execute strictly ONE trade
        op = eval_res["order_parameters"]
        logger.info("\n*** [SINGLE DEMO TRADE QUALIFIED] ***")
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
        
        # Monitor until closed
        mon = await monitor_position(adapter, pos_id, timeout=600)
        pnl = mon["realized_pnl_usd"]
        post_sum = await adapter.get_account_summary(force_refresh=True)
        cur_eq = float(post_sum.get("equity") or post_sum.get("balance") or 5000.0)
        TradingStateManager.record_trade_result(conn, ACCOUNT_ID, pnl, cur_eq)
        
        executed_trade = {
            "order_parameters": op,
            "execution_result": order_res,
            "settlement": mon,
            "post_trade_equity": cur_eq,
        }
        logger.info(f"Single trade settled with realized P&L: ${pnl:+.2f} USD. Post-trade equity: ${cur_eq:.2f} USD")
        logger.info("Stopping runner immediately after single completed trade.")
        break

    post_summary = await adapter.get_account_summary(force_refresh=True)
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "account_id": ACCOUNT_ID,
        "initial_summary": pre_summary,
        "final_summary": post_summary,
        "total_trades_completed": 1 if executed_trade else 0,
        "trade": executed_trade,
        "cycles_evaluated": cycles,
        "real_trading_locked": REAL_TRADING_PERMANENTLY_LOCKED,
    }
    with open("/tmp/single_demo_trade_result.json", "w") as f:
        json.dump(report, f, indent=2)
    logger.info(f"\nProtocol completed. Trade executed: {bool(executed_trade)}. Evidence saved to /tmp/single_demo_trade_result.json")

asyncio.run(main())
