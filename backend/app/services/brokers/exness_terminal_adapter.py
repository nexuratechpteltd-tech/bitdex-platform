"""
BITDEX Exness Terminal / DXtrade Broker Adapter (Section 2)
===========================================================
Implements `UniversalBrokerAdapter` for Exness Terminal (`EXNESS_TERMINAL`, stream `dx.2.trial.std`)
accounts using the officially supported Exness Public Trader API v1.0.2 (`trading.public.yaml`)
over BITDEX-managed cloud execution infrastructure.

Verified official capabilities on `https://ap-58ee8e27.exness.com`:
1. Host discovery (`GET /v1/trading/access-point?account_id=...`) & Ed25519 authentication
2. Account configuration (`GET /v1/configuration/accounts/{id}/account`) & rate limits (`/limits`)
3. Real-time account state snapshot (`GET /v1/trading/accounts/{id}/snapshot` -> balance, equity, used_margin, free_margin)
4. Supported instruments (`GET /v1/configuration/accounts/{id}/instruments`) & conditions (`/instruments/{sym}/conditions`)
5. Live quotes & historical bid/ask candles (`GET /v1/market-data/accounts/{id}/candles` & `WSS /v1/server-events/accounts/{id}/ws/ticks`)
6. Open positions (`GET /v1/trading/accounts/{id}/snapshot`)
7. Order history (`GET /v1/history/accounts/{id}/orders`)
8. Market order placement with SL/TP (`POST /v1/trading/accounts/{id}/positions` + `/operations/{op_id}`)
9. Attach SL/TP (`POST /v1/trading/accounts/{id}/orders` with `type: "sltp"`)
10. Modify orders (`PATCH /v1/trading/accounts/{id}/orders/{order_id}`)
11. Close individual position (`DELETE /v1/trading/accounts/{id}/positions/{position_id}`)
12. Close all positions (batch `DELETE`)
13. Commissions, swaps & realised P&L (`GET /v1/history/accounts/{id}/deals`)
14. Order & position status reconciliation (`/snapshot` + `/operations/{op_id}` + `/deals`)
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .base_contract import AdapterCapabilityMatrix, UniversalBrokerAdapter
from ..exness.trader_api_adapter import ExnessTraderAPIAdapter, normalize_exness_terminal_symbol


class ExnessTerminalBrokerAdapter(UniversalBrokerAdapter):
    """
    BITDEX-managed cloud execution adapter for Exness Terminal / DXtrade accounts.
    Operates 100% natively via the official Exness Public Trader API v1.0.2 without any MT5 dependency.
    """

    def __init__(
        self,
        owner_user_id: str,
        connection_id: str,
        account_id: str,
        api_key: str,
        api_secret: str,
        environment: str = "DEMO",
        server_name: str = "dx.2.trial.std",
        access_point: Optional[str] = None,
        account_tier: str = "STANDARD",
    ):
        super().__init__(
            owner_user_id=owner_user_id,
            connection_id=connection_id,
            account_id=account_id,
            broker_name="EXNESS",
            trading_platform="EXNESS_TERMINAL",
            environment=environment,
            server_name=server_name or "dx.2.trial.std",
        )
        self.client = ExnessTraderAPIAdapter(
            api_key=api_key,
            api_secret=api_secret,
            account_id=account_id,
            environment=environment,
            discovery_base_url="https://api.exness.com",
            account_tier=account_tier,
            access_point=access_point,
        )
        self._event_manager = None

    @property
    def event_manager(self):
        if self._event_manager is None:
            from ..exness.event_stream import ExnessTransactionEventManager
            self._event_manager = ExnessTransactionEventManager(self.client)
        return self._event_manager

    @property
    def adapter_name(self) -> str:
        return "ExnessTerminalBrokerAdapter"

    def get_capabilities(self) -> AdapterCapabilityMatrix:
        return AdapterCapabilityMatrix(
            authenticate_account=True,
            verify_ownership_and_environment=True,
            account_balance_equity_margin=True,
            supported_instruments_and_specs=True,
            live_quotes_and_market_data=True,
            open_positions=True,
            order_history=True,
            place_market_orders=True,
            attach_sl_tp=True,
            modify_orders=True,
            close_individual_positions=True,
            close_all_positions=True,
            commissions_swaps_and_pnl=True,
            reconcile_positions_and_orders=True,
        )

    async def authenticate_account(self) -> Dict[str, Any]:
        ap = await self.client._ensure_access_point()
        cfg = await self.client.get_account_configuration()
        snap = await self.client.get_trading_snapshot()
        settings = cfg.get("settings") or {}
        acct_state = snap.get("account_state") or {}
        authenticated = bool(ap and (cfg.get("account_id") or acct_state.get("balance") is not None))
        return {
            "authenticated": authenticated,
            "adapter": self.adapter_name,
            "broker": self.broker_name,
            "trading_platform": self.trading_platform,
            "account_id": self.account_id,
            "stream_id": cfg.get("stream_id") or self.server_name,
            "access_point": ap,
            "trade_mode": settings.get("trade_mode", "enabled"),
            "account_status": settings.get("account_status", "active"),
            "execution_mode": settings.get("execution_mode", "market"),
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }

    async def get_account_summary(self, force_refresh: bool = False) -> Dict[str, Any]:
        info = await self.client.get_account_info(force_refresh=force_refresh)
        bal_ok = bool(info.get("balance_retrieved"))
        is_demo = bool(info.get("is_demo", self.environment == "DEMO"))
        trade_enabled = str(info.get("trade_mode", "enabled")).lower() == "enabled"
        acct_active = str(info.get("account_status", "active")).lower() == "active"
        exec_ready = bal_ok and is_demo and trade_enabled and acct_active

        return {
            "owner_user_id": self.owner_user_id,
            "connection_id": self.connection_id,
            "account_id": self.account_id,
            "login": self.account_id,
            "broker": self.broker_name,
            "trading_platform": self.trading_platform,
            "adapter": self.adapter_name,
            "environment": "DEMO" if is_demo else "REAL",
            "account_type": "DEMO" if is_demo else "REAL",
            "server": info.get("stream_id") or self.server_name,
            "server_name": info.get("stream_id") or self.server_name,
            "platform": self.trading_platform,
            "stream_id": info.get("stream_id") or self.server_name,
            "currency": info.get("currency", "USD"),
            "balance": info.get("balance"),
            "equity": info.get("equity"),
            "margin": info.get("used_margin", 0.0),
            "used_margin": info.get("used_margin", 0.0),
            "free_margin": info.get("free_margin"),
            "available_margin": info.get("free_margin"),
            "margin_level": info.get("margin_level", 0.0),
            "leverage": info.get("leverage", 2000),
            "open_positions_count": info.get("open_positions_count", 0),
            "open_orders_count": info.get("open_orders_count", 0),
            "api_connected": bal_ok,
            "broker_authenticated": bal_ok,
            "automated_execution_supported": True,
            "automated_execution_verified": exec_ready,
            "execution_readiness_status": (
                "READY_FOR_DEMO_EXECUTION"
                if exec_ready
                else ("REAL_EXECUTION_LOCKED" if not is_demo else "CONNECTION_DEGRADED")
            ),
            "execution_readiness_reason": (
                "Connected & Ready for Automated Demo Execution."
                if exec_ready
                else (
                    "Real-account automated execution is locked for safety."
                    if not is_demo
                    else "Unable to reach broker trading stream."
                )
            ),
            "custody_model": "NON_CUSTODIAL",
            "custodian": "Exness (broker-held funds)",
            "non_custodial_disclosure": (
                "BITDEX is an automated trading software platform. Your trading funds remain in your own Exness brokerage account. "
                "BITDEX does not hold customer deposits or custody customer funds. Trading instructions are sent to your connected "
                "Exness account using authorised API access. Trading involves financial risk."
            ),
            "deposit_withdrawal_route": "Directly in Exness Personal Area (https://my.exness.com/pa/)",
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "data_source": info.get("data_source"),
        }

    async def get_supported_instruments(self) -> List[Dict[str, Any]]:
        featured = [
            ("BTCUSDr", "BTCUSD", "Bitcoin vs US Dollar", "CRYPTO"),
            ("XAUUSDr", "XAUUSD", "Gold vs US Dollar", "METALS"),
            ("EURUSDr", "EURUSD", "Euro vs US Dollar", "FOREX"),
            ("ETHUSDr", "ETHUSD", "Ethereum vs US Dollar", "CRYPTO"),
            ("GBPUSDr", "GBPUSD", "Great Britain Pound vs US Dollar", "FOREX"),
            ("SOLUSDr", "SOLUSD", "Solana vs US Dollar", "CRYPTO"),
        ]
        all_syms = set(await self.client.get_symbols())
        result: List[Dict[str, Any]] = []
        for ui_sym, broker_sym, desc, cat in featured:
            if not all_syms or broker_sym in all_syms:
                spec = await self.client.get_symbol_info(broker_sym) or {}
                result.append({
                    "symbol": ui_sym,
                    "broker_symbol": broker_sym,
                    "canonical_symbol": broker_sym,
                    "display_name": f"{broker_sym[:3]}/{broker_sym[3:]}",
                    "description": spec.get("name", desc),
                    "category": spec.get("category", cat),
                    "digits": spec.get("digits", 2),
                    "contract_size": spec.get("contract_size", 1.0),
                    "min_volume": spec.get("min_volume", 0.01),
                    "max_volume": spec.get("max_volume", 200.0),
                    "volume_step": spec.get("volume_step", 0.01),
                    "is_tradable": spec.get("is_tradable", True),
                    "adapter": self.adapter_name,
                })
        return result

    async def get_instrument_specification(self, symbol: str) -> Dict[str, Any]:
        spec = await self.client.get_symbol_info(symbol)
        if not spec:
            raise ValueError(f"Instrument {symbol} is not supported on {self.server_name}.")
        return spec

    async def get_live_quote(self, symbol: str) -> Dict[str, Any]:
        tick = await self.client.get_latest_tick(symbol)
        if not tick:
            raise RuntimeError(f"Live quote unavailable for {symbol} on {self.server_name}.")
        tick["adapter"] = self.adapter_name
        tick["broker"] = self.broker_name
        tick["trading_platform"] = self.trading_platform
        tick["account_id"] = self.account_id
        return tick

    async def get_historical_candles(
        self, symbol: str, timeframe: str = "M1", count: int = 100
    ) -> List[Dict[str, Any]]:
        return await self.client.get_historical_candles(symbol=symbol, timeframe=timeframe, count=count)

    async def get_open_positions(self) -> List[Dict[str, Any]]:
        return await self.client.get_open_positions()

    async def get_order_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        return await self.client.get_order_history(limit=limit)

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
        if self.environment == "REAL":
            raise PermissionError("REAL_TRADING_PERMANENTLY_LOCKED: Real-account execution is permanently locked.")
        return await self.client.submit_order({
            "symbol": normalize_exness_terminal_symbol(symbol),
            "side": side,
            "volume": volume,
            "sl": sl,
            "tp": tp,
            "comment": comment,
            "idempotency_key": idempotency_key,
            "dry_run": dry_run,
        })

    async def attach_sl_tp(
        self,
        position_id: str,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        symbol: str = "BTCUSD",
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        return await self.client.attach_sl_tp(
            position_id=position_id, sl=sl, tp=tp, symbol=symbol, dry_run=dry_run
        )

    async def modify_order(
        self,
        order_id: str,
        price: Optional[float] = None,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        symbol: str = "BTCUSD",
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        return await self.client.modify_order(
            ticket=order_id, sl=sl, tp=tp, price=price, symbol=symbol, dry_run=dry_run
        )

    def unlock_demo_execution_for_test(self, authorized_account_id: str) -> None:
        if self.environment != 'DEMO':
            raise PermissionError('REAL_TRADING_PERMANENTLY_LOCKED: Real-account execution is permanently locked.')
        if str(self.account_id) != '17000109575' or str(authorized_account_id) != '17000109575':
            raise PermissionError('SAFETY_LOCK: Execution unlock is strictly restricted to Demo account 17000109575.')
        self.client.unlock_demo_execution_for_test(authorized_account_id)

    async def modify_position(
        self,
        position_id: str,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        symbol: str = 'BTCUSD',
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        return await self.client.modify_position(
            position_id=position_id, sl=sl, tp=tp, symbol=symbol, dry_run=dry_run
        )

    async def close_position(
        self, position_id: str, volume: Optional[float] = None, dry_run: bool = True
    ) -> Dict[str, Any]:
        return await self.client.close_position(ticket=position_id, volume=volume, dry_run=dry_run)

    async def close_all_positions(
        self, symbol: Optional[str] = None, dry_run: bool = True
    ) -> Dict[str, Any]:
        return await self.client.close_all_positions(symbol=symbol, dry_run=dry_run)

    async def get_commissions_swaps_and_pnl(self, limit: int = 100) -> Dict[str, Any]:
        deals, positions = await self.client.get_trade_history(limit=limit), await self.client.get_open_positions()
        realized_pnl = 0.0
        total_commission = 0.0
        total_swap = 0.0
        for d in deals:
            prof = d.get("profit")
            if isinstance(prof, dict):
                realized_pnl += float(prof.get("amount", 0.0))
            elif prof is not None:
                realized_pnl += float(prof)
            comm = d.get("commission")
            if isinstance(comm, dict):
                total_commission += float(comm.get("amount", 0.0))
            elif comm is not None:
                total_commission += float(comm)
            sw = d.get("swap")
            if isinstance(sw, dict):
                total_swap += float(sw.get("amount", 0.0))
            elif sw is not None:
                total_swap += float(sw)

        unrealized_pnl = sum(float(p.get("unrealized_pnl", 0.0)) for p in positions)
        open_swap = sum(float(p.get("swap", 0.0)) for p in positions)
        open_comm = sum(float(p.get("commission", 0.0)) for p in positions)

        return {
            "account_id": self.account_id,
            "adapter": self.adapter_name,
            "realized_pnl": round(realized_pnl, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "total_commission": round(total_commission + open_comm, 2),
            "total_swap": round(total_swap + open_swap, 2),
            "net_pnl": round(realized_pnl + unrealized_pnl - abs(total_commission + open_comm) + (total_swap + open_swap), 2),
            "deals_count": len(deals),
            "open_positions_count": len(positions),
            "deals": deals,
        }

    async def reconcile_positions_and_orders(
        self, local_positions: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        return await self.client.reconcile_account(local_positions=local_positions)

    async def check_execution_readiness(self) -> Dict[str, Any]:
        summary = await self.get_account_summary()
        caps = self.get_capabilities()
        is_demo = summary.get("environment") == "DEMO"
        ready = bool(summary.get("automated_execution_verified")) and is_demo
        return {
            "ready": ready,
            "status": summary.get("execution_readiness_status"),
            "reason": summary.get("execution_readiness_reason"),
            "broker": self.broker_name,
            "trading_platform": self.trading_platform,
            "adapter": self.adapter_name,
            "account_id": self.account_id,
            "environment": summary.get("environment"),
            "capabilities": caps.to_dict(),
        }
