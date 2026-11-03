"""
Deterministic Signal Timing & State Machine Engine
Implements TIMEFRAME_POLICY_V1 for Trade Setup, Tauric Deep Research, Scalping, and Swing strategies.
Zero LLM calls. Server-authoritative time (UTC storage + Asia/Karachi PKT display).
"""

import math
import logging
import httpx
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Pakistan Standard Time (PKT) UTC+5
PKT_TZ = timezone(timedelta(hours=5), name="PKT")

TIMEFRAME_POLICY_V1 = {
    "SCALPING": {
        "timeframe": "15m",
        "entry_valid_minutes": 45,       # 3 x 15m candles
        "expiry_minutes": 120,           # 2 hours
        "time_stop_minutes": 240,        # 4 hours
        "stale_minutes": 60              # 1 hour
    },
    "SWING": {
        "timeframe": "4h",
        "entry_valid_minutes": 720,      # 12 hours
        "expiry_minutes": 2880,          # 48 hours (2 days)
        "time_stop_minutes": 7200,       # 120 hours (5 days)
        "stale_minutes": 1440            # 24 hours
    },
    "TRADE_SETUP": {
        "15m": {
            "entry_valid_minutes": 45,
            "expiry_minutes": 120,
            "time_stop_minutes": 240,
            "stale_minutes": 60
        },
        "1h": {
            "entry_valid_minutes": 180,   # 3 hours
            "expiry_minutes": 720,        # 12 hours
            "time_stop_minutes": 1440,    # 24 hours
            "stale_minutes": 360          # 6 hours
        },
        "4h": {
            "entry_valid_minutes": 720,   # 12 hours
            "expiry_minutes": 2880,       # 48 hours
            "time_stop_minutes": 7200,    # 5 days
            "stale_minutes": 1440         # 24 hours
        },
        "1d": {
            "entry_valid_minutes": 2880,  # 2 days
            "expiry_minutes": 10080,      # 7 days
            "time_stop_minutes": 20160,   # 14 days
            "stale_minutes": 4320         # 3 days
        }
    },
    "TAURIC_DEEP_RESEARCH": {
        "timeframe": "1h",
        "entry_valid_minutes": 240,      # 4 hours
        "expiry_minutes": 1440,          # 24 hours
        "time_stop_minutes": 2880,       # 48 hours
        "stale_minutes": 720             # 12 hours
    }
}

FOREX_TIMEFRAME_POLICY_V1 = {
    "SCALPING": {
        "5m": {
            "timeframe": "5m",
            "entry_valid_minutes": 15,
            "expiry_minutes": 45,
            "time_stop_minutes": 90,
            "stale_minutes": 30
        },
        "10m": {
            "timeframe": "10m",
            "entry_valid_minutes": 30,
            "expiry_minutes": 90,
            "time_stop_minutes": 180,
            "stale_minutes": 45
        },
        "15m": {
            "timeframe": "15m",
            "entry_valid_minutes": 45,
            "expiry_minutes": 120,
            "time_stop_minutes": 240,
            "stale_minutes": 60
        }
    },
    "SWING": {
        "1h": {
            "timeframe": "1h",
            "entry_valid_minutes": 180,
            "expiry_minutes": 720,
            "time_stop_minutes": 1440,
            "stale_minutes": 360
        },
        "4h": {
            "timeframe": "4h",
            "entry_valid_minutes": 720,
            "expiry_minutes": 2880,
            "time_stop_minutes": 7200,
            "stale_minutes": 1440
        },
        "1d": {
            "timeframe": "1d",
            "entry_valid_minutes": 2880,
            "expiry_minutes": 10080,
            "time_stop_minutes": 20160,
            "stale_minutes": 4320
        }
    },
    "TRADE_SETUP": {
        "15m": {"entry_valid_minutes": 45, "expiry_minutes": 120, "time_stop_minutes": 240, "stale_minutes": 60},
        "1h": {"entry_valid_minutes": 180, "expiry_minutes": 720, "time_stop_minutes": 1440, "stale_minutes": 360},
        "4h": {"entry_valid_minutes": 720, "expiry_minutes": 2880, "time_stop_minutes": 7200, "stale_minutes": 1440},
        "1d": {"entry_valid_minutes": 2880, "expiry_minutes": 10080, "time_stop_minutes": 20160, "stale_minutes": 4320}
    },
    "TAURIC_DEEP_RESEARCH": {
        "timeframe": "1h",
        "entry_valid_minutes": 240,
        "expiry_minutes": 1440,
        "time_stop_minutes": 2880,
        "stale_minutes": 720
    }
}

