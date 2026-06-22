import docker

def running():
    client = docker.from_env()     # To see what all is running in the server
    l = client.containers.list(filters={'status': 'running'})
    for _ in l:
        print(_.name)