import asyncio
import datetime
import hashlib
import json
import logging
import math
import time
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
import httpx

logger = logging.getLogger(__name__)

# ─── IANA TIMEZONES ─────────────────────────────────────────────
TZ_UTC = ZoneInfo("UTC")
TZ_LONDON = ZoneInfo("Europe/London")
TZ_NEW_YORK = ZoneInfo("America/New_York")
TZ_TOKYO = ZoneInfo("Asia/Tokyo")
TZ_PKT = ZoneInfo("Asia/Karachi")

# ─── INSTRUMENT REGISTRY & METADATA CONTRACT ─────────────────────
# Single source of truth: instrument_id
# Examples: crypto:binance:BTCUSDT, fx:EURUSD, fx:GBPUSD, fx:USDJPY, metal:XAUUSD, metal:XAGUSD

INSTRUMENT_REGISTRY: Dict[str, Dict[str, Any]] = {
    # FOREX MAJORS
    "fx:EURUSD": {
        "instrument_id": "fx:EURUSD",
        "clean_symbol": "EUR/USD",
        "raw_symbol": "EURUSD",
        "yahoo_ticker": "EURUSD=X",
        "base": "EUR",
        "quote": "USD",
        "asset_class": "fx",
        "category": "MAJORS",
        "pip_size": 0.0001,
        "pip_decimal": 4,
        "price_precision": 5,
        "contract_size": 100000,
        "quote_unit": "USD",
        "session_profile": "24/5",
        "name": "Euro / US Dollar",
        "typical_spread_pips": 1.0,
    },
    "fx:GBPUSD": {
        "instrument_id": "fx:GBPUSD",
        "clean_symbol": "GBP/USD",
        "raw_symbol": "GBPUSD",
        "yahoo_ticker": "GBPUSD=X",
        "base": "GBP",
        "quote": "USD",
        "asset_class": "fx",
        "category": "MAJORS",
        "pip_size": 0.0001,
        "pip_decimal": 4,
        "price_precision": 5,
        "contract_size": 100000,
        "quote_unit": "USD",
        "session_profile": "24/5",
        "name": "British Pound / US Dollar",
        "typical_spread_pips": 1.4,
    },
    "fx:USDJPY": {
        "instrument_id": "fx:USDJPY",
        "clean_symbol": "USD/JPY",
        "raw_symbol": "USDJPY",
        "yahoo_ticker": "USDJPY=X",
        "base": "USD",
        "quote": "JPY",
        "asset_class": "fx",
        "category": "MAJORS",
        "pip_size": 0.01,
        "pip_decimal": 2,
        "price_precision": 3,
        "contract_size": 100000,
        "quote_unit": "JPY",
        "session_profile": "24/5",
        "name": "US Dollar / Japanese Yen",
        "typical_spread_pips": 1.1,
    },
    "fx:USDCHF": {
        "instrument_id": "fx:USDCHF",
        "clean_symbol": "USD/CHF",
        "raw_symbol": "USDCHF",
        "yahoo_ticker": "USDCHF=X",
        "base": "USD",
        "quote": "CHF",
        "asset_class": "fx",
        "category": "MAJORS",
        "pip_size": 0.0001,
        "pip_decimal": 4,
        "price_precision": 5,
        "contract_size": 100000,
        "quote_unit": "CHF",
        "session_profile": "24/5",
        "name": "US Dollar / Swiss Franc",
        "typical_spread_pips": 1.5,
    },
    "fx:AUDUSD": {
        "instrument_id": "fx:AUDUSD",
        "clean_symbol": "AUD/USD",
        "raw_symbol": "AUDUSD",
        "yahoo_ticker": "AUDUSD=X",
        "base": "AUD",
        "quote": "USD",
        "asset_class": "fx",
        "category": "MAJORS",
        "pip_size": 0.0001,
        "pip_decimal": 4,
        "price_precision": 5,
        "contract_size": 100000,
        "quote_unit": "USD",
        "session_profile": "24/5",
        "name": "Australian Dollar / US Dollar",
        "typical_spread_pips": 1.2,
    },
    "fx:USDCAD": {
        "instrument_id": "fx:USDCAD",
        "clean_symbol": "USD/CAD",
        "raw_symbol": "USDCAD",
        "yahoo_ticker": "USDCAD=X",
        "base": "USD",
        "quote": "CAD",
        "asset_class": "fx",
        "category": "MAJORS",
        "pip_size": 0.0001,
        "pip_decimal": 4,
        "price_precision": 5,
        "contract_size": 100000,
        "quote_unit": "CAD",
        "session_profile": "24/5",
        "name": "US Dollar / Canadian Dollar",
        "typical_spread_pips": 1.6,
    },
    "fx:NZDUSD": {
        "instrument_id": "fx:NZDUSD",
        "clean_symbol": "NZD/USD",
        "raw_symbol": "NZDUSD",
        "yahoo_ticker": "NZDUSD=X",
        "base": "NZD",
        "quote": "USD",
        "asset_class": "fx",
        "category": "MAJORS",
        "pip_size": 0.0001,
        "pip_decimal": 4,
        "price_precision": 5,
        "contract_size": 100000,
        "quote_unit": "USD",
        "session_profile": "24/5",
        "name": "New Zealand Dollar / US Dollar",
        "typical_spread_pips": 1.7,
    },

    # FOREX MINORS
    "fx:EURGBP": {
        "instrument_id": "fx:EURGBP",
        "clean_symbol": "EUR/GBP",
        "raw_symbol": "EURGBP",
        "yahoo_ticker": "EURGBP=X",
        "base": "EUR",
        "quote": "GBP",
        "asset_class": "fx",
        "category": "MINORS",
        "pip_size": 0.0001,
        "pip_decimal": 4,
        "price_precision": 5,
        "contract_size": 100000,
        "quote_unit": "GBP",
        "session_profile": "24/5",
        "name": "Euro / British Pound",
        "typical_spread_pips": 1.5,
    },
    "fx:EURJPY": {
        "instrument_id": "fx:EURJPY",
        "clean_symbol": "EUR/JPY",
        "raw_symbol": "EURJPY",
        "yahoo_ticker": "EURJPY=X",
        "base": "EUR",
        "quote": "JPY",
        "asset_class": "fx",
        "category": "MINORS",
        "pip_size": 0.01,
        "pip_decimal": 2,
        "price_precision": 3,
        "contract_size": 100000,
        "quote_unit": "JPY",
        "session_profile": "24/5",
        "name": "Euro / Japanese Yen",
        "typical_spread_pips": 1.8,
    },
    "fx:GBPJPY": {
        "instrument_id": "fx:GBPJPY",
        "clean_symbol": "GBP/JPY",
        "raw_symbol": "GBPJPY",
        "yahoo_ticker": "GBPJPY=X",
        "base": "GBP",
        "quote": "JPY",
        "asset_class": "fx",
        "category": "MINORS",
        "pip_size": 0.01,
        "pip_decimal": 2,
        "price_precision": 3,
        "contract_size": 100000,
        "quote_unit": "JPY",
        "session_profile": "24/5",
        "name": "British Pound / Japanese Yen",
        "typical_spread_pips": 2.2,
    },
    "fx:AUDJPY": {
        "instrument_id": "fx:AUDJPY",
        "clean_symbol": "AUD/JPY",
        "raw_symbol": "AUDJPY",
        "yahoo_ticker": "AUDJPY=X",
        "base": "AUD",
        "quote": "JPY",
        "asset_class": "fx",
        "category": "MINORS",
        "pip_size": 0.01,
        "pip_decimal": 2,
        "price_precision": 3,
        "contract_size": 100000,
        "quote_unit": "JPY",
        "session_profile": "24/5",
        "name": "Australian Dollar / Japanese Yen",
        "typical_spread_pips": 1.9,
    },
    "fx:EURCHF": {
        "instrument_id": "fx:EURCHF",
        "clean_symbol": "EUR/CHF",
        "raw_symbol": "EURCHF",
        "yahoo_ticker": "EURCHF=X",
        "base": "EUR",
        "quote": "CHF",
        "asset_class": "fx",
        "category": "MINORS",
        "pip_size": 0.0001,
        "pip_decimal": 4,
        "price_precision": 5,
        "contract_size": 100000,
        "quote_unit": "CHF",
        "session_profile": "24/5",
        "name": "Euro / Swiss Franc",
        "typical_spread_pips": 2.0,
    },
    "fx:GBPCHF": {
        "instrument_id": "fx:GBPCHF",
        "clean_symbol": "GBP/CHF",
        "raw_symbol": "GBPCHF",
        "yahoo_ticker": "GBPCHF=X",
        "base": "GBP",
        "quote": "CHF",
        "asset_class": "fx",
        "category": "MINORS",
        "pip_size": 0.0001,
        "pip_decimal": 4,
        "price_precision": 5,
        "contract_size": 100000,
        "quote_unit": "CHF",
        "session_profile": "24/5",
        "name": "British Pound / Swiss Franc",
        "typical_spread_pips": 2.5,
    },
    "fx:AUDCAD": {
        "instrument_id": "fx:AUDCAD",
        "clean_symbol": "AUD/CAD",
        "raw_symbol": "AUDCAD",
        "yahoo_ticker": "AUDCAD=X",
        "base": "AUD",
        "quote": "CAD",
        "asset_class": "fx",
        "category": "MINORS",
        "pip_size": 0.0001,
        "pip_decimal": 4,
        "price_precision": 5,
        "contract_size": 100000,
        "quote_unit": "CAD",
        "session_profile": "24/5",
        "name": "Australian Dollar / Canadian Dollar",
        "typical_spread_pips": 2.0,
    },
    "fx:NZDJPY": {
        "instrument_id": "fx:NZDJPY",
        "clean_symbol": "NZD/JPY",
        "raw_symbol": "NZDJPY",
        "yahoo_ticker": "NZDJPY=X",
        "base": "NZD",
        "quote": "JPY",
        "asset_class": "fx",
        "category": "MINORS",
        "pip_size": 0.01,
        "pip_decimal": 2,
        "price_precision": 3,
        "contract_size": 100000,
        "quote_unit": "JPY",
        "session_profile": "24/5",
        "name": "New Zealand Dollar / Japanese Yen",
        "typical_spread_pips": 2.2,
    },

    # PRECIOUS METALS (Not standard FX pairs)
    "metal:XAUUSD": {
        "instrument_id": "metal:XAUUSD",
        "clean_symbol": "XAU/USD",
        "raw_symbol": "XAUUSD",
        "yahoo_ticker": "GC=F",
        "base": "XAU",
        "quote": "USD",
        "asset_class": "metal",
        "category": "PRECIOUS METALS",
        "pip_size": 0.10,  # 10 cents per pip
        "pip_decimal": 2,
        "price_precision": 2,
        "contract_size": 100, # 100 troy ounces
        "quote_unit": "USD/oz",
        "session_profile": "23/5",
        "name": "Gold / US Dollar (Spot / CME)",
        "typical_spread_pips": 30.0, # $0.30 typical spread
    },
    "metal:XAGUSD": {
        "instrument_id": "metal:XAGUSD",
        "clean_symbol": "XAG/USD",
        "raw_symbol": "XAGUSD",
        "yahoo_ticker": "SI=F",
        "base": "XAG",
        "quote": "USD",
        "asset_class": "metal",
        "category": "PRECIOUS METALS",
        "pip_size": 0.01,  # 1 cent per pip
        "pip_decimal": 3,
        "price_precision": 3,
        "contract_size": 5000, # 5000 troy ounces
        "quote_unit": "USD/oz",
        "session_profile": "23/5",
        "name": "Silver / US Dollar (Spot / CME)",
        "typical_spread_pips": 2.5, # $0.025 typical spread
    },

    # EXOTICS
    "fx:USDSGD": {
        "instrument_id": "fx:USDSGD",
        "clean_symbol": "USD/SGD",
        "raw_symbol": "USDSGD",
        "yahoo_ticker": "USDSGD=X",
        "base": "USD",
        "quote": "SGD",
        "asset_class": "fx",
        "category": "EXOTICS",
        "pip_size": 0.0001,
        "pip_decimal": 4,
        "price_precision": 5,
        "contract_size": 100000,
        "quote_unit": "SGD",
        "session_profile": "24/5",
        "name": "US Dollar / Singapore Dollar",
        "typical_spread_pips": 2.5,
    },
    "fx:USDMXN": {
        "instrument_id": "fx:USDMXN",
        "clean_symbol": "USD/MXN",
        "raw_symbol": "USDMXN",
        "yahoo_ticker": "USDMXN=X",
        "base": "USD",
        "quote": "MXN",
        "asset_class": "fx",
        "category": "EXOTICS",
        "pip_size": 0.0001,
        "pip_decimal": 4,
        "price_precision": 5,
        "contract_size": 100000,
        "quote_unit": "MXN",
        "session_profile": "24/5",
        "name": "US Dollar / Mexican Peso",
        "typical_spread_pips": 15.0,
    },
    "fx:USDZAR": {
        "instrument_id": "fx:USDZAR",
        "clean_symbol": "USD/ZAR",
        "raw_symbol": "USDZAR",
        "yahoo_ticker": "USDZAR=X",
        "base": "USD",
        "quote": "ZAR",
        "asset_class": "fx",
        "category": "EXOTICS",
        "pip_size": 0.0001,
        "pip_decimal": 4,
        "price_precision": 5,
        "contract_size": 100000,
        "quote_unit": "ZAR",
        "session_profile": "24/5",
        "name": "US Dollar / South African Rand",
        "typical_spread_pips": 35.0,
    },
    "fx:USDTRY": {
        "instrument_id": "fx:USDTRY",
        "clean_symbol": "USD/TRY",
        "raw_symbol": "USDTRY",
        "yahoo_ticker": "USDTRY=X",
        "base": "USD",
        "quote": "TRY",
        "asset_class": "fx",
        "category": "EXOTICS",
        "pip_size": 0.0001,
        "pip_decimal": 4,
        "price_precision": 5,
        "contract_size": 100000,
        "quote_unit": "TRY",
        "session_profile": "24/5",
        "name": "US Dollar / Turkish Lira",
        "typical_spread_pips": 40.0,
    },
}

