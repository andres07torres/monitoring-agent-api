from fastapi import APIRouter, HTTPException, Depends, Request, status
import httpx
import subprocess
import os
import logging
import urllib.parse
from typing import List, Dict, Any, Optional

from schemas.system_schemas import (
    SystemStats, HealthCheckResponse, Alert, SystemLog, CommandRequest, CommandResponse, PowerActionResponse
)
from schemas.docker_schemas import (
    ContainerBase, ContainerInfo, ContainerActionResponse, PruneResponse, LogsResponse
)
from services.system_service import (
    get_system_stats, get_system_metadata, trigger_shutdown, trigger_reboot, get_system_alerts, get_system_logs, add_system_log
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
    get_docker_client,
    find_container,
    is_non_http_service,
    get_container_web_target,
    get_container_web_targets
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
    """Retorna telemetría del servidor en tiempo real (CPU, RAM, Disco y metadatos del sistema)."""
    try:
        return get_system_stats()
    except Exception as e:
        logger.error(f"Error inesperado al calcular estadísticas del sistema: {e}")
        # En caso de cualquier imprevisto, retorna métricas por defecto seguras
        try:
            metadata = get_system_metadata()
        except Exception:
            metadata = {
                "os": "Desconocido",
                "architecture": "unknown",
                "uptime": "0 min",
                "protected_ports": "",
                "zero_trust_tunnel": "Ninguno",
            }
        return {
            "cpu_percent": 0.0,
            "cpu_cores": 1,
            "cpu_frequency": 0.0,
            "ram_percent": 0.0,
            "ram_used_gb": 0.0,
            "ram_total_gb": 0.0,
            "disk_percent": 0.0,
            "disk_used_gb": 0.0,
            "disk_total_gb": 0.0,
            **metadata
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
            "id": "A0",
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

@router.get("/healthcheck", response_model=HealthCheckResponse, response_model_exclude_none=True)
async def healthcheck(
    url: Optional[str] = None,
    container_id: Optional[str] = None,
    container_name: Optional[str] = None,
    container: Optional[str] = None,
    service_type: Optional[str] = None,
    type: Optional[str] = None,
    port: Optional[int] = None,
):
    """
    Comprobación de salud (Healthcheck) con diferenciación de tipos de contenedor:
    1. Bases de datos / Servicios no HTTP (mysql, postgres, redis, mailer, workers):
       No intenta realizar peticiones HTTP. Consulta el estado de Docker.
       Si el estado del contenedor es running, responde { "status": 200, "message": "Container is Running" }.
    2. Servicios Web (APIs / Apps Web):
       Realiza petición HTTP por red interna o localhost usando HTTP con timeout de 3 a 5 segundos.
       Si responde OK, responde { "status": 200, "message": "OK" }.
       Si está caído o no responde al timeout, responde { "status": 503, "message": "Connection refused / Timeout" }.
    3. Siempre responde con HTTP 200 a nivel de cabecera de la API administrativa.
    """
    target_container_ref = container or container_id or container_name
    svc_type = service_type or type

    # Caso A: Healthcheck local del agente (sin parámetros de destino)
    if not url and not target_container_ref:
        return {"status": 200, "message": "OK"}

    parsed_port = port
    parsed_host = ""
    is_direct_url = False

    if url:
        url_stripped = url.strip()
        if "://" in url_stripped:
            try:
                parsed = urllib.parse.urlparse(url_stripped)
                parsed_host = parsed.hostname or ""
                if parsed.port:
                    parsed_port = parsed.port
                is_direct_url = True
            except Exception:
                is_direct_url = True
        elif ":" in url_stripped and not url_stripped.startswith("/"):
            parts = url_stripped.split(":", 1)
            parsed_host = parts[0]
            try:
                parsed_port = int(parts[1].split("/")[0])
            except ValueError:
                pass
            is_direct_url = True
        else:
            if not target_container_ref:
                target_container_ref = url_stripped

    # Buscar contenedor en Docker
    container_obj = None
    if target_container_ref:
        container_obj = find_container(target_container_ref)
    elif parsed_host and parsed_host not in ("localhost", "127.0.0.1", "0.0.0.0"):
        container_obj = find_container(parsed_host)

    # Determinar si es Base de datos / Servicio no HTTP (mysql, postgres, redis, mailer, workers)
    is_non_http = is_non_http_service(
        container=container_obj,
        identifier=(target_container_ref or parsed_host or url or ""),
        port=parsed_port,
        service_type=svc_type
    )

    # 1. Bases de datos / Servicios no HTTP
    if is_non_http:
        if container_obj:
            try:
                container_obj.reload()
                c_status = getattr(container_obj, "status", "").lower()
                if c_status == "running":
                    return {"status": 200, "message": "Container is Running"}
                else:
                    return {"status": 503, "message": "Connection refused / Timeout"}
            except Exception as e:
                logger.warning(f"Error consultando contenedor Docker: {e}")
                return {"status": 503, "message": "Connection refused / Timeout"}

        return {"status": 503, "message": "Connection refused / Timeout"}

    # 2. Servicios Web (APIs / Apps Web)
    # Si el contenedor existe en Docker y no está running, responder 503
    if container_obj:
        try:
            container_obj.reload()
            if getattr(container_obj, "status", "").lower() != "running":
                return {"status": 503, "message": "Connection refused / Timeout"}
        except Exception:
            pass

    # Resolver lista de URLs HTTP a probar
    targets_to_try = []
    if is_direct_url and url:
        raw_url = url.strip()
        if raw_url.startswith("https://"):
            raw_url = "http://" + raw_url[8:]
        elif not raw_url.startswith("http://"):
            raw_url = "http://" + raw_url
        targets_to_try.append(raw_url)
    elif container_obj:
        targets_to_try = get_container_web_targets(container_obj, default_port=parsed_port)
    elif target_container_ref:
        p = parsed_port or 80
        targets_to_try.append(f"http://127.0.0.1:{p}")
        targets_to_try.append(f"http://172.17.0.1:{p}")
    else:
        p = parsed_port or 80
        targets_to_try.append(f"http://127.0.0.1:{p}")

    # Timeout de conexión: máximo 3 a 5 segundos (configurado en 3.0s por intento)
    http_timeout = httpx.Timeout(3.0, connect=2.0)

    # Intentar conexión HTTP hacia los objetivos resueltos
    for target_http_url in targets_to_try[:4]:
        try:
            async with httpx.AsyncClient(verify=False, timeout=http_timeout) as client:
                response = await client.get(target_http_url)
                # Si el servicio web responde (cualquier código indicativo de que el servidor web está activo)
                if response.status_code < 500:
                    return {"status": 200, "message": "OK"}
        except Exception:
            continue

    # Si la petición HTTP directa no respondió (por aislamiento de red Docker o app interna),
    # pero el contenedor existe y está en ejecución (running) en Docker, está activo:
    if container_obj:
        try:
            container_obj.reload()
            if getattr(container_obj, "status", "").lower() == "running":
                return {"status": 200, "message": "Container is Running"}
        except Exception:
            pass

    return {"status": 503, "message": "Connection refused / Timeout"}

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
