"""
Tauric Platform — Phase 3.3 Exchange Framework Test Suite
Covers:
- Adapter contracts & capability matrix
- Credential vault masking & encryption
- Order sizing, precision (step/tick), and min notional validation
- Insufficient balance rejection
- Fail-closed risk gates: stale data, illiquidity, expired validity, unqualified setup, blackout
- Live trading hard-lock enforcement (PermissionError / 403 Forbidden)
- Demo execution lifecycle, idempotency key protection, and immutable execution receipts
- Position tracking, mark-to-market live P&L, position close, and realized P&L
"""

import unittest
import asyncio
import os
import json
import time
from typing import Dict, Any

from app.services.exchange_framework import (
    exchange_framework,
    credential_vault,
    BinanceSpotAdapter,
    BybitSpotAdapter,
    Environment,
    ExchangeId,
    OrderStatus,
    OrderSide,
    OrderType,
    SymbolTradingRules,
    OrderExecutionReceipt
)
from app.config import settings


import tempfile
import shutil

class TestPhase33ExecutionFramework(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        # Configure test master vault key
        import secrets
        self._orig_env_key = os.environ.get("TAURIC_VAULT_KEY")
        os.environ["TAURIC_VAULT_KEY"] = secrets.token_hex(32)
        self._orig_vault_storage = credential_vault.storage_path
        self.test_dir = tempfile.mkdtemp()
        credential_vault.storage_path = os.path.join(self.test_dir, "test_vault.json")
        credential_vault._profiles = {}

        # Use clean stores for testing
        exchange_framework._orders = {}
        exchange_framework._positions = {}
        exchange_framework._processed_idempotency_keys = set()
        exchange_framework.demo_trading_enabled = True

        # Attach mock adapter submit to allow testing framework lifecycle
        self._orig_binance_submit = exchange_framework.get_adapter("BINANCE").submit_order

        async def mock_submit(order_request, environment, credentials):
            now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            qty = order_request["quantity"]
            price = order_request.get("price", 65000.0)
            return OrderExecutionReceipt(
                client_order_id=order_request["client_order_id"],
                exchange_order_id="EXCH-TESTNET-999",
                exchange=order_request.get("exchange", "BINANCE"),
                environment=environment.value,
                account_label=order_request.get("account_label", "Demo Profile"),
                symbol=order_request["symbol"],
                side=order_request["side"],
                order_type=order_request.get("order_type", "LIMIT"),
                status=OrderStatus.FILLED,
                requested_qty=qty,
                executed_qty=qty,
                requested_price=price,
                avg_fill_price=price,
                fee_amount=round(qty * price * 0.001, 4),
                fee_asset="USDT",
                protective_stop_loss=order_request.get("stop_loss"),
                protective_take_profit=order_request.get("take_profit"),
                submitted_at_utc=now_iso,
                filled_at_utc=now_iso,
                audit_trail=["Mock testnet order fill verified."]
            )
        exchange_framework.get_adapter("BINANCE").submit_order = mock_submit

    def tearDown(self):
        exchange_framework.get_adapter("BINANCE").submit_order = self._orig_binance_submit
        self.loop.close()
        credential_vault.storage_path = self._orig_vault_storage
        if self._orig_env_key is not None:
            os.environ["TAURIC_VAULT_KEY"] = self._orig_env_key
        else:
            os.environ.pop("TAURIC_VAULT_KEY", None)
        credential_vault._profiles = {}
        if os.path.exists(credential_vault.storage_path):
            credential_vault._load()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_adapter_contract_and_capabilities(self):
        """Verify capability registry separates Demo vs Live capabilities."""
        binance = BinanceSpotAdapter()
        bybit = BybitSpotAdapter()

        demo_caps_binance = binance.get_capabilities(Environment.DEMO)
        live_caps_binance = binance.get_capabilities(Environment.LIVE)

        self.assertIn("TESTNET_DEMO", [c.value for c in demo_caps_binance])
        self.assertNotIn("TESTNET_DEMO", [c.value for c in live_caps_binance])
        self.assertIn("LIVE_TRADING", [c.value for c in live_caps_binance])
        self.assertNotIn("LIVE_TRADING", [c.value for c in demo_caps_binance])

        # Bybit capabilities
        demo_caps_bybit = bybit.get_capabilities(Environment.DEMO)
        self.assertIn("SPOT_TRADING", [c.value for c in demo_caps_bybit])
        self.assertIn("TESTNET_DEMO", [c.value for c in demo_caps_bybit])

    def test_02_credential_vault_masking_and_encryption(self):
        """Verify API keys are masked and secrets are never returned in public profiles."""
        profile = credential_vault.save_profile(
            exchange="BINANCE",
            environment="DEMO",
            label="Testnet Key",
            api_key="vmPU1234567890abcdefXYZ",
            api_secret="very_secret_private_key_abc_123"
        )

        self.assertIn("vmPU••••••••fXYZ", profile["api_key_masked"])
        self.assertNotIn("api_secret", profile)
        self.assertNotIn("_api_secret_enc", profile)

        # Retrieve decrypted internal credentials
        creds = credential_vault.get_credentials(profile["profile_id"])
        self.assertEqual(creds["api_key"], "vmPU1234567890abcdefXYZ")
        self.assertEqual(creds["api_secret"], "very_secret_private_key_abc_123")

        # Cleanup
        credential_vault.delete_profile(profile["profile_id"])

    def test_03_order_validation_tick_and_step_precision(self):
        """Verify quantity step and price tick snapping."""
        adapter = BinanceSpotAdapter()
        rules = SymbolTradingRules(
            symbol="BTCUSDT",
            base_asset="BTC",
            quote_asset="USDT",
            min_qty=0.001,
            max_qty=100.0,
            step_size=0.001,
            tick_size=0.10,
            min_notional=10.0
        )

        res = adapter.validate_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.01567,   # Should snap to 0.016
            price=65123.456,    # Should snap to 65123.50
            quote_balance=10000.0,
            base_balance=0.0,
            rules=rules
        )

        self.assertTrue(res.is_valid)
        self.assertEqual(res.normalized_qty, 0.016)
        self.assertEqual(res.normalized_price, 65123.50)

    def test_04_order_validation_insufficient_balance(self):
        """Verify order is rejected when balance cannot cover notional + fee."""
        adapter = BinanceSpotAdapter()
        rules = SymbolTradingRules(
            symbol="BTCUSDT",
            base_asset="BTC",
            quote_asset="USDT",
            min_qty=0.001,
            max_qty=100.0,
            step_size=0.001,
            tick_size=0.01,
            min_notional=10.0
        )

        # Buying 0.1 BTC at $60,000 requires $6,000 + $6 fee = $6,006
        res = adapter.validate_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.1,
            price=60000.0,
            quote_balance=2500.0,  # Insufficient
            base_balance=0.0,
            rules=rules
        )

        self.assertFalse(res.is_valid)
        self.assertTrue(any("Insufficient USDT balance" in err for err in res.errors))

    def test_05_order_validation_min_notional(self):
        """Verify order below minimum notional is rejected."""
        adapter = BinanceSpotAdapter()
        rules = SymbolTradingRules(
            symbol="BTCUSDT",
            base_asset="BTC",
            quote_asset="USDT",
            min_qty=0.0001,
            max_qty=100.0,
            step_size=0.0001,
            tick_size=0.01,
            min_notional=10.0
        )

        # 0.0001 BTC at $50,000 = $5.00 < $10.00 min notional
        res = adapter.validate_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.0001,
            price=50000.0,
            quote_balance=1000.0,
            base_balance=0.0,
            rules=rules
        )

        self.assertFalse(res.is_valid)
        self.assertTrue(any("below minimum notional" in err for err in res.errors))

    def test_06_order_validation_stale_data_fails_closed(self):
        """Verify stale market data fails closed."""
        adapter = BinanceSpotAdapter()
        rules = SymbolTradingRules(
            symbol="ETHUSDT",
            base_asset="ETH",
            quote_asset="USDT",
            min_qty=0.01,
            max_qty=1000.0,
            step_size=0.01,
            tick_size=0.01,
            min_notional=10.0
        )

        res = adapter.validate_order(
            symbol="ETHUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1.0,
            price=2500.0,
            quote_balance=5000.0,
            base_balance=0.0,
            rules=rules,
            freshness_status="STALE"
        )

        self.assertFalse(res.is_valid)
        self.assertTrue(any("Market data is not fresh" in err for err in res.errors))

    def test_07_order_validation_liquidity_unqualified_fails_closed(self):
        """Verify unqualified liquidity fails closed."""
        adapter = BinanceSpotAdapter()
        rules = SymbolTradingRules(
            symbol="ETHUSDT",
            base_asset="ETH",
            quote_asset="USDT",
            min_qty=0.01,
            max_qty=1000.0,
            step_size=0.01,
            tick_size=0.01,
            min_notional=10.0
        )

        res = adapter.validate_order(
            symbol="ETHUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1.0,
            price=2500.0,
            quote_balance=5000.0,
            base_balance=0.0,
            rules=rules,
            liquidity_status="ILLIQUID"
        )

        self.assertFalse(res.is_valid)
        self.assertTrue(any("Market liquidity is not qualified" in err for err in res.errors))

    def test_08_order_validation_expired_entry_validity(self):
        """Verify expired setup window fails closed."""
        adapter = BinanceSpotAdapter()
        rules = SymbolTradingRules(
            symbol="ETHUSDT",
            base_asset="ETH",
            quote_asset="USDT",
            min_qty=0.01,
            max_qty=1000.0,
            step_size=0.01,
            tick_size=0.01,
            min_notional=10.0
        )

        res = adapter.validate_order(
            symbol="ETHUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1.0,
            price=2500.0,
            quote_balance=5000.0,
            base_balance=0.0,
            rules=rules,
            entry_validity_sec=0
        )

        self.assertFalse(res.is_valid)
        self.assertTrue(any("entry validity window has expired" in err for err in res.errors))

    def test_09_order_validation_unqualified_setup(self):
        """Verify unqualified trade setup fails closed."""
        adapter = BinanceSpotAdapter()
        rules = SymbolTradingRules(
            symbol="ETHUSDT",
            base_asset="ETH",
            quote_asset="USDT",
            min_qty=0.01,
            max_qty=1000.0,
            step_size=0.01,
            tick_size=0.01,
            min_notional=10.0
        )

        res = adapter.validate_order(
            symbol="ETHUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1.0,
            price=2500.0,
            quote_balance=5000.0,
            base_balance=0.0,
            rules=rules,
            setup_qualified=False
        )

        self.assertFalse(res.is_valid)
        self.assertTrue(any("Technical trade setup is not qualified" in err for err in res.errors))

    def test_10_order_validation_event_blackout(self):
        """Verify active event blackout blocks execution."""
        adapter = BinanceSpotAdapter()
        rules = SymbolTradingRules(
            symbol="ETHUSDT",
            base_asset="ETH",
            quote_asset="USDT",
            min_qty=0.01,
            max_qty=1000.0,
            step_size=0.01,
            tick_size=0.01,
            min_notional=10.0
        )

        res = adapter.validate_order(
            symbol="ETHUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1.0,
            price=2500.0,
            quote_balance=5000.0,
            base_balance=0.0,
            rules=rules,
            is_blackout=True
        )

        self.assertFalse(res.is_valid)
        self.assertTrue(any("event blackout window" in err for err in res.errors))

    def test_11_live_trading_hard_locked(self):
        """Verify submitting to LIVE environment raises PermissionError."""
        adapter = BinanceSpotAdapter()
        order_req = {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "quantity": 0.01,
            "price": 60000.0
        }

        with self.assertRaises(PermissionError) as ctx:
            self.loop.run_until_complete(adapter.submit_order(order_req, Environment.LIVE, {}))
        self.assertIn("Live trading is hard-locked", str(ctx.exception))

    def test_12_demo_execution_lifecycle_and_receipt(self):
        """Verify demo execution lifecycle produces verified execution receipt."""
        order_req = {
            "exchange": "BINANCE",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.05,
            "price": 65000.0,
            "stop_loss": 63500.0,
            "take_profit": 68000.0,
            "account_label": "Demo Profile"
        }

        receipt = self.loop.run_until_complete(
            exchange_framework.execute_demo_order(
                profile_id=None,
                order_request=order_req,
                idempotency_key="IDEMP-DEMO-001"
            )
        )

        self.assertEqual(receipt.status, OrderStatus.FILLED)
        self.assertTrue(receipt.client_order_id.startswith("ORD-DEMO-"))
        self.assertEqual(receipt.executed_qty, 0.05)
        self.assertEqual(receipt.avg_fill_price, 65000.0)
        self.assertEqual(receipt.fee_amount, 3.25)  # 0.05 * 65000 * 0.001
        self.assertEqual(receipt.protective_stop_loss, 63500.0)
        self.assertEqual(receipt.protective_take_profit, 68000.0)

    def test_13_idempotency_duplicate_submission_protection(self):
        """Verify identical idempotency key returns existing receipt without duplicate fill."""
        order_req = {
            "exchange": "BINANCE",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "quantity": 0.01,
            "price": 60000.0
        }

        r1 = self.loop.run_until_complete(
            exchange_framework.execute_demo_order(None, order_req, "IDEMP-DUPLICATE-KEY-999")
        )
        r2 = self.loop.run_until_complete(
            exchange_framework.execute_demo_order(None, order_req, "IDEMP-DUPLICATE-KEY-999")
        )

        self.assertEqual(r1.client_order_id, r2.client_order_id)
        # Should only have one order stored
        self.assertEqual(len(exchange_framework._orders), 1)

    def test_14_position_tracking_and_live_pnl(self):
        """Verify position tracking and mark-to-market unrealized P&L calculation."""
        order_req = {
            "exchange": "BINANCE",
            "symbol": "ETHUSDT",
            "side": "BUY",
            "quantity": 2.0,
            "price": 2500.0,
            "stop_loss": 2400.0,
            "take_profit": 2700.0
        }

        receipt = self.loop.run_until_complete(
            exchange_framework.execute_demo_order(None, order_req, "IDEMP-POS-TEST-1")
        )
        self.assertEqual(receipt.status, OrderStatus.FILLED)

        # Mark price moves up from 2500 to 2600 (+100 per ETH = +$200 PnL)
        exchange_framework.update_mark_prices({"ETH": 2600.0})
        positions = exchange_framework.get_positions("DEMO")
        self.assertEqual(len(positions), 1)
        pos = positions[0]
        self.assertEqual(pos["symbol"], "ETHUSDT")
        self.assertEqual(pos["unrealized_pnl"], 200.0)
        self.assertEqual(pos["unrealized_pnl_pct"], 4.0)

    def test_15_position_close_and_realized_pnl(self):
        """Verify closing position calculates realized P&L and marks position CLOSED."""
        # 1. Open Long 1.0 BTC at 60,000
        open_req = {
            "exchange": "BINANCE",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "quantity": 1.0,
            "price": 60000.0
        }
        self.loop.run_until_complete(
            exchange_framework.execute_demo_order(None, open_req, "IDEMP-CLOSE-01")
        )

        # 2. Close Long by Selling 1.0 BTC at 62,000 (+2,000 gain)
        close_req = {
            "exchange": "BINANCE",
            "symbol": "BTCUSDT",
            "side": "SELL",
            "quantity": 1.0,
            "price": 62000.0
        }
        self.loop.run_until_complete(
            exchange_framework.execute_demo_order(None, close_req, "IDEMP-CLOSE-02")
        )

        positions = exchange_framework.get_positions("DEMO")
        btc_pos = [p for p in positions if p["symbol"] == "BTCUSDT"][0]
        self.assertEqual(btc_pos["status"], "CLOSED")
        self.assertEqual(btc_pos["size"], 0.0)
        # Realized PnL: $2,000 gross gain - $62 exit fee = $1,938.00
        self.assertEqual(btc_pos["realized_pnl"], 1938.0)


if __name__ == "__main__":
    unittest.main()
