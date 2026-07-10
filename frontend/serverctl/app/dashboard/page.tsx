"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, clearToken, getToken } from "@/lib/api";

export default function DashboardPage() {
  const router = useRouter();
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [containerName, setContainerName] = useState("");
  const [output, setOutput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    setCheckingAuth(false);
  }, [router]);

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