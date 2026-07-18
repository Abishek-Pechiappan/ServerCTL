"use client";

import { useEffect, useRef, useState } from "react";
import MetricChart, { type Point } from "./MetricChart";

function useCountUp(target: number, durationMs = 700) {
  const [value, setValue] = useState(target);
  const fromRef = useRef(target);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    const from = fromRef.current;
    const start = performance.now();
    function tick(now: number) {
      const t = Math.min(1, (now - start) / durationMs);
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(from + (target - from) * eased);
      if (t < 1) rafRef.current = requestAnimationFrame(tick);
      else fromRef.current = target;
    }
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
    };
  }, [target, durationMs]);

  return value;
}

export default function StatTile({
  label,
  value,
  unit,
  detail,
  color,
  data,
  max = 100,
  decimals = 0,
  delay = 0,
  icon,
}: {
  label: string;
  value: number | null;
  unit: string;
  detail?: string;
  color: string;
  data: Point[];
  max?: number;
  decimals?: number;
  delay?: number;
  icon?: React.ReactNode;
}) {
  const animated = useCountUp(value ?? 0);
  const pct = value != null ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  const status = pct >= 85 ? "crit" : pct >= 65 ? "warn" : "good";
  const statusColor =
    status === "crit" ? "var(--status-crit)" : status === "warn" ? "var(--status-warn)" : "var(--status-good)";

  return (
    <div
      className="group animate-fade-in-up card-sheen relative flex flex-col gap-3 overflow-hidden rounded-2xl border border-black/[.06] bg-white/70 p-5 shadow-sm backdrop-blur-xl transition-all duration-300 hover:-translate-y-1 hover:shadow-xl dark:border-white/[.08] dark:bg-zinc-900/50"
      style={{ animationDelay: `${delay}ms` }}
    >
      {/* colored top edge */}
      <span
        className="absolute inset-x-0 top-0 h-[3px] opacity-80"
        style={{ background: `linear-gradient(90deg, transparent, ${color}, transparent)` }}
      />
      {/* soft corner glow in the metric hue */}
      <span
        className="animate-glow-breathe pointer-events-none absolute -right-10 -top-10 h-28 w-28 rounded-full blur-2xl"
        style={{ background: color, opacity: 0.14 }}
      />

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span
            className="flex h-7 w-7 items-center justify-center rounded-lg"
            style={{ background: `color-mix(in srgb, ${color} 16%, transparent)`, color }}
          >
            {icon}
          </span>
          <span className="text-xs font-semibold tracking-wide text-zinc-500 uppercase dark:text-zinc-400">
            {label}
          </span>
        </div>
        <span
          className="flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase"
          style={{ background: `color-mix(in srgb, ${statusColor} 15%, transparent)`, color: statusColor }}
        >
          <span className="h-1.5 w-1.5 rounded-full" style={{ background: statusColor }} />
          {status === "crit" ? "high" : status === "warn" ? "busy" : "ok"}
        </span>
      </div>

      <div className="flex items-baseline gap-1">
        <span className="text-3xl font-semibold tracking-tight text-black tabular-nums dark:text-zinc-50">
          {value == null ? "—" : animated.toFixed(decimals)}
        </span>
        <span className="text-sm font-medium text-zinc-400 dark:text-zinc-500">{unit}</span>
        {detail && <span className="ml-auto text-xs text-zinc-400 dark:text-zinc-500">{detail}</span>}
      </div>

      <MetricChart data={data} color={color} max={max} unit={unit} label={label} height={64} />
    </div>
  );
}
