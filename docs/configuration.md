# Configuration

[← back to the README](../Readme.md)

Everything optional goes in `backend/.env`, read at container start. Nothing is
required — the entrypoint fills in whatever is missing on first boot.

| Key | Description |
|---|---|
| `ADMIN_USERNAME` | Login name. Defaults to `admin`. |
| `ADMIN_PASSWORD` | Plaintext, hashed at boot. The simplest way to set your own. |
| `ADMIN_PASSWORD_HASH` | Pre-computed scrypt hash from `python3 setup.py`. Wins over `ADMIN_PASSWORD`. |
| `JWT_SECRET_KEY` | Signs session tokens. Generated and persisted if unset. Changing it logs everyone out. |
| `SERVERCTL_PORT` | App port, default `3000`. Set it with `nginx/set-port.sh`. |
| `ALLOWED_ORIGINS` | CORS origins. Leave unset unless you serve the UI from another host. |
| `DEBUG` | `1` enables `/docs`. Off by default — it is an unauthenticated map of the API. |

The app always binds `127.0.0.1`; that is not configurable. See
[Security](security.md).

Apply a change with `docker compose up -d --force-recreate`. An `.env` change does
not need a rebuild; a code change does.

> A pre-computed `ADMIN_PASSWORD_HASH` uses `:` separators rather than `$`, because
> Compose performs variable interpolation on env files and would eat a `$` — the
> hash would be silently truncated and every login would fail. `setup.py` handles
> this for you.

## Changing the port

There are two ports and they must agree:

| | | Default |
|---|---|---|
| **app** | the port the container listens on | `3000` |
| **listen** | the port nginx accepts browser traffic on, if you use nginx | `80` |

Use the script rather than editing files by hand — it updates
`nginx/serverctl.conf` and `backend/.env` together, which is the whole point.
Editing the nginx side alone leaves the app on its old port and produces a **502
that looks like the app crashed**.

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

Passing one flag leaves the other alone, and re-running with the same values is a
no-op. The script refuses ports outside 1–65535 and refuses to set both to the same
value. `preflight.py` warns if the two ever drift apart.

If you are **not** using nginx, only `--app` matters — point cloudflared at that
port directly.

## The optional nginx proxy

You do not need nginx. The container already serves the dashboard and the API from
one process, so there is no routing to do. [`nginx/serverctl.conf`](../nginx/serverctl.conf)
exists for two cases only:

1. serving on port 80/443 instead of 3000;
2. terminating TLS yourself, if you are not using a cloudflared tunnel.

```bash
# Arch
sudo cp nginx/serverctl.conf /etc/nginx/conf.d/serverctl.conf
# Debian / Ubuntu
sudo ln -s "$PWD/nginx/serverctl.conf" /etc/nginx/sites-enabled/serverctl.conf

sudo nginx -t && sudo systemctl reload nginx
```

Two deliberate choices in that file, worth preserving if you write your own:

- The proxy headers are written out explicitly rather than pulled in with
  `include proxy_params;` — that file ships only on Debian/Ubuntu and makes the
  config fail to load on Arch.
- `X-Forwarded-For` is set to `$remote_addr`, **not**
  `$proxy_add_x_forwarded_for`. The appending form lets a client inject its own
  address and dodge the brute-force lockout. See [Security](security.md).
