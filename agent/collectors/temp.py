import psutil

def temprature():
    information = psutil.sensors_temperatures()
    for temp_key,temp_value in information.items():
        for temp_list in temp_value:
            if temp_list.label == 'Package id 0':
                print(temp_list.current)
        