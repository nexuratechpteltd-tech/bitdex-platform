import sys
import json
from collections import defaultdict
from app.services.binance_futures_adapter import BinanceFuturesAdapter
from app.services.futures_regime import MarketRegimeClassifier
from app.services.futures_signal_engine import FuturesSignalEngine
from app.services.futures_sizing import FuturesSizingEngine

def run_forensic():
    adapter = BinanceFuturesAdapter(environment="testnet")
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    
    trades = []
    regimes = defaultdict(int)
    evaluations = 0
    rejections = defaultdict(int)

    for sym in symbols:
        params = {"symbol": sym, "interval": "5m", "limit": 120}
        res = adapter._request("GET", "/fapi/v1/klines", params=params)
        klines = [{
            "open_time": int(k[0]), "open": float(k[1]), "high": float(k[2]),
            "low": float(k[3]), "close": float(k[4]), "volume": float(k[5]),
            "close_time": int(k[6]), "quote_volume": float(k[7]), "trades_count": int(k[8])
        } for k in res]
        filters = adapter.get_symbol_filters(sym)

        window_size = 30
        for i in range(window_size, len(klines) - 2):
            evaluations += 1
            history = klines[i - window_size:i]
            current = klines[i]
            entry_price = current["close"]

            regime = MarketRegimeClassifier.classify(history, sym)
            regime_name = regime["regime"]
            regimes[regime_name] += 1

            if not regime["trade_eligible"]:
                rejections["REGIME_INELIGIBLE"] += 1
                continue

            atr = regime.get("atr", 1.0)
            sizing = FuturesSizingEngine.calculate_scalp_sizing(
                symbol=sym, price=entry_price, atr=atr,
                stop_price=entry_price - (atr * 1.8),
                available_balance=1000.0, equity=1000.0,
                symbol_filters=filters, target_net_usd=1.00
            )

            if not sizing["feasible"]:
                rejections[sizing.get("rejection_reason", "SIZING_INFEASIBLE")] += 1
                continue

            signal = FuturesSignalEngine.evaluate_signal(
                symbol=sym, klines=history, current_market_price=entry_price,
                proposed_quantity=sizing["quantity"], equity=1000.0, regime_data=regime
            )

            if signal["decision"] != "TRADE":
                rejections[signal.get("rejection_reason", "SIGNAL_NO_TRADE")] += 1
                continue

            direction = signal["direction"]
            target_exit = signal["target_exit_price"]
            stop_price = signal["protective_stop_price"]
            qty = sizing["quantity"]

            forward_bars = klines[i:min(i + 3, len(klines))]
            bar1 = forward_bars[0]
            exit_price = None
            exit_reason = None
            hold_min = 10.0

            if direction == "LONG":
                if bar1["low"] <= stop_price:
                    exit_price = stop_price; exit_reason = "STOP_LOSS"; hold_min = 3.0
                elif bar1["high"] >= target_exit:
                    exit_price = target_exit; exit_reason = "TARGET_HIT"; hold_min = 4.0
                elif len(forward_bars) > 1 and bar1["close"] > entry_price + (entry_price * 0.001):
                    exit_price = bar1["close"]; exit_reason = "5M_PROFIT_TAKE"; hold_min = 5.0
            else:
                if bar1["high"] >= stop_price:
                    exit_price = stop_price; exit_reason = "STOP_LOSS"; hold_min = 3.0
                elif bar1["low"] <= target_exit:
                    exit_price = target_exit; exit_reason = "TARGET_HIT"; hold_min = 4.0
                elif len(forward_bars) > 1 and bar1["close"] < entry_price - (entry_price * 0.001):
                    exit_price = bar1["close"]; exit_reason = "5M_PROFIT_TAKE"; hold_min = 5.0

            if exit_price is None and len(forward_bars) > 1:
                bar2 = forward_bars[1]
                if direction == "LONG":
                    if bar2["low"] <= stop_price:
                        exit_price = stop_price; exit_reason = "STOP_LOSS"; hold_min = 7.0
                    elif bar2["high"] >= target_exit:
                        exit_price = target_exit; exit_reason = "TARGET_HIT"; hold_min = 8.0
                    else:
                        exit_price = bar2["close"]; exit_reason = "10M_EXPIRY"; hold_min = 10.0
                else:
                    if bar2["high"] >= stop_price:
                        exit_price = stop_price; exit_reason = "STOP_LOSS"; hold_min = 7.0
                    elif bar2["low"] <= target_exit:
                        exit_price = target_exit; exit_reason = "TARGET_HIT"; hold_min = 8.0
                    else:
                        exit_price = bar2["close"]; exit_reason = "10M_EXPIRY"; hold_min = 10.0

            if exit_price is None:
                exit_price = forward_bars[-1]["close"]
                exit_reason = "10M_EXPIRY"

            # Gross PnL
            gross_pnl = (exit_price - entry_price) * qty if direction == "LONG" else (entry_price - exit_price) * qty

            # Fees taker vs maker
            notional = entry_price * qty
            exit_notional = exit_price * qty
            taker_fees = (notional + exit_notional) * 0.0004
            maker_fees = (notional + exit_notional) * 0.0002
            hybrid_fees = (notional * 0.0002) + (exit_notional * 0.0004) # maker entry, taker exit

            slippage = 0.05
            net_taker = gross_pnl - taker_fees - slippage
            net_maker = gross_pnl - maker_fees - slippage
            net_hybrid = gross_pnl - hybrid_fees - slippage

            trades.append({
                "symbol": sym, "direction": direction, "regime": regime_name,
                "entry_price": entry_price, "exit_price": exit_price, "qty": qty,
                "notional": notional, "exit_reason": exit_reason, "hold_min": hold_min,
                "gross_pnl": gross_pnl, "taker_fees": taker_fees, "maker_fees": maker_fees,
                "net_taker": net_taker, "net_maker": net_maker, "net_hybrid": net_hybrid,
                "target_hit": (exit_reason == "TARGET_HIT" or net_taker >= 0.95),
            })

    print("=" * 80)
    print("BITDEX PHASE 3.1 FORENSIC PERFORMANCE ANALYSIS REPORT")
    print("=" * 80)
    print(f"Total Evaluations: {evaluations}")
    print(f"Trades Triggered: {len(trades)} ({len(trades)/evaluations*100:.1f}%)")
    
    # 1. OVERALL METRICS COMPARISON (Taker vs Maker vs Hybrid)
    print("\n--- 1. OVERALL COMMISSION SENSITIVITY ---")
    for mode, key, fee_key in [("Taker (0.04%/0.04%)", "net_taker", "taker_fees"),
                               ("Hybrid (Maker Entry 0.02% / Taker Exit 0.04%)", "net_hybrid", "hybrid_fees"),
                               ("Maker (0.02%/0.02%)", "net_maker", "maker_fees")]:
        wins = [t for t in trades if t[key] > 0]
        losses = [t for t in trades if t[key] <= 0]
        win_rate = len(wins) / len(trades) * 100 if trades else 0
        avg_gross = sum(t["gross_pnl"] for t in trades) / len(trades)
        avg_fees = sum(t["taker_fees" if fee_key == "taker_fees" else "maker_fees"] for t in trades) / len(trades)
        avg_net = sum(t[key] for t in trades) / len(trades)
        print(f"{mode:45s} | WinRate: {win_rate:5.1f}% | AvgGross: ${avg_gross:+.3f} | AvgFee: ${avg_fees:.3f} | AvgNet: ${avg_net:+.3f}")

    # 2. LONG VS SHORT PERFORMANCE
    print("\n--- 2. DIRECTIONAL PERFORMANCE (TAKER NET) ---")
    for d in ["LONG", "SHORT"]:
        sub = [t for t in trades if t["direction"] == d]
        if not sub: continue
        wins = [t for t in sub if t["net_taker"] > 0]
        avg_gross = sum(t["gross_pnl"] for t in sub) / len(sub)
        avg_net = sum(t["net_taker"] for t in sub) / len(sub)
        print(f"{d:6s} | Trades: {len(sub):3d} | WinRate: {len(wins)/len(sub)*100:5.1f}% | AvgGross: ${avg_gross:+.3f} | AvgNet: ${avg_net:+.3f}")

    # 3. SYMBOL PERFORMANCE
    print("\n--- 3. SYMBOL BREAKDOWN (TAKER NET) ---")
    for s in symbols:
        sub = [t for t in trades if t["symbol"] == s]
        if not sub: continue
        wins = [t for t in sub if t["net_taker"] > 0]
        avg_gross = sum(t["gross_pnl"] for t in sub) / len(sub)
        avg_net = sum(t["net_taker"] for t in sub) / len(sub)
        print(f"{s:8s} | Trades: {len(sub):3d} | WinRate: {len(wins)/len(sub)*100:5.1f}% | AvgGross: ${avg_gross:+.3f} | AvgNet: ${avg_net:+.3f}")

    # 4. REGIME PERFORMANCE
    print("\n--- 4. REGIME PERFORMANCE (TAKER NET) ---")
    for r in ["TRENDING_UP", "TRENDING_DOWN", "RANGING_SIDEWAYS"]:
        sub = [t for t in trades if t["regime"] == r]
        if not sub: continue
        wins = [t for t in sub if t["net_taker"] > 0]
        avg_gross = sum(t["gross_pnl"] for t in sub) / len(sub)
        avg_net = sum(t["net_taker"] for t in sub) / len(sub)
        print(f"{r:18s} | Trades: {len(sub):3d} | WinRate: {len(wins)/len(sub)*100:5.1f}% | AvgGross: ${avg_gross:+.3f} | AvgNet: ${avg_net:+.3f}")

    # 5. EXIT REASON BREAKDOWN
    print("\n--- 5. EXIT REASON ATTRIBUTION ---")
    for ex in ["TARGET_HIT", "5M_PROFIT_TAKE", "10M_EXPIRY", "STOP_LOSS"]:
        sub = [t for t in trades if t["exit_reason"] == ex]
        if not sub: continue
        avg_gross = sum(t["gross_pnl"] for t in sub) / len(sub)
        avg_net = sum(t["net_taker"] for t in sub) / len(sub)
        avg_hold = sum(t["hold_min"] for t in sub) / len(sub)
        print(f"{ex:16s} | Count: {len(sub):3d} ({len(sub)/len(trades)*100:4.1f}%) | AvgGross: ${avg_gross:+.3f} | AvgNet: ${avg_net:+.3f} | AvgHold: {avg_hold:4.1f}m")

    # 6. AVERAGE WIN VS AVERAGE LOSS
    wins = [t for t in trades if t["net_taker"] > 0]
    losses = [t for t in trades if t["net_taker"] <= 0]
    avg_win = sum(t["net_taker"] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t["net_taker"] for t in losses) / len(losses) if losses else 0
    print(f"\n--- 6. PAYOFF RATIO ---")
    print(f"Avg Win: ${avg_win:+.3f} | Avg Loss: ${avg_loss:+.3f} | Ratio: {abs(avg_win/avg_loss):.2f}")

    # 7. NOTIONAL DISTRIBUTION
    notionals = [t["notional"] for t in trades]
    print(f"\n--- 7. POSITION NOTIONAL STATS ---")
    print(f"Min: ${min(notionals):.2f} | Max: ${max(notionals):.2f} | Avg: ${sum(notionals)/len(notionals):.2f}")

run_forensic()
