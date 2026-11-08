"""
BITDEX Universal Multi-Broker Execution Package
===============================================
"""

from .base_contract import AdapterCapabilityMatrix, UniversalBrokerAdapter
from .exness_terminal_adapter import ExnessTerminalBrokerAdapter
from .mt5_broker_adapter import ExnessMT5BrokerAdapter
from .binance_futures_adapter import BinanceFuturesBrokerAdapter
from .strategy_risk_engine import CommonStrategyAndRiskEngine
from .execution_router import CentralExecutionRouter, TenantAccountExecutionContext

__all__ = [
    "AdapterCapabilityMatrix",
    "UniversalBrokerAdapter",
    "ExnessTerminalBrokerAdapter",
    "ExnessMT5BrokerAdapter",
    "BinanceFuturesBrokerAdapter",
    "CommonStrategyAndRiskEngine",
    "CentralExecutionRouter",
    "TenantAccountExecutionContext",
]
