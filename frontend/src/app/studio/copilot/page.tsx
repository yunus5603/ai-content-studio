"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AssetModal } from "@/components/asset-modal";
import { AssetPicker } from "@/components/asset-picker";
import { MediaTile } from "@/components/media";
import { ApiError, type Asset, type ModelSpec, useApi } from "@/lib/api";
import { useBilling } from "@/lib/billing";
import { useCatalog } from "@/lib/catalog";
import { type Plan, type PlanStep, type Preference, examples, keySettings, preferences } from "@/lib/copilot";
import { usd } from "@/lib/format";
import { useWorkspace } from "@/lib/workspace";

const statusStyle: Record<string, string> = {
  pending: "bg-white/5 text-zinc-400",
  queued: "bg-sky-400/15 text-sky-300",
  running: "bg-violet-400/15 text-violet-300",
  succeeded: "bg-emerald-400/15 text-emerald-300",
  failed: "bg-red-400/15 text-red-300",
  canceled: "bg-white/5 text-zinc-500",
  skipped: "bg-white/5 text-zinc-500",
  draft: "bg-amber-400/15 text-amber-300",
};

function Badge({ status }: { status: string }) {
  return <span className={`rounded-full px-2 py-0.5 text-xs ${statusStyle[status] ?? ""}`}>{status === "draft" ? "waiting for you" : status}</span>;
}

function StepCard({
  step,
  index,
  plan,
  models,
  editable,
  onChange,
  onRemove,
  onOpen,
}: {
  step: PlanStep;
  index: number;
  plan: Plan;
  models: ModelSpec[];
  editable: boolean;
  onChange: (patch: Partial<Pick<PlanStep, "prompt" | "model" | "title">>) => void;
  onRemove: () => void;
  onOpen: (a: Asset) => void;
}) {
  const [prompt, setPrompt] = useState(step.prompt);
  // eslint-disable-next-line react-hooks/set-state-in-effect -- keep the editor in sync after saves and revisions
  useEffect(() => setPrompt(step.prompt), [step.prompt]);
  const job = plan.jobs.find((j) => j.id === step.job_id);
  const options = models.filter((m) => m.operations.some((o) => o.operation === step.operation));
  const model = models.find((m) => m.id === step.model);
  const from = step.inputs.filter((i) => i.from_step).map((i) => plan.steps.findIndex((s) => s.id === i.from_step) + 1);
  const attached = step.inputs.filter((i) => i.asset_id).length;

  return (
    <li className="relative pl-12" data-step={step.id}>
      <span className="absolute left-0 top-4 grid h-8 w-8 place-items-center rounded-full border border-white/15 bg-zinc-950 text-sm font-medium">
        {step.status === "succeeded" ? "✓" : index + 1}
      </span>
      <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <p className="font-medium">{step.title}</p>
            <p className="mt-0.5 text-xs text-zinc-500">
              {step.operation.replaceAll("_", " ")}
              {from.length > 0 && <> · uses the result of step {from.join(", ")}</>}
              {attached > 0 && <> · uses your attached {attached === 1 ? "file" : "files"}</>}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {plan.status !== "draft" && <Badge status={step.status} />}
            <span className="text-sm tabular-nums text-zinc-300">{usd(step.estimated_price_usd)}</span>
          </div>
        </div>

        {editable ? (
          <select
            value={step.model}
            onChange={(e) => onChange({ model: e.target.value })}
            className="mt-3 w-full rounded-lg border border-white/10 bg-black/40 px-2 py-2 text-sm"
          >
            {options.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
                {m.status === "preview" ? " (preview)" : ""}
              </option>
            ))}
          </select>
        ) : (
          <p className="mt-3 text-sm text-zinc-300">{model?.name ?? step.model}</p>
        )}
        <div className="mt-2 flex flex-wrap gap-1.5">
          {keySettings(step.params).map((s) => (
            <span key={s} className="rounded-md border border-white/10 px-2 py-0.5 text-xs text-zinc-400">{s}</span>
          ))}
        </div>

        {editable ? (
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onBlur={() => prompt.trim() && prompt !== step.prompt && onChange({ prompt })}
            rows={3}
            className="mt-3 w-full resize-y rounded-lg border border-white/10 bg-black/30 p-3 text-sm text-zinc-200 outline-none focus:border-violet-400/50"
          />
        ) : (
          <p className="mt-3 whitespace-pre-wrap text-sm text-zinc-300">{step.prompt}</p>
        )}
        {step.why && <p className="mt-2 text-xs text-zinc-500">Why: {step.why}</p>}

        {job && (job.status === "running" || job.status === "queued") && (
          <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/5">
            <div className="h-full rounded-full bg-violet-400 transition-all" style={{ width: `${Math.max(job.progress * 100, 6)}%` }} />
          </div>
        )}
        {step.error && step.status !== "pending" && <p className="mt-2 text-sm text-red-300">{step.error}</p>}
        {job && job.outputs.length > 0 && (
          <div className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-4">
            {job.outputs.map((a) => (
              <MediaTile key={a.id} asset={a} onOpen={onOpen} />
            ))}
          </div>
        )}
        {editable && plan.steps.length > 1 && (
          <button onClick={onRemove} className="mt-3 text-xs text-zinc-500 hover:text-red-300">Remove step</button>
        )}
      </div>
    </li>
  );
}

