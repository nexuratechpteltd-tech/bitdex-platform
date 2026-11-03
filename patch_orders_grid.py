with open('/opt/tauric-platform-staging/backend/app/routes/orders.py', 'r') as f:
    src = f.read()

# Replace step calculation and receipt variables
old_snippet = """    grid_levels = []
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
    }"""

new_snippet = """    grid_levels = []
    step = (upper - lower) / req.grid_count
    for i in range(req.grid_count + 1):
        grid_levels.append(round(lower + (i * step), 2))

    order_size_per_grid = round(capital / req.grid_count, 2)

    receipt = {
        "client_order_id": f"GRID-{req.idempotency_key}",
        "strategy_label": "Scalping — Grid Strategy",
        "symbol": req.symbol,
        "exchange": req.exchange,
        "status": "ACTIVE_DEMO_GRID",
        "grid_lower_price": lower,
        "grid_upper_price": upper,
        "grid_count": req.grid_count,
        "grid_spacing_pct": spacing,
        "capital_allocated_usd": capital,
        "order_size_per_grid_usd": order_size_per_grid,
        "grid_levels": grid_levels,
        "invalidation_condition": req.invalidation_condition or f"Price closes below ${round(lower * 0.965, 2)}",
        "exit_condition": req.exit_condition or f"Price closes above ${round(upper * 1.035, 2)}",
        "fee_charged_usd": fee_assessed,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    }

    return {
        "status": "SUCCESS",
        "message": f"Successfully initialized Scalping — Grid Strategy ({req.grid_count} grids) for {req.symbol}.",
        "receipt": receipt,
        "grid_levels": grid_levels,
        "strategy_label": "Scalping — Grid Strategy"
    }"""

if old_snippet in src:
    src = src.replace(old_snippet, new_snippet, 1)
    with open('/opt/tauric-platform-staging/backend/app/routes/orders.py', 'w') as f:
        f.write(src)
    print("SUCCESS: patched orders.py")
else:
    print("ERROR: old_snippet not found!")
