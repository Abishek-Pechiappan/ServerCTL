import os
import time
import datetime
import socket

SUSPICIOUS_PROCESS_PATHS = ["/tmp", "/dev/shm", "/var/tmp"]

SUSPICIOUS_PORTS = [
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
]

PROCESS_LOG_FILE = "log.txt"
NETWORK_LOG_FILE = "network_log.text"


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


def is_suspicious_process(cmdline, owner):
    return owner == "ROOT" and any(path in cmdline for path in SUSPICIOUS_PROCESS_PATHS)


def log_suspicious_process(pid, name, owner):
    with open(PROCESS_LOG_FILE, "a") as log:
        timestamp = str(datetime.datetime.now())
        log.write(f"{timestamp} PID: {pid} | {name} | {owner}\n")


def process_monitor():
    processes = []
    for pid in list_pids():
        try:
            name = read_process_name(pid)
            owner = read_process_owner(pid)
            cmdline = read_process_cmdline(pid)
        except FileNotFoundError:
            continue

        suspicious = is_suspicious_process(cmdline, owner)
        if suspicious:
            log_suspicious_process(pid, name, owner)

        processes.append({"pid": pid, "name": name, "owner": owner, "suspicious": suspicious})

    return processes


def parse_tcp_line(line):
    fields = line.split()
    ip_hex, port_hex = fields[1].split(":")
    ip = socket.inet_ntoa(bytes.fromhex(ip_hex)[::-1])  # stored little-endian in /proc/net/tcp
    port = int(port_hex, 16)
    return ip, port


def log_suspicious_connection(ip, port):
    with open(NETWORK_LOG_FILE, "a") as log:
        timestamp = str(datetime.datetime.now())
        log.write(f"{timestamp} | The IP {ip} is suspicious on port {port}\n")


def network_monitor():
    suspicious_connections = []
    with open("/proc/net/tcp") as f:
        next(f)  # header line
        for line in f:
            ip, port = parse_tcp_line(line)
            if port in SUSPICIOUS_PORTS:
                log_suspicious_connection(ip, port)
                suspicious_connections.append({"ip": ip, "port": port})
    return suspicious_connections


def run_scan():
    return {
        "processes": process_monitor(),
        "suspicious_connections": network_monitor(),
    }

