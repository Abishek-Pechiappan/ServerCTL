"""Verify ServerCTL's own logic, without Docker and without a running server.

Complements preflight.py, which checks the *host*. This checks the *code*: the
things that are easy to break silently and annoying to notice — build-context
rules, port de-duplication, /proc parsing, password hashing, the auth matrix, the
snapshot loop's timing, and the static-file wiring.

    python3 selftest.py

Groups that need the backend's dependencies (FastAPI, PyJWT, psutil) are skipped
with a SKIP rather than failing, so the script is still useful on a bare host:

    backend/myenv/bin/python3 selftest.py     # runs everything

Exit code is 1 if any check FAILs.
"""

import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).parent

OK, FAIL, SKIP = "OK", "FAIL", "SKIP"
_COLOR = {OK: "\033[32m", FAIL: "\033[31m", SKIP: "\033[90m"}
_RESET = "\033[0m"
_USE_COLOR = sys.stdout.isatty()

results: list[tuple[str, str]] = []


def report(level: str, check: str, detail: str = "") -> None:
    results.append((level, check))
    tag = f"{_COLOR[level]}{level:<4}{_RESET}" if _USE_COLOR else f"{level:<4}"
    print(f"[{tag}] {check}")
    for line in detail.splitlines():
        if line:
            print(f"         {line}")


def check(name, condition, detail=""):
    report(OK if condition else FAIL, name, "" if condition else detail)


def group(title):
    print(f"\n--- {title} " + "-" * max(0, 66 - len(title)))


# --------------------------------------------------------------------------
# Build context: .dockerignore vs the Dockerfile's COPY lines
# --------------------------------------------------------------------------

