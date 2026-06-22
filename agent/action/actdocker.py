import subprocess
import docker

def docker_down():         # You can down the container by the name of it 
    client = docker.from_env()
    up = client.containers.list()
    for ids in up:
        print(ids.name)
    kill = input('container you want to kill :')
    for ids in up:
        if kill == ids.name:
            ids.kill()
            
def docker_up():            # You can start an conatiner by the name of it
    client = docker.from_env()
    down = client.containers.list(filters={'status': 'exited'})
    for ids in down:
        print(ids.name)
    start = input('Enter the container Name: ')
    for ids in down:
        if ids.name == start:
            ids.start()