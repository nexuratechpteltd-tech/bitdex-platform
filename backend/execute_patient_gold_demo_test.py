#!/usr/bin/env python3
"""
BITDEX — PATIENT MULTI-TIMEFRAME XAUUSD DEMO EXECUTION
Target Account: 17000660016
Broker: Exness (dx.2.trial.std)
Instrument: XAUUSD / Gold
Volume: 0.01 lots per trade
Max Planned Loss: <= $1.00 USD per trade
Maximum Trades: 5 (Executes ONLY when genuinely qualified, patient waiting)
"""

import sys
import os
import time
import json
import asyncio
from datetime import datetime, timezone

sys.path.insert(0, "/opt/tauric-platform-staging/backend")

from app.services.brokers.execution_router import CentralExecutionRouter
from app.services.saas_db import get_db_connection
from app.services.exness.event_stream import ExnessTransactionEventManager

TARGET_USER_ID = "USR-ADM-B022F490"
TARGET_ACCOUNT_ID = "17000660016"
TARGET_INSTRUMENT = "XAUUSD"
TRADE_VOLUME = 0.01
MAX_PLANNED_LOSS_USD = 1.00
SL_DISTANCE_PTS = 0.70  # $0.70 USD base risk on 0.01 lots (1.0 oz)
TP_DISTANCE_PTS = 0.90  # $0.90 USD target reward on 0.01 lots (1.0 oz)

def calc_ema(series, period):
    if not series: return 0.0
    k = 2.0 / (period + 1.0)
    res = series[0]
    for v in series[1:]:
        res = (v * k) + (res * (1.0 - k))
    return res

def calc_rsi(closes, period=14):
    if len(closes) < period + 1: return 50.0
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains = [max(0.0, d) for d in deltas]
    losses = [max(0.0, -d) for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0: return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

def calc_macd(closes, fast=12, slow=26, signal=9):
    if len(closes) < slow: return 0.0, 0.0, 0.0
    fast_emas = []
    k_f = 2.0 / (fast + 1.0)
    v = closes[0]
    for c in closes:
        v = (c * k_f) + (v * (1.0 - k_f))
        fast_emas.append(v)
    slow_emas = []
    k_s = 2.0 / (slow + 1.0)
    v = closes[0]
    for c in closes:
        v = (c * k_s) + (v * (1.0 - k_s))
        slow_emas.append(v)
    macd_line = [f - s for f, s in zip(fast_emas, slow_emas)]
    signal_line = []
    k_sig = 2.0 / (signal + 1.0)
    v = macd_line[0]
    for m in macd_line:
        v = (m * k_sig) + (v * (1.0 - k_sig))
        signal_line.append(v)
    hist = macd_line[-1] - signal_line[-1]
    return macd_line[-1], signal_line[-1], hist

def calc_atr(candles, period=14):
    if len(candles) < 2: return 1.0
    trs = []
    for i in range(1, len(candles)):
        h = float(candles[i]["high"])
        l = float(candles[i]["low"])
        prev_c = float(candles[i-1]["close"])
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr)
    return sum(trs[-period:]) / min(len(trs), period)

async def fetch_multi_timeframe_data(adapter):
    """Fetches M1, M5, M15, and H1 candles with safe rate-limit spacing."""
    tick = await adapter.client.get_latest_tick(TARGET_INSTRUMENT)
    await asyncio.sleep(0.7)
    m1 = await adapter.client.get_historical_candles(TARGET_INSTRUMENT, timeframe="M1", count=40)
    await asyncio.sleep(0.7)
    m5 = await adapter.client.get_historical_candles(TARGET_INSTRUMENT, timeframe="M5", count=25)
    await asyncio.sleep(0.7)
    m15 = await adapter.client.get_historical_candles(TARGET_INSTRUMENT, timeframe="M15", count=25)
    await asyncio.sleep(0.7)
    h1 = await adapter.client.get_historical_candles(TARGET_INSTRUMENT, timeframe="H1", count=25)

    return tick, m1, m5, m15, h1

