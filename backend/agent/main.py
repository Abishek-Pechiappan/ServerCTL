import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
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


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    response.headers["Server"] = "ServerCTL"

    # The API returns only JSON and should never be allowed to pull anything in,
    # so it keeps the strictest possible policy. The dashboard needs to load its
    # own bundle, so it gets a policy scoped to same-origin assets. Applying the
    # API's `default-src 'none'` to the HTML would block the page's own scripts
    # and styles and render a blank screen.
    if request.url.path.startswith("/api"):
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    else:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            # Next inlines a small hydration bootstrap and Tailwind injects
            # styles at runtime, neither of which can carry a nonce in a static
            # export — so 'unsafe-inline' is required for the page to render.
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "base-uri 'none'; "
            "form-action 'none'; "
            "frame-ancestors 'none'"
        )
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
PORT = int(os.environ.get("SERVERCTL_PORT", "3000"))

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT, server_header=False)
