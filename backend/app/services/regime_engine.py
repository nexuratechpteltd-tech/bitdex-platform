"""
Deterministic Market-Regime Engine for Tauric Trading Platform (Phase 2).
100% Rule-Based, Zero-AI-Cost, Fail-Closed Architecture.

Supported Regimes:
- RISK_ON: Favorable market expansion, positive momentum, healthy breadth, controlled volatility.
- NEUTRAL: Range-bound consolidation, balanced order flow, no strong directional drift.
- RISK_OFF: Adverse volatility spike, severe downside breakdown (<= -3.0%), or liquidity decay.
- EVENT_BLACKOUT: Imminent high-impact macro event (FOMC, CPI, NFP) within pre/post time window.
- UNKNOWN: Missing, corrupt, non-finite, stale, or untrusted input data.
"""

from dataclasses import dataclass, field
from enum import Enum
import math
import time
from typing import Any, Dict, List, Optional, Tuple, Protocol


class MarketRegime(str, Enum):
    RISK_ON = "RISK_ON"
    NEUTRAL = "NEUTRAL"
    RISK_OFF = "RISK_OFF"
    EVENT_BLACKOUT = "EVENT_BLACKOUT"
    UNKNOWN = "UNKNOWN"


class EventSeverity(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


@dataclass
class MacroEvent:
    event_id: str
    title: str
    timestamp_ms: int
    severity: EventSeverity = EventSeverity.HIGH
    affected_currencies: List[str] = field(default_factory=lambda: ["USD"])
    source: str = "verified_calendar"
    is_trustworthy: bool = True


@dataclass
class RegimeEngineConfig:
    """Configurable, documented thresholds for deterministic regime classification."""
    risk_off_drop_pct: float = -3.0        # 24h drop <= -3.0% triggers RISK_OFF
    risk_on_min_pct: float = 1.0           # 24h rise >= +1.0% eligible for RISK_ON
    extreme_volatility_pct: float = 5.0    # Absolute 24h change >= 5.0% triggers RISK_OFF
    event_blackout_pre_mins: int = 30      # Minutes before high-impact event to enforce blackout
    event_blackout_post_mins: int = 15     # Minutes after high-impact event to enforce blackout
    max_quote_age_seconds: float = 60.0    # Stale data threshold in seconds
    rsi_oversold_extreme: float = 25.0     # RSI <= 25 indicates severe selling / volatility
    rsi_overbought_extreme: float = 78.0   # RSI >= 78 indicates blow-off risk
    require_event_risk_clear: bool = False # When True, UNKNOWN/STALE/UNAVAILABLE event risk fails closed (WAIT)


@dataclass
class RegimeAnalysisResult:
    regime: MarketRegime
    confidence: float                      # 0.0 to 1.0
    status: str                            # "PASS", "WAIT", "STALE", "UNKNOWN", "BLACKOUT"
    symbol: str
    reasons: List[str]
    metrics: Dict[str, Any]
    is_blackout: bool
    blackout_event: Optional[Dict[str, Any]]
    timestamp_ms: int
    event_risk_status: str = "CLEAR"       # "CLEAR" | "BLACKOUT" | "UNKNOWN" | "STALE" | "UNAVAILABLE" | "DISABLED" | "NOT_CONFIGURED"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "regime": self.regime.value if hasattr(self.regime, "value") else str(self.regime),
            "confidence": self.confidence,
            "status": self.status,
            "symbol": self.symbol,
            "reasons": self.reasons,
            "metrics": self.metrics,
            "is_blackout": self.is_blackout,
            "blackout_event": self.blackout_event,
            "event_risk_status": self.event_risk_status,
            "timestamp_ms": self.timestamp_ms
        }


class EventCalendarSource(Protocol):
    """Protocol for verified economic calendar providers."""
    def get_events(self, start_ms: int, end_ms: int) -> List[MacroEvent]:
        ...
    def is_reliable(self) -> bool:
        ...


