import sys
import math
import httpx
from collections import defaultdict
from app.services.futures_regime import MarketRegimeClassifier
from app.services.futures_sizing import FuturesSizingEngine

def calculate_bollinger_bands(closes, period=20, std_dev=2.0):
    if len(closes) < period:
        return 0.0, 0.0, 0.0
    recent = closes[-period:]
    sma = sum(recent) / period
    variance = sum((x - sma) ** 2 for x in recent) / period
    std = math.sqrt(variance)
    return sma - (std_dev * std), sma, sma + (std_dev * std)

def fetch_1000_klines(symbol):
    r = httpx.get("https://fapi.binance.com/fapi/v1/klines", params={"symbol": symbol, "interval": "5m", "limit": 1000})
    data = r.json()
    return [{
        "open_time": int(k[0]), "open": float(k[1]), "high": float(k[2]),
        "low": float(k[3]), "close": float(k[4]), "volume": float(k[5]),
        "close_time": int(k[6]), "quote_volume": float(k[7]), "trades_count": int(k[8])
    } for k in data]

def run_experiment(klines_by_symbol, filters_by_symbol, 
                   maker_entry=True,
                   min_score=0.70,
                   adx_min=28.0,
                   ranging_bb_filter=True,
                   exit_model="atr_scaled",  # "fixed", "atr_scaled", "trailing", "momentum"
                   min_atr_pct=0.0012):
    
    trades = []
    evaluations = 0

    for sym, klines in klines_by_symbol.items():
        filters = filters_by_symbol[sym]
        window_size = 30
        
        for i in range(window_size, len(klines) - 3):
            evaluations += 1
            history = klines[i - window_size:i]
            current = klines[i]
            entry_price = current["close"]

            regime = MarketRegimeClassifier.classify(history, sym)
            regime_name = regime["regime"]
            if not regime["trade_eligible"]:
                continue

            atr = regime.get("atr", 1.0)
            atr_pct = atr / entry_price if entry_price > 0 else 0
            if atr_pct < min_atr_pct:
                continue

            adx = regime.get("adx", 20.0)
            if regime_name in ("TRENDING_UP", "TRENDING_DOWN") and adx < adx_min:
                continue

            closes = [k["close"] for k in history]
            highs = [k["high"] for k in history]
            lows = [k["low"] for k in history]

            # Bollinger band filter for ranging
            if regime_name == "RANGING_SIDEWAYS" and ranging_bb_filter:
                lower_bb, mid_bb, upper_bb = calculate_bollinger_bands(closes, 20, 2.0)
                band_width = upper_bb - lower_bb
                if band_width <= 0:
                    continue
                # If price is in middle 60% of bands, skip mean reversion
                dist_from_lower = (entry_price - lower_bb) / band_width
                # We only want to buy when near lower band (<0.25) or sell when near upper band (>0.75)
                # If middle, skip
                if 0.25 < dist_from_lower < 0.75:
                    continue

            # Sizing
            sizing = FuturesSizingEngine.calculate_scalp_sizing(
                symbol=sym, price=entry_price, atr=atr,
                stop_price=entry_price - (atr * 1.8),
                available_balance=1000.0, equity=1000.0,
                symbol_filters=filters, target_net_usd=1.00
            )
            if not sizing["feasible"]:
                continue

            # Signal scoring with higher bar
            ema9 = MarketRegimeClassifier.calculate_ema(closes, 9)
            ema21 = MarketRegimeClassifier.calculate_ema(closes, 21)
            prev_close = closes[-2]
            candle_body = current["close"] - current["open"]

            # RSI
            gains = [max(0.0, closes[j] - closes[j-1]) for j in range(1, len(closes))]
            losses = [max(0.0, closes[j-1] - closes[j]) for j in range(1, len(closes))]
            avg_gain = sum(gains[-14:]) / 14.0 if gains else 0.0
            avg_loss = sum(losses[-14:]) / 14.0 if losses else 0.0
            rs = (avg_gain / avg_loss) if avg_loss > 0 else 100.0
            rsi = 100.0 - (100.0 / (1.0 + rs))

            long_score, short_score = 0.0, 0.0
            if ema9 > ema21: long_score += 0.35
            elif ema9 < ema21: short_score += 0.35

            if current["close"] > prev_close and candle_body > 0: long_score += 0.25
            elif current["close"] < prev_close and candle_body < 0: short_score += 0.25

            if 45.0 <= rsi <= 65.0: long_score += 0.20
            elif 35.0 <= rsi <= 55.0: short_score += 0.20

            recent_high_10 = max(highs[-10:-1])
            recent_low_10 = min(lows[-10:-1])
            if current["close"] >= recent_high_10 * 0.999: long_score += 0.20
            elif current["close"] <= recent_low_10 * 1.001: short_score += 0.20

            permitted = regime.get("permitted_directions", [])
            if "LONG" not in permitted: long_score = 0.0
            if "SHORT" not in permitted: short_score = 0.0

            best_dir = None
            best_score = 0.0
            if long_score > short_score and long_score >= min_score:
                best_dir = "LONG"; best_score = long_score
            elif short_score > long_score and short_score >= min_score:
                best_dir = "SHORT"; best_score = short_score
            else:
                continue

            # Ranging filter directional check
            if regime_name == "RANGING_SIDEWAYS" and ranging_bb_filter:
                lower_bb, mid_bb, upper_bb = calculate_bollinger_bands(closes, 20, 2.0)
                band_width = upper_bb - lower_bb
                dist_from_lower = (entry_price - lower_bb) / band_width
                if best_dir == "LONG" and dist_from_lower > 0.30:
                    continue  # Only long near bottom of range
                if best_dir == "SHORT" and dist_from_lower < 0.70:
                    continue  # Only short near top of range

            qty = sizing["quantity"]
            stop_mult = 1.8
            stop_dist = max(0.0025 * entry_price, min(0.045 * entry_price, atr * stop_mult))
            stop_price = (entry_price - stop_dist) if best_dir == "LONG" else (entry_price + stop_dist)

            # Target exit calculation based on exit model
            if exit_model == "fixed":
                target_net = 1.00
            elif exit_model == "atr_scaled":
                # ATR scaled target: higher volatility gives larger scalp targets, improving payoff ratio
                # e.g., target gross = 1.0 * ATR * qty, minus fees
                est_gross = 1.2 * atr * qty
                target_net = max(1.00, est_gross - (entry_price * qty * 0.0008) - 0.05)
            elif exit_model in ("trailing", "momentum"):
                target_net = 1.00

            # Solve target exit price
            # Fee assumption: if maker_entry, entry fee is 0.02%. Exit can be maker (0.02%) if limit hit, or taker (0.04%) if stopped.
            entry_fee_rate = 0.0002 if maker_entry else 0.0004
            target_exit_fee_rate = 0.0002 if maker_entry else 0.0004
            
            # Target exit formula:
            # (exit - entry)*qty - entry*qty*fee1 - exit*qty*fee2 - slippage = target_net
            target_friction = target_net + 0.05
            if best_dir == "LONG":
                target_exit = (target_friction + entry_price * qty * (1.0 + entry_fee_rate)) / (qty * (1.0 - target_exit_fee_rate))
            else:
                target_exit = (entry_price * qty * (1.0 - entry_fee_rate) - target_friction) / (qty * (1.0 + target_exit_fee_rate))

            # Simulate Forward Bars (Bar 0, 1, 2)
            forward_bars = klines[i:min(i + 3, len(klines))]
            exit_price = None
            exit_reason = None
            hold_min = 10.0
            exit_fee_rate = 0.0004  # default taker on exit

            # Check maker entry fill: in next bar, did price touch entry_price?
            if maker_entry:
                # Realistic fill check: did bar 0 low <= entry_price (for LONG) or high >= entry_price (for SHORT)?
                # If we entered at close of previous candle, a maker order sits at that close. In bar 0:
                filled = (forward_bars[0]["low"] <= entry_price) if best_dir == "LONG" else (forward_bars[0]["high"] >= entry_price)
                if not filled:
                    # Order was not filled as maker
                    continue

            # Now evaluate forward bars
            # Bar 0 (0-5 min)
            bar0 = forward_bars[0]
            if best_dir == "LONG":
                if bar0["low"] <= stop_price:
                    exit_price = stop_price; exit_reason = "STOP_LOSS"; hold_min = 3.0; exit_fee_rate = 0.0004
                elif bar0["high"] >= target_exit:
                    exit_price = target_exit; exit_reason = "TARGET_HIT"; hold_min = 4.0; exit_fee_rate = 0.0002
                elif exit_model == "momentum" and bar0["close"] < bar0["open"] and (bar0["close"] < entry_price):
                    # Momentum reversal: candle closed bearish below entry
                    exit_price = bar0["close"]; exit_reason = "MOMENTUM_EXIT"; hold_min = 5.0; exit_fee_rate = 0.0004
                elif exit_model == "trailing" and bar0["high"] >= entry_price + (atr * 0.8):
                    # Trailing stop locked in
                    trailing_stop = bar0["high"] - (atr * 0.4)
                    if bar0["close"] <= trailing_stop:
                        exit_price = trailing_stop; exit_reason = "TRAILING_STOP"; hold_min = 5.0; exit_fee_rate = 0.0004
            else:
                if bar0["high"] >= stop_price:
                    exit_price = stop_price; exit_reason = "STOP_LOSS"; hold_min = 3.0; exit_fee_rate = 0.0004
                elif bar0["low"] <= target_exit:
                    exit_price = target_exit; exit_reason = "TARGET_HIT"; hold_min = 4.0; exit_fee_rate = 0.0002
                elif exit_model == "momentum" and bar0["close"] > bar0["open"] and (bar0["close"] > entry_price):
                    exit_price = bar0["close"]; exit_reason = "MOMENTUM_EXIT"; hold_min = 5.0; exit_fee_rate = 0.0004
                elif exit_model == "trailing" and bar0["low"] <= entry_price - (atr * 0.8):
                    trailing_stop = bar0["low"] + (atr * 0.4)
                    if bar0["close"] >= trailing_stop:
                        exit_price = trailing_stop; exit_reason = "TRAILING_STOP"; hold_min = 5.0; exit_fee_rate = 0.0004

            # Bar 1 (5-10 min)
            if exit_price is None and len(forward_bars) > 1:
                bar1 = forward_bars[1]
                if best_dir == "LONG":
                    if bar1["low"] <= stop_price:
                        exit_price = stop_price; exit_reason = "STOP_LOSS"; hold_min = 7.0; exit_fee_rate = 0.0004
                    elif bar1["high"] >= target_exit:
                        exit_price = target_exit; exit_reason = "TARGET_HIT"; hold_min = 8.0; exit_fee_rate = 0.0002
                    elif exit_model == "momentum" and bar1["close"] < bar1["open"] and bar1["close"] < entry_price:
                        exit_price = bar1["close"]; exit_reason = "MOMENTUM_EXIT"; hold_min = 8.0; exit_fee_rate = 0.0004
                    else:
                        exit_price = bar1["close"]; exit_reason = "10M_EXPIRY"; hold_min = 10.0; exit_fee_rate = 0.0004
                else:
                    if bar1["high"] >= stop_price:
                        exit_price = stop_price; exit_reason = "STOP_LOSS"; hold_min = 7.0; exit_fee_rate = 0.0004
                    elif bar1["low"] <= target_exit:
                        exit_price = target_exit; exit_reason = "TARGET_HIT"; hold_min = 8.0; exit_fee_rate = 0.0002
                    elif exit_model == "momentum" and bar1["close"] > bar1["open"] and bar1["close"] > entry_price:
                        exit_price = bar1["close"]; exit_reason = "MOMENTUM_EXIT"; hold_min = 8.0; exit_fee_rate = 0.0004
                    else:
                        exit_price = bar1["close"]; exit_reason = "10M_EXPIRY"; hold_min = 10.0; exit_fee_rate = 0.0004

            if exit_price is None:
                exit_price = forward_bars[-1]["close"]
                exit_reason = "10M_EXPIRY"
                exit_fee_rate = 0.0004

            # PnL computation
            gross_pnl = (exit_price - entry_price) * qty if best_dir == "LONG" else (entry_price - exit_price) * qty
            entry_fee = entry_price * qty * (0.0002 if maker_entry else 0.0004)
            exit_fee = exit_price * qty * exit_fee_rate
            total_fees = entry_fee + exit_fee
            slippage = 0.05
            net_pnl = gross_pnl - total_fees - slippage

            trades.append({
                "symbol": sym, "direction": best_dir, "regime": regime_name,
                "gross_pnl": gross_pnl, "total_fees": total_fees, "net_pnl": net_pnl,
                "exit_reason": exit_reason, "hold_min": hold_min
            })

    if not trades:
        return {"trades": 0, "win_rate": 0, "avg_gross": 0, "avg_net": 0, "drawdown": 0}

    wins = [t for t in trades if t["net_pnl"] > 0]
    win_rate = len(wins) / len(trades) * 100
    avg_gross = sum(t["gross_pnl"] for t in trades) / len(trades)
    avg_fees = sum(t["total_fees"] for t in trades) / len(trades)
    avg_net = sum(t["net_pnl"] for t in trades) / len(trades)

    cum, peak, dd = 0, 0, 0
    cons_loss, max_cons_loss = 0, 0
    for t in trades:
        cum += t["net_pnl"]
        if cum > peak: peak = cum
        d = peak - cum
        if d > dd: dd = d
        if t["net_pnl"] < 0:
            cons_loss += 1
            if cons_loss > max_cons_loss: max_cons_loss = cons_loss
        else:
            cons_loss = 0

    reasons = defaultdict(int)
    for t in trades:
        reasons[t["exit_reason"]] += 1

    return {
        "evaluations": evaluations,
        "trades": len(trades),
        "trade_rate_pct": round(len(trades) / evaluations * 100, 2),
        "win_rate": round(win_rate, 2),
        "avg_gross": round(avg_gross, 4),
        "avg_fees": round(avg_fees, 4),
        "avg_net": round(avg_net, 4),
        "drawdown": round(dd, 2),
        "max_cons_losses": max_cons_loss,
        "reasons": dict(reasons)
    }

