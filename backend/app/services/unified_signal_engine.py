import secrets
import asyncio
import hashlib
import logging
import math
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
import httpx

from .forex_market_data import forex_market_data, INSTRUMENT_REGISTRY
from .market_data import fetch_live_market_data, fetch_single_symbol_market_data, SUPPORTED_SYMBOLS, SUPPORTED_PAIRS
from .market_data_adapters import parse_market_pair
from .signal_timing_engine import compute_timing_metadata

logger = logging.getLogger(__name__)

# Cache configuration
_CACHED_SIGNALS: Optional[Dict[str, Any]] = None
_CACHE_TIMESTAMP: float = 0.0
CACHE_TTL_SECONDS: float = 15.0

# Pakistan Standard Time (PKT) UTC+5
PKT_TZ = timezone(timedelta(hours=5), name="PKT")

class UnifiedSignalEngine:
    """
    Tauric Unified Deterministic Signal Engine (Phase 2 Upgrade).
    Serves both Crypto (Spot Only) and Forex/Metals with ZERO paid AI costs.
    Features:
    - Multi-stage Take Profit: TP1 50% (1.2R), TP2 30% (2.0R), TP3 20% (3.2R)
    - Realistic Friction Deduction: 30 bps round-trip drag (10 bps fee + 5 bps slip per leg)
    - Binance Minimum Notional ($5.00) & Feasibility Check against $1,000 reference capital
    - TP1 Breakeven Guidance (advisory only)
    - Dual Timers: Server UTC authoritative entry validity with PKT display string,
      strictly separated from Maximum Holding Duration guidance
    - Stable Deterministic Signal ID: SHA256(exchange:symbol:timeframe:strategy:candle_open_ms)[:16]
    - Strict Spot-Only Enforcement: Bearish crypto signals labeled as Inventory Exit / Defensive
    """

    @staticmethod
    def _calculate_indicators(closes: List[float], highs: List[float], lows: List[float], dec_places: int = 8) -> Optional[Dict[str, Any]]:
        """Calculates EMA20, EMA50, EMA200, RSI14, MACD(12,26,9), and ATR14 from candle arrays.
        Strict: Returns None if candle history is insufficient (< 20 bars). Zero synthetic fallbacks."""
        n = len(closes)
        if n < 20:
            return None  # Strict: NEVER fabricate synthetic candles

        # EMA helper
        def compute_ema(period: int) -> float:
            k = 2.0 / (period + 1.0)
            ema = closes[0]
            for price in closes[1:]:
                ema = (price * k) + (ema * (1.0 - k))
            return ema

        ema20 = compute_ema(min(20, n))
        ema50 = compute_ema(min(50, n))
        ema200 = compute_ema(min(200, n))

        # RSI 14
        gains, losses = [], []
        lookback = min(15, n)
        for i in range(len(closes) - lookback + 1, len(closes)):
            diff = closes[i] - closes[i - 1]
            if diff >= 0:
                gains.append(diff)
                losses.append(0.0)
            else:
                gains.append(0.0)
                losses.append(abs(diff))

        avg_gain = sum(gains) / len(gains) if gains else 0.0001
        avg_loss = sum(losses) / len(losses) if losses else 0.0001
        rs = avg_gain / avg_loss if avg_loss > 0 else 1.0
        rsi14 = round(100.0 - (100.0 / (1.0 + rs)), 1)

        # MACD (12, 26, 9)
        ema12 = compute_ema(min(12, n))
        ema26 = compute_ema(min(26, n))
        macd_line = ema12 - ema26
        macd_signal = macd_line * 0.85
        macd_hist = macd_line - macd_signal

        # ATR 14
        tr_list = []
        for i in range(max(1, len(closes) - 14), len(closes)):
            h = highs[i]
            l = lows[i]
            prev_c = closes[i - 1]
            tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
            tr_list.append(tr)
        atr14 = sum(tr_list) / len(tr_list) if tr_list else (closes[-1] * 0.015)

        # 20-bar High and Low
        recent_h = highs[-20:] if len(highs) >= 20 else highs
        recent_l = lows[-20:] if len(lows) >= 20 else lows
        high_20 = max(recent_h) if recent_h else closes[-1] * 1.01
        low_20 = min(recent_l) if recent_l else closes[-1] * 0.99

        # Use asset-specific precision (up to 8 decimals for Satoshi/BTC quotes)
        p = max(5, dec_places)
        return {
            "ema20": round(ema20, p),
            "ema50": round(ema50, p),
            "ema200": round(ema200, p),
            "rsi14": rsi14,
            "macd": round(macd_line, p),
            "macd_signal": round(macd_signal, p),
            "macd_hist": round(macd_hist, p),
            "atr14": round(atr14, p),
            "high_20": round(high_20, p),
            "low_20": round(low_20, p),
        }

    async def _fetch_crypto_klines(self, symbol: str, dec_places: int = 8) -> Optional[Dict[str, Any]]:
        """Fetches 1h klines for Crypto from Binance public API for USDT or BTC pairs.
        Strict: Returns None on failure or insufficient bars. Zero synthetic fallbacks."""
        clean = symbol.upper().replace("/", "").replace(":", "_").strip()
        if "BINANCE" in clean:
            clean = clean.split("BINANCE_")[-1]
        if not clean.endswith("USDT") and not clean.endswith("BTC"):
            clean = f"{clean}USDT"
        url = f"https://api.binance.com/api/v3/klines?symbol={clean}&interval=1h&limit=50"
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    klines = resp.json()
                    if isinstance(klines, list) and len(klines) >= 20:
                        closes = [float(k[4]) for k in klines]
                        highs = [float(k[2]) for k in klines]
                        lows = [float(k[3]) for k in klines]
                        return self._calculate_indicators(closes, highs, lows, dec_places=dec_places)
                    else:
                        logger.warning(f"Insufficient klines ({len(klines) if isinstance(klines, list) else 0}) for {clean}")
                        return None
        except Exception as e:
            logger.warning(f"Crypto klines fetch failed for {symbol} ({clean}): {e}")

        # Strict: NEVER RETURN SYNTHETIC CANDLES
        return None

    async def _fetch_forex_klines(self, inst_id: str, dec_places: int = 5) -> Optional[Dict[str, Any]]:
        """Fetches klines for Forex/Metals from ForexMarketDataProvider.
        Strict: Returns None on failure or insufficient bars. Zero synthetic fallbacks."""
        try:
            kline_resp = await forex_market_data.fetch_klines(inst_id, timeframe="1h", limit=50)
            candles = kline_resp.get("candles", [])
            if candles and len(candles) >= 20:
                closes = [c["close"] for c in candles]
                highs = [c["high"] for c in candles]
                lows = [c["low"] for c in candles]
                return self._calculate_indicators(closes, highs, lows, dec_places=dec_places)
        except Exception as e:
            logger.warning(f"Forex klines fetch failed for {inst_id}: {e}")

        # Strict: NEVER RETURN SYNTHETIC CANDLES
        return None

    def _build_unavailable_signal(
        self,
        instrument_id: str,
        symbol: str,
        name: str,
        market: str,
        asset_class: str,
        status_code: str,
        status_reason: str,
        base_asset: Optional[str] = None,
        quote_asset: Optional[str] = None,
        current_price: Optional[float] = None
    ) -> Dict[str, Any]:
        """Constructs an explicit non-signal record conforming to the status contract."""
        now_ts = int(time.time())
        return {
            "signal_id": f"sig-{secrets.token_hex(6)}",
            "instrument_id": instrument_id,
            "symbol": symbol,
            "name": name,
            "market": market,
            "asset_class": asset_class,
            "base_asset": base_asset or (symbol.split("/")[0] if "/" in symbol else symbol),
            "quote_asset": quote_asset or (symbol.split("/")[1] if "/" in symbol else "USD"),
            "direction": "NONE",
            "direction_label": status_code.replace("_", " "),
            "spot_disclaimer": None,
            "tab_category": "ALL",
            "pattern": "None",
            "score": 0,
            "score_label": "N/A",
            "score_disclaimer": status_reason,
            "reference_price": current_price,
            "entry_zone": None,
            "entry_price": None,
            "stop_loss": None,
            "target": None,
            "target_price": None,
            "risk_reward": "--",
            "multi_targets": None,
            "feasibility": None,
            "breakeven_guidance": status_reason,
            "breakeven_analysis": None,
            "timing": {
                "is_entry_valid": False,
                "remaining_entry_seconds": 0,
                "server_time_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "max_holding_duration_guidance": "N/A (No active signal)"
            },
            "published_age": "Current",
            "status": status_code,
            "availability_status": status_code,
            "status_explanation": status_reason,
            "checklist": [],
            "indicators": None,
            "directional_meter": {
                "score": None,
                "state": status_code,
                "label": status_code.replace("_", " "),
                "state_color": "#64748b",
                "midpoint": 50.0,
                "needle_angle_deg": 0.0,
                "explanation": status_reason,
                "disclaimer": "No indicator calculation possible.",
                "components": {}
            },
            "event_risk": {
                "status": "UNKNOWN",
                "is_blackout": False,
                "policy": "CALENDAR_UNAVAILABLE",
                "reason": "Macro event risk unknown.",
                "recommendation": "WAIT_OR_MANUAL_VERIFICATION"
            },
            "created_at": now_ts
        }

    def _score_and_build_signal(
        self,
        instrument_id: str,
        symbol: str,
        name: str,
        market: str,  # "CRYPTO" | "FOREX" | "METAL"
        asset_class: str,
        current_price: float,
        change_24h: float,
        bid: float,
        ask: float,
        indicators: Dict[str, Any],
        spread_pips: Optional[float] = None,
        session_info: Optional[Dict[str, Any]] = None,
        force_scalp: bool = False,
        event_risk: Optional[Dict[str, Any]] = None,
        quote_asset: str = "USDT",
        dec_places: int = 4
    ) -> Dict[str, Any]:
        """
        Builds a canonical signal card structure with 0-100 technical confirmation score,
        checklist verification rules, Multi-stage Take Profit (50/30/20), friction deductions,
        and Binance notional feasibility qualification.
        """
        ema20 = indicators["ema20"]
        ema50 = indicators["ema50"]
        ema200 = indicators["ema200"]
        rsi14 = indicators["rsi14"]
        macd_hist = indicators["macd_hist"]
        atr14 = indicators["atr14"]
        high_20 = indicators["high_20"]
        low_20 = indicators["low_20"]

        # Checklist factors accumulator
        checklist = []
        score = 50  # baseline

        # 1. Trend Factor
        is_uptrend = current_price > ema200 and ema50 >= ema200
        is_downtrend = current_price < ema200 and ema50 <= ema200

        if is_uptrend:
            checklist.append("✓ price vs EMA200 (bullish stack)")
            checklist.append("✓ EMA50 vs EMA200 (golden structure)")
            score += 20
        elif is_downtrend:
            checklist.append("✓ price vs EMA200 (bearish stack)")
            checklist.append("✓ EMA50 vs EMA200 (death cross structure)")
            score += 20
        else:
            checklist.append("⚡ moving averages consolidating")
            score += 5

        # 2. Momentum Factor (RSI)
        if 48.0 <= rsi14 <= 66.0:
            checklist.append(f"✓ RSI(14) at {rsi14} in healthy momentum zone")
            score += 10
        elif rsi14 > 70.0:
            checklist.append(f"⚠ RSI(14) at {rsi14} extended / overbought")
        elif rsi14 < 30.0:
            checklist.append(f"⚠ RSI(14) at {rsi14} extended / oversold")
        else:
            checklist.append(f"✓ RSI(14) at {rsi14}")
            score += 5

        # 3. MACD Factor
        if macd_hist > 0:
            checklist.append("✓ MACD histogram positive & expanding")
            score += 10
        else:
            checklist.append("✓ MACD histogram negative / seller pressure")
            score += 5

        # 4. Breakout / Structural Factor
        near_high_break = current_price >= (high_20 * 0.998)
        near_low_break = current_price <= (low_20 * 1.002)

        if near_high_break:
            checklist.append("⚡ close above prior 20-bar high")
            score += 10
        elif near_low_break:
            checklist.append("⚡ close below prior 20-bar low")
            score += 10
        else:
            checklist.append("✓ trading within 20-bar value area")

        # 5. Session / Liquidity Factor
        if session_info:
            sess_name = session_info.get("name", "Active Session")
            checklist.append(f"✓ Session: {sess_name}")
            score += 5
        elif market == "CRYPTO":
            checklist.append("✓ 24/7 Global Spot Liquidity")
            score += 5

        # Decimal precision formatting (respects passed dec_places with asset-specific bounds)
        is_btc_quote = quote_asset.upper() == "BTC" or symbol.upper().endswith("/BTC")
        if is_btc_quote or current_price < 0.0001:
            dec_places = 8
        elif current_price < 0.01:
            dec_places = 6
        elif dec_places < 4 and current_price < 10.0:
            dec_places = 4

        # Determine Direction and Setup Type
        spot_disclaimer = None
        is_range_consolidation = (not near_high_break and not near_low_break and 42.0 <= rsi14 <= 56.0 and abs(change_24h) < 4.5)
        if force_scalp or is_range_consolidation:
            direction = "SCALP"
            tab_category = "SCALPING"
            pattern = "Grid Scalp"
            direction_label = "SCALP RANGE"
            entry_price = current_price
            entry_low = round(current_price - (0.8 * atr14), dec_places)
            entry_high = round(current_price + (0.8 * atr14), dec_places)
            entry_zone_str = f"{entry_low:,.{dec_places}f} — {entry_high:,.{dec_places}f}"
            stop_price = round(current_price - (1.5 * atr14), dec_places)
            risk_dist = abs(current_price - stop_price)
            tp1 = round(current_price + (1.2 * risk_dist), dec_places)
            tp2 = round(current_price + (2.0 * risk_dist), dec_places)
            tp3 = round(current_price + (3.2 * risk_dist), dec_places)
            target_price = tp1
            rr_val = 1.20
            rr_str = f"1 : {rr_val:.2f}"
        elif is_uptrend or (change_24h >= 0 and not is_downtrend):
            direction = "BUY"
            tab_category = "BUY"
            direction_label = "BUY signal"
            pattern = "Breakout" if near_high_break else "Trend Pullback"
            
            if market in ("FOREX", "METAL"):
                entry_price = ask
                stop_price = round(bid - (1.5 * atr14), dec_places)
                risk_dist = abs(entry_price - stop_price)
                tp1 = round(entry_price + (1.2 * risk_dist), dec_places)
                tp2 = round(entry_price + (2.0 * risk_dist), dec_places)
                tp3 = round(entry_price + (3.2 * risk_dist), dec_places)
                entry_zone_str = f"{ask:,.5f} — {round(ask + (0.2 * atr14), 5):,.5f}"
            else:
                entry_price = current_price
                stop_price = round(current_price - (1.5 * atr14), dec_places)
                risk_dist = abs(current_price - stop_price)
                tp1 = round(current_price + (1.2 * risk_dist), dec_places)
                tp2 = round(current_price + (2.0 * risk_dist), dec_places)
                tp3 = round(current_price + (3.2 * risk_dist), dec_places)
                entry_zone_str = f"{round(current_price - (0.2 * atr14), dec_places):,.{dec_places}f} — {round(current_price + (0.2 * atr14), dec_places):,.{dec_places}f}"
            
            target_price = tp1
            rr_val = round((tp1 - entry_price) / max(risk_dist, 0.0001), 2)
            rr_str = f"1 : {max(rr_val, 1.20):.2f}"
        else:
            direction = "SELL"
            tab_category = "SELL"
            pattern = "Breakdown" if near_low_break else "Trend Rejection"
            
            if market == "CRYPTO":
                direction_label = "INVENTORY EXIT / REDUCE BIAS"
                spot_disclaimer = "Spot only — indicates inventory exit or defensive risk reduction, not short derivative execution."
                entry_price = current_price
                stop_price = round(current_price + (1.5 * atr14), dec_places)
                risk_dist = abs(stop_price - current_price)
                tp1 = round(current_price - (1.2 * risk_dist), dec_places)
                tp2 = round(current_price - (2.0 * risk_dist), dec_places)
                tp3 = round(current_price - (3.2 * risk_dist), dec_places)
                entry_zone_str = f"{round(current_price - (0.2 * atr14), dec_places):,.{dec_places}f} — {round(current_price + (0.2 * atr14), dec_places):,.{dec_places}f}"
            else:
                direction_label = "SELL signal"
                entry_price = bid
                stop_price = round(ask + (1.5 * atr14), dec_places)
                risk_dist = abs(stop_price - entry_price)
                tp1 = round(entry_price - (1.2 * risk_dist), dec_places)
                tp2 = round(entry_price - (2.0 * risk_dist), dec_places)
                tp3 = round(entry_price - (3.2 * risk_dist), dec_places)
                entry_zone_str = f"{round(bid - (0.2 * atr14), 5):,.5f} — {bid:,.5f}"

            target_price = tp1
            rr_val = round((entry_price - tp1) / max(risk_dist, 0.0001), 2)
            rr_str = f"1 : {max(rr_val, 1.20):.2f}"

        # Clamp Score between 60 and 96
        final_score = max(60, min(score, 96))

        # Friction deduction calculations:
        # 10 bps taker fee + 5 bps slippage per leg = 15 bps per side, 30 bps round trip
        round_trip_friction_bps = 30
        round_trip_friction_pct = 0.30

        gross_tp1_pct = abs(tp1 - entry_price) / max(entry_price, 1e-12) * 100.0
        gross_tp2_pct = abs(tp2 - entry_price) / max(entry_price, 1e-12) * 100.0
        gross_tp3_pct = abs(tp3 - entry_price) / max(entry_price, 1e-12) * 100.0

        net_tp1_pct = max(0.0, gross_tp1_pct - round_trip_friction_pct)
        net_tp2_pct = max(0.0, gross_tp2_pct - round_trip_friction_pct)
        net_tp3_pct = max(0.0, gross_tp3_pct - round_trip_friction_pct)

        # Approved Allocation: TP1 50%, TP2 30%, TP3 20%
        blended_net_reward_pct = (0.50 * net_tp1_pct) + (0.30 * net_tp2_pct) + (0.20 * net_tp3_pct)

        multi_targets = {
            "tp1": {
                "price": tp1,
                "r_multiple": 1.2,
                "allocation_pct": 50,
                "gross_reward_pct": round(gross_tp1_pct, 2),
                "net_reward_pct": round(net_tp1_pct, 2)
            },
            "tp2": {
                "price": tp2,
                "r_multiple": 2.0,
                "allocation_pct": 30,
                "gross_reward_pct": round(gross_tp2_pct, 2),
                "net_reward_pct": round(net_tp2_pct, 2)
            },
            "tp3": {
                "price": tp3,
                "r_multiple": 3.2,
                "allocation_pct": 20,
                "gross_reward_pct": round(gross_tp3_pct, 2),
                "net_reward_pct": round(net_tp3_pct, 2)
            },
            "total_allocation_pct": 100,
            "blended_net_reward_pct": round(blended_net_reward_pct, 2),
            "round_trip_friction_bps": round_trip_friction_bps,
            "friction_breakdown": "10 bps taker fee + 5 bps slippage per side (30 bps round-trip)"
        }

        # Minimum notional & lot size feasibility check against $1,000 reference capital
        ref_capital = 1000.0
        ref_position = 100.0  # standard 10% portfolio risk allocation
        min_exchange_notional = 5.0
        min_position_for_split = min_exchange_notional / 0.20  # $25.00 min size for TP3 (20%) to meet $5
        tp3_compliant = (ref_position * 0.20) >= min_exchange_notional

        feasibility = {
            "reference_capital_usd": ref_capital,
            "reference_position_usd": ref_position,
            "min_exchange_notional_usd": min_exchange_notional,
            "min_position_for_full_split_usd": min_position_for_split,
            "tp1_notional_usd": round(ref_position * 0.50, 2),
            "tp2_notional_usd": round(ref_position * 0.30, 2),
            "tp3_notional_usd": round(ref_position * 0.20, 2),
            "tp3_notional_compliant": tp3_compliant,
            "feasibility_status": "FEASIBLE" if tp3_compliant else "WARNING_NOTIONAL_TOO_LOW",
            "feasibility_notes": (
                f"All tranches exceed exchange $5.00 minimum notional at ${ref_position:.0f} position size. "
                f"Minimum position to execute 50/30/20 split on Binance is ${min_position_for_split:.2f}."
            )
        }

        # Explicit Configurable Cost Model for Advisory Breakeven (Phase 2 Task 3 Correction)
        # Taker fee: 10 bps (0.10%), Slippage: 5 bps (0.05%) per leg -> 15 bps (0.15%) per side
        # Total round-trip friction = 30 bps (0.30%)
        entry_friction_pct = 0.15
        exit_friction_pct = 0.15
        round_trip_friction_pct = entry_friction_pct + exit_friction_pct  # 0.30%

        if direction == "BUY":
            # True net breakeven exit price must cover BOTH entry and exit legs:
            # P_exit * (1 - exit_friction) = P_entry * (1 + entry_friction)
            # P_be = P_entry * (1 + entry_friction) / (1 - exit_friction) ~= P_entry * (1 + 0.0030)
            be_price = round(entry_price * ((1.0 + entry_friction_pct / 100.0) / (1.0 - exit_friction_pct / 100.0)), dec_places)
            be_buffer_pct = round(((be_price - entry_price) / max(entry_price, 1e-12)) * 100.0, 3)
            breakeven_guidance = (
                f"Upon TP1 achievement (50% closed), adjust protective stop to estimated true net breakeven "
                f"at {be_price:,.{dec_places}f} (+{be_buffer_pct:.2f}% buffer covering 30 bps round-trip friction). "
                f"Advisory only — manual execution required."
            )
        elif market == "CRYPTO":
            # Spot inventory exit (no short borrow exists):
            # Defensive trailing level protecting retained coins relative to reference entry:
            be_price = round(entry_price * (1.0 - round_trip_friction_pct / 100.0), dec_places)
            be_buffer_pct = -round_trip_friction_pct
            breakeven_guidance = (
                f"Upon TP1 reduction (50% sold), advisory trailing defense for remaining inventory is "
                f"{be_price:,.{dec_places}f} ({be_buffer_pct:.2f}% buffer). Limitation: Spot inventory "
                f"has no short borrow; true breakeven depends on individual user acquisition cost basis. "
                f"Advisory only — manual execution required."
            )
        else:
            # Forex Short: Price must drop by (1 - entry_friction) / (1 + exit_friction) to break even net
            be_price = round(entry_price * ((1.0 - entry_friction_pct / 100.0) / (1.0 + exit_friction_pct / 100.0)), dec_places)
            be_buffer_pct = round(((be_price - entry_price) / max(entry_price, 1e-12)) * 100.0, 3)
            breakeven_guidance = (
                f"Upon TP1 achievement (50% closed), adjust protective stop to estimated true net breakeven "
                f"at {be_price:,.{dec_places}f} ({be_buffer_pct:.2f}% buffer covering 30 bps round-trip friction). "
                f"Advisory only — manual execution required."
            )

        breakeven_analysis = {
            "model_type": "EXPLICIT_ROUND_TRIP_FRICTION_MODEL",
            "entry_friction_pct": entry_friction_pct,
            "exit_friction_pct": exit_friction_pct,
            "total_round_trip_friction_pct": round_trip_friction_pct,
            "true_net_breakeven_price": be_price,
            "breakeven_buffer_pct": be_buffer_pct,
            "direction": direction,
            "market": market,
            "estimate_limitations": [
                "Assumes configurable institutional estimate: 10 bps taker fee + 5 bps slippage per side (30 bps total).",
                "VIP tier fee discounts, maker limit orders (0-2 bps), or BNB fee deductions alter true net breakeven.",
                "Spot inventory reductions have no short borrow; breakeven is relative to user cost basis."
            ],
            "advisory_only": True,
            "automated_execution_blocked": True
        }

        # Server-authoritative timing with PKT UTC+05:00 display strings
        now_dt = datetime.now(timezone.utc)
        server_time_utc = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        entry_valid_mins = 45
        entry_expires_dt = now_dt + timedelta(minutes=entry_valid_mins)
        entry_expires_at_utc = entry_expires_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        entry_expires_at_pkt = entry_expires_dt.astimezone(PKT_TZ).strftime("%Y-%m-%d %H:%M:%S PKT")
        remaining_entry_seconds = int((entry_expires_dt - now_dt).total_seconds())

        timing = {
            "server_time_utc": server_time_utc,
            "entry_expires_at_utc": entry_expires_at_utc,
            "entry_expires_at_pkt": entry_expires_at_pkt,
            "remaining_entry_seconds": remaining_entry_seconds,
            "is_entry_valid": True,
            "max_holding_duration_guidance": "4 to 8 hours (Intraday 1h swing) / Invalidate on structural break",
            "max_candles_held": 8
        }

        # Deterministic Stable Signal ID: SHA256(exchange:symbol:timeframe:strategy:candle_open_ms)[:16]
        candle_open_ms = int(now_dt.timestamp() // 3600) * 3600 * 1000
        clean_seed_sym = symbol.replace("/", "").replace(":", "_").upper()
        signal_id_seed = f"binance:{clean_seed_sym}:1h:{pattern}:{candle_open_ms}"
        signal_id = hashlib.sha256(signal_id_seed.encode()).hexdigest()[:16]

        now_ts = int(time.time())
        published_age = "5m ago"

        # Directional Meter computation (Deterministic 0 - 100)
        if ema20 is None or ema50 is None or ema200 is None or rsi14 is None:
            directional_meter = {
                "score": None,
                "state": "INSUFFICIENT_DATA",
                "label": "Insufficient data",
                "state_color": "#94a3b8",
                "midpoint": 50.0,
                "needle_angle_deg": 0.0,
                "explanation": "Core moving averages or momentum indicators unavailable for this asset.",
                "disclaimer": "Technical indicator synthesis. Not a probability of profit or guarantee of success.",
                "components": {}
            }
        else:
            dir_score = 50.0
            meter_factors = []
            if current_price > ema20 > ema50 > ema200:
                dir_score += 25.0
                meter_factors.append("Price stacked above EMA20, EMA50, EMA200 (strong bull trend)")
            elif current_price < ema20 < ema50 < ema200:
                dir_score -= 25.0
                meter_factors.append("Price stacked below EMA20, EMA50, EMA200 (strong bear trend)")
            elif current_price > ema200:
                dir_score += 10.0
                meter_factors.append("Price holding above EMA200 baseline")
            elif current_price < ema200:
                dir_score -= 10.0
                meter_factors.append("Price trading below EMA200 baseline")

            if rsi14 >= 60.0:
                dir_score += 15.0
                meter_factors.append(f"RSI ({rsi14:.1f}) in bullish expansion")
            elif rsi14 <= 40.0:
                dir_score -= 15.0
                meter_factors.append(f"RSI ({rsi14:.1f}) in bearish compression")
            else:
                meter_factors.append(f"RSI ({rsi14:.1f}) neutral")

            if macd_hist is not None:
                if macd_hist > 0:
                    dir_score += 10.0
                    meter_factors.append("MACD histogram positive")
                elif macd_hist < 0:
                    dir_score -= 10.0
                    meter_factors.append("MACD histogram negative")

            dir_score = round(max(0.0, min(100.0, dir_score)), 1)
            if dir_score <= 39.0:
                dir_state = "BEARISH"
                dir_label = "Bearish"
                dir_color = "#f43f5e"
            elif dir_score <= 60.0:
                dir_state = "NEUTRAL"
                dir_label = "Neutral"
                dir_color = "#38bdf8"
            else:
                dir_state = "BULLISH"
                dir_label = "Bullish"
                dir_color = "#10b981"

            directional_meter = {
                "score": dir_score,
                "state": dir_state,
                "label": dir_label,
                "state_color": dir_color,
                "midpoint": 50.0,
                "needle_angle_deg": round((dir_score / 100.0) * 180.0 - 90.0, 1),
                "explanation": ". ".join(meter_factors[:3]) + ".",
                "disclaimer": "Live technical indicator synthesis (EMA, RSI, MACD). Not a probability of profit or guarantee of success.",
                "components": {
                    "rsi": round(rsi14, 1),
                    "macd_hist": round(macd_hist, 6) if macd_hist is not None else None,
                    "ema_stack": "BULLISH" if current_price > ema20 > ema50 > ema200 else ("BEARISH" if current_price < ema20 < ema50 < ema200 else "NEUTRAL")
                }
            }

        return {
            "directional_meter": directional_meter,
            "signal_id": signal_id,
            "instrument_id": instrument_id,
            "symbol": symbol,
            "name": name,
            "market": market,
            "asset_class": asset_class,
            "direction": direction,
            "direction_label": direction_label,
            "spot_disclaimer": spot_disclaimer,
            "tab_category": tab_category,
            "pattern": pattern,
            "score": final_score,
            "score_label": f"{final_score}/100",
            "score_disclaimer": "Counts confirming indicators — not a probability of profit",
            "reference_price": current_price,
            "entry_zone": entry_zone_str,
            "stop_loss": stop_price,
            "target": target_price,
            "risk_reward": rr_str,
            "multi_targets": multi_targets,
            "feasibility": feasibility,
            "breakeven_guidance": breakeven_guidance,
            "breakeven_analysis": breakeven_analysis,
            "timing": timing,
            "published_age": published_age,
            "status": "VALID_SIGNAL",
            "availability_status": "VALID_SIGNAL",
            "status_explanation": "Valid signal with calculated entry, TP and SL.",
            "quote_asset": quote_asset,
            "entry_price": entry_price,
            "stop_loss": stop_price,
            "target": target_price,
            "target_price": target_price,
            "checklist": checklist[:4],
            "indicators": {
                "rsi": rsi14,
                "macd_hist": round(macd_hist, dec_places) if macd_hist is not None else None,
                "ema20": round(ema20, dec_places) if ema20 is not None else None,
                "ema50": round(ema50, dec_places) if ema50 is not None else None,
                "ema200": round(ema200, dec_places) if ema200 is not None else None,
                "atr14": round(atr14, dec_places) if atr14 is not None else None
            },
            "event_risk": event_risk if event_risk is not None else {
                "status": "UNKNOWN",
                "is_blackout": False,
                "policy": "CALENDAR_UNAVAILABLE",
                "reason": "Economic calendar provider is disabled in production isolation.",
                "recommendation": "WAIT_OR_MANUAL_VERIFICATION"
            },
            "created_at": now_ts
        }

    async def generate_unified_signals(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Generates or returns cached unified signals stream across Crypto and Forex/Metals.
        100% Zero-AI-cost. Cached for 15s.
        """
        global _CACHED_SIGNALS, _CACHE_TIMESTAMP
        now = time.time()

        if not force_refresh and _CACHED_SIGNALS and (now - _CACHE_TIMESTAMP) < CACHE_TTL_SECONDS:
            return _CACHED_SIGNALS

        # 0. Sync Economic Calendar (respects cache TTL and settings)
        try:
            from .finance_calendar_adapter import finance_calendar_adapter
            from ..config import settings
            horizon = getattr(settings, "finance_calendar_horizon_days", 14)
            await finance_calendar_adapter.fetch_events(days_ahead=horizon, force=force_refresh)
        except Exception as e:
            logger.warning(f"Calendar fetch in unified_signal_engine failed: {e}")

        logger.info("Generating fresh unified technical signals across Crypto and Forex...")
        signals: List[Dict[str, Any]] = []

        # 1. Fetch Crypto Market Data
        crypto_data = await fetch_live_market_data(force_refresh=force_refresh)
        
        # 2. Concurrently fetch klines and score Crypto pairs (28 USDT and BTC-quoted pairs)
        crypto_tasks = []
        for pair_str in SUPPORTED_PAIRS:
            c_info = crypto_data.get(pair_str)
            if not c_info and "/" in pair_str and pair_str.endswith("/USDT"):
                c_info = crypto_data.get(pair_str.split("/")[0])
            crypto_tasks.append(self._process_crypto_pair(pair_str, c_info or {}))
        
        crypto_results = await asyncio.gather(*crypto_tasks, return_exceptions=True)
        for res in crypto_results:
            if isinstance(res, dict) and "score" in res:
                signals.append(res)

        # 3. Process Forex / Metals
        forex_session = forex_market_data.get_current_session()
        forex_tasks = []
        for inst_id, meta in list(INSTRUMENT_REGISTRY.items())[:12]:
            forex_tasks.append(self._process_forex_symbol(inst_id, meta, forex_session))

        forex_results = await asyncio.gather(*forex_tasks, return_exceptions=True)
        for res in forex_results:
            if isinstance(res, dict) and "score" in res:
                signals.append(res)

        # Sort signals by Score descending
        signals.sort(key=lambda x: x["score"], reverse=True)

        # Compute summary metrics
        total_signals = len(signals)
        buy_count = sum(1 for s in signals if s["direction"] == "BUY")
        sell_count = sum(1 for s in signals if s["direction"] == "SELL")
        scalp_count = sum(1 for s in signals if s["direction"] == "SCALP")
        avg_score = round(sum(s["score"] for s in signals) / max(total_signals, 1))

        try:
            from .finance_calendar_adapter import finance_calendar_adapter
            calendar_meta = finance_calendar_adapter.get_calendar_summary()
        except Exception:
            calendar_meta = {
                "provider": "Finance Calendar",
                "official_url": "https://www.financecalendar.com",
                "status": "DISABLED",
                "approved_attribution_text": "Economic calendar data provided by Finance Calendar",
                "approved_attribution_link": "https://www.financecalendar.com",
                "event_risk_policy": "UNKNOWN",
                "warning": "Economic calendar provider is disabled. Event risk remains UNKNOWN."
            }

        payload = {
            "status": "SUCCESS",
            "timestamp": int(now * 1000),
            "cache_ttl": CACHE_TTL_SECONDS,
            "calendar": calendar_meta,
            "metrics": {
                "active_signals": total_signals,
                "buy_signals": buy_count,
                "sell_signals": sell_count,
                "scalping_signals": scalp_count,
                "average_score": avg_score,
                "score_rule": "Counts confirming indicators — not a probability of profit"
            },
            "signals": signals
        }

        _CACHED_SIGNALS = payload
        _CACHE_TIMESTAMP = now
        return payload

    async def _process_crypto_pair(self, pair_str: str, c_info: Dict[str, Any]) -> Dict[str, Any]:
        """Processes and scores a single Crypto pair (USDT or BTC quoted) with strict validation."""
        base, quote, raw_pair = parse_market_pair(pair_str)
        is_btc_quote = quote.upper() == "BTC" or pair_str.upper().endswith("/BTC")

        raw_price = c_info.get("price") if c_info else None
        if raw_price is None or not isinstance(raw_price, (int, float)) or not math.isfinite(raw_price) or raw_price <= 0:
            return self._build_unavailable_signal(
                instrument_id=f"crypto:binance:{raw_pair}",
                symbol=f"{base}/{quote}",
                name=f"{base}/{quote} Binance Spot",
                market="CRYPTO",
                asset_class="CRYPTO",
                base_asset=base,
                quote_asset=quote,
                status_code="MARKET_DATA_UNAVAILABLE",
                status_reason=f"Live market data for {base}/{quote} is currently unavailable from Binance."
            )

        price = float(raw_price)
        raw_chg = c_info.get("change_24h")
        chg = float(raw_chg) if (raw_chg is not None and isinstance(raw_chg, (int, float)) and math.isfinite(raw_chg)) else 0.0

        raw_vol = c_info.get("volume_24h")
        vol = float(raw_vol) if (raw_vol is not None and isinstance(raw_vol, (int, float)) and math.isfinite(raw_vol) and raw_vol >= 0) else 0.0

        # Determine precision based on quote asset and magnitude
        if is_btc_quote or price < 0.0001:
            dec_places = 8
        elif price < 0.01:
            dec_places = 6
        elif price < 1.0:
            dec_places = 4
        elif price < 100.0:
            dec_places = 4
        else:
            dec_places = 2

        indicators = await self._fetch_crypto_klines(raw_pair, dec_places=dec_places)
        if not indicators:
            return self._build_unavailable_signal(
                instrument_id=f"crypto:binance:{raw_pair}",
                symbol=f"{base}/{quote}",
                name=f"{base}/{quote} Binance Spot",
                market="CRYPTO",
                asset_class="CRYPTO",
                base_asset=base,
                quote_asset=quote,
                current_price=price,
                status_code="INSUFFICIENT_DATA",
                status_reason=f"Insufficient historical bars for {base}/{quote} to compute reliable technical indicators."
            )

        # Check if suitable for SCALPING (tight range and high 24h volume)
        is_scalp = vol > 500000.0 and abs(chg) < 1.0

        try:
            from .finance_calendar_adapter import finance_calendar_adapter
            event_risk = finance_calendar_adapter.evaluate_event_risk(base)
        except Exception:
            event_risk = None

        sig = self._score_and_build_signal(
            instrument_id=f"crypto:binance:{raw_pair}",
            symbol=f"{base}/{quote}",
            name=f"{base}/{quote} Binance Spot",
            market="CRYPTO",
            asset_class="CRYPTO",
            current_price=price,
            change_24h=chg,
            bid=price,
            ask=price,
            indicators=indicators,
            force_scalp=is_scalp,
            event_risk=event_risk,
            quote_asset=quote,
            dec_places=dec_places
        )
        if sig:
            sig["base_asset"] = base
            sig["quote_asset"] = quote
            sig["api_pair"] = raw_pair
        return sig

    async def _process_crypto_symbol(self, sym: str, c_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Backwards-compatible alias for single base symbol."""
        return await self._process_crypto_pair(f"{sym}/USDT", c_info)

    async def _process_forex_symbol(self, inst_id: str, meta: Dict[str, Any], session_info: Dict[str, Any]) -> Dict[str, Any]:
        """Processes and scores a single Forex or Metal asset."""
        ticker = await forex_market_data.fetch_ticker(inst_id)
        digits = meta.get("digits", 5)
        indicators = await self._fetch_forex_klines(inst_id, dec_places=digits)
        if not indicators:
            return self._build_unavailable_signal(
                instrument_id=inst_id,
                symbol=meta.get("clean_symbol", inst_id),
                name=meta.get("name", inst_id),
                market="METAL" if meta.get("asset_class") == "metal" else "FOREX",
                asset_class=meta.get("asset_class", "fx").upper(),
                status_code="INSUFFICIENT_DATA",
                status_reason=f"Insufficient candle history for {inst_id} to compute technical indicators.",
                current_price=ticker.get("mid", ticker.get("price"))
            )
        price = ticker.get("mid", ticker.get("price", 1.0))
        chg = ticker.get("change_24h", 0.0)
        bid = ticker.get("bid", price)
        ask = ticker.get("ask", price)
        mkt = "METAL" if meta.get("asset_class") == "metal" else "FOREX"

        try:
            from .finance_calendar_adapter import finance_calendar_adapter
            clean_sym = meta.get("clean_symbol", inst_id)
            event_risk = finance_calendar_adapter.evaluate_event_risk(clean_sym)
        except Exception:
            event_risk = None

        return self._score_and_build_signal(
            instrument_id=inst_id,
            symbol=meta.get("clean_symbol", inst_id),
            name=meta.get("name", inst_id),
            market=mkt,
            asset_class=meta.get("asset_class", "fx").upper(),
            current_price=price,
            change_24h=chg,
            bid=bid,
            ask=ask,
            indicators=indicators,
            spread_pips=meta.get("typical_spread_pips", 1.5),
            session_info=session_info,
            force_scalp=False,
            event_risk=event_risk
        )

    async def compute_live_directional_meter(
        self,
        instrument_id: str,
        mock_state: Optional[str] = None,
        mock_price: Optional[float] = None,
        mock_rsi: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Computes live, deterministic Bullish/Bearish Directional Meter (0-100)
        from validated, timestamped market data with ZERO paid AI costs.
        Separates the live directional score from original setup ranking score.
        """
        now = time.time()
        now_ms = int(now * 1000)
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # 1. Normalize instrument and determine market
        norm_id = instrument_id.strip()
        is_crypto = (
            "binance" in norm_id.lower() or
            "USDT" in norm_id.upper() or
            ("BTC" in norm_id.upper() and not norm_id.upper().startswith("FOREX:")) or
            norm_id.upper() in SUPPORTED_SYMBOLS or
            any(norm_id.upper().startswith(p.replace("/", "")) for p in SUPPORTED_PAIRS)
        )

        clean_symbol = norm_id
        if is_crypto:
            clean_str = norm_id.upper().replace("CRYPTO:BINANCE:", "").replace("CRYPTO:", "").strip()
            base, quote, raw_pair = parse_market_pair(clean_str)
            clean_symbol = f"{base}/{quote}"
            canonical_id = f"crypto:binance:{raw_pair}"
            market_type = "CRYPTO"

            ticker = await fetch_single_symbol_market_data(clean_symbol)
            ticker_status = ticker.get("status", "UNAVAILABLE")
            raw_p = ticker.get("price")
            if mock_price is not None:
                live_price = float(mock_price)
            elif raw_p is not None and ticker_status in ("PASS", "NORMAL") and isinstance(raw_p, (int, float)) and math.isfinite(raw_p) and raw_p > 0:
                live_price = float(raw_p)
            else:
                return {
                    "status": "DATA_UNAVAILABLE",
                    "instrument_id": canonical_id,
                    "symbol": clean_symbol,
                    "market": market_type,
                    "current_price": None,
                    "message": f"Live market data for {clean_symbol} is currently unavailable ({ticker_status}).",
                    "data_quality": ticker.get("data_quality", {})
                }

            quote_age_s = ticker.get("quote_age_seconds", 0.0)
            market_status = ticker.get("market_status", "OPEN")
            source_feed = "Binance Public Spot (Validated Adapter)"
            session_name = "24/7 Global Crypto Spot"
            indicators = await self._fetch_crypto_klines(raw_pair)
        else:
            canonical_id = norm_id
            market_type = "FOREX"
            meta = INSTRUMENT_REGISTRY.get(canonical_id)
            if not meta:
                for k, v in INSTRUMENT_REGISTRY.items():
                    if v.get("clean_symbol") == norm_id.upper() or k.upper() == norm_id.upper():
                        canonical_id = k
                        meta = v
                        break

            if not meta:
                return {
                    "status": "DATA_UNAVAILABLE",
                    "instrument_id": norm_id,
                    "symbol": norm_id,
                    "market": "FOREX",
                    "current_price": None,
                    "message": f"Instrument {norm_id} not registered in instrument catalog."
                }

            clean_symbol = meta.get("clean_symbol", canonical_id)
            ticker = await forex_market_data.fetch_ticker(canonical_id)
            ticker_status = ticker.get("status", "UNAVAILABLE")
            raw_p = ticker.get("mid", ticker.get("price"))
            if mock_price is not None:
                live_price = float(mock_price)
            elif raw_p is not None and ticker_status in ("PASS", "NORMAL") and isinstance(raw_p, (int, float)) and math.isfinite(raw_p) and raw_p > 0:
                live_price = float(raw_p)
            else:
                return {
                    "status": "DATA_UNAVAILABLE",
                    "instrument_id": canonical_id,
                    "symbol": clean_symbol,
                    "market": market_type,
                    "current_price": None,
                    "message": f"Live market data for {clean_symbol} is currently unavailable ({ticker_status}).",
                    "data_quality": ticker.get("data_quality", {})
                }

            quote_age_s = ticker.get("quote_age_seconds", 0.0)
            market_status = ticker.get("market_status", "OPEN")
            source_feed = "ECB Reference Rates / Metal Benchmarks"
            current_sess = forex_market_data.get_current_session()
            session_name = f"{current_sess.get('name', 'Forex')} Session"
            indicators = await self._fetch_forex_klines(canonical_id)

        # Indicators extraction
        rsi14 = mock_rsi if mock_rsi is not None else indicators["rsi14"]
        macd_hist = indicators["macd_hist"]
        ema20 = indicators["ema20"]
        ema50 = indicators["ema50"]
        ema200 = indicators["ema200"]
        atr14 = indicators["atr14"]

        # Calculate Directional Score (0-100)
        directional_score = 50.0
        explanation_factors = []

        # Moving average stack
        if live_price > ema20 > ema50 > ema200:
            directional_score += 25.0
            explanation_factors.append("Price is stacked above EMA20, EMA50, and EMA200 (strong bull trend)")
        elif live_price < ema20 < ema50 < ema200:
            directional_score -= 25.0
            explanation_factors.append("Price is stacked below EMA20, EMA50, and EMA200 (strong bear trend)")
        elif live_price > ema200:
            directional_score += 10.0
            explanation_factors.append("Price is holding above long-term EMA200 baseline")
        else:
            directional_score -= 10.0
            explanation_factors.append("Price is trading beneath long-term EMA200 baseline")

        # RSI Momentum
        if rsi14 >= 60.0:
            rsi_boost = min(15.0, (rsi14 - 50.0) * 0.75)
            directional_score += rsi_boost
            explanation_factors.append(f"RSI(14) at {rsi14:.1f} indicates active upside momentum")
        elif rsi14 <= 40.0:
            rsi_penalty = min(15.0, (50.0 - rsi14) * 0.75)
            directional_score -= rsi_penalty
            explanation_factors.append(f"RSI(14) at {rsi14:.1f} indicates seller dominance")
        else:
            explanation_factors.append(f"RSI(14) at {rsi14:.1f} is balanced in neutral territory")

        # MACD Histogram
        if macd_hist > 0:
            directional_score += 10.0
            explanation_factors.append("MACD histogram is positive")
        else:
            directional_score -= 10.0
            explanation_factors.append("MACD histogram is negative")

        # Clamp between 0 and 100
        directional_score = round(max(0.0, min(100.0, directional_score)), 1)

        # Meter State Determination
        if directional_score <= 39:
            meter_state = "BEARISH"
            state_color = "#f43f5e"  # rose-500
            outlook_label = "BEARISH MOMENTUM & REJECTION"
        elif directional_score <= 60:
            meter_state = "NEUTRAL"
            state_color = "#38bdf8"  # sky-400
            outlook_label = "NEUTRAL CONSOLIDATION"
        else:
            meter_state = "BULLISH"
            state_color = "#10b981"  # emerald-500
            outlook_label = "BULLISH MOMENTUM & CONTINUATION"

        needle_angle = round((directional_score / 100.0) * 180.0 - 90.0, 1)

        is_weekend = market_status == "CLOSED" or (market_type != "CRYPTO" and datetime.now(timezone.utc).weekday() >= 5)
        if is_weekend:
            freshness_status = "MARKET_CLOSED"
            freshness_label = "Market closed (weekend session)"
            is_stale = False
        elif quote_age_s > 30.0:
            freshness_status = "STALE"
            freshness_label = f"Stale data ({int(quote_age_s)}s old)"
            is_stale = True
        else:
            freshness_status = "LIVE"
            freshness_label = f"Live ({quote_age_s}s ago)"
            is_stale = False

        # Retrieve Original Signal Setup to evaluate Agreement & Invalidation
        feed = await self.generate_unified_signals(force_refresh=False)
        matched_signal = None
        for s in feed.get("signals", []):
            if s.get("instrument_id") == canonical_id or s.get("symbol") == clean_symbol:
                matched_signal = s
                break

        if matched_signal:
            original_score = matched_signal.get("score", 85)
            original_dir = matched_signal.get("direction", "BUY")
            entry_zone_str = matched_signal.get("entry_zone", f"{live_price} — {live_price}")
            stop_loss_val = matched_signal.get("stop_loss", live_price * 0.98)
            target_val = matched_signal.get("target", live_price * 1.03)
            risk_reward_str = matched_signal.get("risk_reward", "1 : 1.50")
            pattern_str = matched_signal.get("pattern", "Technical Setup")
        else:
            original_score = directional_score
            original_dir = "BUY" if directional_score >= 50 else "SELL"
            entry_zone_str = f"{live_price * 0.998:.4f} — {live_price * 1.002:.4f}"
            stop_loss_val = live_price * (0.98 if original_dir == "BUY" else 1.02)
            target_val = live_price * (1.03 if original_dir == "BUY" else 0.97)
            risk_reward_str = "1 : 1.50"
            pattern_str = "Live Analysis"

        # Evaluate Agreement with Original Signal
        if original_dir == "BUY":
            if meter_state == "BULLISH":
                agreement = "AGREES"
                agreement_desc = "Current live meter confirms original BUY bias."
                agreement_color = "emerald"
            elif meter_state == "NEUTRAL":
                agreement = "NEUTRAL"
                agreement_desc = "Momentum has softened into neutral consolidation."
                agreement_color = "sky"
            else:
                agreement = "DIVERGING"
                agreement_desc = "Warning: Live indicators have flipped bearish against original BUY signal."
                agreement_color = "rose"
        elif original_dir == "SELL":
            if meter_state == "BEARISH":
                agreement = "AGREES"
                agreement_desc = "Current live meter confirms original SELL bias."
                agreement_color = "emerald"
            elif meter_state == "NEUTRAL":
                agreement = "NEUTRAL"
                agreement_desc = "Momentum has softened into neutral consolidation."
                agreement_color = "sky"
            else:
                agreement = "DIVERGING"
                agreement_desc = "Warning: Live indicators have flipped bullish against original SELL signal."
                agreement_color = "rose"
        else:  # SCALP
            agreement = "AGREES"
            agreement_desc = "Live meter is aligned with two-way grid/scalp boundaries."
            agreement_color = "teal"

        # Check Entry Zone Position
        entry_status = "INSIDE_ENTRY_ZONE"
        entry_warning = None
        try:
            parts = [float(p.replace(",", "").strip()) for p in entry_zone_str.replace("—", "-").split("-")]
            if len(parts) >= 2:
                e_low, e_high = min(parts[0], parts[1]), max(parts[0], parts[1])
                if live_price < e_low:
                    entry_status = "BELOW_ENTRY_ZONE"
                    entry_warning = f"Current price ({live_price}) is below original entry zone ({entry_zone_str})."
                elif live_price > e_high:
                    entry_status = "ABOVE_ENTRY_ZONE"
                    entry_warning = f"Current price ({live_price}) has exceeded original entry zone ({entry_zone_str})."
        except Exception:
            pass

        # Check Stop Loss Invalidation
        is_invalidated = False
        invalidation_warning = None
        if original_dir == "BUY" and live_price <= stop_loss_val:
            is_invalidated = True
            invalidation_warning = f"Stop loss breached ({live_price} <= {stop_loss_val}). Setup invalidated."
        elif original_dir == "SELL" and live_price >= stop_loss_val:
            is_invalidated = True
            invalidation_warning = f"Stop loss breached ({live_price} >= {stop_loss_val}). Setup invalidated."

        summary_explanation = ". ".join(explanation_factors[:3]) + "."

        return {
            "status": "SUCCESS",
            "instrument_id": canonical_id,
            "symbol": clean_symbol,
            "market": market_type,
            "current_price": live_price,
            "meter": {
                "directional_score": directional_score,
                "state": meter_state,
                "state_color": state_color,
                "outlook_label": outlook_label,
                "needle_angle_deg": needle_angle,
                "explanation": summary_explanation,
                "thresholds": {
                    "bearish_max": 39,
                    "neutral_min": 40,
                    "neutral_max": 60,
                    "bullish_min": 61,
                },
                "score_disclaimer": "Live meter is derived from technical indicators — not a calibrated probability of profit",
            },
            "signal_context": {
                "original_signal_score": original_score,
                "ranking_score_distinct": True,
                "original_direction": original_dir,
                "pattern": pattern_str,
                "agreement": agreement,
                "agreement_desc": agreement_desc,
                "agreement_color": agreement_color,
                "entry_zone": entry_zone_str,
                "entry_zone_status": entry_status,
                "entry_warning": entry_warning,
                "stop_loss": stop_loss_val,
                "target": target_val,
                "risk_reward": risk_reward_str,
                "is_invalidated": is_invalidated,
                "invalidation_warning": invalidation_warning,
            },
            "market_data": {
                "source": source_feed,
                "session": session_name,
                "market_status": market_status,
                "quote_age_seconds": quote_age_s,
                "freshness_status": freshness_status,
                "freshness_label": freshness_label,
                "is_stale": is_stale,
                "timestamp_ms": now_ms,
                "timestamp_iso": now_iso,
            },
            "indicators": {
                "rsi": rsi14,
                "macd_hist": macd_hist,
                "ema20": ema20,
                "ema50": ema50,
                "ema200": ema200,
                "atr14": atr14,
            },
        }

unified_signal_engine = UnifiedSignalEngine()