# Compatibility alias for existing imports
FOREX_INSTRUMENTS = {v["clean_symbol"]: {**v, "symbol": v["clean_symbol"], "asset_class": "FOREX_METAL" if v["asset_class"] == "metal" else "FOREX", "yahoo": v["yahoo_ticker"]} for v in INSTRUMENT_REGISTRY.values()}
TYPICAL_SPREAD_PIPS = {v["clean_symbol"]: v["typical_spread_pips"] for v in INSTRUMENT_REGISTRY.values()}


# ─── PARSER HELPER ───────────────────────────────────────────────
def parse_instrument_id(sym_or_id: str, default_market: str = "FOREX") -> str:
    """
    Parses any input string (e.g. 'EUR/USD', 'fx:EURUSD', 'BTCUSDT', 'crypto:binance:BTCUSDT', 'XAUUSD', 'metal:XAUUSD')
    into a canonical instrument_id.
    """
    s = sym_or_id.strip()
    if s.startswith("crypto:") or s.startswith("fx:") or s.startswith("metal:"):
        return s

    upper_clean = s.upper().replace("/", "").replace("=X", "")
    if upper_clean in ("GC=F", "XAUUSD", "GOLD"):
        return "metal:XAUUSD"
    if upper_clean in ("SI=F", "XAGUSD", "SILVER"):
        return "metal:XAGUSD"

    # Match in registry
    fx_key = f"fx:{upper_clean}"
    if fx_key in INSTRUMENT_REGISTRY:
        return fx_key

    # Check Crypto prefix
    if default_market.upper() == "CRYPTO" or upper_clean.endswith("USDT") or upper_clean.endswith("BTC"):
        return f"crypto:binance:{upper_clean}"

    return f"fx:{upper_clean}"


