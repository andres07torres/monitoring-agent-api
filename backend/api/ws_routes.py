from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import json
from services.system_service import get_system_stats
from services.docker_service import get_container_logs

import os

ws_router = APIRouter(prefix="/ws/v1")

async def verify_ws_api_key(websocket: WebSocket):
    expected_api_key = os.getenv("API_SECRET_KEY", "super-secret-key")
    # Intentar leer desde los headers o desde los parámetros de la URL (?token=...)
    client_key = websocket.headers.get("X-API-Key") or websocket.query_params.get("token")
    
    if client_key != expected_api_key:
        print(f"WS Auth failed. Received token: {client_key}")
        await websocket.close(code=1008, reason="Unauthorized")
        return False
    return True

@ws_router.websocket("/system/stream")
async def websocket_system_stream(websocket: WebSocket):
    await websocket.accept()
    if not await verify_ws_api_key(websocket):
        return
    try:
        while True:
            # Obtenemos los stats y los enviamos cada 2 segundos
            stats = get_system_stats()
            await websocket.send_json(stats)
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        print("Cliente desconectado del stream de métricas del sistema.")

@ws_router.websocket("/containers/{container_id}/logs/stream")
async def websocket_container_logs(websocket: WebSocket, container_id: str):
    await websocket.accept()
    if not await verify_ws_api_key(websocket):
        return
    try:
        # Note: In a real production scenario, you would attach to the Docker container stream
        # using docker-py's attach_socket or similar streaming API, and yield chunks.
        # This is a simplified polling approach for demonstration.
        while True:
            logs = get_container_logs(container_id, tail=20)
            await websocket.send_text(logs)
            await asyncio.sleep(3)
    except WebSocketDisconnect:
        print(f"Cliente desconectado de logs del contenedor {container_id}.")
    except Exception as e:
        print(f"Error en websocket logs: {e}")
        await websocket.close()
