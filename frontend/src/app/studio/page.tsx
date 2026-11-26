"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { AssetPicker, useUpload } from "@/components/asset-picker";
import { JobCard, useJobPolling } from "@/components/job-card";
import { MaskEditor } from "@/components/mask-editor";
import { ParamControls } from "@/components/param-controls";
import {
  ApiError,
  type Asset,
  type Estimate,
  type InputRole,
  type InputSpec,
  type Job,
  type ModelSpec,
  type Operation,
  type ParamValue,
  useApi,
} from "@/lib/api";
import { IMAGE_OPS, VIDEO_OPS, activeValues, defaultsFor, modelsFor, paramsFor, useCatalog } from "@/lib/catalog";
import { usd } from "@/lib/format";
import { useWorkspace } from "@/lib/workspace";

const OP_HINTS: Record<Operation, string> = {
  text_to_image: "Describe the image you want…",
  image_edit: "Describe how to change or combine the reference images…",
  inpaint: "Describe what should appear in the painted area…",
  text_to_video: "Describe the scene, the action, the camera and the sound…",
  image_to_video: "Describe how the image should come to life…",
};

const statusBadge: Record<ModelSpec["status"], string | null> = { ga: null, preview: "Preview", deprecated: "Retiring" };

function Thumb({ asset, onRemove }: { asset: Asset; onRemove: () => void }) {
  return (
    <div className="group relative h-20 w-20 overflow-hidden rounded-lg border border-white/10">
      {asset.media_type === "video" ? (
        <video src={asset.url ?? undefined} className="h-full w-full object-cover" muted />
      ) : (
        // eslint-disable-next-line @next/next/no-img-element -- signed storage URL
        <img src={asset.url ?? undefined} alt="" className="h-full w-full object-cover" />
      )}
      <button
        onClick={onRemove}
        className="absolute right-1 top-1 hidden h-5 w-5 rounded-full bg-black/80 text-xs group-hover:block"
        aria-label="Remove"
      >
        ✕
      </button>
    </div>
  );
}

