"""
BITDEX Central Execution Risk Gate (v2 — percentage-based risk policy)
=====================================================================
Every live Exness order must pass through `execute_order_with_fail_safe_protection`.
The final submission layers (adapter + Trader API client) refuse live orders outside this
gate's context (see execution_gate_token). All failures return structured reason codes and
fail CLOSED.
"""

import asyncio
import logging
import secrets
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from .trading_state_manager import TradingStateManager
from .strategy_candidate_a import CandidateAStrategy
from .risk_policy import RiskPolicy, broker_account_stats, value_per_price_unit_per_lot
try:
    from .execution_gate_token import enter_gate, exit_gate
except ImportError:
    from ..execution_gate_token import enter_gate, exit_gate

logger = logging.getLogger("bitdex.central_risk_gate")

REAL_TRADING_PERMANENTLY_LOCKED: bool = True
REAL_ACCOUNT_IDS = {"16000629657"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class CentralRiskGate:
    MAX_DATA_AGE_SECONDS: int = 600          # newest M5 candle must have opened within 10 min
    MAX_SPREAD_TO_ATR_RATIO: float = 0.35
    MIN_ATR: float = 0.50
    MAX_ATR: float = 6.00
    PROTECTION_TIMEOUT_SECONDS: float = 4.0
    MAX_MARGIN_FRACTION_OF_FREE: float = 0.50

    _account_locks: Dict[str, asyncio.Lock] = {}
    _seen_idempotency_keys: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def _lock_for(cls, account_id: str) -> asyncio.Lock:
        lk = cls._account_locks.get(str(account_id))
        if lk is None:
            lk = asyncio.Lock()
            cls._account_locks[str(account_id)] = lk
        return lk

    # ─────────────────────────────────────────────────────────────────────────
    @classmethod
    async def evaluate_full_gate(
        cls,
        conn: sqlite3.Connection,
        adapter: Any,
        authenticated_user_id: str,
        account_id: str,
        symbol: str,
        h1_candles: List[Dict[str, Any]],
        m15_candles: List[Dict[str, Any]],
        m5_candles: List[Dict[str, Any]],
        quote: Dict[str, Any],
        spec: Dict[str, Any],
        idempotency_key: Optional[str] = None,
        dry_run: bool = True,
        policy: Optional[RiskPolicy] = None,
        approved_risk_budget_usd: Optional[float] = None,  # deprecated, ignored
        trade_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        policy = policy or RiskPolicy.load()
        checks: List[Dict[str, Any]] = []

        def ok(name, detail=""):
            checks.append({"check": name, "passed": True, "detail": detail})

        def rej(code, detail, extra=None):
            checks.append({"check": code, "passed": False, "detail": detail})
            return cls._reject(code, detail, extra, checks)

        # 1. Authentication & ownership
        if not authenticated_user_id or not account_id:
            return rej("ERR_UNAUTHORIZED", "Missing authenticated user or account.")
        if str(getattr(adapter, "account_id", "")) != str(account_id):
            return rej("ERR_ACCOUNT_MISMATCH", "Adapter account does not match requested account.")
        try:
            await adapter.verify_ownership_and_environment(authenticated_user_id)
        except Exception as e:
            return rej("ERR_ACCOUNT_OWNERSHIP_MISMATCH", str(e))
        ok("1_AUTH_AND_OWNERSHIP", authenticated_user_id)

        # 2-3. Demo only, Real permanently locked
        env = str(getattr(adapter, "environment", "")).upper()
        if env != "DEMO":
            return rej("ERR_NON_DEMO_ENVIRONMENT", f"Environment {env} not permitted.")
        if REAL_TRADING_PERMANENTLY_LOCKED is not True or str(account_id) in REAL_ACCOUNT_IDS:
            return rej("ERR_REAL_ACCOUNT_BLOCKED", "Real-account execution is permanently locked.")
        ok("2_DEMO_ENVIRONMENT", env)
        ok("3_REAL_LOCK", "REAL_TRADING_PERMANENTLY_LOCKED=True")

        # 4. Fresh data (quote time_ms is stamped locally by the adapter, so use candle time)
        bid, ask = float(quote.get("bid") or 0), float(quote.get("ask") or 0)
        if bid <= 0 or ask <= 0 or ask < bid:
            return rej("ERR_INVALID_QUOTE", f"bid={bid} ask={ask}")
        newest = max((int(c.get("time") or 0) for c in m5_candles), default=0)
        age = time.time() - newest
        if newest <= 0 or age > cls.MAX_DATA_AGE_SECONDS:
            return rej("ERR_STALE_MARKET_DATA", f"Newest M5 candle opened {age:.0f}s ago.")
        ok("4_FRESH_MARKET_DATA", f"newest M5 open {age:.0f}s ago; bid={bid} ask={ask}")

        # 5. Symbol & spec
        sym = str(spec.get("broker_symbol") or spec.get("symbol") or symbol).upper()
        if not any(k in sym for k in ("XAU", "USDJPY", "EURUSD", "GBPUSD", "BTCUSD", "ETHUSD")):
            return rej("ERR_UNSUPPORTED_INSTRUMENT", f"{sym} not authorised.")
        if value_per_price_unit_per_lot(spec) <= 0 or float(spec.get("volume_step") or 0) <= 0:
            return rej("ERR_INVALID_SPECIFICATION", "Missing tick_value/tick_size/volume_step.")
        if str(spec.get("trade_mode", "enabled")).lower() not in ("enabled", "full"):
            return rej("ERR_SYMBOL_NOT_TRADABLE", f"trade_mode={spec.get('trade_mode')}")
        ok("5_SYMBOL_SPEC", f"contract={spec.get('contract_size')} tick={spec.get('tick_size')}/{spec.get('tick_value')} "
                            f"min={spec.get('min_volume')} step={spec.get('volume_step')} comm={spec.get('commission_per_lot')}")

        # Account equity (fresh) and broker-derived stats
        summary = await adapter.get_account_summary(force_refresh=True) if _accepts_force(adapter) else await adapter.get_account_summary()
        equity = float(summary.get("equity") or 0.0)
        balance = float(summary.get("balance") or equity)
        free_margin = float(summary.get("free_margin") or equity)
        leverage = float(summary.get("leverage") or 0) or 100.0
        if equity <= 0:
            return rej("ERR_EQUITY_UNAVAILABLE", "Broker equity unavailable.")
        if trade_history is None:
            trade_history = await adapter.client.get_trade_history(limit=1000)
        stats = broker_account_stats(trade_history, balance, policy)

        # 14. Daily realized-loss ceiling (broker-derived)
        if stats["daily_limit_reached"]:
            return rej("ERR_DAILY_LOSS_LIMIT_REACHED",
                       f"Today's realized P&L ${stats['today_realized_pnl_usd']:.2f} <= -{policy.daily_loss_limit_pct}% "
                       f"of day-start ${stats['day_start_balance_usd']:.2f} (${stats['daily_loss_limit_usd']:.2f}).", {"account_stats": stats})
        ok("14_DAILY_LOSS_LIMIT", f"today ${stats['today_realized_pnl_usd']:+.2f} / limit -${stats['daily_loss_limit_usd']:.2f}")

        # 15. Consecutive-loss cooldown (broker-derived OR persisted state, e.g. emergency freeze)
        in_cd, cd_until, _ = TradingStateManager.check_cooldown(conn, account_id)
        if stats["cooldown_active"] or in_cd:
            return rej("ERR_COOLDOWN_ACTIVE",
                       f"Cooldown until {stats['cooldown_until'] or cd_until} "
                       f"(trailing losses={stats['trailing_consecutive_losses']}).", {"account_stats": stats})
        ok("15_CONSECUTIVE_LOSS_COOLDOWN", f"trailing losses={stats['trailing_consecutive_losses']}, last={stats['last_loss_time']}")

        # 16. One open position
        positions = await adapter.get_open_positions()
        if len(positions) >= policy.max_open_positions:
            return rej("ERR_CONCURRENT_POSITION_EXISTS", f"{len(positions)} open position(s).")
        ok("16_ONE_POSITION", "0 open positions")

        # 17. Idempotency
        if idempotency_key and idempotency_key in cls._seen_idempotency_keys:
            cached = dict(cls._seen_idempotency_keys[idempotency_key])
            cached["idempotent_replay"] = True
            return cached
        ok("17_DUPLICATE_ORDER_PREVENTION", idempotency_key or "no key (dry)")

        # 6-8, 10-12. Candidate A + percentage sizing
        ev = CandidateAStrategy.evaluate(
            h1_candles=h1_candles, m15_candles=m15_candles, m5_candles=m5_candles,
            current_bid=bid, current_ask=ask, account_equity=equity, spec=spec, policy=policy,
        )
        for g in ev.get("passed_gates", []):
            ok(f"STRATEGY_{g}")
        if ev["outcome"] == "NO_TRADE":
            return rej(ev["error_code"], ev["detail"], {"strategy_evaluation": ev, "account_stats": stats, "equity": equity})

        op = ev["order_parameters"]
        direction = op["direction"]

        # 9. Setup fingerprint + 60-minute same-direction lock after a stop-out
        fp = TradingStateManager.compute_setup_fingerprint(symbol, direction, op["trigger_candle_time"], op["entry_price"])
        dir_fp = TradingStateManager.compute_direction_lock_fingerprint(symbol, direction)
        for key in (fp, dir_fp):
            inval, why = TradingStateManager.is_setup_invalidated(conn, account_id, key)
            if inval:
                return rej("ERR_SETUP_FINGERPRINT_INVALIDATED", f"{key}: {why}", {"strategy_evaluation": ev})
        lo = stats.get("last_loss_open_direction"), stats.get("last_loss_time")
        ok("9_SETUP_FINGERPRINT", fp)

        # 13. Spread / volatility
        atr = op["atr_m5"]
        if atr < cls.MIN_ATR or atr > cls.MAX_ATR:
            return rej("ERR_VOLATILITY_OUT_OF_BOUNDS", f"M5 ATR {atr} outside [{cls.MIN_ATR}, {cls.MAX_ATR}].")
        if op["spread_pts"] / atr > cls.MAX_SPREAD_TO_ATR_RATIO:
            return rej("ERR_SPREAD_EXCEEDS_ATR_THRESHOLD", f"spread {op['spread_pts']} / ATR {atr} > {cls.MAX_SPREAD_TO_ATR_RATIO}.")
        ok("13_SPREAD_AND_VOLATILITY", f"spread/ATR={op['spread_pts']/atr:.3f}")

        # Margin sanity
        req_margin = op["volume"] * float(spec.get("contract_size") or 100) * op["entry_price"] / leverage
        if req_margin > cls.MAX_MARGIN_FRACTION_OF_FREE * free_margin:
            return rej("ERR_INSUFFICIENT_MARGIN", f"Required margin ${req_margin:.2f} > 50% of free ${free_margin:.2f}.")
        ok("MARGIN", f"required ${req_margin:.2f} of free ${free_margin:.2f} (1:{int(leverage)})")
        ok("10_ATR_STOP", f"SL {op['sl_distance_pts']} = {op['sl_atr_ratio']}x ATR")
        ok("11_MIN_LOT_FEASIBILITY", f"volume {op['volume']}")
        ok("12_MAX_MONETARY_RISK", f"planned ${op['total_monetary_risk_usd']} <= budget ${op['risk_budget_usd']}")

        return {
            "status": "PASSED", "passed": True, "error_code": None,
            "setup_fingerprint": fp, "direction_lock_fingerprint": dir_fp,
            "order_parameters": op, "strategy_evaluation": ev,
            "account_equity": equity, "account_balance": balance, "required_margin_usd": round(req_margin, 2),
            "account_stats": stats, "risk_policy": policy.to_dict(), "checks": checks,
        }

    # ─────────────────────────────────────────────────────────────────────────
    @classmethod
    async def execute_order_with_fail_safe_protection(
        cls,
        conn: sqlite3.Connection,
        adapter: Any,
        authenticated_user_id: str,
        account_id: str,
        symbol: str,
        h1_candles: List[Dict[str, Any]],
        m15_candles: List[Dict[str, Any]],
        m5_candles: List[Dict[str, Any]],
        quote: Dict[str, Any],
        spec: Dict[str, Any],
        comment: str = "BITDEX-CDA",
        idempotency_key: Optional[str] = None,
        dry_run: bool = True,
        policy: Optional[RiskPolicy] = None,
        approved_risk_budget_usd: Optional[float] = None,  # deprecated, ignored
        sl_verify_poll_sec: float = 0.5,
    ) -> Dict[str, Any]:
        async with cls._lock_for(account_id):
            pre = await cls.evaluate_full_gate(
                conn, adapter, authenticated_user_id, account_id, symbol,
                h1_candles, m15_candles, m5_candles, quote, spec, idempotency_key, dry_run, policy,
            )
            if not pre.get("passed") or pre.get("idempotent_replay"):
                return pre

            op = pre["order_parameters"]
            direction, volume = op["direction"], op["volume"]
            digits = int(spec.get("digits", 3))
            vpu = value_per_price_unit_per_lot(spec)

            if dry_run:
                res = {**pre, "status": "DRY_RUN_PASSED", "dry_run": True}
                if idempotency_key:
                    cls._seen_idempotency_keys[idempotency_key] = res
                return res

            gate_ref = f"GATE-{secrets.token_hex(4).upper()}"
            token = enter_gate(account_id, gate_ref)
            try:
                if hasattr(adapter, "unlock_demo_execution_for_test"):
                    adapter.unlock_demo_execution_for_test(account_id)

                t0 = time.perf_counter()
                order_res = await adapter.place_market_order(
                    symbol=symbol, side=direction.lower(), volume=volume,
                    sl=op["sl_price"], tp=op["tp_price"], comment=comment,
                    idempotency_key=idempotency_key, dry_run=False,
                )
                lat_ms = round((time.perf_counter() - t0) * 1000, 1)
                op_id = str(order_res.get("operation_id") or (order_res.get("ack") or {}).get("operation_id") or "")
                if not op_id:
                    return cls._reject("ERR_ORDER_SUBMISSION_FAILED", f"No operation id: {order_res}", {"pre": pre})

                # 18. Reconcile fill — HTTP 202 is NOT a fill
                reconciled: Dict[str, Any] = {}
                em = getattr(adapter, "event_manager", None)
                if em is not None and hasattr(em, "reconcile_operation"):
                    reconciled = await em.reconcile_operation(op_id, max_retries=10, delay_sec=1.0)
                    if str(reconciled.get("state", "")).upper() == "REJECTED":
                        return cls._reject("ERR_BROKER_REJECTED", str(reconciled.get("error_detail")), {"pre": pre})
                position_id = str(reconciled.get("position_id") or "")
                fill = float(reconciled.get("execution_price") or 0.0)

                pos = await cls._find_position(adapter, position_id, symbol)
                if pos is None:
                    return cls._reject("ERR_FILL_RECONCILIATION_FAILED",
                                       f"Operation {op_id} has no reconciled open position.", {"pre": pre, "operation_id": op_id})
                position_id = str(pos.get("position_id") or pos.get("id"))
                fill = float(pos.get("open_price") or fill or op["entry_price"])
                actual_vol = float(pos.get("volume") or volume)

                # 19. Verify broker-side SL (poll fresh snapshots)
                protected, pos = await cls._await_protection(adapter, position_id, direction, fill, symbol, sl_verify_poll_sec)
                attach_attempted = False
                if not protected:
                    attach_attempted = True
                    sl_px, tp_px = op["sl_price"], op["tp_price"]
                    if (direction == "BUY" and sl_px >= fill) or (direction == "SELL" and sl_px <= fill):
                        sl_px = round(fill - op["sl_distance_pts"], digits) if direction == "BUY" else round(fill + op["sl_distance_pts"], digits)
                        tp_px = round(fill + op["tp_distance_pts"], digits) if direction == "BUY" else round(fill - op["tp_distance_pts"], digits)
                    logger.warning(f"Position {position_id}: SL not confirmed on fill; attaching SL={sl_px} TP={tp_px}")
                    try:
                        await adapter.attach_sl_tp(position_id=position_id, sl=sl_px, tp=tp_px, symbol=symbol, dry_run=False)
                    except Exception as e:
                        logger.error(f"attach_sl_tp error: {e}")
                    protected, pos = await cls._await_protection(adapter, position_id, direction, fill, symbol, sl_verify_poll_sec)

                if not protected:
                    logger.critical(f"EMERGENCY: SL unconfirmed for {position_id}; closing at market.")
                    try:
                        await adapter.close_position(position_id=position_id, dry_run=False)
                    except Exception as e:
                        logger.error(f"emergency close error: {e}")
                    still_open = True
                    for _ in range(8):
                        await asyncio.sleep(sl_verify_poll_sec)
                        if await cls._find_position(adapter, position_id, symbol, exact_only=True) is None:
                            still_open = False
                            break
                    if still_open:
                        TradingStateManager.freeze_account(conn, account_id, "EMERGENCY_CLOSE_UNCONFIRMED", hours=24)
                        conn.commit()
                        return cls._reject("ERR_EMERGENCY_CLOSE_FAILED",
                                           f"Position {position_id} unprotected and close unconfirmed. Account frozen.",
                                           {"position_id": position_id})
                    return cls._reject("ERR_SL_UNCONFIRMED_EMERGENCY_CLOSED",
                                       f"Position {position_id} closed at market: broker SL could not be verified.",
                                       {"position_id": position_id})

                actual_sl = float(pos.get("sl") or pos.get("stop_loss_price"))
                actual_tp = float(pos.get("tp") or pos.get("take_profit_price") or 0.0) or None
                slip = (policy or RiskPolicy.load()).est_slippage_pts_per_side
                actual_planned_loss = round((abs(fill - actual_sl) + slip) * vpu * actual_vol, 2)

                # Consume this exact setup so the same trigger bar can never fire twice.
                TradingStateManager.invalidate_setup(conn, account_id, symbol, direction, pre["setup_fingerprint"],
                                                     reason="SETUP_CONSUMED", ttl_minutes=60)
                conn.commit()

                res = {
                    "status": "FILLED_AND_PROTECTED", "passed": True, "dry_run": False,
                    "gate_ref": gate_ref, "account_id": account_id, "position_id": position_id,
                    "operation_id": op_id, "symbol": symbol, "direction": direction,
                    "volume": actual_vol, "execution_price": fill,
                    "broker_sl": actual_sl, "broker_tp": actual_tp,
                    "exact_sl": actual_sl, "exact_tp": actual_tp,
                    "sl_attached_at_submission": not attach_attempted,
                    "stop_loss_verified": True,
                    "planned_loss_at_fill_usd": actual_planned_loss,
                    "latency_ms": lat_ms, "opened_at": _now_iso(),
                    "setup_fingerprint": pre["setup_fingerprint"],
                    "direction_lock_fingerprint": pre["direction_lock_fingerprint"],
                    "pre_trade": pre,
                }
                if idempotency_key:
                    cls._seen_idempotency_keys[idempotency_key] = res
                return res
            finally:
                exit_gate(token)

    # ─────────────────────────────────────────────────────────────────────────
    @staticmethod
    async def _positions_fresh(adapter: Any) -> List[Dict[str, Any]]:
        client = getattr(adapter, "client", None)
        if client is not None and hasattr(client, "get_trading_snapshot"):
            try:
                await client.get_trading_snapshot(force_refresh=True)
            except Exception:
                pass
        return await adapter.get_open_positions()

    @classmethod
    async def _find_position(cls, adapter, position_id: str, symbol: str, exact_only: bool = False):
        for _ in range(4):
            positions = await cls._positions_fresh(adapter)
            if position_id:
                p = next((p for p in positions if str(p.get("position_id") or p.get("id")) == str(position_id)), None)
                if p or exact_only:
                    return p
            if not exact_only:
                cand = [p for p in positions if symbol.upper()[:3] in str(p.get("symbol") or p.get("instrument") or "").upper()]
                if len(cand) == 1:
                    return cand[0]
            await asyncio.sleep(0.5)
        return None

    @classmethod
    async def _await_protection(cls, adapter, position_id, direction, fill, symbol, poll):
        deadline = time.monotonic() + cls.PROTECTION_TIMEOUT_SECONDS
        pos = None
        while True:
            pos = await cls._find_position(adapter, position_id, symbol, exact_only=True)
            if pos is not None:
                sl = pos.get("sl") if pos.get("sl") is not None else pos.get("stop_loss_price")
                try:
                    sl = float(sl) if sl is not None else 0.0
                except (TypeError, ValueError):
                    sl = 0.0
                if sl > 0 and ((direction == "BUY" and sl < fill) or (direction == "SELL" and sl > fill)):
                    return True, pos
            if time.monotonic() >= deadline:
                return False, pos
            await asyncio.sleep(poll)

    @staticmethod
    def _reject(code: str, detail: str, extra: Optional[Dict[str, Any]] = None,
                checks: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        logger.warning(f"CentralRiskGate REJECT [{code}]: {detail}")
        payload = {"status": "REJECTED", "passed": False, "error_code": code, "detail": detail,
                   "fail_closed": True, "timestamp_utc": _now_iso()}
        if checks is not None:
            payload["checks"] = checks
        if extra:
            payload["details"] = extra
        return payload


def _accepts_force(adapter) -> bool:
    import inspect
    try:
        return "force_refresh" in inspect.signature(adapter.get_account_summary).parameters
    except (TypeError, ValueError):
        return False