def main():
    print("Fetching 1000 klines for BTCUSDT, ETHUSDT, SOLUSDT...")
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    klines_by_sym = {s: fetch_1000_klines(s) for s in symbols}
    from app.services.binance_futures_adapter import BinanceFuturesAdapter
    adapter = BinanceFuturesAdapter(environment="testnet")
    filters_by_sym = {s: adapter.get_symbol_filters(s) for s in symbols}

    print("\n=== EXPERIMENT 1: BASELINE (Taker 0.04%, score 0.60, fixed ) ===")
    r1 = run_experiment(klines_by_sym, filters_by_sym, maker_entry=False, min_score=0.60, adx_min=25.0, ranging_bb_filter=False, exit_model="fixed", min_atr_pct=0.0005)
    print(r1)

    print("\n=== EXPERIMENT 2: MAKER POST-ONLY ENTRY (0.02% maker, score 0.60, fixed ) ===")
    r2 = run_experiment(klines_by_sym, filters_by_sym, maker_entry=True, min_score=0.60, adx_min=25.0, ranging_bb_filter=False, exit_model="fixed", min_atr_pct=0.0005)
    print(r2)

    print("\n=== EXPERIMENT 3: MAKER + STRICT SIGNAL FILTERS (score 0.70, ADX>=28, BB range gating) ===")
    r3 = run_experiment(klines_by_sym, filters_by_sym, maker_entry=True, min_score=0.70, adx_min=28.0, ranging_bb_filter=True, exit_model="fixed", min_atr_pct=0.0012)
    print(r3)

    print("\n=== EXPERIMENT 4: MAKER + STRICT FILTERS + ATR-SCALED EXIT MODEL ===")
    r4 = run_experiment(klines_by_sym, filters_by_sym, maker_entry=True, min_score=0.70, adx_min=28.0, ranging_bb_filter=True, exit_model="atr_scaled", min_atr_pct=0.0012)
    print(r4)

    print("\n=== EXPERIMENT 5: MAKER + STRICT FILTERS + MOMENTUM WEAKENING EXIT MODEL ===")
    r5 = run_experiment(klines_by_sym, filters_by_sym, maker_entry=True, min_score=0.70, adx_min=28.0, ranging_bb_filter=True, exit_model="momentum", min_atr_pct=0.0012)
    print(r5)

    print("\n=== EXPERIMENT 6: MAKER + STRICT FILTERS + TRAILING EXIT MODEL ===")
    r6 = run_experiment(klines_by_sym, filters_by_sym, maker_entry=True, min_score=0.70, adx_min=28.0, ranging_bb_filter=True, exit_model="trailing", min_atr_pct=0.0012)
    print(r6)

if __name__ == "__main__":
    main()
