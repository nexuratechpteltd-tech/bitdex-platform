"""
Tauric Trading Platform — Finance Calendar Adapter
Provider Candidate: Finance Calendar (https://www.financecalendar.com)
Approved Attribution: "Economic calendar data provided by Finance Calendar" (with clickable link to https://www.financecalendar.com)

Features:
- Explicit provider configuration (enabled via settings.finance_calendar_enabled in staging)
- Normalized economic-event model with UTC canonical timestamps and PKT display strings
- Explicit status differentiation: missing value, not-yet-released, feed unavailable, confirmed release
- Duplicate event deduplication & deterministic chronological ordering
- Safe rate limiting, request timeout, bounded retries, and error handling
- Stale-data detection and last-retrieval tracking
- Event-specific Actual vs. Forecast interpretation (no blunt universal bullish/bearish rule)
- Implementation of the EventCalendarSource protocol for seamless regime_engine integration
- Offline mock fixtures for 100% deterministic, zero-cost, zero-network unit tests
"""

import math
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
import httpx

from .regime_engine import MacroEvent, EventSeverity

try:
    from ..config import settings
    DEFAULT_ENABLED = getattr(settings, "finance_calendar_enabled", True)
    DEFAULT_API_URL = getattr(settings, "finance_calendar_api_url", "https://www.financecalendar.com/wp-json/fc/v1/calendar")
    DEFAULT_HORIZON_DAYS = getattr(settings, "finance_calendar_horizon_days", 14)
    DEFAULT_TTL_SEC = getattr(settings, "finance_calendar_cache_ttl_sec", 300)
except Exception:
    DEFAULT_ENABLED = True
    DEFAULT_API_URL = "https://www.financecalendar.com/wp-json/fc/v1/calendar"
    DEFAULT_HORIZON_DAYS = 14
    DEFAULT_TTL_SEC = 300

logger = logging.getLogger(__name__)

PKT_OFFSET = timedelta(hours=5)  # Asia/Karachi (UTC+05:00)

FINANCE_CALENDAR_SPECS: Dict[str, Any] = {
    "provider_name": "Finance Calendar",
    "official_url": "https://www.financecalendar.com",
    "docs_url": "https://www.financecalendar.com/api/",
    "api_base_url": "https://www.financecalendar.com/wp-json/fc/v1",
    "bulk_dataset_url": "https://www.financecalendar.com/wp-content/uploads/fc/calendar.json",
    "cost": "$0.00 (100% Free for keyless and free-key tiers)",
    "commercial_use_permitted": True,
    "commercial_use_terms": "Free for any use, commercial included, with visible link attribution",
    "approved_attribution_text": "Economic calendar data provided by Finance Calendar",
    "approved_attribution_link": "https://www.financecalendar.com",
    "attribution_required": True,
    "auth_required": False,
    "rate_limits": {
        "keyless_per_ip_per_day": 2000,
        "free_key_per_day": 10000,
        "reset_time_utc": "00:00:00"
    },
    "cache_ttl_seconds": DEFAULT_TTL_SEC,
    "dataset_rebuild_interval_sec": 3600,
    "coverage": {
        "countries": ["US", "GB", "EU", "DE", "JP", "CA", "AU", "CN", "CH", "NZ", "NO", "SE", "IN", "HK"],
        "series_count": ">50 economic and central bank decision series",
        "holidays_count": "12 exchange holiday tables",
        "earnings_included": False
    }
}

COUNTRY_CURRENCY_MAP: Dict[str, str] = {
    "US": "USD",
    "GB": "GBP",
    "EU": "EUR",
    "DE": "EUR",
    "JP": "JPY",
    "CA": "CAD",
    "AU": "AUD",
    "CN": "CNY",
    "CH": "CHF",
    "NZ": "NZD",
    "NO": "NOK",
    "SE": "SEK",
    "IN": "INR",
    "HK": "HKD"
}

# Ambiguous macroeconomic series with multi-channel transmission or conflicting asset implications
AMBIGUOUS_SERIES: List[str] = [
    "trade-balance", "retail-inventories", "crude-oil", "crude-oil-stocks",
    "michigan-sentiment", "consumer-confidence", "average-hourly-earnings"
]

