from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import json
import logging
import os
from services.system_service import get_system_stats, add_system_log
from services.docker_service import get_container_logs

logger = logging.getLogger(__name__)

ws_router = APIRouter(prefix="/ws/v1")
api_ws_router = APIRouter(prefix="/api/v1")

def check_ws_auth(websocket: WebSocket) -> bool:
    """
    Verifica las credenciales del WebSocket:
      - Parámetro de consulta '?token=<TOKEN>' o '?api_key=<TOKEN>'
      - Cabeceras 'X-API-Key' o 'Authorization: Bearer <TOKEN>'
    """
    expected_api_key = os.getenv("API_SECRET_KEY", "").strip() or "super-secret-key"

    # 1. Parámetros de consulta
    client_key = websocket.query_params.get("token") or websocket.query_params.get("api_key")

    # 2. Cabeceras
    if not client_key:
        client_key = websocket.headers.get("X-API-Key") or websocket.headers.get("x-api-key")

    if not client_key:
        auth_header = websocket.headers.get("Authorization") or websocket.headers.get("authorization")
        if auth_header:
            if auth_header.lower().startswith("bearer "):
                client_key = auth_header[7:].strip()
            else:
                client_key = auth_header.strip()

    is_valid = (client_key == expected_api_key)
    if not is_valid:
        logger.warning(f"Fallo de autenticación en WebSocket. Token recibido: '{client_key}'")
    return is_valid

# ==============================================================================
# 3.1 Transmisión de Métricas en Tiempo Real
# wss://<HOST>/ws/v1/system/stream
# ==============================================================================

@ws_router.websocket("/system/stream")
async def websocket_system_stream(websocket: WebSocket):
    await websocket.accept()
    if not check_ws_auth(websocket):
        await websocket.close(code=1008, reason="Unauthorized")
        return

    try:
        while True:
            # Enviar métricas del sistema cada 1 a 2 segundos
            stats = get_system_stats()
            await websocket.send_json(stats)

            # Esperar timeout para procesar pings de Android (OkHttp) sin bloquear
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=1.5)
            except asyncio.TimeoutError:
                pass
    except WebSocketDisconnect:
        logger.info("Cliente desconectado del stream de métricas del sistema.")
    except Exception as e:
        logger.warning(f"Excepción en websocket system/stream: {e}")

# ==============================================================================
# 3.2 Transmisión de Logs de Contenedores en Tiempo Real
# wss://<HOST>/ws/v1/containers/{container_id}/logs/stream
# ==============================================================================

@ws_router.websocket("/containers/{container_id}/logs/stream")
async def websocket_container_logs(websocket: WebSocket, container_id: str):
    await websocket.accept()
    if not check_ws_auth(websocket):
        await websocket.close(code=1008, reason="Unauthorized")
        return

    try:
        while True:
            logs = get_container_logs(container_id, tail=30)
            # Transmite en formato JSON {"logs": [...]} esperado por InfraMonitor
            await websocket.send_json({"logs": logs})

            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=2.5)
            except asyncio.TimeoutError:
                pass
    except WebSocketDisconnect:
        logger.info(f"Cliente desconectado de logs en vivo para contenedor {container_id}.")
    except Exception as e:
        logger.warning(f"Excepción en websocket logs {container_id}: {e}")

# ==============================================================================
# 3.3 Terminal Bidireccional Interactivo
# wss://<HOST>/api/v1/diagnostics/ws  (y alias /ws/v1/diagnostics/ws)
# ==============================================================================

async def run_interactive_terminal(websocket: WebSocket):
    await websocket.accept()
    if not check_ws_auth(websocket):
        await websocket.close(code=1008, reason="Unauthorized")
        return

    welcome_msg = "=== Terminal Interactivo de Diagnóstico InfraMonitor ===\r\nConexión establecida. Ingrese comandos para ejecutar:\r\n> "
    await websocket.send_text(welcome_msg)
    add_system_log("INFO", "Sesión de terminal WebSocket interactivo iniciada")

    try:
        while True:
            data = await websocket.receive_text()
            if not data:
                continue

            command_to_run = data.strip()
            # Si el cliente envía un JSON {"command": "..."}
            if command_to_run.startswith("{") and command_to_run.endswith("}"):
                try:
                    payload = json.loads(command_to_run)
                    if isinstance(payload, dict) and "command" in payload:
                        command_to_run = str(payload["command"]).strip()
                except Exception:
                    pass

            if not command_to_run:
                await websocket.send_text("> ")
                continue

            if command_to_run.lower() in ["exit", "quit"]:
                await websocket.send_text("Cerrando sesión de terminal.\r\n")
                await websocket.close()
                break

            # Ejecutar el comando en shell de forma asíncrona y transmitir stdout/stderr
            try:
                proc = await asyncio.create_subprocess_shell(
                    command_to_run,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT
                )

                while True:
                    line = await proc.stdout.readline()
                    if not line:
                        break
                    await websocket.send_text(line.decode("utf-8", errors="replace"))

                await proc.wait()
                await websocket.send_text(f"[Exit code: {proc.returncode}]\r\n> ")
            except Exception as e:
                await websocket.send_text(f"Error al ejecutar: {str(e)}\r\n> ")

    except WebSocketDisconnect:
        logger.info("Cliente desconectado del terminal interactivo.")
    except Exception as e:
        logger.warning(f"Excepción en terminal WebSocket: {e}")

@api_ws_router.websocket("/diagnostics/ws")
async def websocket_diagnostics_terminal_api(websocket: WebSocket):
    """Endpoint principal especificado en el contrato: wss://<HOST>/api/v1/diagnostics/ws"""
    await run_interactive_terminal(websocket)

@ws_router.websocket("/diagnostics/ws")
async def websocket_diagnostics_terminal_ws(websocket: WebSocket):
    """Alias en /ws/v1/diagnostics/ws para compatibilidad adicional"""
    await run_interactive_terminal(websocket)
