import psutil
from collections import deque
from datetime import datetime
import os
import platform
import subprocess
import threading
import time
import logging

logger = logging.getLogger(__name__)

def get_system_stats():
    cpu_usage = psutil.cpu_percent(interval=0.5)
    cpu_cores = psutil.cpu_count(logical=True)
    
    # Manejar el caso donde cpu_freq() devuelva None (ej. en algunos contenedores o VMs muy restringidas)
    freq_info = psutil.cpu_freq()
    cpu_freq = round(freq_info.current / 1000, 2) if freq_info else 0.0
    
    ram = psutil.virtual_memory()
    
    # Leemos el almacenamiento del disco raíz ('/')
    disk = psutil.disk_usage('/')
    
    stats = {
        "timestamp": datetime.now().isoformat(),
        "cpu_percent": cpu_usage,
        "cpu_cores": cpu_cores,
        "cpu_frequency": cpu_freq,
        "ram_percent": ram.percent,
        "ram_used_gb": round(ram.used / (1024**3), 2),
        "ram_total_gb": round(ram.total / (1024**3), 2),
        "disk_percent": disk.percent,
        "disk_used_gb": round(disk.used / (1024**3), 2),
        "disk_total_gb": round(disk.total / (1024**3), 2)
    }
    return stats

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
            # En Linux (Ubuntu / Debian)
            is_docker = os.path.exists("/.dockerenv")
            cmd_target = "poweroff" if action == "shutdown" else "reboot"
            flag = "-h" if action == "shutdown" else "-r"
            
            if is_docker:
                # Si se ejecuta en contenedor con acceso al host
                cmd = f"nsenter -t 1 -m -u -i -n -p systemctl {cmd_target} || nsenter -t 1 -m -u -i -n -p shutdown {flag} now"
            else:
                # Ejecución nativa en el host
                cmd = f"sudo systemctl {cmd_target} || sudo shutdown {flag} now"
            
            subprocess.run(cmd, shell=True, check=False)
    except Exception as e:
        logger.error(f"Error al ejecutar la acción de energía '{action}': {e}")

def trigger_shutdown():
    """Programa el apagado del servidor."""
    thread = threading.Thread(target=_delayed_power_action, args=("shutdown",), daemon=True)
    thread.start()
    return {
        "success": True,
        "message": "Orden de apagado enviada correctamente. El servidor se apagará en breve."
    }

def trigger_reboot():
    """Programa el reinicio del servidor."""
    thread = threading.Thread(target=_delayed_power_action, args=("reboot",), daemon=True)
    thread.start()
    return {
        "success": True,
        "message": "Orden de reinicio enviada correctamente. El servidor se reiniciará en breve."
    }
