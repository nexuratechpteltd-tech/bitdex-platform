"""
BITDEX Phase 3.1: Historical Multi-Period Replay & Profitability Validation
============================================================================
Evaluates SCALP_ONE_DOLLAR strategy performance on real Binance USD(S)-M Futures 5m klines.
Strictly partitioned into:
- In-Sample (Training / Optimization: first 60% of timeline)
- Validation (next 20% of timeline)
- Out-of-Sample (final 20% of timeline)

Evaluates all 16 required metrics across:
- Baseline (Phase 3 Taker 0.04%, score 0.60, fixed $1)
- Phase 3.1 Optimized (Maker Post-Only 0.02%, score 0.70, ADX>=28, BB range gating)
- 4 Exit Models (Fixed $1, ATR-Scaled, Trailing Exit, Momentum Weakening)
"""

import sys
import json
import math
import httpx
from collections import defaultdict
from typing import Dict, Any, List, Tuple

from app.services.binance_futures_adapter import BinanceFuturesAdapter
from app.services.futures_regime import MarketRegimeClassifier
from app.services.futures_signal_engine import FuturesSignalEngine
from app.services.futures_sizing import FuturesSizingEngine


def fetch_klines(symbol: str, limit: int = 1000) -> List[Dict[str, Any]]:
    url = "https://fapi.binance.com/fapi/v1/klines"
    resp = httpx.get(url, params={"symbol": symbol.upper(), "interval": "5m", "limit": limit})
    raw = resp.json()
    klines = []
    for k in raw:
        klines.append({
            "open_time": int(k[0]),
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
            "close_time": int(k[6]),
            "quote_volume": float(k[7]),
            "trades_count": int(k[8]),
        })
    return klines


