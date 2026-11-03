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

def test_pullback_entry():
    for mode in ["baseline_chase", "pullback_retest", "macd_momentum_breakout"]:
        trades = []
        for sym, klines in klines_by_sym.items():
            filters = filters_by_sym[sym]
            window_size = 30
            for i in range(window_size, len(klines) - 3):
                history = klines[i - window_size:i]
                current = klines[i]
                entry_price = current["close"]
                regime = MarketRegimeClassifier.classify(history, sym)
                if not regime["trade_eligible"]: continue
                atr = regime.get("atr", 1.0)
                if atr / entry_price < 0.0010: continue # Skip if volatility too low

                closes = [k["close"] for k in history]
                highs = [k["high"] for k in history]
                lows = [k["low"] for k in history]
                ema9 = MarketRegimeClassifier.calculate_ema(closes, 9)
                ema21 = MarketRegimeClassifier.calculate_ema(closes, 21)
                adx = regime.get("adx", 20.0)

                best_dir = None
                if mode == "baseline_chase":
                    if regime["regime"] == "TRENDING_UP" and current["close"] > current["open"]:
                        best_dir = "LONG"
                    elif regime["regime"] == "TRENDING_DOWN" and current["close"] < current["open"]:
                        best_dir = "SHORT"

                elif mode == "pullback_retest":
                    # PULLBACK: In uptrend, previous candle pulled back near EMA21 or EMA9, and current candle reverses back up
                    if regime["regime"] == "TRENDING_UP" and ema9 > ema21:
                        # Price low touched or approached EMA9/EMA21, and current candle closed green confirming reversal
                        if history[-2]["low"] <= ema9 * 1.001 and current["close"] > current["open"] and current["close"] > ema9:
                            best_dir = "LONG"
                    elif regime["regime"] == "TRENDING_DOWN" and ema9 < ema21:
                        if history[-2]["high"] >= ema9 * 0.999 and current["close"] < current["open"] and current["close"] < ema9:
                            best_dir = "SHORT"

                elif mode == "macd_momentum_breakout":
                    # Breakout with volume expansion: current volume > 1.5x average 10-bar volume
                    vols = [k["volume"] for k in history]
                    avg_vol = sum(vols[-10:]) / 10.0
                    if current["volume"] > 1.5 * avg_vol:
                        if regime["regime"] == "TRENDING_UP" and current["close"] > max(highs[-5:-1]):
                            best_dir = "LONG"
                        elif regime["regime"] == "TRENDING_DOWN" and current["close"] < min(lows[-5:-1]):
                            best_dir = "SHORT"

                if not best_dir: continue

                # Sizing
                sizing = FuturesSizingEngine.calculate_scalp_sizing(
                    symbol=sym, price=entry_price, atr=atr,
                    stop_price=entry_price - (atr * 1.5),
                    available_balance=1000.0, equity=1000.0,
                    symbol_filters=filters, target_net_usd=1.00
                )
                if not sizing["feasible"]: continue
                qty = sizing["quantity"]

                # Target & Stop
                stop_dist = max(0.0025 * entry_price, min(0.045 * entry_price, atr * 1.5))
                stop_price = entry_price - stop_dist if best_dir == "LONG" else entry_price + stop_dist

                # Target exit for  net with maker entry (0.02%) + maker exit (0.02%):
                target_friction = 1.00 + 0.05
                if best_dir == "LONG":
                    target_exit = (target_friction + entry_price * qty * 1.0002) / (qty * 0.9998)
                else:
                    target_exit = (entry_price * qty * 0.9998 - target_friction) / (qty * 1.0002)

                # Forward 2 bars
                forward = klines[i:min(i + 3, len(klines))]
                # Maker entry check
                filled = (forward[0]["low"] <= entry_price) if best_dir == "LONG" else (forward[0]["high"] >= entry_price)
                if not filled: continue

                exit_price = None; exit_reason = None
                for bar in forward[:2]:
                    if best_dir == "LONG":
                        if bar["low"] <= stop_price: exit_price = stop_price; exit_reason = "STOP_LOSS"; break
                        elif bar["high"] >= target_exit: exit_price = target_exit; exit_reason = "TARGET_HIT"; break
                    else:
                        if bar["high"] >= stop_price: exit_price = stop_price; exit_reason = "STOP_LOSS"; break
                        elif bar["low"] <= target_exit: exit_price = target_exit; exit_reason = "TARGET_HIT"; break

                if exit_price is None:
                    exit_price = forward[-1]["close"]
                    exit_reason = "10M_EXPIRY"

                gross = (exit_price - entry_price)*qty if best_dir == "LONG" else (entry_price - exit_price)*qty
                fee = entry_price*qty*0.0002 + exit_price*qty*(0.0002 if exit_reason == "TARGET_HIT" else 0.0004)
                net = gross - fee - 0.05
                trades.append({"net": net, "gross": gross, "fee": fee, "reason": exit_reason})

            if not trades: continue
        wins = [t for t in trades if t["net"] > 0]
        avg_gross = sum(t["gross"] for t in trades) / len(trades) if trades else 0
        avg_net = sum(t["net"] for t in trades) / len(trades) if trades else 0
        reasons = defaultdict(int)
        for t in trades: reasons[t["reason"]] += 1
        print(f"{mode:25s} | Trades: {len(trades):3d} | WinRate: {len(wins)/len(trades)*100:5.1f}% | AvgGross: ${avg_gross:+.3f} | AvgNet: ${avg_net:+.3f} | TargetHits: {reasons['TARGET_HIT']} ({reasons['TARGET_HIT']/len(trades)*100:4.1f}%) | Expiry: {reasons['10M_EXPIRY']} | Stops: {reasons['STOP_LOSS']}")

test_pullback_entry()
