from action.actdocker import get_client


def running():
    """Names of currently running containers.

    Shares the process-wide client rather than calling docker.from_env() here.
    This runs inside the 5-second snapshot loop, so building a client per call
    meant a new connection pool to /var/run/docker.sock every 5 seconds, none of
    them ever closed.
    """
    return [
        (c.get("Names") or ["?"])[0].lstrip("/")
        for c in get_client().api.containers(filters={"status": "running"})
    ]
