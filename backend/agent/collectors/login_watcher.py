import os
import threading
import time

import requests

from action.login_noti import login_history

CHECK_INTERVAL_SECONDS = 5
HISTORY_LIMIT = 200

N8N_WEBHOOK_URL = os.environ.get("N8N_LOGIN_WEBHOOK_URL")

_lock = threading.Lock()
_seen_keys = set()
_history = []


def _key(entry):
    return (entry["user"], entry["tty"], entry["login_time"])


def _notify(entry):
    if not N8N_WEBHOOK_URL:
        return
    try:
        requests.post(N8N_WEBHOOK_URL, json={"event": "ssh_login", **entry}, timeout=3)
    except requests.RequestException:
        pass


def get_history():
    with _lock:
        return list(_history)


def _watch_loop():
    try:
        initial = login_history(limit=HISTORY_LIMIT)
    except Exception:
        initial = []

    with _lock:
        for entry in initial:
            _seen_keys.add(_key(entry))
        _history.extend(initial)

    while True:
        time.sleep(CHECK_INTERVAL_SECONDS)
        try:
            recent = login_history(limit=20)
        except Exception:
            continue

        new_entries = []
        with _lock:
            for entry in recent:
                key = _key(entry)
                if key not in _seen_keys:
                    _seen_keys.add(key)
                    _history.append(entry)
                    new_entries.append(entry)

        for entry in new_entries:
            _notify(entry)


def start_login_watcher():
    threading.Thread(target=_watch_loop, daemon=True).start()
