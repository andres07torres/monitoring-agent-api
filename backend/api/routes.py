from fastapi import APIRouter, HTTPException
from services.system_service import get_system_stats
from services.docker_service import (
    list_containers, 
    get_container_info, 
    start_container, 
    stop_container, 
    get_container_logs
)
from datetime import datetime
import psutil

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

@router.get("/logs")
def get_global_logs():
    """
    Devuelve los últimos eventos del sistema o del orquestador.
    Por ahora usamos datos estructurados para que la UI los pinte.
    """
    return [
        {"id": "1", "timestamp": datetime.now().isoformat(), "level": "INFO", "message": "Conexión segura establecida vía Cloudflare Zero Trust"},
        {"id": "2", "timestamp": datetime.now().isoformat(), "level": "INFO", "message": "Agente de monitoreo iniciado correctamente en Ubuntu"},
        {"id": "3", "timestamp": datetime.now().isoformat(), "level": "WARNING", "message": "Intento de lectura de alertas completado"}
    ]

@router.get("/alerts")
def get_alerts():
    """
    Evalúa el estado del hardware de la máquina virtual Ubuntu 
    y genera alertas si los recursos superan los umbrales.
    """
    alerts = []
    cpu_usage = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory()
    
    if cpu_usage > 80:
        alerts.append({"id": "A1", "severity": "HIGH", "message": f"Sobrecarga de CPU detectada: {cpu_usage}%"})
    
    if ram.percent > 90:
        alerts.append({"id": "A2", "severity": "HIGH", "message": f"Memoria RAM en nivel crítico: {ram.percent}%"})
        
    if not alerts:
        alerts.append({"id": "A0", "severity": "LOW", "message": "Todos los sistemas operan dentro de los parámetros normales. Sin alertas."})
        
    return alerts
