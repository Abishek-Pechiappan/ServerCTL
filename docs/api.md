# API reference

[← back to the README](../Readme.md)

Base path `/api`. Everything except `/api/login` requires
`Authorization: Bearer <token>`. Tokens last **60 minutes**.

| Method | Path | Returns |
|---|---|---|
| POST | `/api/login` | `{access_token, token_type}` from `{username, password}` |
| GET | `/api/system/monitor` | Full snapshot: cpu, ram, disk, temperature, docker, ports, cloudflared, `ssh_active`, `ssh_history` |
| GET | `/api/network/ports` | `{port, process, scope}` — `scope` is `local`, `all`, or a specific address |
| GET | `/api/docker/containers` | `{name, status, image}`. `503` if the Docker socket is not mounted |
| POST | `/api/docker/up` | Start a container, body `{name}`. `400` if it does not exist or is already running |
| POST | `/api/docker/down` | Stop it gracefully — SIGTERM, then SIGKILL after 15s. `400` if it does not exist or is not running |
| GET | `/api/security/scan` | `{processes_scanned, suspicious_processes, suspicious_connections}` |
| GET | `/api/ssh/active` | Current login sessions |
| GET | `/api/ssh/history` | Recent logins (last 50) |
| GET | `/api/cloudflared/tunnels` | Ingress rules with a `healthy` flag |
| POST | `/api/system/update` | Non-functional — see [known limitations](troubleshooting.md#known-limitations) |
| POST | `/api/system/upgrade` | Non-functional — see [known limitations](troubleshooting.md#known-limitations) |

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:3000/api/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"you","password":"yourpassword"}' | jq -r .access_token)

curl -s http://127.0.0.1:3000/api/system/monitor -H "Authorization: Bearer $TOKEN" | jq
```

## Errors

**Authentication.** Missing, malformed and expired tokens all return `401` with a
`WWW-Authenticate: Bearer` challenge — the dashboard treats that as "session over"
and returns to the login page. Too many failed logins return `429` with
`Retry-After`.

**Validation.** `422` for a body that fails validation, and its `detail` is an
*array* of field errors rather than a string. `413` for a body over 64 KB.

**Partial failure.** Every collector is wrapped individually, so one that throws
appears as `{"error": "..."}` in its own field of the snapshot rather than failing
the whole request. That is why an empty panel is the designed failure mode.

## Reading the snapshot

`/api/system/monitor` serves a cached snapshot refreshed every 5 seconds by a
background thread, so polling it from several clients does not multiply the work.
Two refinements keep that loop from being a permanent tax on an idle machine:

- **Tiered.** Cloudflared health checks open a real connection per ingress rule,
  and login history forks `last` to re-read all of `wtmp`. Neither changes on a
  5-second timescale, so both run on a 30-second tier, and the health probes run in
  parallel so one slow service cannot stall the cycle.
- **Idle-parking.** After 60 seconds with nothing reading the snapshot, the loop
  stops collecting and waits; the next request wakes it. With no browser open,
  ServerCTL is not forking `ss`/`who` or touching the Docker socket at all.

The dedicated endpoints (`/api/network/ports`, `/api/cloudflared/tunnels`,
`/api/ssh/*`) read the same cache. The dashboard itself derives those panels from
one `/api/system/monitor` response rather than calling them separately.

Interval constants live in
[`backend/agent/action/agents.py`](../backend/agent/action/agents.py).

## Enabling the interactive docs

Set `DEBUG=1` to expose Swagger UI at `/docs` and the schema at `/openapi.json`.
They are off by default because they are an unauthenticated map of the whole API.
Keep `DEBUG` unset in production.
