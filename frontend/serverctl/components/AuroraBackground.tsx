/** Animated aurora-mesh + dot-grid backdrop. Purely decorative, non-interactive. */
export default function AuroraBackground({ dense = false }: { dense?: boolean }) {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="absolute inset-0 bg-dotgrid opacity-70" />
      <div
        className="animate-aurora absolute -top-1/3 -left-1/4 h-[36rem] w-[36rem] rounded-full blur-3xl"
        style={{
          background:
            "radial-gradient(circle at center, rgba(16,185,129,0.30), transparent 65%)",
        }}
      />
      <div
        className="animate-aurora absolute top-1/4 -right-1/4 h-[34rem] w-[34rem] rounded-full blur-3xl"
        style={{
          animationDelay: "7s",
          background:
            "radial-gradient(circle at center, rgba(34,211,238,0.24), transparent 65%)",
        }}
      />
      <div
        className="animate-aurora absolute -bottom-1/3 left-1/3 h-[30rem] w-[30rem] rounded-full blur-3xl"
        style={{
          animationDelay: "13s",
          background:
            "radial-gradient(circle at center, rgba(192,38,211,0.18), transparent 65%)",
        }}
      />
      {dense && (
        <div
          className="animate-aurora absolute top-1/2 left-1/2 h-[28rem] w-[28rem] rounded-full blur-3xl"
          style={{
            animationDelay: "4s",
            background:
              "radial-gradient(circle at center, rgba(217,119,6,0.16), transparent 65%)",
          }}
        />
      )}
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(120% 80% at 50% 0%, transparent 40%, var(--background) 100%)",
        }}
      />
    </div>
  );
}
