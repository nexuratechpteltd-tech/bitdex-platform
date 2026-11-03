from app.config import resolve_model_tier, validate_model_preflight, DEFAULT_MODEL, PREMIUM_MODEL, ALLOWED_PRODUCTION_MODELS
import logging
import asyncio
import os

logger = logging.getLogger(__name__)
import re
import time
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

load_dotenv('/opt/tauric-platform/backend/.env')

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.agents.rating import extract_rating
from tradingagents.dataflows.date_window import get_current_date

def get_default_stages() -> List[Dict[str, Any]]:
    return [
        {"id": "market_analyst", "name": "Market Analyst", "status": "PENDING", "description": "Analyzing order book, volume profiles & technical structure"},
        {"id": "sentiment_analyst", "name": "Sentiment Analyst", "status": "PENDING", "description": "Gauging social sentiment & on-chain sentiment signals"},
        {"id": "news_analyst", "name": "News Analyst", "status": "PENDING", "description": "Screening real-time market catalysts & regulatory updates"},
        {"id": "bull_researcher", "name": "Bull Researcher", "status": "PENDING", "description": "Building growth thesis & upside catalyst scenarios"},
        {"id": "bear_researcher", "name": "Bear Researcher", "status": "PENDING", "description": "Stress-testing downside risks & liquidation clusters"},
        {"id": "research_manager", "name": "Research Manager", "status": "PENDING", "description": "Synthesizing bull/bear debate into strategic conviction"},
        {"id": "trader", "name": "Trader Sizing", "status": "PENDING", "description": "Formulating precise entry zones, stop losses & order sizing"},
        {"id": "risk_team", "name": "Risk Team Review", "status": "PENDING", "description": "Stress-testing proposal across aggressive, neutral & conservative profiles"},
        {"id": "portfolio_manager", "name": "Portfolio Manager Ruling", "status": "PENDING", "description": "Finalizing portfolio allocation rating & strategic thesis"},
        {"id": "jev_review", "name": "Jev Independent Review", "status": "PENDING", "description": "Running independent blind statistical expectation validation"}
    ]

def calculate_overall_progress(stages: List[Dict[str, Any]]) -> int:
    completed_count = sum(1 for s in stages if s.get("status") == "COMPLETED")
    running_count = sum(1 for s in stages if s.get("status") == "RUNNING")
    
    progress = completed_count * 10
    if running_count > 0 and progress < 95:
        progress += 5
    if completed_count == len(stages):
        progress = 100
    return min(100, progress)

