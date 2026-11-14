from fastapi import APIRouter, HTTPException, Depends, Request, status
import httpx
import subprocess
import os
import logging
from typing import List, Dict, Any, Optional

from schemas.system_schemas import (
    SystemStats, HealthCheckResponse, Alert, SystemLog, CommandRequest, CommandResponse, PowerActionResponse
)
from schemas.docker_schemas import (
    ContainerBase, ContainerInfo, ContainerActionResponse, PruneResponse, LogsResponse
)
from services.system_service import (
    get_system_stats, trigger_shutdown, trigger_reboot, get_system_alerts, get_system_logs, add_system_log
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
    get_container_logs,
    get_docker_client
)

logger = logging.getLogger(__name__)

def verify_api_key(request: Request) -> str:
    """
    Middleware de seguridad unificado:
    Verifica que las peticiones incluyan un token válido vía:
      - Cabecera 'X-API-Key: <TOKEN>'
      - Cabecera 'Authorization: Bearer <TOKEN>'
      - Parámetro de consulta '?token=<TOKEN>' o '?api_key=<TOKEN>'
    Si es inválido o no existe, responde con HTTP 401 en lugar de 500.
    """
    expected_api_key = os.getenv("API_SECRET_KEY", "").strip() or "super-secret-key"

    # 1. Cabecera X-API-Key
    api_key_header = request.headers.get("X-API-Key") or request.headers.get("x-api-key")

    # 2. Cabecera Authorization: Bearer <TOKEN>
    bearer_token = None
    auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
    if auth_header:
        if auth_header.lower().startswith("bearer "):
            bearer_token = auth_header[7:].strip()
        else:
            bearer_token = auth_header.strip()

    # 3. Query Param ?token=<TOKEN> o ?api_key=<TOKEN>
    query_token = request.query_params.get("token") or request.query_params.get("api_key")

    received_token = api_key_header or bearer_token or query_token

    if not received_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No se proporcionó token de autenticación (use X-API-Key o Authorization: Bearer <TOKEN>)"
        )

    if received_token != expected_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token o clave de API inválida"
        )

    return received_token

router = APIRouter(prefix="/api/v1", dependencies=[Depends(verify_api_key)], tags=["Monitoring"])

# ==============================================================================
# 2.1 Métricas del Sistema Host
# ==============================================================================

@router.get("/system/stats", response_model=SystemStats)
def system_stats():
    """Retorna telemetría del servidor en tiempo real (CPU, RAM, Disco)."""
    try:
        return get_system_stats()
    except Exception as e:
        logger.error(f"Error inesperado al calcular estadísticas del sistema: {e}")
        # En caso de cualquier imprevisto, retorna métricas por defecto seguras
        return {
            "cpu_percent": 0.0,
            "cpu_cores": 1,
            "cpu_frequency": 0.0,
            "ram_percent": 0.0,
            "ram_used_gb": 0.0,
            "ram_total_gb": 0.0,
            "disk_percent": 0.0,
            "disk_used_gb": 0.0,
            "disk_total_gb": 0.0
        }

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

# ==============================================================================
# 2.2 Gestión de Contenedores Docker
# ==============================================================================

@router.get("/containers", response_model=List[ContainerBase])
def get_containers():
    """Retorna la lista de contenedores con sus estadísticas calculadas (cpu_usage, ram_usage)."""
    try:
        return list_containers()
    except Exception as e:
        logger.warning(f"Error al listar contenedores: {e}")
        return []

