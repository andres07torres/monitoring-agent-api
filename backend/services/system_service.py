import psutil
from collections import deque
from datetime import datetime, timezone
import os
import platform
import subprocess
import threading
import time
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Configurar ruta de /proc del host cuando corre dentro de Docker en Linux
if "HOST_PROC" in os.environ and hasattr(psutil, "PROCFS_PATH"):
    try:
        psutil.PROCFS_PATH = os.environ["HOST_PROC"]
    except Exception as e:
        logger.warning(f"No se pudo establecer psutil.PROCFS_PATH: {e}")

_system_logs_buffer: deque = deque(maxlen=100)

# ==============================================================================
# Metadatos dinámicos del sistema (OS, arquitectura, uptime, puertos y túnel)
# ==============================================================================

# Etiquetas legibles para los puertos más habituales en un servidor monitoreado.
_PORT_LABELS = {
    22: "SSH",
    80: "HTTP",
    443: "HTTPS",
    3000: "App",
    3306: "MySQL",
    5432: "PostgreSQL",
    6379: "Redis",
    8000: "HTTP",
    8001: "API",
    8080: "HTTP-Alt",
    8443: "WSS",
    9000: "Panel",
}

# Cachés con TTL para evitar escanear procesos/puertos en cada petición (el
# WebSocket de métricas llama a get_system_stats() cada ~1.5 s).
_METADATA_CACHE_TTL = 60.0
_protected_ports_cache: Dict[str, Any] = {"value": "", "timestamp": 0.0}
_tunnel_cache: Dict[str, Any] = {"value": "", "timestamp": 0.0}


def _running_in_container() -> bool:
    """Detecta si el agente se ejecuta dentro de un contenedor (Docker/LXC)."""
    if os.path.exists("/.dockerenv"):
        return True
    try:
        with open("/proc/1/cgroup", "r", encoding="utf-8", errors="ignore") as f:
            content = f.read().lower()
        return any(tag in content for tag in ("docker", "containerd", "kubepods", "lxc"))
    except Exception:
        return False


def _read_os_release(path: str) -> str:
    """Extrae el nombre legible del sistema operativo desde un archivo os-release."""
    try:
        values: Dict[str, str] = {}
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, raw_value = line.partition("=")
                values[key.strip()] = raw_value.strip().strip('"').strip("'")

        pretty = values.get("PRETTY_NAME")
        if pretty:
            return pretty
        name = values.get("NAME")
        version = values.get("VERSION") or values.get("VERSION_ID")
        if name and version:
            return f"{name} {version}"
        return name or ""
    except Exception:
        return ""


def _detect_os() -> str:
    """
    Devuelve el nombre y versión del sistema operativo anfitrión.
    En Docker se prioriza /host/etc/os-release (montado desde el host) y se
    agrega la marca "(Docker Engine)" cuando el agente corre contenerizado.
    """
    override = os.getenv("SYSTEM_OS", "").strip()
    if override:
        return override

    candidates = [
        os.getenv("HOST_OS_RELEASE", "").strip(),
        "/host/etc/os-release",
        "/etc/os-release",
        "/usr/lib/os-release",
    ]

    os_name = ""
    for candidate in candidates:
        if not candidate:
            continue
        os_name = _read_os_release(candidate)
        if os_name:
            break

    if not os_name:
        system = platform.system() or "Desconocido"
        if system == "Linux":
            os_name = f"Linux {platform.release()}".strip()
        elif system == "Darwin":
            os_name = f"macOS {platform.mac_ver()[0]}".strip()
        elif system == "Windows":
            os_name = f"Windows {platform.release()}".strip()
        else:
            os_name = f"{system} {platform.release()}".strip()

    if _running_in_container() and "docker" not in os_name.lower():
        os_name = f"{os_name} (Docker Engine)"

    return os_name


