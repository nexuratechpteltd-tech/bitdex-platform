"""
Exness Deterministic Mock Adapter
Provides a high-fidelity simulation of an Exness MT5 Standard/Pro Demo account.
Specification reference: Master Exness HFT Implementation Specification, Part 4.3 & Part 10.
"""

import time
import math
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import logging

from .base_adapter import ExnessBaseAdapter

logger = logging.getLogger("bitdex.exness.mock")

# Standard Exness MT5 Instrument Specifications
EXNESS_MOCK_SPECS: Dict[str, Dict[str, Any]] = {
    "XAUUSDm": {
        "broker_symbol": "XAUUSDm",
        "canonical_symbol": "XAU/USD",
        "name": "Gold vs US Dollar (Mini/Pro)",
        "product_type": "METALS",
        "contract_size": 100.0,  # 100 oz per 1.0 lot
        "min_volume": 0.01,
        "max_volume": 20.0,
        "volume_step": 0.01,
        "tick_size": 0.01,
        "tick_value": 1.0,  # $1 per $0.01 move per lot
        "digits": 2,
        "typical_spread": 0.16,  # 16 cents spread
        "stops_level": 30,  # minimum distance in points (0.30)
        "leverage": 2000,
        "margin_initial_pct": 0.05,  # 0.05% margin (1:2000)
        "commission_per_lot_usd": 0.0,  # Standard/Pro zero-commission model (spread only)
        "swap_long_points": -8.5,
        "swap_short_points": 2.1,
        "is_tradable": True,
        "trade_mode": "FULL_ACCESS",
        "base_price": 2742.50,
    },
    "EURUSDm": {
        "broker_symbol": "EURUSDm",
        "canonical_symbol": "EUR/USD",
        "name": "Euro vs US Dollar",
        "product_type": "FOREX",
        "contract_size": 100000.0,
        "min_volume": 0.01,
        "max_volume": 50.0,
        "volume_step": 0.01,
        "tick_size": 0.00001,
        "tick_value": 1.0,
        "digits": 5,
        "typical_spread": 0.00008,
        "stops_level": 10,
        "leverage": 2000,
        "margin_initial_pct": 0.05,
        "commission_per_lot_usd": 0.0,
        "swap_long_points": -5.2,
        "swap_short_points": 1.8,
        "is_tradable": True,
        "trade_mode": "FULL_ACCESS",
        "base_price": 1.11950,
    },
    "GBPUSDm": {
        "broker_symbol": "GBPUSDm",
        "canonical_symbol": "GBP/USD",
        "name": "Great Britain Pound vs US Dollar",
        "product_type": "FOREX",
        "contract_size": 100000.0,
        "min_volume": 0.01,
        "max_volume": 50.0,
        "volume_step": 0.01,
        "tick_size": 0.00001,
        "tick_value": 1.0,
        "digits": 5,
        "typical_spread": 0.00012,
        "stops_level": 15,
        "leverage": 2000,
        "margin_initial_pct": 0.05,
        "commission_per_lot_usd": 0.0,
        "swap_long_points": -4.1,
        "swap_short_points": 0.9,
        "is_tradable": True,
        "trade_mode": "FULL_ACCESS",
        "base_price": 1.31200,
    },
    "BTCUSDm": {
        "broker_symbol": "BTCUSDm",
        "canonical_symbol": "BTC/USD",
        "name": "Bitcoin vs US Dollar",
        "product_type": "CRYPTO",
        "contract_size": 1.0,
        "min_volume": 0.01,
        "max_volume": 5.0,
        "volume_step": 0.01,
        "tick_size": 0.1,
        "tick_value": 0.1,
        "digits": 2,
        "typical_spread": 12.50,
        "stops_level": 50,
        "leverage": 200,  # Lower crypto leverage
        "margin_initial_pct": 0.5,
        "commission_per_lot_usd": 0.0,
        "swap_long_points": -15.0,
        "swap_short_points": 5.0,
        "is_tradable": True,
        "trade_mode": "FULL_ACCESS",
        "base_price": 77800.00,
    },
}


