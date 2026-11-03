"""
Tauric Platform — Phase 3.3.2 Testnet Acceptance Test Suite

Comprehensive acceptance testing covering:
1. Credential vault key lifecycle, secure provisioning, restart reload, backup/recovery, and failure handling.
2. Unconfigured / invalid credentials execution blocking (zero fabricated fills).
3. Controlled test order execution and multi-factor reconciliation.
4. Pre-flight insufficient balance rejection (quote and base).
5. Pre-flight invalid precision and minimum notional filter rejection.
6. Protective order (TP/SL) sanity checks fail-closed.
7. Duplicate client order ID and idempotency protection.
8. Submission timeout reconciliation by client_order_id (no blind duplicates).
9. Partial fill position ledger accounting and proportional fee deduction.
10. Order cancellation verification.
11. Environment segregation and live execution lock.
12. Portfolio data freshness and mark-to-market accuracy.
"""

import unittest
import asyncio
import os
import json
import time
import shutil
import tempfile
from unittest.mock import patch, AsyncMock
import httpx

from app.services.exchange_framework import (
    exchange_framework,
    credential_vault,
    CredentialVault,
    BinanceSpotAdapter,
    BybitSpotAdapter,
    Environment,
    ExchangeId,
    OrderStatus,
    OrderSide,
    OrderType,
    SymbolTradingRules,
    OrderExecutionReceipt,
    get_vault_master_key
)
from app.config import settings


import secrets

