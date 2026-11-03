import logging
import httpx
import time
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class OutcomeEvaluationEngine:
    def __init__(self):
        # Realistic friction configuration
        self.taker_fee_pct = 0.10    # 10 bps per side
        self.slippage_pct = 0.05     # 5 bps per side

    async def fetch_subsequent_candles(self, symbol: str, start_time_ms: int, interval: str = "1h", limit: int = 50) -> List[Dict[str, float]]:
        """
        Fetches historical candles from Binance public API starting after start_time_ms.
        """
        clean_sym = symbol.upper().replace("USDT", "").replace("-USD", "") + "USDT"
        url = f"https://api.binance.com/api/v3/klines?symbol={clean_sym}&interval={interval}&startTime={start_time_ms}&limit={limit}"
        
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    raw = res.json()
                    candles = []
                    for k in raw:
                        candles.append({
                            "open_time": k[0],
                            "open": float(k[1]),
                            "high": float(k[2]),
                            "low": float(k[3]),
                            "close": float(k[4]),
                            "volume": float(k[5]),
                            "close_time": k[6]
                        })
                    return candles
                else:
                    logger.warning(f"Binance klines returned HTTP {res.status_code}")
                    return []
        except Exception as e:
            logger.error(f"Failed to fetch klines: {e}")
            return []

    def evaluate_single_trade(
        self,
        direction: str,
        entry: float,
        stop_loss: float,
        tp1: float,
        tp2: float,
        candles: List[Dict[str, float]],
        tp3: float = 0.0
    ) -> Dict[str, Any]:
        """
        Strict evaluation of an individual trade path over historical candles.
        Defect D Fix: Conservative same-candle conflict resolution defaults to LOSS_SL
        (worst-case stop hit first) rather than AMBIGUOUS neutral $0.00 P/L.
        """
        if direction not in ["LONG", "SHORT", "BUY", "SELL"] or entry <= 0:
            return {
                "outcome": "NO_TRADE",
                "mfe": 0.0,
                "mae": 0.0,
                "gross_pnl": 0.0,
                "fees": 0.0,
                "slippage": 0.0,
                "net_pnl": 0.0,
                "exit_price": entry,
                "candles_held": 0,
                "same_candle_conflict": False,
                "conflict_resolution": "NONE",
                "details": "Direction is FLAT or invalid entry."
            }

        is_long = direction in ["LONG", "BUY"]

        # If stop loss is missing or invalid, generate a standard 2.0% protective stop
        if stop_loss <= 0 or (is_long and stop_loss >= entry) or (not is_long and stop_loss <= entry):
            stop_loss = entry * 0.98 if is_long else entry * 1.02

        # If TP1 is missing or invalid, generate standard 1.5R target
        risk = abs(entry - stop_loss)
        if tp1 <= 0 or (is_long and tp1 <= entry) or (not is_long and tp1 >= entry):
            tp1 = entry + (1.2 * risk) if is_long else entry - (1.2 * risk)
            
        if tp2 <= 0 or (is_long and tp2 <= tp1) or (not is_long and tp2 >= tp1):
            tp2 = entry + (2.0 * risk) if is_long else entry - (2.0 * risk)

        if tp3 <= 0 or (is_long and tp3 <= tp2) or (not is_long and tp3 >= tp2):
            tp3 = entry + (3.2 * risk) if is_long else entry - (3.2 * risk)

        mfe = 0.0
        mae = 0.0
        outcome = "PENDING"
        exit_price = entry
        candles_held = 0
        same_candle_conflict = False
        conflict_resolution = "NONE"

        for i, c in enumerate(candles):
            candles_held = i + 1
            high = c["high"]
            low = c["low"]
            close = c["close"]

            if is_long:
                # Long excursions
                fav = max(0.0, high - entry)
                adv = max(0.0, entry - low)
                if fav > mfe: mfe = fav
                if adv > mae: mae = adv

                hit_tp1 = high >= tp1
                hit_tp2 = high >= tp2
                hit_tp3 = tp3 > 0 and high >= tp3
                hit_sl = low <= stop_loss

                # SAME CANDLE CONFLICT CHECK:
                # If both a target and the protective stop were hit in the same candle,
                # resolve conservatively as LOSS_SL (worst-case assumption: stop hit first).
                if (hit_tp1 or hit_tp2 or hit_tp3) and hit_sl:
                    outcome = "LOSS_SL"
                    exit_price = stop_loss
                    same_candle_conflict = True
                    conflict_resolution = "CONSERVATIVE_STOP_FIRST"
                    break

                if hit_tp3:
                    outcome = "WIN_TP3"
                    exit_price = tp3
                    break
                elif hit_tp2:
                    outcome = "WIN_TP2"
                    exit_price = tp2
                    break
                elif hit_tp1:
                    outcome = "WIN_TP1"
                    exit_price = tp1
                    break
                elif hit_sl:
                    outcome = "LOSS_SL"
                    exit_price = stop_loss
                    break

            else:
                # Short excursions
                fav = max(0.0, entry - low)
                adv = max(0.0, high - entry)
                if fav > mfe: mfe = fav
                if adv > mae: mae = adv

                hit_tp1 = low <= tp1
                hit_tp2 = low <= tp2
                hit_tp3 = tp3 > 0 and low <= tp3
                hit_sl = high >= stop_loss

                # SAME CANDLE CONFLICT CHECK:
                if (hit_tp1 or hit_tp2 or hit_tp3) and hit_sl:
                    outcome = "LOSS_SL"
                    exit_price = stop_loss
                    same_candle_conflict = True
                    conflict_resolution = "CONSERVATIVE_STOP_FIRST"
                    break

                if hit_tp3:
                    outcome = "WIN_TP3"
                    exit_price = tp3
                    break
                elif hit_tp2:
                    outcome = "WIN_TP2"
                    exit_price = tp2
                    break
                elif hit_tp1:
                    outcome = "WIN_TP1"
                    exit_price = tp1
                    break
                elif hit_sl:
                    outcome = "LOSS_SL"
                    exit_price = stop_loss
                    break

        # If candles exhausted and no TP/SL hit
        if outcome == "PENDING" and len(candles) > 0:
            outcome = "EXPIRED"
            exit_price = candles[-1]["close"]

        # Calculate P/L
        if is_long:
            gross_pnl = ((exit_price - entry) / entry) * 100.0
            round_trip_fee = (self.taker_fee_pct * 2)
            round_trip_slip = (self.slippage_pct * 2)
            fees = round_trip_fee
            slippage = round_trip_slip
            net_pnl = gross_pnl - fees - slippage
        else:
            gross_pnl = ((entry - exit_price) / entry) * 100.0
            round_trip_fee = (self.taker_fee_pct * 2)
            round_trip_slip = (self.slippage_pct * 2)
            fees = round_trip_fee
            slippage = round_trip_slip
            net_pnl = gross_pnl - fees - slippage

        return {
            "outcome": outcome,
            "mfe": round(mfe, 2),
            "mae": round(mae, 2),
            "gross_pnl": round(gross_pnl, 2),
            "fees": round(fees, 3),
            "slippage": round(slippage, 3),
            "net_pnl": round(net_pnl, 2),
            "exit_price": round(exit_price, 2),
            "candles_held": candles_held,
            "same_candle_conflict": same_candle_conflict,
            "conflict_resolution": conflict_resolution
        }

    async def evaluate_decision_record(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluates Tracks A, B, and C against actual subsequent market prices.
        """
        symbol = decision.get("symbol", "BTC-USD")
        ts_str = decision.get("timestamp")
        
        # Parse timestamp
        start_ms = int(time.time() * 1000) - (24 * 3600 * 1000)
        if ts_str:
            try:
                dt = datetime.fromisoformat(ts_str.replace("Z", ""))
                start_ms = int(dt.timestamp() * 1000)
            except Exception:
                pass

        candles = await self.fetch_subsequent_candles(symbol, start_ms, interval="1h", limit=50)

        # Track A: Tauric Only
        dir_a = decision.get("tauric_direction", "FLAT")
        entry_a = float(decision.get("tauric_entry") or decision.get("current_price") or 0.0)
        stop_a = float(decision.get("tauric_stop") or 0.0)
        tp1_a = float(decision.get("tauric_tp1") or 0.0)
        tp2_a = float(decision.get("tauric_tp2") or 0.0)
        tp3_a = float(decision.get("tauric_tp3") or 0.0)
        res_a = self.evaluate_single_trade(dir_a, entry_a, stop_a, tp1_a, tp2_a, candles, tp3=tp3_a)

        # Track B: Tauric + Jev (Only active if approved by reconciliation)
        reconcile = decision.get("reconciliation_result", "NO_TRADE")
        if reconcile in ["APPROVED", "SHADOW_DECISION", "TRADE"]:
            res_b = res_a.copy()
        else:
            res_b = {
                "outcome": "NO_TRADE",
                "mfe": 0.0,
                "mae": 0.0,
                "gross_pnl": 0.0,
                "fees": 0.0,
                "slippage": 0.0,
                "net_pnl": 0.0,
                "exit_price": entry_a,
                "candles_held": 0,
                "same_candle_conflict": False,
                "conflict_resolution": "NONE"
            }

        # Track C: Jev Fast Only
        dir_c = decision.get("jev_fast_direction", "FLAT")
        entry_c = float(decision.get("jev_fast_entry") or decision.get("current_price") or 0.0)
        stop_c = float(decision.get("jev_fast_stop") or 0.0)
        tp1_c = float(decision.get("jev_fast_tp1") or 0.0)
        tp2_c = float(decision.get("jev_fast_tp2") or 0.0)
        tp3_c = float(decision.get("jev_fast_tp3") or 0.0)
        res_c = self.evaluate_single_trade(dir_c, entry_c, stop_c, tp1_c, tp2_c, candles, tp3=tp3_c)

        return {
            "track_a_outcome": res_a["outcome"],
            "track_a_mfe": res_a["mfe"],
            "track_a_mae": res_a["mae"],
            "track_a_gross_pnl": res_a["gross_pnl"],
            "track_a_fees": res_a["fees"],
            "track_a_slippage": res_a["slippage"],
            "track_a_net_pnl": res_a["net_pnl"],

            "track_b_outcome": res_b["outcome"],
            "track_b_mfe": res_b["mfe"],
            "track_b_mae": res_b["mae"],
            "track_b_gross_pnl": res_b["gross_pnl"],
            "track_b_fees": res_b["fees"],
            "track_b_slippage": res_b["slippage"],
            "track_b_net_pnl": res_b["net_pnl"],

            "track_c_outcome": res_c["outcome"],
            "track_c_mfe": res_c["mfe"],
            "track_c_mae": res_c["mae"],
            "track_c_gross_pnl": res_c["gross_pnl"],
            "track_c_fees": res_c["fees"],
            "track_c_slippage": res_c["slippage"],
            "track_c_net_pnl": res_c["net_pnl"]
        }

outcome_engine = OutcomeEvaluationEngine()
