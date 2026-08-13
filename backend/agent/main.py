import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from action.agents import start_monitor
from route import router

# In production the interactive docs and OpenAPI schema are an unauthenticated
# map of the whole API for any bot/crawler — keep them off unless DEBUG is set.
DEBUG = os.environ.get("DEBUG", "").lower() in ("1", "true", "yes")

# The dashboard's static export, built by the frontend stage of the Dockerfile
# and copied to /app/static. Absent during local backend-only development, in
# which case the API still serves fine and only the UI is missing.
STATIC_DIR = Path(os.environ.get("STATIC_DIR", Path(__file__).parent.parent / "static"))

# CORS only applies when the dashboard is served from somewhere other than this
# process — the default single-container setup is same-origin, so no preflight
# ever happens and this list is unused. Set ALLOWED_ORIGINS (comma-separated)
# only if you split the frontend back onto its own host.
ALLOWED_ORIGINS = [
    o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()
]


# The API returns only JSON and should never be allowed to pull anything in, so it
# keeps the strictest possible policy.
_API_CSP = "default-src 'none'; frame-ancestors 'none'"

# The dashboard needs to load its own bundle, so it gets a policy scoped to
# same-origin assets. Applying the API's `default-src 'none'` to the HTML would
# block the page's own scripts and styles and render a blank screen.
_DASHBOARD_CSP = (
    "default-src 'self'; "
    # Next inlines a small hydration bootstrap and Tailwind injects styles at
    # runtime, neither of which can carry a nonce in a static export — so
    # 'unsafe-inline' is required for the page to render.
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "base-uri 'none'; "
    "form-action 'none'; "
    "frame-ancestors 'none'"
)

# Swagger UI and ReDoc pull their own JS/CSS from cdn.jsdelivr.net, so under the
# dashboard policy /docs rendered as a blank page — the DEBUG flag advertised
# something that could not work. These paths only exist when DEBUG is set.
_DOCS_PATHS = frozenset({"/docs", "/redoc", "/docs/oauth2-redirect"})
_DOCS_CSP = (
    "default-src 'none'; "
    "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "font-src https://cdn.jsdelivr.net; "
    "connect-src 'self'; "
    "base-uri 'none'; "
    "frame-ancestors 'none'"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_monitor()
    yield


app = FastAPI(
    title="ServerCTL",
    lifespan=lifespan,
    docs_url="/docs" if DEBUG else None,
    redoc_url="/redoc" if DEBUG else None,
    openapi_url="/openapi.json" if DEBUG else None,
)


# Every endpoint takes a small JSON object; nothing here legitimately posts more.
# The cap lives in the app because nginx/serverctl.conf is optional — without it
# uvicorn reads the whole body into memory before Pydantic gets a chance to reject
# it, and /login is reachable with no authentication at all.
MAX_BODY_BYTES = 64 * 1024


# Defined before security_headers so that one stays the outermost middleware and
# its headers land on these early rejections too.
@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    length = request.headers.get("content-length")
    if length is not None:
        try:
            too_big = int(length) > MAX_BODY_BYTES
        except ValueError:
            return JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)
        if too_big:
            return JSONResponse({"detail": "Request body too large"}, status_code=413)
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    response.headers["Server"] = "ServerCTL"
    # Nothing here uses these APIs; saying so costs one header.
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"

    # nginx sets these too, but it is optional, so the app cannot depend on it —
    # and behind a Cloudflare tunnel there is a shared cache in the path by
    # definition. Hashed asset filenames are safe forever; the dashboard shell and
    # every API response must not be stored anywhere.
    if request.url.path.startswith("/_next/static/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    else:
        response.headers["Cache-Control"] = "no-store"

    # The API returns only JSON and should never be allowed to pull anything in,
    # so it keeps the strictest possible policy. The dashboard needs to load its
    # own bundle, so it gets a policy scoped to same-origin assets. Applying the
    # API's `default-src 'none'` to the HTML would block the page's own scripts
    # and styles and render a blank screen.
    if request.url.path in _DOCS_PATHS:
        response.headers["Content-Security-Policy"] = _DOCS_CSP
    elif request.url.path.startswith("/api"):
        response.headers["Content-Security-Policy"] = _API_CSP
    else:
        response.headers["Content-Security-Policy"] = _DASHBOARD_CSP
    return response


if ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

# Mounted under /api so the endpoints cannot collide with the dashboard's own
# routes — POST /login (the endpoint) and GET /login (the page) would otherwise
# be the same path.
app.include_router(router, prefix="/api")

# Registered last: Starlette matches routes in order, so every /api path is
# claimed above before this catch-all mount sees it. html=True resolves /login
# to login/index.html, which is the layout `trailingSlash: true` produces.
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="dashboard")

# Bind to loopback only, always. With `network_mode: host` this is the host's own
# 127.0.0.1, so the API is reachable from the host (and from any reverse proxy or
# cloudflared tunnel running there) but never directly from the LAN — which
# matters because anyone who authenticates here has effective root on the box.
# Change the port with SERVERCTL_PORT; use nginx/set-port.sh so the nginx config
# is updated to match in the same step.
HOST = "127.0.0.1"
DEFAULT_PORT = 3000


def _resolve_port() -> int:
    """SERVERCTL_PORT, validated.

    A malformed value is fatal rather than silently falling back to 3000: the
    whole reason nginx/set-port.sh exists is that an app on a different port than
    the proxy expects produces a 502 that looks like a crash. Booting on the wrong
    port would recreate exactly that. An empty value means "unset" — an
    `SERVERCTL_PORT=` line with nothing after it is not a considered choice.
    """
    raw = os.environ.get("SERVERCTL_PORT", "").strip()
    if not raw:
        return DEFAULT_PORT
    try:
        port = int(raw)
    except ValueError:
        raise SystemExit(f"SERVERCTL_PORT must be a number between 1 and 65535, got {raw!r}")
    if not 1 <= port <= 65535:
        raise SystemExit(f"SERVERCTL_PORT must be between 1 and 65535, got {port}")
    return port


PORT = _resolve_port()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT, server_header=False)
