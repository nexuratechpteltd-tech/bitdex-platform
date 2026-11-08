import logging
"""
Tauric Platform — Staging API Authentication & Transport Security Boundary (P0 Remediation)
Enforces:
1. Caller authentication (X-Tauric-Api-Key or Authorization: Bearer JWT) on all protected /api/v1/* routes.
2. Transport security gate blocking credential submissions over unencrypted non-loopback HTTP.
"""

import os
import hmac
import hashlib
from typing import Optional
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .services.exchange_framework import get_vault_master_key

PUBLIC_EXEMPT_PATHS = {
    "/",
    "/api/v1/health",
    "/api/v1/health/",
    "/api/v1/grid/symbols",
    "/api/v1/grid/symbols/",
    "/api/v1/markets/overview",
    "/api/v1/markets/overview/",
    "/api/v1/signals",
    "/api/v1/signals/",
    "/api/v1/settings/trading-controls/live-authorization",
    "/api/v1/settings/trading-controls/live-authorization/",
    "/api/v1/saas/auth/register",
    "/api/v1/saas/auth/register/verify-otp",
    "/api/v1/saas/auth/register/resend-otp",
    "/api/v1/saas/auth/login",
    "/api/v1/saas/auth/verify-otp",
    "/api/v1/saas/auth/resend-otp",
    "/api/v1/saas/auth/setup-password",
    "/api/v1/saas/auth/email-status",
    "/api/v1/saas/auth/verify-email",
    "/api/v1/saas/auth/forgot-password",
    "/api/v1/saas/auth/forgot-password/verify-otp",
    "/api/v1/saas/auth/forgot-password/resend-otp",
    "/api/v1/saas/auth/reset-password",
    "/api/v1/saas/webhooks/kyc",
    "/api/v1/saas/webhooks/payment",
    "/api/v1/saas/webhooks/binance-pay",
    "/api/v1/saas/customer/hft/activation/webhook",
}

CREDENTIAL_SUBMISSION_PATHS = (
    "/api/v1/connections/universal",
    "/api/v1/connections/profiles",
    "/api/v1/connections/test",
    "/api/v1/saas/customer/connections",
    "/api/v1/saas/customer/connections/test",
)


def get_api_auth_token() -> str:
    explicit = os.getenv("TAURIC_API_AUTH_TOKEN", "").strip()
    if explicit:
        return explicit
    master_key = get_vault_master_key()
    return hmac.new(master_key, b"tauric-staging-api-auth-v1", hashlib.sha256).hexdigest()


def extract_bearer_or_api_key(request: Request) -> Optional[str]:
    api_key_hdr = request.headers.get("x-tauric-api-key", "").strip()
    if api_key_hdr:
        return api_key_hdr
    auth_hdr = request.headers.get("authorization", "").strip()
    if auth_hdr.lower().startswith("bearer "):
        return auth_hdr[7:].strip()
    return None


def is_credential_submission_request(method: str, path: str) -> bool:
    if method.upper() not in ("POST", "PUT"):
        return False
    clean_path = path.rstrip("/")
    if clean_path in (
        "/api/v1/connections/universal",
        "/api/v1/connections/profiles",
        "/api/v1/connections/test",
        "/api/v1/saas/customer/connections",
        "/api/v1/saas/customer/connections/test",
    ):
        return True
    if clean_path.startswith("/api/v1/connections/profiles/") and method.upper() == "PUT":
        return True
    return False


class TauricSecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path

        # 1. Transport Security Gate for Credential Submissions
        if is_credential_submission_request(request.method, path):
            xf_proto = request.headers.get("x-forwarded-proto", "").strip().lower()
            peer_ip = request.client.host if request.client else "127.0.0.1"
            is_loopback = peer_ip in ("127.0.0.1", "::1", "localhost", "testclient")
            is_https = (xf_proto == "https") or (request.url.scheme == "https")

            if xf_proto == "http" or (not is_loopback and not is_https):
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": (
                            "Transport security violation: credential submission over unencrypted public HTTP "
                            "is strictly prohibited. Use HTTPS/TLS or an encrypted loopback tunnel."
                        ),
                        "error_code": "INSECURE_TRANSPORT_BLOCKED",
                    },
                )

        # 2. Protected API Authentication Boundary
        is_exempt = (path in PUBLIC_EXEMPT_PATHS) or path.startswith("/api/v1/signals") or path.startswith("/api/v1/saas/auth/") or path.startswith("/api/v1/markets") or path.startswith("/api/v1/grid/symbols")
        if path.startswith("/api/v1") and not is_exempt:
            provided = extract_bearer_or_api_key(request)
            try:
                expected = get_api_auth_token()
            except Exception:
                return JSONResponse(
                    status_code=503,
                    content={
                        "detail": "API authentication boundary unavailable: vault key not configured.",
                        "error_code": "AUTH_BOUNDARY_UNCONFIGURED",
                    },
                )

            is_authenticated = False
            if provided:
                # First check platform master token
                if hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8")):
                    is_authenticated = True
                else:
                    # Second check customer JWT session token
                    try:
                        from .services.auth_manager import AuthManager
                        user = AuthManager.get_user_from_token(provided)
                        if user and user.get("status") != "BLOCKED":
                            is_authenticated = True
                        elif user and user.get("status") == "BLOCKED":
                            return JSONResponse(
                                status_code=403,
                                content={
                                    "detail": "Account is blocked by administrator.",
                                    "error_code": "ACCOUNT_BLOCKED",
                                },
                            )
                    except HTTPException as exc:
                        if exc.status_code == 403:
                            return JSONResponse(
                                status_code=403,
                                content={
                                    "detail": exc.detail,
                                    "error_code": "ACCOUNT_BLOCKED",
                                },
                            )
                        is_authenticated = False
                    except Exception:
                        is_authenticated = False

            if not is_authenticated:
                return JSONResponse(
                    status_code=401,
                    content={
                        "detail": "Authentication required: missing or invalid API authentication token.",
                        "error_code": "UNAUTHORIZED_API_REQUEST",
                    },
                )

        try:
            return await call_next(request)
        except Exception as unhandled_exc:
            logging.getLogger("uvicorn.error").error(
                f"Unhandled exception caught by TauricSecurityMiddleware on {request.method} {request.url.path}: {unhandled_exc}",
                exc_info=True,
            )
            return JSONResponse(
                status_code=500,
                content={
                    "status": "ERROR",
                    "detail": "Service temporarily unavailable. Please try again shortly.",
                    "error_code": "INTERNAL_SERVER_ERROR",
                },
            )
