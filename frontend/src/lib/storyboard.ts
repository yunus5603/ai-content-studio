import type { Asset, ParamValue } from "./api";

export type JobBrief = {
  id: string;
  status: "queued" | "running" | "succeeded" | "failed" | "canceled";
  progress: number;
  error: string | null;
  price_usd: number;
};

export type StepCost = { price_usd: number | null; problem: string | null };

export type Shot = {
  id: string;
  position: number;
  title: string | null;
  description: string;
  motion: string | null;
  duration_seconds: number | null;
  end_on_next: boolean;
  references: Asset[];
  keyframe: Asset | null;
  keyframe_job: JobBrief | null;
  clip: Asset | null;
  clip_job: JobBrief | null;
  clip_stale: boolean;
  keyframe_cost: StepCost;
  clip_cost: StepCost;
};

export type Storyboard = {
  id: string;
  workspace_id: string;
  created_by_id: string;
  title: string;
  logline: string | null;
  style: string | null;
  image_model: string;
  image_params: Record<string, ParamValue>;
  video_model: string;
  video_params: Record<string, ParamValue>;
  transition: "cut" | "fade";
  created_at: string;
  updated_at: string;
  shots: Shot[];
  film: Asset | null;
  film_job: JobBrief | null;
  film_stale: boolean;
  totals: {
    shots: number;
    keyframes_done: number;
    clips_done: number;
    seconds: number;
    missing_keyframes_usd: number;
    missing_clips_usd: number;
    all_keyframes_usd: number;
    all_clips_usd: number;
    spent_usd: number;
  };
};

export type StoryboardSummary = {
  id: string;
  title: string;
  logline: string | null;
  shot_count: number;
  keyframes_done: number;
  clips_done: number;
  cover: Asset | null;
  has_film: boolean;
  updated_at: string;
};

export const isActive = (j: JobBrief | null) => !!j && (j.status === "queued" || j.status === "running");

export function anyActive(sb: Storyboard): boolean {
  return isActive(sb.film_job) || sb.shots.some((s) => isActive(s.keyframe_job) || isActive(s.clip_job));
}

/** "Wide shot of a lighthouse\nClose-up of the keeper" -> one shot per line. */
export function shotsFromText(text: string) {
  return text
    .split("\n")
    .map((l) => l.replace(/^\s*(\d+[.)]|[-*•])\s*/, "").trim())
    .filter(Boolean)
    .map((description) => ({ description }));
}
