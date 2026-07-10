"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { login, setToken } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const token = await login(username, password);
      setToken(token);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-1 items-center justify-center bg-zinc-50 dark:bg-black">
      <form
        onSubmit={handleSubmit}
        className="flex w-full max-w-sm flex-col gap-4 rounded-xl border border-black/[.08] bg-white p-8 dark:border-white/[.145] dark:bg-zinc-900"
      >
        <h1 className="text-xl font-semibold text-black dark:text-zinc-50">
          ServerCTL Login
        </h1>

        <div className="flex flex-col gap-1">
          <label className="text-sm text-zinc-600 dark:text-zinc-400">
            Username
          </label>
          <input
            className="rounded-md border border-black/[.08] bg-transparent px-3 py-2 text-black outline-none focus:border-zinc-400 dark:border-white/[.145] dark:text-zinc-50"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            required
          />
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-sm text-zinc-600 dark:text-zinc-400">
            Password
          </label>
          <input
            type="password"
            className="rounded-md border border-black/[.08] bg-transparent px-3 py-2 text-black outline-none focus:border-zinc-400 dark:border-white/[.145] dark:text-zinc-50"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </div>

        {error && <p className="text-sm text-red-500">{error}</p>}

        <button
          type="submit"
          disabled={loading}
          className="mt-2 flex h-11 items-center justify-center rounded-full bg-foreground px-5 text-background transition-colors hover:bg-[#383838] disabled:opacity-50 dark:hover:bg-[#ccc]"
        >
          {loading ? "Signing in..." : "Sign in"}
        </button>
      </form>
    </div>
  );
}