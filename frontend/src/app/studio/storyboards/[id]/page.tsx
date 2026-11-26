"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AssetPicker } from "@/components/asset-picker";
import { ParamControls } from "@/components/param-controls";
import { type Asset, type Catalog, type ModelSpec, type Operation, type ParamValue, useApi } from "@/lib/api";
import { useBilling } from "@/lib/billing";
import { modelsFor, paramsFor, useCatalog } from "@/lib/catalog";
import { usd } from "@/lib/format";
import { type JobBrief, type Shot, type Storyboard, anyActive, isActive } from "@/lib/storyboard";
import { useWorkspace } from "@/lib/workspace";

const field = "w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-sm outline-none transition focus:border-violet-400";
const primary = "rounded-lg bg-white px-3.5 py-2 text-sm font-medium text-black transition hover:bg-zinc-200 disabled:cursor-not-allowed disabled:opacity-40";
const secondary = "rounded-lg border border-white/15 px-3 py-1.5 text-sm text-zinc-200 transition hover:border-white/40 hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40";

type Api = ReturnType<typeof useApi>;

/** Params a storyboard sets once for every shot (quantity is always one per shot). */
function boardParams(model: ModelSpec | undefined, op: Operation) {
  if (!model) return [];
  return paramsFor(model, op).filter((p) => !["n", "number_of_videos"].includes(p.name));
}

function secondsOptions(model: ModelSpec | undefined): number[] {
  const p = model?.params.find((x) => x.name === "duration_seconds");
  return p ? p.options.map((o) => Number(o.value)) : [];
}

function Progress({ job, label }: { job: JobBrief; label: string }) {
  if (job.status === "failed" || job.status === "canceled") return null;
  const pct = Math.round((job.status === "queued" ? 0.03 : Math.max(job.progress, 0.06)) * 100);
  return (
    <div className="absolute inset-0 grid place-items-center bg-black/55 backdrop-blur-[2px]">
      <div className="w-2/3 text-center">
        <p className="text-sm text-white">{job.status === "queued" ? "Queued…" : `${label}… ${pct}%`}</p>
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/15">
          <div className="h-full rounded-full bg-gradient-to-r from-violet-400 to-sky-400 transition-all duration-700" style={{ width: `${pct}%` }} />
        </div>
      </div>
    </div>
  );
}

function Frame({ shot, view }: { shot: Shot; view: "keyframe" | "clip" }) {
  const busy = isActive(shot.keyframe_job) ? shot.keyframe_job : isActive(shot.clip_job) ? shot.clip_job : null;
  const showClip = view === "clip" && shot.clip?.url;
  return (
    <div className="relative aspect-video overflow-hidden rounded-xl border border-white/10 bg-gradient-to-br from-zinc-900 to-zinc-800">
      {showClip ? (
        <video key={shot.clip!.id} src={shot.clip!.url!} poster={shot.keyframe?.url ?? undefined} preload="metadata" className="h-full w-full object-cover" controls loop playsInline />
      ) : shot.keyframe?.url ? (
        // eslint-disable-next-line @next/next/no-img-element -- signed URLs from storage
        <img key={shot.keyframe.id} src={shot.keyframe.url} alt="" className="h-full w-full object-cover transition-opacity duration-500" />
      ) : (
        <div className="grid h-full place-items-center text-xs text-zinc-500">No keyframe yet</div>
      )}
      {busy && <Progress job={busy} label={busy === shot.keyframe_job ? "Drawing keyframe" : "Animating"} />}
      <span className="absolute left-2 top-2 rounded-md bg-black/70 px-2 py-0.5 text-xs font-medium text-white">{shot.position + 1}</span>
    </div>
  );
}