function CreateStudio() {
  const api = useApi();
  const params = useSearchParams();
  const { current, can } = useWorkspace();
  const { catalog, error: catalogError } = useCatalog();
  const upload = useUpload(current?.id ?? "");

  const [media, setMedia] = useState<"image" | "video">("image");
  const [op, setOp] = useState<Operation>("text_to_image");
  const [modelId, setModelId] = useState<string | null>(null);
  const [values, setValues] = useState<Record<string, ParamValue>>({});
  const [inputs, setInputs] = useState<Partial<Record<InputRole, Asset[]>>>({});
  const [prompt, setPrompt] = useState("");
  const [estimate, setEstimate] = useState<Estimate | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [enhancing, setEnhancing] = useState(false);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [picker, setPicker] = useState<InputSpec | null>(null);
  const [masking, setMasking] = useState(false);

  const modelsById = useMemo(() => Object.fromEntries((catalog?.models ?? []).map((m) => [m.id, m])), [catalog]);
  const available = useMemo(() => (catalog ? modelsFor(catalog, op) : []), [catalog, op]);
  const model = modelId ? modelsById[modelId] : undefined;
  const opSpec = model?.operations.find((o) => o.operation === op);
  const ops = (media === "image" ? IMAGE_OPS : VIDEO_OPS).filter((o) => catalog && modelsFor(catalog, o).length > 0);

  // Pick a model for the operation, keeping the current one when it still fits.
  const chooseModel = useCallback(
    (nextOp: Operation, preferred?: string | null) => {
      if (!catalog) return;
      const options = modelsFor(catalog, nextOp);
      const next = options.find((m) => m.id === preferred) ?? options.find((m) => m.status !== "deprecated") ?? options[0];
      setModelId(next?.id ?? null);
      setValues(next ? defaultsFor(next, nextOp) : {});
    },
    [catalog],
  );

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- choose a default once the catalog loads
    if (catalog && !modelId) chooseModel(op);
  }, [catalog, modelId, op, chooseModel]);

  // "Use as input" from the gallery: /studio?input=<asset id>
  const inputParam = params.get("input");
  useEffect(() => {
    if (!inputParam || !current) return;
    api<Asset>(`/v1/workspaces/${current.id}/assets/${inputParam}`).then((asset) => {
      if (asset.media_type !== "image") return;
      const nextOp = params.get("op") === "image_to_video" ? "image_to_video" : "image_edit";
      setMedia(nextOp === "image_to_video" ? "video" : "image");
      setOp(nextOp);
      setInputs(nextOp === "image_to_video" ? { first_frame: [asset] } : { image: [asset] });
      setModelId(null); // re-pick a model for the new operation
    });
  }, [inputParam, params, current, api]);

  // Live price and validation from the server, so the UI never disagrees with it.
  useEffect(() => {
    if (!model) return;
    const body = { model: model.id, operation: op, params: activeValues(model, op, values) };
    const timer = setTimeout(async () => {
      try {
        setEstimate(await api<Estimate>("/v1/catalog/estimate", { method: "POST", body: JSON.stringify(body) }));
        setProblem(null);
      } catch (e) {
        setEstimate(null);
        setProblem(e instanceof Error ? e.message : "Invalid settings");
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [api, model, op, values]);

  const onJobUpdate = useCallback((job: Job) => setJobs((all) => all.map((j) => (j.id === job.id ? job : j))), []);
  useJobPolling(current?.id, jobs, onJobUpdate);

  if (!current) return null;
  if (catalogError) return <p className="text-red-400">{catalogError}</p>;
  if (!catalog) return <p className="text-zinc-500">Loading models…</p>;

  const canGenerate = can("generate");
  const missing = (opSpec?.inputs ?? []).filter((spec) => (inputs[spec.role]?.length ?? 0) < spec.min);

  function switchMedia(next: "image" | "video") {
    setMedia(next);
    const nextOp = next === "image" ? "text_to_image" : "text_to_video";
    setOp(nextOp);
    setInputs({});
    chooseModel(nextOp);
  }

  function switchOp(next: Operation) {
    setOp(next);
    setInputs({});
    chooseModel(next, modelId);
  }

  function addInput(spec: InputSpec, asset: Asset) {
    setInputs((cur) => {
      const list = spec.max === 1 ? [asset] : [...(cur[spec.role] ?? []), asset].slice(0, spec.max);
      // A new base image invalidates an old mask.
      return spec.role === "image" && op === "inpaint" ? { image: list } : { ...cur, [spec.role]: list };
    });
    setPicker(null);
  }

  async function enhance() {
    if (!prompt.trim()) return;
    setEnhancing(true);
    try {
      const r = await api<{ prompt: string }>(`/v1/workspaces/${current!.id}/prompts/enhance`, {
        method: "POST",
        body: JSON.stringify({ prompt, model: model?.id, operation: op }),
      });
      setPrompt(r.prompt);
    } catch (e) {
      setProblem(e instanceof Error ? e.message : "Couldn't enhance the prompt");
    } finally {
      setEnhancing(false);
    }
  }

  async function generate() {
    if (!model) return;
    setSubmitting(true);
    setProblem(null);
    try {
      const job = await api<Job>(`/v1/workspaces/${current!.id}/jobs`, {
        method: "POST",
        body: JSON.stringify({
          model: model.id,
          operation: op,
          prompt,
          params: activeValues(model, op, values),
          inputs: Object.entries(inputs).flatMap(([role, list]) => (list ?? []).map((a) => ({ asset_id: a.id, role }))),
        }),
      });
      setJobs((all) => [job, ...all]);
    } catch (e) {
      setProblem(e instanceof ApiError || e instanceof Error ? e.message : "Couldn't start the generation");
    } finally {
      setSubmitting(false);
    }
  }

  async function cancel(job: Job) {
    onJobUpdate(await api<Job>(`/v1/workspaces/${current!.id}/jobs/${job.id}/cancel`, { method: "POST" }));
  }

  async function saveMask(blob: Blob) {
    setMasking(false);
    try {
      const mask = await upload(blob, "mask.png");
      setInputs((cur) => ({ ...cur, mask: [mask] }));
    } catch (e) {
      setProblem(e instanceof Error ? e.message : "Couldn't save the mask");
    }
  }

  const baseImage = inputs.image?.[0];

  return (
    <div className="mx-auto grid max-w-6xl gap-6 lg:grid-cols-[1fr_320px]">
      <section className="min-w-0">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex rounded-full border border-white/10 p-1">
            {(["image", "video"] as const).map((m) => (
              <button
                key={m}
                onClick={() => switchMedia(m)}
                className={`rounded-full px-4 py-1.5 text-sm capitalize ${media === m ? "bg-white text-black" : "text-zinc-300"}`}
              >
                {m}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap gap-1">
            {ops.map((o) => (
              <button
                key={o}
                onClick={() => switchOp(o)}
                className={`rounded-full px-3 py-1.5 text-sm ${op === o ? "bg-white/15 text-white" : "text-zinc-400 hover:text-white"}`}
              >
                {catalog.operations[o]}
              </button>
            ))}
          </div>
        </div>

        {!canGenerate && (
          <p className="mt-4 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-200">
            You have view-only access to this workspace. Ask an admin for the member role to create.
          </p>
        )}

        {opSpec && opSpec.inputs.length > 0 && (
          <div className="mt-5 space-y-4">
            {opSpec.inputs.map((spec) => {
              const list = inputs[spec.role] ?? [];
              if (spec.role === "mask") {
                return (
                  <div key={spec.role}>
                    <p className="mb-2 text-xs text-zinc-400">{spec.label}</p>
                    <div className="flex items-center gap-3">
                      {list[0] && <Thumb asset={list[0]} onRemove={() => setInputs((c) => ({ ...c, mask: [] }))} />}
                      <button
                        disabled={!baseImage?.url}
                        onClick={() => setMasking(true)}
                        className="rounded-lg border border-white/15 px-3 py-2 text-sm hover:bg-white/5 disabled:opacity-40"
                      >
                        {list[0] ? "Repaint mask" : "Paint mask"}
                      </button>
                      {!baseImage && <span className="text-xs text-zinc-500">Choose the image first</span>}
                    </div>
                  </div>
                );
              }
              return (
                <div key={spec.role}>
                  <p className="mb-2 text-xs text-zinc-400">
                    {spec.label}
                    {spec.max > 1 && ` (up to ${spec.max})`}
                  </p>
                  <div className="flex flex-wrap items-center gap-2">
                    {list.map((a, i) => (
                      <Thumb
                        key={`${a.id}-${i}`}
                        asset={a}
                        onRemove={() => setInputs((c) => ({ ...c, [spec.role]: list.filter((_, j) => j !== i) }))}
                      />
                    ))}
                    {list.length < spec.max && (
                      <button
                        disabled={!canGenerate}
                        onClick={() => setPicker(spec)}
                        className="grid h-20 w-20 place-items-center rounded-lg border border-dashed border-white/20 text-2xl text-zinc-500 hover:bg-white/5 disabled:opacity-40"
                        aria-label={`Add ${spec.label}`}
                      >
                        +
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        <div className="mt-5 rounded-2xl border border-white/10 bg-white/[0.02] p-4">
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder={OP_HINTS[op]}
            rows={5}
            disabled={!canGenerate}
            className="w-full resize-y bg-transparent outline-none placeholder:text-zinc-600"
          />
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <button
              onClick={enhance}
              disabled={!canGenerate || enhancing || !prompt.trim()}
              className="rounded-lg border border-white/15 px-3 py-2 text-sm hover:bg-white/5 disabled:opacity-40"
            >
              {enhancing ? "Enhancing…" : "✦ Enhance prompt"}
            </button>
            <div className="ml-auto flex items-center gap-3">
              {estimate && (
                <span className="text-sm text-zinc-400" title="Provider price plus 10% platform fee">
                  ≈ {usd(estimate.price_usd)}
                </span>
              )}
              <button
                onClick={generate}
                disabled={!canGenerate || submitting || !prompt.trim() || !estimate || missing.length > 0}
                className="rounded-lg bg-white px-5 py-2 text-sm font-medium text-black disabled:opacity-40"
              >
                {submitting ? "Starting…" : "Generate"}
              </button>
            </div>
          </div>
          {missing.length > 0 && <p className="mt-2 text-xs text-zinc-500">Add: {missing.map((m) => m.label).join(", ")}</p>}
          {problem && <p className="mt-2 text-sm text-red-400">{problem}</p>}
        </div>

        <div className="mt-8 space-y-3">
          {jobs.map((j) => (
            <JobCard key={j.id} job={j} models={modelsById} onCancel={cancel} />
          ))}
        </div>
      </section>

      <aside id="settings" className="space-y-5 rounded-2xl border border-white/10 bg-white/[0.02] p-4 lg:sticky lg:top-6 lg:self-start">
        <div>
          <label htmlFor="model-select" className="mb-1 block text-xs text-zinc-400">Model</label>
          <select
            id="model-select"
            value={modelId ?? ""}
            onChange={(e) => chooseModel(op, e.target.value)}
            className="w-full rounded-lg border border-white/10 bg-black/40 px-2.5 py-2 text-sm"
          >
            {["openai", "vertex", "debug"].map((provider) => {
              const group = available.filter((m) => m.provider === provider);
              if (!group.length) return null;
              const label = { openai: "OpenAI", vertex: "Google", debug: "Debug" }[provider];
              return (
                <optgroup key={provider} label={label}>
                  {group.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name}
                      {statusBadge[m.status] ? ` (${statusBadge[m.status]})` : ""}
                    </option>
                  ))}
                </optgroup>
              );
            })}
          </select>
          {model && (
            <div className="mt-2 text-xs text-zinc-500">
              <p>{model.description}</p>
              {model.shutdown_date && <p className="mt-1 text-amber-300/80">Retires {model.shutdown_date}</p>}
              <div className="mt-2 flex flex-wrap gap-1">
                {model.tags.map((t) => (
                  <span key={t} className="rounded border border-white/10 px-1.5 py-0.5">{t.replace("-", " ")}</span>
                ))}
              </div>
            </div>
          )}
        </div>
        {model && (
          <ParamControls
            key={`${model.id}-${op}`}
            specs={paramsFor(model, op)}
            values={values}
            onChange={(name, v) =>
              setValues((cur) => {
                const next = { ...cur };
                if (v === undefined) delete next[name];
                else next[name] = v;
                return next;
              })
            }
          />
        )}
      </aside>

      {picker && (
        <AssetPicker
          workspaceId={current.id}
          mediaType={picker.media_type}
          onPick={(a) => addInput(picker, a)}
          onClose={() => setPicker(null)}
        />
      )}
      {masking && baseImage?.url && <MaskEditor imageUrl={baseImage.url} onDone={saveMask} onClose={() => setMasking(false)} />}
    </div>
  );
}

export default function CreatePage() {
  return (
    <Suspense>
      <CreateStudio />
    </Suspense>
  );
}