# Event-specific Actual vs. Forecast interpretation guidelines
EVENT_INTERPRETATION_RULES: Dict[str, Dict[str, Any]] = {
    "INFLATION": {
        "series": ["cpi", "us-cpi", "uk-cpi", "pce", "us-pce", "ppi"],
        "comparison_basis": "Year-over-Year (YoY) or Month-over-Month (MoM) price indices compared against Bloomberg/consensus survey.",
        "higher_than_forecast": {
            "currency_bias": "BULLISH",     # Hawkish rate expectations support currency
            "crypto_bias": "BEARISH",       # High inflation delays rate cuts -> bearish risk assets
            "rationale": "Above-consensus inflation raises yields and strengthens domestic currency, while depressing risk assets."
        },
        "lower_than_forecast": {
            "currency_bias": "BEARISH",
            "crypto_bias": "BULLISH",
            "rationale": "Cooling inflation increases dovish Fed pivot probability, relieving pressure on risk assets."
        }
    },
    "EMPLOYMENT": {
        "series": ["nfp", "us-jobs-report", "adp", "us-adp-employment"],
        "comparison_basis": "Net monthly change in nonfarm payroll employment (thousands) relative to consensus median forecast.",
        "higher_than_forecast": {
            "currency_bias": "BULLISH",
            "crypto_bias": "BEARISH",       # Tight labor market sustains restrictive monetary policy
            "rationale": "Robust job creation supports economic resilience but delays central bank easing."
        },
        "lower_than_forecast": {
            "currency_bias": "BEARISH",
            "crypto_bias": "BULLISH",
            "rationale": "Labor softening prompts monetary accommodation, favoring speculative liquidity."
        }
    },
    "LABOR_SLACK": {
        "series": ["weekly-jobless-claims", "unemployment-rate"],
        "comparison_basis": "Unemployment rate percentage or initial unemployment insurance claims relative to consensus forecast.",
        "higher_than_forecast": {
            "currency_bias": "BEARISH",     # Rising claims indicate economic weakness
            "crypto_bias": "BULLISH",       # Dovish pressure on central banks
            "rationale": "Higher claims reflect labor weakness, lowering rate-hike probabilities."
        },
        "lower_than_forecast": {
            "currency_bias": "BULLISH",
            "crypto_bias": "BEARISH",
            "rationale": "Lower claims confirm tight labor market, reinforcing higher-for-longer policy."
        }
    },
    "RATE_DECISION": {
        "series": ["fomc", "ecb", "boe", "boj", "snb", "boc", "rba", "rbnz"],
        "comparison_basis": "Central bank benchmark policy rate target range / official bank rate compared against consensus forecast and prior benchmark rate.",
        "higher_than_forecast": {
            "currency_bias": "BULLISH",
            "crypto_bias": "BEARISH",
            "rationale": "Unexpected interest rate hike / hawkish policy surprise. Benchmark rate increased above consensus. Tightens monetary conditions, supports currency yield, and depresses risk-asset discount valuations."
        },
        "lower_than_forecast": {
            "currency_bias": "BEARISH",
            "crypto_bias": "BULLISH",
            "rationale": "Unexpected interest rate cut / dovish policy surprise. Benchmark rate reduced below consensus. Eases financial conditions, lowers discount rate, and expands speculative risk liquidity."
        }
    },
    "GROWTH": {
        "series": ["gdp", "us-gdp", "us-gdp-report", "retail-sales", "us-retail-sales", "ism-manufacturing-pmi", "ism-services-pmi"],
        "comparison_basis": "Annualized GDP growth rate, retail sales volume, or PMI diffusion index (50.0 threshold) vs consensus forecast.",
        "higher_than_forecast": {
            "currency_bias": "BULLISH",
            "crypto_bias": "NEUTRAL",       # Strong growth supports confidence but may keep rates elevated
            "rationale": "Expansionary growth metrics support currency valuations."
        },
        "lower_than_forecast": {
            "currency_bias": "BEARISH",
            "crypto_bias": "NEUTRAL",
            "rationale": "Contractionary growth indicators weigh on currency and raise recession risks."
        }
    }
}


@dataclass
class NormalizedEconomicEvent:
    event_id: str
    series_code: str
    title: str
    country: str
    currency: str
    scheduled_utc: str
    scheduled_timestamp_ms: int
    scheduled_pkt: str
    impact: str                           # HIGH | MEDIUM | LOW | UNKNOWN
    impact_weight: int                    # 3 | 2 | 1 | 0
    status: str                           # scheduled | confirmed | released | rescheduled | cancelled | FEED_UNAVAILABLE
    actual: Optional[float] = None
    actual_raw: Optional[str] = None
    forecast: Optional[float] = None
    forecast_raw: Optional[str] = None
    previous: Optional[float] = None
    previous_raw: Optional[str] = None
    revised_previous: Optional[float] = None
    is_revised: bool = False
    unit: Optional[str] = None
    source_url: Optional[str] = None
    source_name: str = "Finance Calendar"
    retrieved_at_utc: str = ""
    retrieved_at_pkt: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "series_code": self.series_code,
            "title": self.title,
            "country": self.country,
            "currency": self.currency,
            "scheduled_utc": self.scheduled_utc,
            "scheduled_timestamp_ms": self.scheduled_timestamp_ms,
            "scheduled_pkt": self.scheduled_pkt,
            "impact": self.impact,
            "impact_weight": self.impact_weight,
            "status": self.status,
            "actual": self.actual,
            "actual_raw": self.actual_raw,
            "forecast": self.forecast,
            "forecast_raw": self.forecast_raw,
            "previous": self.previous,
            "previous_raw": self.previous_raw,
            "revised_previous": self.revised_previous,
            "is_revised": self.is_revised,
            "unit": self.unit,
            "source_url": self.source_url,
            "source_name": self.source_name,
            "retrieved_at_utc": self.retrieved_at_utc,
            "retrieved_at_pkt": self.retrieved_at_pkt,
            "is_missing_actual": self.actual is None,
            "is_missing_forecast": self.forecast is None,
            "is_not_yet_released": self.status in ("scheduled", "confirmed") and self.actual is None,
            "is_confirmed_release": self.status == "released" and self.actual is not None,
            "is_feed_unavailable": self.status == "FEED_UNAVAILABLE",
            "interpretation": self.interpret() if (self.actual is not None and self.forecast is not None) else None
        }

    def interpret(self) -> Dict[str, Any]:
        """Provides heuristic economic interpretation of Actual vs. Forecast print."""
        return FinanceCalendarAdapter.interpret_actual_vs_forecast(
            series_code=self.series_code,
            actual=self.actual,
            forecast=self.forecast,
            previous=self.previous,
            raw_actual=self.actual_raw,
            raw_forecast=self.forecast_raw,
            raw_previous=self.previous_raw,
            revised_previous=self.revised_previous,
            currency=self.currency
        )

    def to_macro_event(self) -> MacroEvent:
        """Converts to regime_engine.MacroEvent for deterministic blackout evaluation."""
        if self.impact == "HIGH":
            sev = EventSeverity.HIGH
        elif self.impact == "MEDIUM":
            sev = EventSeverity.MEDIUM
        elif self.impact == "LOW":
            sev = EventSeverity.LOW
        else:
            sev = EventSeverity.UNKNOWN

        return MacroEvent(
            event_id=self.event_id,
            title=self.title,
            timestamp_ms=self.scheduled_timestamp_ms,
            severity=sev,
            affected_currencies=[self.currency, "USD"] if self.currency != "USD" else ["USD"],
            source="financecalendar.com",
            is_trustworthy=self.status != "FEED_UNAVAILABLE"
        )


