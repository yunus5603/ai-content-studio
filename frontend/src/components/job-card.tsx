"use client";

import { useEffect } from "react";
import { MediaTile } from "@/components/media";
import { type Job, type ModelSpec, useApi } from "@/lib/api";
import { usd } from "@/lib/format";

const statusColor: Record<Job["status"], string> = {
  queued: "text-zinc-400",
  running: "text-cyan-300",
  succeeded: "text-emerald-400",
  failed: "text-red-400",
  canceled: "text-zinc-500",
};

export const isActive = (j: Job) => j.status === "queued" || j.status === "running";

/** Refreshes active jobs every 2 seconds until they finish. */
export function useJobPolling(workspaceId: string | undefined, jobs: Job[], onUpdate: (job: Job) => void) {
  const api = useApi();
  const activeIds = jobs.filter(isActive).map((j) => j.id).join(",");
  useEffect(() => {
    if (!workspaceId || !activeIds) return;
    const timer = setInterval(async () => {
      for (const id of activeIds.split(",")) {
        try {
          onUpdate(await api<Job>(`/v1/workspaces/${workspaceId}/jobs/${id}`));
        } catch {}
      }
    }, 2000);
    return () => clearInterval(timer);
  }, [api, workspaceId, activeIds, onUpdate]);
}

export function JobCard({
  job,
  models,
  onCancel,
}: {
  job: Job;
  models?: Record<string, ModelSpec>;
  onCancel?: (job: Job) => void;
}) {
  const model = models?.[job.model];
  const active = isActive(job);
  const pct = Math.round(job.progress * 100);
  return (
    <div className="rounded-xl border border-white/10 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-sm">
          <span className="font-medium">{model?.name ?? job.model}</span>
          <span className="text-zinc-500"> · {job.operation.replaceAll("_", " ")}</span>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <span className="text-zinc-500">{usd(job.price_usd ?? job.estimated_price_usd)}</span>
          <span className={statusColor[job.status]}>
            {job.status === "running" ? `generating ${pct}%` : job.status}
          </span>
          {active && onCancel && (
            <button onClick={() => onCancel(job)} className="text-zinc-500 hover:text-white">Cancel</button>
          )}
        </div>
      </div>
      {active && (
        <div className="mt-3 h-1 overflow-hidden rounded-full bg-white/10">
          <div
            className={`h-full rounded-full bg-gradient-to-r from-violet-500 to-cyan-400 transition-all ${job.status === "queued" ? "w-1/12 animate-pulse" : ""}`}
            style={job.status === "running" ? { width: `${Math.max(pct, 5)}%` } : undefined}
          />
        </div>
      )}
      {job.prompt && <p className="mt-2 line-clamp-3 text-sm text-zinc-300">{job.prompt}</p>}
      {job.error && <p className="mt-2 text-sm text-red-400">{job.error}</p>}
      {job.outputs.length > 0 && (
        <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
          {job.outputs.map((a) => (
            <MediaTile key={a.id} asset={a} />
          ))}
        </div>
      )}
    </div>
  );
}
