import os
import logging
import httpx
from typing import Dict, Any, List, Optional
from datetime import datetime
from ..config import settings

logger = logging.getLogger(__name__)

class JevClient:
    def __init__(self):
        self.endpoint = settings.typesafe_api_endpoint
        self.api_key = settings.typesafe_api_key
        self.model = settings.typesafe_model

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    async def check_connectivity(self) -> Dict[str, Any]:
        if not self.api_key:
            return {"provider": "TypeSafe Jev", "status": "NOT_CONFIGURED", "model": self.model}

        try:
            body = {
                "model": self.model,
                "state": {"ping": "health_check"},
                "questions": {
                    "active": {
                        "type": "choice",
                        "instructions": "Is the system functioning normally?",
                        "criteria": {
                            "active": "Yes, system active",
                            "inactive": "No, system inactive"
                        }
                    }
                }
            }
            async with httpx.AsyncClient(timeout=6.0) as client:
                res = await client.post(self.endpoint, json=body, headers=self._headers())
                if res.status_code == 200:
                    data = res.json()
                    try:
                        from .telemetry_manager import telemetry_manager
                        telemetry_manager.record_token_usage("jev", data.get("usage"), data.get("model", self.model))
                    except Exception:
                        pass

                    return {
                        "provider": "TypeSafe Jev (Fast Probability Engine)",
                        "status": "CONNECTED",
                        "model": data.get("model", self.model)
                    }
                return {"provider": "TypeSafe Jev", "status": f"HTTP_{res.status_code}", "model": self.model}
        except Exception as e:
            logger.warning(f"Jev connectivity check failed: {e}")
            return {"provider": "TypeSafe Jev", "status": "DISCONNECTED", "error": str(e), "model": self.model}

    async def fast_decision(self, ticker: str, market_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fast decision layer querying Jev (or fallback if unavailable/key missing) for rapid statistical directional bias.
        """
        clean_ticker = ticker.replace("USDT", "").replace("-USD", "")
        price = market_state.get("price", 0.0)
        change_24h = market_state.get("change_24h", 0.0)
        volume = market_state.get("volume_24h", market_state.get("volume", 0.0))
        
        state = {
            "instrument": f"{clean_ticker}-USD",
            "price": price,
            "change_24h": change_24h,
            "volume_24h": volume
        }
        
        questions = {
            "opportunity": {
                "type": "choice",
                "instructions": f"Does {clean_ticker} present a favorable immediate directional asymmetry?",
                "criteria": {
                    "actionable": "Market displays clear directional bias and positive expectancy.",
                    "wait": "Market is choppy, unconfirmed, or within equilibrium noise."
                }
            },
            "bias": {
                "type": "choice",
                "instructions": f"What is the predominant directional impulse on {clean_ticker}?",
                "criteria": {
                    "bullish": "Positive upward momentum and buyer absorption.",
                    "bearish": "Downward selling pressure or distribution.",
                    "neutral": "Balanced two-way flow without directional edge."
                }
            }
        }
        
        if not self.api_key:
            # Deterministic fallback when key is not configured
            # Evaluated strictly from market_state metrics
            if change_24h is not None and change_24h > 1.5:
                direction = "bullish"
                decision = "ACTIONABLE"
                confidence = 0.78
            elif change_24h is not None and change_24h < -2.0:
                direction = "bearish"
                decision = "ACTIONABLE"
                confidence = 0.81
            else:
                direction = "neutral"
                decision = "WAIT"
                confidence = 0.65
                
            return {
                "decision": decision,
                "bias": {"direction": direction, "confidence": confidence},
                "opportunity": {
                    "choice": "actionable" if decision == "ACTIONABLE" else "wait",
                    "confidence": confidence,
                    "probabilities": {
                        "bullish": 0.7 if direction == "bullish" else 0.2,
                        "bearish": 0.7 if direction == "bearish" else 0.2,
                        "neutral": 0.6 if direction == "neutral" else 0.1
                    }
                },
                "status": "LOCAL_DETERMINISTIC_MODEL",
                "reasoning": f"Local fast decision: {decision} ({direction})"
            }

        try:
            body = {
                "model": self.model,
                "state": state,
                "questions": questions
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(self.endpoint, json=body, headers=self._headers())
                if res.status_code == 200:
                    payload = res.json()
                    try:
                        from .telemetry_manager import telemetry_manager
                        telemetry_manager.record_token_usage("jev", payload.get("usage"), payload.get("model", self.model))
                    except Exception:
                        pass
                    
                    answers = payload.get("answers", {})
                    opp = answers.get("opportunity", {})
                    bias_ans = answers.get("bias", {})
                    
                    decision = "ACTIONABLE" if opp.get("choice") == "actionable" else "WAIT"
                    direction = bias_ans.get("choice", "neutral").lower()
                    
                    return {
                        "decision": decision,
                        "bias": {"direction": direction, "confidence": bias_ans.get("confidence", 0.75)},
                        "opportunity": opp,
                        "status": "SUCCESS",
                        "model": payload.get("model", self.model)
                    }
                else:
                    return {
                        "decision": "WAIT",
                        "bias": {"direction": "neutral", "confidence": 0.5},
                        "opportunity": {"choice": "wait", "confidence": 0.5, "probabilities": {}},
                        "status": "ERROR",
                        "reasoning": f"Jev API returned HTTP {res.status_code}"
                    }
        except Exception as e:
            logger.error(f"Jev fast_decision error: {e}")
            return {
                "decision": "WAIT",
                "bias": {"direction": "neutral", "confidence": 0.5},
                "opportunity": {"choice": "wait", "confidence": 0.5, "probabilities": {}},
                "status": "FALLBACK",
                "reasoning": str(e)
            }

    async def batch_fast_screening(self, pairs_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Stage 3: ONE batched Jev request for top candidate screening.
        """
        if not pairs_data:
            return {"status": "EMPTY", "results": {}}
            
        screening_state = {
            "batch_timestamp": datetime.now().isoformat(),
            "candidates_count": len(pairs_data),
            "candidates": [
                {
                    "symbol": p.get("symbol"),
                    "price": p.get("current_price"),
                    "change_24h": p.get("change_24h"),
                    "volume": p.get("volume_24h", 0),
                    "grid_count": p.get("grid_count", 0),
                    "direction": p.get("direction", "N/A"),
                    "strategy": p.get("strategy")
                }
                for p in pairs_data
            ]
        }

        questions = {
            "market_regime": {
                "type": "choice",
                "instructions": "Evaluate the current multi-asset volatility and liquidity regime for these candidates.",
                "criteria": {
                    "safe_to_trade": "Market conditions show stable two-way liquidity and controlled directional risk.",
                    "high_volatility": "Elevated momentum expansion or potential liquidity gap risks present.",
                    "defensive_wait": "High risk of adverse breakout or regime transition."
                }
            }
        }

        try:
            body = {
                "model": self.model,
                "state": screening_state,
                "questions": questions
            }
            async with httpx.AsyncClient(timeout=12.0) as client:
                res = await client.post(self.endpoint, json=body, headers=self._headers())
                if res.status_code == 200:
                    payload = res.json()
                    try:
                        from .telemetry_manager import telemetry_manager
                        telemetry_manager.record_token_usage("jev", payload.get("usage"), payload.get("model", self.model))
                    except Exception:
                        pass
                    return {
                        "status": "SUCCESS",
                        "model": payload.get("model", self.model),
                        "answers": payload.get("answers", {}),
                        "timestamp": datetime.now().strftime("%H:%M:%S")
                    }
                else:
                    return {"status": "ERROR", "error": f"HTTP {res.status_code}"}
        except Exception as e:
            logger.error(f"Jev batch_fast_screening error: {e}")
            return {"status": "FALLBACK", "error": str(e)}

    async def blind_review(self, ticker: str, grid_params: Dict[str, Any], market_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Independent Jev review for Spot Grid.
        Give Jev ONLY: raw market data (price, change, volume, ATR) and grid parameters.
        """
        clean_ticker = ticker.replace("USDT", "").replace("-USD", "")
        
        blind_state = {
            "instrument": f"{clean_ticker}-USD",
            "current_market_price": market_state.get("price", 0.0),
            "current_24h_delta": market_state.get("change_24h", 0.0),
            "volume_24h": market_state.get("volume", 0.0),
            "atr": market_state.get("atr", 0.0),
            "grid_range_low": grid_params.get("lower_price", 0.0),
            "grid_range_high": grid_params.get("upper_price", 0.0),
            "grid_count": grid_params.get("grid_count", 0),
            "grid_spacing": grid_params.get("spacing_pct", 0.0)
        }

        questions = {
            "validation": {
                "type": "choice",
                "instructions": (
                    f"Blind Risk & Expectancy Validation for {clean_ticker}: "
                    f"A grid trading model proposes parameters with range {blind_state['grid_range_low']} to {blind_state['grid_range_high']}, "
                    f"{blind_state['grid_count']} grids, and {blind_state['grid_spacing']}% spacing. "
                    f"Given current price action, volume, and ATR, does this grid structure possess positive mathematical expectancy?"
                ),
                "criteria": {
                    "agree": "The proposed grid parameters align well with the current volatility, ATR, and liquidity.",
                    "disagree": "The proposed grid parameters contradict current market dynamics, risk squeeze, or offer adverse asymmetry."
                }
            },
            "risk_profile": {
                "type": "choice",
                "instructions": f"Evaluate the risk tolerance for this proposed grid setup on {clean_ticker}.",
                "criteria": {
                    "acceptable_risk": "Risk is controlled with clear bounds.",
                    "elevated_risk": "Elevated risk due to volatility expansion or proximity to inflection.",
                    "unacceptable_risk": "Excessive tail risk or poor risk-to-reward ratio."
                }
            }
        }

        try:
            body = {
                "model": self.model,
                "state": blind_state,
                "questions": questions
            }
            async with httpx.AsyncClient(timeout=12.0) as client:
                res = await client.post(self.endpoint, json=body, headers=self._headers())
                if res.status_code == 200:
                    payload = res.json()
                    try:
                        from .telemetry_manager import telemetry_manager
                        telemetry_manager.record_token_usage("jev", payload.get("usage"), payload.get("model", self.model))
                    except Exception:
                        pass

                    ans = payload.get("answers", {})
                    val_ans = ans.get("validation", {})
                    risk_ans = ans.get("risk_profile", {})

                    choice = val_ans.get("choice", "agree")
                    confidence = val_ans.get("confidence", 0.85)
                    probs = val_ans.get("probabilities", {})

                    agree_prob = probs.get("agree", 0.75)
                    outcome = "AGREE" if choice == "agree" else "DISAGREE"

                    return {
                        "status": "SUCCESS",
                        "prob_agree": agree_prob,
                        "confidence": confidence,
                        "risk_score": risk_ans.get("choice", "acceptable_risk"),
                        "outcome": outcome,
                        "reasoning": f"Jev Blind Review completed with outcome: {outcome}"
                    }
                else:
                    return {
                        "status": "ERROR",
                        "prob_agree": 0.5,
                        "confidence": 0.5,
                        "risk_score": "acceptable_risk",
                        "reasoning": f"Jev API returned HTTP {res.status_code}"
                    }
        except Exception as e:
            logger.error(f"Jev blind_review error: {e}")
            return {
                "status": "FALLBACK",
                "prob_agree": 0.5,
                "confidence": 0.5,
                "risk_score": "acceptable_risk",
                "reasoning": f"Jev review fallback: {str(e)}"
            }

    async def blind_review_trade_setup(self, ticker: str, trade_plan: Dict[str, Any], market_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Independent Jev review for directional TRADE SETUP.
        Give Jev raw market data and directional parameters (direction, entry, TP, SL, R:R).
        """
        clean_ticker = ticker.replace("USDT", "").replace("-USD", "")
        direction = trade_plan.get("direction", trade_plan.get("action", "LONG"))
        entry = trade_plan.get("entry_price", market_state.get("price", 0.0))
        tp = trade_plan.get("take_profit", 0.0)
        sl = trade_plan.get("stop_loss", 0.0)
        
        blind_state = {
            "instrument": f"{clean_ticker}-USD",
            "current_market_price": market_state.get("price", 0.0),
            "current_24h_delta": market_state.get("change_24h", 0.0),
            "proposed_direction": direction,
            "proposed_entry": entry,
            "proposed_take_profit": tp,
            "proposed_stop_loss": sl,
            "atr": market_state.get("atr", 0.0)
        }

        questions = {
            "validation": {
                "type": "choice",
                "instructions": (
                    f"Blind Risk & Expectancy Validation for {clean_ticker}: "
                    f"A directional model proposes {direction} at ${entry} with target ${tp} and stop loss at ${sl}. "
                    f"Given current price action, volume, and volatility, does this trade structure possess positive mathematical expectancy?"
                ),
                "criteria": {
                    "agree": f"The proposed {direction} setup aligns with positive mathematical expectancy and favorable asymmetry.",
                    "disagree": f"The proposed {direction} setup contradicts current market dynamics, risks squeeze, or offers adverse asymmetry."
                }
            },
            "risk_profile": {
                "type": "choice",
                "instructions": f"Evaluate the risk tolerance for this proposed {direction} setup on {clean_ticker}.",
                "criteria": {
                    "acceptable_risk": "Risk is controlled with clear invalidation bounds.",
                    "elevated_risk": "Elevated risk due to volatility expansion or momentum exhaustion.",
                    "unacceptable_risk": "Excessive tail risk or unfavorable risk-to-reward ratio."
                }
            }
        }

        try:
            body = {
                "model": self.model,
                "state": blind_state,
                "questions": questions
            }
            async with httpx.AsyncClient(timeout=12.0) as client:
                res = await client.post(self.endpoint, json=body, headers=self._headers())
                if res.status_code == 200:
                    payload = res.json()
                    try:
                        from .telemetry_manager import telemetry_manager
                        telemetry_manager.record_token_usage("jev", payload.get("usage"), payload.get("model", self.model))
                    except Exception:
                        pass

                    ans = payload.get("answers", {})
                    val_ans = ans.get("validation", {})
                    risk_ans = ans.get("risk_profile", {})

                    choice = val_ans.get("choice", "agree")
                    confidence = val_ans.get("confidence", 0.85)
                    probs = val_ans.get("probabilities", {})

                    agree_prob = probs.get("agree", 0.75)
                    outcome = "AGREE" if choice == "agree" else "DISAGREE"

                    return {
                        "status": "SUCCESS",
                        "prob_agree": agree_prob,
                        "confidence": confidence,
                        "risk_score": risk_ans.get("choice", "acceptable_risk"),
                        "outcome": outcome,
                        "probabilities": probs,
                        "log_summary": f"Jev independent statistical expectation model evaluated {direction} proposal (Agree Prob: {agree_prob:.0%}, Confidence: {confidence:.0%})."
                    }
                else:
                    return {
                        "status": "ERROR",
                        "prob_agree": 0.5,
                        "confidence": 0.5,
                        "risk_score": "acceptable_risk",
                        "outcome": "AGREE",
                        "log_summary": f"Jev API returned HTTP {res.status_code}"
                    }
        except Exception as e:
            logger.error(f"Jev blind_review_trade_setup error: {e}")
            return {
                "status": "FALLBACK",
                "prob_agree": 0.5,
                "confidence": 0.5,
                "risk_score": "acceptable_risk",
                "outcome": "AGREE",
                "log_summary": f"Jev review fallback: {str(e)}"
            }

    # Backward-compatible alias
    async def blind_check(self, ticker: str, trade_plan: Dict[str, Any], market_state: Dict[str, Any]) -> Dict[str, Any]:
        return await self.blind_review_trade_setup(ticker, trade_plan, market_state)

jev_client = JevClient()
