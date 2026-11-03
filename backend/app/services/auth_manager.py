import os
import hmac
import hashlib
import time
import struct
import base64
import secrets
import logging
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Tuple
import bcrypt
import jwt
import re
from fastapi import HTTPException, status, Header, Request, Depends

from .saas_db import get_db_connection
from .email_service import EmailService

logger = logging.getLogger("tauric.auth_manager")

JWT_SECRET_KEY = os.getenv("TAURIC_JWT_SECRET", "tauric_super_secret_staging_jwt_key_2026_xyz")
JWT_ALGORITHM = "HS256"
SESSION_DURATION_DAYS = 7
OTP_VALIDITY_SECONDS = 300  # 5 minutes
OTP_COOLDOWN_SECONDS = 60   # 1 minute

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False

def mask_email(email: str) -> str:
    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        masked_local = local[0] + "*"
    else:
        masked_local = local[0] + "***" + local[-1]
    return f"{masked_local}@{domain}"

def _compute_otp_hash(otp_plain: str, otp_salt: str = "") -> str:
    if otp_salt:
        return hashlib.sha256(f"{otp_plain}:{otp_salt}:{JWT_SECRET_KEY}".encode("utf-8")).hexdigest()
    return hashlib.sha256((otp_plain + JWT_SECRET_KEY).encode("utf-8")).hexdigest()

# ─── Pure-Python RFC 6238 TOTP Implementation ─────────────────

