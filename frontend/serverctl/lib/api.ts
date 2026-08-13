// Relative by default: the backend serves this bundle and the API from the same
// origin, so requests are same-origin and never trigger a CORS preflight. The
// /api prefix keeps the API clear of the static routes — without it, POST /login
// (the endpoint) would collide with /login (the page).
//
// Override only if you split the two back onto separate hosts, in which case the
// backend needs a matching ALLOWED_ORIGINS entry.
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "/api";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("token");
}

export function setToken(token: string) {
  localStorage.setItem("token", token);
  emitTokenChange();
}

export function clearToken() {
  localStorage.removeItem("token");
  emitTokenChange();
}

// ---- token presence as an external store ------------------------------------
//
// Exposed this way so components can read "am I signed in?" through
// useSyncExternalStore instead of setting state from inside an effect. That
// matters for more than lint: localStorage does not exist while the page is
// prerendered, so the value genuinely is unknown until hydration finishes, and
// getServerSnapshot returning null models that honestly rather than guessing and
// producing a hydration mismatch.
const tokenListeners = new Set<() => void>();

function emitTokenChange() {
  tokenListeners.forEach((listener) => listener());
}

export function subscribeToken(onChange: () => void): () => void {
  tokenListeners.add(onChange);
  // A "storage" event only fires for *other* tabs, which is exactly the case
  // local calls cannot cover: log out in one tab and this one follows.
  window.addEventListener("storage", onChange);
  return () => {
    tokenListeners.delete(onChange);
    window.removeEventListener("storage", onChange);
  };
}

/** Whether a token is present. A stable primitive, as getSnapshot requires. */
export function getHasToken(): boolean {
  return getToken() !== null;
}

/** null = "not known yet", used during prerender and hydration. */
export function getHasTokenServer(): null {
  return null;
}

/** Turns any error body into something worth showing a person.
 *
 *  FastAPI's `detail` is a plain string for our own HTTPExceptions but an *array
 *  of field errors* for a 422 from request validation. Passing that straight to
 *  `new Error()` rendered a literal "[object Object]" on the login form.
 */
function errorMessage(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const first = detail[0] as { msg?: unknown; loc?: unknown } | undefined;
    const field = Array.isArray(first?.loc) ? first.loc[first.loc.length - 1] : undefined;
    if (typeof first?.msg === "string") {
      return field ? `${String(field)}: ${first.msg}` : first.msg;
    }
  }
  return fallback;
}

export async function login(username: string, password: string): Promise<string> {
  const res = await fetch(`${API_BASE_URL}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    // Deliberately not distinguishing "no such user" from "wrong password" — the
    // server already returns one message for both, and this must not undo that.
    throw new Error(errorMessage(body, res.status === 429
      ? "Too many attempts. Try again later."
      : "Login failed"));
  }

  const data = await res.json();
  return data.access_token as string;
}

// trailingSlash: true in next.config.ts, so the exported page is /login/.
const LOGIN_PATH = "/login/";

export async function apiFetch(path: string, options: RequestInit = {}) {
  const token = getToken();
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });

  // Tokens last an hour, so this is a routine event, not an edge case. Every
  // caller in the dashboard swallows fetch errors to keep one dead panel from
  // taking down the page — which meant an expired session showed no error and no
  // login prompt, just a dashboard frozen on stale numbers. Handle it here, once,
  // where the status code is still visible.
  if (res.status === 401) {
    clearToken();
    if (typeof window !== "undefined" && window.location.pathname !== LOGIN_PATH) {
      // Full navigation rather than a router push: it also discards the stale
      // in-memory snapshot the dashboard is holding.
      window.location.replace(LOGIN_PATH);
    }
    throw new Error("Session expired — please sign in again");
  }

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(errorMessage(body, `Request failed: ${res.status}`));
  }

  return res.json();
}
