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

def list_containers():
    """All containers (running + stopped) with a UI-friendly status/image."""
    containers = get_client().containers.list(all=True)
    result = []
    for c in containers:
        image = c.image.tags[0] if c.image and c.image.tags else c.short_id
        result.append({"name": c.name, "status": c.status, "image": image})
    result.sort(key=lambda c: (c["status"] != "running", c["name"].lower()))
    return result

def docker_down(name: str):
    for container in get_client().containers.list(all=True):
        if container.name == name and container.status == "running":
            container.kill()
            return

def docker_up(name: str):
    for container in get_client().containers.list(all=True):
        if container.name == name and container.status != "running":
            container.start()
            return