"""Run ServerCTL against entirely synthetic data, for screenshots.

Every collector is replaced before the app starts, so no real host information —
no real ports, processes, container names, users, IPs or tunnel hostnames — can
reach the page. Addresses use the IANA documentation ranges (192.0.2.0/24,
198.51.100.0/24, 203.0.113.0/24) and example.com, which are reserved for exactly
this purpose and cannot belong to anyone.
"""

import math
import os
import sys
import time
from pathlib import Path

# Derived from this file's location (docs/screenshots/), never hardcoded — an
# absolute path would bake whoever generated the screenshots into the repo.
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from password import hash_password  # noqa: E402

DEMO_USER = "demo"
DEMO_PASSWORD = "demo-password"

os.environ.update(
    {
        "ADMIN_USERNAME": DEMO_USER,
        "ADMIN_PASSWORD_HASH": hash_password(DEMO_PASSWORD),
        "JWT_SECRET_KEY": "0" * 64,
        "STATIC_DIR": str(ROOT / "frontend" / "serverctl" / "out"),
        "SERVERCTL_PORT": "8099",
    }
)

sys.path.insert(0, str(ROOT / "backend" / "agent"))

import action.agents as agents  # noqa: E402
import route  # noqa: E402

_start = time.time()


def _wave(period, low, high, phase=0.0):
    """A smooth value in [low, high] so the charts show movement, not a flat line."""
    t = time.time() - _start
    frac = (math.sin(2 * math.pi * (t / period) + phase) + 1) / 2
    return low + (high - low) * frac


CONTAINERS = [
    {"name": "demo-web", "status": "running", "image": "nginx:1.27-alpine"},
    {"name": "demo-api", "status": "running", "image": "demo/api:2.4.1"},
    {"name": "demo-postgres", "status": "running", "image": "postgres:16-alpine"},
    {"name": "demo-redis", "status": "running", "image": "redis:7-alpine"},
    {"name": "demo-worker", "status": "running", "image": "demo/worker:2.4.1"},
    {"name": "demo-backup", "status": "exited", "image": "demo/backup:1.0.9"},
    {"name": "demo-staging", "status": "exited", "image": "demo/api:2.3.0"},
]

PORTS = [
    {"port": "22", "process": "sshd (pid 812)", "scope": "all"},
    {"port": "80", "process": "nginx (pid 1204)", "scope": "all"},
    {"port": "443", "process": "nginx (pid 1204)", "scope": "all"},
    {"port": "3000", "process": "python (pid 2201)", "scope": "local"},
    {"port": "5432", "process": "postgres (pid 1580)", "scope": "local"},
    {"port": "6379", "process": "redis-server (pid 1633)", "scope": "local"},
    {"port": "8080", "process": "demo-api (pid 1902)", "scope": "local"},
    {"port": "9090", "process": "node_exporter (pid 990)", "scope": "192.0.2.11"},
]

TUNNELS = [
    {"hostname": "panel.example.com", "service": "http://127.0.0.1:3000", "healthy": True},
    {"hostname": "app.example.com", "service": "http://127.0.0.1:8080", "healthy": True},
    {"hostname": "files.example.com", "service": "http://127.0.0.1:8200", "healthy": False},
]

SSH_ACTIVE = [
    {"user": "demo", "tty": "pts/0", "login_time": "2026-08-13T09:42", "host": "192.0.2.44"},
    {"user": "deploy", "tty": "pts/1", "login_time": "2026-08-13T10:15", "host": "198.51.100.7"},
]

SSH_HISTORY = [
    {"user": "demo", "tty": "pts/0", "host": "192.0.2.44",
     "login_time": "2026-08-13T09:42:11", "logout_time": None, "still_logged_in": True},
    {"user": "deploy", "tty": "pts/1", "host": "198.51.100.7",
     "login_time": "2026-08-13T10:15:03", "logout_time": None, "still_logged_in": True},
    {"user": "deploy", "tty": "pts/2", "host": "198.51.100.7",
     "login_time": "2026-08-12T18:03:55", "logout_time": "2026-08-12T19:47:12", "still_logged_in": False},
    {"user": "demo", "tty": "pts/0", "host": "203.0.113.19",
     "login_time": "2026-08-12T08:21:40", "logout_time": "2026-08-12T12:09:02", "still_logged_in": False},
    {"user": "backup", "tty": "pts/3", "host": None,
     "login_time": "2026-08-11T02:00:04", "logout_time": "2026-08-11T02:04:31", "still_logged_in": False},
]

SCAN = {
    "processes_scanned": 214,
    "suspicious_processes": [],
    "suspicious_connections": [
        {"ip": "203.0.113.19", "port": 22,
         "local": "192.0.2.11:22", "remote": "203.0.113.19:51884"},
    ],
}


def fake_snapshot(now=None):
    used = round(_wave(47, 9.2, 13.6), 2)
    return {
        "cpu_percent": round(_wave(23, 8.0, 46.0), 1),
        "ram": {"total_gb": 32.0, "used_gb": used, "cached_gb": 6.4,
                "percent": round(used / 32.0 * 100, 1)},
        "disk": {"total_gb": 931.5, "used_gb": 412.8, "percent": 44.3},
        "temperature": round(_wave(31, 38.0, 57.0, phase=1.1), 1),
        "docker_running": [c["name"] for c in CONTAINERS if c["status"] == "running"],
        "ports": PORTS,
        "cloudflared": TUNNELS,
        "ssh_active": SSH_ACTIVE,
        "ssh_history": SSH_HISTORY,
    }


# Replace the collectors *before* anything starts them. agents._monitor_loop looks
# collect_all up as a module global on each pass, and route.py imported these two
# by name, so both have to be patched where they are used.
agents.collect_all = fake_snapshot
route.list_containers = lambda: CONTAINERS
route.run_scan = lambda: SCAN

import main  # noqa: E402

if __name__ == "__main__":
    import uvicorn

    print(f"demo credentials: {DEMO_USER} / {DEMO_PASSWORD}", flush=True)
    uvicorn.run(main.app, host="127.0.0.1", port=8099,
                server_header=False, log_level="warning")
