import Link from "next/link";

export function LogoMark({ className = "h-7 w-7" }: { className?: string }) {
  return (
    <span
      className={`relative grid place-items-center overflow-hidden rounded-[9px] bg-[conic-gradient(from_210deg,#5b4cf0,#9b4cf0,#f0508c,#f59e42,#5b4cf0)] text-white shadow-[0_4px_12px_-4px_rgb(91_76_240/0.6)] ${className}`}
    >
      <svg viewBox="0 0 24 24" className="h-[58%] w-[58%]" fill="currentColor" aria-hidden>
        <path d="M12 2.5c.5 4.6 2.9 7 7.5 7.5-4.6.5-7 2.9-7.5 7.5-.5-4.6-2.9-7-7.5-7.5 4.6-.5 7-2.9 7.5-7.5Z" />
        <path d="M19 15.5c.2 1.8 1.2 2.8 3 3-1.8.2-2.8 1.2-3 3-.2-1.8-1.2-2.8-3-3 1.8-.2 2.8-1.2 3-3Z" opacity=".8" />
      </svg>
    </span>
  );
}

export function Logo() {
  return (
    <Link href="/" className="flex items-center gap-2.5 font-semibold tracking-tight text-ink">
      <LogoMark />
      AI Content Studio
    </Link>
  );
}
