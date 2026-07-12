import socket
from pathlib import Path
from urllib.parse import urlparse

import requests
import yaml

CONFIG_PATH = Path.home() / ".cloudflared" / "config.yml"


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
    parsed = urlparse(service)

    if parsed.scheme in ("http", "https"):
        try:
            requests.get(service, timeout=2)
            return True
        except requests.RequestException:
            return False

    if parsed.hostname and parsed.port:
        try:
            with socket.create_connection((parsed.hostname, parsed.port), timeout=2):
                return True
        except OSError:
            return False

    return False


def get_tunnels():
    return [
        {
            "hostname": rule["hostname"],
            "service": rule["service"],
            "healthy": check_health(rule["service"]),
        }
        for rule in read_ingress_rules()
    ]