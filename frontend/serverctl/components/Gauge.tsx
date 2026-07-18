"use client";

import { useEffect, useId, useRef, useState } from "react";

function useCountUp(target: number, durationMs = 800) {
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

export default function Gauge({
  percent,
  label,
  detail,
  color = "#10b981",
  size = 104,
}: {
  percent: number;
  label: string;
  detail: string;
  color?: string;
  size?: number;
}) {
  const uid = useId().replace(/:/g, "");
  const animated = useCountUp(Number.isFinite(percent) ? percent : 0);
  const stroke = 8;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.min(100, Math.max(0, animated));
  const offset = circumference - (clamped / 100) * circumference;

  return (
    <div className="group/gauge flex flex-col items-center gap-2.5">
      <div className="relative" style={{ width: size, height: size }}>
        {/* hue glow behind the ring */}
        <span
          className="animate-glow-breathe absolute inset-2 rounded-full blur-xl"
          style={{ background: color, opacity: 0.18 }}
        />
        <svg width={size} height={size} className="relative -rotate-90">
          <defs>
            <linearGradient id={`g-${uid}`} x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity="0.55" />
              <stop offset="100%" stopColor={color} />
            </linearGradient>
            <filter id={`gg-${uid}`} x="-40%" y="-40%" width="180%" height="180%">
              <feGaussianBlur stdDeviation="2" result="b" />
              <feMerge>
                <feMergeNode in="b" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            strokeWidth={stroke}
            className="stroke-black/[.06] dark:stroke-white/[.07]"
          />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            strokeWidth={stroke}
            strokeLinecap="round"
            stroke={`url(#g-${uid})`}
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            filter={`url(#gg-${uid})`}
            style={{ transition: "stroke-dashoffset 0.8s cubic-bezier(.16,1,.3,1)" }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-lg font-semibold tracking-tight text-black tabular-nums dark:text-zinc-50">
            {Math.round(clamped)}
            <span className="text-xs text-zinc-400">%</span>
          </span>
        </div>
      </div>
      <div className="text-center">
        <p className="text-[11px] font-semibold tracking-wide uppercase" style={{ color }}>
          {label}
        </p>
        <p className="text-xs text-zinc-500 tabular-nums dark:text-zinc-500">{detail}</p>
      </div>
    </div>
  );
}