export default function CopilotPage() {
  const api = useApi();
  const { current, can } = useWorkspace();
  const { catalog } = useCatalog();
  const { billing, refreshBilling } = useBilling();
  const [goal, setGoal] = useState("");
  const [preference, setPreference] = useState<Preference>("balanced");
  const [budget, setBudget] = useState("");
  const [autorun, setAutorun] = useState(false);
  const [attachments, setAttachments] = useState<Asset[]>([]);
  const [picking, setPicking] = useState(false);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [history, setHistory] = useState<Plan[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<{ message: string; billing?: boolean } | null>(null);
  const [change, setChange] = useState("");
  const [open, setOpen] = useState<Asset | null>(null);

  const base = current ? `/v1/workspaces/${current.id}/copilot/plans` : "";
  const models = useMemo(() => (catalog?.models ?? []).filter((m) => m.provider !== "debug"), [catalog]);
  const modelsById = useMemo(() => Object.fromEntries((catalog?.models ?? []).map((m) => [m.id, m])), [catalog]);

  const loadHistory = useCallback(async () => {
    if (base) setHistory(await api<Plan[]>(base));
  }, [api, base]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial load
    loadHistory();
  }, [loadHistory]);

  // Follow a running plan.
  useEffect(() => {
    if (!plan || plan.status !== "running") return;
    const timer = setInterval(async () => {
      const next = await api<Plan>(`${base}/${plan.id}`);
      setPlan(next);
      if (next.status !== "running") {
        refreshBilling();
        loadHistory();
      }
    }, 2000);
    return () => clearInterval(timer);
  }, [api, base, plan, refreshBilling, loadHistory]);

  async function act(label: string, fn: () => Promise<Plan>) {
    setBusy(label);
    setError(null);
    try {
      const next = await fn();
      setPlan(next);
      if (next.status !== "draft") refreshBilling();
      loadHistory();
    } catch (e) {
      setError({
        message: e instanceof Error ? e.message : "Something went wrong",
        billing: e instanceof ApiError && (e.status === 402 || e.status === 403),
      });
    } finally {
      setBusy(null);
    }
  }

  const ask = () =>
    act("plan", () =>
      api<Plan>(base, {
        method: "POST",
        body: JSON.stringify({
          goal,
          preference,
          budget_usd: budget ? Number(budget) : null,
          attachments: attachments.map((a) => a.id),
          autorun,
        }),
      }),
    );
  const patchStep = (step: PlanStep, patch: object) =>
    act("edit", () => api<Plan>(`${base}/${plan!.id}/steps/${step.id}`, { method: "PATCH", body: JSON.stringify(patch) }));
  const removeStep = (step: PlanStep) => act("edit", () => api<Plan>(`${base}/${plan!.id}/steps/${step.id}`, { method: "DELETE" }));
  const revise = (body: object) =>
    act("revise", () => api<Plan>(`${base}/${plan!.id}/revise`, { method: "POST", body: JSON.stringify(body) })).then(() => setChange(""));
  const run = () => act("run", () => api<Plan>(`${base}/${plan!.id}/run`, { method: "POST" }));
  const cancel = () => act("cancel", () => api<Plan>(`${base}/${plan!.id}/cancel`, { method: "POST" }));

  if (!current) return null;
  if (!can("generate")) return <p className="text-zinc-400">Your role can view the workspace but not generate.</p>;
  const editable = plan?.status === "draft";
  const short = plan && billing && editable && plan.estimated_price_usd > billing.balance_usd;

  return (
    <div className="mx-auto grid max-w-6xl gap-8 lg:grid-cols-[1fr_260px]">
      <div>
        <h1 className="text-2xl font-semibold">Copilot</h1>
        <p className="mt-1 text-sm text-zinc-400">
          Describe what you want. Copilot plans the steps, picks the models and settings, and shows the price. Nothing runs until you approve.
        </p>

        <div className="mt-6 rounded-2xl border border-white/10 bg-white/[0.03] p-4" id="copilot-composer">
          <textarea
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && goal.trim().length > 2) ask();
            }}
            rows={3}
            placeholder="e.g. A 30-second launch teaser for our new running shoe, energetic, vertical for Instagram"
            className="w-full resize-y bg-transparent outline-none placeholder:text-zinc-600"
          />
          {!plan && !goal && (
            <div className="mt-2 flex flex-wrap gap-2">
              {examples.map((ex) => (
                <button key={ex} onClick={() => setGoal(ex)} className="rounded-full border border-white/10 px-3 py-1 text-xs text-zinc-400 hover:border-white/30 hover:text-white">
                  {ex.length > 52 ? `${ex.slice(0, 52)}…` : ex}
                </button>
              ))}
            </div>
          )}
          {attachments.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {attachments.map((a) => (
                <div key={a.id} className="relative h-16 w-16 overflow-hidden rounded-lg border border-white/10">
                  <MediaTile asset={a} />
                  <button
                    onClick={() => setAttachments((all) => all.filter((x) => x.id !== a.id))}
                    className="absolute right-0.5 top-0.5 rounded-full bg-black/70 px-1.5 text-xs"
                    aria-label="Remove attachment"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          )}
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <div className="flex rounded-full border border-white/10 p-0.5 text-sm">
              {preferences.map((p) => (
                <button
                  key={p.value}
                  title={p.hint}
                  onClick={() => setPreference(p.value)}
                  className={`rounded-full px-3 py-1 ${preference === p.value ? "bg-white text-black" : "text-zinc-400 hover:text-white"}`}
                >
                  {p.label}
                </button>
              ))}
            </div>
            <button onClick={() => setPicking(true)} className="rounded-full border border-white/10 px-3 py-1 text-sm text-zinc-300 hover:border-white/30">
              + Attach image
            </button>
            <label className="flex items-center gap-1 rounded-full border border-white/10 px-3 py-1 text-sm text-zinc-400">
              Budget $
              <input
                value={budget}
                onChange={(e) => setBudget(e.target.value.replace(/[^0-9.]/g, ""))}
                placeholder="any"
                inputMode="decimal"
                className="w-12 bg-transparent text-white outline-none placeholder:text-zinc-600"
              />
            </label>
            <label className="flex items-center gap-1.5 text-sm text-zinc-400" title="Start right away when the plan costs $0.50 or less">
              <input type="checkbox" checked={autorun} onChange={(e) => setAutorun(e.target.checked)} />
              Autopilot for small jobs
            </label>
            <button
              onClick={ask}
              disabled={goal.trim().length < 3 || busy !== null}
              className="ml-auto rounded-lg bg-white px-5 py-2 text-sm font-medium text-black disabled:opacity-40"
            >
              {busy === "plan" ? "Planning…" : "✦ Plan it"}
            </button>
          </div>
        </div>

        {error && (
          <p className="mt-4 text-sm text-red-300">
            {error.message}{" "}
            {error.billing && <Link href="/studio/billing" className="text-white underline underline-offset-2">Go to billing</Link>}
          </p>
        )}

        {plan && (
          <section className="mt-8" id="copilot-plan">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-lg font-semibold">{plan.title || "Your plan"}</h2>
                  <Badge status={plan.status} />
                </div>
                <p className="mt-1 text-sm text-zinc-400">{plan.summary}</p>
              </div>
              <div className="text-right">
                <p className="text-2xl font-semibold tabular-nums">{usd(plan.status === "draft" || plan.status === "running" ? plan.estimated_price_usd : plan.charged_usd)}</p>
                <p className="text-xs text-zinc-500">{plan.status === "draft" ? "estimated total, incl. fees" : plan.status === "running" ? "estimated, charged as steps finish" : "charged"}</p>
              </div>
            </div>
            {plan.notes.length > 0 && (
              <ul className="mt-3 space-y-1 text-sm text-amber-200/90">
                {plan.notes.map((n) => (
                  <li key={n}>• {n}</li>
                ))}
              </ul>
            )}

            <ol className="relative mt-6 space-y-4 before:absolute before:bottom-6 before:left-4 before:top-6 before:w-px before:bg-white/10">
              {plan.steps.map((s, i) => (
                <StepCard
                  key={s.id}
                  step={s}
                  index={i}
                  plan={plan}
                  models={models}
                  editable={!!editable && busy === null}
                  onChange={(patch) => patchStep(s, patch)}
                  onRemove={() => removeStep(s)}
                  onOpen={setOpen}
                />
              ))}
            </ol>

            {editable && (
              <div className="mt-6 space-y-4 rounded-2xl border border-white/10 p-4">
                <form
                  className="flex gap-2"
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (change.trim()) revise({ instruction: change });
                  }}
                >
                  <input
                    value={change}
                    onChange={(e) => setChange(e.target.value)}
                    placeholder="Ask for a change: “make it vertical”, “add a second scene”, “cheaper”…"
                    className="min-w-0 flex-1 rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm"
                  />
                  <button disabled={busy !== null || !change.trim()} className="rounded-lg border border-white/15 px-4 text-sm disabled:opacity-40">
                    {busy === "revise" ? "Revising…" : "Revise"}
                  </button>
                </form>
                <div className="flex flex-wrap items-center gap-3">
                  <span className="text-sm text-zinc-500">Re-plan for</span>
                  {preferences
                    .filter((p) => p.value !== plan.preference)
                    .map((p) => (
                      <button key={p.value} onClick={() => revise({ preference: p.value })} disabled={busy !== null} className="rounded-full border border-white/10 px-3 py-1 text-sm text-zinc-300 hover:border-white/30">
                        {p.label}
                      </button>
                    ))}
                  <div className="ml-auto flex items-center gap-3">
                    {billing && <span className={`text-sm ${short ? "text-amber-300" : "text-zinc-500"}`}>Balance {usd(billing.balance_usd)}</span>}
                    {short ? (
                      <Link href="/studio/billing" className="rounded-lg bg-amber-300 px-5 py-2 text-sm font-medium text-black">Buy credits</Link>
                    ) : (
                      <button onClick={run} disabled={busy !== null} id="run-plan" className="rounded-lg bg-violet-500 px-5 py-2 text-sm font-medium text-white hover:bg-violet-400 disabled:opacity-40">
                        {busy === "run" ? "Starting…" : `Approve and run · ${usd(plan.estimated_price_usd)}`}
                      </button>
                    )}
                  </div>
                </div>
              </div>
            )}
            {plan.status === "running" && (
              <button onClick={cancel} disabled={busy !== null} className="mt-6 rounded-lg border border-white/15 px-4 py-2 text-sm text-zinc-300">
                Stop plan
              </button>
            )}
            {plan.error && plan.status !== "running" && <p className="mt-4 text-sm text-red-300">{plan.error}</p>}
            {plan.status === "succeeded" && (
              <p className="mt-6 text-sm text-zinc-400">
                Done. Everything is saved in your <Link href="/studio/gallery" className="text-white underline underline-offset-2">Gallery</Link>.
              </p>
            )}
          </section>
        )}
      </div>

      <aside>
        <h2 className="text-sm uppercase tracking-wide text-zinc-500">Recent plans</h2>
        {history.length === 0 && <p className="mt-3 text-sm text-zinc-500">Your plans will show up here.</p>}
        <ul className="mt-3 space-y-2">
          {history.map((h) => (
            <li key={h.id}>
              <button
                onClick={() => setPlan(h)}
                className={`w-full rounded-xl border px-3 py-2 text-left text-sm ${plan?.id === h.id ? "border-violet-400/50 bg-violet-400/10" : "border-white/10 hover:border-white/25"}`}
              >
                <span className="line-clamp-1">{h.title || h.goal}</span>
                <span className="mt-1 flex items-center justify-between text-xs text-zinc-500">
                  <Badge status={h.status} />
                  {usd(h.status === "draft" ? h.estimated_price_usd : h.charged_usd)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      {picking && (
        <AssetPicker
          workspaceId={current.id}
          mediaType="image"
          onPick={(a) => {
            setAttachments((all) => (all.some((x) => x.id === a.id) ? all : [...all, a]).slice(0, 4));
            setPicking(false);
          }}
          onClose={() => setPicking(false)}
        />
      )}
      {open && <AssetModal asset={open} models={modelsById} onClose={() => setOpen(null)} onDeleted={() => setOpen(null)} />}
    </div>
  );
}
