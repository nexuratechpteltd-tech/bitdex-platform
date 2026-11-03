"""
BITDEX Autonomous Binance Futures Scalping Engine
=================================================
Orchestrates autonomous lifecycle for the SCALP_ONE_DOLLAR profile:
- Pair discovery & screening
- Regime classification & signal generation
- Risk-bounded sizing & pre-trade risk gate
- Execution with fail-safe protective stops
- Position monitoring (5m reassessment, 10m maximum expiry, $1.00 net target exit)
- Realized PnL accounting & trade auditing
- Cooldowns, circuit breakers, and emergency shutdown
"""

import time
import json
import logging
import sqlite3
from typing import Optional, Dict, Any, List

from .binance_futures_adapter import BinanceFuturesAdapter, BinanceFuturesError
from .futures_discovery import MarketDiscoveryService
from .futures_regime import MarketRegimeClassifier
from .futures_signal_engine import FuturesSignalEngine
from .futures_sizing import FuturesSizingEngine
from .futures_risk_engine import FuturesRiskEngine
from .futures_execution import FuturesExecutionEngine
from .futures_db import (
    get_or_create_futures_account,
    get_futures_account,
    get_open_futures_position,
    list_open_futures_positions,
    get_or_create_scalp_run,
    update_scalp_run_state,
    record_scalp_signal,
    record_scalp_trade,
    complete_scalp_trade,
    utc_now_iso,
)

logger = logging.getLogger("bitdex.futures.scalper")


