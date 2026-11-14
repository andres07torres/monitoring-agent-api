import docker
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

_docker_client: Optional[docker.DockerClient] = None

def get_docker_client() -> Optional[docker.DockerClient]:
    """
    Retorna el cliente de Docker si está disponible.
    Intenta reconectarse si se perdió la conexión. Nunca lanza excepciones no capturadas.
    """
    global _docker_client
    if _docker_client is not None:
        try:
            _docker_client.ping()
            return _docker_client
        except Exception:
            _docker_client = None

    try:
        _docker_client = docker.from_env()
        _docker_client.ping()
        return _docker_client
    except Exception as e:
        logger.warning(f"No se pudo conectar con Docker Engine (/var/run/docker.sock): {e}")
        _docker_client = None
        return None

def _get_single_container_stats(container) -> Dict[str, float]:
    """Calcula cpu_usage (%) y ram_usage (MB) para un contenedor de forma segura."""
    try:
        if container.status != "running":
            return {"cpu_usage": 0.0, "ram_usage": 0.0}

        stats = container.stats(stream=False)

        # 1. RAM Usage (MB)
        memory_stats = stats.get("memory_stats", {})
        usage_bytes = memory_stats.get("usage", 0)
        stats_sub = memory_stats.get("stats", {})
        cache_bytes = stats_sub.get("cache") or stats_sub.get("inactive_file", 0)
        actual_mem = max(0, usage_bytes - cache_bytes) if (cache_bytes and cache_bytes < usage_bytes) else usage_bytes
        ram_mb = round(actual_mem / (1024 * 1024), 1)

        # 2. CPU Usage (%)
        cpu_stats = stats.get("cpu_stats", {})
        precpu_stats = stats.get("precpu_stats", {})

        cpu_delta = cpu_stats.get("cpu_usage", {}).get("total_usage", 0) - precpu_stats.get("cpu_usage", {}).get("total_usage", 0)
        system_delta = cpu_stats.get("system_cpu_usage", 0) - precpu_stats.get("system_cpu_usage", 0)

        cpu_percent = 0.0
        if system_delta > 0 and cpu_delta > 0:
            online_cpus = cpu_stats.get("online_cpus") or len(cpu_stats.get("cpu_usage", {}).get("percpu_usage", [])) or 1
            cpu_percent = round((cpu_delta / system_delta) * online_cpus * 100.0, 1)

        return {"cpu_usage": cpu_percent, "ram_usage": ram_mb}
    except Exception as e:
        logger.debug(f"Error al obtener métricas de contenedor {getattr(container, 'name', '')}: {e}")
        return {"cpu_usage": 0.0, "ram_usage": 0.0}

def _get_container_image_tag(container) -> str:
    """Extrae el nombre o tag de la imagen de forma segura sin disparar ImageNotFound."""
    try:
        # 1. Buscar en los atributos ya presentes en memoria
        config_image = container.attrs.get("Config", {}).get("Image")
        if config_image:
            return config_image
        # 2. Si c.image existe y tiene tags
        if hasattr(container, "image") and container.image and hasattr(container.image, "tags") and container.image.tags:
            return container.image.tags[0]
        # 3. Fallback al Image ID corto
        raw_img = container.attrs.get("Image", "")
        return str(raw_img)[:12] if raw_img else "N/A"
    except Exception:
        return "N/A"

def list_containers() -> List[Dict[str, Any]]:
    """
    Retorna la lista de contenedores con sus métricas calculadas.
    Si Docker no está disponible, retorna una lista vacía en vez de lanzar Error 500.
    """
    client = get_docker_client()
    if not client:
        logger.warning("list_containers: Docker client no disponible.")
        return []

    try:
        raw_containers = client.containers.list(all=True)
    except Exception as e:
        logger.error(f"Error al listar contenedores desde Docker SDK: {e}")
        return []

    # Excluimos el contenedor del propio agente de monitoreo si aplica
    containers = [c for c in raw_containers if getattr(c, "name", "") != "monitoring-agent-api"]

    # Calcular estadísticas concurrentemente para todos los contenedores en ejecución
    stats_map = {}
    running_containers = [c for c in containers if getattr(c, "status", "") == "running"]

    if running_containers:
        max_workers = min(len(running_containers), 15)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_cid = {executor.submit(_get_single_container_stats, c): c.short_id for c in running_containers}
            try:
                # Timeout global de 2.5s para no bloquear peticiones móviles
                for future in as_completed(future_to_cid, timeout=2.5):
                    cid = future_to_cid[future]
                    try:
                        stats_map[cid] = future.result()
                    except Exception:
                        stats_map[cid] = {"cpu_usage": 0.0, "ram_usage": 0.0}
            except Exception:
                # Si se alcanza el timeout global, los pendientes quedan con 0.0
                pass

    result = []
    for c in containers:
        try:
            cid = getattr(c, "short_id", getattr(c, "id", "unknown")[:12])
            c_name = getattr(c, "name", "unknown")
            c_status = getattr(c, "status", "unknown")
            c_stats = stats_map.get(cid, {"cpu_usage": 0.0, "ram_usage": 0.0})
            image_tag = _get_container_image_tag(c)

            result.append({
                "id": cid,
                "name": c_name,
                "status": c_status,
                "cpu_usage": c_stats["cpu_usage"],
                "ram_usage": c_stats["ram_usage"],
                "image": image_tag
            })
        except Exception as ex:
            logger.warning(f"Error parseando contenedor: {ex}")
            try:
                result.append({
                    "id": getattr(c, "short_id", "unknown"),
                    "name": getattr(c, "name", "unknown"),
                    "status": getattr(c, "status", "unknown"),
                    "cpu_usage": 0.0,
                    "ram_usage": 0.0,
                    "image": "N/A"
                })
            except Exception:
                pass

    return result

