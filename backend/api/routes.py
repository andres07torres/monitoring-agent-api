from fastapi import APIRouter, HTTPException, Depends, Security
from fastapi.security import APIKeyHeader
import httpx
import subprocess
from schemas.system_schemas import (
    SystemStats, HealthCheckResponse, Alert, CommandRequest, CommandResponse, PowerActionResponse
)
from schemas.docker_schemas import (
    ContainerBase, ContainerInfo, ContainerActionResponse, PruneResponse, LogsResponse
)
from services.system_service import (
    get_system_stats, trigger_shutdown, trigger_reboot
)
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
from typing import List, Dict, Any

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=True)

def verify_api_key(api_key_header: str = Security(api_key_header)):
    """
    Middleware de seguridad: Verifica que las peticiones (ej. desde Android vía Retrofit)
    incluyan el header X-API-Key correcto.
    """
    expected_api_key = os.getenv("API_SECRET_KEY", "super-secret-key")
    if api_key_header != expected_api_key:
        raise HTTPException(status_code=403, detail="Could not validate API KEY")
    return api_key_header

router = APIRouter(prefix="/api/v1", dependencies=[Depends(verify_api_key)], tags=["Monitoring"])

@router.get("/system/stats", response_model=SystemStats)
def system_stats():
    """Retorna telemetría del servidor en tiempo real (CPU, RAM)."""
    try:
        return get_system_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error interno del agente")

@router.post("/system/reboot", response_model=PowerActionResponse)
def reboot_system():
    """Reinicia el servidor anfitrión de manera segura."""
    try:
        return trigger_reboot()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al solicitar reinicio: {str(e)}")

@router.post("/system/shutdown", response_model=PowerActionResponse)
def shutdown_system():
    """Apaga el servidor anfitrión de manera segura."""
    try:
        return trigger_shutdown()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al solicitar apagado: {str(e)}")

@router.get("/containers", response_model=List[ContainerBase])
def get_containers():
    """Retorna la lista de contenedores locales."""
    try:
        return list_containers()
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error al listar contenedores")

@router.get("/containers/{container_id}", response_model=ContainerInfo)
def get_container(container_id: str):
    try:
        return get_container_info(container_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Contenedor no encontrado: {str(e)}")

@router.post("/containers/{container_id}/start", response_model=ContainerActionResponse)
def start_container_route(container_id: str):
    try:
        return start_container(container_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al iniciar contenedor: {str(e)}")

@router.post("/containers/{container_id}/stop", response_model=ContainerActionResponse)
def stop_container_route(container_id: str):
    try:
        return stop_container(container_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al detener contenedor: {str(e)}")

@router.post("/containers/{container_id}/restart", response_model=ContainerActionResponse)
def restart_container_route(container_id: str):
    try:
        return restart_container(container_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al reiniciar contenedor: {str(e)}")

@router.post("/containers/{container_id}/pause", response_model=ContainerActionResponse)
def pause_container_route(container_id: str):
    try:
        return pause_container(container_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al pausar contenedor: {str(e)}")

@router.post("/containers/{container_id}/unpause", response_model=ContainerActionResponse)
def unpause_container_route(container_id: str):
    try:
        return unpause_container(container_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al reanudar contenedor: {str(e)}")

@router.delete("/containers/{container_id}", response_model=ContainerActionResponse)
def remove_container_route(container_id: str):
    try:
        return remove_container(container_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al eliminar contenedor: {str(e)}")

@router.get("/containers/{container_id}/stats", response_model=Dict[str, Any])
def get_container_stats_route(container_id: str):
    try:
        return get_container_stats(container_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener estadísticas del contenedor: {str(e)}")

@router.post("/system/prune", response_model=PruneResponse)
def prune_system_route():
    try:
        return prune_system()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al realizar limpieza de Docker: {str(e)}")

@router.get("/containers/{container_id}/logs", response_model=LogsResponse)
def get_logs(container_id: str, tail: int = 100):
    try:
        return {"logs": get_container_logs(container_id, tail)}
    except Exception as e:
        return {"logs": [f"Error al obtener registros: {str(e)}"]}

@router.get("/logs", response_model=List[Dict[str, Any]])
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

@router.get("/alerts", response_model=List[Alert])
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

@router.get("/healthcheck", response_model=HealthCheckResponse)
async def healthcheck(url: str):
    """Verifica si un endpoint HTTP externo responde (200 OK)."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=5.0)
            return {"status": response.status_code, "message": "Servicio alcanzable"}
    except Exception as e:
        return {"status": 0, "message": f"Inalcanzable: {str(e)}"}

@router.post("/diagnostics/exec", response_model=CommandResponse)
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