def _detect_architecture() -> str:
    """Normaliza la arquitectura del sistema a valores tipo x86_64 / arm64."""
    machine = (os.getenv("HOST_ARCH", "").strip() or platform.machine() or "").lower()
    aliases = {
        "x86_64": "x86_64",
        "amd64": "x86_64",
        "x64": "x86_64",
        "aarch64": "arm64",
        "arm64": "arm64",
        "armv8l": "arm64",
        "i386": "x86",
        "i486": "x86",
        "i586": "x86",
        "i686": "x86",
    }
    return aliases.get(machine, machine or "unknown")


def _format_uptime(seconds: float) -> str:
    """Convierte segundos de uptime a un texto legible en español."""
    total = max(0, int(seconds))
    days, remainder = divmod(total, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)

    def plural(value: int, singular: str, plural_form: str) -> str:
        return f"{value} {singular if value == 1 else plural_form}"

    if days > 0:
        return ", ".join([
            plural(days, "día", "días"),
            plural(hours, "hora", "horas"),
            f"{minutes} min",
        ])
    if hours > 0:
        return f"{plural(hours, 'hora', 'horas')}, {minutes} min"
    if minutes > 0:
        return f"{minutes} min"
    return plural(secs, "segundo", "segundos")


def _format_port(port: int, label: Optional[str] = None) -> str:
    label = label or _PORT_LABELS.get(port)
    return f"{port} ({label})" if label else str(port)


def _parse_ports_env(raw: str) -> str:
    """Parsea PROTECTED_PORTS admitiendo '443', '443:HTTPS' o '443=HTTPS'."""
    formatted: List[str] = []
    for item in raw.replace(";", ",").split(","):
        item = item.strip()
        if not item:
            continue
        port: Optional[int] = None
        label: Optional[str] = None
        for separator in (":", "="):
            if separator in item:
                left, _, right = item.partition(separator)
                if left.strip().isdigit():
                    port = int(left.strip())
                    label = right.strip() or None
                break
        if port is None and item.isdigit():
            port = int(item)
        formatted.append(_format_port(port, label) if port is not None else item)
    return ", ".join(dict.fromkeys(formatted))


def _collect_listening_ports() -> set:
    """Obtiene los puertos TCP en escucha del host/proc visible por el agente."""
    ports = set()
    try:
        for conn in psutil.net_connections(kind="inet"):
            if conn.status != psutil.CONN_LISTEN or not conn.laddr:
                continue
            port = getattr(conn.laddr, "port", None)
            if port is None and isinstance(conn.laddr, (tuple, list)) and len(conn.laddr) >= 2:
                port = conn.laddr[1]
            if port:
                ports.add(int(port))
    except Exception as e:
        logger.debug(f"No se pudieron enumerar los puertos en escucha: {e}")
    return ports


def _collect_docker_published_ports() -> set:
    """Obtiene los puertos publicados por los contenedores Docker en ejecución."""
    ports = set()
    try:
        from services.docker_service import get_docker_client

        client = get_docker_client()
        if not client:
            return ports
        for container in client.containers.list():
            bindings = (container.attrs.get("NetworkSettings") or {}).get("Ports") or {}
            for host_bindings in bindings.values():
                for binding in host_bindings or []:
                    host_port = (binding or {}).get("HostPort")
                    if host_port and str(host_port).isdigit():
                        ports.add(int(host_port))
    except Exception as e:
        logger.debug(f"No se pudieron obtener los puertos publicados de Docker: {e}")
    return ports


def _detect_protected_ports() -> str:
    """
    Devuelve los puertos protegidos/expuestos, calculados dinámicamente.
    Prioridad: variable PROTECTED_PORTS > puertos Docker publicados + puertos
    en escucha relevantes + puerto propio del agente.
    """
    override = os.getenv("PROTECTED_PORTS", "").strip()
    if override:
        return _parse_ports_env(override)

    now = time.monotonic()
    if _protected_ports_cache["value"] and (now - _protected_ports_cache["timestamp"]) < _METADATA_CACHE_TTL:
        return _protected_ports_cache["value"]

    agent_port = 8001
    try:
        agent_port = int(os.getenv("API_PORT", "8001"))
    except (TypeError, ValueError):
        pass

    ports = {agent_port}
    ports.update(_collect_docker_published_ports())

    # Solo se muestran puertos conocidos/relevantes para evitar ruido de
    # puertos efímeros del sistema.
    for port in _collect_listening_ports():
        if port in _PORT_LABELS or port == agent_port:
            ports.add(port)

    value = ", ".join(_format_port(port) for port in sorted(ports))
    _protected_ports_cache.update({"value": value, "timestamp": now})
    return value


