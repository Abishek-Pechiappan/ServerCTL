import docker


def running():
    client = docker.from_env()     # To see what all is running in the server
    containers = client.containers.list(filters={'status': 'running'})
    return [container.name for container in containers]