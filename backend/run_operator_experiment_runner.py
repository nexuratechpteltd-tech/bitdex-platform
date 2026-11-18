from pathlib import Path
import json
#!/usr/bin/env python3
"""
BITDEX Institutional 9-Hour Operator Demo Experiment Supervisor & Autonomous Execution Runner
Location: /opt/tauric-platform-staging/backend/run_operator_experiment_runner.py

EXPLICIT OPERATOR AUTHORIZATION:
- Account: Exness DEMO 17000694512
- Server: dx.2.trial.raw
- Staging VPS: 169.58.218.168
- Strategies Authorized:
  1. Gold Long-Term (XAUUSD Structure on D1/H4/H1)
  2. New Gold Scalping Engine (M5 Micro-Structure with Volatility Filter)
  3. Forex Long-Term & Approved Scalping (EURUSD, GBPUSD, USDJPY, USDCAD)
- HARD BANS:
  * Retired Track 1 Micro-Scalper is PERMANENTLY BANNED.
  * Real trading is PERMANENTLY LOCKED (REAL_TRADING_PERMANENTLY_LOCKED = True).
  * No customer accounts, no martingale, no averaging down, no grid.
- DURATION: 9 hours from activation. Automatically halts and transitions to COMPLETED.
- PERSISTENCE: Records every scan, signal, rejection, fill, and outcome into SQLite Trade Memory.
"""

import os
import sys
import time
import json
import math
import sqlite3
import asyncio
import logging
from datetime import datetime, timezone, timedelta

LOG_FILE = "/opt/tauric-platform-staging/backend/data/operator_9h_experiment.log"
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] [OPERATOR_EXP] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE)
    ]
)
logger = logging.getLogger("bitdex.operator_experiment")

from app.services.brokers.shared_risk_manager import SharedCentralRiskManager
REAL_TRADING_PERMANENTLY_LOCKED = True
from app.services.brokers.execution_router import CentralExecutionRouter
from app.services.automated_scalping_engine import AutomatedHighFrequencyScalpingEngine
from app.services.brokers.micro_scalping_engine import MicroScalpingEngine
from app.services.brokers.shared_risk_manager import SharedCentralRiskManager
from app.services.trade_memory_service import TradeMemoryService
from app.services.trade_memory_service import TradeMemoryService
from app.services.paper_trading_simulator import PaperTradingSimulator
from app.services.saas_db import get_db_connection

ACCOUNT_ID = "17000694512"
SERVER_NAME = "dx.2.trial.raw"
DURATION_HOURS = 9.0

# Supported Universe for Experiment
FOREX_SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "USDCAD"]
COMMODITY_SYMBOLS = ["XAUUSD"]
CRYPTO_SYMBOLS = ["BTCUSD", "ETHUSD"]

LOCK_FILE = Path("/opt/tauric-platform-staging/backend/data/experiment_lock.json")

def check_persistent_experiment_lock():
    if not LOCK_FILE.exists():
        logger.error(f"EXPERIMENT LOCKED: {LOCK_FILE} not found. Explicit operator authorization required.")
        return False, None
    try:
        data = json.loads(LOCK_FILE.read_text())
    except Exception as e:
        logger.error(f"EXPERIMENT LOCKED: Failed to parse {LOCK_FILE}: {e}")
        return False, None
    if data.get("authorized") is not True:
        logger.error(f"EXPERIMENT LOCKED: authorized={data.get("authorized")} (reason: {data.get("reason", "not authorized")}).")
        return False, None
    if str(data.get("account_id")) != ACCOUNT_ID or str(data.get("server")) != SERVER_NAME:
        logger.error(f"EXPERIMENT LOCKED: Account/server mismatch in lock file.")
        return False, None
    expires_raw = data.get("expires_at_utc")
    if not expires_raw:
        logger.error("EXPERIMENT LOCKED: Missing expires_at_utc in lock file.")
        return False, None
    try:
        expires_at = datetime.fromisoformat(str(expires_raw).replace("Z", "+00:00"))
    except Exception as e:
        logger.error(f"EXPERIMENT LOCKED: Invalid expires_at_utc {expires_raw}: {e}")
        return False, None
    now = datetime.now(timezone.utc)
    if now >= expires_at:
        logger.error(f"EXPERIMENT EXPIRED: Current UTC {now.isoformat()} >= {expires_at.isoformat()}. Re-authorization required.")
        return False, expires_at
    return True, expires_at

