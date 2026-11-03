from fastapi import APIRouter
from ..services.system_metrics import get_system_health
from ..services.venice_client import venice_client
from ..services.jev_client import jev_client
from ..config import settings

router = APIRouter(prefix="/health", tags=["Health"])

@router.get("")
async def get_health():
    sys_metrics = get_system_health()
    venice_status = await venice_client.check_connectivity()
    jev_status = await jev_client.check_connectivity()
    
    return {
        "status": "HEALTHY",
        "app_name": settings.app_name,
        "version": settings.app_version,
        "server": {
            "ip": sys_metrics["ip_address"],
            "location": sys_metrics["location"],
            "os": sys_metrics["os"],
            "uptime_seconds": sys_metrics["uptime_seconds"]
        },
        "resources": {
            "cpu_percent": sys_metrics["cpu"]["usage_percent"],
            "ram_percent": sys_metrics["ram"]["usage_percent"],
            "disk_percent": sys_metrics["disk"]["usage_percent"]
        },
        "ai_providers": {
            "venice": {
                "name": venice_status["provider"],
                "status": venice_status["status"],
                "primary_model": venice_status["primary_model"]
            },
            "jev": {
                "name": jev_status["provider"],
                "status": jev_status["status"],
                "model": jev_status["model"]
            }
        },
        "ai_provider": {
            "name": venice_status["provider"],
            "status": venice_status["status"],
            "primary_model": venice_status["primary_model"]
        },
        "security": {
            "live_trading_locked": settings.live_trading_locked,
            "read_only_mode": settings.read_only_mode
        }
    }
