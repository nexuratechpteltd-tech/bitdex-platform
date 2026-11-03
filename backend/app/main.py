from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import logging
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .security import TauricSecurityMiddleware
from .services.saas_db import init_saas_db
from .services.auth_manager import AuthManager
from .routes import (
    health,
    markets,
    analysis,
    research,
    backtests,
    system,
    logs,
    jev,
    shadow,
    grid,
    signals,
    dual_ai,
    connections,
    orders,
    ledger,
    orchestration,
    settings as settings_route,
    saas_customer,
    saas_admin,
)

# Initialize SaaS Database and seed admin/owner accounts
init_saas_db()
from .services.ledger_db import init_ledger_tables
init_ledger_tables()
AuthManager.seed_initial_accounts()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Bitdex Quantitative AI Intelligence & Multi-Tenant SaaS Platform Backend API (Staging)",
    docs_url="/docs" if settings.enable_api_docs else None,
    redoc_url="/redoc" if settings.enable_api_docs else None,
    openapi_url="/openapi.json" if settings.enable_api_docs else None,
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logging.getLogger("uvicorn.error").error(
        f"Global unhandled exception on {request.method} {request.url.path}: {exc}",
        exc_info=True
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. Please try again or contact support."}
    )

@app.on_event("startup")
async def _start_market_integrity():
    from .services.market_integrity import market_integrity
    market_integrity.start()


@app.on_event("shutdown")
async def _stop_market_integrity():
    from .services.market_integrity import market_integrity
    await market_integrity.stop()


# Enforce caller authentication boundary and transport security gate on /api/v1/*
app.add_middleware(TauricSecurityMiddleware)

# Restrict CORS to explicit allowed origins (no wildcard * with credentials)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Accept", "Authorization", "X-Tauric-Api-Key", "X-Idempotency-Key", "X-Payload-Signature"],
)

# Include Core API v1 Routers
app.include_router(health.router, prefix="/api/v1")
app.include_router(markets.router, prefix="/api/v1")
app.include_router(analysis.router, prefix="/api/v1")
app.include_router(research.router, prefix="/api/v1")
app.include_router(backtests.router, prefix="/api/v1")
app.include_router(system.router, prefix="/api/v1")
app.include_router(logs.router, prefix="/api/v1")
app.include_router(jev.router, prefix="/api/v1")
app.include_router(shadow.router, prefix="/api/v1")
app.include_router(grid.grid_router, prefix="/api/v1")
app.include_router(signals.router, prefix="/api/v1")
app.include_router(dual_ai.router, prefix="/api/v1")
app.include_router(connections.connections_router, prefix="/api/v1")
app.include_router(orders.orders_router, prefix="/api/v1")
app.include_router(ledger.ledger_router, prefix="/api/v1")
app.include_router(orchestration.orchestration_router, prefix="/api/v1")
app.include_router(settings_route.router, prefix="/api/v1")

# Include SaaS Multi-Tenant & Billing Routers
app.include_router(saas_customer.customer_router, prefix="/api/v1")
app.include_router(saas_admin.admin_router, prefix="/api/v1")
app.include_router(saas_admin.webhook_router, prefix="/api/v1")

@app.get("/")
async def root():
    return {
        "platform": "Bitdex Quantitative Intelligence Platform",
        "domain": "https://bitdex.ltd",
        "support_email": "go@bitdex.ltd",
        "version": settings.app_version,
        "environment": settings.environment,
        "status": "ONLINE",
        "trading_mode": "READ_ONLY_RESEARCH",
        "live_trading_locked": settings.live_trading_locked,
        "read_only_mode": settings.read_only_mode,
        "api_v1": "/api/v1/health",
        "docs_enabled": settings.enable_api_docs,
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
