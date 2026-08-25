from fastapi import APIRouter, HTTPException
from services.system_service import get_system_stats
from services.docker_service import (
    list_containers, 
    get_container_info, 
    start_container, 
    stop_container, 
    get_container_logs
)

router = APIRouter(prefix="/api/v1")

@router.get("/system/stats")
def system_stats():
    """Retorna telemetría del servidor en tiempo real (CPU, RAM)."""
    return get_system_stats()

@router.get("/containers")
def get_containers():
    """Retorna la lista de contenedores locales."""
    try:
        return list_containers()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/containers/{container_id}")
def get_container(container_id: str):
    try:
        return get_container_info(container_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/containers/{container_id}/start")
def start_container_route(container_id: str):
    try:
        return start_container(container_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/containers/{container_id}/stop")
def stop_container_route(container_id: str):
    try:
        return stop_container(container_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/containers/{container_id}/logs")
def get_logs(container_id: str, tail: int = 100):
    try:
        return {"logs": get_container_logs(container_id, tail)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
