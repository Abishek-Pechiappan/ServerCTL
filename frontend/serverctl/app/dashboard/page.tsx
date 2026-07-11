"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, clearToken, getToken } from "@/lib/api";

type MonitorSnapshot = {
  cpu_percent?: number;
  ram?: { total_gb: number; used_gb: number; cached_gb: number; percent: number } | { error: string };
  disk?: { total_gb: number; used_gb: number; percent: number } | { error: string };
  temperature?: number | null;
  docker_running?: string[] | { error: string };
};

type Port = {
  address: string;
  port: string;
  process: string | null;
};

export default function DashboardPage() {
  const router = useRouter();
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [containerName, setContainerName] = useState("");
  const [output, setOutput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [monitor, setMonitor] = useState<MonitorSnapshot | null>(null);
  const [ports, setPorts] = useState<Port[] | null>(null);
  const [securityScan, setSecurityScan] = useState<unknown>(null);
  const [scanning, setScanning] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    setCheckingAuth(false);
  }, [router]);

  useEffect(() => {
    if (checkingAuth) return;

    let cancelled = false;

    async function fetchMonitor() {
      try {
        const data = await apiFetch("/system/monitor");
        if (!cancelled) setMonitor(data);
      } catch {
        // keep showing the last known snapshot on a transient failure
      }
    }

    fetchMonitor();
    const interval = setInterval(fetchMonitor, 5000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [checkingAuth]);

  useEffect(() => {
    if (checkingAuth) return;

    let cancelled = false;

    async function fetchPorts() {
      try {
        const data = await apiFetch("/network/ports");
        if (!cancelled) setPorts(data);
      } catch {
        // keep showing the last known list on a transient failure
      }
    }

    fetchPorts();
    const interval = setInterval(fetchPorts, 5000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [checkingAuth]);

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

  return (
    <div className="flex flex-1 flex-col items-center bg-zinc-50 px-6 py-12 dark:bg-black">
      <div className="flex w-full max-w-2xl flex-col gap-8">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold text-black dark:text-zinc-50">
            Dashboard
          </h1>
          <button
            onClick={handleLogout}
            className="rounded-full border border-black/[.08] px-4 py-2 text-sm text-black transition-colors hover:bg-black/[.04] dark:border-white/[.145] dark:text-zinc-50 dark:hover:bg-[#1a1a1a]"
          >
            Log out
          </button>
        </div>

        <section className="flex flex-col gap-3 rounded-xl border border-black/[.08] bg-white p-6 dark:border-white/[.145] dark:bg-zinc-900">
          <h2 className="font-medium text-black dark:text-zinc-50">
            System monitor
          </h2>
          {!monitor ? (
            <p className="text-sm text-zinc-500">Loading...</p>
          ) : (
            <div className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
              <div>
                <p className="text-zinc-500">CPU</p>
                <p className="text-black dark:text-zinc-50">
                  {monitor.cpu_percent ?? "-"}%
                </p>
              </div>
              <div>
                <p className="text-zinc-500">RAM</p>
                <p className="text-black dark:text-zinc-50">
                  {monitor.ram && "percent" in monitor.ram
                    ? `${monitor.ram.used_gb} / ${monitor.ram.total_gb} GB`
                    : "-"}
                </p>
              </div>
              <div>
                <p className="text-zinc-500">Disk</p>
                <p className="text-black dark:text-zinc-50">
                  {monitor.disk && "percent" in monitor.disk
                    ? `${monitor.disk.used_gb} / ${monitor.disk.total_gb} GB`
                    : "-"}
                </p>
              </div>
              <div>
                <p className="text-zinc-500">Temp</p>
                <p className="text-black dark:text-zinc-50">
                  {monitor.temperature != null ? `${monitor.temperature}°C` : "-"}
                </p>
              </div>
              <div className="col-span-2 sm:col-span-4">
                <p className="text-zinc-500">Docker containers running</p>
                <p className="text-black dark:text-zinc-50">
                  {Array.isArray(monitor.docker_running)
                    ? monitor.docker_running.join(", ") || "none"
                    : monitor.docker_running?.error ?? "-"}
                </p>
              </div>
            </div>
          )}
        </section>

        <section className="flex flex-col gap-3 rounded-xl border border-black/[.08] bg-white p-6 dark:border-white/[.145] dark:bg-zinc-900">
          <h2 className="font-medium text-black dark:text-zinc-50">
            Open ports
          </h2>
          {!ports ? (
            <p className="text-sm text-zinc-500">Loading...</p>
          ) : (
            <div className="max-h-80 overflow-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="text-zinc-500">
                    <th className="pb-2 pr-4 font-normal">Address</th>
                    <th className="pb-2 pr-4 font-normal">Port</th>
                    <th className="pb-2 font-normal">Process</th>
                  </tr>
                </thead>
                <tbody>
                  {ports.map((p, i) => (
                    <tr key={i} className="text-black dark:text-zinc-50">
                      <td className="py-1 pr-4">{p.address}</td>
                      <td className="py-1 pr-4">{p.port}</td>
                      <td className="py-1">{p.process ?? "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="flex flex-col gap-3 rounded-xl border border-black/[.08] bg-white p-6 dark:border-white/[.145] dark:bg-zinc-900">
          <h2 className="font-medium text-black dark:text-zinc-50">
            Docker containers
          </h2>
          <input
            className="rounded-md border border-black/[.08] bg-transparent px-3 py-2 text-black outline-none focus:border-zinc-400 dark:border-white/[.145] dark:text-zinc-50"
            placeholder="Container name"
            value={containerName}
            onChange={(e) => setContainerName(e.target.value)}
          />
          <div className="flex gap-3">
            <button
              disabled={loading || !containerName}
              onClick={() => runAction("/docker/down", { name: containerName })}
              className="rounded-full bg-foreground px-5 py-2 text-sm text-background transition-colors hover:bg-[#383838] disabled:opacity-50 dark:hover:bg-[#ccc]"
            >
              Kill
            </button>
            <button
              disabled={loading || !containerName}
              onClick={() => runAction("/docker/up", { name: containerName })}
              className="rounded-full border border-black/[.08] px-5 py-2 text-sm text-black transition-colors hover:bg-black/[.04] disabled:opacity-50 dark:border-white/[.145] dark:text-zinc-50 dark:hover:bg-[#1a1a1a]"
            >
              Start
            </button>
          </div>
        </section>

        <section className="flex flex-col gap-3 rounded-xl border border-black/[.08] bg-white p-6 dark:border-white/[.145] dark:bg-zinc-900">
          <h2 className="font-medium text-black dark:text-zinc-50">
            Security scan
          </h2>
          <button
            disabled={scanning}
            onClick={runSecurityScan}
            className="w-fit rounded-full bg-foreground px-5 py-2 text-sm text-background transition-colors hover:bg-[#383838] disabled:opacity-50 dark:hover:bg-[#ccc]"
          >
            {scanning ? "Scanning..." : "Run scan"}
          </button>
          {securityScan != null && (
            <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-md border border-black/[.08] bg-zinc-50 p-4 text-xs text-black dark:border-white/[.145] dark:bg-black dark:text-zinc-50">
              {JSON.stringify(securityScan, null, 2)}
            </pre>
          )}
        </section>

        <section className="flex flex-col gap-3 rounded-xl border border-black/[.08] bg-white p-6 dark:border-white/[.145] dark:bg-zinc-900">
          <h2 className="font-medium text-black dark:text-zinc-50">
            System maintenance
          </h2>
          <div className="flex gap-3">
            <button
              disabled={loading}
              onClick={() => runAction("/system/update")}
              className="rounded-full bg-foreground px-5 py-2 text-sm text-background transition-colors hover:bg-[#383838] disabled:opacity-50 dark:hover:bg-[#ccc]"
            >
              apt update
            </button>
            <button
              disabled={loading}
              onClick={() => runAction("/system/upgrade")}
              className="rounded-full border border-black/[.08] px-5 py-2 text-sm text-black transition-colors hover:bg-black/[.04] disabled:opacity-50 dark:border-white/[.145] dark:text-zinc-50 dark:hover:bg-[#1a1a1a]"
            >
              apt upgrade
            </button>
          </div>
        </section>

        {error && <p className="text-sm text-red-500">{error}</p>}

        {output && (
          <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-xl border border-black/[.08] bg-white p-4 text-xs text-black dark:border-white/[.145] dark:bg-zinc-900 dark:text-zinc-50">
            {output}
          </pre>
        )}
      </div>
    </div>
  );
}