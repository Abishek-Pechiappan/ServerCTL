from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from action.actdocker import docker_down, docker_up
from action.agents import get_latest_snapshot
from action.system_management import system_update, system_upgrade
from authentication import create_access_token, get_current_user, verify_credentials
from security.proc import run_scan

router = APIRouter()


class ContainerRequest(BaseModel):
    name: str


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(payload: LoginRequest):
    if not verify_credentials(payload.username, payload.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
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
