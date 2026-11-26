"use client";

import Link from "next/link";
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
import { SAMPLES } from "@/lib/samples";
import { IconPlay, IconSparkles } from "@/components/icons";
import { useWorkspace } from "@/lib/workspace";
import { monthlyRoom, useBilling } from "@/lib/billing";

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
    <div className="group relative h-20 w-20 overflow-hidden rounded-lg border border-line">
      {asset.media_type === "video" ? (
        <video src={asset.url ?? undefined} className="h-full w-full object-cover" muted />
      ) : (
        // eslint-disable-next-line @next/next/no-img-element -- signed storage URL
        <img src={asset.url ?? undefined} alt="" className="h-full w-full object-cover" />
      )}
      <button
        onClick={onRemove}
        className="absolute right-1 top-1 hidden h-5 w-5 rounded-full bg-ink/30 backdrop-blur-sm animate-fade-in text-xs group-hover:block"
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
  const { billing, refreshBilling } = useBilling();
  const upload = useUpload(current?.id ?? "");

  const [media, setMedia] = useState<"image" | "video">("image");
  const [op, setOp] = useState<Operation>("text_to_image");
  const [modelId, setModelId] = useState<string | null>(null);
  const [values, setValues] = useState<Record<string, ParamValue>>({});
  const [inputs, setInputs] = useState<Partial<Record<InputRole, Asset[]>>>({});
  const [prompt, setPrompt] = useState("");
  const [estimate, setEstimate] = useState<Estimate | null>(null);
  const [problem, setProblem] = useState<{ message: string; billing?: boolean } | null>(null);
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
        setProblem({ message: e instanceof Error ? e.message : "Invalid settings" });
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [api, model, op, values]);

  const onJobUpdate = useCallback(
    (job: Job) => {
      setJobs((all) => all.map((j) => (j.id === job.id ? job : j)));
      if (!["queued", "running"].includes(job.status)) refreshBilling();
    },
    [refreshBilling],
  );
  useJobPolling(current?.id, jobs, onJobUpdate);

  if (!current) return null;
  if (catalogError) return <p className="text-danger">{catalogError}</p>;
  if (!catalog) return <p className="text-subtle">Loading models…</p>;

  const canGenerate = can("generate");
  const room = billing ? monthlyRoom(billing) : null;
  const short =
    billing && estimate
      ? estimate.price_usd > billing.balance_usd
        ? "Not enough credits for this generation."
        : room != null && estimate.price_usd > room
          ? "This would go over the monthly spending limit."
          : null
      : null;
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
      setProblem({ message: e instanceof Error ? e.message : "Couldn't enhance the prompt" });
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
      refreshBilling();
    } catch (e) {
      setProblem({
        message: e instanceof Error ? e.message : "Couldn't start the generation",
        billing: e instanceof ApiError && (e.status === 402 || (e.status === 403 && e.message.includes("limit"))),
      });
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
      setProblem({ message: e instanceof Error ? e.message : "Couldn't save the mask" });
    }
  }

  const baseImage = inputs.image?.[0];

  return (
    <div className="mx-auto grid max-w-6xl gap-6 lg:grid-cols-[1fr_320px]">
      <section className="min-w-0">
        <header className="mb-6">
          <h1 className="text-2xl font-semibold tracking-tight">What will you create today?</h1>
          <p className="mt-1 text-sm text-muted">Describe it, pick a model, and results land in your gallery automatically.</p>
        </header>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex rounded-full border border-line bg-surface p-1 shadow-soft">
            {(["image", "video"] as const).map((m) => (
              <button
                key={m}
                onClick={() => switchMedia(m)}
                className={`rounded-full px-4 py-1.5 text-sm capitalize transition-all duration-200 ${media === m ? "bg-ink text-white shadow-soft" : "text-ink-2 hover:text-ink"}`}
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
                className={`rounded-full px-3 py-1.5 text-sm transition-colors duration-200 ${op === o ? "bg-brand-soft font-medium text-brand-ink" : "text-muted hover:bg-surface-2 hover:text-ink"}`}
              >
                {catalog.operations[o]}
              </button>
            ))}
          </div>
        </div>

        {!canGenerate && (
          <p className="mt-4 rounded-lg border border-warning/30 bg-warning/10 p-3 text-sm text-warning">
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
                    <p className="mb-2 text-xs text-muted">{spec.label}</p>
                    <div className="flex items-center gap-3">
                      {list[0] && <Thumb asset={list[0]} onRemove={() => setInputs((c) => ({ ...c, mask: [] }))} />}
                      <button
                        disabled={!baseImage?.url}
                        onClick={() => setMasking(true)}
                        className="rounded-lg border border-line-strong px-3 py-2 text-sm hover:bg-surface-2 disabled:opacity-40"
                      >
                        {list[0] ? "Repaint mask" : "Paint mask"}
                      </button>
                      {!baseImage && <span className="text-xs text-subtle">Choose the image first</span>}
                    </div>
                  </div>
                );
              }
              return (
                <div key={spec.role}>
                  <p className="mb-2 text-xs text-muted">
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
                        className="grid h-20 w-20 place-items-center rounded-lg border border-dashed border-line-strong text-2xl text-subtle hover:bg-surface-2 disabled:opacity-40"
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

        <div className="card mt-5 p-4 transition-shadow duration-300 focus-within:border-brand/40 focus-within:shadow-card">
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder={OP_HINTS[op]}
            rows={5}
            disabled={!canGenerate}
            className="w-full resize-y bg-transparent outline-none placeholder:text-subtle"
          />
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <button
              onClick={enhance}
              disabled={!canGenerate || enhancing || !prompt.trim()}
              className="btn btn-secondary"
            >
              <IconSparkles className={`h-4 w-4 text-brand ${enhancing ? "animate-spin" : ""}`} />
              {enhancing ? "Enhancing…" : "Enhance prompt"}
            </button>
            <div className="ml-auto flex items-center gap-3">
              {estimate && (
                <span className="text-right text-sm text-muted" title="Provider price plus 10% platform fee">
                  ≈ {usd(estimate.price_usd)}
                  {billing && (
                    <span className={`block text-xs ${short ? "text-warning" : "text-subtle"}`}>
                      {usd(billing.balance_usd)} left
                    </span>
                  )}
                </span>
              )}
              <button
                onClick={generate}
                disabled={!canGenerate || submitting || !prompt.trim() || !estimate || missing.length > 0}
                className="btn btn-brand"
              >
                {submitting ? "Starting…" : "Generate"}
              </button>
            </div>
          </div>
          {missing.length > 0 && <p className="mt-2 text-xs text-subtle">Add: {missing.map((m) => m.label).join(", ")}</p>}
          {short && !problem && (
            <p className="mt-2 text-sm text-warning">
              {short}{" "}
              <Link href="/studio/billing" className="underline underline-offset-2">
                {short.startsWith("Not enough") ? "Buy credits" : "See billing"}
              </Link>
            </p>
          )}
          {problem && (
            <p className="mt-2 text-sm text-danger">
              {problem.message}{" "}
              {problem.billing && (
                <Link href="/studio/billing" className="text-ink underline underline-offset-2">
                  Go to billing
                </Link>
              )}
            </p>
          )}
        </div>

        {jobs.length === 0 && (
          <Inspiration
            media={media}
            onPick={(p) => setPrompt(p)}
          />
        )}

        <div className="mt-8 space-y-3">
          {jobs.map((j) => (
            <JobCard key={j.id} job={j} models={modelsById} onCancel={cancel} />
          ))}
        </div>
      </section>

      <aside id="settings" className="card space-y-5 p-5 lg:sticky lg:top-8 lg:self-start">
        <div>
          <label htmlFor="model-select" className="label">Model</label>
          <select
            id="model-select"
            value={modelId ?? ""}
            onChange={(e) => chooseModel(op, e.target.value)}
            className="input cursor-pointer"
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
            <div className="mt-2 text-xs text-subtle">
              <p>{model.description}</p>
              {model.shutdown_date && <p className="mt-1 text-warning">Retires {model.shutdown_date}</p>}
              <div className="mt-2 flex flex-wrap gap-1">
                {model.tags.map((t) => (
                  <span key={t} className="rounded-md bg-surface-2 px-1.5 py-0.5 text-muted">{t.replace("-", " ")}</span>
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

function Inspiration({ media, onPick }: { media: "image" | "video"; onPick: (prompt: string) => void }) {
  const ideas = [...SAMPLES].sort((a, b) => Number(b.media === media) - Number(a.media === media)).slice(0, 4);
  return (
    <div className="mt-8">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold">Need an idea?</h2>
        <span className="text-xs text-subtle">Click one to use its prompt</span>
      </div>
      <div className="stagger grid grid-cols-2 gap-3 sm:grid-cols-4">
        {ideas.map((s) => (
          <button
            key={s.id}
            onClick={() => onPick(s.prompt)}
            className="card card-hover group overflow-hidden p-1.5 text-left"
          >
            <div className="relative overflow-hidden rounded-[10px]">
              {/* eslint-disable-next-line @next/next/no-img-element -- static showcase asset */}
              <img src={s.src} alt="" className="aspect-[4/3] w-full object-cover transition duration-500 group-hover:scale-105" />
              {s.media === "video" && (
                <span className="absolute left-1.5 top-1.5 grid h-6 w-6 place-items-center rounded-full bg-white/85 text-ink shadow-soft">
                  <IconPlay className="h-3 w-3" />
                </span>
              )}
            </div>
            <p className="px-1 pb-0.5 pt-2 text-xs font-medium">{s.title}</p>
            <p className="line-clamp-2 px-1 pb-1 text-[11px] leading-snug text-subtle">{s.prompt}</p>
          </button>
        ))}
      </div>
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
