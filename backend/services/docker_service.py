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

# ==============================================================================
# Comprobaciones y Detección de Salud de Contenedores (Healthcheck)
# ==============================================================================

NON_HTTP_KEYWORDS = [
    "mysql", "mariadb",
    "postgres", "postgresql", "pgsql",
    "redis", "valkey", "memcached", "keydb",
    "mongo", "mongodb",
    "mailer", "mailhog", "mailpit", "postfix", "exim", "smtp",
    "worker", "workers", "celery", "queue", "rabbitmq", "kafka", "zookeeper", "nats",
    "cron", "scheduler", "beat"
]

NON_HTTP_PORTS = {
    3306, 33060,  # MySQL / MariaDB
    5432,         # PostgreSQL
    6379,         # Redis
    27017, 27018, # MongoDB
    5672,         # RabbitMQ
    9092,         # Kafka
    11211,        # Memcached
    25, 465, 587, # SMTP / Mailers
}

def find_container(identifier: str):
    """
    Busca un contenedor por ID (completo o corto) o por nombre.
    """
    if not identifier:
        return None
    client = get_docker_client()
    if not client:
        return None

    cleaned_id = identifier.strip().strip("/")
    try:
        return client.containers.get(cleaned_id)
    except Exception:
        pass

    try:
        all_c = client.containers.list(all=True)
        # Búsqueda exacta por nombre o IDs
        for c in all_c:
            c_name = getattr(c, "name", "").strip("/")
            c_id = getattr(c, "id", "")
            c_short_id = getattr(c, "short_id", "")
            if cleaned_id in (c_name, c_id, c_short_id):
                return c

        # Búsqueda insensible a mayúsculas/minúsculas
        lower_id = cleaned_id.lower()
        for c in all_c:
            c_name = getattr(c, "name", "").strip("/").lower()
            if lower_id == c_name:
                return c

        for c in all_c:
            c_name = getattr(c, "name", "").strip("/").lower()
            if lower_id in c_name:
                return c
    except Exception as e:
        logger.warning(f"Error buscando contenedor '{identifier}': {e}")

    return None

def is_non_http_service(
    container=None,
    identifier: str = "",
    port: Optional[int] = None,
    service_type: Optional[str] = None
) -> bool:
    """
    Determina si un servicio/contenedor corresponde a una Base de Datos o servicio no HTTP
    (mysql, postgres, redis, mailer, workers, etc.).
    """
    # 1. Indicador explícito por parámetro service_type / type
    if service_type:
        st = service_type.strip().lower()
        if st in ["db", "database", "non-http", "non_http", "worker", "mailer", "queue", "redis", "postgres", "mysql", "nosql"]:
            return True
        if st in ["web", "http", "api", "app", "frontend", "backend"]:
            return False

    # 2. Puerto conocido de base de datos o servicio no HTTP
    if port and int(port) in NON_HTTP_PORTS:
        return True

    # 3. Inspección de metadatos del contenedor Docker si está disponible
    if container:
        c_name = getattr(container, "name", "").lower()
        c_image = _get_container_image_tag(container).lower()

        # Comprobar palabras clave en nombre o imagen
        for kw in NON_HTTP_KEYWORDS:
            if kw in c_name or kw in c_image:
                return True

        # Comprobar puertos expuestos
        exposed = container.attrs.get("Config", {}).get("ExposedPorts") or {}
        ports_mapping = container.attrs.get("NetworkSettings", {}).get("Ports") or {}
        all_port_keys = list(exposed.keys()) + list(ports_mapping.keys())
        
        has_non_http_port = False
        has_http_port = False
        for p_key in all_port_keys:
            try:
                p_num = int(p_key.split("/")[0])
                if p_num in NON_HTTP_PORTS:
                    has_non_http_port = True
                elif p_num in (80, 443, 8080, 3000, 5000, 8000, 8081, 9000):
                    has_http_port = True
            except (ValueError, IndexError):
                continue
        
        if has_non_http_port and not has_http_port:
            return True

    # 4. Palabras clave en el identificador o URL pasada
    if identifier:
        id_lower = identifier.lower()
        for kw in NON_HTTP_KEYWORDS:
            if kw in id_lower:
                return True

    return False

def get_container_web_target(container, default_port: Optional[int] = None) -> str:
    """
    Obtiene la URL HTTP interna o en localhost para un contenedor web.
    Prioriza consultar el puerto expuesto en localhost o el puerto estándar interno HTTP.
    """
    ports_mapping = container.attrs.get("NetworkSettings", {}).get("Ports") or {}
    
    # Priorizar mapeo a localhost
    preferred_internal = [80, 8080, 3000, 5000, 8000, 443]
    if default_port:
        preferred_internal.insert(0, int(default_port))

    for p_int in preferred_internal:
        p_key = f"{p_int}/tcp"
        if p_key in ports_mapping and ports_mapping[p_key]:
            host_port = ports_mapping[p_key][0].get("HostPort")
            if host_port:
                return f"http://127.0.0.1:{host_port}"

    for p_key, bindings in ports_mapping.items():
        if bindings:
            host_port = bindings[0].get("HostPort")
            if host_port:
                return f"http://127.0.0.1:{host_port}"

    # Red interna Docker (IP interna del contenedor)
    ip_addr = container.attrs.get("NetworkSettings", {}).get("IPAddress")
    if not ip_addr:
        networks = container.attrs.get("NetworkSettings", {}).get("Networks") or {}
        for net_name, net_conf in networks.items():
            if net_conf.get("IPAddress"):
                ip_addr = net_conf["IPAddress"]
                break

    int_port = default_port or 80
    exposed = container.attrs.get("Config", {}).get("ExposedPorts") or {}
    if exposed:
        for p_key in exposed.keys():
            try:
                int_port = int(p_key.split("/")[0])
                break
            except (ValueError, IndexError):
                pass

    if ip_addr:
        return f"http://{ip_addr}:{int_port}"

    c_name = getattr(container, "name", "").strip("/")
    if c_name:
        return f"http://{c_name}:{int_port}"

    return f"http://127.0.0.1:{int_port}"
