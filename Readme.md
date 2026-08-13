# ServerCTL

A single-container web dashboard for one Linux server: CPU, RAM, disk and
temperature graphs, open ports, Docker containers you can start and stop,
cloudflared tunnel health, SSH sessions, and a basic process/connection scan.

The dashboard and the API are one process on `127.0.0.1:3000`. There is nothing to
wire together and no CORS to configure.

> **This app is root-equivalent.** It mounts the Docker socket and runs with
> `pid: host`, so anyone who logs in can start a privileged container and own the
> machine. Treat the admin password like a root password, and never expose the
> port directly — put it behind a tunnel.

---

## Requirements

- Linux with systemd, Docker, and the Compose plugin **v2.24+**
  (`docker compose version`—older plugins cannot parse this `docker-compose.yml`)
- Python 3.10+ on the host, only for the optional `preflight.py` / `selftest.py`
  helpers

Node and Python for the app itself live inside the build.

```bash
sudo usermod -aG docker $USER    # then log out and back in
sudo systemctl enable --now docker
```

## Install

```bash
git https://github.com/Abishek-Pechiappan/ServerCTL.git && cd ServerCTL
docker compose up -d --build
```

Open <http://localhost:3000>. On first run the container generates an admin
password and prints it once:

```bash
docker compose logs | grep -A6 "generated for you"
```

It is kept in a Docker volume, so it survives restarts and rebuilds.

**To choose your own**, create `backend/.env` and recreate:

```bash
printf 'ADMIN_USERNAME=you\nADMIN_PASSWORD=your-secret\n' > backend/.env
docker compose up -d --force-recreate
```

The password is hashed with scrypt at boot; only the hash is stored. Treat
`backend/.env` as a secret — Compose records its values in the container config.

### Everyday commands

```bash
docker compose logs -f                   # follow logs (auth events land here)
docker compose up -d --build             # after a code change
docker compose up -d --force-recreate    # after a backend/.env change
python3 preflight.py                     # check the host if it won't start
```

## Remote access