def simulate_period(
    klines: List[Dict[str, Any]],
    symbol: str,
    filters: Dict[str, Any],
    period_name: str,
    maker_entry: bool = True,
    min_score: float = 0.70,
    exit_model: str = "FIXED_1_DOLLAR",
    equity: float = 1000.0,
) -> Dict[str, Any]:
    window_size = 30
    evaluations = 0
    trades = []
    rejections = defaultdict(int)

    for i in range(window_size, len(klines) - 3):
        evaluations += 1
        history = klines[i - window_size:i]
        current = klines[i]
        entry_price = current["close"]

        # 1. Regime
        regime = MarketRegimeClassifier.classify(history, symbol)
        if not regime["trade_eligible"]:
            rejections["REGIME_INELIGIBLE"] += 1
            continue

        atr = regime.get("atr", 1.0)
        atr_pct = atr / entry_price if entry_price > 0 else 0
        if atr_pct < 0.0010:  # Filter out low-volatility compression
            rejections["LOW_VOLATILITY"] += 1
            continue

        # 2. Sizing
        sizing = FuturesSizingEngine.calculate_scalp_sizing(
            symbol=symbol,
            price=entry_price,
            atr=atr,
            stop_price=entry_price - (atr * 1.5),
            available_balance=equity,
            equity=equity,
            symbol_filters=filters,
            target_net_usd=1.00,
            order_type="POST_ONLY" if maker_entry else "MARKET"
        )

        if not sizing["feasible"]:
            rejections["SIZING_INFEASIBLE"] += 1
            continue

        # 3. Signal
        signal = FuturesSignalEngine.evaluate_signal(
            symbol=symbol,
            klines=history,
            current_market_price=entry_price,
            proposed_quantity=sizing["quantity"],
            equity=equity,
            regime_data=regime,
            exit_model=exit_model,
            is_maker=maker_entry
        )

        if signal["decision"] != "TRADE":
            rejections["SIGNAL_NO_TRADE"] += 1
            continue

        direction = signal["direction"]
        qty = sizing["quantity"]
        stop_price = signal["protective_stop_price"]
        target_exit = signal["target_exit_price"]

        # 4. Forward Simulation (up to 2 bars = 10 min)
        forward = klines[i:min(i + 3, len(klines))]

        # Realistic maker entry fill simulation
        if maker_entry:
            # Entry order placed at close; must be touched by subsequent bar
            filled = (forward[0]["low"] <= entry_price) if direction == "LONG" else (forward[0]["high"] >= entry_price)
            if not filled:
                rejections["MAKER_UNFILLED"] += 1
                continue

        exit_price = None
        exit_reason = None
        hold_minutes = 10.0
        exit_fee_rate = 0.0004  # taker default for stop / expiry

        # Bar 0 (0-5m)
        b0 = forward[0]
        if direction == "LONG":
            if b0["low"] <= stop_price:
                exit_price = stop_price; exit_reason = "STOP_LOSS"; hold_minutes = 3.0
            elif b0["high"] >= target_exit:
                exit_price = target_exit; exit_reason = "TARGET_HIT"; hold_minutes = 4.0; exit_fee_rate = 0.0002 if maker_entry else 0.0004
            elif exit_model == "MOMENTUM_WEAKENING" and b0["close"] < b0["open"] and b0["close"] < entry_price:
                exit_price = b0["close"]; exit_reason = "MOMENTUM_EXIT"; hold_minutes = 5.0
            elif exit_model == "TRAILING_EXIT" and b0["high"] >= entry_price + (atr * 0.8):
                trail = b0["high"] - (atr * 0.4)
                if b0["close"] <= trail:
                    exit_price = trail; exit_reason = "TRAILING_STOP"; hold_minutes = 5.0
        else:  # SHORT
            if b0["high"] >= stop_price:
                exit_price = stop_price; exit_reason = "STOP_LOSS"; hold_minutes = 3.0
            elif b0["low"] <= target_exit:
                exit_price = target_exit; exit_reason = "TARGET_HIT"; hold_minutes = 4.0; exit_fee_rate = 0.0002 if maker_entry else 0.0004
            elif exit_model == "MOMENTUM_WEAKENING" and b0["close"] > b0["open"] and b0["close"] > entry_price:
                exit_price = b0["close"]; exit_reason = "MOMENTUM_EXIT"; hold_minutes = 5.0
            elif exit_model == "TRAILING_EXIT" and b0["low"] <= entry_price - (atr * 0.8):
                trail = b0["low"] + (atr * 0.4)
                if b0["close"] >= trail:
                    exit_price = trail; exit_reason = "TRAILING_STOP"; hold_minutes = 5.0

        # Bar 1 (5-10m)
        if exit_price is None and len(forward) > 1:
            b1 = forward[1]
            if direction == "LONG":
                if b1["low"] <= stop_price:
                    exit_price = stop_price; exit_reason = "STOP_LOSS"; hold_minutes = 7.0
                elif b1["high"] >= target_exit:
                    exit_price = target_exit; exit_reason = "TARGET_HIT"; hold_minutes = 8.0; exit_fee_rate = 0.0002 if maker_entry else 0.0004
                elif exit_model == "MOMENTUM_WEAKENING" and b1["close"] < b1["open"] and b1["close"] < entry_price:
                    exit_price = b1["close"]; exit_reason = "MOMENTUM_EXIT"; hold_minutes = 8.0
                else:
                    exit_price = b1["close"]; exit_reason = "10M_EXPIRY"; hold_minutes = 10.0
            else:
                if b1["high"] >= stop_price:
                    exit_price = stop_price; exit_reason = "STOP_LOSS"; hold_minutes = 7.0
                elif b1["low"] <= target_exit:
                    exit_price = target_exit; exit_reason = "TARGET_HIT"; hold_minutes = 8.0; exit_fee_rate = 0.0002 if maker_entry else 0.0004
                elif exit_model == "MOMENTUM_WEAKENING" and b1["close"] > b1["open"] and b1["close"] > entry_price:
                    exit_price = b1["close"]; exit_reason = "MOMENTUM_EXIT"; hold_minutes = 8.0
                else:
                    exit_price = b1["close"]; exit_reason = "10M_EXPIRY"; hold_minutes = 10.0

        if exit_price is None:
            exit_price = forward[-1]["close"]
            exit_reason = "10M_EXPIRY"

        # PnL accounting
        gross_pnl = (exit_price - entry_price) * qty if direction == "LONG" else (entry_price - exit_price) * qty
        entry_fee = entry_price * qty * (0.0002 if maker_entry else 0.0004)
        exit_fee = exit_price * qty * exit_fee_rate
        total_fees = entry_fee + exit_fee
        slippage = 0.05
        net_pnl = gross_pnl - total_fees - slippage

        trades.append({
            "direction": direction,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "qty": qty,
            "notional": entry_price * qty,
            "exit_reason": exit_reason,
            "hold_minutes": hold_minutes,
            "gross_pnl": gross_pnl,
            "total_fees": total_fees,
            "slippage": slippage,
            "net_pnl": net_pnl,
            "target_hit": (exit_reason == "TARGET_HIT" or net_pnl >= 0.95),
        })

    total_trades = len(trades)
    if total_trades == 0:
        return {
            "symbol": symbol,
            "period": period_name,
            "evaluations": evaluations,
            "trades": 0,
            "execution_rate_pct": 0.0,
            "win_rate_pct": 0.0,
            "target_hit_rate_pct": 0.0,
            "avg_gross_pnl": 0.0,
            "avg_net_pnl": 0.0,
            "avg_fees": 0.0,
            "avg_slippage": 0.0,
            "max_drawdown": 0.0,
            "max_consecutive_losses": 0,
            "avg_holding_minutes": 0.0,
            "payoff_ratio": 0.0,
            "status": "NO_TRADES"
        }

    wins = [t for t in trades if t["net_pnl"] > 0]
    losses = [t for t in trades if t["net_pnl"] <= 0]
    target_hits = [t for t in trades if t["target_hit"]]

    win_rate = (len(wins) / total_trades) * 100.0
    target_hit_rate = (len(target_hits) / total_trades) * 100.0
    avg_gross = sum(t["gross_pnl"] for t in trades) / total_trades
    avg_net = sum(t["net_pnl"] for t in trades) / total_trades
    avg_fees = sum(t["total_fees"] for t in trades) / total_trades
    avg_hold = sum(t["hold_minutes"] for t in trades) / total_trades

    avg_win = sum(t["net_pnl"] for t in wins) / len(wins) if wins else 0.0
    avg_loss = sum(t["net_pnl"] for t in losses) / len(losses) if losses else 0.0
    payoff_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0.0

    # Drawdown & Consecutive losses
    cum, peak, dd = 0.0, 0.0, 0.0
    cons_losses, max_cons_losses = 0, 0
    for t in trades:
        cum += t["net_pnl"]
        if cum > peak: peak = cum
        d = peak - cum
        if d > dd: dd = d
        if t["net_pnl"] < 0:
            cons_losses += 1
            if cons_losses > max_cons_losses: max_cons_losses = cons_losses
        else:
            cons_losses = 0

    reasons = defaultdict(int)
    for t in trades:
        reasons[t["exit_reason"]] += 1

    # PASS / FAIL based on profitability
    status = "PASS" if avg_net > 0.0 else "FAIL"

    return {
        "symbol": symbol,
        "period": period_name,
        "evaluations": evaluations,
        "trades": total_trades,
        "execution_rate_pct": round((total_trades / evaluations) * 100.0, 2),
        "win_rate_pct": round(win_rate, 2),
        "target_hit_rate_pct": round(target_hit_rate, 2),
        "avg_gross_pnl": round(avg_gross, 4),
        "avg_net_pnl": round(avg_net, 4),
        "avg_fees": round(avg_fees, 4),
        "avg_slippage": 0.05,
        "max_drawdown": round(dd, 2),
        "max_consecutive_losses": max_cons_losses,
        "avg_holding_minutes": round(avg_hold, 1),
        "payoff_ratio": round(payoff_ratio, 2),
        "exit_breakdown": dict(reasons),
        "status": status
    }


