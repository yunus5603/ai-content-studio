"use client";

import { useCallback, useEffect, useState } from "react";
import { type Asset, type Page, useApi } from "@/lib/api";

export function useUpload(workspaceId: string) {
  const api = useApi();
  return useCallback(
    async (file: Blob, filename: string) => {
      const form = new FormData();
      form.append("file", file, filename);
      return api<Asset>(`/v1/workspaces/${workspaceId}/uploads`, { method: "POST", body: form });
    },
    [api, workspaceId],
  );
}

/** Modal to pick media from the workspace gallery or upload new files. */
export function AssetPicker({
  workspaceId,
  mediaType,
  onPick,
  onClose,
}: {
  workspaceId: string;
  mediaType: "image" | "video";
  onPick: (asset: Asset) => void;
  onClose: () => void;
}) {
  const api = useApi();
  const upload = useUpload(workspaceId);
  const [items, setItems] = useState<Asset[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Page<Asset>>(`/v1/workspaces/${workspaceId}/assets?media_type=${mediaType}&limit=60`).then(
      (p) => setItems(p.items),
      (e: Error) => setError(e.message),
    );
  }, [api, workspaceId, mediaType]);

  async function onFiles(files: FileList | null) {
    const file = files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      onPick(await upload(file, file.name));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-ink/30 backdrop-blur-sm animate-fade-in p-4" onClick={onClose}>
      <div className="max-h-[85vh] w-full max-w-3xl overflow-y-auto rounded-2xl border border-line bg-surface shadow-float animate-scale-in p-5" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h2 className="font-medium">Choose {mediaType === "image" ? "an image" : "a video"}</h2>
          <button onClick={onClose} className="text-muted hover:text-ink" aria-label="Close">✕</button>
        </div>
        <label className={`mt-4 flex cursor-pointer items-center justify-center rounded-xl border border-dashed border-line-strong p-6 text-sm text-ink-2 hover:bg-surface-2 ${busy ? "opacity-50" : ""}`}>
          {busy ? "Uploading…" : "Upload from your device"}
          <input type="file" accept={`${mediaType}/*`} className="hidden" disabled={busy} onChange={(e) => onFiles(e.target.files)} />
        </label>
        {error && <p className="mt-3 text-sm text-danger">{error}</p>}
        <p className="mt-5 text-xs uppercase tracking-wide text-subtle">Or pick from your gallery</p>
        {items.length === 0 && <p className="mt-2 text-sm text-subtle">Nothing in the gallery yet.</p>}
        <div className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-5">
          {items.map((a) => (
            <button key={a.id} onClick={() => onPick(a)} className="overflow-hidden rounded-lg border border-line hover:border-brand">
              {a.media_type === "video" ? (
                <video src={a.url ?? undefined} className="aspect-square w-full object-cover" muted />
              ) : (
                // eslint-disable-next-line @next/next/no-img-element -- signed storage URL
                <img src={a.url ?? undefined} alt="" className="aspect-square w-full object-cover" />
              )}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