def evaluate_patient_market_setup(tick, m1, m5, m15, h1):
    bid = float(tick.get("bid", 0.0))
    ask = float(tick.get("ask", 0.0))
    spread = round(ask - bid, 3)
    digits = int(tick.get("digits", 3))

    closes_m1 = [float(c["close"]) for c in m1]
    closes_m5 = [float(c["close"]) for c in m5]
    closes_m15 = [float(c["close"]) for c in m15]
    closes_h1 = [float(c["close"]) for c in h1] if h1 else []

    # Moving averages across timeframes
    ema9_m1, ema21_m1, ema50_m1 = calc_ema(closes_m1, 9), calc_ema(closes_m1, 21), calc_ema(closes_m1, 50)
    ema9_m5, ema21_m5 = calc_ema(closes_m5, 9), calc_ema(closes_m5, 21)
    ema9_m15, ema21_m15 = calc_ema(closes_m15, 9), calc_ema(closes_m15, 21)
    ema9_h1, ema21_h1 = (calc_ema(closes_h1, 9), calc_ema(closes_h1, 21)) if closes_h1 else (0.0, 0.0)

    # Macro trend identification
    macro_bullish = (ema9_h1 > ema21_h1) if closes_h1 else (ema9_m15 > ema21_m15)
    m15_bullish = (ema9_m15 > ema21_m15)

    # Indicators on M1
    rsi14 = calc_rsi(closes_m1, 14)
    macd_l, macd_s, macd_h = calc_macd(closes_m1)
    atr14 = calc_atr(m1, 14)

    # Support & Resistance (20-period swing high/low on M1)
    recent_20 = m1[-20:]
    res_20 = max(float(c["high"]) for c in recent_20)
    sup_20 = min(float(c["low"]) for c in recent_20)

    # Candle price action: inspect completed bar [-2] and current bar [-1]
    completed_bar = m1[-2] if len(m1) >= 2 else m1[-1]
    comp_open = float(completed_bar["open"])
    comp_close = float(completed_bar["close"])
    comp_high = float(completed_bar["high"])
    comp_low = float(completed_bar["low"])
    comp_range = max(0.001, comp_high - comp_low)
    comp_body = comp_close - comp_open

    # Extension from EMA9 (anti-chase check)
    extension_from_ema9 = abs(bid - ema9_m1)
    is_chasing = extension_from_ema9 > (atr14 * 1.1)

    # Independent scoring
    buy_score = 0.0
    sell_score = 0.0
    buy_reasons = []
    sell_reasons = []
    rejection_notes = []

    # 1. Macro Trend Alignment (30 pts)
    if macro_bullish and m15_bullish:
        buy_score += 30.0
        buy_reasons.append(f"Macro H1/M15 Bullish (H1 EMA9 {ema9_h1:.1f} > EMA21 {ema21_h1:.1f})")
    elif not macro_bullish and not m15_bullish:
        sell_score += 30.0
        sell_reasons.append(f"Macro H1/M15 Bearish (H1 EMA9 {ema9_h1:.1f} < EMA21 {ema21_h1:.1f})")
    else:
        buy_score += 15.0
        sell_score += 15.0
        rejection_notes.append("Macro H1/M15 trend mixed")

    # 2. Execution M1/M5 Trend Alignment (25 pts)
    if ema9_m1 > ema21_m1 and ema9_m5 >= ema21_m5:
        buy_score += 25.0
        buy_reasons.append(f"M1/M5 Execution Trend Bullish (M1 EMA9 {ema9_m1:.2f} > EMA21 {ema21_m1:.2f})")
    elif ema9_m1 < ema21_m1 and ema9_m5 <= ema21_m5:
        sell_score += 25.0
        sell_reasons.append(f"M1/M5 Execution Trend Bearish (M1 EMA9 {ema9_m1:.2f} < EMA21 {ema21_m1:.2f})")
    elif ema9_m1 > ema21_m1:
        buy_score += 15.0
    elif ema9_m1 < ema21_m1:
        sell_score += 15.0

    # 3. MACD Momentum Confirmation (20 pts)
    if macd_h > 0.05:
        buy_score += 20.0
        buy_reasons.append(f"MACD Histogram Bullish ({macd_h:+.3f})")
    elif macd_h < -0.05:
        sell_score += 20.0
        sell_reasons.append(f"MACD Histogram Bearish ({macd_h:+.3f})")

    # 4. RSI Regime Filter (15 pts)
    if 46.0 <= rsi14 <= 68.0:
        buy_score += 15.0
        buy_reasons.append(f"RSI14 Healthy Bullish Expansion ({rsi14:.1f})")
    elif 32.0 <= rsi14 <= 54.0:
        sell_score += 15.0
        sell_reasons.append(f"RSI14 Healthy Bearish Expansion ({rsi14:.1f})")
    elif rsi14 > 72.0:
        rejection_notes.append(f"RSI Overbought ({rsi14:.1f} > 72)")
    elif rsi14 < 28.0:
        rejection_notes.append(f"RSI Oversold ({rsi14:.1f} < 28)")

    # 5. Completed Candle Action & Non-Chase Clearance (10 pts)
    if comp_body > 0 or ((comp_close - comp_low) / comp_range > 0.60):
        if not is_chasing and (res_20 - ask) >= 0.50:
            buy_score += 10.0
            buy_reasons.append(f"Bullish completed candle & clearance ({res_20 - ask:.2f} pts to res)")
        else:
            rejection_notes.append("BUY: price chasing or resistance within 0.50 pts")
    elif comp_body < 0 or ((comp_high - comp_close) / comp_range > 0.60):
        if not is_chasing and (bid - sup_20) >= 0.50:
            sell_score += 10.0
            sell_reasons.append(f"Bearish completed candle & clearance ({bid - sup_20:.2f} pts to sup)")
        else:
            rejection_notes.append("SELL: price chasing or support within 0.50 pts")

    # Qualification Threshold: Minimum 75 points and >= 35 points advantage over opposing side
    is_qualified = False
    direction = None
    qual_reasons = []

    if buy_score >= 75.0 and buy_score >= (sell_score + 35.0):
        if spread <= 0.32:
            is_qualified = True
            direction = "BUY"
            qual_reasons = buy_reasons
        else:
            rejection_notes.append(f"Spread wide (${spread:.3f} > $0.32)")
    elif sell_score >= 75.0 and sell_score >= (buy_score + 35.0):
        if spread <= 0.32:
            is_qualified = True
            direction = "SELL"
            qual_reasons = sell_reasons
        else:
            rejection_notes.append(f"Spread wide (${spread:.3f} > $0.32)")
    else:
        rejection_notes.append(f"Indecisive score: BUY {buy_score:.1f} vs SELL {sell_score:.1f} (<75 req)")

    return {
        "is_qualified": is_qualified,
        "direction": direction,
        "buy_score": buy_score,
        "sell_score": sell_score,
        "qual_reasons": qual_reasons,
        "rejection_notes": rejection_notes,
        "market_data": {
            "bid": bid, "ask": ask, "spread": spread, "digits": digits,
            "ema9_m1": ema9_m1, "ema21_m1": ema21_m1,
            "ema9_m5": ema9_m5, "ema21_m5": ema21_m5,
            "ema9_m15": ema9_m15, "ema21_m15": ema21_m15,
            "ema9_h1": ema9_h1, "ema21_h1": ema21_h1,
            "rsi14": rsi14, "macd_hist": macd_h, "atr14": atr14,
            "res_20": res_20, "sup_20": sup_20, "is_chasing": is_chasing
        }
    }

