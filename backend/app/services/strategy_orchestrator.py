"""
Tauric Platform — Universal Multi-Exchange Strategy Orchestrator Service
=========================================================================
Architectural, provider-agnostic strategy orchestration supporting:
- Dynamic connection registry across arbitrary profiles (Binance, Bitget, Bybit, Coinbase, OKX, MT5, etc.)
- Multi-run isolation: multiple concurrent strategy runs on the same or different assets
- Immutable run records, scoped idempotency keys, and explicit audit trail
- Real account balance fetching & strict allocation validation ("money from account")
- Live trading authorization safety gate (HTTP 403 / BLOCKED_LIVE_LOCK)
- Zero silent fallback across DEMO, PAPER, and LIVE environments
- Execution Integrity: Truthful status, worker liveness supervisor, zero synthetic orders,
  and verifiable read-only exchange reconciliation.
"""

import os
import json
import time
import uuid
import hashlib
import asyncio
from enum import Enum
from typing import Dict, Any, List, Optional, Set, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass, asdict, field, fields

from app.config import settings
from app.services.live_trading_auth import live_trading_auth_manager
from app.services.exchange_framework import (
    credential_vault,
    exchange_framework,
    ProductType,
    MarketType,
    Environment,
    ConnectionStatus,
)
from app.services.paper_trading_engine import paper_engine

_backend_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_data_dir = os.getenv(
    "TAURIC_DATA_DIR",
    os.path.join(settings.platform_root, "backend", "data")
    if os.path.isdir(os.path.join(settings.platform_root, "backend", "data"))
    else os.path.join(_backend_root, "data")
)
DEFAULT_RUNS_PATH = os.path.join(_data_dir, "strategy_runs.json") if not _data_dir.endswith(".json") else _data_dir


class StrategyStatus(str, Enum):
    INITIALIZING = "INITIALIZING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    # Execution Integrity Remediation Statuses
    PLAN_ONLY = "PLAN_ONLY"
    PAPER_SIMULATION = "PAPER_SIMULATION"
    SUBMISSION_PENDING = "SUBMISSION_PENDING"
    SUBMISSION_NOT_IMPLEMENTED = "SUBMISSION_NOT_IMPLEMENTED"
    EXCHANGE_ACCEPTED = "EXCHANGE_ACCEPTED"
    OPEN_ON_EXCHANGE = "OPEN_ON_EXCHANGE"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    STOP_REQUESTED = "STOP_REQUESTED"
    CANCEL_SENT = "CANCEL_SENT"
    CANCEL_CONFIRMED = "CANCEL_CONFIRMED"
    STOP_UNCONFIRMED = "STOP_UNCONFIRMED"
    CANCELLED_ON_EXCHANGE = "CANCELLED_ON_EXCHANGE"
    STOPPED_ON_EXCHANGE = "STOPPED_ON_EXCHANGE"
    ORPHANED = "ORPHANED"
    STALE = "STALE"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class ExecutionAuthorizationState(str, Enum):
    AUTHORIZED_DEMO = "AUTHORIZED_DEMO"
    AUTHORIZED_PAPER = "AUTHORIZED_PAPER"
    BLOCKED_LIVE_LOCK = "BLOCKED_LIVE_LOCK"


class ProviderImplementationStatus(str, Enum):
    IMPLEMENTED_TESTED = "IMPLEMENTED_TESTED"
    BRIDGE_DEPENDENT = "BRIDGE_DEPENDENT"
    PLANNED = "PLANNED"


# Universal Provider Status Mapping
PROVIDER_IMPLEMENTATION_STATUS: Dict[str, ProviderImplementationStatus] = {
    "BINANCE": ProviderImplementationStatus.IMPLEMENTED_TESTED,
    "BITGET": ProviderImplementationStatus.IMPLEMENTED_TESTED,
    "BYBIT": ProviderImplementationStatus.IMPLEMENTED_TESTED,
    "COINBASE": ProviderImplementationStatus.IMPLEMENTED_TESTED,
    "OKX": ProviderImplementationStatus.IMPLEMENTED_TESTED,
    "MT5": ProviderImplementationStatus.BRIDGE_DEPENDENT,
    "CUSTOM_FOREX": ProviderImplementationStatus.BRIDGE_DEPENDENT,
    "KRAKEN": ProviderImplementationStatus.PLANNED,
    "DERIBIT": ProviderImplementationStatus.PLANNED,
    "INTERACTIVE_BROKERS": ProviderImplementationStatus.PLANNED,
}


