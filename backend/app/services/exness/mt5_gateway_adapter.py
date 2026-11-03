"""
Exness MT5 Production Gateway Adapter (Hardened Phase 2.1)
Connects to MetaTrader 5 execution terminal via dedicated MT5 Gateway / Bridge.
Enforces strict fail-closed security and separates adapter connection from broker authentication.
Specification reference: Master Exness HFT Implementation Specification, Part 4.2 & Part 4.3.
"""

import os
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from .base_adapter import ExnessBaseAdapter

logger = logging.getLogger("bitdex.exness.gateway")


class ExnessMT5GatewayAdapter(ExnessBaseAdapter):
    """
    Exness MT5 Gateway Adapter.
    Communicates with a secure MetaTrader 5 bridge daemon (or MetaTrader5 native IPC).
    Enforces strict safety locks:
    - Default: Live trading is locked (`live_execution_locked = True`).
    - Only demo connections authorized.
    - Gracefully fails closed if MT5 gateway daemon is unreachable.
    - Separates adapter connection from broker authentication.
    """

    def __init__(
        self,
        account_id: str,
        server: str,
        gateway_url: Optional[str] = None,
    ):
        self.account_id = account_id
        self.server = server
        self.gateway_url = gateway_url or os.getenv("EXNESS_MT5_GATEWAY_URL", "http://127.0.0.1:8095")
        self.is_connected = False
        self.broker_authenticated = False
        self.live_execution_locked = True  # Strict safety requirement

    async def connect(self) -> Dict[str, Any]:
        """Attempts connection to the MT5 gateway bridge."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.post(
                    f"{self.gateway_url}/connect",
                    json={"login": self.account_id, "server": self.server},
                )
                if res.status_code == 200:
                    data = res.json()
                    self.is_connected = True
                    self.broker_authenticated = data.get("broker_authenticated", False)
                    return {
                        "status": "CONNECTED" if self.broker_authenticated else "AUTHENTICATION_FAILED",
                        "adapter_connected": True,
                        "broker_authenticated": self.broker_authenticated,
                        "is_mock": False,
                        "broker_mode": "EXNESS_MT5_GATEWAY",
                        "connection_type": "REAL_EXNESS_DEMO",
                        "account_id": self.account_id,
                        "server": self.server,
                        "connected_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    }
        except Exception as e:
            logger.warning(f"MT5 Gateway bridge at {self.gateway_url} is offline or unreachable: {e}")

        # In staging without active Windows MT5 bridge, fail closed safely
        self.is_connected = False
        self.broker_authenticated = False
        return {
            "status": "MT5_TERMINAL_UNAVAILABLE",
            "adapter_connected": False,
            "broker_authenticated": False,
            "is_connected": False,
            "is_mock": False,
            "broker_mode": "EXNESS_MT5_GATEWAY",
            "connection_type": "REAL_EXNESS_DEMO",
            "account_id": self.account_id,
            "server": self.server,
            "gateway_url": self.gateway_url,
            "reason": (
                "Exness MT5 execution terminal is not reachable. Ensure the MT5 Gateway "
                "service or MetaTrader 5 Windows bridge is running."
            ),
            "live_execution_locked": self.live_execution_locked,
            "recommended_action": "Use ExnessDeterministicMockAdapter (use_mock=true) for staging testing until bridge is live.",
        }

    async def disconnect(self) -> Dict[str, Any]:
        self.is_connected = False
        self.broker_authenticated = False
        return {
            "status": "DISCONNECTED",
            "adapter_connected": False,
            "broker_authenticated": False,
            "is_mock": False,
            "broker_mode": "EXNESS_MT5_GATEWAY",
            "account_id": self.account_id,
        }

    async def get_connection_status(self) -> Dict[str, Any]:
        return {
            "is_connected": self.is_connected,
            "adapter_connected": self.is_connected,
            "broker_authenticated": self.broker_authenticated,
            "is_mock": False,
            "broker_mode": "EXNESS_MT5_GATEWAY",
            "connection_type": "REAL_EXNESS_DEMO",
            "broker_server": self.server,
            "account_id": self.account_id,
            "gateway_url": self.gateway_url,
            "live_execution_locked": self.live_execution_locked,
            "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    async def get_account_info(self) -> Dict[str, Any]:
        if not self.is_connected or not self.broker_authenticated:
            raise ConnectionError("MT5 Gateway terminal is disconnected or unauthenticated.")
        return {}

    async def get_symbols(self) -> List[str]:
        if not self.is_connected or not self.broker_authenticated:
            return []
        return []

    async def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        return None

    async def get_latest_tick(self, symbol: str) -> Optional[Dict[str, Any]]:
        return None

    async def get_historical_candles(
        self, symbol: str, timeframe: str = "M1", count: int = 100
    ) -> List[Dict[str, Any]]:
        return []

    async def calculate_margin(
        self, symbol: str, order_type: str, volume: float
    ) -> Dict[str, Any]:
        return {"status": "BLOCKED", "reason": "MT5_GATEWAY_DISCONNECTED"}

    async def submit_order(self, order_req: Dict[str, Any]) -> Dict[str, Any]:
        raise PermissionError(
            "Order submission rejected: Live and gateway execution are strictly disabled in Phase 2.1."
        )

    async def modify_order(
        self, ticket: str, sl: Optional[float] = None, tp: Optional[float] = None
    ) -> Dict[str, Any]:
        raise PermissionError("Order modification rejected: MT5 Gateway terminal is not connected.")

    async def close_position(
        self, ticket: str, volume: Optional[float] = None
    ) -> Dict[str, Any]:
        raise PermissionError("Position close rejected: MT5 Gateway terminal is not connected.")

    async def close_partial_position(
        self, ticket: str, volume: float
    ) -> Dict[str, Any]:
        raise PermissionError("Partial close rejected: MT5 Gateway terminal is not connected.")

    async def get_open_positions(self) -> List[Dict[str, Any]]:
        return []

    async def get_order_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        return []

    async def get_trade_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        return []

    async def verify_protective_stop(self, ticket: str) -> Dict[str, Any]:
        return {"broker_stop_active": False, "reason": "MT5_GATEWAY_DISCONNECTED"}

    async def reconcile_account(
        self, local_positions: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        return {
            "status": "BROKER_UNAVAILABLE",
            "reconciliation_source": "AUTHORITATIVE_BROKER",
            "is_mock": False,
            "account_id": self.account_id,
            "discrepancy_count": 0,
            "broker_positions_count": 0,
            "local_positions_count": len(local_positions) if local_positions else 0,
            "reason": "MT5 Gateway execution terminal is disconnected or unavailable.",
            "reconciled_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
