import re
import subprocess

PROCESS_PATTERN = re.compile(r'\(\("([^"]+)",pid=(\d+)')


def list_ports():
    result = subprocess.run(["ss", "-tulpn"], capture_output=True, text=True)

    ports = []
    for line in result.stdout.splitlines()[1:]:
        fields = line.split()
        if len(fields) < 5:
            continue

        address, _, port = fields[4].rpartition(":")
        process_field = fields[6] if len(fields) > 6 else ""
        match = PROCESS_PATTERN.search(process_field)
        process = f'{match.group(1)} (pid {match.group(2)})' if match else None

        ports.append({"address": address, "port": port, "process": process})

    return ports