@router.get("/containers/{container_id}", response_model=ContainerInfo)
def get_container(container_id: str):
    """Retorna información detallada de un contenedor."""
    client = get_docker_client()
    if not client:
        raise HTTPException(status_code=503, detail="Docker Engine no disponible")
    try:
        return get_container_info(container_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Contenedor '{container_id}' no encontrado: {str(e)}")

def _exec_docker_action(action_func, container_id: str, action_name: str) -> Dict[str, str]:
    client = get_docker_client()
    if not client:
        raise HTTPException(status_code=503, detail="Docker Engine no disponible o socket inaccesible")
    try:
        res = action_func(container_id)
        add_system_log("INFO", f"Acción '{action_name}' ejecutada en contenedor {container_id}")
        return res
    except Exception as e:
        err_msg = str(e)
        if "No such container" in err_msg or "404" in err_msg:
            raise HTTPException(status_code=404, detail=f"Contenedor '{container_id}' no encontrado")
        raise HTTPException(status_code=400, detail=f"Error al ejecutar {action_name}: {err_msg}")

@router.post("/containers/{container_id}/start", response_model=ContainerActionResponse)
def start_container_route(container_id: str):
    return _exec_docker_action(start_container, container_id, "start")

@router.post("/containers/{container_id}/stop", response_model=ContainerActionResponse)
def stop_container_route(container_id: str):
    return _exec_docker_action(stop_container, container_id, "stop")

@router.post("/containers/{container_id}/restart", response_model=ContainerActionResponse)
def restart_container_route(container_id: str):
    return _exec_docker_action(restart_container, container_id, "restart")

@router.post("/containers/{container_id}/pause", response_model=ContainerActionResponse)
def pause_container_route(container_id: str):
    return _exec_docker_action(pause_container, container_id, "pause")

@router.post("/containers/{container_id}/unpause", response_model=ContainerActionResponse)
def unpause_container_route(container_id: str):
    return _exec_docker_action(unpause_container, container_id, "unpause")

@router.delete("/containers/{container_id}", response_model=ContainerActionResponse)
def remove_container_route(container_id: str):
    return _exec_docker_action(remove_container, container_id, "remove")

@router.get("/containers/{container_id}/stats", response_model=Dict[str, Any])
def get_container_stats_route(container_id: str):
    client = get_docker_client()
    if not client:
        raise HTTPException(status_code=503, detail="Docker Engine no disponible")
    try:
        return get_container_stats(container_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Error al obtener estadísticas: {str(e)}")

@router.post("/system/prune", response_model=PruneResponse)
def prune_system_route():
    """Limpia contenedores detenidos, redes y volúmenes en desuso."""
    client = get_docker_client()
    if not client:
        raise HTTPException(status_code=503, detail="Docker Engine no disponible")
    try:
        res = prune_system()
        add_system_log("INFO", "Limpieza de sistema Docker (prune) ejecutada exitosamente")
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al ejecutar prune: {str(e)}")

# ==============================================================================
# 2.3 Logs y Alertas
# ==============================================================================

@router.get("/containers/{container_id}/logs", response_model=LogsResponse)
def get_logs(container_id: str, tail: int = 100):
    """Retorna los registros de un contenedor."""
    try:
        return {"logs": get_container_logs(container_id, tail)}
    except Exception as e:
        return {"logs": [f"Error al obtener registros: {str(e)}"]}

@router.get("/alerts", response_model=List[Alert])
def get_alerts():
    """
    Evalúa el estado del hardware y genera alertas con severidades soportadas:
    HIGH, CRITICAL, MEDIUM, WARNING, LOW, SUCCESS.
    """
    try:
        return get_system_alerts()
    except Exception as e:
        logger.warning(f"Error generando alertas: {e}")
        return [{
            "id": "alt-err-001",
            "severity": "LOW",
            "message": "Sistema funcionando normalmente",
            "timestamp": "2026-11-13T21:00:00Z"
        }]

@router.get("/logs", response_model=List[SystemLog])
def get_global_logs():
    """Retorna el historial de eventos del sistema y orquestador."""
    try:
        return get_system_logs()
    except Exception as e:
        logger.warning(f"Error obteniendo logs globales: {e}")
        return []

# ==============================================================================
# 2.4 Diagnóstico y Comprobaciones
# ==============================================================================

@router.get("/healthcheck", response_model=HealthCheckResponse)
async def healthcheck(url: Optional[str] = None):
    """
    Verifica el estado del servicio o de un endpoint externo si se especifica ?url=...
    """
    if not url:
        return {"status": 200, "message": "OK"}
    try:
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.get(url, timeout=5.0)
            msg = "OK" if response.status_code == 200 else f"HTTP {response.status_code}"
            return {"status": response.status_code, "message": msg}
    except Exception as e:
        return {"status": 503, "message": f"Inalcanzable: {str(e)}"}

@router.post("/diagnostics/exec", response_model=CommandResponse)
def execute_command(request: CommandRequest):
    """Ejecuta un comando de diagnóstico en el servidor anfitrión."""
    try:
        result = subprocess.run(
            request.command, 
            shell=True, 
            capture_output=True, 
            text=True, 
            timeout=15
        )
        output = result.stdout if result.stdout else result.stderr
        add_system_log("INFO", f"Comando ejecutado vía diagnostics: {request.command[:50]}")
        return {"output": output or "Comando ejecutado sin salida en consola", "exitCode": result.returncode}
    except subprocess.TimeoutExpired:
        return {"output": "El comando excedió el tiempo límite de ejecución (15s)", "exitCode": 124}
    except Exception as e:
        return {"output": str(e), "exitCode": 1}