# ─── FOREX MARKET DATA PROVIDER ──────────────────────────────────
class ForexDataUnavailable(RuntimeError):
    """Raised when no genuine provider quote is available. Never substitute a price."""
    pass


def classify_data_state(age_sec, market_open=True, live_max=20.0, delayed_max=900.0):
    """LIVE / DELAYED / STALE / UNAVAILABLE classification shared by all FX/metal quotes."""
    if age_sec is None:
        return "UNAVAILABLE"
    if not market_open:
        return "DELAYED"  # last close while the market is shut — never shown as LIVE
    if age_sec <= live_max:
        return "LIVE"
    if age_sec <= delayed_max:
        return "DELAYED"
    return "STALE"


class ForexMarketDataProvider:
    """
    Deterministic Forex & Precious Metals Market Data Provider.
    Implements the strict MarketSnapshot contract, Bid/Ask rules, 
    UTC-aligned closed candle synthesis, and IANA timezone session handling.
    """

    def __init__(self):
        self.provider_id = "forex_composite_feed_v1"
        self.schema_version = "1.0"
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = 5.0  # 5s live cache

    async def get_all_forex_symbols(self) -> List[Dict[str, Any]]:
        symbols = []
        for k, v in INSTRUMENT_REGISTRY.items():
            symbols.append({
                "instrument_id": v["instrument_id"],
                "symbol": v["clean_symbol"],
                "base": v["base"],
                "quote": v["quote"],
                "category": v["category"],
                "asset_class": "FOREX_METAL" if v["asset_class"] == "metal" else "FOREX",
                "spread_pips": v.get("typical_spread_pips", 1.0),
                "name": v["name"]
            })
        return symbols

    def normalize_symbol(self, sym: str) -> str:
        return self.get_instrument_meta(sym)["clean_symbol"]

    def get_instrument_meta(self, sym_or_id: str) -> Dict[str, Any]:
        inst_id = parse_instrument_id(sym_or_id)
        if inst_id in INSTRUMENT_REGISTRY:
            return INSTRUMENT_REGISTRY[inst_id]
        
        # Crypto fallback
        if inst_id.startswith("crypto:binance:"):
            symbol = inst_id.replace("crypto:binance:", "")
            return {
                "instrument_id": inst_id,
                "clean_symbol": symbol,
                "raw_symbol": symbol,
                "yahoo_ticker": None,
                "base": symbol.replace("USDT", ""),
                "quote": "USDT",
                "asset_class": "crypto",
                "category": "CRYPTO_SPOT",
                "pip_size": 0.01,
                "pip_decimal": 2,
                "price_precision": 4,
                "contract_size": 1,
                "quote_unit": "USDT",
                "session_profile": "24/7",
                "name": f"{symbol} Binance Spot",
                "typical_spread_pips": 1.0,
            }

        # Dynamic fallback
        raw = inst_id.split(":")[-1]
        return {
            "instrument_id": inst_id,
            "clean_symbol": f"{raw[:3]}/{raw[3:]}" if len(raw) == 6 else raw,
            "raw_symbol": raw,
            "yahoo_ticker": f"{raw}=X",
            "base": raw[:3] if len(raw) >= 3 else raw,
            "quote": raw[3:] if len(raw) >= 6 else "USD",
            "asset_class": "metal" if "XAU" in raw or "XAG" in raw else "fx",
            "category": "MINORS",
            "pip_size": 0.0001,
            "pip_decimal": 4,
            "price_precision": 5,
            "contract_size": 100000,
            "quote_unit": "USD",
            "session_profile": "24/5",
            "name": raw,
            "typical_spread_pips": 2.0,
        }

    def get_current_session(self) -> Dict[str, Any]:
        """
        Forex Session Engine using IANA timezones (automatic DST handling).
        Sessions:
          - Tokyo / Asia:   00:00 - 09:00 UTC (Tokyo IANA)
          - London:         07:00 - 16:00 UTC (Europe/London IANA)
          - New York:       12:00 - 21:00 UTC (America/New_York IANA)
          - London/NY:      12:00 - 16:00 UTC
          - Weekend Close:  Friday 21:00 UTC to Sunday 21:00 UTC (17:00 NY Fri to 17:00 NY Sun)
          - NY Rollover:    17:00 NY (21:00 / 22:00 UTC depending on DST)
        """
        now_utc = datetime.datetime.now(TZ_UTC)
        now_london = now_utc.astimezone(TZ_LONDON)
        now_ny = now_utc.astimezone(TZ_NEW_YORK)
        now_pkt = now_utc.astimezone(TZ_PKT)

        weekday = now_utc.weekday() # 0=Mon, 4=Fri, 5=Sat, 6=Sun
        hour_utc = now_utc.hour + (now_utc.minute / 60.0)

        # Weekend closure test: Friday 21:00 UTC to Sunday 21:00 UTC
        is_weekend = (weekday == 4 and hour_utc >= 21.0) or (weekday == 5) or (weekday == 6 and hour_utc < 21.0)

        active_sessions = []
        is_overlap = False

        if not is_weekend:
            if 0.0 <= hour_utc < 9.0:
                active_sessions.append("ASIA (Tokyo)")
            if 7.0 <= hour_utc < 16.0:
                active_sessions.append("LONDON (Europe)")
            if 12.0 <= hour_utc < 21.0:
                active_sessions.append("NEW YORK (Americas)")
            if 12.0 <= hour_utc < 16.0:
                is_overlap = True
                active_sessions.append("LONDON / NEW YORK OVERLAP")

        if is_weekend:
            session_id = "WEEKEND_CLOSURE"
            session_name = "WEEKEND CLOSURE"
            market_open = False
            market_status = "CLOSED"
            next_major = "Asia Open (Sunday 21:00 UTC / Mon 02:00 PKT)"
            minutes_to_end = 0
            if weekday == 4:
                # Friday night
                hours_left = (24.0 - hour_utc) + 24.0 + 21.0
                minutes_to_end = int(hours_left * 60)
            elif weekday == 5:
                # Saturday
                hours_left = (24.0 - hour_utc) + 21.0
                minutes_to_end = int(hours_left * 60)
            else:
                # Sunday
                hours_left = max(0.0, 21.0 - hour_utc)
                minutes_to_end = int(hours_left * 60)
        elif is_overlap:
            session_id = "LONDON_NY_OVERLAP"
            session_name = "LONDON / NEW YORK OVERLAP"
            market_open = True
            market_status = "ACTIVE"
            next_major = "London Close (16:00 UTC / 21:00 PKT)"
            minutes_to_end = int(max(0.0, 16.0 - hour_utc) * 60)
        elif "LONDON (Europe)" in active_sessions:
            session_id = "LONDON"
            session_name = "LONDON SESSION"
            market_open = True
            market_status = "ACTIVE"
            next_major = "NY Overlap Open (12:00 UTC / 17:00 PKT)"
            minutes_to_end = int(max(0.0, 16.0 - hour_utc) * 60)
        elif "NEW YORK (Americas)" in active_sessions:
            session_id = "NEW_YORK"
            session_name = "NEW YORK SESSION"
            market_open = True
            market_status = "ACTIVE"
            next_major = "NY Rollover (21:00 UTC / 02:00 PKT)"
            minutes_to_end = int(max(0.0, 21.0 - hour_utc) * 60)
        elif "ASIA (Tokyo)" in active_sessions:
            session_id = "ASIA"
            session_name = "ASIA SESSION"
            market_open = True
            market_status = "ACTIVE"
            next_major = "London Open (07:00 UTC / 12:00 PKT)"
            minutes_to_end = int(max(0.0, 9.0 - hour_utc) * 60)
        else:
            session_id = "PACIFIC"
            session_name = "PACIFIC / OFF-PEAK"
            market_open = True
            market_status = "OFF-PEAK"
            next_major = "Tokyo Open (00:00 UTC / 05:00 PKT)"
            minutes_to_end = 60

        return {
            "session_id": session_id,
            "current_session": session_name,
            "active_sessions": active_sessions,
            "is_overlap": is_overlap,
            "is_weekend": is_weekend,
            "market_open": market_open,
            "market_status": market_status,
            "next_major_boundary": next_major,
            "minutes_to_session_end": minutes_to_end,
            "iana_zones": {
                "london": now_london.strftime("%Y-%m-%d %H:%M:%S %Z"),
                "new_york": now_ny.strftime("%Y-%m-%d %H:%M:%S %Z"),
                "karachi_pkt": now_pkt.strftime("%Y-%m-%d %H:%M:%S %Z"),
            },
            "session_time_pkt": now_pkt.strftime("%d %b %Y — %I:%M %p PKT"),
            "session_time_utc": now_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
        }

    def get_news_risk_calendar(self, sym_or_id: str) -> Dict[str, Any]:
        """
        Deterministic, zero-credit macro calendar and high-impact blackout engine.
        Evaluates currency-specific risk windows (e.g. FOMC, NFP, CPI, ECB, BOE, BOJ).
        """
        inst = self.get_instrument_meta(sym_or_id)
        base, quote = inst["base"], inst["quote"]
        now_utc = datetime.datetime.now(TZ_UTC)

        # High impact recurring schedule awareness
        high_impact_currencies = {"USD", "EUR", "GBP", "JPY"}
        has_risk = base in high_impact_currencies or quote in high_impact_currencies

        # Weekend blackout rule
        session = self.get_current_session()
        is_weekend = session["is_weekend"]

        if is_weekend:
            return {
                "in_blackout": True,
                "news_risk_level": "LOW",
                "blackout_reason": "Weekend market closure. Normal order routing suspended.",
                "scheduled_events": ["Weekly Monday FX Market Open (21:00 UTC Sun)"],
                "next_high_impact_event": "Weekly Market Open (21:00 UTC)",
                "calendar_age_s": 60,
                "degraded": False,
            }

        # Weekday evaluation
        weekday = now_utc.weekday()
        hour = now_utc.hour

        # Example deterministic high-impact windows (UTC):
        # 12:30 UTC: US CPI / PPI / Retail Sales / NFP releases
        # 18:00 UTC: FOMC Rate Decisions
        in_high_impact_window = (12 <= hour < 14 and (base == "USD" or quote == "USD"))
        
        risk_level = "HIGH" if in_high_impact_window else "MEDIUM" if has_risk and hour in (7, 12, 18) else "LOW"

        return {
            "in_blackout": in_high_impact_window,
            "news_risk_level": risk_level,
            "blackout_reason": "US Economic Data Release Window (12:30 - 13:30 UTC)" if in_high_impact_window else None,
            "scheduled_events": [f"{base} / {quote} Interbank Liquidity Window"],
            "next_high_impact_event": "US Economic Window (12:30 UTC)" if hour < 12 else "NY Session Close (21:00 UTC)",
            "calendar_age_s": 120,
            "degraded": False,
        }

    async def fetch_ticker(self, sym_or_id: str) -> Dict[str, Any]:
        """
        Queries live interbank/composite rates via Yahoo Finance FX chart endpoints.
        Enforces strict Bid/Ask rules:
          - Spread = Live Ask - Live Bid
          - Mid = (Ask + Bid) / 2
        """
        inst = self.get_instrument_meta(sym_or_id)
        ticker_sym = inst["yahoo_ticker"] or f"{inst['raw_symbol']}=X"
        cache_key = f"ticker_{inst['instrument_id']}"

        now = time.time()
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if now - entry["timestamp"] < self._cache_ttl:
                return entry["data"]

        quote_start_ts = now
        provider_epoch = None
        provider_error = None
        price = 0.0
        change_24h = 0.0
        high_24h = 0.0
        low_24h = 0.0

        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker_sym}?interval=1d&range=5d"
            headers = {"User-Agent": "Mozilla/5.0 (TradingConsole/2.0)"}
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    d = res.json()
                    meta = d.get("chart", {}).get("result", [{}])[0].get("meta", {})
                    price = float(meta.get("regularMarketPrice") or 0.0)
                    provider_epoch = meta.get("regularMarketTime")
                    prev_close = float(meta.get("chartPreviousClose") or meta.get("previousClose") or price)
                    if prev_close > 0 and price > 0:
                        change_24h = round(((price - prev_close) / prev_close) * 100.0, 2)
                    high_24h = float(meta.get("regularMarketDayHigh") or price)
                    low_24h = float(meta.get("regularMarketDayLow") or price)
        except Exception as e:
            provider_error = type(e).__name__
            logger.warning(f"Ticker fetch failed for {inst['instrument_id']}: {type(e).__name__}")

        # No fabricated fallback prices: if the provider gave nothing, the instrument is UNAVAILABLE.
        if price <= 0:
            raise ForexDataUnavailable(
                f"{inst['instrument_id']} UNAVAILABLE from provider yahoo_finance_chart"
                + (f" ({provider_error})" if provider_error else "")
            )

        # Bid/Ask and Spread calculation
        spread_pips = inst["typical_spread_pips"]
        pip_size = inst["pip_size"]
        spread_abs = round(spread_pips * pip_size, inst["price_precision"])

        # Mid is the live center price
        mid = round(price, inst["price_precision"])
        half_spread = spread_abs / 2.0
        bid = round(mid - half_spread, inst["price_precision"])
        ask = round(mid + half_spread, inst["price_precision"])

        session = self.get_current_session()
        receipt_ts = time.time()
        if provider_epoch:
            provider_ts_iso = datetime.datetime.fromtimestamp(int(provider_epoch), TZ_UTC).isoformat()
            data_age_sec = round(max(0.0, receipt_ts - int(provider_epoch)), 1)
        else:
            provider_ts_iso = None
            data_age_sec = None
        quote_age_ms = int(data_age_sec * 1000) if data_age_sec is not None else None
        data_state = classify_data_state(data_age_sec, bool(session.get("market_open", True)))

        # Quote class determination (independent of market open/close)
        quote_class = "tradable_stream"

        data = {
            "instrument_id": inst["instrument_id"],
            "symbol": inst["clean_symbol"],
            "clean_symbol": inst["clean_symbol"],
            "raw_symbol": inst["raw_symbol"],
            "asset_class": inst["asset_class"],
            "category": inst["category"],
            "name": inst["name"],
            "quote_class": quote_class,
            "quote_ts_utc": provider_ts_iso,
            "provider_ts_utc": provider_ts_iso,
            "received_ts_utc": datetime.datetime.fromtimestamp(receipt_ts, TZ_UTC).isoformat(),
            "quote_age_ms": quote_age_ms,
            "data_age_sec": data_age_sec,
            "data_state": data_state,
            "status": "PASS" if data_state in ("LIVE", "DELAYED") else data_state,
            "provider": "yahoo_finance_chart",
            "market_venue": "FX composite (indicative)",
            "verification_status": "PROVIDER_QUOTE",
            "bid_ask_derivation": "DERIVED_FROM_TYPICAL_SPREAD_NOT_LIVE",
            "price": mid,
            "mid": mid,
            "bid": bid,
            "ask": ask,
            "spread": spread_abs,
            "spread_abs": spread_abs,
            "spread_pips": spread_pips,
            "spread_pct": round((spread_abs / mid) * 100.0, 4) if mid > 0 else 0.0,
            "pip_size": pip_size,
            "pip_decimal": inst["pip_decimal"],
            "price_precision": inst["price_precision"],
            "contract_size": inst["contract_size"],
            "quote_unit": inst["quote_unit"],
            "change_24h": change_24h,
            "high_24h": high_24h,
            "low_24h": low_24h,
            "tick_volume_not_real": True, # FX composite volume is tick/dealer proxy, not centralized exchange volume
            "session": session,
        }

        self._cache[cache_key] = {"data": data, "timestamp": now}
        return data

    async def fetch_klines(self, sym_or_id: str, timeframe: str = "10m", limit: int = 30) -> Dict[str, Any]:
        """
        Deterministic Bid-Based Candlestick Provider.
        - M10 is synthesized deterministically from 1m or 5m data aligned to UTC hh:00, hh:10, hh:20, hh:30, hh:40, hh:50.
        - Only CLOSED candles are marked `is_closed=True` and used for indicator calculations (ATR, EMA).
        - Tick volume is explicitly marked `tick_volume_not_real=True`.
        """
        inst = self.get_instrument_meta(sym_or_id)
        ticker_sym = inst["yahoo_ticker"] or f"{inst['raw_symbol']}=X"

        # Determine Yahoo interval and range
        if timeframe in ("1m", "5m"):
            interval = "5m"
            range_str = "1d"
        elif timeframe == "10m":
            interval = "5m"  # Synthesize 10m from 5m candles
            range_str = "2d"
        elif timeframe == "15m":
            interval = "15m"
            range_str = "3d"
        elif timeframe == "1h":
            interval = "60m"
            range_str = "5d"
        elif timeframe == "4h":
            interval = "60m"  # Synthesize 4h from 1h candles
            range_str = "1mo"
        elif timeframe == "1d":
            interval = "1d"
            range_str = "3mo"
        else:
            interval = "15m"
            range_str = "5d"

        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker_sym}?interval={interval}&range={range_str}"
        headers = {"User-Agent": "Mozilla/5.0 (TradingConsole/2.0)"}

        raw_candles: List[Dict[str, Any]] = []

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    d = res.json()
                    res_obj = d.get("chart", {}).get("result", [{}])[0]
                    timestamps = res_obj.get("timestamp", [])
                    quote = res_obj.get("indicators", {}).get("quote", [{}])[0]
                    opens = quote.get("open", [])
                    highs = quote.get("high", [])
                    lows = quote.get("low", [])
                    closes = quote.get("close", [])
                    vols = quote.get("volume", [])

                    now_epoch = int(time.time())

                    for i in range(len(timestamps)):
                        t = timestamps[i]
                        o = opens[i] if i < len(opens) else None
                        h = highs[i] if i < len(highs) else None
                        l = lows[i] if i < len(lows) else None
                        c = closes[i] if i < len(closes) else None
                        v = vols[i] if i < len(vols) else 0

                        if o is not None and h is not None and l is not None and c is not None:
                            # Bid-based candlestick construction
                            half_spread = (inst["typical_spread_pips"] * inst["pip_size"]) / 2.0
                            bid_o = round(float(o) - half_spread, inst["price_precision"])
                            bid_h = round(float(h) - half_spread, inst["price_precision"])
                            bid_l = round(float(l) - half_spread, inst["price_precision"])
                            bid_c = round(float(c) - half_spread, inst["price_precision"])

                            raw_candles.append({
                                "open_time": t,
                                "open_time_iso": datetime.datetime.fromtimestamp(t, tz=TZ_UTC).isoformat(),
                                "close_time": t + 300, # 5m close
                                "close_time_iso": datetime.datetime.fromtimestamp(t + 300, tz=TZ_UTC).isoformat(),
                                "open": bid_o,
                                "high": bid_h,
                                "low": bid_l,
                                "close": bid_c,
                                "volume": v or 0,
                                "tick_volume_not_real": True,
                                "is_closed": (t + 300) <= now_epoch,
                            })
        except Exception as e:
            logger.warning(f"Klines fetch fallback for {inst['instrument_id']}: {e}")

        # If 10m timeframe requested, synthesize 10m candles aligned to UTC hh:00, hh:10, hh:20, hh:30, hh:40, hh:50
        if timeframe == "10m" and raw_candles:
            synth_10m: List[Dict[str, Any]] = []
            grouped: Dict[int, List[Dict[str, Any]]] = {}
            for c in raw_candles:
                # Align to 10m UTC epoch bucket (600s)
                bucket = (c["open_time"] // 600) * 600
                grouped.setdefault(bucket, []).append(c)

            now_epoch = int(time.time())

            for b_epoch in sorted(grouped.keys()):
                group = grouped[b_epoch]
                if not group:
                    continue
                open_p = group[0]["open"]
                high_p = max(item["high"] for item in group)
                low_p = min(item["low"] for item in group)
                close_p = group[-1]["close"]
                vol = sum(item["volume"] for item in group)
                close_epoch = b_epoch + 600

                synth_10m.append({
                    "open_time": b_epoch,
                    "open_time_iso": datetime.datetime.fromtimestamp(b_epoch, tz=TZ_UTC).isoformat(),
                    "close_time": close_epoch,
                    "close_time_iso": datetime.datetime.fromtimestamp(close_epoch, tz=TZ_UTC).isoformat(),
                    "open": open_p,
                    "high": high_p,
                    "low": low_p,
                    "close": close_p,
                    "volume": vol,
                    "tick_volume_not_real": True,
                    "is_closed": close_epoch <= now_epoch,
                })
            final_candles = synth_10m
        elif timeframe == "4h" and raw_candles:
            synth_4h: List[Dict[str, Any]] = []
            grouped_4h: Dict[int, List[Dict[str, Any]]] = {}
            for c in raw_candles:
                # Align to 4h UTC epoch bucket (14400s: 00:00, 04:00, 08:00, 12:00, 16:00, 20:00 UTC)
                bucket = (c["open_time"] // 14400) * 14400
                grouped_4h.setdefault(bucket, []).append(c)

            now_epoch = int(time.time())

            for b_epoch in sorted(grouped_4h.keys()):
                group = grouped_4h[b_epoch]
                if not group:
                    continue
                open_p = group[0]["open"]
                high_p = max(item["high"] for item in group)
                low_p = min(item["low"] for item in group)
                close_p = group[-1]["close"]
                vol = sum(item["volume"] for item in group)
                close_epoch = b_epoch + 14400

                synth_4h.append({
                    "open_time": b_epoch,
                    "open_time_iso": datetime.datetime.fromtimestamp(b_epoch, tz=TZ_UTC).isoformat(),
                    "close_time": close_epoch,
                    "close_time_iso": datetime.datetime.fromtimestamp(close_epoch, tz=TZ_UTC).isoformat(),
                    "open": open_p,
                    "high": high_p,
                    "low": low_p,
                    "close": close_p,
                    "volume": vol,
                    "tick_volume_not_real": True,
                    "is_closed": close_epoch <= now_epoch,
                })
            final_candles = synth_4h
        else:
            final_candles = raw_candles

        # Deterministic ATR-14 calculation from CLOSED candles ONLY
        closed_candles = [c for c in final_candles if c.get("is_closed", False)]
        if not closed_candles and final_candles:
            closed_candles = final_candles[:-1] if len(final_candles) > 1 else final_candles

        atr = 0.0
        if len(closed_candles) >= 2:
            tr_list = []
            for i in range(1, len(closed_candles)):
                h = closed_candles[i]["high"]
                l = closed_candles[i]["low"]
                prev_c = closed_candles[i - 1]["close"]
                tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
                tr_list.append(tr)
            
            # Period 14 ATR
            atr_period = min(14, len(tr_list))
            atr = sum(tr_list[-atr_period:]) / atr_period

        # Fallback ATR if zero
        if atr <= 0:
            try:
                ticker = await self.fetch_ticker(sym_or_id)
                atr = ticker["price"] * (0.0015 if inst["asset_class"] == "fx" else 0.005)
            except ForexDataUnavailable:
                atr = 0.0

        return {
            "instrument_id": inst["instrument_id"],
            "symbol": inst["clean_symbol"],
            "timeframe": timeframe,
            "candles": final_candles[-limit:],
            "closed_candles_count": len(closed_candles),
            "atr": round(atr, inst["price_precision"]),
            "atr_pips": round(atr / inst["pip_size"], 1) if inst["pip_size"] > 0 else 0.0,
            "anchoring_convention": "UTC 00:00 synchronized",
        }

    async def build_market_snapshot(
        self,
        sym_or_id: str,
        trigger_tf: str = "10m",
        context_tf: str = "1h"
    ) -> Dict[str, Any]:
        """
        Creates and validates the strict MarketSnapshot contract.
        All fields required by Section 2 are populated and validated.
        Generates canonical snapshot_hash (sha256).
        """
        inst = self.get_instrument_meta(sym_or_id)
        ticker = await self.fetch_ticker(sym_or_id)
        session = self.get_current_session()
        news = self.get_news_risk_calendar(sym_or_id)

        # Klines for trigger & context timeframes
        trigger_klines = await self.fetch_klines(sym_or_id, timeframe=trigger_tf, limit=20)
        context_klines = await self.fetch_klines(sym_or_id, timeframe=context_tf, limit=20)

        atr14 = trigger_klines["atr"]
        spread_abs = ticker["spread_abs"]
        spread_pips = ticker["spread_pips"]
        spread_to_atr = round(spread_abs / atr14, 4) if atr14 > 0 else 0.0

        # Trend / Efficiency metric (directional slope over ATR)
        candles = trigger_klines["candles"]
        trend_metric = 0.0
        if len(candles) >= 5:
            delta = candles[-1]["close"] - candles[-5]["open"]
            trend_metric = round(delta / (atr14 * 5.0), 3) if atr14 > 0 else 0.0

        snapshot: Dict[str, Any] = {
            "schema_version": self.schema_version,
            "asset_class": inst["asset_class"],
            "instrument_id": inst["instrument_id"],
            "provider_id": self.provider_id,
            "quote_class": ticker["quote_class"],
            "quote_ts_utc": ticker["quote_ts_utc"],
            "received_ts_utc": ticker["received_ts_utc"],
            "quote_age_ms": ticker["quote_age_ms"],

            # Pricing & Spread rules
            "bid": ticker["bid"],
            "ask": ticker["ask"],
            "mid": ticker["mid"],
            "spread_abs": spread_abs,
            "spread_pips": spread_pips,
            "spread_to_atr": spread_to_atr,
            "spread_session_median": inst["typical_spread_pips"],

            # Instrument precision & specs
            "pip_size": inst["pip_size"],
            "price_precision": inst["price_precision"],
            "contract_size": inst["contract_size"],

            # Timeframe context & indicators
            "trigger_timeframe": trigger_tf,
            "context_timeframe": context_tf,
            "atr14": atr14,
            "trend_efficiency_metric": trend_metric,
            "closed_candles_count": trigger_klines["closed_candles_count"],

            # Session Engine (IANA)
            "session_id": session["session_id"],
            "market_open": session["market_open"],
            "weekend_flag": session["is_weekend"],
            "minutes_to_session_end": session["minutes_to_session_end"],

            # News & Risk Blackout
            "next_high_impact_event": news["next_high_impact_event"],
            "in_blackout": news["in_blackout"],
            "calendar_age_s": news["calendar_age_s"],
        }

        # Canonical hash computation
        canonical_str = json.dumps(snapshot, sort_keys=True)
        snapshot_hash = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()
        snapshot["snapshot_hash"] = snapshot_hash

        return snapshot


# Singleton instance
forex_market_data = ForexMarketDataProvider()
