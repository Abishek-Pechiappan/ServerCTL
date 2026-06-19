import psutil 

def disk():
    a = psutil.disk_usage('/')
    total = round(a.total/pow(1024, 3), 2)
    used = round(a.used/pow(1024, 3), 2)
    print(total)
    print(used)
    print(a.percent,"%")

disk()