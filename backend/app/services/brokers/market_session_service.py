"""
BITDEX Authoritative Market Session and Schedule Service
========================================================
Determines live market availability and accurate next opening countdowns:
- Crypto (BTC, ETH, XRP, SOL, etc.): 24/7/365 Continuous Trading.
- Forex (EUR, GBP, JPY, AUD, CAD, CHF, NZD): Sunday 22:00 UTC to Friday 22:00 UTC.
- Metals (XAU, XAG, XPT): Sunday 23:00 UTC to Friday 21:55 UTC (Daily break 21:55 - 23:00 UTC).
- Real-time quote freshness evaluation: If market is within hours but no quote received within threshold -> QUOTE STALE / BROKER UNAVAILABLE.
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Tuple

def get_market_session_status(
    symbol: str,
    category: str,
    quote: Optional[Dict[str, Any]] = None,
    current_time: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Evaluates authoritative market status and computes exact seconds until opening.
    """
    now = current_time or datetime.now(timezone.utc)
    sym = symbol.strip().upper()
    cat = (category or "").strip().upper()

    is_crypto = "CRYPTO" in cat or sym.startswith("BTC") or sym.startswith("ETH") or sym.startswith("SOL") or sym.startswith("XRP") or sym.startswith("LTC") or sym.startswith("DOGE")
    is_metal = "METAL" in cat or sym.startswith("XAU") or sym.startswith("XAG") or sym.startswith("XPT")
    is_forex = not is_crypto and not is_metal

    # 1. Crypto Schedule: 24/7/365
    if is_crypto:
        if not quote or not quote.get("bid") or quote.get("bid") <= 0:
            return {
                "market_status": "BROKER UNAVAILABLE",
                "is_market_open": False,
                "reason": "Live quote unavailable from broker stream",
                "seconds_until_open": 0,
                "opens_at_iso": None,
                "countdown_text": ""
            }
        return {
            "market_status": "MARKET OPEN",
            "is_market_open": True,
            "reason": "Crypto trades 24/7/365",
            "seconds_until_open": 0,
            "opens_at_iso": None,
            "countdown_text": ""
        }

    weekday = now.weekday() # 0 = Monday, 4 = Friday, 5 = Saturday, 6 = Sunday
    hour = now.hour
    minute = now.minute
    time_float = hour + minute / 60.0

    # 2. Forex Schedule: Sunday 22:00 UTC -> Friday 22:00 UTC
    if is_forex:
        is_open = True
        opens_at = None

        # Weekend closure: Friday 22:00 UTC to Sunday 22:00 UTC
        if weekday == 4 and time_float >= 22.0: # Friday after 22:00 UTC
            is_open = False
            days_ahead = 2 # Sunday
            opens_at = (now + timedelta(days=days_ahead)).replace(hour=22, minute=0, second=0, microsecond=0)
        elif weekday == 5: # Saturday
            is_open = False
            days_ahead = 1 # Sunday
            opens_at = (now + timedelta(days=days_ahead)).replace(hour=22, minute=0, second=0, microsecond=0)
        elif weekday == 6 and time_float < 22.0: # Sunday before 22:00 UTC
            is_open = False
            opens_at = now.replace(hour=22, minute=0, second=0, microsecond=0)

        if not is_open and opens_at:
            secs = max(0, int((opens_at - now).total_seconds()))
            m, s = divmod(secs, 60)
            h, m = divmod(m, 60)
            cd_text = f"{h:02d}:{m:02d}:{s:02d}"
            return {
                "market_status": "MARKET CLOSED",
                "is_market_open": False,
                "reason": f"Weekend Forex closure (Reopens Sunday 22:00 UTC)",
                "seconds_until_open": secs,
                "opens_at_iso": opens_at.isoformat(),
                "countdown_text": cd_text
            }

        # Market is within hours: verify quote freshness
        if not quote or not quote.get("bid") or quote.get("bid") <= 0:
            return {
                "market_status": "QUOTE STALE",
                "is_market_open": False,
                "reason": "Market open but waiting for live broker quote",
                "seconds_until_open": 0,
                "opens_at_iso": None,
                "countdown_text": ""
            }

        return {
            "market_status": "MARKET OPEN",
            "is_market_open": True,
            "reason": "Standard Forex market session active",
            "seconds_until_open": 0,
            "opens_at_iso": None,
            "countdown_text": ""
        }

    # 3. Metals Schedule: Sunday 23:00 UTC -> Friday 21:55 UTC (Daily break 21:55 - 23:00 UTC)
    if is_metal:
        is_open = True
        opens_at = None

        # Weekend closure: Friday 21:55 UTC to Sunday 23:00 UTC
        if (weekday == 4 and time_float >= (21 + 55/60.0)) or weekday == 5 or (weekday == 6 and time_float < 23.0):
            is_open = False
            days_ahead = (6 - weekday) % 7
            if weekday == 6 and time_float < 23.0:
                opens_at = now.replace(hour=23, minute=0, second=0, microsecond=0)
            else:
                opens_at = (now + timedelta(days=days_ahead)).replace(hour=23, minute=0, second=0, microsecond=0)
        # Daily maintenance break: Mon-Thu 21:55 - 23:00 UTC
        elif weekday in (0, 1, 2, 3) and (21 + 55/60.0) <= time_float < 23.0:
            is_open = False
            opens_at = now.replace(hour=23, minute=0, second=0, microsecond=0)

        if not is_open and opens_at:
            secs = max(0, int((opens_at - now).total_seconds()))
            m, s = divmod(secs, 60)
            h, m = divmod(m, 60)
            cd_text = f"{h:02d}:{m:02d}:{s:02d}"
            return {
                "market_status": "MARKET CLOSED",
                "is_market_open": False,
                "reason": "Market closed (Daily break or weekend closure)",
                "seconds_until_open": secs,
                "opens_at_iso": opens_at.isoformat(),
                "countdown_text": cd_text
            }

        if not quote or not quote.get("bid") or quote.get("bid") <= 0:
            return {
                "market_status": "QUOTE STALE",
                "is_market_open": False,
                "reason": "Market open but waiting for live broker quote",
                "seconds_until_open": 0,
                "opens_at_iso": None,
                "countdown_text": ""
            }

        return {
            "market_status": "MARKET OPEN",
            "is_market_open": True,
            "reason": "Metals market session active",
            "seconds_until_open": 0,
            "opens_at_iso": None,
            "countdown_text": ""
        }

    return {
        "market_status": "MARKET STATUS UNKNOWN",
        "is_market_open": False,
        "reason": "Unknown category schedule",
        "seconds_until_open": 0,
        "opens_at_iso": None,
        "countdown_text": ""
    }
