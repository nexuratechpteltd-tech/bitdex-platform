"""
BITDEX — TRACK 2: PRECISION STRATEGY ENGINE (CANDIDATE A V2)
============================================================
Moves Candidate A v2 High-Conviction Precision Scalper into the Long-Term / HTF Strategy domain:
- Multi-timeframe: H1 EMA21/EMA50 trend confirmation -> M15 market structure -> M5 EMA9/EMA21 alignment + rejection candle.
- Execution cap: 1 to 3 executed positions per day.
- Structural targets: Dynamic ATR and swing-based levels (no hardcoded fixed pips).
- Stops: ATR/swing-based invalidation levels verified against broker min stop distance.
- Cost-adjusted Net R:R: >= 1.50R floor (targeting 2.0R+).
- Fully decoupled from Track 1 micro-scalping.
"""

import time
import math
import logging
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional, Tuple

from .strategy_candidate_a import CandidateAStrategy, RiskPolicy

logger = logging.getLogger("bitdex.precision_strategy_engine")


@dataclass
class PrecisionEngineConfig:
    strategy_code: str = "TRACK2_PRECISION_CANDIDATE_A_V2"
    max_daily_executions: int = 3
    risk_pct_per_trade: float = 0.0025  # 0.25% equity
    min_net_rr: float = 1.50
    target_net_rr: float = 2.00
    require_broker_sltp_verification: bool = True


class PrecisionStrategyEngine:
    """Independent Track 2 Precision Strategy Service."""

    def __init__(self, config: Optional[PrecisionEngineConfig] = None):
        self.config = config or PrecisionEngineConfig()
        self.candidate_a = CandidateAStrategy()

    def evaluate_precision_setup(
        self,
        symbol: str,
        candles_h1: List[Dict[str, Any]],
        candles_m15: List[Dict[str, Any]],
        candles_m5: List[Dict[str, Any]],
        bid: float,
        ask: float,
        account_equity: float,
        contract_spec: Dict[str, Any],
        daily_executed_count: int = 0
    ) -> Dict[str, Any]:
        """
        Evaluates Candidate A v2 precision entry.
        Checks 1-3 daily executions limit before qualifying.
        """
        # Daily execution frequency limit
        if daily_executed_count >= self.config.max_daily_executions:
            return {
                "decision": "NO_TRADE",
                "symbol": symbol,
                "strategy": self.config.strategy_code,
                "reason": f"DAILY_EXECUTION_LIMIT_REACHED: {daily_executed_count}/{self.config.max_daily_executions} trades executed today.",
                "daily_executed_count": daily_executed_count,
                "status": "HALTED_DAILY_LIMIT"
            }

        # Build risk policy for Candidate A v2
        policy = RiskPolicy(
            risk_pct=self.config.risk_pct_per_trade,
            cost_markup_factor=1.20,
            prefer_2r=True
        )

        # Delegate to Candidate A v2 engine
        eval_result = self.candidate_a.evaluate(
            candles_h1=candles_h1,
            candles_m15=candles_m15,
            candles_m5=candles_m5,
            bid=bid,
            ask=ask,
            account_equity=account_equity,
            contract_spec=contract_spec,
            risk_policy=policy
        )

        # Inject Track 2 metadata
        eval_result["strategy"] = self.config.strategy_code
        eval_result["daily_executed_count"] = daily_executed_count
        eval_result["max_daily_executions"] = self.config.max_daily_executions
        eval_result["track"] = "TRACK_2_PRECISION_SCALPING"

        # Format price distance and monetary values
        if eval_result.get("decision") == "BUY" or eval_result.get("decision") == "SELL":
            entry = eval_result.get("entry_price", 0.0)
            sl = eval_result.get("stop_loss", 0.0)
            tp = eval_result.get("take_profit", 0.0)
            digits = contract_spec.get("digits", 2)
            eval_result["price_sl_distance"] = round(abs(entry - sl), digits)
            eval_result["price_tp_distance"] = round(abs(entry - tp), digits)
            eval_result["status"] = "READY TO TRADE"

        return eval_result
