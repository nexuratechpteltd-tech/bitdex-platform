import sys, math, httpx
from collections import defaultdict
from app.services.futures_regime import MarketRegimeClassifier
from app.services.futures_sizing import FuturesSizingEngine
from strategy_optimizer import fetch_1000_klines, calculate_bollinger_bands
from app.services.binance_futures_adapter import BinanceFuturesAdapter

symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
klines_by_sym = {s: fetch_1000_klines(s) for s in symbols}
adapter = BinanceFuturesAdapter(environment="testnet")
filters_by_sym = {s: adapter.get_symbol_filters(s) for s in symbols}

def evaluate_adaptive_strategy(target_mode="atr_scaled", use_breakeven=True, use_maker=True, max_hold_bars=3):
    trades = []
    evaluations = 0

    for sym, klines in klines_by_sym.items():
        filters = filters_by_sym[sym]
        window_size = 30
        for i in range(window_size, len(klines) - max_hold_bars - 1):
            evaluations += 1
            history = klines[i - window_size:i]
            current = klines[i]
            entry_price = current["close"]
            regime = MarketRegimeClassifier.classify(history, sym)
            if not regime["trade_eligible"]: continue
            atr = regime.get("atr", 1.0)
            if atr / entry_price < 0.0012: continue # Filter low volatility

            adx = regime.get("adx", 20.0)
            regime_name = regime["regime"]
            if regime_name in ("TRENDING_UP", "TRENDING_DOWN") and adx < 28.0:
                continue

            closes = [k["close"] for k in history]
            highs = [k["high"] for k in history]
            lows = [k["low"] for k in history]
            ema9 = MarketRegimeClassifier.calculate_ema(closes, 9)
            ema21 = MarketRegimeClassifier.calculate_ema(closes, 21)

            # Ranging filter
            if regime_name == "RANGING_SIDEWAYS":
                lower_bb, mid_bb, upper_bb = calculate_bollinger_bands(closes, 20, 2.0)
                bw = upper_bb - lower_bb
                if bw <= 0: continue
                dist_pct = (entry_price - lower_bb) / bw
                if 0.20 < dist_pct < 0.80: continue # Skip middle chop

            # Signal scoring
            long_score, short_score = 0.0, 0.0
            if ema9 > ema21: long_score += 0.35
            elif ema9 < ema21: short_score += 0.35

            if current["close"] > current["open"]: long_score += 0.25
            elif current["close"] < current["open"]: short_score += 0.25

            # Volume confirmation
            vols = [k["volume"] for k in history]
            if current["volume"] > sum(vols[-5:])/5.0:
                if long_score > short_score: long_score += 0.20
                else: short_score += 0.20

            # RSI
            gains = [max(0.0, closes[j] - closes[j-1]) for j in range(1, len(closes))]
            losses = [max(0.0, closes[j-1] - closes[j]) for j in range(1, len(closes))]
            rs = (sum(gains[-14:])/14.0) / (sum(losses[-14:])/14.0 or 1.0)
            rsi = 100.0 - (100.0 / (1.0 + rs))
            if 48.0 <= rsi <= 65.0: long_score += 0.20
            elif 35.0 <= rsi <= 52.0: short_score += 0.20

            permitted = regime.get("permitted_directions", [])
            if "LONG" not in permitted: long_score = 0.0
            if "SHORT" not in permitted: short_score = 0.0

            best_dir = None
            if long_score >= 0.75 and long_score > short_score: best_dir = "LONG"
            elif short_score >= 0.75 and short_score > long_score: best_dir = "SHORT"
            else: continue

            # Sizing
            sizing = FuturesSizingEngine.calculate_scalp_sizing(
                symbol=sym, price=entry_price, atr=atr,
                stop_price=entry_price - (atr * 1.5),
                available_balance=1000.0, equity=1000.0,
                symbol_filters=filters, target_net_usd=1.00
            )
            if not sizing["feasible"]: continue
            qty = sizing["quantity"]

            # Stop & Target
            stop_dist = max(0.003 * entry_price, min(0.03 * entry_price, atr * 1.5))
            initial_stop = entry_price - stop_dist if best_dir == "LONG" else entry_price + stop_dist

            # Fees
            maker_fee_rate = 0.0002
            taker_fee_rate = 0.0004
            entry_fee = entry_price * qty * (maker_fee_rate if use_maker else taker_fee_rate)

            # Target calculation
            if target_mode == "fixed":
                target_net = 1.00
            elif target_mode == "atr_scaled":
                # Scale target: 1.5x ATR * qty - fees, bounded at min .00
                target_gross = 1.5 * atr * qty
                target_net = max(1.00, target_gross - (entry_price * qty * 0.0008) - 0.05)
            elif target_mode == "2x_atr":
                target_gross = 2.0 * atr * qty
                target_net = max(1.50, target_gross - (entry_price * qty * 0.0008) - 0.05)

            target_friction = target_net + 0.05
            exit_fee_rate_est = maker_fee_rate if use_maker else taker_fee_rate
            if best_dir == "LONG":
                target_exit = (target_friction + entry_price * qty * (1.0 + (maker_fee_rate if use_maker else taker_fee_rate))) / (qty * (1.0 - exit_fee_rate_est))
            else:
                target_exit = (entry_price * qty * (1.0 - (maker_fee_rate if use_maker else taker_fee_rate)) - target_friction) / (qty * (1.0 + exit_fee_rate_est))

            # Forward simulation
            forward = klines[i:i + max_hold_bars + 1]
            if use_maker:
                # Maker entry check on bar 0
                filled = (forward[0]["low"] <= entry_price) if best_dir == "LONG" else (forward[0]["high"] >= entry_price)
                if not filled: continue

            current_stop = initial_stop
            exit_price = None
            exit_reason = None
            exit_fee_rate = taker_fee_rate

            for bar_idx, bar in enumerate(forward[:max_hold_bars]):
                # 1. Check Breakeven activation: if price reaches halfway to target, raise stop to entry + fees
                if use_breakeven:
                    if best_dir == "LONG" and bar["high"] >= entry_price + (atr * 0.8):
                        current_stop = max(current_stop, entry_price + (entry_price * 0.0005))
                    elif best_dir == "SHORT" and bar["low"] <= entry_price - (atr * 0.8):
                        current_stop = min(current_stop, entry_price - (entry_price * 0.0005))

                # 2. Check Stop Loss
                if best_dir == "LONG" and bar["low"] <= current_stop:
                    exit_price = current_stop
                    exit_reason = "BREAKEVEN_STOP" if current_stop > initial_stop else "STOP_LOSS"
                    exit_fee_rate = taker_fee_rate
                    break
                elif best_dir == "SHORT" and bar["high"] >= current_stop:
                    exit_price = current_stop
                    exit_reason = "BREAKEVEN_STOP" if current_stop < initial_stop else "STOP_LOSS"
                    exit_fee_rate = taker_fee_rate
                    break

                # 3. Check Target Hit
                if best_dir == "LONG" and bar["high"] >= target_exit:
                    exit_price = target_exit
                    exit_reason = "TARGET_HIT"
                    exit_fee_rate = maker_fee_rate if use_maker else taker_fee_rate
                    break
                elif best_dir == "SHORT" and bar["low"] <= target_exit:
                    exit_price = target_exit
                    exit_reason = "TARGET_HIT"
                    exit_fee_rate = maker_fee_rate if use_maker else taker_fee_rate
                    break

            if exit_price is None:
                exit_price = forward[max_hold_bars - 1]["close"]
                exit_reason = "TIME_EXPIRY"
                exit_fee_rate = taker_fee_rate

            gross = (exit_price - entry_price)*qty if best_dir == "LONG" else (entry_price - exit_price)*qty
            exit_fee = exit_price * qty * exit_fee_rate
            total_fee = entry_fee + exit_fee
            slippage = 0.05
            net = gross - total_fee - slippage

            trades.append({"net": net, "gross": gross, "fee": total_fee, "reason": exit_reason})

        if not trades: continue

    wins = [t for t in trades if t["net"] > 0]
    wr = len(wins)/len(trades)*100 if trades else 0
    avg_g = sum(t["gross"] for t in trades)/len(trades) if trades else 0
    avg_f = sum(t["fee"] for t in trades)/len(trades) if trades else 0
    avg_n = sum(t["net"] for t in trades)/len(trades) if trades else 0
    cum, peak, dd = 0, 0, 0
    for t in trades:
        cum += t["net"]
        if cum > peak: peak = cum
        if peak - cum > dd: dd = peak - cum
    reasons = defaultdict(int)
    for t in trades: reasons[t["reason"]] += 1

    return {
        "trades": len(trades), "win_rate": round(wr, 1),
        "avg_gross": round(avg_g, 3), "avg_fee": round(avg_f, 3), "avg_net": round(avg_n, 3),
        "drawdown": round(dd, 2), "reasons": dict(reasons)
    }

print("Evaluating combinations across 1000 klines:")
print("1. Baseline Fixed .00 (Taker, No BE, 2 bars / 10m):")
print(evaluate_adaptive_strategy(target_mode="fixed", use_breakeven=False, use_maker=False, max_hold_bars=2))

print("\n2. Maker Entry + Fixed .00 (No BE, 2 bars / 10m):")
print(evaluate_adaptive_strategy(target_mode="fixed", use_breakeven=False, use_maker=True, max_hold_bars=2))

print("\n3. Maker Entry + Breakeven Stop + Fixed .00 (2 bars / 10m):")
print(evaluate_adaptive_strategy(target_mode="fixed", use_breakeven=True, use_maker=True, max_hold_bars=2))

print("\n4. Maker Entry + Breakeven Stop + ATR Scaled Target (2 bars / 10m):")
print(evaluate_adaptive_strategy(target_mode="atr_scaled", use_breakeven=True, use_maker=True, max_hold_bars=2))

print("\n5. Maker Entry + Breakeven Stop + 2x ATR Target (3 bars / 15m):")
print(evaluate_adaptive_strategy(target_mode="2x_atr", use_breakeven=True, use_maker=True, max_hold_bars=3))
