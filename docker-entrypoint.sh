#!/usr/bin/env bash
#
# First-run bootstrap + container self-check, so a fresh clone starts with just
# `docker compose up`. Everything setup.py used to do by hand — hash a password,
# generate a JWT secret — happens here at boot instead, and the checks from
# preflight.py that make sense from inside the container run before the app does.
#
# Precedence for every secret is the same: an explicit value in backend/.env
# wins, then a value persisted in the data volume, then a freshly generated one
# (which is itself persisted, so it survives restarts).

set -euo pipefail

# password.py lives at /app; the app is launched from /app/agent. Overridable only
# so this script can be exercised outside a container — nothing sets PYTHONPATH in
# the image, so the default is what actually runs.
export PYTHONPATH="${PYTHONPATH:-/app}"
DATA_DIR="${SERVERCTL_DATA_DIR:-/data}"
mkdir -p "$DATA_DIR"

log() { printf '[serverctl] %s\n' "$1"; }
die() { printf '[serverctl] ERROR: %s\n' "$1" >&2; exit 1; }

hash_pw() {
    # Password is passed via the environment, never argv, so it does not leak
    # into the process list.
    _PW="$1" python -c 'import os; from password import hash_password; print(hash_password(os.environ["_PW"]))'
}

# --- JWT signing secret -----------------------------------------------------
if [ -z "${JWT_SECRET_KEY:-}" ]; then
    if [ -f "$DATA_DIR/jwt_secret" ]; then
        JWT_SECRET_KEY="$(cat "$DATA_DIR/jwt_secret")"
    else
        JWT_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
        (umask 077; printf '%s' "$JWT_SECRET_KEY" > "$DATA_DIR/jwt_secret")
        log "generated a new JWT signing secret (stored in the data volume)"
    fi
    export JWT_SECRET_KEY
fi

# --- admin credentials ------------------------------------------------------
if [ -n "${ADMIN_PASSWORD_HASH:-}" ]; then
    :  # already hashed (e.g. by setup.py) — use as-is
elif [ -n "${ADMIN_PASSWORD:-}" ]; then
    ADMIN_PASSWORD_HASH="$(hash_pw "$ADMIN_PASSWORD")"
    export ADMIN_PASSWORD_HASH
    log "hashed ADMIN_PASSWORD from backend/.env"
    # Lowercased so "Admin" is caught too. The empty case the previous list
    # included was unreachable — this branch already required a non-empty value —
    # and the password itself is deliberately not logged.
    case "$(printf '%s' "$ADMIN_PASSWORD" | tr '[:upper:]' '[:lower:]')" in
        admin|password|changeme|serverctl|123456)
            log "WARNING: that admin password is trivially guessable, and this account"
            log "         has effective root on the host. Set a long, unique"
            log "         ADMIN_PASSWORD in backend/.env, then:"
            log "           docker compose up -d --force-recreate" ;;
    esac
elif [ -f "$DATA_DIR/admin_password_hash" ]; then
    ADMIN_PASSWORD_HASH="$(cat "$DATA_DIR/admin_password_hash")"
    export ADMIN_PASSWORD_HASH
else
    _GEN="$(python -c 'import secrets; print(secrets.token_urlsafe(12))')"
    ADMIN_PASSWORD_HASH="$(hash_pw "$_GEN")"
    export ADMIN_PASSWORD_HASH
    (umask 077; printf '%s' "$ADMIN_PASSWORD_HASH" > "$DATA_DIR/admin_password_hash")
    printf '\n'
    log "=================================================================="
    log " No admin password was set, so one was generated for you:"
    log ""
    log "     username: ${ADMIN_USERNAME:-admin}"
    log "     password: ${_GEN}"
    log ""
    log " Shown only once. To choose your own, set ADMIN_PASSWORD in"
    log " backend/.env then:  docker compose up -d --force-recreate"
    log "=================================================================="
    printf '\n'
fi

export ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"

# The hash is all the app needs from here on, so drop the plaintext before exec'ing
# it. Otherwise ADMIN_PASSWORD stays in the app process's environment and is
# readable from /proc/<pid>/environ — which, under `pid: host`, means any root
# process on the machine. It remains visible in `docker inspect` (Compose puts
# env_file values in the container config), so this is defence in depth, not a
# substitute for treating backend/.env as a secret.
unset ADMIN_PASSWORD

# --- self-check (container-side only) ---------------------------------------
# Host-side checks — is Docker installed, are you in the docker group, is a
# stale container holding the port — cannot be answered from inside the
# container, so they stay in preflight.py as an optional pre-check on the host.
[ -d /app/static ] \
    || log "WARNING: /app/static missing — dashboard UI will not be served (API only)"

[ -S /var/run/docker.sock ] \
    || log "WARNING: /var/run/docker.sock not mounted — the Docker panel will be empty"

log "starting on 127.0.0.1:${SERVERCTL_PORT:-3000}"

exec "$@"
