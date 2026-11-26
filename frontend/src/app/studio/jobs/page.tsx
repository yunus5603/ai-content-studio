"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { JobCard, useJobPolling } from "@/components/job-card";
import { type Job, type Page, useApi } from "@/lib/api";
import { useCatalog } from "@/lib/catalog";
import { useWorkspace } from "@/lib/workspace";

export default function JobsPage() {
  const api = useApi();
  const { current } = useWorkspace();
  const { catalog } = useCatalog();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const models = useMemo(() => Object.fromEntries((catalog?.models ?? []).map((m) => [m.id, m])), [catalog]);

  const load = useCallback(
    async (after: string | null) => {
      if (!current) return;
      const page = await api<Page<Job>>(`/v1/workspaces/${current.id}/jobs${after ? `?cursor=${encodeURIComponent(after)}` : ""}`);
      setJobs((prev) => (after ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
    },
    [api, current],
  );

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial load
    load(null);
  }, [load]);

  const onUpdate = useCallback((job: Job) => setJobs((all) => all.map((j) => (j.id === job.id ? job : j))), []);
  useJobPolling(current?.id, jobs, onUpdate);

  async function cancel(job: Job) {
    onUpdate(await api<Job>(`/v1/workspaces/${current!.id}/jobs/${job.id}/cancel`, { method: "POST" }));
  }

  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="text-2xl font-semibold">Jobs</h1>
      {jobs.length === 0 && <p className="mt-10 text-subtle">No generations yet.</p>}
      <div className="mt-6 space-y-3">
        {jobs.map((j) => (
          <JobCard key={j.id} job={j} models={models} onCancel={cancel} />
        ))}
      </div>
      {cursor && (
        <button onClick={() => load(cursor)} className="mt-6 rounded-lg border border-line-strong px-4 py-2 text-sm">
          Load more
        </button>
      )}
    </div>
  );
}
