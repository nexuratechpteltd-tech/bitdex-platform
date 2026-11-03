import re

# 1. Update four_engine_orchestrator.py
with open("/opt/tauric-platform-staging/backend/app/services/four_engine_orchestrator.py", "r") as f:
    fe_src = f.read()

# Fix analyze signature
old_sig = """        strategy_name: str = "OctoBot_GridTrend_v2",
        mock_overrides: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:"""

new_sig = """        strategy_name: str = "OctoBot_GridTrend_v2",
        mock_overrides: Optional[Dict[str, Any]] = None,
        simulate_market_closed: bool = False
    ) -> Dict[str, Any]:"""

if old_sig in fe_src:
    fe_src = fe_src.replace(old_sig, new_sig, 1)

# Ensure is_fx_closed uses simulate_market_closed
fe_src = re.sub(
    r'is_fx_closed\s*=\s*(simulate_market_closed\s+or\s+)?session\.get\("market_status"\)\s*==\s*"CLOSED"\s+or\s+not\s+session\.get\("market_open",\s*True\)',
    'is_fx_closed = simulate_market_closed or session.get("market_status") == "CLOSED" or not session.get("market_open", True)',
    fe_src
)

# Ensure is_market_closed in snapshot check uses simulate_market_closed
fe_src = re.sub(
    r'is_market_closed\s*=\s*(simulate_market_closed\s+or\s+)?bool\(snapshot\.get\("market_data",\s*\{\}\)\.get\("is_market_closed",\s*False\)\)',
    'is_market_closed = simulate_market_closed or bool(snapshot.get("market_data", {}).get("is_market_closed", False))',
    fe_src
)

# In contract dictionary assembly, add consensus_verdict
old_contract_header = """"market_data_timestamp": snapshot.get("market_data", {}).get("timestamp_utc", start_iso),
            "is_market_closed": is_market_closed,"""

new_contract_header = """"market_data_timestamp": snapshot.get("market_data", {}).get("timestamp_utc", start_iso),
            "is_market_closed": is_market_closed,
            "consensus_verdict": final_decision,"""

if old_contract_header in fe_src and '"consensus_verdict": final_decision,' not in fe_src:
    fe_src = fe_src.replace(old_contract_header, new_contract_header, 1)

with open("/opt/tauric-platform-staging/backend/app/services/four_engine_orchestrator.py", "w") as f:
    f.write(fe_src)
print("Updated four_engine_orchestrator.py successfully.")

# 2. Update orders.py
with open("/opt/tauric-platform-staging/backend/app/routes/orders.py", "r") as f:
    orders_src = f.read()

# Add strategy to DemoOrderSubmitRequest if not present
old_demo_req = """class DemoOrderSubmitRequest(BaseModel):
    profile_id: Optional[str] = None
    exchange: str = Field(default="BINANCE")
    symbol: str = Field(..., description="e.g. BTCUSDT")
    side: str = Field(..., description="BUY or SELL")"""

new_demo_req = """class DemoOrderSubmitRequest(BaseModel):
    profile_id: Optional[str] = None
    exchange: str = Field(default="BINANCE")
    symbol: str = Field(..., description="e.g. BTCUSDT")
    side: str = Field(..., description="BUY or SELL")
    strategy: Optional[str] = None
    strategy_type: Optional[str] = None"""

if old_demo_req in orders_src:
    orders_src = orders_src.replace(old_demo_req, new_demo_req, 1)

# Ensure scalping guard in submit_demo_order catches side and strategy
old_guard = """    # Guard: Reject scalping grid orders sent to Spot endpoint
    if getattr(req, "side", "").upper() in ("SCALP", "SCALPING", "GRID"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Scalping grid strategies must be dispatched to /orders/grid/submit, not the Spot buy/sell endpoint."
        )"""

new_guard = """    # Guard: Reject scalping grid orders sent to Spot endpoint
    strat = getattr(req, "strategy", "") or getattr(req, "strategy_type", "") or ""
    side_str = getattr(req, "side", "") or ""
    if side_str.upper() in ("SCALP", "SCALPING", "GRID") or strat.upper() in ("SCALP", "SCALPING", "GRID", "SCALPING_GRID"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Scalping grid strategies must be dispatched to /orders/grid/submit, not the Spot buy/sell endpoint."
        )"""

if old_guard in orders_src:
    orders_src = orders_src.replace(old_guard, new_guard, 1)

# Now fix submit_grid_order parameter unpacking and validation
old_grid_val = """    # Strategy & Grid Parameter Validations
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
        )"""

new_grid_val = """    # Parameter resolution
    lower = req.grid_lower_price if req.grid_lower_price is not None else req.lower_price
    upper = req.grid_upper_price if req.grid_upper_price is not None else req.upper_price
    capital = req.capital_allocated_usd if req.capital_allocated_usd is not None else req.capital_usd

    if lower is None or upper is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Grid lower and upper price boundaries are required."
        )

    if capital is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Allocated capital in USD is required."
        )

    # Strategy & Grid Parameter Validations
    if req.strategy_type != "SCALPING_GRID":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Strategy type must be SCALPING_GRID.")

    if lower >= upper:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid grid range: Lower price (${lower}) must be strictly below upper price (${upper})."
        )

    if req.grid_count < 3 or req.grid_count > 150:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid grid count ({req.grid_count}). Must be between 3 and 150 grids."
        )

    spacing = req.grid_spacing_pct
    if spacing is None:
        spacing = ((upper - lower) / lower / (req.grid_count - 1)) * 100

    if spacing < 0.25:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Grid spacing ({spacing:.2f}%) fails minimum 0.25% round-trip fee friction threshold."
        )

    if capital < 15.0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Capital allocated (${capital}) is below minimum grid strategy capital requirement ($15.00)."
        )"""

if old_grid_val in orders_src:
    orders_src = orders_src.replace(old_grid_val, new_grid_val, 1)

# In submit_grid_order calculations, replace any lingering req.grid_lower_price, etc.
orders_src = orders_src.replace("step = (req.grid_upper_price - req.grid_lower_price) / (req.grid_count - 1)", "step = (upper - lower) / (req.grid_count - 1)")
orders_src = orders_src.replace("price = round(req.grid_lower_price + (i * step), 4)", "price = round(lower + (i * step), 4)")
orders_src = orders_src.replace('"lower_price": req.grid_lower_price', '"lower_price": lower')
orders_src = orders_src.replace('"upper_price": req.grid_upper_price', '"upper_price": upper')
orders_src = orders_src.replace('"capital_usd": req.capital_allocated_usd', '"capital_usd": capital')
orders_src = orders_src.replace('"capital_per_grid_usd": round(req.capital_allocated_usd / req.grid_count, 2)', '"capital_per_grid_usd": round(capital / req.grid_count, 2)')
orders_src = orders_src.replace('"spacing_pct": req.grid_spacing_pct', '"spacing_pct": spacing')

with open("/opt/tauric-platform-staging/backend/app/routes/orders.py", "w") as f:
    f.write(orders_src)
print("Updated orders.py successfully.")