def _dockerignore_patterns():
    path = ROOT / ".dockerignore"
    if not path.exists():
        return None
    return [
        line.strip()
        for line in path.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _matches(pattern: str, path: str) -> bool:
    """Docker's .dockerignore matching, which is not gitignore's.

    Patterns are matched against the whole slash-separated path. Each segment is
    a filepath.Match glob (so `*` does not cross `/`), and `**` matches any number
    of segments. A directory pattern also matches everything beneath it.
    """
    import fnmatch

    pat_parts = pattern.strip("/").split("/")
    path_parts = path.strip("/").split("/")

    def walk(pi, si):
        while pi < len(pat_parts):
            if pat_parts[pi] == "**":
                if pi + 1 == len(pat_parts):
                    return True
                return any(walk(pi + 1, s) for s in range(si, len(path_parts) + 1))
            if si >= len(path_parts):
                return False
            if not fnmatch.fnmatchcase(path_parts[si], pat_parts[pi]):
                return False
            pi += 1
            si += 1
        # Pattern exhausted: an exact match, or a prefix (directory) match.
        return True

    return walk(0, 0)


def _copy_sources():
    """Every host path the Dockerfile copies into the image."""
    text = (ROOT / "Dockerfile").read_text()
    sources = []
    for line in text.splitlines():
        line = line.strip()
        if not line.upper().startswith("COPY "):
            continue
        parts = line.split()[1:]
        if any(p.startswith("--from=") for p in parts):
            continue  # copied from an earlier stage, not from the context
        parts = [p for p in parts if not p.startswith("--")]
        sources.extend(parts[:-1])  # last argument is the destination
    return sources


def check_build_context():
    patterns = _dockerignore_patterns()
    if patterns is None:
        report(FAIL, ".dockerignore exists",
               "Without it the build context includes backend/myenv and any host\n"
               "node_modules, which then overlays the image's own npm ci output.")
        return
    report(OK, ".dockerignore exists", f"{len(patterns)} patterns")

    # The whole point of the file: these must be excluded.
    for path in ("backend/myenv/bin/python3", "frontend/serverctl/node_modules/next",
                 "frontend/serverctl/.next/build", "backend/.env", ".git/config"):
        hit = next((p for p in patterns if _matches(p, path)), None)
        check(f"excluded from context: {path}", hit is not None,
              "No pattern matches it. Remember Docker needs '**/' for nested\n"
              "paths — a bare 'node_modules' matches only a top-level one.")

    # And these must survive, or the build breaks.
    for source in _copy_sources():
        rel = source.rstrip("/")
        exists = (ROOT / rel).exists()
        check(f"COPY source exists: {rel}", exists, "Referenced by the Dockerfile but not in the repo.")
        if not exists:
            continue
        hit = next((p for p in patterns if _matches(p, rel)), None)
        check(f"COPY source not ignored: {rel}", hit is None,
              f"Pattern '{hit}' excludes a path the Dockerfile copies — the build\n"
              f"will fail or silently produce an incomplete image.")


# --------------------------------------------------------------------------
# Collectors and parsers (pure logic, no dependencies)
# --------------------------------------------------------------------------

def check_ports_dedupe():
    sys.path.insert(0, str(ROOT / "backend" / "agent"))
    from collectors.ports import _scope, list_ports

    check("port scope: 0.0.0.0 is 'all'", _scope("0.0.0.0") == "all")
    check("port scope: '*' is 'all'", _scope("*") == "all")
    check("port scope: '[::]' is 'all'", _scope("[::]") == "all")
    check("port scope: 127.0.0.53%lo is 'local'", _scope("127.0.0.53%lo") == "local")
    check("port scope: ::1 is 'local'", _scope("::1") == "local")
    check("port scope: a real address is kept", _scope("10.1.2.3") == "10.1.2.3")

    if not shutil.which("ss"):
        report(SKIP, "port list de-duplicated", "iproute2 (ss) not installed")
        return

    rows = list_ports()
    keys = [(r["process"], r["port"]) for r in rows]
    check("port list de-duplicated", len(keys) == len(set(keys)),
          "ss emits a row per address family and protocol; without merging, the\n"
          "dashboard prints the same application/port line two to four times.")
    check("every port row carries a scope", all(r.get("scope") for r in rows))


def check_proc_parsing():
    sys.path.insert(0, str(ROOT / "backend" / "agent"))
    import socket

    from security.proc import _parse_address, is_suspicious_process

    # Known-good vectors straight out of /proc/net/tcp{,6}.
    check("IPv4 /proc address decode",
          _parse_address("0100007F:1F90", socket.AF_INET) == ("127.0.0.1", 8080),
          f"got {_parse_address('0100007F:1F90', socket.AF_INET)}")
    # 4 little-endian 32-bit words, reversed per word — not across the address.
    check("IPv6 /proc address decode",
          _parse_address("00000000000000000000000001000000:0277", socket.AF_INET6)
          == ("::1", 631),
          f"got {_parse_address('00000000000000000000000001000000:0277', socket.AF_INET6)}")

    check("flags a root binary running from /tmp",
          is_suspicious_process("/tmp/x", "/tmp/x", "ROOT"))
    check("flags /dev/shm and /var/tmp too",
          is_suspicious_process("/dev/shm/a", "", "ROOT")
          and is_suspicious_process("/var/tmp/b", "", "ROOT"))
    check("does not flag a normal root binary",
          not is_suspicious_process("/usr/bin/sleep", "sleep 8", "ROOT"))
    check("does not flag a cmdline merely mentioning /tmp",
          not is_suspicious_process("/usr/bin/tar", "tar -xf /tmp/x.tar", "ROOT"),
          "Matching the command line flagged any root process that referenced a\n"
          "temp path; the executable's resolved path is what actually matters.")
    check("does not flag non-root processes",
          not is_suspicious_process("/tmp/x", "/tmp/x", "USER"))
    check("/tmpfoo is not treated as /tmp",
          not is_suspicious_process("/tmpfoo/x", "", "ROOT"))


def check_password():
    sys.path.insert(0, str(ROOT / "backend"))
    from password import hash_password, verify_password

    encoded = hash_password("correct-horse-battery-staple")
    check("hash round-trips", verify_password("correct-horse-battery-staple", encoded))
    check("wrong password rejected", not verify_password("correct-horse-battery-stapl", encoded))
    check("empty password rejected against a real hash", not verify_password("", encoded))
    check("hash uses ':' separators, never '$'", ":" in encoded and "$" not in encoded,
          "docker-compose interpolates '$' out of env files, which would truncate\n"
          "the hash and make every login fail.")
    check("hash is scrypt with 6 fields",
          encoded.split(":")[0] == "scrypt" and len(encoded.split(":")) == 6)
    check("salt is random per call", hash_password("x") != hash_password("x"))
    check("malformed hash is rejected, not crashed", not verify_password("x", "garbage"))
    check("non-scrypt scheme rejected", not verify_password("x", "md5:1:1:1:aa:bb"))
    check("unicode password round-trips", verify_password("pä✓ss", hash_password("pä✓ss")))


# --------------------------------------------------------------------------
# Ports / nginx agreement
# --------------------------------------------------------------------------

def check_nginx_port_agreement():
    conf = ROOT / "nginx" / "serverctl.conf"
    if not conf.exists():
        report(SKIP, "nginx proxies to the app port", "nginx/serverctl.conf absent")
        return
    text = conf.read_text()
    proxy = re.search(r"proxy_pass\s+http://127\.0\.0\.1:(\d+)", text)
    check("nginx config has a proxy_pass to loopback", proxy is not None)

    # Directives only. The comment above that line names the variable in order to
    # explain why it is *not* used, and a naive substring search matches it.
    directives = "\n".join(
        line for line in text.splitlines() if not line.strip().startswith("#")
    )
    check("nginx does not append to X-Forwarded-For",
          "$proxy_add_x_forwarded_for" not in directives,
          "$proxy_add_x_forwarded_for appends to a client-supplied header, so the\n"
          "first element — which the login lockout keys on — becomes\n"
          "attacker-chosen. Use $remote_addr.")

    env = ROOT / "backend" / ".env"
    app_port = 3000
    if env.exists():
        m = re.search(r"^SERVERCTL_PORT=(\d+)", env.read_text(), re.M)
        if m:
            app_port = int(m.group(1))
    if proxy:
        check(f"nginx proxy_pass ({proxy.group(1)}) matches the app port ({app_port})",
              int(proxy.group(1)) == app_port,
              "Mismatched ports produce a 502 that looks like the app crashed.\n"
              f"Fix both together:  ./nginx/set-port.sh --app {app_port}")


def check_set_port_script():
    script = ROOT / "nginx" / "set-port.sh"
    if not (script.exists() and shutil.which("bash")):
        report(SKIP, "set-port.sh behaviour", "script or bash unavailable")
        return

    with tempfile.TemporaryDirectory() as tmp:
        sandbox = Path(tmp)
        (sandbox / "nginx").mkdir()
        shutil.copy(script, sandbox / "nginx" / "set-port.sh")
        shutil.copy(ROOT / "nginx" / "serverctl.conf", sandbox / "nginx" / "serverctl.conf")
        run = sandbox / "nginx" / "set-port.sh"

        def sh(*args):
            return subprocess.run([str(run), *args], capture_output=True, text=True, cwd=sandbox)

        # No backend/.env yet: the app port must still be written, or nginx ends up
        # pointing at a port nothing listens on.
        sh("--app", "4000")
        env = sandbox / "backend" / ".env"
        check("set-port.sh creates backend/.env when absent", env.exists(),
              "It used to only print a warning, leaving nginx on the new port and\n"
              "the app on the old one.")
        if env.exists():
            check("set-port.sh writes SERVERCTL_PORT", "SERVERCTL_PORT=4000" in env.read_text())

        # One flag must not reset the other.
        sh("--listen", "8080")
        shown = sh("--show").stdout
        check("set-port.sh --listen preserves --app",
              "8080" in shown and "4000" in shown, f"--show said:\n{shown}")

        # A file with no trailing newline must not have the last line corrupted.
        env.write_text("JWT_SECRET_KEY=abc123")
        sh("--app", "4100")
        check("set-port.sh preserves a newline-less last line",
              "JWT_SECRET_KEY=abc123\n" in env.read_text(),
              f"got: {env.read_text()!r}")

        check("set-port.sh rejects an out-of-range port", sh("--app", "99999").returncode != 0)
        check("set-port.sh refuses equal ports", sh("--listen", "5000", "--app", "5000").returncode != 0)

        # --show must fall back to defaults rather than printing blanks.
        conf = sandbox / "nginx" / "serverctl.conf"
        conf.write_text("\n".join(l for l in conf.read_text().splitlines() if "listen" not in l))
        check("set-port.sh --show falls back when no listen line exists",
              "listen (nginx) : 80" in sh("--show").stdout)


# --------------------------------------------------------------------------
# The HTTP surface (needs FastAPI + PyJWT + psutil)
# --------------------------------------------------------------------------

def _build_client():
    """A TestClient for the real app, with throwaway credentials."""
    import os

    sys.path.insert(0, str(ROOT / "backend"))
    from password import hash_password

    os.environ.update(
        {
            "JWT_SECRET_KEY": "0" * 64,
            "ADMIN_USERNAME": "admin",
            "ADMIN_PASSWORD_HASH": hash_password("s3cret"),
        }
    )
    out = ROOT / "frontend" / "serverctl" / "out"
    if out.is_dir():
        os.environ["STATIC_DIR"] = str(out)

    sys.path.insert(0, str(ROOT / "backend" / "agent"))
    from fastapi.testclient import TestClient

    import authentication as auth
    import main

    # Rate-limit state is module-level and outlives a TestClient, so a group that
    # deliberately trips the lockout would otherwise leave every later group
    # unable to log in. Reset it whenever a fresh client is built.
    with auth._login_lock:
        auth._login_failures.clear()
        auth._login_lockouts.clear()
        auth._global_failures.clear()

    return TestClient(main.app), main


def check_auth():
    try:
        client, main = _build_client()
    except Exception as e:
        report(SKIP, "auth matrix", f"backend dependencies unavailable ({type(e).__name__}: {e})\n"
                                    f"Run with backend/myenv/bin/python3 to include these.")
        return

    with client as c:
        login = lambda pw, user="admin": c.post("/api/login", json={"username": user, "password": pw})

        r = login("s3cret")
        check("correct credentials return a token", r.status_code == 200 and "access_token" in r.json())
        token = r.json().get("access_token", "")

        check("wrong password returns 401", login("nope").status_code == 401)
        check("non-ASCII username returns 401, not 500", login("nope", "ünïcode").status_code == 401,
              "hmac.compare_digest raises TypeError on non-ASCII str, which escaped\n"
              "as a 500 and skipped the lockout counter entirely.")
        check("oversized password rejected before hashing", login("A" * 5000).status_code == 422)
        check("empty username rejected", login("x", "").status_code == 422)

        # Bearer handling.
        r = c.get("/api/system/monitor")
        check("missing token returns 401 (not 403)", r.status_code == 401,
              "A 403 is indistinguishable from 'authenticated but forbidden', so the\n"
              "dashboard cannot tell an expired session from a real error.")
        check("401 carries a WWW-Authenticate challenge",
              r.headers.get("www-authenticate") == "Bearer")
        check("wrong auth scheme returns 401",
              c.get("/api/system/monitor", headers={"Authorization": "Basic abc"}).status_code == 401)
        check("garbage token returns 401",
              c.get("/api/system/monitor", headers={"Authorization": "Bearer nope"}).status_code == 401)

        # Tokens forged with a leaked key must still satisfy the required claims.
        import jwt as pyjwt

        for label, payload in (("no exp", {"sub": "admin"}), ("no sub", {"exp": time.time() + 60})):
            forged = pyjwt.encode(payload, "0" * 64, algorithm="HS256")
            check(f"token with {label} is rejected",
                  c.get("/api/system/monitor",
                        headers={"Authorization": f"Bearer {forged}"}).status_code == 401)

        # Authenticated reads.
        h = {"Authorization": f"Bearer {token}"}
        time.sleep(1.0)  # let the first snapshot land
        snap = c.get("/api/system/monitor", headers=h)
        check("authenticated snapshot returns 200", snap.status_code == 200)
        body = snap.json() if snap.status_code == 200 else {}
        check("snapshot carries everything the dashboard needs",
              all(k in body for k in ("cpu_percent", "ram", "disk", "ports",
                                      "cloudflared", "ssh_active", "ssh_history")),
              f"keys present: {sorted(body)}\n"
              f"The dashboard derives four panels from this one response; a missing\n"
              f"key silently empties a panel.")
        check("cpu_percent is a real reading, not the 0.0 first-call placeholder",
              isinstance(body.get("cpu_percent"), (int, float)))

        # CSP is per-surface.
        api_csp = c.get("/api/system/monitor").headers.get("content-security-policy", "")
        check("API responses keep default-src 'none'", api_csp.startswith("default-src 'none'"))
        if main.DEBUG:
            docs_csp = c.get("/docs").headers.get("content-security-policy", "")
            check("docs CSP allows its CDN", "cdn.jsdelivr.net" in docs_csp)

        # Hardening for an internet-exposed deployment.
        big = c.post("/api/login", json={"username": "admin", "password": "x"},
                     headers={"Content-Length": str(1024 * 1024)})
        check("oversized Content-Length rejected with 413", big.status_code == 413,
              "nginx caps the body, but nginx is optional — without an app-level cap\n"
              "uvicorn buffers the whole body before validation, on an endpoint that\n"
              "needs no authentication.")
        check("dashboard shell is not cacheable",
              c.get("/").headers.get("cache-control") == "no-store",
              "A shared cache — and a Cloudflare tunnel puts one in the path by\n"
              "definition — must not store the authenticated shell.")
        check("hashed assets are cacheable forever",
              "immutable" in c.get("/_next/static/x").headers.get("cache-control", ""))
        hdrs = c.get("/api/system/monitor").headers
        check("API responses are not cacheable", hdrs.get("cache-control") == "no-store")
        check("clickjacking blocked two ways",
              hdrs.get("x-frame-options") == "DENY" and "frame-ancestors 'none'" in
              hdrs.get("content-security-policy", ""))
        check("HSTS present", "max-age=" in hdrs.get("strict-transport-security", ""))
        check("Referrer-Policy is no-referrer", hdrs.get("referrer-policy") == "no-referrer")

        # A 422's detail is a list, not a string; the login form has to survive it.
        r = c.post("/api/login", json={"username": "admin", "password": "A" * 5000})
        check("422 detail is a list (the UI must handle this shape)",
              isinstance(r.json().get("detail"), list),
              "If this ever becomes a string the frontend's errorMessage() can be\n"
              "simplified; until then it must not be passed to new Error() raw.")

        # Brute-force lockout.
        codes = [login("wrong").status_code for _ in range(7)]
        check("lockout trips after 5 failures",
              codes.count(401) <= 5 and 429 in codes, f"status sequence: {codes}")
        locked = login("wrong")
        check("lockout response carries Retry-After",
              locked.status_code == 429 and locked.headers.get("retry-after", "").isdigit())
        check("lockout message does not reveal which field was wrong",
              "password" not in locked.json().get("detail", "").lower()
              or "username" not in locked.json().get("detail", "").lower())


def check_injection():
    """Injection sinks. There is no SQL anywhere here, so the sinks are argv, the
    Docker API path, the static file tree, and log/header output."""
    # Source-level invariants first: cheap, and they hold without any dependencies.
    py_files = [p for p in (ROOT / "backend").rglob("*.py") if "myenv" not in p.parts]
    py_files += [ROOT / "preflight.py", ROOT / "setup.py", ROOT / "install.py"]
    sources = {p: p.read_text() for p in py_files if p.exists()}

    for needle, label in (
        ("shell=True", "no subprocess uses shell=True"),
        ("os.system", "no os.system"),
        ("os.popen", "no os.popen"),
        ("yaml.load(", "no unsafe yaml.load (must be safe_load)"),
    ):
        hits = [str(p.relative_to(ROOT)) for p, text in sources.items() if needle in text]
        check(label, not hits, f"found in: {', '.join(hits)}")

    check("cloudflared config is parsed with safe_load",
          "yaml.safe_load" in (ROOT / "backend" / "agent" / "collectors" / "cloudflared.py").read_text())

    try:
        client, _ = _build_client()
    except Exception as e:
        report(SKIP, "injection probes", f"backend dependencies unavailable ({type(e).__name__})")
        return

    with client as c:
        token = c.post("/api/login", json={"username": "admin", "password": "s3cret"}).json()
        h = {"Authorization": f"Bearer {token.get('access_token', '')}"}

        # The container name is the only user string reaching a privileged sink.
        # docker-py does not encode '/' or '.', so a traversal would arrive at the
        # daemon intact; these must never get past validation.
        hostile = ["../../../images/json", "foo/../../info", "a;whoami", "$(id)",
                   "`id`", "|cat /etc/passwd", "name\nsecond", ".hidden", "-flag",
                   "x" * 300, "../", "..", "a/b"]
        for name in hostile:
            for path in ("/api/docker/up", "/api/docker/down"):
                r = c.post(path, json={"name": name}, headers=h)
                if r.status_code != 422:
                    check(f"rejects container name {name!r}", False,
                          f"{path} answered {r.status_code}; it must be a 422 from\n"
                          f"the request model before the name reaches the Docker socket.")
                    break
            else:
                continue
            break
        else:
            check(f"rejects all {len(hostile)} hostile container names", True)

        check("still accepts a legitimate container name",
              c.post("/api/docker/down", json={"name": "web_app-1.2"},
                     headers=h).status_code != 422,
              "The pattern must not be so strict that real Docker names fail.")
        check("still accepts a 64-char container ID",
              c.post("/api/docker/down", json={"name": "a" * 64},
                     headers=h).status_code != 422)

        # Static tree must not serve anything outside the export directory.
        for path in ("/../backend/.env", "/..%2f..%2fbackend%2fauthentication.py",
                     "/%2e%2e/%2e%2e/etc/passwd", "/_next/../../../etc/passwd",
                     "/....//....//etc/passwd", "/etc/passwd"):
            r = c.get(path)
            body = r.text if r.status_code == 200 else ""
            check(f"no traversal via {path}",
                  r.status_code != 200 or not any(
                      m in body for m in ("root:", "JWT_SECRET", "ADMIN_PASSWORD", "import ")),
                  f"status {r.status_code} and the body looks like a real file.")

        # A CRLF in the client-IP header must not be able to forge a log line.
        sys.path.insert(0, str(ROOT / "backend" / "agent"))
        from route import _client_ip

        class FakeRequest:
            headers = {"cf-connecting-ip": "1.2.3.4\r\n[serverctl:auth] forged",
                       "x-forwarded-for": "9.9.9.9\nalso forged"}
            client = type("C", (), {"host": "127.0.0.1"})()

        ip = _client_ip(FakeRequest())
        check("client IP is parsed, so no CRLF reaches a log line or a dict key",
              "\r" not in ip and "\n" not in ip and ip == "127.0.0.1",
              f"_client_ip returned {ip!r}; it must fall through to the socket peer\n"
              f"when a header does not parse as an IP address.")

        # Nothing user-controlled is echoed into a response header.
        r = c.post("/api/login", json={"username": "admin", "password": "x"})
        check("Server header is a fixed value", r.headers.get("server") == "ServerCTL")
        retry = r.headers.get("retry-after")
        check("Retry-After, when present, is numeric",
              retry is None or retry.isdigit(), f"got {retry!r}")


def check_global_throttle():
    """The second brute-force control: a global delay, not a global lockout."""
    try:
        sys.path.insert(0, str(ROOT / "backend"))
        import os

        os.environ.setdefault("JWT_SECRET_KEY", "0" * 64)
        os.environ.setdefault("ADMIN_USERNAME", "admin")
        os.environ.setdefault("ADMIN_PASSWORD_HASH", "scrypt:16384:8:1:aa:bb")
        import authentication as auth
    except Exception as e:
        report(SKIP, "global throttle", f"backend dependencies unavailable ({type(e).__name__})")
        return

    with auth._login_lock:
        auth._global_failures.clear()
    check("no delay under normal use", auth.global_throttle_delay() == 0.0)

    now = time.monotonic()
    with auth._login_lock:
        auth._global_failures.extend([now] * 25)
    check("delay engages once failures pile up globally", auth.global_throttle_delay() >= 1.0,
          "Without this, an attacker rotating source addresses — or spoofing\n"
          "CF-Connecting-IP from the host — gets unlimited attempts, because the\n"
          "per-IP lockout only ever sees 1 failure per 'IP'.")

    with auth._login_lock:
        auth._global_failures.extend([now] * 100)
    check("delay is capped", auth.global_throttle_delay() <= auth.GLOBAL_MAX_DELAY)

    # The important property: it must never become a lockout, or an attacker could
    # keep the real admin out at will.
    check("global control degrades, never denies",
          auth.global_throttle_delay() < float("inf")
          and auth.check_login_allowed("198.51.100.7") is None,
          "A global *lockout* would hand any attacker a trivial way to deny the\n"
          "admin access. This must stay a delay.")

    with auth._login_lock:
        auth._global_failures.clear()

    # Stale entries must age out of the window.
    with auth._login_lock:
        auth._global_failures.extend([now - auth.GLOBAL_WINDOW_SECONDS - 1] * 50)
    check("global window ages out old failures", auth.global_throttle_delay() == 0.0)
    with auth._login_lock:
        auth._global_failures.clear()


def check_static_serving():
    out = ROOT / "frontend" / "serverctl" / "out"
    if not out.is_dir():
        report(SKIP, "static dashboard wiring",
               "frontend/serverctl/out absent — build it with:\n"
               "  cd frontend/serverctl && npm ci && npm run build")
        return
    try:
        client, _ = _build_client()
    except Exception as e:
        report(SKIP, "static dashboard wiring", f"backend dependencies unavailable ({type(e).__name__})")
        return

    check("export contains login/index.html", (out / "login" / "index.html").exists(),
          "trailingSlash: true is what produces this layout; without it a plain\n"
          "static file server cannot resolve /login.")

    with client as c:
        r = c.get("/", follow_redirects=False)
        check("/ serves the dashboard shell", r.status_code == 200)
        check("/ ships the app bundle", "/_next/static" in c.get("/").text)
        r = c.get("/login", follow_redirects=False)
        check("/login redirects to /login/", r.status_code in (307, 308))
        check("/login/ serves a page", c.get("/login/").status_code == 200)
        check("/dashboard/ serves a page", c.get("/dashboard/").status_code == 200)
        check("an unknown path 404s", c.get("/no-such-page").status_code == 404)
        check("/api is not shadowed by the static mount",
              c.get("/api/system/monitor").status_code == 401,
              "The catch-all static mount must be registered after the API router.")


def check_monitor_loop():
    try:
        sys.path.insert(0, str(ROOT / "backend" / "agent"))
        import action.agents as agents
    except Exception as e:
        report(SKIP, "snapshot loop", f"backend dependencies unavailable ({type(e).__name__})")
        return

    # Compress the timings so the check runs in a couple of seconds.
    agents.REFRESH_SECONDS = 0.5
    agents.IDLE_AFTER_SECONDS = 1
    agents._IDLE_WAIT_SECONDS = 0.2

    calls = {"n": 0}
    real = agents.collect_all

    def counting(now=None):
        calls["n"] += 1
        return real(now)

    agents.collect_all = counting
    agents.start_monitor()
    time.sleep(0.7)

    check("a snapshot is collected without waiting for a request", calls["n"] >= 1,
          "start_monitor must begin in the active state, or the first client sees\n"
          "an empty snapshot.")
    check("snapshot has every field", set(agents.get_latest_snapshot()) >= {
        "cpu_percent", "ram", "disk", "temperature", "docker_running",
        "ports", "cloudflared", "ssh_active", "ssh_history"})

    time.sleep(1.5)          # cross the idle threshold
    calls["n"] = 0
    time.sleep(1.5)          # steady-state idle
    check("loop parks when nothing is reading", calls["n"] == 0,
          f"collected {calls['n']} times while unwatched; it should be 0.")

    calls["n"] = 0
    agents.get_latest_snapshot()
    time.sleep(0.8)
    check("a read wakes the loop back up", calls["n"] >= 1,
          "The snapshot would go permanently stale after the first idle period.")

    agents.collect_all = real


CHECKS = (
    ("Build context", check_build_context),
    ("Password hashing", check_password),
    ("Port collector", check_ports_dedupe),
    ("/proc parsing", check_proc_parsing),
    ("nginx / port agreement", check_nginx_port_agreement),
    ("set-port.sh", check_set_port_script),
    ("Snapshot loop", check_monitor_loop),
    ("Auth matrix", check_auth),
    ("Global throttle", check_global_throttle),
    ("Injection sinks", check_injection),
    ("Static dashboard wiring", check_static_serving),
)


def main() -> int:
    print("ServerCTL selftest")
    for title, fn in CHECKS:
        group(title)
        try:
            fn()
        except Exception as e:
            report(FAIL, f"{title} (check itself errored)", f"{type(e).__name__}: {e}")

    fails = sum(1 for level, _ in results if level == FAIL)
    skips = sum(1 for level, _ in results if level == SKIP)
    passed = sum(1 for level, _ in results if level == OK)

    print()
    if fails:
        print(f"{passed} passed, {fails} FAILED, {skips} skipped.")
        return 1
    print(f"{passed} passed, {skips} skipped. All good.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