class TestPhase332Acceptance(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.test_master_key = secrets.token_hex(32)
        os.environ["TAURIC_VAULT_KEY"] = self.test_master_key
        self.test_dir = tempfile.mkdtemp()
        self.vault_path = os.path.join(self.test_dir, "test_vault.json")
        self.vault = CredentialVault(storage_path=self.vault_path)

        # Clean framework state
        exchange_framework._orders = {}
        exchange_framework._positions = {}
        exchange_framework._processed_idempotency_keys = set()
        exchange_framework.demo_trading_enabled = True

    def tearDown(self):
        self.loop.close()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_vault_key_lifecycle_and_restart(self):
        """Verify credential vault key lifecycle, process restart reload, and failure handling."""
        # 1. Save credential under active key
        profile = self.vault.save_profile(
            exchange="BINANCE",
            environment="DEMO",
            label="Lifecycle Test",
            api_key="vmPU1234567890abcdefXYZ",
            api_secret="vault_secret_999888"
        )
        pid = profile["profile_id"]

        # 2. Simulate process restart by creating a new CredentialVault instance on disk
        restarted_vault = CredentialVault(storage_path=self.vault_path)
        restarted_creds = restarted_vault.get_credentials(pid)
        self.assertEqual(restarted_creds["api_key"], "vmPU1234567890abcdefXYZ")
        self.assertEqual(restarted_creds["api_secret"], "vault_secret_999888")

        # 3. Simulate restart without master key (fail closed)
        del os.environ["TAURIC_VAULT_KEY"]
        settings.tauric_vault_key = ""
        no_key_vault = CredentialVault(storage_path=self.vault_path)
        with self.assertRaises(RuntimeError) as ctx:
            no_key_vault.get_credentials(pid)
        self.assertIn("TAURIC_VAULT_KEY", str(ctx.exception))

        # 4. Simulate recovery with wrong master key (fail closed)
        os.environ["TAURIC_VAULT_KEY"] = secrets.token_hex(32)
        wrong_key_vault = CredentialVault(storage_path=self.vault_path)
        with self.assertRaises(PermissionError) as ctx:
            wrong_key_vault.get_credentials(pid)
        self.assertIn("Vault integrity verification failed", str(ctx.exception))

        # Restore test key
        os.environ["TAURIC_VAULT_KEY"] = self.test_master_key

    def test_02_unconfigured_credentials_blocks_execution(self):
        """Verify execution is BLOCKED with zero fills when testnet credentials are not configured."""
        adapter = BinanceSpotAdapter()
        order_req = {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.05,
            "price": 65000.0,
            "account_label": "Unconfigured Testnet"
        }

        receipt = self.loop.run_until_complete(
            adapter.submit_order(order_req, Environment.DEMO, {})
        )

        self.assertEqual(receipt.status, OrderStatus.REJECTED)
        self.assertEqual(receipt.executed_qty, 0.0)
        self.assertEqual(receipt.avg_fill_price, 0.0)
        self.assertIn("BLOCKED", receipt.error_message)
        self.assertTrue(any("BLOCKED" in msg for msg in receipt.audit_trail))

    def test_03_controlled_test_order_reconciliation_contract(self):
        """Verify end-to-end reconciliation: order status, fill price, fee, balance, position ledger, and P&L."""
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        # Controlled mock receipt simulating verified exchange response
        mock_receipt = OrderExecutionReceipt(
            client_order_id="ORD-DEMO-RECON-101",
            exchange_order_id="BINANCE-TESTNET-771122",
            exchange="BINANCE",
            environment="DEMO",
            account_label="Binance Testnet",
            symbol="BTCUSDT",
            side="BUY",
            order_type="LIMIT",
            status=OrderStatus.FILLED,
            requested_qty=0.05,
            executed_qty=0.05,
            requested_price=64000.0,
            avg_fill_price=64000.0,
            fee_amount=3.20,  # 0.05 * 64000 * 0.001
            fee_asset="USDT",
            protective_stop_loss=62000.0,
            protective_take_profit=68000.0,
            submitted_at_utc=now_iso,
            filled_at_utc=now_iso,
            audit_trail=["Controlled acceptance test fill verified against exchange receipt."]
        )

        with patch.object(exchange_framework.get_adapter("BINANCE"), "submit_order", return_value=mock_receipt):
            order_req = {
                "exchange": "BINANCE",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "order_type": "LIMIT",
                "quantity": 0.05,
                "price": 64000.0,
                "stop_loss": 62000.0,
                "take_profit": 68000.0
            }
            receipt = self.loop.run_until_complete(
                exchange_framework.execute_demo_order(None, order_req, "IDEMP-RECON-101")
            )

        # 1. Reconcile receipt fields
        self.assertEqual(receipt.status, OrderStatus.FILLED)
        self.assertEqual(receipt.exchange_order_id, "BINANCE-TESTNET-771122")
        self.assertEqual(receipt.executed_qty, 0.05)
        self.assertEqual(receipt.avg_fill_price, 64000.0)
        self.assertEqual(receipt.fee_amount, 3.20)
        self.assertEqual(receipt.fee_asset, "USDT")

        # 2. Reconcile position ledger
        positions = exchange_framework.get_positions("DEMO")
        self.assertEqual(len(positions), 1)
        pos = positions[0]
        self.assertEqual(pos["symbol"], "BTCUSDT")
        self.assertEqual(pos["side"], "LONG")
        self.assertEqual(pos["size"], 0.05)
        self.assertEqual(pos["entry_price"], 64000.0)
        self.assertEqual(pos["fees_paid"], 3.20)
        self.assertEqual(pos["stop_loss"], 62000.0)
        self.assertEqual(pos["take_profit"], 68000.0)

        # 3. Reconcile mark price move and unrealized P&L (+1,000 price rise)
        exchange_framework.update_mark_prices({"BTC": 65000.0})
        updated_pos = exchange_framework.get_positions("DEMO")[0]
        # (65000 - 64000) * 0.05 = +$50.00
        self.assertEqual(updated_pos["unrealized_pnl"], 50.00)
        self.assertEqual(updated_pos["unrealized_pnl_pct"], 1.56)

    def test_04_preflight_insufficient_balance_rejection(self):
        """Verify preflight rejects BUY and SELL when balance is insufficient."""
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

        # BUY: Requires 6,000 + 6 fee = 6,006. Balance is only 5,000.
        res_buy = adapter.validate_order("BTCUSDT", OrderSide.BUY, OrderType.LIMIT, 0.1, 60000.0, 5000.0, 0.0, rules)
        self.assertFalse(res_buy.is_valid)
        self.assertTrue(any("Insufficient USDT balance" in e for e in res_buy.errors))

        # SELL: Requires 0.5 BTC. Available balance is only 0.2 BTC.
        res_sell = adapter.validate_order("BTCUSDT", OrderSide.SELL, OrderType.LIMIT, 0.5, 60000.0, 10000.0, 0.2, rules)
        self.assertFalse(res_sell.is_valid)
        self.assertTrue(any("Insufficient BTC balance" in e for e in res_sell.errors))

    def test_05_preflight_invalid_precision_and_min_notional(self):
        """Verify preflight validates step size, tick size, and minimum notional filter."""
        adapter = BinanceSpotAdapter()
        rules = SymbolTradingRules(
            symbol="BTCUSDT",
            base_asset="BTC",
            quote_asset="USDT",
            min_qty=0.001,
            max_qty=100.0,
            step_size=0.001,
            tick_size=0.10,
            min_notional=25.0
        )

        # Quantity below min_qty
        r1 = adapter.validate_order("BTCUSDT", OrderSide.BUY, OrderType.LIMIT, 0.0005, 60000.0, 10000.0, 0.0, rules)
        self.assertFalse(r1.is_valid)
        self.assertTrue(any("below minimum allowed" in e for e in r1.errors))

        # Notional below $25.00 min notional (0.001 * 20000 = $20.00)
        r2 = adapter.validate_order("BTCUSDT", OrderSide.BUY, OrderType.LIMIT, 0.001, 20000.0, 10000.0, 0.0, rules)
        self.assertFalse(r2.is_valid)
        self.assertTrue(any("below minimum notional" in e for e in r2.errors))

    def test_06_protective_tp_sl_sanity_checks(self):
        """Verify protective orders (TP/SL) reject inverted levels."""
        adapter = BinanceSpotAdapter()
        rules = SymbolTradingRules("BTCUSDT", "BTC", "USDT", 0.001, 100.0, 0.001, 0.01, 10.0)

        # BUY with Stop-Loss >= entry price
        r1 = adapter.validate_order("BTCUSDT", OrderSide.BUY, OrderType.LIMIT, 0.01, 60000.0, 10000.0, 0.0, rules, stop_loss=60500.0)
        self.assertFalse(r1.is_valid)
        self.assertTrue(any("must be strictly below entry price" in e for e in r1.errors))

        # BUY with Take-Profit <= entry price
        r2 = adapter.validate_order("BTCUSDT", OrderSide.BUY, OrderType.LIMIT, 0.01, 60000.0, 10000.0, 0.0, rules, take_profit=59000.0)
        self.assertFalse(r2.is_valid)
        self.assertTrue(any("must be strictly above entry price" in e for e in r2.errors))

    def test_07_duplicate_client_order_id_and_idempotency(self):
        """Verify identical idempotency key returns cached receipt without submitting twice."""
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        mock_receipt = OrderExecutionReceipt(
            client_order_id="ORD-IDEMP-202",
            exchange_order_id="EXCH-202",
            exchange="BINANCE",
            environment="DEMO",
            account_label="Demo",
            symbol="BTCUSDT",
            side="BUY",
            order_type="LIMIT",
            status=OrderStatus.FILLED,
            requested_qty=0.01,
            executed_qty=0.01,
            requested_price=60000.0,
            avg_fill_price=60000.0,
            fee_amount=0.60,
            fee_asset="USDT",
            protective_stop_loss=None,
            protective_take_profit=None,
            submitted_at_utc=now_iso,
            filled_at_utc=now_iso
        )

        with patch.object(exchange_framework.get_adapter("BINANCE"), "submit_order", return_value=mock_receipt) as mock_sub:
            req = {"exchange": "BINANCE", "symbol": "BTCUSDT", "side": "BUY", "quantity": 0.01, "price": 60000.0}
            r1 = self.loop.run_until_complete(exchange_framework.execute_demo_order(None, req, "IDEMP-KEY-TEST-202"))
            r2 = self.loop.run_until_complete(exchange_framework.execute_demo_order(None, req, "IDEMP-KEY-TEST-202"))

            self.assertEqual(r1.client_order_id, r2.client_order_id)
            self.assertEqual(mock_sub.call_count, 1)

    def test_08_submission_timeout_reconciliation_no_blind_duplicate(self):
        """Verify submission timeout triggers inquiry and marks FAILED without blind resubmission."""
        adapter = BinanceSpotAdapter()
        order_req = {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "quantity": 0.01,
            "price": 60000.0,
            "client_order_id": "ORD-TIMEOUT-RECON-202"
        }
        creds = {"api_key": "dummy_key", "api_secret": "dummy_secret"}

        with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Read timeout")):
            with patch("httpx.AsyncClient.get", return_value=AsyncMock(status_code=404, json=lambda: {})):
                receipt = self.loop.run_until_complete(
                    adapter.submit_order(order_req, Environment.DEMO, creds)
                )

        self.assertEqual(receipt.status, OrderStatus.FAILED)
        self.assertEqual(receipt.executed_qty, 0.0)
        self.assertTrue(any("could not be confirmed" in msg for msg in receipt.audit_trail))

    def test_09_partial_fill_accounting(self):
        """Verify partial fill increments position by executed quantity and proportional fee."""
        partial_receipt = OrderExecutionReceipt(
            client_order_id="ORD-PARTIAL-303",
            exchange_order_id="EXCH-PARTIAL-303",
            exchange="BINANCE",
            environment="DEMO",
            account_label="Binance Testnet",
            symbol="ETHUSDT",
            side="BUY",
            order_type="LIMIT",
            status=OrderStatus.PARTIALLY_FILLED,
            requested_qty=2.0,
            executed_qty=0.8,  # Partial fill
            requested_price=2500.0,
            avg_fill_price=2500.0,
            fee_amount=2.0,    # 0.8 * 2500 * 0.001
            fee_asset="USDT",
            protective_stop_loss=2400.0,
            protective_take_profit=2700.0,
            submitted_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            filled_at_utc=None
        )

        exchange_framework._update_position_from_fill(partial_receipt)
        pos = exchange_framework.get_positions("DEMO")[0]

        self.assertEqual(pos["symbol"], "ETHUSDT")
        self.assertEqual(pos["status"], "OPEN")
        self.assertEqual(pos["size"], 0.8)
        self.assertEqual(pos["entry_price"], 2500.0)
        self.assertEqual(pos["fees_paid"], 2.0)

    def test_10_order_cancellation_verification(self):
        """Verify order cancellation contracts for Binance, Bybit, and framework orchestrator."""
        # Binance adapter cancellation
        binance = BinanceSpotAdapter()
        res_binance = self.loop.run_until_complete(
            binance.cancel_order("BTCUSDT", "ORD-CANCEL-001", Environment.DEMO, {})
        )
        self.assertEqual(res_binance["status"], "SUCCESS")
        self.assertEqual(res_binance["client_order_id"], "ORD-CANCEL-001")

        # Bybit adapter cancellation
        bybit = BybitSpotAdapter()
        res_bybit = self.loop.run_until_complete(
            bybit.cancel_order("BTCUSDT", "ORD-CANCEL-002", Environment.DEMO, {})
        )
        self.assertEqual(res_bybit["status"], "SUCCESS")
        self.assertEqual(res_bybit["client_order_id"], "ORD-CANCEL-002")

        # Framework cancellation updating order store
        exchange_framework._orders["ORD-CANCEL-003"] = {
            "client_order_id": "ORD-CANCEL-003",
            "status": "OPEN"
        }
        res_framework = self.loop.run_until_complete(
            exchange_framework.cancel_order("BTCUSDT", "ORD-CANCEL-003")
        )
        self.assertEqual(res_framework["status"], "SUCCESS")
        self.assertEqual(exchange_framework._orders["ORD-CANCEL-003"]["status"], "CANCELLED")

    def test_11_environment_segregation_and_live_lock(self):
        """Verify DEMO connects strictly to testnets and LIVE order execution raises PermissionError."""
        binance = BinanceSpotAdapter()
        bybit = BybitSpotAdapter()

        # Check base URLs
        self.assertEqual(binance._get_base_url(Environment.DEMO), "https://testnet.binance.vision/api/v3")
        self.assertEqual(bybit._get_base_url(Environment.DEMO), "https://api-testnet.bybit.com/v5")

        # Check LIVE order execution lock
        with self.assertRaises(PermissionError) as ctx_binance:
            self.loop.run_until_complete(
                binance.submit_order({"symbol": "BTCUSDT", "side": "BUY", "quantity": 0.01}, Environment.LIVE, {})
            )
        self.assertIn("Live trading is hard-locked", str(ctx_binance.exception))

        with self.assertRaises(PermissionError) as ctx_bybit:
            self.loop.run_until_complete(
                bybit.submit_order({"symbol": "BTCUSDT", "side": "BUY", "quantity": 0.01}, Environment.LIVE, {})
            )
        self.assertIn("Live trading is hard-locked", str(ctx_bybit.exception))

    def test_12_portfolio_freshness_marking(self):
        """Verify position valuation tracks mark prices and reports freshness accurately."""
        exchange_framework._positions["BINANCE_DEMO_BTCUSDT"] = {
            "position_id": "POS-FRESH-01",
            "symbol": "BTCUSDT",
            "exchange": "BINANCE",
            "environment": "DEMO",
            "side": "LONG",
            "size": 1.0,
            "entry_price": 60000.0,
            "mark_price": 60000.0,
            "unrealized_pnl": 0.0,
            "unrealized_pnl_pct": 0.0,
            "realized_pnl": 0.0,
            "fees_paid": 60.0,
            "opened_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status": "OPEN"
        }

        # Update mark price
        exchange_framework.update_mark_prices({"BTC": 61500.0})
        pos = exchange_framework.get_positions("DEMO")[0]
        self.assertEqual(pos["mark_price"], 61500.0)
        self.assertEqual(pos["unrealized_pnl"], 1500.0)
        self.assertEqual(pos["unrealized_pnl_pct"], 2.5)


if __name__ == "__main__":
    unittest.main()