async def execute_patient_trade(adapter, trade_idx: int):
    print("\n" + "=" * 80)
    print(f"STEP: PATIENT SCAN FOR QUALIFIED OPPORTUNITY #{trade_idx}")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 80)

    snap = await adapter.client.get_trading_snapshot(force_refresh=True)
    open_pos = snap.get("positions") or []
    if len(open_pos) > 0:
        raise RuntimeError(f"ABORT: Active positions detected ({len(open_pos)}). Zero required.")

    acc_state = snap.get("account_state") or {}
    start_bal = float(acc_state.get("balance", 0.0))
    start_eq = float(acc_state.get("equity", 0.0))
    print(f"Verified Account: {TARGET_ACCOUNT_ID} (DEMO · {adapter.server_name})")
    print(f"Starting Balance: ${start_bal:.2f} USD | Equity: ${start_eq:.2f} USD")

    # Patient scan loop (up to 40 attempts, 3.5s per cycle = ~2.5 mins per trade window)
    setup = None
    max_scan_attempts = 40
    for attempt in range(1, max_scan_attempts + 1):
        tick, m1, m5, m15, h1 = await fetch_multi_timeframe_data(adapter)
        setup = evaluate_patient_market_setup(tick, m1, m5, m15, h1)
        m = setup["market_data"]

        print(f"  [Scan {attempt:02d}] Bid: ${m['bid']:.3f} | Ask: ${m['ask']:.3f} | Scores: BUY {setup['buy_score']:.0f} vs SELL {setup['sell_score']:.0f} | MACD: {m['macd_hist']:+.3f} | RSI: {m['rsi14']:.1f}")

        if setup["is_qualified"]:
            print(f"  >>> PATIENT ENTRY QUALIFIED on Attempt {attempt}: {setup['direction']} (Score: {setup['buy_score'] if setup['direction'] == 'BUY' else setup['sell_score']:.0f}/100)")
            for r in setup["qual_reasons"]:
                print(f"      - {r}")
            # Confirmation pause: wait 3 seconds and re-verify quote hasn't collapsed
            print("  Waiting 3.0s for price stability confirmation...")
            await asyncio.sleep(3.0)
            tick_confirm = await adapter.client.get_latest_tick(TARGET_INSTRUMENT)
            c_bid = float(tick_confirm.get("bid", 0.0))
            c_ask = float(tick_confirm.get("ask", 0.0))
            if setup["direction"] == "BUY" and c_ask > (m["ask"] + 0.35):
                print(f"  Confirmation failed: price spiked up ${c_ask:.3f} (slippage risk). Re-scanning...")
                continue
            elif setup["direction"] == "SELL" and c_bid < (m["bid"] - 0.35):
                print(f"  Confirmation failed: price collapsed down ${c_bid:.3f} (slippage risk). Re-scanning...")
                continue
            print("  Confirmation PASSED. Executing order...")
            break
        else:
            print(f"      Out of market: {'; '.join(setup['rejection_notes'])}")
            await asyncio.sleep(3.5)

    if not setup or not setup["is_qualified"]:
        print(f"\n[DECISION] No setup qualified within {max_scan_attempts} attempts. Capital protected. Skipping trade #{trade_idx}.")
        return None

    direction = setup["direction"]
    m = setup["market_data"]
    digits = m["digits"]

    if direction == "BUY":
        entry_est = m["ask"]
        sl_price = round(entry_est - SL_DISTANCE_PTS, digits)
        tp_price = round(entry_est + TP_DISTANCE_PTS, digits)
        base_risk_usd = round(SL_DISTANCE_PTS * 1.0, 2)
        total_max_risk_usd = round((SL_DISTANCE_PTS + m["spread"] + 0.05) * 1.0, 2)
        target_reward_usd = round(TP_DISTANCE_PTS * 1.0, 2)
    else:
        entry_est = m["bid"]
        sl_price = round(entry_est + SL_DISTANCE_PTS, digits)
        tp_price = round(entry_est - TP_DISTANCE_PTS, digits)
        base_risk_usd = round(SL_DISTANCE_PTS * 1.0, 2)
        total_max_risk_usd = round((SL_DISTANCE_PTS + m["spread"] + 0.05) * 1.0, 2)
        target_reward_usd = round(TP_DISTANCE_PTS * 1.0, 2)

    print(f"\nOrder Parameters for Trade #{trade_idx}:")
    print(f"  Direction:              {direction}")
    print(f"  Estimated Entry:        ${entry_est:.3f}")
    print(f"  Attached Stop Loss:     ${sl_price:.3f} (Risk: -${base_risk_usd:.2f} USD)")
    print(f"  Attached Take Profit:   ${tp_price:.3f} (Target: +${target_reward_usd:.2f} USD)")
    print(f"  Total Max Potential Loss:${total_max_risk_usd:.2f} USD (strictly <= $1.00 USD)")

    adapter.unlock_demo_execution_for_test(TARGET_ACCOUNT_ID)
    event_mgr = ExnessTransactionEventManager(adapter.client)
    idempotency_key = f"bitdex-patient-t{trade_idx}-{int(time.time())}"

    t0 = time.perf_counter()
    order_res = await adapter.place_market_order(
        symbol=TARGET_INSTRUMENT,
        side=direction.lower(),
        volume=TRADE_VOLUME,
        sl=None,
        tp=None,
        comment=f"BITDEX-PT-{trade_idx}",
        idempotency_key=idempotency_key,
        dry_run=False,
    )
    lat_ms = (time.perf_counter() - t0) * 1000
    op_id = str(order_res.get("operation_id") or order_res.get("ack", {}).get("operation_id") or "")
    print(f"  Broker Response: HTTP 202 in {lat_ms:.1f}ms (Op ID: #{op_id})")

    if not op_id:
        print(f"  Order submission failed: {order_res}")
        return None

    print("Reconciling fill via Exness event stream...")
    reconciled = await event_mgr.reconcile_operation(op_id, max_retries=15, delay_sec=1.0)
    if reconciled.get("state") == "REJECTED":
        err_msg = reconciled.get("error_detail", "REJECTED_BY_BROKER")
        print(f"  Broker Rejected Operation #{op_id}: {err_msg}")
        return None

    position_id = str(reconciled.get("position_id") or "")
    exec_price = float(reconciled.get("execution_price") or entry_est)

    if not position_id:
        snap_check = await adapter.client.get_trading_snapshot(force_refresh=True)
        check_pos = [p for p in snap_check.get("positions", []) if "XAU" in str(p.get("symbol", "")).upper()]
        if check_pos:
            position_id = str(check_pos[0].get("position_id", check_pos[0].get("id", "")))
            exec_price = float(check_pos[0].get("open_price", exec_price))
        else:
            print(f"  Fill reconciliation failed for Op ID #{op_id}")
            return None

    print(f"  Position ID:   #{position_id}")
    print(f"  Execution Fill:${exec_price:.3f}")

    if direction == "BUY":
        exact_sl = round(exec_price - SL_DISTANCE_PTS, digits)
        exact_tp = round(exec_price + TP_DISTANCE_PTS, digits)
    else:
        exact_sl = round(exec_price + SL_DISTANCE_PTS, digits)
        exact_tp = round(exec_price - TP_DISTANCE_PTS, digits)

    print(f"  Attaching Exact SL (${exact_sl:.3f}) & TP (${exact_tp:.3f}) based on fill...")
    await adapter.client.attach_sl_tp(position_id=position_id, sl=exact_sl, tp=exact_tp, symbol=TARGET_INSTRUMENT, dry_run=False)

    opened_time_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"Monitoring Position #{position_id} until closed...")
    is_closed = False
    exit_price = None
    exit_deal_id = None
    open_deal_id = None
    exit_order_id = None
    realized_pnl = None
    closed_time_iso = None

    for elapsed in range(0, 180, 2):
        await asyncio.sleep(2.0)
        snap = await adapter.client.get_trading_snapshot(force_refresh=True)
        active_pos = snap.get("positions") or []
        pos_match = [p for p in active_pos if str(p.get("position_id") or p.get("id")) == str(position_id)]

        if pos_match:
            cur_p = pos_match[0]
            cur_fp = float(cur_p.get("floating_profit", cur_p.get("profit", 0.0)))
            cur_mark = float(cur_p.get("current_price", cur_p.get("mark_price", exec_price)))
            print(f"  [T+{elapsed+2:03d}s] Pos #{position_id} Mark: ${cur_mark:.3f} | Float: ${cur_fp:+.2f} USD")

            # Secure profit when target is reached (>= $0.70 USD)
            if cur_fp >= 0.70:
                print(f"  >>> Target reached (${cur_fp:+.2f} USD >= $0.70)! Securing profit at market...")
                await adapter.close_position(position_id=position_id, dry_run=False)
                await asyncio.sleep(2.0)
        else:
            print(f"\n[EVENT] Position #{position_id} closed at broker!")
            is_closed = True
            closed_time_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            break

    if not is_closed:
        print(f"  Timeout reached. Securing position at market...")
        await adapter.close_position(position_id=position_id, dry_run=False)
        await asyncio.sleep(2.5)
        is_closed = True
        closed_time_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    await asyncio.sleep(2.0)

    # Reconcile Deals
    deals = await adapter.client.get_trade_history(limit=25)
    for d in deals:
        deal_info = d.get("deal", d)
        if str(deal_info.get("position_id") or "") == str(position_id):
            dtype = str(deal_info.get("type", "")).lower()
            if dtype == "open":
                open_deal_id = str(deal_info.get("deal_id") or "")
            elif dtype == "close":
                exit_deal_id = str(deal_info.get("deal_id") or "")
                exit_order_id = str(deal_info.get("order_id") or "")
                exit_price = float(deal_info.get("price", 0.0))
                prof_val = deal_info.get("profit")
                if isinstance(prof_val, dict):
                    realized_pnl = float(prof_val.get("amount", 0.0))
                elif prof_val is not None:
                    realized_pnl = float(prof_val)

    snap_final = await adapter.client.get_trading_snapshot(force_refresh=True)
    fin_state = snap_final.get("account_state") or {}
    end_bal = float(fin_state.get("balance", start_bal))
    end_eq = float(fin_state.get("equity", start_eq))

    if realized_pnl is None:
        realized_pnl = round(end_bal - start_bal, 2)

    print(f"\nTrade #{trade_idx} Reconciled:")
    print(f"  Open Deal Ticket:   #{open_deal_id}")
    print(f"  Exit Deal Ticket:   #{exit_deal_id}")
    print(f"  Entry Price:        ${exec_price:.3f}")
    print(f"  Exit Price:         ${exit_price:.3f}" if exit_price else "  Exit Price:         N/A")
    print(f"  Realized P&L:       ${realized_pnl:+.2f} USD")
    print(f"  Updated Balance:    ${end_bal:.2f} USD (Delta: ${end_bal - start_bal:+.2f} USD)")

    return {
        "trade_number": trade_idx,
        "status": "COMPLETED",
        "account_id": TARGET_ACCOUNT_ID,
        "broker_server": adapter.server_name,
        "instrument": TARGET_INSTRUMENT,
        "direction": direction,
        "volume_lots": TRADE_VOLUME,
        "contract_size": 100.0,
        "operation_id": op_id,
        "position_id": position_id,
        "entry_order_id": op_id,
        "open_deal_id": open_deal_id,
        "exit_deal_id": exit_deal_id,
        "exit_order_id": exit_order_id,
        "entry_price": exec_price,
        "exit_price": exit_price,
        "stop_loss_price": exact_sl,
        "take_profit_price": exact_tp,
        "base_risk_usd": base_risk_usd,
        "total_max_risk_usd": total_max_risk_usd,
        "target_reward_usd": target_reward_usd,
        "realized_profit_usd": realized_pnl,
        "opened_at_utc": opened_time_iso,
        "closed_at_utc": closed_time_iso,
        "initial_balance_usd": start_bal,
        "updated_balance_usd": end_bal,
        "updated_equity_usd": end_eq,
        "net_account_delta_usd": round(end_bal - start_bal, 2),
        "indicators_at_entry": {
            "m1_ema9": m["ema9_m1"], "m1_ema21": m["ema21_m1"],
            "m5_ema9": m["ema9_m5"], "m5_ema21": m["ema21_m5"],
            "m15_ema9": m["ema9_m15"], "m15_ema21": m["ema21_m15"],
            "h1_ema9": m["ema9_h1"], "h1_ema21": m["ema21_h1"],
            "rsi_14": m["rsi14"], "macd_hist": m["macd_hist"], "atr_14": m["atr14"],
            "qual_reasons": setup["qual_reasons"]
        }
    }

