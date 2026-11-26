"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useApi } from "@/lib/api";
import { type Storyboard, type StoryboardSummary, shotsFromText } from "@/lib/storyboard";
import { useWorkspace } from "@/lib/workspace";

const field = "w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-sm outline-none transition focus:border-violet-400";

const EXAMPLE = `Dawn over a rocky coast, a lone lighthouse on the cliff
The keeper climbs the spiral stairs, lantern in hand
Close-up: the great lens turns and catches the first light
A fishing boat rounds the headland, guided home`;

function NewStoryboard({ onCancel }: { onCancel: () => void }) {
  const api = useApi();
  const router = useRouter();
  const { current } = useWorkspace();
  const [title, setTitle] = useState("");
  const [style, setStyle] = useState("");
  const [shots, setShots] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create() {
    if (!current) return;
    setBusy(true);
    setError(null);
    try {
      const sb = await api<Storyboard>(`/v1/workspaces/${current.id}/storyboards`, {
        method: "POST",
        body: JSON.stringify({ title: title.trim() || "Untitled storyboard", style: style.trim() || null, shots: shotsFromText(shots) }),
      });
      router.push(`/studio/storyboards/${sb.id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
      <h2 className="text-lg font-medium">New storyboard</h2>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <label className="block">
          <span className="mb-1 block text-xs text-zinc-400">Title</span>
          <input id="sb-title" className={field} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="The last lighthouse" autoFocus />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs text-zinc-400">Look and feel (added to every frame)</span>
          <input id="sb-style" className={field} value={style} onChange={(e) => setStyle(e.target.value)} placeholder="cinematic, 35mm film, soft dawn light" />
        </label>
      </div>
      <label className="mt-4 block">
        <span className="mb-1 flex justify-between text-xs text-zinc-400">
          <span>Shots, one per line (optional, you can add them later)</span>
          <button type="button" className="text-violet-300 hover:text-violet-200" onClick={() => setShots(EXAMPLE)}>
            Use an example
          </button>
        </span>
        <textarea id="sb-shots" className={`${field} min-h-32`} value={shots} onChange={(e) => setShots(e.target.value)} placeholder={EXAMPLE} />
      </label>
      {error && <p className="mt-3 text-sm text-red-400">{error}</p>}
      <div className="mt-4 flex gap-2">
        <button id="sb-create" onClick={create} disabled={busy} className="rounded-lg bg-white px-4 py-2 text-sm font-medium text-black transition hover:bg-zinc-200 disabled:opacity-50">
          {busy ? "Creating…" : `Create${shotsFromText(shots).length ? ` with ${shotsFromText(shots).length} shots` : ""}`}
        </button>
        <button onClick={onCancel} className="rounded-lg px-4 py-2 text-sm text-zinc-400 hover:text-white">
          Cancel
        </button>
      </div>
    </div>
  );
}

export default function StoryboardsPage() {
  const api = useApi();
  const { current } = useWorkspace();
  const [items, setItems] = useState<StoryboardSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const canEdit = current?.permissions.includes("generate");

  const load = useCallback(async () => {
    if (!current) return;
    try {
      setItems(await api<StoryboardSummary[]>(`/v1/workspaces/${current.id}/storyboards`));
    } catch (e) {
      setError((e as Error).message);
    }
  }, [api, current]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- load once the workspace is known
    load();
  }, [load]);

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Storyboards</h1>
          <p className="mt-1 text-sm text-zinc-400">Plan a sequence shot by shot, make a keyframe for each, animate them, and join the clips into one film.</p>
        </div>
        {canEdit && !creating && (
          <button id="sb-new" onClick={() => setCreating(true)} className="rounded-lg bg-white px-4 py-2 text-sm font-medium text-black transition hover:bg-zinc-200">
            New storyboard
          </button>
        )}
      </div>

      {creating && <NewStoryboard onCancel={() => setCreating(false)} />}
      {error && <p className="text-sm text-red-400">{error}</p>}
      {items && items.length === 0 && !creating && (
        <div className="rounded-2xl border border-dashed border-white/15 p-10 text-center text-zinc-400">
          <p>No storyboards yet.</p>
          {canEdit && (
            <button onClick={() => setCreating(true)} className="mt-3 text-violet-300 hover:text-violet-200">
              Start your first one
            </button>
          )}
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {items?.map((sb) => (
          <Link
            key={sb.id}
            href={`/studio/storyboards/${sb.id}`}
            className="group overflow-hidden rounded-2xl border border-white/10 bg-black/30 transition duration-300 hover:-translate-y-0.5 hover:border-white/30 hover:shadow-lg hover:shadow-violet-500/10"
          >
            <div className="relative aspect-video bg-gradient-to-br from-violet-500/20 via-fuchsia-500/10 to-sky-500/20">
              {sb.cover?.url && (
                // eslint-disable-next-line @next/next/no-img-element -- signed URLs from storage
                <img src={sb.cover.url} alt="" className="h-full w-full object-cover transition duration-500 group-hover:scale-[1.03]" />
              )}
              {sb.has_film && <span className="absolute right-2 top-2 rounded-full bg-black/70 px-2 py-0.5 text-xs text-white">Film ready</span>}
            </div>
            <div className="p-4">
              <p className="font-medium">{sb.title}</p>
              <p className="mt-1 text-xs text-zinc-500">
                {sb.shot_count} shots · {sb.keyframes_done} keyframes · {sb.clips_done} clips
              </p>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