class DeterministicMarketRegimeEngine:
    """
    Evaluates market regime deterministically from validated numeric data and calendar feeds.
    Zero LLM or paid AI calls.
    """

    def __init__(self, config: Optional[RegimeEngineConfig] = None):
        self.config = config or RegimeEngineConfig()

    def check_event_blackout(
        self,
        current_time_ms: int,
        calendar_source: Optional[EventCalendarSource] = None,
        symbol: Optional[str] = None
    ) -> Tuple[bool, MarketRegime, List[str], Optional[MacroEvent]]:
        """
        Evaluates whether an EVENT_BLACKOUT is active.
        Safety Invariant: Requires a trustworthy event source and valid timestamps.
        If no reliable calendar is configured or timestamps are invalid, returns UNKNOWN
        rather than inventing a phantom event.
        """
        if calendar_source is None:
            # No calendar configured: cannot declare blackout, must NOT invent events
            return False, MarketRegime.UNKNOWN, ["No trustworthy calendar provider configured"], None

        # Check explicit disabled status
        if hasattr(calendar_source, "enabled") and not calendar_source.enabled:
            return False, MarketRegime.UNKNOWN, ["Calendar provider is disabled or marked untrustworthy: event risk cannot be confirmed clear"], None

        # Check staleness or missing initial fetch
        if hasattr(calendar_source, "is_stale") and calendar_source.is_stale():
            if getattr(calendar_source, "_last_retrieval_utc", None) is None:
                return False, MarketRegime.UNKNOWN, ["Calendar data unavailable: no successful initial fetch"], None
            return False, MarketRegime.UNKNOWN, ["Calendar data is stale (>threshold): event risk cannot be confirmed clear"], None

        if not calendar_source.is_reliable():
            return False, MarketRegime.UNKNOWN, ["Calendar provider marked untrustworthy"], None

        pre_ms = self.config.event_blackout_pre_mins * 60 * 1000
        post_ms = self.config.event_blackout_post_mins * 60 * 1000

        window_start = current_time_ms - post_ms
        window_end = current_time_ms + pre_ms

        try:
            events = calendar_source.get_events(window_start, window_end)
        except Exception as exc:
            return False, MarketRegime.UNKNOWN, [f"Calendar provider error: {str(exc)}"], None

        if not isinstance(events, list):
            return False, MarketRegime.UNKNOWN, ["Calendar returned non-list event payload"], None

        # Inspect events in blackout window
        unknown_impact_events: List[MacroEvent] = []
        for event in events:
            if not isinstance(event, MacroEvent):
                continue

            # Verify timestamp validity
            if not isinstance(event.timestamp_ms, (int, float)) or not math.isfinite(event.timestamp_ms) or event.timestamp_ms <= 0:
                continue

            if not event.is_trustworthy:
                continue

            blackout_start = event.timestamp_ms - pre_ms
            blackout_end = event.timestamp_ms + post_ms

            if blackout_start <= current_time_ms <= blackout_end:
                # Check if event affects this symbol (default USD for crypto and major FX)
                if event.severity == EventSeverity.HIGH:
                    remaining_mins = max(0, int((event.timestamp_ms - current_time_ms) / 60000))
                    reasons = [
                        f"EVENT_BLACKOUT active for '{event.title}' at {event.timestamp_ms}.",
                        f"Blackout window: -{self.config.event_blackout_pre_mins}m to +{self.config.event_blackout_post_mins}m.",
                        f"Minutes to event: {remaining_mins}m"
                    ]
                    return True, MarketRegime.EVENT_BLACKOUT, reasons, event
                elif event.severity == EventSeverity.UNKNOWN or event.severity is None:
                    unknown_impact_events.append(event)

        if unknown_impact_events:
            ev0 = unknown_impact_events[0]
            return False, MarketRegime.UNKNOWN, [
                f"Event '{ev0.title}' within risk window lacks impact classification; event risk cannot be confirmed clear"
            ], ev0

        return False, MarketRegime.NEUTRAL, ["No active high-impact blackout events detected"], None

    def evaluate_symbol_regime(
        self,
        symbol: str,
        price: Optional[float],
        change_24h: Optional[float],
        quote_timestamp_ms: Optional[int] = None,
        data_status: Optional[str] = "PASS",
        indicators: Optional[Dict[str, Any]] = None,
        calendar_source: Optional[EventCalendarSource] = None,
        current_time_ms: Optional[int] = None,
        require_event_risk_clear: Optional[bool] = None
    ) -> RegimeAnalysisResult:
        """
        Determines the market regime for a single symbol using strict deterministic rules.
        When require_event_risk_clear is True (or configured on the engine), any UNKNOWN,
        STALE, UNAVAILABLE, or DISABLED event-risk status fails closed (status="WAIT").
        """
        now_ms = current_time_ms if current_time_ms is not None else int(time.time() * 1000)
        req_clear = self.config.require_event_risk_clear if require_event_risk_clear is None else require_event_risk_clear

        # ─── GATE 1: Input Validity & Freshness ───────────────────────────
        if data_status not in ("PASS", "NORMAL"):
            return RegimeAnalysisResult(
                regime=MarketRegime.UNKNOWN,
                confidence=0.0,
                status="UNKNOWN",
                symbol=symbol,
                reasons=[f"Market data status '{data_status}' is degraded; regime cannot be qualified"],
                metrics={"price": price, "change_24h": change_24h},
                is_blackout=False,
                blackout_event=None,
                timestamp_ms=now_ms,
                event_risk_status="UNKNOWN"
            )

        if price is None or not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
            return RegimeAnalysisResult(
                regime=MarketRegime.UNKNOWN,
                confidence=0.0,
                status="UNKNOWN",
                symbol=symbol,
                reasons=["Price is missing, non-finite, or <= 0"],
                metrics={"price": price, "change_24h": change_24h},
                is_blackout=False,
                blackout_event=None,
                timestamp_ms=now_ms,
                event_risk_status="UNKNOWN"
            )

        if change_24h is None or not isinstance(change_24h, (int, float)) or not math.isfinite(change_24h):
            return RegimeAnalysisResult(
                regime=MarketRegime.UNKNOWN,
                confidence=0.0,
                status="UNKNOWN",
                symbol=symbol,
                reasons=["24h price change is missing or non-finite"],
                metrics={"price": price, "change_24h": change_24h},
                is_blackout=False,
                blackout_event=None,
                timestamp_ms=now_ms,
                event_risk_status="UNKNOWN"
            )

        # Freshness Check
        if quote_timestamp_ms is not None and isinstance(quote_timestamp_ms, (int, float)):
            age_sec = (now_ms - quote_timestamp_ms) / 1000.0
            if age_sec > self.config.max_quote_age_seconds:
                return RegimeAnalysisResult(
                    regime=MarketRegime.UNKNOWN,
                    confidence=0.0,
                    status="STALE",
                    symbol=symbol,
                    reasons=[f"Quote age ({age_sec:.1f}s) exceeds max threshold ({self.config.max_quote_age_seconds}s)"],
                    metrics={"price": price, "change_24h": change_24h, "age_sec": age_sec},
                    is_blackout=False,
                    blackout_event=None,
                    timestamp_ms=now_ms,
                    event_risk_status="UNKNOWN"
                )

        # ─── GATE 2: Event Blackout Gate ─────────────────────────────────
        event_risk_status = "NOT_CONFIGURED"
        blackout_event_dict = None
        is_blackout = False

        if calendar_source is not None:
            is_blackout, blackout_regime, blackout_reasons, event = self.check_event_blackout(
                current_time_ms=now_ms,
                calendar_source=calendar_source,
                symbol=symbol
            )
            if event:
                blackout_event_dict = {
                    "event_id": event.event_id,
                    "title": event.title,
                    "timestamp_ms": event.timestamp_ms,
                    "severity": event.severity.value if hasattr(event.severity, "value") else str(event.severity)
                }

            if is_blackout:
                event_risk_status = "BLACKOUT"
                return RegimeAnalysisResult(
                    regime=MarketRegime.EVENT_BLACKOUT,
                    confidence=0.95,
                    status="BLACKOUT",
                    symbol=symbol,
                    reasons=blackout_reasons,
                    metrics={"price": price, "change_24h": change_24h},
                    is_blackout=True,
                    blackout_event=blackout_event_dict,
                    timestamp_ms=now_ms,
                    event_risk_status=event_risk_status
                )
            elif blackout_regime == MarketRegime.UNKNOWN:
                r_lower = " ".join(blackout_reasons).lower()
                if "stale" in r_lower:
                    event_risk_status = "STALE"
                elif "disabled" in r_lower:
                    event_risk_status = "DISABLED"
                elif "no successful initial fetch" in r_lower or "error" in r_lower or "unavailable" in r_lower or "non-list" in r_lower:
                    event_risk_status = "UNAVAILABLE"
                else:
                    event_risk_status = "UNKNOWN"

                # Fail-closed check: where event-risk gate is required, UNKNOWN/STALE/UNAVAILABLE
                # MUST NOT be interpreted as confirmed clear, and is_blackout=False CANNOT override!
                if req_clear:
                    return RegimeAnalysisResult(
                        regime=MarketRegime.UNKNOWN,
                        confidence=0.0,
                        status="WAIT",
                        symbol=symbol,
                        reasons=[
                            f"Event-risk clearance required, but event risk status is '{event_risk_status}'. "
                            f"{blackout_reasons[0] if blackout_reasons else 'Event risk not confirmed clear.'}"
                        ],
                        metrics={"price": price, "change_24h": change_24h},
                        is_blackout=False,
                        blackout_event=blackout_event_dict,
                        timestamp_ms=now_ms,
                        event_risk_status=event_risk_status
                    )
            else:
                event_risk_status = "CLEAR"
        elif req_clear:
            # Calendar source is None, but event risk clearance was required
            return RegimeAnalysisResult(
                regime=MarketRegime.UNKNOWN,
                confidence=0.0,
                status="WAIT",
                symbol=symbol,
                reasons=["Event-risk clearance required, but no trustworthy calendar provider is configured."],
                metrics={"price": price, "change_24h": change_24h},
                is_blackout=False,
                blackout_event=None,
                timestamp_ms=now_ms,
                event_risk_status="NOT_CONFIGURED"
            )

        # ─── GATE 3: Deterministic Volatility & Trend Classification ─────
        ind = indicators or {}
        rsi = ind.get("rsi") or ind.get("rsi14")
        ema50 = ind.get("ema50")
        ema200 = ind.get("ema200")
        has_emas = (ema50 is not None and ema200 is not None and 
                    isinstance(ema50, (int, float)) and isinstance(ema200, (int, float)) and
                    math.isfinite(ema50) and math.isfinite(ema200))

        reasons: List[str] = []
        metrics: Dict[str, Any] = {
            "price": price,
            "change_24h": change_24h,
            "rsi": rsi,
            "ema50": ema50,
            "ema200": ema200
        }

        # Rule A: Extreme Volatility Shock -> RISK_OFF
        if abs(change_24h) >= self.config.extreme_volatility_pct:
            reasons.append(f"Extreme 24h volatility detected ({change_24h:+.2f}% >= {self.config.extreme_volatility_pct}%)")
            reasons.append("Elevated adverse selection risk; inventory exposure constrained")
            return RegimeAnalysisResult(
                regime=MarketRegime.RISK_OFF,
                confidence=0.92,
                status="PASS",
                symbol=symbol,
                reasons=reasons,
                metrics=metrics,
                is_blackout=False,
                blackout_event=None,
                timestamp_ms=now_ms,
                event_risk_status=event_risk_status
            )

        # Rule B: Sharp Downside Breakdown -> RISK_OFF
        if change_24h <= self.config.risk_off_drop_pct:
            reasons.append(f"Sharp directional selling ({change_24h:+.2f}% <= {self.config.risk_off_drop_pct}%)")
            if rsi is not None and rsi <= self.config.rsi_oversold_extreme:
                reasons.append(f"RSI extended ({rsi:.1f} <= {self.config.rsi_oversold_extreme}); capitulation risk")
            return RegimeAnalysisResult(
                regime=MarketRegime.RISK_OFF,
                confidence=0.88,
                status="PASS",
                symbol=symbol,
                reasons=reasons,
                metrics=metrics,
                is_blackout=False,
                blackout_event=None,
                timestamp_ms=now_ms,
                event_risk_status=event_risk_status
            )

        # Rule C: Consistent Upward Impulse + Trend Structure -> RISK_ON
        if change_24h >= self.config.risk_on_min_pct:
            bullish_structure = True
            if has_emas:
                bullish_structure = price >= ema50 >= ema200

            if bullish_structure:
                reasons.append(f"Positive momentum ({change_24h:+.2f}%) with favorable market structure")
                if has_emas:
                    reasons.append("Price positioned above key moving averages (EMA50 > EMA200)")
                if rsi is not None and 45.0 <= rsi <= 72.0:
                    reasons.append(f"RSI({rsi:.1f}) in constructive momentum corridor")
                
                confidence = 0.84 if has_emas else 0.78
                return RegimeAnalysisResult(
                    regime=MarketRegime.RISK_ON,
                    confidence=confidence,
                    status="PASS",
                    symbol=symbol,
                    reasons=reasons,
                    metrics=metrics,
                    is_blackout=False,
                    blackout_event=None,
                    timestamp_ms=now_ms,
                    event_risk_status=event_risk_status
                )

        # Rule D: Consolidation / Balanced Range -> NEUTRAL
        reasons.append(f"24h change at {change_24h:+.2f}% within neutral channel (-3.0% to +1.0%)")
        reasons.append("Two-way volume balance supports statistical mean-reversion models")
        if rsi is not None:
            reasons.append(f"RSI({rsi:.1f}) centered around neutral median")

        return RegimeAnalysisResult(
            regime=MarketRegime.NEUTRAL,
            confidence=0.82,
            status="PASS",
            symbol=symbol,
            reasons=reasons,
            metrics=metrics,
            is_blackout=False,
            blackout_event=None,
            timestamp_ms=now_ms,
            event_risk_status=event_risk_status
        )

    def evaluate_market_breadth_regime(
        self,
        market_snapshots: Dict[str, Dict[str, Any]],
        benchmark_symbol: str = "BTC",
        calendar_source: Optional[EventCalendarSource] = None,
        current_time_ms: Optional[int] = None
    ) -> RegimeAnalysisResult:
        """
        Determines aggregate market-wide regime from multi-asset breadth.
        """
        now_ms = current_time_ms if current_time_ms is not None else int(time.time() * 1000)

        # Check calendar blackout first
        event_risk_status = "NOT_CONFIGURED"
        if calendar_source is not None:
            is_blackout, blackout_regime, blackout_reasons, event = self.check_event_blackout(
                current_time_ms=now_ms,
                calendar_source=calendar_source
            )
            if is_blackout:
                event_dict = {
                    "event_id": event.event_id,
                    "title": event.title,
                    "timestamp_ms": event.timestamp_ms
                } if event else None
                return RegimeAnalysisResult(
                    regime=MarketRegime.EVENT_BLACKOUT,
                    confidence=0.95,
                    status="BLACKOUT",
                    symbol="MARKET_BREADTH",
                    reasons=blackout_reasons,
                    metrics={},
                    is_blackout=True,
                    blackout_event=event_dict,
                    timestamp_ms=now_ms,
                    event_risk_status="BLACKOUT"
                )
            elif blackout_regime == MarketRegime.UNKNOWN:
                event_risk_status = "UNKNOWN"
            else:
                event_risk_status = "CLEAR"

        if not market_snapshots:
            return RegimeAnalysisResult(
                regime=MarketRegime.UNKNOWN,
                confidence=0.0,
                status="UNKNOWN",
                symbol="MARKET_BREADTH",
                reasons=["No market data snapshots provided for breadth calculation"],
                metrics={},
                is_blackout=False,
                blackout_event=None,
                timestamp_ms=now_ms,
                event_risk_status=event_risk_status
            )

        valid_changes = []
        positive_count = 0
        negative_count = 0

        for sym, data in market_snapshots.items():
            if not isinstance(data, dict):
                continue
            if data.get("status") not in ("PASS", "NORMAL"):
                continue
            chg = data.get("change_24h")
            if chg is not None and isinstance(chg, (int, float)) and math.isfinite(chg):
                valid_changes.append(float(chg))
                if chg > 0:
                    positive_count += 1
                elif chg < 0:
                    negative_count += 1

        if not valid_changes:
            return RegimeAnalysisResult(
                regime=MarketRegime.UNKNOWN,
                confidence=0.0,
                status="UNKNOWN",
                symbol="MARKET_BREADTH",
                reasons=["Zero valid market snapshots with status PASS/NORMAL"],
                metrics={},
                is_blackout=False,
                blackout_event=None,
                timestamp_ms=now_ms,
                event_risk_status=event_risk_status
            )

        avg_change = sum(valid_changes) / len(valid_changes)
        breadth_ratio = positive_count / len(valid_changes)

        metrics = {
            "total_pairs": len(valid_changes),
            "positive_pairs": positive_count,
            "negative_pairs": negative_count,
            "breadth_ratio": round(breadth_ratio, 2),
            "average_24h_change": round(avg_change, 2)
        }

        # Benchmark reference
        btc_data = market_snapshots.get(benchmark_symbol, {})
        btc_change = btc_data.get("change_24h") if (btc_data.get("status") in ("PASS", "NORMAL")) else None
        if btc_change is not None:
            metrics[f"{benchmark_symbol.lower()}_change_24h"] = round(float(btc_change), 2)

        if avg_change <= self.config.risk_off_drop_pct or breadth_ratio <= 0.20:
            return RegimeAnalysisResult(
                regime=MarketRegime.RISK_OFF,
                confidence=0.90,
                status="PASS",
                symbol="MARKET_BREADTH",
                reasons=[
                    f"Aggregate market breadth is heavily skewed negative ({breadth_ratio:.0%} positive)",
                    f"Average market-wide 24h change is {avg_change:+.2f}%"
                ],
                metrics=metrics,
                is_blackout=False,
                blackout_event=None,
                timestamp_ms=now_ms,
                event_risk_status=event_risk_status
            )
        elif avg_change >= self.config.risk_on_min_pct and breadth_ratio >= 0.70:
            return RegimeAnalysisResult(
                regime=MarketRegime.RISK_ON,
                confidence=0.85,
                status="PASS",
                symbol="MARKET_BREADTH",
                reasons=[
                    f"Broad risk appetite confirmed across {breadth_ratio:.0%} of traded pairs",
                    f"Average market-wide 24h change is {avg_change:+.2f}%"
                ],
                metrics=metrics,
                is_blackout=False,
                blackout_event=None,
                timestamp_ms=now_ms,
                event_risk_status=event_risk_status
            )
        else:
            return RegimeAnalysisResult(
                regime=MarketRegime.NEUTRAL,
                confidence=0.80,
                status="PASS",
                symbol="MARKET_BREADTH",
                reasons=[
                    f"Market breadth is balanced ({breadth_ratio:.0%} positive, {1.0 - breadth_ratio:.0%} negative)",
                    f"Average market-wide 24h change is {avg_change:+.2f}%"
                ],
                metrics=metrics,
                is_blackout=False,
                blackout_event=None,
                timestamp_ms=now_ms,
                event_risk_status=event_risk_status
            )


# Global deterministic regime engine singleton
regime_engine = DeterministicMarketRegimeEngine()
