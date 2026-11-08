"""
BITDEX Universal Broker Execution Contract (Section 1)
======================================================
Defines the common internal execution interface (`UniversalBrokerAdapter`) and
capability matrix (`AdapterCapabilityMatrix`) implemented by all BITDEX-managed
broker adapters:
- `ExnessMT5BrokerAdapter` (Exness MT5 accounts via BITDEX-managed MT5 Gateway)
- `ExnessTerminalBrokerAdapter` (Exness Terminal / DXtrade accounts via official Exness Public Trader API v1.0.2)
- `BinanceFuturesBrokerAdapter` (Binance USD-M Futures accounts via REST/WS API)

The BITDEX strategy engine, risk management framework, and customer portal interact
exclusively with this universal contract and `CentralExecutionRouter`, never with
MT5-specific APIs.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional


@dataclass
class AdapterCapabilityMatrix:
    """Explicitly declares which of the 14 universal trading lifecycle capabilities an adapter supports."""
    authenticate_account: bool = True
    verify_ownership_and_environment: bool = True
    account_balance_equity_margin: bool = True
    supported_instruments_and_specs: bool = True
    live_quotes_and_market_data: bool = True
    open_positions: bool = True
    order_history: bool = True
    place_market_orders: bool = True
    attach_sl_tp: bool = True
    modify_orders: bool = True
    close_individual_positions: bool = True
    close_all_positions: bool = True
    commissions_swaps_and_pnl: bool = True
    reconcile_positions_and_orders: bool = True

    def is_full_lifecycle_supported(self) -> bool:
        return all([
            self.authenticate_account,
            self.verify_ownership_and_environment,
            self.account_balance_equity_margin,
            self.supported_instruments_and_specs,
            self.live_quotes_and_market_data,
            self.open_positions,
            self.order_history,
            self.place_market_orders,
            self.attach_sl_tp,
            self.modify_orders,
            self.close_individual_positions,
            self.close_all_positions,
            self.commissions_swaps_and_pnl,
            self.reconcile_positions_and_orders,
        ])

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["full_lifecycle_supported"] = self.is_full_lifecycle_supported()
        return d


class UniversalBrokerAdapter(ABC):
    """
    Common internal execution contract for all BITDEX-managed broker integrations.
    Every adapter is instantiated with strict tenant ownership binding (`owner_user_id`, `connection_id`, `account_id`).
    """

    def __init__(
        self,
        owner_user_id: str,
        connection_id: str,
        account_id: str,
        broker_name: str,
        trading_platform: str,
        environment: str,
        server_name: str,
    ):
        self.owner_user_id = str(owner_user_id).strip()
        self.connection_id = str(connection_id).strip()
        self.account_id = str(account_id).strip()
        self.broker_name = str(broker_name).strip().upper()
        self.trading_platform = str(trading_platform).strip().upper()
        self.environment = str(environment).strip().upper()
        self.server_name = str(server_name).strip()
        self.real_execution_locked = True  # Permanent lock on REAL accounts

    @property
    @abstractmethod
    def adapter_name(self) -> str:
        """Canonical adapter class identifier."""
        pass

    @abstractmethod
    def get_capabilities(self) -> AdapterCapabilityMatrix:
        """Returns the 14-point capability matrix for this broker adapter."""
        pass

    # 1. Authenticate broker account
    @abstractmethod
    async def authenticate_account(self) -> Dict[str, Any]:
        pass

    # 2. Verify account ownership and environment
    async def verify_ownership_and_environment(self, authenticated_user_id: str) -> Dict[str, Any]:
        req_user = str(authenticated_user_id or "").strip()
        if not req_user or req_user != self.owner_user_id:
            raise PermissionError(
                f"TENANT_ISOLATION_VIOLATION: Account {self.account_id} does not belong to user {req_user}."
            )
        is_demo = self.environment == "DEMO"
        is_real = self.environment == "REAL"
        return {
            "verified": True,
            "owner_user_id": self.owner_user_id,
            "connection_id": self.connection_id,
            "account_id": self.account_id,
            "broker": self.broker_name,
            "trading_platform": self.trading_platform,
            "environment": self.environment,
            "is_demo": is_demo,
            "is_real": is_real,
            "real_execution_locked": True,
            "execution_permitted_by_environment": is_demo,
        }

    # 3. Retrieve account balance, equity and available margin
    @abstractmethod
    async def get_account_summary(self, force_refresh: bool = False) -> Dict[str, Any]:
        pass

    # 4. Retrieve supported instruments & specifications
    @abstractmethod
    async def get_supported_instruments(self) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    async def get_instrument_specification(self, symbol: str) -> Dict[str, Any]:
        pass

    # 5. Retrieve live quotes and market data
    @abstractmethod
    async def get_live_quote(self, symbol: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def get_historical_candles(
        self, symbol: str, timeframe: str = "M1", count: int = 100
    ) -> List[Dict[str, Any]]:
        pass

    # 6. Retrieve open positions
    @abstractmethod
    async def get_open_positions(self) -> List[Dict[str, Any]]:
        pass

    # 7. Retrieve order history
    @abstractmethod
    async def get_order_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        pass

    # 8. Place market orders
    @abstractmethod
    async def place_market_order(
        self,
        symbol: str,
        side: str,
        volume: float,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        comment: str = "BITDEX-SCALP",
        idempotency_key: Optional[str] = None,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        pass

    # 9. Attach stop-loss and take-profit
    @abstractmethod
    async def attach_sl_tp(
        self,
        position_id: str,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        symbol: str = "BTCUSD",
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        pass

    # 10. Modify orders where supported
    @abstractmethod
    async def modify_order(
        self,
        order_id: str,
        price: Optional[float] = None,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        symbol: str = "BTCUSD",
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        pass

    # 11. Close individual positions
    @abstractmethod
    async def close_position(
        self, position_id: str, volume: Optional[float] = None, dry_run: bool = True
    ) -> Dict[str, Any]:
        pass

    # 12. Close all positions
    @abstractmethod
    async def close_all_positions(
        self, symbol: Optional[str] = None, dry_run: bool = True
    ) -> Dict[str, Any]:
        pass

    # 13. Retrieve actual commissions, swaps and realised P&L
    @abstractmethod
    async def get_commissions_swaps_and_pnl(self, limit: int = 100) -> Dict[str, Any]:
        pass

    # 14. Reconcile order and position status
    @abstractmethod
    async def reconcile_positions_and_orders(
        self, local_positions: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        pass

    # Execution Readiness Check
    @abstractmethod
    async def check_execution_readiness(self) -> Dict[str, Any]:
        pass
