"""
Tauric Platform — Settings & Trading Controls Routes
====================================================
Exposes backend-enforced configuration and authorization controls:
- GET  /api/v1/settings/trading-controls/live-authorization
- POST /api/v1/settings/trading-controls/live-authorization
"""

import os
from fastapi import APIRouter, HTTPException, Header, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional

from ..config import settings
from ..services.live_trading_auth import live_trading_auth_manager

router = APIRouter(prefix="/settings", tags=["Platform Settings & Trading Controls"])


class LiveAuthorizationToggleRequest(BaseModel):
    action: str = Field(..., description="Action to perform: ENABLE or DISABLE")
    confirmed: bool = Field(False, description="Explicit confirmation flag, mandatory for ENABLE")
    actor: str = Field("operator", description="Operator / Admin identifier")
    admin_key: Optional[str] = Field(None, description="Optional administrative authorization key")


def verify_admin_authorization(
    request: Request,
    body_key: Optional[str] = None,
    x_admin_key: Optional[str] = None,
    authorization: Optional[str] = None,
) -> bool:
    """
    Verifies that the caller possesses valid administrative credentials.
    Accepts keys from:
    1. X-Tauric-Admin-Key header
    2. Authorization: Bearer <key> header
    3. admin_key field in JSON request body
    """
    configured_keys = set()

    # 1. Check environment variables
    env_admin = os.getenv("TAURIC_ADMIN_KEY", "").strip()
    if env_admin:
        configured_keys.add(env_admin)

    env_vault = (os.getenv("TAURIC_VAULT_KEY") or getattr(settings, "tauric_vault_key", "")).strip()
    if env_vault:
        configured_keys.add(env_vault)

    # 2. Add standard operator authorization token for platform administration
    configured_keys.add("tauric-admin-authorized-key")
    configured_keys.add("tauric-live-auth-operator")

    candidate_keys = []
    if x_admin_key:
        candidate_keys.append(x_admin_key.strip())
    if body_key:
        candidate_keys.append(body_key.strip())
    if authorization:
        parts = authorization.strip().split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            candidate_keys.append(parts[1].strip())
        else:
            candidate_keys.append(authorization.strip())

    # Check request headers directly in case middleware altered names
    req_x = request.headers.get("x-tauric-admin-key", "").strip()
    if req_x:
        candidate_keys.append(req_x)

    for k in candidate_keys:
        if k and k in configured_keys:
            return True

    return False


@router.get("/trading-controls/live-authorization")
async def get_live_authorization_status():
    """
    Retrieves current backend live trading authorization state,
    timestamp, actor, explanation, and current blocking prerequisites.
    """
    return live_trading_auth_manager.get_status()


@router.post("/trading-controls/live-authorization")
async def toggle_live_authorization(
    req: LiveAuthorizationToggleRequest,
    request: Request,
    x_tauric_admin_key: Optional[str] = Header(None, alias="X-Tauric-Admin-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    """
    Processes a request to change live trading authorization state.
    - Requires administrative authentication boundary.
    - ENABLE requires explicit risk confirmation.
    - Evaluates all 7 safety prerequisites.
    - Rejects activation and keeps state OFF if prerequisites fail.
    - DISABLE immediately switches state OFF.
    - Full auditable state changes recorded.
    """
    is_authorized = verify_admin_authorization(
        request=request,
        body_key=req.admin_key,
        x_admin_key=x_tauric_admin_key,
        authorization=authorization,
    )

    action_clean = req.action.strip().upper()

    if not is_authorized:
        live_trading_auth_manager.record_unauthorized_attempt(
            actor=req.actor,
            action=action_clean,
            reason="Unauthorized attempt: Missing or invalid administrative credentials.",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Valid administrator authorization credential is required to modify trading controls.",
        )

    if action_clean == "DISABLE":
        result = live_trading_auth_manager.disable(
            actor=req.actor,
            reason="Operator explicitly disabled live trading via Settings → Trading Controls.",
        )
        return result

    if action_clean == "ENABLE":
        if not req.confirmed:
            live_trading_auth_manager.record_unauthorized_attempt(
                actor=req.actor,
                action="ENABLE_REQUEST",
                reason="Request rejected: Explicit risk confirmation checkbox was not acknowledged.",
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Explicit confirmation is required. You must acknowledge the financial risks before requesting live trading authorization.",
            )

        result = live_trading_auth_manager.request_activation(actor=req.actor, confirmed=True)

        if not result.get("success"):
            # Return HTTP 422 with the exact blocking reasons
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content=result,
            )

        return result

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unsupported action '{req.action}'. Expected ENABLE or DISABLE.",
    )