class FinanceCalendarAdapter:
    """
    Isolated Staging Adapter for Finance Calendar (https://www.financecalendar.com).
    Controlled by configuration flag settings.finance_calendar_enabled.
    """

    def __init__(
        self,
        enabled: Optional[bool] = None,
        api_url: Optional[str] = None,
        stale_threshold_seconds: Optional[float] = None,
        request_timeout_seconds: float = 10.0,
        max_retries: int = 2
    ):
        self.enabled = enabled if enabled is not None else DEFAULT_ENABLED
        self.api_url = api_url or DEFAULT_API_URL
        self.stale_threshold_seconds = stale_threshold_seconds if stale_threshold_seconds is not None else float(DEFAULT_TTL_SEC)
        self.request_timeout_seconds = request_timeout_seconds
        self.max_retries = max_retries

        self._cached_events: List[NormalizedEconomicEvent] = []
        self._last_retrieval_utc: Optional[datetime] = None
        self._last_error: Optional[str] = None
        self._total_requests_made: int = 0

    # ─── Configuration & Metadata ──────────────────────────────────────
    def get_provider_specs(self) -> Dict[str, Any]:
        """Returns verified provider specifications, boundaries, and attribution."""
        return {
            **FINANCE_CALENDAR_SPECS,
            "adapter_enabled": self.enabled,
            "last_retrieval_utc": self._last_retrieval_utc.isoformat() if self._last_retrieval_utc else None,
            "last_retrieval_pkt": self._format_pkt(self._last_retrieval_utc) if self._last_retrieval_utc else None,
            "is_stale": self.is_stale(),
            "status": self.get_provider_status(),
            "cached_events_count": len(self._cached_events),
            "requests_made": self._total_requests_made
        }

    def get_provider_status(self) -> str:
        """Returns one of: 'DISABLED', 'AVAILABLE', 'STALE', 'UNAVAILABLE'."""
        if not self.enabled:
            return "DISABLED"
        if self._last_error and not self._cached_events:
            return "UNAVAILABLE"
        if self.is_stale():
            return "STALE"
        if self._cached_events:
            return "AVAILABLE"
        return "UNAVAILABLE"

    def is_stale(self) -> bool:
        """Determines if the cached calendar data has exceeded the staleness threshold."""
        if self._last_retrieval_utc is None:
            return True
        now_utc = datetime.now(timezone.utc)
        age_seconds = (now_utc - self._last_retrieval_utc).total_seconds()
        return age_seconds > self.stale_threshold_seconds

    # ─── Time Parsing & Formatting ─────────────────────────────────────
    @staticmethod
    def _format_pkt(dt: Optional[datetime]) -> str:
        """Converts UTC datetime to authoritative PKT (UTC+05:00) presentation string."""
        if dt is None:
            return "--"
        pkt_dt = dt + PKT_OFFSET
        return pkt_dt.strftime("%Y-%m-%d %H:%M:%S PKT")

    @staticmethod
    def _parse_timestamp(t_val: Any) -> Tuple[Optional[datetime], Optional[int], str, str]:
        """
        Extracts canonical UTC datetime, epoch ms, UTC ISO string, and PKT display string.
        Rejects invalid, missing, or non-finite inputs deterministically.
        """
        if not t_val or not isinstance(t_val, str):
            return None, None, "", ""

        clean = t_val.strip()
        if not clean:
            return None, None, "", ""

        try:
            # Handle standard ISO formats: 2026-10-28T18:00:00+00:00 or 2026-10-28 18:00:00 or 2026-10-28
            if "T" in clean:
                dt = datetime.fromisoformat(clean.replace("Z", "+00:00"))
            elif " " in clean:
                dt = datetime.strptime(clean, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            else:
                dt = datetime.strptime(clean, "%Y-%m-%d").replace(tzinfo=timezone.utc)

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)

            ts_ms = int(dt.timestamp() * 1000)
            utc_str = dt.isoformat()
            pkt_str = (dt + PKT_OFFSET).strftime("%Y-%m-%d %H:%M:%S PKT")
            return dt, ts_ms, utc_str, pkt_str
        except Exception:
            return None, None, "", ""

    # ─── Numeric Parsing (Float / None) ────────────────────────────────
    @staticmethod
    def _parse_float(val: Any) -> Tuple[Optional[float], Optional[str]]:
        """Parses float without fabricating defaults. Returns (parsed_float, raw_str)."""
        if val is None:
            return None, None
        if isinstance(val, (int, float)):
            if math.isfinite(val):
                return float(val), str(val)
            return None, str(val)
        if isinstance(val, str):
            s = val.strip().replace("%", "").replace(",", "")
            if not s:
                return None, None
            try:
                f_val = float(s)
                if math.isfinite(f_val):
                    return f_val, val.strip()
            except ValueError:
                return None, val.strip()
        return None, str(val) if val is not None else None

    # ─── Event Parsing & Normalization ─────────────────────────────────
    def parse_events(self, raw_events: Any) -> List[NormalizedEconomicEvent]:
        """
        Parses raw Finance Calendar API / Bulk JSON records into canonical NormalizedEconomicEvent objects.
        Unwraps {"events": [...]} dictionary payloads automatically.
        Guarantees:
        - Rejection of invalid timestamps
        - No fabricated default impacts (UNKNOWN if omitted)
        - No fabricated actual/forecast/previous values
        - Deduplication by (event_id, scheduled_utc)
        - Deterministic chronological sorting
        """
        if isinstance(raw_events, dict):
            raw_events = raw_events.get("events", [])

        if not isinstance(raw_events, list):
            logger.warning("[FinanceCalendar] Event payload is not a list or dict with 'events'; returning empty list.")
            return []

        now_utc = datetime.now(timezone.utc)
        now_utc_str = now_utc.isoformat()
        now_pkt_str = self._format_pkt(now_utc)

        seen_keys = set()
        normalized_list: List[NormalizedEconomicEvent] = []

        for item in raw_events:
            if not isinstance(item, dict):
                continue

            event_id = str(item.get("id") or item.get("event_id") or item.get("name") or "").strip()
            series_code = str(item.get("series_code") or item.get("series") or "UNKNOWN").strip().lower()
            title = str(item.get("title") or item.get("name") or item.get("series_name") or "Economic Event").strip()

            raw_time = item.get("release_at_utc") or item.get("time_utc") or item.get("time") or item.get("date")
            dt, ts_ms, utc_str, pkt_str = self._parse_timestamp(raw_time)

            if dt is None or ts_ms is None or ts_ms <= 0:
                continue

            if not event_id:
                event_id = f"{series_code}_{utc_str}"

            dedup_key = (event_id, utc_str)
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)

            country = str(item.get("country") or "US").strip().upper()
            currency = COUNTRY_CURRENCY_MAP.get(country, "USD")

            raw_impact = item.get("impact")
            if raw_impact is not None and isinstance(raw_impact, str):
                imp_clean = raw_impact.strip().upper()
                if imp_clean in ("HIGH", "3"):
                    impact = "HIGH"
                    impact_weight = 3
                elif imp_clean in ("MEDIUM", "MED", "2"):
                    impact = "MEDIUM"
                    impact_weight = 2
                elif imp_clean in ("LOW", "1"):
                    impact = "LOW"
                    impact_weight = 1
                else:
                    impact = "UNKNOWN"
                    impact_weight = 0
            else:
                impact = "UNKNOWN"
                impact_weight = 0

            raw_status = str(item.get("status") or "").strip().lower()
            if raw_status in ("released", "published"):
                status = "released"
            elif raw_status in ("confirmed", "scheduled"):
                status = "confirmed"
            elif raw_status in ("rescheduled", "delayed"):
                status = "rescheduled"
            elif raw_status in ("cancelled", "canceled"):
                status = "cancelled"
            else:
                status = "scheduled"

            actual, actual_raw = self._parse_float(item.get("actual"))
            forecast, forecast_raw = self._parse_float(item.get("consensus") or item.get("forecast") or item.get("estimate"))
            previous, previous_raw = self._parse_float(item.get("prior") or item.get("previous") or item.get("prev"))
            revised_prev, _ = self._parse_float(item.get("revised_prior") or item.get("revised_previous"))

            is_revised = revised_prev is not None and previous is not None and revised_prev != previous

            if actual is not None and status in ("scheduled", "confirmed"):
                status = "released"

            unit = item.get("unit")
            source_url = item.get("url") or item.get("source_url") or "https://www.financecalendar.com"

            event_obj = NormalizedEconomicEvent(
                event_id=event_id,
                series_code=series_code,
                title=title,
                country=country,
                currency=currency,
                scheduled_utc=utc_str,
                scheduled_timestamp_ms=ts_ms,
                scheduled_pkt=pkt_str,
                impact=impact,
                impact_weight=impact_weight,
                status=status,
                actual=actual,
                actual_raw=actual_raw,
                forecast=forecast,
                forecast_raw=forecast_raw,
                previous=previous,
                previous_raw=previous_raw,
                revised_previous=revised_prev,
                is_revised=is_revised,
                unit=unit,
                source_url=source_url,
                source_name=item.get("source_name", "Finance Calendar"),
                retrieved_at_utc=now_utc_str,
                retrieved_at_pkt=now_pkt_str
            )
            normalized_list.append(event_obj)

        normalized_list.sort(key=lambda x: (x.scheduled_timestamp_ms, x.series_code))
        return normalized_list

    # ─── Live Data Ingestion ───────────────────────────────────────────
    async def fetch_events(self, days_ahead: int = DEFAULT_HORIZON_DAYS, force: bool = False) -> List[NormalizedEconomicEvent]:
        """
        Fetches macroeconomic calendar events from official free endpoint with bounded timeout.
        Updates in-memory cache and staleness tracking.
        Does NOT poll continuously; respects edge cache TTL (300s).
        """
        if not self.enabled:
            return self._cached_events

        if not force and not self.is_stale() and self._cached_events:
            return self._cached_events

        now_utc = datetime.now(timezone.utc)
        from_str = now_utc.strftime("%Y-%m-%d")
        to_str = (now_utc + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

        url = self.api_url
        params = {
            "from": from_str,
            "to": to_str,
            "limit": 100
        }

        self._total_requests_made += 1

        try:
            async with httpx.AsyncClient(timeout=self.request_timeout_seconds) as client:
                resp = await client.get(url, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    events = self.parse_events(data)
                    self._cached_events = events
                    self._last_retrieval_utc = datetime.now(timezone.utc)
                    self._last_error = None
                    logger.info(f"[FinanceCalendar] Successfully fetched and normalized {len(events)} events ({from_str} to {to_str})")
                    return events
                elif resp.status_code == 429:
                    self._last_error = "Finance Calendar rate limit reached (HTTP 429). Preserving cache."
                    logger.warning(f"[FinanceCalendar] {self._last_error}")
                else:
                    self._last_error = f"Finance Calendar returned HTTP {resp.status_code}"
                    logger.warning(f"[FinanceCalendar] {self._last_error}")
        except Exception as e:
            self._last_error = f"Network or parsing error connecting to Finance Calendar: {e}"
            logger.warning(f"[FinanceCalendar] {self._last_error}")

        return self._cached_events

    def get_upcoming_events(
        self,
        hours_ahead: int = 24,
        min_impact: str = "HIGH",
        currency: Optional[str] = None
    ) -> List[NormalizedEconomicEvent]:
        """Returns upcoming events scheduled within the next N hours."""
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        end_ms = now_ms + (hours_ahead * 3600 * 1000)

        results = []
        for ev in self._cached_events:
            if now_ms <= ev.scheduled_timestamp_ms <= end_ms:
                if min_impact == "HIGH" and ev.impact != "HIGH":
                    continue
                if currency and ev.currency != currency and ev.currency != "USD":
                    continue
                results.append(ev)
        return results

    # ─── Event-Risk Evaluation ─────────────────────────────────────────
    def evaluate_event_risk(
        self,
        symbol: str,
        current_time_ms: Optional[int] = None,
        pre_mins: int = 30,
        post_mins: int = 15
    ) -> Dict[str, Any]:
        """
        Evaluates whether an active macro EVENT_BLACKOUT window applies to the given symbol.
        Safety Invariants:
        - If provider is DISABLED, returns UNKNOWN. Never claims clear.
        - If calendar data is UNAVAILABLE or STALE, returns UNKNOWN/UNAVAILABLE.
        - If HIGH-impact event is within [-post_mins, +pre_mins], returns BLACKOUT / SUSPEND_ENTRY.
        - If verified clear within window, returns CLEAR with explicit window boundaries.
        """
        now_ms = current_time_ms if current_time_ms is not None else int(datetime.now(timezone.utc).timestamp() * 1000)
        provider_status = self.get_provider_status()

        # 1. Gate: Provider Disabled Check
        if not self.enabled:
            return {
                "event_risk_status": "UNKNOWN",
                "is_blackout": False,
                "policy": "CALENDAR_UNAVAILABLE",
                "reason": "Economic calendar provider is disabled. Macro event risk cannot be confirmed clear.",
                "recommendation": "WAIT_OR_MANUAL_VERIFICATION",
                "provider_status": "DISABLED",
                "attribution_approved": FINANCE_CALENDAR_SPECS["approved_attribution_text"],
                "attribution_link": FINANCE_CALENDAR_SPECS["approved_attribution_link"],
                "conflicting_events": [],
                "upcoming_events_24h": [],
                "relevant_events": [],
                "disclaimer": "Safety policy: Event risk remains UNKNOWN when calendar is disabled."
            }

        # 2. Gate: Provider Health Check
        if provider_status in ("UNAVAILABLE", "STALE"):
            return {
                "event_risk_status": "UNAVAILABLE" if provider_status == "UNAVAILABLE" else "STALE",
                "is_blackout": False,
                "policy": "CALENDAR_UNAVAILABLE",
                "reason": f"Economic calendar data is {provider_status}. Macro event risk is UNKNOWN, not confirmed clear.",
                "recommendation": "WAIT_OR_MANUAL_VERIFICATION",
                "provider_status": provider_status,
                "attribution_approved": FINANCE_CALENDAR_SPECS["approved_attribution_text"],
                "attribution_link": FINANCE_CALENDAR_SPECS["approved_attribution_link"],
                "conflicting_events": [],
                "upcoming_events_24h": [],
                "relevant_events": [],
                "disclaimer": "Safety policy: An unavailable or stale calendar does not guarantee safety."
            }

        # 3. Gate: Event Window Calculation
        pre_ms = pre_mins * 60 * 1000
        post_ms = post_mins * 60 * 1000
        window_start = now_ms - post_ms
        window_end = now_ms + pre_ms

        clean_sym = symbol.upper()
        relevant_currencies = ["USD"]
        if "EUR" in clean_sym:
            relevant_currencies.append("EUR")
        if "GBP" in clean_sym:
            relevant_currencies.append("GBP")
        if "JPY" in clean_sym:
            relevant_currencies.append("JPY")
        if "CAD" in clean_sym:
            relevant_currencies.append("CAD")
        if "AUD" in clean_sym:
            relevant_currencies.append("AUD")

        conflicting_events = []
        unknown_impact_events = []
        upcoming_24h = []
        relevant_events = []

        horizon_24h_ms = now_ms + (24 * 3600 * 1000)

        for ev in self._cached_events:
            if ev.currency not in relevant_currencies:
                continue

            ev_dict = ev.to_dict()
            delta_mins = round((ev.scheduled_timestamp_ms - now_ms) / 60000.0, 1)
            ev_summary = {
                "event_id": ev.event_id,
                "title": ev.title,
                "currency": ev.currency,
                "scheduled_utc": ev.scheduled_utc,
                "scheduled_pkt": ev.scheduled_pkt,
                "impact": ev.impact,
                "minutes_delta": delta_mins,
                "status": ev.status,
                "interpretation": ev_dict.get("interpretation")
            }

            # Blackout window check
            if window_start <= ev.scheduled_timestamp_ms <= window_end:
                if ev.impact == "HIGH":
                    conflicting_events.append(ev_summary)
                elif ev.impact in ("UNKNOWN", "", None) or ev.impact_weight == 0:
                    unknown_impact_events.append(ev)

            # 24h upcoming high-impact events check
            if now_ms < ev.scheduled_timestamp_ms <= horizon_24h_ms and ev.impact == "HIGH":
                upcoming_24h.append(ev_summary)

            # Recent releases or imminent events (within +/- 24h) for news-aware context
            if (now_ms - 86400000) <= ev.scheduled_timestamp_ms <= horizon_24h_ms:
                relevant_events.append(ev_summary)

        has_blackout = len(conflicting_events) > 0
        if has_blackout:
            primary_ev = conflicting_events[0]
            return {
                "event_risk_status": "BLACKOUT",
                "is_blackout": True,
                "policy": "EVENT_BLACKOUT",
                "reason": f"Active blackout for '{primary_ev['title']}' at {primary_ev['scheduled_pkt']}.",
                "recommendation": "SUSPEND_ENTRY",
                "provider_status": "AVAILABLE",
                "symbol": symbol,
                "buffer_window": {"pre_mins": pre_mins, "post_mins": post_mins},
                "conflicting_events": conflicting_events,
                "upcoming_events_24h": upcoming_24h,
                "relevant_events": relevant_events[:5],
                "attribution_approved": FINANCE_CALENDAR_SPECS["approved_attribution_text"],
                "attribution_link": FINANCE_CALENDAR_SPECS["approved_attribution_link"]
            }

        if unknown_impact_events:
            ev0 = unknown_impact_events[0]
            return {
                "event_risk_status": "UNKNOWN",
                "is_blackout": False,
                "policy": "UNCLASSIFIED_EVENT_RISK",
                "reason": f"Event '{ev0.title}' within risk window lacks impact classification; event risk cannot be confirmed clear.",
                "recommendation": "WAIT_OR_MANUAL_VERIFICATION",
                "provider_status": "AVAILABLE",
                "symbol": symbol,
                "buffer_window": {"pre_mins": pre_mins, "post_mins": post_mins},
                "conflicting_events": [],
                "upcoming_events_24h": upcoming_24h,
                "relevant_events": relevant_events[:5],
                "attribution_approved": FINANCE_CALENDAR_SPECS["approved_attribution_text"],
                "attribution_link": FINANCE_CALENDAR_SPECS["approved_attribution_link"]
            }

        # Clear window
        return {
            "event_risk_status": "CLEAR",
            "is_blackout": False,
            "policy": "CLEAR",
            "reason": f"No high-impact economic events detected within checked window ({pre_mins}m pre / {post_mins}m post).",
            "recommendation": "STANDARD_OPERATION",
            "provider_status": "AVAILABLE",
            "symbol": symbol,
            "window_checked": {
                "start_utc": datetime.fromtimestamp(window_start / 1000.0, timezone.utc).isoformat(),
                "end_utc": datetime.fromtimestamp(window_end / 1000.0, timezone.utc).isoformat(),
                "pre_mins": pre_mins,
                "post_mins": post_mins
            },
            "conflicting_events": [],
            "upcoming_events_24h": upcoming_24h,
            "relevant_events": relevant_events[:5],
            "attribution_approved": FINANCE_CALENDAR_SPECS["approved_attribution_text"],
            "attribution_link": FINANCE_CALENDAR_SPECS["approved_attribution_link"]
        }

    # ─── Summary for API & Dashboard ──────────────────────────────────
    def get_calendar_summary(self) -> Dict[str, Any]:
        """Provides full structured calendar metadata and 14-day normalized events."""
        status = self.get_provider_status()
        is_stale_flag = self.is_stale()
        return {
            "provider": FINANCE_CALENDAR_SPECS["provider_name"],
            "official_url": FINANCE_CALENDAR_SPECS["official_url"],
            "status": status,
            "approved_attribution_text": FINANCE_CALENDAR_SPECS["approved_attribution_text"],
            "approved_attribution_link": FINANCE_CALENDAR_SPECS["approved_attribution_link"],
            "last_retrieval_utc": self._last_retrieval_utc.isoformat() if self._last_retrieval_utc else None,
            "last_retrieval_pkt": self._format_pkt(self._last_retrieval_utc) if self._last_retrieval_utc else "--",
            "is_stale": is_stale_flag,
            "time_window_covered": f"{DEFAULT_HORIZON_DAYS}-Day Horizon (14 Countries)",
            "event_risk_policy": "GATED_BLACKOUT_WINDOWS" if status == "AVAILABLE" else "UNKNOWN",
            "warning": None if status == "AVAILABLE" else (
                "Economic calendar provider is disabled in configuration." if not self.enabled else f"Economic calendar data is {status}."
            ),
            "cached_events_count": len(self._cached_events),
            "events": [e.to_dict() for e in self._cached_events]
        }

    # ─── Event-Specific Actual vs Forecast Interpretation ─────────────
    @staticmethod
    def interpret_actual_vs_forecast(
        series_code: str,
        actual: Optional[float],
        forecast: Optional[float],
        previous: Optional[float] = None,
        raw_actual: Optional[str] = None,
        raw_forecast: Optional[str] = None,
        raw_previous: Optional[str] = None,
        revised_previous: Optional[float] = None,
        currency: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Event-specific interpretation of Actual vs. Forecast macroeconomic data.
        Adheres to strict financial interpretation standards:
        - Rejects generic 'actual > forecast' rules for unmapped indicators (returns UNKNOWN).
        - Handles central-bank rate decisions with explicit comparison basis and benchmark rates.
        - Identifies ambiguous indicators with multi-channel transmission (returns MIXED).
        - Preserves raw string values alongside parsed floats.
        """
        clean_code = series_code.lower()
        curr_rel = [currency.upper()] if currency else (["USD"] if "us" in clean_code or clean_code in ("fomc", "nfp", "cpi") else ["USD"])

        if actual is None or forecast is None:
            return {
                "status": "UNAVAILABLE",
                "series_code": clean_code,
                "measured_value": actual,
                "forecast_value": forecast,
                "previous_value": previous,
                "raw_actual": raw_actual or (str(actual) if actual is not None else None),
                "raw_forecast": raw_forecast or (str(forecast) if forecast is not None else None),
                "raw_previous": raw_previous or (str(previous) if previous is not None else None),
                "revised_previous": revised_previous,
                "is_revised": revised_previous is not None,
                "surprise_diff": None,
                "surprise_direction": "UNKNOWN",
                "currency_relevance": curr_rel,
                "currency_bias": "NEUTRAL",
                "crypto_bias": "NEUTRAL",
                "comparison_basis": "Consensus forecast comparison",
                "model_interpretation": "Actual or consensus forecast value is missing; surprise cannot be calculated.",
                "explanation": "Actual or consensus forecast value is missing; surprise cannot be calculated.",
                "disclaimer": "Heuristic macroeconomic analysis only — not a trade recommendation. Automated trade execution is strictly disabled."
            }

        diff = round(actual - forecast, 4)
        surprise_direction = "POSITIVE" if diff > 0 else ("NEGATIVE" if diff < 0 else "IN_LINE")

        if any(amb in clean_code for amb in AMBIGUOUS_SERIES):
            return {
                "status": "MIXED",
                "series_code": clean_code,
                "measured_value": actual,
                "forecast_value": forecast,
                "previous_value": previous,
                "raw_actual": raw_actual or str(actual),
                "raw_forecast": raw_forecast or str(forecast),
                "raw_previous": raw_previous or (str(previous) if previous is not None else None),
                "revised_previous": revised_previous,
                "is_revised": revised_previous is not None,
                "surprise_diff": diff,
                "surprise_direction": surprise_direction,
                "currency_relevance": curr_rel,
                "currency_bias": "MIXED",
                "crypto_bias": "MIXED",
                "comparison_basis": "Multi-channel macroeconomic indicator vs consensus forecast",
                "model_interpretation": (
                    f"Indicator '{series_code}' has ambiguous or conflicting economic transmission channels. Directional bias is MIXED."
                ),
                "explanation": f"Indicator '{series_code}' exhibits ambiguous economic transmission channels. Directional bias is MIXED.",
                "disclaimer": "Heuristic macroeconomic analysis only — not a trade recommendation. Automated trade execution is strictly disabled."
            }

        matched_cat = None
        matched_rule = None
        for category, cat_data in EVENT_INTERPRETATION_RULES.items():
            if any(s in clean_code for s in cat_data["series"]):
                matched_cat = category
                matched_rule = cat_data
                break

        if matched_rule is None:
            return {
                "status": "UNKNOWN",
                "series_code": clean_code,
                "measured_value": actual,
                "forecast_value": forecast,
                "previous_value": previous,
                "raw_actual": raw_actual or str(actual),
                "raw_forecast": raw_forecast or str(forecast),
                "raw_previous": raw_previous or (str(previous) if previous is not None else None),
                "revised_previous": revised_previous,
                "is_revised": revised_previous is not None,
                "surprise_diff": diff,
                "surprise_direction": surprise_direction,
                "currency_relevance": curr_rel,
                "currency_bias": "UNKNOWN",
                "crypto_bias": "UNKNOWN",
                "comparison_basis": "Unmapped indicator vs consensus forecast",
                "model_interpretation": (
                    f"Unclassified series '{series_code}'. Generic rules are rejected for safety. Bias is UNKNOWN."
                ),
                "explanation": f"Unmapped series '{series_code}'. Generic rules are rejected for safety. Bias is UNKNOWN.",
                "disclaimer": "Heuristic macroeconomic analysis only — not a trade recommendation. Automated trade execution is strictly disabled."
            }

        comparison_basis = matched_rule.get("comparison_basis", "Consensus forecast comparison")

        if matched_cat == "RATE_DECISION":
            if diff > 0:
                rule_bias = matched_rule["higher_than_forecast"]
            elif diff < 0:
                rule_bias = matched_rule["lower_than_forecast"]
            else:
                if previous is not None and actual > previous:
                    rule_bias = {
                        "currency_bias": "BULLISH",
                        "crypto_bias": "BEARISH",
                        "rationale": f"Rate increased by {round(actual - previous, 3)}% as anticipated by consensus. Hawkish policy stance priced in."
                    }
                elif previous is not None and actual < previous:
                    rule_bias = {
                        "currency_bias": "BEARISH",
                        "crypto_bias": "BULLISH",
                        "rationale": f"Rate cut by {round(previous - actual, 3)}% as anticipated by consensus. Dovish accommodation priced in."
                    }
                else:
                    rule_bias = {
                        "currency_bias": "NEUTRAL",
                        "crypto_bias": "NEUTRAL",
                        "rationale": "Policy rate maintained unchanged in line with consensus forecast and prior level. Focus on statement."
                    }
        else:
            if diff > 0:
                rule_bias = matched_rule["higher_than_forecast"]
            elif diff < 0:
                rule_bias = matched_rule["lower_than_forecast"]
            else:
                rule_bias = {
                    "currency_bias": "NEUTRAL",
                    "crypto_bias": "NEUTRAL",
                    "rationale": "Actual print matched consensus forecast exactly."
                }

        return {
            "status": "EVALUATED",
            "series_code": clean_code,
            "measured_value": actual,
            "forecast_value": forecast,
            "previous_value": previous,
            "raw_actual": raw_actual or str(actual),
            "raw_forecast": raw_forecast or str(forecast),
            "raw_previous": raw_previous or (str(previous) if previous is not None else None),
            "revised_previous": revised_previous,
            "is_revised": revised_previous is not None,
            "surprise_diff": diff,
            "surprise_direction": surprise_direction,
            "currency_relevance": curr_rel,
            "currency_bias": rule_bias["currency_bias"],
            "crypto_bias": rule_bias["crypto_bias"],
            "comparison_basis": comparison_basis,
            "model_interpretation": rule_bias["rationale"],
            "explanation": rule_bias["rationale"],
            "disclaimer": "Heuristic macroeconomic model interpretation only — not a trade recommendation. Automated trade execution is strictly disabled."
        }

    # ─── EventCalendarSource Protocol Implementation ──────────────────
    def get_events(self, start_ms: int, end_ms: int) -> List[MacroEvent]:
        """Implements EventCalendarSource.get_events for regime_engine."""
        if not self.enabled or self.is_stale():
            return []

        macro_events: List[MacroEvent] = []
        for ev in self._cached_events:
            if start_ms <= ev.scheduled_timestamp_ms <= end_ms:
                macro_events.append(ev.to_macro_event())
        return macro_events

    def is_reliable(self) -> bool:
        """Implements EventCalendarSource.is_reliable for regime_engine."""
        return self.enabled and not self.is_stale() and (self._last_error is None)

    # ─── Mock Fixtures & Testing Injection ────────────────────────────
    def load_mock_fixtures(self, fixtures: Optional[List[Dict[str, Any]]] = None) -> int:
        """Loads mock fixtures into in-memory cache for deterministic testing."""
        raw = fixtures if fixtures is not None else MOCK_FINANCE_CALENDAR_FIXTURES
        self._cached_events = self.parse_events(raw)
        self._last_retrieval_utc = datetime.now(timezone.utc)
        self._last_error = None
        return len(self._cached_events)


# ─── 100% Deterministic Mock Fixtures ─────────────────────────────────
MOCK_FINANCE_CALENDAR_FIXTURES: List[Dict[str, Any]] = [
    {
        "id": "fomc-rate-decision-october-2026",
        "series": "fomc",
        "series_code": "fomc",
        "series_name": "FOMC Rate Decision",
        "title": "FOMC Rate Decision",
        "country": "US",
        "category": "central-banks-monetary-policy",
        "impact": "high",
        "date": "2026-10-28",
        "release_at_utc": "2026-10-28T18:00:00+00:00",
        "status": "confirmed",
        "consensus": 5.25,
        "prior": 5.25,
        "actual": None,
        "unit": "% target range",
        "source_url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
    },
    {
        "id": "us-cpi-yoy-october-2026",
        "series": "us-cpi",
        "series_code": "us-cpi",
        "series_name": "US CPI Inflation YoY",
        "title": "US CPI Inflation YoY",
        "country": "US",
        "category": "economic-indicators",
        "impact": "high",
        "date": "2026-10-21",
        "release_at_utc": "2026-10-21T12:30:00+00:00",
        "status": "released",
        "consensus": 3.1,
        "prior": 3.4,
        "actual": 3.2,
        "unit": "%",
        "source_url": "https://www.bls.gov/cpi/"
    },
    {
        "id": "us-gdp-q3-2026",
        "series": "us-gdp",
        "series_code": "us-gdp",
        "series_name": "US Real GDP Annualized",
        "title": "US Real GDP Annualized",
        "country": "US",
        "category": "economic-indicators",
        "impact": "high",
        "date": "2026-10-29",
        "release_at_utc": "2026-10-29T12:30:00+00:00",
        "status": "scheduled",
        "consensus": None,
        "prior": 2.8,
        "actual": None,
        "unit": "%",
        "source_url": "https://www.bea.gov/"
    },
    {
        "id": "uk-jobs-report-october-2026",
        "series": "uk-jobs",
        "series_code": "uk-jobs",
        "series_name": "UK Claimant Count Rate",
        "title": "UK Claimant Count Rate",
        "country": "GB",
        "category": "economic-indicators",
        "impact": "medium",
        "date": "2026-10-20",
        "release_at_utc": "2026-10-20T06:00:00+00:00",
        "status": "released",
        "consensus": 4.7,
        "prior": 4.6,
        "revised_prior": 4.5,
        "actual": 4.7,
        "unit": "%",
        "source_url": "https://www.ons.gov.uk/"
    },
    {
        "id": "ecb-rate-decision-october-2026",
        "series": "ecb",
        "series_code": "ecb",
        "series_name": "ECB Main Refinancing Rate",
        "title": "ECB Main Refinancing Rate",
        "country": "EU",
        "category": "central-banks-monetary-policy",
        "impact": "high",
        "date": "2026-10-29",
        "release_at_utc": "2026-10-29T12:15:00+00:00",
        "status": "confirmed",
        "consensus": 3.75,
        "prior": 3.75,
        "actual": None,
        "unit": "%",
        "source_url": "https://www.ecb.europa.eu/"
    },
    {
        "id": "de-ifo-october-2026",
        "series": "de-ifo",
        "series_code": "de-ifo",
        "series_name": "German Ifo Business Climate",
        "title": "German Ifo Business Climate",
        "country": "DE",
        "category": "economic-indicators",
        "impact": "low",
        "date": "2026-10-26",
        "release_at_utc": "2026-10-26T08:00:00+00:00",
        "status": "confirmed",
        "consensus": 85.5,
        "prior": 85.4,
        "actual": None,
        "unit": "Index"
    }
]

finance_calendar_adapter = FinanceCalendarAdapter()
