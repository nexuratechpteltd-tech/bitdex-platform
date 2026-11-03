"""
Exness Broker-Independent Adapter Interface
Part of BITDEX Exness High-Frequency Trading (HFT) Architecture.
Specification reference: Master Exness HFT Implementation Specification, Part 4.3.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class ExnessBaseAdapter(ABC):
    """
    Abstract broker-independent adapter interface for Exness MT5 execution.
    All Exness adapters (Deterministic Mock and MT5 Gateway) must strictly implement
    these 18 authoritative methods to guarantee uniform operational behavior.
    """

    @abstractmethod
    async def connect(self) -> Dict[str, Any]:
        """Establish session connection to Exness broker."""
        pass

    @abstractmethod
    async def disconnect(self) -> Dict[str, Any]:
        """Safely terminate session connection."""
        pass

    @abstractmethod
    async def get_account_info(self) -> Dict[str, Any]:
        """
        Retrieves real-time account telemetry:
        balance, equity, margin, free_margin, margin_level, leverage, currency, is_demo.
        """
        pass

    @abstractmethod
    async def get_symbols(self) -> List[str]:
        """Returns list of available symbols from the broker."""
        pass

    @abstractmethod
    async def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Returns full contract specifications for an instrument:
        contract_size, min_volume, max_volume, volume_step, tick_size, tick_value,
        spread, digits, stops_level, margin_initial, is_tradable, trade_mode, sessions.
        """
        pass

    @abstractmethod
    async def get_latest_tick(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Returns current best bid, ask, spread, and timestamp for symbol."""
        pass

    @abstractmethod
    async def get_historical_candles(
        self, symbol: str, timeframe: str = "M1", count: int = 100
    ) -> List[Dict[str, Any]]:
        """Fetches historical OHLCV bars for volatility and regime detection."""
        pass

    @abstractmethod
    async def calculate_margin(
        self, symbol: str, order_type: str, volume: float
    ) -> Dict[str, Any]:
        """
        Calculates required margin, free margin post-trade, and margin level.
        Returns whether the trade is affordable without margin-call risk.
        """
        pass

    @abstractmethod
    async def submit_order(self, order_req: Dict[str, Any]) -> Dict[str, Any]:
        """
        Submits an order to the broker.
        Requires: symbol, order_type (BUY/SELL), volume, idempotency_key.
        Optional: price, sl, tp, comment, magic_number.
        """
        pass

    @abstractmethod
    async def modify_order(
        self, ticket: str, sl: Optional[float] = None, tp: Optional[float] = None
    ) -> Dict[str, Any]:
        """Modifies protective stop-loss and take-profit for an existing position."""
        pass

    @abstractmethod
    async def close_position(
        self, ticket: str, volume: Optional[float] = None
    ) -> Dict[str, Any]:
        """Closes an open position by ticket, optionally with partial volume."""
        pass

    @abstractmethod
    async def close_partial_position(
        self, ticket: str, volume: float
    ) -> Dict[str, Any]:
        """Partially closes an open position with specified volume."""
        pass

    @abstractmethod
    async def get_open_positions(self) -> List[Dict[str, Any]]:
        """
        Retrieves all currently active positions on the broker account:
        ticket, symbol, type, volume, open_price, current_price, sl, tp, commission, swap, profit.
        """
        pass

    @abstractmethod
    async def get_order_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieves historical orders."""
        pass

    @abstractmethod
    async def get_trade_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieves historical completed trades (deals) with realized P&L and fees."""
        pass

    @abstractmethod
    async def reconcile_account(self) -> Dict[str, Any]:
        """
        Performs authoritative broker reconciliation:
        Cross-checks local database basket records with actual broker positions.
        """
        pass

    @abstractmethod
    async def verify_protective_stop(self, ticket: str) -> Dict[str, Any]:
        """
        Verifies whether an exchange/broker-side Stop Loss order is actively registered.
        Returns confirmed status, stop price, and distance in points.
        """
        pass

    @abstractmethod
    async def get_connection_status(self) -> Dict[str, Any]:
        """Returns connection state, latency_ms, last heartbeat, and broker server."""
        pass
