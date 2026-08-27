from fastapi import APIRouter, HTTPException, Depends, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
import httpx
import subprocess
from services.system_service import get_system_stats, get_system_history
from services.docker_service import (
    list_containers, 
    get_container_info, 
    start_container, 
    stop_container,
    restart_container,
    pause_container,
    unpause_container,
    remove_container,
    get_container_stats,
    prune_system,
    get_container_logs
)
from datetime import datetime
import psutil
import os

class CommandRequest(BaseModel):
    command: str

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=True)

def verify_api_key(api_key_header: str = Security(api_key_header)):
    """
    Middleware de seguridad: Verifica que las peticiones (ej. desde Android vía Retrofit)
    incluyan el header X-API-Key correcto.
    """
    # Se recomienda usar variables de entorno, p.ej. os.getenv("API_SECRET_KEY", "super-secret-key")
    expected_api_key = os.getenv("API_SECRET_KEY", "super-secret-key")
    if api_key_header != expected_api_key:
        raise HTTPException(status_code=403, detail="Could not validate API KEY")
    return api_key_header

router = APIRouter(prefix="/api/v1", dependencies=[Depends(verify_api_key)])

@router.get("/system/stats")
def system_stats():
    """Retorna telemetría del servidor en tiempo real (CPU, RAM)."""
    return get_system_stats()

@router.get("/system/history")
def system_history():
    """Retorna el historial de telemetría (útil para gráficas de tendencias)."""
    return get_system_history()

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

@router.post("/containers/{container_id}/restart")
def restart_container_route(container_id: str):
    try:
        return restart_container(container_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/containers/{container_id}/pause")
def pause_container_route(container_id: str):
    try:
        return pause_container(container_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/containers/{container_id}/unpause")
def unpause_container_route(container_id: str):
    try:
        return unpause_container(container_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/containers/{container_id}")
def remove_container_route(container_id: str):
    try:
        return remove_container(container_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/containers/{container_id}/stats")
def get_container_stats_route(container_id: str):
    try:
        return get_container_stats(container_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/system/prune")
def prune_system_route():
    try:
        return prune_system()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/containers/{container_id}/logs")
def get_logs(container_id: str, tail: int = 100):
    try:
        return {"logs": get_container_logs(container_id, tail)}
    except Exception as e:
        # Manejo de errores básico devolviendo un array como espera Android
        return {"logs": [f"Error al obtener registros: {str(e)}"]}

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

@router.get("/healthcheck")
async def healthcheck(url: str):
    """Verifica si un endpoint HTTP externo responde (200 OK)."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=5.0)
            return {"status": response.status_code, "message": "Servicio alcanzable"}
    except Exception as e:
        return {"status": 0, "message": f"Inalcanzable: {str(e)}"}

@router.post("/diagnostics/exec")
def execute_command(request: CommandRequest):
    """Ejecuta un comando de diagnóstico en el servidor Ubuntu."""
    try:
        # Ejecuta el comando y captura la salida
        result = subprocess.run(
            request.command, 
            shell=True, 
            capture_output=True, 
            text=True, 
            timeout=10
        )
        output = result.stdout if result.stdout else result.stderr
        return {"output": output, "exitCode": result.returncode}
    except Exception as e:
        return {"output": str(e), "exitCode": 1}
