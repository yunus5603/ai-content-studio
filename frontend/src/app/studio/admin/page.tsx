"use client";

import { useCallback, useEffect, useState } from "react";
import { type AdminOverview, type AdminWorkspaceRow, useApi } from "@/lib/api";
import { usd } from "@/lib/format";
import { useWorkspace } from "@/lib/workspace";

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <p className="text-xs uppercase tracking-wide text-subtle">{label}</p>
      <p className="mt-1 text-xl font-semibold tabular-nums">{value}</p>
      {sub && <p className="mt-1 text-xs text-subtle">{sub}</p>}
    </div>
  );
}

export default function AdminPage() {
  const api = useApi();
  const { me } = useWorkspace();
  const [days, setDays] = useState(30);
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [rows, setRows] = useState<AdminWorkspaceRow[]>([]);
  const [q, setQ] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [o, w] = await Promise.all([
        api<AdminOverview>(`/v1/admin/overview?days=${days}`),
        api<AdminWorkspaceRow[]>(`/v1/admin/workspaces?q=${encodeURIComponent(q)}`),
      ]);
      setOverview(o);
      setRows(w);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't load");
    }
  }, [api, days, q]);

  useEffect(() => {
    const t = setTimeout(load, 200);
    return () => clearTimeout(t);
  }, [load]);

  async function adjust(row: AdminWorkspaceRow) {
    const amount = prompt(`Add credits to "${row.name}" (USD, negative to remove)`);
    if (!amount) return;
    const reason = prompt("Reason (shown in their activity)");
    if (!reason) return;
    setError(null);
    try {
      const updated = await api<AdminWorkspaceRow>(`/v1/admin/workspaces/${row.id}/credits`, {
        method: "POST",
        body: JSON.stringify({ amount_usd: Number(amount), reason }),
      });
      setRows((all) => all.map((r) => (r.id === updated.id ? updated : r)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't adjust credits");
    }
  }

  if (!me?.user.is_platform_admin) return <p className="text-subtle">Not available.</p>;

  return (
    <div className="mx-auto max-w-6xl">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Admin</h1>
          <p className="mt-1 text-sm text-muted">Platform-wide revenue, cost and customers. Only staff see this page.</p>
        </div>
        <div className="flex gap-1 text-sm">
          {[7, 30, 90].map((d) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`rounded-full px-3 py-1 ${days === d ? "bg-ink text-white shadow-soft" : "border border-line-strong text-ink-2"}`}
            >
              {d} days
            </button>
          ))}
        </div>
      </div>

      {overview && (
        <>
          <div className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Payments received" value={usd(overview.revenue_usd)} />
            <Stat label="Credits used" value={usd(overview.customer_spend_usd)} sub={`${overview.jobs} jobs, ${overview.failed_jobs} failed`} />
            <Stat label="Provider cost" value={usd(overview.provider_cost_usd)} />
            <Stat label="Margin" value={usd(overview.margin_usd)} sub="Credits used minus provider cost" />
            <Stat label="Unspent credit" value={usd(overview.outstanding_credit_usd)} sub="Owed to customers, all time" />
            <Stat label="Free credit given" value={usd(overview.free_credit_granted_usd)} />
            <Stat label="Users" value={String(overview.users)} sub={`${overview.new_users} new`} />
            <Stat label="Workspaces" value={String(overview.workspaces)} />
          </div>
          {overview.by_model.length > 0 && (
            <div className="mt-6 rounded-xl border border-line p-4">
              <h2 className="text-sm font-medium">Spend by model</h2>
              <ul className="mt-3 divide-y divide-line text-sm">
                {overview.by_model.map((m) => (
                  <li key={m.key} className="flex justify-between py-1.5">
                    <span>{m.label}</span>
                    <span className="tabular-nums text-muted">{usd(m.spent_usd)} · {m.jobs} jobs</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}

      <div className="mt-10 flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-medium">Customers</h2>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search by workspace or owner email"
          className="w-full max-w-xs rounded-lg border border-line bg-surface px-3 py-2 text-sm"
        />
      </div>
      {error && <p className="mt-3 text-sm text-danger">{error}</p>}
      <div className="mt-3 overflow-x-auto rounded-xl border border-line">
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase tracking-wide text-subtle">
            <tr className="border-b border-line">
              <th className="px-4 py-2 font-normal">Workspace</th>
              <th className="px-4 py-2 font-normal">Owner</th>
              <th className="px-4 py-2 text-right font-normal">Balance</th>
              <th className="px-4 py-2 text-right font-normal">Purchased</th>
              <th className="px-4 py-2 text-right font-normal">Spent</th>
              <th className="px-4 py-2 text-right font-normal">Jobs</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rows.map((r) => (
              <tr key={r.id}>
                <td className="px-4 py-2">{r.name}</td>
                <td className="px-4 py-2 text-muted">{r.owner_email}</td>
                <td className="px-4 py-2 text-right tabular-nums">{usd(r.balance_usd)}</td>
                <td className="px-4 py-2 text-right tabular-nums text-muted">{usd(r.purchased_usd)}</td>
                <td className="px-4 py-2 text-right tabular-nums text-muted">{usd(r.spent_usd)}</td>
                <td className="px-4 py-2 text-right tabular-nums text-muted">{r.jobs}</td>
                <td className="px-4 py-2 text-right">
                  <button onClick={() => adjust(r)} className="text-xs text-brand hover:text-ink">Adjust credits</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
