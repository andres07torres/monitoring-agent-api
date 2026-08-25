import psutil

def get_system_stats():
    cpu_usage = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory()
    return {
        "cpu_percent": cpu_usage,
        "ram_percent": ram.percent,
        "ram_used_gb": round(ram.used / (1024**3), 2),
        "ram_total_gb": round(ram.total / (1024**3), 2)
    }
