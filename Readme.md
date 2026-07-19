# ServerCTL

A self-hosted web dashboard for a home server. It shows live system stats,
manages Docker containers, lists open ports and SSH logins, checks cloudflared
tunnel health, and runs a basic process/network scan — all behind a single admin
login.

It ships as **one Docker container running one process on one port**. There is
nothing to wire together.

---

## Contents

- [What it does](#what-it-does)
- [How it works](#how-it-works)
- [Requirements](#requirements)
- [Installation](#installation)
- [Accessing it remotely](#accessing-it-remotely)
- [Configuration](#configuration)
- [API reference](#api-reference)
- [Troubleshooting](#troubleshooting)
- [Known limitations](#known-limitations)
- [Security](#security)
- [Upgrading from the two-container setup](#upgrading-from-the-two-container-setup)
- [Development](#development)
- [Project layout](#project-layout)

---

## What it does

| Panel | Source | Notes |
|---|---|---|
| CPU / RAM / disk | `psutil` | Disk is `/` only. CPU is a 1-second sampled average. |
| CPU temperature | `psutil.sensors_temperatures()` | Intel only — see [limitations](#known-limitations). |
| Docker containers | Docker socket | Lists all containers, running first; start and stop them. |
| Open ports | `ss -tulpn` | Shows the owning process and PID. |
| SSH sessions | `who` / `last` | Empty on recent distros — see [limitations](#known-limitations). |
| cloudflared tunnels | `~/.cloudflared/config.yml` | Reads your ingress rules and health-checks each service. |
| Security scan | `/proc` | Flags root processes running from `/tmp`, `/dev/shm`, `/var/tmp`, and connections on known-malware ports. |

A background thread refreshes all of the above every **5 seconds**
(`REFRESH_SECONDS` in [backend/agent/action/agents.py](backend/agent/action/agents.py))
and caches one snapshot. Dashboard requests read that cache, so polling many
clients does not multiply the work. A collector that throws is caught
individually — one broken panel returns `{"error": "..."}` instead of taking the
whole snapshot down.

---

## How it works

```
serverctl container   (network_mode: host, pid: host)
  └─ uvicorn on 127.0.0.1:3000
       /            →  dashboard   (static Next.js export, served by FastAPI)
       /api/*       →  FastAPI

     mounts:  /var/run/docker.sock      manage containers
              ~/.cloudflared            read tunnel config
              /var/log/wtmp, /run/utmp  login history
```

**One process.** The dashboard is compiled to static HTML/JS/CSS at build time
and served by the same uvicorn process that serves the API. If the container is
up, the whole app is up — there is no second service that can be down.

**No CORS, structurally.** Because the page and the API share an origin, the
browser never issues a preflight. There is no origin list to keep in sync with
your hostname. (This was the single most common setup failure before.)

**No Node.js at runtime.** Every page in the app is `"use client"`, so Next.js
has no server-side work to do and builds to plain files
(`output: "export"`). The final image is `python:3.12-slim` plus static assets.

**Why the API lives under `/api`.** `POST /api/login` is the endpoint and
`/login` is the page. Without the prefix they would be the same path,
distinguished only by HTTP method — fragile and confusing.

**Why `network_mode: host` and `pid: host`.** `ss` must see the host's sockets,
not the container's, and `psutil` must see the host's processes. Host networking
also means uvicorn binds the *host's* `127.0.0.1:3000` directly.

---

## Requirements

- Linux with systemd
- Docker + the Compose plugin
- Python 3.10+ on the host — **optional**, only for the `preflight.py` /
  `setup.py` helpers; not needed to run the app

Node and Python for the app itself live **inside the build** — you do not
install them.

| | Arch | Debian / Ubuntu |
|---|---|---|
| Install | `sudo pacman -S docker docker-compose` | `sudo apt install docker.io docker-compose-plugin` |
| Enable | `sudo systemctl enable --now docker` | usually already running |

Docker is **not** started automatically on Arch — the `enable --now` step is
required. On both, add yourself to the `docker` group so you can run it without
`sudo`:

```bash
sudo usermod -aG docker $USER
```

Then **log out and back in** — group membership only applies to new sessions.

---

## Installation

```bash
git clone <repo-url> && cd ServerCTL
docker compose up -d --build
```

That's it. Open <http://localhost:3000>. On the first run the container creates
an admin login for you and prints it once:

```bash
docker compose logs | grep -A6 "generated for you"
```

```
 No admin password was set, so one was generated for you:
     username: admin
     password: 0HGAdLWtyP2MGB-j
```

Log in with that. It is saved in a Docker volume, so it survives restarts and
rebuilds — you only see it printed the once.

### Choosing your own password

If you would rather set the login yourself, create `backend/.env` before the
first start (or any time — then recreate):

```bash
printf 'ADMIN_USERNAME=you\nADMIN_PASSWORD=your-secret\n' > backend/.env
docker compose up -d --force-recreate
```

The container hashes the password with **scrypt** at boot; the plaintext is only
ever in that file, never stored elsewhere. A value you set here always wins over
the auto-generated one.

> **`setup.py` still works** and does the same thing up front (writing an
> `ADMIN_PASSWORD_HASH` and a `JWT_SECRET_KEY` so nothing is stored as
> plaintext). It is now optional — use it if you prefer not to keep a plaintext
> password in `backend/.env`, or for local non-Docker runs.

### Optional: check the host first

`preflight.py` verifies the things the container cannot check about the **host**
— Docker installed, you are in the `docker` group, the port is free, no leftover
containers. Run it if the first start does not come up:

```bash
python3 preflight.py
```

Output is `OK` / `WARN` / `FAIL`; a `WARN` means it starts but a panel will be
empty, only `FAIL` blocks. The container checks its own side (credentials, built
UI, socket mount) automatically at boot and logs any problem.

### Everyday commands

```bash
docker compose logs -f          # follow logs
docker compose up -d --build    # rebuild after a code change
docker compose up -d --force-recreate   # apply a backend/.env change
docker compose down             # stop and remove
```

> **Code changes need `--build`.** The dashboard is compiled into the image, so a
> plain `restart` reruns the old build.

---

## Accessing it remotely

The app binds `127.0.0.1` only — it is **not** reachable from your LAN by
design. Everything here has root-equivalent power (see [Security](#security)),
so it should not be a port you can hit from any device on the network.

### Option A — cloudflared (recommended)

Point your tunnel straight at the port. One service, no routing rules:

```yaml
# ~/.cloudflared/config.yml
ingress:
  - hostname: panel.example.com
    service: http://127.0.0.1:3000
  - service: http_status:404
```

Cloudflare terminates TLS, so there are no certificates to manage. The
tunnels panel in the dashboard reads this same file and health-checks each
service listed.

### Option B — nginx (optional)

Only needed if you want to serve on port 80/443 or terminate TLS yourself.
[nginx/serverctl.conf](nginx/serverctl.conf) is a ready-made reverse proxy:

```bash
# Arch
sudo cp nginx/serverctl.conf /etc/nginx/conf.d/serverctl.conf
# Debian / Ubuntu
sudo ln -s "$PWD/nginx/serverctl.conf" /etc/nginx/sites-enabled/serverctl.conf

sudo nginx -t && sudo systemctl reload nginx
```

Edit `server_name` to your hostname. The config sets long cache headers on
`/_next/static/` (filenames are content-hashed) and `no-store` everywhere else.

### Changing the port

There are two ports and they must agree:

| | | Default |
|---|---|---|
| **listen** | the port nginx accepts browser traffic on | 80 |
| **app** | the port the container listens on internally | 3000 |

Use the script — it updates `nginx/serverctl.conf` and `backend/.env` together,
which is the point. Editing the nginx file by hand leaves the app on its old
port and produces a **502 that looks like the app crashed**.

```bash
./nginx/set-port.sh --show                  # what is set now
./nginx/set-port.sh --app 4000              # move the app to 4000
./nginx/set-port.sh --listen 8080           # serve on 8080 instead of 80
./nginx/set-port.sh --listen 8080 --app 4000
```

Then apply:

```bash
docker compose up -d
sudo nginx -t && sudo systemctl reload nginx   # only if you use nginx
```

Passing one flag leaves the other alone, and re-running with the same values is
a no-op. The script refuses ports outside 1–65535 and refuses to set both to the
same value. `preflight.py` warns if the two ever drift apart.

If you are **not** using nginx, only `--app` matters — point cloudflared at that
port directly.

> The proxy headers are written out explicitly rather than using
> `include proxy_params;` — that file only exists on Debian/Ubuntu and would
> make the config fail to load on Arch.

---

## Configuration

Optional settings go in `backend/.env`, read at container start. None are
required — the entrypoint fills in credentials on first boot (see
[Installation](#installation)). Set what you want to control:

| Key | Description |
|---|---|
| `ADMIN_USERNAME` | Login username. Defaults to `admin`. |
| `ADMIN_PASSWORD` | Plaintext password, **hashed at boot** (never stored as-is). The simplest way to set your own login. |
| `ADMIN_PASSWORD_HASH` | A pre-computed scrypt hash from `setup.py`. Use this instead of `ADMIN_PASSWORD` if you would rather not keep a plaintext password in the file. Takes precedence if both are set. |
| `JWT_SECRET_KEY` | Signs session tokens. Auto-generated and persisted if unset. Changing it logs everyone out. |
| `SERVERCTL_PORT` | Port the app listens on. Defaults to `3000`. Set it with [`nginx/set-port.sh`](nginx/set-port.sh) so the nginx config stays in sync. |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins. Leave unset — only needed if you serve the dashboard from a different host than the API. |
| `DEBUG` | `1` enables `/docs` and `/openapi.json`. Off by default, because they are an unauthenticated map of the API. |

The app always binds `127.0.0.1` and that is not configurable — see
[Security](#security).

After editing, apply with `docker compose up -d --force-recreate` (an `.env`
change does not need a rebuild; a code change does).

> `.env` files are read by Compose with variable interpolation, which is why a
> pre-computed `ADMIN_PASSWORD_HASH` uses `:` separators rather than `$`. A `$`
> would be eaten as an undefined variable and silently truncate the hash, making
> every login fail. `setup.py` handles this for you.

---

## API reference

Base path `/api`. All routes except `/api/login` require
`Authorization: Bearer <token>`.

| Method | Path | Returns |
|---|---|---|
| POST | `/api/login` | `{access_token, token_type}`. Body: `{username, password}`. |
| GET | `/api/system/monitor` | Full snapshot: cpu, ram, disk, temperature, docker, ports, cloudflared, ssh. |
| GET | `/api/network/ports` | Open ports with owning process. |
| GET | `/api/docker/containers` | All containers: `{name, status, image}`. |
| POST | `/api/docker/up` | Start a container. Body: `{name}`. |
| POST | `/api/docker/down` | Stop a container. Body: `{name}`. |
| GET | `/api/security/scan` | Process list with `suspicious` flags, plus flagged connections. |
| GET | `/api/ssh/active` | Current login sessions. |
| GET | `/api/ssh/history` | Recent logins (last 50). |
| GET | `/api/cloudflared/tunnels` | Ingress rules with a `healthy` boolean. |
| POST | `/api/system/update` | Currently non-functional — see [limitations](#known-limitations). |
| POST | `/api/system/upgrade` | Currently non-functional — see [limitations](#known-limitations). |

Example:

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:3000/api/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"you","password":"yourpassword"}' | jq -r .access_token)

curl -s http://127.0.0.1:3000/api/system/monitor -H "Authorization: Bearer $TOKEN" | jq
```

Tokens expire after **60 minutes**.

---

## Troubleshooting

**Start here:** `python3 preflight.py`. It detects most of what follows.

### The page won't load / "connection refused"

```bash
docker compose ps        # is it running?
docker compose logs -f   # why did it stop?
```

### Browser console shows a CORS error

Almost always **not** actually CORS. When a request gets *no response at all*,
Chrome reports it as `No 'Access-Control-Allow-Origin' header is present` — the
`net::ERR_FAILED` alongside it is the tell. Check whether anything is listening:

```bash
curl -i http://127.0.0.1:3000/api/system/monitor
```

- `Connection refused` → the container is down. See above.
- An HTTP response → genuinely a CORS issue, which only happens if you set
  `ALLOWED_ORIGINS` or split the frontend onto another host.

In the default single-container setup, real CORS errors are impossible.

### Container exits immediately

```bash
docker compose logs | tail -20
```

The entrypoint bootstraps credentials, so this is usually a mount or socket
problem rather than missing keys. The log lines prefixed `[serverctl]` say what
it found.

### I didn't see the generated password

It is printed only on the boot that creates it. Retrieve the current state:

```bash
docker compose logs | grep -A6 "generated for you"   # if still in the log buffer
```

If the log has rotated, just set your own and recreate:

```bash
printf 'ADMIN_USERNAME=you\nADMIN_PASSWORD=your-secret\n' > backend/.env
docker compose up -d --force-recreate
```

To start completely fresh (new generated password), remove the data volume:
`docker compose down && docker volume rm serverctl_serverctl-data`.

### Login always returns 401

1. Wrong password. Set a known one: put `ADMIN_PASSWORD=...` in `backend/.env`
   and `docker compose up -d --force-recreate`.
2. A hand-written `ADMIN_PASSWORD_HASH` that is malformed. Prefer `ADMIN_PASSWORD`
   (hashed for you) or `python3 setup.py`.
3. Locked out: 5 failed attempts within 5 minutes blocks your IP for 15 minutes
   and returns **429**, not 401. Wait, or `docker compose restart` to clear the
   in-memory counter.

### Port already in use

```bash
sudo ss -tlnp | grep 3000
docker rm -f serverctl-backend serverctl-frontend   # leftovers from the old setup
```

Or move ServerCTL out of the way: `./nginx/set-port.sh --app 4000`.

### nginx returns 502 Bad Gateway

nginx is forwarding to a port nothing is listening on — almost always because
`nginx/serverctl.conf` was edited by hand without updating the app. Check both:

```bash
./nginx/set-port.sh --show
```

If they disagree, set them together and restart:

```bash
./nginx/set-port.sh --app 3000
docker compose up -d && sudo systemctl reload nginx
```

`preflight.py` reports this mismatch too.

### "permission denied" on the Docker socket

You are not in the `docker` group:

```bash
sudo usermod -aG docker $USER   # then log out and back in
```

### A panel is empty

| Panel | Likely cause |
|---|---|
| SSH sessions | Your distro dropped utmp — expected, see below. |
| Temperature | Non-Intel CPU — expected, see below. |
| cloudflared | No `~/.cloudflared/config.yml`, or it has no `ingress:` rules. |
| Docker | Socket not mounted or permission denied — check logs. |

### Changes to the code did nothing

Use `docker compose up -d --build`. The dashboard is compiled into the image;
`restart` reuses the old build.

---

## Known limitations

These are real, known, and not worth reporting as bugs.

**System update / upgrade does not work.** `/api/system/update` and
`/api/system/upgrade` run `sudo apt` from inside the container, which has neither
`sudo` nor your host's package database. The endpoint errors out — and even if it
ran, it would update the ephemeral container rather than your server. Fixing it
properly means executing on the host (`nsenter`, using the existing `pid: host`,
or a small host-side helper) plus a `pacman` branch for Arch. Not wired up.

**Login history is empty on recent distros.** systemd 258 disabled utmp, so
`/run/utmp` and `/var/log/wtmp` are no longer maintained on current Arch and
Ubuntu 25.10+. `who` and `last` return nothing. Migrating to `wtmpdb` or the
systemd journal would fix it.

> Docker creates an empty **root-owned directory** at any missing bind-mount
> source. If `ls /run/utmp` says it does not exist, delete those two volume lines
> from `docker-compose.yml` to avoid the clutter.

**CPU temperature is Intel-only.** `collectors/temp.py` matches the label
`Package id 0`, emitted by Intel's `coretemp` driver. AMD's `k10temp` reports
`Tctl`, so the tile stays blank.

**The security scan is heuristic, not a real IDS.** It flags root processes whose
command line mentions `/tmp`, `/dev/shm` or `/var/tmp`, and connections on a
hardcoded list of malware-associated ports. That list includes **22 (SSH)** and
**2222**, so a normal server with SSH enabled will always report a "suspicious
connection". It reads only `/proc/net/tcp`, so IPv4 only. Treat it as a hint.

**Scan logs are ephemeral.** Suspicious findings are appended to `log.txt` and
`network_log.text` in the container's working directory, which is not a volume —
they vanish when the container is recreated.

**Stopping a container is not graceful.** `docker_down` calls `kill()`, which
sends SIGKILL immediately rather than SIGTERM-then-wait. Containers get no
chance to shut down cleanly.

**Disk shows `/` only.** Other mounts are not reported.

---

## Security

**This app is root-equivalent.** It mounts the Docker socket and runs with
`pid: host`. Anyone who can log in can start a privileged container and own the
machine. Treat the admin password as a root password.

What is in place:

| | |
|---|---|
| Password storage | scrypt (n=16384, r=8, p=1), 16-byte random salt |
| Credential check | Constant-time compare, both fields always evaluated so timing does not reveal which was wrong |
| Sessions | JWT, HS256, 60-minute expiry |
| Brute force | 5 failed logins per IP in 5 minutes → 15-minute lockout (`429`) |
| Network exposure | Binds `127.0.0.1` only |
| API docs | `/docs` and `/openapi.json` disabled unless `DEBUG=1` |
| Headers | HSTS, `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer` |
| CSP | Strict `default-src 'none'` on API responses; same-origin policy on the dashboard |

Recommendations:

- Reach it through a cloudflared tunnel, not an open port.
- Use a long, unique password — there is only one account and it is powerful.
- Keep `DEBUG` unset in production.

Client IPs for the lockout come from `CF-Connecting-IP` or `X-Forwarded-For`.
That is trustworthy **because** the port is loopback-only and a tunnel or proxy
is the sole client. If you ever expose the port directly, those headers become
attacker-controlled and the lockout can be trivially bypassed.

---

## Upgrading from the two-container setup

Earlier versions ran `serverctl-backend` and `serverctl-frontend` separately.
Remove them first — the old frontend still holds port 3000:

```bash
docker rm -f serverctl-backend serverctl-frontend
docker compose up -d --build
```

`preflight.py` checks for these and fails if they are present.

What changed:

- The two Dockerfiles were replaced by one at the repo root.
- API paths moved from `/…` to `/api/…`.
- The API port 8001 is gone; everything is on 3000.
- The root `.env` and its `NEXT_PUBLIC_API_URL` are no longer used — delete them.
- `ALLOWED_ORIGINS` is no longer needed and defaults to empty.

---

## Development

For most changes, rebuilding is fast enough — layer caching means only your
changed stage runs again:

```bash
docker compose up -d --build
```

To iterate on the backend without Docker:

```bash
python3 install.py    # creates backend/myenv and installs deps
cd frontend/serverctl && npm run build && cd -   # writes ./out
STATIC_DIR=frontend/serverctl/out backend/myenv/bin/python3 backend/agent/main.py
```

`STATIC_DIR` tells the app where the built dashboard is. It defaults to
`../static` relative to `main.py`, which is where the Dockerfile puts it. If the
directory is missing the API still runs and only the UI is absent.

To iterate on the frontend with hot reload, run `npm run dev` in
`frontend/serverctl` and set `NEXT_PUBLIC_API_URL` to the backend you are
running against — the Next dev server serves `/api` itself otherwise, and calls
will not reach FastAPI. That is the one situation where you need
`ALLOWED_ORIGINS` set, because the dev server is a different origin.

> `install.py` shells out to `apt-get` for Node. On Arch, install `nodejs` and
> `npm` with pacman first, then run it.

---

## Project layout

```
Dockerfile              multi-stage: node builds the UI, python runs everything
docker-entrypoint.sh    first-run credential bootstrap + container self-check
docker-compose.yml      the single service
setup.py                optional: create the admin login up front
preflight.py            optional: check the host before first start
install.py / dev.py     local (non-Docker) development
nginx/
  serverctl.conf        optional reverse proxy
  set-port.sh           change the listen / app ports together

backend/
  authentication.py     password verify, JWT, brute-force lockout
  password.py           scrypt hashing
  requirements.txt
  agent/
    main.py             FastAPI app, static mount, security headers
    route.py            all API endpoints
    action/
      agents.py         5-second background snapshot loop
      actdocker.py      container list / start / stop
      login_noti.py     who + last parsing
      system_management.py   apt update/upgrade (non-functional)
    collectors/         cpu, ram, disk, temp, ports, docker, cloudflared
    security/proc.py    process and connection scan

frontend/serverctl/
  next.config.ts        output: "export"
  lib/api.ts            fetch wrapper, token storage
  app/                  login, dashboard pages (all "use client")
  components/           gauges, tiles, charts
```