function ShotCard({
  sb,
  shot,
  total,
  canEdit,
  videoModel,
  api,
  onChange,
  onError,
  onGenerate,
}: {
  sb: Storyboard;
  shot: Shot;
  total: number;
  canEdit: boolean;
  videoModel: ModelSpec | undefined;
  api: Api;
  onChange: (sb: Storyboard) => void;
  onError: (msg: string | null) => void;
  onGenerate: (stage: "keyframes" | "clips", shotIds: string[], redo: boolean) => Promise<void>;
}) {
  const base = `/v1/workspaces/${sb.workspace_id}/storyboards/${sb.id}`;
  const [view, setView] = useState<"keyframe" | "clip">(shot.clip ? "clip" : "keyframe");
  const [picker, setPicker] = useState<null | "keyframe" | "reference">(null);
  const [draft, setDraft] = useState({ title: shot.title ?? "", description: shot.description, motion: shot.motion ?? "" });
  const seconds = secondsOptions(videoModel);
  const lastFrame = videoModel?.operations.find((o) => o.operation === "image_to_video")?.inputs.some((i) => i.role === "last_frame");
  const prev = sb.shots[shot.position - 1];

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- show the clip once it arrives
    if (shot.clip) setView("clip");
  }, [shot.clip?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  async function patch(body: Record<string, unknown>) {
    try {
      onChange(await api<Storyboard>(`${base}/shots/${shot.id}`, { method: "PATCH", body: JSON.stringify(body) }));
      onError(null);
    } catch (e) {
      onError((e as Error).message);
    }
  }

  async function call(path: string, method: string, body?: unknown) {
    try {
      onChange(await api<Storyboard>(`${base}${path}`, { method, body: body ? JSON.stringify(body) : undefined }));
      onError(null);
    } catch (e) {
      onError((e as Error).message);
    }
  }

  function saveText(key: "title" | "description" | "motion") {
    const value = draft[key].trim();
    const current = key === "description" ? shot.description : (shot[key] ?? "");
    if (value !== current) patch({ [key]: key === "description" ? value : value || null });
  }

  function move(delta: number) {
    const ids = sb.shots.map((s) => s.id);
    const i = shot.position;
    [ids[i], ids[i + delta]] = [ids[i + delta], ids[i]];
    call("/order", "PUT", { shot_ids: ids });
  }

  const kfBusy = isActive(shot.keyframe_job);
  const clipBusy = isActive(shot.clip_job);
  const kfFailed = shot.keyframe_job?.status === "failed" ? shot.keyframe_job.error : null;
  const clipFailed = shot.clip_job?.status === "failed" ? shot.clip_job.error : null;

  return (
    <article className="shot-card grid gap-5 rounded-2xl border border-white/10 bg-white/[0.02] p-4 transition duration-300 hover:border-white/20 md:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
      <div className="space-y-2">
        <Frame shot={shot} view={view} />
        <div className="flex flex-wrap items-center gap-2">
          {shot.clip && (
            <div className="flex rounded-lg border border-white/10 p-0.5 text-xs">
              {(["keyframe", "clip"] as const).map((v) => (
                <button key={v} onClick={() => setView(v)} className={`rounded-md px-2 py-1 capitalize transition ${view === v ? "bg-white text-black" : "text-zinc-400 hover:text-white"}`}>
                  {v}
                </button>
              ))}
            </div>
          )}
          {shot.clip_stale && <span className="rounded-md bg-amber-400/10 px-2 py-1 text-xs text-amber-300">Keyframe changed since this clip</span>}
        </div>
        {kfFailed && <p className="text-xs text-red-400">Keyframe failed: {kfFailed}</p>}
        {clipFailed && <p className="text-xs text-red-400">Animation failed: {clipFailed}</p>}
        {canEdit && (
          <div className="flex flex-wrap gap-2">
            <button
              className={shot.keyframe ? secondary : primary}
              disabled={kfBusy || shot.keyframe_cost.price_usd == null}
              title={shot.keyframe_cost.problem ?? undefined}
              onClick={() => onGenerate("keyframes", [shot.id], true)}
            >
              {shot.keyframe ? "Redraw" : "Draw keyframe"} · {usd(shot.keyframe_cost.price_usd)}
            </button>
            <button className={secondary} disabled={kfBusy} onClick={() => setPicker("keyframe")}>
              Pick image
            </button>
            <button
              className={shot.keyframe && (!shot.clip || shot.clip_stale) ? primary : secondary}
              disabled={!shot.keyframe || kfBusy || clipBusy || shot.clip_cost.price_usd == null}
              title={!shot.keyframe ? "Make a keyframe first" : (shot.clip_cost.problem ?? undefined)}
              onClick={() => onGenerate("clips", [shot.id], true)}
            >
              {shot.clip ? "Re-animate" : "Animate"} · {usd(shot.clip_cost.price_usd)}
            </button>
          </div>
        )}
      </div>

      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <input
            className="flex-1 bg-transparent text-base font-medium outline-none placeholder:text-zinc-600"
            value={draft.title}
            placeholder={`Shot ${shot.position + 1}`}
            disabled={!canEdit}
            onChange={(e) => setDraft({ ...draft, title: e.target.value })}
            onBlur={() => saveText("title")}
          />
          {canEdit && (
            <div className="flex gap-1 text-zinc-500">
              <button aria-label="Move up" disabled={shot.position === 0} onClick={() => move(-1)} className="rounded px-1.5 hover:bg-white/10 hover:text-white disabled:opacity-30">↑</button>
              <button aria-label="Move down" disabled={shot.position === total - 1} onClick={() => move(1)} className="rounded px-1.5 hover:bg-white/10 hover:text-white disabled:opacity-30">↓</button>
              <button aria-label="Delete shot" onClick={() => confirm("Delete this shot? Its images stay in the gallery.") && call(`/shots/${shot.id}`, "DELETE")} className="rounded px-1.5 hover:bg-red-500/20 hover:text-red-300">✕</button>
            </div>
          )}
        </div>
        <label className="block">
          <span className="mb-1 block text-xs text-zinc-400">What we see (keyframe)</span>
          <textarea
            className={`${field} min-h-20`}
            value={draft.description}
            disabled={!canEdit}
            placeholder="Wide shot: a lone lighthouse on a cliff at dawn, waves crashing below"
            onChange={(e) => setDraft({ ...draft, description: e.target.value })}
            onBlur={() => saveText("description")}
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs text-zinc-400">What happens (animation)</span>
          <textarea
            className={`${field} min-h-16`}
            value={draft.motion}
            disabled={!canEdit}
            placeholder="Slow aerial push-in, gulls cross the frame, the lamp flickers on"
            onChange={(e) => setDraft({ ...draft, motion: e.target.value })}
            onBlur={() => saveText("motion")}
          />
        </label>
        <div className="flex flex-wrap items-end gap-4">
          {seconds.length > 0 && (
            <label className="block">
              <span className="mb-1 block text-xs text-zinc-400">Length</span>
              <select
                className={`${field} w-auto`}
                disabled={!canEdit}
                value={shot.duration_seconds ?? ""}
                onChange={(e) => patch({ duration_seconds: e.target.value ? Number(e.target.value) : null })}
              >
                <option value="">Board default</option>
                {seconds.map((s) => (
                  <option key={s} value={s}>
                    {s} seconds
                  </option>
                ))}
              </select>
            </label>
          )}
          {lastFrame && shot.position < total - 1 && (
            <label className="flex items-center gap-2 pb-2 text-xs text-zinc-300" title="The clip ends on the next shot's keyframe, for a seamless move into it">
              <input type="checkbox" disabled={!canEdit} checked={shot.end_on_next} onChange={(e) => patch({ end_on_next: e.target.checked })} className="accent-violet-400" />
              End on next shot&apos;s keyframe
            </label>
          )}
        </div>
        <div>
          <span className="mb-1 block text-xs text-zinc-400">References (characters, products, places)</span>
          <div className="flex flex-wrap items-center gap-2">
            {shot.references.map((r) => (
              <div key={r.id} className="group relative h-12 w-12 overflow-hidden rounded-lg border border-white/10">
                {/* eslint-disable-next-line @next/next/no-img-element -- signed URLs */}
                <img src={r.url ?? undefined} alt="" className="h-full w-full object-cover" />
                {canEdit && (
                  <button
                    aria-label="Remove reference"
                    onClick={() => patch({ reference_asset_ids: shot.references.filter((x) => x.id !== r.id).map((x) => x.id) })}
                    className="absolute inset-0 hidden place-items-center bg-black/60 text-xs text-white group-hover:grid"
                  >
                    ✕
                  </button>
                )}
              </div>
            ))}
            {canEdit && (
              <>
                <button onClick={() => setPicker("reference")} className="grid h-12 w-12 place-items-center rounded-lg border border-dashed border-white/20 text-lg text-zinc-400 transition hover:border-white/50 hover:text-white">
                  +
                </button>
                {prev?.keyframe && !shot.references.some((r) => r.id === prev.keyframe!.id) && (
                  <button
                    className="text-xs text-violet-300 hover:text-violet-200"
                    onClick={() => patch({ reference_asset_ids: [...shot.references.map((r) => r.id), prev.keyframe!.id] })}
                  >
                    Keep continuity with shot {prev.position + 1}
                  </button>
                )}
              </>
            )}
          </div>
        </div>
      </div>

      {picker && (
        <AssetPicker
          workspaceId={sb.workspace_id}
          mediaType="image"
          onClose={() => setPicker(null)}
          onPick={(a: Asset) => {
            setPicker(null);
            if (picker === "keyframe") call(`/shots/${shot.id}/keyframe`, "PUT", { asset_id: a.id });
            else patch({ reference_asset_ids: [...shot.references.map((r) => r.id), a.id] });
          }}
        />
      )}
    </article>
  );
}

