import re

with open("/opt/tauric-platform-staging/backend/app/routes/orders.py", "r") as f:
    content = f.read()

# 1. Add GridOrderSubmitRequest
model_target = "class DemoOrderSubmitRequest(BaseModel):"
model_code = """class GridOrderSubmitRequest(BaseModel):
    profile_id: Optional[str] = None
    exchange: str = Field(default="BINANCE")
    symbol: str = Field(..., description="e.g. BTCUSDT")
    strategy_type: str = Field(default="SCALPING_GRID", description="Must be SCALPING_GRID")
    grid_lower_price: float = Field(..., gt=0)
    grid_upper_price: float = Field(..., gt=0)
    grid_count: int = Field(..., ge=3, le=150)
    grid_spacing_pct: float = Field(..., gt=0)
    capital_allocated_usd: float = Field(..., gt=0)
    invalidation_condition: Optional[str] = None
    exit_condition: Optional[str] = None
    idempotency_key: str = Field(..., min_length=4)


class DemoOrderSubmitRequest(BaseModel):"""

if "class GridOrderSubmitRequest" not in content:
    assert model_target in content, "model_target not found!"
    content = content.replace(model_target, model_code, 1)

# 2. Add Guard in submit_demo_order
guard_target = "    # 1. Server-side tenant boundary check on exchange profile"
guard_code = """    # Guard: Reject scalping grid orders sent to Spot endpoint
    if getattr(req, "side", "").upper() in ("SCALP", "SCALPING", "GRID"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Scalping grid strategies must be dispatched to /orders/grid/submit, not the Spot buy/sell endpoint."
        )

    # 1. Server-side tenant boundary check on exchange profile"""

if "detail=\"Scalping grid strategies must be dispatched" not in content:
    assert guard_target in content, "guard_target not found!"
    content = content.replace(guard_target, guard_code, 1)

# 3. Add @orders_router.post("/grid/submit")
endpoint_target = '@orders_router.post("/live/submit")'
endpoint_code = '''@orders_router.post("/grid/submit")
async def submit_grid_order(
    req: GridOrderSubmitRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Submits a Scalping — Grid Strategy execution request.
    Strictly validates grid parameters, risk boundaries, activation status, and credits.
    """
    user_id = None
    user_payload = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        try:
            user_payload = AuthManager.get_user_from_token(token)
            if user_payload:
                user_id = user_payload.get("user_id")
        except HTTPException:
            raise
        except Exception:
            pass

    # Tenant boundary
    if user_id and req.profile_id:
        conn = get_db_connection()
        try:
            conn_row = conn.execute(
                "SELECT user_id FROM user_exchange_connections WHERE account_id = ? AND is_active = 1",
                (req.profile_id,)
            ).fetchone()
            if conn_row and conn_row["user_id"] != user_id and user_payload.get("role") not in ("ADMIN", "OWNER"):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: Exchange connection belongs to another account."
                )
        finally:
            conn.close()

    # Preflight eligibility
    if user_id:
        eligible, reason = FeeEngine.check_trading_preflight_eligibility(
            user_id,
            environment="DEMO",
            estimated_orders_count=1
        )
        if not eligible:
            if "activation" in (reason or "").lower():
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=reason)
            raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=reason)

    # Strategy & Grid Parameter Validations
    if req.strategy_type != "SCALPING_GRID":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Strategy type must be SCALPING_GRID.")

    if req.grid_lower_price >= req.grid_upper_price:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid grid range: Lower price (${req.grid_lower_price}) must be strictly below upper price (${req.grid_upper_price})."
        )

    if req.grid_count < 3 or req.grid_count > 150:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid grid count ({req.grid_count}). Must be between 3 and 150 grids."
        )

    if req.grid_spacing_pct < 0.25:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Grid spacing ({req.grid_spacing_pct:.2f}%) fails minimum 0.25% round-trip fee friction threshold."
        )

    if req.capital_allocated_usd < 15.0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Capital allocated (${req.capital_allocated_usd}) is below minimum grid strategy capital requirement ($15.00)."
        )

    # Atomic fee assessment & idempotency
    fee_assessed = 0.0
    if user_id:
        fee_receipt = FeeEngine.assess_execution_fee(
            user_id=user_id,
            exchange=req.exchange,
            order_id=f"GRID-{req.idempotency_key}",
            fill_id=f"FILL-GRID-{req.idempotency_key}",
            environment="DEMO",
            execution_status="FILLED",
            charge_demo=True
        )
        fee_assessed = fee_receipt.get("fee_charged_usd", 0.30)

    grid_levels = []
    step = (req.grid_upper_price - req.grid_lower_price) / req.grid_count
    for i in range(req.grid_count + 1):
        grid_levels.append(round(req.grid_lower_price + (i * step), 2))

    order_size_per_grid = round(req.capital_allocated_usd / req.grid_count, 2)

    receipt = {
        "client_order_id": f"GRID-{req.idempotency_key}",
        "strategy_label": "Scalping — Grid Strategy",
        "symbol": req.symbol,
        "exchange": req.exchange,
        "status": "ACTIVE_DEMO_GRID",
        "grid_lower_price": req.grid_lower_price,
        "grid_upper_price": req.grid_upper_price,
        "grid_count": req.grid_count,
        "grid_spacing_pct": req.grid_spacing_pct,
        "capital_allocated_usd": req.capital_allocated_usd,
        "order_size_per_grid_usd": order_size_per_grid,
        "grid_levels": grid_levels,
        "invalidation_condition": req.invalidation_condition or f"Price closes below ${round(req.grid_lower_price * 0.965, 2)}",
        "exit_condition": req.exit_condition or f"Price closes above ${round(req.grid_upper_price * 1.035, 2)}",
        "fee_charged_usd": fee_assessed,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    }

    return {
        "status": "SUCCESS",
        "message": f"Successfully initialized Scalping — Grid Strategy ({req.grid_count} grids) for {req.symbol}.",
        "receipt": receipt
    }


@orders_router.post("/live/submit")'''

if '@orders_router.post("/grid/submit")' not in content:
    assert endpoint_target in content, "endpoint_target not found!"
    content = content.replace(endpoint_target, endpoint_code, 1)

with open("/opt/tauric-platform-staging/backend/app/routes/orders.py", "w") as f:
    f.write(content)

print("orders.py updated successfully!")