def _detect_zero_trust_tunnel() -> str:
    """
    Detecta el túnel Zero Trust en uso a partir de los procesos en ejecución
    y, como respaldo, de archivos de configuración habituales.
    """
    override = os.getenv("ZERO_TRUST_TUNNEL", "").strip()
    if override:
        return override

    now = time.monotonic()
    if _tunnel_cache["value"] and (now - _tunnel_cache["timestamp"]) < _METADATA_CACHE_TTL:
        return _tunnel_cache["value"]

    signatures = (
        ("cloudflared", "Cloudflare Tunnel (HTTPS/WSS)"),
        ("tailscaled", "Tailscale (WireGuard)"),
        ("tailscale", "Tailscale (WireGuard)"),
        ("ngrok", "ngrok (HTTPS)"),
        ("zerotier-one", "ZeroTier (VPN)"),
        ("frpc", "FRP (TCP)"),
    )

    detected: List[str] = []
    try:
        for proc in psutil.process_iter(["name", "cmdline"]):
            info = proc.info or {}
            blob = f"{info.get('name') or ''} {' '.join(info.get('cmdline') or [])}".lower()
            for token, label in signatures:
                if token in blob and label not in detected:
                    detected.append(label)
                    break
    except Exception as e:
        logger.debug(f"No se pudieron inspeccionar procesos para detectar el túnel: {e}")

    if not detected:
        config_candidates = (
            ("/host/etc/cloudflared/config.yml", "Cloudflare Tunnel (HTTPS/WSS)"),
            ("/etc/cloudflared/config.yml", "Cloudflare Tunnel (HTTPS/WSS)"),
            ("/host/etc/ngrok.yml", "ngrok (HTTPS)"),
            ("/etc/ngrok.yml", "ngrok (HTTPS)"),
        )
        for path, label in config_candidates:
            if os.path.exists(path) and label not in detected:
                detected.append(label)

    value = ", ".join(detected) if detected else "Ninguno"
    _tunnel_cache.update({"value": value, "timestamp": now})
    return value


def get_system_metadata() -> Dict[str, str]:
    """Retorna los metadatos dinámicos del sistema usados por la app Android."""
    metadata = {
        "os": "Desconocido",
        "architecture": "unknown",
        "uptime": "0 min",
        "protected_ports": "",
        "zero_trust_tunnel": "Ninguno",
    }

    try:
        metadata["os"] = _detect_os()
    except Exception as e:
        logger.warning(f"Error al detectar el sistema operativo: {e}")

    try:
        metadata["architecture"] = _detect_architecture()
    except Exception as e:
        logger.warning(f"Error al detectar la arquitectura: {e}")

    try:
        metadata["uptime"] = _format_uptime(time.time() - psutil.boot_time())
    except Exception as e:
        logger.warning(f"Error al calcular el uptime: {e}")

    try:
        metadata["protected_ports"] = _detect_protected_ports()
    except Exception as e:
        logger.warning(f"Error al detectar los puertos protegidos: {e}")

    try:
        metadata["zero_trust_tunnel"] = _detect_zero_trust_tunnel()
    except Exception as e:
        logger.warning(f"Error al detectar el túnel Zero Trust: {e}")

    return metadata

def add_system_log(level: str, message: str) -> Dict[str, Any]:
    """Registra un evento en el historial en memoria."""
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = {
        "id": f"log-{int(time.time() * 1000)}",
        "timestamp": now_iso,
        "level": level.upper(),
        "message": message
    }
    _system_logs_buffer.appendleft(entry)
    return entry