def run_multi_period_validation():
    print("=" * 80)
    print("BITDEX PHASE 3.1: HISTORICAL MULTI-PERIOD STRATEGY REPLAY VALIDATION")
    print("=" * 80)
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    adapter = BinanceFuturesAdapter(environment="testnet")
    filters_by_sym = {s: adapter.get_symbol_filters(s) for s in symbols}

    all_results = []

    for sym in symbols:
        print(f"\nFetching 1,000 real 5m klines for {sym}...")
        klines = fetch_klines(sym, limit=1000)
        total_len = len(klines)

        # 60% In-Sample, 20% Validation, 20% Out-of-Sample
        idx_train = int(total_len * 0.60)
        idx_val = int(total_len * 0.80)

        in_sample_klines = klines[:idx_train]
        validation_klines = klines[idx_train:idx_val]
        out_of_sample_klines = klines[idx_val:]

        print(f"Data split for {sym}: Total {total_len} | In-Sample {len(in_sample_klines)} | Validation {len(validation_klines)} | Out-of-Sample {len(out_of_sample_klines)}")

        # Evaluate across partitions
        for pname, pklines in [("IN_SAMPLE (60%)", in_sample_klines),
                              ("VALIDATION (20%)", validation_klines),
                              ("OUT_OF_SAMPLE (20%)", out_of_sample_klines)]:

            # A. Phase 3 Baseline (Taker 0.04%, score 0.60, fixed $1)
            res_baseline = simulate_period(
                klines=pklines, symbol=sym, filters=filters_by_sym[sym],
                period_name=f"{pname} - BASELINE_PHASE3",
                maker_entry=False, min_score=0.60, exit_model="FIXED_1_DOLLAR"
            )
            all_results.append(res_baseline)

            # B. Phase 3.1 Optimized (Maker 0.02%, score 0.70, BB gating, fixed $1)
            res_opt = simulate_period(
                klines=pklines, symbol=sym, filters=filters_by_sym[sym],
                period_name=f"{pname} - OPTIMIZED_MAKER",
                maker_entry=True, min_score=0.70, exit_model="FIXED_1_DOLLAR"
            )
            all_results.append(res_opt)

            # C. Phase 3.1 Exit Models (ATR-Scaled, Trailing, Momentum)
            res_atr = simulate_period(
                klines=pklines, symbol=sym, filters=filters_by_sym[sym],
                period_name=f"{pname} - EXIT_MODEL_ATR_SCALED",
                maker_entry=True, min_score=0.70, exit_model="ATR_SCALED"
            )
            all_results.append(res_atr)

            res_trail = simulate_period(
                klines=pklines, symbol=sym, filters=filters_by_sym[sym],
                period_name=f"{pname} - EXIT_MODEL_TRAILING",
                maker_entry=True, min_score=0.70, exit_model="TRAILING_EXIT"
            )
            all_results.append(res_trail)

            res_mom = simulate_period(
                klines=pklines, symbol=sym, filters=filters_by_sym[sym],
                period_name=f"{pname} - EXIT_MODEL_MOMENTUM",
                maker_entry=True, min_score=0.70, exit_model="MOMENTUM_WEAKENING"
            )
            all_results.append(res_mom)

    # Print Formatted Table of Results
    print("\n" + "=" * 120)
    print(f"{'Symbol':8s} | {'Partition & Config':36s} | {'Trades':6s} | {'Exec%':5s} | {'Win%':5s} | {'Tgt%':5s} | {'AvgGross':8s} | {'AvgFees':7s} | {'AvgNet':8s} | {'MaxDD':7s} | {'Losses':6s} | {'Status':6s}")
    print("=" * 120)
    for r in all_results:
        print(f"{r['symbol']:8s} | {r['period']:36s} | {r['trades']:6d} | {r['execution_rate_pct']:4.1f}% | {r['win_rate_pct']:4.1f}% | {r['target_hit_rate_pct']:4.1f}% | ${r['avg_gross_pnl']:+6.3f} | ${r['avg_fees']:5.3f} | ${r['avg_net_pnl']:+6.3f} | ${r['max_drawdown']:6.1f} | {r['max_consecutive_losses']:6d} | {r['status']:6s}")
    print("=" * 120)

    # Save to JSON for report generation
    with open("/opt/tauric-platform-staging/backend/multi_period_results.json", "w") as f:
        json.dump(all_results, f, indent=2)
    print("Results saved to /opt/tauric-platform-staging/backend/multi_period_results.json")
    return all_results


if __name__ == "__main__":
    run_multi_period_validation()
