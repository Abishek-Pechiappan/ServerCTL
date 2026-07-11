import psutil


def ram():
    mem = psutil.virtual_memory()
    return {
        "total_gb": round(mem.total / pow(1024, 3), 2),
        "used_gb": round(mem.used / pow(1024, 3), 2),
        "cached_gb": round(mem.cached / pow(1024, 3), 2),
        "percent": mem.percent,
    }