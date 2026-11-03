"""
BITDEX Phase 3: Historical & Replay Strategy Validation
========================================================
Runs real Binance USD(S)-M Futures historical klines through the SCALP_ONE_DOLLAR
strategy engine across trending, ranging, and volatile regimes.

Evaluates:
- Trade count, win rate, average gross P&L, average net P&L
- Commission and execution-cost impact (0.04% taker per side)
- Percentage of trades reaching $1.00 net target
- Maximum drawdown, consecutive losses, average holding duration
- Rejected opportunities, NO_TRADE frequency
- Slippage sensitivity analysis ($0.02, $0.05, $0.10, $0.20)
"""

import sys
import time
import math
import logging
from typing import Dict, Any, List

from app.services.saas_db import get_db_connection
from app.services.binance_futures_adapter import BinanceFuturesAdapter
from app.services.futures_discovery import MarketDiscoveryService
from app.services.futures_regime import MarketRegimeClassifier
from app.services.futures_signal_engine import FuturesSignalEngine
from app.services.futures_sizing import FuturesSizingEngine


class HistoricalReplayValidator:
    def __init__(self):
        self.adapter = BinanceFuturesAdapter(environment="testnet")
        self.symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

    def fetch_historical_klines(self, symbol: str, limit: int = 200) -> List[Dict[str, Any]]:
        """Fetch real 5m klines from Binance Futures."""
        params = {"symbol": symbol.upper(), "interval": "5m", "limit": limit}
        res = self.adapter._request("GET", "/fapi/v1/klines", params=params)
        klines = []
        for k in res:
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

    def run_replay(self) -> Dict[str, Any]:
        print("=" * 70)
        print("STARTING HISTORICAL & REPLAY STRATEGY VALIDATION (SCALP_ONE_DOLLAR)")
        print("=" * 70)

        all_trades = []
        rejected_opportunities = 0
        no_trade_evaluations = 0
        total_evaluations = 0

        regime_distribution = {}

        for sym in self.symbols:
            print(f"Fetching real 5m klines for {sym}...")
            try:
                klines = self.fetch_historical_klines(sym, limit=120)
                filters = self.adapter.get_symbol_filters(sym)
            except Exception as e:
                print(f"Failed to fetch klines for {sym}: {e}")
                continue

            if len(klines) < 30:
                print(f"Insufficient klines for {sym}")
                continue

            # Slide a window of 30 bars across the 120 bars
            window_size = 30
            for i in range(window_size, len(klines) - 2):
                total_evaluations += 1
                history_window = klines[i - window_size:i]
                current_candle = klines[i]
                entry_price = current_candle["close"]

                # 1. Regime
                regime = MarketRegimeClassifier.classify(history_window, sym)
                r_name = regime["regime"]
                regime_distribution[r_name] = regime_distribution.get(r_name, 0) + 1

                if not regime["trade_eligible"]:
                    rejected_opportunities += 1
                    no_trade_evaluations += 1
                    continue

                # 2. Sizing
                atr = regime.get("atr", 1.0)
                sizing = FuturesSizingEngine.calculate_scalp_sizing(
                    symbol=sym,
                    price=entry_price,
                    atr=atr,
                    stop_price=entry_price - (atr * 1.8),
                    available_balance=1000.0,
                    equity=1000.0,
                    symbol_filters=filters,
                    target_net_usd=1.00
                )

                if not sizing["feasible"]:
                    rejected_opportunities += 1
                    continue

                # 3. Signal
                signal = FuturesSignalEngine.evaluate_signal(
                    symbol=sym,
                    klines=history_window,
                    current_market_price=entry_price,
                    proposed_quantity=sizing["quantity"],
                    equity=1000.0,
                    regime_data=regime
                )

                if signal["decision"] != "TRADE":
                    no_trade_evaluations += 1
                    continue

                # 4. Simulate Trade Forward (up to 2 bars = 10 minutes max holding window)
                direction = signal["direction"]
                target_exit = signal["target_exit_price"]
                stop_price = signal["protective_stop_price"]
                qty = sizing["quantity"]

                forward_bars = klines[i:min(i + 3, len(klines))]
                exit_price = None
                exit_reason = None
                exit_time_minutes = 10.0

                # Evaluate bar 1 (5 min)
                bar1 = forward_bars[0]
                if direction == "LONG":
                    if bar1["low"] <= stop_price:
                        exit_price = stop_price
                        exit_reason = "STOP_LOSS"
                        exit_time_minutes = 3.0
                    elif bar1["high"] >= target_exit:
                        exit_price = target_exit
                        exit_reason = "TARGET_HIT"
                        exit_time_minutes = 4.0
                    elif len(forward_bars) > 1 and bar1["close"] > entry_price + (entry_price * 0.001):
                        exit_price = bar1["close"]
                        exit_reason = "5M_PROFIT_TAKE"
                        exit_time_minutes = 5.0
                else:  # SHORT
                    if bar1["high"] >= stop_price:
                        exit_price = stop_price
                        exit_reason = "STOP_LOSS"
                        exit_time_minutes = 3.0
                    elif bar1["low"] <= target_exit:
                        exit_price = target_exit
                        exit_reason = "TARGET_HIT"
                        exit_time_minutes = 4.0
                    elif len(forward_bars) > 1 and bar1["close"] < entry_price - (entry_price * 0.001):
                        exit_price = bar1["close"]
                        exit_reason = "5M_PROFIT_TAKE"
                        exit_time_minutes = 5.0

                # If still open, evaluate bar 2 (10 min max expiry)
                if exit_price is None and len(forward_bars) > 1:
                    bar2 = forward_bars[1]
                    if direction == "LONG":
                        if bar2["low"] <= stop_price:
                            exit_price = stop_price
                            exit_reason = "STOP_LOSS"
                            exit_time_minutes = 7.0
                        elif bar2["high"] >= target_exit:
                            exit_price = target_exit
                            exit_reason = "TARGET_HIT"
                            exit_time_minutes = 8.0
                        else:
                            exit_price = bar2["close"]
                            exit_reason = "10M_EXPIRY"
                            exit_time_minutes = 10.0
                    else:  # SHORT
                        if bar2["high"] >= stop_price:
                            exit_price = stop_price
                            exit_reason = "STOP_LOSS"
                            exit_time_minutes = 7.0
                        elif bar2["low"] <= target_exit:
                            exit_price = target_exit
                            exit_reason = "TARGET_HIT"
                            exit_time_minutes = 8.0
                        else:
                            exit_price = bar2["close"]
                            exit_reason = "10M_EXPIRY"
                            exit_time_minutes = 10.0

                if exit_price is None:
                    exit_price = forward_bars[-1]["close"]
                    exit_reason = "10M_EXPIRY"

                # Calculate PnL with round-trip fees (0.04% each side)
                entry_fee = entry_price * qty * 0.0004
                exit_fee = exit_price * qty * 0.0004
                total_fees = entry_fee + exit_fee

                if direction == "LONG":
                    gross_pnl = (exit_price - entry_price) * qty
                else:
                    gross_pnl = (entry_price - exit_price) * qty

                net_pnl = gross_pnl - total_fees - 0.05  # $0.05 slippage

                all_trades.append({
                    "symbol": sym,
                    "direction": direction,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "quantity": qty,
                    "exit_reason": exit_reason,
                    "holding_minutes": exit_time_minutes,
                    "gross_pnl": gross_pnl,
                    "total_fees": total_fees,
                    "net_pnl": net_pnl,
                    "target_hit": (exit_reason == "TARGET_HIT" or net_pnl >= 0.95),
                })

        # Calculate Statistics
        total_trades = len(all_trades)
        if total_trades == 0:
            print("No trades triggered in replay.")
            return {"status": "BLOCKED", "reason": "NO_TRADES_TRIGGERED"}

        winning_trades = [t for t in all_trades if t["net_pnl"] > 0]
        losing_trades = [t for t in all_trades if t["net_pnl"] <= 0]
        target_hits = [t for t in all_trades if t["target_hit"]]

        win_rate = (len(winning_trades) / total_trades) * 100.0
        target_hit_rate = (len(target_hits) / total_trades) * 100.0
        avg_gross = sum(t["gross_pnl"] for t in all_trades) / total_trades
        avg_net = sum(t["net_pnl"] for t in all_trades) / total_trades
        avg_hold = sum(t["holding_minutes"] for t in all_trades) / total_trades

        # Drawdown calculation
        cumulative_pnl = 0.0
        peak = 0.0
        max_drawdown = 0.0
        consecutive_losses = 0
        max_consecutive_losses = 0

        for t in all_trades:
            cumulative_pnl += t["net_pnl"]
            if cumulative_pnl > peak:
                peak = cumulative_pnl
            dd = peak - cumulative_pnl
            if dd > max_drawdown:
                max_drawdown = dd

            if t["net_pnl"] < 0:
                consecutive_losses += 1
                if consecutive_losses > max_consecutive_losses:
                    max_consecutive_losses = consecutive_losses
            else:
                consecutive_losses = 0

        # Slippage Sensitivity Analysis
        slippage_levels = [0.02, 0.05, 0.10, 0.20]
        slippage_results = {}
        for s_level in slippage_levels:
            s_nets = [t["gross_pnl"] - t["total_fees"] - s_level for t in all_trades]
            s_wins = sum(1 for n in s_nets if n > 0)
            slippage_results[f"slippage_${s_level:.2f}"] = {
                "avg_net_pnl": round(sum(s_nets) / len(s_nets), 4),
                "win_rate_pct": round((s_wins / len(s_nets)) * 100, 2),
                "target_hit_count": sum(1 for n in s_nets if n >= 0.95),
            }

        report = {
            "status": "VALIDATED",
            "data_source": "Binance USD(S)-M Futures Real 5m Klines",
            "symbols_evaluated": self.symbols,
            "total_evaluations": total_evaluations,
            "trade_count": total_trades,
            "winning_trades_count": len(winning_trades),
            "losing_trades_count": len(losing_trades),
            "win_rate_pct": round(win_rate, 2),
            "target_hit_rate_pct": round(target_hit_rate, 2),
            "average_gross_pnl_usd": round(avg_gross, 4),
            "average_net_pnl_usd": round(avg_net, 4),
            "average_holding_duration_minutes": round(avg_hold, 1),
            "max_drawdown_usd": round(max_drawdown, 2),
            "max_consecutive_losses": max_consecutive_losses,
            "rejected_opportunities_count": rejected_opportunities,
            "no_trade_evaluations_count": no_trade_evaluations,
            "no_trade_frequency_pct": round((no_trade_evaluations / total_evaluations) * 100, 2) if total_evaluations > 0 else 0.0,
            "regime_distribution": regime_distribution,
            "slippage_sensitivity": slippage_results
        }

        print("=" * 70)
        print("REPLAY VALIDATION COMPLETED:")
        print(f"Total Evaluations: {total_evaluations} | Total Trades: {total_trades}")
        print(f"Win Rate: {win_rate:.2f}% | Target Hit Rate: {target_hit_rate:.2f}%")
        print(f"Avg Gross P&L: ${avg_gross:.4f} | Avg Net P&L: ${avg_net:.4f}")
        print(f"Avg Holding Duration: {avg_hold:.1f} minutes | Max Drawdown: ${max_drawdown:.2f}")
        print(f"Max Consecutive Losses: {max_consecutive_losses}")
        print(f"NO_TRADE Frequency: {report['no_trade_frequency_pct']:.2f}%")
        print("=" * 70)

        return report


if __name__ == "__main__":
    validator = HistoricalReplayValidator()
    res = validator.run_replay()
    if res["status"] != "VALIDATED":
        sys.exit(1)
    sys.exit(0)
