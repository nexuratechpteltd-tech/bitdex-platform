"""
Exness HFT Services Package (Phase 4.1 Architecture)
"""

from .base_adapter import ExnessBaseAdapter
from .mock_adapter import ExnessDeterministicMockAdapter, EXNESS_MOCK_SPECS
from .mt5_gateway_adapter import ExnessMT5GatewayAdapter
from .trader_api_adapter import ExnessTraderAPIAdapter
from .payments_service import ExnessPaymentsService
from .vault import ExnessCredentialVault
from .exness_db import (
    apply_exness_migrations,
    get_user_exness_connection,
    get_all_user_exness_connections,
    get_user_exness_connection_by_mode,
    disconnect_exness_connection,
    set_preferred_account,
    save_exness_connection,
    create_exness_transfer,
    get_exness_transfer_by_idempotency,
    get_user_exness_transfers,
    update_exness_transfer_status,
)
from .simulation_engine import (
    HFTPairedSimulationEngine,
    QuantitativeRegimeClassifier,
    MarketRegime,
    CostModelConfig,
)
from .risk_guard import ExnessRiskGuard, RiskLimits

__all__ = [
    "ExnessBaseAdapter",
    "ExnessDeterministicMockAdapter",
    "EXNESS_MOCK_SPECS",
    "ExnessMT5GatewayAdapter",
    "ExnessTraderAPIAdapter",
    "ExnessPaymentsService",
    "ExnessCredentialVault",
    "apply_exness_migrations",
    "get_user_exness_connection",
    "get_all_user_exness_connections",
    "get_user_exness_connection_by_mode",
    "disconnect_exness_connection",
    "set_preferred_account",
    "save_exness_connection",
    "create_exness_transfer",
    "get_exness_transfer_by_idempotency",
    "get_user_exness_transfers",
    "update_exness_transfer_status",
    "HFTPairedSimulationEngine",
    "QuantitativeRegimeClassifier",
    "MarketRegime",
    "CostModelConfig",
    "ExnessRiskGuard",
    "RiskLimits",
]
