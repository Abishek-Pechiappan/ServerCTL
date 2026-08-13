import re

import docker
from docker.errors import DockerException, NotFound

_client = None


def get_client():
    """One shared client for the whole process.

    Every caller must go through this. Building a client per call (which
    collectors/docker_collector.py used to do, on a 5-second loop) opens a fresh
    connection pool to the socket each time and never closes it.
    """
    global _client
    if _client is None:
        _client = docker.from_env()
    return _client


def list_containers():
    """All containers (running + stopped) with a UI-friendly status/image.

    Deliberately the low-level list endpoint. The high-level
    `containers.list(all=True)` inspects every container individually — 1 + N
    requests — and reading `container.image` on top of that lazily fetches each
    image, for another N. `GET /containers/json` already carries the name, state
    and image tag, so one request covers it. This runs on a 5-second poll, so
    the difference is 2N wasted socket round trips every 5 seconds.
    """
    result = []
    for c in get_client().api.containers(all=True):
        names = c.get("Names") or []
        result.append(
            {
                "name": names[0].lstrip("/") if names else c.get("Id", "")[:12],
                # "running", "exited", "created", "paused" — the same vocabulary
                # the inspect-based .status property returned.
                "status": c.get("State") or "unknown",
                "image": c.get("Image") or c.get("ImageID", "")[:19],
            }
        )
    result.sort(key=lambda c: (c["status"] != "running", c["name"].lower()))
    return result


# Re-checked here, not only in route.py's request model, because this is the sink:
# the name is interpolated into a Docker API path and the socket is
# root-equivalent, so it should be impossible to reach the daemon with a traversal
# regardless of which caller supplied the name.
_VALID_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")


def _get_container(name: str):
    if not _VALID_NAME.match(name):
        raise RuntimeError(f"invalid container name: {name!r}")
    try:
        return get_client().containers.get(name)
    except NotFound:
        raise RuntimeError(f"no such container: {name}")
    except DockerException as e:
        raise RuntimeError(f"docker error: {e}")


# How long a container gets to shut down on its own before it is killed. Docker's
# own default is 10s; 15 gives a database or a queue consumer a little more room to
# flush without making a stuck container hold the request open for long.
STOP_TIMEOUT_SECONDS = 15


# Both of these used to scan the full container list and `return` silently when
# nothing matched, so the route still answered {"status": "ok", "...killed"} for
# a container that does not exist or was already in the target state. Failing
# loudly is the point: the caller is a dashboard button, and a success message
# for an action that did nothing is worse than an error.
def docker_down(name: str):
    container = _get_container(name)
    if container.status != "running":
        raise RuntimeError(f"{name} is not running (status: {container.status})")
    # stop(), not kill(). kill() sent SIGKILL immediately, giving the process no
    # chance to flush or close anything — a good way to corrupt a database being
    # managed from this dashboard. stop() sends SIGTERM, waits, and only then
    # escalates to SIGKILL, so a well-behaved container exits cleanly and a wedged
    # one still dies.
    container.stop(timeout=STOP_TIMEOUT_SECONDS)


def docker_up(name: str):
    container = _get_container(name)
    if container.status == "running":
        raise RuntimeError(f"{name} is already running")
    container.start()
