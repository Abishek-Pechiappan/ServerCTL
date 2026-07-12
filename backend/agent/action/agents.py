import threading
import time

from collectors.cloudflared import get_tunnels
from collectors.cpu import cpu
from collectors.disk import disk
from collectors.docker_collector import running as docker_running
from collectors.ports import list_ports
from collectors.ram import ram
from collectors.temp import temprature

REFRESH_SECONDS = 5

_lock = threading.Lock()
_latest_snapshot = {}


def _safe(collector):
    try:
        return collector()
    except Exception as e:
        return {"error": str(e)}


def collect_all():
    return {
        "cpu_percent": _safe(cpu),
        "ram": _safe(ram),
        "disk": _safe(disk),
        "temperature": _safe(temprature),
        "docker_running": _safe(docker_running),
        "ports": _safe(list_ports),
        "cloudflared": _safe(get_tunnels),
    }


def get_latest_snapshot():
    with _lock:
        return _latest_snapshot


def _monitor_loop():
    global _latest_snapshot
    while True:
        snapshot = collect_all()
        with _lock:
            _latest_snapshot = snapshot
        time.sleep(REFRESH_SECONDS)


def start_monitor():
    threading.Thread(target=_monitor_loop, daemon=True).start()