Point a [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
tunnel straight at the app:

```yaml
# ~/.cloudflared/config.yml
ingress:
  - hostname: panel.example.com
    service: http://127.0.0.1:3000
  - service: http_status:404
```

**Put Cloudflare Access in front of it.** One password is the only thing between
the internet and root on your box; Access adds SSO in front of that and is the
single highest-value thing you can do here. See [Security](#security).

Only if you need port 80/443 or your own TLS, there is an optional nginx config in
[`nginx/serverctl.conf`](nginx/serverctl.conf). To change ports, use the script so
both sides stay in agreement — editing either alone gives you a 502 that looks
like a crash:

```bash
./nginx/set-port.sh --show
./nginx/set-port.sh --app 4000      # container port
./nginx/set-port.sh --listen 8080   # nginx port
```

## Configuration

Optional, in `backend/.env`. Nothing is required — the container fills in what is
missing on first boot.

| Key | Description |
|---|---|
| `ADMIN_USERNAME` | Login name. Defaults to `admin`. |
| `ADMIN_PASSWORD` | Plaintext, hashed at boot. The simplest way to set your own. |
| `ADMIN_PASSWORD_HASH` | Pre-computed scrypt hash from `python3 setup.py`. Wins over `ADMIN_PASSWORD`. |
| `JWT_SECRET_KEY` | Signs session tokens. Generated and persisted if unset. Changing it logs everyone out. |
| `SERVERCTL_PORT` | App port, default `3000`. Set it with `nginx/set-port.sh`. |
| `ALLOWED_ORIGINS` | CORS origins. Leave unset unless you serve the UI from another host. |
| `DEBUG` | `1` enables `/docs`. Off by default — it is an unauthenticated map of the API. |

The app always binds `127.0.0.1`; that is not configurable.

> A pre-computed hash uses `:` separators, not `$`, because Compose would eat a
> `$` and silently truncate it. `setup.py` handles this.

## API

Base path `/api`. Everything except `/api/login` needs
`Authorization: Bearer <token>`. Tokens last 60 minutes.

| Method | Path | Returns |
|---|---|---|
| POST | `/api/login` | `{access_token, token_type}` from `{username, password}` |
| GET | `/api/system/monitor` | Full snapshot: cpu, ram, disk, temperature, docker, ports, cloudflared, ssh |
| GET | `/api/network/ports` | `{port, process, scope}` — `scope` is `local`, `all`, or an address |
| GET | `/api/docker/containers` | `{name, status, image}`. `503` if the socket is not mounted |
| POST | `/api/docker/up` | Start a container, body `{name}` |
| POST | `/api/docker/down` | Stop it gracefully (SIGTERM, SIGKILL after 15s) |
| GET | `/api/security/scan` | `{processes_scanned, suspicious_processes, suspicious_connections}` |
| GET | `/api/ssh/active` · `/api/ssh/history` | Current sessions · recent logins |
| GET | `/api/cloudflared/tunnels` | Ingress rules with a `healthy` flag |
| POST | `/api/system/update` · `/api/system/upgrade` | Non-functional, see [limitations](#known-limitations) |

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:3000/api/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"you","password":"yourpassword"}' | jq -r .access_token)

curl -s http://127.0.0.1:3000/api/system/monitor -H "Authorization: Bearer $TOKEN" | jq
```

Missing, malformed and expired tokens all return `401` with a
`WWW-Authenticate: Bearer` challenge. A failing collector appears as
`{"error": "..."}` in its own field rather than failing the request.

## Security

| | |
|---|---|
| Passwords | scrypt (n=16384, r=8, p=1), random 16-byte salt, constant-time compare |
| Sessions | JWT HS256, 60-minute expiry, `exp` and `sub` required on decode |
| Brute force | 5 failures per IP in 5 min → 15-min lockout; plus a **global delay** once failures pile up from many addresses |
| Audit | Every login success, failure and lockout is logged to stdout |
| Limits | Body capped at 64 KB; username ≤ 256 and password ≤ 1024 chars, checked before hashing |
| Injection | No database and no shell: every `subprocess` call is a fixed argv list, and the container name — the only user string reaching a privileged sink — is pattern-matched to Docker's own naming rule |
| Exposure | Binds `127.0.0.1` only |
| Headers | CSP, HSTS, `nosniff`, `X-Frame-Options: DENY`, `no-referrer`, `no-store` |

The global delay exists because a per-IP lockout is not enough once you are on the
internet: an attacker can rotate source addresses, and anything that can reach
`127.0.0.1` on the host can set `CF-Connecting-IP` itself. It **delays** rather
than locks, deliberately — a global lockout would let an attacker keep you out.

If you put your own proxy in front, set `X-Forwarded-For` to `$remote_addr`, not
`$proxy_add_x_forwarded_for`. The appending form lets a client inject its own
address and dodge the lockout.

**Recommended**

- **Cloudflare Access in front of the tunnel.** One account, no MFA, no
  revocation — Access supplies all three.
- A long, unique password. There is one account and it is powerful.
- Keep `DEBUG` unset.

**Known weakness.** The session token is in `localStorage`, and the dashboard is a
static export whose inline bootstrap forces `script-src 'unsafe-inline'`. Any XSS
in the dashboard therefore yields a working token, valid until it expires —
logout only forgets it client-side. Rotating `JWT_SECRET_KEY` invalidates every
token immediately. Fixing it properly means `HttpOnly` cookies plus CSRF
protection on every mutating route.

## Known limitations

- **`/api/system/update` and `/api/system/upgrade` do not work.** They run
  `sudo apt` inside a container that has neither, and would update the container
  rather than the host.
- **Login history is empty on recent distros.** systemd 258 disabled utmp, so
  `who` and `last` return nothing on current Arch and Ubuntu 25.10+. Docker
  creates a root-owned *directory* at a missing bind mount, so delete the
  `wtmp`/`utmp` volume lines if `/run/utmp` does not exist.
- **CPU temperature is Intel-only** (`coretemp`'s `Package id 0`; AMD reports
  `Tctl`).
- **The security scan is a hint, not an IDS.** It flags root processes running
  from `/tmp`, `/dev/shm` or `/var/tmp`, and established connections on a
  hardcoded port list that includes 22 — so your own SSH session shows up. Edit
  `SUSPICIOUS_PORTS` in `backend/agent/security/proc.py`.
- **Disk shows `/` only.**

## Troubleshooting

**Won't start / connection refused** — `docker compose logs -f`, then
`python3 preflight.py`.

**Login always fails** — set a known password:
`printf 'ADMIN_PASSWORD=new-secret\n' >> backend/.env && docker compose up -d --force-recreate`.
A hand-written `ADMIN_PASSWORD_HASH` containing `$` is the other usual cause.

**Locked out (429)** — wait 15 minutes, or `docker compose restart` to clear the
in-memory counters.

**Port already in use** — `sudo ss -tlnp | grep 3000`. Upgrading from the old
two-container layout? Remove the leftovers, which still hold the port:
`docker rm -f serverctl-backend serverctl-frontend`.

**A panel is empty** — a missing mount or an unsupported distro; `preflight.py`
names which. Empty is the designed failure mode.

**Code changes did nothing** — `docker compose up -d --build`. Only `.env`
changes work with `--force-recreate` alone.

## Development

```bash
python3 install.py                                  # venv + npm deps
cd frontend/serverctl && npm run build && cd -      # writes ./out
STATIC_DIR=frontend/serverctl/out backend/myenv/bin/python3 backend/agent/main.py
```

`preflight.py` checks the host, `selftest.py` checks the code — neither needs
Docker or a running server:

```bash
backend/myenv/bin/python3 selftest.py    # everything
python3 selftest.py                      # skips groups needing FastAPI/psutil
cd frontend/serverctl && npx tsc --noEmit && npx eslint . && npm run build
```

`selftest.py` covers the things that break quietly: `.dockerignore` still keeping
the virtualenv and host `node_modules` out while preserving every path the
Dockerfile copies, port de-duplication, `/proc/net/tcp{,6}` decoding, scrypt
round-trips, `set-port.sh` file handling, the snapshot loop's idle-parking, the
authentication matrix, and the static-export wiring.

### Layout

```
Dockerfile / .dockerignore   node builds the UI, python serves everything
docker-entrypoint.sh         first-run credential bootstrap + self-check
backend/authentication.py    password verify, JWT, lockout, audit log
backend/agent/main.py        FastAPI app, static mount, security headers
backend/agent/route.py       every endpoint
backend/agent/action/         snapshot loop, docker, login history
backend/agent/collectors/     cpu, ram, disk, temp, ports, docker, cloudflared
frontend/serverctl/          Next.js static export (output: "export")
nginx/                       optional proxy + the port-changing script
```

Every page is `"use client"`, so Next builds to plain files and there is no Node
runtime in the final image. Security headers are set by the backend, not
`next.config.ts` — `headers()` needs a server a static export does not have.