def get_system_logs() -> List[Dict[str, Any]]:
    """Retorna los últimos registros del sistema o del orquestador."""
    if not _system_logs_buffer:
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return [
            {
                "id": "log-001",
                "timestamp": now_iso,
                "level": "INFO",
                "message": "Servicio de monitoreo iniciado correctamente"
            },
            {
                "id": "log-002",
                "timestamp": now_iso,
                "level": "INFO",
                "message": "Agente conectado y listo para recibir peticiones"
            }
        ]
    return list(_system_logs_buffer)

def get_system_stats() -> Dict[str, Any]:
    """
    Retorna telemetría del servidor anfitrión de forma segura.
    Cada llamada a psutil está protegida individualmente para evitar cualquier Error 500.
    """
    # 1. CPU Percent
    try:
        cpu_usage = float(psutil.cpu_percent(interval=0.2))
    except Exception as e:
        logger.warning(f"Error al leer cpu_percent: {e}")
        cpu_usage = 0.0

    # 2. CPU Cores
    try:
        cpu_cores = int(psutil.cpu_count(logical=True) or 1)
    except Exception as e:
        logger.warning(f"Error al leer cpu_cores: {e}")
        cpu_cores = 1

    # 3. CPU Frequency (en GHz)
    try:
        freq_info = psutil.cpu_freq()
        cpu_freq = round(freq_info.current / 1000.0, 2) if (freq_info and freq_info.current) else 0.0
    except Exception as e:
        logger.warning(f"Error al leer cpu_freq: {e}")
        cpu_freq = 0.0

    # 4. RAM
    try:
        ram = psutil.virtual_memory()
        ram_percent = float(ram.percent)
        ram_used_gb = round(ram.used / (1024**3), 2)
        ram_total_gb = round(ram.total / (1024**3), 2)
    except Exception as e:
        logger.warning(f"Error al leer virtual_memory: {e}")
        ram_percent = 0.0
        ram_used_gb = 0.0
        ram_total_gb = 0.0

    # 5. Disco
    try:
        if platform.system() == "Windows":
            disk_path = os.path.splitdrive(os.getcwd())[0] + os.sep or "C:\\"
        else:
            disk_path = "/"
        disk = psutil.disk_usage(disk_path)
        disk_percent = float(disk.percent)
        disk_used_gb = round(disk.used / (1024**3), 2)
        disk_total_gb = round(disk.total / (1024**3), 2)
    except Exception as e:
        try:
            disk = psutil.disk_usage(".")
            disk_percent = float(disk.percent)
            disk_used_gb = round(disk.used / (1024**3), 2)
            disk_total_gb = round(disk.total / (1024**3), 2)
        except Exception as e2:
            logger.warning(f"Error al leer disk_usage: {e2}")
            disk_percent = 0.0
            disk_used_gb = 0.0
            disk_total_gb = 0.0

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        "cpu_percent": cpu_usage,
        "cpu_cores": cpu_cores,
        "cpu_frequency": cpu_freq,
        "ram_percent": ram_percent,
        "ram_used_gb": ram_used_gb,
        "ram_total_gb": ram_total_gb,
        "disk_percent": disk_percent,
        "disk_used_gb": disk_used_gb,
        "disk_total_gb": disk_total_gb,
        **get_system_metadata(),
        "timestamp": now_iso
    }

