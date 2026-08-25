import docker
import logging

logger = logging.getLogger(__name__)

# Inicializar cliente de Docker (se conecta al socket local de Linux)
try:
    docker_client = docker.from_env()
except Exception as e:
    logger.error(f"Error conectando a Docker: {e}")
    docker_client = None

def _get_client():
    if not docker_client:
        raise Exception("Cliente Docker no inicializado")
    return docker_client

def list_containers():
    client = _get_client()
    containers = client.containers.list(all=True)
    return [{"id": c.short_id, "name": c.name, "status": c.status, "image": c.image.tags[0] if c.image.tags else "N/A"} for c in containers]

def get_container_info(container_id: str):
    client = _get_client()
    container = client.containers.get(container_id)
    return {
        "id": container.short_id,
        "name": container.name,
        "status": container.status,
        "image": container.image.tags[0] if container.image.tags else "N/A",
        "created": container.attrs.get("Created")
    }

def start_container(container_id: str):
    client = _get_client()
    container = client.containers.get(container_id)
    container.start()
    return {"status": "started", "id": container_id}

def stop_container(container_id: str):
    client = _get_client()
    container = client.containers.get(container_id)
    container.stop()
    return {"status": "stopped", "id": container_id}

def get_container_logs(container_id: str, tail: int = 100):
    client = _get_client()
    container = client.containers.get(container_id)
    # .logs returns bytes, decode to string
    logs = container.logs(tail=tail).decode('utf-8')
    return logs

