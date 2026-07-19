"""Check everything ServerCTL needs before `docker compose up`.

Stdlib only and no venv required — this has to be runnable on a fresh box
before install.py has done anything.

    python3 preflight.py

Exit code is 1 if any check FAILs, 0 otherwise. WARNs are things that will
start fine but leave a panel widget empty or misbehaving.
"""

import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
BACKEND_ENV = ROOT / "backend" / ".env"
ROOT_ENV = ROOT / ".env"

OK, WARN, FAIL = "OK", "WARN", "FAIL"

_COLOR = {OK: "\033[32m", WARN: "\033[33m", FAIL: "\033[31m"}
_RESET = "\033[0m"
_USE_COLOR = sys.stdout.isatty()

results: list[tuple[str, str, str]] = []


def report(level: str, check: str, detail: str = "") -> None:
    results.append((level, check, detail))
    tag = f"{_COLOR[level]}{level:<4}{_RESET}" if _USE_COLOR else f"{level:<4}"
    print(f"[{tag}] {check}")
    if detail:
        for line in detail.splitlines():
            print(f"         {line}")


def read_env(path: Path) -> dict[str, str]:
    """Parse a KEY=VALUE file. Not a full dotenv parser — matches what
    docker-compose's env_file accepts, which is all this project writes."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def run(cmd: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return proc.returncode, (proc.stdout + proc.stderr).strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return 127, ""


# --------------------------------------------------------------------------
# Host / distro
# --------------------------------------------------------------------------

def check_distro() -> None:
    pm = next((p for p in ("apt-get", "pacman", "dnf", "zypper") if shutil.which(p)), None)
    name = "unknown"
    os_release = Path("/etc/os-release")
    if os_release.exists():
        match = re.search(r'^PRETTY_NAME="?([^"\n]+)', os_release.read_text(), re.M)
        if match:
            name = match.group(1)

    if pm is None:
        report(WARN, "Package manager", f"{name}: none of apt-get/pacman/dnf/zypper found.")
        return

    if pm == "apt-get":
        report(OK, "Package manager", f"{name} (apt-get)")
    else:
        # install.py shells out to apt-get, and the /system/update endpoint runs
        # `sudo apt` inside the backend container.
        report(
            WARN,
            "Package manager",
            f"{name} ({pm}) — install.py assumes apt-get and will fail here.\n"
            f"Install nodejs/npm yourself, then run install.py.\n"
            f"The /system/update and /system/upgrade endpoints are apt-only too.",
        )


# --------------------------------------------------------------------------
# Docker
# --------------------------------------------------------------------------

def check_docker() -> None:
    if not shutil.which("docker"):
        report(FAIL, "Docker installed", "Install docker, then enable it:\n"
                                         "  sudo systemctl enable --now docker")
        return

    code, out = run(["docker", "info", "--format", "{{.ServerVersion}}"])
    if code != 0:
        hint = "sudo systemctl enable --now docker"
        if "permission denied" in out.lower():
            hint = ("You are not in the 'docker' group:\n"
                    "  sudo usermod -aG docker $USER   (then log out and back in)")
        report(FAIL, "Docker daemon reachable", hint)
        return
    report(OK, "Docker daemon reachable", f"server {out}")

    code, _ = run(["docker", "compose", "version"])
    if code != 0:
        report(FAIL, "Compose plugin", "Arch: sudo pacman -S docker-compose\n"
                                       "Debian: sudo apt install docker-compose-plugin")
    else:
        report(OK, "Compose plugin")

    # The backend bind-mounts the socket to manage other containers.
    if not Path("/var/run/docker.sock").exists():
        report(FAIL, "docker.sock present", "/var/run/docker.sock is missing; is the daemon running?")
    else:
        report(OK, "docker.sock present")


# --------------------------------------------------------------------------
# Credentials
# --------------------------------------------------------------------------

def check_credentials() -> None:
    if not BACKEND_ENV.exists():
        report(FAIL, "backend/.env exists", "Run:  python3 setup.py")
        return

    env = read_env(BACKEND_ENV)

    if "ADMIN_PASSWORD" in env and "ADMIN_PASSWORD_HASH" not in env:
        # authentication.py raises at import if the hash is absent, so the
        # container crash-loops rather than starting with a plaintext password.
        report(FAIL, "Admin password hashed",
               "backend/.env has ADMIN_PASSWORD, but the backend requires\n"
               "ADMIN_PASSWORD_HASH and will refuse to start. Run:  python3 setup.py")
        return

    missing = [k for k in ("ADMIN_USERNAME", "ADMIN_PASSWORD_HASH", "JWT_SECRET_KEY")
               if not env.get(k)]
    if missing:
        report(FAIL, "Credentials set", f"Missing from backend/.env: {', '.join(missing)}\n"
                                        f"Run:  python3 setup.py")
        return

    # Must match the encoding in backend/password.py, which uses ':' rather than
    # '$' because docker-compose interpolates '$' out of env files.
    parts = env["ADMIN_PASSWORD_HASH"].split(":")
    if len(parts) != 6 or parts[0] != "scrypt":
        detail = "Hash is not in the expected scrypt:N:r:p:salt:hash form."
        if "$" in env["ADMIN_PASSWORD_HASH"]:
            detail += ("\nIt still uses the old '$' separator, which compose mangles —\n"
                       "every login returns 401. Re-run:  python3 setup.py")
        report(FAIL, "Password hash format", detail)
    else:
        report(OK, "Password hash format", "scrypt, ':'-separated")

    if len(env["JWT_SECRET_KEY"]) < 32:
        report(WARN, "JWT secret strength",
               "JWT_SECRET_KEY is shorter than setup.py generates (64 hex chars).")
    else:
        report(OK, "JWT secret strength")


# --------------------------------------------------------------------------
# Networking / nginx
# --------------------------------------------------------------------------

def port_busy(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
            return False
        except OSError:
            return True


def check_ports() -> None:
    running = set()
    code, out = run(["docker", "ps", "--filter", "name=serverctl", "--format", "{{.Names}}"])
    if code == 0:
        running = {line.strip() for line in out.splitlines() if line.strip()}

    for port, service, container in ((8001, "backend", "serverctl-backend"),
                                     (3000, "frontend", "serverctl-frontend")):
        if not port_busy(port):
            report(OK, f"Port {port} free ({service})")
        elif container in running:
            report(OK, f"Port {port} in use ({service})", f"held by {container} — already running")
        else:
            report(FAIL, f"Port {port} free ({service})",
                   f"Something else is on {port}. Find it with:  sudo ss -tlnp | grep {port}")


def check_nginx() -> None:
    conf = ROOT / "nginx" / "serverctl.conf"
    api_url = read_env(ROOT_ENV).get("NEXT_PUBLIC_API_URL", "http://localhost:8001")

    if not shutil.which("nginx"):
        report(WARN, "nginx installed",
               "Optional, but recommended: it puts the UI and API on one origin,\n"
               "which removes CORS entirely and is required for remote access.\n"
               "  Arch:   sudo pacman -S nginx\n"
               "  Debian: sudo apt install nginx\n"
               f"Then install {conf.relative_to(ROOT)} — see Readme.md.")
        if api_url == "/api":
            report(FAIL, "API URL matches setup",
                   "NEXT_PUBLIC_API_URL=/api needs a proxy, but nginx is not installed.\n"
                   "Install nginx, or set NEXT_PUBLIC_API_URL=http://localhost:8001.")
        return

    installed = any(
        (Path(d) / "serverctl.conf").exists()
        for d in ("/etc/nginx/conf.d", "/etc/nginx/sites-enabled")
    )
    if not installed:
        report(WARN, "nginx config installed", "See Readme.md for the cp/ln -s command.")
    else:
        code, out = run(["nginx", "-t"])
        if code == 0:
            report(OK, "nginx config valid")
        elif code == 127 or "permission denied" in out.lower():
            report(WARN, "nginx config valid", "Re-run as root to test:  sudo nginx -t")
        else:
            report(FAIL, "nginx config valid", out)

    if installed and api_url != "/api":
        report(WARN, "API URL matches setup",
               f"nginx is configured but NEXT_PUBLIC_API_URL={api_url}.\n"
               f"Behind the proxy this should be /api, or the browser bypasses\n"
               f"nginx and you are back to needing CORS. Set it in .env, then:\n"
               f"  docker compose up -d --build")
    elif installed:
        report(OK, "API URL matches setup", "/api (single origin, no CORS)")


# --------------------------------------------------------------------------
# Optional data sources — these start fine but leave widgets empty
# --------------------------------------------------------------------------

def check_login_history() -> None:
    # systemd 258 disabled utmp by default; Ubuntu 25.10+ and current Arch no
    # longer maintain these files, so `who`/`last` return nothing.
    utmp, wtmp = Path("/run/utmp"), Path("/var/log/wtmp")
    missing = [str(p) for p in (utmp, wtmp) if not p.exists()]
    if not missing:
        report(OK, "Login history (utmp/wtmp)")
        return
    report(WARN, "Login history (utmp/wtmp)",
           f"Missing: {', '.join(missing)}\n"
           f"Your distro dropped utmp, so the SSH sessions panel will be empty.\n"
           f"Also: docker creates a DIRECTORY at a missing bind-mount source, so\n"
           f"remove those volume lines from docker-compose.yml to avoid clutter.")


def check_temperature() -> None:
    # collectors/temp.py matches the label 'Package id 0', which only the Intel
    # coretemp driver emits. AMD's k10temp uses 'Tctl'.
    labels = [p.read_text().strip()
              for p in Path("/sys/class/hwmon").glob("hwmon*/temp*_label")
              if p.is_file()]
    if any(label == "Package id 0" for label in labels):
        report(OK, "CPU temperature sensor", "coretemp 'Package id 0' found")
    else:
        found = ", ".join(sorted(set(labels))[:4]) or "none"
        report(WARN, "CPU temperature sensor",
               f"No 'Package id 0' label (found: {found}).\n"
               f"collectors/temp.py returns None; the temperature tile stays blank.")


def check_cloudflared() -> None:
    path = Path.home() / ".cloudflared"
    if path.is_dir():
        tunnels = list(path.glob("*.json"))
        report(OK, "cloudflared config", f"{len(tunnels)} tunnel credential file(s)")
    else:
        report(WARN, "cloudflared config",
               f"{path} does not exist. docker-compose mounts it, so docker will\n"
               f"create it as an empty root-owned directory and the tunnels panel\n"
               f"will be empty. Harmless if you are not using cloudflared.")


CHECKS = (
    check_distro,
    check_docker,
    check_credentials,
    check_ports,
    check_nginx,
    check_login_history,
    check_temperature,
    check_cloudflared,
)


def main() -> int:
    print("ServerCTL preflight\n")
    for check in CHECKS:
        try:
            check()
        except Exception as exc:  # a broken check must not mask the others
            report(WARN, f"{check.__name__} (check itself errored)", repr(exc))

    fails = sum(1 for level, _, _ in results if level == FAIL)
    warns = sum(1 for level, _, _ in results if level == WARN)

    print()
    if fails:
        print(f"{fails} blocking problem(s), {warns} warning(s). Fix the FAILs above first.")
        return 1
    if warns:
        print(f"No blocking problems, {warns} warning(s) — safe to start:")
    else:
        print("All checks passed:")
    print("  docker compose up -d --build")
    return 0


if __name__ == "__main__":
    sys.exit(main())