function ModelSettings({
  label,
  op,
  models,
  modelId,
  values,
  onModel,
  onParams,
  disabled,
}: {
  label: string;
  op: Operation;
  models: ModelSpec[];
  modelId: string;
  values: Record<string, ParamValue>;
  onModel: (id: string) => void;
  onParams: (v: Record<string, ParamValue>) => void;
  disabled: boolean;
}) {
  const model = models.find((m) => m.id === modelId);
  return (
    <div className="space-y-3">
      <label className="block">
        <span className="mb-1 block text-xs text-zinc-400">{label}</span>
        <select className={field} value={modelId} disabled={disabled} onChange={(e) => onModel(e.target.value)}>
          {models.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name}
            </option>
          ))}
        </select>
      </label>
      {model && <p className="text-xs text-zinc-500">{model.description}</p>}
      {model && !disabled && (
        <ParamControls
          key={model.id}
          specs={boardParams(model, op)}
          values={values}
          onChange={(name, v) => {
            const next = { ...values };
            if (v === undefined) delete next[name];
            else next[name] = v;
            onParams(next);
          }}
        />
      )}
    </div>
  );
}

function Step({ n, title, done, total, children }: { n: number; title: string; done: number; total: number; children: React.ReactNode }) {
  const complete = total > 0 && done >= total;
  return (
    <div className={`rounded-2xl border p-4 transition ${complete ? "border-emerald-400/30 bg-emerald-400/[0.04]" : "border-white/10 bg-white/[0.02]"}`}>
      <div className="flex items-center gap-2">
        <span className={`grid h-6 w-6 place-items-center rounded-full text-xs font-semibold ${complete ? "bg-emerald-400 text-black" : "bg-white/10 text-zinc-300"}`}>{complete ? "✓" : n}</span>
        <span className="font-medium">{title}</span>
        <span className="ml-auto text-xs tabular-nums text-zinc-500">
          {done}/{total}
        </span>
      </div>
      <div className="mt-2 h-1 overflow-hidden rounded-full bg-white/10">
        <div className="h-full rounded-full bg-gradient-to-r from-violet-400 to-sky-400 transition-all duration-700" style={{ width: `${total ? (done / total) * 100 : 0}%` }} />
      </div>
      <div className="mt-3">{children}</div>
    </div>
  );
}

