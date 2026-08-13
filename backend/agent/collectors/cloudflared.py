import socket
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import requests
import yaml

CONFIG_PATH = Path.home() / ".cloudflared" / "config.yml"

_TIMEOUT_SECONDS = 2

# One session for connection reuse across probes and across refreshes, instead of
# a fresh TCP (and TLS) handshake per rule per cycle.
_session = requests.Session()

# Probes are pure waiting, so run them together: a config with several rules used
# to cost timeout x rules sequentially, stalling the whole snapshot cycle it
# landed on. Bounded so a large config cannot spawn a thread per rule.
_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="tunnel-health")

# cloudflared's built-in services are answered by cloudflared itself, so there is
# nothing to connect to. Probing them always failed and reported the tunnel down.
_BUILTIN_SERVICES = ("hello_world", "hello-world", "bastion")


def read_ingress_rules():
    if not CONFIG_PATH.exists():
        return []

    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f) or {}

    rules = []
    for rule in config.get("ingress", []):
        hostname = rule.get("hostname")
        service = rule.get("service")
        if not hostname or not service:
            continue
        rules.append({"hostname": hostname, "service": service})

    return rules


def check_health(service: str) -> bool:
    if service in _BUILTIN_SERVICES or service.startswith("http_status:"):
        return True

    parsed = urlparse(service)

    if parsed.scheme in ("http", "https"):
        try:
            # Any response means something is listening and speaking HTTP; a 500
            # is still "up" for this panel's purpose. stream=True so we stop at
            # the headers rather than pulling down a whole page we discard.
            with _session.get(service, timeout=_TIMEOUT_SECONDS, stream=True):
                return True
        except requests.RequestException:
            return False

    if parsed.hostname and parsed.port:
        try:
            with socket.create_connection(
                (parsed.hostname, parsed.port), timeout=_TIMEOUT_SECONDS
            ):
                return True
        except OSError:
            return False

    return False


def get_tunnels():
    rules = read_ingress_rules()
    if not rules:
        return []

    health = _pool.map(lambda r: check_health(r["service"]), rules)
    return [
        {"hostname": rule["hostname"], "service": rule["service"], "healthy": healthy}
        for rule, healthy in zip(rules, health)
    ]