class OperatorExperimentSupervisor:
    def __init__(self):
        self.start_time = datetime.now(timezone.utc)
        self.expiry_time = self.start_time + timedelta(hours=DURATION_HOURS)
        self.state = "INITIALIZING"
        self.iteration = 0
        self.trades_opened_count = 0
        self.gold_scalp_engine = AutomatedHighFrequencyScalpingEngine()
        self.forex_scalp_engine = MicroScalpingEngine()


    async def validate_instrument_and_budget(self, adapter, symbol: str, sl_distance: float, risk_budget_usd: float) -> tuple[bool, str, dict]:
        specs = await adapter.get_instrument_specs(symbol) if hasattr(adapter, "get_instrument_specs") else None
        if not specs or not specs.get("contract_size") or not specs.get("volume_min"):
            return False, f"ERR_MISSING_SPECS: Missing or invalid instrument specifications for {symbol}", {}
        min_vol = float(specs["volume_min"])
        contract_size = float(specs["contract_size"])
        min_risk_usd = min_vol * contract_size * abs(sl_distance)
        if min_risk_usd > risk_budget_usd:
            return False, f"ERR_MIN_VOL_EXCEEDS_RISK_BUDGET: min_vol={min_vol} risk=${min_risk_usd:.2f} > budget=${risk_budget_usd:.2f}", specs
        return True, "OK", specs

    async def scan_longterm_crypto_opportunities(self, adapter, open_positions: list) -> list:
        """Evaluate BTCUSD and ETHUSD on H1 using EMA20/EMA50/EMA200 warmup + pullback confirmation.
        Routed through CentralExecutionRouter and SharedCentralRiskManager.preflight_check()."""
        candidates = []
        for sym in CRYPTO_SYMBOLS:
            try:
                h1 = await adapter.get_historical_candles(sym, timeframe="H1", count=250)
                if not h1 or len(h1) < 200:
                    continue
                closes = [float(c["close"]) for c in h1]
                e20 = sum(closes[-20:]) / 20.0
                e50 = sum(closes[-50:]) / 50.0
                e200 = sum(closes[-200:]) / 200.0
                last_c = closes[-1]
                if e20 > e50 > e200 and last_c <= e20 * 1.002:
                    sl = round(e50 * 0.995, 2)
                    tp = round(last_c + 2.0 * (last_c - sl), 2)
                    candidates.append({"symbol": sym, "side": "BUY", "strategy_track": "CRYPTO_LONGTERM", "entry_price": last_c, "sl_price": sl, "tp_price": tp})
                elif e20 < e50 < e200 and last_c >= e20 * 0.998:
                    sl = round(e50 * 1.005, 2)
                    tp = round(last_c - 2.0 * (sl - last_c), 2)
                    candidates.append({"symbol": sym, "side": "SELL", "strategy_track": "CRYPTO_LONGTERM", "entry_price": last_c, "sl_price": sl, "tp_price": tp})
            except Exception as e:
                logger.warning(f"[CRYPTO_LONGTERM:{sym}] Scan error: {e}")
        return candidates

    async def scan_scalping_opportunities(self, adapter, open_positions: list) -> list:
        """Evaluate Gold Scalping (AutomatedHighFrequencyScalpingEngine) and Forex Scalping (MicroScalpingEngine).
        All candidates are routed through SharedCentralRiskManager.preflight_check() with TRACK_1_SCALPING permanently blocked."""
        candidates = []
        # Gold Scalping (XAUUSD)
        try:
            xau_candles = await adapter.get_historical_candles("XAUUSD", timeframe="M5", count=60)
            if xau_candles and len(xau_candles) >= 20:
                gold_res = self.gold_scalp_engine.evaluate_market_opportunity(xau_candles)
                if gold_res and gold_res.get("action") in ("BUY", "SELL"):
                    candidates.append({
                        "symbol": "XAUUSD",
                        "side": gold_res["action"],
                        "strategy_track": "GOLD_SCALPING",
                        "entry_price": gold_res.get("entry_price"),
                        "sl_price": gold_res.get("sl_price"),
                        "tp_price": gold_res.get("tp_price"),
                    })
        except Exception as e:
            logger.warning(f"[GOLD_SCALPING] Scan error: {e}")

        # Crypto Scalping (BTCUSD, ETHUSD)
        for sym in CRYPTO_SYMBOLS:
            try:
                c_candles = await adapter.get_historical_candles(sym, timeframe="M5", count=60)
                if c_candles and len(c_candles) >= 20:
                    c_res = self.gold_scalp_engine.evaluate_market_opportunity(c_candles)
                    if c_res and c_res.get("action") in ("BUY", "SELL"):
                        candidates.append({
                            "symbol": sym,
                            "side": c_res["action"],
                            "strategy_track": "CRYPTO_SCALPING",
                            "entry_price": c_res.get("entry_price"),
                            "sl_price": c_res.get("sl_price"),
                            "tp_price": c_res.get("tp_price"),
                        })
            except Exception as e:
                logger.warning(f"[CRYPTO_SCALPING:{sym}] Scan error: {e}")

        # Forex Scalping (EURUSD, GBPUSD)
        for sym in ("EURUSD", "GBPUSD"):
            try:
                fx_candles = await adapter.get_historical_candles(sym, timeframe="M5", count=60)
                if fx_candles and len(fx_candles) >= 20:
                    fx_res = self.forex_scalp_engine.evaluate_setup(sym, fx_candles)
                    if fx_res and fx_res.get("signal") in ("BUY", "SELL"):
                        candidates.append({
                            "symbol": sym,
                            "side": fx_res["signal"],
                            "strategy_track": "FOREX_SCALPING",
                            "entry_price": fx_res.get("entry_price"),
                            "sl_price": fx_res.get("sl_price"),
                            "tp_price": fx_res.get("tp_price"),
                        })
            except Exception as e:
                logger.warning(f"[FOREX_SCALPING:{sym}] Scan error: {e}")
        return candidates

    async def verify_environment(self, adapter):
        logger.info("Verifying environment invariants...")
        assert REAL_TRADING_PERMANENTLY_LOCKED is True, "CRITICAL: Real trading lock is not True!"
        assert adapter.server_name == SERVER_NAME, f"Server mismatch: {adapter.server_name} != {SERVER_NAME}"
        assert adapter.environment == "DEMO", "Adapter environment must be DEMO!"
        
        summary = await adapter.get_account_summary(force_refresh=True)
        equity = float(summary.get("equity") or 0.0)
        balance = float(summary.get("balance") or 0.0)
        logger.info(f"Verified Exness Demo Account {ACCOUNT_ID} on {SERVER_NAME}. Equity: ${equity:.2f}, Balance: ${balance:.2f}")
        return summary

    @staticmethod
    def filter_closed_candles(raw_candles: list, tf_sec: int, now_utc: datetime, is_d1: bool = False) -> list:
        """Remediation A: Strict UTC closed-candle filter (bar_open_utc + tf_sec <= now_utc)."""
        if not isinstance(raw_candles, list):
            return []
        now_ts = now_utc.timestamp()
        by_ts = {}
        for c in raw_candles:
            if not isinstance(c, dict):
                continue
            raw_t = c.get("timestamp") if c.get("timestamp") is not None else c.get("time")
            if raw_t is None:
                continue
            try:
                if isinstance(raw_t, (int, float)):
                    open_dt = datetime.fromtimestamp(float(raw_t), tz=timezone.utc)
                else:
                    s = str(raw_t).strip()
                    if s.endswith("Z"):
                        s = s[:-1] + "+00:00"
                    open_dt = datetime.fromisoformat(s)
                    if open_dt.tzinfo is None:
                        open_dt = open_dt.replace(tzinfo=timezone.utc)
                    else:
                        open_dt = open_dt.astimezone(timezone.utc)
                open_ts = open_dt.timestamp()
            except Exception:
                continue

            # Exclude forming or future candles
            if open_ts + tf_sec > now_ts + 1e-6:
                continue

            try:
                bo = float(c.get("bid_open") if c.get("bid_open") is not None else c.get("open"))
                bh = float(c.get("bid_high") if c.get("bid_high") is not None else c.get("high"))
                bl = float(c.get("bid_low") if c.get("bid_low") is not None else c.get("low"))
                bc = float(c.get("bid_close") if c.get("bid_close") is not None else c.get("close"))
                ao = float(c.get("ask_open") if c.get("ask_open") is not None else bo)
                ah = float(c.get("ask_high") if c.get("ask_high") is not None else bh)
                al = float(c.get("ask_low") if c.get("ask_low") is not None else bl)
                ac = float(c.get("ask_close") if c.get("ask_close") is not None else bc)
                spr = float(c.get("spread_price") if c.get("spread_price") is not None else round(ac - bc, 6))
            except Exception:
                continue

            import math as _m
            if not all(_m.isfinite(x) and x > 0 for x in (bo, bh, bl, bc, ao, ah, al, ac)):
                continue
            if bh < max(bo, bc) or bl > min(bo, bc) or ah < max(ao, ac) or al > min(ao, ac) or bc > ac + 1e-6:
                continue

            iso_str = open_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            if is_d1:
                by_ts[open_ts] = {"time": iso_str, "close": bc}
            else:
                by_ts[open_ts] = {
                    "time": iso_str,
                    "bid_open": bo, "bid_high": bh, "bid_low": bl, "bid_close": bc,
                    "ask_open": ao, "ask_high": ah, "ask_low": al, "ask_close": ac,
                    "spread_close": spr,
                }
        return [by_ts[k] for k in sorted(by_ts.keys())]

    # ─── Command 15 Remediations: Transactional Leg Lifecycle, Exness Response Normalisation & Fail-Closed Post-Fill ───

    # ─── Command 17 Remediations: Five Critical Execution-Reliability Fixes ───

    @staticmethod
    def _leg_state_path(account_id: str) -> str:
        safe_id = "".join(ch for ch in str(account_id) if ch.isalnum() or ch in ("_", "-"))
        return f"/opt/tauric-platform-staging/backend/data/a2_leg_state_{safe_id}.json"

    @staticmethod
    def _leg_lock_path(account_id: str) -> str:
        safe_id = "".join(ch for ch in str(account_id) if ch.isalnum() or ch in ("_", "-"))
        return f"/opt/tauric-platform-staging/backend/data/a2_leg_state_{safe_id}.lock"

    @staticmethod
    def _incident_path(account_id: str) -> str:
        safe_id = "".join(ch for ch in str(account_id) if ch.isalnum() or ch in ("_", "-"))
        return f"/opt/tauric-platform-staging/backend/data/a2_post_fill_incidents_{safe_id}.jsonl"

    @classmethod
    def _default_leg_state_doc(cls, account_id: str) -> dict:
        return {
            "schema_version": "3.0",
            "account_id": str(account_id),
            "strategy_id": "LT_STRUCTURE_EURUSD_A2",
            "state": "AVAILABLE",
            "new_entries_disabled": False,
            "halt_reason": None,
            "last_confirmed_leg_id": None,
            "last_leg_id": None,
            "pending_reservation": None,
            "confirmed_legs": {},
            "reconciled_deal_ids": [],
            "history": [],
            "updated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    @classmethod
    def _write_leg_state_doc_unlocked(cls, account_id: str, doc: dict) -> bool:
        path = cls._leg_state_path(account_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp_path = f"{path}.tmp.{os.getpid()}.{time.time_ns()}"
        doc = dict(doc)
        doc["account_id"] = str(account_id)
        doc["strategy_id"] = "LT_STRUCTURE_EURUSD_A2"
        doc["last_leg_id"] = doc.get("last_confirmed_leg_id")
        doc["updated_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            with open(tmp_path, "w") as tf:
                json.dump(doc, tf, indent=2)
                tf.flush()
                os.fsync(tf.fileno())
            os.replace(tmp_path, path)
            return True
        except Exception:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            return False

    @classmethod
    def _read_leg_state_doc_unlocked(cls, account_id: str) -> tuple[str, dict | None]:
        """Returns ('OK'|'MISSING'|'CORRUPT', doc_or_none)."""
        path = cls._leg_state_path(account_id)
        if not os.path.exists(path):
            return "MISSING", None
        try:
            with open(path, "r") as f:
                data = json.load(f)
            if not isinstance(data, dict) or data.get("account_id") != str(account_id):
                return "CORRUPT", None
            if "last_confirmed_leg_id" not in data and "last_leg_id" not in data:
                return "CORRUPT", None
            st = str(data.get("state") or "AVAILABLE").upper()
            valid_states = (
                "AVAILABLE",
                "PENDING",
                "CONFIRMED_FILLED",
                "REJECTED_OR_EXPIRED",
                "AMBIGUOUS_LOCKED",
                "HALTED_POST_FILL_BREACH_OR_INCIDENT",
            )
            if st not in valid_states:
                return "CORRUPT", None
            if "last_confirmed_leg_id" not in data:
                data["last_confirmed_leg_id"] = data.get("last_leg_id")
            if "confirmed_legs" not in data or not isinstance(data["confirmed_legs"], dict):
                c_legs = {}
                if data.get("last_confirmed_leg_id"):
                    c_legs[str(data["last_confirmed_leg_id"])] = {"reconstructed": True}
                data["confirmed_legs"] = c_legs
            if "reconciled_deal_ids" not in data or not isinstance(data["reconciled_deal_ids"], list):
                data["reconciled_deal_ids"] = []
            if "new_entries_disabled" not in data:
                data["new_entries_disabled"] = (st in ("AMBIGUOUS_LOCKED", "HALTED_POST_FILL_BREACH_OR_INCIDENT"))
            if "pending_reservation" not in data:
                data["pending_reservation"] = None
            if "history" not in data or not isinstance(data["history"], list):
                data["history"] = []
            return "OK", data
        except Exception:
            return "CORRUPT", None

    def ensure_post_fill_guard(self):
        if not hasattr(self, "post_fill_guard") or self.post_fill_guard is None:
            from app.services.brokers.shared_risk_manager import PostFillRiskBreachGuard
            self.post_fill_guard = PostFillRiskBreachGuard(max_risk_usd=10.0)
        if not hasattr(self, "_reconciled_fill_tickets"):
            self._reconciled_fill_tickets = set()
        if not hasattr(self, "_reconciled_deal_ids"):
            self._reconciled_deal_ids = set()
        if not hasattr(self, "critical_incidents"):
            self.critical_incidents = []

    @staticmethod
    def _ensure_deal_ledger_table(conn) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS a2_deal_ledger (
                account_id TEXT NOT NULL,
                deal_id TEXT NOT NULL,
                broker_ticket TEXT NOT NULL,
                order_id TEXT NOT NULL,
                leg_id TEXT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                volume_lots REAL NOT NULL,
                fill_price REAL NOT NULL,
                recorded_at_utc TEXT NOT NULL,
                PRIMARY KEY (account_id, deal_id)
            )
        """)

    def _persist_disable_in_state_file(self, account_id: str, code: str, detail: str) -> bool:
        """Remediation 5: Durably persist new_entries_disabled = True in the leg state file."""
        import fcntl
        lock_path = self._leg_lock_path(account_id)
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)
        try:
            with open(lock_path, "a+") as lf:
                fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
                try:
                    status, doc = self._read_leg_state_doc_unlocked(account_id)
                    if status != "OK" or doc is None:
                        doc = self._default_leg_state_doc(account_id)
                    doc["new_entries_disabled"] = True
                    doc["halt_reason"] = f"{code}: {detail}"
                    if doc.get("state") not in ("AMBIGUOUS_LOCKED",):
                        doc["state"] = "HALTED_POST_FILL_BREACH_OR_INCIDENT"
                    doc["history"].append({
                        "event": "HALTED_NEW_ENTRIES_DISABLED",
                        "code": str(code),
                        "detail": str(detail),
                        "at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    })
                    if len(doc["history"]) > 50:
                        doc["history"] = doc["history"][-50:]
                    return self._write_leg_state_doc_unlocked(account_id, doc)
                finally:
                    fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
        except Exception:
            return False

    def record_critical_incident(self, account_id: str, code: str, detail: str, context: dict | None = None, persist_state_halt: bool = True) -> dict:
        """Remediation 5: Immediately disable new entries in-memory AND durably on disk (both JSONL incident log and state file)."""
        self.ensure_post_fill_guard()
        self.post_fill_guard.new_entries_disabled = True
        inc = {
            "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "account_id": str(account_id),
            "incident_code": str(code),
            "detail": str(detail),
            "new_entries_disabled": True,
            "context": context or {},
        }
        self.critical_incidents.append(inc)
        inc_path = self._incident_path(account_id)
        try:
            os.makedirs(os.path.dirname(inc_path), exist_ok=True)
            with open(inc_path, "a") as f:
                f.write(json.dumps(inc) + "\n")
                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            logger.critical(f"[LT_STRUCTURE_EURUSD_A2] Failed to append incident file {inc_path}: {e}")
        if persist_state_halt:
            self._persist_disable_in_state_file(account_id, code, detail)
        logger.critical(f"[LT_STRUCTURE_EURUSD_A2] CRITICAL INCIDENT [{code}]: {detail}")
        return inc

    @classmethod
    def _has_durable_incidents_on_disk(cls, account_id: str) -> tuple[bool, list[dict]]:
        inc_path = cls._incident_path(account_id)
        if not os.path.exists(inc_path):
            return False, []
        incidents = []
        try:
            with open(inc_path, "r") as f:
                for line in f:
                    s = line.strip()
                    if not s:
                        continue
                    rec = json.loads(s)
                    if isinstance(rec, dict) and not rec.get("resolved", False):
                        incidents.append(rec)
            return len(incidents) > 0, incidents
        except Exception:
            # Corrupt incident file -> fail closed!
            return True, [{"incident_code": "CORRUPT_INCIDENT_LOG", "detail": "Incident JSONL log is unreadable or corrupt."}]

    @classmethod
    def load_a2_leg_state(cls, account_id: str) -> tuple[bool, str | None]:
        """Read-only inspection of persistent leg deduplication state; fails closed on corruption, unresolved PENDING/AMBIGUOUS/HALTED state, or durable incident log."""
        import fcntl
        has_inc, _ = cls._has_durable_incidents_on_disk(account_id)
        if has_inc:
            return False, None
        lock_path = cls._leg_lock_path(account_id)
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)
        try:
            with open(lock_path, "a+") as lf:
                fcntl.flock(lf.fileno(), fcntl.LOCK_SH)
                try:
                    status, doc = cls._read_leg_state_doc_unlocked(account_id)
                finally:
                    fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
            if status in ("CORRUPT", "MISSING") or doc is None:
                return False, None
            if (
                doc.get("new_entries_disabled") is True
                or doc.get("state") in ("PENDING", "AMBIGUOUS_LOCKED", "HALTED_POST_FILL_BREACH_OR_INCIDENT")
                or doc.get("pending_reservation") is not None
            ):
                return False, doc.get("last_confirmed_leg_id")
            return True, doc.get("last_confirmed_leg_id")
        except Exception:
            return False, None

    @classmethod
    def save_a2_leg_state(cls, account_id: str, leg_id: str | None, state: str = "CONFIRMED_FILLED", fill_meta: dict | None = None) -> bool:
        """Atomic locked update of persistent leg deduplication state."""
        import fcntl
        lock_path = cls._leg_lock_path(account_id)
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)
        try:
            with open(lock_path, "a+") as lf:
                fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
                try:
                    status, doc = cls._read_leg_state_doc_unlocked(account_id)
                    if status != "OK" or doc is None:
                        doc = cls._default_leg_state_doc(account_id)
                    doc["state"] = state
                    doc["pending_reservation"] = None
                    if leg_id is not None and state == "CONFIRMED_FILLED":
                        doc["last_confirmed_leg_id"] = str(leg_id)
                        doc["confirmed_legs"][str(leg_id)] = fill_meta or {
                            "confirmed_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                        }
                    elif leg_id is None and state == "AVAILABLE":
                        doc["last_confirmed_leg_id"] = None
                    return cls._write_leg_state_doc_unlocked(account_id, doc)
                finally:
                    fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
        except Exception:
            return False

    def reserve_a2_leg_pending(self, account_id: str, leg_id: str, signal_meta: dict | None = None) -> tuple[bool, str]:
        """Atomically transition an unconsumed leg to PENDING reservation so concurrent workers cannot duplicate it."""
        import fcntl
        if not leg_id or not str(leg_id).strip():
            return False, "INVALID_LEG_ID"
        has_inc, _ = self._has_durable_incidents_on_disk(account_id)
        if has_inc:
            return False, "HALTED_BY_DURABLE_INCIDENT"
        leg_str = str(leg_id).strip()
        lock_path = self._leg_lock_path(account_id)
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)
        try:
            with open(lock_path, "a+") as lf:
                fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
                try:
                    status, doc = self._read_leg_state_doc_unlocked(account_id)
                    if status != "OK" or doc is None:
                        return False, f"STATE_{status}"
                    if (
                        doc.get("new_entries_disabled") is True
                        or doc.get("state") in ("PENDING", "AMBIGUOUS_LOCKED", "HALTED_POST_FILL_BREACH_OR_INCIDENT")
                        or doc.get("pending_reservation") is not None
                    ):
                        return False, "PENDING_OR_HALTED_STATE_ACTIVE"
                    if doc.get("last_confirmed_leg_id") == leg_str or leg_str in (doc.get("confirmed_legs") or {}):
                        return False, "LEG_ALREADY_CONFIRMED"
                    res_id = f"RES-{os.getpid()}-{int(time.time() * 1000)}"
                    doc["state"] = "PENDING"
                    doc["pending_reservation"] = {
                        "reservation_id": res_id,
                        "leg_id": leg_str,
                        "reserved_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "pid": os.getpid(),
                        "signal_meta": {**(signal_meta or {}), "order_submitted": False},
                    }
                    doc["history"].append({"event": "RESERVED_PENDING", "leg_id": leg_str, "reservation_id": res_id})
                    if len(doc["history"]) > 50:
                        doc["history"] = doc["history"][-50:]
                    if not self._write_leg_state_doc_unlocked(account_id, doc):
                        return False, "STATE_WRITE_FAILED"
                    return True, res_id
                finally:
                    fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
        except Exception as e:
            return False, f"LOCK_ERROR:{e}"

    def mark_a2_leg_order_submitting(self, account_id: str, leg_id: str, reservation_id: str | None = None, idempotency_key: str | None = None) -> bool:
        """
        Remediation 1 (Command 17): Atomically persist order_submitted = True BEFORE invoking adapter.place_market_order().
        Guarantees that if the process crashes during or immediately after broker submission, restart reconciliation
        recognises that an order was dispatched to the broker and never mistakes the crash for a pre-submission interruption.
        """
        import fcntl
        if not leg_id or not str(leg_id).strip():
            return False
        leg_str = str(leg_id).strip()
        lock_path = self._leg_lock_path(account_id)
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)
        try:
            with open(lock_path, "a+") as lf:
                fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
                try:
                    status, doc = self._read_leg_state_doc_unlocked(account_id)
                    if status != "OK" or doc is None:
                        return False
                    pend = doc.get("pending_reservation")
                    if not isinstance(pend, dict) or pend.get("leg_id") != leg_str:
                        return False
                    if reservation_id and pend.get("reservation_id") != reservation_id:
                        return False
                    s_meta = dict(pend.get("signal_meta") or {})
                    s_meta["order_submitted"] = True
                    s_meta["submitted_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    if idempotency_key:
                        s_meta["idempotency_key"] = str(idempotency_key)
                    pend["signal_meta"] = s_meta
                    doc["pending_reservation"] = pend
                    doc["state"] = "PENDING"
                    doc["history"].append({
                        "event": "ORDER_SUBMITTING_PERSISTED",
                        "leg_id": leg_str,
                        "reservation_id": pend.get("reservation_id"),
                        "idempotency_key": idempotency_key,
                        "at_utc": s_meta["submitted_at_utc"],
                    })
                    if len(doc["history"]) > 50:
                        doc["history"] = doc["history"][-50:]
                    return self._write_leg_state_doc_unlocked(account_id, doc)
                finally:
                    fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
        except Exception:
            return False

    def release_a2_leg_reservation(self, account_id: str, leg_id: str, reason: str, reservation_id: str | None = None) -> bool:
        """Transition a PENDING leg to REJECTED_OR_EXPIRED when quote/spread/sizing/preflight/order-rejection occurs before any fill."""
        import fcntl
        leg_str = str(leg_id).strip()
        lock_path = self._leg_lock_path(account_id)
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)
        try:
            with open(lock_path, "a+") as lf:
                fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
                try:
                    status, doc = self._read_leg_state_doc_unlocked(account_id)
                    if status != "OK" or doc is None:
                        return False
                    pend = doc.get("pending_reservation")
                    if not isinstance(pend, dict) or pend.get("leg_id") != leg_str:
                        return False
                    if reservation_id and pend.get("reservation_id") != reservation_id:
                        return False
                    doc["pending_reservation"] = None
                    if doc.get("new_entries_disabled") is True:
                        doc["state"] = "HALTED_POST_FILL_BREACH_OR_INCIDENT"
                    else:
                        doc["state"] = "REJECTED_OR_EXPIRED"
                    doc["last_rejection_reason"] = str(reason)
                    doc["history"].append({
                        "event": "REJECTED_OR_EXPIRED",
                        "leg_id": leg_str,
                        "reason": str(reason),
                        "at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    })
                    if len(doc["history"]) > 50:
                        doc["history"] = doc["history"][-50:]
                    return self._write_leg_state_doc_unlocked(account_id, doc)
                finally:
                    fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
        except Exception:
            return False

    def confirm_a2_leg_fill(self, account_id: str, leg_id: str, fill_meta: dict, disable_new_entries: bool = False, halt_reason: str | None = None) -> bool:
        """Durably transition a leg to CONFIRMED_FILLED (or HALTED_POST_FILL_BREACH_OR_INCIDENT if risk breach occurred) with broker & deal identifiers."""
        import fcntl
        if not leg_id or not str(leg_id).strip():
            return False
        leg_str = str(leg_id).strip()
        lock_path = self._leg_lock_path(account_id)
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)
        try:
            with open(lock_path, "a+") as lf:
                fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
                try:
                    status, doc = self._read_leg_state_doc_unlocked(account_id)
                    if status != "OK" or doc is None:
                        doc = self._default_leg_state_doc(account_id)
                    doc["pending_reservation"] = None
                    if disable_new_entries or doc.get("new_entries_disabled") is True:
                        doc["new_entries_disabled"] = True
                        doc["state"] = "HALTED_POST_FILL_BREACH_OR_INCIDENT"
                        if halt_reason:
                            doc["halt_reason"] = str(halt_reason)
                    else:
                        doc["state"] = "CONFIRMED_FILLED"
                    doc["last_confirmed_leg_id"] = leg_str
                    doc["confirmed_legs"][leg_str] = {
                        **(fill_meta or {}),
                        "confirmed_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    }
                    rec_deals = list(doc.get("reconciled_deal_ids") or [])
                    for d in (fill_meta or {}).get("deal_ids") or []:
                        ds = str(d).strip()
                        if ds and ds not in rec_deals:
                            rec_deals.append(ds)
                    doc["reconciled_deal_ids"] = rec_deals
                    doc["history"].append({
                        "event": "CONFIRMED_FILLED",
                        "leg_id": leg_str,
                        "broker_ticket": (fill_meta or {}).get("broker_ticket"),
                        "order_id": (fill_meta or {}).get("order_id"),
                        "deal_ids": (fill_meta or {}).get("deal_ids"),
                        "new_entries_disabled": doc.get("new_entries_disabled", False),
                        "at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    })
                    if len(doc["history"]) > 50:
                        doc["history"] = doc["history"][-50:]
                    return self._write_leg_state_doc_unlocked(account_id, doc)
                finally:
                    fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
        except Exception:
            return False

    def mark_a2_leg_ambiguous(self, account_id: str, leg_id: str | None, detail: str, raw_meta: dict | None = None) -> bool:
        """Transition state to AMBIGUOUS_LOCKED and set new_entries_disabled = True so an ambiguous order is never retried."""
        import fcntl
        lock_path = self._leg_lock_path(account_id)
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)
        try:
            with open(lock_path, "a+") as lf:
                fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
                try:
                    status, doc = self._read_leg_state_doc_unlocked(account_id)
                    if status != "OK" or doc is None:
                        doc = self._default_leg_state_doc(account_id)
                    doc["state"] = "AMBIGUOUS_LOCKED"
                    doc["new_entries_disabled"] = True
                    doc["halt_reason"] = f"AMBIGUOUS_LOCKED: {detail}"
                    doc["ambiguous_detail"] = {
                        "leg_id": leg_id,
                        "detail": str(detail),
                        "raw_meta": raw_meta or {},
                        "at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    }
                    return self._write_leg_state_doc_unlocked(account_id, doc)
                finally:
                    fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
        except Exception:
            return False

    @staticmethod
    def _extract_eurusd_broker_history(raw_orders: list, raw_deals: list) -> tuple[list[dict], list[dict]]:
        """Normalises read-only Exness order history and deal history items for EURUSD."""
        eur_orders = []
        for it in raw_orders or []:
            if not isinstance(it, dict):
                continue
            o = it.get("order") if isinstance(it.get("order"), dict) else it
            sym = str(o.get("instrument") or o.get("symbol") or "").upper().rstrip("RM")
            if sym == "EURUSD":
                eur_orders.append(o)
        eur_deals = []
        for it in raw_deals or []:
            if not isinstance(it, dict):
                continue
            d = it.get("deal") if isinstance(it.get("deal"), dict) else it
            sym = str(d.get("instrument") or d.get("symbol") or "").upper().rstrip("RM")
            if sym == "EURUSD":
                eur_deals.append(d)
        return eur_orders, eur_deals

    async def reconcile_exness_terminal_operation(
        self,
        adapter,
        raw_res: dict,
        sig: dict,
        account_id: str = ACCOUNT_ID,
    ) -> dict:
        """
        Remediation 3 (Command 17): Reconcile actual ExnessTraderAPIClient.submit_order() operation response
        against genuine read-only broker execution records (snapshot open positions, order history, deal history).
        - Never fabricates position_id, order_id, deal_id, or fill_price.
        - If raw_res is an EXNESS_TERMINAL_V1 confirmed operation lacking execution identifiers, queries
          read-only broker interfaces (get_open_positions, get_order_history, get_trade_history) to match the
          genuine broker execution records.
        - If complete reconciliation is impossible (missing order_id, missing deal/position, or ambiguous multiple matches),
          returns the unmodified response so normalize_exness_order_response() fails closed as AMBIGUOUS.
        """
        if not isinstance(raw_res, dict) or adapter is None:
            return raw_res

        top_st = str(raw_res.get("status") or "").upper()
        op_obj = raw_res.get("operation")
        if top_st != "FILLED" or not isinstance(op_obj, dict):
            return raw_res
        op_st = str(op_obj.get("status") or "").lower()
        if op_st not in ("confirmed", "filled", "executed"):
            return raw_res

        # Check if operation already has complete execution identifiers
        has_pos = bool(str(op_obj.get("position_id") or op_obj.get("ticket") or "").strip())
        has_ord = bool(str(op_obj.get("order_id") or op_obj.get("order") or "").strip())
        has_px = any(op_obj.get(k) is not None for k in ("fill_price", "execution_price", "open_price", "price")) or isinstance(op_obj.get("deals"), list)
        if has_pos and has_ord and has_px:
            return raw_res

        # Read-only broker reconciliation via adapter
        try:
            client = getattr(adapter, "client", None)
            if client is not None and hasattr(client, "get_trading_snapshot"):
                await client.get_trading_snapshot(force_refresh=True)
        except Exception:
            pass

        try:
            open_positions = await adapter.get_open_positions() if hasattr(adapter, "get_open_positions") else []
        except Exception:
            open_positions = []

        try:
            raw_orders = await adapter.get_order_history(limit=100) if hasattr(adapter, "get_order_history") else []
        except Exception:
            raw_orders = []

        try:
            if hasattr(adapter, "get_trade_history"):
                raw_deals = await adapter.get_trade_history(limit=100)
            elif getattr(adapter, "client", None) is not None and hasattr(adapter.client, "get_trade_history"):
                raw_deals = await adapter.client.get_trade_history(limit=100)
            else:
                raw_deals = []
        except Exception:
            raw_deals = []

        eur_orders, eur_deals = self._extract_eurusd_broker_history(raw_orders, raw_deals)

        # Exclude tickets and order_ids already recorded in TradeMemoryService
        known_tickets = set(self._reconciled_fill_tickets)
        known_orders = set()
        known_deals = set(self._reconciled_deal_ids)
        try:
            tm_rows = TradeMemoryService.get_trade_history(account_id=str(account_id), execution_type="ACTUAL_DEMO", limit=200)
            for r in tm_rows:
                bt = str(r.get("broker_ticket") or "").strip()
                oid = str(r.get("order_id") or "").strip()
                did = str(r.get("deal_id") or "").strip()
                if bt:
                    known_tickets.add(bt)
                if oid:
                    known_orders.add(oid)
                if did:
                    for part in did.split(","):
                        if part.strip():
                            known_deals.add(part.strip())
        except Exception:
            pass

        op_id = str(raw_res.get("operation_id") or op_obj.get("operation_id") or "").strip()
        client_req_id = str(
            op_obj.get("client_request_id")
            or ((raw_res.get("ack") or {}).get("client_request_id") if isinstance(raw_res.get("ack"), dict) else "")
            or raw_res.get("idempotency_key")
            or ""
        ).strip()
        exp_side = str((sig or {}).get("side") or ((raw_res.get("payload") or {}).get("side") if isinstance(raw_res.get("payload"), dict) else "") or "").upper()

        # 1. Match open EURUSD position in snapshot (not already in known_tickets)
        eur_open = [
            p for p in (open_positions or [])
            if isinstance(p, dict)
            and str(p.get("symbol") or p.get("instrument") or "").upper().rstrip("RM") == "EURUSD"
            and str(p.get("position_id") or p.get("ticket") or "").strip() not in known_tickets
        ]
        if exp_side in ("BUY", "SELL"):
            eur_open = [p for p in eur_open if str(p.get("side") or p.get("direction") or "").upper() == exp_side]

        matched_pos_id = None
        matched_ord_id = None
        matched_deals = []
        matched_px = None
        matched_vol = None

        if len(eur_open) == 1:
            pos = eur_open[0]
            matched_pos_id = str(pos.get("position_id") or pos.get("ticket") or "").strip()
            try:
                matched_px = float(pos.get("open_price") or pos.get("entry_price") or pos.get("price"))
                matched_vol = float(pos.get("volume"))
            except Exception:
                matched_px = None
                matched_vol = None
        elif len(eur_open) > 1:
            # Ambiguous multiple untracked EURUSD positions -> refuse to guess!
            return raw_res

        # 2. Match deals from deal history
        cand_deals = []
        for d in eur_deals:
            did = str(d.get("deal_id") or d.get("deal_ticket") or d.get("id") or "").strip()
            if not did or did in known_deals:
                continue
            d_entry = str(d.get("entry") or d.get("type") or "IN").upper()
            if d_entry in ("OUT", "CLOSE"):
                continue
            d_pos = str(d.get("position_id") or d.get("ticket") or "").strip()
            d_op = str(d.get("operation_id") or "").strip()
            d_creq = str(d.get("client_request_id") or "").strip()
            if matched_pos_id and d_pos == matched_pos_id:
                cand_deals.append(d)
            elif not matched_pos_id and ((op_id and d_op == op_id) or (client_req_id and d_creq == client_req_id)):
                cand_deals.append(d)

        if not matched_pos_id and cand_deals:
            pos_set = {str(d.get("position_id") or d.get("ticket") or "").strip() for d in cand_deals if str(d.get("position_id") or d.get("ticket") or "").strip()}
            if len(pos_set) == 1:
                matched_pos_id = next(iter(pos_set))

        if matched_pos_id and not cand_deals:
            # Also check if any deals match matched_pos_id regardless of entry field
            for d in eur_deals:
                did = str(d.get("deal_id") or d.get("deal_ticket") or d.get("id") or "").strip()
                d_pos = str(d.get("position_id") or d.get("ticket") or "").strip()
                d_entry = str(d.get("entry") or d.get("type") or "IN").upper()
                if did and d_pos == matched_pos_id and d_entry not in ("OUT", "CLOSE"):
                    cand_deals.append(d)

        # 3. Match genuine order_id from deal records or order history (NEVER use protective_order_id or operation_id)
        for d in cand_deals:
            oid = str(d.get("order_id") or d.get("order") or "").strip()
            if oid and oid != op_id and oid != matched_pos_id:
                matched_ord_id = oid
                break

        if not matched_ord_id and eur_orders:
            cand_orders = []
            for o in eur_orders:
                oid = str(o.get("order_id") or o.get("order") or o.get("id") or "").strip()
                if not oid or oid in known_orders or oid == op_id:
                    continue
                o_type = str(o.get("order_type") or o.get("type") or "").lower()
                if o_type == "sltp":
                    continue
                o_pos = str(o.get("position_id") or o.get("ticket") or "").strip()
                o_op = str(o.get("operation_id") or "").strip()
                o_creq = str(o.get("client_request_id") or "").strip()
                if (matched_pos_id and o_pos == matched_pos_id) or (op_id and o_op == op_id) or (client_req_id and o_creq == client_req_id):
                    cand_orders.append((oid, o_pos, o))
            if len(cand_orders) == 1:
                matched_ord_id, o_pos, o_rec = cand_orders[0]
                if not matched_pos_id and o_pos:
                    matched_pos_id = o_pos
                if matched_px is None and o_rec.get("fill_price") is not None:
                    try:
                        matched_px = float(o_rec.get("fill_price"))
                    except Exception:
                        pass
                if matched_vol is None and o_rec.get("filled_volume") is not None:
                    try:
                        matched_vol = float(o_rec.get("filled_volume"))
                    except Exception:
                        pass

        # Construct reconciled operation dict ONLY from genuine matched broker fields
        enriched = dict(raw_res)
        enriched_op = dict(op_obj)
        if matched_pos_id:
            enriched_op["position_id"] = matched_pos_id
        if matched_ord_id:
            enriched_op["order_id"] = matched_ord_id
        if cand_deals:
            clean_deals = []
            for d in cand_deals:
                did = str(d.get("deal_id") or d.get("deal_ticket") or d.get("id") or "").strip()
                d_oid = str(d.get("order_id") or d.get("order") or matched_ord_id or "").strip()
                d_pos = str(d.get("position_id") or d.get("ticket") or matched_pos_id or "").strip()
                clean_deals.append({
                    "deal_id": did,
                    "position_id": d_pos,
                    "order_id": d_oid,
                    "price": d.get("price") or d.get("fill_price") or d.get("execution_price"),
                    "volume": d.get("volume") or d.get("filled_volume"),
                })
            enriched_op["deals"] = clean_deals
            if len(clean_deals) == 1 and clean_deals[0].get("deal_id"):
                enriched_op["deal_id"] = clean_deals[0]["deal_id"]
        else:
            if matched_px is not None:
                enriched_op["fill_price"] = matched_px
            if matched_vol is not None:
                enriched_op["filled_volume"] = matched_vol

        enriched["operation"] = enriched_op
        enriched["reconciled_from_broker_records"] = True
        return enriched

    async def reconcile_or_initialize_a2_leg_state(self, adapter, account_id: str = ACCOUNT_ID) -> tuple[bool, str | None, str]:
        """
        Remediations 1, 2, 4, 5 (Command 17):
        - Restores durable post-fill safety locks (incident JSONL file, state file new_entries_disabled, and TradeMemory post_fill_within_budget=False)
          BEFORE any new-entry evaluation after restart.
        - Inspects read-only broker snapshot (get_open_positions), order history (get_order_history), and deal history (get_trade_history)
          as well as TradeMemoryService and a2_deal_ledger.
        - Never expires a PENDING reservation if order_submitted=True or if broker order/deal history shows an untracked EURUSD execution.
        """
        import fcntl
        self.ensure_post_fill_guard()
        lock_path = self._leg_lock_path(account_id)
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)

        # 1. Check durable incident log on disk first (Remediation 5)
        has_inc, inc_list = self._has_durable_incidents_on_disk(account_id)
        if has_inc:
            self.post_fill_guard.new_entries_disabled = True
            self._persist_disable_in_state_file(account_id, "RESTORED_DURABLE_INCIDENT_LOCK", "Unresolved post-fill incident present on disk.")
            return False, None, "HALTED_BY_DURABLE_INCIDENT_LOG"

        with open(lock_path, "a+") as lf:
            fcntl.flock(lf.fileno(), fcntl.LOCK_SH)
            try:
                status, doc = self._read_leg_state_doc_unlocked(account_id)
            finally:
                fcntl.flock(lf.fileno(), fcntl.LOCK_UN)

        if status == "CORRUPT":
            self.record_critical_incident(
                account_id,
                "CORRUPT_DEDUPLICATION_STATE",
                "Persistent A2 deduplication state file is corrupt or account-mismatched; failing closed.",
            )
            return False, None, "CORRUPT_STATE_FAIL_CLOSED"

        # 2. Query read-only broker snapshot, order history, and deal history (Remediation 2)
        try:
            open_positions = await adapter.get_open_positions() if adapter is not None else []
            if not isinstance(open_positions, list):
                raise RuntimeError("adapter.get_open_positions() did not return a list")
            raw_orders = await adapter.get_order_history(limit=100) if (adapter is not None and hasattr(adapter, "get_order_history")) else []
            if adapter is not None and hasattr(adapter, "get_trade_history"):
                raw_deals = await adapter.get_trade_history(limit=100)
            elif adapter is not None and getattr(adapter, "client", None) is not None and hasattr(adapter.client, "get_trade_history"):
                raw_deals = await adapter.client.get_trade_history(limit=100)
            else:
                raw_deals = []
            if not isinstance(raw_orders, list) or not isinstance(raw_deals, list):
                raise RuntimeError("Broker order/deal history did not return a list")
        except Exception as e:
            self.record_critical_incident(
                account_id,
                "RECONCILIATION_BROKER_HISTORY_READ_FAILED",
                f"Cannot verify broker snapshot/order/deal history during state reconciliation: {e}",
            )
            return False, None, "BROKER_HISTORY_READ_FAILED"

        eur_orders, eur_deals = self._extract_eurusd_broker_history(raw_orders, raw_deals)

        # 3. Query TradeMemoryService & a2_deal_ledger
        try:
            tm_records = TradeMemoryService.get_trade_history(
                account_id=str(account_id),
                track="LT_STRUCTURE_EURUSD_A2",
                execution_type="ACTUAL_DEMO",
                limit=100,
            )
            tm_conn = TradeMemoryService.get_connection()
            try:
                self._ensure_deal_ledger_table(tm_conn)
                ledger_rows = tm_conn.execute(
                    "SELECT deal_id, broker_ticket, order_id, leg_id FROM a2_deal_ledger WHERE account_id = ?",
                    (str(account_id),),
                ).fetchall()
            finally:
                tm_conn.close()
        except Exception as e:
            self.record_critical_incident(
                account_id,
                "RECONCILIATION_TRADEMEMORY_READ_FAILED",
                f"Cannot query TradeMemoryService or deal ledger during state reconciliation: {e}",
            )
            return False, None, "TRADEMEMORY_READ_FAILED"

        # Hydrate in-memory idempotency sets from durable storage (Remediation 4)
        for lr in ledger_rows:
            if lr["deal_id"]:
                self._reconciled_deal_ids.add(str(lr["deal_id"]))
            if lr["broker_ticket"]:
                self._reconciled_fill_tickets.add(str(lr["broker_ticket"]))
        if status == "OK" and doc:
            for d in doc.get("reconciled_deal_ids") or []:
                if d:
                    self._reconciled_deal_ids.add(str(d))

        tm_by_ticket = {}
        tm_order_ids = set()
        tm_deal_ids = set(self._reconciled_deal_ids)
        latest_tm_leg_id = None
        reconstructed_confirmed = {}
        breach_detected_in_tm = False

        for r in tm_records:
            tkt = str(r.get("broker_ticket") or "").strip()
            oid = str(r.get("order_id") or "").strip()
            did_str = str(r.get("deal_id") or "").strip()
            if tkt:
                self._reconciled_fill_tickets.add(tkt)
            if oid:
                tm_order_ids.add(oid)
            if did_str:
                for part in did_str.split(","):
                    if part.strip():
                        tm_deal_ids.add(part.strip())
                        self._reconciled_deal_ids.add(part.strip())

            sr = r.get("signal_reason_json")
            if isinstance(sr, str):
                try:
                    sr = json.loads(sr)
                except Exception:
                    sr = {}
            if isinstance(sr, dict):
                for d in sr.get("deal_ids") or []:
                    if d:
                        tm_deal_ids.add(str(d).strip())
                        self._reconciled_deal_ids.add(str(d).strip())
                if sr.get("post_fill_within_budget") is False:
                    breach_detected_in_tm = True

            leg_val = (sr or {}).get("leg_id") if isinstance(sr, dict) else None
            if tkt:
                tm_by_ticket[tkt] = {"leg_id": leg_val, "order_id": oid, "record": r}
            if leg_val and tkt and oid:
                if latest_tm_leg_id is None:
                    latest_tm_leg_id = str(leg_val)
                reconstructed_confirmed[str(leg_val)] = {
                    "broker_ticket": tkt,
                    "order_id": oid,
                    "deal_id": did_str,
                    "reconciled_from": "TradeMemoryService",
                }
            elif tkt and not leg_val:
                self.record_critical_incident(
                    account_id,
                    "INCOMPLETE_TRADEMEMORY_LEG_IDENTIFIER",
                    f"TradeMemory record for ticket {tkt} is missing structural leg_id; complete reconciliation impossible.",
                    {"broker_ticket": tkt},
                )
                return False, None, "INCOMPLETE_TRADEMEMORY_LEG_ID"

        # Remediation 5: If TradeMemory has any post-fill budget breach OR state doc has new_entries_disabled=True, restore lock!
        if breach_detected_in_tm:
            self.record_critical_incident(
                account_id,
                "RESTORED_POST_FILL_RISK_BREACH_LOCK",
                "TradeMemoryService contains a post-fill risk breach (post_fill_within_budget=False); keeping new entries disabled across restart.",
            )
            return False, latest_tm_leg_id, "HALTED_POST_FILL_BREACH_RESTORED"

        if status == "OK" and doc:
            if doc.get("new_entries_disabled") is True or doc.get("state") == "HALTED_POST_FILL_BREACH_OR_INCIDENT":
                self.post_fill_guard.new_entries_disabled = True
                return False, doc.get("last_confirmed_leg_id"), "HALTED_STATE_RESTORED"
            if doc.get("state") == "AMBIGUOUS_LOCKED":
                self.record_critical_incident(
                    account_id,
                    "AMBIGUOUS_STATE_LOCKED",
                    "Deduplication state is locked due to prior ambiguous broker response.",
                    doc.get("ambiguous_detail") or {},
                )
                return False, doc.get("last_confirmed_leg_id"), "AMBIGUOUS_LOCKED"

        # Check all open EURUSD positions AND broker EURUSD deal/order history for any untracked broker execution (Remediation 2)
        eurusd_open = [
            p for p in open_positions
            if isinstance(p, dict) and str(p.get("symbol") or p.get("instrument") or "").upper().rstrip("RM") == "EURUSD"
        ]
        untracked_broker_deals = [
            d for d in eur_deals
            if str(d.get("deal_id") or d.get("deal_ticket") or d.get("id") or "").strip() not in tm_deal_ids
            and str(d.get("position_id") or d.get("ticket") or "").strip() not in tm_by_ticket
        ]
        untracked_broker_orders = [
            o for o in eur_orders
            if str(o.get("order_id") or o.get("order") or o.get("id") or "").strip() not in tm_order_ids
            and str(o.get("position_id") or o.get("ticket") or "").strip() not in tm_by_ticket
            and str(o.get("order_type") or o.get("type") or "").lower() != "sltp"
            and str(o.get("state") or o.get("status") or "filled").lower() in ("filled", "confirmed", "executed", "placed", "partially_filled")
        ]

        if status == "MISSING":
            for pos in eurusd_open:
                ptkt = str(pos.get("position_id") or pos.get("ticket") or "").strip()
                if not ptkt or ptkt not in tm_by_ticket or not tm_by_ticket[ptkt].get("leg_id"):
                    self.record_critical_incident(
                        account_id,
                        "MISSING_STATE_UNRECONCILABLE_OPEN_POSITION",
                        f"State file missing and open EURUSD position #{ptkt} has no confirmed leg_id in TradeMemory.",
                        {"position": pos},
                    )
                    return False, None, "MISSING_STATE_UNRECONCILABLE_OPEN_POSITION"

            if untracked_broker_deals or untracked_broker_orders:
                self.record_critical_incident(
                    account_id,
                    "MISSING_STATE_UNRECONCILABLE_BROKER_HISTORY",
                    "State file missing and broker order/deal history contains EURUSD executions not recorded in TradeMemoryService.",
                    {"untracked_deals_count": len(untracked_broker_deals), "untracked_orders_count": len(untracked_broker_orders)},
                )
                return False, None, "MISSING_STATE_UNRECONCILABLE_BROKER_HISTORY"

            new_doc = self._default_leg_state_doc(account_id)
            new_doc["state"] = "CONFIRMED_FILLED" if latest_tm_leg_id else "AVAILABLE"
            new_doc["last_confirmed_leg_id"] = latest_tm_leg_id
            new_doc["confirmed_legs"] = reconstructed_confirmed
            new_doc["reconciled_deal_ids"] = sorted(tm_deal_ids)
            new_doc["history"].append({
                "event": "RECONCILED_MISSING_STATE",
                "last_confirmed_leg_id": latest_tm_leg_id,
                "reconciled_count": len(reconstructed_confirmed),
                "at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            })
            with open(lock_path, "a+") as lf:
                fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
                try:
                    ok_w = self._write_leg_state_doc_unlocked(account_id, new_doc)
                finally:
                    fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
            if not ok_w:
                self.record_critical_incident(account_id, "STATE_RECONSTRUCTION_WRITE_FAILED", "Failed to write reconstructed state.")
                return False, None, "STATE_RECONSTRUCTION_WRITE_FAILED"
            return True, latest_tm_leg_id, "RECONCILED_FROM_MISSING"

        # Status == "OK": Handle PENDING state on restart
        if doc.get("state") == "PENDING" or doc.get("pending_reservation") is not None:
            pend = doc.get("pending_reservation") or {}
            pend_leg = str(pend.get("leg_id") or "").strip()
            if not pend_leg:
                self.record_critical_incident(account_id, "CORRUPT_PENDING_RESERVATION", "Pending reservation has no leg_id.")
                return False, None, "CORRUPT_PENDING_RESERVATION"

            if pend_leg in reconstructed_confirmed:
                self.confirm_a2_leg_fill(account_id, pend_leg, reconstructed_confirmed[pend_leg])
                return True, pend_leg, "RECONCILED_PENDING_TO_CONFIRMED"

            for pos in eurusd_open:
                ptkt = str(pos.get("position_id") or pos.get("ticket") or "").strip()
                if ptkt not in tm_by_ticket:
                    self.record_critical_incident(
                        account_id,
                        "PENDING_RESERVATION_WITH_UNTRACKED_BROKER_POSITION",
                        f"Pending leg {pend_leg} found alongside untracked open EURUSD broker position #{ptkt}; manual recovery required.",
                        {"pending_leg": pend_leg, "untracked_position_ticket": ptkt},
                    )
                    return False, doc.get("last_confirmed_leg_id"), "PENDING_UNTRACKED_BROKER_POSITION"

            if untracked_broker_deals or untracked_broker_orders:
                self.record_critical_incident(
                    account_id,
                    "PENDING_RESERVATION_WITH_UNTRACKED_BROKER_HISTORY",
                    f"Pending leg {pend_leg} found alongside untracked EURUSD broker order/deal history (including closed positions); failing closed.",
                    {"pending_leg": pend_leg, "untracked_deals": len(untracked_broker_deals), "untracked_orders": len(untracked_broker_orders)},
                )
                return False, doc.get("last_confirmed_leg_id"), "PENDING_UNTRACKED_BROKER_HISTORY"

            if (pend.get("signal_meta") or {}).get("order_submitted"):
                self.record_critical_incident(
                    account_id,
                    "PENDING_SUBMITTED_ORDER_UNRECONCILABLE",
                    f"Pending leg {pend_leg} had order_submitted=True before restart; refusing automatic retry.",
                    {"pending_reservation": pend},
                )
                return False, doc.get("last_confirmed_leg_id"), "PENDING_SUBMITTED_ORDER_UNRECONCILABLE"

            self.release_a2_leg_reservation(account_id, pend_leg, "EXPIRED_PRE_SUBMISSION_ON_RESTART", pend.get("reservation_id"))
            return True, doc.get("last_confirmed_leg_id"), "RECONCILED_PENDING_EXPIRED"

        # Even if state == AVAILABLE/CONFIRMED_FILLED, any untracked EURUSD broker open position or deal history must fail closed
        for pos in eurusd_open:
            ptkt = str(pos.get("position_id") or pos.get("ticket") or "").strip()
            if ptkt not in tm_by_ticket:
                self.record_critical_incident(
                    account_id,
                    "UNTRACKED_OPEN_EURUSD_POSITION_DETECTED",
                    f"Open EURUSD broker position #{ptkt} is not tracked in TradeMemoryService; failing closed.",
                    {"position": pos},
                )
                return False, doc.get("last_confirmed_leg_id"), "UNTRACKED_OPEN_POSITION"

        if untracked_broker_deals:
            self.record_critical_incident(
                account_id,
                "UNTRACKED_EURUSD_BROKER_DEAL_HISTORY_DETECTED",
                "Broker deal history contains untracked EURUSD deals; failing closed.",
                {"untracked_deals_count": len(untracked_broker_deals)},
            )
            return False, doc.get("last_confirmed_leg_id"), "UNTRACKED_BROKER_DEAL_HISTORY"

        persisted_leg = doc.get("last_confirmed_leg_id")
        if latest_tm_leg_id and not persisted_leg:
            self.confirm_a2_leg_fill(account_id, latest_tm_leg_id, reconstructed_confirmed[latest_tm_leg_id])
            persisted_leg = latest_tm_leg_id

        return True, persisted_leg, "OK"

    @staticmethod
    def normalize_exness_order_response(
        raw_res: dict,
        expected_symbol: str = "EURUSD",
        expected_side: str | None = None,
        expected_account_id: str = ACCOUNT_ID,
        executable_quote: float | None = None,
    ) -> dict:
        """
        Remediation C-3 & Command 17 Fix 3: Explicit Response-Normalisation Layer for Exness Adapters.
        Supports ONLY the two documented adapter structures:
          1. ExnessTraderAPIClient.submit_order() -> {status, operation_id, ack, operation, payload, ...}
          2. ExnessMT5BrokerAdapter.place_market_order() -> {status, http_status, response}
        Never treats operation_id as broker_ticket or order_id.
        """
        from app.services.trade_memory_service import reconcile_partial_fills
        import math as _m

        if not isinstance(raw_res, dict) or not raw_res:
            return {
                "normalized_status": "MALFORMED_OR_CONTRADICTORY",
                "error_code": "NON_DICT_OR_EMPTY_RESPONSE",
                "detail": "Broker response is not a non-empty dictionary.",
            }

        if raw_res.get("dry_run") is True or str(raw_res.get("status") or "").upper() == "DRY_RUN_VERIFIED":
            return {
                "normalized_status": "MALFORMED_OR_CONTRADICTORY",
                "error_code": "DRY_RUN_NOT_LIVE_FILL",
                "detail": "Dry-run verification response cannot be processed as a live broker fill.",
            }

        has_terminal_keys = any(k in raw_res for k in ("operation", "ack", "operation_id", "payload"))
        has_mt5_keys = "http_status" in raw_res and "response" in raw_res

        if not has_terminal_keys and not has_mt5_keys:
            top_st = str(raw_res.get("status") or "").upper()
            if top_st in ("REJECTED", "FAILED", "ERROR", "CANCELLED"):
                return {
                    "normalized_status": "REJECTED",
                    "error_code": f"BROKER_{top_st}",
                    "detail": str(raw_res.get("error") or raw_res.get("detail") or top_st),
                }
            return {
                "normalized_status": "MALFORMED_OR_CONTRADICTORY",
                "error_code": "UNSUPPORTED_ADAPTER_SCHEMA",
                "detail": "Response does not match ExnessTraderAPIClient.submit_order() or ExnessMT5BrokerAdapter.place_market_order() schema.",
            }

        if has_terminal_keys and has_mt5_keys:
            return {
                "normalized_status": "MALFORMED_OR_CONTRADICTORY",
                "error_code": "CONTRADICTORY_ADAPTER_SCHEMAS",
                "detail": "Response mixes ExnessTerminal and ExnessMT5 fields.",
            }

        top_status = str(raw_res.get("status") or "").upper()
        adapter_schema = "EXNESS_TERMINAL_V1" if has_terminal_keys else "EXNESS_MT5_GATEWAY"

        if adapter_schema == "EXNESS_TERMINAL_V1":
            op_obj = raw_res.get("operation")
            ack_obj = raw_res.get("ack")
            payload_obj = raw_res.get("payload")
            op_id = str(raw_res.get("operation_id") or (ack_obj.get("operation_id") if isinstance(ack_obj, dict) else "") or "").strip() or None

            if top_status in ("REJECTED", "FAILED", "CANCELLED"):
                if isinstance(op_obj, dict) and str(op_obj.get("status") or "").lower() in ("confirmed", "filled", "executed"):
                    return {
                        "normalized_status": "MALFORMED_OR_CONTRADICTORY",
                        "error_code": "CONTRADICTORY_TOP_AND_OPERATION_STATUS",
                        "detail": f"Top status is {top_status} but operation.status is {op_obj.get('status')}.",
                        "operation_id": op_id,
                    }
                return {
                    "normalized_status": "REJECTED",
                    "adapter_schema": adapter_schema,
                    "operation_id": op_id,
                    "error_code": "EXNESS_TERMINAL_REJECTED",
                    "detail": str(raw_res.get("error") or (op_obj.get("error_message") if isinstance(op_obj, dict) else "") or top_status),
                }

            if not isinstance(op_obj, dict):
                return {
                    "normalized_status": "MALFORMED_OR_CONTRADICTORY",
                    "adapter_schema": adapter_schema,
                    "operation_id": op_id,
                    "error_code": "MISSING_OPERATION_DICT",
                    "detail": "ExnessTerminal response missing 'operation' dictionary.",
                }

            op_status = str(op_obj.get("status") or "").lower()
            if op_status in ("rejected", "failed", "cancelled", "expired"):
                if top_status == "FILLED":
                    return {
                        "normalized_status": "MALFORMED_OR_CONTRADICTORY",
                        "adapter_schema": adapter_schema,
                        "operation_id": op_id,
                        "error_code": "CONTRADICTORY_FILLED_AND_REJECTED",
                        "detail": f"Top status FILLED contradicts operation.status={op_status}.",
                    }
                return {
                    "normalized_status": "REJECTED",
                    "adapter_schema": adapter_schema,
                    "operation_id": op_id,
                    "error_code": f"OPERATION_{op_status.upper()}",
                    "detail": str(op_obj.get("error_message") or op_obj.get("reason") or op_status),
                }

            if op_status in ("accepted", "pending", "processing", "queued", "unknown") or top_status in ("ACCEPTED", "PENDING"):
                return {
                    "normalized_status": "ACCEPTED_NOT_FILLED" if op_status == "accepted" else "PENDING_OPERATION",
                    "adapter_schema": adapter_schema,
                    "operation_id": op_id,
                    "error_code": f"OPERATION_{op_status.upper() or 'PENDING'}",
                    "detail": "Operation accepted/pending at broker but fill is not yet confirmed.",
                }

            if top_status != "FILLED" or op_status not in ("confirmed", "filled", "executed"):
                return {
                    "normalized_status": "AMBIGUOUS",
                    "adapter_schema": adapter_schema,
                    "operation_id": op_id,
                    "error_code": "UNRECOGNIZED_TERMINAL_STATUS",
                    "detail": f"Unrecognized status combination top={top_status}, op={op_status}.",
                }

            src_dict = op_obj
            req_vol_raw = (payload_obj or {}).get("volume") if isinstance(payload_obj, dict) else src_dict.get("requested_volume")
            inst_raw = (
                src_dict.get("instrument")
                or src_dict.get("symbol")
                or ((payload_obj or {}).get("instrument") if isinstance(payload_obj, dict) else None)
            )
            side_raw = (
                src_dict.get("side")
                or src_dict.get("direction")
                or ((payload_obj or {}).get("side") if isinstance(payload_obj, dict) else None)
            )
            acct_raw = str(raw_res.get("account_id") or src_dict.get("account_id") or expected_account_id).strip()
            exec_type_raw = str(raw_res.get("execution_type") or src_dict.get("execution_type") or "ACTUAL_DEMO").upper()
            ts_raw = str(src_dict.get("updated_at") or src_dict.get("created_at") or "").strip()

        else:
            http_status = raw_res.get("http_status")
            resp_obj = raw_res.get("response")
            op_id = None

            if not isinstance(resp_obj, dict):
                return {
                    "normalized_status": "MALFORMED_OR_CONTRADICTORY",
                    "adapter_schema": adapter_schema,
                    "error_code": "MT5_RESPONSE_NOT_DICT",
                    "detail": "ExnessMT5BrokerAdapter 'response' field must be a dict.",
                }

            inner_st = str(resp_obj.get("status") or resp_obj.get("state") or "").upper()
            if top_status == "REJECTED" and (http_status == 200 and inner_st in ("FILLED", "CONFIRMED", "DONE")):
                return {
                    "normalized_status": "MALFORMED_OR_CONTRADICTORY",
                    "adapter_schema": adapter_schema,
                    "error_code": "MT5_CONTRADICTORY_REJECTED_STATUS",
                    "detail": "MT5 top status REJECTED contradicts inner FILLED status.",
                }
            if top_status == "FILLED" and (http_status != 200 or inner_st in ("REJECTED", "FAILED", "ERROR", "CANCELLED")):
                return {
                    "normalized_status": "MALFORMED_OR_CONTRADICTORY",
                    "adapter_schema": adapter_schema,
                    "error_code": "MT5_CONTRADICTORY_FILLED_STATUS",
                    "detail": f"MT5 top status FILLED contradicts http_status={http_status}, inner_status={inner_st}.",
                }
            if top_status in ("REJECTED", "FAILED") or (http_status is not None and int(http_status) >= 400 and inner_st in ("REJECTED", "FAILED", "")):
                return {
                    "normalized_status": "REJECTED",
                    "adapter_schema": adapter_schema,
                    "error_code": f"MT5_HTTP_{http_status}",
                    "detail": str(resp_obj.get("error") or resp_obj.get("detail") or "MT5 order rejected"),
                }
            if inner_st in ("ACCEPTED", "PENDING", "QUEUED", "PLACED"):
                return {
                    "normalized_status": "ACCEPTED_NOT_FILLED" if inner_st == "ACCEPTED" else "PENDING_OPERATION",
                    "adapter_schema": adapter_schema,
                    "error_code": f"MT5_{inner_st}",
                    "detail": f"MT5 order in non-filled state {inner_st}.",
                }
            if top_status != "FILLED" or int(http_status or 0) != 200:
                return {
                    "normalized_status": "AMBIGUOUS",
                    "adapter_schema": adapter_schema,
                    "error_code": "MT5_AMBIGUOUS_HTTP_OR_STATUS",
                    "detail": f"Ambiguous MT5 response status={top_status}, http_status={http_status}.",
                }

            src_dict = resp_obj
            req_vol_raw = src_dict.get("requested_volume") or src_dict.get("request_volume") or src_dict.get("volume")
            inst_raw = src_dict.get("symbol") or src_dict.get("instrument")
            side_raw = src_dict.get("side") or src_dict.get("order_type") or src_dict.get("type")
            acct_raw = str(src_dict.get("account_id") or raw_res.get("account_id") or expected_account_id).strip()
            exec_type_raw = str(src_dict.get("execution_type") or raw_res.get("execution_type") or "ACTUAL_DEMO").upper()
            ts_raw = str(src_dict.get("time_utc") or src_dict.get("filled_at") or src_dict.get("timestamp") or "").strip()

        if acct_raw != str(expected_account_id):
            return {
                "normalized_status": "MALFORMED_OR_CONTRADICTORY",
                "adapter_schema": adapter_schema,
                "operation_id": op_id,
                "error_code": "ACCOUNT_OWNERSHIP_MISMATCH",
                "detail": f"Response account_id '{acct_raw}' does not match expected '{expected_account_id}'.",
            }
        if exec_type_raw != "ACTUAL_DEMO":
            return {
                "normalized_status": "MALFORMED_OR_CONTRADICTORY",
                "adapter_schema": adapter_schema,
                "operation_id": op_id,
                "error_code": "INVALID_EXECUTION_TYPE",
                "detail": f"Invalid execution_type '{exec_type_raw}'; only ACTUAL_DEMO is permitted.",
            }

        norm_inst = str(inst_raw or "").strip().upper().replace("/", "").replace("_", "")
        if norm_inst.endswith(("M", "R", "C")) and norm_inst[:-1] == "EURUSD":
            norm_inst = "EURUSD"
        if norm_inst != str(expected_symbol).upper():
            return {
                "normalized_status": "MALFORMED_OR_CONTRADICTORY",
                "adapter_schema": adapter_schema,
                "operation_id": op_id,
                "error_code": "WRONG_INSTRUMENT",
                "detail": f"Response instrument '{inst_raw}' (normalized '{norm_inst}') != '{expected_symbol}'.",
            }

        norm_side = str(side_raw or "").strip().upper()
        if "BUY" in norm_side:
            norm_side = "BUY"
        elif "SELL" in norm_side:
            norm_side = "SELL"
        if norm_side not in ("BUY", "SELL") or (expected_side and norm_side != str(expected_side).upper()):
            return {
                "normalized_status": "MALFORMED_OR_CONTRADICTORY",
                "adapter_schema": adapter_schema,
                "operation_id": op_id,
                "error_code": "INVALID_OR_CONTRADICTORY_SIDE",
                "detail": f"Response side '{side_raw}' does not match expected '{expected_side}'.",
            }

        pos_id = str(src_dict.get("position_id") or src_dict.get("ticket") or "").strip()
        ord_id = str(src_dict.get("order_id") or src_dict.get("order") or "").strip()

        raw_deals = src_dict.get("deals") if isinstance(src_dict.get("deals"), list) else (
            src_dict.get("fills") if isinstance(src_dict.get("fills"), list) else []
        )

        if raw_deals:
            for d in raw_deals:
                if isinstance(d, dict):
                    if not pos_id and (d.get("position_id") or d.get("ticket")):
                        pos_id = str(d.get("position_id") or d.get("ticket")).strip()
                    if not ord_id and (d.get("order_id") or d.get("order")):
                        ord_id = str(d.get("order_id") or d.get("order")).strip()

        if not pos_id:
            return {
                "normalized_status": "AMBIGUOUS",
                "adapter_schema": adapter_schema,
                "operation_id": op_id,
                "error_code": "MISSING_BROKER_TICKET",
                "detail": "Confirmed fill response is missing genuine position_id / broker_ticket.",
            }
        if not ord_id:
            return {
                "normalized_status": "AMBIGUOUS",
                "adapter_schema": adapter_schema,
                "operation_id": op_id,
                "broker_ticket": pos_id,
                "error_code": "MISSING_GENUINE_ORDER_ID",
                "detail": "Confirmed fill response is missing genuine broker order_id (refusing to fabricate or copy broker_ticket/operation_id).",
            }
        if op_id and (pos_id == op_id or ord_id == op_id):
            return {
                "normalized_status": "MALFORMED_OR_CONTRADICTORY",
                "adapter_schema": adapter_schema,
                "operation_id": op_id,
                "error_code": "OPERATION_ID_MISUSED_AS_TICKET_OR_ORDER_ID",
                "detail": "operation_id cannot be used as broker_ticket or order_id.",
            }

        deal_ids = []
        normalized_deals = []
        if raw_deals:
            for idx, d in enumerate(raw_deals):
                if not isinstance(d, dict):
                    return {
                        "normalized_status": "AMBIGUOUS",
                        "adapter_schema": adapter_schema,
                        "broker_ticket": pos_id,
                        "order_id": ord_id,
                        "error_code": "MALFORMED_DEAL_RECORD",
                        "detail": f"Deal record at index {idx} is not a dict.",
                    }
                did = str(d.get("deal_id") or d.get("deal_ticket") or d.get("id") or "").strip()
                if not did:
                    return {
                        "normalized_status": "AMBIGUOUS",
                        "adapter_schema": adapter_schema,
                        "broker_ticket": pos_id,
                        "order_id": ord_id,
                        "error_code": "MISSING_DEAL_ID_IN_PARTIAL_FILLS",
                        "detail": f"Deal record at index {idx} is missing deal_id/deal_ticket.",
                    }
                d_pos = str(d.get("position_id") or d.get("ticket") or pos_id).strip()
                if d_pos != pos_id:
                    return {
                        "normalized_status": "MALFORMED_OR_CONTRADICTORY",
                        "adapter_schema": adapter_schema,
                        "broker_ticket": pos_id,
                        "order_id": ord_id,
                        "error_code": "CONTRADICTORY_DEAL_POSITION_ID",
                        "detail": f"Deal {did} position_id {d_pos} != aggregate position_id {pos_id}.",
                    }
                try:
                    d_px = float(d.get("price") or d.get("fill_price") or d.get("execution_price"))
                    d_vol = float(d.get("volume") or d.get("filled_volume"))
                except Exception:
                    return {
                        "normalized_status": "AMBIGUOUS",
                        "adapter_schema": adapter_schema,
                        "broker_ticket": pos_id,
                        "order_id": ord_id,
                        "error_code": "INVALID_DEAL_PRICE_OR_VOLUME",
                        "detail": f"Deal {did} has non-numeric price or volume.",
                    }
                if not (_m.isfinite(d_px) and d_px > 0 and _m.isfinite(d_vol) and d_vol > 0):
                    return {
                        "normalized_status": "AMBIGUOUS",
                        "adapter_schema": adapter_schema,
                        "broker_ticket": pos_id,
                        "order_id": ord_id,
                        "error_code": "NON_POSITIVE_DEAL_PRICE_OR_VOLUME",
                        "detail": f"Deal {did} has non-positive price={d_px} or volume={d_vol}.",
                    }
                normalized_deals.append({"deal_ticket": did, "price": d_px, "volume": d_vol, "position_id": pos_id, "order_id": ord_id})

            rec = reconcile_partial_fills(norm_side, executable_quote, normalized_deals, 0.00001)
            fill_px = rec.get("vwap_fill_price")
            fill_vol = rec.get("total_volume")
            deal_ids = [str(x) for x in (rec.get("deal_tickets") or []) if x]
            primary_deal_id = ",".join(deal_ids)
        else:
            raw_px = src_dict.get("fill_price") if src_dict.get("fill_price") is not None else (
                src_dict.get("execution_price") if src_dict.get("execution_price") is not None else (
                    src_dict.get("open_price") if src_dict.get("open_price") is not None else src_dict.get("price")
                )
            )
            raw_fvol = src_dict.get("filled_volume") if src_dict.get("filled_volume") is not None else (
                src_dict.get("executed_volume") if src_dict.get("executed_volume") is not None else src_dict.get("volume")
            )
            if raw_px is None or raw_fvol is None:
                return {
                    "normalized_status": "AMBIGUOUS",
                    "adapter_schema": adapter_schema,
                    "operation_id": op_id,
                    "broker_ticket": pos_id,
                    "order_id": ord_id,
                    "error_code": "MISSING_CONFIRMED_FILL_PRICE_OR_VOLUME",
                    "detail": "Confirmed fill response is missing fill_price or filled_volume.",
                }
            try:
                fill_px = float(raw_px)
                fill_vol = float(raw_fvol)
            except Exception:
                return {
                    "normalized_status": "AMBIGUOUS",
                    "adapter_schema": adapter_schema,
                    "operation_id": op_id,
                    "broker_ticket": pos_id,
                    "order_id": ord_id,
                    "error_code": "NON_NUMERIC_FILL_PRICE_OR_VOLUME",
                    "detail": "Confirmed fill price or volume is non-numeric.",
                }
            single_deal = str(src_dict.get("deal_id") or src_dict.get("deal") or "").strip()
            deal_ids = [single_deal] if single_deal else []
            primary_deal_id = single_deal

        if fill_px is None or not _m.isfinite(fill_px) or fill_px <= 0 or fill_vol is None or not _m.isfinite(fill_vol) or fill_vol <= 0:
            return {
                "normalized_status": "AMBIGUOUS",
                "adapter_schema": adapter_schema,
                "operation_id": op_id,
                "broker_ticket": pos_id,
                "order_id": ord_id,
                "error_code": "INVALID_CONFIRMED_FILL_PRICE_OR_VOLUME",
                "detail": f"Invalid fill_price={fill_px} or filled_volume={fill_vol}.",
            }

        try:
            req_vol = float(req_vol_raw) if req_vol_raw is not None else fill_vol
        except Exception:
            req_vol = fill_vol

        if fill_vol > req_vol + 1e-6:
            return {
                "normalized_status": "MALFORMED_OR_CONTRADICTORY",
                "adapter_schema": adapter_schema,
                "operation_id": op_id,
                "broker_ticket": pos_id,
                "order_id": ord_id,
                "error_code": "FILLED_VOLUME_EXCEEDS_REQUESTED_VOLUME",
                "detail": f"Filled volume {fill_vol} exceeds requested volume {req_vol}.",
            }

        is_partial = bool(fill_vol < req_vol - 1e-6)
        if not ts_raw:
            ts_raw = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        return {
            "normalized_status": "CONFIRMED_PARTIAL_FILL" if is_partial else "CONFIRMED_FULL_FILL",
            "adapter_schema": adapter_schema,
            "account_id": acct_raw,
            "execution_type": "ACTUAL_DEMO",
            "symbol": "EURUSD",
            "side": norm_side,
            "broker_ticket": pos_id,
            "position_id": pos_id,
            "order_id": ord_id,
            "deal_id": primary_deal_id,
            "deal_ids": deal_ids,
            "operation_id": op_id,
            "requested_volume": round(req_vol, 6),
            "filled_volume": round(fill_vol, 6),
            "is_partial_fill": is_partial,
            "fill_price": round(fill_px, 6),
            "filled_at_utc": ts_raw,
            "deals": normalized_deals,
        }

    def process_broker_fill_response(
        self,
        order_res: dict,
        sig: dict,
        sl: float,
        tp: float,
        now_iso: str,
        account_id: str = ACCOUNT_ID,
        reservation_id: str | None = None,
    ) -> dict:
        """
        Command 17 Remediated Post-Fill Processor:
        - Normalises Exness responses via normalize_exness_order_response().
        - Enforces cross-process and cross-restart idempotency across broker_ticket, order_id, and individual deal_ids
          using both a2_deal_ledger (PRIMARY KEY (account_id, deal_id)), signal_reason_json.deal_ids, and state file reconciled_deal_ids.
        - Persists post-fill risk breaches and post-fill exceptions durably on disk so a restart never re-enables new entries.
        """
        self.ensure_post_fill_guard()
        leg_id = sig.get("leg_id") if isinstance(sig, dict) else None
        exp_side = sig.get("side") if isinstance(sig, dict) else None
        exec_quote = sig.get("entry_price") if isinstance(sig, dict) else None

        try:
            norm = self.normalize_exness_order_response(
                order_res,
                expected_symbol=str((sig or {}).get("symbol") or "EURUSD"),
                expected_side=exp_side,
                expected_account_id=str(account_id),
                executable_quote=exec_quote,
            )
        except Exception as norm_exc:
            if leg_id:
                self.mark_a2_leg_ambiguous(account_id, leg_id, f"Normalisation exception: {norm_exc}", {"raw": str(order_res)})
            inc = self.record_critical_incident(
                account_id,
                "CRITICAL_RESPONSE_NORMALISATION_EXCEPTION",
                f"Exception normalising broker response: {norm_exc}",
                {"leg_id": leg_id, "raw_response": order_res if isinstance(order_res, dict) else str(order_res)},
            )
            return {
                "status": "CRITICAL_RESPONSE_NORMALISATION_EXCEPTION",
                "recorded": False,
                "new_entries_disabled": True,
                "incident": inc,
            }

        nst = norm.get("normalized_status")

        if nst == "REJECTED":
            if leg_id:
                self.release_a2_leg_reservation(account_id, leg_id, f"ORDER_REJECTED:{norm.get('error_code')}", reservation_id)
            return {
                "status": "ORDER_REJECTED",
                "error_code": norm.get("error_code"),
                "detail": norm.get("detail"),
                "recorded": False,
                "new_entries_disabled": self.post_fill_guard.new_entries_disabled,
            }

        if nst not in ("CONFIRMED_FULL_FILL", "CONFIRMED_PARTIAL_FILL"):
            if leg_id:
                self.mark_a2_leg_ambiguous(account_id, leg_id, f"{nst}:{norm.get('error_code')}", norm)
            inc = self.record_critical_incident(
                account_id,
                f"CRITICAL_{nst}_{norm.get('error_code')}",
                norm.get("detail") or f"Non-confirmed broker response state: {nst}",
                {
                    "leg_id": leg_id,
                    "normalized": norm,
                },
            )
            return {
                "status": f"CRITICAL_{nst}",
                "error_code": norm.get("error_code"),
                "broker_ticket": norm.get("broker_ticket"),
                "order_id": norm.get("order_id"),
                "operation_id": norm.get("operation_id"),
                "recorded": False,
                "new_entries_disabled": True,
                "incident": inc,
            }

        tkt = norm["broker_ticket"]
        ord_id = norm["order_id"]
        deal_id = norm["deal_id"]
        deal_ids = [str(d).strip() for d in (norm.get("deal_ids") or []) if str(d).strip()]
        fill_px = norm["fill_price"]
        fill_vol = norm["filled_volume"]
        req_vol = norm["requested_volume"]
        is_partial = norm["is_partial_fill"]

        # Remediation 4: Cross-process & cross-restart idempotency check (in-memory, state file, SQLite trade_memory, and SQLite a2_deal_ledger)
        if tkt in self._reconciled_fill_tickets or any(d in self._reconciled_deal_ids for d in deal_ids):
            return {
                "status": "DUPLICATE_FILL_IGNORED",
                "ticket": tkt,
                "order_id": ord_id,
                "deal_id": deal_id,
                "recorded": False,
                "new_entries_disabled": self.post_fill_guard.new_entries_disabled,
            }

        try:
            st_doc_ok, st_doc = self._read_leg_state_doc_unlocked(account_id)
            if st_doc_ok == "OK" and st_doc:
                persisted_deals = set(str(x) for x in (st_doc.get("reconciled_deal_ids") or []))
                if any(d in persisted_deals for d in deal_ids):
                    self._reconciled_fill_tickets.add(tkt)
                    self._reconciled_deal_ids.update(deal_ids)
                    return {
                        "status": "DUPLICATE_FILL_IGNORED",
                        "ticket": tkt,
                        "order_id": ord_id,
                        "deal_id": deal_id,
                        "recorded": False,
                        "new_entries_disabled": self.post_fill_guard.new_entries_disabled,
                    }
        except Exception:
            pass

        try:
            TradeMemoryService.init_db()
            tm_conn = TradeMemoryService.get_connection()
            try:
                self._ensure_deal_ledger_table(tm_conn)
                existing_row = tm_conn.execute(
                    "SELECT trade_id, deal_id, signal_reason_json FROM trade_memory WHERE account_id = ? AND (broker_ticket = ? OR order_id = ?)",
                    (str(account_id), str(tkt), str(ord_id)),
                ).fetchone()
                dup_deal_found = False
                if not existing_row and deal_ids:
                    placeholders = ",".join("?" for _ in deal_ids)
                    dl_row = tm_conn.execute(
                        f"SELECT deal_id FROM a2_deal_ledger WHERE account_id = ? AND deal_id IN ({placeholders}) LIMIT 1",
                        (str(account_id), *deal_ids),
                    ).fetchone()
                    if dl_row:
                        dup_deal_found = True
                    else:
                        # Also scan trade_memory rows for comma-separated deal_id or signal_reason_json.deal_ids
                        all_acct_rows = tm_conn.execute(
                            "SELECT deal_id, signal_reason_json FROM trade_memory WHERE account_id = ?",
                            (str(account_id),),
                        ).fetchall()
                        for ar in all_acct_rows:
                            existing_dids = {p.strip() for p in str(ar["deal_id"] or "").split(",") if p.strip()}
                            try:
                                sr_obj = json.loads(ar["signal_reason_json"] or "{}")
                                if isinstance(sr_obj, dict):
                                    for sd in sr_obj.get("deal_ids") or []:
                                        if str(sd).strip():
                                            existing_dids.add(str(sd).strip())
                            except Exception:
                                pass
                            if any(d in existing_dids for d in deal_ids):
                                dup_deal_found = True
                                break
            finally:
                tm_conn.close()

            if existing_row or dup_deal_found:
                self._reconciled_fill_tickets.add(tkt)
                self._reconciled_deal_ids.update(deal_ids)
                return {
                    "status": "DUPLICATE_FILL_IGNORED",
                    "ticket": tkt,
                    "order_id": ord_id,
                    "deal_id": deal_id,
                    "recorded": False,
                    "new_entries_disabled": self.post_fill_guard.new_entries_disabled,
                }
        except Exception as db_chk_err:
            logger.error(f"TradeMemory duplicate check warning: {db_chk_err}")

        self._reconciled_fill_tickets.add(tkt)
        self._reconciled_deal_ids.update(deal_ids)

        actual_risk_usd = round(abs(fill_px - float(sl)) * fill_vol * 100000.0, 4)

        fill_recovery_context = {
            "account_id": str(account_id),
            "leg_id": leg_id,
            "broker_ticket": tkt,
            "position_id": tkt,
            "order_id": ord_id,
            "deal_id": deal_id,
            "deal_ids": deal_ids,
            "operation_id": norm.get("operation_id"),
            "symbol": "EURUSD",
            "side": norm["side"],
            "requested_volume": req_vol,
            "filled_volume": fill_vol,
            "is_partial_fill": is_partial,
            "fill_price": fill_px,
            "sl_price": float(sl),
            "tp_price": float(tp),
            "actual_risk_usd": actual_risk_usd,
            "filled_at_utc": norm["filled_at_utc"],
        }

        # Step 3a: PostFillRiskBreachGuard evaluation (Remediation 5: durable incident + durable state halt on breach or exception)
        guard_error = None
        within_budget = False
        try:
            within_budget = bool(self.post_fill_guard.evaluate_fill(tkt, "EURUSD", actual_risk_usd))
            if not within_budget:
                self.record_critical_incident(
                    account_id,
                    "POST_FILL_RISK_BREACH_NEW_ENTRIES_DISABLED",
                    f"Confirmed fill #{tkt} actual risk ${actual_risk_usd:.4f} exceeded max budget ${self.post_fill_guard.max_risk_usd:.2f}.",
                    fill_recovery_context,
                )
        except Exception as g_exc:
            guard_error = str(g_exc)
            self.record_critical_incident(
                account_id,
                "POST_FILL_GUARD_EXCEPTION",
                f"PostFillRiskBreachGuard raised exception on confirmed fill #{tkt}: {g_exc}",
                fill_recovery_context,
            )

        # Step 3b: Durable leg state confirmation (preserves new_entries_disabled=True if breach or guard error occurred)
        state_saved = False
        state_error = None
        halt_flag = (not within_budget) or (guard_error is not None)
        if leg_id:
            try:
                state_saved = bool(
                    self.confirm_a2_leg_fill(
                        account_id,
                        leg_id,
                        fill_recovery_context,
                        disable_new_entries=halt_flag,
                        halt_reason="POST_FILL_RISK_BREACH_OR_GUARD_ERROR" if halt_flag else None,
                    )
                )
                if not state_saved:
                    state_error = "confirm_a2_leg_fill returned False"
            except Exception as st_exc:
                state_saved = False
                state_error = str(st_exc)
            if not state_saved:
                self.record_critical_incident(
                    account_id,
                    "POST_FILL_STATE_PERSISTENCE_FAILURE",
                    f"Failed to persist CONFIRMED_FILLED leg state for #{tkt} ({leg_id}): {state_error}",
                    fill_recovery_context,
                )
        else:
            state_saved = True

        # Step 3c: TradeMemoryService.record_trade() + independent deal rows in a2_deal_ledger (Remediation 4)
        tm_recorded = False
        tm_error = None
        try:
            TradeMemoryService.record_trade({
                "trade_id": f"OPDEMO-{tkt}",
                "broker_ticket": tkt,
                "order_id": ord_id,
                "deal_id": deal_id,
                "account_id": str(account_id),
                "strategy_track": sig["strategy"],
                "strategy_version": sig["strategy_version"],
                "symbol": "EURUSD",
                "side": norm["side"],
                "volume_lots": fill_vol,
                "executable_quote": exec_quote,
                "entry_price": fill_px,
                "tick_size": 0.00001,
                "sl_price": float(sl),
                "tp_price": float(tp),
                "planned_risk_usd": actual_risk_usd,
                "entry_time": norm["filled_at_utc"] or now_iso,
                "execution_type": "ACTUAL_DEMO",
                "status": "PARTIAL_OPEN" if is_partial else "OPEN",
                "market_session": "LONDON_NY_SESSION",
                "signal_reason_json": json.dumps({
                    "reason": sig.get("reason", ""),
                    "leg_id": leg_id,
                    "position_id": tkt,
                    "order_id": ord_id,
                    "deal_ids": deal_ids,
                    "operation_id": norm.get("operation_id"),
                    "requested_volume": req_vol,
                    "filled_volume": fill_vol,
                    "is_partial_fill": is_partial,
                    "post_fill_within_budget": within_budget,
                }),
            })
            # Persist individual deal IDs in a2_deal_ledger
            if deal_ids or norm.get("deals"):
                dl_conn = TradeMemoryService.get_connection()
                try:
                    with dl_conn:
                        self._ensure_deal_ledger_table(dl_conn)
                        if norm.get("deals"):
                            for d_item in norm["deals"]:
                                dl_conn.execute(
                                    """
                                    INSERT OR REPLACE INTO a2_deal_ledger
                                    (account_id, deal_id, broker_ticket, order_id, leg_id, symbol, side, volume_lots, fill_price, recorded_at_utc)
                                    VALUES (?, ?, ?, ?, ?, 'EURUSD', ?, ?, ?, ?)
                                    """,
                                    (
                                        str(account_id),
                                        str(d_item["deal_ticket"]),
                                        str(tkt),
                                        str(ord_id),
                                        str(leg_id or ""),
                                        str(norm["side"]),
                                        float(d_item["volume"]),
                                        float(d_item["price"]),
                                        str(norm["filled_at_utc"] or now_iso),
                                    ),
                                )
                        else:
                            for did_single in deal_ids:
                                dl_conn.execute(
                                    """
                                    INSERT OR REPLACE INTO a2_deal_ledger
                                    (account_id, deal_id, broker_ticket, order_id, leg_id, symbol, side, volume_lots, fill_price, recorded_at_utc)
                                    VALUES (?, ?, ?, ?, ?, 'EURUSD', ?, ?, ?, ?)
                                    """,
                                    (
                                        str(account_id),
                                        str(did_single),
                                        str(tkt),
                                        str(ord_id),
                                        str(leg_id or ""),
                                        str(norm["side"]),
                                        float(fill_vol),
                                        float(fill_px),
                                        str(norm["filled_at_utc"] or now_iso),
                                    ),
                                )
                finally:
                    dl_conn.close()
            tm_recorded = True
        except Exception as tm_exc:
            tm_error = str(tm_exc)
            self.record_critical_incident(
                account_id,
                "POST_FILL_TRADEMEMORY_RECORD_FAILURE",
                f"TradeMemoryService.record_trade failed after confirmed broker fill #{tkt}: {tm_exc}",
                fill_recovery_context,
            )

        if guard_error or state_error or tm_error:
            self.post_fill_guard.new_entries_disabled = True
            status_code = "CRITICAL_POST_FILL_PROTECTION_OR_PERSISTENCE_FAILURE"
        elif not within_budget:
            self.post_fill_guard.new_entries_disabled = True
            status_code = "POST_FILL_RISK_BREACH_NEW_ENTRIES_DISABLED"
        elif is_partial:
            status_code = "CONFIRMED_PARTIAL_FILL_AND_PROTECTED"
        else:
            status_code = "CONFIRMED_AND_PROTECTED"

        return {
            "status": status_code,
            "fill_recognized": True,
            "ticket": tkt,
            "position_id": tkt,
            "order_id": ord_id,
            "deal_id": deal_id,
            "deal_ids": deal_ids,
            "operation_id": norm.get("operation_id"),
            "requested_volume": req_vol,
            "fill_volume": fill_vol,
            "is_partial_fill": is_partial,
            "fill_price": fill_px,
            "actual_risk_usd": actual_risk_usd,
            "recorded": tm_recorded,
            "leg_state_saved": state_saved,
            "within_budget": within_budget,
            "new_entries_disabled": self.post_fill_guard.new_entries_disabled,
            "errors": {
                "guard_error": guard_error,
                "state_error": state_error,
                "trade_memory_error": tm_error,
            },
        }

    async def scan_market_opportunities(self, conn, adapter, now_utc: datetime | None = None, account_id: str = ACCOUNT_ID):
        """
        Command 17 Remediated Wiring:
        1. Restores durable safety locks and reconciles persistent leg deduplication state against read-only broker snapshot,
           order history, deal history, and TradeMemory before evaluation.
        2. Filters D1/H4/H1 closed candles strictly in UTC.
        3. Evaluates frozen EurUsdStructureA2(d1_df, h4_df, er_thr=0.20).
        4. Atomically reserves a qualifying leg as PENDING; releases reservation (without consuming the leg) if
           quote retrieval, spread check, or risk lot sizing fails.
        """
        import sys as _sys
        import pandas as _pd
        if "/opt/bitdex-research-v2" not in _sys.path:
            _sys.path.insert(0, "/opt/bitdex-research-v2")
        from strategies.eurusd_structure_a2 import EurUsdStructureA2
        from backtesting.execution_simulator import ExecutionCostConfig, compute_risk_lots

        self.ensure_post_fill_guard()
        state_ok, persisted_leg, rec_status = await self.reconcile_or_initialize_a2_leg_state(adapter, account_id)
        if not state_ok or self.post_fill_guard.new_entries_disabled:
            logger.error(f"[LT_STRUCTURE_EURUSD_A2] NO_TRADE: Deduplication/safety state check blocked entries ({rec_status}); failing closed.")
            return []

        eval_now = now_utc or datetime.now(timezone.utc)
        reserved_leg = None
        reservation_id = None
        try:
            d1_raw = await adapter.get_historical_candles("EURUSD", timeframe="D1", count=130)
            h4_raw = await adapter.get_historical_candles("EURUSD", timeframe="H4", count=130)
            h1_raw = await adapter.get_historical_candles("EURUSD", timeframe="H1", count=530)

            d1_closed = self.filter_closed_candles(d1_raw, 86400, eval_now, is_d1=True)
            h4_closed = self.filter_closed_candles(h4_raw, 14400, eval_now, is_d1=False)
            h1_closed = self.filter_closed_candles(h1_raw, 3600, eval_now, is_d1=False)

            if len(d1_closed) < 65 or len(h4_closed) < 40 or len(h1_closed) < 260:
                logger.info("[LT_STRUCTURE_EURUSD_A2] NO_TRADE: Insufficient closed candle history after UTC close-time filter.")
                return []

            d1_df = _pd.DataFrame(d1_closed)
            h4_df = _pd.DataFrame(h4_closed)
            a2 = EurUsdStructureA2(d1_df, h4_df, er_thr=0.20)
            a2.last_leg_id = persisted_leg
            sig = a2.generate_signal(h1_closed, len(h1_closed) - 1)
            if not sig or sig.get("direction") not in ("BUY", "SELL"):
                return []

            candidate_leg = a2.last_leg_id
            ok_res, res_token = self.reserve_a2_leg_pending(
                account_id,
                candidate_leg,
                {"direction": sig["direction"], "sl": float(sig["sl"]), "tp": float(sig["tp"]), "order_submitted": False},
            )
            if not ok_res:
                logger.info(f"[LT_STRUCTURE_EURUSD_A2] NO_TRADE: Could not reserve leg {candidate_leg} ({res_token}).")
                return []
            reserved_leg = candidate_leg
            reservation_id = res_token

            try:
                q = await adapter.get_live_quote("EURUSD")
            except Exception as q_err:
                self.release_a2_leg_reservation(account_id, reserved_leg, f"QUOTE_FAILURE:{q_err}", reservation_id)
                return []

            if not isinstance(q, dict) or q.get("bid") is None or q.get("ask") is None:
                self.release_a2_leg_reservation(account_id, reserved_leg, "INVALID_QUOTE_PAYLOAD", reservation_id)
                return []

            bid_px = float(q["bid"])
            ask_px = float(q["ask"])
            if bid_px <= 0 or ask_px <= 0 or ask_px < bid_px:
                self.release_a2_leg_reservation(account_id, reserved_leg, "NON_POSITIVE_OR_INVERTED_QUOTE", reservation_id)
                return []

            live_spread = round(ask_px - bid_px, 6)
            max_spread = float(q.get("max_spread_price") or 0.00025)
            if live_spread > max_spread:
                self.release_a2_leg_reservation(account_id, reserved_leg, f"SPREAD_REJECTED:{live_spread}>{max_spread}", reservation_id)
                return []

            side = sig["direction"]
            entry_px = ask_px if side == "BUY" else bid_px
            sl_px = round(float(sig["sl"]), 5)
            tp_px = round(float(sig["tp"]), 5)
            lots, _ = compute_risk_lots(entry_px, sl_px, 10.0, ExecutionCostConfig())
            if lots is None or lots <= 0:
                self.release_a2_leg_reservation(account_id, reserved_leg, "SIZING_REJECTED", reservation_id)
                return []

            return [{
                "strategy": "LT_STRUCTURE_EURUSD_A2",
                "engine_type": "LONG_TERM",
                "strategy_version": "2.0",
                "symbol": "EURUSD",
                "side": side,
                "volume": lots,
                "entry_price": entry_px,
                "sl_price": sl_px,
                "tp_price": tp_px,
                "leg_id": reserved_leg,
                "reservation_id": reservation_id,
                "reason": "Frozen LT_STRUCTURE_EURUSD_A2 v2.0 closed-candle signal",
            }]
        except Exception as e:
            if reserved_leg:
                self.release_a2_leg_reservation(account_id, reserved_leg, f"SCAN_EXCEPTION:{e}", reservation_id)
            logger.error(f"[LT_STRUCTURE_EURUSD_A2] Scan error: {e}")
            return []

    async def execute_signal_Cycle(self, conn, adapter, sig: dict, now_iso: str, account_id: str = ACCOUNT_ID) -> dict:
        """
        Command 17 Remediated Signal Execution Cycle:
        1. Runs SharedCentralRiskManager.preflight_check(). If rejected -> releases PENDING reservation without consuming leg.
        2. Atomically persists order_submitted = True on disk BEFORE invoking adapter.place_market_order() (Remediation 1).
        3. Submits order via adapter.place_market_order().
        4. Reconciles Exness Terminal operation response against read-only broker snapshot/order/deal records (Remediation 3).
        5. Processes confirmed fill via process_broker_fill_response().
        """
        self.ensure_post_fill_guard()
        leg_id = sig.get("leg_id")
        res_id = sig.get("reservation_id")

        if self.post_fill_guard.new_entries_disabled:
            if leg_id:
                self.release_a2_leg_reservation(account_id, leg_id, "NEW_ENTRIES_DISABLED_PRE_PREFLIGHT", res_id)
            return {"status": "BLOCKED_NEW_ENTRIES_DISABLED", "recorded": False}

        try:
            passed, reason, p_ctx = await SharedCentralRiskManager.preflight_check(
                conn=conn, adapter=adapter, account_id=account_id,
                symbol=sig["symbol"], side=sig["side"], volume=sig["volume"],
                entry_price=sig["entry_price"], sl_price=sig["sl_price"],
                engine_type=sig["engine_type"],
                real_trading_permanently_locked=REAL_TRADING_PERMANENTLY_LOCKED
            )
        except Exception as pf_exc:
            if leg_id:
                self.release_a2_leg_reservation(account_id, leg_id, f"PREFLIGHT_EXCEPTION:{pf_exc}", res_id)
            return {"status": "PREFLIGHT_EXCEPTION", "detail": str(pf_exc), "recorded": False}

        if not passed:
            if leg_id:
                self.release_a2_leg_reservation(account_id, leg_id, f"PREFLIGHT_REJECTED:{reason}", res_id)
            return {"status": "PREFLIGHT_REJECTED", "reason": reason, "recorded": False}

        # Remediation 1: Atomically mark order_submitted = True BEFORE invoking place_market_order
        idem_key = f"a2-ord-{account_id}-{int(time.time() * 1000)}"
        if leg_id:
            if not self.mark_a2_leg_order_submitting(account_id, leg_id, reservation_id=res_id, idempotency_key=idem_key):
                inc = self.record_critical_incident(
                    account_id,
                    "PRE_SUBMISSION_STATE_PERSIST_FAILED",
                    f"Failed to persist order_submitted=True before order placement for leg {leg_id}; aborting order.",
                    {"leg_id": leg_id, "reservation_id": res_id},
                )
                return {"status": "PRE_SUBMISSION_STATE_PERSIST_FAILED", "recorded": False, "new_entries_disabled": True, "incident": inc}

        try:
            order_res = await adapter.place_market_order(
                symbol=sig["symbol"], side=sig["side"], volume=sig["volume"],
                sl=sig["sl_price"], tp=sig["tp_price"], dry_run=False,
                comment=f"OPEXP_{sig['engine_type'][:4]}"
            )
        except Exception as ord_exc:
            if leg_id:
                self.mark_a2_leg_ambiguous(account_id, leg_id, f"ORDER_SUBMISSION_EXCEPTION:{ord_exc}")
            inc = self.record_critical_incident(
                account_id,
                "CRITICAL_ORDER_SUBMISSION_EXCEPTION",
                f"Exception during place_market_order for leg {leg_id}; refusing retry and disabling new entries: {ord_exc}",
                {"leg_id": leg_id, "signal": sig, "idempotency_key": idem_key},
            )
            return {"status": "CRITICAL_ORDER_SUBMISSION_EXCEPTION", "recorded": False, "new_entries_disabled": True, "incident": inc}

        # Remediation 3: Reconcile Exness Terminal operation response against read-only broker snapshot/order/deal records
        reconciled_res = await self.reconcile_exness_terminal_operation(adapter, order_res, sig, account_id=account_id)

        fill_outcome = self.process_broker_fill_response(
            reconciled_res, sig, sig["sl_price"], sig["tp_price"], now_iso, account_id, reservation_id=res_id
        )
        if fill_outcome.get("fill_recognized"):
            self.trades_opened_count += 1
        return fill_outcome

    async def run(self):
        ok, lock_expiry = check_persistent_experiment_lock()
        if not ok:
            logger.error("Exiting immediately due to persistent experiment lock / expiry.")
            return
        self.expiry_time = lock_expiry
        self.ensure_post_fill_guard()
        conn = get_db_connection()
        adapter, ctx, ud = CentralExecutionRouter.resolve_adapter_for_customer(conn, 'USR-ADM-B022F490', ACCOUNT_ID)
        adapter.unlock_demo_execution_for_test(ACCOUNT_ID)
        await self.verify_environment(adapter)
        self.state = "RUNNING_ACTIVE_MONITORING"

        while True:
            ok, lock_expiry = check_persistent_experiment_lock()
            if not ok or self.post_fill_guard.new_entries_disabled:
                logger.error("Stopping loop: lock revoked/expired or post-fill risk breach guard triggered.")
                break
            self.expiry_time = lock_expiry
            self.iteration += 1
            now_iso = datetime.now(timezone.utc).isoformat()
            try:
                positions = await adapter.get_open_positions()
                signals = await self.scan_market_opportunities(conn, adapter)
                for sig in signals:
                    if self.post_fill_guard.new_entries_disabled:
                        if sig.get("leg_id"):
                            self.release_a2_leg_reservation(ACCOUNT_ID, sig["leg_id"], "NEW_ENTRIES_DISABLED", sig.get("reservation_id"))
                        break
                    await self.execute_signal_Cycle(conn, adapter, sig, now_iso, ACCOUNT_ID)
            except Exception as loop_err:
                logger.error(f"Error in experiment cycle: {loop_err}", exc_info=True)
            await asyncio.sleep(60)
        conn.close()

if __name__ == "__main__":
    supervisor = OperatorExperimentSupervisor()
    asyncio.run(supervisor.run())
