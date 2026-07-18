import datetime
import hmac
import os
import threading

import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from password import verify_password

load_dotenv()

SECRET_KEY = os.environ["JWT_SECRET_KEY"]
ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = 60

ADMIN_USERNAME = os.environ["ADMIN_USERNAME"]
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

_login_lock = threading.Lock()
_login_failures: dict[str, list[float]] = {}
_login_lockouts: dict[str, float] = {}

security = HTTPBearer()


def verify_credentials(username: str, password: str) -> bool:
    # Evaluate both checks unconditionally so timing doesn't reveal which failed.
    username_ok = hmac.compare_digest(username, ADMIN_USERNAME)
    password_ok = verify_password(password, ADMIN_PASSWORD_HASH)
    return username_ok and password_ok


def check_login_allowed(client_ip: str) -> None:
    now = datetime.datetime.now(datetime.timezone.utc).timestamp()
    with _login_lock:
        locked_until = _login_lockouts.get(client_ip)
        if locked_until is not None:
            if now < locked_until:
                raise HTTPException(
                    status_code=429,
                    detail="Too many failed attempts. Try again later.",
                    headers={"Retry-After": str(int(locked_until - now))},
                )
            del _login_lockouts[client_ip]
            _login_failures.pop(client_ip, None)


def record_login_failure(client_ip: str) -> None:
    now = datetime.datetime.now(datetime.timezone.utc).timestamp()
    with _login_lock:
        failures = [t for t in _login_failures.get(client_ip, []) if now - t < WINDOW_SECONDS]
        failures.append(now)
        _login_failures[client_ip] = failures
        if len(failures) >= MAX_ATTEMPTS:
            _login_lockouts[client_ip] = now + LOCKOUT_SECONDS


def record_login_success(client_ip: str) -> None:
    with _login_lock:
        _login_failures.pop(client_ip, None)
        _login_lockouts.pop(client_ip, None)


def create_access_token(username: str) -> str:
    expire = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    payload = {"sub": username, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload["sub"]