class AutonomousScalpingEngine:
    """Autonomous scalping engine implementing SCALP_ONE_DOLLAR."""

    STRATEGY_NAME = "SCALP_ONE_DOLLAR"
    TARGET_NET_PROFIT_USD = 1.00
    PREFERRED_HOLDING_SECONDS = 300   # 5 minutes
    MAXIMUM_HOLDING_SECONDS = 600     # 10 minutes max expiry
    COOLDOWN_AFTER_TRADE_SECONDS = 60 # 60 seconds cooldown between trades

    def __init__(
        self,
        conn: sqlite3.Connection,
        user_id: str,
        account_id: Optional[str] = None,
        adapter: Optional[BinanceFuturesAdapter] = None,
        environment: str = "testnet",
        simulate_execution: bool = False,
    ):
        self.conn = conn
        self.user_id = user_id
        self.environment = environment
        self.adapter = adapter or BinanceFuturesAdapter(environment=environment)
        self.simulate_execution = simulate_execution
        
        # Initialize or fetch account
        acct = get_or_create_futures_account(
            self.conn, user_id=self.user_id,
            exchange_connection_id=f"CONN-{user_id[:8]}",
            environment=environment
        )
        self.account_id = account_id or acct["account_id"]
        
        # Initialize discovery service
        self.discovery = MarketDiscoveryService(adapter=self.adapter)
        
        # State tracking
        self.is_running = False
        self.is_paused = False
        self.circuit_breaker_active = False
        self.last_trade_time = 0
        self.active_trade_id: Optional[str] = None
        self.active_symbol: Optional[str] = None
        self.active_entry_time: float = 0.0

    # ─────────────────────────────────────────────────────────────
    # Lifecycle Controls
    # ─────────────────────────────────────────────────────────────

    def start(self) -> Dict[str, Any]:
        """Start or resume the autonomous scalping run."""
        run = get_or_create_scalp_run(self.conn, self.user_id, self.account_id, self.STRATEGY_NAME)
        self.is_running = True
        self.is_paused = False
        update_scalp_run_state(
            self.conn, run["run_id"],
            status="RUNNING",
            state_dict={
                "is_running": True,
                "is_paused": False,
                "active_symbol": self.active_symbol,
                "last_started": utc_now_iso()
            }
        )
        logger.info("Autonomous scalping engine started for %s (Run: %s)", self.user_id, run["run_id"])
        return {"status": "SUCCESS", "run_id": run["run_id"], "engine_state": "RUNNING"}

    def pause(self) -> Dict[str, Any]:
        """Pause scanning without terminating open positions."""
        self.is_paused = True
        run = get_or_create_scalp_run(self.conn, self.user_id, self.account_id, self.STRATEGY_NAME)
        update_scalp_run_state(
            self.conn, run["run_id"],
            status="PAUSED",
            state_dict={"is_running": self.is_running, "is_paused": True, "paused_at": utc_now_iso()}
        )
        logger.info("Autonomous scalping engine paused for %s", self.user_id)
        return {"status": "SUCCESS", "engine_state": "PAUSED"}

    def resume(self) -> Dict[str, Any]:
        """Resume paused engine."""
        self.is_paused = False
        self.is_running = True
        run = get_or_create_scalp_run(self.conn, self.user_id, self.account_id, self.STRATEGY_NAME)
        update_scalp_run_state(
            self.conn, run["run_id"],
            status="RUNNING",
            state_dict={"is_running": True, "is_paused": False, "resumed_at": utc_now_iso()}
        )
        logger.info("Autonomous scalping engine resumed for %s", self.user_id)
        return {"status": "SUCCESS", "engine_state": "RUNNING"}

    def stop(self, reason: str = "ADMIN_REQUEST") -> Dict[str, Any]:
        """Stop autonomous scalping engine cleanly."""
        self.is_running = False
        self.is_paused = False
        run = get_or_create_scalp_run(self.conn, self.user_id, self.account_id, self.STRATEGY_NAME)
        now = utc_now_iso()
        update_scalp_run_state(
            self.conn, run["run_id"],
            status="STOPPED",
            state_dict={"is_running": False, "is_paused": False, "stop_reason": reason},
            stopped_at=now
        )
        logger.info("Autonomous scalping engine stopped for %s (Reason: %s)", self.user_id, reason)
        return {"status": "SUCCESS", "engine_state": "STOPPED", "reason": reason}

    def emergency_shutdown(self) -> Dict[str, Any]:
        """
        Emergency stop: Halts scanning immediately.
        Does NOT automatically close unrelated manual positions.
        """
        self.circuit_breaker_active = True
        return self.stop(reason="EMERGENCY_SHUTDOWN")

    # ─────────────────────────────────────────────────────────────
    # Autonomous Scan & Evaluation Step
    # ─────────────────────────────────────────────────────────────

    def run_single_iteration(
        self,
        candidate_symbols: Optional[List[str]] = None,
        custom_klines: Optional[Dict[str, List[Dict[str, Any]]]] = None
    ) -> Dict[str, Any]:
        """
        Executes one complete cycle:
        1. Checks active trade monitoring
        2. Discovers eligible universe
        3. Evaluates regimes & signals
        4. Sizes and executes approved trade
        """
        now = time.time()

        # Cooldown check
        if (now - self.last_trade_time) < self.COOLDOWN_AFTER_TRADE_SECONDS:
            remaining = int(self.COOLDOWN_AFTER_TRADE_SECONDS - (now - self.last_trade_time))
            return {
                "action": "COOLDOWN",
                "message": f"Cooldown active ({remaining}s remaining)",
                "active_symbol": self.active_symbol
            }

        # 1. Active Position Monitoring (if we already have an open scalp position)
        if self.active_symbol:
            pos = get_open_futures_position(self.conn, user_id=self.user_id, symbol=self.active_symbol)
            if pos and abs(float(pos["quantity"])) > 1e-8:
                return self.monitor_active_position(pos)
            else:
                # Position closed externally (e.g. Stop loss hit)
                self.active_symbol = None
                self.active_trade_id = None
                self.last_trade_time = now

        # 2. Check general one-position-per-symbol policy and max concurrent positions
        open_positions = list_open_futures_positions(self.conn, user_id=self.user_id)
        if len(open_positions) >= 3:
            return {
                "action": "NO_TRADE",
                "message": f"Max concurrent positions reached ({len(open_positions)}/3)",
            }

        # 3. Market Discovery & Universe Screening
        symbols_to_scan = candidate_symbols or ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT"]
        discovery_result = self.discovery.scan_and_rank_eligible_pairs(universe_override=symbols_to_scan)

        if discovery_result.get("status") != "SUCCESS" or not discovery_result.get("candidates"):
            return {
                "action": "NO_TRADE",
                "message": "No eligible symbols passed liquidity, volume, and spread gates.",
                "discovery": discovery_result
            }

        candidates = discovery_result["candidates"]
        account = get_futures_account(self.conn, user_id=self.user_id, account_id=self.account_id)
        avail_bal = float(account["available_balance"])
        equity = float(account["wallet_balance"])

        evaluated_signals = []

        # 4. Evaluate Regimes and Signals for Candidates
        for cand in candidates:
            sym = cand["symbol"]
            # Exclude if already holding a position in this symbol
            if any(p["symbol"] == sym for p in open_positions):
                continue

            # Fetch or use klines
            if custom_klines and sym in custom_klines:
                klines = custom_klines[sym]
            else:
                try:
                    klines = self.discovery.fetch_klines(sym, interval="5m", limit=30)
                except Exception as ke:
                    logger.warning("Could not fetch klines for %s: %s", sym, str(ke))
                    continue

            regime = MarketRegimeClassifier.classify(klines, sym)
            curr_price = cand["price"]
            spread_ratio = cand["spread_ratio"]

            # Tentative sizing to evaluate net target feasibility
            filters = self.adapter.get_symbol_filters(sym)
            raw_stop_dist = regime.get("atr", 1.0) * 1.8
            tentative_stop = curr_price - raw_stop_dist

            sizing = FuturesSizingEngine.calculate_scalp_sizing(
                symbol=sym,
                price=curr_price,
                atr=regime.get("atr", 1.0),
                stop_price=tentative_stop,
                available_balance=avail_bal,
                equity=equity,
                symbol_filters=filters,
                target_net_usd=self.TARGET_NET_PROFIT_USD
            )

            if not sizing["feasible"]:
                record_scalp_signal(
                    conn=self.conn,
                    user_id=self.user_id,
                    account_id=self.account_id,
                    symbol=sym,
                    direction="NO_TRADE",
                    market_price=curr_price,
                    entry_price=curr_price,
                    stop_price=0.0,
                    target_exit_price=0.0,
                    expected_gross_pnl=0.0,
                    estimated_fees=0.0,
                    expected_net_pnl=0.0,
                    signal_score=0.0,
                    regime=regime.get("regime", "UNSTABLE"),
                    status="REJECTED",
                    rejection_reason=sizing["rejection_reason"]
                )
                continue

            # Generate signal with clamped sizing
            signal = FuturesSignalEngine.evaluate_signal(
                symbol=sym,
                klines=klines,
                current_market_price=curr_price,
                proposed_quantity=sizing["quantity"],
                equity=equity,
                regime_data=regime,
                spread_ratio=spread_ratio
            )

            # Persist signal decision
            sig_status = "APPROVED" if signal["decision"] == "TRADE" else "REJECTED"
            record_scalp_signal(
                conn=self.conn,
                user_id=self.user_id,
                account_id=self.account_id,
                symbol=sym,
                direction=signal["direction"],
                market_price=curr_price,
                entry_price=signal["entry_reference_price"],
                stop_price=signal["protective_stop_price"],
                target_exit_price=signal["target_exit_price"],
                expected_gross_pnl=signal["expected_gross_pnl_usd"],
                estimated_fees=signal["estimated_fees_usd"],
                expected_net_pnl=signal["expected_net_pnl_usd"],
                signal_score=signal["signal_score"],
                regime=signal["regime"],
                status=sig_status,
                rejection_reason=signal["rejection_reason"]
            )

            if signal["decision"] == "TRADE":
                evaluated_signals.append({
                    "symbol": sym,
                    "signal": signal,
                    "sizing": sizing,
                    "score": signal["signal_score"]
                })

        # 5. Rank and Select Best Trade
        if not evaluated_signals:
            return {
                "action": "NO_TRADE",
                "message": "All evaluated candidates resulted in NO_TRADE or failed sizing criteria.",
                "candidates_scanned": len(candidates)
            }

        evaluated_signals.sort(key=lambda s: s["score"], reverse=True)
        top_opportunity = evaluated_signals[0]
        selected_sym = top_opportunity["symbol"]
        selected_sig = top_opportunity["signal"]
        selected_sizing = top_opportunity["sizing"]

        # 6. Execute Intent via Phase 2 Execution Engine (POST_ONLY maker entry)
        exec_res = FuturesExecutionEngine.execute_intent(
            conn=self.conn,
            user_id=self.user_id,
            intent=selected_sig["intent"],
            symbol=selected_sym,
            quantity=selected_sizing["quantity"],
            price=selected_sig["market_price"],
            stop_price=selected_sig["protective_stop_price"],
            leverage=selected_sizing["leverage"],
            margin_type="ISOLATED",
            order_type="POST_ONLY",
            adapter=self.adapter,
            environment=self.environment,
            simulate_execution=self.simulate_execution
        )

        if not exec_res.get("success"):
            return {
                "action": "EXECUTION_FAILED",
                "error_code": exec_res.get("error_code"),
                "message": exec_res.get("message"),
                "symbol": selected_sym
            }

        # 7. Record Trade
        trade_rec = record_scalp_trade(
            conn=self.conn,
            user_id=self.user_id,
            account_id=self.account_id,
            symbol=selected_sym,
            direction=selected_sig["direction"],
            entry_order_id=exec_res["order_id"],
            protective_stop_order_id=exec_res.get("protective_stop_order_id"),
            quantity=exec_res["executed_qty"],
            entry_price=exec_res["fill_price"],
            strategy_name=self.STRATEGY_NAME
        )

        self.active_symbol = selected_sym
        self.active_trade_id = trade_rec["trade_id"]
        self.active_entry_time = now

        return {
            "action": "ENTERED_TRADE",
            "trade_id": self.active_trade_id,
            "symbol": selected_sym,
            "direction": selected_sig["direction"],
            "quantity": exec_res["executed_qty"],
            "fill_price": exec_res["fill_price"],
            "stop_price": selected_sig["protective_stop_price"],
            "target_exit_price": selected_sig["target_exit_price"],
            "expected_net_usd": selected_sig["expected_net_pnl_usd"],
            "protective_stop_order_id": exec_res.get("protective_stop_order_id"),
            "execution": exec_res
        }

    # ─────────────────────────────────────────────────────────────
    # Position Monitoring & Dual Exit Mechanism
    # ─────────────────────────────────────────────────────────────

    def monitor_active_position(
        self,
        position: Dict[str, Any],
        current_price_override: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Monitors active scalping position:
        A. Net-profit target exit ($1.00 net achieved)
        B. 5-minute reassessment & 10-minute maximum intended holding expiry
        """
        sym = position["symbol"]
        qty = abs(float(position["quantity"]))
        entry_price = float(position["entry_price"])
        direction = "LONG" if float(position["quantity"]) > 0 else "SHORT"
        now = time.time()
        holding_seconds = now - self.active_entry_time if self.active_entry_time > 0 else 0.0

        if current_price_override:
            curr_price = current_price_override
        else:
            try:
                curr_price = self.adapter.get_ticker_price(sym)
            except Exception as e:
                logger.error("Failed to fetch price for %s: %s", sym, str(e))
                return {"action": "MONITORING_PRICE_FETCH_FAILED", "symbol": sym}

        # Compute executable net profit right now
        if direction == "LONG":
            gross_pnl = (curr_price - entry_price) * qty
        else:
            gross_pnl = (entry_price - curr_price) * qty

        entry_fee = float(position.get("entry_fee_usd", entry_price * qty * 0.0004))
        exit_fee = curr_price * qty * 0.0004
        total_round_trip_fees = entry_fee + exit_fee
        current_net_pnl = gross_pnl - total_round_trip_fees

        # ── EXIT CONDITION A: NET-PROFIT TARGET ACHIEVED (>= $1.00) ──
        if current_net_pnl >= self.TARGET_NET_PROFIT_USD:
            exit_intent = "LONG_EXIT" if direction == "LONG" else "SHORT_EXIT"
            exit_res = FuturesExecutionEngine.execute_intent(
                conn=self.conn,
                user_id=self.user_id,
                intent=exit_intent,
                symbol=sym,
                quantity=qty,
                price=curr_price,
                adapter=self.adapter,
                environment=self.environment,
                simulate_execution=self.simulate_execution
            )
            if self.active_trade_id:
                complete_scalp_trade(
                    conn=self.conn,
                    trade_id=self.active_trade_id,
                    exit_order_id=exit_res.get("order_id", ""),
                    exit_price=curr_price,
                    exit_reason="NET_PROFIT_TARGET_HIT",
                    gross_pnl_usd=gross_pnl,
                    total_fees_usd=total_round_trip_fees,
                    net_pnl_usd=current_net_pnl,
                    target_hit=True,
                    holding_duration_seconds=holding_seconds
                )
            self.active_symbol = None
            self.active_trade_id = None
            self.last_trade_time = now
            return {
                "action": "EXITED_TRADE",
                "reason": "NET_PROFIT_TARGET_HIT",
                "gross_pnl_usd": round(gross_pnl, 4),
                "total_fees_usd": round(total_round_trip_fees, 4),
                "net_pnl_usd": round(current_net_pnl, 4),
                "target_hit": True,
                "holding_duration_seconds": round(holding_seconds, 1),
                "execution": exit_res
            }

        # ── EXIT CONDITION B: 10-MINUTE MAXIMUM INTENDED EXPIRY ──
        if holding_seconds >= self.MAXIMUM_HOLDING_SECONDS:
            exit_intent = "LONG_EXIT" if direction == "LONG" else "SHORT_EXIT"
            exit_res = FuturesExecutionEngine.execute_intent(
                conn=self.conn,
                user_id=self.user_id,
                intent=exit_intent,
                symbol=sym,
                quantity=qty,
                price=curr_price,
                adapter=self.adapter,
                environment=self.environment,
                simulate_execution=self.simulate_execution
            )
            if self.active_trade_id:
                complete_scalp_trade(
                    conn=self.conn,
                    trade_id=self.active_trade_id,
                    exit_order_id=exit_res.get("order_id", ""),
                    exit_price=curr_price,
                    exit_reason="MAX_HOLDING_TIME_EXPIRY",
                    gross_pnl_usd=gross_pnl,
                    total_fees_usd=total_round_trip_fees,
                    net_pnl_usd=current_net_pnl,
                    target_hit=False,
                    holding_duration_seconds=holding_seconds
                )
            self.active_symbol = None
            self.active_trade_id = None
            self.last_trade_time = now
            return {
                "action": "EXITED_TRADE",
                "reason": "MAX_HOLDING_TIME_EXPIRY",
                "gross_pnl_usd": round(gross_pnl, 4),
                "total_fees_usd": round(total_round_trip_fees, 4),
                "net_pnl_usd": round(current_net_pnl, 4),
                "target_hit": False,
                "holding_duration_seconds": round(holding_seconds, 1),
                "execution": exit_res
            }

        # ── EXIT CONDITION C: 5-MINUTE REASSESSMENT EXIT IF PROFITABLE ──
        if holding_seconds >= self.PREFERRED_HOLDING_SECONDS and current_net_pnl > 0.05:
            # At 5 minutes, if trade has achieved net positive profit (> $0.05), take it
            exit_intent = "LONG_EXIT" if direction == "LONG" else "SHORT_EXIT"
            exit_res = FuturesExecutionEngine.execute_intent(
                conn=self.conn,
                user_id=self.user_id,
                intent=exit_intent,
                symbol=sym,
                quantity=qty,
                price=curr_price,
                adapter=self.adapter,
                environment=self.environment,
                simulate_execution=self.simulate_execution
            )
            if self.active_trade_id:
                complete_scalp_trade(
                    conn=self.conn,
                    trade_id=self.active_trade_id,
                    exit_order_id=exit_res.get("order_id", ""),
                    exit_price=curr_price,
                    exit_reason="5M_REASSESSMENT_PROFIT_TAKE",
                    gross_pnl_usd=gross_pnl,
                    total_fees_usd=total_round_trip_fees,
                    net_pnl_usd=current_net_pnl,
                    target_hit=(current_net_pnl >= 0.95),
                    holding_duration_seconds=holding_seconds
                )
            self.active_symbol = None
            self.active_trade_id = None
            self.last_trade_time = now
            return {
                "action": "EXITED_TRADE",
                "reason": "5M_REASSESSMENT_PROFIT_TAKE",
                "gross_pnl_usd": round(gross_pnl, 4),
                "total_fees_usd": round(total_round_trip_fees, 4),
                "net_pnl_usd": round(current_net_pnl, 4),
                "target_hit": (current_net_pnl >= 0.95),
                "holding_duration_seconds": round(holding_seconds, 1),
                "execution": exit_res
            }

        # Otherwise: continue monitoring
        return {
            "action": "MONITORING_POSITION",
            "symbol": sym,
            "direction": direction,
            "holding_duration_seconds": round(holding_seconds, 1),
            "current_price": curr_price,
            "entry_price": entry_price,
            "gross_pnl_usd": round(gross_pnl, 4),
            "estimated_round_trip_fees_usd": round(total_round_trip_fees, 4),
            "estimated_net_pnl_usd": round(current_net_pnl, 4),
        }
