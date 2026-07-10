import psutil 

def ram():
    mem = psutil.virtual_memory()
    total = round(mem.total/pow(1024, 3), 2)
    used = round(mem.used/pow(1024, 3), 2)
    cached = round(mem.cached/pow(1024, 3), 2)
    print(total)
    print(used)
    print(cached)

ram()