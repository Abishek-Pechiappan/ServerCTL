import psutil

def cpu():
    print(psutil.cpu_percent(interval=1))