function Settings({ sb, catalog, canEdit, api, onChange, onError }: { sb: Storyboard; catalog: Catalog; canEdit: boolean; api: Api; onChange: (sb: Storyboard) => void; onError: (m: string | null) => void }) {
  const [style, setStyle] = useState(sb.style ?? "");
  const imageModels = useMemo(() => modelsFor(catalog, "text_to_image").filter((m) => m.media_type === "image"), [catalog]);
  const videoModels = useMemo(() => modelsFor(catalog, "image_to_video"), [catalog]);

  async function patch(body: Record<string, unknown>) {
    try {
      onChange(await api<Storyboard>(`/v1/workspaces/${sb.workspace_id}/storyboards/${sb.id}`, { method: "PATCH", body: JSON.stringify(body) }));
      onError(null);
    } catch (e) {
      onError((e as Error).message);
    }
  }

  return (
    <div className="grid gap-6 rounded-2xl border border-white/10 bg-white/[0.02] p-5 md:grid-cols-3">
      <div className="space-y-4">
        <label className="block">
          <span className="mb-1 block text-xs text-zinc-400">Look and feel (added to every frame)</span>
          <textarea
            id="sb-style-edit"
            className={`${field} min-h-24`}
            value={style}
            disabled={!canEdit}
            placeholder="cinematic, 35mm film grain, soft dawn light, muted teal and amber"
            onChange={(e) => setStyle(e.target.value)}
            onBlur={() => style.trim() !== (sb.style ?? "") && patch({ style: style.trim() || null })}
          />
        </label>
        <div>
          <span className="mb-1 block text-xs text-zinc-400">Between shots</span>
          <div className="flex gap-1 rounded-lg border border-white/10 bg-black/40 p-1">
            {(["cut", "fade"] as const).map((t) => (
              <button key={t} disabled={!canEdit} onClick={() => patch({ transition: t })} className={`flex-1 rounded-md px-2 py-1 text-sm transition ${sb.transition === t ? "bg-white text-black" : "text-zinc-300 hover:bg-white/5"}`}>
                {t === "cut" ? "Hard cut" : "Crossfade"}
              </button>
            ))}
          </div>
        </div>
      </div>
      <ModelSettings
        label="Keyframe model"
        op="text_to_image"
        models={imageModels}
        modelId={sb.image_model}
        values={sb.image_params}
        disabled={!canEdit}
        onModel={(id) => patch({ image_model: id })}
        onParams={(v) => patch({ image_params: v })}
      />
      <ModelSettings
        label="Animation model"
        op="image_to_video"
        models={videoModels}
        modelId={sb.video_model}
        values={sb.video_params}
        disabled={!canEdit}
        onModel={(id) => patch({ video_model: id })}
        onParams={(v) => patch({ video_params: v })}
      />
    </div>
  );
}

