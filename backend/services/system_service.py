import psutil
from collections import deque
from datetime import datetime

# Guardar los últimos 60 registros (ej. 1 hora si se consulta cada minuto, o 1 min si es cada seg)
system_history = deque(maxlen=60)

def get_system_stats():
    cpu_usage = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory()
    
    # Leemos el almacenamiento del disco raíz ('/')
    disk = psutil.disk_usage('/')
    
    stats = {
        "timestamp": datetime.now().isoformat(),
        "cpu_percent": cpu_usage,
        "ram_percent": ram.percent,
        "ram_used_gb": round(ram.used / (1024**3), 2),
        "ram_total_gb": round(ram.total / (1024**3), 2),
        "disk_percent": disk.percent,
        "disk_used_gb": round(disk.used / (1024**3), 2),
        "disk_total_gb": round(disk.total / (1024**3), 2)
    }
    
    # Añadimos al historial en memoria
    system_history.append(stats)
    
    return stats

def get_system_history():
    # Retorna la lista de historial
    return list(system_history)