class ExnessDeterministicMockAdapter(ExnessBaseAdapter):
    """
    Deterministic Mock Demo Adapter for Exness MT5.
    Explicitly labeled as mock / demo-only.
    Models broker contract rules, margin calculation, order tickets, and fills.
    """

    def __init__(
        self,
        account_id: str = "149827361",
        server: str = "Exness-MT5Trial",
        initial_balance: float = 5000.0,
    ):
        self.account_id = account_id
        self.server = server
        self.balance = float(initial_balance)
        self.currency = "USD"
        self.leverage = 2000
        self.is_connected = False
        self.connected_at: Optional[str] = None

        # State storage
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.order_history: List[Dict[str, Any]] = []
        self.trade_history: List[Dict[str, Any]] = []
        self._price_offsets: Dict[str, float] = {}

    async def connect(self) -> Dict[str, Any]:
        """Connects to mock Exness session."""
        self.is_connected = True
        self.connected_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        logger.info(f"Connected to Exness Mock Demo (Account: {self.account_id}, Server: {self.server})")
        return {
            "status": "CONNECTED",
            "adapter_connected": True,
            "broker_authenticated": False,  # Explicitly simulated!
            "is_mock": True,
            "broker_mode": "DETERMINISTIC_MOCK_DEMO",
            "connection_type": "SIMULATED_DEMO",
            "account_id": self.account_id,
            "server": self.server,
            "connected_at": self.connected_at,
            "notice": "Simulated Exness MT5 Demo session. Not a real broker connection.",
        }

    async def disconnect(self) -> Dict[str, Any]:
        """Terminates mock session."""
        self.is_connected = False
        return {
            "status": "DISCONNECTED",
            "adapter_connected": False,
            "broker_authenticated": False,
            "is_mock": True,
            "broker_mode": "DETERMINISTIC_MOCK_DEMO",
            "connection_type": "SIMULATED_DEMO",
        }

    async def get_connection_status(self) -> Dict[str, Any]:
        return {
            "is_connected": self.is_connected,
            "adapter_connected": self.is_connected,
            "broker_authenticated": False,  # Mock is never real broker authentication
            "is_mock": True,
            "broker_mode": "DETERMINISTIC_MOCK_DEMO",
            "connection_type": "SIMULATED_DEMO",
            "live_execution_locked": True,
            "latency_ms": 14.5 if self.is_connected else None,
            "broker_server": self.server,
            "account_id": self.account_id,
            "last_heartbeat_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    async def get_symbols(self) -> List[str]:
        return list(EXNESS_MOCK_SPECS.keys())

    async def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        sym = symbol.strip()
        # Resolve both XAUUSDm and XAU/USD
        match = next(
            (spec for k, spec in EXNESS_MOCK_SPECS.items() if k == sym or spec["canonical_symbol"] == sym),
            None,
        )
        return match.copy() if match else None

    async def get_latest_tick(self, symbol: str) -> Optional[Dict[str, Any]]:
        spec = await self.get_symbol_info(symbol)
        if not spec:
            return None

        sym_key = spec["broker_symbol"]
        base_p = spec["base_price"]
        offset = self._price_offsets.get(sym_key, 0.0)
        spread = spec["typical_spread"]

        mid = base_p + offset
        bid = round(mid - (spread / 2.0), spec["digits"])
        ask = round(mid + (spread / 2.0), spec["digits"])

        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return {
            "symbol": sym_key,
            "canonical_symbol": spec["canonical_symbol"],
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "spread": spread,
            "spread_points": int(round(spread / spec["tick_size"])),
            "time_utc": now_utc,
            "timestamp_ms": int(time.time() * 1000),
            "is_mock": True,
        }

    async def get_historical_candles(
        self, symbol: str, timeframe: str = "M1", count: int = 100
    ) -> List[Dict[str, Any]]:
        tick = await self.get_latest_tick(symbol)
        if not tick:
            return []
        mid = tick["mid"]
        now_ts = int(time.time())
        candles = []
        for i in range(count, 0, -1):
            t = now_ts - (i * 60)
            wave = math.sin(i / 5.0) * 0.4
            c_open = mid + wave
            c_close = c_open + (0.1 if i % 2 == 0 else -0.1)
            candles.append({
                "time": t,
                "time_iso": datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "open": round(c_open, 2),
                "high": round(max(c_open, c_close) + 0.25, 2),
                "low": round(min(c_open, c_close) - 0.25, 2),
                "close": round(c_close, 2),
                "volume": 45 + (i % 20),
            })
        return candles

    async def calculate_margin(
        self, symbol: str, order_type: str, volume: float
    ) -> Dict[str, Any]:
        spec = await self.get_symbol_info(symbol)
        if not spec:
            raise ValueError(f"Unknown symbol {symbol}")

        tick = await self.get_latest_tick(symbol)
        price = tick["ask"] if order_type.upper() == "BUY" else tick["bid"]
        contract_size = spec["contract_size"]
        notional = volume * contract_size * price
        required_margin = round(notional / spec["leverage"], 2)

        acct = await self.get_account_info()
        free_margin_post = round(acct["free_margin"] - required_margin, 2)
        is_affordable = free_margin_post >= 0

        return {
            "symbol": spec["broker_symbol"],
            "order_type": order_type.upper(),
            "volume": volume,
            "notional_usd": round(notional, 2),
            "leverage": spec["leverage"],
            "required_margin_usd": required_margin,
            "current_free_margin_usd": acct["free_margin"],
            "free_margin_post_usd": free_margin_post,
            "is_affordable": is_affordable,
            "status": "APPROVED" if is_affordable else "INSUFFICIENT_MARGIN",
        }

    async def get_account_info(self) -> Dict[str, Any]:
        """Calculates live equity, used margin, free margin, and margin level."""
        used_margin = 0.0
        unrealized_pnl = 0.0

        for pos in self.positions.values():
            spec = EXNESS_MOCK_SPECS.get(pos["symbol"])
            if not spec:
                continue
            tick = await self.get_latest_tick(pos["symbol"])
            cur_price = tick["bid"] if pos["type"] == "BUY" else tick["ask"]
            pos["current_price"] = cur_price

            # P&L Calculation: (PriceDiff) * Volume * ContractSize
            price_diff = (cur_price - pos["open_price"]) if pos["type"] == "BUY" else (pos["open_price"] - cur_price)
            pos_profit = round(price_diff * pos["volume"] * spec["contract_size"], 2)
            pos["profit"] = pos_profit
            unrealized_pnl += pos_profit

            # Margin for leg
            notional = pos["volume"] * spec["contract_size"] * pos["open_price"]
            used_margin += (notional / spec["leverage"])

        used_margin = round(used_margin, 2)
        equity = round(self.balance + unrealized_pnl, 2)
        free_margin = round(equity - used_margin, 2)
        margin_level = round((equity / used_margin * 100.0), 2) if used_margin > 0 else 0.0

        return {
            "account_id": self.account_id,
            "server": self.server,
            "currency": self.currency,
            "leverage": self.leverage,
            "balance": round(self.balance, 2),
            "equity": equity,
            "used_margin": used_margin,
            "free_margin": free_margin,
            "margin_level": margin_level,
            "open_positions_count": len(self.positions),
            "is_demo": True,
            "is_mock": True,
            "broker_mode": "DETERMINISTIC_MOCK_DEMO",
            "updated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    async def submit_order(self, order_req: Dict[str, Any]) -> Dict[str, Any]:
        """Submits and fills a simulated Exness demo order."""
        symbol = order_req.get("symbol")
        spec = await self.get_symbol_info(symbol)
        if not spec:
            raise ValueError(f"Unsupported symbol: {symbol}")

        volume = float(order_req.get("volume", 0.0))
        if volume < spec["min_volume"] or volume > spec["max_volume"]:
            raise ValueError(f"Volume {volume} outside limits [{spec['min_volume']}, {spec['max_volume']}]")

        # Step check
        steps = round(volume / spec["volume_step"], 4)
        if not abs(steps - round(steps)) < 1e-4:
            raise ValueError(f"Volume {volume} does not match step {spec['volume_step']}")

        side = str(order_req.get("order_type", "BUY")).upper()
        if side not in ("BUY", "SELL"):
            raise ValueError(f"Invalid order_type: {side}")

        # Check margin
        margin_check = await self.calculate_margin(spec["broker_symbol"], side, volume)
        if not margin_check["is_affordable"]:
            return {
                "status": "REJECTED",
                "reason": "INSUFFICIENT_MARGIN",
                "details": margin_check,
            }

        tick = await self.get_latest_tick(spec["broker_symbol"])
        fill_price = tick["ask"] if side == "BUY" else tick["bid"]

        sl = order_req.get("sl")
        tp = order_req.get("tp")
        sl_val = float(sl) if sl is not None else None
        tp_val = float(tp) if tp is not None else None

        # Verify stop loss distance against broker stops_level
        stops_dist_pts = spec["stops_level"] * spec["tick_size"]
        if sl_val is not None:
            if side == "BUY" and (fill_price - sl_val) < stops_dist_pts:
                raise ValueError(f"Stop-loss distance {fill_price - sl_val:.2f} less than broker stop level {stops_dist_pts:.2f}")
            if side == "SELL" and (sl_val - fill_price) < stops_dist_pts:
                raise ValueError(f"Stop-loss distance {sl_val - fill_price:.2f} less than broker stop level {stops_dist_pts:.2f}")

        ticket = f"MT5-DEMO-{secrets.token_hex(4).upper()}"
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        pos = {
            "ticket": ticket,
            "symbol": spec["broker_symbol"],
            "canonical_symbol": spec["canonical_symbol"],
            "type": side,
            "volume": volume,
            "open_price": fill_price,
            "current_price": fill_price,
            "sl": sl_val,
            "tp": tp_val,
            "broker_stop_confirmed": sl_val is not None,
            "commission": spec["commission_per_lot_usd"] * volume,
            "swap": 0.0,
            "profit": 0.0,
            "idempotency_key": order_req.get("idempotency_key", f"idemp-{secrets.token_hex(4)}"),
            "comment": order_req.get("comment", "BITDEX-HFT-DEMO"),
            "magic_number": order_req.get("magic_number", 777001),
            "time_opened": now_utc,
            "is_mock": True,
        }

        self.positions[ticket] = pos
        self.order_history.append(pos.copy())

        logger.info(f"Filled Mock Order: Ticket={ticket}, Side={side}, Volume={volume}, Price={fill_price}")
        return {
            "status": "FILLED",
            "ticket": ticket,
            "symbol": spec["broker_symbol"],
            "side": side,
            "filled_volume": volume,
            "fill_price": fill_price,
            "sl": sl_val,
            "tp": tp_val,
            "broker_stop_active": sl_val is not None,
            "timestamp_utc": now_utc,
            "is_mock": True,
        }

    async def modify_order(
        self, ticket: str, sl: Optional[float] = None, tp: Optional[float] = None
    ) -> Dict[str, Any]:
        if ticket not in self.positions:
            raise KeyError(f"Ticket {ticket} not found among active positions")
        pos = self.positions[ticket]
        if sl is not None:
            pos["sl"] = float(sl)
            pos["broker_stop_confirmed"] = True
        if tp is not None:
            pos["tp"] = float(tp)
        return {
            "status": "MODIFIED",
            "ticket": ticket,
            "sl": pos["sl"],
            "tp": pos["tp"],
            "broker_stop_confirmed": pos["broker_stop_confirmed"],
            "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    async def close_position(
        self, ticket: str, volume: Optional[float] = None
    ) -> Dict[str, Any]:
        if ticket not in self.positions:
            raise KeyError(f"Ticket {ticket} not found among active positions")
        pos = self.positions[ticket]
        close_vol = float(volume) if volume is not None else pos["volume"]

        if close_vol >= pos["volume"] - 1e-6:
            # Full close
            tick = await self.get_latest_tick(pos["symbol"])
            close_price = tick["bid"] if pos["type"] == "BUY" else tick["ask"]
            spec = EXNESS_MOCK_SPECS[pos["symbol"]]

            price_diff = (close_price - pos["open_price"]) if pos["type"] == "BUY" else (pos["open_price"] - close_price)
            realized_pnl = round(price_diff * pos["volume"] * spec["contract_size"], 2)

            self.balance = round(self.balance + realized_pnl, 2)
            closed_pos = self.positions.pop(ticket)
            closed_pos["close_price"] = close_price
            closed_pos["realized_pnl"] = realized_pnl
            closed_pos["time_closed"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            self.trade_history.append(closed_pos)

            return {
                "status": "CLOSED",
                "ticket": ticket,
                "closed_volume": pos["volume"],
                "close_price": close_price,
                "realized_pnl": realized_pnl,
                "remaining_volume": 0.0,
                "is_mock": True,
            }
        else:
            return await self.close_partial_position(ticket, close_vol)

    async def close_partial_position(
        self, ticket: str, volume: float
    ) -> Dict[str, Any]:
        if ticket not in self.positions:
            raise KeyError(f"Ticket {ticket} not found")
        pos = self.positions[ticket]
        if volume <= 0 or volume >= pos["volume"]:
            raise ValueError(f"Partial volume {volume} invalid for position size {pos['volume']}")

        spec = EXNESS_MOCK_SPECS[pos["symbol"]]
        tick = await self.get_latest_tick(pos["symbol"])
        close_price = tick["bid"] if pos["type"] == "BUY" else tick["ask"]

        price_diff = (close_price - pos["open_price"]) if pos["type"] == "BUY" else (pos["open_price"] - close_price)
        realized_pnl = round(price_diff * volume * spec["contract_size"], 2)

        self.balance = round(self.balance + realized_pnl, 2)
        pos["volume"] = round(pos["volume"] - volume, 2)

        deal = {
            "ticket": ticket,
            "type": f"PARTIAL_{pos['type']}",
            "closed_volume": volume,
            "remaining_volume": pos["volume"],
            "close_price": close_price,
            "realized_pnl": realized_pnl,
            "time_closed": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        self.trade_history.append(deal)

        return {
            "status": "PARTIALLY_CLOSED",
            "ticket": ticket,
            "closed_volume": volume,
            "remaining_volume": pos["volume"],
            "close_price": close_price,
            "realized_pnl": realized_pnl,
            "is_mock": True,
        }

    async def get_open_positions(self) -> List[Dict[str, Any]]:
        # Refresh current prices and profits
        await self.get_account_info()
        return list(self.positions.values())

    async def get_order_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        return list(reversed(self.order_history[-limit:]))

    async def get_trade_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        return list(reversed(self.trade_history[-limit:]))

    async def verify_protective_stop(self, ticket: str) -> Dict[str, Any]:
        if ticket not in self.positions:
            return {"broker_stop_active": False, "reason": "POSITION_NOT_FOUND"}
        pos = self.positions[ticket]
        spec = EXNESS_MOCK_SPECS[pos["symbol"]]
        sl = pos.get("sl")
        if sl is None:
            return {
                "ticket": ticket,
                "broker_stop_active": False,
                "reason": "NO_STOP_LOSS_SET",
            }
        tick = await self.get_latest_tick(pos["symbol"])
        dist_pts = abs(tick["mid"] - sl) / spec["tick_size"]
        return {
            "ticket": ticket,
            "broker_stop_active": True,
            "stop_price": sl,
            "current_mid": tick["mid"],
            "distance_points": round(dist_pts, 1),
            "is_valid": dist_pts >= spec["stops_level"],
            "stops_level": spec["stops_level"],
        }

    async def reconcile_account(
        self, local_positions: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Authoritative reconciliation cross-checking broker positions with local records.
        Never compares broker count against itself.
        """
        if not self.is_connected:
            return {
                "status": "BROKER_UNAVAILABLE",
                "reconciliation_source": "SIMULATED_MOCK",
                "is_mock": True,
                "discrepancy_count": 0,
                "reason": "Mock session is disconnected.",
                "reconciled_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }

        acct = await self.get_account_info()
        broker_pos = await self.get_open_positions()
        loc_pos = local_positions if local_positions is not None else []

        broker_by_ticket = {str(p["ticket"]): p for p in broker_pos}
        local_by_ticket = {
            str(p.get("broker_ticket", p.get("ticket"))): p
            for p in loc_pos
            if p.get("broker_ticket") or p.get("ticket")
        }

        discrepancies = []

        # 1. Untracked broker positions (exists on broker, missing in local DB)
        for t, bp in broker_by_ticket.items():
            if t not in local_by_ticket:
                discrepancies.append({
                    "ticket": t,
                    "type": "UNTRACKED_BROKER_POSITION",
                    "symbol": bp["symbol"],
                    "volume": bp["volume"],
                    "details": f"Position {t} ({bp['symbol']} {bp['volume']} lots) exists on broker but missing locally.",
                })
            else:
                lp = local_by_ticket[t]
                # Symbol match
                b_sym = str(bp.get("symbol", "")).upper()
                l_sym = str(lp.get("symbol", "")).upper()
                if l_sym and b_sym and l_sym != b_sym:
                    discrepancies.append({
                        "ticket": t,
                        "type": "SYMBOL_MISMATCH",
                        "broker_symbol": b_sym,
                        "local_symbol": l_sym,
                        "details": f"Symbol mismatch on {t}: broker={b_sym}, local={l_sym}",
                    })
                # Direction match
                b_dir = str(bp.get("type", "")).upper()
                l_dir = str(lp.get("order_side", "")).upper()
                if l_dir and b_dir and l_dir != b_dir:
                    discrepancies.append({
                        "ticket": t,
                        "type": "DIRECTION_MISMATCH",
                        "broker_direction": b_dir,
                        "local_direction": l_dir,
                        "details": f"Direction mismatch on {t}: broker={b_dir}, local={l_dir}",
                    })
                # Volume match
                b_vol = float(bp.get("volume", 0))
                l_vol = float(lp.get("volume", 0))
                if abs(b_vol - l_vol) > 1e-4:
                    discrepancies.append({
                        "ticket": t,
                        "type": "VOLUME_MISMATCH",
                        "broker_volume": b_vol,
                        "local_volume": l_vol,
                        "details": f"Volume mismatch on {t}: broker={b_vol}, local={l_vol}",
                    })

        # 2. Missing broker positions (exists in local DB, missing on broker)
        for t, lp in local_by_ticket.items():
            if t not in broker_by_ticket:
                discrepancies.append({
                    "ticket": t,
                    "type": "MISSING_BROKER_POSITION",
                    "details": f"Local position {t} not found among active broker positions (may be closed or liquidated).",
                })

        net_lots_broker = sum(p["volume"] if p["type"] == "BUY" else -p["volume"] for p in broker_pos)
        gross_lots_broker = sum(p["volume"] for p in broker_pos)
        net_lots_local = sum(
            float(p.get("volume", 0)) if str(p.get("order_side", "")).upper() == "BUY" else -float(p.get("volume", 0))
            for p in loc_pos
        )

        status = "DISCREPANCY_DETECTED" if discrepancies else "RECONCILED"

        return {
            "status": status,
            "reconciliation_source": "SIMULATED_MOCK",
            "is_mock": True,
            "account_id": self.account_id,
            "broker_positions_count": len(broker_pos),
            "local_positions_count": len(loc_pos),
            "discrepancy_count": len(discrepancies),
            "discrepancies": discrepancies,
            "net_broker_lots": round(net_lots_broker, 4),
            "net_local_lots": round(net_lots_local, 4),
            "gross_broker_lots": round(gross_lots_broker, 4),
            "equity": acct["equity"],
            "balance": acct["balance"],
            "used_margin": acct["used_margin"],
            "free_margin": acct["free_margin"],
            "margin_level": acct["margin_level"],
            "reconciled_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    # Simulation Helper Methods for Testing & Adverse Scenarios
    def simulate_price_movement(self, symbol: str, delta: float) -> None:
        """Simulates price ticks for backtesting and adverse condition evaluation."""
        spec = EXNESS_MOCK_SPECS.get(symbol)
        if spec:
            self._price_offsets[symbol] = self._price_offsets.get(symbol, 0.0) + delta
