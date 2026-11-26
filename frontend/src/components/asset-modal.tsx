"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { type Asset, type Job, type ModelSpec, type Share, useApi } from "@/lib/api";
import { bytes, usd } from "@/lib/format";
import { useWorkspace } from "@/lib/workspace";

export function AssetModal({
  asset,
  models,
  onClose,
  onDeleted,
}: {
  asset: Asset;
  models: Record<string, ModelSpec>;
  onClose: () => void;
  onDeleted: (id: string) => void;
}) {
  const api = useApi();
  const { current, me, can } = useWorkspace();
  const [job, setJob] = useState<Job | null>(null);
  const [shares, setShares] = useState<Share[]>([]);
  const [includePrompt, setIncludePrompt] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const base = `/v1/workspaces/${current!.id}`;

  useEffect(() => {
    if (asset.job_id) api<Job>(`${base}/jobs/${asset.job_id}`).then(setJob, () => {});
    api<Share[]>(`${base}/assets/${asset.id}/shares`).then(setShares, () => {});
  }, [api, base, asset]);

  const shareUrl = (s: Share) => `${window.location.origin}/s/${s.token}`;

  async function share() {
    try {
      const s = await api<Share>(`${base}/assets/${asset.id}/shares`, {
        method: "POST",
        body: JSON.stringify({ include_prompt: includePrompt }),
      });
      setShares((all) => [s, ...all]);
      await copy(s);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't create a link");
    }
  }

  async function copy(s: Share) {
    try {
      await navigator.clipboard.writeText(shareUrl(s));
      setCopied(s.id);
      setTimeout(() => setCopied(null), 1500);
    } catch {}
  }

  async function revoke(s: Share) {
    await api(`${base}/shares/${s.id}`, { method: "DELETE" });
    setShares((all) => all.filter((x) => x.id !== s.id));
  }

  async function remove() {
    if (!confirm("Delete this file? This can't be undone.")) return;
    try {
      await api(`${base}/assets/${asset.id}`, { method: "DELETE" });
      onDeleted(asset.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't delete");
    }
  }

  const mine = asset.created_by_id === me?.user.id;
  const canDelete = mine ? can("delete_own_asset") : can("delete_any_asset");
  const model = job ? models[job.model] : undefined;

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-ink/30 backdrop-blur-sm animate-fade-in p-4" onClick={onClose}>
      <div
        className="grid max-h-[92vh] w-full max-w-5xl overflow-y-auto rounded-2xl border border-line bg-surface shadow-float animate-scale-in md:grid-cols-[1fr_320px]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-center bg-surface-2 p-2">
          {asset.media_type === "video" ? (
            <video src={asset.url ?? undefined} className="max-h-[80vh] w-full" controls autoPlay loop playsInline />
          ) : (
            // eslint-disable-next-line @next/next/no-img-element -- signed storage URL
            <img src={asset.url ?? undefined} alt="" className="max-h-[80vh] w-full object-contain" />
          )}
        </div>
        <div className="space-y-5 p-5 text-sm">
          <div className="flex items-start justify-between">
            <div>
              <p className="font-medium">{asset.kind === "output" ? model?.name ?? "Generated" : asset.filename ?? "Upload"}</p>
              <p className="text-xs text-subtle">
                {new Date(asset.created_at).toLocaleString()} · {bytes(asset.size_bytes)}
                {asset.width && asset.height ? ` · ${asset.width}×${asset.height}` : ""}
              </p>
            </div>
            <button onClick={onClose} className="text-muted hover:text-ink" aria-label="Close">✕</button>
          </div>

          {job?.prompt && (
            <div>
              <p className="mb-1 text-xs uppercase tracking-wide text-subtle">Prompt</p>
              <p className="whitespace-pre-wrap text-ink-2">{job.prompt}</p>
              <p className="mt-2 text-xs text-subtle">
                {Object.entries(job.params).map(([k, v]) => `${k}: ${v}`).join(" · ")}
              </p>
              {job.price_usd != null && <p className="mt-1 text-xs text-subtle">Cost {usd(job.price_usd)}</p>}
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            <a href={asset.url ?? "#"} download className="btn btn-primary">Download</a>
            {asset.media_type === "image" && can("generate") && (
              <>
                <Link href={`/studio?input=${asset.id}`} className="rounded-lg border border-line-strong px-3 py-1.5">Edit</Link>
                <Link href={`/studio?input=${asset.id}&op=image_to_video`} className="rounded-lg border border-line-strong px-3 py-1.5">Animate</Link>
              </>
            )}
            {canDelete && (
              <button onClick={remove} className="rounded-lg border border-line-strong px-3 py-1.5 text-danger">Delete</button>
            )}
          </div>

          {can("generate") && (
            <div>
              <p className="mb-2 text-xs uppercase tracking-wide text-subtle">Share</p>
              <div className="flex items-center gap-3">
                <button onClick={share} className="rounded-lg border border-line-strong px-3 py-1.5">Create public link</button>
                {job?.prompt && (
                  <label className="flex items-center gap-1.5 text-xs text-muted">
                    <input type="checkbox" checked={includePrompt} onChange={(e) => setIncludePrompt(e.target.checked)} />
                    Show prompt
                  </label>
                )}
              </div>
              <ul className="mt-3 space-y-2">
                {shares.map((s) => (
                  <li key={s.id} className="flex items-center gap-2 text-xs">
                    <code className="min-w-0 flex-1 truncate text-muted">{shareUrl(s)}</code>
                    <button onClick={() => copy(s)} className="text-ink-2 hover:text-ink">{copied === s.id ? "Copied" : "Copy"}</button>
                    <button onClick={() => revoke(s)} className="text-subtle hover:text-danger">Revoke</button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {error && <p className="text-danger">{error}</p>}
        </div>
      </div>
    </div>
  );
}
