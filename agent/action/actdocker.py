import subprocess
import docker

client = docker.from_env()

def containers_stopped():
    return client.containers.list(filters={'status': 'exited'})
            
def containers_running():
    return client.containers.list()

def docker_down():         # You can down the container by the name of it 
    running = containers_running()
    for container in running:
        print(container.name)
    name = input('container you want to kill :')
    for container in running:
        if container.name == name:
            container.kill()
            
def docker_up():
    stopped = containers_stopped()   
    for container in stopped:
        print(container.name)
    name = input('Enter the container Name: ')
    for container in stopped:
        if container.name == name:
            container.start()
    
docker_down()