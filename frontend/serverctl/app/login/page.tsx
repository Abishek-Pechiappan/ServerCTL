"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { login, setToken } from "@/lib/api";
import AuroraBackground from "@/components/AuroraBackground";

const PARTICLES = Array.from({ length: 14 }, (_, i) => ({
  left: (i * 37) % 100,
  delay: (i * 0.7) % 9,
  duration: 7 + (i % 5) * 1.6,
  size: 2 + (i % 3),
}));

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [shake, setShake] = useState(false);

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
      setShake(true);
      setTimeout(() => setShake(false), 400);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="relative flex flex-1 items-center justify-center overflow-hidden bg-zinc-50 dark:bg-black">
      <AuroraBackground dense />

      {/* floating particles */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        {PARTICLES.map((p, i) => (
          <span
            key={i}
            className="absolute bottom-0 rounded-full bg-emerald-400/50 dark:bg-emerald-300/40"
            style={{
              left: `${p.left}%`,
              width: p.size,
              height: p.size,
              animation: `rise ${p.duration}s linear ${p.delay}s infinite`,
            }}
          />
        ))}
      </div>

      {/* gradient-bordered glow card */}
      <div className="animate-scale-in relative w-full max-w-sm p-[1px]">
        <div
          className="absolute inset-0 rounded-2xl opacity-70 blur-sm"
          style={{
            background:
              "conic-gradient(from 0deg, rgba(16,185,129,0.6), rgba(34,211,238,0.5), rgba(192,38,211,0.4), rgba(16,185,129,0.6))",
          }}
        />
        <form
          onSubmit={handleSubmit}
          className={`relative flex w-full flex-col gap-5 rounded-2xl border border-white/60 bg-white/80 p-8 shadow-2xl backdrop-blur-2xl dark:border-white/[.08] dark:bg-zinc-950/80 ${
            shake ? "animate-shake" : ""
          }`}
        >
          <div className="flex flex-col items-center gap-3 text-center">
            <div className="animate-float relative flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-500/20 to-cyan-500/10 text-emerald-500 shadow-lg shadow-emerald-500/20 dark:text-emerald-400">
              <span className="absolute inline-flex h-3 w-3 rounded-full bg-emerald-500 animate-pulse-ring" />
              <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="4" width="18" height="7" rx="1.5" />
                <rect x="3" y="13" width="18" height="7" rx="1.5" />
                <circle cx="7" cy="7.5" r="0.8" fill="currentColor" stroke="none" />
                <circle cx="7" cy="16.5" r="0.8" fill="currentColor" stroke="none" />
              </svg>
            </div>
            <div>
              <h1 className="text-sheen text-2xl font-bold tracking-tight">ServerCTL</h1>
              <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-500">
                Sign in to command your server
              </p>
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">Username</label>
            <input
              className="rounded-lg border border-black/[.08] bg-white/60 px-3 py-2.5 text-sm text-black outline-none transition-all focus:border-emerald-500/60 focus:ring-4 focus:ring-emerald-500/10 dark:border-white/[.1] dark:bg-black/30 dark:text-zinc-50"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              required
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">Password</label>
            <input
              type="password"
              className="rounded-lg border border-black/[.08] bg-white/60 px-3 py-2.5 text-sm text-black outline-none transition-all focus:border-emerald-500/60 focus:ring-4 focus:ring-emerald-500/10 dark:border-white/[.1] dark:bg-black/30 dark:text-zinc-50"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </div>

          {error && (
            <p className="animate-fade-in-up flex items-center gap-2 rounded-lg bg-red-500/10 px-3 py-2 text-sm text-red-500">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="group relative mt-1 flex h-11 items-center justify-center overflow-hidden rounded-lg bg-gradient-to-r from-emerald-600 to-emerald-500 text-sm font-semibold text-white shadow-lg shadow-emerald-500/25 transition-transform active:scale-[.98] disabled:opacity-50"
          >
            <span className="relative z-10 flex items-center gap-2">
              {loading && (
                <svg className="animate-spin-slow" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                  <path d="M21 12a9 9 0 1 1-6.219-8.56" />
                </svg>
              )}
              {loading ? "Signing in…" : "Sign in"}
            </span>
            <span className="absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/30 to-transparent transition-transform duration-700 group-hover:translate-x-full" />
          </button>
        </form>
      </div>
    </div>
  );
}