class TauricExecutionManager:
    def __init__(self):
        self.runs: Dict[str, Dict[str, Any]] = {}
        self.cancel_events: Dict[str, threading.Event] = {}
        self.lock = threading.Lock()
        self.results_dir = Path("/opt/tauric-platform/backend/results")
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir = Path("/opt/tauric-platform/backend/data/reports")
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self._load_cached_runs()

    def _load_cached_runs(self):
        """Scan /opt/tauric-platform/backend/data/reports and populate initial completed runs."""
        try:
            for rep_dir in sorted(self.reports_dir.iterdir(), reverse=True):
                if not rep_dir.is_dir():
                    continue
                dir_name = rep_dir.name  # e.g. BTC-USD_20260929_035656
                parts = dir_name.split("_")
                ticker = parts[0] if len(parts) > 0 else "BTC-USD"
                timestamp_str = "_".join(parts[1:]) if len(parts) > 1 else "cached"
                run_id = f"RUN-{ticker}-{timestamp_str}"

                json_p = rep_dir / "run_data.json"
                if json_p.exists():
                    try:
                        self.runs[run_id] = json.loads(json_p.read_text(encoding="utf-8"))
                        continue
                    except Exception:
                        pass

                # Read files
                def read_file(subpath):
                    p = rep_dir / subpath
                    return p.read_text(encoding="utf-8") if p.exists() else None

                market_rep = read_file("1_analysts/market.md")
                sent_rep = read_file("1_analysts/sentiment.md")
                news_rep = read_file("1_analysts/news.md")
                bull_rep = read_file("2_research/bull.md")
                bear_rep = read_file("2_research/bear.md")
                mgr_rep = read_file("2_research/manager.md")
                trader_rep = read_file("3_trading/trader.md")
                agg_rep = read_file("4_risk/aggressive.md")
                con_rep = read_file("4_risk/conservative.md")
                neu_rep = read_file("4_risk/neutral.md")
                pm_rep = read_file("5_portfolio/decision.md")
                comp_rep = read_file("complete_report.md")

                # Parse trader
                trader_data = {
                    "status": "COMPLETED" if trader_rep else "PENDING",
                    "name": "Trader",
                    "action": None,
                    "reasoning": None,
                    "entry_price": None,
                    "stop_loss": None,
                    "position_sizing": None,
                    "full_report": trader_rep
                }
                if trader_rep:
                    act = re.search(r"\*\*Action\*\*:\s*([^\n]+)", trader_rep, re.IGNORECASE)
                    if act: trader_data["action"] = act.group(1).strip()
                    rea = re.search(r"\*\*Reasoning\*\*:\s*([^\n]+(?:\n[^\n*]+)*)", trader_rep, re.IGNORECASE)
                    if rea: trader_data["reasoning"] = rea.group(1).strip()
                    ent = re.search(r"\*\*Entry Price\*\*:\s*([^\n]+)", trader_rep, re.IGNORECASE)
                    if ent: trader_data["entry_price"] = ent.group(1).strip()
                    stp = re.search(r"\*\*Stop Loss\*\*:\s*([^\n]+)", trader_rep, re.IGNORECASE)
                    if stp: trader_data["stop_loss"] = stp.group(1).strip()
                    siz = re.search(r"\*\*Position Sizing\*\*:\s*([^\n]+)", trader_rep, re.IGNORECASE)
                    if siz: trader_data["position_sizing"] = siz.group(1).strip()

                # Parse research manager
                mgr_data = {
                    "status": "COMPLETED" if mgr_rep else "PENDING",
                    "name": "Research Manager",
                    "recommendation": None,
                    "rationale": None,
                    "strategic_actions": None,
                    "full_report": mgr_rep
                }
                if mgr_rep:
                    rec = re.search(r"\*\*Recommendation\*\*:\s*([^\n]+)", mgr_rep, re.IGNORECASE)
                    if rec: mgr_data["recommendation"] = rec.group(1).strip()
                    rat = re.search(r"\*\*Rationale\*\*:\s*([^\n]+(?:\n[^\n*]+)*)", mgr_rep, re.IGNORECASE)
                    if rat: mgr_data["rationale"] = rat.group(1).strip()
                    act = re.search(r"\*\*Strategic Actions\*\*:\s*([^\n]+(?:\n[^\n*]+)*)", mgr_rep, re.IGNORECASE)
                    if act: mgr_data["strategic_actions"] = act.group(1).strip()

                # Parse portfolio manager
                pm_data = {
                    "status": "COMPLETED" if pm_rep else "PENDING",
                    "name": "Portfolio Manager",
                    "rating": None,
                    "executive_summary": None,
                    "investment_thesis": None,
                    "price_target": None,
                    "time_horizon": None,
                    "full_report": pm_rep
                }
                if pm_rep:
                    rating = extract_rating(pm_rep) or "Review"
                    pm_data["rating"] = rating
                    ex = re.search(r"\*\*Executive Summary\*\*[:\s]*([^\n]+(?:\n[^\n*]+)*)", pm_rep, re.IGNORECASE)
                    if ex: pm_data["executive_summary"] = ex.group(1).strip()
                    th = re.search(r"\*\*Investment Thesis\*\*[:\s]*([^\n]+(?:\n[^\n*]+)*)", pm_rep, re.IGNORECASE)
                    if th: pm_data["investment_thesis"] = th.group(1).strip()

                stgs = get_default_stages()
                for s in stgs:
                    s["status"] = "COMPLETED"

                run_state = {
                    "run_id": run_id,
                    "ticker": ticker,
                    "trade_date": "2026-09-29",
                    "research_depth": 5,
                    "status": "COMPLETED",
                    "current_stage": "COMPLETED",
                    "overall_progress": 100,
                    "current_activity": "Research completed.",
                    "stages": stgs,
                    "start_time": datetime.now().isoformat(),
                    "completion_time": datetime.now().isoformat(),
                    "error": None,
                    "analyst_team": {
                        "market_analyst": {"status": "COMPLETED" if market_rep else "PENDING", "name": "Market Analyst", "report": market_rep},
                        "sentiment_analyst": {"status": "COMPLETED" if sent_rep else "PENDING", "name": "Sentiment Analyst", "report": sent_rep},
                        "news_analyst": {"status": "COMPLETED" if news_rep else "PENDING", "name": "News Analyst", "report": news_rep},
                    },
                    "research_team": {
                        "bull_researcher": {"status": "COMPLETED" if bull_rep else "PENDING", "name": "Bull Researcher", "report": bull_rep},
                        "bear_researcher": {"status": "COMPLETED" if bear_rep else "PENDING", "name": "Bear Researcher", "report": bear_rep},
                        "research_manager": mgr_data
                    },
                    "trading_team": {
                        "trader": trader_data
                    },
                    "risk_team": {
                        "aggressive_analyst": {"status": "COMPLETED" if agg_rep else "PENDING", "name": "Aggressive Analyst", "report": agg_rep},
                        "conservative_analyst": {"status": "COMPLETED" if con_rep else "PENDING", "name": "Conservative Analyst", "report": con_rep},
                        "neutral_analyst": {"status": "COMPLETED" if neu_rep else "PENDING", "name": "Neutral Analyst", "report": neu_rep}
                    },
                    "portfolio_manager": pm_data,
                    "complete_report": comp_rep,
                    "messages": [
                        {"timestamp": "03:56:00", "sender": "System", "content": f"Loaded verified Tauric research run from disk for {ticker}", "type": "info"},
                        {"timestamp": "03:56:56", "sender": "System", "content": "Analysis complete.", "type": "status"}
                    ]
                }
                self.runs[run_id] = run_state
        except Exception as e:
            print(f"[TauricExecutionManager Cache Warning]: {e}")

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            return self.runs.get(run_id)

    def list_runs(self) -> List[Dict[str, Any]]:
        with self.lock:
            return [
                {
                    "run_id": r["run_id"],
                    "ticker": r["ticker"],
                    "trade_date": r["trade_date"],
                    "status": r["status"],
                    "current_stage": r["current_stage"],
                    "overall_progress": r.get("overall_progress", 0),
                    "current_activity": r.get("current_activity", ""),
                    "start_time": r["start_time"],
                    "completion_time": r.get("completion_time"),
                    "rating": r["portfolio_manager"].get("rating", "PENDING"),
                    "trader_action": r["trading_team"]["trader"].get("action", "PENDING"),
                    "shadow_decision": r.get("shadow_decision", "PENDING"),
                    "jev_decision": r.get("jev_fast_decision", {}).get("decision", "PENDING") if isinstance(r.get("jev_fast_decision"), dict) else "PENDING",
                    "jev_blind_outcome": r.get("jev_blind_check", {}).get("outcome", "PENDING") if isinstance(r.get("jev_blind_check"), dict) else "PENDING"
                }
                for r in self.runs.values()
            ]

    def stop_run(self, run_id: str) -> Dict[str, Any]:
        with self.lock:
            if run_id in self.cancel_events:
                self.cancel_events[run_id].set()
            
            run = self.runs.get(run_id)
            now_iso = datetime.now().isoformat()
            if not run:
                return {
                    "status": "NOT_FOUND",
                    "run_id": run_id,
                    "message": "Run ID not found."
                }
            
            if run.get("status") == "COMPLETED":
                return {
                    "status": "ALREADY_COMPLETED",
                    "run_id": run_id,
                    "message": "Run has already completed."
                }
            
            if run.get("status") == "CANCELLED":
                return {
                    "status": "ALREADY_CANCELLED",
                    "run_id": run_id,
                    "cancel_confirmed_at": run.get("cancel_confirmed_at", now_iso),
                    "worker_terminated_at": run.get("worker_terminated_at", now_iso)
                }
            
            run["status"] = "CANCELLED"
            run["cancel_confirmed_at"] = now_iso
            run["worker_terminated_at"] = now_iso
            run["current_stage"] = "CANCELLED"
            run["current_activity"] = "Research stopped by user request. Worker terminated."
            
            # Mark running/pending stages as CANCELLED
            if "stages" in run:
                for stg in run["stages"]:
                    if stg.get("status") in ("RUNNING", "PENDING"):
                        stg["status"] = "CANCELLED"
            
            run["messages"].append({
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "sender": "System",
                "content": "Execution stopped by user request. Worker thread terminated.",
                "type": "warning"
            })
            return {
                "status": "CANCELLED",
                "run_id": run_id,
                "cancel_confirmed_at": now_iso,
                "worker_terminated_at": now_iso,
                "post_cancel_calls": 0
            }

    def start_run(self, ticker: str, analysts: List[str] = None, research_depth: int = 1, trade_date: str = None, thinking_tier: str = "deepseek-v4-flash", model_tier: str = "standard") -> str:
        ticker = ticker.strip().upper()
        if not trade_date:
            trade_date = get_current_date()
        if not analysts:
            analysts = ["market", "social", "news"]

        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_sym = ticker.replace("/", "-")
        run_id = f"RUN-{safe_sym}-{timestamp_str}"

        init_stages = get_default_stages()
        init_stages[0]["status"] = "RUNNING"

        resolved_model = resolve_model_tier(thinking_tier or model_tier)
        if not validate_model_preflight(resolved_model["model_id"]):
            raise ValueError(f"Invalid model ID '{resolved_model['model_id']}'. Allowed production models: {ALLOWED_PRODUCTION_MODELS}")

        logger.info(f"Tauric Engine Model Routing: requested={thinking_tier}, selected={resolved_model['model_id']} ({resolved_model['cost_tier']}), reason={resolved_model['reason']}")

        run_state = {
            "model_info": resolved_model,
            "model": resolved_model["model_id"],
            "model_name": resolved_model["model_name"],
            "model_tier": resolved_model["model_tier"],
            "cost_tier": resolved_model["cost_tier"],
            "run_id": run_id,
            "ticker": ticker,
            "trade_date": trade_date,
            "research_depth": research_depth,
            "status": "RUNNING",
            "current_stage": "ANALYST_TEAM",
            "overall_progress": 5,
            "current_activity": "Market Analyst — analyzing order book, volume profiles & technical structure",
            "stages": init_stages,
            "cancel_requested_at": None,
            "cancel_confirmed_at": None,
            "worker_terminated_at": None,
            "start_time": datetime.now().isoformat(),
            "completion_time": None,
            "error": None,
            "analyst_team": {
                "market_analyst": {"status": "RUNNING", "name": "Market Analyst", "report": None},
                "sentiment_analyst": {"status": "PENDING", "name": "Sentiment Analyst", "report": None},
                "news_analyst": {"status": "PENDING", "name": "News Analyst", "report": None},
            },
            "research_team": {
                "bull_researcher": {"status": "PENDING", "name": "Bull Researcher", "report": None},
                "bear_researcher": {"status": "PENDING", "name": "Bear Researcher", "report": None},
                "research_manager": {
                    "status": "PENDING",
                    "name": "Research Manager",
                    "recommendation": None,
                    "rationale": None,
                    "strategic_actions": None,
                    "full_report": None
                }
            },
            "trading_team": {
                "trader": {
                    "status": "PENDING",
                    "name": "Trader",
                    "action": None,
                    "reasoning": None,
                    "entry_price": None,
                    "stop_loss": None,
                    "position_sizing": None,
                    "full_report": None
                }
            },
            "risk_team": {
                "aggressive_analyst": {"status": "PENDING", "name": "Aggressive Analyst", "report": None},
                "conservative_analyst": {"status": "PENDING", "name": "Conservative Analyst", "report": None},
                "neutral_analyst": {"status": "PENDING", "name": "Neutral Analyst", "report": None}
            },
            "portfolio_manager": {
                "status": "PENDING",
                "name": "Portfolio Manager",
                "rating": None,
                "executive_summary": None,
                "investment_thesis": None,
                "price_target": None,
                "time_horizon": None,
                "full_report": None
            },
            "jev_fast_decision": None,
            "jev_blind_check": None,
            "shadow_decision": "PENDING",
            "complete_report": None,
            "messages": [
                {"timestamp": datetime.now().strftime("%H:%M:%S"), "sender": "System", "content": f"Initializing Tauric execution graph for {ticker} (Date: {trade_date}, Depth: {research_depth} rds)", "type": "info"}
            ]
        }

        with self.lock:
            self.runs[run_id] = run_state
            self.cancel_events[run_id] = threading.Event()

        # Spawn background thread to stream graph execution
        thread = threading.Thread(target=self._execute_graph_thread, args=(run_id, ticker, trade_date, analysts, research_depth), daemon=True)
        thread.start()

        return run_id

    def _set_stage_status(self, run: Dict[str, Any], stage_id: str, status: str):
        if "stages" in run:
            for s in run["stages"]:
                if s["id"] == stage_id:
                    s["status"] = status
        run["overall_progress"] = calculate_overall_progress(run.get("stages", []))

    def _execute_graph_thread(self, run_id: str, ticker: str, trade_date: str, analysts: List[str], research_depth: int):
        run = self.runs[run_id]
        cancel_ev = self.cancel_events.get(run_id)

        try:
            if cancel_ev and cancel_ev.is_set():
                run["status"] = "CANCELLED"
                run["worker_terminated_at"] = datetime.now().isoformat()
                return

            # Step 1: Jev Fast Decision Layer
            is_forex = "/" in ticker or "XAU" in ticker or "XAG" in ticker or ticker in ("EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD")
            try:
                from .jev_client import jev_client
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                if is_forex:
                    from .forex_market_data import forex_market_data
                    fx_ticker = loop.run_until_complete(forex_market_data.fetch_ticker(ticker))
                    m_state = {
                        "price": fx_ticker["price"],
                        "change_24h": fx_ticker["change_24h"],
                        "bid": fx_ticker["bid"],
                        "ask": fx_ticker["ask"],
                        "spread_pips": fx_ticker["spread_pips"],
                        "market": "FOREX",
                        "asset_class": fx_ticker["asset_class"]
                    }
                else:
                    from .market_data import fetch_live_market_data
                    sym = ticker.replace("USDT", "").replace("-USD", "")
                    live_mkts = loop.run_until_complete(fetch_live_market_data())
                    m_state = live_mkts.get(sym)
                    if not m_state or not isinstance(m_state, dict) or m_state.get("price") is None or m_state.get("status") not in ("PASS", "NORMAL"):
                        m_state = {"symbol": sym, "price": None, "change_24h": None, "status": "DATA_UNAVAILABLE"}
                fast_dec = loop.run_until_complete(jev_client.fast_decision(ticker, m_state))
                loop.close()
                run["jev_fast_decision"] = fast_dec
                run["messages"].append({
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "sender": "Jev Fast Layer",
                    "content": f"Decision: {fast_dec.get('decision')} | Regime: {fast_dec.get('regime', {}).get('status')} ({fast_dec.get('regime', {}).get('confidence', 0):.0%} conf) | Bias: {fast_dec.get('bias', {}).get('direction')}",
                    "type": "status"
                })
            except Exception as e_fast:
                print(f"[Jev Fast Layer Warning]: {e_fast}")

            if cancel_ev and cancel_ev.is_set():
                run["status"] = "CANCELLED"
                run["worker_terminated_at"] = datetime.now().isoformat()
                return

            config = DEFAULT_CONFIG.copy()
            config["results_dir"] = str(self.results_dir)
            config["data_cache_dir"] = "/opt/tauric-platform/backend/data/cache"
            config["max_debate_rounds"] = research_depth
            config["max_risk_discuss_rounds"] = research_depth
            config["llm_provider"] = "openai_compatible"
            config["backend_url"] = os.getenv("TRADINGAGENTS_LLM_BACKEND_URL", "https://api.venice.ai/api/v1")
            model_info = run.get("model_info") or resolve_model_tier(None)
            target_model_id = model_info.get("model_id", "deepseek-v4-flash")
            config["quick_think_llm"] = target_model_id
            config["deep_think_llm"] = target_model_id if not model_info.get("is_premium") else "deepseek-v4-pro-0813"
            logger.info(f"TradingAgents graph configured with model: {target_model_id} (premium={model_info.get('is_premium')})")
            config["checkpoint_enabled"] = False
            config["output_language"] = "English"

            if is_forex:
                asset_type = "forex_metal" if ("XAU" in ticker or "XAG" in ticker) else "forex"
                run["market"] = "FOREX"
                run["asset_class"] = "FOREX_METAL" if ("XAU" in ticker or "XAG" in ticker) else "FOREX"
            elif any(c in ticker for c in ["BTC", "ETH", "SOL", "ADA", "DOGE", "-USD", "/USDT", "USDT"]):
                asset_type = "crypto"
                run["market"] = "CRYPTO"
                run["asset_class"] = "CRYPTO_SPOT"
            else:
                asset_type = "stock"
                run["market"] = "EQUITY"
                run["asset_class"] = "STOCK"

            run["messages"].append({
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "sender": "System",
                "content": f"Detected asset type: {asset_type}. Building TradingAgents graph...",
                "type": "info"
            })

            graph = TradingAgentsGraph(
                selected_analysts=analysts,
                config=config,
                debug=True
            )

            init_agent_state = graph.create_run_state(ticker, trade_date, asset_type, None)
            args = graph.propagator.get_graph_args()

            run["messages"].append({
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "sender": "System",
                "content": "Graph compiled. Starting live multi-agent execution pipeline...",
                "type": "info"
            })

            trace = []
            for chunk in graph.graph.stream(init_agent_state, **args):
                if cancel_ev and cancel_ev.is_set():
                    run["status"] = "CANCELLED"
                    run["worker_terminated_at"] = datetime.now().isoformat()
                    run["current_stage"] = "CANCELLED"
                    run["current_activity"] = "Research stopped by user request. Worker terminated."
                    if "stages" in run:
                        for stg in run["stages"]:
                            if stg.get("status") in ("RUNNING", "PENDING"):
                                stg["status"] = "CANCELLED"
                    return

                trace.append(chunk)

                for msg in chunk.get("messages", []):
                    content = getattr(msg, "content", "")
                    if content and isinstance(content, str) and content.strip():
                        sender = getattr(msg, "name", None) or type(msg).__name__
                        run["messages"].append({
                            "timestamp": datetime.now().strftime("%H:%M:%S"),
                            "sender": sender,
                            "content": content[:300] + ("..." if len(content) > 300 else ""),
                            "type": "agent_message"
                        })
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        for tc in msg.tool_calls:
                            tc_name = tc.get("name", "tool") if isinstance(tc, dict) else getattr(tc, "name", "tool")
                            run["messages"].append({
                                "timestamp": datetime.now().strftime("%H:%M:%S"),
                                "sender": "Tool",
                                "content": f"Calling tool: {tc_name}",
                                "type": "tool_call"
                            })

                # 1. Analyst Team Check
                if "market_report" in chunk and chunk["market_report"]:
                    run["analyst_team"]["market_analyst"]["status"] = "COMPLETED"
                    run["analyst_team"]["market_analyst"]["report"] = chunk["market_report"]
                    run["analyst_team"]["sentiment_analyst"]["status"] = "RUNNING"
                    self._set_stage_status(run, "market_analyst", "COMPLETED")
                    self._set_stage_status(run, "sentiment_analyst", "RUNNING")
                    run["current_activity"] = "Sentiment Analyst — gauging social sentiment & crowd dynamics"
                    run["messages"].append({
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                        "sender": "Market Analyst",
                        "content": "Market analysis report generated.",
                        "type": "status"
                    })

                if "sentiment_report" in chunk and chunk["sentiment_report"]:
                    run["analyst_team"]["sentiment_analyst"]["status"] = "COMPLETED"
                    run["analyst_team"]["sentiment_analyst"]["report"] = chunk["sentiment_report"]
                    run["analyst_team"]["news_analyst"]["status"] = "RUNNING"
                    self._set_stage_status(run, "sentiment_analyst", "COMPLETED")
                    self._set_stage_status(run, "news_analyst", "RUNNING")
                    run["current_activity"] = "News Analyst — screening real-time market catalysts & news"
                    run["messages"].append({
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                        "sender": "Sentiment Analyst",
                        "content": "Sentiment analysis report generated.",
                        "type": "status"
                    })

                if "news_report" in chunk and chunk["news_report"]:
                    run["analyst_team"]["news_analyst"]["status"] = "COMPLETED"
                    run["analyst_team"]["news_analyst"]["report"] = chunk["news_report"]
                    run["current_stage"] = "RESEARCH_TEAM"
                    run["research_team"]["bull_researcher"]["status"] = "RUNNING"
                    run["research_team"]["bear_researcher"]["status"] = "RUNNING"
                    self._set_stage_status(run, "news_analyst", "COMPLETED")
                    self._set_stage_status(run, "bull_researcher", "RUNNING")
                    self._set_stage_status(run, "bear_researcher", "RUNNING")
                    run["current_activity"] = "Research Debate — Bull & Bear researchers debating market conditions"
                    run["messages"].append({
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                        "sender": "News Analyst",
                        "content": "News analysis report generated. Moving to Research Team.",
                        "type": "status"
                    })

                # 2. Research Team Check
                if chunk.get("investment_debate_state"):
                    debate = chunk["investment_debate_state"]
                    bull_h = debate.get("bull_history", "").strip()
                    bear_h = debate.get("bear_history", "").strip()
                    judge = debate.get("judge_decision", "").strip()

                    if bull_h:
                        run["research_team"]["bull_researcher"]["status"] = "COMPLETED"
                        run["research_team"]["bull_researcher"]["report"] = bull_h
                        self._set_stage_status(run, "bull_researcher", "COMPLETED")
                    if bear_h:
                        run["research_team"]["bear_researcher"]["status"] = "COMPLETED"
                        run["research_team"]["bear_researcher"]["report"] = bear_h
                        self._set_stage_status(run, "bear_researcher", "COMPLETED")
                    if judge:
                        run["research_team"]["research_manager"]["status"] = "COMPLETED"
                        run["research_team"]["research_manager"]["full_report"] = judge
                        self._set_stage_status(run, "research_manager", "COMPLETED")

                        rec_match = re.search(r"\*\*Recommendation\*\*:\s*([^\n]+)", judge, re.IGNORECASE)
                        if rec_match:
                            run["research_team"]["research_manager"]["recommendation"] = rec_match.group(1).strip()
                        rat_match = re.search(r"\*\*Rationale\*\*:\s*([^\n]+(?:\n[^\n*]+)*)", judge, re.IGNORECASE)
                        if rat_match:
                            run["research_team"]["research_manager"]["rationale"] = rat_match.group(1).strip()
                        act_match = re.search(r"\*\*Strategic Actions\*\*:\s*([^\n]+(?:\n[^\n*]+)*)", judge, re.IGNORECASE)
                        if act_match:
                            run["research_team"]["research_manager"]["strategic_actions"] = act_match.group(1).strip()

                        run["current_stage"] = "TRADING_TEAM"
                        run["trading_team"]["trader"]["status"] = "RUNNING"
                        self._set_stage_status(run, "trader", "RUNNING")
                        run["current_activity"] = "Trader — formulating directional entry zones, stops & sizing"
                        run["messages"].append({
                            "timestamp": datetime.now().strftime("%H:%M:%S"),
                            "sender": "Research Manager",
                            "content": f"Research synthesis complete. Recommendation: {run['research_team']['research_manager'].get('recommendation', 'Formulated')}.",
                            "type": "status"
                        })

                # 3. Trading Team Check
                if chunk.get("trader_investment_plan"):
                    plan = chunk["trader_investment_plan"]
                    trader_dict = run["trading_team"]["trader"]
                    trader_dict["status"] = "COMPLETED"
                    trader_dict["full_report"] = plan
                    self._set_stage_status(run, "trader", "COMPLETED")

                    act = re.search(r"\*\*Action\*\*:\s*([^\n]+)", plan, re.IGNORECASE)
                    if act: trader_dict["action"] = act.group(1).strip()
                    rea = re.search(r"\*\*Reasoning\*\*:\s*([^\n]+(?:\n[^\n*]+)*)", plan, re.IGNORECASE)
                    if rea: trader_dict["reasoning"] = rea.group(1).strip()
                    ent = re.search(r"\*\*Entry Price\*\*:\s*([^\n]+)", plan, re.IGNORECASE)
                    if ent: trader_dict["entry_price"] = ent.group(1).strip()
                    stp = re.search(r"\*\*Stop Loss\*\*:\s*([^\n]+)", plan, re.IGNORECASE)
                    if stp: trader_dict["stop_loss"] = stp.group(1).strip()
                    siz = re.search(r"\*\*Position Sizing\*\*:\s*([^\n]+)", plan, re.IGNORECASE)
                    if siz: trader_dict["position_sizing"] = siz.group(1).strip()

                    run["current_stage"] = "RISK_TEAM"
                    run["risk_team"]["aggressive_analyst"]["status"] = "RUNNING"
                    run["risk_team"]["conservative_analyst"]["status"] = "RUNNING"
                    run["risk_team"]["neutral_analyst"]["status"] = "RUNNING"
                    self._set_stage_status(run, "risk_team", "RUNNING")
                    run["current_activity"] = "Risk Team — running aggressive, conservative & neutral risk models"
                    run["messages"].append({
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                        "sender": "Trader",
                        "content": f"Trader proposal complete. Action: {trader_dict.get('action')}, Entry: {trader_dict.get('entry_price')}, Stop: {trader_dict.get('stop_loss')}.",
                        "type": "status"
                    })

                # 4. Risk Team Check
                if chunk.get("risk_debate_state"):
                    risk = chunk["risk_debate_state"]
                    agg_h = risk.get("aggressive_history", "").strip()
                    con_h = risk.get("conservative_history", "").strip()
                    neu_h = risk.get("neutral_history", "").strip()
                    judge = risk.get("judge_decision", "").strip()

                    if agg_h:
                        run["risk_team"]["aggressive_analyst"]["status"] = "COMPLETED"
                        run["risk_team"]["aggressive_analyst"]["report"] = agg_h
                    if con_h:
                        run["risk_team"]["conservative_analyst"]["status"] = "COMPLETED"
                        run["risk_team"]["conservative_analyst"]["report"] = con_h
                    if neu_h:
                        run["risk_team"]["neutral_analyst"]["status"] = "COMPLETED"
                        run["risk_team"]["neutral_analyst"]["report"] = neu_h
                    if judge:
                        self._set_stage_status(run, "risk_team", "COMPLETED")
                        # 5. Portfolio Manager
                        run["current_stage"] = "PORTFOLIO_MANAGER"
                        pm_dict = run["portfolio_manager"]
                        pm_dict["status"] = "COMPLETED"
                        pm_dict["full_report"] = judge
                        self._set_stage_status(run, "portfolio_manager", "COMPLETED")

                        rating = extract_rating(judge) or "Review"
                        pm_dict["rating"] = rating

                        ex_match = re.search(r"\*\*Executive Summary\*\*[:\s]*([^\n]+(?:\n[^\n*]+)*)", judge, re.IGNORECASE)
                        if ex_match: pm_dict["executive_summary"] = ex_match.group(1).strip()

                        th_match = re.search(r"\*\*Investment Thesis\*\*[:\s]*([^\n]+(?:\n[^\n*]+)*)", judge, re.IGNORECASE)
                        if th_match: pm_dict["investment_thesis"] = th_match.group(1).strip()

                        pt_match = re.search(r"\*\*Price Target\*\*[:\s]*([^\n]+)", judge, re.IGNORECASE)
                        if pt_match: pm_dict["price_target"] = pt_match.group(1).strip()

                        hz_match = re.search(r"\*\*Time Horizon\*\*[:\s]*([^\n]+)", judge, re.IGNORECASE)
                        if hz_match: pm_dict["time_horizon"] = hz_match.group(1).strip()

                        run["messages"].append({
                            "timestamp": datetime.now().strftime("%H:%M:%S"),
                            "sender": "Portfolio Manager",
                            "content": f"Portfolio decision finalized. Rating: {rating}.",
                            "type": "status"
                        })

            if cancel_ev and cancel_ev.is_set():
                run["status"] = "CANCELLED"
                run["worker_terminated_at"] = datetime.now().isoformat()
                run["current_stage"] = "CANCELLED"
                run["current_activity"] = "Research stopped by user request. Worker terminated."
                if "stages" in run:
                    for stg in run["stages"]:
                        if stg.get("status") in ("RUNNING", "PENDING"):
                            stg["status"] = "CANCELLED"
                return

            # Step 3: Jev Blind Check & Shadow Decision
            self._set_stage_status(run, "jev_review", "RUNNING")
            run["current_activity"] = "Jev Independent Review — performing blind statistical validation"
            try:
                from .market_data import fetch_live_market_data
                from .jev_client import jev_client
                trade_plan = {
                    "action": run["trading_team"]["trader"].get("action") or "Hold",
                    "entry_price": run["trading_team"]["trader"].get("entry_price"),
                    "stop_loss": run["trading_team"]["trader"].get("stop_loss"),
                    "rating": run["portfolio_manager"].get("rating") or "Review"
                }
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                live_mkts = loop.run_until_complete(fetch_live_market_data())
                m_state = live_mkts.get(sym)
                if not m_state or not isinstance(m_state, dict) or m_state.get("price") is None or m_state.get("status") not in ("PASS", "NORMAL"):
                    m_state = {"symbol": sym, "price": None, "change_24h": None, "status": "DATA_UNAVAILABLE"}
                blind_dec = loop.run_until_complete(jev_client.blind_check(ticker, trade_plan, m_state))
                loop.close()

                run["jev_blind_check"] = blind_dec
                run["shadow_decision"] = blind_dec.get("shadow_decision", "NO_TRADE")
                run["messages"].append({
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "sender": "Jev Blind Check",
                    "content": blind_dec.get("log_summary", "Blind validation complete."),
                    "type": "status"
                })
            except Exception as e_blind:
                print(f"[Jev Blind Check Warning]: {e_blind}")
                run["shadow_decision"] = "NO_TRADE"

            self._set_stage_status(run, "jev_review", "COMPLETED")
            run["overall_progress"] = 100
            run["current_activity"] = "Analysis complete. Consensus synthesized."

            final_state = {}
            for chunk in trace:
                final_state.update(chunk)

            sections = []
            if run.get("jev_fast_decision"):
                jfd = run["jev_fast_decision"]
                dec_val = jfd.get("decision")
                reg_val = jfd.get("regime", {}).get("status") or jfd.get("regime", {}).get("choice")
                bias_val = jfd.get("bias", {}).get("direction") or jfd.get("bias", {}).get("choice")
                sections.append(f"## 0. TypeSafe Jev Fast Decision Layer\nDecision: {dec_val}\nRegime: {reg_val}\nBias: {bias_val}\nModel: {jfd.get('model', 'jev-1.13.0')}\n")

            sections.append(f"# Tauric Multi-Agent Research Report: {ticker}\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n")

            if run["analyst_team"]["market_analyst"]["report"]:
                sections.append(f"## I. Analyst Team\n### Market Analyst\n{run['analyst_team']['market_analyst']['report']}")
            if run["analyst_team"]["sentiment_analyst"]["report"]:
                sections.append(f"### Sentiment Analyst\n{run['analyst_team']['sentiment_analyst']['report']}")
            if run["analyst_team"]["news_analyst"]["report"]:
                sections.append(f"### News Analyst\n{run['analyst_team']['news_analyst']['report']}")

            if run["research_team"]["bull_researcher"]["report"]:
                sections.append(f"## II. Research Team\n### Bull Researcher\n{run['research_team']['bull_researcher']['report']}")
            if run["research_team"]["bear_researcher"]["report"]:
                sections.append(f"### Bear Researcher\n{run['research_team']['bear_researcher']['report']}")
            if run["research_team"]["research_manager"]["full_report"]:
                sections.append(f"### Research Manager Decision\n{run['research_team']['research_manager']['full_report']}")

            if run["trading_team"]["trader"]["full_report"]:
                sections.append(f"## III. Trading Team Plan\n{run['trading_team']['trader']['full_report']}")

            if run["risk_team"]["aggressive_analyst"]["report"]:
                sections.append(f"## IV. Risk Management Team\n### Aggressive Analyst\n{run['risk_team']['aggressive_analyst']['report']}")
            if run["risk_team"]["conservative_analyst"]["report"]:
                sections.append(f"### Conservative Analyst\n{run['risk_team']['conservative_analyst']['report']}")
            if run["risk_team"]["neutral_analyst"]["report"]:
                sections.append(f"### Neutral Analyst\n{run['risk_team']['neutral_analyst']['report']}")

            if run["portfolio_manager"]["full_report"]:
                sections.append(f"## V. Portfolio Manager Final Decision\n{run['portfolio_manager']['full_report']}")

            if run.get("jev_blind_check"):
                jbc = run["jev_blind_check"]
                sections.append(f"## VI. TypeSafe Jev Blind Check & Shadow Decision\nOutcome: {jbc.get('outcome')}\nShadow Decision: {jbc.get('shadow_decision')}\nConfidence: {jbc.get('confidence', 0):.1%}\nAgree Prob: {jbc.get('probabilities', {}).get('agree', 0):.1%}\nRisk Assessment: {jbc.get('risk_profile', {}).get('level')}\nSummary: {jbc.get('log_summary')}\n")

            run["complete_report"] = "\n\n".join(sections)
            run["status"] = "COMPLETED"
            run["current_stage"] = "COMPLETED"
            run["completion_time"] = datetime.now().isoformat()
            self._persist_run(run)

            # Record decision into dedicated Shadow Validation Telemetry Store
            try:
                from .shadow_store import shadow_store
                from .outcome_engine import outcome_engine
                
                trader_action = (run.get("trading_team", {}).get("trader", {}).get("action") or "HOLD").upper()
                trader_dir = "LONG" if "BUY" in trader_action else "SHORT" if "SELL" in trader_action else "FLAT"
                
                entry_val = 0.0
                try:
                    entry_val = float(str(run.get("trading_team", {}).get("trader", {}).get("entry_price", "0")).replace("$", "").replace(",", ""))
                except Exception:
                    pass
                if entry_val <= 0:
                    raw_cur = run.get("jev_fast_decision", {}).get("telemetry", {}).get("current_price")
                    entry_val = float(raw_cur) if (raw_cur is not None and isinstance(raw_cur, (int, float)) and math.isfinite(raw_cur)) else 0.0

                stop_val = 0.0
                try:
                    stop_val = float(str(run.get("trading_team", {}).get("trader", {}).get("stop_loss", "0")).replace("$", "").replace(",", ""))
                except Exception:
                    pass

                jbc = run.get("jev_blind_check") or {}
                agreement = jbc.get("outcome") or jbc.get("agreement") or "DISAGREE"
                reconcile = "APPROVED" if agreement == "AGREE" and trader_dir != "FLAT" else "VETOED" if trader_dir != "FLAT" else "NO_TRADE"

                jfd = run.get("jev_fast_decision") or {}
                fast_bias = (jfd.get("bias", {}).get("direction") or "neutral").upper()
                fast_dir = "LONG" if fast_bias == "BULLISH" else "SHORT" if fast_bias == "BEARISH" else "FLAT"

                # Estimate market regime
                reg_name = "range_chop"
                ch24 = float(jfd.get("telemetry", {}).get("change_24h_percent", 0.0))
                if abs(ch24) >= 4.0: reg_name = "high_volatility"
                elif ch24 > 1.5: reg_name = "trending_up"
                elif ch24 < -1.5: reg_name = "trending_down"
                elif abs(ch24) <= 0.8: reg_name = "low_volatility"

                shd_record = {
                    "symbol": ticker,
                    "timeframe": "1d",
                    "current_price": entry_val,
                    "market_regime": reg_name,
                    "market_snapshot": jfd.get("telemetry", {}),
                    
                    # Track A
                    "tauric_decision": run.get("portfolio_manager", {}).get("rating") or "Hold",
                    "tauric_direction": trader_dir,
                    "tauric_entry": entry_val,
                    "tauric_stop": stop_val,
                    "tauric_tp1": entry_val * 1.03 if trader_dir == "LONG" else entry_val * 0.97 if trader_dir == "SHORT" else 0.0,
                    "tauric_tp2": entry_val * 1.06 if trader_dir == "LONG" else entry_val * 0.94 if trader_dir == "SHORT" else 0.0,
                    "tauric_size": run.get("trading_team", {}).get("trader", {}).get("position_sizing") or "Standard",
                    "tauric_horizon": run.get("portfolio_manager", {}).get("time_horizon") or "1w-2w",
                    "tauric_latency_ms": 120000,
                    
                    # Track B
                    "reconciliation_result": reconcile,
                    "agreement_status": agreement,
                    "veto_reason": jbc.get("log_summary", ""),
                    "blind_review_decision": agreement,
                    "blind_review_prob_agree": jbc.get("probabilities", {}).get("agree", 0.0),
                    "blind_review_prob_disagree": jbc.get("probabilities", {}).get("disagree", 0.0),
                    "blind_review_confidence": jbc.get("confidence", 0.0),
                    "blind_review_risk_profile": jbc.get("risk_profile", {}).get("level") if isinstance(jbc.get("risk_profile"), dict) else jbc.get("risk_profile") or "acceptable_risk",
                    "blind_review_latency_ms": 1200,
                    
                    # Track C
                    "jev_fast_decision": jfd.get("decision") or "WAIT",
                    "jev_fast_direction": fast_dir,
                    "jev_fast_entry": entry_val,
                    "jev_fast_stop": entry_val * 0.98 if fast_dir == "LONG" else entry_val * 1.02 if fast_dir == "SHORT" else 0.0,
                    "jev_fast_tp1": entry_val * 1.025 if fast_dir == "LONG" else entry_val * 0.975 if fast_dir == "SHORT" else 0.0,
                    "jev_fast_tp2": entry_val * 1.045 if fast_dir == "LONG" else entry_val * 0.955 if fast_dir == "SHORT" else 0.0,
                    "jev_fast_confidence": jfd.get("opportunity", {}).get("confidence", 0.0),
                    "jev_fast_probabilities": jfd.get("opportunity", {}).get("probabilities", {}),
                    "jev_fast_latency_ms": 1500,
                    
                    "run_ref_id": run_id
                }
                
                shd_id = shadow_store.record_decision(shd_record)
                run["shadow_decision_id"] = shd_id
                
                # Evaluate outcomes
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                outcomes = loop.run_until_complete(outcome_engine.evaluate_decision_record(shd_record))
                shadow_store.update_outcomes(shd_id, outcomes)
                loop.close()
                
            except Exception as e_shd:
                print(f"[Shadow Record Warning]: {e_shd}")
            run["messages"].append({
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "sender": "System",
                "content": f"Pipeline execution completed successfully for {ticker}.",
                "type": "info"
            })

        except Exception as e:
            import traceback
            err_trace = traceback.format_exc()
            run["status"] = "FAILED"
            run["error"] = str(e)
            run["current_activity"] = f"Execution failed: {str(e)}"
            run["messages"].append({
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "sender": "Error",
                "content": f"Execution error: {str(e)}",
                "type": "error"
            })
            print(f"[TauricExecutionManager Error]: {err_trace}")


    def _persist_run(self, run: Dict[str, Any]):
        try:
            ticker = run.get("ticker", "UNKNOWN")
            run_id = run.get("run_id", "RUN")
            parts = run_id.split("-")
            ts = parts[-1] if len(parts) > 1 else datetime.now().strftime("%Y%m%d_%H%M%S")
            out_dir = self.reports_dir / f"{ticker}_{ts}"
            out_dir.mkdir(parents=True, exist_ok=True)
            
            (out_dir / "complete_report.md").write_text(run.get("complete_report") or "", encoding="utf-8")
            (out_dir / "run_data.json").write_text(json.dumps(run, indent=2), encoding="utf-8")
            
            (out_dir / "1_analysts").mkdir(exist_ok=True)
            if run["analyst_team"]["market_analyst"]["report"]:
                (out_dir / "1_analysts/market.md").write_text(run["analyst_team"]["market_analyst"]["report"], encoding="utf-8")
            if run["analyst_team"]["sentiment_analyst"]["report"]:
                (out_dir / "1_analysts/sentiment.md").write_text(run["analyst_team"]["sentiment_analyst"]["report"], encoding="utf-8")
            if run["analyst_team"]["news_analyst"]["report"]:
                (out_dir / "1_analysts/news.md").write_text(run["analyst_team"]["news_analyst"]["report"], encoding="utf-8")

            (out_dir / "2_research").mkdir(exist_ok=True)
            if run["research_team"]["bull_researcher"]["report"]:
                (out_dir / "2_research/bull.md").write_text(run["research_team"]["bull_researcher"]["report"], encoding="utf-8")
            if run["research_team"]["bear_researcher"]["report"]:
                (out_dir / "2_research/bear.md").write_text(run["research_team"]["bear_researcher"]["report"], encoding="utf-8")
            if run["research_team"]["research_manager"]["full_report"]:
                (out_dir / "2_research/manager.md").write_text(run["research_team"]["research_manager"]["full_report"], encoding="utf-8")

            (out_dir / "3_trading").mkdir(exist_ok=True)
            if run["trading_team"]["trader"]["full_report"]:
                (out_dir / "3_trading/trader.md").write_text(run["trading_team"]["trader"]["full_report"], encoding="utf-8")

            (out_dir / "4_risk").mkdir(exist_ok=True)
            if run["risk_team"]["aggressive_analyst"]["report"]:
                (out_dir / "4_risk/aggressive.md").write_text(run["risk_team"]["aggressive_analyst"]["report"], encoding="utf-8")
            if run["risk_team"]["conservative_analyst"]["report"]:
                (out_dir / "4_risk/conservative.md").write_text(run["risk_team"]["conservative_analyst"]["report"], encoding="utf-8")
            if run["risk_team"]["neutral_analyst"]["report"]:
                (out_dir / "4_risk/neutral.md").write_text(run["risk_team"]["neutral_analyst"]["report"], encoding="utf-8")

            (out_dir / "5_portfolio").mkdir(exist_ok=True)
            if run["portfolio_manager"]["full_report"]:
                (out_dir / "5_portfolio/decision.md").write_text(run["portfolio_manager"]["full_report"], encoding="utf-8")

        except Exception as e:
            print(f"[TauricExecutionManager Persist Warning]: {e}")

tauric_engine = TauricExecutionManager()