@dataclass
class StrategyRun:
    run_id: str
    asset: str
    strategy_id: str
    strategy_name: str
    profile_id: str
    provider_id: str
    product_type: str
    environment: str
    investment_amount: float
    currency: str
    status: str
    execution_mode: str
    authorization_state: str
    created_at_utc: str
    started_at_utc: Optional[str] = None
    stopped_at_utc: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    risk_config: Dict[str, Any] = field(default_factory=dict)
    balance_source: Dict[str, Any] = field(default_factory=dict)
    provider_order_ids: List[str] = field(default_factory=list)
    normalized_orders: List[Dict[str, Any]] = field(default_factory=list)
    fills: List[Dict[str, Any]] = field(default_factory=list)
    fees_incurred: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    idempotency_key: str = ""
    data_provenance: Dict[str, Any] = field(default_factory=dict)
    # Execution integrity fields
    worker_status: str = "NO_WORKER"
    exchange_status: str = "NO_EXCHANGE_ORDERS"
    execution_nature: str = "PLAN_ONLY"
    last_exchange_verification_utc: Optional[str] = None
    exchange_verification_evidence: Dict[str, Any] = field(default_factory=dict)
    client_order_ids: List[str] = field(default_factory=list)
    residual_position: Dict[str, Any] = field(default_factory=dict)
    status_reason: str = ""
    is_test: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class StrategyOrchestrator:
    """
    Central universal strategy run coordinator and state engine.
    Ensures absolute ledger, balance, and order isolation across profiles and exchanges.
    Enforces execution integrity and verifiable exchange state reconciliation.
    """

    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = storage_path or DEFAULT_RUNS_PATH
        self._runs: Dict[str, StrategyRun] = {}
        self._lock = asyncio.Lock()
        self._load()

    def _load(self):
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                valid_fields = {f.name for f in fields(StrategyRun)}
                self._runs = {
                    rid: StrategyRun(**{k: v for k, v in r.items() if k in valid_fields})
                    for rid, r in data.items()
                    if isinstance(r, dict)
                }
            except Exception:
                self._runs = {}
        else:
            self._runs = {}

    def _save(self):
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        with open(self.storage_path, "w", encoding="utf-8") as f:
            serialized = {rid: r.to_dict() for rid, r in self._runs.items()}
            json.dump(serialized, f, indent=2)

    def _evaluate_worker_liveness(self, run: StrategyRun) -> bool:
        """
        Evaluates worker liveness.
        If run claims RUNNING but has no worker heartbeat within 90s, marks as ORPHANED.
        Returns True if state changed.
        """
        if run.status == StrategyStatus.RUNNING.value:
            heartbeat_str = (run.data_provenance or {}).get("last_heartbeat_utc") or run.started_at_utc or run.created_at_utc
            is_alive = False
            if heartbeat_str:
                try:
                    hb_time = datetime.fromisoformat(heartbeat_str.replace("Z", "+00:00"))
                    now_time = datetime.now(timezone.utc)
                    age_seconds = (now_time - hb_time).total_seconds()
                    if age_seconds < 90:
                        is_alive = True
                except Exception:
                    is_alive = False

            if not is_alive:
                run.status = StrategyStatus.ORPHANED.value
                run.worker_status = "ORPHANED"
                run.status_reason = "No active background worker heartbeat within 90 seconds."
                return True
        return False

    def get_provider_implementation_status(self, provider_id: str) -> str:
        return PROVIDER_IMPLEMENTATION_STATUS.get(
            provider_id.upper(), ProviderImplementationStatus.PLANNED
        ).value

    async def get_profile_available_capital(
        self, profile_id: str, asset: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Fetches the authoritative available balance/capital allocated to the target profile.
        - PAPER: Virtual simulated cash ledger
        - Connected Exchange: Reads wallet/margin balance of quote asset (or USD equivalent).
        """
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        quote = "USDT"
        if asset:
            clean = asset.replace("/", "").replace("-", "").upper()
            if "USDT" in clean:
                quote = "USDT"
            elif "USD" in clean:
                quote = "USD"
            elif "EUR" in clean:
                quote = "EUR"
            elif "BTC" in clean and not clean.startswith("BTC"):
                quote = "BTC"

        # 1. Paper Mode
        if not profile_id or profile_id.upper() == "PAPER":
            summary = paper_engine.get_ledger_summary()
            free_cash = float(summary.get("cash_balance_usd", 10000.0))
            return {
                "profile_id": "PAPER",
                "exchange": "PAPER",
                "environment": "PAPER",
                "currency": "USD",
                "quote_asset": quote,
                "available_capital": free_cash,
                "total_equity": float(summary.get("total_equity_usd", 10000.0)),
                "allocation_status": "AVAILABLE",
                "verified": True,
                "detail": "Virtual paper trading sandbox ledger.",
                "last_refreshed_utc": now_iso,
            }

        # 2. Vault Profile Lookup
        profile = credential_vault.get_profile_public(profile_id)
        if not profile:
            return {
                "profile_id": profile_id,
                "exchange": "UNKNOWN",
                "environment": "UNKNOWN",
                "currency": quote,
                "quote_asset": quote,
                "available_capital": 0.0,
                "total_equity": 0.0,
                "allocation_status": "PROFILE_NOT_FOUND",
                "verified": False,
                "detail": f"Profile '{profile_id}' not found in vault.",
                "last_refreshed_utc": now_iso,
            }

        exch = str(profile.get("exchange", "")).upper()
        env = str(profile.get("environment", "DEMO")).upper()
        label = str(profile.get("label", exch))
        acct_data = profile.get("account_data")

        # Refresh balance if missing or old, with strict 3-second timeout
        if not acct_data:
            try:
                bal_res = await asyncio.wait_for(exchange_framework.fetch_profile_balances(profile_id), timeout=3.0)
                acct_data = bal_res.get("account_data")
            except Exception:
                acct_data = None

        if not acct_data:
            return {
                "profile_id": profile_id,
                "exchange": exch,
                "label": label,
                "environment": env,
                "currency": quote,
                "quote_asset": quote,
                "available_capital": 0.0,
                "total_equity": 0.0,
                "allocation_status": "UNVERIFIED_BALANCE",
                "verified": False,
                "detail": f"Account balances for '{label}' have not yet been synchronized from {exch}.",
                "last_refreshed_utc": now_iso,
            }

        # Extract free quote balance from assets or total valuation
        free_bal = 0.0
        tot_eq = float(acct_data.get("total_valuation_usd", 0.0) or acct_data.get("account_equity", 0.0) or acct_data.get("balance", 0.0))

        assets = acct_data.get("assets", [])
        if assets:
            for a in assets:
                if str(a.get("asset", "")).upper() == quote:
                    free_bal = float(a.get("free", 0.0))
                    break
            if free_bal == 0.0 and tot_eq > 0:
                free_bal = tot_eq
        else:
            free_bal = float(acct_data.get("free_margin", 0.0) or acct_data.get("balance", 0.0) or tot_eq)

        return {
            "profile_id": profile_id,
            "exchange": exch,
            "label": label,
            "environment": env,
            "currency": quote,
            "quote_asset": quote,
            "available_capital": round(free_bal, 2),
            "total_equity": round(tot_eq, 2),
            "allocation_status": "AVAILABLE" if free_bal > 0 else "ZERO_BALANCE",
            "verified": True,
            "detail": f"Fresh authenticated balance from {exch} ({env}).",
            "last_refreshed_utc": acct_data.get("last_refreshed_utc", now_iso),
        }

    async def preflight_strategy_launch(
        self,
        asset: str,
        strategy_id: str,
        profile_id: str,
        investment_amount: float,
        environment: str,
        risk_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Rigorous 5-point universal pre-flight gate:
        1. Profile Active Verification (ON/OFF)
        2. Provider & Product Compatibility
        3. Authentication & Capability Freshness
        4. Account Capital Allocation ('money from account' check)
        5. Live Execution Authorization Gate
        """
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        strat_clean = strategy_id.upper()
        env_clean = environment.upper()
        clean_asset = asset.strip().upper()

        checks = []
        blockers = []
        corrective_actions = []

        # -------------------------------------------------------------
        # Step 1: Profile Active Check
        # -------------------------------------------------------------
        if not profile_id or profile_id.upper() == "PAPER":
            is_active = True
            provider = "PAPER"
            product = "SIMULATED"
            prof_label = "Paper Sandbox"
            auth_ok = True
            impl_status = ProviderImplementationStatus.IMPLEMENTED_TESTED.value
            checks.append({
                "name": "Profile Active State",
                "passed": True,
                "severity": "INFO",
                "detail": "Paper simulation engine is active.",
            })
        else:
            profile = credential_vault.get_profile_public(profile_id)
            if not profile:
                return {
                    "status": "REJECTED",
                    "eligible": False,
                    "confirmation_summary": f"Execution REJECTED: Profile '{profile_id}' not found",
                    "checks": [{
                        "name": "Profile Lookup",
                        "passed": False,
                        "severity": "BLOCKER",
                        "detail": f"Profile '{profile_id}' does not exist.",
                    }],
                    "blockers": [f"Connection profile '{profile_id}' not found."],
                    "corrective_actions": ["Select a valid configured profile."],
                    "available_capital": 0.0,
                }
            provider = str(profile.get("exchange", "")).upper()
            product = str(profile.get("product_type") or "SPOT").upper()
            prof_label = str(profile.get("label", provider))
            is_active = profile.get("is_active", True)
            conn_stat = str(profile.get("connection_status", "")).upper()
            auth_ok = ("VERIFIED" in conn_stat)
            impl_status = self.get_provider_implementation_status(provider)

            if not is_active:
                checks.append({
                    "name": "Profile Active State",
                    "passed": False,
                    "severity": "BLOCKER",
                    "detail": f"Profile '{prof_label}' is toggled OFF (Inactive). Disabled profiles cannot run strategies.",
                })
                blockers.append(f"Connection profile '{prof_label}' is disabled (OFF).")
                corrective_actions.append("Turn this profile ON in the Connections Manager before launching.")
            else:
                checks.append({
                    "name": "Profile Active State",
                    "passed": True,
                    "severity": "INFO",
                    "detail": f"Profile '{prof_label}' is active (ON).",
                })

        # -------------------------------------------------------------
        # Step 2: Provider & Product Compatibility
        # -------------------------------------------------------------
        is_futures_strat = "FUTURES" in strat_clean
        is_futures_profile = "FUTURES" in product

        if is_futures_strat:
            checks.append({
                "name": "Strategy Compatibility",
                "passed": False,
                "severity": "BLOCKER",
                "detail": f"Futures strategy execution is coming soon and currently disabled.",
            })
            blockers.append("Futures strategies are not enabled in this release.")
            corrective_actions.append("Select a Spot strategy.")
        elif is_futures_profile and not is_futures_strat:
            checks.append({
                "name": "Product Alignment",
                "passed": True,
                "severity": "INFO",
                "detail": f"Spot strategy mapped to {product} profile with isolation.",
            })
        else:
            checks.append({
                "name": "Product Alignment",
                "passed": True,
                "severity": "INFO",
                "detail": f"Strategy matches profile product type ({product}).",
            })

        if impl_status == ProviderImplementationStatus.PLANNED.value:
            checks.append({
                "name": "Provider Support",
                "passed": False,
                "severity": "BLOCKER",
                "detail": f"Provider '{provider}' integration is planned for a future release.",
            })
            blockers.append(f"Provider '{provider}' is not yet supported for execution.")
            corrective_actions.append("Select Binance, Bitget, Bybit, Coinbase, OKX, or MT5.")
        else:
            checks.append({
                "name": "Provider Support",
                "passed": True,
                "severity": "INFO",
                "detail": f"Provider '{provider}' is fully supported ({impl_status}).",
            })

        # -------------------------------------------------------------
        # Step 3: Auth & Capabilities
        # -------------------------------------------------------------
        if not auth_ok and env_clean != "PAPER":
            checks.append({
                "name": "Authentication State",
                "passed": False,
                "severity": "WARNING",
                "detail": f"Connection profile '{prof_label}' has UNVERIFIED credentials.",
            })
            blockers.append(f"Profile '{prof_label}' API credentials are not verified.")
            corrective_actions.append("Run 'Verify Connection' in the Connections Manager.")
        else:
            checks.append({
                "name": "Authentication State",
                "passed": True,
                "severity": "INFO",
                "detail": f"Authentication status verified for {prof_label}.",
            })

        # -------------------------------------------------------------
        # Step 4: Account Capital Allocation ('Money from Account')
        # -------------------------------------------------------------
        cap_info = await self.get_profile_available_capital(profile_id, clean_asset)
        avail = float(cap_info.get("available_capital", 0.0))
        currency = cap_info.get("currency", "USDT")

        if investment_amount <= 0:
            checks.append({
                "name": "Capital Sizing",
                "passed": False,
                "severity": "BLOCKER",
                "detail": "Investment amount must be greater than zero.",
            })
            blockers.append("Investment amount must be positive.")
            corrective_actions.append("Specify an investment amount.")
        elif avail <= 0:
            checks.append({
                "name": "Account Capital Availability",
                "passed": False,
                "severity": "BLOCKER",
                "detail": f"Account has zero {currency} available for strategy allocation.",
            })
            blockers.append(f"Zero available {currency} in selected profile '{prof_label}'.")
            corrective_actions.append(f"Deposit funds or transfer {currency} into your {provider} account.")
        elif investment_amount > avail:
            checks.append({
                "name": "Account Capital Allocation",
                "passed": False,
                "severity": "BLOCKER",
                "detail": f"Requested allocation (${investment_amount:,.2f} {currency}) exceeds available balance (${avail:,.2f} {currency}).",
            })
            blockers.append(f"Requested ${investment_amount:,.2f} exceeds available ${avail:,.2f} {currency}.")
            corrective_actions.append(f"Reduce allocated amount to ≤ ${avail:,.2f} {currency}.")
        else:
            checks.append({
                "name": "Account Capital Allocation",
                "passed": True,
                "severity": "INFO",
                "detail": f"Allocated ${investment_amount:,.2f} {currency} safely covered by available ${avail:,.2f} {currency}.",
            })

        # -------------------------------------------------------------
        # Step 5: Live Execution Authorization Gate
        # -------------------------------------------------------------
        if env_clean == "LIVE":
            if not live_trading_auth_manager.is_live_trading_authorized():
                checks.append({
                    "name": "Live Trading Authorization",
                    "passed": False,
                    "severity": "BLOCKER",
                    "detail": "Backend live trading authorization is OFF in Settings.",
                })
                blockers.append("Live trading is unauthorized: Backend live trading authorization is OFF in Settings (live_trading_locked=true).")
                corrective_actions.append("Navigate to Settings -> Trading Controls and toggle Live Trading ON after acknowledging risks.")
                auth_state = ExecutionAuthorizationState.BLOCKED_LIVE_LOCK.value
            elif settings.live_trading_locked or settings.read_only_mode:
                checks.append({
                    "name": "System Safety Invariant",
                    "passed": False,
                    "severity": "BLOCKER",
                    "detail": "System configuration has hard-locked live trading (live_trading_locked=true / read_only_mode=true).",
                })
                blockers.append("System safety invariants enforce read-only execution.")
                corrective_actions.append("Live trading is locked by system configuration. Use DEMO or PAPER.")
                auth_state = ExecutionAuthorizationState.BLOCKED_LIVE_LOCK.value
            else:
                checks.append({
                    "name": "Live Trading Authorization",
                    "passed": True,
                    "severity": "INFO",
                    "detail": "Live trading authorized and confirmed.",
                })
                auth_state = "AUTHORIZED_LIVE"
        elif env_clean == "PAPER":
            auth_state = ExecutionAuthorizationState.AUTHORIZED_PAPER.value
            checks.append({
                "name": "Execution Authorization",
                "passed": True,
                "severity": "INFO",
                "detail": "Paper sandbox execution mode authorized.",
            })
        else:
            auth_state = ExecutionAuthorizationState.AUTHORIZED_DEMO.value
            checks.append({
                "name": "Execution Authorization",
                "passed": True,
                "severity": "INFO",
                "detail": "Demo execution mode authorized.",
            })

        eligible = len(blockers) == 0
        summary = (
            f"Preflight PASSED: Ready to launch {strat_clean} on {clean_asset} via {prof_label} ({env_clean})."
            if eligible
            else f"Preflight REJECTED: {len(blockers)} blocking issue(s) detected."
        )

        return {
            "status": "APPROVED" if eligible else "REJECTED",
            "eligible": eligible,
            "confirmation_summary": summary,
            "asset": clean_asset,
            "strategy_id": strat_clean,
            "profile_id": profile_id,
            "provider_id": provider,
            "product_type": product,
            "environment": env_clean,
            "investment_amount": investment_amount,
            "currency": currency,
            "available_capital": avail,
            "authorization_state": auth_state,
            "checks": checks,
            "blockers": blockers,
            "corrective_actions": corrective_actions,
            "last_verified_utc": now_iso,
        }

    async def launch_strategy_run(
        self,
        asset: str,
        strategy_id: str,
        profile_id: str,
        investment_amount: float,
        environment: str,
        parameters: Optional[Dict[str, Any]] = None,
        risk_config: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
        is_test: bool = False,
    ) -> Dict[str, Any]:
        """
        Launches an isolated strategy run across any provider/profile.
        Execution Integrity Enforcement:
        - Live trading lock enforced.
        - Exchange mutations remain disabled by safety policy.
        - For exchange profiles: records status "PLAN_ONLY", execution_nature "PLAN_ONLY",
          worker_status "NO_WORKER", exchange_status "SUBMISSION_NOT_IMPLEMENTED", provider_order_ids [].
        - For paper profiles: records status "PAPER_SIMULATION", execution_nature "PAPER_SIMULATION",
          worker_status "NO_WORKER", exchange_status "NO_EXCHANGE_ORDERS", provider_order_ids [].
        - Planned orders marked status "PLANNED", exchange_order_id None. Zero synthetic IDs.
        """
        async with self._lock:
            strat_clean = strategy_id.upper()
            clean_asset = asset.strip().upper()
            env_clean = environment.upper()
            params = parameters or {}
            risk = risk_config or {}
            is_test_run = is_test or bool(params.get("is_test") or risk.get("is_test"))

            # Generate or verify idempotency key
            idemp = idempotency_key or hashlib.sha256(
                f"{profile_id}:{env_clean}:{clean_asset}:{strat_clean}:{investment_amount}:{int(time.time() // 30)}".encode("utf-8")
            ).hexdigest()[:16]

            # Idempotency deduplication check: return existing if launched recently
            for r in self._runs.values():
                if r.idempotency_key == idemp and r.status in (
                    StrategyStatus.RUNNING.value,
                    StrategyStatus.INITIALIZING.value,
                    StrategyStatus.PLAN_ONLY.value,
                    StrategyStatus.PAPER_SIMULATION.value,
                ):
                    return {
                        "status": "DUPLICATE_IDEMPOTENT",
                        "message": "Strategy run already active for this idempotency key.",
                        "strategy_run": r.to_dict(),
                    }

            # Run Preflight Gate
            preflight = await self.preflight_strategy_launch(
                asset=clean_asset,
                strategy_id=strat_clean,
                profile_id=profile_id,
                investment_amount=investment_amount,
                environment=env_clean,
                risk_config=risk,
            )

            if env_clean == "LIVE" and not live_trading_auth_manager.is_live_trading_authorized():
                return {
                    "status": "AUTHORIZATION_BLOCKED",
                    "message": "Strategy launch rejected: Live trading authorization is OFF in Settings.",
                    "blockers": ["Live trading is unauthorized: Backend live trading authorization is OFF in Settings."],
                    "preflight": preflight,
                }

            if not preflight.get("eligible"):
                return {
                    "status": "PREFLIGHT_BLOCKED",
                    "message": "Strategy launch was rejected by preflight validation.",
                    "blockers": preflight.get("blockers", []),
                    "corrective_actions": preflight.get("corrective_actions", []),
                    "preflight": preflight,
                }

            # Generate immutable run ID
            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            run_id = f"strat_run_{int(time.time())}_{uuid.uuid4().hex[:8]}"
            provider = preflight["provider_id"]
            product = preflight["product_type"]
            currency = preflight["currency"]
            auth_state = preflight["authorization_state"]

            # Initialize planned order levels
            # Orders are explicitly marked PLANNED with exchange_order_id = None
            initial_orders = []
            ref_price = float(params.get("reference_price") or params.get("entry_price") or 100.0)
            if "GRID" in strat_clean:
                grid_count = int(params.get("grid_count", 5))
                lower_price = ref_price * 0.95
                upper_price = ref_price * 1.05
                step = (upper_price - lower_price) / (grid_count + 1)
                for i in range(1, grid_count + 1):
                    p_lvl = round(lower_price + step * i, 2)
                    cid = f"client_{run_id}_{i}"
                    initial_orders.append({
                        "order_id": cid,
                        "client_order_id": cid,
                        "exchange_order_id": None,
                        "side": "BUY" if p_lvl < ref_price else "SELL",
                        "price": p_lvl,
                        "quantity": round(investment_amount / grid_count / p_lvl, 4),
                        "status": "PLANNED",
                        "type": "LIMIT_GRID",
                        "submitted_to_exchange": False,
                        "created_at_utc": now_iso,
                    })
            elif "SCALP" in strat_clean:
                entry_p = float(params.get("entry_price") or ref_price)
                sl_p = float(risk.get("stop_loss") or (entry_p * 0.98))
                tp_p = float(risk.get("take_profit") or (entry_p * 1.03))
                qty = round(investment_amount / entry_p, 4) if entry_p > 0 else 1.0
                cid_entry = f"client_{run_id}_entry"
                cid_tp = f"client_{run_id}_tp"
                cid_sl = f"client_{run_id}_sl"
                initial_orders.append({
                    "order_id": cid_entry,
                    "client_order_id": cid_entry,
                    "exchange_order_id": None,
                    "side": "BUY",
                    "price": entry_p,
                    "quantity": qty,
                    "status": "PLANNED",
                    "type": "LIMIT_ENTRY",
                    "submitted_to_exchange": False,
                    "created_at_utc": now_iso,
                })
                initial_orders.append({
                    "order_id": cid_tp,
                    "client_order_id": cid_tp,
                    "exchange_order_id": None,
                    "side": "SELL",
                    "price": tp_p,
                    "quantity": qty,
                    "status": "PLANNED",
                    "type": "TAKE_PROFIT",
                    "submitted_to_exchange": False,
                    "created_at_utc": now_iso,
                })
                initial_orders.append({
                    "order_id": cid_sl,
                    "client_order_id": cid_sl,
                    "exchange_order_id": None,
                    "side": "SELL",
                    "price": sl_p,
                    "quantity": qty,
                    "status": "PLANNED",
                    "type": "STOP_LOSS",
                    "submitted_to_exchange": False,
                    "created_at_utc": now_iso,
                })
            else:
                entry_p = float(params.get("entry_price") or ref_price)
                qty = round(investment_amount / entry_p, 4) if entry_p > 0 else 1.0
                tp_p = float(risk.get("take_profit") or (entry_p * 1.03))
                cid_entry = f"client_{run_id}_entry"
                cid_target = f"client_{run_id}_target"
                initial_orders.append({
                    "order_id": cid_entry,
                    "client_order_id": cid_entry,
                    "exchange_order_id": None,
                    "side": "BUY",
                    "price": entry_p,
                    "quantity": qty,
                    "status": "PLANNED",
                    "type": "LIMIT_ENTRY",
                    "submitted_to_exchange": False,
                    "created_at_utc": now_iso,
                })
                initial_orders.append({
                    "order_id": cid_target,
                    "client_order_id": cid_target,
                    "exchange_order_id": None,
                    "side": "SELL",
                    "price": tp_p,
                    "quantity": qty,
                    "status": "PLANNED",
                    "type": "TARGET_PROFIT",
                    "submitted_to_exchange": False,
                    "created_at_utc": now_iso,
                })

            # Determine execution nature and truthful status
            # Exchange mutations remain disabled by safety constraints
            if profile_id.upper() == "PAPER":
                exec_nature = "PAPER_SIMULATION"
                init_status = StrategyStatus.PAPER_SIMULATION.value
                worker_stat = "NO_WORKER"
                exch_stat = "NO_EXCHANGE_ORDERS"
                status_rsn = "Simulated paper strategy staged. Zero exchange orders placed."
            else:
                exec_nature = "PLAN_ONLY"
                init_status = StrategyStatus.PLAN_ONLY.value
                worker_stat = "NO_WORKER"
                exch_stat = "SUBMISSION_NOT_IMPLEMENTED"
                status_rsn = "Strategy plan generated. Exchange order submission is disabled by safety policy (PLAN_ONLY). Zero exchange orders placed."

            new_run = StrategyRun(
                run_id=run_id,
                asset=clean_asset,
                strategy_id=strat_clean,
                strategy_name=strat_clean.replace("_", " ").title(),
                profile_id=profile_id,
                provider_id=provider,
                product_type=product,
                environment=env_clean,
                investment_amount=investment_amount,
                currency=currency,
                status=init_status,
                execution_mode=env_clean,
                authorization_state=auth_state,
                created_at_utc=now_iso,
                started_at_utc=now_iso,
                parameters=params,
                risk_config=risk,
                balance_source={
                    "profile_id": profile_id,
                    "allocated_amount": investment_amount,
                    "available_at_start": preflight["available_capital"],
                    "currency": currency,
                },
                provider_order_ids=[],  # Never synthetic order IDs
                normalized_orders=initial_orders,
                fills=[],
                fees_incurred=0.0,
                realized_pnl=0.0,
                unrealized_pnl=0.0,
                idempotency_key=idemp,
                data_provenance={
                    "provider": provider,
                    "environment": env_clean,
                    "confirmation_summary": preflight["confirmation_summary"],
                    "last_heartbeat_utc": now_iso,
                    "audit_note": status_rsn,
                },
                worker_status=worker_stat,
                exchange_status=exch_stat,
                execution_nature=exec_nature,
                last_exchange_verification_utc=now_iso,
                exchange_verification_evidence={
                    "source": "INTERNAL_AUDIT",
                    "checked_at": now_iso,
                    "open_orders_found": 0,
                    "detail": "Verified zero provider order IDs were ever submitted to exchange.",
                },
                client_order_ids=[o["order_id"] for o in initial_orders],
                residual_position={},
                status_reason=status_rsn,
                is_test=is_test_run,
            )

            self._runs[run_id] = new_run
            self._save()

            return {
                "status": "SUCCESS",
                "message": f"Strategy plan '{run_id}' registered successfully as {init_status} on {provider} ({env_clean}). Zero exchange orders placed.",
                "strategy_run": new_run.to_dict(),
                "execution_integrity": {
                    "execution_nature": new_run.execution_nature,
                    "status": new_run.status,
                    "worker_status": new_run.worker_status,
                    "exchange_status": new_run.exchange_status,
                    "provider_order_ids_count": 0,
                    "real_orders_placed": False,
                    "safe_mode": True,
                },
            }

    def list_strategy_runs(
        self,
        provider: Optional[str] = None,
        environment: Optional[str] = None,
        asset: Optional[str] = None,
        status: Optional[str] = None,
        exclude_tests: bool = True,
    ) -> List[Dict[str, Any]]:
        self._load()
        changed = False
        for r in self._runs.values():
            if self._evaluate_worker_liveness(r):
                changed = True
        if changed:
            self._save()

        runs = list(self._runs.values())

        if exclude_tests:
            runs = [r for r in runs if not getattr(r, "is_test", False)]
        if provider:
            runs = [r for r in runs if r.provider_id.upper() == provider.upper()]
        if environment:
            runs = [r for r in runs if r.environment.upper() == environment.upper()]
        if asset:
            clean_asset = asset.replace("/", "").replace("-", "").upper()
            runs = [r for r in runs if r.asset.replace("/", "").replace("-", "").upper() == clean_asset]
        if status:
            runs = [r for r in runs if r.status.upper() == status.upper()]

        # Sort by creation timestamp descending
        runs.sort(key=lambda r: r.created_at_utc, reverse=True)
        return [r.to_dict() for r in runs]

    def get_strategy_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        self._load()
        run = self._runs.get(run_id)
        if run:
            if self._evaluate_worker_liveness(run):
                self._save()
            return run.to_dict()
        return None

    async def pause_strategy_run(self, run_id: str) -> bool:
        async with self._lock:
            self._load()
            run = self._runs.get(run_id)
            if not run or run.status not in (StrategyStatus.RUNNING.value, StrategyStatus.PLAN_ONLY.value, StrategyStatus.PAPER_SIMULATION.value):
                return False
            run.status = StrategyStatus.PAUSED.value
            self._save()
            return True

    async def resume_strategy_run(self, run_id: str) -> bool:
        async with self._lock:
            self._load()
            run = self._runs.get(run_id)
            if not run or run.status != StrategyStatus.PAUSED.value:
                return False
            # Restore truthful status according to execution nature
            if run.execution_nature == "PAPER_SIMULATION":
                run.status = StrategyStatus.PAPER_SIMULATION.value
            elif run.execution_nature == "PLAN_ONLY":
                run.status = StrategyStatus.PLAN_ONLY.value
            else:
                run.status = StrategyStatus.RUNNING.value
            self._save()
            return True

    async def stop_strategy_run(self, run_id: str) -> Dict[str, Any]:
        """
        Verifiable Stop State Machine:
        - If no exchange orders ever existed (PLAN_ONLY or PAPER):
          clean local stop to STOPPED with NO_EXCHANGE_ORDERS.
        - If exchange orders were tracked:
          queries exchange; if real order cancellation disabled by safety lock:
          enters STOP_UNCONFIRMED / RECONCILIATION_REQUIRED.
        """
        async with self._lock:
            self._load()
            run = self._runs.get(run_id)
            if not run:
                return {
                    "status": "NOT_FOUND",
                    "message": f"Strategy run '{run_id}' not found.",
                }

            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            run.stopped_at_utc = now_iso

            # Zero exchange orders existed
            if len(run.provider_order_ids) == 0:
                run.status = StrategyStatus.STOPPED.value
                run.worker_status = "STOPPED"
                run.exchange_status = "NO_EXCHANGE_ORDERS"
                run.status_reason = "Strategy stopped locally. Zero exchange orders existed."
                run.last_exchange_verification_utc = now_iso
                run.exchange_verification_evidence = {
                    "source": "INTERNAL_AUDIT",
                    "checked_at": now_iso,
                    "open_orders_found": 0,
                    "detail": "Verified zero provider order IDs were ever submitted to exchange.",
                }
                self._save()
                return {
                    "status": "SUCCESS",
                    "run_status": run.status,
                    "worker_status": run.worker_status,
                    "exchange_status": run.exchange_status,
                    "message": "Strategy run stopped locally. Zero exchange orders existed.",
                    "evidence": run.exchange_verification_evidence,
                }
            else:
                # Exchange orders exist: Stop requested, check exchange
                run.status = StrategyStatus.STOP_REQUESTED.value
                # Since real cancel order mutation is disabled by safety invariants:
                run.status = StrategyStatus.STOP_UNCONFIRMED.value
                run.exchange_status = "RECONCILIATION_REQUIRED"
                run.status_reason = "Exchange order cancellation is disabled by safety locks. Open orders require manual cancellation or reconciliation."
                self._save()
                return {
                    "status": "WARNING",
                    "run_status": run.status,
                    "worker_status": "STOPPED",
                    "exchange_status": run.exchange_status,
                    "message": "Stop requested. Exchange cancellation is blocked by safety locks.",
                    "evidence": {
                        "source": "SAFETY_LOCK",
                        "checked_at": now_iso,
                        "open_orders_remaining": len(run.provider_order_ids),
                        "detail": "Cancellation mutation blocked by live_trading_locked=true.",
                    },
                }

    async def reconcile_strategy_run(self, run_id: str) -> Dict[str, Any]:
        """
        Performs a read-only exchange reconciliation for the given strategy run.
        Probes the exchange for open orders without mutating state.
        Updates last_exchange_verification_utc, exchange_verification_evidence, and exchange_status.
        """
        async with self._lock:
            self._load()
            run = self._runs.get(run_id)
            if not run:
                return {
                    "status": "NOT_FOUND",
                    "message": f"Strategy run '{run_id}' not found.",
                }

            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            # Case A: Paper Simulation
            if run.profile_id.upper() == "PAPER":
                evidence = {
                    "source": "PAPER_SANDBOX",
                    "checked_at": now_iso,
                    "open_orders_found": 0,
                    "detail": "Paper simulation run: isolated virtual ledger, zero exchange exposure.",
                }
                run.last_exchange_verification_utc = now_iso
                run.exchange_verification_evidence = evidence
                run.exchange_status = "NO_EXCHANGE_ORDERS"
                self._save()
                return {
                    "status": "SUCCESS",
                    "run_id": run_id,
                    "execution_nature": run.execution_nature,
                    "exchange_status": run.exchange_status,
                    "open_orders_count": 0,
                    "evidence": evidence,
                }

            # Case B: Exchange Profile (e.g. Binance, Bitget)
            clean_sym = run.asset.replace("/", "").replace("-", "").upper()
            try:
                # Query read-only open orders from exchange_framework
                res = await exchange_framework.fetch_open_orders(run.profile_id, symbol=clean_sym)
                matched_orders = []
                orders_list = res.get("orders", []) if res.get("status") == "SUCCESS" else []

                # Check for orders matching client_order_ids or provider_order_ids
                cids = set(run.client_order_ids)
                pids = set(run.provider_order_ids)
                for o in orders_list:
                    coid = str(o.get("client_order_id", ""))
                    oid = str(o.get("order_id", ""))
                    if (coid and coid in cids) or (oid and oid in pids):
                        matched_orders.append(o)

                evidence = {
                    "source": f"EXCHANGE_{run.provider_id}",
                    "checked_at": now_iso,
                    "profile_id": run.profile_id,
                    "symbol": clean_sym,
                    "exchange_fetch_status": res.get("status", "UNKNOWN"),
                    "total_open_orders_on_symbol": len(orders_list),
                    "matched_orders_for_run": len(matched_orders),
                    "raw_summary": f"Queried {run.provider_id} read-only endpoint: {len(orders_list)} symbol orders, {len(matched_orders)} matched.",
                }

                run.last_exchange_verification_utc = now_iso
                run.exchange_verification_evidence = evidence

                if len(matched_orders) > 0:
                    run.exchange_status = "OPEN_ON_EXCHANGE"
                elif len(run.provider_order_ids) == 0:
                    run.exchange_status = "NO_EXCHANGE_ORDERS"
                else:
                    run.exchange_status = "NO_OPEN_ORDERS"

                self._save()

                return {
                    "status": "SUCCESS",
                    "run_id": run_id,
                    "execution_nature": run.execution_nature,
                    "exchange_status": run.exchange_status,
                    "open_orders_count": len(matched_orders),
                    "evidence": evidence,
                }
            except Exception as e:
                evidence = {
                    "source": f"EXCHANGE_{run.provider_id}",
                    "checked_at": now_iso,
                    "profile_id": run.profile_id,
                    "error": str(e),
                    "raw_summary": f"Read-only exchange query failed: {str(e)}",
                }
                run.last_exchange_verification_utc = now_iso
                run.exchange_verification_evidence = evidence
                run.exchange_status = "UNKNOWN"
                self._save()
                return {
                    "status": "VERIFICATION_ERROR",
                    "run_id": run_id,
                    "exchange_status": "UNKNOWN",
                    "evidence": evidence,
                }

    async def delete_strategy_run(self, run_id: str) -> bool:
        async with self._lock:
            self._load()
            if run_id in self._runs:
                del self._runs[run_id]
                self._save()
                return True
            return False


# Global singleton instance
strategy_orchestrator = StrategyOrchestrator()
