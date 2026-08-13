import os
import socket

SUSPICIOUS_PROCESS_PATHS = ("/tmp", "/dev/shm", "/var/tmp")

SUSPICIOUS_PORTS = frozenset(
    {
        21,     # FTP (Unencrypted data exfiltration)
        22,     # SSH (Brute-force entry point)
        23,     # Telnet (Botnet command & control)
        511,    # T0rn Rootkit
        666,    # Satanz Backdoor / Ripper
        1008,   # Li0n Worm
        1337,   # Common Reverse Shell port
        1524,   # Trinoo DDoS tool / Ingres backdoor
        2222,   # Alternate SSH (often used to hide SSH or by malware)
        3040,   # Ramen Worm
        4444,   # Metasploit default listener
        6667,   # IRC-based Botnet C2
        31337,  # Elite Backdoors
        33567,  # Lion Worm rootshell
        33568,  # Lion Worm trojaned SSH
    }
)

# /proc/net/tcp{,6} state column. Only established sockets are interesting here:
# a LISTEN socket on 22 is just sshd, and reporting it as a "suspicious
# connection" made the panel cry wolf on every machine that runs SSH.
_TCP_ESTABLISHED = "01"


def list_pids():
    return [pid for pid in os.listdir("/proc") if pid.isdigit()]


def read_process_name(pid):
    with open(f"/proc/{pid}/comm") as f:
        return f.read().rstrip("\n")


def read_process_owner(pid):
    with open(f"/proc/{pid}/status") as f:
        for line in f:
            if line.startswith("Uid"):
                uid = line.split()[1]
                return "ROOT" if uid == "0" else "USER"
    return "USER"


def read_process_cmdline(pid):
    with open(f"/proc/{pid}/cmdline") as f:
        return f.read().replace("\x00", " ").rstrip("\n")


def read_process_exe(pid):
    """Resolved path of the running binary, or "" if it cannot be read.

    This, not the command line, is what "running from /tmp" means. Matching the
    cmdline flagged any root process that merely *mentions* a temp path —
    `tar -xf /tmp/x`, `grep foo /var/tmp/log` — while missing the actual case of
    a binary that was copied to /tmp and renamed.
    """
    try:
        return os.readlink(f"/proc/{pid}/exe")
    except OSError:
        return ""


def is_suspicious_process(exe, cmdline, owner):
    if owner != "ROOT":
        return False
    # exe is authoritative when readable (kernel threads and vanished processes
    # have none); fall back to the cmdline's argv[0] only, not the whole line.
    target = exe or cmdline.split(" ")[0]
    return any(target.startswith(path + "/") for path in SUSPICIOUS_PROCESS_PATHS)


def process_monitor():
    """Root processes running from a world-writable directory.

    Returns only the hits. It used to return every process on the box — several
    hundred entries — of which the caller displays the handful that are
    suspicious, so the rest was payload the dashboard downloaded and discarded.

    Reads are ordered cheapest-and-most-selective first. Every check here requires
    owner == ROOT, so reading status decides most processes on its own; name and
    cmdline are only needed to *describe* a hit, so they are read after one is
    confirmed. Doing all four reads up front cost ~4 file opens per PID across
    several hundred PIDs to describe, typically, nothing.
    """
    suspicious = []
    scanned = 0
    for pid in list_pids():
        try:
            owner = read_process_owner(pid)
            scanned += 1
            if owner != "ROOT":
                continue

            exe = read_process_exe(pid)
            cmdline = read_process_cmdline(pid)
            if not is_suspicious_process(exe, cmdline, owner):
                continue

            suspicious.append(
                {
                    "pid": pid,
                    "name": read_process_name(pid),
                    "owner": owner,
                    "exe": exe,
                    "cmdline": cmdline,
                    "suspicious": True,
                }
            )
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            # Processes exit while we walk /proc; that is normal, not an error.
            continue

    return scanned, suspicious


def _parse_address(raw, family):
    """Decode a /proc/net address ("<hex-addr>:<hex-port>") to (ip, port)."""
    ip_hex, _, port_hex = raw.rpartition(":")
    if family == socket.AF_INET:
        packed = bytes.fromhex(ip_hex)[::-1]
    else:
        # 4 little-endian 32-bit words, so reverse within each word, not across
        # the whole address.
        packed = b"".join(
            bytes.fromhex(ip_hex[i : i + 8])[::-1] for i in range(0, 32, 8)
        )
    return socket.inet_ntop(family, packed), int(port_hex, 16)


def _scan_tcp_table(path, family):
    hits = []
    try:
        with open(path) as f:
            next(f, None)  # header line
            for line in f:
                fields = line.split()
                if len(fields) < 4 or fields[3] != _TCP_ESTABLISHED:
                    continue
                try:
                    local_ip, local_port = _parse_address(fields[1], family)
                    remote_ip, remote_port = _parse_address(fields[2], family)
                except ValueError:
                    continue
                # Check both ends: an inbound connection to a backdoor port and an
                # outbound reverse shell to one are both worth reporting, and the
                # old code only looked at the local side.
                matched = {local_port, remote_port} & SUSPICIOUS_PORTS
                if matched:
                    hits.append(
                        {
                            "ip": remote_ip,
                            "port": sorted(matched)[0],
                            "local": f"{local_ip}:{local_port}",
                            "remote": f"{remote_ip}:{remote_port}",
                        }
                    )
    except FileNotFoundError:
        pass
    return hits


def network_monitor():
    # IPv6 was invisible before: only /proc/net/tcp was read, so a backdoor
    # listening or dialling out over v6 was never seen.
    return _scan_tcp_table("/proc/net/tcp", socket.AF_INET) + _scan_tcp_table(
        "/proc/net/tcp6", socket.AF_INET6
    )


def run_scan():
    # No file logging. This appended to ./log.txt and ./network_log.text next to
    # the code on every scan — inside the container, so it grew without bound,
    # was never rotated, and vanished on the next `docker compose up`. The
    # findings are in the response, which is where the caller reads them.
    scanned, suspicious = process_monitor()
    return {
        "processes_scanned": scanned,
        "suspicious_processes": suspicious,
        "suspicious_connections": network_monitor(),
    }
