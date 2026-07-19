# syntax=docker/dockerfile:1
#
# One image, one process: the dashboard is built to static files and served by
# the same uvicorn process that serves the API. There is nothing to connect, no
# supervisor, and no second container that can be up while the other is down.

# ---- Stage 1: build the dashboard to static HTML/JS/CSS --------------------
FROM node:22-alpine AS frontend
WORKDIR /build

# Copy manifests first so `npm ci` is only re-run when dependencies change,
# not on every source edit.
COPY frontend/serverctl/package.json frontend/serverctl/package-lock.json ./
RUN npm ci

COPY frontend/serverctl/ ./
# next.config.ts sets output: "export", so this writes plain files to ./out and
# no Node runtime is needed after this stage.
RUN npm run build


# ---- Stage 2: runtime ------------------------------------------------------
FROM python:3.12-slim-bookworm
WORKDIR /app

# iproute2 provides `ss` (collectors/ports.py). util-linux provides `last`/`who`
# (collectors/login_noti.py) reading the host's wtmp/utmp, bind-mounted in via
# docker-compose. Pinned to bookworm because the newer trixie-based slim image
# replaced `last` with wtmpdb (sqlite-backed), which can't read classic wtmp.
RUN apt-get update \
    && apt-get install -y --no-install-recommends iproute2 util-linux \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/authentication.py backend/password.py ./
COPY backend/agent ./agent

# main.py looks here for the dashboard; see STATIC_DIR.
COPY --from=frontend /build/out ./static

# Started via main.py rather than the uvicorn CLI so the listen port comes from
# SERVERCTL_PORT at runtime. An exec-form CMD does not expand variables, so
# hardcoding --port here would make the setting silently unreachable.
#
# No EXPOSE: it is metadata only and does nothing under `network_mode: host`,
# and a fixed value would be misleading once the port is configurable.
WORKDIR /app/agent
CMD ["python", "main.py"]
