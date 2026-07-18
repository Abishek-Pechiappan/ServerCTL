export default function Button({
  variant = "primary",
  className = "",
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary";
}) {
  const base =
    "group relative overflow-hidden rounded-full px-5 py-2 text-sm font-medium transition-all active:scale-[.96] disabled:opacity-50 disabled:active:scale-100";
  const variants = {
    primary:
      "bg-black text-white hover:shadow-md hover:shadow-black/10 dark:bg-white dark:text-black dark:hover:shadow-white/10",
    secondary:
      "border border-black/[.1] text-black hover:bg-black/[.04] dark:border-white/[.15] dark:text-zinc-50 dark:hover:bg-white/[.06]",
  };

  return (
    <button className={`${base} ${variants[variant]} ${className}`} {...props}>
      <span className="relative z-10">{children}</span>
      <span className="absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/20 to-transparent transition-transform duration-700 group-hover:translate-x-full dark:via-black/10" />
    </button>
  );
}
