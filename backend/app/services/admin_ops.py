"""
BITDEX Admin Operations Service — Administrative controls, customer lifecycle, KYC, and direct communication.
"""
from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from .email_service import EmailService

email_svc = EmailService()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def audit(conn: sqlite3.Connection, actor_id: str, action: str, target_user_id: str, details: dict) -> str:
    """Write to audit_logs table. Returns log_id."""
    log_id = f"AUD-{secrets.token_hex(6).upper()}"
    now_iso = _now()
    conn.execute(
        "INSERT INTO audit_logs (log_id, actor_id, action, target_user_id, details_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (log_id, actor_id, action, target_user_id, json.dumps(details), now_iso)
    )
    return log_id


def _wrap_branded_email(subject: str, inner_html: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ background-color: #0A0A0E; color: #EAECEF; font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 40px; }}
    .email-container {{ max-width: 600px; margin: 0 auto; background: #121218; border: 1px solid #272735; border-radius: 12px; overflow: hidden; }}
    .email-header {{ background: #181822; padding: 24px 32px; border-bottom: 1px solid #272735; }}
    .logo-text {{ font-size: 20px; font-weight: 800; color: #FFFFFF; letter-spacing: 1px; }}
    .logo-accent {{ color: #00E5FF; }}
    .email-body {{ padding: 32px; font-size: 14px; line-height: 1.6; color: #94A3B8; }}
    .email-body h2 {{ color: #FFFFFF; font-size: 18px; margin-top: 0; }}
    .callout-box {{ background: #0A0A0E; border-left: 3px solid #F59E0B; padding: 16px; margin: 20px 0; border-radius: 4px; color: #EAECEF; font-size: 13px; }}
    .callout-danger {{ border-left-color: #F43F5E; }}
    .callout-success {{ border-left-color: #10B981; }}
    .email-footer {{ background: #0A0A0E; padding: 20px 32px; text-align: center; font-size: 12px; color: #64748B; border-top: 1px solid #272735; }}
  </style>
</head>
<body>
  <div class="email-container">
    <div class="email-header">
      <div class="logo-text">BIT<span class="logo-accent">DEX</span></div>
    </div>
    <div class="email-body">
      <h2>{subject}</h2>
      {inner_html}
    </div>
    <div class="email-footer">
      &copy; 2026 BITDEX &mdash; Institutional Digital Asset Intelligence.<br>
      Automated administrative notice.
    </div>
  </div>
</body>
</html>"""


def hold_customer(conn: sqlite3.Connection, actor_id: str, user_id: str, reason: str) -> Dict[str, Any]:
    user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="Customer not found.")
    if user["status"] == "DELETED":
        raise HTTPException(status_code=400, detail="Cannot place hold on deleted customer.")

    old_status = user["status"]
    target_status = "TEMPORARY_HOLD"
    now_iso = _now()

    conn.execute("UPDATE users SET status = ?, updated_at = ? WHERE user_id = ?", (target_status, now_iso, user_id))

    audit(conn, actor_id, "CUSTOMER_HOLD_PLACED", user_id, {
        "old_status": old_status,
        "new_status": target_status,
        "reason": reason
    })
    conn.commit()

    # Dispatch email notice
    email_body = f"""
    <p>Dear {user['first_name'] or 'Customer'},</p>
    <p>Your BITDEX account has been placed on <strong>temporary administrative hold</strong> pending compliance review.</p>
    <div class="callout-box">
        <strong>Reason:</strong> {reason}
    </div>
    <p>Trading execution and AI telemetry runs are temporarily paused while your account details remain securely preserved.</p>
    """
    html_content = _wrap_branded_email("Account Notice: Temporary Administrative Hold", email_body)
    try:
        email_svc.dispatch_email(recipient_email=user["email"], subject="BITDEX Account Notice: Temporary Hold", body_text=f"Account on hold: {reason}", body_html=html_content, email_type="ACCOUNT_HOLD", metadata={"subject": "BITDEX Account Notice: Temporary Hold", "reason": reason})
    except Exception as e:
        import logging
        logging.getLogger("bitdex.admin_ops").error(f"Failed to dispatch KYC email: {e}", exc_info=True)

    return {
        "user_id": user_id,
        "old_status": old_status,
        "new_status": target_status,
        "reason": reason
    }


def block_customer(conn: sqlite3.Connection, actor_id: str, user_id: str, reason: str) -> Dict[str, Any]:
    user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="Customer not found.")
    if user["status"] == "DELETED":
        raise HTTPException(status_code=400, detail="Cannot block deleted customer.")

    old_status = user["status"]
    target_status = "BLOCKED"
    now_iso = _now()

    conn.execute("UPDATE users SET status = ?, updated_at = ? WHERE user_id = ?", (target_status, now_iso, user_id))
    # Revoke sessions immediately
    conn.execute("UPDATE sessions SET revoked = 1 WHERE user_id = ?", (user_id,))

    audit(conn, actor_id, "CUSTOMER_BLOCKED", user_id, {
        "old_status": old_status,
        "new_status": target_status,
        "reason": reason
    })
    conn.commit()

    email_body = f"""
    <p>Dear {user['first_name'] or 'Customer'},</p>
    <p>Your BITDEX institutional account has been <strong>blocked</strong> by platform compliance administration.</p>
    <div class="callout-box callout-danger">
        <strong>Compliance Notice:</strong> {reason}
    </div>
    <p>Active trading sessions have been revoked. If you believe this action was taken in error, contact support.</p>
    """
    html_content = _wrap_branded_email("Account Notice: Access Suspended", email_body)
    try:
        email_svc.dispatch_email(recipient_email=user["email"], subject="BITDEX Account Notice: Access Suspended", body_text=f"Account blocked: {reason}", body_html=html_content, email_type="ACCOUNT_BLOCKED", metadata={"subject": "BITDEX Account Notice: Access Suspended", "reason": reason})
    except Exception:
        pass

    return {
        "user_id": user_id,
        "old_status": old_status,
        "new_status": target_status,
        "reason": reason
    }


def reactivate_customer(conn: sqlite3.Connection, actor_id: str, user_id: str, reason: str) -> Dict[str, Any]:
    user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="Customer not found.")
    if user["status"] == "DELETED":
        raise HTTPException(status_code=400, detail="Cannot reactivate deleted customer.")

    old_status = user["status"]
    target_status = "ACTIVE"
    now_iso = _now()

    conn.execute("UPDATE users SET status = ?, updated_at = ? WHERE user_id = ?", (target_status, now_iso, user_id))

    audit(conn, actor_id, "CUSTOMER_REACTIVATED", user_id, {
        "old_status": old_status,
        "new_status": target_status,
        "reason": reason
    })
    conn.commit()

    email_body = f"""
    <p>Dear {user['first_name'] or 'Customer'},</p>
    <p>Good news! Your BITDEX account administrative hold has been removed and full institutional trading privileges are restored.</p>
    <div class="callout-box callout-success">
        <strong>Status Update:</strong> {reason}
    </div>
    <p>You may log in and resume trading strategy operations immediately.</p>
    """
    html_content = _wrap_branded_email("Account Notice: Privileges Restored", email_body)
    try:
        email_svc.dispatch_email(recipient_email=user["email"], subject="BITDEX Account Notice: Privileges Restored", body_text=f"Account reactivated: {reason}", body_html=html_content, email_type="ACCOUNT_REACTIVATED", metadata={"subject": "BITDEX Account Notice: Privileges Restored", "reason": reason})
    except Exception:
        pass

    return {
        "user_id": user_id,
        "old_status": old_status,
        "new_status": target_status,
        "reason": reason
    }


def delete_customer(conn: sqlite3.Connection, actor_id: str, user_id: str, reason: str, confirm: bool = False) -> Dict[str, Any]:
    user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="Customer not found.")
    if user["status"] == "DELETED":
        raise HTTPException(status_code=400, detail="Customer is already deleted.")
    if user["role"] in ("ADMIN", "OWNER"):
        raise HTTPException(status_code=403, detail="Administrative accounts cannot be deleted through customer management.")

    if not confirm:
        raise HTTPException(status_code=409, detail={
            "code": "CONFIRMATION_REQUIRED",
            "message": f"Permanently delete customer {user['email']}? All active sessions and connections will be revoked. Resend with confirm=true.",
            "user_id": user_id,
            "email": user["email"]
        })

    now_iso = _now()
    user_dict = dict(user)
    # Mask secrets before audit logging snapshot
    user_dict.pop("password_hash", None)
    user_dict.pop("two_factor_secret", None)
    user_dict.pop("email_otp_hash", None)

    # 1. Update user record: append deleted suffix to email to free up original email address for re-registration
    original_email = user["email"]
    freed_email_tag = f"deleted_{secrets.token_hex(4)}_{original_email}"
    conn.execute(
        "UPDATE users SET status = 'DELETED', email = ?, updated_at = ? WHERE user_id = ?",
        (freed_email_tag, now_iso, user_id)
    )

    # 2. Revoke sessions
    conn.execute("UPDATE sessions SET revoked = 1 WHERE user_id = ?", (user_id,))

    # 3. Clean up active exchange connections
    conn.execute("DELETE FROM user_exchange_connections WHERE user_id = ?", (user_id,))

    # 4. Zero balance
    conn.execute("UPDATE billing_accounts SET prepaid_credits_usd = 0.0, updated_at = ? WHERE user_id = ?", (now_iso, user_id))

    # 5. Revoke pricing overrides
    conn.execute("UPDATE customer_pricing_overrides SET status = 'REVOKED', revoked_by = ?, revoked_at = ?, revoke_reason = 'Customer deleted' WHERE user_id = ? AND status = 'ACTIVE'", (actor_id, now_iso, user_id))

    # Audit entry
    audit(conn, actor_id, "CUSTOMER_DELETED", user_id, {
        "original_email": original_email,
        "reason": reason,
        "user_snapshot": user_dict
    })

    return {
        "user_id": user_id,
        "email_freed": original_email,
        "status": "DELETED",
        "reason": reason
    }


def request_kyc_documents(conn: sqlite3.Connection, actor_id: str, user_id: str, document_types: List[str], message: str) -> Dict[str, Any]:
    user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="Customer not found.")

    now_iso = _now()
    conn.execute("UPDATE users SET kyc_status = 'PENDING_DOCUMENTS', updated_at = ? WHERE user_id = ?", (now_iso, user_id))

    record_id = f"KYC-{secrets.token_hex(6).upper()}"
    conn.execute("""
        INSERT INTO kyc_records (record_id, user_id, status, provider, notes, created_at, updated_at)
        VALUES (?, ?, 'PENDING_DOCUMENTS', 'INTERNAL_ADMIN', ?, ?, ?)
    """, (record_id, user_id, f"Requested docs: {', '.join(document_types)}. Note: {message}", now_iso, now_iso))

    audit(conn, actor_id, "KYC_DOCUMENTS_REQUESTED", user_id, {
        "document_types": document_types,
        "message": message,
        "record_id": record_id
    })
    conn.commit()

    u_dict = dict(user)
    customer_name = f"{u_dict.get('first_name') or ''} {u_dict.get('last_name') or ''}".strip() or u_dict.get('username') or 'Valued Client'
    doc_list_html = "".join([f"<li style='margin-bottom: 8px; color: #EAECEF;'><strong>{doc}</strong></li>" for doc in document_types])
    
    email_body = f"""
    <p style="margin-top:0;">Dear {customer_name},</p>
    <p>To comply with institutional regulatory frameworks and platform risk policies, our Compliance &amp; Security Team requires updated verification documentation for your account.</p>
    
    <div style="background: #181822; border: 1px solid #272735; border-radius: 8px; padding: 16px; margin: 20px 0;">
      <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: #64748B; margin-bottom: 4px;">Account Identification</div>
      <div style="font-size: 14px; font-weight: 700; color: #00E5FF; font-family: monospace;">User ID: {user_id}</div>
      <div style="font-size: 13px; color: #94A3B8; margin-top: 2px;">Email: {user['email']}</div>
    </div>

    <h3 style="color: #FFFFFF; font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 24px; margin-bottom: 12px;">Required Documentation:</h3>
    <ul style="padding-left: 20px; line-height: 1.6;">{doc_list_html}</ul>

    <div class="callout-box" style="background: #0A0A0E; border-left: 3px solid #00E5FF; padding: 16px; margin: 20px 0; border-radius: 4px; color: #EAECEF;">
      <strong style="color: #00E5FF;">Administrator / Compliance Note:</strong><br>
      <span style="display: block; margin-top: 6px; color: #CBD5E1;">{message}</span>
    </div>

    <h3 style="color: #FFFFFF; font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 24px; margin-bottom: 12px;">Submission Specifications:</h3>
    <ul style="padding-left: 20px; line-height: 1.6; color: #94A3B8;">
      <li><strong>Accepted File Formats:</strong> PDF, JPEG, PNG</li>
      <li><strong>Maximum File Size:</strong> 10 MB per file</li>
      <li><strong>Image Quality:</strong> All corners visible, high resolution, unedited, legible text with no glare or blur</li>
    </ul>

    <h3 style="color: #FFFFFF; font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 24px; margin-bottom: 12px;">Submission Instructions:</h3>
    <p style="color: #94A3B8;">
      1. Log in to your BITDEX Portal and navigate to the <strong>Compliance &amp; Verification</strong> tab to securely upload your files.<br>
      2. Alternatively, forward your documents directly from your registered email address to <a href="mailto:kyc@bitdex.ltd" style="color: #00E5FF; text-decoration: none;">kyc@bitdex.ltd</a> quoting your User ID (<strong>{user_id}</strong>) in the subject line.
    </p>

    <p style="margin-top: 24px; color: #64748B; font-size: 12px; border-top: 1px solid #272735; padding-top: 16px;">
      If you require assistance, our institutional support desk is reachable at <a href="mailto:support@bitdex.ltd" style="color: #00E5FF; text-decoration: none;">support@bitdex.ltd</a>.
    </p>
    """
    html_content = _wrap_branded_email("Institutional Compliance: Documentation Required", email_body)
    try:
        docs_joined = ", ".join(document_types)
        email_svc.dispatch_email(
            recipient_email=user["email"],
            subject="BITDEX Verification: Institutional Document Request",
            body_text=f"Document request: {docs_joined}",
            body_html=html_content,
            email_type="KYC_REQUEST",
            metadata={
                "subject": "BITDEX Verification: Institutional Document Request",
                "document_types": document_types,
                "body_html": html_content
            }
        )
    except Exception:
        pass

    return {
        "user_id": user_id,
        "record_id": record_id,
        "kyc_status": "PENDING_DOCUMENTS",
        "document_types": document_types
    }


def send_admin_email(conn: sqlite3.Connection, actor_id: str, user_id: str, subject: str, body_html: str, email_type: str = "ADMIN_CUSTOM") -> Dict[str, Any]:
    user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="Customer not found.")

    html_content = _wrap_branded_email(subject, body_html)
    email_res = email_svc.dispatch_email(recipient_email=user["email"], subject=subject, body_text=body_html, body_html=html_content, email_type=email_type, metadata={"subject": subject, "body_html": html_content})
    dispatch_id = email_res.get("dispatch_id", "DISP-UNKNOWN") if isinstance(email_res, dict) else str(email_res)

    audit(conn, actor_id, "ADMIN_EMAIL_SENT", user_id, {
        "recipient_email": user["email"],
        "subject": subject,
        "email_type": email_type,
        "dispatch_id": dispatch_id
    })

    return {
        "user_id": user_id,
        "recipient_email": user["email"],
        "dispatch_id": dispatch_id,
        "subject": subject,
        "status": "DISPATCHED"
    }


def get_customer_audit_trail(conn: sqlite3.Connection, user_id: str, limit: int = 200) -> List[Dict[str, Any]]:
    rows = conn.execute("""
        SELECT * FROM audit_logs
        WHERE target_user_id = ? OR actor_id = ?
        ORDER BY created_at DESC LIMIT ?
    """, (user_id, user_id, limit)).fetchall()
    return [dict(r) for r in rows]


def get_customer_ai_usage(conn: sqlite3.Connection, user_id: str) -> Dict[str, Any]:
    stats = conn.execute("""
        SELECT
            COUNT(*) as total_runs,
            SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as completed_runs,
            SUM(CASE WHEN status = 'FAILED_REFUNDED' THEN 1 ELSE 0 END) as failed_runs,
            SUM(CASE WHEN status = 'COMPLETED' THEN customer_price_usd ELSE 0.0 END) as total_revenue_usd,
            SUM(provider_tokens_used) as total_tokens
        FROM ai_analysis_runs
        WHERE user_id = ?
    """, (user_id,)).fetchone()

    recent_runs = conn.execute("""
        SELECT run_id, symbol, market, timeframe, model_id, status, customer_price_usd, created_at, completed_at
        FROM ai_analysis_runs
        WHERE user_id = ?
        ORDER BY created_at DESC LIMIT 15
    """, (user_id,)).fetchall()

    return {
        "total_runs": int(stats["total_runs"] or 0),
        "completed_runs": int(stats["completed_runs"] or 0),
        "failed_runs": int(stats["failed_runs"] or 0),
        "total_revenue_usd": round(float(stats["total_revenue_usd"] or 0.0), 2),
        "total_tokens": int(stats["total_tokens"] or 0),
        "recent_runs": [dict(r) for r in recent_runs]
    }


def get_customer_connections(conn: sqlite3.Connection, user_id: str) -> List[Dict[str, Any]]:
    rows = conn.execute("""
        SELECT c.account_id, c.user_id, c.provider, c.exchange_name, c.label,
               c.environment, c.product_type, c.connection_status, c.verification_status,
               c.key_fingerprint, c.last_verified_at, c.created_at
        FROM user_exchange_connections c
        JOIN users u ON c.user_id = u.user_id
        WHERE c.user_id = ? AND u.role = 'CUSTOMER'
        ORDER BY c.created_at DESC
    """, (user_id,)).fetchall()
    return [dict(r) for r in rows]
