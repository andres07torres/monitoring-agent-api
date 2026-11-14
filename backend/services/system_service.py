import psutil
from collections import deque
from datetime import datetime, timezone
import os
import platform
import subprocess
import threading
import time
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# Configurar ruta de /proc del host cuando corre dentro de Docker en Linux
if "HOST_PROC" in os.environ and hasattr(psutil, "PROCFS_PATH"):
    try:
        psutil.PROCFS_PATH = os.environ["HOST_PROC"]
    except Exception as e:
        logger.warning(f"No se pudo establecer psutil.PROCFS_PATH: {e}")

_system_logs_buffer: deque = deque(maxlen=100)

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
            "id": "alt-ok-001",
            "severity": "LOW",
            "message": "Todos los sistemas operan dentro de los parámetros normales. Sin alertas.",
            "timestamp": now_iso
        })

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
