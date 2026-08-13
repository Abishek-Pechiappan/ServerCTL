import datetime
import hmac
import os
import threading
import time

import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from password import verify_password

load_dotenv()

SECRET_KEY = os.environ["JWT_SECRET_KEY"]
ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = 60

ADMIN_USERNAME = os.environ["ADMIN_USERNAME"]
# Pre-encoded: hmac.compare_digest refuses str arguments that are not ASCII-only
# (it raises TypeError), so a login attempt with a non-ASCII username would 500
# instead of returning 401 — and would never reach record_login_failure, so it
# would not count against the lockout. Comparing bytes has no such restriction.
_ADMIN_USERNAME_BYTES = ADMIN_USERNAME.encode()
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH")
if not ADMIN_PASSWORD_HASH:
    raise RuntimeError(
        "ADMIN_PASSWORD_HASH is not set. Re-run `python setup.py` to (re)generate "
        "backend/.env with a hashed admin password."
    )

# Brute-force protection for /login: after MAX_ATTEMPTS failures from an IP
# within WINDOW_SECONDS, further attempts are locked out for LOCKOUT_SECONDS.
MAX_ATTEMPTS = 5
WINDOW_SECONDS = 300
LOCKOUT_SECONDS = 900

# Per-IP lockout is not enough on its own once the panel is reachable from the
# internet. Two ways around it:
#
#   1. A distributed attacker simply uses a new source address every 5 attempts.
#   2. Anything that can reach 127.0.0.1 on this host can set CF-Connecting-IP
#      itself, and the app cannot tell it apart from cloudflared, so a local
#      unprivileged user can mint a fresh "IP" per request.
#
# So there is a second, global control — and it *delays* rather than locks, which
# matters: a global lockout would hand any attacker a trivial way to keep the real
# admin out. The admin who knows their password still gets in on the first try,
# just a second or two later, while a distributed guesser is slowed by orders of
# magnitude. The delay is awaited, not slept, so it costs no worker thread.
GLOBAL_WINDOW_SECONDS = 300
GLOBAL_THROTTLE_TIERS = ((100, 4.0), (50, 2.0), (20, 1.0))
GLOBAL_MAX_DELAY = 4.0

_login_lock = threading.Lock()
_login_failures: dict[str, list[float]] = {}
_login_lockouts: dict[str, float] = {}
_global_failures: list[float] = []

# auto_error=False so a missing or malformed Authorization header produces our own
# 401 with a WWW-Authenticate challenge. FastAPI's default raises 403 there, which
# a client cannot distinguish from "authenticated but not allowed" — so the
# dashboard could not tell an expired session from a real failure.
security = HTTPBearer(auto_error=False)


def verify_credentials(username: str, password: str) -> bool:
    # Evaluate both checks unconditionally so timing doesn't reveal which failed.
    username_ok = hmac.compare_digest(username.encode(), _ADMIN_USERNAME_BYTES)
    password_ok = verify_password(password, ADMIN_PASSWORD_HASH)
    return username_ok and password_ok


def _prune(now: float) -> None:
    """Drop expired bookkeeping for every IP, not just the one being checked.

    Call with _login_lock held. Without this, both dicts are append-only maps
    keyed by a remote-controlled value: an attacker cycling through source
    addresses grows them without bound for the life of the process. Pruning is
    O(tracked IPs) and only runs on a login attempt, which is already rate
    limited, so the cost is irrelevant next to the scrypt verification.
    """
    for ip in [ip for ip, until in _login_lockouts.items() if now >= until]:
        del _login_lockouts[ip]
        _login_failures.pop(ip, None)
    for ip in [
        ip
        for ip, times in _login_failures.items()
        if ip not in _login_lockouts and all(now - t >= WINDOW_SECONDS for t in times)
    ]:
        del _login_failures[ip]


def _log(message: str) -> None:
    """Authentication events go to stdout, i.e. `docker compose logs`.

    An internet-exposed admin panel with no record of who tried to get in is a
    panel you cannot reason about after the fact. flush=True because stdout is a
    pipe under Docker and would otherwise sit in a buffer for a long time.
    """
    print(f"[serverctl:auth] {message}", flush=True)


def check_login_allowed(client_ip: str) -> None:
    # monotonic, not wall clock: these are durations, and a clock step (NTP, a
    # manual date change) must not cut a lockout short or extend it for hours.
    now = time.monotonic()
    with _login_lock:
        _prune(now)
        locked_until = _login_lockouts.get(client_ip)
        if locked_until is not None and now < locked_until:
            raise HTTPException(
                status_code=429,
                detail="Too many failed attempts. Try again later.",
                headers={"Retry-After": str(int(locked_until - now))},
            )


def global_throttle_delay() -> float:
    """Seconds to wait before checking a password, given recent global failures.

    Zero in normal use — you have to be well past any legitimate mistyping for
    this to engage.
    """
    now = time.monotonic()
    with _login_lock:
        _global_failures[:] = [t for t in _global_failures if now - t < GLOBAL_WINDOW_SECONDS]
        recent = len(_global_failures)
    for threshold, delay in GLOBAL_THROTTLE_TIERS:
        if recent >= threshold:
            return min(delay, GLOBAL_MAX_DELAY)
    return 0.0


def record_login_failure(client_ip: str) -> None:
    now = time.monotonic()
    with _login_lock:
        _prune(now)
        failures = [t for t in _login_failures.get(client_ip, []) if now - t < WINDOW_SECONDS]
        failures.append(now)
        _login_failures[client_ip] = failures

        _global_failures[:] = [t for t in _global_failures if now - t < GLOBAL_WINDOW_SECONDS]
        _global_failures.append(now)
        global_recent = len(_global_failures)

        locked = len(failures) >= MAX_ATTEMPTS
        if locked:
            _login_lockouts[client_ip] = now + LOCKOUT_SECONDS

    if locked:
        _log(f"LOCKOUT {client_ip} after {len(failures)} failures "
             f"— blocked for {LOCKOUT_SECONDS}s")
    else:
        _log(f"failed login from {client_ip} ({len(failures)}/{MAX_ATTEMPTS})")

    if global_recent and global_recent % 20 == 0:
        _log(f"WARNING: {global_recent} failed logins from all sources in the last "
             f"{GLOBAL_WINDOW_SECONDS}s — possible distributed brute force; "
             f"every attempt is now delayed")


def record_login_success(client_ip: str) -> None:
    with _login_lock:
        had_failures = bool(_login_failures.pop(client_ip, None))
        _login_lockouts.pop(client_ip, None)
    _log(f"successful login from {client_ip}"
         + (" (after earlier failures)" if had_failures else ""))


def create_access_token(username: str) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": username,
        "iat": now,
        "exp": now + datetime.timedelta(minutes=TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _unauthorized(detail: str) -> HTTPException:
    # WWW-Authenticate is what makes a 401 a well-formed challenge, and it is how
    # the dashboard distinguishes "session gone, go log in again" from a
    # transient error.
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized("Not authenticated")
    try:
        payload = jwt.decode(
            credentials.credentials,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            # Reject a token that omits them rather than treating "no expiry" as
            # "never expires". Only reachable with a leaked signing key, but the
            # whole point of that key leaking is that everything after it matters.
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Token expired")
    except jwt.InvalidTokenError:
        raise _unauthorized("Invalid token")

    username = payload.get("sub")
    if not isinstance(username, str) or not username:
        raise _unauthorized("Invalid token")
    return username