def format_pkt_datetime(dt: datetime) -> str:
    """Formats datetime in Asia/Karachi (PKT) as '30 Sep 2026 — 05:00 PM PKT'."""
    dt_pkt = dt.astimezone(PKT_TZ)
    return dt_pkt.strftime("%d %b %Y — %I:%M %p PKT")

def format_pkt_time_only(dt: datetime) -> str:
    """Formats datetime time in Asia/Karachi (PKT) as '05:00 PM PKT'."""
    dt_pkt = dt.astimezone(PKT_TZ)
    return dt_pkt.strftime("%I:%M %p PKT")

def parse_iso_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    if not dt_str:
        return None
    try:
        clean_str = dt_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None

def compute_timing_metadata(
    strategy: str,
    timeframe: str = "1h",
    generated_at: Optional[datetime] = None,
    market: str = "CRYPTO"
) -> Dict[str, Any]:
    """
    Computes deterministic timing timestamps according to CRYPTO_TIMEFRAME_POLICY_V1 or FOREX_TIMEFRAME_POLICY_V1.
    """
    if not generated_at:
        generated_at = datetime.now(timezone.utc)
    elif generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)

    strat_key = strategy.upper()
    tf_clean = (timeframe or "1h").lower()
    is_forex = (market or "").upper() == "FOREX" or "/" in strat_key
    
    if is_forex:
        policy_version = "FOREX_TIMEFRAME_POLICY_V1"
        if "TAURIC" in strat_key:
            policy = FOREX_TIMEFRAME_POLICY_V1["TAURIC_DEEP_RESEARCH"]
        elif "SWING" in strat_key or "LONGER" in strat_key:
            policy = FOREX_TIMEFRAME_POLICY_V1["SWING"].get(tf_clean, FOREX_TIMEFRAME_POLICY_V1["SWING"]["4h"])
        elif "SCALP" in strat_key or "SHORT" in strat_key:
            policy = FOREX_TIMEFRAME_POLICY_V1["SCALPING"].get(tf_clean, FOREX_TIMEFRAME_POLICY_V1["SCALPING"]["10m"])
        elif "TRADE_SETUP" in strat_key or "SETUP" in strat_key:
            policy = FOREX_TIMEFRAME_POLICY_V1["TRADE_SETUP"].get(tf_clean, FOREX_TIMEFRAME_POLICY_V1["TRADE_SETUP"]["1h"])
        else:
            policy = FOREX_TIMEFRAME_POLICY_V1["TRADE_SETUP"]["1h"]
    else:
        policy_version = "CRYPTO_TIMEFRAME_POLICY_V1"
        if "TAURIC" in strat_key:
            policy = TIMEFRAME_POLICY_V1["TAURIC_DEEP_RESEARCH"]
        elif "SWING" in strat_key or "LONGER" in strat_key:
            policy = TIMEFRAME_POLICY_V1["SWING"]
        elif "SCALP" in strat_key or "SHORT" in strat_key:
            policy = TIMEFRAME_POLICY_V1["SCALPING"]
        elif "TRADE_SETUP" in strat_key or "SETUP" in strat_key:
            policy = TIMEFRAME_POLICY_V1["TRADE_SETUP"].get(tf_clean, TIMEFRAME_POLICY_V1["TRADE_SETUP"]["1h"])
        else:
            policy = TIMEFRAME_POLICY_V1["TRADE_SETUP"]["1h"]

    entry_valid_min = policy["entry_valid_minutes"]
    expiry_min = policy["expiry_minutes"]
    time_stop_min = policy["time_stop_minutes"]
    stale_min = policy["stale_minutes"]

    entry_valid_until_dt = generated_at + timedelta(minutes=entry_valid_min)
    expires_at_dt = generated_at + timedelta(minutes=expiry_min)
    time_stop_dt = generated_at + timedelta(minutes=time_stop_min)
    stale_after_dt = generated_at + timedelta(minutes=stale_min)

    now_utc = datetime.now(timezone.utc)
    expires_in_sec = max(0, int((expires_at_dt - now_utc).total_seconds()))
    entry_valid_in_sec = max(0, int((entry_valid_until_dt - now_utc).total_seconds()))

    def sec_to_human(secs: int) -> str:
        if secs <= 0:
            return "Expired"
        hrs = secs // 3600
        mins = (secs % 3600) // 60
        if hrs > 0:
            return f"{hrs}h {mins}m"
        return f"{mins}m"

    return {
        "policy_version": policy_version,
        "timeframe": policy.get("timeframe", timeframe.upper()),
        "timezone": "Asia/Karachi",
        "timezone_offset": "+05:00",
        "generated_at_utc": generated_at.isoformat(),
        "generated_at_pkt": format_pkt_datetime(generated_at),
        "entry_valid_until_utc": entry_valid_until_dt.isoformat(),
        "entry_valid_until_pkt": format_pkt_time_only(entry_valid_until_dt),
        "entry_valid_until_full_pkt": format_pkt_datetime(entry_valid_until_dt),
        "expires_at_utc": expires_at_dt.isoformat(),
        "expires_at_pkt": format_pkt_time_only(expires_at_dt),
        "expires_at_full_pkt": format_pkt_datetime(expires_at_dt),
        "time_stop_utc": time_stop_dt.isoformat(),
        "time_stop_pkt": format_pkt_time_only(time_stop_dt),
        "time_stop_full_pkt": format_pkt_datetime(time_stop_dt),
        "stale_after_utc": stale_after_dt.isoformat(),
        "stale_after_pkt": format_pkt_time_only(stale_after_dt),
        "entry_valid_minutes": entry_valid_min,
        "expiry_minutes": expiry_min,
        "time_stop_minutes": time_stop_min,
        "expires_in_seconds": expires_in_sec,
        "expires_in_display": sec_to_human(expires_in_sec),
        "entry_valid_in_seconds": entry_valid_in_sec,
        "entry_valid_in_display": sec_to_human(entry_valid_in_sec)
    }

