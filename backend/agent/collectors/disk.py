import psutil


def disk():
    usage = psutil.disk_usage('/')
    return {
        "total_gb": round(usage.total / pow(1024, 3), 2),
        "used_gb": round(usage.used / pow(1024, 3), 2),
        "percent": usage.percent,
    }