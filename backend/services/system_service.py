import psutil
import time
import threading
from collections import deque
from datetime import datetime

# Una lista para guardar las últimas 60 muestras (aprox 10 minutos de historial)
history_data = deque(maxlen=60)

def background_collector():
    """Esta función corre en segundo plano y guarda una muestra cada 10 segundos."""
    while True:
        cpu = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory().percent
        timestamp = int(time.time())
        
        # Guardamos la muestra con las llaves que espera Vico en Android
        history_data.append({
            "timestamp": timestamp,
            "cpu": cpu,
            "ram": ram
        })
        time.sleep(10)

# Iniciamos el recolector apenas se importa el servicio
threading.Thread(target=background_collector, daemon=True).start()

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
    return stats

def get_system_history():
    # Retorna la lista de historial
    return list(history_data)
