import re
import subprocess

ACTIVE_PATTERN = re.compile(
    r'^(?P<user>\S+)\s+(?P<tty>\S+)\s+(?P<date>\d{4}-\d{2}-\d{2})\s+(?P<time>\d{2}:\d{2})(?:\s+\((?P<host>[^)]*)\))?'
)

HISTORY_PATTERN = re.compile(
    r'^(?P<user>\S+)\s+(?P<tty>\S+)\s+(?P<host>\S+)\s+(?P<start>\S+)\s+'
    r'(?:-\s+(?P<end>\S+)\s+\([^)]*\)|(?P<still>still logged in))'
)


# Both commands read utmp/wtmp, which live on a bind mount. A stale or broken
# mount makes them block, and the snapshot loop would block with them.
_TIMEOUT_SECONDS = 10


def active_sessions():
    try:
        result = subprocess.run(
            ["who"], capture_output=True, text=True, timeout=_TIMEOUT_SECONDS
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    sessions = []
    for line in result.stdout.splitlines():
        match = ACTIVE_PATTERN.match(line)
        if not match:
            continue
        sessions.append({
            "user": match.group("user"),
            "tty": match.group("tty"),
            "login_time": f'{match.group("date")}T{match.group("time")}',
            "host": match.group("host"),
        })
    return sessions


def login_history(limit=50):
    try:
        result = subprocess.run(
            ["last", "--time-format", "iso", "-n", str(limit)],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    entries = []
    for line in result.stdout.splitlines():
        if not line.strip() or line.startswith("wtmp begins") or line.split()[0] == "reboot":
            continue
        match = HISTORY_PATTERN.match(line)
        if not match:
            continue
        host = match.group("host")
        entries.append({
            "user": match.group("user"),
            "tty": match.group("tty"),
            "host": None if host in ("-", "local") else host,
            "login_time": match.group("start"),
            "logout_time": match.group("end"),
            "still_logged_in": match.group("still") is not None,
        })
    return entries
