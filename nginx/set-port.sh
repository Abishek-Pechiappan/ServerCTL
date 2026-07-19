#!/usr/bin/env bash
#
# Change the ports ServerCTL uses.
#
#   ./nginx/set-port.sh --listen 8080          # nginx serves on 8080
#   ./nginx/set-port.sh --app 4000             # app moves to 4000
#   ./nginx/set-port.sh --listen 8080 --app 4000
#   ./nginx/set-port.sh --show                 # print current values
#
# There are two separate ports and they are easy to confuse:
#
#   --listen  the port nginx accepts browser traffic on        (default 80)
#   --app     the port the container listens on internally     (default 3000)
#
# nginx proxies --listen to --app, so they must agree. That is the whole reason
# this script exists: editing nginx/serverctl.conf by hand leaves the app on its
# old port and produces a 502 that looks like the app crashed.
#
# If you are not using nginx, only --app matters.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONF="$ROOT/nginx/serverctl.conf"
ENV_FILE="$ROOT/backend/.env"

DEFAULT_LISTEN=80
DEFAULT_APP=3000

die() { printf 'error: %s\n' "$1" >&2; exit 1; }

usage() {
    sed -n '3,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

# Reads the port nginx currently proxies to, so --listen alone does not clobber
# a previously set --app value (and vice versa).
current_listen() {
    grep -oP '^\s*listen\s+\K[0-9]+' "$CONF" 2>/dev/null | head -1 || true
}

current_app() {
    if [ -f "$ENV_FILE" ] && grep -q '^SERVERCTL_PORT=' "$ENV_FILE"; then
        grep '^SERVERCTL_PORT=' "$ENV_FILE" | head -1 | cut -d= -f2
    else
        grep -oP 'proxy_pass\s+http://127\.0\.0\.1:\K[0-9]+' "$CONF" 2>/dev/null | head -1 || true
    fi
}

valid_port() {
    [[ "$1" =~ ^[0-9]+$ ]] && [ "$1" -ge 1 ] && [ "$1" -le 65535 ]
}

# Warns rather than fails: the port may be held by ServerCTL's own container
# from a previous run, which `docker compose up -d` will replace anyway.
warn_if_busy() {
    local port="$1" label="$2"
    if command -v ss >/dev/null 2>&1 && ss -tln 2>/dev/null | grep -qE "[:.]${port}\s"; then
        printf 'warning: something is already listening on %s (%s)\n' "$port" "$label" >&2
        printf '         check with:  sudo ss -tlnp | grep %s\n' "$port" >&2
    fi
}

LISTEN=""
APP=""
SHOW=0

while [ $# -gt 0 ]; do
    case "$1" in
        --listen) [ $# -ge 2 ] || die "--listen needs a port"; LISTEN="$2"; shift 2 ;;
        --app)    [ $# -ge 2 ] || die "--app needs a port";    APP="$2";    shift 2 ;;
        --show)   SHOW=1; shift ;;
        -h|--help) usage 0 ;;
        *) die "unknown option: $1  (try --help)" ;;
    esac
done

[ -f "$CONF" ] || die "not found: $CONF"

if [ "$SHOW" = 1 ]; then
    printf 'listen (nginx) : %s\n' "$(current_listen || echo "$DEFAULT_LISTEN")"
    printf 'app (container): %s\n' "$(current_app || echo "$DEFAULT_APP")"
    exit 0
fi

if [ -z "$LISTEN" ] && [ -z "$APP" ]; then
    usage 1
fi

for pair in "listen:$LISTEN" "app:$APP"; do
    name="${pair%%:*}"; value="${pair#*:}"
    [ -n "$value" ] || continue
    valid_port "$value" || die "--$name must be a port between 1 and 65535, got '$value'"
done

# Fill in whichever side was not passed, so one flag never resets the other.
[ -n "$LISTEN" ] || LISTEN="$(current_listen)"; LISTEN="${LISTEN:-$DEFAULT_LISTEN}"
[ -n "$APP" ]    || APP="$(current_app)";       APP="${APP:-$DEFAULT_APP}"

[ "$LISTEN" != "$APP" ] || die "--listen and --app must differ (both are $LISTEN); nginx would proxy to itself"

warn_if_busy "$LISTEN" "nginx listen port"
warn_if_busy "$APP" "app port"

# --- nginx config -----------------------------------------------------------
# Matches whatever port is currently there rather than a literal 80/3000, so the
# script is idempotent and safe to run repeatedly.
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
sed -E \
    -e "s|^(\s*listen\s+)[0-9]+(\s*;)|\1${LISTEN}\2|" \
    -e "s|^(\s*listen\s+\[::\]:)[0-9]+(\s*;)|\1${LISTEN}\2|" \
    -e "s|(proxy_pass\s+http://127\.0\.0\.1:)[0-9]+|\1${APP}|" \
    "$CONF" > "$tmp"
mv "$tmp" "$CONF"
trap - EXIT

# --- app port ---------------------------------------------------------------
# Written to backend/.env because docker-compose passes that file to the
# container, and main.py reads SERVERCTL_PORT from the environment.
if [ -f "$ENV_FILE" ]; then
    if grep -q '^SERVERCTL_PORT=' "$ENV_FILE"; then
        sed -i -E "s|^SERVERCTL_PORT=.*|SERVERCTL_PORT=${APP}|" "$ENV_FILE"
    else
        # A file not ending in a newline would otherwise get SERVERCTL_PORT
        # glued onto the end of the last line, silently corrupting whatever
        # value was there (JWT_SECRET_KEY, typically).
        [ -s "$ENV_FILE" ] && [ -n "$(tail -c 1 "$ENV_FILE")" ] && printf '\n' >> "$ENV_FILE"
        printf 'SERVERCTL_PORT=%s\n' "$APP" >> "$ENV_FILE"
    fi
    env_note="backend/.env updated"
else
    env_note="backend/.env does not exist yet — run 'python3 setup.py' first, then re-run this script"
fi

cat <<EOF

  nginx listens on : ${LISTEN}
  app listens on   : ${APP}

  nginx/serverctl.conf updated
  ${env_note}

Apply the change:

  docker compose up -d                 # restart the app on port ${APP}
EOF

if command -v nginx >/dev/null 2>&1; then
    cat <<EOF
  sudo nginx -t && sudo systemctl reload nginx
EOF
else
    cat <<EOF

nginx is not installed, so only the app port applies. Reach it directly at
http://127.0.0.1:${APP} or point cloudflared at that port.
EOF
fi