export default function StoryboardEditor() {
  const { id } = useParams<{ id: string }>();
  const api = useApi();
  const router = useRouter();
  const { current } = useWorkspace();
  const { refreshBilling } = useBilling();
  const { catalog } = useCatalog();
  const [sb, setSb] = useState<Storyboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const canEdit = !!current?.permissions.includes("generate");
  const base = current ? `/v1/workspaces/${current.id}/storyboards/${id}` : null;

  const load = useCallback(async () => {
    if (!base) return;
    try {
      setSb(await api<Storyboard>(base));
    } catch (e) {
      setError((e as Error).message);
    }
  }, [api, base]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial load
    load();
  }, [load]);

  const active = sb ? anyActive(sb) : false;
  useEffect(() => {
    if (!active) return;
    const t = setInterval(async () => {
      await load();
    }, 2000);
    return () => {
      clearInterval(t);
      refreshBilling();
    };
  }, [active, load, refreshBilling]);

  async function generate(stage: "keyframes" | "clips", shotIds: string[] | null, redo: boolean) {
    if (!base) return;
    setBusy(true);
    try {
      setSb(await api<Storyboard>(`${base}/generate`, { method: "POST", body: JSON.stringify({ stage, shot_ids: shotIds, redo }) }));
      setError(null);
      refreshBilling();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function post(path: string, body?: unknown) {
    if (!base) return;
    setBusy(true);
    try {
      setSb(await api<Storyboard>(`${base}${path}`, { method: "POST", body: body ? JSON.stringify(body) : undefined }));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function rename(title: string) {
    if (!base || !sb || !title.trim() || title === sb.title) return;
    try {
      setSb(await api<Storyboard>(base, { method: "PATCH", body: JSON.stringify({ title: title.trim() }) }));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function remove() {
    if (!base || !confirm("Delete this storyboard? Keyframes, clips and films stay in the gallery.")) return;
    await api(base, { method: "DELETE" });
    router.push("/studio/storyboards");
  }

  if (!sb) return <div className="text-zinc-500">{error ?? "Loading…"}</div>;
  const t = sb.totals;
  const videoModel = catalog?.models.find((m) => m.id === sb.video_model);
  const imageModel = catalog?.models.find((m) => m.id === sb.image_model);
  const missingKf = sb.shots.filter((s) => !s.keyframe && !isActive(s.keyframe_job)).length;
  const missingClips = sb.shots.filter((s) => s.keyframe && (!s.clip || s.clip_stale) && !isActive(s.clip_job)).length;
  const filmBusy = isActive(sb.film_job);
  const canAssemble = t.shots > 0 && t.clips_done === t.shots && !filmBusy && !sb.shots.some((s) => isActive(s.clip_job));

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div>
        <Link href="/studio/storyboards" className="text-sm text-zinc-500 transition hover:text-white">
          ← Storyboards
        </Link>
        <div className="mt-2 flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <input
              key={sb.title}
              defaultValue={sb.title}
              disabled={!canEdit}
              onBlur={(e) => rename(e.target.value)}
              className="w-full bg-transparent text-2xl font-semibold outline-none"
            />
            <p className="mt-1 text-sm text-zinc-400">
              {t.shots} shots · about {Math.round(t.seconds)} seconds · {imageModel?.name ?? sb.image_model} → {videoModel?.name ?? sb.video_model} · spent {usd(t.spent_usd)}
            </p>
          </div>
          <div className="flex gap-2">
            <button id="sb-settings" onClick={() => setShowSettings(!showSettings)} className={secondary}>
              {showSettings ? "Hide settings" : "Style & models"}
            </button>
            {canEdit && (
              <button onClick={remove} className={`${secondary} hover:border-red-400/50 hover:text-red-300`}>
                Delete
              </button>
            )}
          </div>
        </div>
      </div>

      {showSettings && catalog && <Settings sb={sb} catalog={catalog} canEdit={canEdit} api={api} onChange={setSb} onError={setError} />}

      <div className="grid gap-3 md:grid-cols-3" id="sb-pipeline">
        <Step n={1} title="Keyframes" done={t.keyframes_done} total={t.shots}>
          {canEdit && (
            <button className={primary} disabled={busy || missingKf === 0} onClick={() => generate("keyframes", null, false)}>
              {missingKf ? `Draw ${missingKf} keyframe${missingKf > 1 ? "s" : ""} · ${usd(t.missing_keyframes_usd)}` : "All drawn"}
            </button>
          )}
        </Step>
        <Step n={2} title="Clips" done={t.clips_done} total={t.shots}>
          {canEdit && (
            <button className={primary} disabled={busy || missingClips === 0} onClick={() => generate("clips", sb.shots.filter((s) => s.keyframe && (!s.clip || s.clip_stale) && !isActive(s.clip_job)).map((s) => s.id), false)}>
              {missingClips ? `Animate ${missingClips} shot${missingClips > 1 ? "s" : ""} · ${usd(sb.shots.filter((s) => s.keyframe && (!s.clip || s.clip_stale) && !isActive(s.clip_job)).reduce((a, s) => a + (s.clip_cost.price_usd ?? 0), 0))}` : t.clips_done === t.shots && t.shots ? "All animated" : "Draw keyframes first"}
            </button>
          )}
        </Step>
        <Step n={3} title="Film" done={sb.film && !sb.film_stale ? 1 : 0} total={1}>
          {canEdit && (
            <button className={primary} disabled={busy || !canAssemble} onClick={() => post("/assemble")}>
              {filmBusy ? "Assembling…" : sb.film ? "Re-assemble · free" : "Assemble film · free"}
            </button>
          )}
        </Step>
      </div>

      {error && (
        <div className="flex items-start justify-between gap-4 rounded-xl border border-red-400/30 bg-red-400/10 px-4 py-3 text-sm text-red-300">
          <span>{error}</span>
          {/insufficient|not enough credits/i.test(error) && (
            <Link href="/studio/billing" className="shrink-0 underline">
              Buy credits
            </Link>
          )}
        </div>
      )}

      {(sb.film || sb.film_job) && (
        <section id="sb-film" className="overflow-hidden rounded-2xl border border-white/10 bg-black/40">
          <div className="relative aspect-video bg-black">
            {sb.film?.url && <video key={sb.film.id} src={sb.film.url} controls playsInline className="h-full w-full" />}
            {sb.film_job && isActive(sb.film_job) && <Progress job={sb.film_job} label="Assembling" />}
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-sm">
            <span className="text-zinc-300">
              {sb.film ? `Film · ${sb.film.duration_seconds?.toFixed(1)}s · ${sb.transition === "fade" ? "crossfades" : "hard cuts"}` : "Assembling your film…"}
              {sb.film_stale && <span className="ml-2 text-amber-300">Shots changed since this cut</span>}
            </span>
            {sb.film?.url && (
              <a href={sb.film.url} download className="text-violet-300 hover:text-violet-200">
                Download
              </a>
            )}
          </div>
          {sb.film_job?.status === "failed" && <p className="px-4 pb-3 text-sm text-red-400">Assembly failed: {sb.film_job.error}</p>}
        </section>
      )}

      <div className="space-y-4">
        {sb.shots.map((s) => (
          <ShotCard
            key={s.id}
            sb={sb}
            shot={s}
            total={sb.shots.length}
            canEdit={canEdit}
            videoModel={videoModel}
            api={api}
            onChange={setSb}
            onError={setError}
            onGenerate={generate}
          />
        ))}
      </div>

      {canEdit && (
        <button
          id="sb-add-shot"
          onClick={() => post("/shots", { description: "" })}
          disabled={busy}
          className="w-full rounded-2xl border border-dashed border-white/15 py-5 text-sm text-zinc-400 transition hover:border-white/40 hover:bg-white/[0.02] hover:text-white"
        >
          + Add shot
        </button>
      )}
    </div>
  );
}
