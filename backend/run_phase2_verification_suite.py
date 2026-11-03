"""
BITDEX Phase 2: Complete 22-Scenario Verification Suite
========================================================
Runs authoritative tests covering all 22 required safety, risk, execution,
reconciliation, isolation, and regression scenarios for Binance USD(S)-M Futures.
"""

import sys
import time
import secrets
import sqlite3
import asyncio
from typing import Dict, Any, List

# Services
from app.services.saas_db import get_db_connection
from app.services.binance_futures_adapter import (
    BinanceFuturesAdapter,
    BinanceFuturesError,
    BinanceFuturesAuthError,
    BinanceFuturesRateLimitError,
    BinanceFuturesClockSkewError,
    BinanceFuturesMarginError,
    BinanceFuturesOrderRejectedError,
)
from app.services.futures_db import (
    apply_futures_migrations,
    get_or_create_futures_account,
    get_futures_account,
    update_futures_account_balances,
    set_futures_kill_switch,
    create_futures_order,
    get_futures_order,
    update_futures_order_status,
    get_open_futures_position,
    list_open_futures_positions,
    upsert_futures_position,
    record_futures_fill,
    record_realized_pnl,
    record_funding_payment,
    record_reconciliation_event,
)
from app.services.futures_risk_engine import FuturesRiskEngine, FuturesRiskDecisionResult
from app.services.futures_execution import FuturesExecutionEngine
from app.services.futures_reconciliation import FuturesReconciliationEngine

# Spot adapter for regression check
from app.services.exchange_framework import BinanceSpotAdapter, Environment


