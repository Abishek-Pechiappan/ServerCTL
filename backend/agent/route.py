from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from action.actdocker import docker_down, docker_up, list_containers
from action.agents import get_latest_snapshot
from action.login_noti import login_history
from action.system_management import system_update, system_upgrade
from authentication import (
    check_login_allowed,
    create_access_token,
    get_current_user,
    record_login_failure,
    record_login_success,
    verify_credentials,
)
from security.proc import run_scan

router = APIRouter()


class ContainerRequest(BaseModel):
    name: str


class LoginRequest(BaseModel):
    username: str
    password: str


def _client_ip(request: Request) -> str:
    # Behind the Cloudflare tunnel the socket peer is always cloudflared on
    # localhost, so the visitor's real IP arrives in CF-Connecting-IP. We bind
    # only to 127.0.0.1 (cloudflared is the sole client), so this header is
    # trustworthy here. Do NOT trust it if you ever expose the port directly.
    cf = request.headers.get("cf-connecting-ip")
    if cf:
        return cf.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/login")
def login(payload: LoginRequest, request: Request):
    client_ip = _client_ip(request)
    check_login_allowed(client_ip)
    if not verify_credentials(payload.username, payload.password):
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
    return {"status": "ok", "message": f"{payload.name} killed"}


@router.post("/docker/up")
def docker_up_route(payload: ContainerRequest, user: str = Depends(get_current_user)):
    try:
        docker_up(payload.name)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok", "message": f"{payload.name} started"}


@router.get("/docker/containers")
def docker_containers_route(user: str = Depends(get_current_user)):
    return list_containers()


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
    return login_history()
