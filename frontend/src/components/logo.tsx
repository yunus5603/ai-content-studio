import Link from "next/link";

export function Logo() {
  return (
    <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
      <span className="grid h-7 w-7 place-items-center rounded-lg bg-gradient-to-br from-violet-500 to-cyan-400 text-sm text-black">
        ✦
      </span>
      AI Content Studio
    </Link>
  );
}