def get_container_info(container_id: str) -> Dict[str, Any]:
    client = get_docker_client()
    if not client:
        raise RuntimeError("Docker Engine no disponible")
    container = client.containers.get(container_id)
    c_stats = _get_single_container_stats(container)
    image_tag = _get_container_image_tag(container)
    return {
        "id": container.short_id,
        "name": container.name,
        "status": container.status,
        "cpu_usage": c_stats["cpu_usage"],
        "ram_usage": c_stats["ram_usage"],
        "image": image_tag,
        "created": container.attrs.get("Created")
    }

def start_container(container_id: str) -> Dict[str, str]:
    client = get_docker_client()
    if not client:
        raise RuntimeError("Docker Engine no disponible")
    container = client.containers.get(container_id)
    container.start()
    return {"status": "started", "id": container_id, "message": f"Contenedor {container_id} iniciado"}

def stop_container(container_id: str) -> Dict[str, str]:
    client = get_docker_client()
    if not client:
        raise RuntimeError("Docker Engine no disponible")
    container = client.containers.get(container_id)
    container.stop()
    return {"status": "stopped", "id": container_id, "message": f"Contenedor {container_id} detenido"}

def restart_container(container_id: str) -> Dict[str, str]:
    client = get_docker_client()
    if not client:
        raise RuntimeError("Docker Engine no disponible")
    container = client.containers.get(container_id)
    container.restart()
    return {"status": "restarted", "id": container_id, "message": f"Contenedor {container_id} reiniciado"}

def pause_container(container_id: str) -> Dict[str, str]:
    client = get_docker_client()
    if not client:
        raise RuntimeError("Docker Engine no disponible")
    container = client.containers.get(container_id)
    container.pause()
    return {"status": "paused", "id": container_id, "message": f"Contenedor {container_id} pausado"}

def unpause_container(container_id: str) -> Dict[str, str]:
    client = get_docker_client()
    if not client:
        raise RuntimeError("Docker Engine no disponible")
    container = client.containers.get(container_id)
    container.unpause()
    return {"status": "unpaused", "id": container_id, "message": f"Contenedor {container_id} reanudado"}

def remove_container(container_id: str) -> Dict[str, str]:
    client = get_docker_client()
    if not client:
        raise RuntimeError("Docker Engine no disponible")
    container = client.containers.get(container_id)
    container.remove(force=True)
    return {"status": "removed", "id": container_id, "message": f"Contenedor {container_id} eliminado"}

def get_container_stats(container_id: str) -> Dict[str, Any]:
    client = get_docker_client()
    if not client:
        raise RuntimeError("Docker Engine no disponible")
    container = client.containers.get(container_id)
    return container.stats(stream=False)

def prune_system() -> Dict[str, Any]:
    client = get_docker_client()
    if not client:
        raise RuntimeError("Docker Engine no disponible")
    containers_pruned = client.containers.prune()
    images_pruned = client.images.prune()
    networks_pruned = client.networks.prune()
    volumes_pruned = client.volumes.prune()
    return {
        "status": "pruned",
        "message": "Limpieza de recursos Docker completada con éxito",
        "details": {
            "containers": containers_pruned,
            "images": images_pruned,
            "networks": networks_pruned,
            "volumes": volumes_pruned
        }
    }

def get_container_logs(container_id: str, tail: int = 100) -> List[str]:
    client = get_docker_client()
    if not client:
        return ["Docker Engine no disponible"]
    try:
        container = client.containers.get(container_id)
        raw_logs = container.logs(tail=tail).decode('utf-8', errors='replace')
        return raw_logs.splitlines()
    except Exception as e:
        logger.warning(f"Error al obtener registros de {container_id}: {e}")
        return [f"Error al obtener registros: {str(e)}"]