def generate_totp_code(secret_b32: str, time_step: int = 30, for_time: Optional[float] = None) -> str:
    """Generates a 6-digit RFC 6238 TOTP code from a Base32 secret."""
    key = base64.b32decode(secret_b32.upper(), casefold=True)
    t = for_time if for_time is not None else time.time()
    counter = int(t // time_step)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset:offset+4])[0] & 0x7FFFFFFF
    return str(code % 1000000).zfill(6)

def verify_totp_code(secret_b32: str, code: str, window: int = 1) -> bool:
    """Verifies a 6-digit TOTP code allowing for +/- 1 time-step clock drift (90-second total window)."""
    if not secret_b32 or not code or len(code.strip()) != 6:
        return False
    clean_code = code.strip()
    now = time.time()
    for drift in range(-window, window + 1):
        if generate_totp_code(secret_b32, for_time=now + (drift * 30)) == clean_code:
            return True
    return False

class AuthManager:
    # ─── End-to-End Registration & Verification Flow (Phases 2 & 3) ────

    @staticmethod
    def initiate_registration(
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        username: Optional[str] = "",
        country: str = "SG"
    ) -> Dict[str, Any]:
        """
        Step 1 & 2 of Customer Registration:
        Validates credentials and password strength.
        Enforces PENDING_VERIFICATION state (account is NOT active, no token granted).
        Dispatches single-use 6-digit OTP via official GoDaddy SMTP.
        Does not mark email verified or activate user until OTP is verified.
        """
        email = (email or "").strip().lower()
        if "@" not in email or len(email) < 5:
            raise HTTPException(status_code=400, detail="Please enter a valid email address.")
        if not first_name or not first_name.strip():
            raise HTTPException(status_code=400, detail="First name is required.")
        if not last_name or not last_name.strip():
            raise HTTPException(status_code=400, detail="Last name is required.")
        if not password or len(password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters long.")

        conn = get_db_connection()
        try:
            existing = conn.execute("SELECT user_id, email, status FROM users WHERE email = ?", (email,)).fetchone()
            if existing:
                if existing["status"] == "ACTIVE":
                    raise HTTPException(status_code=409, detail="An account with this email address already exists. Please sign in.")
                elif existing["status"] == "BLOCKED":
                    raise HTTPException(status_code=403, detail="Account is blocked by administrator.")

            reg_otp = f"{secrets.randbelow(900000) + 100000}"
            reg_salt = secrets.token_hex(16)
            reg_hash = _compute_otp_hash(reg_otp, reg_salt)

            now = datetime.now(timezone.utc)
            now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
            exp_iso = (now + timedelta(seconds=OTP_VALIDITY_SECONDS)).strftime("%Y-%m-%dT%H:%M:%SZ")

            # Dispatch verification OTP via GoDaddy SMTP
            dispatch_res = EmailService.send_registration_otp(email, reg_otp)
            raw_delivery = dispatch_res.get("status", "QUEUED")
            is_delivered = raw_delivery in ("SENT", "ACCEPTED")
            delivery_status = "ACCEPTED" if is_delivered else "FAILED"

            pw_hash = hash_password(password)
            derived_username = (username or f"{first_name.strip()} {last_name.strip()}").strip()

            with conn:
                if existing and existing["status"] == "PENDING_VERIFICATION":
                    user_id = existing["user_id"]
                    conn.execute("""
                        UPDATE users
                        SET password_hash = ?, first_name = ?, last_name = ?, username = ?,
                            country = ?, email_otp_hash = ?, email_otp_expires_at = ?,
                            email_otp_sent_at = ?, email_otp_attempts = 3, email_verification_token = ?,
                            email_verified = 0, status = 'PENDING_VERIFICATION', updated_at = ?
                        WHERE user_id = ?
                    """, (
                        pw_hash, first_name.strip(), last_name.strip(), derived_username,
                        (country or "SG").upper(), reg_hash, exp_iso, now_iso, reg_salt,
                        now_iso, user_id
                    ))
                else:
                    user_id = f"USR-{secrets.token_hex(5).upper()}"
                    conn.execute("""
                        INSERT INTO users (
                            user_id, email, username, password_hash, role, status, email_verified,
                            kyc_status, first_name, last_name, country, email_otp_hash,
                            email_otp_expires_at, email_otp_sent_at, email_otp_attempts,
                            email_verification_token, two_factor_enabled, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, 'CUSTOMER', 'PENDING_VERIFICATION', 0, 'NOT_REQUIRED', ?, ?, ?, ?, ?, ?, 3, ?, 0, ?, ?)
                    """, (
                        user_id, email, derived_username, pw_hash, first_name.strip(),
                        last_name.strip(), (country or "SG").upper(), reg_hash, exp_iso,
                        now_iso, reg_salt, now_iso, now_iso
                    ))

            return {
                "status": "PENDING_VERIFICATION",
                "challenge_id": user_id,
                "email": email,
                "email_masked": mask_email(email),
                "expires_in_seconds": OTP_VALIDITY_SECONDS,
                "resend_cooldown_seconds": OTP_COOLDOWN_SECONDS,
                "delivery_status": delivery_status,
                "delivery_blocked": not is_delivered,
                "message": (
                    f"A 6-digit verification code has been dispatched to {mask_email(email)}."
                    if is_delivered
                    else "Email provider encountered high load. Please use the Resend code button to retry delivery."
                )
            }
        finally:
            conn.close()

    @staticmethod
    def verify_registration_otp(email: str, otp_code: str) -> Dict[str, Any]:
        """
        Step 3 of Customer Registration:
        Verifies 6-digit OTP correctness, expiration, and attempt limits.
        Only marks email verified, completes registration, and activates customer account upon success.
        """
        email = (email or "").strip().lower()
        clean_code = (otp_code or "").strip()
        if len(clean_code) != 6 or not clean_code.isdigit():
            raise HTTPException(status_code=400, detail="A valid 6-digit verification code is required.")

        conn = get_db_connection()
        try:
            user = conn.execute("""
                SELECT user_id, email, username, first_name, last_name, country, status,
                       email_verified, email_otp_hash, email_otp_expires_at, email_otp_attempts,
                       email_verification_token
                FROM users WHERE email = ?
            """, (email,)).fetchone()

            if not user or user["status"] != "PENDING_VERIFICATION":
                if user and user["status"] == "ACTIVE" and user["email_verified"] == 1:
                    return {
                        "status": "SUCCESS",
                        "message": "Account already verified. You may sign in.",
                        "email": email
                    }
                raise HTTPException(status_code=400, detail="No pending registration found for this email address.")

            if user["email_otp_attempts"] <= 0:
                raise HTTPException(status_code=400, detail="Maximum verification attempts reached. Please request a new verification code.")

            exp_str = user["email_otp_expires_at"]
            if exp_str:
                exp_dt = datetime.fromisoformat(exp_str.replace("Z", "+00:00"))
                if datetime.now(timezone.utc) > exp_dt:
                    raise HTTPException(status_code=400, detail="Verification code has expired. Please request a new code.")

            salt = user["email_verification_token"] or ""
            computed_hash = _compute_otp_hash(clean_code, salt)
            if not hmac.compare_digest(computed_hash, user["email_otp_hash"] or ""):
                new_attempts = max(0, user["email_otp_attempts"] - 1)
                with conn:
                    conn.execute("UPDATE users SET email_otp_attempts = ? WHERE user_id = ?", (new_attempts, user["user_id"]))
                if new_attempts <= 0:
                    raise HTTPException(status_code=400, detail="Invalid verification code. Maximum attempts reached. Please request a new code.")
                raise HTTPException(status_code=400, detail=f"Invalid verification code. {new_attempts} attempt(s) remaining.")

            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            with conn:
                conn.execute("""
                    UPDATE users
                    SET status = 'ACTIVE', email_verified = 1, email_otp_hash = '',
                        email_otp_expires_at = '', email_otp_attempts = 0,
                        email_verification_token = '', updated_at = ?
                    WHERE user_id = ?
                """, (now_iso, user["user_id"]))

                existing_acct = conn.execute("SELECT account_id FROM billing_accounts WHERE user_id = ?", (user["user_id"],)).fetchone()
                if not existing_acct:
                    acct_id = f"BAC-{secrets.token_hex(4).upper()}"
                    conn.execute("""
                        INSERT INTO billing_accounts (account_id, user_id, prepaid_credits_usd, total_deposited_usd, total_fees_paid_usd, updated_at)
                        VALUES (?, ?, 0.0, 0.0, 0.0, ?)
                    """, (acct_id, user["user_id"], now_iso))

                existing_pol = conn.execute("SELECT policy_id FROM fee_policies WHERE user_id = ?", (user["user_id"],)).fetchone()
                if not existing_pol:
                    pol_id = f"POL-{secrets.token_hex(4).upper()}"
                    conn.execute("""
                        INSERT INTO fee_policies (
                            policy_id, user_id, version, activation_fee_enabled, activation_fee_usd,
                            activation_fee_charged, execution_fee_enabled, execution_fee_usd,
                            ai_research_fee_enabled, ai_research_fee_usd, ai_research_fee_cents, fee_waived, currency, updated_at
                        ) VALUES (?, ?, 1, 1, 20.0, 0, 1, 0.30, 1, 1.0, 100, 0, 'USD', ?)
                    """, (pol_id, user["user_id"], now_iso))

                log_id = f"AUD-{secrets.token_hex(6).upper()}"
                conn.execute("""
                    INSERT INTO audit_logs (log_id, actor_id, action, target_user_id, details_json, created_at)
                    VALUES (?, ?, 'USER_REGISTERED_VERIFIED', ?, ?, ?)
                """, (log_id, user["user_id"], user["user_id"], f'{{"email": "{email}", "status": "ACTIVE"}}', now_iso))

            EmailService.send_welcome_email_async(recipient_email=email, username=user["username"])

            return {
                "status": "SUCCESS",
                "message": "Institutional account activated. Your email has been verified successfully.",
                "user": {
                    "user_id": user["user_id"],
                    "email": email,
                    "first_name": user["first_name"],
                    "last_name": user["last_name"],
                    "username": user["username"],
                    "status": "ACTIVE",
                    "email_verified": True
                }
            }
        finally:
            conn.close()

    @staticmethod
    def resend_registration_otp(email: str) -> Dict[str, Any]:
        """Resends registration verification OTP enforcing 60s cooldown."""
        email = (email or "").strip().lower()
        conn = get_db_connection()
        try:
            user = conn.execute("""
                SELECT user_id, email, status, email_otp_sent_at
                FROM users WHERE email = ?
            """, (email,)).fetchone()

            if not user or user["status"] != "PENDING_VERIFICATION":
                raise HTTPException(status_code=400, detail="No pending registration found for this email address.")

            sent_at = user["email_otp_sent_at"]
            if sent_at:
                sent_dt = datetime.fromisoformat(sent_at.replace("Z", "+00:00"))
                elapsed = (datetime.now(timezone.utc) - sent_dt).total_seconds()
                if elapsed < OTP_COOLDOWN_SECONDS:
                    wait_sec = max(1, int(OTP_COOLDOWN_SECONDS - elapsed))
                    raise HTTPException(status_code=429, detail=f"Please wait {wait_sec}s before requesting a new code.")

            reg_otp = f"{secrets.randbelow(900000) + 100000}"
            reg_salt = secrets.token_hex(16)
            reg_hash = _compute_otp_hash(reg_otp, reg_salt)

            now = datetime.now(timezone.utc)
            now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
            exp_iso = (now + timedelta(seconds=OTP_VALIDITY_SECONDS)).strftime("%Y-%m-%dT%H:%M:%SZ")

            dispatch_res = EmailService.send_registration_otp(email, reg_otp)
            if dispatch_res.get("status") not in ("SENT", "ACCEPTED"):
                raise HTTPException(status_code=503, detail="Could not deliver verification email. Please retry.")

            with conn:
                conn.execute("""
                    UPDATE users
                    SET email_otp_hash = ?, email_otp_expires_at = ?, email_otp_sent_at = ?,
                        email_otp_attempts = 3, email_verification_token = ?, updated_at = ?
                    WHERE user_id = ?
                """, (reg_hash, exp_iso, now_iso, reg_salt, now_iso, user["user_id"]))

            return {
                "status": "RESENT",
                "email_masked": mask_email(email),
                "expires_in_seconds": OTP_VALIDITY_SECONDS,
                "resend_cooldown_seconds": OTP_COOLDOWN_SECONDS,
                "delivery_status": "ACCEPTED",
                "message": f"A fresh 6-digit verification code has been dispatched to {mask_email(email)}."
            }
        finally:
            conn.close()

    @staticmethod
    def register_user(
        email: str,
        password: str,
        role: str = "CUSTOMER",
        first_name: str = "",
        last_name: str = "",
        username: str = "",
        country: str = "SG",
        status: str = "ACTIVE",
        email_verified: bool = False,
        kyc_status: str = "NOT_REQUIRED",
        allow_privileged_seed: bool = False
    ) -> Dict[str, Any]:
        email = email.strip().lower()
        if "@" not in email or len(email) < 5:
            raise HTTPException(status_code=400, detail="Invalid email address.")
        if len(password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters long.")
        # Security Boundary: Standard user registration creates strictly CUSTOMER accounts.
        effective_role = role if allow_privileged_seed else "CUSTOMER"

        derived_username = (username or "").strip()
        if not derived_username:
            full_name = f"{first_name.strip()} {last_name.strip()}".strip()
            derived_username = full_name if full_name else email.split("@")[0]

        conn = get_db_connection()
        try:
            with conn:
                existing = conn.execute("SELECT user_id FROM users WHERE email = ?", (email,)).fetchone()
                if existing:
                    raise HTTPException(status_code=409, detail="A user with this email already exists.")

                user_id = f"USR-{secrets.token_hex(5).upper()}"
                pw_hash = hash_password(password)
                now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                verif_token = secrets.token_hex(16)

                # Lookup global default AI analysis price
                cfg = conn.execute("SELECT ai_analysis_price_usd, ai_analysis_price_cents FROM platform_pricing_config WHERE config_key = 'GLOBAL_DEFAULT'").fetchone()
                default_ai_usd = float(cfg["ai_analysis_price_usd"]) if cfg else 1.00
                default_ai_cents = int(cfg["ai_analysis_price_cents"]) if cfg else 100

                conn.execute("""
                    INSERT INTO users (
                        user_id, email, username, password_hash, role, status, email_verified,
                        kyc_status, first_name, last_name, country, email_verification_token,
                        two_factor_enabled, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                """, (user_id, email, derived_username, pw_hash, effective_role, status, 1 if email_verified else 0, kyc_status, first_name, last_name, country.upper(), verif_token, now_iso, now_iso))

                acct_id = f"BAC-{secrets.token_hex(4).upper()}"
                conn.execute("""
                    INSERT INTO billing_accounts (account_id, user_id, prepaid_credits_usd, total_deposited_usd, total_fees_paid_usd, updated_at)
                    VALUES (?, ?, 0.0, 0.0, 0.0, ?)
                """, (acct_id, user_id, now_iso))

                pol_id = f"POL-{secrets.token_hex(4).upper()}"
                conn.execute("""
                    INSERT INTO fee_policies (
                        policy_id, user_id, version, activation_fee_enabled, activation_fee_usd,
                        activation_fee_charged, execution_fee_enabled, execution_fee_usd,
                        ai_research_fee_enabled, ai_research_fee_usd, ai_research_fee_cents, fee_waived, currency, updated_at
                    ) VALUES (?, ?, 1, 1, 20.0, 0, 1, 0.30, 1, ?, ?, 0, 'USD', ?)
                """, (pol_id, user_id, default_ai_usd, default_ai_cents, now_iso))

                log_id = f"AUD-{secrets.token_hex(6).upper()}"
                conn.execute("""
                    INSERT INTO audit_logs (log_id, actor_id, action, target_user_id, details_json, created_at)
                    VALUES (?, ?, 'USER_REGISTERED', ?, ?, ?)
                """, (log_id, user_id, user_id, f'{{"email": "{email}", "username": "{derived_username}", "role": "{effective_role}", "country": "{country}"}}', now_iso))

                # Asynchronously dispatch official branded welcome email (non-blocking <50ms registration response)
                try:
                    EmailService.send_welcome_email_async(recipient_email=email, username=derived_username)
                except Exception as mail_err:
                    logger.warning(f"Failed to dispatch async welcome email to {email}: {mail_err}")

                return {
                    "user_id": user_id,
                    "email": email,
                    "username": derived_username,
                    "role": effective_role,
                    "status": status,
                    "first_name": first_name,
                    "last_name": last_name,
                    "country": country,
                    "email_verified": email_verified,
                    "email_verification_token": verif_token,
                    "kyc_status": kyc_status,
                    "created_at": now_iso
                }
        finally:
            conn.close()

    @staticmethod
    def verify_email(token: str) -> Dict[str, Any]:
        if not token:
            raise HTTPException(status_code=400, detail="Missing verification token.")
        conn = get_db_connection()
        try:
            with conn:
                user = conn.execute("SELECT user_id, email, email_verified FROM users WHERE email_verification_token = ?", (token,)).fetchone()
                if not user:
                    raise HTTPException(status_code=400, detail="Invalid or expired email verification token.")
                now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                conn.execute("""
                    UPDATE users
                    SET email_verified = 1, email_verification_token = '', updated_at = ?
                    WHERE user_id = ?
                """, (now_iso, user["user_id"]))

                log_id = f"AUD-{secrets.token_hex(6).upper()}"
                conn.execute("""
                    INSERT INTO audit_logs (log_id, actor_id, action, target_user_id, details_json, created_at)
                    VALUES (?, ?, 'EMAIL_VERIFIED', ?, '{"status": "verified"}', ?)
                """, (log_id, user["user_id"], user["user_id"], now_iso))

                return {"status": "SUCCESS", "message": f"Email {user['email']} verified successfully."}
        finally:
            conn.close()

    # ─── End-to-End Forgot Password OTP Flow (Requirement 10) ──────

    @staticmethod
    def initiate_password_reset(email: str) -> Dict[str, Any]:
        """
        Step 1 of Forgot Password OTP Flow:
        Validates email format, generates a 6-digit single-use OTP with per-challenge salt,
        stores only salted hash in password_reset_challenges, invalidates older reset challenges,
        and dispatches OTP via go@bitdex.ltd.
        Does not disclose whether an account exists in public error messages.
        """
        email = (email or "").strip().lower()
        if "@" not in email or len(email) < 5:
            raise HTTPException(status_code=400, detail="Please enter a valid email address.")

        conn = get_db_connection()
        try:
            user = conn.execute("SELECT user_id, email, status FROM users WHERE email = ?", (email,)).fetchone()
            challenge_id = f"RST-{secrets.token_hex(16)}"

            if not user or user["status"] == "BLOCKED":
                # Safe anti-enumeration response with synthetic challenge_id
                return {
                    "status": "RESET_OTP_DISPATCHED",
                    "challenge_id": challenge_id,
                    "email_masked": mask_email(email),
                    "expires_in_seconds": OTP_VALIDITY_SECONDS,
                    "resend_cooldown_seconds": OTP_COOLDOWN_SECONDS,
                    "message": f"If an account is registered for {mask_email(email)}, a 6-digit password reset code has been sent."
                }

            # Check rate limit / cooldown on most recent challenge for this user
            recent = conn.execute("""
                SELECT resend_after FROM password_reset_challenges
                WHERE user_id = ? AND used = 0
                ORDER BY created_at DESC LIMIT 1
            """, (user["user_id"],)).fetchone()
            if recent and recent["resend_after"]:
                resend_dt = datetime.fromisoformat(recent["resend_after"].replace("Z", "+00:00"))
                if datetime.now(timezone.utc) < resend_dt:
                    wait_sec = max(1, int((resend_dt - datetime.now(timezone.utc)).total_seconds()))
                    raise HTTPException(status_code=429, detail=f"Please wait {wait_sec}s before requesting another password reset code.")

            otp_plain = f"{secrets.randbelow(900000) + 100000}"
            otp_salt = secrets.token_hex(16)
            otp_hash = _compute_otp_hash(otp_plain, otp_salt)

            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(seconds=OTP_VALIDITY_SECONDS)
            resend_after = now + timedelta(seconds=OTP_COOLDOWN_SECONDS)
            now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
            exp_iso = expires_at.strftime("%Y-%m-%dT%H:%M:%SZ")
            resend_iso = resend_after.strftime("%Y-%m-%dT%H:%M:%SZ")

            with conn:
                # Invalidate any older active password reset challenges for this user
                conn.execute("UPDATE password_reset_challenges SET used = 1 WHERE user_id = ? AND used = 0", (user["user_id"],))

                conn.execute("""
                    INSERT INTO password_reset_challenges (
                        challenge_id, user_id, email, otp_hash, otp_salt,
                        expires_at, attempts_left, resend_after, verified, used, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 3, ?, 0, 0, ?)
                """, (challenge_id, user["user_id"], email, otp_hash, otp_salt, exp_iso, resend_iso, now_iso))

                log_id = f"AUD-{secrets.token_hex(6).upper()}"
                conn.execute("""
                    INSERT INTO audit_logs (log_id, actor_id, action, target_user_id, details_json, created_at)
                    VALUES (?, ?, 'PASSWORD_RESET_OTP_REQUESTED', ?, ?, ?)
                """, (log_id, user["user_id"], user["user_id"], f'{{"challenge_id": "{challenge_id}"}}', now_iso))

            dispatch_res = EmailService.send_password_reset_otp(email, otp_plain)

            delivery_status = dispatch_res.get("status", "QUEUED")
            delivery_blocked = dispatch_res.get("delivery_blocked", False)

            if delivery_status in ("SENT", "ACCEPTED"):
                msg = "Email provider accepted the message"
            elif delivery_blocked or delivery_status == "FAILED":
                msg = "Could not send verification email. Please retry."
            else:
                msg = "Delivery status pending"

            return {
                "status": "RESET_OTP_DISPATCHED",
                "challenge_id": challenge_id,
                "email_masked": mask_email(email),
                "expires_in_seconds": OTP_VALIDITY_SECONDS,
                "resend_cooldown_seconds": OTP_COOLDOWN_SECONDS,
                "delivery_status": delivery_status,
                "delivery_blocked": delivery_blocked,
                "provider_response": dispatch_res.get("provider_response", ""),
                "message": msg
            }
        finally:
            conn.close()

    @staticmethod
    def verify_password_reset_otp(challenge_id: str, otp_code: str) -> Dict[str, Any]:
        """
        Step 2 of Forgot Password OTP Flow:
        Verifies the 6-digit OTP code, enforces expiration and 3-attempt limit,
        and issues a short-lived single-use reset_token to unlock the New Password form.
        """
        if not challenge_id or not otp_code or len(otp_code.strip()) != 6:
            raise HTTPException(status_code=400, detail="Please enter a valid 6-digit verification code.")

        clean_otp = otp_code.strip()
        conn = get_db_connection()
        try:
            challenge = conn.execute("""
                SELECT challenge_id, user_id, email, otp_hash, otp_salt,
                       expires_at, attempts_left, verified, used
                FROM password_reset_challenges WHERE challenge_id = ?
            """, (challenge_id,)).fetchone()

            if not challenge or challenge["used"]:
                raise HTTPException(status_code=400, detail="Invalid or expired password reset session. Please request a new code.")

            if challenge["attempts_left"] <= 0:
                raise HTTPException(status_code=400, detail="Maximum verification attempts exceeded. Please request a new reset code.")

            exp_dt = datetime.fromisoformat(challenge["expires_at"].replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > exp_dt:
                raise HTTPException(status_code=400, detail="Verification code has expired. Please request a new code.")

            computed_hash = _compute_otp_hash(clean_otp, challenge["otp_salt"] or "")
            if not hmac.compare_digest(computed_hash, challenge["otp_hash"]):
                new_attempts = challenge["attempts_left"] - 1
                with conn:
                    conn.execute(
                        "UPDATE password_reset_challenges SET attempts_left = ?, used = CASE WHEN ? <= 0 THEN 1 ELSE used END WHERE challenge_id = ?",
                        (new_attempts, new_attempts, challenge_id)
                    )
                if new_attempts <= 0:
                    raise HTTPException(status_code=400, detail="Invalid code. Maximum attempts reached. Please request a new reset code.")
                raise HTTPException(status_code=400, detail=f"Invalid verification code. {new_attempts} attempt(s) remaining.")

            reset_token = secrets.token_urlsafe(32)
            reset_token_hash = hashlib.sha256((reset_token + JWT_SECRET_KEY).encode("utf-8")).hexdigest()

            with conn:
                conn.execute("""
                    UPDATE password_reset_challenges
                    SET verified = 1, attempts_left = 0, reset_token_hash = ?
                    WHERE challenge_id = ?
                """, (reset_token_hash, challenge_id))

            return {
                "status": "OTP_VERIFIED",
                "challenge_id": challenge_id,
                "reset_token": reset_token,
                "message": "Verification code confirmed. You may now set a new password."
            }
        finally:
            conn.close()

    @staticmethod
    def resend_password_reset_otp(challenge_id: str) -> Dict[str, Any]:
        """Resends password reset OTP enforcing the 60-second cooldown."""
        conn = get_db_connection()
        try:
            challenge = conn.execute("""
                SELECT challenge_id, user_id, email, resend_after, used
                FROM password_reset_challenges WHERE challenge_id = ?
            """, (challenge_id,)).fetchone()

            if not challenge or challenge["used"]:
                raise HTTPException(status_code=400, detail="Invalid or expired password reset session.")

            resend_dt = datetime.fromisoformat(challenge["resend_after"].replace("Z", "+00:00"))
            if datetime.now(timezone.utc) < resend_dt:
                wait_sec = max(1, int((resend_dt - datetime.now(timezone.utc)).total_seconds()))
                raise HTTPException(status_code=429, detail=f"Please wait {wait_sec}s before requesting a new code.")

            otp_plain = f"{secrets.randbelow(900000) + 100000}"
            otp_salt = secrets.token_hex(16)
            otp_hash = _compute_otp_hash(otp_plain, otp_salt)

            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(seconds=OTP_VALIDITY_SECONDS)
            resend_after = now + timedelta(seconds=OTP_COOLDOWN_SECONDS)

            with conn:
                conn.execute("""
                    UPDATE password_reset_challenges
                    SET otp_hash = ?, otp_salt = ?, expires_at = ?, attempts_left = 3,
                        resend_after = ?, verified = 0, reset_token_hash = NULL
                    WHERE challenge_id = ?
                """, (
                    otp_hash,
                    otp_salt,
                    expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    resend_after.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    challenge_id
                ))

            dispatch_res = EmailService.send_password_reset_otp(challenge["email"], otp_plain)

            delivery_status = dispatch_res.get("status", "QUEUED")
            delivery_blocked = dispatch_res.get("delivery_blocked", False)

            if delivery_status in ("SENT", "ACCEPTED"):
                msg = "Email provider accepted the message"
            elif delivery_blocked or delivery_status == "FAILED":
                msg = "Could not send verification email. Please retry."
            else:
                msg = "Delivery status pending"

            return {
                "status": "RESENT",
                "challenge_id": challenge_id,
                "expires_in_seconds": OTP_VALIDITY_SECONDS,
                "resend_cooldown_seconds": OTP_COOLDOWN_SECONDS,
                "delivery_status": delivery_status,
                "delivery_blocked": delivery_blocked,
                "provider_response": dispatch_res.get("provider_response", ""),
                "message": msg
            }
        finally:
            conn.close()

    @staticmethod
    def complete_password_reset(
        challenge_id: str,
        reset_token: str,
        new_password: str,
        confirm_password: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Step 3 of Forgot Password OTP Flow:
        Verifies single-use reset_token, enforces password policy and confirmation match,
        updates bcrypt password hash, invalidates reset challenge immediately,
        revokes all sessions, logs audit event, and sends security notification email.
        """
        if not new_password or len(new_password) < 8:
            raise HTTPException(status_code=400, detail="New password must be at least 8 characters long.")
        if confirm_password is not None and new_password != confirm_password:
            raise HTTPException(status_code=400, detail="New password and confirm password do not match.")
        if not challenge_id or not reset_token:
            raise HTTPException(status_code=400, detail="Missing password reset authorization parameters.")

        conn = get_db_connection()
        try:
            with conn:
                challenge = conn.execute("""
                    SELECT challenge_id, user_id, email, expires_at, verified, used, reset_token_hash
                    FROM password_reset_challenges WHERE challenge_id = ?
                """, (challenge_id,)).fetchone()

                if not challenge or challenge["used"] or not challenge["verified"] or not challenge["reset_token_hash"]:
                    raise HTTPException(status_code=400, detail="Invalid or already-used password reset session.")

                exp_dt = datetime.fromisoformat(challenge["expires_at"].replace("Z", "+00:00"))
                # Allow 10-minute grace window after OTP creation to submit the new password form
                if datetime.now(timezone.utc) > (exp_dt + timedelta(minutes=5)):
                    raise HTTPException(status_code=400, detail="Password reset session has expired. Please start again.")

                expected_hash = hashlib.sha256((reset_token + JWT_SECRET_KEY).encode("utf-8")).hexdigest()
                if not hmac.compare_digest(expected_hash, challenge["reset_token_hash"]):
                    raise HTTPException(status_code=400, detail="Invalid password reset token.")

                new_hash = hash_password(new_password)
                now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

                # Mark challenge used immediately (single-use)
                conn.execute("""
                    UPDATE password_reset_challenges
                    SET used = 1, reset_token_hash = NULL
                    WHERE challenge_id = ?
                """, (challenge_id,))

                # Update user password hash and clear any legacy reset tokens
                conn.execute("""
                    UPDATE users
                    SET password_hash = ?, password_reset_token = '', password_reset_expires = '',
                        must_change_password = 0, updated_at = ?
                    WHERE user_id = ?
                """, (new_hash, now_iso, challenge["user_id"]))

                # Revoke all active sessions for this user
                conn.execute("UPDATE sessions SET revoked = 1 WHERE user_id = ?", (challenge["user_id"],))

                log_id = f"AUD-{secrets.token_hex(6).upper()}"
                conn.execute("""
                    INSERT INTO audit_logs (log_id, actor_id, action, target_user_id, details_json, created_at)
                    VALUES (?, ?, 'PASSWORD_RESET_COMPLETED', ?, ?, ?)
                """, (log_id, challenge["user_id"], challenge["user_id"], f'{{"challenge_id": "{challenge_id}", "sessions_revoked": true}}', now_iso))

            # Send security notification email
            EmailService.send_security_notification(
                challenge["email"],
                "Password Reset Completed",
                "Your Bitdex account password was successfully reset via Email OTP verification, and all previous sessions have been revoked."
            )

            return {
                "status": "SUCCESS",
                "message": "Your password has been updated. Please sign in with your new password."
            }
        finally:
            conn.close()

    # Keep legacy token method for backward compatibility with existing tests if called directly
    @staticmethod
    def request_password_reset(email: str) -> Dict[str, Any]:
        return AuthManager.initiate_password_reset(email)

    @staticmethod
    def reset_password_with_token(token: str, new_password: str, confirm_password: Optional[str] = None, challenge_id: Optional[str] = None) -> Dict[str, Any]:
        if challenge_id:
            return AuthManager.complete_password_reset(challenge_id, token, new_password, confirm_password)
        if len(new_password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters long.")
        if confirm_password is not None and new_password != confirm_password:
            raise HTTPException(status_code=400, detail="Passwords do not match.")
        conn = get_db_connection()
        try:
            # Check if token matches a verified password_reset_challenges row
            token_hash = hashlib.sha256((token + JWT_SECRET_KEY).encode("utf-8")).hexdigest()
            chal = conn.execute("SELECT challenge_id FROM password_reset_challenges WHERE reset_token_hash = ? AND used = 0", (token_hash,)).fetchone()
            if chal:
                return AuthManager.complete_password_reset(chal["challenge_id"], token, new_password, confirm_password)

            with conn:
                user = conn.execute("""
                    SELECT user_id, email, password_reset_expires FROM users WHERE password_reset_token = ?
                """, (token,)).fetchone()
                if not user:
                    raise HTTPException(status_code=400, detail="Invalid or expired password reset token.")

                exp_str = user["password_reset_expires"]
                if exp_str:
                    exp_dt = datetime.fromisoformat(exp_str.replace("Z", "+00:00"))
                    if datetime.now(timezone.utc) > exp_dt:
                        raise HTTPException(status_code=400, detail="Password reset token has expired.")

                new_hash = hash_password(new_password)
                now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

                conn.execute("""
                    UPDATE users
                    SET password_hash = ?, password_reset_token = '', password_reset_expires = '', must_change_password = 0, updated_at = ?
                    WHERE user_id = ?
                """, (new_hash, now_iso, user["user_id"]))

                conn.execute("UPDATE sessions SET revoked = 1 WHERE user_id = ?", (user["user_id"],))

                log_id = f"AUD-{secrets.token_hex(6).upper()}"
                conn.execute("""
                    INSERT INTO audit_logs (log_id, actor_id, action, target_user_id, details_json, created_at)
                    VALUES (?, ?, 'PASSWORD_RESET_COMPLETED', ?, '{"sessions_revoked": true}', ?)
                """, (log_id, user["user_id"], user["user_id"], now_iso))

            EmailService.send_security_notification(
                user["email"],
                "Password Reset Completed",
                "Your Bitdex account password was reset and all previous active sessions were revoked."
            )
            return {"status": "SUCCESS", "message": "Password reset successful. Please sign in with your new credentials."}
        finally:
            conn.close()

    # ─── Mandatory Email OTP Authentication ───────────────────────

    @staticmethod
    def initiate_login(email: str, password: str) -> Dict[str, Any]:
        """
        Step 1 of Mandatory Email OTP Login Flow:
        Validates email/password credentials and generates a 6-digit cryptographically random OTP.
        Stores only the secure salted OTP hash. Dispatches email OTP via go@bitdex.ltd.
        Returns a short-lived challenge ID.
        """
        email = email.strip().lower()
        conn = get_db_connection()
        try:
            user = conn.execute("""
                SELECT user_id, email, username, password_hash, role, status, email_verified,
                       two_factor_secret, two_factor_enabled
                FROM users WHERE email = ?
            """, (email,)).fetchone()

            if not user or not verify_password(password, user["password_hash"]):
                raise HTTPException(status_code=401, detail="Invalid email or password.")

            if user["status"] == "PENDING_VERIFICATION":
                raise HTTPException(
                    status_code=403,
                    detail="Registration incomplete: Email verification is required before login. Please enter the 6-digit verification code sent to your email."
                )

            if user["status"] == "BLOCKED":
                raise HTTPException(status_code=403, detail="Account is blocked by administrator. Contact go@bitdex.ltd.")

            otp_plain = f"{secrets.randbelow(900000) + 100000}"
            otp_salt = secrets.token_hex(16)
            otp_hash = _compute_otp_hash(otp_plain, otp_salt)

            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(seconds=OTP_VALIDITY_SECONDS)
            resend_after = now + timedelta(seconds=OTP_COOLDOWN_SECONDS)
            now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
            exp_iso = expires_at.strftime("%Y-%m-%dT%H:%M:%SZ")
            resend_iso = resend_after.strftime("%Y-%m-%dT%H:%M:%SZ")

            challenge_id = f"CHAL-{secrets.token_hex(16)}"

            with conn:
                conn.execute("UPDATE login_challenges SET verified = 1 WHERE user_id = ? AND verified = 0", (user["user_id"],))

                conn.execute("""
                    INSERT INTO login_challenges (
                        challenge_id, user_id, otp_hash, otp_salt, expires_at, attempts_left,
                        resend_after, verified, created_at
                    ) VALUES (?, ?, ?, ?, ?, 3, ?, 0, ?)
                """, (challenge_id, user["user_id"], otp_hash, otp_salt, exp_iso, resend_iso, now_iso))

                conn.execute("""
                    UPDATE users
                    SET email_otp_hash = ?, email_otp_expires_at = ?, email_otp_attempts = 0, email_otp_sent_at = ?, updated_at = ?
                    WHERE user_id = ?
                """, (otp_hash, exp_iso, now_iso, now_iso, user["user_id"]))

            dispatch_res = EmailService.send_login_otp(email, otp_plain)

            delivery_status = dispatch_res.get("status", "QUEUED")
            delivery_blocked = dispatch_res.get("delivery_blocked", False)

            if delivery_status not in ("SENT", "ACCEPTED"):
                delivery_status = "FAILED"
                delivery_blocked = True
                msg = "Email delivery provider encountered high load. Please use the Resend code button to retry delivery."
            else:
                delivery_status = "ACCEPTED"
                delivery_blocked = False
                msg = "Email provider accepted the message"

            return {
                "status": "EMAIL_OTP_REQUIRED",
                "challenge_id": challenge_id,
                "email_masked": mask_email(email),
                "expires_in_seconds": OTP_VALIDITY_SECONDS,
                "requires_2fa": bool(user["two_factor_enabled"] or user["role"] in ("ADMIN", "OWNER")),
                "delivery_status": delivery_status,
                "delivery_blocked": delivery_blocked,
                "provider_response": dispatch_res.get("provider_response", ""),
                "message": msg
            }
        finally:
            conn.close()

    @staticmethod
    def verify_login_otp(
        challenge_id: str,
        otp_code: str,
        totp_code: Optional[str] = None,
        remember_me: bool = False
    ) -> Dict[str, Any]:
        """
        Step 2 of Mandatory Email OTP Login Flow:
        Verifies the hashed OTP against the challenge.
        Enforces expiration, attempt limits, and 2FA (for Admin/Owner or enrolled accounts).
        Creates session upon successful verification (24 hours if remember_me is enabled).
        """
        if not challenge_id or not otp_code or len(otp_code.strip()) != 6:
            raise HTTPException(status_code=400, detail="Invalid verification parameters. A 6-digit code is required.")

        clean_otp = otp_code.strip()
        conn = get_db_connection()
        try:
            challenge = conn.execute("""
                SELECT challenge_id, user_id, otp_hash, otp_salt, expires_at, attempts_left, verified
                FROM login_challenges WHERE challenge_id = ?
            """, (challenge_id,)).fetchone()

            if not challenge or challenge["verified"]:
                raise HTTPException(status_code=401, detail="Invalid or expired verification session. Please login again.")

            if challenge["attempts_left"] <= 0:
                raise HTTPException(status_code=401, detail="Maximum verification attempts exceeded. Please initiate a new login.")

            exp_dt = datetime.fromisoformat(challenge["expires_at"].replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > exp_dt:
                raise HTTPException(status_code=401, detail="Verification code has expired. Please request a new code.")

            computed_hash = _compute_otp_hash(clean_otp, challenge["otp_salt"] or "")
            is_valid = hmac.compare_digest(computed_hash, challenge["otp_hash"])

            if not is_valid:
                new_attempts = challenge["attempts_left"] - 1
                with conn:
                    conn.execute("UPDATE login_challenges SET attempts_left = ? WHERE challenge_id = ?", (new_attempts, challenge_id))
                if new_attempts <= 0:
                    raise HTTPException(status_code=401, detail="Invalid code. Maximum attempts reached. Please login again.")
                raise HTTPException(status_code=401, detail=f"Invalid verification code. Attempts remaining: {new_attempts}")

            user = conn.execute("""
                SELECT user_id, email, username, role, status, email_verified, kyc_status,
                       first_name, last_name, country, two_factor_secret, two_factor_enabled,
                       must_change_password
                FROM users WHERE user_id = ?
            """, (challenge["user_id"],)).fetchone()

            if not user or user["status"] == "BLOCKED":
                raise HTTPException(status_code=403, detail="Account is blocked by administrator.")

            requires_2fa = bool(user["two_factor_enabled"] or user["role"] in ("ADMIN", "OWNER"))
            if requires_2fa:
                if not totp_code:
                    return {
                        "status": "TOTP_2FA_REQUIRED",
                        "challenge_id": challenge_id,
                        "email_masked": mask_email(user["email"]),
                        "message": "Two-factor authentication code required."
                    }
                if not verify_totp_code(user["two_factor_secret"], totp_code):
                    raise HTTPException(status_code=401, detail="Invalid 2FA authenticator code.")

            with conn:
                conn.execute("UPDATE login_challenges SET verified = 1, attempts_left = 0 WHERE challenge_id = ?", (challenge_id,))

            now = datetime.now(timezone.utc)
            session_duration = timedelta(hours=24) if remember_me else timedelta(days=SESSION_DURATION_DAYS)
            expires_at = now + session_duration
            now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
            exp_iso = expires_at.strftime("%Y-%m-%dT%H:%M:%SZ")

            session_id = f"SES-{secrets.token_hex(8).upper()}"
            payload = {
                "sub": user["user_id"],
                "email": user["email"],
                "role": user["role"],
                "session_id": session_id,
                "remember_me": bool(remember_me),
                "exp": int(expires_at.timestamp())
            }
            token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
            token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

            with conn:
                conn.execute("""
                    INSERT INTO sessions (session_id, user_id, token_hash, expires_at, revoked, created_at)
                    VALUES (?, ?, ?, ?, 0, ?)
                """, (session_id, user["user_id"], token_hash, exp_iso, now_iso))

                log_id = f"AUD-{secrets.token_hex(6).upper()}"
                conn.execute("""
                    INSERT INTO audit_logs (log_id, actor_id, action, target_user_id, details_json, created_at)
                    VALUES (?, ?, 'USER_LOGIN_OTP_VERIFIED', ?, ?, ?)
                """, (log_id, user["user_id"], user["user_id"], f'{{"session_id": "{session_id}", "role": "{user["role"]}"}}', now_iso))

            display_username = user["username"] or f"{user['first_name'] or ''} {user['last_name'] or ''}".strip() or user["email"].split("@")[0]

            return {
                "status": "SUCCESS",
                "token": token,
                "token_type": "bearer",
                "expires_at": exp_iso,
                "user": {
                    "user_id": user["user_id"],
                    "email": user["email"],
                    "username": display_username,
                    "role": user["role"],
                    "status": user["status"],
                    "first_name": user["first_name"] or "",
                    "last_name": user["last_name"] or "",
                    "country": user["country"] or "SG",
                    "email_verified": bool(user["email_verified"]),
                    "two_factor_enabled": bool(user["two_factor_enabled"]),
                    "must_change_password": bool(user["must_change_password"]),
                    "kyc_status": user["kyc_status"]
                }
            }
        finally:
            conn.close()

    @staticmethod
    def resend_login_otp(challenge_id: str) -> Dict[str, Any]:
        """Resends email OTP enforcing cooldown rate limits."""
        conn = get_db_connection()
        try:
            challenge = conn.execute("""
                SELECT challenge_id, user_id, resend_after, verified FROM login_challenges WHERE challenge_id = ?
            """, (challenge_id,)).fetchone()

            if not challenge or challenge["verified"]:
                raise HTTPException(status_code=400, detail="Invalid verification challenge.")

            resend_dt = datetime.fromisoformat(challenge["resend_after"].replace("Z", "+00:00"))
            if datetime.now(timezone.utc) < resend_dt:
                wait_sec = max(1, int((resend_dt - datetime.now(timezone.utc)).total_seconds()))
                raise HTTPException(status_code=429, detail=f"Please wait {wait_sec}s before requesting a new code.")

            user = conn.execute("SELECT email FROM users WHERE user_id = ?", (challenge["user_id"],)).fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="User not found.")

            otp_plain = f"{secrets.randbelow(900000) + 100000}"
            otp_salt = secrets.token_hex(16)
            otp_hash = _compute_otp_hash(otp_plain, otp_salt)

            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(seconds=OTP_VALIDITY_SECONDS)
            resend_after = now + timedelta(seconds=OTP_COOLDOWN_SECONDS)

            with conn:
                conn.execute("""
                    UPDATE login_challenges
                    SET otp_hash = ?, otp_salt = ?, expires_at = ?, attempts_left = 3, resend_after = ?
                    WHERE challenge_id = ?
                """, (otp_hash, otp_salt, expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"), resend_after.strftime("%Y-%m-%dT%H:%M:%SZ"), challenge_id))

            dispatch_res = EmailService.send_login_otp(user["email"], otp_plain)

            delivery_status = dispatch_res.get("status", "QUEUED")
            delivery_blocked = dispatch_res.get("delivery_blocked", False)

            if delivery_status in ("SENT", "ACCEPTED"):
                msg = "Email provider accepted the message"
            elif delivery_blocked or delivery_status == "FAILED":
                msg = "Could not send verification email. Please retry."
            else:
                msg = "Delivery status pending"

            return {
                "status": "RESENT",
                "challenge_id": challenge_id,
                "expires_in_seconds": OTP_VALIDITY_SECONDS,
                "delivery_status": delivery_status,
                "delivery_blocked": delivery_blocked,
                "provider_response": dispatch_res.get("provider_response", ""),
                "message": msg
            }
        finally:
            conn.close()

    @staticmethod
    def login_user(email: str, password: str, totp_code: Optional[str] = None) -> Dict[str, Any]:
        """Unified login endpoint: initiates email OTP challenge."""
        return AuthManager.initiate_login(email, password)

    # ─── Administrator Provisioning & Invitation Flow ─────────────

    @staticmethod
    def provision_admin(
        email: str = "go@bitdex.ltd",
        first_name: str = "Bitdex",
        last_name: str = "Administrator",
        country: str = "SG",
        initial_password: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Securely provisions the requested administrator (go@bitdex.ltd).
        Checks for duplicates, establishes verified email and mandatory 2FA,
        generates an invitation/password-setup token, and logs audit record.
        """
        email = email.strip().lower()
        conn = get_db_connection()
        try:
            with conn:
                existing = conn.execute("SELECT user_id, email, role, status FROM users WHERE email = ?", (email,)).fetchone()
                if existing:
                    return {
                        "status": "ALREADY_EXISTS",
                        "user_id": existing["user_id"],
                        "email": existing["email"],
                        "role": existing["role"],
                        "message": f"Administrator '{email}' already exists. Refusing duplicate provisioning."
                    }

                user_id = f"USR-ADM-{secrets.token_hex(4).upper()}"
                now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                inv_token = secrets.token_urlsafe(32)
                inv_expires = (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")

                if initial_password:
                    pw_hash = hash_password(initial_password)
                    must_change = 0
                else:
                    pw_hash = hash_password(secrets.token_hex(24))
                    must_change = 1

                totp_secret = "JBSWY3DPEHPK3PXP"
                username = f"{first_name} {last_name}".strip() or "Bitdex Admin"

                conn.execute("""
                    INSERT INTO users (
                        user_id, email, username, password_hash, role, status, email_verified,
                        kyc_status, first_name, last_name, country, two_factor_secret,
                        two_factor_enabled, must_change_password, invitation_token,
                        invitation_expires_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 'ADMIN', 'ACTIVE', 1, 'APPROVED', ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
                """, (user_id, email, username, pw_hash, first_name, last_name, country, totp_secret, must_change, inv_token, inv_expires, now_iso, now_iso))

                acct_id = f"BAC-{secrets.token_hex(4).upper()}"
                conn.execute("""
                    INSERT INTO billing_accounts (account_id, user_id, prepaid_credits_usd, total_deposited_usd, total_fees_paid_usd, updated_at)
                    VALUES (?, ?, 0.0, 0.0, 0.0, ?)
                """, (acct_id, user_id, now_iso))

                pol_id = f"POL-{secrets.token_hex(4).upper()}"
                conn.execute("""
                    INSERT INTO fee_policies (
                        policy_id, user_id, version, activation_fee_enabled, activation_fee_usd,
                        activation_fee_charged, execution_fee_enabled, execution_fee_usd,
                        ai_research_fee_enabled, ai_research_fee_usd, ai_research_fee_cents, fee_waived, currency, updated_at
                    ) VALUES (?, ?, 1, 0, 0.0, 1, 0, 0.0, 0, 0.0, 0, 1, 'USD', ?)
                """, (pol_id, user_id, now_iso))

                log_id = f"AUD-{secrets.token_hex(6).upper()}"
                conn.execute("""
                    INSERT INTO audit_logs (log_id, actor_id, action, target_user_id, details_json, created_at)
                    VALUES (?, 'SYSTEM_CLI', 'ADMIN_PROVISIONED', ?, ?, ?)
                """, (log_id, user_id, f'{{"email": "{email}", "role": "ADMIN", "invitation": true}}', now_iso))

            invitation_url = f"https://bitdex.ltd/?invitation_token={inv_token}"
            EmailService.send_admin_invitation(email, invitation_url)

            logger.info(f"Administrator successfully provisioned: {email} (User ID: {user_id})")
            return {
                "status": "PROVISIONED",
                "user_id": user_id,
                "email": email,
                "username": username,
                "email_masked": mask_email(email),
                "role": "ADMIN",
                "email_verified": True,
                "two_factor_enforced": True,
                "must_change_password": bool(must_change),
                "invitation_token": inv_token,
                "invitation_url": invitation_url,
                "invitation_expires": inv_expires
            }
        finally:
            conn.close()

    @staticmethod
    def setup_password_with_invitation(invitation_token: str, new_password: str) -> Dict[str, Any]:
        """Sets account password via one-time invitation token."""
        if len(new_password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters long.")

        conn = get_db_connection()
        try:
            with conn:
                user = conn.execute("""
                    SELECT user_id, email, invitation_expires_at FROM users WHERE invitation_token = ?
                """, (invitation_token,)).fetchone()

                if not user:
                    raise HTTPException(status_code=400, detail="Invalid or expired invitation token.")

                exp_str = user["invitation_expires_at"]
                if exp_str:
                    exp_dt = datetime.fromisoformat(exp_str.replace("Z", "+00:00"))
                    if datetime.now(timezone.utc) > exp_dt:
                        raise HTTPException(status_code=400, detail="Invitation token has expired.")

                new_hash = hash_password(new_password)
                now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

                conn.execute("""
                    UPDATE users
                    SET password_hash = ?, invitation_token = '', invitation_expires_at = '',
                        must_change_password = 0, email_verified = 1, updated_at = ?
                    WHERE user_id = ?
                """, (new_hash, now_iso, user["user_id"]))

                conn.execute("UPDATE sessions SET revoked = 1 WHERE user_id = ?", (user["user_id"],))

                log_id = f"AUD-{secrets.token_hex(6).upper()}"
                conn.execute("""
                    INSERT INTO audit_logs (log_id, actor_id, action, target_user_id, details_json, created_at)
                    VALUES (?, ?, 'PASSWORD_SET_VIA_INVITATION', ?, '{"status": "completed"}', ?)
                """, (log_id, user["user_id"], user["user_id"], now_iso))

                return {"status": "SUCCESS", "message": "Password initialized successfully. Please sign in with your credentials."}
        finally:
            conn.close()

    @staticmethod
    def setup_2fa(user_id: str) -> Dict[str, Any]:
        """Generates a Base32 TOTP secret and QR code data URL for voluntary user enrollment."""
        secret = base64.b32encode(secrets.token_bytes(10)).decode("utf-8").replace("=", "")
        conn = get_db_connection()
        try:
            with conn:
                user = conn.execute("SELECT email, two_factor_enabled FROM users WHERE user_id = ?", (user_id,)).fetchone()
                if not user:
                    raise HTTPException(status_code=404, detail="User not found.")

                uri = f"otpauth://totp/Bitdex:{user['email']}?secret={secret}&issuer=Bitdex%20Institutional"
                now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                # Store pending secret; DO NOT set two_factor_enabled = 1 until first code verified!
                conn.execute("UPDATE users SET two_factor_secret = ?, updated_at = ? WHERE user_id = ?", (secret, now_iso, user_id))

            qr_data_url = ""
            try:
                import qrcode, io
                qr = qrcode.QRCode(box_size=6, border=2)
                qr.add_data(uri)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                qr_data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("utf-8")
            except Exception as e:
                logger.warning(f"QR code generation failed: {e}")

            formatted_key = " ".join([secret[i:i+4] for i in range(0, len(secret), 4)])

            return {
                "status": "SUCCESS",
                "secret": secret,
                "totp_secret": secret,
                "manual_key": formatted_key,
                "manual_entry_key": formatted_key,
                "otpauth_uri": uri,
                "qr_code_url": qr_data_url,
                "qr_uri": qr_data_url,
                "totp_enabled": bool(user["two_factor_enabled"]),
                "instructions": "Scan the QR code with Google Authenticator, Authy, or 1Password, or enter the manual key."
            }
        finally:
            conn.close()

    @staticmethod
    def disable_2fa(user_id: str, password: str) -> Dict[str, Any]:
        """Disables voluntary TOTP authentication after verifying account password."""
        conn = get_db_connection()
        try:
            user = conn.execute("SELECT user_id, password_hash, role FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="User not found.")
            if user["role"] in ("ADMIN", "OWNER"):
                raise HTTPException(status_code=403, detail="Privileged administrator accounts cannot disable mandatory two-factor authentication.")
            if not verify_password(password, user["password_hash"]):
                raise HTTPException(status_code=401, detail="Incorrect password. Authorization denied.")

            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            with conn:
                conn.execute("UPDATE users SET two_factor_enabled = 0, two_factor_secret = '', updated_at = ? WHERE user_id = ?", (now_iso, user_id))
                log_id = f"AUD-{secrets.token_hex(6).upper()}"
                conn.execute("""
                    INSERT INTO audit_logs (log_id, actor_id, action, target_user_id, details_json, created_at)
                    VALUES (?, ?, '2FA_DISABLED', ?, '{"method": "RFC_6238_TOTP"}', ?)
                """, (log_id, user_id, user_id, now_iso))

            return {"status": "SUCCESS", "message": "Two-factor authentication has been disabled."}
        finally:
            conn.close()

    @staticmethod
    def verify_and_enable_2fa(user_id: str, totp_code: str) -> Dict[str, Any]:
        conn = get_db_connection()
        try:
            user = conn.execute("SELECT two_factor_secret FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if not user or not user["two_factor_secret"]:
                raise HTTPException(status_code=400, detail="2FA setup has not been initiated.")

            if not verify_totp_code(user["two_factor_secret"], totp_code):
                raise HTTPException(status_code=400, detail="Invalid TOTP verification code. Clock skew exceeded or code incorrect.")

            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            with conn:
                conn.execute("UPDATE users SET two_factor_enabled = 1, updated_at = ? WHERE user_id = ?", (now_iso, user_id))
                log_id = f"AUD-{secrets.token_hex(6).upper()}"
                conn.execute("""
                    INSERT INTO audit_logs (log_id, actor_id, action, target_user_id, details_json, created_at)
                    VALUES (?, ?, '2FA_ENABLED', ?, '{"method": "RFC_6238_TOTP"}', ?)
                """, (log_id, user_id, user_id, now_iso))

            return {"status": "SUCCESS", "message": "Two-factor authentication successfully enabled."}
        finally:
            conn.close()

    # ─── Account Settings: Change Username, Email & Password ────────

    @staticmethod
    def change_username(user_id: str, new_username: str) -> Dict[str, Any]:
        """
        Validates allowed characters and length, enforces uniqueness,
        updates account atomically, and writes an audit event.
        """
        clean_user = new_username.strip()
        if len(clean_user) < 3 or len(clean_user) > 30:
            raise HTTPException(status_code=400, detail="Username must be between 3 and 30 characters.")
        if not re.match(r"^[a-zA-Z0-9_.-]+$", clean_user):
            raise HTTPException(status_code=400, detail="Username may only contain letters, numbers, dots, underscores, and hyphens.")

        conn = get_db_connection()
        try:
            with conn:
                existing = conn.execute(
                    "SELECT user_id FROM users WHERE LOWER(username) = LOWER(?) AND user_id != ?",
                    (clean_user, user_id)
                ).fetchone()
                if existing:
                    raise HTTPException(status_code=400, detail="This username is already taken. Please choose another.")

                now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                conn.execute(
                    "UPDATE users SET username = ?, updated_at = ? WHERE user_id = ?",
                    (clean_user, now_iso, user_id)
                )

                log_id = f"AUD-{secrets.token_hex(6).upper()}"
                conn.execute("""
                    INSERT INTO audit_logs (log_id, actor_id, action, target_user_id, details_json, created_at)
                    VALUES (?, ?, 'USERNAME_CHANGED', ?, ?, ?)
                """, (log_id, user_id, user_id, json.dumps({"new_username": clean_user}), now_iso))

            return {
                "status": "SUCCESS",
                "username": clean_user,
                "message": "Username updated successfully."
            }
        finally:
            conn.close()

    @staticmethod
    def initiate_email_change(user_id: str, current_password: str, new_email: str) -> Dict[str, Any]:
        """
        Validates credentials and proposed new email.
        If email already exists, shows duplicate notification.
        If available, sends short-lived OTP to the NEW email address.
        """
        clean_email = new_email.strip().lower()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", clean_email):
            raise HTTPException(status_code=400, detail="Please enter a valid email address.")

        conn = get_db_connection()
        try:
            user = conn.execute(
                "SELECT user_id, email, password_hash FROM users WHERE user_id = ?",
                (user_id,)
            ).fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="User account not found.")
            if current_password and not verify_password(current_password, user["password_hash"]):
                raise HTTPException(status_code=401, detail="Current password is incorrect.")

            if clean_email == user["email"].lower():
                raise HTTPException(status_code=400, detail="Proposed new email cannot be the same as your current email.")

            # Check if email is already taken
            conflict = conn.execute(
                "SELECT user_id FROM users WHERE LOWER(email) = LOWER(?)",
                (clean_email,)
            ).fetchone()
            if conflict:
                raise HTTPException(
                    status_code=409,
                    detail="This email address is already registered. Please use another email."
                )

            # Check rate limiting / cooldown on active challenges
            recent = conn.execute("""
                SELECT resend_after FROM email_change_challenges
                WHERE user_id = ? AND verified = 0 AND expires_at > ?
                ORDER BY created_at DESC LIMIT 1
            """, (user_id, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))).fetchone()

            if recent and recent["resend_after"]:
                resend_dt = datetime.fromisoformat(recent["resend_after"].replace("Z", "+00:00"))
                if datetime.now(timezone.utc) < resend_dt:
                    wait_sec = max(1, int((resend_dt - datetime.now(timezone.utc)).total_seconds()))
                    raise HTTPException(status_code=429, detail=f"Please wait {wait_sec}s before requesting a new verification code.")

            otp_plain = f"{secrets.randbelow(900000) + 100000}"
            otp_salt = secrets.token_hex(16)
            otp_hash = _compute_otp_hash(otp_plain, otp_salt)

            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(seconds=600)  # 10 minutes
            resend_after = now + timedelta(seconds=60)  # 60s cooldown
            now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
            exp_iso = expires_at.strftime("%Y-%m-%dT%H:%M:%SZ")
            resend_iso = resend_after.strftime("%Y-%m-%dT%H:%M:%SZ")

            challenge_id = f"EMC-{secrets.token_hex(16)}"

            with conn:
                # Mark previous unverified challenges as inactive
                conn.execute(
                    "UPDATE email_change_challenges SET attempts_left = 0 WHERE user_id = ? AND verified = 0",
                    (user_id,)
                )
                conn.execute("""
                    INSERT INTO email_change_challenges (
                        challenge_id, user_id, old_email, new_email, otp_salt, otp_hash,
                        expires_at, attempts_left, resend_after, verified, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 3, ?, 0, ?)
                """, (challenge_id, user_id, user["email"], clean_email, otp_salt, otp_hash, exp_iso, resend_iso, now_iso))

            # Dispatch OTP to NEW email address
            EmailService.send_email_change_otp(clean_email, otp_plain)

            return {
                "status": "OTP_SENT",
                "challenge_id": challenge_id,
                "masked_new_email": mask_email(clean_email),
                "expires_in_seconds": 600,
                "resend_cooldown_seconds": 60,
                "message": f"A 6-digit confirmation code has been dispatched to {mask_email(clean_email)}."
            }
        finally:
            conn.close()

    @staticmethod
    def verify_email_change(
        user_id: str,
        challenge_id: str,
        otp_code: str,
        client_ip: str = "",
        client_country: str = "SG"
    ) -> Dict[str, Any]:
        """
        Verifies OTP server-side with expiry and attempt limits,
        rechecks uniqueness inside transaction, updates email, and notifies old+new addresses.
        """
        clean_otp = otp_code.strip()
        conn = get_db_connection()
        try:
            challenge = conn.execute("""
                SELECT challenge_id, user_id, old_email, new_email, otp_salt, otp_hash,
                       expires_at, attempts_left, verified
                FROM email_change_challenges WHERE challenge_id = ? AND user_id = ?
            """, (challenge_id, user_id)).fetchone()

            if not challenge or challenge["verified"]:
                raise HTTPException(status_code=400, detail="Invalid or already verified email change request.")

            if challenge["attempts_left"] <= 0:
                raise HTTPException(status_code=400, detail="Maximum verification attempts reached. Please request a new code.")

            exp_dt = datetime.fromisoformat(challenge["expires_at"].replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > exp_dt:
                raise HTTPException(status_code=400, detail="Verification code has expired. Please request a new code.")

            computed_hash = _compute_otp_hash(clean_otp, challenge["otp_salt"] or "")
            if not hmac.compare_digest(computed_hash, challenge["otp_hash"]):
                new_attempts = challenge["attempts_left"] - 1
                with conn:
                    conn.execute(
                        "UPDATE email_change_challenges SET attempts_left = ? WHERE challenge_id = ?",
                        (new_attempts, challenge_id)
                    )
                if new_attempts <= 0:
                    raise HTTPException(status_code=400, detail="Invalid code. Maximum attempts reached. Please request a new code.")
                raise HTTPException(status_code=400, detail=f"Invalid code. {new_attempts} attempt(s) remaining.")

            new_email = challenge["new_email"]
            old_email = challenge["old_email"]
            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            with conn:
                # Recheck uniqueness inside transaction
                conflict = conn.execute(
                    "SELECT user_id FROM users WHERE LOWER(email) = LOWER(?) AND user_id != ?",
                    (new_email, user_id)
                ).fetchone()
                if conflict:
                    raise HTTPException(status_code=409, detail="This email address is already registered. Please use another email.")

                conn.execute(
                    "UPDATE users SET email = ?, email_verified = 1, updated_at = ? WHERE user_id = ?",
                    (new_email, now_iso, user_id)
                )

                conn.execute(
                    "UPDATE email_change_challenges SET verified = 1, attempts_left = 0 WHERE challenge_id = ?",
                    (challenge_id,)
                )

                log_id = f"AUD-{secrets.token_hex(6).upper()}"
                conn.execute("""
                    INSERT INTO audit_logs (log_id, actor_id, action, target_user_id, details_json, created_at)
                    VALUES (?, ?, 'EMAIL_CHANGED', ?, ?, ?)
                """, (log_id, user_id, user_id, json.dumps({
                    "old_email": old_email,
                    "new_email": new_email,
                    "ip": client_ip,
                    "country": client_country
                }), now_iso))

            # Send security notification to BOTH old and new email addresses
            EmailService.send_email_change_security_notice(
                old_email, old_email, new_email, client_ip, client_country, now_iso
            )
            EmailService.send_email_change_security_notice(
                new_email, old_email, new_email, client_ip, client_country, now_iso
            )

            return {
                "status": "SUCCESS",
                "new_email": new_email,
                "message": "Account email address updated successfully."
            }
        finally:
            conn.close()

    @staticmethod
    def change_password(
        user_id: str,
        current_password: str,
        new_password: str,
        confirm_password: str,
        client_ip: str = "",
        client_country: str = "SG",
        current_session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validates current password, enforces password strength and confirmation match,
        updates password hash atomically, revokes other sessions, and sends security alert.
        """
        if new_password != confirm_password:
            raise HTTPException(status_code=400, detail="New password and confirmation do not match.")
        if len(new_password) < 8:
            raise HTTPException(status_code=400, detail="New password must be at least 8 characters long.")
        if current_password == new_password:
            raise HTTPException(status_code=400, detail="New password cannot be the same as your current password.")

        conn = get_db_connection()
        try:
            user = conn.execute(
                "SELECT user_id, email, password_hash FROM users WHERE user_id = ?",
                (user_id,)
            ).fetchone()
            if not user or not verify_password(current_password, user["password_hash"]):
                raise HTTPException(status_code=401, detail="Current password is incorrect.")

            new_hash = hash_password(new_password)
            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            with conn:
                conn.execute("""
                    UPDATE users
                    SET password_hash = ?, must_change_password = 0, updated_at = ?
                    WHERE user_id = ?
                """, (new_hash, now_iso, user_id))

                # Revoke all other sessions for this user (preserving current session if provided)
                if current_session_id:
                    conn.execute(
                        "UPDATE sessions SET revoked = 1 WHERE user_id = ? AND session_id != ?",
                        (user_id, current_session_id)
                    )
                else:
                    conn.execute("UPDATE sessions SET revoked = 1 WHERE user_id = ?", (user_id,))

                log_id = f"AUD-{secrets.token_hex(6).upper()}"
                conn.execute("""
                    INSERT INTO audit_logs (log_id, actor_id, action, target_user_id, details_json, created_at)
                    VALUES (?, ?, 'PASSWORD_CHANGED', ?, ?, ?)
                """, (log_id, user_id, user_id, json.dumps({
                    "ip": client_ip,
                    "country": client_country,
                    "other_sessions_revoked": True
                }), now_iso))

            # Send security notification
            EmailService.send_password_change_security_notice(
                user["email"], client_ip, client_country, now_iso
            )

            return {
                "status": "SUCCESS",
                "message": "Password updated successfully. Other active sessions have been revoked."
            }
        finally:
            conn.close()

    @staticmethod
    def get_user_from_token(token: str) -> Dict[str, Any]:
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            user_id = payload["sub"]
            session_id = payload.get("session_id")
        except jwt.PyJWTError:
            raise HTTPException(status_code=401, detail="Invalid or expired session token.")

        conn = get_db_connection()
        try:
            if session_id:
                sess = conn.execute("SELECT revoked FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
                if not sess or sess["revoked"]:
                    raise HTTPException(status_code=401, detail="Session has been revoked or logged out.")

            user = conn.execute("""
                SELECT user_id, email, username, role, status, email_verified, kyc_status,
                       first_name, last_name, country, two_factor_enabled, must_change_password
                FROM users WHERE user_id = ?
            """, (user_id,)).fetchone()

            if not user or user["status"] == "BLOCKED":
                raise HTTPException(status_code=403, detail="Account is blocked by administrator.")

            u_dict = dict(user)
            if not u_dict.get("username"):
                u_dict["username"] = f"{u_dict.get('first_name') or ''} {u_dict.get('last_name') or ''}".strip() or u_dict["email"].split("@")[0]
            return u_dict
        finally:
            conn.close()

    @staticmethod
    def logout(session_id: str):
        conn = get_db_connection()
        try:
            with conn:
                conn.execute("UPDATE sessions SET revoked = 1 WHERE session_id = ?", (session_id,))
        finally:
            conn.close()

    @staticmethod
    def rotate_password(
        user_id: str,
        old_password: str,
        new_password: str,
        confirm_password: Optional[str] = None
    ) -> bool:
        """
        Requirement 11 — End-to-End Update Password Flow:
        Verifies current password server-side, checks confirmation match and password policy,
        updates bcrypt hash, revokes sessions, logs audit event, and sends security notification.
        """
        if not new_password or len(new_password) < 8:
            raise HTTPException(status_code=400, detail="New password must be at least 8 characters long.")
        if confirm_password is not None and new_password != confirm_password:
            raise HTTPException(status_code=400, detail="New password and confirm password do not match.")
        if old_password == new_password:
            raise HTTPException(status_code=400, detail="New password must be different from your current password.")

        conn = get_db_connection()
        try:
            with conn:
                user = conn.execute("SELECT email, password_hash FROM users WHERE user_id = ?", (user_id,)).fetchone()
                if not user or not verify_password(old_password, user["password_hash"]):
                    raise HTTPException(status_code=400, detail="Current password incorrect.")

                new_hash = hash_password(new_password)
                now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

                conn.execute("""
                    UPDATE users
                    SET password_hash = ?, must_change_password = 0, updated_at = ?
                    WHERE user_id = ?
                """, (new_hash, now_iso, user_id))

                conn.execute("UPDATE sessions SET revoked = 1 WHERE user_id = ?", (user_id,))

                log_id = f"AUD-{secrets.token_hex(6).upper()}"
                conn.execute("""
                    INSERT INTO audit_logs (log_id, actor_id, action, target_user_id, details_json, created_at)
                    VALUES (?, ?, 'PASSWORD_ROTATED', ?, '{"sessions_revoked": true}', ?)
                """, (log_id, user_id, user_id, now_iso))

            EmailService.send_security_notification(
                user["email"],
                "Password Updated",
                "Your Bitdex account password was changed from your account security settings, and previous sessions have been revoked."
            )

            return True
        finally:
            conn.close()

    @staticmethod
    def seed_initial_accounts():
        """
        Seeds/provisions:
        1. Official Bitdex Administrator (go@bitdex.ltd) with mandatory 2FA.
        2. Platform Owner (owner@bitdex.ltd / owner@tauric.com).
        3. Test Customer (test.customer@bitdex.ltd) clearly labelled with NO live trading authority.
        """
        admin_pass = os.getenv("TAURIC_ADMIN_INITIAL_PASSWORD", "AdminSecurePass2026!")
        owner_pass = os.getenv("TAURIC_OWNER_INITIAL_PASSWORD", "OwnerSecurePass2026!")
        test_cust_pass = os.getenv("TAURIC_TEST_CUSTOMER_PASSWORD", "TestCustomer2026!")

        # 1. Provision official Bitdex administrator go@bitdex.ltd
        AuthManager.provision_admin(
            email="go@bitdex.ltd",
            first_name="Bitdex",
            last_name="Administrator",
            country="SG",
            initial_password=admin_pass
        )

        conn = get_db_connection()
        try:
            # Ensure go@bitdex.ltd has the active admin password & 2FA in staging
            admin_row = conn.execute("SELECT user_id FROM users WHERE email = 'go@bitdex.ltd'").fetchone()
            if admin_row:
                conn.execute(
                    "UPDATE users SET username = 'Bitdex Admin', first_name = 'Bitdex', last_name = 'Administrator', role = 'ADMIN', two_factor_secret = 'JBSWY3DPEHPK3PXP', two_factor_enabled = 1, email_verified = 1, password_hash = ? WHERE user_id = ?",
                    (hash_password(admin_pass), admin_row["user_id"])
                )
                conn.commit()

            # 2. Owner account
            owner_row = conn.execute("SELECT user_id FROM users WHERE email IN ('owner@bitdex.ltd', 'owner@tauric.com')").fetchone()
            if not owner_row:
                owner_user = AuthManager.register_user(
                    email="owner@bitdex.ltd",
                    password=owner_pass,
                    role="OWNER",
                    first_name="Platform",
                    last_name="Owner",
                    username="Platform Owner",
                    country="SG",
                    status="ACTIVE",
                    email_verified=True,
                    kyc_status="APPROVED",
                    allow_privileged_seed=True
                )
                conn.execute("UPDATE users SET role = 'OWNER', two_factor_secret = 'JBSWY3DPEHPK3PXP', two_factor_enabled = 1, must_change_password = 1 WHERE user_id = ?", (owner_user["user_id"],))
                conn.commit()
                logger.info("Bootstrap Owner account seeded: owner@bitdex.ltd")
            else:
                conn.execute("UPDATE users SET role = 'OWNER', username = 'Platform Owner', two_factor_secret = 'JBSWY3DPEHPK3PXP', two_factor_enabled = 1, password_hash = ? WHERE user_id = ?", (hash_password(owner_pass), owner_row["user_id"]))
                conn.commit()

            # 3. Test Customer (Labelled TEST CUSTOMER, NO live trading authority)
            test_row = conn.execute("SELECT user_id FROM users WHERE email = 'test.customer@bitdex.ltd'").fetchone()
            if not test_row:
                AuthManager.register_user(
                    email="test.customer@bitdex.ltd",
                    password=test_cust_pass,
                    role="CUSTOMER",
                    first_name="TEST",
                    last_name="CUSTOMER",
                    username="Test Customer",
                    country="SG",
                    status="ACTIVE",
                    email_verified=True,
                    kyc_status="NOT_REQUIRED"
                )
                logger.info("Staging Test Customer seeded: test.customer@bitdex.ltd (Read-only, no live authority)")
            else:
                conn.execute("UPDATE users SET username = 'Test Customer', first_name = 'TEST', last_name = 'CUSTOMER', password_hash = ? WHERE user_id = ?", (hash_password(test_cust_pass), test_row["user_id"]))
                conn.commit()
        finally:
            conn.close()

def get_current_user(request: Request) -> Dict[str, Any]:
    """FastAPI dependency for authenticated tenant."""
    auth_header = request.headers.get("authorization", "").strip()
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        return AuthManager.get_user_from_token(token)

    api_key = request.headers.get("x-tauric-api-key", "").strip()
    explicit_user = request.headers.get("x-tauric-user-id", "").strip()
    if api_key and explicit_user:
        conn = get_db_connection()
        try:
            user = conn.execute("SELECT user_id, email, username, role, status, email_verified, kyc_status, first_name, last_name, country, two_factor_enabled, created_at FROM users WHERE user_id = ?", (explicit_user,)).fetchone()
            if user:
                u_dict = dict(user)
                if not u_dict.get("username"):
                    u_dict["username"] = f"{u_dict.get('first_name') or ''} {u_dict.get('last_name') or ''}".strip() or u_dict["email"].split("@")[0]
                return u_dict
        finally:
            conn.close()

    raise HTTPException(status_code=401, detail="Authentication required. Provide a valid Bearer token.")

def get_admin_user(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """FastAPI dependency for Admin role only."""
    if current_user.get("role") not in ("ADMIN", "OWNER"):
        raise HTTPException(status_code=403, detail="Administrative privileges required.")
    return current_user

def assert_tenant_boundary(current_user: Dict[str, Any], target_user_id: str):
    """Ensures customer A cannot access customer B resources."""
    if current_user.get("role") in ("ADMIN", "OWNER"):
        return
    if current_user.get("user_id") != target_user_id:
        raise HTTPException(
            status_code=403,
            detail="Cross-tenant access violation: Cannot access or manipulate another customer's resources."
        )
