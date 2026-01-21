"""
Status API endpoints
System status and health monitoring
"""
from fastapi import APIRouter

from app.core.executor import get_executor_status
from app.core.session import create_session

router = APIRouter()


@router.get("/status", summary="Get service status")
async def get_status():
    """Returns service health and executor status"""
    executor_status = get_executor_status()
    
    return {
        "service": "SUSE Data Masking Service",
        "version": "1.0.0",
        "status": "healthy",
        "executor": executor_status
    }


@router.post("/session", summary="Create new session")
async def new_session():
    """Creates a new session for file isolation"""
    session_id = create_session()
    return {
        "session_id": session_id,
        "message": "Session created successfully"
    }
