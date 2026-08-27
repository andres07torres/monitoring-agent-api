import psutil
from collections import deque
from datetime import datetime

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
