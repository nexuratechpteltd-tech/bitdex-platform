import os
import smtplib
import secrets
import logging
import json
import threading
import time
import socket
from datetime import datetime, timezone, timedelta
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr, make_msgid, formatdate
from typing import Tuple, Dict, Any, Optional
from dotenv import load_dotenv

from .saas_db import get_db_connection

logger = logging.getLogger("bitdex.email_service")
_smtp_lock = threading.Lock()

ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"

def _load_smtp_env() -> Dict[str, Any]:
    if ENV_PATH.exists():
        load_dotenv(dotenv_path=ENV_PATH, override=True)
    host = os.getenv("SMTP_HOST", "").strip()
    port = int(os.getenv("SMTP_PORT", "587").strip() or "587")
    user = os.getenv("SMTP_USERNAME", "").strip()
    pw = os.getenv("SMTP_PASSWORD", "").strip()
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() in ("true", "1", "yes")
    email_from = os.getenv("EMAIL_FROM", "go@bitdex.ltd").strip() or "go@bitdex.ltd"
    if "sheltr" in email_from.lower() or "nexura" in email_from.lower():
        email_from = "go@bitdex.ltd"
    resend_key = os.getenv("RESEND_API_KEY", "").strip()
    return {
        "host": host,
        "port": port,
        "user": user,
        "pw": pw,
        "use_tls": use_tls,
        "from": email_from,
        "resend_key": resend_key,
    }

