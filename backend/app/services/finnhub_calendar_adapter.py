"""
Finnhub Economic Calendar Evaluation & Adapter (Phase 2).
Provides zero-cost, read-only analysis and parsing of economic calendar releases.

Architecture & Tier Boundaries:
1. Endpoint: GET https://finnhub.io/api/v1/calendar/economic?from={from_date}&to={to_date}&token={api_key}
2. Coverage: Major G10 currencies (USD, EUR, GBP, JPY, CAD, AUD, CHF) and events:
   - High Impact: CPI, Non-Farm Payrolls (NFP), FOMC / ECB / BOE Interest Rate Decisions, GDP.
   - Medium Impact: Retail Sales, PMI (Manufacturing/Services), PPI, Consumer Confidence.
   - Low Impact: Trade Balance, Housing Starts, Factory Orders.
3. Rate Limits:
   - Free Tier: 30 to 60 API calls per minute (30 req/min default per IP).
   - Commercial / Paid Tier: 300+ req/min, websocket streams.
4. Evaluation Recommendation:
   - Free tier is adequate for 30-minute to 1-hour interval polling of high-impact macroeconomic event schedules.
   - Live trading blackout engine requires only the release schedule timestamps, not paid millisecond news feeds.
5. Invariant Enforcement:
   - NO paid API calls or subscriptions.
   - Zero-cost mock fixtures provided for offline unit testing and automated continuous integration.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

FINNHUB_TIER_SPECS = {
    "provider": "Finnhub",
    "endpoint": "https://finnhub.io/api/v1/calendar/economic",
    "parameters": ["from (YYYY-MM-DD)", "to (YYYY-MM-DD)", "token"],
    "free_tier_status": "NOT_AVAILABLE",
    "free_tier_entitlement": "NEEDS APPROVAL / UNVERIFIED",
    "entitlement_finding": (
        "Finnhub official API documentation specifies 'Premium Access Required' for /calendar/economic. "
        "The $0/month Free Tier does not grant access to this endpoint (returns HTTP 403 Forbidden). "
        "Access requires the 'Economic Data' (Economic-1) module at $50.00/month (billed quarterly) or Enterprise plan."
    ),
    "paid_tier_cost_monthly_usd": 50.0,
    "paid_tier_billing": "Quarterly ($150.00 / quarter)",
    "rate_limits": {
        "free_tier_general_rpm": 60,
        "economic_calendar_rpm": 0,  # Premium only
        "paid_tier_rpm": 150
    },
    "supported_fields": ["event", "country", "time", "impact", "actual", "estimate", "prev", "unit"],
    "supported_countries": ["US", "EU", "GB", "JP", "CA", "AU", "CH"],
    "supported_currencies": ["USD", "EUR", "GBP", "JPY", "CAD", "AUD", "CHF"],
    "zero_cost_safeguard": "Use offline mock fixtures for risk engine testing. Do not connect paid API without explicit user approval."
}

# Backward compatibility alias
FINNHUB_FREE_TIER_SPECS = FINNHUB_TIER_SPECS

# Standard mock fixture for offline testing
MOCK_FINNHUB_CALENDAR_FIXTURES: List[Dict[str, Any]] = [
    {
        "actual": 3.2,
        "country": "US",
        "estimate": 3.1,
        "event": "CPI YoY",
        "impact": "high",
        "prev": 3.4,
        "time": "2026-10-21 12:30:00",
        "unit": "%"
    },
    {
        "actual": None,
        "country": "US",
        "estimate": 5.25,
        "event": "Fed Interest Rate Decision",
        "impact": "high",
        "prev": 5.25,
        "time": "2026-10-21 18:00:00",
        "unit": "%"
    },
    {
        "actual": 51.2,
        "country": "EU",
        "estimate": 50.8,
        "event": "HCOB Flash Eurozone Manufacturing PMI",
        "impact": "medium",
        "prev": 50.5,
        "time": "2026-10-21 08:00:00",
        "unit": "Index"
    },
    {
        "actual": 0.4,
        "country": "GB",
        "estimate": 0.3,
        "event": "Retail Sales MoM",
        "impact": "low",
        "prev": -0.1,
        "time": "2026-10-21 06:00:00",
        "unit": "%"
    }
]

class FinnhubCalendarAdapter:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.specs = FINNHUB_FREE_TIER_SPECS

    def get_tier_specifications(self) -> Dict[str, Any]:
        """Returns the rate limit, cost, and architecture boundaries for Finnhub."""
        return self.specs

    def parse_economic_events(self, raw_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Parses raw Finnhub economic calendar records into canonical Tauric event structures.
        Handles missing fields, None actuals, and normalizes impact scores.
        """
        parsed = []
        for e in raw_events:
            event_name = str(e.get("event") or "Economic Release").strip()
            country = str(e.get("country") or "GLOBAL").strip().upper()
            impact_raw = str(e.get("impact") or "low").strip().lower()
            
            # Map impact string to integer weight
            if impact_raw in ("high", "3"):
                impact_level = "HIGH"
                impact_weight = 3
            elif impact_raw in ("medium", "med", "2"):
                impact_level = "MEDIUM"
                impact_weight = 2
            else:
                impact_level = "LOW"
                impact_weight = 1

            time_str = str(e.get("time") or "")
            actual = e.get("actual")
            estimate = e.get("estimate")
            prev = e.get("prev")
            unit = str(e.get("unit") or "").strip()

            parsed.append({
                "event": event_name,
                "country": country,
                "impact_level": impact_level,
                "impact_weight": impact_weight,
                "time_utc": time_str,
                "actual": actual,
                "estimate": estimate,
                "previous": prev,
                "unit": unit,
                "is_released": actual is not None
            })
            
        return parsed

    def filter_high_impact_events(
        self,
        events: List[Dict[str, Any]],
        country: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Filters events to return only HIGH impact releases, optionally filtered by country."""
        res = []
        c_filter = country.upper() if country else None
        for ev in events:
            if ev.get("impact_level") == "HIGH":
                if c_filter is None or ev.get("country") == c_filter:
                    res.append(ev)
        return res

    def check_event_blackout_risk(
        self,
        events: List[Dict[str, Any]],
        symbol: str,
        buffer_minutes: int = 30
    ) -> Dict[str, Any]:
        """
        Determines whether a high-impact event is within +/- buffer_minutes of current time.
        If so, signals an EVENT_BLACKOUT risk for the relevant asset.
        """
        clean_sym = symbol.upper()
        # Map symbol to affected country
        affected_countries = ["US"]  # USD impacts all crypto and USD pairs
        if "EUR" in clean_sym:
            affected_countries.append("EU")
        if "GBP" in clean_sym:
            affected_countries.append("GB")
        if "JPY" in clean_sym:
            affected_countries.append("JP")

        now_utc = datetime.now(timezone.utc)
        conflicting_events = []

        for ev in events:
            if ev.get("impact_level") != "HIGH":
                continue
            if ev.get("country") not in affected_countries:
                continue

            # Parse event time
            t_str = ev.get("time_utc")
            if not t_str:
                continue

            try:
                # Expected format: "YYYY-MM-DD HH:MM:SS" or ISO
                if "T" in t_str:
                    ev_dt = datetime.fromisoformat(t_str.replace("Z", "+00:00"))
                else:
                    ev_dt = datetime.strptime(t_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)

                diff_seconds = abs((ev_dt - now_utc).total_seconds())
                if diff_seconds <= (buffer_minutes * 60):
                    conflicting_events.append({
                        "event": ev.get("event"),
                        "country": ev.get("country"),
                        "scheduled_utc": t_str,
                        "minutes_delta": round(diff_seconds / 60.0, 1)
                    })
            except Exception:
                pass

        has_blackout = len(conflicting_events) > 0
        return {
            "has_blackout_risk": has_blackout,
            "policy": "EVENT_BLACKOUT" if has_blackout else "CLEAR",
            "symbol": symbol,
            "buffer_minutes": buffer_minutes,
            "conflicting_events": conflicting_events,
            "recommendation": "SUSPEND_ENTRY" if has_blackout else "STANDARD_OPERATION"
        }

    def get_mock_fixtures(self) -> List[Dict[str, Any]]:
        """Returns offline mock fixtures for testing without network requests or API costs."""
        return self.parse_economic_events(MOCK_FINNHUB_CALENDAR_FIXTURES)

finnhub_calendar_adapter = FinnhubCalendarAdapter()
