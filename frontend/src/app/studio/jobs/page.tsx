"use client";

import { useCallback, useEffect, useState } from "react";
import { MediaTile } from "@/components/media";
import { type Job, type Page, useApi } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";

const statusColor: Record<Job["status"], string> = {
  queued: "text-zinc-400",
  running: "text-cyan-300",
  succeeded: "text-emerald-400",
  failed: "text-red-400",
  canceled: "text-zinc-500",
};

export default function JobsPage() {
  const api = useApi();
  const { current } = useWorkspace();
  const [jobs, setJobs] = useState<Job[]>([]);

  const load = useCallback(async () => {
    if (!current) return;
    const page = await api<Page<Job>>(`/v1/workspaces/${current.id}/jobs`);
    setJobs(page.items);
  }, [api, current]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial load
    load();
    // Poll while anything is in flight. Step 2 swaps this for live updates.
    const timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  }, [load]);

  async function cancel(id: string) {
    await api(`/v1/workspaces/${current!.id}/jobs/${id}/cancel`, { method: "POST" });
    load();
  }

  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="text-2xl font-semibold">Jobs</h1>
      {jobs.length === 0 && <p className="mt-10 text-zinc-500">No generations yet.</p>}
      <ul className="mt-6 space-y-3">
        {jobs.map((j) => (
          <li key={j.id} className="rounded-xl border border-white/10 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="text-sm">
                <span className="font-medium">{j.provider}/{j.model}</span>
                <span className="text-zinc-500"> · {j.operation.replaceAll("_", " ")}</span>
              </div>
              <div className="flex items-center gap-3 text-sm">
                <span className={statusColor[j.status]}>
                  {j.status}
                  {j.status === "running" && ` ${Math.round(j.progress * 100)}%`}
                </span>
                {(j.status === "queued" || j.status === "running") && (
                  <button onClick={() => cancel(j.id)} className="text-zinc-500 hover:text-white">Cancel</button>
                )}
              </div>
            </div>
            {j.prompt && <p className="mt-2 text-sm text-zinc-300">{j.prompt}</p>}
            {j.error && <p className="mt-2 text-sm text-red-400">{j.error}</p>}
            {j.outputs.length > 0 && (
              <div className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-6">
                {j.outputs.map((a) => (
                  <MediaTile key={a.id} asset={a} />
                ))}
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
