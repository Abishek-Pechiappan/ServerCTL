# Development

[← back to the README](../Readme.md)

For most changes, rebuilding is fast enough — layer caching means only your changed
stage runs again:

```bash
docker compose up -d --build
```

## Running without Docker

```bash
python3 install.py                                  # backend/myenv + npm deps
cd frontend/serverctl && npm run build && cd -      # writes ./out
STATIC_DIR=frontend/serverctl/out backend/myenv/bin/python3 backend/agent/main.py
```

`STATIC_DIR` tells the app where the built dashboard is. It defaults to `../static`
relative to `main.py`, which is where the Dockerfile puts it. If the directory is
missing the API still runs and only the UI is absent.

To iterate on the frontend with hot reload, run `npm run dev` in
`frontend/serverctl` and set `NEXT_PUBLIC_API_URL` to the backend you are running
against — otherwise the Next dev server answers `/api` itself and calls never reach
FastAPI. That is the one situation where you need `ALLOWED_ORIGINS` set, because the
dev server is a different origin.

> `install.py` shells out to `apt-get` for Node. On Arch, install `nodejs` and `npm`
> with pacman first, then run it.

## Checking a change

`preflight.py` checks the host; `selftest.py` checks the code. Neither needs Docker
or a running server.

```bash
backend/myenv/bin/python3 selftest.py    # everything
python3 selftest.py                      # skips the groups needing FastAPI/psutil
```

```bash
cd frontend/serverctl && npx tsc --noEmit && npx eslint . && npm run build
```

`selftest.py` covers the things that break quietly:

- `.dockerignore` still excluding the virtualenv and any host `node_modules`, while
  preserving every path the Dockerfile copies. It parses the `COPY` lines and
  implements Docker's own segment-wise matching, including the `**/` rule that makes
  gitignore instincts wrong here.
- Port collector de-duplication — `ss` emits a row per address family and protocol.
- `/proc/net/tcp{,6}` address decoding against known vectors.
- scrypt round-trips, and that hashes use `:` rather than `$`.
- `set-port.sh`'s file handling, including a `.env` with no trailing newline.
- The snapshot loop's idle-parking and wake-up.
- The full authentication matrix, and the injection sinks.
- The static export being wired up so `/login` resolves and `/api` is not shadowed
  by the catch-all mount.

It also guards against regressions at the source level — it fails if anyone
introduces `shell=True`, `os.system` or `yaml.load`.

## Regenerating the screenshots

[`docs/screenshots/demo-server.py`](screenshots/demo-server.py) runs the app against
entirely synthetic data, so no real host information can reach the page. Start it,
then drive a browser at `http://127.0.0.1:8099` and log in with
`demo` / `demo-password`.

```bash
backend/myenv/bin/python3 docs/screenshots/demo-server.py
```

The charts build client-side from successive 3-second polls, so give it 90 seconds
before capturing if you want populated graphs.

## Layout

```
Dockerfile / .dockerignore   node builds the UI, python serves everything
docker-entrypoint.sh         first-run credential bootstrap + container self-check
docker-compose.yml           the single service
setup.py                     optional: create the admin login up front
preflight.py                 optional: check the host before first start
selftest.py                  optional: check the code
install.py                   local (non-Docker) development

backend/
  authentication.py          password verify, JWT, lockout, audit log
  password.py                scrypt hashing
  agent/
    main.py                  FastAPI app, static mount, security headers
    route.py                 every endpoint
    action/                  snapshot loop, docker, login history
    collectors/              cpu, ram, disk, temp, ports, docker, cloudflared
    security/proc.py         process and connection scan

frontend/serverctl/          Next.js static export (output: "export")
nginx/                       optional proxy + the port-changing script
docs/                        this documentation, and the screenshots
```

## Two things worth knowing before you change them

**Every page is `"use client"`**, so Next has no server-side work and builds to
plain files (`output: "export"`). That is why there is no Node runtime in the final
image — the FastAPI process serves the static export directly.

**Security headers are set by the backend, not `next.config.ts`.** Next's
`headers()` requires a server that a static export does not have, so Next would
silently drop them. They live in
[`backend/agent/main.py`](../backend/agent/main.py), which is the only thing
actually serving those files.
