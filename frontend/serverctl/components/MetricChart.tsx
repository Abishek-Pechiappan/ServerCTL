"use client";

import { useId, useMemo, useState } from "react";

export type Point = { t: number; v: number };

/** Catmull-Rom -> cubic Bézier so the line reads smooth without overshooting hard. */
function smoothPath(pts: { x: number; y: number }[]): string {
  if (pts.length === 0) return "";
  if (pts.length === 1) return `M ${pts[0].x} ${pts[0].y}`;
  let d = `M ${pts[0].x} ${pts[0].y}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i - 1] ?? pts[i];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[i + 2] ?? p2;
    const c1x = p1.x + (p2.x - p0.x) / 6;
    const c1y = p1.y + (p2.y - p0.y) / 6;
    const c2x = p2.x - (p3.x - p1.x) / 6;
    const c2y = p2.y - (p3.y - p1.y) / 6;
    d += ` C ${c1x} ${c1y}, ${c2x} ${c2y}, ${p2.x} ${p2.y}`;
  }
  return d;
}

export default function MetricChart({
  data,
  color,
  max = 100,
  unit = "%",
  height = 72,
  label,
}: {
  data: Point[];
  color: string;
  max?: number;
  unit?: string;
  height?: number;
  label: string;
}) {
  const uid = useId().replace(/:/g, "");
  const W = 300;
  const H = height;
  const padY = 6;
  const [hover, setHover] = useState<number | null>(null);

  const pts = useMemo(() => {
    if (data.length === 0) return [];
    const n = data.length;
    return data.map((d, i) => {
      const x = n === 1 ? W : (i / (n - 1)) * W;
      const clamped = Math.max(0, Math.min(max, d.v));
      const y = H - padY - (clamped / max) * (H - padY * 2);
      return { x, y, v: d.v, t: d.t };
    });
  }, [data, max, H]);

  if (pts.length < 2) {
    return (
      <div
        className="flex items-center justify-center rounded-lg text-xs text-zinc-400 dark:text-zinc-600"
        style={{ height: H }}
      >
        <span className="flex items-center gap-2">
          <span className="h-1.5 w-1.5 animate-ping rounded-full" style={{ background: color }} />
          collecting live data…
        </span>
      </div>
    );
  }

  const line = smoothPath(pts);
  const area = `${line} L ${pts[pts.length - 1].x} ${H} L ${pts[0].x} ${H} Z`;
  const active = hover != null ? pts[hover] : null;

  function onMove(e: React.PointerEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * W;
    let best = 0;
    let bestD = Infinity;
    for (let i = 0; i < pts.length; i++) {
      const d = Math.abs(pts[i].x - x);
      if (d < bestD) {
        bestD = d;
        best = i;
      }
    }
    setHover(best);
  }

  return (
    <div className="relative w-full" style={{ height: H }}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        className="h-full w-full overflow-visible"
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
      >
        <defs>
          <linearGradient id={`fill-${uid}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.32" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
          <filter id={`glow-${uid}`} x="-20%" y="-40%" width="140%" height="180%">
            <feGaussianBlur stdDeviation="2.4" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* baseline grid hairlines */}
        {[0.25, 0.5, 0.75].map((f) => (
          <line
            key={f}
            x1="0"
            x2={W}
            y1={padY + f * (H - padY * 2)}
            y2={padY + f * (H - padY * 2)}
            stroke="var(--grid-line)"
            strokeWidth="1"
            vectorEffect="non-scaling-stroke"
          />
        ))}

        <path d={area} fill={`url(#fill-${uid})`} />
        <path
          d={line}
          fill="none"
          stroke={color}
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          vectorEffect="non-scaling-stroke"
          filter={`url(#glow-${uid})`}
          style={{
            strokeDasharray: 1000,
            strokeDashoffset: 1000,
            animation: "draw 1.4s cubic-bezier(.16,1,.3,1) forwards",
          }}
        />

        {/* leading pulse dot */}
        <circle cx={pts[pts.length - 1].x} cy={pts[pts.length - 1].y} r="3.2" fill={color}>
          <animate attributeName="r" values="3.2;5;3.2" dur="1.8s" repeatCount="indefinite" />
          <animate attributeName="opacity" values="1;0.5;1" dur="1.8s" repeatCount="indefinite" />
        </circle>

        {active && (
          <g>
            <line
              x1={active.x}
              x2={active.x}
              y1="0"
              y2={H}
              stroke={color}
              strokeWidth="1"
              strokeOpacity="0.4"
              vectorEffect="non-scaling-stroke"
            />
            <circle cx={active.x} cy={active.y} r="4" fill={color} stroke="var(--background)" strokeWidth="2" />
          </g>
        )}
      </svg>

      {active && (
        <div
          className="pointer-events-none absolute -top-1 z-10 -translate-y-full rounded-md border border-black/10 bg-white/95 px-2 py-1 text-[11px] font-medium whitespace-nowrap shadow-lg backdrop-blur dark:border-white/15 dark:bg-zinc-900/95"
          style={{
            left: `${(active.x / W) * 100}%`,
            transform: `translate(-50%, -100%)`,
          }}
        >
          <span style={{ color }}>{label}</span>{" "}
          <span className="tabular-nums text-black dark:text-zinc-50">
            {active.v.toFixed(unit === "°C" ? 1 : 0)}
            {unit}
          </span>
        </div>
      )}
    </div>
  );
}
