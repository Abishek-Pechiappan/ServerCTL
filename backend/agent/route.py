import asyncio
import ipaddress

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from action.actdocker import docker_down, docker_up, list_containers
from action.agents import get_latest_snapshot
from action.system_management import system_update, system_upgrade
from authentication import (
    check_login_allowed,
    create_access_token,
    get_current_user,
    global_throttle_delay,
    record_login_failure,
    record_login_success,
    verify_credentials,
)
from security.proc import run_scan

router = APIRouter()


# Length caps, not just types. Both fields land in unbounded server-side work —
# the password in scrypt, the name in a Docker lookup — and /login is reachable
# before any authentication, so the request body is the one thing an anonymous
# caller fully controls. nginx also caps the body at 64k, but nginx is optional.
class ContainerRequest(BaseModel):
    # Docker's own naming rule, enforced because this is the only user-supplied
    # string in the whole API that reaches a privileged sink. docker-py
    # interpolates it into the path /containers/{name}/json and encodes `?`, `&`
    # and `;` — but *not* `/` or `.`, so a name like "../../../images/json"
    # arrives at the daemon with the traversal intact and the daemon's router
    # decides what it addresses. Nothing an authenticated admin could not already
    # do through the socket directly, so this is hygiene rather than a boundary —
    # but it stops the request from meaning something other than it says, and it
    # becomes load-bearing the moment a read-only role exists.
    name: str = Field(
        min_length=1, max_length=255, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$"
    )


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=1, max_length=1024)


def _client_ip(request: Request) -> str:
    # Behind the Cloudflare tunnel the socket peer is always cloudflared on
    # localhost, so the visitor's real IP arrives in CF-Connecting-IP. We bind
    # only to 127.0.0.1 (cloudflared is the sole client), so this header is
    # trustworthy here. Do NOT trust it if you ever expose the port directly.
    #
    # CF-Connecting-IP is checked first because Cloudflare always overwrites it,
    # whereas X-Forwarded-For is *appended* to by proxies — a client that sends
    # its own X-Forwarded-For puts an attacker-chosen value in first position.
    # nginx/serverctl.conf therefore sets X-Forwarded-For to $remote_addr rather
    # than $proxy_add_x_forwarded_for, so the value here is the real peer.
    for header in ("cf-connecting-ip", "x-forwarded-for"):
        value = request.headers.get(header)
        if not value:
            continue
        candidate = value.split(",")[0].strip()
        try:
            # Parse rather than trust: the lockout tables are keyed by this
            # string, so an unvalidated header lets a caller choose arbitrary
            # (and arbitrarily long) keys. Normalising also stops "1.2.3.4" and
            # "::ffff:1.2.3.4" counting as two separate attackers.
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            continue
    return request.client.host if request.client else "unknown"


# async, unlike the other routes, for two specific reasons:
#
#   * the global throttle is `await`ed, so slowing a distributed brute force costs
#     an idle coroutine rather than one of the threadpool's ~40 workers — otherwise
#     the defence would itself become the denial of service;
#   * scrypt is explicitly pushed to a worker thread, because at 16 MiB and ~50 ms
#     a call it would stall the event loop for every other request if run inline.
@router.post("/login")
async def login(payload: LoginRequest, request: Request):
    client_ip = _client_ip(request)
    check_login_allowed(client_ip)

    delay = global_throttle_delay()
    if delay:
        await asyncio.sleep(delay)

    ok = await run_in_threadpool(verify_credentials, payload.username, payload.password)
    if not ok:
        record_login_failure(client_ip)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    record_login_success(client_ip)
    token = create_access_token(payload.username)
    return {"access_token": token, "token_type": "bearer"}


@router.post("/docker/down")
def docker_down_route(payload: ContainerRequest, user: str = Depends(get_current_user)):
    try:
        docker_down(payload.name)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok", "message": f"{payload.name} stopped"}


@router.post("/docker/up")
def docker_up_route(payload: ContainerRequest, user: str = Depends(get_current_user)):
    try:
        docker_up(payload.name)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok", "message": f"{payload.name} started"}


@router.get("/docker/containers")
def docker_containers_route(user: str = Depends(get_current_user)):
    try:
        return list_containers()
    except Exception as e:
        # Unreachable socket is a configuration problem, not a server fault: this
        # used to escape as a 500 with a traceback whenever /var/run/docker.sock
        # was not mounted — the case the entrypoint explicitly warns about.
        raise HTTPException(status_code=503, detail=f"Docker unavailable: {e}")


@router.post("/system/update")
def system_update_route(user: str = Depends(get_current_user)):
    try:
        output = system_update()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok", "output": output}


@router.post("/system/upgrade")
def system_upgrade_route(user: str = Depends(get_current_user)):
    try:
        output = system_upgrade()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok", "output": output}


@router.get("/system/monitor")
def system_monitor_route(user: str = Depends(get_current_user)):
    return get_latest_snapshot()


@router.get("/security/scan")
def security_scan_route(user: str = Depends(get_current_user)):
    return run_scan()


@router.get("/network/ports")
def network_ports_route(user: str = Depends(get_current_user)):
    return get_latest_snapshot().get("ports", [])


@router.get("/cloudflared/tunnels")
def cloudflared_tunnels_route(user: str = Depends(get_current_user)):
    return get_latest_snapshot().get("cloudflared", [])


@router.get("/ssh/active")
def ssh_active_route(user: str = Depends(get_current_user)):
    return get_latest_snapshot().get("ssh_active", [])


@router.get("/ssh/history")
def ssh_history_route(user: str = Depends(get_current_user)):
    # Served from the cached snapshot like every other read. Calling
    # login_history() here forked `last` once per request.
    return get_latest_snapshot().get("ssh_history", [])
