"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";
import {
  apiFetch,
  clearToken,
  getHasToken,
  getHasTokenServer,
  subscribeToken,
} from "@/lib/api";
import SectionCard from "@/components/SectionCard";
import StatTile from "@/components/StatTile";
import Skeleton from "@/components/Skeleton";
import Button from "@/components/Button";
import AuroraBackground from "@/components/AuroraBackground";
import type { Point } from "@/components/MetricChart";

// ---- validated metric palette (dataviz-checked, light + dark) -----------------
const C = {
  cpu: "#059669",
  ram: "#c026d3",
  disk: "#0891b2",
  temp: "#d97706",
} as const;

const HISTORY_LEN = 40;

/** A snapshot list, or null while the first snapshot is still in flight.
 *
 * Each collector is wrapped server-side, so a field is `{error: "..."}` when that
 * one collector failed. Treat that as "nothing to show" so a single broken
 * collector empties its own panel instead of throwing during render.
 */
function listFrom<T>(value: T[] | { error: string } | undefined): T[] | null {
  if (value === undefined) return null;
  return Array.isArray(value) ? value : [];
}

const ic = (path: React.ReactNode) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    {path}
  </svg>
);
const Icons = {
  cpu: ic(<><rect x="4" y="4" width="16" height="16" rx="2" /><rect x="9" y="9" width="6" height="6" /><path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3" /></>),
  ram: ic(<><rect x="2" y="7" width="20" height="10" rx="2" /><path d="M6 7v10M10 7v10M14 7v10M18 7v10" /></>),
  disk: ic(<><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="2.5" /><path d="M16 8l-2.5 2.5" /></>),
  temp: ic(<path d="M14 14.76V5a2 2 0 0 0-4 0v9.76a4 4 0 1 0 4 0z" />),
  docker: ic(<><path d="M22 12.5c-1 .8-2.5.8-3.5 0" /><rect x="3" y="9" width="4" height="4" /><rect x="8" y="9" width="4" height="4" /><rect x="13" y="9" width="4" height="4" /><rect x="8" y="4" width="4" height="4" /><path d="M2 13c0 4 3 7 8 7 6 0 10-4 11-8" /></>),
  ports: ic(<><rect x="2" y="4" width="20" height="16" rx="2" /><path d="M2 9h20M6 4v5M12 4v5M18 4v5" /></>),
  tunnel: ic(<><path d="M2 12a10 10 0 0 1 20 0" /><path d="M6 12a6 6 0 0 1 12 0" /><path d="M10 12a2 2 0 0 1 4 0v8h-4z" /></>),
  ssh: ic(<><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M7 9l3 3-3 3M13 15h4" /></>),
  shield: ic(<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />),
  wrench: ic(<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.8 2.8-2-2 2.8-2.8z" />),
  play: ic(<polygon points="6 4 20 12 6 20 6 4" />),
  stop: ic(<rect x="6" y="6" width="12" height="12" rx="1.5" />),
};

// /system/monitor returns the whole cached snapshot, ports/tunnels/ssh included.
// Everything below the metrics used to be fetched again from its own endpoint on
// its own timer, which meant four extra requests per cycle for data the server
// had already assembled and served. They are read from here instead; the
// dedicated endpoints still exist for API clients.
type MonitorSnapshot = {
  cpu_percent?: number;
  ram?: { total_gb: number; used_gb: number; cached_gb: number; percent: number } | { error: string };
  disk?: { total_gb: number; used_gb: number; percent: number } | { error: string };
  temperature?: number | null;
  docker_running?: string[] | { error: string };
  ports?: Port[] | { error: string };
  cloudflared?: Tunnel[] | { error: string };
  ssh_active?: ActiveSession[] | { error: string };
  ssh_history?: LoginHistoryEntry[] | { error: string };
};

// "local" = loopback only, "all" = bound on every interface, otherwise the
// specific address. The collector merges the two-to-four rows `ss` prints per
// service (IPv4/IPv6 x tcp/udp) into one, keeping the widest scope.
type Port = { port: string; process: string | null; scope: string };
type Tunnel = { hostname: string; service: string; healthy: boolean };
type ActiveSession = { user: string; tty: string; login_time: string; host: string | null };
type LoginHistoryEntry = {
  user: string;
  tty: string;
  host: string | null;
  login_time: string;
  logout_time: string | null;
  still_logged_in: boolean;
};
type Container = { name: string; status: string; image: string };

type Hist = { cpu: Point[]; ram: Point[]; disk: Point[]; temp: Point[] };

function push(arr: Point[], t: number, v: number | null): Point[] {
  if (v == null || !Number.isFinite(v)) return arr;
  const next = [...arr, { t, v }];
  return next.length > HISTORY_LEN ? next.slice(next.length - HISTORY_LEN) : next;
}

// ---- one shared 1-second ticker ---------------------------------------------
//
// The wall clock and the session timer both need to advance every second. Holding
// that in the dashboard's own state re-rendered the *entire* page once a second —
// every table, every chart — to repaint two spans. Subscribing leaf components to
// an external store keeps the tick where it belongs: only the two components that
// display a time re-render, and there is one interval for the page rather than one
// per consumer.
const tickListeners = new Set<() => void>();
let tickTimer: ReturnType<typeof setInterval> | null = null;
let tickNow = 0;
let sessionStart = 0;

function subscribeTick(onChange: () => void): () => void {
  tickListeners.add(onChange);
  if (tickTimer === null) {
    // First subscriber: the session starts here, which is also what makes the
    // timer restart cleanly after a logout and a fresh login.
    tickNow = Date.now();
    sessionStart = tickNow;
    tickTimer = setInterval(() => {
      tickNow = Date.now();
      tickListeners.forEach((listener) => listener());
    }, 1000);
  }
  return () => {
    tickListeners.delete(onChange);
    if (tickListeners.size === 0 && tickTimer !== null) {
      clearInterval(tickTimer);
      tickTimer = null;
    }
  };
}

const getTick = () => tickNow;
// 0 during prerender and hydration: there is no clock at build time, and emitting
// a real one would not match what the client hydrates with.
const getTickServer = () => 0;

function useTick() {
  return useSyncExternalStore(subscribeTick, getTick, getTickServer);
}

/** Fetches, but does not store. Separating the two keeps the polling effect free
 *  of a synchronous setState and lets the post-action refresh reuse the request
 *  without duplicating the error handling. Returns null when the call failed —
 *  a 401 has already redirected by then. */
async function fetchContainers(): Promise<Container[] | null> {
  try {
    return await apiFetch("/docker/containers");
  } catch {
    return null;
  }
}

function LiveClock() {
  const now = useTick();
  if (!now) return <span className="tabular-nums">--:--:--</span>;
  return <span className="tabular-nums">{new Date(now).toLocaleTimeString([], { hour12: false })}</span>;
}

function SessionUptime() {
  const now = useTick();
  const seconds = now && sessionStart ? Math.floor((now - sessionStart) / 1000) : 0;
  const pad = (n: number) => n.toString().padStart(2, "0");
  return (
    <span className="tabular-nums">
      session {pad(Math.floor(seconds / 3600))}:{pad(Math.floor((seconds % 3600) / 60))}:{pad(seconds % 60)}
    </span>
  );
}

export default function DashboardPage() {
  const router = useRouter();
  const [output, setOutput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [monitor, setMonitor] = useState<MonitorSnapshot | null>(null);
  const [hist, setHist] = useState<Hist>({ cpu: [], ram: [], disk: [], temp: [] });
  const [securityScan, setSecurityScan] = useState<unknown>(null);
  const [scanning, setScanning] = useState(false);
  const [containers, setContainers] = useState<Container[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  // Derived from the one snapshot rather than held in their own state: no extra
  // request, no extra render, and they cannot drift out of step with the metrics.
  const ports = listFrom<Port>(monitor?.ports);
  const tunnels = listFrom<Tunnel>(monitor?.cloudflared);
  const activeSessions = listFrom<ActiveSession>(monitor?.ssh_active);
  const loginHistory = listFrom<LoginHistoryEntry>(monitor?.ssh_history);

  // null until hydration has run and localStorage can be read; false means no
  // session. Read from the store instead of copied into state by an effect, which
  // also means a logout in another tab takes effect here.
  const hasToken = useSyncExternalStore(subscribeToken, getHasToken, getHasTokenServer);
  const checkingAuth = hasToken !== true;

  useEffect(() => {
    if (hasToken === false) router.replace("/login");
  }, [hasToken, router]);


  useEffect(() => {
    if (checkingAuth) return;
    let cancelled = false;
    async function fetchMonitor() {
      try {
        const data: MonitorSnapshot = await apiFetch("/system/monitor");
        if (cancelled) return;
        setMonitor(data);
        const t = Date.now();
        const ramPct = data.ram && "percent" in data.ram ? data.ram.percent : null;
        const diskPct = data.disk && "percent" in data.disk ? data.disk.percent : null;
        setHist((h) => ({
          cpu: push(h.cpu, t, data.cpu_percent ?? null),
          ram: push(h.ram, t, ramPct),
          disk: push(h.disk, t, diskPct),
          temp: push(h.temp, t, data.temperature ?? null),
        }));
      } catch {}
    }
    fetchMonitor();
    const interval = setInterval(fetchMonitor, 3000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [checkingAuth]);

  useEffect(() => {
    if (checkingAuth) return;
    let cancelled = false;
    async function run() {
      const data = await fetchContainers();
      if (!cancelled && data) setContainers(data);
    }
    run();
    const interval = setInterval(run, 5000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [checkingAuth]);

  // No effect is needed to clear a selection whose container vanished: `sel` below
  // resolves the name against the current list every render, so a stale name
  // already reads as "nothing selected" everywhere it matters. Nulling the state
  // from an effect only added a second render pass to reach the same place.

  async function runAction(path: string, body?: object) {
    setError(null);
    setLoading(true);
    setOutput("");
    try {
      const data = await apiFetch(path, {
        method: "POST",
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
      setOutput(data.output ?? data.message ?? "Done");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  async function runDocker(path: string) {
    if (!selected) return;
    await runAction(path, { name: selected });
    // Refresh immediately so the status badge reflects the action rather than
    // waiting out the remainder of the 5-second poll.
    const data = await fetchContainers();
    if (data) setContainers(data);
  }

  async function runSecurityScan() {
    setError(null);
    setScanning(true);
    try {
      const data = await apiFetch("/security/scan");
      setSecurityScan(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scan failed");
    } finally {
      setScanning(false);
    }
  }

  function handleLogout() {
    clearToken();
    router.push("/login");
  }

  if (checkingAuth) return null;

  const ram = monitor?.ram && "percent" in monitor.ram ? monitor.ram : null;
  const disk = monitor?.disk && "percent" in monitor.disk ? monitor.disk : null;
  const sel = containers?.find((c) => c.name === selected) ?? null;
  const selRunning = sel?.status === "running";
  const runningCount = containers?.filter((c) => c.status === "running").length ?? 0;

  return (
    <div className="relative flex flex-1 flex-col items-center overflow-hidden bg-zinc-50 px-4 py-8 sm:px-6 lg:px-8 dark:bg-black">
      <AuroraBackground />

      <div className="relative flex w-full max-w-[100rem] flex-col gap-5">
        {/* ---- hero header ---- */}
        <header className="animate-fade-in-up flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="relative flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-500/20 to-cyan-500/10 text-emerald-500 shadow-lg shadow-emerald-500/10 dark:text-emerald-400">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="4" width="18" height="7" rx="1.5" />
                <rect x="3" y="13" width="18" height="7" rx="1.5" />
                <circle cx="7" cy="7.5" r="0.8" fill="currentColor" stroke="none" />
                <circle cx="7" cy="16.5" r="0.8" fill="currentColor" stroke="none" />
              </svg>
            </div>
            <div>
              <h1 className="text-sheen text-3xl font-bold tracking-tight">ServerCTL</h1>
              <div className="mt-1 flex items-center gap-3 text-xs text-zinc-500 dark:text-zinc-400">
                <span className="flex items-center gap-1.5">
                  <span className="relative flex h-2 w-2">
                    <span className="animate-pulse-ring absolute inline-flex h-2 w-2 rounded-full bg-emerald-500" />
                    <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
                  </span>
                  <span className="font-medium text-emerald-600 dark:text-emerald-400">online</span>
                </span>
                <span className="text-zinc-300 dark:text-zinc-700">·</span>
                <LiveClock />
                <span className="text-zinc-300 dark:text-zinc-700">·</span>
                <SessionUptime />
              </div>
            </div>
          </div>
          <Button variant="secondary" onClick={handleLogout}>
            Log out
          </Button>
        </header>

        {/* ---- live metric graphs (full width) ---- */}
        {!monitor ? (
          <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-44 w-full rounded-2xl" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
            <StatTile label="CPU" value={monitor.cpu_percent ?? null} unit="%" color={C.cpu} data={hist.cpu} icon={Icons.cpu} delay={0} />
            <StatTile label="Memory" value={ram ? ram.percent : null} unit="%" detail={ram ? `${ram.used_gb}/${ram.total_gb} GB` : undefined} color={C.ram} data={hist.ram} icon={Icons.ram} delay={70} />
            <StatTile label="Disk" value={disk ? disk.percent : null} unit="%" detail={disk ? `${disk.used_gb}/${disk.total_gb} GB` : undefined} color={C.disk} data={hist.disk} icon={Icons.disk} delay={140} />
            <StatTile label="Temp" value={monitor.temperature ?? null} unit="°C" decimals={1} color={C.temp} data={hist.temp} icon={Icons.temp} delay={210} />
          </div>
        )}

        {/* ---- main + sidebar bento ---- */}
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
          {/* main column (2/3) */}
          <div className="flex flex-col gap-5 lg:col-span-2">
            {/* tunnels */}
            <SectionCard title="Tunnels" icon={Icons.tunnel} accent={C.disk} delay={120}>
              {!tunnels ? (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <Skeleton className="h-40 w-full" />
                  <Skeleton className="h-40 w-full" />
                </div>
              ) : tunnels.length === 0 ? (
                <p className="text-sm text-zinc-500">No ingress rules found.</p>
              ) : (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  {tunnels.map((t, i) => (
                    <div
                      key={t.hostname}
                      className="animate-fade-in-up group/tunnel flex flex-col gap-2 rounded-xl border border-black/[.08] p-3 transition-all hover:-translate-y-0.5 hover:border-black/[.16] hover:shadow-md dark:border-white/[.12] dark:hover:border-white/[.25]"
                      style={{ animationDelay: `${i * 60}ms` }}
                    >
                      <div className="flex items-center gap-2">
                        <span className="relative flex h-2.5 w-2.5">
                          {t.healthy && <span className="animate-pulse-ring absolute inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500" />}
                          <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${t.healthy ? "bg-emerald-500" : "bg-red-500"}`} />
                        </span>
                        <span className="truncate text-sm font-medium text-black dark:text-zinc-50">{t.hostname}</span>
                        <span className={`ml-auto rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${t.healthy ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" : "bg-red-500/10 text-red-500"}`}>
                          {t.healthy ? "healthy" : "down"}
                        </span>
                      </div>
                      <p className="truncate text-xs text-zinc-500">{t.service}</p>
                      {/* A link, not a live <iframe> preview.
                       *
                       * The preview that used to be here never rendered: the
                       * dashboard's CSP sets no frame-src, so frames fall back to
                       * `default-src 'self'` and the browser refused every one of
                       * them — the panel only ever showed broken grey boxes.
                       *
                       * Making it work would mean allowing `frame-src https:`, i.e.
                       * embedding arbitrary third-party pages inside a
                       * root-equivalent admin panel, and the old sandbox
                       * ("allow-scripts allow-same-origin") is defeated outright if
                       * a tunnel points back at this panel's own origin — which the
                       * first documented example does. The health dot above already
                       * carries the useful signal, so this just offers a way in. */}
                      <a
                        href={`https://${t.hostname}`}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="mt-1 inline-flex w-fit items-center gap-1 rounded-lg border border-black/[.08] px-2.5 py-1 text-xs font-medium text-zinc-600 transition-colors hover:border-emerald-500/40 hover:text-emerald-600 dark:border-white/[.12] dark:text-zinc-300 dark:hover:border-emerald-400/40 dark:hover:text-emerald-400"
                      >
                        Open
                        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M7 17L17 7M17 7H9M17 7v8" />
                        </svg>
                      </a>
                    </div>
                  ))}
                </div>
              )}
            </SectionCard>

            {/* ssh */}
            <SectionCard title="SSH logins" icon={Icons.ssh} accent={C.ram} delay={160}>
              <div>
                <p className="mb-2 text-xs font-medium tracking-wide text-zinc-500 uppercase dark:text-zinc-400">Active now</p>
                {!activeSessions ? (
                  <Skeleton className="h-9 w-full" />
                ) : activeSessions.length === 0 ? (
                  <p className="text-sm text-zinc-500">No one is currently logged in.</p>
                ) : (
                  <div className="flex flex-col gap-2">
                    {activeSessions.map((s, i) => (
                      <div key={i} className="animate-fade-in-up flex items-center gap-2 rounded-lg border border-emerald-500/20 bg-emerald-500/[.04] p-2 text-sm" style={{ animationDelay: `${i * 50}ms` }}>
                        <span className="relative flex h-2.5 w-2.5">
                          <span className="animate-pulse-ring absolute inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500" />
                          <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500" />
                        </span>
                        <span className="font-medium text-black dark:text-zinc-50">{s.user}</span>
                        <span className="text-zinc-500">{s.tty}</span>
                        <span className="text-zinc-500">{s.host ?? "local"}</span>
                        <span className="ml-auto text-xs text-zinc-500 tabular-nums">{s.login_time}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <div>
                <p className="mb-2 text-xs font-medium tracking-wide text-zinc-500 uppercase dark:text-zinc-400">History</p>
                {!loginHistory ? (
                  <div className="flex flex-col gap-2">
                    {Array.from({ length: 4 }).map((_, i) => (
                      <Skeleton key={i} className="h-5 w-full" />
                    ))}
                  </div>
                ) : (
                  <div className="max-h-72 overflow-auto">
                    <table className="w-full text-left text-sm">
                      <thead className="sticky top-0 bg-white/80 backdrop-blur dark:bg-zinc-900/80">
                        <tr className="text-zinc-500">
                          <th className="pb-2 pr-4 font-normal">User</th>
                          <th className="pb-2 pr-4 font-normal">Host</th>
                          <th className="pb-2 pr-4 font-normal">Login</th>
                          <th className="pb-2 font-normal">Logout</th>
                        </tr>
                      </thead>
                      <tbody>
                        {loginHistory.map((entry, i) => (
                          <tr key={i} className="text-black transition-colors hover:bg-black/[.03] dark:text-zinc-50 dark:hover:bg-white/[.04]">
                            <td className="py-1 pr-4">{entry.user}</td>
                            <td className="py-1 pr-4">{entry.host ?? "local"}</td>
                            <td className="py-1 pr-4 tabular-nums">{entry.login_time}</td>
                            <td className="py-1">
                              {entry.still_logged_in ? (
                                <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-500">
                                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                                  active
                                </span>
                              ) : (
                                <span className="tabular-nums">{entry.logout_time ?? "-"}</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </SectionCard>
          </div>

          {/* sidebar column (1/3) */}
          <div className="flex flex-col gap-5">
            {/* containers: select + start/stop */}
            <SectionCard title={`Containers · ${runningCount} running`} icon={Icons.docker} accent={C.disk} delay={140}>
              {!containers ? (
                <div className="flex flex-col gap-2">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <Skeleton key={i} className="h-9 w-full" />
                  ))}
                </div>
              ) : containers.length === 0 ? (
                <p className="text-sm text-zinc-500">No containers found.</p>
              ) : (
                <div className="max-h-64 overflow-auto pr-1">
                  <div className="flex flex-col gap-1.5">
                    {containers.map((c) => {
                      const running = c.status === "running";
                      const active = c.name === selected;
                      return (
                        <button
                          key={c.name}
                          type="button"
                          onClick={() => setSelected(active ? null : c.name)}
                          className={`group/row flex w-full items-center gap-2.5 rounded-lg border px-3 py-2 text-left text-sm transition-all ${
                            active
                              ? "border-emerald-500/50 bg-emerald-500/[.08] ring-1 ring-emerald-500/30"
                              : "border-black/[.06] hover:border-black/[.14] hover:bg-black/[.02] dark:border-white/[.08] dark:hover:border-white/[.18] dark:hover:bg-white/[.03]"
                          }`}
                        >
                          <span className="relative flex h-2.5 w-2.5 shrink-0">
                            {running && <span className="animate-pulse-ring absolute inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500" />}
                            <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${running ? "bg-emerald-500" : "bg-zinc-400 dark:bg-zinc-600"}`} />
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="block truncate font-medium text-black dark:text-zinc-50">{c.name}</span>
                            <span className="block truncate text-xs text-zinc-400 dark:text-zinc-500">{c.image}</span>
                          </span>
                          <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${running ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" : "bg-zinc-500/10 text-zinc-500"}`}>
                            {c.status}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              <div className="mt-1 flex items-center gap-2">
                <button
                  type="button"
                  disabled={loading || !sel || selRunning}
                  onClick={() => runDocker("/docker/up")}
                  className="flex flex-1 items-center justify-center gap-1.5 rounded-full bg-emerald-500 px-4 py-2 text-sm font-medium text-white transition-all hover:bg-emerald-600 active:scale-[.97] disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {Icons.play}
                  Start
                </button>
                <button
                  type="button"
                  disabled={loading || !sel || !selRunning}
                  onClick={() => runDocker("/docker/down")}
                  className="flex flex-1 items-center justify-center gap-1.5 rounded-full bg-red-500 px-4 py-2 text-sm font-medium text-white transition-all hover:bg-red-600 active:scale-[.97] disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {Icons.stop}
                  Stop
                </button>
              </div>
              <p className="text-center text-xs text-zinc-400 dark:text-zinc-500">
                {sel ? <>Selected <span className="font-medium text-zinc-600 dark:text-zinc-300">{sel.name}</span></> : "Select a container to start or kill it"}
              </p>
            </SectionCard>

            {/* open ports */}
            <SectionCard title="Open ports" icon={Icons.ports} accent={C.cpu} delay={180}>
              {!ports ? (
                <div className="flex flex-col gap-2">
                  {Array.from({ length: 5 }).map((_, i) => (
                    <Skeleton key={i} className="h-5 w-full" />
                  ))}
                </div>
              ) : (
                <div className="max-h-64 overflow-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="sticky top-0 bg-white/80 backdrop-blur dark:bg-zinc-900/80">
                      <tr className="text-zinc-500">
                        <th className="pb-2 pr-3 font-normal">Application</th>
                        <th className="pb-2 font-normal">Port</th>
                      </tr>
                    </thead>
                    <tbody>
                      {ports.map((p) => {
                        // Whether a port is loopback-only or reachable from the
                        // network is the one thing in this panel that carries
                        // risk, so it survives the two-column layout as colour
                        // on the badge rather than a raw address column.
                        const exposed = p.scope === "all";
                        return (
                          <tr key={`${p.process ?? "?"}:${p.port}`} className="text-black transition-colors hover:bg-black/[.03] dark:text-zinc-50 dark:hover:bg-white/[.04]">
                            <td className="py-1 pr-3 text-zinc-600 dark:text-zinc-300">{p.process ?? "-"}</td>
                            <td className="py-1">
                              <span
                                title={exposed ? "Listening on all interfaces — reachable from the network" : `Bound to ${p.scope}`}
                                className={`rounded-md px-1.5 py-0.5 font-medium tabular-nums ${
                                  exposed
                                    ? "bg-amber-500/10 text-amber-600 dark:text-amber-400"
                                    : "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                                }`}
                              >
                                {p.port}
                              </span>
                              {exposed && (
                                <span className="ml-2 text-xs text-amber-600/80 dark:text-amber-400/80">all interfaces</span>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </SectionCard>

            {/* security */}
            <SectionCard title="Security scan" icon={Icons.shield} accent={C.temp} delay={220}>
              <Button disabled={scanning} onClick={runSecurityScan} className="w-fit">
                {scanning ? "Scanning…" : "Run scan"}
              </Button>
              {securityScan != null && (
                <pre className="animate-fade-in-up max-h-64 overflow-auto rounded-lg border border-black/[.08] bg-zinc-50 p-4 text-xs whitespace-pre-wrap text-black dark:border-white/[.12] dark:bg-black dark:text-zinc-50">
                  {JSON.stringify(securityScan, null, 2)}
                </pre>
              )}
            </SectionCard>

            {/* maintenance */}
            <SectionCard title="System maintenance" icon={Icons.wrench} accent={C.cpu} delay={260}>
              <div className="flex gap-3">
                <Button disabled={loading} onClick={() => runAction("/system/update")}>apt update</Button>
                <Button variant="secondary" disabled={loading} onClick={() => runAction("/system/upgrade")}>apt upgrade</Button>
              </div>
            </SectionCard>
          </div>
        </div>

        {error && (
          <p className="animate-fade-in-up flex items-center gap-2 rounded-lg bg-red-500/10 px-3 py-2 text-sm text-red-500">{error}</p>
        )}
        {output && (
          <pre className="animate-fade-in-up max-h-80 overflow-auto rounded-xl border border-black/[.08] bg-white p-4 text-xs whitespace-pre-wrap text-black dark:border-white/[.12] dark:bg-zinc-900 dark:text-zinc-50">
            {output}
          </pre>
        )}
      </div>
    </div>
  );
}
