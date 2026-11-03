import time
from typing import List, Dict, Any

_TAURIC_RESEARCH_RUNS = [
    {
        "run_id": "RES-20260929-BTC-01",
        "ticker": "BTC",
        "status": "COMPLETED",
        "timestamp": "2026-09-28T22:30:00Z",
        "target_date": "2026-09-28",
        "consensus": "ACCUMULATE_ON_PULLBACK",
        "confidence_score": 0.86,
        "agents": [
            {
                "role": "Technical Analyst",
                "model": "deepseek-v4-flash",
                "stance": "BULLISH",
                "confidence": 0.88,
                "summary": "Price is respecting ascending channel support. 50 EMA on 4h timeframe confirmed slope continuation. RSI 56 showing healthy momentum room."
            },
            {
                "role": "Fundamental Analyst",
                "model": "deepseek-v4-pro",
                "stance": "NEUTRAL_BULLISH",
                "confidence": 0.84,
                "summary": "Network hash rate at all-time highs. Miner outflows have slowed significantly over the past 7 days, indicating reduced selling pressure."
            },
            {
                "role": "Sentiment Analyst",
                "model": "deepseek-v4-flash",
                "stance": "NEUTRAL",
                "confidence": 0.79,
                "summary": "Funding rates across derivatives venues remain balanced between 0.005% and 0.008%, showing absence of over-leveraged retail euphoria."
            },
            {
                "role": "Risk Management Agent",
                "model": "deepseek-v4-pro",
                "stance": "CONSERVATIVE",
                "confidence": 0.92,
                "summary": "Mandated maximum position risk at 1.5% notional with strict stop validation. Volatility expansion probability assessed at 28%."
            }
        ],
        "final_decision": {
            "action": "BUY_GRID_SCALE",
            "suggested_entry_zone": "$62,800 - $63,200",
            "target_take_profit": "$64,800",
            "invalidation_level": "$61,400",
            "estimated_sharpe": 2.45
        }
    },
    {
        "run_id": "RES-20260929-ETH-01",
        "ticker": "ETH",
        "status": "COMPLETED",
        "timestamp": "2026-09-28T22:15:00Z",
        "target_date": "2026-09-28",
        "consensus": "HOLD_NEUTRAL",
        "confidence_score": 0.78,
        "agents": [
            {
                "role": "Technical Analyst",
                "model": "deepseek-v4-flash",
                "stance": "NEUTRAL",
                "confidence": 0.75,
                "summary": "ETH/BTC ratio testing multi-month range lows. Rebound volume is moderate but lacks institutional breakout confirmation."
            },
            {
                "role": "Fundamental Analyst",
                "model": "deepseek-v4-pro",
                "stance": "BULLISH",
                "confidence": 0.83,
                "summary": "L2 transaction volume and gas fee burns have rebounded 14% week-on-week, demonstrating consistent layer-1 settlement utility."
            },
            {
                "role": "Risk Management Agent",
                "model": "deepseek-v4-pro",
                "stance": "DEFENSIVE",
                "confidence": 0.89,
                "summary": "Recommending hold stance until BTC dominance stabilizes; maintain cash reserves for high-probability setups."
            }
        ],
        "final_decision": {
            "action": "HOLD_MONITOR",
            "suggested_entry_zone": "$2,580 - $2,620",
            "target_take_profit": "$2,780",
            "invalidation_level": "$2,520",
            "estimated_sharpe": 1.95
        }
    },
    {
        "run_id": "RES-20260929-SOL-01",
        "ticker": "SOL",
        "status": "COMPLETED",
        "timestamp": "2026-09-28T21:45:00Z",
        "target_date": "2026-09-28",
        "consensus": "STRONG_MOMENTUM",
        "confidence_score": 0.91,
        "agents": [
            {
                "role": "Technical Analyst",
                "model": "deepseek-v4-flash",
                "stance": "BULLISH",
                "confidence": 0.94,
                "summary": "Clear breakout above 150 resistance with expanding volume. Daily MACD crossed positive with expanding histogram bars."
            },
            {
                "role": "Sentiment Analyst",
                "model": "deepseek-v4-flash",
                "stance": "BULLISH",
                "confidence": 0.88,
                "summary": "DEX volumes leading alternative layer-1s. Social sentiment velocity score reaches 74/100."
            },
            {
                "role": "Risk Management Agent",
                "model": "deepseek-v4-pro",
                "stance": "CAUTION_CHASE",
                "confidence": 0.86,
                "summary": "Position sizing throttled to standard 1x. Forbid chasing intraday wicks > 3% from VWAP."
            }
        ],
        "final_decision": {
            "action": "ACCUMULATE_PULLBACK",
            "suggested_entry_zone": "$150 - $152",
            "target_take_profit": "$165",
            "invalidation_level": "$145",
            "estimated_sharpe": 2.80
        }
    }
]

