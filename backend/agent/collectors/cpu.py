import psutil


def cpu():
    return psutil.cpu_percent(interval=1)