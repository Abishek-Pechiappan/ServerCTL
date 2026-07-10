import subprocess
import docker

_client = None

def get_client():
    global _client
    if _client is None:
        _client = docker.from_env()
    return _client

def containers_stopped():
    return get_client().containers.list(filters={'status': 'exited'})

def containers_running():
    return get_client().containers.list()

def docker_down(name: str):         # You can down the container by the name of it
    running = containers_running()
    for container in running:
        print(container.name)
    for container in running:
        if container.name == name:
            container.kill()
            
def docker_up(name: str):
    stopped = containers_stopped()
    for container in stopped:
        print(container.name)
    for container in stopped:
        if container.name == name:
            container.start()