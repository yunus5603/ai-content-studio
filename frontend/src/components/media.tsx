import type { Asset } from "@/lib/api";

export function MediaTile({ asset }: { asset: Asset }) {
  if (!asset.url) return null;
  return (
    <a href={asset.url} target="_blank" rel="noreferrer" className="group block overflow-hidden rounded-xl border border-white/10 bg-black/40">
      {asset.media_type === "video" ? (
        <video src={asset.url} className="aspect-square w-full object-cover" muted loop playsInline controls />
      ) : (
        // eslint-disable-next-line @next/next/no-img-element -- signed URLs from storage
        <img src={asset.url} alt={asset.filename ?? "Generated image"} className="aspect-square w-full object-cover" />
      )}
      <div className="flex justify-between gap-2 truncate px-3 py-2 text-xs text-zinc-500">
        <span>{asset.kind === "upload" ? "Upload" : "Generated"}</span>
        <span>{new Date(asset.created_at).toLocaleDateString()}</span>
      </div>
    </a>
  );
}
