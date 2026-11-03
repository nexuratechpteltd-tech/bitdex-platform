"""
Tauric Platform — Phase 3.3.1 Security Hardening & Demo Execution Test Suite

Comprehensive adversarial security and verification suite covering:
1. AES-256-GCM authenticated encryption and decryption.
2. Ciphertext tampering detection (InvalidTag -> PermissionError).
3. Associated Data (AAD) tampering detection.
4. Missing or invalid master vault key fail-closed behavior.
5. Secret leakage audit across public profile endpoints and serialization.
6. Safe migration of legacy XOR credentials to AES-256-GCM.
7. Unconfigured credentials demo execution block (zero fabricated fills).
8. Actual exchange testnet public connectivity & authentication rejection.
9. Timeout reconciliation by client_order_id.
10. Protective order sanity checks (inverted TP/SL rejection).
11. Partial fill position ledger accounting and fee deduction.
12. Balance pre-flight validation fail-closed checks.
13. Deterministic risk gates: stale data, illiquidity, expired validity, blackout.
14. Idempotency duplicate submission prevention.
"""

import unittest
import asyncio
import os
import json
import time
import hashlib
from typing import Dict, Any
from unittest.mock import patch, AsyncMock
import httpx

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
    OrderExecutionReceipt,
    get_vault_master_key
)
from app.config import settings


import secrets
import tempfile
import shutil

