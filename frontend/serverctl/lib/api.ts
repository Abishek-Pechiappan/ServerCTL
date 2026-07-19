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
}

export function clearToken() {
  localStorage.removeItem("token");
}

export async function login(username: string, password: string): Promise<string> {
  const res = await fetch(`${API_BASE_URL}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? "Login failed");
  }

  const data = await res.json();
  return data.access_token as string;
}

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

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `Request failed: ${res.status}`);
  }

  return res.json();
}