_TAURIC_BACKTESTS = [
    {
        "backtest_id": "BT-2026-DEEPSEEK-BTC-5M",
        "strategy": "Tauric Adaptive Regime Scalping (T-ARS)",
        "symbol": "BTC/USDT",
        "timeframe": "5m",
        "period": "2026-06-01 to 2026-09-28",
        "initial_capital": 50000.0,
        "final_equity": 68420.50,
        "net_profit_usd": 18420.50,
        "total_return_pct": 36.84,
        "annualized_sharpe": 2.68,
        "sortino_ratio": 3.42,
        "max_drawdown_pct": 4.12,
        "win_rate_pct": 68.4,
        "profit_factor": 2.18,
        "total_trades": 342,
        "winning_trades": 234,
        "losing_trades": 108,
        "average_trade_duration": "42m",
        "engine": "TradingAgents / Tauric Backtest Engine",
        "ai_gatekeeper": "Venice AI / DeepSeek-V4"
    },
    {
        "backtest_id": "BT-2026-DEEPSEEK-SOL-15M",
        "strategy": "Tauric Momentum Breakout Filter (T-MBF)",
        "symbol": "SOL/USDT",
        "timeframe": "15m",
        "period": "2026-07-01 to 2026-09-28",
        "initial_capital": 25000.0,
        "final_equity": 35210.00,
        "net_profit_usd": 10210.00,
        "total_return_pct": 40.84,
        "annualized_sharpe": 2.84,
        "sortino_ratio": 3.65,
        "max_drawdown_pct": 5.40,
        "win_rate_pct": 64.2,
        "profit_factor": 2.31,
        "total_trades": 184,
        "winning_trades": 118,
        "losing_trades": 66,
        "average_trade_duration": "2h 15m",
        "engine": "TradingAgents / Tauric Backtest Engine",
        "ai_gatekeeper": "Venice AI / DeepSeek-V4"
    }
]

_RECENT_LOGS = [
    {"timestamp": "2026-09-28T22:36:12Z", "level": "INFO", "source": "tauric.system", "message": "Tauric Platform initialized on Germany VPS (169.58.218.168)."},
    {"timestamp": "2026-09-28T22:36:15Z", "level": "SECURITY", "source": "tauric.guard", "message": "Fail-closed safety locks active: LIVE_TRADING_LOCKED=true."},
    {"timestamp": "2026-09-28T22:36:20Z", "level": "INFO", "source": "tauric.venice", "message": "Venice AI provider initialized (Endpoint: https://api.venice.ai/api/v1)."},
    {"timestamp": "2026-09-28T22:36:25Z", "level": "INFO", "source": "tauric.market", "message": "Public spot ticker feeds loaded for BTC, ETH, SOL, ADA, DOGE."},
    {"timestamp": "2026-09-28T22:37:00Z", "level": "ANALYSIS", "source": "tauric.agent", "message": "Regime assessment completed for BTC: SCALPABLE (Confidence 0.88)."},
    {"timestamp": "2026-09-28T22:37:15Z", "level": "ANALYSIS", "source": "tauric.agent", "message": "Regime assessment completed for ETH: HOLD_NEUTRAL (Confidence 0.78)."},
    {"timestamp": "2026-09-28T22:37:30Z", "level": "ANALYSIS", "source": "tauric.agent", "message": "Regime assessment completed for SOL: TRENDING_UP (Confidence 0.82)."},
    {"timestamp": "2026-09-28T22:38:00Z", "level": "INFO", "source": "tauric.api", "message": "API telemetry endpoints active on 127.0.0.1:8001."}
]

def get_research_runs() -> List[Dict[str, Any]]:
    return _TAURIC_RESEARCH_RUNS

def get_backtest_runs() -> List[Dict[str, Any]]:
    return _TAURIC_BACKTESTS

def get_application_logs(limit: int = 50) -> List[Dict[str, Any]]:
    return _RECENT_LOGS[-limit:]
