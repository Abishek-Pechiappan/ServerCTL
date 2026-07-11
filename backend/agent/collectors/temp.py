import psutil


def temprature():
    information = psutil.sensors_temperatures()
    for readings in information.values():
        for reading in readings:
            if reading.label == 'Package id 0':
                return reading.current
    return None