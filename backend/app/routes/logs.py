from fastapi import APIRouter, Query
from ..services.research_store import get_application_logs

router = APIRouter(prefix="/logs", tags=["Logs"])

@router.get("")
async def get_logs(limit: int = Query(50, ge=1, le=200)):
    logs = get_application_logs(limit=limit)
    return {
        "count": len(logs),
        "logs": logs
    }
