import subprocess


def list_ports():
    result = subprocess.run(["ss", "-tulpn"], capture_output=True, text=True)
    return result.stdout