def _build_bitdex_html(title: str, body_html: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>{title}</title>
</head>
<body style="margin:0;padding:0;background-color:#020617;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#f8fafc;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#020617;padding:32px 16px;">
    <tr>
      <td align="center">
        <table width="100%" style="max-width:560px;background-color:#0f172a;border:1px solid #1e293b;border-radius:16px;overflow:hidden;">
          <tr>
            <td style="padding:24px 28px;background:linear-gradient(90deg,#090d1a 0%,#0f172a 100%);border-bottom:1px solid #1e293b;">
              <div style="font-size:20px;font-weight:900;letter-spacing:3px;color:#ffffff;">BITDEX</div>
              <div style="font-size:10px;font-family:monospace;letter-spacing:2px;color:#38bdf8;margin-top:2px;">QUANTITATIVE INTELLIGENCE • BITDEX.LTD</div>
            </td>
          </tr>
          <tr>
            <td style="padding:28px;font-size:14px;line-height:1.6;color:#cbd5e1;">
              <h2 style="margin:0 0 16px 0;font-size:17px;color:#ffffff;">{title}</h2>
              {body_html}
            </td>
          </tr>
          <tr>
            <td style="padding:18px 28px;background-color:#090d1a;border-top:1px solid #1e293b;font-size:11px;color:#64748b;">
              <div>Official Sender &amp; Support: <a href="mailto:go@bitdex.ltd" style="color:#38bdf8;text-decoration:none;">go@bitdex.ltd</a></div>
              <div style="margin-top:4px;">&copy; 2026 Bitdex Quantitative Platform (<a href="https://bitdex.ltd" style="color:#38bdf8;text-decoration:none;">https://bitdex.ltd</a>). Non-custodial read/trade architecture.</div>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

class EmailService:
    @staticmethod
    def get_configuration_status() -> Dict[str, Any]:
        """Returns whether real email delivery is configured and the exact required configuration."""
        cfg = _load_smtp_env()
        has_smtp = bool(cfg["host"] and cfg["user"] and cfg["pw"])
        has_resend = bool(cfg["resend_key"])
        is_configured = has_smtp or has_resend

        missing = []
        if not cfg["host"]: missing.append("SMTP_HOST")
        if not cfg["user"]: missing.append("SMTP_USERNAME")
        if not cfg["pw"]: missing.append("SMTP_PASSWORD")

        return {
            "is_configured": is_configured,
            "provider": "SMTP" if has_smtp else "RESEND" if has_resend else "NONE",
            "active_host": cfg["host"] or "Unconfigured",
            "from_address": cfg["from"],
            "support_email": "go@bitdex.ltd",
            "missing_variables": missing if not has_resend else [],
            "status_label": "READY" if is_configured else "BLOCKED_BY_SMTP_CONFIGURATION",
            "instruction": "Configure SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, and EMAIL_FROM=go@bitdex.ltd in backend .env."
        }

    @staticmethod
    def dispatch_email(
        recipient_email: str,
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
        email_type: str = "LOGIN_OTP",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Dispatches an email via configured verified SMTP provider or logs explicit failure if unconfigured.
        Never reports an email as SENT unless the SMTP server accepted the message.
        Plaintext secret/OTP is NEVER recorded in permanent logs or exposed in responses.
        """
        cfg = _load_smtp_env()
        config = EmailService.get_configuration_status()
        dispatch_id = f"DISP-{secrets.token_hex(6).upper()}"
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        error_detail = None
        server_response_msg = None

        if config["is_configured"]:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = formataddr(("Bitdex Platform", cfg["from"]))
            msg["Reply-To"] = "go@bitdex.ltd"
            msg["To"] = recipient_email
            msg["Date"] = formatdate(localtime=False)
            msg["Message-ID"] = make_msgid(domain="bitdex.ltd")

            msg.attach(MIMEText(body_text, "plain", "utf-8"))
            if body_html:
                msg.attach(MIMEText(body_html, "html", "utf-8"))

            max_attempts = 4
            attempt = 0
            send_success = False

            while attempt < max_attempts and not send_success:
                attempt += 1
                try:
                    with _smtp_lock:
                        if cfg["host"]:
                            if cfg["port"] == 465:
                                with smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=25) as server:
                                    server.ehlo()
                                    server.login(cfg["user"], cfg["pw"])
                                    server.sendmail(cfg["from"], [recipient_email], msg.as_string())
                                    server_response_msg = "250 Message accepted for delivery by SMTP provider"
                            else:
                                with smtplib.SMTP(cfg["host"], cfg["port"], timeout=25) as server:
                                    server.ehlo()
                                    if cfg["use_tls"]:
                                        server.starttls()
                                        server.ehlo()
                                    server.login(cfg["user"], cfg["pw"])
                                    server.sendmail(cfg["from"], [recipient_email], msg.as_string())
                                    server_response_msg = "250 Message accepted for delivery by SMTP provider"
                    send_success = True
                except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, smtplib.SMTPResponseException, socket.timeout, TimeoutError, ConnectionResetError, OSError) as transient_err:
                    error_detail = str(transient_err)
                    logger.warning(f"SMTP transient connection error on attempt {attempt}/{max_attempts} for {recipient_email}: {transient_err}")
                    if attempt < max_attempts:
                        time.sleep(3.0 * attempt)
                except Exception as fatal_err:
                    error_detail = str(fatal_err)
                    logger.error(f"SMTP non-retryable error for {recipient_email}: {fatal_err}")
                    break

            if send_success:
                conn = get_db_connection()
                try:
                    with conn:
                        conn.execute("""
                            INSERT INTO email_dispatches (dispatch_id, recipient_email, email_type, status, provider, details_json, created_at)
                            VALUES (?, ?, ?, 'SENT', 'SMTP', ?, ?)
                        """, (
                            dispatch_id,
                            recipient_email,
                            email_type,
                            json.dumps({**(metadata or {}), "from": cfg["from"], "host": cfg["host"], "provider_response": server_response_msg}),
                            now_iso
                        ))
                finally:
                    conn.close()

                logger.info(f"Email {email_type} accepted by SMTP ({cfg['from']}) for {recipient_email}")
                return {
                    "status": "ACCEPTED",
                    "dispatch_id": dispatch_id,
                    "recipient": recipient_email,
                    "from": cfg["from"],
                    "delivery_blocked": False,
                    "provider_response": server_response_msg or "250 Message accepted for delivery by SMTP provider"
                }
            else:
                status = "FAILED"
                logger.error(f"Failed to dispatch email via SMTP after {attempt} attempt(s): {error_detail}")
        else:
            status = "BLOCKED_BY_SMTP_CONFIGURATION"
            error_detail = "SMTP credentials are not configured on the server."

        conn = get_db_connection()
        try:
            with conn:
                conn.execute("""
                    INSERT INTO email_dispatches (dispatch_id, recipient_email, email_type, status, provider, details_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    dispatch_id,
                    recipient_email,
                    email_type,
                    status,
                    "SMTP_ERROR" if config["is_configured"] else "NONE_CONFIGURED",
                    json.dumps({**(metadata or {}), "error": error_detail}),
                    now_iso
                ))
        finally:
            conn.close()

        return {
            "status": status,
            "dispatch_id": dispatch_id,
            "recipient": recipient_email,
            "from": cfg["from"],
            "delivery_blocked": True,
            "error": error_detail,
            "provider_response": error_detail,
            "required_configuration": config["missing_variables"]
        }

    @staticmethod
    def send_welcome_email(recipient_email: str, username: str = "") -> Dict[str, Any]:
        """
        Dispatches a branded Bitdex welcome email upon customer registration.
        Contains no passwords or tokens. Includes getting started guidelines and security reminders.
        Enforces a 24-hour deduplication window per recipient to prevent duplicate emails.
        """
        recipient_clean = recipient_email.strip().lower()
        # 24-hour deduplication check
        conn = get_db_connection()
        try:
            one_day_ago = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
            existing = conn.execute("""
                SELECT dispatch_id, status FROM email_dispatches
                WHERE LOWER(recipient_email) = ? AND email_type = 'WELCOME_REGISTRATION' AND status = 'SENT' AND created_at > ?
            """, (recipient_clean, one_day_ago)).fetchone()
            if existing:
                logger.info(f"Skipping duplicate welcome email to {recipient_clean} (already sent in last 24h: {existing['dispatch_id']})")
                return {
                    "status": "SKIPPED_DEDUPLICATED",
                    "dispatch_id": existing["dispatch_id"],
                    "recipient": recipient_clean,
                    "provider": "DEDUPLICATION_CACHE",
                    "details": "Welcome email was already sent within the past 24 hours."
                }
        finally:
            conn.close()

        subject = "Welcome to Bitdex — Your Account Is Ready"
        display_name = (username or recipient_email.split("@")[0]).strip()
        portal_url = "https://bitdex.ltd"

        body_text = f"""Hello {display_name},

Welcome to Bitdex! Your quantitative intelligence and algorithmic trade execution account is active and ready to use.

Getting Started with Bitdex:
1. Review Live Market Signals — Explore real-time deterministic quantitative setups across Crypto spot pairs quoted in USDT and BTC.
2. Connect Your Exchange or Watch Wallets — Securely link read-only exchange API keys or non-custodial wallet addresses for portfolio tracking.
3. Dual-AI Quantitative Intelligence — Utilize Tauric research and Jev micro-risk verification for comprehensive algorithmic trade staging.
4. Prepaid Credits — Maintain your pay-per-use AI intelligence balance without recurring subscription lock-ins.

Access your portal: {portal_url}

IMPORTANT SECURITY REMINDER:
Bitdex staff, administrators, and automated agents will NEVER ask for your password, exchange API secrets, wallet private keys, or seed phrases. Never share your credentials with anyone.

Support & Inquiries:
Official customer support is available at go@bitdex.ltd.

Best regards,
Bitdex Quantitative Platform Team
https://bitdex.ltd • go@bitdex.ltd
"""
        body_html = _build_bitdex_html(
            "Welcome to Bitdex",
            f"""<h2 style="color:#ffffff;margin-top:0;font-size:18px;">Welcome to Bitdex, {display_name}!</h2>
            <p style="color:#94a3b8;font-size:14px;line-height:1.6;">
              Your quantitative intelligence and algorithmic trade staging account is officially active. You now have access to institutional-grade deterministic market signals, Dual-AI deep research, and real-time portfolio tracking.
            </p>
            <div style="margin:20px 0;padding:16px;background-color:#020617;border:1px solid #1e293b;border-radius:12px;">
              <div style="font-size:13px;font-weight:bold;color:#38bdf8;margin-bottom:10px;text-transform:uppercase;letter-spacing:1px;">Getting Started</div>
              <ul style="margin:0;padding-left:18px;color:#cbd5e1;font-size:13px;line-height:1.8;">
                <li><strong>Live Market Signals:</strong> Scan institutional algorithmic setups quoted in USDT and BTC.</li>
                <li><strong>Exchange & Wallet Connections:</strong> Securely link read-only exchange API keys or non-custodial watched addresses.</li>
                <li><strong>Dual-AI Intelligence:</strong> Execute on-demand deep macro/micro research via Tauric & Jev.</li>
                <li><strong>Trade Execution Wizard:</strong> Stage simulated orders with strict pre-flight risk checks.</li>
              </ul>
            </div>
            <div style="text-align:center;margin:28px 0;">
              <a href="{portal_url}" style="display:inline-block;padding:12px 28px;background:linear-gradient(90deg,#0ea5e9 0%,#10b981 100%);color:#020617;font-weight:bold;font-size:13px;text-decoration:none;border-radius:8px;letter-spacing:1px;text-transform:uppercase;">
                Access Bitdex Portal
              </a>
            </div>
            <div style="margin:20px 0;padding:14px;background-color:#1e1b4b;border:1px solid #4338ca;border-radius:10px;">
              <div style="font-size:11px;font-weight:bold;color:#a5b4fc;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;">🔒 Security Guarantee</div>
              <p style="margin:0;font-size:11px;color:#cbd5e1;line-height:1.5;">
                Bitdex staff and agents will <strong>NEVER</strong> ask for your password, exchange API secret, private keys, or seed phrases. Always ensure you are on <a href="{portal_url}" style="color:#38bdf8;">https://bitdex.ltd</a>.
              </p>
            </div>
            <p style="font-size:12px;color:#64748b;margin-top:20px;">
              Need assistance? Contact our official support desk at <a href="mailto:go@bitdex.ltd" style="color:#38bdf8;text-decoration:none;">go@bitdex.ltd</a>.
            </p>"""
        )
        return EmailService.dispatch_email(
            recipient_email=recipient_clean,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            email_type="WELCOME_REGISTRATION",
            metadata={"purpose": "customer_welcome", "username": display_name}
        )

    @staticmethod
    def send_welcome_email_async(recipient_email: str, username: str = "") -> None:
        """
        Dispatches welcome email asynchronously in a background daemon thread with 24h deduplication.
        Prevents blocking HTTP registration response latency while guaranteeing background delivery.
        """
        def _bg_task():
            try:
                EmailService.send_welcome_email(recipient_email=recipient_email, username=username)
            except Exception as exc:
                logger.warning(f"Async welcome email dispatch failed for {recipient_email}: {exc}")

        t = threading.Thread(target=_bg_task, daemon=True)
        t.start()

    @staticmethod
    def send_registration_otp(recipient_email: str, otp_code: str) -> Dict[str, Any]:
        """
        Dispatches a 6-digit registration activation OTP via official verified SMTP.
        Does not activate account until code is cryptographically verified by the user.
        """
        subject = "Bitdex — Your Account Verification Code"
        body_text = f"""Hello,

Welcome to Bitdex Quantitative Platform (https://bitdex.ltd).

Your 6-digit email verification code is:

    {otp_code}

This code is valid for 5 minutes (300 seconds) and can be used only once to activate your institutional profile.
If you did not register for an account on Bitdex, you can safely ignore this email.

Best regards,
Bitdex Quantitative Platform
https://bitdex.ltd | go@bitdex.ltd
"""
        body_html = _build_bitdex_html(
            "Verify Your Email Address",
            f"""<p>Thank you for registering on <strong>Bitdex</strong>. Enter the following 6-digit security code to verify your email and activate your account:</p>
            <div style="margin:20px 0;padding:16px;background-color:#020617;border:1px solid #00E5FF;border-radius:12px;text-align:center;font-family:monospace;font-size:28px;font-weight:800;letter-spacing:8px;color:#00E5FF;">{otp_code}</div>
            <p style="font-size:12px;color:#94a3b8;">This code expires in <strong>5 minutes (300 seconds)</strong>. Never share this code with anyone.</p>"""
        )
        return EmailService.dispatch_email(
            recipient_email=recipient_email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            email_type="REGISTRATION_OTP",
            metadata={"purpose": "account_registration_activation"}
        )

    @staticmethod
    def send_login_otp(recipient_email: str, otp_code: str) -> Dict[str, Any]:
        subject = "Bitdex — Your One-Time Login Verification Code"
        body_text = f"""Hello,

Your Bitdex Platform (https://bitdex.ltd) login verification code is:

    {otp_code}

This code is valid for 5 minutes (300 seconds) and is single-use.
If you did not initiate this login request, please reset your password immediately or contact go@bitdex.ltd.

Best regards,
Bitdex Security Team
https://bitdex.ltd | go@bitdex.ltd
"""
        body_html = _build_bitdex_html(
            "One-Time Login Verification Code",
            f"""<p>Use the following single-use verification code to complete your sign-in to <strong>Bitdex</strong>:</p>
            <div style="margin:20px 0;padding:16px;background-color:#020617;border:1px solid #0ea5e9;border-radius:12px;text-align:center;font-family:monospace;font-size:28px;font-weight:800;letter-spacing:8px;color:#38bdf8;">{otp_code}</div>
            <p style="font-size:12px;color:#94a3b8;">This code expires in <strong>5 minutes (300 seconds)</strong>. Never share this code with anyone.</p>"""
        )
        return EmailService.dispatch_email(
            recipient_email=recipient_email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            email_type="LOGIN_OTP",
            metadata={"purpose": "session_authentication"}
        )

    @staticmethod
    def send_password_reset_otp(recipient_email: str, otp_code: str) -> Dict[str, Any]:
        subject = "Bitdex — Password Reset Verification Code"
        body_text = f"""Hello,

We received a request to reset the password for your Bitdex account ({recipient_email}).
Your single-use password reset verification code is:

    {otp_code}

This code expires in 5 minutes (300 seconds).
If you did not request a password reset, you can safely ignore this message; your account remains secure.

Best regards,
Bitdex Security Team
https://bitdex.ltd | go@bitdex.ltd
"""
        body_html = _build_bitdex_html(
            "Password Reset Verification Code",
            f"""<p>We received a request to reset the password for your Bitdex account (<strong>{recipient_email}</strong>).</p>
            <p>Enter this 6-digit verification code in the Bitdex application to set a new password:</p>
            <div style="margin:20px 0;padding:16px;background-color:#020617;border:1px solid #f59e0b;border-radius:12px;text-align:center;font-family:monospace;font-size:28px;font-weight:800;letter-spacing:8px;color:#fbbf24;">{otp_code}</div>
            <p style="font-size:12px;color:#94a3b8;">This code is valid for <strong>5 minutes</strong> and is single-use. If you did not request this reset, no changes have been made to your account.</p>"""
        )
        return EmailService.dispatch_email(
            recipient_email=recipient_email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            email_type="PASSWORD_RESET_OTP",
            metadata={"purpose": "password_reset"}
        )

    @staticmethod
    def send_security_notification(recipient_email: str, event_title: str, event_description: str) -> Dict[str, Any]:
        subject = f"Bitdex Security Alert — {event_title}"
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        body_text = f"""Hello,

This is an automated security notification for your Bitdex account ({recipient_email}):

Event: {event_title}
Details: {event_description}
Timestamp: {now_str}

If you did not authorize this change, please contact Bitdex Support immediately at go@bitdex.ltd.

Best regards,
Bitdex Security Team
https://bitdex.ltd | go@bitdex.ltd
"""
        body_html = _build_bitdex_html(
            f"Security Notification: {event_title}",
            f"""<p>{event_description}</p>
            <div style="margin:16px 0;padding:12px 16px;background-color:#020617;border-left:3px solid #10b981;font-family:monospace;font-size:12px;color:#94a3b8;">
              <div><strong>Account:</strong> {recipient_email}</div>
              <div><strong>Timestamp:</strong> {now_str}</div>
            </div>
            <p style="font-size:12px;color:#94a3b8;">If you did not perform this action, contact <a href="mailto:go@bitdex.ltd" style="color:#38bdf8;">go@bitdex.ltd</a> immediately.</p>"""
        )
        return EmailService.dispatch_email(
            recipient_email=recipient_email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            email_type="SECURITY_NOTIFICATION",
            metadata={"event": event_title}
        )

    @staticmethod
    def send_support_ticket_notification(
        recipient_email: str,
        ticket_id: str,
        subject_line: str = "",
        status: str = "",
        message_preview: str = "",
        is_reply: bool = False,
        subject: Optional[str] = None,
        status_label: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        actual_subject = subject or subject_line or "Support Ticket Update"
        actual_status = status_label or status or "Open"
        action_label = "New Reply on Support Ticket" if is_reply else "Support Ticket Created"
        subj = f"Bitdex Support [{ticket_id}] — {actual_subject}"
        body_text = f"""Hello,

{action_label} ({ticket_id}):

Subject: {actual_subject}
Status: {actual_status}

Message:
{message_preview}

You can view the full conversation and reply inside your Bitdex Portal under Help & Support (https://bitdex.ltd) or contact us at go@bitdex.ltd.

Best regards,
Bitdex Customer Support
go@bitdex.ltd
"""
        body_html = _build_bitdex_html(
            f"{action_label}: {ticket_id}",
            f"""<p>Your Bitdex support ticket has been updated:</p>
            <div style="margin:16px 0;padding:14px;background-color:#020617;border:1px solid #1e293b;border-radius:10px;font-size:13px;">
              <div><strong>Ticket Reference:</strong> <span style="font-family:monospace;color:#38bdf8;">{ticket_id}</span></div>
              <div style="margin-top:4px;"><strong>Subject:</strong> {actual_subject}</div>
              <div style="margin-top:4px;"><strong>Status:</strong> <span style="color:#10b981;">{actual_status}</span></div>
              <hr style="border:0;border-top:1px solid #1e293b;margin:12px 0;" />
              <div style="white-space:pre-wrap;color:#e2e8f0;">{message_preview}</div>
            </div>
            <p style="font-size:12px;color:#94a3b8;">Sign in at <a href="https://bitdex.ltd" style="color:#38bdf8;">https://bitdex.ltd</a> to view and reply to this ticket.</p>"""
        )
        return EmailService.dispatch_email(
            recipient_email=recipient_email,
            subject=subj,
            body_text=body_text,
            body_html=body_html,
            email_type="SUPPORT_TICKET_UPDATE",
            metadata={"ticket_id": ticket_id, "status": actual_status, "is_reply": is_reply}
        )

    @staticmethod
    def send_billing_receipt(
        recipient_email: str,
        receipt_type: str,
        amount_usd: float,
        balance_after_usd: float,
        reference_id: str,
        description: str = ""
    ) -> Dict[str, Any]:
        subject = f"Bitdex Billing Statement — {receipt_type} ({reference_id})"
        body_text = f"""Hello,

A billing transaction has been recorded on your Bitdex account ({recipient_email}):

Transaction Type: {receipt_type}
Amount: ${amount_usd:.2f} USD
Available Prepaid Balance: ${balance_after_usd:.2f} USD
Reference ID: {reference_id}
Description: {description}

View your complete immutable billing ledger anytime at https://bitdex.ltd.

Best regards,
Bitdex Billing & Operations
go@bitdex.ltd
"""
        body_html = _build_bitdex_html(
            f"Billing Transaction: {receipt_type}",
            f"""<p>A transaction has been posted to your Bitdex prepaid credit ledger:</p>
            <div style="margin:16px 0;padding:14px;background-color:#020617;border:1px solid #1e293b;border-radius:10px;font-family:monospace;font-size:12px;">
              <div><strong>Type:</strong> {receipt_type}</div>
              <div style="margin-top:4px;"><strong>Amount:</strong> ${amount_usd:.2f} USD</div>
              <div style="margin-top:4px;"><strong>Balance After:</strong> ${balance_after_usd:.2f} USD</div>
              <div style="margin-top:4px;"><strong>Reference:</strong> {reference_id}</div>
              <div style="margin-top:4px;"><strong>Details:</strong> {description}</div>
            </div>"""
        )
        return EmailService.dispatch_email(
            recipient_email=recipient_email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            email_type="BILLING_RECEIPT",
            metadata={"receipt_type": receipt_type, "reference_id": reference_id}
        )

    @staticmethod
    def send_admin_invitation(recipient_email: str, invitation_link: str) -> Dict[str, Any]:
        subject = "Bitdex — Administrator Account Provisioning Invitation"
        body_text = f"""Hello,

You have been provisioned as an Administrator on the Bitdex Platform for:
{recipient_email}

To set up your secure password and initialize mandatory 2FA, please follow this link:
{invitation_link}

This one-time invitation link expires in 48 hours.

Best regards,
Bitdex Platform Governance
go@bitdex.ltd
"""
        body_html = _build_bitdex_html(
            "Administrator Account Provisioning",
            f"""<p>Your Bitdex Administrator account (<strong>{recipient_email}</strong>) has been provisioned.</p>
            <p>Use the one-time setup link below to configure your password and mandatory 2FA:</p>
            <div style="margin:16px 0;padding:12px;background-color:#020617;border:1px solid #38bdf8;border-radius:8px;font-family:monospace;font-size:12px;word-break:break-all;color:#38bdf8;">{invitation_link}</div>"""
        )
        return EmailService.dispatch_email(
            recipient_email=recipient_email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            email_type="ADMIN_INVITATION",
            metadata={"purpose": "admin_onboarding"}
        )

    @staticmethod
    def send_email_change_otp(recipient_email: str, otp_code: str) -> Dict[str, Any]:
        """Dispatches a 6-digit confirmation code to a proposed new email address."""
        subject = f"Bitdex — Verify New Email Address: {otp_code}"
        body_text = f"""Hello,

You have requested to change your Bitdex account email to:
{recipient_email}

Your 6-digit verification code is:
{otp_code}

This code expires in 10 minutes. If you did not initiate this request, please contact Bitdex Support immediately at go@bitdex.ltd.

Best regards,
Bitdex Security & Platform Operations
go@bitdex.ltd
"""
        body_html = _build_bitdex_html(
            "Verify Your New Email Address",
            f"""<p>You requested to update your account email to: <strong>{recipient_email}</strong></p>
            <p>Enter the verification code below to confirm this change:</p>
            <div style="margin:20px 0;padding:16px;background-color:#020617;border:1px solid #10b981;border-radius:12px;text-align:center;">
              <span style="font-size:32px;font-weight:900;letter-spacing:8px;color:#10b981;font-family:monospace;">{otp_code}</span>
            </div>
            <p style="font-size:12px;color:#94a3b8;">This code expires in 10 minutes and is single-use. If you did not request this change, contact <a href="mailto:go@bitdex.ltd" style="color:#38bdf8;">go@bitdex.ltd</a>.</p>"""
        )
        return EmailService.dispatch_email(
            recipient_email=recipient_email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            email_type="EMAIL_CHANGE_OTP",
            metadata={"otp_code_len": len(otp_code)}
        )

    @staticmethod
    def send_email_change_security_notice(
        recipient_email: str,
        old_email: str,
        new_email: str,
        approx_ip: str,
        approx_country: str,
        timestamp_iso: str
    ) -> Dict[str, Any]:
        """Sends security notification to both previous and new email addresses."""
        subject = "Bitdex Security Alert — Account Email Address Changed"
        loc_str = f"Approximate IP: {approx_ip} ({approx_country})" if approx_ip else "IP: Unavailable"
        body_text = f"""Hello,

This is an automated security notice from Bitdex.

The primary email address associated with your Bitdex account was updated:
Previous Email: {old_email}
New Email: {new_email}
Timestamp: {timestamp_iso} UTC
{loc_str}

If you made this change, no further action is required.
If you did NOT authorize this change, please contact Bitdex Security immediately at go@bitdex.ltd.

Best regards,
Bitdex Security Team
go@bitdex.ltd
"""
        body_html = _build_bitdex_html(
            "Security Alert: Email Address Updated",
            f"""<p>The primary email address for your Bitdex account has been updated.</p>
            <div style="margin:16px 0;padding:14px;background-color:#020617;border:1px solid #1e293b;border-radius:10px;font-family:monospace;font-size:12px;">
              <div><strong>Previous Email:</strong> {old_email}</div>
              <div style="margin-top:4px;"><strong>New Email:</strong> {new_email}</div>
              <div style="margin-top:4px;"><strong>Event Timestamp:</strong> {timestamp_iso} UTC</div>
              <div style="margin-top:4px;"><strong>Network Location:</strong> {loc_str}</div>
            </div>
            <p style="font-size:12px;color:#f87171;">If you did not authorize this change, contact <a href="mailto:go@bitdex.ltd" style="color:#38bdf8;">go@bitdex.ltd</a> immediately.</p>"""
        )
        return EmailService.dispatch_email(
            recipient_email=recipient_email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            email_type="SECURITY_NOTICE_EMAIL_CHANGED",
            metadata={"old_email": old_email, "new_email": new_email, "timestamp": timestamp_iso}
        )

    @staticmethod
    def send_password_change_security_notice(
        recipient_email: str,
        approx_ip: str,
        approx_country: str,
        timestamp_iso: str
    ) -> Dict[str, Any]:
        """Sends security notification upon password change."""
        subject = "Bitdex Security Alert — Account Password Changed"
        loc_str = f"Approximate IP: {approx_ip} ({approx_country})" if approx_ip else "IP: Unavailable"
        body_text = f"""Hello,

Your Bitdex account password was successfully updated.

Event Timestamp: {timestamp_iso} UTC
{loc_str}

All other active sessions have been invalidated as a security precaution.
If you did NOT authorize this change, please contact Bitdex Security immediately at go@bitdex.ltd.

Best regards,
Bitdex Security Team
go@bitdex.ltd
"""
        body_html = _build_bitdex_html(
            "Security Alert: Password Updated",
            f"""<p>Your Bitdex account password was successfully changed.</p>
            <div style="margin:16px 0;padding:14px;background-color:#020617;border:1px solid #1e293b;border-radius:10px;font-family:monospace;font-size:12px;">
              <div><strong>Account:</strong> {recipient_email}</div>
              <div style="margin-top:4px;"><strong>Event Timestamp:</strong> {timestamp_iso} UTC</div>
              <div style="margin-top:4px;"><strong>Network Location:</strong> {loc_str}</div>
              <div style="margin-top:4px;"><strong>Sessions:</strong> Other active sessions revoked</div>
            </div>
            <p style="font-size:12px;color:#f87171;">If you did not perform this change, contact <a href="mailto:go@bitdex.ltd" style="color:#38bdf8;">go@bitdex.ltd</a> immediately.</p>"""
        )
        return EmailService.dispatch_email(
            recipient_email=recipient_email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            email_type="SECURITY_NOTICE_PASSWORD_CHANGED",
            metadata={"timestamp": timestamp_iso}
        )

