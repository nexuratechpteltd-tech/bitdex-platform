import re

# 1. Update orders.py
with open("/opt/tauric-platform-staging/backend/app/routes/orders.py", "r") as f:
    orders_src = f.read()

old_req = """class GridOrderSubmitRequest(BaseModel):
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
    idempotency_key: str = Field(..., min_length=4)"""

new_req = """class GridOrderSubmitRequest(BaseModel):
    profile_id: Optional[str] = None
    exchange: str = Field(default="BINANCE")
    symbol: str = Field(..., description="e.g. BTCUSDT")
    market: Optional[str] = "CRYPTO"
    strategy_type: str = Field(default="SCALPING_GRID", description="Must be SCALPING_GRID")
    grid_lower_price: Optional[float] = None
    grid_upper_price: Optional[float] = None
    lower_price: Optional[float] = None
    upper_price: Optional[float] = None
    grid_count: int = Field(default=8, ge=3, le=150)
    grid_spacing_pct: Optional[float] = None
    capital_allocated_usd: Optional[float] = None
    capital_usd: Optional[float] = None
    invalidation_condition: Optional[str] = None
    exit_condition: Optional[str] = None
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    idempotency_key: str = Field(default_factory=lambda: f"GRID-{int(time.time()*1000)}")"""

if old_req in orders_src:
    orders_src = orders_src.replace(old_req, new_req, 1)

old_body = """    # 2. Mathematical Boundary Validation
    if req.grid_lower_price >= req.grid_upper_price:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid grid range: Lower price (${req.grid_lower_price}) must be strictly below upper price (${req.grid_upper_price})."
        )

    if req.capital_allocated_usd < 15.0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Capital allocation (${req.capital_allocated_usd:.2f}) is below minimum threshold of $15.00 USDT."
        )"""

new_body = """    lower = req.grid_lower_price if req.grid_lower_price is not None else req.lower_price
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

    # 2. Mathematical Boundary Validation
    if lower >= upper:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid grid range: Lower price (${lower}) must be strictly below upper price (${upper})."
        )

    if capital < 15.0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Capital allocation (${capital:.2f}) is below minimum threshold of $15.00 USDT."
        )"""

if old_body in orders_src:
    orders_src = orders_src.replace(old_body, new_body, 1)

# In submit_grid_order, also replace req.grid_lower_price, req.grid_upper_price, req.capital_allocated_usd with lower, upper, capital
orders_src = orders_src.replace("step = (req.grid_upper_price - req.grid_lower_price) / (req.grid_count - 1)", "step = (upper - lower) / (req.grid_count - 1)")
orders_src = orders_src.replace("price = round(req.grid_lower_price + (i * step), 4)", "price = round(lower + (i * step), 4)")
orders_src = orders_src.replace('"lower_price": req.grid_lower_price', '"lower_price": lower')
orders_src = orders_src.replace('"upper_price": req.grid_upper_price', '"upper_price": upper')
orders_src = orders_src.replace('"capital_usd": req.capital_allocated_usd', '"capital_usd": capital')
orders_src = orders_src.replace('"capital_per_grid_usd": round(req.capital_allocated_usd / req.grid_count, 2)', '"capital_per_grid_usd": round(capital / req.grid_count, 2)')

with open("/opt/tauric-platform-staging/backend/app/routes/orders.py", "w") as f:
    f.write(orders_src)
print("Updated orders.py successfully.")

# 2. Update saas_customer.py for simulate_market_closed
with open("/opt/tauric-platform-staging/backend/app/routes/saas_customer.py", "r") as f:
    cust_src = f.read()

old_ai_req = """class AIAnalysisRunRequest(BaseModel):
    symbol: str = Field(..., min_length=2, max_length=20)
    market: str = "CRYPTO"  # CRYPTO or FOREX
    timeframe: str = "1h"
    idempotency_key: str = Field(..., min_length=4, max_length=120)
    simulate_failure: bool = False"""

new_ai_req = """class AIAnalysisRunRequest(BaseModel):
    symbol: str = Field(..., min_length=2, max_length=20)
    market: str = "CRYPTO"  # CRYPTO or FOREX
    timeframe: str = "1h"
    idempotency_key: str = Field(..., min_length=4, max_length=120)
    simulate_failure: bool = False
    simulate_market_closed: bool = False"""

if old_ai_req in cust_src:
    cust_src = cust_src.replace(old_ai_req, new_ai_req, 1)

old_ai_call = """        contract = await FourEngineOrchestrator.analyze(
            symbol=symbol,
            timeframe=timeframe,
            market=market,
            user_id=user_id
        )"""

new_ai_call = """        contract = await FourEngineOrchestrator.analyze(
            symbol=symbol,
            timeframe=timeframe,
            market=market,
            user_id=user_id,
            simulate_market_closed=req.simulate_market_closed
        )"""

if old_ai_call in cust_src:
    cust_src = cust_src.replace(old_ai_call, new_ai_call, 1)

with open("/opt/tauric-platform-staging/backend/app/routes/saas_customer.py", "w") as f:
    f.write(cust_src)
print("Updated saas_customer.py successfully.")

# 3. Update four_engine_orchestrator.py for simulate_market_closed
with open("/opt/tauric-platform-staging/backend/app/services/four_engine_orchestrator.py", "r") as f:
    fe_src = f.read()

old_fe_def = "async def analyze(cls, symbol: str, timeframe: str = '1h', market: str = 'CRYPTO', user_id: str = None) -> Dict[str, Any]:"
new_fe_def = "async def analyze(cls, symbol: str, timeframe: str = '1h', market: str = 'CRYPTO', user_id: str = None, simulate_market_closed: bool = False) -> Dict[str, Any]:"

if old_fe_def in fe_src:
    fe_src = fe_src.replace(old_fe_def, new_fe_def, 1)

old_fx_closed = 'is_fx_closed = session.get("market_status") == "CLOSED" or not session.get("market_open", True)'
new_fx_closed = 'is_fx_closed = simulate_market_closed or session.get("market_status") == "CLOSED" or not session.get("market_open", True)'

if old_fx_closed in fe_src:
    fe_src = fe_src.replace(old_fx_closed, new_fx_closed, 1)

old_closed_check = 'is_market_closed = bool(snapshot.get("market_data", {}).get("is_market_closed", False))'
new_closed_check = 'is_market_closed = simulate_market_closed or bool(snapshot.get("market_data", {}).get("is_market_closed", False))'

if old_closed_check in fe_src:
    fe_src = fe_src.replace(old_closed_check, new_closed_check, 1)

with open("/opt/tauric-platform-staging/backend/app/services/four_engine_orchestrator.py", "w") as f:
    f.write(fe_src)
print("Updated four_engine_orchestrator.py successfully.")