def get_system_alerts() -> List[Dict[str, Any]]:
    """
    Evalúa el estado del hardware y genera alertas con severidades soportadas:
    HIGH, CRITICAL, MEDIUM, WARNING, LOW, SUCCESS.
    """
    alerts = []
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Evaluar CPU
    try:
        cpu = psutil.cpu_percent(interval=0.2)
        if cpu >= 90:
            alerts.append({
                "id": "alt-cpu-001",
                "severity": "CRITICAL",
                "message": f"Uso de CPU supera el 90%: {cpu}%",
                "timestamp": now_iso
            })
        elif cpu >= 75:
            alerts.append({
                "id": "alt-cpu-002",
                "severity": "HIGH",
                "message": f"Sobrecarga de CPU detectada: {cpu}%",
                "timestamp": now_iso
            })
        elif cpu >= 60:
            alerts.append({
                "id": "alt-cpu-003",
                "severity": "MEDIUM",
                "message": f"Uso moderado de CPU: {cpu}%",
                "timestamp": now_iso
            })
    except Exception as e:
        logger.warning(f"Error al evaluar alertas de CPU: {e}")

    # Evaluar RAM
    try:
        ram = psutil.virtual_memory()
        if ram.percent >= 90:
            alerts.append({
                "id": "alt-ram-001",
                "severity": "CRITICAL",
                "message": f"Uso de memoria supera el 90%: {ram.percent}%",
                "timestamp": now_iso
            })
        elif ram.percent >= 80:
            alerts.append({
                "id": "alt-ram-002",
                "severity": "HIGH",
                "message": f"Memoria RAM en nivel elevado: {ram.percent}%",
                "timestamp": now_iso
            })
    except Exception as e:
        logger.warning(f"Error al evaluar alertas de RAM: {e}")

    # Evaluar Disco
    try:
        disk_path = os.path.splitdrive(os.getcwd())[0] + os.sep if platform.system() == "Windows" else "/"
        disk = psutil.disk_usage(disk_path)
        if disk.percent >= 90:
            alerts.append({
                "id": "alt-disk-001",
                "severity": "CRITICAL",
                "message": f"Almacenamiento en disco crítico (>90%): {disk.percent}%",
                "timestamp": now_iso
            })
        elif disk.percent >= 80:
            alerts.append({
                "id": "alt-disk-002",
                "severity": "WARNING",
                "message": f"Uso de disco elevado: {disk.percent}%",
                "timestamp": now_iso
            })
    except Exception as e:
        logger.warning(f"Error al evaluar alertas de disco: {e}")

    if not alerts:
        alerts.append({
            "id": "A0",
            "severity": "LOW",
            "message": "Todos los sistemas operan dentro de los parámetros normales. Sin alertas.",
            "timestamp": now_iso
        })

    # Asignar identificadores cortos secuenciales (A0, A1, A2, ...)
    for idx, alert in enumerate(alerts):
        alert["id"] = f"A{idx}"

    return alerts

def _delayed_power_action(action: str):
    """
    Espera 1.5 segundos para permitir que la respuesta HTTP termine de enviarse
    al cliente antes de cortar los servicios del sistema operativo.
    """
    time.sleep(1.5)
    system = platform.system()
    try:
        if system == "Windows":
            flag = "/s" if action == "shutdown" else "/r"
            subprocess.run(["shutdown", flag, "/t", "1"], check=False)
        else:
            cmd_target = "poweroff" if action == "shutdown" else "reboot"
            flag = "-h" if action == "shutdown" else "-r"
            cmd = (
                f"nsenter -t 1 -m -u -i -n -p /bin/systemctl {cmd_target} 2>/dev/null || "
                f"nsenter -t 1 -m -u -i -n -p /sbin/shutdown {flag} now 2>/dev/null || "
                f"nsenter -t 1 -m -u -i -n -p shutdown {flag} now 2>/dev/null || "
                f"sudo systemctl {cmd_target} 2>/dev/null || "
                f"sudo shutdown {flag} now"
            )
            logger.info(f"Ejecutando acción de energía: {action}")
            subprocess.run(cmd, shell=True, check=False)
    except Exception as e:
        logger.error(f"Error al ejecutar la acción de energía '{action}': {e}")

def trigger_shutdown():
    """Programa el apagado del servidor."""
    add_system_log("WARNING", "Orden de apagado del servidor recibida")
    thread = threading.Thread(target=_delayed_power_action, args=("shutdown",), daemon=True)
    thread.start()
    return {
        "success": True,
        "message": "Orden de apagado enviada correctamente. El servidor se apagará en breve."
    }

def trigger_reboot():
    """Programa el reinicio del servidor."""
    add_system_log("WARNING", "Orden de reinicio del servidor recibida")
    thread = threading.Thread(target=_delayed_power_action, args=("reboot",), daemon=True)
    thread.start()
    return {
        "success": True,
        "message": "Orden de reinicio enviada correctamente. El servidor se reiniciará en breve."
    }
