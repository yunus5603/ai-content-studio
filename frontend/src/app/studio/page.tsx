"use client";

import { useState } from "react";
import { MediaTile } from "@/components/media";
import { type Asset, type Job, useApi } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";

const debugEnabled = process.env.NEXT_PUBLIC_ENABLE_DEBUG_OPERATIONS === "true";

export default function CreatePage() {
  const api = useApi();
  const { current, can } = useWorkspace();
  const [prompt, setPrompt] = useState("");
  const [uploads, setUploads] = useState<Asset[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!current) return null;
  const canGenerate = can("generate");

  async function upload(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true);
    setMessage(null);
    try {
      for (const file of Array.from(files)) {
        const form = new FormData();
        form.append("file", file);
        const asset = await api<Asset>(`/v1/workspaces/${current!.id}/uploads`, { method: "POST", body: form });
        setUploads((u) => [asset, ...u]);
      }
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  async function debugGenerate() {
    setBusy(true);
    try {
      const job = await api<Job>(`/v1/workspaces/${current!.id}/jobs`, {
        method: "POST",
        body: JSON.stringify({ operation: "text_to_image", provider: "debug", model: "pixel", prompt }),
      });
      setMessage(`Test job queued (${job.id.slice(0, 8)}). Check the Jobs page.`);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="text-2xl font-semibold">Create</h1>
      <p className="mt-1 text-sm text-zinc-400">
        Model selection and real generation arrive in the next step. You can already upload reference media.
      </p>

      {!canGenerate && (
        <p className="mt-6 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-200">
          You have view-only access to this workspace. Ask an admin for the member role to create.
        </p>
      )}

      <div className="mt-6 rounded-2xl border border-white/10 bg-white/[0.02] p-4">
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Describe the image or video you want…"
          rows={4}
          disabled={!canGenerate}
          className="w-full resize-none bg-transparent outline-none placeholder:text-zinc-600"
        />
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <label className={`cursor-pointer rounded-lg border border-white/15 px-3 py-2 text-sm hover:bg-white/5 ${!canGenerate ? "pointer-events-none opacity-50" : ""}`}>
            Upload media
            <input type="file" multiple accept="image/*,video/*" className="hidden" onChange={(e) => upload(e.target.files)} />
          </label>
          <span className="rounded-lg border border-dashed border-white/15 px-3 py-2 text-sm text-zinc-500">Model: coming next</span>
          {debugEnabled && (
            <button
              disabled={busy || !canGenerate}
              onClick={debugGenerate}
              className="ml-auto rounded-lg bg-white px-4 py-2 text-sm font-medium text-black disabled:opacity-50"
            >
              Run test job
            </button>
          )}
        </div>
      </div>

      {message && <p className="mt-4 text-sm text-zinc-300">{message}</p>}

      {uploads.length > 0 && (
        <div className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {uploads.map((a) => (
            <MediaTile key={a.id} asset={a} />
          ))}
        </div>
      )}
    </div>
  );
}
