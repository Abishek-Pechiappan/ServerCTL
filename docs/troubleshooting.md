# Troubleshooting

[← back to the README](../Readme.md)

**Start here:** `python3 preflight.py`. It checks the host — Docker installed, you
are in the `docker` group, the port is free, no leftover containers, mounts present
— and names what is wrong. `OK` / `WARN` / `FAIL`; only `FAIL` blocks a start.

### Won't start / connection refused

```bash
docker compose ps        # is it running?
docker compose logs -f   # why did it stop?
```

A `docker compose` version below **2.24** cannot parse this `docker-compose.yml`
(it uses the `env_file` long form) and the error does not mention the version.
Check with `docker compose version`.

### Login always fails

Set a password you know:

```bash
printf 'ADMIN_PASSWORD=new-secret\n' >> backend/.env
docker compose up -d --force-recreate
```

The other usual cause is a hand-written `ADMIN_PASSWORD_HASH` containing `$`, which
Compose eats — see [Configuration](configuration.md). Prefer `ADMIN_PASSWORD` and
let the container hash it, or use `python3 setup.py`.

### Locked out (429)

Wait 15 minutes, or `docker compose restart` — the counters are in memory only.

### I didn't see the generated password

```bash
docker compose logs | grep -A6 "generated for you"
```

It is printed once and only once. If the log has rotated away, set your own with
`ADMIN_PASSWORD` and `--force-recreate`.

### Port already in use

```bash
sudo ss -tlnp | grep 3000
```

Upgrading from the old two-container layout? Those still hold the port:

```bash
docker rm -f serverctl-backend serverctl-frontend
docker compose up -d --build
```

`preflight.py` checks for them and fails if they are present.

### nginx returns 502 Bad Gateway

The two ports have drifted apart: nginx is proxying somewhere the app is not
listening. Fix both together with `./nginx/set-port.sh --app <port>` — see
[Configuration](configuration.md). `preflight.py` reports this mismatch too.

### "permission denied" on the Docker socket

```bash
sudo usermod -aG docker $USER   # then log out and back in
```

Group membership only applies to new sessions.

### A panel is empty

Empty is the designed failure mode — a collector that fails returns
`{"error": "..."}` in its own field rather than taking the request down. Usually a
missing mount or an unsupported distro; `preflight.py` names which, and the
limitations below cover the expected cases.

### Code changes did nothing

```bash
docker compose up -d --build
```

Only `.env` changes work with `--force-recreate` alone.

---

## Known limitations

These are real, known, and not worth reporting as bugs.

**`/api/system/update` and `/api/system/upgrade` do not work.** They run `sudo apt`
inside a container that has neither `sudo` nor your host's package database — and
even if it ran, it would update the ephemeral container rather than your server.
Doing it properly means executing on the host (`nsenter`, using the existing
`pid: host`, or a small host-side helper) plus a `pacman` branch for Arch.

**Login history is empty on recent distros.** systemd 258 disabled utmp, so
`/run/utmp` and `/var/log/wtmp` are no longer maintained on current Arch and
Ubuntu 25.10+, and `who`/`last` return nothing. Migrating to `wtmpdb` or the
journal would fix it.

> Docker creates an empty **root-owned directory** at any missing bind-mount
> source. If `ls /run/utmp` says it does not exist, delete those two volume lines
> from `docker-compose.yml` to avoid the clutter.

**CPU temperature is Intel-only.** `collectors/temp.py` matches the label
`Package id 0`, emitted by Intel's `coretemp`. AMD's `k10temp` reports `Tctl`, so
the tile stays blank.

**The security scan is a hint, not an IDS.** It flags root processes whose
executable resolves into `/tmp`, `/dev/shm` or `/var/tmp`, and established
connections on a hardcoded port list. That list includes **22** and **2222** —
listening sockets are ignored, so idle `sshd` does not trip it, but any live SSH
session of yours will be reported. Edit `SUSPICIOUS_PORTS` in
[`backend/agent/security/proc.py`](../backend/agent/security/proc.py) to suit your
own threat model.

**Disk shows `/` only.** Other mounts are not reported.

**No tunnel previews.** The Tunnels panel shows health and a link, not a live
preview of each site. Embedding third-party pages in a root-equivalent admin panel
is a bad trade, and the dashboard's CSP blocks framing outright.
