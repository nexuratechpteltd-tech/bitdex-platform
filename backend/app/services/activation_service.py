"""
BITDEX One-Time $20.00 USD HFT Account Activation Service
=========================================================
Enforces the mandatory one-time USD $20.00 account activation fee before
High-Frequency Trading (HFT) execution, strategy configuration, or live/demo
HFT order placement is unlocked for any customer.

States:
- NOT_ACTIVATED
- PAYMENT_PENDING
- ACTIVE
- PAYMENT_FAILED
- REVOKED
"""

import hashlib
import hmac
import json
import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException

from .saas_db import get_db_connection

logger = logging.getLogger("tauric.activation_service")

ACTIVATION_FEE_USD: float = 20.00
ACTIVATION_CURRENCY: str = "USD"
VALID_STATUSES = {"NOT_ACTIVATED", "PAYMENT_PENDING", "ACTIVE", "PAYMENT_FAILED", "REVOKED"}
VALID_PROVIDERS = {"BINANCE_PAY", "STRIPE", "CRYPTO_USDT", "SANDBOX_SIGNED"}

_WEBHOOK_SECRET = os.getenv(
    "BITDEX_ACTIVATION_WEBHOOK_SECRET",
    "bitdex-hft-20usd-activation-hmac-key-2026-institutional"
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def compute_activation_signature(
    user_id: str,
    payment_reference: str,
    amount: float = ACTIVATION_FEE_USD,
    currency: str = ACTIVATION_CURRENCY,
) -> str:
    """Computes deterministic HMAC-SHA256 signature for $20 activation verification."""
    canonical = f"{user_id}:{payment_reference}:{float(amount):.2f}:{currency.upper().strip()}"
    return hmac.new(
        _WEBHOOK_SECRET.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def ensure_activation_tables(conn) -> None:
    """Ensures `hft_account_activations` and `hft_activation_webhooks` tables exist."""
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS hft_account_activations (
            activation_id TEXT PRIMARY KEY,
            user_id TEXT UNIQUE NOT NULL,
            activation_status TEXT NOT NULL DEFAULT 'NOT_ACTIVATED',
            activation_amount REAL NOT NULL DEFAULT 20.0,
            currency TEXT NOT NULL DEFAULT 'USD',
            payment_reference TEXT,
            payment_provider TEXT,
            activated_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS hft_activation_webhooks (
            event_id TEXT PRIMARY KEY,
            payment_reference TEXT NOT NULL,
            user_id TEXT NOT NULL,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            processed_at TEXT NOT NULL
        );
        """
    )
    conn.commit()


def _write_audit(conn, actor_id: str, action: str, target_user_id: str, details: Dict[str, Any]) -> None:
    try:
        log_id = f"AUD-ACT-{secrets.token_hex(6).upper()}"
        conn.execute(
            "INSERT INTO audit_logs (log_id, actor_id, action, target_user_id, details_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (log_id, actor_id, action, target_user_id, json.dumps(details), _now_iso()),
        )
    except Exception as exc:
        logger.warning(f"Audit log write warning in activation_service: {exc}")


def get_activation_status(conn, user_id: str, user_role: str = "CUSTOMER") -> Dict[str, Any]:
    """
    Returns authoritative HFT activation record for `user_id`.
    Admin/Owner accounts are automatically exempt and marked ACTIVE.
    """
    ensure_activation_tables(conn)
    role_upper = (user_role or "CUSTOMER").upper()
    if role_upper in ("ADMIN", "OWNER"):
        return {
            "activation_id": f"ACT-ADMIN-{user_id}",
            "user_id": user_id,
            "activation_status": "ACTIVE",
            "is_activated": True,
            "is_admin_exempt": True,
            "activation_amount": ACTIVATION_FEE_USD,
            "currency": ACTIVATION_CURRENCY,
            "payment_reference": "ADMIN_EXEMPT",
            "payment_provider": "ADMIN_EXEMPT",
            "activated_at": "2026-01-01T00:00:00Z",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": _now_iso(),
        }

    row = conn.execute(
        "SELECT * FROM hft_account_activations WHERE user_id = ?",
        (user_id,),
    ).fetchone()

    if not row:
        now = _now_iso()
        act_id = f"ACT-{secrets.token_hex(6).upper()}"
        conn.execute(
            "INSERT OR IGNORE INTO hft_account_activations "
            "(activation_id, user_id, activation_status, activation_amount, currency, payment_reference, payment_provider, activated_at, created_at, updated_at) "
            "VALUES (?, ?, 'NOT_ACTIVATED', ?, ?, NULL, NULL, NULL, ?, ?)",
            (act_id, user_id, ACTIVATION_FEE_USD, ACTIVATION_CURRENCY, now, now),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM hft_account_activations WHERE user_id = ?",
            (user_id,),
        ).fetchone()

    data = dict(row)
    data["is_activated"] = data.get("activation_status") == "ACTIVE"
    data["is_admin_exempt"] = False
    data["activation_amount"] = float(data.get("activation_amount", ACTIVATION_FEE_USD))
    return data


def create_activation_checkout(
    conn,
    user_id: str,
    provider: str = "BINANCE_PAY",
    user_role: str = "CUSTOMER",
) -> Dict[str, Any]:
    """
    Initiates a $20.00 USD one-time HFT account activation payment session.
    Transitions `NOT_ACTIVATED` or `PAYMENT_FAILED` -> `PAYMENT_PENDING`.
    """
    ensure_activation_tables(conn)
    current = get_activation_status(conn, user_id, user_role)
    if current["activation_status"] == "ACTIVE":
        return {
            "status": "ALREADY_ACTIVE",
            "message": "Your BITDEX HFT account is already activated.",
            "activation": current,
        }
    if current["activation_status"] == "REVOKED":
        raise HTTPException(
            status_code=403,
            detail={
                "error": "ACTIVATION_REVOKED",
                "message": "Your HFT account activation has been revoked by an administrator. Please contact BITDEX Support.",
            },
        )

    provider_clean = (provider or "BINANCE_PAY").upper().strip()
    if provider_clean not in VALID_PROVIDERS:
        provider_clean = "BINANCE_PAY"

    payment_ref = f"PAY-HFT20-{secrets.token_hex(6).upper()}"
    now = _now_iso()
    conn.execute(
        "UPDATE hft_account_activations "
        "SET activation_status = 'PAYMENT_PENDING', "
        "    activation_amount = ?, "
        "    currency = ?, "
        "    payment_reference = ?, "
        "    payment_provider = ?, "
        "    updated_at = ? "
        "WHERE user_id = ?",
        (ACTIVATION_FEE_USD, ACTIVATION_CURRENCY, payment_ref, provider_clean, now, user_id),
    )
    _write_audit(
        conn,
        actor_id=user_id,
        action="HFT_ACTIVATION_CHECKOUT_INITIATED",
        target_user_id=user_id,
        details={
            "payment_reference": payment_ref,
            "provider": provider_clean,
            "amount_usd": ACTIVATION_FEE_USD,
            "currency": ACTIVATION_CURRENCY,
        },
    )
    conn.commit()

    updated = get_activation_status(conn, user_id, user_role)
    signature = compute_activation_signature(user_id, payment_ref, ACTIVATION_FEE_USD, ACTIVATION_CURRENCY)

    return {
        "status": "SUCCESS",
        "message": "One-time $20.00 USD HFT activation checkout created.",
        "activation": updated,
        "checkout": {
            "payment_reference": payment_ref,
            "amount": ACTIVATION_FEE_USD,
            "currency": ACTIVATION_CURRENCY,
            "provider": provider_clean,
            "description": "BITDEX One-Time High-Frequency Trading (HFT) Account Activation",
            "verification_signature": signature,
            "expires_in_seconds": 1800,
        },
    }


def verify_and_complete_activation(
    conn,
    user_id: str,
    payment_reference: str,
    amount: float,
    currency: str,
    signature: str,
    provider: Optional[str] = None,
    event_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Verifies a signed $20.00 USD payment proof or webhook callback and transitions
    the customer's HFT activation status to `ACTIVE`.
    """
    ensure_activation_tables(conn)

    if not payment_reference or not payment_reference.strip():
        raise HTTPException(
            status_code=400,
            detail={"error": "MISSING_PAYMENT_REFERENCE", "message": "A valid payment_reference is required."},
        )

    payment_reference = payment_reference.strip()

    # 1. Check webhook idempotency if event_id is supplied
    if event_id:
        existing_evt = conn.execute(
            "SELECT * FROM hft_activation_webhooks WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        if existing_evt:
            act = get_activation_status(conn, user_id)
            return {
                "status": "SUCCESS",
                "idempotent_replay": True,
                "message": "Webhook event already processed idempotently.",
                "activation": act,
            }

    # 2. Check payment_reference ownership (prevent cross-tenant reuse)
    ref_owner = conn.execute(
        "SELECT * FROM hft_account_activations WHERE payment_reference = ?",
        (payment_reference,),
    ).fetchone()

    if not ref_owner:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "PAYMENT_REFERENCE_NOT_FOUND",
                "message": f"Payment reference '{payment_reference}' was not found.",
            },
        )

    if ref_owner["user_id"] != user_id:
        _write_audit(
            conn,
            actor_id=user_id,
            action="HFT_ACTIVATION_CROSS_TENANT_ATTEMPT_BLOCKED",
            target_user_id=ref_owner["user_id"],
            details={"attempted_by": user_id, "payment_reference": payment_reference},
        )
        conn.commit()
        raise HTTPException(
            status_code=403,
            detail={
                "error": "CROSS_TENANT_PAYMENT_REFERENCE_FORBIDDEN",
                "message": "Security violation: Payment reference belongs to another customer account.",
            },
        )

    if ref_owner["activation_status"] == "REVOKED":
        raise HTTPException(
            status_code=403,
            detail={
                "error": "ACTIVATION_REVOKED",
                "message": "Account activation is revoked and cannot be self-activated.",
            },
        )

    # 3. Validate Currency
    if (currency or "").upper().strip() != ACTIVATION_CURRENCY:
        conn.execute(
            "UPDATE hft_account_activations SET activation_status = 'PAYMENT_FAILED', updated_at = ? WHERE user_id = ?",
            (_now_iso(), user_id),
        )
        conn.commit()
        raise HTTPException(
            status_code=400,
            detail={
                "error": "INVALID_ACTIVATION_CURRENCY",
                "message": f"Invalid currency '{currency}'. Exactly {ACTIVATION_CURRENCY} is required.",
            },
        )

    # 4. Validate Exact $20.00 Amount
    try:
        numeric_amount = round(float(amount), 2)
    except (TypeError, ValueError):
        numeric_amount = -1.0

    if numeric_amount != ACTIVATION_FEE_USD:
        conn.execute(
            "UPDATE hft_account_activations SET activation_status = 'PAYMENT_FAILED', updated_at = ? WHERE user_id = ?",
            (_now_iso(), user_id),
        )
        _write_audit(
            conn,
            actor_id=user_id,
            action="HFT_ACTIVATION_INVALID_AMOUNT",
            target_user_id=user_id,
            details={"received_amount": amount, "required_amount": ACTIVATION_FEE_USD, "payment_reference": payment_reference},
        )
        conn.commit()
        raise HTTPException(
            status_code=400,
            detail={
                "error": "INVALID_ACTIVATION_AMOUNT",
                "message": f"Invalid activation payment amount (${numeric_amount:.2f}). Exactly ${ACTIVATION_FEE_USD:.2f} USD is required.",
            },
        )

    # 5. Verify cryptographic HMAC signature
    expected_sig = compute_activation_signature(user_id, payment_reference, ACTIVATION_FEE_USD, ACTIVATION_CURRENCY)
    if not signature or not hmac.compare_digest(signature.strip(), expected_sig):
        conn.execute(
            "UPDATE hft_account_activations SET activation_status = 'PAYMENT_FAILED', updated_at = ? WHERE user_id = ?",
            (_now_iso(), user_id),
        )
        _write_audit(
            conn,
            actor_id=user_id,
            action="HFT_ACTIVATION_SIGNATURE_REJECTED",
            target_user_id=user_id,
            details={"payment_reference": payment_reference},
        )
        conn.commit()
        raise HTTPException(
            status_code=400,
            detail={
                "error": "INVALID_PAYMENT_SIGNATURE",
                "message": "Cryptographic payment verification failed: invalid or forged signature.",
            },
        )

    # 6. If already ACTIVE for this reference, return idempotently
    now = _now_iso()
    if ref_owner["activation_status"] == "ACTIVE":
        if event_id:
            conn.execute(
                "INSERT OR IGNORE INTO hft_activation_webhooks (event_id, payment_reference, user_id, status, payload_json, processed_at) "
                "VALUES (?, ?, ?, 'IDEMPOTENT_ACTIVE', ?, ?)",
                (event_id, payment_reference, user_id, json.dumps({"amount": amount, "currency": currency}), now),
            )
            conn.commit()
        return {
            "status": "SUCCESS",
            "idempotent_replay": True,
            "message": "Account is already activated.",
            "activation": get_activation_status(conn, user_id),
        }

    # 7. Transition to ACTIVE
    final_provider = (provider or ref_owner["payment_provider"] or "BINANCE_PAY").upper()
    conn.execute(
        "UPDATE hft_account_activations "
        "SET activation_status = 'ACTIVE', "
        "    payment_provider = ?, "
        "    activated_at = ?, "
        "    updated_at = ? "
        "WHERE user_id = ?",
        (final_provider, now, now, user_id),
    )

    # Synchronize legacy fee_policies table if present
    try:
        conn.execute(
            "UPDATE fee_policies SET fee_paid = 1, updated_at = ? WHERE user_id = ?",
            (now, user_id),
        )
    except Exception:
        pass

    if event_id:
        conn.execute(
            "INSERT OR IGNORE INTO hft_activation_webhooks (event_id, payment_reference, user_id, status, payload_json, processed_at) "
            "VALUES (?, ?, ?, 'PROCESSED', ?, ?)",
            (event_id, payment_reference, user_id, json.dumps({"amount": amount, "currency": currency, "provider": final_provider}), now),
        )

    _write_audit(
        conn,
        actor_id=user_id,
        action="HFT_ACCOUNT_ACTIVATED",
        target_user_id=user_id,
        details={
            "payment_reference": payment_reference,
            "amount_usd": ACTIVATION_FEE_USD,
            "currency": ACTIVATION_CURRENCY,
            "provider": final_provider,
            "activated_at": now,
        },
    )
    conn.commit()

    return {
        "status": "SUCCESS",
        "idempotent_replay": False,
        "message": "Your BITDEX account is now ACTIVATED for High-Frequency Trading.",
        "activation": get_activation_status(conn, user_id),
    }


def admin_set_activation_status(
    conn,
    admin_user_id: str,
    target_user_id: str,
    new_status: str,
    reason: str,
) -> Dict[str, Any]:
    """Allows an administrator to activate, waive, or revoke a customer's HFT activation."""
    ensure_activation_tables(conn)
    clean_status = (new_status or "").upper().strip()
    if clean_status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid activation status '{clean_status}'.")

    _ = get_activation_status(conn, target_user_id)
    now = _now_iso()
    activated_at = now if clean_status == "ACTIVE" else None
    conn.execute(
        "UPDATE hft_account_activations "
        "SET activation_status = ?, "
        "    payment_provider = COALESCE(payment_provider, 'ADMIN_OVERRIDE'), "
        "    payment_reference = COALESCE(payment_reference, ?), "
        "    activated_at = COALESCE(?, activated_at), "
        "    updated_at = ? "
        "WHERE user_id = ?",
        (clean_status, f"ADM-OVR-{secrets.token_hex(4).upper()}", activated_at, now, target_user_id),
    )
    _write_audit(
        conn,
        actor_id=admin_user_id,
        action="HFT_ACTIVATION_ADMIN_OVERRIDE",
        target_user_id=target_user_id,
        details={"new_status": clean_status, "reason": reason},
    )
    conn.commit()
    return get_activation_status(conn, target_user_id)


def assert_hft_activated(user: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reusable server-side authorization gate for all HFT execution, configuration,
    and order submission endpoints.
    Raises HTTP 403 `ACCOUNT_ACTIVATION_REQUIRED` if the customer has not completed
    the one-time $20.00 USD HFT activation.
    """
    user_id = user.get("user_id")
    role = user.get("role", "CUSTOMER")
    conn = get_db_connection()
    try:
        act = get_activation_status(conn, user_id, role)
    finally:
        conn.close()

    if act.get("activation_status") != "ACTIVE":
        raise HTTPException(
            status_code=403,
            detail={
                "error": "ACCOUNT_ACTIVATION_REQUIRED",
                "message": "Your BITDEX account must be activated with a one-time $20.00 USD fee before High-Frequency Trading execution is unlocked.",
                "activation_status": act.get("activation_status", "NOT_ACTIVATED"),
                "activation_fee_usd": ACTIVATION_FEE_USD,
                "currency": ACTIVATION_CURRENCY,
            },
        )
    return act