class SignalTimingEngine:
    """
    Evaluates candle data from Binance public REST API and runs the server-side state machine.
    """

    async def fetch_public_klines_since(
        self,
        symbol: str,
        start_time_ms: int,
        interval: str = "15m",
        limit: int = 500
    ) -> List[List[Any]]:
        """Queries Binance public klines since generated_at timestamp (zero authentication/free)."""
        clean_sym = symbol.upper().replace("/USDT", "").replace("-USD", "").replace("USDT", "").replace("/", "")
        url = f"https://api.binance.com/api/v3/klines?symbol={clean_sym}USDT&interval={interval}&startTime={start_time_ms}&limit={limit}"
        async with httpx.AsyncClient(timeout=8.0) as client:
            try:
                res = await client.get(url)
                if res.status_code == 200:
                    return res.json()
            except Exception as e:
                logger.error(f"Error fetching klines for {symbol}: {e}")
        return []

    async def fetch_current_ticker_price(self, symbol: str) -> float:
        """Fetches current live price for Crypto or Forex/Precious Metals."""
        clean_sym = symbol.upper().strip()
        is_forex = "/" in clean_sym or "XAU" in clean_sym or "XAG" in clean_sym or clean_sym in ("EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD")
        
        if is_forex:
            from .forex_market_data import forex_market_data
            try:
                t = await forex_market_data.fetch_ticker(clean_sym)
                return float(t.get("price", 0.0))
            except Exception as e:
                logger.error(f"Error fetching Forex ticker for {symbol}: {e}")
                return 0.0

        clean_crypto = clean_sym.replace("/USDT", "").replace("-USD", "").replace("USDT", "").replace("/", "")
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={clean_crypto}USDT"
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                res = await client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    return float(data.get("price", 0.0))
            except Exception as e:
                logger.error(f"Error fetching ticker for {symbol}: {e}")
        return 0.0

    async def evaluate_signal_lifecycle(
        self,
        symbol: str,
        direction: str,
        entry_min: float,
        entry_max: float,
        take_profit: float,
        stop_loss: float,
        invalidation_price: float,
        timing_meta: Dict[str, Any],
        historical_status: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Server-authoritative state machine:
        Precedence:
        1. CANCELLED / COMPLETED
        2. INVALIDATED
        3. EXPIRED
        4. MISSED
        5. WAIT
        6. ACTIVE
        """
        now_utc = datetime.now(timezone.utc)
        checked_at_pkt = format_pkt_time_only(now_utc)
        
        # Check if legacy or missing timing
        if not timing_meta or not timing_meta.get("generated_at_utc"):
            current_price = await self.fetch_current_ticker_price(symbol)
            return {
                "signal_state": historical_status or "LEGACY_UNKNOWN",
                "state_label": "Legacy Record",
                "state_color": "slate",
                "current_price": current_price,
                "checked_at_pkt": checked_at_pkt,
                "checked_at_utc": now_utc.isoformat(),
                "reason": "Legacy record without TIMEFRAME_POLICY_V1 timing metadata.",
                "candle_summary": "Candle history unavailable for legacy record.",
                "timing": timing_meta or {}
            }

        gen_dt = parse_iso_datetime(timing_meta.get("generated_at_utc")) or now_utc
        entry_valid_until_dt = parse_iso_datetime(timing_meta.get("entry_valid_until_utc")) or (gen_dt + timedelta(hours=3))
        entry_valid_dt = entry_valid_until_dt
        expires_at_dt = parse_iso_datetime(timing_meta.get("expires_at_utc")) or (gen_dt + timedelta(hours=12))
        time_stop_dt = parse_iso_datetime(timing_meta.get("time_stop_utc")) or (gen_dt + timedelta(hours=24))

        start_ms = int(gen_dt.timestamp() * 1000)
        klines = await self.fetch_public_klines_since(symbol, start_ms, interval="15m", limit=500)
        
        current_price = await self.fetch_current_ticker_price(symbol)
        if current_price <= 0 and klines:
            current_price = float(klines[-1][4])

        entry_touched = False
        entry_touch_time = None
        tp_reached = False
        sl_reached = False
        invalidation_reached = False

        highest_candle_high = 0.0
        lowest_candle_low = float("inf")

        is_long = direction.upper() == "LONG"

        for k in klines:
            open_time = datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc)
            high = float(k[2])
            low = float(k[3])
            close = float(k[4])

            if high > highest_candle_high:
                highest_candle_high = high
            if low < lowest_candle_low:
                lowest_candle_low = low

            # 1. Entry zone evaluation
            if not entry_touched:
                # If candle range intersects entry zone [entry_min, entry_max]
                if (low <= entry_max and high >= entry_min):
                    # Check if entry occurred before entry_valid_until
                    if open_time <= entry_valid_dt:
                        entry_touched = True
                        entry_touch_time = open_time

            # 2. Invalidation & SL evaluation
            if is_long:
                if low <= stop_loss:
                    sl_reached = True
                if invalidation_price > 0 and close <= invalidation_price:
                    invalidation_reached = True
                if high >= take_profit:
                    tp_reached = True
            else:
                if high >= stop_loss:
                    sl_reached = True
                if invalidation_price > 0 and close >= invalidation_price:
                    invalidation_reached = True
                if low <= take_profit:
                    tp_reached = True

        # Refresh countdowns
        expires_in_sec = max(0, int((expires_at_dt - now_utc).total_seconds()))
        entry_valid_in_sec = max(0, int((entry_valid_until_dt - now_utc).total_seconds()))

        def sec_to_human(secs: int) -> str:
            if secs <= 0:
                return "Expired"
            hrs = secs // 3600
            mins = (secs % 3600) // 60
            if hrs > 0:
                return f"{hrs}h {mins}m"
            return f"{mins}m"

        timing_meta["expires_in_seconds"] = expires_in_sec
        timing_meta["expires_in_display"] = sec_to_human(expires_in_sec)
        timing_meta["entry_valid_in_seconds"] = entry_valid_in_sec
        timing_meta["entry_valid_in_display"] = sec_to_human(entry_valid_in_sec)

        # STATE MACHINE DETERMINATION
        if historical_status == "CANCELLED":
            state = "CANCELLED"
            reason = "Research session stopped by user request."
            color = "slate"
        elif invalidation_reached or sl_reached:
            state = "INVALIDATED"
            reason = f"Price breached stop loss (${stop_loss:,.2f}) or invalidation level."
            color = "rose"
        elif tp_reached:
            if entry_touched:
                state = "COMPLETED"
                reason = f"Take Profit (${take_profit:,.2f}) successfully achieved following valid entry."
                color = "emerald"
            else:
                state = "MISSED"
                reason = f"Price expanded to Take Profit (${take_profit:,.2f}) without filling the entry zone."
                color = "amber"
        elif now_utc > expires_at_dt:
            if not entry_touched:
                state = "EXPIRED"
                reason = "Setup lifetime expired prior to valid entry zone fill."
                color = "slate"
            else:
                if now_utc > time_stop_dt:
                    state = "EXPIRED"
                    reason = "Time stop elapsed without TP or SL being filled. Reassess/Exit."
                    color = "slate"
                else:
                    state = "ACTIVE"
                    reason = f"Position filled at entry zone. In progress (Time Stop active until {timing_meta.get('time_stop_pkt')})."
                    color = "green"
        elif not entry_touched:
            if now_utc <= entry_valid_dt:
                state = "WAIT"
                reason = f"Awaiting entry pull-back into ${entry_min:,.2f}–${entry_max:,.2f} (Valid until {timing_meta.get('entry_valid_until_pkt')})."
                color = "cyan"
            else:
                state = "EXPIRED"
                reason = f"Entry window closed at {timing_meta.get('entry_valid_until_pkt')}. Do not enter."
                color = "amber"
        else:
            state = "ACTIVE"
            reason = f"Position active (filled in entry zone). Monitoring Take Profit (${take_profit:,.2f}) and Stop Loss (${stop_loss:,.2f})."
            color = "green"

        candle_summary = (
            f"Evaluated {len(klines)} candles since {timing_meta.get('generated_at_pkt')}. "
            f"Range: [${lowest_candle_low:,.2f} - ${highest_candle_high:,.2f}]. "
            f"Entry filled: {'YES' if entry_touched else 'NO'}."
        )

        return {
            "signal_state": state,
            "state_label": state,
            "state_color": color,
            "current_price": current_price,
            "checked_at_pkt": checked_at_pkt,
            "checked_at_utc": now_utc.isoformat(),
            "reason": reason,
            "entry_touched": entry_touched,
            "tp_reached": tp_reached,
            "sl_reached": sl_reached,
            "invalidation_reached": invalidation_reached,
            "candle_count": len(klines),
            "candle_summary": candle_summary,
            "timing": timing_meta
        }

    async def evaluate_spot_grid_status(
        self,
        symbol: str,
        lower: float,
        upper: float,
        timing_meta: Dict[str, Any],
        historical_status: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Evaluates Binance Spot Grid plan validity:
        IN_RANGE, STALE, INVALIDATED, EXPIRED, LEGACY_UNKNOWN.
        """
        now_utc = datetime.now(timezone.utc)
        checked_at_pkt = format_pkt_time_only(now_utc)
        current_price = await self.fetch_current_ticker_price(symbol)

        if not timing_meta or not timing_meta.get("generated_at_utc"):
            return {
                "grid_state": historical_status or "LEGACY_UNKNOWN",
                "state_label": "Legacy Grid Plan",
                "state_color": "slate",
                "current_price": current_price,
                "checked_at_pkt": checked_at_pkt,
                "checked_at_utc": now_utc.isoformat(),
                "reason": "Legacy grid plan without TIMEFRAME_POLICY_V1 timing metadata.",
                "timing": timing_meta or {}
            }

        expires_at_dt = parse_iso_datetime(timing_meta.get("expires_at_utc")) or (now_utc + timedelta(hours=24))
        stale_after_dt = parse_iso_datetime(timing_meta.get("stale_after_utc")) or (now_utc + timedelta(hours=12))

        if historical_status == "CANCELLED":
            state = "CANCELLED"
            reason = "Grid plan cancelled by user."
            color = "slate"
        elif current_price < lower:
            state = "INVALIDATED"
            reason = f"Current market price (${current_price:,.2f}) breached lower bound (${lower:,.2f})."
            color = "rose"
        elif current_price > upper:
            state = "INVALIDATED"
            reason = f"Current market price (${current_price:,.2f}) breached upper bound (${upper:,.2f})."
            color = "rose"
        elif now_utc > expires_at_dt:
            state = "EXPIRED"
            reason = "Grid parameters expired (beyond 24h validity window). Run new scan."
            color = "slate"
        elif now_utc > stale_after_dt:
            state = "STALE"
            reason = "Market consolidation range stale (>12h old). Re-check or update parameters."
            color = "amber"
        else:
            state = "IN_RANGE"
            reason = f"Current price (${current_price:,.2f}) is active within channel [${lower:,.2f} - ${upper:,.2f}]."
            color = "green"

        return {
            "grid_state": state,
            "state_label": state,
            "state_color": color,
            "current_price": current_price,
            "checked_at_pkt": checked_at_pkt,
            "checked_at_utc": now_utc.isoformat(),
            "reason": reason,
            "timing": timing_meta
        }

signal_timing_engine = SignalTimingEngine()
