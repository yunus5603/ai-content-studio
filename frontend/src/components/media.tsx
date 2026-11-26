import type { Asset } from "@/lib/api";

export function MediaTile({ asset, onOpen }: { asset: Asset; onOpen?: (asset: Asset) => void }) {
  if (!asset.url) return null;
  const body = (
    <>
      {asset.media_type === "video" ? (
        <video
          src={asset.url}
          className="aspect-square w-full object-cover"
          muted
          loop
          playsInline
          onMouseEnter={(e) => e.currentTarget.play().catch(() => {})}
          onMouseLeave={(e) => e.currentTarget.pause()}
        />
      ) : (
        // eslint-disable-next-line @next/next/no-img-element -- signed URLs from storage
        <img src={asset.url} alt={asset.filename ?? "Generated image"} className="aspect-square w-full object-cover" />
      )}
      <div className="flex justify-between gap-2 truncate px-3 py-2 text-xs text-zinc-500">
        <span>
          {asset.kind === "upload" ? "Upload" : "Generated"}
          {asset.media_type === "video" && " · video"}
        </span>
        <span>{new Date(asset.created_at).toLocaleDateString()}</span>
      </div>
    </>
  );
  const cls = "group block w-full overflow-hidden rounded-xl border border-white/10 bg-black/40 text-left hover:border-white/30";
  if (onOpen) {
    return (
      <button type="button" onClick={() => onOpen(asset)} className={cls}>
        {body}
      </button>
    );
  }
  return (
    <a href={asset.url} target="_blank" rel="noreferrer" className={cls}>
      {body}
    </a>
  );
}
