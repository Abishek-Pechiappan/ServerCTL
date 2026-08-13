import re
import subprocess

PROCESS_PATTERN = re.compile(r'\(\("([^"]+)",pid=(\d+)')

# ss exits non-zero / hangs if something is wrong with the netlink socket; the
# snapshot loop must not stall behind it.
_TIMEOUT_SECONDS = 10


def _scope(address: str) -> str:
    """How reachable a listener is — the part of the address that matters.

    The raw address is not useful on its own (a reader does not care about
    127.0.0.54 vs 127.0.0.53%lo) but the distinction between loopback-only and
    reachable from the network is the single most important thing in this panel,
    so it must not be dropped.
    """
    host = address.strip("[]").split("%")[0]
    if host in ("0.0.0.0", "*", "::", ""):
        return "all"
    if host.startswith("127.") or host == "::1":
        return "local"
    return host


def list_ports():
    try:
        result = subprocess.run(
            ["ss", "-tulpn"], capture_output=True, text=True, timeout=_TIMEOUT_SECONDS
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    # ss reports one row per address family and per protocol, so a single service
    # shows up two to four times (IPv4/IPv6 x tcp/udp). Those rows were told
    # apart by their address; now that the UI keys on process and port, they have
    # to be merged here or the panel prints the same line four times over.
    merged: dict[tuple[str, str], dict] = {}
    for line in result.stdout.splitlines()[1:]:
        fields = line.split()
        if len(fields) < 5:
            continue

        address, _, port = fields[4].rpartition(":")
        process_field = fields[6] if len(fields) > 6 else ""
        match = PROCESS_PATTERN.search(process_field)
        process = f'{match.group(1)} (pid {match.group(2)})' if match else None

        entry = merged.get((process or "", port))
        scope = _scope(address)
        if entry is None:
            merged[(process or "", port)] = {"port": port, "process": process, "scope": scope}
        elif entry["scope"] != scope:
            # Bound on both loopback and a public address: report the weaker one,
            # because that is the one that carries risk.
            entry["scope"] = "all" if "all" in (entry["scope"], scope) else scope

    return sorted(merged.values(), key=lambda p: (int(p["port"]) if p["port"].isdigit() else 0))
