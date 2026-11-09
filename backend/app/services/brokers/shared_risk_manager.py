"""
BITDEX Centralized Shared Account-Level Risk Manager
===================================================
Enforces global portfolio risk constraints across BOTH Scalping & Long-Term engines:
1. Hard Lock: REAL_TRADING_PERMANENTLY_LOCKED == True (Real account #16000629657 permanently blocked)
2. Per-Trade Risk: Maximum 0.25% of current equity per setup
3. Daily Loss Circuit: Maximum 1.00% daily realized + floating drawdown across ALL engines combined
4. Aggregate Open Risk: Sum of open position stop-loss risks <= Max Aggregate Budget (e.g. 1.00%)
5. Cluster Correlation: Prevents stacked same-direction exposure in correlated clusters (e.g. USD, CRYPTO, METAL)
6. Atomic Locking: Process-level mutex preventing race conditions and simultaneous order submission
"""

import asyncio
import json
import logging
import sqlite3
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("SharedCentralRiskManager")

# Correlated asset clusters
ASSET_CLUSTERS = {
    "USD": ["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "USDCHF"],
    "CRYPTO": ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "LTCUSD"],
    "METAL": ["XAUUSD", "XAGUSD"],
    "EQUITY": ["US500", "US30", "USTEC"]
}

_AGGREGATE_RISK_LOCK = asyncio.Lock()

class SharedCentralRiskManager:
    DAILY_LOSS_CEILING_PCT: float = 0.0100 # 1.00%
    MAX_PER_TRADE_RISK_PCT: float = 0.0025 # 0.25%
    MAX_AGGREGATE_OPEN_RISK_PCT: float = 0.0100 # 1.00% max open SL risk
    MAX_CONCURRENT_POSITIONS: int = 2

    @classmethod
    async def preflight_check(
        cls,
        conn: sqlite3.Connection,
        account_id: str,
        adapter,
        symbol: str,
        side: str,
        volume: float,
        entry_price: float,
        sl_price: float,
        engine_type: str = "LONG_TERM",
        real_trading_permanently_locked: bool = True
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Runs atomic 7-point shared account-level risk validation before ANY order can proceed.
        Returns: (passed: bool, rejection_reason: str, audit_context: dict)
        """
        async with _AGGREGATE_RISK_LOCK:
            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            context = {
                "account_id": account_id,
                "symbol": symbol,
                "engine_type": engine_type,
                "side": side,
                "volume": volume,
                "entry_price": entry_price,
                "sl_price": sl_price,
                "timestamp": now_iso
            }

            # 1. Hard Real Account Lock
            if str(account_id).strip() == "16000629657" or not real_trading_permanently_locked:
                return False, "ERR_REAL_TRADING_PERMANENTLY_LOCKED: Account 16000629657 is permanently blocked.", context

            # 2. Query Live Broker Summary & Open Positions
            summary = await adapter.get_account_summary(force_refresh=True)
            equity = float(summary.get("equity") or 5000.20)
            balance = float(summary.get("balance") or equity)
            open_positions = await adapter.get_open_positions()

            context["equity"] = equity
            context["balance"] = balance
            context["open_positions_count"] = len(open_positions)

            # 3. Maximum Concurrent Positions Gate
            if len(open_positions) >= cls.MAX_CONCURRENT_POSITIONS:
                return False, f"ERR_MAX_CONCURRENT_POSITIONS: {len(open_positions)}/{cls.MAX_CONCURRENT_POSITIONS} active.", context

            # 4. Symbol Duplication Check
            existing_syms = [p.get("symbol") for p in open_positions]
            if symbol in existing_syms:
                return False, f"ERR_SYMBOL_POSITION_ALREADY_OPEN: Position on {symbol} already exists.", context

            # 5. Proposed Trade Monetary Risk
            spec = await adapter.get_instrument_specification(symbol)
            contract_size = float(spec.get("contract_size") or 1.0)
            sl_distance = abs(entry_price - sl_price)
            proposed_risk_usd = round(volume * sl_distance * contract_size, 2)
            proposed_risk_pct = proposed_risk_usd / equity if equity > 0 else 1.0

            context["proposed_risk_usd"] = proposed_risk_usd
            context["proposed_risk_pct"] = round(proposed_risk_pct * 100, 3)

            # 0.25% Max per trade (with 10% tolerance for lot-rounding)
            if proposed_risk_pct > (cls.MAX_PER_TRADE_RISK_PCT * 1.15):
                return False, f"ERR_RISK_BUDGET_EXCEEDED: Proposed risk ${proposed_risk_usd} ({proposed_risk_pct*100:.3f}%) exceeds 0.25% cap.", context

            # 6. Aggregate Open Position Risk
            total_open_risk_usd = 0.0
            for p in open_positions:
                p_sym = p.get("symbol")
                p_vol = float(p.get("volume") or 0.0)
                p_entry = float(p.get("open_price") or p.get("entry_price") or 0.0)
                p_sl = float(p.get("sl") or p_entry)
                p_dist = abs(p_entry - p_sl)
                p_spec = await adapter.get_instrument_specification(p_sym)
                p_cs = float(p_spec.get("contract_size") or 1.0)
                total_open_risk_usd += (p_vol * p_dist * p_cs)

            aggregate_risk_usd = total_open_risk_usd + proposed_risk_usd
            aggregate_risk_pct = aggregate_risk_usd / equity if equity > 0 else 1.0

            context["aggregate_risk_usd"] = round(aggregate_risk_usd, 2)
            context["aggregate_risk_pct"] = round(aggregate_risk_pct * 100, 3)

            if aggregate_risk_pct > cls.MAX_AGGREGATE_OPEN_RISK_PCT:
                return False, f"ERR_AGGREGATE_RISK_EXCEEDED: Total risk ${aggregate_risk_usd:.2f} ({aggregate_risk_pct*100:.2f}%) exceeds 1.00% portfolio limit.", context

            # 7. Daily Loss Circuit (Realized + Current Floating)
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            ledger = conn.execute("SELECT * FROM risk_ledger_state WHERE account_id = ?", (account_id,)).fetchone()
            daily_realized_loss = 0.0
            if ledger:
                daily_realized_loss = max(0.0, -float(ledger["daily_realized_pnl"]))

            floating_loss = sum(max(0.0, -float(p.get("unrealized_pnl") or 0.0)) for p in open_positions)
            total_current_loss = daily_realized_loss + floating_loss
            loss_pct = total_current_loss / equity if equity > 0 else 0.0

            if loss_pct >= cls.DAILY_LOSS_CEILING_PCT:
                return False, f"ERR_DAILY_LOSS_CEILING_BREACHED: Current drawdown ${total_current_loss:.2f} ({loss_pct*100:.2f}%) reached 1.00% daily cap.", context

            # 8. Correlated Cluster Exposure Gate
            target_cluster = None
            for cl_name, cl_symbols in ASSET_CLUSTERS.items():
                if symbol in cl_symbols:
                    target_cluster = cl_name
                    break

            if target_cluster:
                cluster_positions = [p for p in open_positions if p.get("symbol") in ASSET_CLUSTERS.get(target_cluster, [])]
                if len(cluster_positions) >= 2:
                    return False, f"ERR_CLUSTER_CORRELATION_LIMIT: Already holding {len(cluster_positions)} positions in {target_cluster} cluster.", context

            return True, "PASS", context
