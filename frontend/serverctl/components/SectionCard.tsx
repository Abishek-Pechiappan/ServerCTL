export default function SectionCard({
  title,
  icon,
  accent,
  delay = 0,
  children,
}: {
  title: string;
  icon?: React.ReactNode;
  accent?: string;
  delay?: number;
  children: React.ReactNode;
}) {
  return (
    <section
      className="animate-fade-in-up group card-sheen relative flex flex-col gap-4 overflow-hidden rounded-2xl border border-black/[.06] bg-white/70 p-6 shadow-sm backdrop-blur-xl transition-all duration-300 hover:-translate-y-0.5 hover:border-black/[.12] hover:shadow-xl dark:border-white/[.08] dark:bg-zinc-900/50 dark:hover:border-white/[.16]"
      style={{ animationDelay: `${delay}ms` }}
    >
      {accent && (
        <span
          className="pointer-events-none absolute -left-16 -top-16 h-40 w-40 rounded-full opacity-[0.12] blur-3xl transition-opacity duration-500 group-hover:opacity-25"
          style={{ background: accent }}
        />
      )}
      <div className="flex items-center gap-2.5">
        {icon && (
          <span
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-black/[.06] bg-black/[.02] text-zinc-600 dark:border-white/[.08] dark:bg-white/[.03] dark:text-zinc-300"
            style={accent ? { color: accent } : undefined}
          >
            {icon}
          </span>
        )}
        <h2 className="text-sm font-semibold tracking-wide text-zinc-500 uppercase dark:text-zinc-400">
          {title}
        </h2>
      </div>
      {children}
    </section>
  );
}
