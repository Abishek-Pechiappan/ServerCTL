# ServerCTL

A dashboard for controlling your home server — system stats, Docker containers,
open ports, SSH sessions and cloudflared tunnels.

## Quick start

```bash
git clone <repo> && cd ServerCTL
python3 setup.py        # create the admin login (interactive)
python3 preflight.py    # check everything this box needs
docker compose up -d --build
```

Then open <http://localhost:3000>.

`preflight.py` is the important one — it catches the problems below before they
turn into a blank page or a 401, and tells you exactly what to run for each.

## Prerequisites

Docker and the Compose plugin. Docker is not enabled automatically on Arch:

| | Arch | Debian / Ubuntu |
|---|---|---|
| Install | `sudo pacman -S docker docker-compose` | `sudo apt install docker.io docker-compose-plugin` |
| Enable | `sudo systemctl enable --now docker` | usually already running |

Then add yourself to the `docker` group and log back in:

```bash
sudo usermod -aG docker $USER
```

`install.py` is only needed for local development against `dev.py` — the Compose
build does not use it. Note it shells out to `apt-get`, so on Arch install
`nodejs`/`npm` with pacman first.

## Remote access (nginx)

By default the dashboard is on `:3000` and the API on `:8001`. Those are two
different origins to a browser, so every API call needs CORS, and the API URL is
baked into the JS bundle at build time — which means the default setup only
works when the browser is on the server itself.

Putting nginx in front fixes both: one origin, no CORS, and something you can
point a tunnel at.

```bash
# Arch
sudo cp nginx/serverctl.conf /etc/nginx/conf.d/serverctl.conf
# Debian / Ubuntu
sudo ln -s "$PWD/nginx/serverctl.conf" /etc/nginx/sites-enabled/serverctl.conf

sudo nginx -t && sudo systemctl reload nginx
```

Then point the frontend at the proxy and rebuild — the URL is compiled into the
bundle, so a restart is not enough:

```bash
echo 'NEXT_PUBLIC_API_URL=/api' > .env
docker compose up -d --build
```

nginx now serves the UI on `/` and proxies `/api/*` to the backend. It listens on
plain HTTP because cloudflared terminates TLS; if you expose the box directly
instead, add a 443 block and redirect.

## Configuration

| File | Purpose |
|---|---|
| `.env` (repo root) | `NEXT_PUBLIC_API_URL` — `/api` behind nginx, otherwise `http://localhost:8001`. Build-time. |
| `backend/.env` | Admin credentials and `JWT_SECRET_KEY`. Written by `setup.py` — do not hand-edit. |

`backend/.env` also accepts `ALLOWED_ORIGINS` (comma-separated) for CORS when
running without nginx. It defaults to `http://localhost:3000,http://127.0.0.1:3000`.
Behind the proxy it is unused, because everything is same-origin.

Both files are gitignored, so they do not travel with the repo — a fresh clone
needs `setup.py` before the backend will start.

## Known limitations

**Login history is empty on recent distros.** systemd 258 disabled utmp, so
`/run/utmp` and `/var/log/wtmp` are no longer maintained on current Arch and on
Ubuntu 25.10+. `who` and `last` return nothing and the SSH sessions panel stays
blank. Docker also creates an empty root-owned *directory* at any missing
bind-mount source, so drop those two volume lines from `docker-compose.yml` if
your box has no utmp.

**System update/upgrade does not work.** `/system/update` and `/system/upgrade`
run `sudo apt` from inside the backend container, which has neither `sudo` nor
your host's package database — so the endpoint errors, and would target the
container rather than the server even if it ran. Fixing it properly means
executing on the host (`nsenter` via the existing `pid: host`, or a host-side
helper) plus a pacman branch. Not wired up yet.

**CPU temperature is Intel-only.** `collectors/temp.py` matches the `Package id 0`
label emitted by the `coretemp` driver. AMD's `k10temp` reports `Tctl`, so the
tile stays blank.

## Security notes

The backend mounts `docker.sock` and runs with `pid: host` — anyone who reaches
it authenticated has effective root on the machine. It binds `127.0.0.1` only, so
reach it through nginx and a tunnel rather than opening a port. `nginx/serverctl.conf`
rate-limits `/api/login` to 5/min per IP.

## Development

`dev.py` runs both services natively against `backend/myenv` (created by
`install.py`), bypassing Docker.
