import os
import json
import sqlite3
import hashlib
import secrets
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple
from fastapi import HTTPException

from .saas_db import get_db_connection

logger = logging.getLogger("tauric.fee_engine")

class FeeEngine:
    @staticmethod
    def get_platform_pricing_config() -> Dict[str, Any]:
        conn = get_db_connection()
        try:
            row = conn.execute("SELECT * FROM platform_pricing_config WHERE config_key = 'GLOBAL_DEFAULT'").fetchone()
            if not row:
                now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                with conn:
                    conn.execute("""
                        INSERT INTO platform_pricing_config (
                            config_key, ai_analysis_price_usd, ai_analysis_price_cents,
                            default_execution_fee_usd, default_activation_fee_usd,
                            admin_fee_waiver_enabled, updated_by, updated_at
                        ) VALUES ('GLOBAL_DEFAULT', 1.00, 100, 0.30, 20.00, 1, 'SYSTEM', ?)
                    """, (now_iso,))
                row = conn.execute("SELECT * FROM platform_pricing_config WHERE config_key = 'GLOBAL_DEFAULT'").fetchone()
            res = dict(row)
            res.setdefault("admin_fee_waiver_enabled", 1)
            return res
        finally:
            conn.close()

    @staticmethod
    def update_platform_pricing_config(
        actor_id: str,
        ai_analysis_price_usd: Optional[float] = None,
        ai_analysis_price_cents: Optional[int] = None,
        default_execution_fee_usd: Optional[float] = None,
        default_activation_fee_usd: Optional[float] = None,
        admin_fee_waiver_enabled: Optional[bool] = None,
        apply_to_all_customers: bool = True
    ) -> Dict[str, Any]:
        current = FeeEngine.get_platform_pricing_config()
        if ai_analysis_price_cents is not None:
            new_cents = max(0, int(ai_analysis_price_cents))
            new_usd = round(new_cents / 100.0, 2)
        elif ai_analysis_price_usd is not None:
            new_usd = round(max(0.0, float(ai_analysis_price_usd)), 2)
            new_cents = int(round(new_usd * 100))
        else:
            new_usd = float(current["ai_analysis_price_usd"])
            new_cents = int(current["ai_analysis_price_cents"])

        new_exec = float(current["default_execution_fee_usd"]) if default_execution_fee_usd is None else round(max(0.0, float(default_execution_fee_usd)), 2)
        new_act = float(current["default_activation_fee_usd"]) if default_activation_fee_usd is None else round(max(0.0, float(default_activation_fee_usd)), 2)
        new_waiver = (1 if admin_fee_waiver_enabled else 0) if admin_fee_waiver_enabled is not None else int(current.get("admin_fee_waiver_enabled", 1))
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        conn = get_db_connection()
        try:
            with conn:
                conn.execute("""
                    UPDATE platform_pricing_config
                    SET ai_analysis_price_usd = ?,
                        ai_analysis_price_cents = ?,
                        default_execution_fee_usd = ?,
                        default_activation_fee_usd = ?,
                        admin_fee_waiver_enabled = ?,
                        updated_by = ?,
                        updated_at = ?
                    WHERE config_key = 'GLOBAL_DEFAULT'
                """, (new_usd, new_cents, new_exec, new_act, new_waiver, actor_id, now_iso))

                if apply_to_all_customers:
                    conn.execute("""
                        UPDATE fee_policies
                        SET ai_research_fee_usd = ?,
                            ai_research_fee_cents = ?,
                            updated_at = ?
                        WHERE fee_waived = 0
                    """, (new_usd, new_cents, now_iso))

                log_id = f"AUD-{secrets.token_hex(6).upper()}"
                details = json.dumps({
                    "actor": actor_id,
                    "ai_analysis_price_usd": new_usd,
                    "ai_analysis_price_cents": new_cents,
                    "default_execution_fee_usd": new_exec,
                    "default_activation_fee_usd": new_act,
                    "admin_fee_waiver_enabled": bool(new_waiver),
                    "apply_to_all_customers": apply_to_all_customers
                })
                conn.execute("""
                    INSERT INTO audit_logs (log_id, actor_id, action, target_user_id, details_json, created_at)
                    VALUES (?, ?, 'PLATFORM_PRICING_UPDATED', 'GLOBAL', ?, ?)
                """, (log_id, actor_id, details, now_iso))

            return FeeEngine.get_platform_pricing_config()
        finally:
            conn.close()

    @staticmethod
    def is_admin_fee_waiver_active(user_id: str, conn: Optional[sqlite3.Connection] = None) -> Tuple[bool, str]:
        """
        Authoritative server-side check:
        Determines whether the user possesses an immutable ADMIN or OWNER role in the users database
        AND whether the server-side platform administrator billing exemption is active.
        Never relies on frontend tokens or headers.
        """
        should_close = False
        if conn is None:
            conn = get_db_connection()
            should_close = True
        try:
            user = conn.execute("SELECT user_id, email, role FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if not user or user["role"] not in ("ADMIN", "OWNER"):
                return False, ""

            cfg = conn.execute("SELECT admin_fee_waiver_enabled FROM platform_pricing_config WHERE config_key = 'GLOBAL_DEFAULT'").fetchone()
            if cfg and dict(cfg).get("admin_fee_waiver_enabled") == 0:
                return False, "Admin fee waiver is explicitly disabled in platform configuration."

            return True, f"Authorized Platform Administrator Billing Exemption ({user['email']}, role={user['role']})"
        finally:
            if should_close:
                conn.close()

    @staticmethod
    def get_user_fee_policy(user_id: str) -> Dict[str, Any]:
        conn = get_db_connection()
        try:
            row = conn.execute("SELECT * FROM fee_policies WHERE user_id = ?", (user_id,)).fetchone()
            if not row:
                cfg = FeeEngine.get_platform_pricing_config()
                now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                policy_id = f"POL-{secrets.token_hex(4).upper()}"
                with conn:
                    conn.execute("""
                        INSERT INTO fee_policies (
                            policy_id, user_id, version, activation_fee_enabled, activation_fee_usd,
                            activation_fee_charged, execution_fee_enabled, execution_fee_usd,
                            ai_research_fee_enabled, ai_research_fee_usd, ai_research_fee_cents,
                            fee_waived, currency, updated_at
                        ) VALUES (?, ?, 1, 1, ?, 0, 1, ?, 1, ?, ?, 0, 'USD', ?)
                    """, (
                        policy_id,
                        user_id,
                        cfg["default_activation_fee_usd"],
                        cfg["default_execution_fee_usd"],
                        cfg["ai_analysis_price_usd"],
                        cfg["ai_analysis_price_cents"],
                        now_iso
                    ))
                row = conn.execute("SELECT * FROM fee_policies WHERE user_id = ?", (user_id,)).fetchone()
            from .pricing_service import apply_effective
            res = apply_effective(row, user_id, conn) or dict(row)
            if "ai_research_fee_cents" not in res or res["ai_research_fee_cents"] is None:
                res["ai_research_fee_cents"] = int(round(float(res.get("ai_research_fee_usd", 1.00)) * 100))
            is_admin_waived, admin_reason = FeeEngine.is_admin_fee_waiver_active(user_id, conn=conn)
            if is_admin_waived:
                res["is_admin_exempt"] = True
                res["fee_waived"] = 1
                res["activation_fee_charged"] = 1
                res["activation_fee_enabled"] = 0
                res["execution_fee_enabled"] = 0
                res["ai_research_fee_enabled"] = 0
                res["waiver_reason"] = admin_reason
            else:
                res["is_admin_exempt"] = False
            return res
        finally:
            conn.close()

    @staticmethod
    def update_user_fee_policy(
        user_id: str,
        actor_id: str,
        activation_fee_enabled: Optional[bool] = None,
        activation_fee_usd: Optional[float] = None,
        execution_fee_enabled: Optional[bool] = None,
        execution_fee_usd: Optional[float] = None,
        ai_research_fee_enabled: Optional[bool] = None,
        ai_research_fee_usd: Optional[float] = None,
        ai_research_fee_cents: Optional[int] = None,
        ai_research_fee_waived: Optional[bool] = None,
        fee_waived: Optional[bool] = None,
        waiver_reason: Optional[str] = None
    ) -> Dict[str, Any]:
        conn = get_db_connection()
        try:
            current = FeeEngine.get_user_fee_policy(user_id)
            new_version = current["version"] + 1
            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            new_act_enabled = current["activation_fee_enabled"] if activation_fee_enabled is None else (1 if activation_fee_enabled else 0)
            new_act_usd = current["activation_fee_usd"] if activation_fee_usd is None else float(activation_fee_usd)
            new_exec_enabled = current["execution_fee_enabled"] if execution_fee_enabled is None else (1 if execution_fee_enabled else 0)
            new_exec_usd = current["execution_fee_usd"] if execution_fee_usd is None else float(execution_fee_usd)
            new_ai_enabled = current.get("ai_research_fee_enabled", 1) if ai_research_fee_enabled is None else (1 if ai_research_fee_enabled else 0)

            if ai_research_fee_cents is not None:
                new_ai_cents = max(0, int(ai_research_fee_cents))
                new_ai_usd = round(new_ai_cents / 100.0, 2)
            elif ai_research_fee_usd is not None:
                new_ai_usd = round(max(0.0, float(ai_research_fee_usd)), 2)
                new_ai_cents = int(round(new_ai_usd * 100))
            else:
                new_ai_usd = float(current.get("ai_research_fee_usd", 1.00))
                new_ai_cents = int(round(new_ai_usd * 100))

            new_ai_waived = current.get("ai_research_fee_waived", 0) if ai_research_fee_waived is None else (1 if ai_research_fee_waived else 0)
            new_waived = current["fee_waived"] if fee_waived is None else (1 if fee_waived else 0)
            new_waiver_reason = waiver_reason if waiver_reason is not None else current.get("waiver_reason")

            with conn:
                conn.execute("""
                    UPDATE fee_policies
                    SET version = ?,
                        activation_fee_enabled = ?,
                        activation_fee_usd = ?,
                        execution_fee_enabled = ?,
                        execution_fee_usd = ?,
                        ai_research_fee_enabled = ?,
                        ai_research_fee_usd = ?,
                        ai_research_fee_cents = ?,
                        ai_research_fee_waived = ?,
                        fee_waived = ?,
                        waiver_reason = ?,
                        updated_at = ?
                    WHERE user_id = ?
                """, (new_version, new_act_enabled, new_act_usd, new_exec_enabled, new_exec_usd, new_ai_enabled, new_ai_usd, new_ai_cents, new_ai_waived, new_waived, new_waiver_reason, now_iso, user_id))

                log_id = f"AUD-{secrets.token_hex(6).upper()}"
                details = json.dumps({
                    "actor": actor_id,
                    "old_version": current["version"],
                    "new_version": new_version,
                    "exec_fee": new_exec_usd,
                    "act_fee": new_act_usd,
                    "ai_fee_usd": new_ai_usd,
                    "ai_fee_cents": new_ai_cents,
                    "waived": new_waived
                })
                conn.execute("""
                    INSERT INTO audit_logs (log_id, actor_id, action, target_user_id, details_json, created_at)
                    VALUES (?, ?, 'FEE_POLICY_UPDATED', ?, ?, ?)
                """, (log_id, actor_id, user_id, details, now_iso))

            return FeeEngine.get_user_fee_policy(user_id)
        finally:
            conn.close()

    @staticmethod
    def get_billing_account(user_id: str) -> Dict[str, Any]:
        conn = get_db_connection()
        try:
            row = conn.execute("SELECT * FROM billing_accounts WHERE user_id = ?", (user_id,)).fetchone()
            if not row:
                now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                acct_id = f"BAC-{secrets.token_hex(4).upper()}"
                with conn:
                    conn.execute("""
                        INSERT INTO billing_accounts (account_id, user_id, prepaid_credits_usd, total_deposited_usd, total_fees_paid_usd, updated_at)
                        VALUES (?, ?, 0.0, 0.0, 0.0, ?)
                    """, (acct_id, user_id, now_iso))
                row = conn.execute("SELECT * FROM billing_accounts WHERE user_id = ?", (user_id,)).fetchone()
            res = dict(row)
            res["prepaid_credits_cents"] = int(round(float(res.get("prepaid_credits_usd", 0.0)) * 100))
            is_admin_waived, admin_reason = FeeEngine.is_admin_fee_waiver_active(user_id, conn=conn)
            res["is_admin_exempt"] = is_admin_waived
            if is_admin_waived:
                res["admin_exemption_reason"] = admin_reason
            return res
        finally:
            conn.close()

    # ─── Requirement 4: Independent AI Analysis & Pay-Per-Use Credits ───

    @staticmethod
    def get_effective_ai_analysis_price(user_id: str) -> Dict[str, Any]:
        policy = FeeEngine.get_user_fee_policy(user_id)
        acct = FeeEngine.get_billing_account(user_id)
        global_cfg = FeeEngine.get_platform_pricing_config()

        balance_usd = round(float(acct.get("prepaid_credits_usd", 0.0)), 2)
        balance_cents = int(round(balance_usd * 100))

        is_admin_waived, admin_reason = FeeEngine.is_admin_fee_waiver_active(user_id)
        if is_admin_waived:
            waived = True
            price_usd = 0.0
            price_cents = 0
            eligible = True
            shortfall_usd = 0.0
            billing_disclosure = f"Administrator Billing Exemption: Zero fees deducted for authorized administrative analysis ({admin_reason})."
        else:
            waived = bool(policy.get("fee_waived") or policy.get("ai_research_fee_waived") or not policy.get("ai_research_fee_enabled", 1))
            if waived:
                price_usd = 0.0
                price_cents = 0
            else:
                from .pricing_service import resolve as resolve_pricing
                eff_pricing = resolve_pricing(user_id, "AI_ANALYSIS")
                price_usd = eff_pricing["price_usd"]
                price_cents = int(round(price_usd * 100))
            eligible = balance_cents >= price_cents
            shortfall_usd = round(max(0.0, price_usd - balance_usd), 2)
            billing_disclosure = (
                f"Each AI Market Intelligence Analysis run deducts ${price_usd:.2f} USD ({price_cents} cents) "
                f"from your prepaid Bitdex credit balance upon execution. If an analysis fails before producing a "
                f"valid intelligence report, the charge is automatically refunded to your prepaid balance."
            )

        return {
            "user_id": user_id,
            "price_usd": price_usd,
            "price_cents": price_cents,
            "fee_waived": waived,
            "prepaid_balance_usd": balance_usd,
            "prepaid_balance_cents": balance_cents,
            "eligible": eligible,
            "shortfall_usd": shortfall_usd,
            "currency": "USD",
            "policy_version": policy.get("version", 1),
            "billing_disclosure": billing_disclosure
        }

    @staticmethod
    def charge_and_record_ai_analysis(
        user_id: str,
        idempotency_key: str,
        symbol: str,
        market: str = "CRYPTO",
        timeframe: str = "1h",
        model_id: str = "bitdex-quant-v2"
    ) -> Dict[str, Any]:
        """
        Atomically verifies customer balance, prevents duplicate charges via idempotency_key,
        deducts credits in a single SQLite BEGIN IMMEDIATE transaction, writes the billing_ledger
        entry, and records the ai_analysis_runs row.
        Includes authoritative server-side billing exemptions for administrators.
        """
        if not idempotency_key or len(idempotency_key.strip()) < 4:
            raise HTTPException(status_code=400, detail="A unique idempotency_key is required for billable AI analysis.")

        clean_idem = f"AI_ANALYSIS:{user_id}:{idempotency_key.strip()}"
        conn = get_db_connection()
        try:
            conn.execute("BEGIN IMMEDIATE;")

            # 1. Check idempotency in ai_analysis_runs first
            existing_run = conn.execute(
                "SELECT * FROM ai_analysis_runs WHERE idempotency_key = ?",
                (clean_idem,)
            ).fetchone()
            if existing_run:
                conn.commit()
                r_dict = dict(existing_run)
                r_dict["is_duplicate"] = True
                return r_dict

            # 2. Check user status
            user = conn.execute("SELECT status FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if not user:
                conn.rollback()
                raise HTTPException(status_code=404, detail="Customer account not found.")
            if user["status"] in ("BLOCKED", "SUSPENDED", "TEMPORARY_HOLD"):
                conn.rollback()
                raise HTTPException(status_code=403, detail=f"AI Analysis blocked: Account status is {user['status']}.")

            # 3. Determine authoritative price inside transaction
            is_admin_waived, admin_reason = FeeEngine.is_admin_fee_waiver_active(user_id, conn=conn)
            policy = conn.execute("SELECT * FROM fee_policies WHERE user_id = ?", (user_id,)).fetchone()
            global_cfg = conn.execute("SELECT * FROM platform_pricing_config WHERE config_key = 'GLOBAL_DEFAULT'").fetchone()
            default_price_usd = float(global_cfg["ai_analysis_price_usd"]) if global_cfg else 1.00

            if is_admin_waived:
                price_usd = 0.0
                price_cents = 0
                policy_version = int(policy["version"]) if policy else 1
            else:
                waived = bool(policy and (policy["fee_waived"] or policy["ai_research_fee_waived"] or not policy["ai_research_fee_enabled"]))
                if waived:
                    price_usd = 0.0
                    price_cents = 0
                    policy_version = int(policy["version"]) if policy else 1
                else:
                    from .pricing_service import resolve as resolve_pricing
                    eff_pricing = resolve_pricing(user_id, "AI_ANALYSIS", conn=conn)
                    price_usd = eff_pricing["price_usd"]
                    price_cents = int(round(price_usd * 100))
                    policy_version = int(policy["version"]) if policy else 1

            acct = conn.execute("SELECT prepaid_credits_usd FROM billing_accounts WHERE user_id = ?", (user_id,)).fetchone()
            cur_balance = round(float(acct["prepaid_credits_usd"]) if acct else 0.0, 2)
            cur_balance_cents = int(round(cur_balance * 100))

            if not is_admin_waived and cur_balance_cents < price_cents:
                conn.rollback()
                raise HTTPException(
                    status_code=402,
                    detail=f"Insufficient prepaid credits for AI Analysis (${cur_balance:.2f} available, ${price_usd:.2f} required). Please top up your prepaid balance."
                )

            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            run_id = f"AIR-{secrets.token_hex(6).upper()}"
            entry_id = f"LED-{secrets.token_hex(6).upper()}"

            if is_admin_waived:
                new_balance = cur_balance
                entry_id = "ADMIN_WAIVED"
                audit_id = f"AUD-{secrets.token_hex(6).upper()}"
                conn.execute("""
                    INSERT INTO audit_logs (log_id, actor_id, action, target_user_id, details_json, created_at)
                    VALUES (?, ?, 'ADMIN_FEE_WAIVED', ?, ?, ?)
                """, (audit_id, user_id, user_id, json.dumps({
                    "fee_type": "AI_ANALYSIS",
                    "symbol": symbol.upper(),
                    "market": market.upper(),
                    "waived_usd": default_price_usd,
                    "reason": admin_reason
                }), now_iso))
            elif price_cents > 0:
                conn.execute("""
                    UPDATE billing_accounts
                    SET prepaid_credits_usd = round(prepaid_credits_usd - ?, 2),
                        total_fees_paid_usd = round(total_fees_paid_usd + ?, 2),
                        updated_at = ?
                    WHERE user_id = ?
                """, (price_usd, price_usd, now_iso, user_id))

                updated_acct = conn.execute("SELECT prepaid_credits_usd FROM billing_accounts WHERE user_id = ?", (user_id,)).fetchone()
                new_balance = round(float(updated_acct["prepaid_credits_usd"]), 2)

                desc = f"Bitdex AI Market Analysis Fee for {symbol.upper()} ({market.upper()} {timeframe})"
                conn.execute("""
                    INSERT INTO billing_ledger (
                        entry_id, user_id, entry_type, amount_usd, balance_after_usd,
                        idempotency_key, billable_order_ref, fill_ref, evidence_source,
                        policy_version, status, description, created_at
                    ) VALUES (?, ?, 'AI_RESEARCH_FEE', ?, ?, ?, ?, ?, 'BITDEX_AI_ENGINE', ?, 'POSTED', ?, ?)
                """, (
                    entry_id, user_id, price_usd, new_balance,
                    f"LEDGER:{clean_idem}", f"AI_RUN:{run_id}", None,
                    policy_version, desc, now_iso
                ))
            else:
                new_balance = cur_balance
                entry_id = "WAIVED"

            conn.execute("""
                INSERT INTO ai_analysis_runs (
                    run_id, user_id, symbol, market, timeframe, idempotency_key,
                    charged_amount_usd, charged_amount_cents, ledger_entry_id,
                    status, model_id, provider_tokens_used, provider_estimated_cost_usd,
                    created_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'RUNNING', ?, 0, 0.0, ?, ?)
            """, (
                run_id, user_id, symbol.upper(), market.upper(), timeframe,
                clean_idem, price_usd, price_cents, entry_id, model_id, now_iso, now_iso
            ))

            row = conn.execute("SELECT * FROM ai_analysis_runs WHERE run_id = ?", (run_id,)).fetchone()
            conn.commit()
            res = dict(row)
            res["balance_after_usd"] = new_balance
            res["is_duplicate"] = False
            return res
        except HTTPException:
            raise
        except Exception as e:
            conn.rollback()
            logger.error(f"Error charging AI analysis for {user_id}: {e}")
            raise
        finally:
            conn.close()

    @staticmethod
    def complete_ai_analysis_run(
        run_id: str,
        result_dict: Dict[str, Any],
        provider_tokens_used: int = 0,
        provider_estimated_cost_usd: float = 0.0
    ) -> Dict[str, Any]:
        """Marks an AI analysis run as COMPLETED and stores provider token telemetry separately from customer fee."""
        conn = get_db_connection()
        try:
            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            with conn:
                conn.execute("""
                    UPDATE ai_analysis_runs
                    SET status = 'COMPLETED',
                        result_json = ?,
                        provider_tokens_used = ?,
                        provider_estimated_cost_usd = ?,
                        completed_at = ?
                    WHERE run_id = ?
                """, (json.dumps(result_dict), int(provider_tokens_used), float(provider_estimated_cost_usd), now_iso, run_id))
                row = conn.execute("SELECT * FROM ai_analysis_runs WHERE run_id = ?", (run_id,)).fetchone()
            return dict(row) if row else {}
        finally:
            conn.close()

    @staticmethod
    def refund_failed_ai_analysis(
        run_id: str,
        user_id: str,
        error_message: str = "AI analysis execution failed before producing a valid result."
    ) -> Dict[str, Any]:
        """
        Requirement 4 Rollback / Refund Policy:
        If an AI analysis fails before producing a valid result, automatically credits back
        the customer's prepaid balance and records an auditable REFUND ledger entry.
        """
        refund_idem = f"REFUND:AI_ANALYSIS:{run_id}"
        conn = get_db_connection()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            run_row = conn.execute("SELECT * FROM ai_analysis_runs WHERE run_id = ? AND user_id = ?", (run_id, user_id)).fetchone()
            if not run_row:
                conn.rollback()
                return {"status": "NOT_FOUND"}

            if run_row["status"] == "FAILED_REFUNDED":
                conn.commit()
                return dict(run_row)

            charged_usd = round(float(run_row["charged_amount_usd"]), 2)
            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            refund_entry_id = ""

            if charged_usd > 0:
                existing_refund = conn.execute("SELECT * FROM billing_ledger WHERE idempotency_key = ?", (refund_idem,)).fetchone()
                if not existing_refund:
                    conn.execute("""
                        UPDATE billing_accounts
                        SET prepaid_credits_usd = round(prepaid_credits_usd + ?, 2),
                            total_fees_paid_usd = round(max(0.0, total_fees_paid_usd - ?), 2),
                            updated_at = ?
                        WHERE user_id = ?
                    """, (charged_usd, charged_usd, now_iso, user_id))

                    acct = conn.execute("SELECT prepaid_credits_usd FROM billing_accounts WHERE user_id = ?", (user_id,)).fetchone()
                    new_bal = round(float(acct["prepaid_credits_usd"]), 2) if acct else charged_usd

                    refund_entry_id = f"LED-{secrets.token_hex(6).upper()}"
                    desc = f"Automatic refund for failed AI Analysis {run_id} ({run_row['symbol']})"
                    conn.execute("""
                        INSERT INTO billing_ledger (
                            entry_id, user_id, entry_type, amount_usd, balance_after_usd,
                            idempotency_key, billable_order_ref, fill_ref, evidence_source,
                            policy_version, status, description, created_at
                        ) VALUES (?, ?, 'AI_RESEARCH_REFUND', ?, ?, ?, ?, ?, 'BITDEX_AUTO_REFUND', 1, 'POSTED', ?, ?)
                    """, (refund_entry_id, user_id, charged_usd, new_bal, refund_idem, run_id, run_row["symbol"], desc, now_iso))

            conn.execute("""
                UPDATE ai_analysis_runs
                SET status = 'FAILED_REFUNDED',
                    refund_entry_id = ?,
                    error_message = ?,
                    completed_at = ?
                WHERE run_id = ?
            """, (refund_entry_id, error_message[:300], now_iso, run_id))

            updated_run = conn.execute("SELECT * FROM ai_analysis_runs WHERE run_id = ?", (run_id,)).fetchone()
            conn.commit()
            return dict(updated_run)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def get_user_ai_analysis_history(user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        conn = get_db_connection()
        try:
            rows = conn.execute("""
                SELECT * FROM ai_analysis_runs
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (user_id, limit)).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                if d.get("result_json"):
                    try:
                        d["result"] = json.loads(d["result_json"])
                    except Exception:
                        d["result"] = None
                out.append(d)
            return out
        finally:
            conn.close()

    @staticmethod
    def get_admin_ai_usage_summary() -> Dict[str, Any]:
        conn = get_db_connection()
        try:
            cfg = FeeEngine.get_platform_pricing_config()
            stats = conn.execute("""
                SELECT
                    COUNT(*) AS total_runs,
                    SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed_runs,
                    SUM(CASE WHEN status = 'FAILED_REFUNDED' THEN 1 ELSE 0 END) AS refunded_runs,
                    SUM(CASE WHEN status = 'COMPLETED' THEN charged_amount_usd ELSE 0.0 END) AS total_customer_revenue_usd,
                    SUM(provider_tokens_used) AS total_provider_tokens,
                    SUM(provider_estimated_cost_usd) AS total_provider_cost_usd
                FROM ai_analysis_runs
            """).fetchone()

            recent_runs = conn.execute("""
                SELECT r.*, u.email, u.username
                FROM ai_analysis_runs r
                LEFT JOIN users u ON r.user_id = u.user_id
                ORDER BY r.created_at DESC
                LIMIT 25
            """).fetchall()

            return {
                "pricing_config": cfg,
                "total_runs": int(stats["total_runs"] or 0),
                "completed_runs": int(stats["completed_runs"] or 0),
                "refunded_runs": int(stats["refunded_runs"] or 0),
                "total_customer_revenue_usd": round(float(stats["total_customer_revenue_usd"] or 0.0), 2),
                "total_provider_tokens": int(stats["total_provider_tokens"] or 0),
                "total_provider_cost_usd": round(float(stats["total_provider_cost_usd"] or 0.0), 4),
                "recent_runs": [dict(r) for r in recent_runs]
            }
        finally:
            conn.close()

    @staticmethod
    def add_prepaid_credits(
        user_id: str,
        amount_usd: float,
        payment_reference: str,
        evidence_source: str = "STRIPE_WEBHOOK"
    ) -> Dict[str, Any]:
        if amount_usd <= 0:
            raise HTTPException(status_code=400, detail="Credit amount must be greater than zero.")

        idempotency_key = f"TOPUP:{user_id}:{payment_reference}"
        conn = get_db_connection()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            existing = conn.execute("SELECT * FROM billing_ledger WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
            if existing:
                conn.commit()
                logger.info(f"Duplicate payment credit ignored via idempotency key {idempotency_key}")
                return dict(existing)

            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            conn.execute("""
                UPDATE billing_accounts
                SET prepaid_credits_usd = round(prepaid_credits_usd + ?, 2),
                    total_deposited_usd = round(total_deposited_usd + ?, 2),
                    updated_at = ?
                WHERE user_id = ?
            """, (amount_usd, amount_usd, now_iso, user_id))

            acct = conn.execute("SELECT prepaid_credits_usd FROM billing_accounts WHERE user_id = ?", (user_id,)).fetchone()
            new_balance = acct["prepaid_credits_usd"] if acct else amount_usd

            entry_id = f"LED-{secrets.token_hex(6).upper()}"
            conn.execute("""
                INSERT INTO billing_ledger (
                    entry_id, user_id, entry_type, amount_usd, balance_after_usd,
                    idempotency_key, billable_order_ref, evidence_source, status,
                    description, created_at
                ) VALUES (?, ?, 'CREDIT_TOPUP', ?, ?, ?, ?, ?, 'POSTED', ?, ?)
            """, (entry_id, user_id, amount_usd, new_balance, idempotency_key, payment_reference, evidence_source, f"Prepaid credit top-up of ${amount_usd:.2f} via {evidence_source}", now_iso))

            entry = conn.execute("SELECT * FROM billing_ledger WHERE entry_id = ?", (entry_id,)).fetchone()
            conn.commit()
            return dict(entry)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def assess_activation_fee(
        user_id: str,
        trigger_event: str = "FIRST_LIVE_ORDER",
        conn: Optional[sqlite3.Connection] = None
    ) -> Optional[Dict[str, Any]]:
        """Assesses one-time activation fee ($20.00 default) if enabled and not yet charged."""
        idempotency_key = f"ACT_FEE:{user_id}:ONCE_ONLY"
        should_close = False
        if conn is None:
            conn = get_db_connection()
            conn.execute("BEGIN IMMEDIATE;")
            should_close = True

        try:
            existing = conn.execute("SELECT * FROM billing_ledger WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
            if existing:
                if should_close:
                    conn.commit()
                return dict(existing)

            is_admin_waived, admin_reason = FeeEngine.is_admin_fee_waiver_active(user_id, conn=conn)
            if is_admin_waived:
                now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                conn.execute("""
                    UPDATE fee_policies
                    SET activation_fee_charged = 1, updated_at = ?
                    WHERE user_id = ?
                """, (now_iso, user_id))
                audit_id = f"AUD-{secrets.token_hex(6).upper()}"
                conn.execute("""
                    INSERT INTO audit_logs (log_id, actor_id, action, target_user_id, details_json, created_at)
                    VALUES (?, ?, 'ADMIN_FEE_WAIVED', ?, ?, ?)
                """, (audit_id, user_id, user_id, json.dumps({
                    "fee_type": "ACTIVATION_FEE",
                    "waived_usd": 20.0,
                    "reason": admin_reason
                }), now_iso))
                if should_close:
                    conn.commit()
                return {
                    "status": "ADMIN_EXEMPT",
                    "reason": admin_reason,
                    "fee_charged_usd": 0.0
                }

            policy = conn.execute("SELECT * FROM fee_policies WHERE user_id = ?", (user_id,)).fetchone()
            if not policy or not policy["activation_fee_enabled"] or policy["activation_fee_charged"] or policy["fee_waived"]:
                if should_close:
                    conn.commit()
                return None

            fee_amount = policy["activation_fee_usd"]
            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            conn.execute("""
                UPDATE billing_accounts
                SET prepaid_credits_usd = round(prepaid_credits_usd - ?, 2),
                    total_fees_paid_usd = round(total_fees_paid_usd + ?, 2),
                    updated_at = ?
                WHERE user_id = ?
            """, (fee_amount, fee_amount, now_iso, user_id))

            acct = conn.execute("SELECT prepaid_credits_usd FROM billing_accounts WHERE user_id = ?", (user_id,)).fetchone()
            new_balance = acct["prepaid_credits_usd"] if acct else -fee_amount

            conn.execute("""
                UPDATE fee_policies
                SET activation_fee_charged = 1, updated_at = ?
                WHERE user_id = ?
            """, (now_iso, user_id))

            entry_id = f"LED-{secrets.token_hex(6).upper()}"
            conn.execute("""
                INSERT INTO billing_ledger (
                    entry_id, user_id, entry_type, amount_usd, balance_after_usd,
                    idempotency_key, billable_order_ref, evidence_source, policy_version,
                    status, description, created_at
                ) VALUES (?, ?, 'ACTIVATION_FEE', ?, ?, ?, ?, 'PLATFORM_POLICY', ?, 'POSTED', ?, ?)
            """, (entry_id, user_id, -fee_amount, new_balance, idempotency_key, trigger_event, policy["version"], f"One-time activation fee of ${fee_amount:.2f}", now_iso))

            entry = conn.execute("SELECT * FROM billing_ledger WHERE entry_id = ?", (entry_id,)).fetchone()
            if should_close:
                conn.commit()
            return dict(entry)
        except Exception:
            if should_close:
                conn.rollback()
            raise
        finally:
            if should_close:
                conn.close()

    @staticmethod
    def assess_execution_fee(
        user_id: str,
        exchange: str,
        order_id: str,
        fill_id: Optional[str] = None,
        environment: str = "LIVE",
        execution_status: str = "FILLED",
        evidence_source: str = "EXCHANGE_FILL_REPORT",
        charge_demo: bool = False
    ) -> Dict[str, Any]:
        """
        EXACT BILLING RULE: ONE EXECUTION FEE PER UNIQUE QUALIFYING EXCHANGE ORDER.
        """
        if environment.upper() != "LIVE" and not charge_demo:
            return {
                "status": "EXEMPT_ENVIRONMENT",
                "reason": f"Orders in environment '{environment}' do not incur platform execution fees.",
                "fee_charged_usd": 0.0
            }

        if execution_status.upper() not in ("FILLED", "PARTIALLY_FILLED"):
            return {
                "status": "EXEMPT_STATUS",
                "reason": f"Order status '{execution_status}' is not a qualifying executed order.",
                "fee_charged_usd": 0.0
            }

        is_admin_waived, admin_reason = FeeEngine.is_admin_fee_waiver_active(user_id)
        if is_admin_waived:
            conn = get_db_connection()
            try:
                now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                audit_id = f"AUD-{secrets.token_hex(6).upper()}"
                with conn:
                    conn.execute("""
                        INSERT INTO audit_logs (log_id, actor_id, action, target_user_id, details_json, created_at)
                        VALUES (?, ?, 'ADMIN_FEE_WAIVED', ?, ?, ?)
                    """, (audit_id, user_id, user_id, json.dumps({
                        "fee_type": "EXECUTION_FEE",
                        "exchange": exchange.upper(),
                        "order_id": order_id,
                        "waived_usd": 0.30,
                        "reason": admin_reason
                    }), now_iso))
            finally:
                conn.close()
            return {
                "status": "ADMIN_EXEMPT",
                "reason": admin_reason,
                "fee_charged_usd": 0.0
            }

        policy = FeeEngine.get_user_fee_policy(user_id)
        if not policy["execution_fee_enabled"]:
            return {
                "status": "EXEMPT_POLICY_DISABLED",
                "reason": "Platform execution fees are disabled for this account.",
                "fee_charged_usd": 0.0
            }

        if policy["fee_waived"]:
            return {
                "status": "FEE_WAIVED",
                "reason": f"Execution fee waived: {policy.get('waiver_reason') or 'Administrative waiver active'}",
                "fee_charged_usd": 0.0
            }

        fee_amount = policy["execution_fee_usd"]
        if fee_amount <= 0.0:
            return {
                "status": "ZERO_FEE_RATE",
                "reason": "Configured execution fee rate is $0.00.",
                "fee_charged_usd": 0.0
            }

        idempotency_key = f"EXEC_FEE:{user_id}:{exchange.upper()}:{order_id}:PER_ORDER"
        conn = get_db_connection()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            existing = conn.execute("SELECT * FROM billing_ledger WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
            if existing:
                conn.commit()
                logger.info(f"Order {order_id} already assessed for execution fee. Suppressing duplicate charge on fill {fill_id}.")
                return {
                    "status": "ALREADY_ASSESSED",
                    "entry_id": existing["entry_id"],
                    "fee_charged_usd": abs(existing["amount_usd"]),
                    "balance_after_usd": existing["balance_after_usd"],
                    "is_duplicate": True
                }

            FeeEngine.assess_activation_fee(user_id, trigger_event=f"LIVE_ORDER_{order_id}", conn=conn)

            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            conn.execute("""
                UPDATE billing_accounts
                SET prepaid_credits_usd = round(prepaid_credits_usd - ?, 2),
                    total_fees_paid_usd = round(total_fees_paid_usd + ?, 2),
                    updated_at = ?
                WHERE user_id = ?
            """, (fee_amount, fee_amount, now_iso, user_id))

            acct = conn.execute("SELECT prepaid_credits_usd FROM billing_accounts WHERE user_id = ?", (user_id,)).fetchone()
            new_balance = acct["prepaid_credits_usd"] if acct else -fee_amount

            entry_id = f"LED-{secrets.token_hex(6).upper()}"
            desc = f"Bitdex Platform Execution Fee for {exchange} order {order_id} (fill {fill_id or 'primary'})"
            conn.execute("""
                INSERT INTO billing_ledger (
                    entry_id, user_id, entry_type, amount_usd, balance_after_usd,
                    idempotency_key, billable_order_ref, fill_ref, evidence_source,
                    policy_version, status, description, created_at
                ) VALUES (?, ?, 'EXECUTION_FEE', ?, ?, ?, ?, ?, ?, ?, 'POSTED', ?, ?)
            """, (entry_id, user_id, -fee_amount, new_balance, idempotency_key, order_id, fill_id, evidence_source, policy["version"], desc, now_iso))

            conn.commit()
            return {
                "status": "POSTED",
                "entry_id": entry_id,
                "fee_charged_usd": fee_amount,
                "balance_after_usd": new_balance,
                "is_duplicate": False
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def check_trading_preflight_eligibility(
        user_id: str,
        environment: str = "LIVE",
        estimated_orders_count: int = 1
    ) -> Tuple[bool, Optional[str]]:
        conn = get_db_connection()
        try:
            user = conn.execute("SELECT status, kyc_status FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if not user:
                return False, "User does not exist."

            if user["status"] == "BLOCKED":
                return False, "Trading blocked: Customer account has been blocked by an administrator."
            if user["status"] == "SUSPENDED":
                return False, "Trading suspended: Account status is suspended."

            # Authoritative Server-Side Admin Fee Waiver Check
            is_admin_waived, admin_reason = FeeEngine.is_admin_fee_waiver_active(user_id, conn=conn)
            if is_admin_waived:
                return True, None

            if environment.upper() == "LIVE":
                if user["kyc_status"] in ("REQUESTED", "PENDING"):
                    return False, "Trading blocked: KYC identity verification is required and currently pending."
                if user["kyc_status"] == "REJECTED":
                    return False, "Trading blocked: KYC identity verification was rejected."

            policy = FeeEngine.get_user_fee_policy(user_id)
            acct = FeeEngine.get_billing_account(user_id)
            cur_balance = acct.get("prepaid_credits_usd", 0.0)

            # 1. Activation check
            if policy.get("activation_fee_enabled") and not policy.get("activation_fee_charged") and not policy.get("fee_waived"):
                act_fee = float(policy.get("activation_fee_usd", 20.0))
                return False, f"Trading blocked: Account activation required (${act_fee:.2f}). Please activate your account."

            # 2. Execution Credit Check
            if policy.get("execution_fee_enabled") and not policy.get("fee_waived"):
                exec_fee = float(policy.get("execution_fee_usd", 0.30))
                orders_count = max(1, int(estimated_orders_count))
                required_exec = round(exec_fee * orders_count, 2)
                if cur_balance < required_exec:
                    return False, f"Trading blocked: Insufficient execution credits (${cur_balance:.2f} available, ${required_exec:.2f} required). Please top up credits."

            return True, None
        finally:
            conn.close()

    @staticmethod
    def get_ledger_history(user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        conn = get_db_connection()
        try:
            rows = conn.execute("""
                SELECT * FROM billing_ledger
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (user_id, limit)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

if __name__ == "__main__":
    print("FeeEngine loaded successfully.")
