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

def test_segments():
    for sym in symbols:
        klines = klines_by_sym[sym]
        filters = filters_by_sym[sym]
        trades_by_regime = defaultdict(list)
        
        window_size = 30
        for i in range(window_size, len(klines) - 3):
            history = klines[i - window_size:i]
            current = klines[i]
            entry_price = current["close"]
            regime = MarketRegimeClassifier.classify(history, sym)
            reg_name = regime["regime"]
            if not regime["trade_eligible"]: continue
            atr = regime.get("atr", 1.0)
            if atr / entry_price < 0.0008: continue

            # Sizing
            sizing = FuturesSizingEngine.calculate_scalp_sizing(
                symbol=sym, price=entry_price, atr=atr,
                stop_price=entry_price - (atr * 1.5),
                available_balance=1000.0, equity=1000.0,
                symbol_filters=filters, target_net_usd=1.00
            )
            if not sizing["feasible"]: continue
            qty = sizing["quantity"]

            # Entry score
            closes = [k["close"] for k in history]
            ema9 = MarketRegimeClassifier.calculate_ema(closes, 9)
            ema21 = MarketRegimeClassifier.calculate_ema(closes, 21)
            candle_body = current["close"] - current["open"]

            best_dir = None
            if reg_name == "TRENDING_UP" and ema9 > ema21 and current["close"] > current["open"]:
                best_dir = "LONG"
            elif reg_name == "TRENDING_DOWN" and ema9 < ema21 and current["close"] < current["open"]:
                best_dir = "SHORT"
            elif reg_name == "RANGING_SIDEWAYS":
                lbb, mbb, ubb = calculate_bollinger_bands(closes, 20, 2.0)
                bw = ubb - lbb
                if bw > 0:
                    dpct = (entry_price - lbb) / bw
                    if dpct <= 0.20 and current["close"] > current["open"]: best_dir = "LONG"
                    elif dpct >= 0.80 and current["close"] < current["open"]: best_dir = "SHORT"

            if not best_dir: continue

            stop_dist = max(0.003 * entry_price, min(0.03 * entry_price, atr * 1.5))
            stop_price = entry_price - stop_dist if best_dir == "LONG" else entry_price + stop_dist

            target_friction = 1.00 + 0.05
            # Maker entry (0.02%), Maker exit (0.02%) on target
            target_exit = (target_friction + entry_price * qty * 1.0002) / (qty * 0.9998) if best_dir == "LONG" else (entry_price * qty * 0.9998 - target_friction) / (qty * 1.0002)

            forward = klines[i:i + 3]
            # Maker check
            filled = (forward[0]["low"] <= entry_price) if best_dir == "LONG" else (forward[0]["high"] >= entry_price)
            if not filled: continue

            exit_p = None
            exit_r = None
            for b in forward[:2]:
                if best_dir == "LONG":
                    if b["low"] <= stop_price: exit_p = stop_price; exit_r = "STOP"; break
                    elif b["high"] >= target_exit: exit_p = target_exit; exit_r = "TARGET"; break
                else:
                    if b["high"] >= stop_price: exit_p = stop_price; exit_r = "STOP"; break
                    elif b["low"] <= target_exit: exit_p = target_exit; exit_r = "TARGET"; break

            if exit_p is None:
                exit_p = forward[1]["close"]
                exit_r = "EXPIRY"

            gross = (exit_p - entry_price)*qty if best_dir == "LONG" else (entry_price - exit_p)*qty
            fee = entry_price*qty*0.0002 + exit_p*qty*(0.0002 if exit_r == "TARGET" else 0.0004)
            net = gross - fee - 0.05
            trades_by_regime[reg_name].append({"gross": gross, "fee": fee, "net": net, "reason": exit_r})

        print(f"=== Symbol: {sym} ===")
        for rname, tr_list in trades_by_regime.items():
            if not tr_list: continue
            wins = [t for t in tr_list if t["net"] > 0]
            avg_g = sum(t["gross"] for t in tr_list) / len(tr_list)
            avg_f = sum(t["fee"] for t in tr_list) / len(tr_list)
            avg_n = sum(t["net"] for t in tr_list) / len(tr_list)
            wr = len(wins) / len(tr_list) * 100
            targets = sum(1 for t in tr_list if t["reason"] == "TARGET")
            print(f"  {rname:18s} | Count: {len(tr_list):3d} | WinRate: {wr:5.1f}% | AvgGross: ${avg_g:+.3f} | AvgFee: ${avg_f:.3f} | AvgNet: ${avg_n:+.3f} | Targets: {targets}")

test_segments()
