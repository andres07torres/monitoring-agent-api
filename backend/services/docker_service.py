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
    # Excluimos el contenedor de la propia API para que no se monitoree a sí misma
    return [
        {"id": c.short_id, "name": c.name, "status": c.status, "image": c.image.tags[0] if c.image.tags else "N/A"} 
        for c in containers 
        if c.name != "monitoring-agent-api"
    ]

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

def restart_container(container_id: str):
    client = _get_client()
    container = client.containers.get(container_id)
    container.restart()
    return {"status": "restarted", "id": container_id}

def pause_container(container_id: str):
    client = _get_client()
    container = client.containers.get(container_id)
    # Check if paused already to avoid error? Not strictly necessary.
    container.pause()
    return {"status": "paused", "id": container_id}

def unpause_container(container_id: str):
    client = _get_client()
    container = client.containers.get(container_id)
    container.unpause()
    return {"status": "unpaused", "id": container_id}

def remove_container(container_id: str):
    client = _get_client()
    container = client.containers.get(container_id)
    container.remove(force=True)
    return {"status": "removed", "id": container_id}

def get_container_stats(container_id: str):
    client = _get_client()
    container = client.containers.get(container_id)
    stats = container.stats(stream=False)
    return stats

def prune_system():
    client = _get_client()
    containers_pruned = client.containers.prune()
    images_pruned = client.images.prune()
    networks_pruned = client.networks.prune()
    volumes_pruned = client.volumes.prune()
    return {
        "status": "pruned",
        "details": {
            "containers": containers_pruned,
            "images": images_pruned,
            "networks": networks_pruned,
            "volumes": volumes_pruned
        }
    }

def get_container_logs(container_id: str, tail: int = 100):
    client = _get_client()
    container = client.containers.get(container_id)
    # .logs returns bytes, decode to string
    raw_logs = container.logs(tail=tail).decode('utf-8')
    # EL TRUCO ESTÁ AQUÍ: Cortamos el string gigante en una lista de líneas
    logs_list = raw_logs.splitlines()
    return logs_list
