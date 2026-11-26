import type { InputRole, Job, Operation, ParamValue } from "./api";

export type Preference = "quality" | "balanced" | "budget";
export type StepStatus = "pending" | "queued" | "running" | "succeeded" | "failed" | "canceled" | "skipped";

export type StepInput = { role: InputRole; asset_id: string | null; from_step: string | null; output_index: number };

export type PlanStep = {
  id: string;
  title: string;
  model: string;
  operation: Operation;
  prompt: string;
  params: Record<string, ParamValue>;
  inputs: StepInput[];
  why: string;
  estimated_price_usd: number;
  status: StepStatus;
  job_id: string | null;
  error: string | null;
};

export type Plan = {
  id: string;
  goal: string;
  preference: Preference;
  budget_usd: number | null;
  attachments: string[];
  title: string;
  summary: string;
  notes: string[];
  steps: PlanStep[];
  planner: "llm" | "rules";
  status: "draft" | "running" | "succeeded" | "failed" | "canceled";
  error: string | null;
  estimated_price_usd: number;
  charged_usd: number;
  can_autorun: boolean;
  created_at: string;
  jobs: Job[];
};

export const preferences: { value: Preference; label: string; hint: string }[] = [
  { value: "quality", label: "Best quality", hint: "Top models and settings" },
  { value: "balanced", label: "Balanced", hint: "Good quality, fair price" },
  { value: "budget", label: "Lowest cost", hint: "Cheapest that does the job" },
];

export const examples = [
  "An 8-second vertical teaser for a cozy coffee shop at sunrise, with ambient cafe sounds",
  "4 logo concepts for an artisan bakery called “Crumb & Co”",
  "A product photo of a perfume bottle on wet black marble, then animate a slow orbit",
  "Turn my photo into a watercolor painting",
];

/** Settings worth showing on a step card, in a readable form. */
export function keySettings(params: Record<string, ParamValue>): string[] {
  const out: string[] = [];
  const p = params;
  if (p.duration_seconds) out.push(`${p.duration_seconds}s`);
  if (p.aspect_ratio) out.push(String(p.aspect_ratio));
  if (p.size && p.size !== "auto") out.push(String(p.size));
  if (p.resolution) out.push(String(p.resolution));
  if (p.quality) out.push(`${p.quality} quality`);
  if (typeof p.generate_audio === "boolean") out.push(p.generate_audio ? "with audio" : "no audio");
  const n = Number(p.n ?? p.number_of_videos ?? 1);
  if (n > 1) out.push(`×${n}`);
  return out;
}