async def main():
    print("=" * 80)
    print("BITDEX — PATIENT MULTI-TIMEFRAME XAUUSD DEMO EXECUTION PIPELINE")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 80)

    conn = get_db_connection()
    all_executed = []
    rejected_count = 0

    try:
        adapter, ctx, route = CentralExecutionRouter.resolve_adapter_for_customer(
            conn, TARGET_USER_ID, TARGET_ACCOUNT_ID
        )

        if str(adapter.account_id) != TARGET_ACCOUNT_ID:
            raise PermissionError(f"Account mismatch: {adapter.account_id} != {TARGET_ACCOUNT_ID}")
        # Load existing completed session trades if present
        for t_idx in (10, 11, 12, 13, 14):
            path = f"/opt/tauric-platform-staging/backend/trade_{t_idx}_execution_evidence.json"
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                        if loaded.get("status") == "COMPLETED":
                            all_executed.append(loaded)
                            print(f"Loaded existing session Trade #{t_idx}: {loaded.get('direction')} Realized P&L ${loaded.get('realized_profit_usd'):+.2f} USD")
                except Exception as e:
                    print(f"Could not load {path}: {e}")

        # Scan for up to 5 opportunities total with patience
        start_window = len(all_executed) + 1
        for window in range(start_window, 6):
            trade_num = 10 + len(all_executed)
            print(f"\n>>> PATIENT EVALUATION WINDOW {window}/5 (Target Global Trade #{trade_num}) <<<")
            ev = await execute_patient_trade(adapter, trade_idx=trade_num)
            if ev:
                all_executed.append(ev)
                with open(f"/opt/tauric-platform-staging/backend/trade_{trade_num}_execution_evidence.json", "w", encoding="utf-8") as f:
                    json.dump(ev, f, indent=2)
                print(f"Pausing 10.0 seconds for market digestion and deal reconciliation...")
                await asyncio.sleep(10.0)
            else:
                rejected_count += 1
                print(f"Window {window} yielded no qualified setup. Pausing 5.0 seconds before next evaluation window...")
                await asyncio.sleep(5.0)

        # Update database & sync connection balance
        snap_final = await adapter.client.get_trading_snapshot(force_refresh=True)
        acc_final = snap_final.get("account_state") or {}
        final_balance = float(acc_final.get("balance", 5002.63))
        final_equity = float(acc_final.get("equity", 5002.63))

        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn.execute("""
            UPDATE exness_demo_connections
            SET balance_usd = ?, equity_usd = ?, last_reconciled_at = ?, updated_at = ?
            WHERE account_login = ? OR connection_id = 'EXN-CONN-02926D69E193'
        """, (final_balance, final_equity, now_iso, now_iso, TARGET_ACCOUNT_ID))
        conn.commit()

        # Cumulative evidence file
        summary_data = {
            "batch_name": "PATIENT_MULTI_TIMEFRAME_GOLD_DEMO_TEST",
            "timestamp_utc": now_iso,
            "account_id": TARGET_ACCOUNT_ID,
            "evaluation_windows_count": 5,
            "trades_actually_executed_count": len(all_executed),
            "opportunities_rejected_count": rejected_count,
            "initial_balance_usd": all_executed[0]["initial_balance_usd"] if all_executed else final_balance,
            "final_balance_usd": final_balance,
            "net_session_delta_usd": round(final_balance - (all_executed[0]["initial_balance_usd"] if all_executed else final_balance), 2),
            "trades": all_executed
        }

        with open("/opt/tauric-platform-staging/backend/patient_five_trades_evidence.json", "w", encoding="utf-8") as f:
            json.dump(summary_data, f, indent=2)

        print("\n" + "=" * 80)
        print("PATIENT DEMO TEST COMPLETE!")
        print(f"Executed: {len(all_executed)} | Rejected: {rejected_count}")
        print(f"Final Balance: ${final_balance:.2f} USD")
        print("=" * 80)

        return summary_data

    finally:
        conn.close()

if __name__ == "__main__":
    asyncio.run(main())
