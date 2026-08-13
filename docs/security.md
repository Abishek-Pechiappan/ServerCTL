# Security

[← back to the README](../Readme.md)

**Start here: this app is root-equivalent.** It mounts the Docker socket and runs
with `pid: host`. Anyone who can log in can start a privileged container and own
the machine. There is one account, and its password is effectively a root password.

## What is in place

| | |
|---|---|
| Passwords | scrypt (n=16384, r=8, p=1), random 16-byte salt, constant-time compare on bytes |
| Sessions | JWT HS256, 60-minute expiry, `exp` and `sub` both required on decode |
| Auth failures | `401` + `WWW-Authenticate: Bearer` for missing, malformed and expired tokens alike |
| Brute force | 5 failures per IP in 5 minutes → 15-minute lockout (`429` + `Retry-After`), plus a global delay (below) |
| Lockout state | Keyed by a *parsed* IP, with expired entries pruned on every attempt, so the tables cannot be grown by a caller |
| Audit | Every login success, failure and lockout is logged to stdout — `docker compose logs` |
| Request limits | Body capped at 64 KB; username ≤ 256 and password ≤ 1024 characters, rejected before any hashing work |
| Injection | No database and no shell. Every `subprocess` call is a fixed argv list, and the container name — the only user-supplied string reaching a privileged sink — is pattern-matched against Docker's own naming rule |
| Exposure | Binds `127.0.0.1` only, and that is not configurable |
| Headers | CSP, HSTS, `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store` |

## Brute force, and why there are two controls

A per-IP lockout is not enough once the panel is reachable from the internet:

1. a distributed attacker simply uses a new source address every 5 attempts;
2. anything that can reach `127.0.0.1` on the host can set `CF-Connecting-IP`
   itself, and the app cannot tell it apart from cloudflared — so even a local
   unprivileged user can mint a fresh "IP" per request.

So there is a second, global control, and it **delays** rather than locks. That
distinction matters: a global lockout would hand any attacker a trivial way to keep
the real admin out. Once failures pile up across all sources, every attempt is
delayed by up to a few seconds. You still get in on the first try knowing your
password; a distributed guesser is slowed by orders of magnitude.

The delay is `await`ed rather than slept, so it costs an idle coroutine instead of
one of the threadpool's workers — otherwise the defence would itself become the
denial of service.

**If you put your own proxy in front**, set `X-Forwarded-For` to `$remote_addr`,
not `$proxy_add_x_forwarded_for`. The appending form preserves a client-supplied
header in first position, which is exactly the value the lockout keys on — a caller
could inject a fresh address per request and never be locked out.
`CF-Connecting-IP` is checked first precisely because Cloudflare always overwrites
it.

## Before you expose it

- **Put Cloudflare Access in front of the tunnel.** One account, no MFA, no
  revocation — Access supplies all three, and it is the single highest-value change
  available here.
- **Reach it through a tunnel, not an open port.** The app binds loopback; keep it
  that way.
- **Use a long, unique password.** There is one account and it is powerful.
- **Keep `DEBUG` unset.**
- **Treat `backend/.env` as a secret.** Compose records its values in the container
  config, so `docker inspect` shows them. The entrypoint does unset
  `ADMIN_PASSWORD` before starting the app, so it is not readable from
  `/proc/<pid>/environ` — which matters under `pid: host`.

## Known weakness: the session token

The token lives in `localStorage`, and the dashboard is a static export whose
inline hydration bootstrap forces `script-src 'unsafe-inline'`. Between those two
facts, any successful XSS in the dashboard yields a valid session token, and that
token stays valid until it expires because there is no server-side revocation —
logout only forgets it client-side.

Rotating `JWT_SECRET_KEY` invalidates every outstanding token immediately, which is
the lever to pull if you suspect a leak.

Fixing it properly means moving to an `HttpOnly`, `SameSite=Strict` cookie, at the
cost of needing CSRF protection on every mutating route.

## Verifying it yourself

`selftest.py` covers the authentication matrix as executable checks — the 401-vs-403
distinction, required JWT claims, the lockout, request size caps, the global
throttle degrading rather than denying, and the injection sinks:

```bash
backend/myenv/bin/python3 selftest.py
```

See [Development](development.md).
