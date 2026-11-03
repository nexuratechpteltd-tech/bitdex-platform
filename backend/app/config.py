import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from pydantic import BaseModel
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

# Centralized Model Configuration — Strict Cost & Provider Control
DEFAULT_MODEL = "deepseek-v4-flash"
PREMIUM_MODEL = "deepseek-v4-pro-0813"
ALLOWED_PRODUCTION_MODELS: List[str] = ["deepseek-v4-flash", "deepseek-v4-pro-0813"]

DEFAULT_MODEL_TIER = "low"
PREMIUM_MODEL_TIER = "high"

def validate_model_preflight(model_id: str) -> bool:
    """Validate model ID against allowed production models."""
    if not model_id:
        return False
    clean = str(model_id).strip().lower()
    return clean in ALLOWED_PRODUCTION_MODELS

def resolve_model_tier(model_or_tier: Optional[str] = None) -> Dict[str, Any]:
    if not model_or_tier:
        return {
            "model_id": DEFAULT_MODEL,
            "model_name": "DeepSeek V4.1 Flash",
            "model_tier": "standard",
            "cost_tier": "LOW COST • DEFAULT",
            "is_premium": False,
            "authorized": True,
            "reason": "Default Flash model applied"
        }
    
    val = str(model_or_tier).lower().strip()
    if val in ["premium", "high", "pro", "deepseek-v4-pro-0813", "deepseek-v4-pro", "deepseek-pro"]:
        return {
            "model_id": PREMIUM_MODEL,
            "model_name": "DeepSeek V4 Pro",
            "model_tier": "premium",
            "cost_tier": "HIGH COST • OPTIONAL",
            "is_premium": True,
            "authorized": True,
            "reason": "Explicit user premium selection"
        }
    
    return {
        "model_id": DEFAULT_MODEL,
        "model_name": "DeepSeek V4.1 Flash",
        "model_tier": "standard",
        "cost_tier": "LOW COST • DEFAULT",
        "is_premium": False,
        "authorized": True,
        "reason": "Standard Flash tier selected"
    }

class Settings(BaseModel):
    app_name: str = "Bitdex Platform API (Staging)"
    app_version: str = "2.0.0"
    environment: str = os.getenv("ENVIRONMENT", "staging")
    host: str = os.getenv("HOST", "127.0.0.1")
    port: int = int(os.getenv("PORT", "8002"))
    
    # Venice AI Configuration
    venice_api_endpoint: str = os.getenv("VENICE_API_ENDPOINT", "https://api.venice.ai/api/v1")
    venice_api_key: str = os.getenv("VENICE_API_KEY", "")
    venice_primary_model: str = os.getenv("VENICE_PRIMARY_MODEL", "deepseek-v4-flash")
    venice_pro_model: str = os.getenv("VENICE_PRO_MODEL", "deepseek-v4-pro-0813")
    max_active_tauric_jobs: int = 1
    
    # TypeSafe Jev Configuration
    typesafe_api_endpoint: str = os.getenv("TYPESAFE_API_ENDPOINT", "https://api.typesafe.ai/v1/systemone")
    typesafe_api_key: str = os.getenv("TYPESAFE_API_KEY", "")
    typesafe_model: str = os.getenv("TYPESAFE_DEFAULT_MODEL", "jev-latest")

    # Invariants & Security
    live_trading_locked: bool = True
    read_only_mode: bool = True
    platform_root: str = "/opt/tauric-platform-staging"
    tauric_vault_key: str = os.getenv("TAURIC_VAULT_KEY", "")
    enable_api_docs: bool = os.getenv("TAURIC_ENABLE_DOCS", "false").lower() in ("true", "1", "yes")
    allowed_origins: List[str] = [
        "https://bitdex.ltd",
        "https://www.bitdex.ltd",
        "https://sheltr.agency",
        "https://www.sheltr.agency",
        "https://bybit-gateway.sheltr.agency",
        "http://127.0.0.1:33900",
        "http://localhost:33900",
    ]
    
    # Finance Calendar Configuration (Staging)
    finance_calendar_enabled: bool = os.getenv("FINANCE_CALENDAR_ENABLED", "true").lower() in ("true", "1", "yes")
    finance_calendar_api_url: str = os.getenv("FINANCE_CALENDAR_API_URL", "https://www.financecalendar.com/wp-json/fc/v1/calendar")
    finance_calendar_horizon_days: int = int(os.getenv("FINANCE_CALENDAR_HORIZON_DAYS", "14"))
    finance_calendar_cache_ttl_sec: int = int(os.getenv("FINANCE_CALENDAR_CACHE_TTL_SEC", "300"))

settings = Settings()
