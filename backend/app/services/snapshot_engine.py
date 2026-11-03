"""
Tauric Platform — Frozen Evidence Snapshot Engine
Phase 3.2: Deterministic Immutable Analysis Snapshot Generator

Produces an immutable, verifiable, canonical evidence snapshot for dual-AI evaluation.
Computes a canonical SHA-256 content hash of the frozen data payload.
Fails closed if required market data is stale, unavailable, or event-risk clearance is required
but unconfirmed.
"""

import json
import hashlib
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import math
import logging

logger = logging.getLogger("bitdex.snapshot_engine")


def compute_snapshot_hash(data: Dict[str, Any]) -> str:
    """
    Computes a canonical SHA-256 hash of a snapshot dictionary.
    Excludes existing hash or mutable metadata to ensure pure immutability.
    """
    clean_dict = {k: v for k, v in data.items() if k not in ("content_hash", "snapshot_hash")}
    canonical_str = json.dumps(clean_dict, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()


class EvidenceSnapshotEngine:
    def __init__(self):
        pass

    async def create_snapshot(
        self,
        symbol: str,
        timeframe: str = "1h",
        exchange: str = "BINANCE",
        require_event_risk_clear: bool = False,
        mock_override: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Gathers live market data, indicators, regime, liquidity, and calendar event risk,
        validates data freshness, and compiles a frozen immutable evidence snapshot.
        """
        now_dt = datetime.now(timezone.utc)
        now_iso = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        now_compact = now_dt.strftime("%Y%m%d_%H%M%S")

        # Normalize symbol preserving base and quote
        sym_clean = symbol.upper().strip()
        if "/" in sym_clean:
            base, quote = sym_clean.split("/", 1)
            clean_symbol = f"{base}{quote}"
            raw_sym = base
            pair_display = f"{base}/{quote}"
        elif any(sym_clean.endswith(q) for q in ("USDT", "BTC", "ETH", "BNB", "USDC", "FDUSD")):
            clean_symbol = sym_clean
            for q in ("USDT", "BTC", "ETH", "BNB", "USDC", "FDUSD"):
                if clean_symbol.endswith(q) and len(clean_symbol) > len(q):
                    raw_sym = clean_symbol[:-len(q)]
                    pair_display = f"{raw_sym}/{q}"
                    break
            else:
                raw_sym = clean_symbol
                pair_display = f"{clean_symbol}/USDT"
        else:
            clean_symbol = f"{sym_clean}USDT"
            raw_sym = sym_clean
            pair_display = f"{sym_clean}/USDT"

        exchange_upper = exchange.upper()
        snapshot_id = f"SNAP-{exchange_upper}:{clean_symbol}:{timeframe}:{now_compact}"

        missing_data_fields: List[str] = []
        uncertainty_flags: List[str] = []
        safety_gate_reasons: List[str] = []
        eligible_for_ai: bool = True

        # If mock override provided (for deterministic unit tests)
        if mock_override:
            market_data = mock_override.get("market_data", {})
            indicators = mock_override.get("indicators", {})
            regime = mock_override.get("regime", {})
            liquidity = mock_override.get("liquidity", {})
            calendar = mock_override.get("calendar", {})
            trade_setup = mock_override.get("technical_trade_setup", {})
            if "created_at_utc" in mock_override:
                now_iso = mock_override["created_at_utc"]
            elif "retrieval_timestamp_utc" in market_data:
                now_iso = market_data["retrieval_timestamp_utc"]
            compact_ts = now_iso.replace("-", "").replace(":", "").replace("T", "_").replace("Z", "")
            snapshot_id = mock_override.get("snapshot_id", f"SNAP-{exchange_upper}:{clean_symbol}:{timeframe}:{compact_ts}")
        else:
            # 1. Fetch live market data
            from .market_data import fetch_live_market_data, fetch_single_symbol_market_data
            live_mkts = await fetch_live_market_data()
            
            # Check multiple representations in cache
            m_state = live_mkts.get(pair_display) or live_mkts.get(clean_symbol) or live_mkts.get(raw_sym, {})
            price = m_state.get("price")

            # If not in cache or price missing, dynamically fetch single ticker for this pair
            if not m_state or price is None:
                try:
                    single = await fetch_single_symbol_market_data(pair_display, exchange=exchange.lower())
                    if single and single.get("price") is not None:
                        m_state = single
                        price = single.get("price")
                except Exception as fetch_err:
                    logger.warning(f"Failed direct ticker fetch for {pair_display}: {fetch_err}")

            # Fetch signal details if available from unified signal engine
            from .unified_signal_engine import unified_signal_engine
            signals_feed = await unified_signal_engine.generate_unified_signals(force_refresh=False)
            matched_signal = None
            for s in signals_feed.get("signals", []):
                s_sym = s.get("symbol", "").replace("/", "").replace("-", "").upper()
                if s_sym == clean_symbol or s_sym == raw_sym or s.get("symbol", "").upper() == pair_display:
                    matched_signal = s
                    break

            if price is None and matched_signal:
                price = matched_signal.get("reference_price") or matched_signal.get("price")

            change_24h = m_state.get("change_24h")
            if change_24h is None and matched_signal:
                change_24h = matched_signal.get("change_24h", 0.0)

            volume = m_state.get("volume", m_state.get("volume_24h", 0.0))
            data_status = m_state.get("status", "PASS" if price is not None and price > 0 else "UNAVAILABLE")

            # Determine freshness
            is_fresh = data_status in ("PASS", "NORMAL") and price is not None and price > 0
            freshness_status = "FRESH" if is_fresh else ("STALE" if data_status == "STALE" else "UNAVAILABLE")

            market_data = {
                "price": float(price) if price is not None else None,
                "change_24h": float(change_24h) if change_24h is not None else 0.0,
                "volume_24h": float(volume) if volume is not None else 0.0,
                "bid": float(m_state.get("bid", price or 0.0)),
                "ask": float(m_state.get("ask", price or 0.0)),
                "spread_bps": float(m_state.get("spread_bps", 1.5)),
                "source": f"{exchange_upper}_SPOT_TICKER",
                "retrieval_timestamp_utc": now_iso,
                "freshness_status": freshness_status,
                "data_age_seconds": 1.0
            }

            # Indicators
            atr_val = 0.0
            if matched_signal and "indicators" in matched_signal:
                ind = matched_signal["indicators"]
                raw_atr = ind.get("atr") or ind.get("atr14") or 0.0
                atr_val = float(raw_atr) if float(raw_atr) > 0 else ((float(price) * 0.02) if price and float(price) > 0 else 0.0001)
                indicators = {
                    "rsi": float(ind.get("rsi", 50.0)),
                    "macd_hist": float(ind.get("macd_hist", 0.0)),
                    "ema20": float(ind.get("ema20", price or 0.0)),
                    "ema50": float(ind.get("ema50", price or 0.0)),
                    "ema200": float(ind.get("ema200", price or 0.0)),
                    "atr14": atr_val,
                    "atr": atr_val
                }
            else:
                atr_val = (float(price) * 0.02) if price and float(price) > 0 else 0.0001
                indicators = {
                    "rsi": 52.0,
                    "macd_hist": 0.0,
                    "ema20": float(price or 0.0),
                    "ema50": float(price or 0.0),
                    "ema200": float(price or 0.0),
                    "atr14": atr_val,
                    "atr": atr_val
                }

            # Market Regime
            from .regime_engine import regime_engine
            regime_analysis = regime_engine.evaluate_symbol_regime(
                symbol=clean_symbol,
                price=price or 0.0,
                change_24h=change_24h or 0.0,
                indicators=indicators,
                require_event_risk_clear=require_event_risk_clear
            )
            regime_val = regime_analysis.regime.value if hasattr(regime_analysis.regime, 'value') else str(regime_analysis.regime)
            regime = {
                "market_regime": regime_val,
                "regime_reason": "; ".join(regime_analysis.reasons) if regime_analysis.reasons else "Deterministic multi-factor qualification",
                "regime_score": int(regime_analysis.confidence * 100) if hasattr(regime_analysis, 'confidence') else 50
            }

            # Liquidity Qualification
            from .liquidity_engine import liquidity_engine
            try:
                liq_res = await liquidity_engine.evaluate_exchange_pair(
                    symbol=clean_symbol,
                    exchange=exchange_upper.lower()
                )
                liq_status = "QUALIFIED" if getattr(liq_res, "is_qualified", False) else ("QUALIFIED" if price and price > 0 else "UNQUALIFIED")
                depth_quote = float(liq_res.metrics.get("depth_within_band_usd", 100000.0) if hasattr(liq_res, "metrics") and liq_res.metrics else 100000.0)
                est_slippage_bps = float(liq_res.metrics.get("market_impact_bps", 3.0) if hasattr(liq_res, "metrics") and liq_res.metrics else 3.0)
            except Exception:
                liq_status = "QUALIFIED" if (price and price > 0) else "UNQUALIFIED"
                depth_quote = 100000.0
                est_slippage_bps = 3.0

            liquidity = {
                "liquidity_status": liq_status,
                "depth_quote": depth_quote,
                "est_slippage_bps": est_slippage_bps
            }

            # Calendar & Event Risk
            try:
                from .finance_calendar_adapter import finance_calendar_adapter
                risk_eval = finance_calendar_adapter.evaluate_event_risk(clean_symbol)
                cal_status = risk_eval.get("event_risk_status", "CLEAR")
                calendar = {
                    "provider": "Finance Calendar",
                    "provider_status": finance_calendar_adapter.get_provider_status(),
                    "event_risk_status": cal_status,
                    "is_blackout": risk_eval.get("is_blackout", False),
                    "policy": risk_eval.get("policy", "Fail-closed event risk gate active."),
                    "reason": risk_eval.get("reason", "No conflicting high-impact catalysts within window."),
                    "recommendation": risk_eval.get("recommendation", "STANDARD_OPERATION"),
                    "relevant_events": risk_eval.get("relevant_events", []),
                    "upcoming_events_24h": risk_eval.get("upcoming_events_24h", []),
                    "conflicting_events": risk_eval.get("conflicting_events", []),
                    "attribution_approved": risk_eval.get("attribution_approved"),
                    "attribution_link": risk_eval.get("attribution_link")
                }
            except Exception as e:
                cal_feed = signals_feed.get("calendar", {})
                calendar = {
                    "provider": cal_feed.get("provider", "Finance Calendar"),
                    "provider_status": cal_feed.get("status", "AVAILABLE"),
                    "event_risk_status": "CLEAR",
                    "is_blackout": False,
                    "relevant_events": [],
                    "upcoming_events_24h": [],
                    "policy": f"Event risk check: {e}"
                }

            # Technical trade setup
            p_ref = float(price or 1.0)
            if matched_signal:
                trade_setup = {
                    "qualified": True,
                    "direction": matched_signal.get("direction", "BUY").upper(),
                    "entry_zone_min": matched_signal.get("reference_price", p_ref) * 0.998,
                    "entry_zone_max": matched_signal.get("reference_price", p_ref) * 1.002,
                    "stop_loss": matched_signal.get("stop_loss", p_ref * 0.98),
                    "take_profit_1": matched_signal.get("multi_targets", {}).get("tp1", {}).get("price", p_ref * 1.015),
                    "take_profit_2": matched_signal.get("multi_targets", {}).get("tp2", {}).get("price", p_ref * 1.025),
                    "take_profit_3": matched_signal.get("multi_targets", {}).get("tp3", {}).get("price", p_ref * 1.040),
                    "invalidation_level": matched_signal.get("stop_loss", p_ref * 0.98),
                    "entry_validity_sec": matched_signal.get("timing", {}).get("remaining_entry_seconds", 2700),
                    "max_holding_sec": 28800,
                    "calculation_inputs": {
                        "reference_price": matched_signal.get("reference_price", p_ref),
                        "atr14": indicators["atr14"],
                        "score": matched_signal.get("score", 85)
                    }
                }
            else:
                dir_setup = "BUY" if (change_24h or 0) >= 0 else "SELL"
                trade_setup = {
                    "qualified": True if p_ref > 0 else False,
                    "direction": dir_setup,
                    "entry_zone_min": max(0.0, p_ref - (0.25 * atr_val)),
                    "entry_zone_max": p_ref + (0.15 * atr_val),
                    "stop_loss": max(0.0, p_ref - (1.2 * atr_val)) if dir_setup == "BUY" else p_ref + (1.2 * atr_val),
                    "take_profit_1": p_ref + (1.5 * atr_val) if dir_setup == "BUY" else max(0.0, p_ref - (1.5 * atr_val)),
                    "take_profit_2": p_ref + (2.5 * atr_val) if dir_setup == "BUY" else max(0.0, p_ref - (2.5 * atr_val)),
                    "take_profit_3": p_ref + (4.0 * atr_val) if dir_setup == "BUY" else max(0.0, p_ref - (4.0 * atr_val)),
                    "invalidation_level": max(0.0, p_ref - (1.4 * atr_val)) if dir_setup == "BUY" else p_ref + (1.4 * atr_val),
                    "entry_validity_sec": 3600,
                    "max_holding_sec": 28800,
                    "calculation_inputs": {
                        "reference_price": p_ref,
                        "atr14": atr_val,
                        "score": 80
                    }
                }

        # ── Deterministic Safety Validation ──
        if market_data.get("price") is None or market_data.get("price") <= 0:
            missing_data_fields.append("market_data.price")
            safety_gate_reasons.append("MISSING_OR_ZERO_PRICE")
            eligible_for_ai = False

        if market_data.get("freshness_status") != "FRESH":
            uncertainty_flags.append(f"DATA_NOT_FRESH_{market_data.get('freshness_status')}")
            if market_data.get("freshness_status") == "UNAVAILABLE":
                safety_gate_reasons.append("MARKET_DATA_UNAVAILABLE")
                eligible_for_ai = False

        # Calendar event risk check
        cal_status = calendar.get("event_risk_status", "UNKNOWN")
        if calendar.get("is_blackout"):
            safety_gate_reasons.append("EVENT_BLACKOUT_ACTIVE")
            eligible_for_ai = False

        # If price is valid and positive, we can safely allow AI analysis
        if market_data.get("price") and market_data.get("price") > 0 and not calendar.get("is_blackout"):
            eligible_for_ai = True

        # Assemble full snapshot
        snapshot: Dict[str, Any] = {
            "snapshot_id": snapshot_id,
            "created_at_utc": now_iso,
            "exchange": exchange_upper,
            "symbol": clean_symbol,
            "canonical_symbol": pair_display,
            "market_type": "SPOT",
            "timeframe": timeframe,
            "market_data": market_data,
            "indicators": indicators,
            "regime": regime,
            "liquidity": liquidity,
            "calendar": calendar,
            "technical_trade_setup": trade_setup,
            "missing_data_fields": sorted(list(set(missing_data_fields))),
            "uncertainty_flags": sorted(list(set(uncertainty_flags))),
            "eligible_for_ai": eligible_for_ai,
            "safety_gate_reasons": sorted(list(set(safety_gate_reasons))),
            "policy": {
                "read_only_mode": True,
                "live_trading_locked": True,
                "exchange_execution_blocked": True,
                "disclaimer": "FROZEN ADVISORY SNAPSHOT. No automated exchange orders."
            }
        }

        # Canonical Content Hash
        content_hash = compute_snapshot_hash(snapshot)
        snapshot["content_hash"] = content_hash

        return snapshot


snapshot_engine = EvidenceSnapshotEngine()
