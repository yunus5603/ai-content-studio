"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Logo } from "@/components/logo";
import { config } from "@/lib/config";

type Shared = {
  media_type: "image" | "video";
  url: string;
  width: number | null;
  height: number | null;
  created_at: string;
  prompt: string | null;
  model_name: string | null;
};

export default function SharedPage() {
  const { token } = useParams<{ token: string }>();
  const [item, setItem] = useState<Shared | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    fetch(`${config.apiUrl}/v1/share/${encodeURIComponent(token)}`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setItem, () => setMissing(true));
  }, [token]);

  return (
    <div className="flex min-h-screen flex-col items-center gap-6 px-4 py-6">
      <header className="flex w-full max-w-5xl items-center justify-between">
        <Logo />
        <Link href="/login?mode=signup" className="btn btn-primary">
          Make your own
        </Link>
      </header>
      {missing && <p className="mt-20 text-muted">This link doesn&apos;t exist or has expired.</p>}
      {!item && !missing && <p className="mt-20 text-subtle">Loading…</p>}
      {item && (
        <main className="w-full max-w-5xl">
          <div className="overflow-hidden rounded-2xl border border-line bg-surface-2">
            {item.media_type === "video" ? (
              <video src={item.url} className="max-h-[78vh] w-full" controls autoPlay loop playsInline />
            ) : (
              // eslint-disable-next-line @next/next/no-img-element -- signed storage URL
              <img src={item.url} alt={item.prompt ?? "Shared image"} className="max-h-[78vh] w-full object-contain" />
            )}
          </div>
          {(item.prompt || item.model_name) && (
            <div className="mt-4 text-sm">
              {item.model_name && <p className="text-subtle">Made with {item.model_name}</p>}
              {item.prompt && <p className="mt-1 whitespace-pre-wrap text-ink-2">{item.prompt}</p>}
            </div>
          )}
        </main>
      )}
    </div>
  );
}
