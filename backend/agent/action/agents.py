import threading
import time

from collectors.cloudflared import get_tunnels
from collectors.cpu import cpu
from collectors.disk import disk
from collectors.docker_collector import running as docker_running
from action.login_noti import active_sessions, login_history
from collectors.ports import list_ports
from collectors.ram import ram
from collectors.temp import temprature

REFRESH_SECONDS = 5

# Not everything is worth sampling every 5 seconds.
#
# get_tunnels() opens a real connection per cloudflared ingress rule with a 2s
# timeout, sequentially — with five rules and one of them down that is one wasted
# second per cycle, forever. login_history() forks `last`, which re-reads the
# whole of wtmp. Neither changes on a 5-second timescale.
TUNNEL_REFRESH_SECONDS = 30
HISTORY_REFRESH_SECONDS = 30

# With no client polling, refreshing is pure waste: it forks ss/who/last and
# talks to the Docker socket on a box nobody is looking at. After this long
# without a read the loop parks until the next request wakes it.
IDLE_AFTER_SECONDS = 60
_IDLE_WAIT_SECONDS = 5

_lock = threading.Lock()
_latest_snapshot = {}
_last_request = 0.0
_wake = threading.Event()

# Only the monitor thread touches these, so they need no lock.
_slow_values: dict[str, object] = {}
_slow_deadlines: dict[str, float] = {}


def _safe(collector):
    try:
        return collector()
    except Exception as e:
        return {"error": str(e)}


def _slow(key, collector, interval, now):
    """_safe(), but recomputed at most once per `interval`."""
    if now >= _slow_deadlines.get(key, 0.0):
        _slow_values[key] = _safe(collector)
        _slow_deadlines[key] = now + interval
    return _slow_values[key]


def collect_all(now=None):
    now = time.monotonic() if now is None else now
    return {
        "cpu_percent": _safe(cpu),
        "ram": _safe(ram),
        "disk": _safe(disk),
        "temperature": _safe(temprature),
        "docker_running": _safe(docker_running),
        "ports": _safe(list_ports),
        "cloudflared": _slow("cloudflared", get_tunnels, TUNNEL_REFRESH_SECONDS, now),
        "ssh_active": _safe(active_sessions),
        # In the snapshot so /api/ssh/history is a dict lookup. It used to fork
        # `last` on every request, on a 10-second dashboard timer.
        "ssh_history": _slow("ssh_history", login_history, HISTORY_REFRESH_SECONDS, now),
    }


def get_latest_snapshot():
    global _last_request
    with _lock:
        _last_request = time.monotonic()
        snapshot = _latest_snapshot
    # Safe to set unconditionally: the loop only waits on this while parked, and
    # a stale flag costs one extra collection, never a missed one.
    _wake.set()
    return snapshot


def _monitor_loop():
    global _latest_snapshot
    while True:
        started = time.monotonic()
        with _lock:
            idle_for = started - _last_request

        if idle_for > IDLE_AFTER_SECONDS:
            # Bounded rather than a bare wait(). The event is cleared only after
            # waking, so a request during the wait cannot be missed; the timeout
            # is there so that no bug in the signalling path can strand the loop
            # permanently — the worst case becomes 5 seconds of staleness, not a
            # dashboard that never updates again.
            _wake.wait(timeout=_IDLE_WAIT_SECONDS)
            _wake.clear()
            continue

        snapshot = collect_all(started)
        with _lock:
            _latest_snapshot = snapshot

        # Sleep to the deadline. `time.sleep(REFRESH_SECONDS)` made the real
        # period REFRESH_SECONDS *plus* however long collection took.
        time.sleep(max(0.0, REFRESH_SECONDS - (time.monotonic() - started)))


def start_monitor():
    global _last_request
    # Start in the active state so one snapshot is collected immediately; the loop
    # parks by itself if nothing reads it within IDLE_AFTER_SECONDS.
    _last_request = time.monotonic()
    threading.Thread(target=_monitor_loop, daemon=True).start()
