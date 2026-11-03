from fastapi import APIRouter
from ..services.system_metrics import get_system_health
from ..services.venice_client import venice_client

router = APIRouter(prefix="/system", tags=["System"])

@router.get("")
async def get_system_status():
    metrics = get_system_health()
    venice = await venice_client.check_connectivity()
    
    return {
        "server": metrics,
        "ai_connectivity": venice,
        "security_policy": {
            "live_trading": "STRICTLY_DISABLED",
            "api_keys_exposed": False,
            "read_only": True
        }
    }

@router.get("/venice/test")
async def test_venice_connection():
    return await venice_client.check_connectivity()