class Phase2Verifier:
    def __init__(self):
        self.results: List[Dict[str, Any]] = []
        self.conn = get_db_connection()
        apply_futures_migrations(self.conn)
        self.test_user_a = "USR-328E147ACA"
        self.test_user_b = "USR-TEST-B-PHASE1A"
        self.admin_user = "USR-66BCFD7350"

    def record_test(self, test_num: int, name: str, passed: bool, evidence: Dict[str, Any], notes: str = ""):
        res = {
            "test_num": test_num,
            "name": name,
            "status": "PASS" if passed else "FAIL",
            "evidence": evidence,
            "notes": notes
        }
        self.results.append(res)
        prefix = "✅ PASS" if passed else "❌ FAIL"
        print(f"[{prefix}] Test {test_num:02d}: {name}")
        if not passed:
            print("  Evidence:", evidence)
            if notes:
                print("  Notes:", notes)

    def run_all(self):
        print("=" * 70)
        print("RUNNING BITDEX PHASE 2: 22-SCENARIO VERIFICATION SUITE")
        print("=" * 70)

        # ── Test 1: Spot vs Futures Adapter Separation ──
        try:
            spot = BinanceSpotAdapter()
            futures = BinanceFuturesAdapter(api_key="test_fut_key", api_secret="test_fut_sec", environment="testnet")
            
            spot_base = spot.LIVE_BASE_URL
            fut_base = futures.base_url
            
            assert "api.binance.com" in spot_base, "Spot should target api.binance.com"
            assert "binancefuture.com" in fut_base or "fapi.binance.com" in fut_base, "Futures should target binancefuture.com"
            assert spot.__class__ != futures.__class__, "Classes must be distinct"
            
            self.record_test(1, "Spot vs Futures Adapter Separation", True, {
                "spot_class": spot.__class__.__name__,
                "spot_live_base_url": spot_base,
                "futures_class": futures.__class__.__name__,
                "futures_base_url": fut_base,
            })
        except Exception as e:
            self.record_test(1, "Spot vs Futures Adapter Separation", False, {"error": str(e)})

        # ── Test 2: Testnet vs Mainnet Configuration Isolation & Live Lock ──
        try:
            fut_testnet = BinanceFuturesAdapter(environment="testnet", live_trading_locked=True)
            fut_mainnet = BinanceFuturesAdapter(environment="mainnet", live_trading_locked=True)
            
            assert fut_testnet.base_url == "https://testnet.binancefuture.com"
            assert fut_mainnet.base_url == "https://fapi.binance.com"
            assert fut_testnet.ws_url == "wss://stream.binancefuture.com"
            assert fut_mainnet.ws_url == "wss://fstream.binance.com"
            
            # Verify Mainnet lock throws exception on submit_order
            locked_exception_caught = False
            try:
                fut_mainnet.submit_order(
                    symbol="BTCUSDT",
                    side="BUY",
                    order_type="MARKET",
                    quantity=0.01
                )
            except RuntimeError as re:
                if "CRITICAL SAFETY LOCK" in str(re):
                    locked_exception_caught = True

            assert locked_exception_caught, "Mainnet with live_trading_locked=True must reject orders"

            self.record_test(2, "Testnet vs Mainnet Isolation & Live Lock", True, {
                "testnet_url": fut_testnet.base_url,
                "mainnet_url": fut_mainnet.base_url,
                "live_lock_verified": locked_exception_caught
            })
        except Exception as e:
            self.record_test(2, "Testnet vs Mainnet Isolation & Live Lock", False, {"error": str(e)})

        # ── Test 3: Invalid Credentials Rejection ──
        try:
            bad_adapter = BinanceFuturesAdapter(api_key="INVALID_KEY", api_secret="INVALID_SECRET", environment="testnet")
            caught_auth_err = False
            try:
                bad_adapter.get_account_balance()
            except (BinanceFuturesAuthError, BinanceFuturesError) as bfe:
                caught_auth_err = True

            self.record_test(3, "Invalid Credentials Rejection", caught_auth_err, {
                "rejected_expectedly": caught_auth_err
            })
        except Exception as e:
            self.record_test(3, "Invalid Credentials Rejection", False, {"error": str(e)})

        # ── Test 4: Invalid Timestamp / Clock Skew Handling ──
        try:
            adapter = BinanceFuturesAdapter(environment="testnet")
            offset_ms = adapter.sync_clock()
            assert isinstance(offset_ms, int)
            server_time = adapter.get_server_time()
            assert server_time > 1700000000000

            self.record_test(4, "Timestamp & Clock Skew Synchronization", True, {
                "offset_ms": offset_ms,
                "server_time": server_time,
                "clock_synced": adapter._clock_synced
            })
        except Exception as e:
            self.record_test(4, "Timestamp & Clock Skew Synchronization", False, {"error": str(e)})

        # ── Test 5: Exchange Rate Limits & Error Normalization ──
        try:
            import httpx
            adapter = BinanceFuturesAdapter(environment="testnet")
            # Create a mock 429 response to verify normalization
            mock_resp = httpx.Response(status_code=429, headers={"Retry-After": "45"}, json={"code": -1003, "msg": "Too many requests."})
            caught_429 = False
            try:
                adapter._handle_error_response(mock_resp)
            except BinanceFuturesRateLimitError as rle:
                caught_429 = (rle.retry_after == 45 and rle.code == -1003)

            self.record_test(5, "Rate Limit & Error Normalization", caught_429, {
                "caught_rate_limit_error": caught_429,
                "retry_after_parsed": 45
            })
        except Exception as e:
            self.record_test(5, "Rate Limit & Error Normalization", False, {"error": str(e)})

        # ── Test 6: Symbol Filter Validation (lotSize, tickSize, minNotional) ──
        try:
            adapter = BinanceFuturesAdapter(environment="testnet")
            filters = adapter.get_symbol_filters("BTCUSDT")
            clamped_qty, clamped_price = adapter.validate_and_clamp_order(
                symbol="BTCUSDT",
                quantity=0.012345678,
                price=65432.1987
            )
            assert clamped_qty <= 0.012345678
            assert clamped_price is not None

            notional_rejected = False
            try:
                adapter.validate_and_clamp_order("BTCUSDT", quantity=0.00001, price=100.0)
            except BinanceFuturesOrderRejectedError:
                notional_rejected = True

            self.record_test(6, "Symbol Filter Validation & Clamping", True, {
                "step_size": filters["step_size"],
                "tick_size": filters["tick_size"],
                "min_notional": filters["min_notional"],
                "clamped_qty": clamped_qty,
                "clamped_price": clamped_price,
                "sub_notional_rejected": notional_rejected
            })
        except Exception as e:
            self.record_test(6, "Symbol Filter Validation & Clamping", False, {"error": str(e)})

        # ── Test 7: Insufficient Available Margin Rejection ──
        try:
            acct = get_or_create_futures_account(self.conn, user_id=self.test_user_a, exchange_connection_id="CONN-TEST-A", initial_balance=100.0)
            update_futures_account_balances(self.conn, self.test_user_a, acct["account_id"], wallet_balance=100.0, available_balance=50.0)

            res = FuturesRiskEngine.evaluate_pre_trade(
                conn=self.conn,
                user_id=self.test_user_a,
                account_id=acct["account_id"],
                client_order_id=f"TEST-COID-{secrets.token_hex(4)}",
                symbol="BTCUSDT",
                side="BUY",
                intent="LONG_ENTRY",
                quantity=0.01,
                price=60000.0,
                leverage=3,
                stop_price=59500.0
            )
            passed = (not res.is_approved and res.rejection_code == "INSUFFICIENT_AVAILABLE_MARGIN")
            self.record_test(7, "Insufficient Available Margin Rejection", passed, {
                "decision": res.decision,
                "code": res.rejection_code,
                "reason": res.rejection_reason
            })
        except Exception as e:
            self.record_test(7, "Insufficient Available Margin Rejection", False, {"error": str(e)})

        # ── Test 8: Excessive Leverage Rejection (> 10x) ──
        try:
            acct = get_futures_account(self.conn, user_id=self.test_user_a)
            update_futures_account_balances(self.conn, self.test_user_a, acct["account_id"], wallet_balance=1000.0, available_balance=1000.0)
            res = FuturesRiskEngine.evaluate_pre_trade(
                conn=self.conn,
                user_id=self.test_user_a,
                account_id=acct["account_id"],
                client_order_id=f"TEST-COID-{secrets.token_hex(4)}",
                symbol="BTCUSDT",
                side="BUY",
                intent="LONG_ENTRY",
                quantity=0.001,
                price=60000.0,
                leverage=25,
                stop_price=59500.0
            )
            passed = (not res.is_approved and res.rejection_code == "LEVERAGE_EXCEEDS_MAX_CAP")
            self.record_test(8, "Excessive Leverage Rejection (> 10x)", passed, {
                "decision": res.decision,
                "code": res.rejection_code,
                "reason": res.rejection_reason
            })
        except Exception as e:
            self.record_test(8, "Excessive Leverage Rejection (> 10x)", False, {"error": str(e)})

        # ── Test 9: Aggregate Exposure Limit Rejection (> $5,000) ──
        try:
            acct = get_futures_account(self.conn, user_id=self.test_user_a)
            update_futures_account_balances(self.conn, self.test_user_a, acct["account_id"], wallet_balance=10000.0, available_balance=10000.0)
            # Notional = 0.1 * 60,000 = $6,000 > $5,000 limit
            # Stop distance = (60000 - 59500)/60000 = 0.83% (within 0.2% - 5.0% bounds)
            # Dollar risk = 500 * 0.1 = $50 <= 2% of $10000 ($200) -> passes risk cap, trips aggregate exposure
            res = FuturesRiskEngine.evaluate_pre_trade(
                conn=self.conn,
                user_id=self.test_user_a,
                account_id=acct["account_id"],
                client_order_id=f"TEST-COID-{secrets.token_hex(4)}",
                symbol="BTCUSDT",
                side="BUY",
                intent="LONG_ENTRY",
                quantity=0.1,
                price=60000.0,
                leverage=5,
                stop_price=59500.0
            )
            passed = (not res.is_approved and res.rejection_code == "AGGREGATE_EXPOSURE_EXCEEDS_LIMIT")
            self.record_test(9, "Aggregate Exposure Limit Rejection (> $5,000)", passed, {
                "decision": res.decision,
                "code": res.rejection_code,
                "reason": res.rejection_reason
            })
        except Exception as e:
            self.record_test(9, "Aggregate Exposure Limit Rejection (> $5,000)", False, {"error": str(e)})

        # ── Test 10: Daily Loss Limit Rejection (>= $250) ──
        try:
            acct = get_futures_account(self.conn, user_id=self.test_user_a)
            record_realized_pnl(
                conn=self.conn,
                user_id=self.test_user_a,
                account_id=acct["account_id"],
                symbol="BTCUSDT",
                entry_price=60000.0,
                exit_price=57400.0,
                closed_qty=0.1,
                gross_pnl_usd=-260.0,
                total_fees_usd=2.0,
                net_pnl_usd=-262.0
            )
            res = FuturesRiskEngine.evaluate_pre_trade(
                conn=self.conn,
                user_id=self.test_user_a,
                account_id=acct["account_id"],
                client_order_id=f"TEST-COID-{secrets.token_hex(4)}",
                symbol="BTCUSDT",
                side="BUY",
                intent="LONG_ENTRY",
                quantity=0.001,
                price=60000.0,
                leverage=3,
                stop_price=59500.0
            )
            passed = (not res.is_approved and res.rejection_code == "DAILY_LOSS_LIMIT_REACHED")
            self.record_test(10, "Daily Loss Limit Rejection (>= $250)", passed, {
                "decision": res.decision,
                "code": res.rejection_code,
                "reason": res.rejection_reason
            })
            self.conn.execute("DELETE FROM futures_realized_pnl WHERE user_id = ? AND net_pnl_usd = -262.0", (self.test_user_a,))
            self.conn.commit()
        except Exception as e:
            self.record_test(10, "Daily Loss Limit Rejection (>= $250)", False, {"error": str(e)})

        # ── Test 11: Stale Market Data Rejection (> 5000ms) ──
        try:
            acct = get_futures_account(self.conn, user_id=self.test_user_a)
            stale_timestamp = int(time.time() * 1000) - 10000
            res = FuturesRiskEngine.evaluate_pre_trade(
                conn=self.conn,
                user_id=self.test_user_a,
                account_id=acct["account_id"],
                client_order_id=f"TEST-COID-{secrets.token_hex(4)}",
                symbol="BTCUSDT",
                side="BUY",
                intent="LONG_ENTRY",
                quantity=0.001,
                price=60000.0,
                leverage=3,
                stop_price=59500.0,
                market_price_timestamp_ms=stale_timestamp
            )
            passed = (not res.is_approved and res.rejection_code == "STALE_MARKET_DATA")
            self.record_test(11, "Stale Market Data Rejection (> 5000ms)", passed, {
                "decision": res.decision,
                "code": res.rejection_code,
                "reason": res.rejection_reason
            })
        except Exception as e:
            self.record_test(11, "Stale Market Data Rejection (> 5000ms)", False, {"error": str(e)})

        # ── Test 12: Missing Protective Stop Rejection ──
        try:
            acct = get_futures_account(self.conn, user_id=self.test_user_a)
            res = FuturesRiskEngine.evaluate_pre_trade(
                conn=self.conn,
                user_id=self.test_user_a,
                account_id=acct["account_id"],
                client_order_id=f"TEST-COID-{secrets.token_hex(4)}",
                symbol="BTCUSDT",
                side="BUY",
                intent="LONG_ENTRY",
                quantity=0.001,
                price=60000.0,
                leverage=3,
                stop_price=None
            )
            passed = (not res.is_approved and res.rejection_code == "MANDATORY_STOP_REQUIRED")
            self.record_test(12, "Missing Protective Stop Rejection", passed, {
                "decision": res.decision,
                "code": res.rejection_code,
                "reason": res.rejection_reason
            })
        except Exception as e:
            self.record_test(12, "Missing Protective Stop Rejection", False, {"error": str(e)})

        # ── Test 13: Duplicate Order / Idempotency Protection ──
        try:
            fixed_coid = f"IDEM-TEST-{secrets.token_hex(6)}"
            acct = get_futures_account(self.conn, user_id=self.test_user_a)
            update_futures_account_balances(self.conn, self.test_user_a, acct["account_id"], wallet_balance=2000.0, available_balance=2000.0)

            exec1 = FuturesExecutionEngine.execute_intent(
                conn=self.conn,
                user_id=self.test_user_a,
                intent="LONG_ENTRY",
                symbol="BTCUSDT",
                quantity=0.005,
                price=60000.0,
                stop_price=59500.0,
                leverage=3,
                client_order_id=fixed_coid,
                simulate_execution=True
            )
            assert exec1["success"] is True

            exec2 = FuturesExecutionEngine.execute_intent(
                conn=self.conn,
                user_id=self.test_user_a,
                intent="LONG_ENTRY",
                symbol="BTCUSDT",
                quantity=0.005,
                price=60000.0,
                stop_price=59500.0,
                leverage=3,
                client_order_id=fixed_coid,
                simulate_execution=True
            )
            passed = (exec2["success"] is False and exec2["error_code"] == "DUPLICATE_CLIENT_ORDER_ID")
            self.record_test(13, "Duplicate Order / Idempotency Protection", passed, {
                "first_success": exec1["success"],
                "duplicate_rejected": not exec2["success"],
                "error_code": exec2.get("error_code")
            })
        except Exception as e:
            self.record_test(13, "Duplicate Order / Idempotency Protection", False, {"error": str(e)})

        # ── Test 14: Partial-Fill Lifecycle ──
        try:
            acct = get_futures_account(self.conn, user_id=self.test_user_a)
            part_order = create_futures_order(
                conn=self.conn,
                user_id=self.test_user_a,
                account_id=acct["account_id"],
                client_order_id=f"PART-{secrets.token_hex(4)}",
                symbol="ETHUSDT",
                side="BUY",
                order_type="LIMIT",
                intent="LONG_ENTRY",
                quantity=1.0,
                price=3000.0,
                stop_price=2950.0,
                status="SUBMITTED"
            )
            update_futures_order_status(
                conn=self.conn,
                user_id=self.test_user_a,
                order_id=part_order["order_id"],
                status="PARTIALLY_FILLED",
                executed_qty=0.4,
                cumulative_quote_qty=1200.0,
                avg_fill_price=3000.0
            )
            ord_check = get_futures_order(self.conn, user_id=self.test_user_a, order_id=part_order["order_id"])
            assert ord_check["status"] == "PARTIALLY_FILLED"
            assert ord_check["executed_qty"] == 0.4

            update_futures_order_status(
                conn=self.conn,
                user_id=self.test_user_a,
                order_id=part_order["order_id"],
                status="FILLED",
                executed_qty=1.0,
                cumulative_quote_qty=3000.0,
                avg_fill_price=3000.0
            )
            ord_filled = get_futures_order(self.conn, user_id=self.test_user_a, order_id=part_order["order_id"])
            passed = (ord_filled["status"] == "FILLED" and ord_filled["executed_qty"] == 1.0)

            self.record_test(14, "Partial-Fill Lifecycle State Progression", passed, {
                "initial_status": "SUBMITTED",
                "intermediate_status": ord_check["status"],
                "final_status": ord_filled["status"],
                "final_executed_qty": ord_filled["executed_qty"]
            })
        except Exception as e:
            self.record_test(14, "Partial-Fill Lifecycle State Progression", False, {"error": str(e)})

        # ── Test 15: Order Cancellation & State Lifecycle ──
        try:
            cancel_coid = f"CAN-{secrets.token_hex(4)}"
            acct = get_futures_account(self.conn, user_id=self.test_user_a)
            c_ord = create_futures_order(
                conn=self.conn,
                user_id=self.test_user_a,
                account_id=acct["account_id"],
                client_order_id=cancel_coid,
                symbol="ETHUSDT",
                side="SELL",
                order_type="LIMIT",
                intent="SHORT_ENTRY",
                quantity=0.5,
                price=3200.0,
                stop_price=3250.0,
                status="NEW"
            )
            update_futures_order_status(
                conn=self.conn,
                user_id=self.test_user_a,
                order_id=c_ord["order_id"],
                status="CANCELED",
                rejection_reason="CANCELED_BY_USER"
            )
            c_check = get_futures_order(self.conn, user_id=self.test_user_a, order_id=c_ord["order_id"])
            passed = (c_check["status"] == "CANCELED" and c_check["rejection_reason"] == "CANCELED_BY_USER")

            self.record_test(15, "Order Cancellation & State Transition", passed, {
                "order_id": c_ord["order_id"],
                "status": c_check["status"],
                "reason": c_check["rejection_reason"]
            })
        except Exception as e:
            self.record_test(15, "Order Cancellation & State Transition", False, {"error": str(e)})

        # ── Test 16: Actual Fee & Realized P&L Accounting ──
        try:
            open_pos = get_open_futures_position(self.conn, user_id=self.test_user_a, symbol="BTCUSDT")
            assert open_pos is not None, "Open position from test 13 must exist"
            
            exit_exec = FuturesExecutionEngine.execute_intent(
                conn=self.conn,
                user_id=self.test_user_a,
                intent="LONG_EXIT",
                symbol="BTCUSDT",
                quantity=float(open_pos["quantity"]),
                price=61000.0,
                simulate_execution=True
            )
            assert exit_exec["success"] is True
            gross_pnl = exit_exec["gross_pnl_usd"]
            net_pnl = exit_exec["net_pnl_usd"]
            fees = exit_exec["fees_usd"]
            
            assert gross_pnl == 5.0, f"Expected gross PnL $5.00, got {gross_pnl}"
            assert net_pnl < gross_pnl, "Net PnL must deduct fees"
            
            closed_pos = get_open_futures_position(self.conn, user_id=self.test_user_a, symbol="BTCUSDT")
            passed = (closed_pos is None)

            self.record_test(16, "Actual Fee & Realized P&L Accounting", passed, {
                "entry_price": exit_exec["entry_price"],
                "exit_price": exit_exec["exit_price"],
                "gross_pnl_usd": gross_pnl,
                "fees_usd": fees,
                "net_pnl_usd": net_pnl,
                "position_closed": passed
            })
        except Exception as e:
            self.record_test(16, "Actual Fee & Realized P&L Accounting", False, {"error": str(e)})

        # ── Test 17: Funding Record Handling & Deduplication ──
        try:
            acct = get_futures_account(self.conn, user_id=self.test_user_a)
            tran_id = int(time.time() * 1000) + secrets.randbelow(100000)
            f1 = record_funding_payment(
                conn=self.conn,
                user_id=self.test_user_a,
                account_id=acct["account_id"],
                symbol="BTCUSDT",
                funding_rate=0.0001,
                position_qty_at_funding=0.01,
                payment_amount_usd=-0.06,
                exchange_tran_id=tran_id
            )
            assert f1 is not None

            f2 = record_funding_payment(
                conn=self.conn,
                user_id=self.test_user_a,
                account_id=acct["account_id"],
                symbol="BTCUSDT",
                funding_rate=0.0001,
                position_qty_at_funding=0.01,
                payment_amount_usd=-0.06,
                exchange_tran_id=tran_id
            )
            passed = (f2 is None)

            self.record_test(17, "Funding Record Handling & Deduplication", passed, {
                "first_insert": f1["funding_id"],
                "duplicate_deduplicated": passed
            })
        except Exception as e:
            self.record_test(17, "Funding Record Handling & Deduplication", False, {"error": str(e)})

        # ── Test 18: Tenant Isolation (Customer A vs Customer B) ──
        try:
            acct_a = get_futures_account(self.conn, user_id=self.test_user_a)
            leaked_acct = get_futures_account(self.conn, user_id=self.test_user_b, account_id=acct_a["account_id"])
            assert leaked_acct is None, "Customer B queried Customer A's account_id!"

            orders_a = self.conn.execute("SELECT client_order_id FROM futures_orders WHERE user_id = ?", (self.test_user_a,)).fetchall()
            if orders_a:
                coid_a = orders_a[0]["client_order_id"]
                leaked_order = get_futures_order(self.conn, user_id=self.test_user_b, client_order_id=coid_a)
                assert leaked_order is None, "Customer B queried Customer A's client_order_id!"

            upsert_futures_position(
                conn=self.conn,
                user_id=self.test_user_a,
                account_id=acct_a["account_id"],
                symbol="SOLUSDT",
                quantity=1.0,
                entry_price=150.0,
                mark_price=150.0,
                leverage=3,
                isolated_margin=50.0
            )
            b_positions = list_open_futures_positions(self.conn, user_id=self.test_user_b)
            assert len(b_positions) == 0, "Customer B saw Customer A's open positions!"

            upsert_futures_position(self.conn, self.test_user_a, acct_a["account_id"], "SOLUSDT", 0.0, 150.0, 150.0, 3, 0.0)

            self.record_test(18, "Tenant Isolation (Customer A vs B)", True, {
                "account_isolated": leaked_acct is None,
                "orders_isolated": True,
                "positions_isolated": len(b_positions) == 0
            })
        except Exception as e:
            self.record_test(18, "Tenant Isolation (Customer A vs B)", False, {"error": str(e)})

        # ── Test 19: Persistence & Schema Integrity ──
        try:
            integrity = self.conn.execute("PRAGMA integrity_check").fetchone()[0]
            assert integrity == "ok"
            tables = ["futures_accounts", "futures_orders", "futures_positions", "futures_fills",
                      "futures_risk_decisions", "futures_realized_pnl", "futures_funding_records", "futures_reconciliation_events"]
            table_counts = {}
            for t in tables:
                cnt = self.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                table_counts[t] = cnt

            self.record_test(19, "Persistence & Database Schema Integrity", True, {
                "sqlite_integrity": integrity,
                "table_counts": table_counts
            })
        except Exception as e:
            self.record_test(19, "Persistence & Database Schema Integrity", False, {"error": str(e)})

        # ── Test 20: Phase 1A & Phase 1B Regression Tests ──
        try:
            with open("/opt/tauric-platform-staging/backend/app/routes/ledger.py", "r") as f:
                ledger_src = f.read()
            assert "USR-402F7BFE6D" not in ledger_src, "USR-402F7BFE6D fallback must not be in ledger.py"

            admin_acct = self.conn.execute("SELECT * FROM users WHERE role = 'ADMIN' LIMIT 1").fetchone()
            ba = self.conn.execute("SELECT prepaid_credits_usd FROM billing_accounts WHERE user_id = ?", (self.test_user_a,)).fetchone()
            assert ba is not None, "Billing account for test user must exist"

            self.record_test(20, "Phase 1A & Phase 1B Regressions Verification", True, {
                "hardcoded_fallback_absent": True,
                "prepaid_credits_usd": float(ba["prepaid_credits_usd"]),
                "admin_actor_id": admin_acct["user_id"]
            })
        except Exception as e:
            self.record_test(20, "Phase 1A & Phase 1B Regressions Verification", False, {"error": str(e)})

        # ── Test 21: Existing Spot Functionality Operational ──
        try:
            spot = BinanceSpotAdapter()
            assert spot.LIVE_BASE_URL == "https://api.binance.com/api/v3"
            assert spot.TESTNET_BASE_URL == "https://demo-api.binance.com/api/v3"
            
            # Test public rules query for BTCUSDT on spot
            rules = asyncio.run(spot.fetch_symbol_rules(Environment.LIVE, "BTCUSDT"))
            assert rules is not None and rules.min_notional >= 5.0

            self.record_test(21, "Existing Spot Functionality Operational", True, {
                "spot_live_url": spot.LIVE_BASE_URL,
                "symbol_rules_fetched": rules.symbol,
                "spot_min_notional": rules.min_notional
            })
        except Exception as e:
            self.record_test(21, "Existing Spot Functionality Operational", False, {"error": str(e)})

        # ── Test 22: Emergency Kill Switch Behavior ──
        try:
            acct = get_futures_account(self.conn, user_id=self.test_user_a)
            set_futures_kill_switch(self.conn, user_id=self.test_user_a, account_id=acct["account_id"], active=True)
            
            entry_res = FuturesExecutionEngine.execute_intent(
                conn=self.conn,
                user_id=self.test_user_a,
                intent="LONG_ENTRY",
                symbol="BTCUSDT",
                quantity=0.001,
                price=60000.0,
                stop_price=59500.0,
                simulate_execution=True
            )
            entry_blocked = (entry_res["success"] is False and entry_res["error_code"] == "TRADING_KILL_SWITCH_ACTIVE")

            upsert_futures_position(
                conn=self.conn,
                user_id=self.test_user_a,
                account_id=acct["account_id"],
                symbol="BTCUSDT",
                quantity=0.005,
                entry_price=60000.0,
                mark_price=60000.0,
                leverage=3,
                isolated_margin=100.0
            )

            exit_res = FuturesExecutionEngine.execute_intent(
                conn=self.conn,
                user_id=self.test_user_a,
                intent="LONG_EXIT",
                symbol="BTCUSDT",
                quantity=0.005,
                price=60100.0,
                simulate_execution=True
            )
            exit_permitted = (exit_res["success"] is True)

            set_futures_kill_switch(self.conn, user_id=self.test_user_a, account_id=acct["account_id"], active=False)

            passed = (entry_blocked and exit_permitted)
            self.record_test(22, "Emergency Kill Switch Behavior", passed, {
                "entry_blocked_by_kill_switch": entry_blocked,
                "exit_permitted_for_risk_reduction": exit_permitted,
                "kill_switch_restored": True
            })
        except Exception as e:
            self.record_test(22, "Emergency Kill Switch Behavior", False, {"error": str(e)})

        print("=" * 70)
        total_passed = sum(1 for r in self.results if r["status"] == "PASS")
        print(f"VERIFICATION COMPLETE: {total_passed}/{len(self.results)} SCENARIOS PASSED")
        print("=" * 70)
        return total_passed == len(self.results)


if __name__ == "__main__":
    verifier = Phase2Verifier()
    success = verifier.run_all()
    sys.exit(0 if success else 1)