class TestPhase331SecurityHardening(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.test_master_key = secrets.token_hex(32)
        self._orig_env_key = os.environ.get("TAURIC_VAULT_KEY")
        os.environ["TAURIC_VAULT_KEY"] = self.test_master_key
        self._orig_vault_storage = credential_vault.storage_path
        self.test_dir = tempfile.mkdtemp()
        credential_vault.storage_path = os.path.join(self.test_dir, "test_vault.json")
        # Clean stores for testing
        exchange_framework._orders = {}
        exchange_framework._positions = {}
        exchange_framework._processed_idempotency_keys = set()
        exchange_framework.demo_trading_enabled = True
        credential_vault._profiles = {}

    def tearDown(self):
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

    def test_01_aes_gcm_authenticated_encryption(self):
        """Verify AES-256-GCM encryption binds ciphertext to AAD and protects secrets."""
        profile = credential_vault.save_profile(
            exchange="BINANCE",
            environment="DEMO",
            label="Binance Testnet Key",
            api_key="vmPU1234567890abcdefXYZ",
            api_secret="very_secret_private_key_abc_123"
        )

        pid = profile["profile_id"]
        stored_raw = credential_vault._profiles[pid]

        # Verify encryption algorithm and payload structure
        self.assertIn("_credentials_enc", stored_raw)
        enc_payload = stored_raw["_credentials_enc"]
        self.assertEqual(enc_payload["cipher"], "AES-256-GCM")
        self.assertEqual(len(bytes.fromhex(enc_payload["nonce"])), 12)  # 96-bit nonce
        self.assertGreater(len(enc_payload["ciphertext"]), 32)

        # Verify plaintext secrets are NOT stored on disk
        self.assertNotIn("_api_key_plain", stored_raw)
        self.assertNotIn("_api_secret_enc", stored_raw)
        self.assertNotIn("api_secret", stored_raw)

        # Retrieve and verify decrypted credentials
        creds = credential_vault.get_credentials(pid)
        self.assertEqual(creds["api_key"], "vmPU1234567890abcdefXYZ")
        self.assertEqual(creds["api_secret"], "very_secret_private_key_abc_123")

    def test_02_ciphertext_tampering_rejected(self):
        """Verify modified ciphertext raises PermissionError due to authentication tag failure."""
        profile = credential_vault.save_profile(
            exchange="BINANCE",
            environment="DEMO",
            label="Tamper Test",
            api_key="vmPU1234567890abcdefXYZ",
            api_secret="original_secret_string"
        )

        pid = profile["profile_id"]
        raw_ct = credential_vault._profiles[pid]["_credentials_enc"]["ciphertext"]

        # Flip the first byte of ciphertext
        tampered_ct = ("00" if raw_ct[:2] != "00" else "ff") + raw_ct[2:]
        credential_vault._profiles[pid]["_credentials_enc"]["ciphertext"] = tampered_ct

        with self.assertRaises(PermissionError) as ctx:
            credential_vault.get_credentials(pid)
        self.assertIn("Vault integrity verification failed", str(ctx.exception))

    def test_03_aad_tampering_rejected(self):
        """Verify modifying Associated Data (exchange, environment) breaks authentication."""
        profile = credential_vault.save_profile(
            exchange="BINANCE",
            environment="DEMO",
            label="AAD Tamper Test",
            api_key="vmPU1234567890abcdefXYZ",
            api_secret="original_secret_string"
        )

        pid = profile["profile_id"]
        # Tamper with environment metadata in profile
        credential_vault._profiles[pid]["environment"] = "LIVE"

        with self.assertRaises(PermissionError) as ctx:
            credential_vault.get_credentials(pid)
        self.assertIn("Vault integrity verification failed", str(ctx.exception))

    def test_04_missing_master_key_fails_closed(self):
        """Verify credential vault fails closed if TAURIC_VAULT_KEY is not configured."""
        if "TAURIC_VAULT_KEY" in os.environ:
            del os.environ["TAURIC_VAULT_KEY"]
        settings.tauric_vault_key = ""

        with self.assertRaises(RuntimeError) as ctx:
            credential_vault.save_profile(
                exchange="BINANCE",
                environment="DEMO",
                label="No Key",
                api_key="test",
                api_secret="test"
            )
        self.assertIn("TAURIC_VAULT_KEY", str(ctx.exception))

    def test_05_invalid_master_key_length_fails_closed(self):
        """Verify non-32-byte key fails closed."""
        os.environ["TAURIC_VAULT_KEY"] = "too_short_key_16_bytes"
        with self.assertRaises(RuntimeError) as ctx:
            get_vault_master_key()
        self.assertIn("Expected 32 bytes", str(ctx.exception))

    def test_06_secret_leakage_audit(self):
        """Verify secrets never leak in public profile responses or serialized JSON."""
        secret_value = "super_confidential_secret_string_987"
        profile = credential_vault.save_profile(
            exchange="BINANCE",
            environment="DEMO",
            label="Leakage Audit",
            api_key="vmPU1234567890abcdefXYZ",
            api_secret=secret_value
        )

        # 1. Check returned profile from save_profile
        profile_json = json.dumps(profile)
        self.assertNotIn(secret_value, profile_json)
        self.assertNotIn("vmPU1234567890abcdefXYZ", profile_json)
        self.assertEqual(profile["api_key_masked"], "vmPU••••••••fXYZ")

        # 2. Check list_profiles
        profiles_list = credential_vault.list_profiles()
        list_json = json.dumps(profiles_list)
        self.assertNotIn(secret_value, list_json)

        # 3. Check public profile fetch
        pub = credential_vault.get_profile_public(profile["profile_id"])
        self.assertNotIn(secret_value, json.dumps(pub))

    def test_07_legacy_xor_migration_to_aes_gcm(self):
        """Verify transparent migration of legacy XOR profiles to AES-256-GCM."""
        pid = "prof_legacy_test_01"
        salt = "abcdef1234567890"
        legacy_key = hashlib.sha256((salt + "tauric_vault_key").encode("utf-8")).digest()
        secret_str = "migrated_secret_token_456"

        # Encrypt with XOR
        xor_ct = bytearray()
        for i, b in enumerate(secret_str.encode("utf-8")):
            xor_ct.append(b ^ legacy_key[i % len(legacy_key)])

        credential_vault._profiles[pid] = {
            "profile_id": pid,
            "exchange": "BINANCE",
            "environment": "DEMO",
            "label": "Legacy Profile",
            "api_key_masked": "vmPU••••••••fXYZ",
            "_api_key_plain": "vmPU1234567890abcdefXYZ",
            "_api_secret_enc": xor_ct.hex(),
            "_salt": salt
        }

        # Trigger migration
        credential_vault._migrate_legacy_profiles()

        migrated = credential_vault._profiles[pid]
        self.assertIn("_credentials_enc", migrated)
        self.assertEqual(migrated["_credentials_enc"]["cipher"], "AES-256-GCM")
        self.assertNotIn("_api_secret_enc", migrated)
        self.assertNotIn("_salt", migrated)
        self.assertNotIn("_api_key_plain", migrated)

        # Verify decrypted credentials match
        creds = credential_vault.get_credentials(pid)
        self.assertEqual(creds["api_secret"], "migrated_secret_token_456")
        self.assertEqual(creds["api_key"], "vmPU1234567890abcdefXYZ")

    def test_08_unconfigured_credentials_blocks_demo_execution(self):
        """Verify demo execution is BLOCKED and returns zero fills when testnet keys are missing."""
        adapter = BinanceSpotAdapter()
        order_req = {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.05,
            "price": 65000.0,
            "account_label": "Unconfigured"
        }

        receipt = self.loop.run_until_complete(
            adapter.submit_order(order_req, Environment.DEMO, {})
        )

        self.assertEqual(receipt.status, OrderStatus.REJECTED)
        self.assertEqual(receipt.executed_qty, 0.0)
        self.assertEqual(receipt.avg_fill_price, 0.0)
        self.assertIn("BLOCKED", receipt.error_message)
        self.assertTrue(any("BLOCKED" in trail for trail in receipt.audit_trail))

    def test_09_actual_testnet_connectivity_and_auth_rejection(self):
        """Verify actual Binance testnet ping passes and invalid credentials fail authentication."""
        adapter = BinanceSpotAdapter()

        # 1. Real connectivity test against testnet ping
        ping = self.loop.run_until_complete(
            adapter.test_connectivity(Environment.DEMO, {})
        )
        self.assertEqual(ping["status"], "PASS")
        self.assertEqual(ping["exchange"], "BINANCE")
        self.assertGreater(ping["latency_ms"], 0)

        # 2. Real permissions test with fake credentials against Binance Testnet API
        fake_creds = {
            "api_key": "fake_testnet_key_1234567890abcdef",
            "api_secret": "fake_testnet_secret_1234567890abcdef"
        }
        auth_res = self.loop.run_until_complete(
            adapter.verify_permissions(Environment.DEMO, fake_creds)
        )
        self.assertEqual(auth_res["status"], "FAIL")
        self.assertFalse(auth_res["verified"])
        self.assertFalse(auth_res["can_trade"])
        self.assertIn("rejected", auth_res["error"])

    def test_10_bybit_testnet_connectivity_and_auth_rejection(self):
        """Verify Bybit testnet public time check passes and invalid credentials fail."""
        adapter = BybitSpotAdapter()

        # 1. Public connectivity
        ping = self.loop.run_until_complete(
            adapter.test_connectivity(Environment.DEMO, {})
        )
        self.assertEqual(ping["status"], "PASS")
        self.assertEqual(ping["exchange"], "BYBIT")

        # 2. Invalid credentials verification
        fake_creds = {
            "api_key": "fake_bybit_key_123",
            "api_secret": "fake_bybit_secret_123"
        }
        auth_res = self.loop.run_until_complete(
            adapter.verify_permissions(Environment.DEMO, fake_creds)
        )
        self.assertEqual(auth_res["status"], "FAIL")
        self.assertFalse(auth_res["verified"])
        self.assertFalse(auth_res["can_trade"])

    def test_11_timeout_reconciliation_by_client_order_id(self):
        """Verify that a submission timeout triggers reconciliation by client_order_id and marks FAILED if unconfirmed."""
        adapter = BinanceSpotAdapter()
        order_req = {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "quantity": 0.01,
            "price": 60000.0,
            "client_order_id": "ORD-TIMEOUT-RECON-001"
        }
        creds = {"api_key": "dummy_key", "api_secret": "dummy_secret"}

        # Simulate TimeoutException on initial POST and 404/not found on reconciliation query
        with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Read timed out")):
            with patch("httpx.AsyncClient.get", return_value=AsyncMock(status_code=404, json=lambda: {})):
                receipt = self.loop.run_until_complete(
                    adapter.submit_order(order_req, Environment.DEMO, creds)
                )

        self.assertEqual(receipt.status, OrderStatus.FAILED)
        self.assertEqual(receipt.executed_qty, 0.0)
        self.assertTrue(any("timed out and could not be confirmed" in trail for trail in receipt.audit_trail))

    def test_12_protective_order_integrity_inverted_tp_sl(self):
        """Verify inverted Stop-Loss or Take-Profit parameters are rejected."""
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

        # Case 1: BUY order with Stop Loss above entry price (inverted)
        res1 = adapter.validate_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.01,
            price=60000.0,
            quote_balance=10000.0,
            base_balance=0.0,
            rules=rules,
            stop_loss=62000.0  # Invalid for BUY
        )
        self.assertFalse(res1.is_valid)
        self.assertTrue(any("must be strictly below entry price" in err for err in res1.errors))

        # Case 2: BUY order with Take Profit below entry price (inverted)
        res2 = adapter.validate_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.01,
            price=60000.0,
            quote_balance=10000.0,
            base_balance=0.0,
            rules=rules,
            take_profit=58000.0  # Invalid for BUY
        )
        self.assertFalse(res2.is_valid)
        self.assertTrue(any("must be strictly above entry price" in err for err in res2.errors))

        # Case 3: SELL order with Stop Loss below entry price (inverted)
        res3 = adapter.validate_order(
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=0.01,
            price=60000.0,
            quote_balance=10000.0,
            base_balance=1.0,
            rules=rules,
            stop_loss=58000.0  # Invalid for SELL
        )
        self.assertFalse(res3.is_valid)
        self.assertTrue(any("must be strictly above entry price" in err for err in res3.errors))

    def test_13_partial_fill_position_tracking_and_fee(self):
        """Verify partial fill updates position ledger with exact executed quantity and proportional fee."""
        partial_receipt = OrderExecutionReceipt(
            client_order_id="ORD-PARTIAL-001",
            exchange_order_id="EXCH-PARTIAL-123",
            exchange="BINANCE",
            environment="DEMO",
            account_label="Demo Testnet",
            symbol="BTCUSDT",
            side="BUY",
            order_type="LIMIT",
            status=OrderStatus.PARTIALLY_FILLED,
            requested_qty=0.10,
            executed_qty=0.04,  # Only 40% filled
            requested_price=60000.0,
            avg_fill_price=60000.0,
            fee_amount=2.40,    # 0.04 * 60000 * 0.001
            fee_asset="USDT",
            protective_stop_loss=58000.0,
            protective_take_profit=65000.0,
            submitted_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            filled_at_utc=None
        )

        exchange_framework._update_position_from_fill(partial_receipt)
        pos = exchange_framework.get_positions("DEMO")[0]

        self.assertEqual(pos["status"], "OPEN")
        self.assertEqual(pos["size"], 0.04)  # Position size reflects executed, not requested
        self.assertEqual(pos["entry_price"], 60000.0)
        self.assertEqual(pos["fees_paid"], 2.40)

    def test_14_balance_reconciliation_and_insufficient_funds(self):
        """Verify order is rejected when quote balance cannot cover notional plus fee."""
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

        # Buying 0.1 BTC at 60,000 requires 6,000 + 6 fee = 6,006
        res = adapter.validate_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.1,
            price=60000.0,
            quote_balance=5999.0,  # Just under required
            base_balance=0.0,
            rules=rules
        )
        self.assertFalse(res.is_valid)
        self.assertTrue(any("Insufficient USDT balance" in err for err in res.errors))

    def test_15_fail_closed_risk_gates(self):
        """Verify all deterministic risk gates fail closed."""
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

        # 1. Stale market data
        r1 = adapter.validate_order("ETHUSDT", OrderSide.BUY, OrderType.LIMIT, 1.0, 2500.0, 5000.0, 0.0, rules, freshness_status="STALE")
        self.assertFalse(r1.is_valid)
        self.assertTrue(any("not fresh" in err for err in r1.errors))

        # 2. Illiquid market
        r2 = adapter.validate_order("ETHUSDT", OrderSide.BUY, OrderType.LIMIT, 1.0, 2500.0, 5000.0, 0.0, rules, liquidity_status="ILLIQUID")
        self.assertFalse(r2.is_valid)
        self.assertTrue(any("not qualified" in err for err in r2.errors))

        # 3. Expired validity
        r3 = adapter.validate_order("ETHUSDT", OrderSide.BUY, OrderType.LIMIT, 1.0, 2500.0, 5000.0, 0.0, rules, entry_validity_sec=0)
        self.assertFalse(r3.is_valid)
        self.assertTrue(any("expired" in err for err in r3.errors))

        # 4. Unqualified setup
        r4 = adapter.validate_order("ETHUSDT", OrderSide.BUY, OrderType.LIMIT, 1.0, 2500.0, 5000.0, 0.0, rules, setup_qualified=False)
        self.assertFalse(r4.is_valid)
        self.assertTrue(any("setup is not qualified" in err for err in r4.errors))

        # 5. Event blackout
        r5 = adapter.validate_order("ETHUSDT", OrderSide.BUY, OrderType.LIMIT, 1.0, 2500.0, 5000.0, 0.0, rules, is_blackout=True)
        self.assertFalse(r5.is_valid)
        self.assertTrue(any("blackout window" in err for err in r5.errors))

    def test_16_idempotency_duplicate_submission_protection(self):
        """Verify identical idempotency key returns cached receipt without submitting twice."""
        mock_receipt = OrderExecutionReceipt(
            client_order_id="ORD-IDEMP-001",
            exchange_order_id="EXCH-001",
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
            submitted_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            filled_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        )

        with patch.object(exchange_framework.get_adapter("BINANCE"), "submit_order", return_value=mock_receipt) as mock_sub:
            order_req = {"exchange": "BINANCE", "symbol": "BTCUSDT", "side": "BUY", "quantity": 0.01, "price": 60000.0}

            r1 = self.loop.run_until_complete(
                exchange_framework.execute_demo_order(None, order_req, "IDEMP-KEY-ABC")
            )
            r2 = self.loop.run_until_complete(
                exchange_framework.execute_demo_order(None, order_req, "IDEMP-KEY-ABC")
            )

            self.assertEqual(r1.client_order_id, r2.client_order_id)
            # Ensure adapter was called only once despite two submissions
            self.assertEqual(mock_sub.call_count, 1)


if __name__ == "__main__":
    unittest.main()
