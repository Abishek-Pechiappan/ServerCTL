import subprocess


def system_update():
    result = subprocess.run(["sudo", "apt", "update"], capture_output=True, text=True)
    return result.stdout


def system_upgrade():
    result = subprocess.run(["sudo", "apt", "upgrade", "-y"], capture_output=True, text=True)
    return result.stdout
