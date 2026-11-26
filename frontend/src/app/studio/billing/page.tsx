"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { type CreditEntry, type Page, type UsageReport, type UsageRow, useApi } from "@/lib/api";
import { useBilling } from "@/lib/billing";
import { usd } from "@/lib/format";
import { useWorkspace } from "@/lib/workspace";

const kindLabel: Record<CreditEntry["kind"], string> = {
  signup_grant: "Free credits",
  purchase: "Purchase",
  job_hold: "Generation",
  job_settle: "Adjustment",
  adjustment: "Credit adjustment",
};

function Card({ label, value, sub }: { label: string; value: string; sub?: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
      <p className="text-xs uppercase tracking-wide text-zinc-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      {sub && <div className="mt-1 text-xs text-zinc-500">{sub}</div>}
    </div>
  );
}

function Bars({ title, rows }: { title: string; rows: UsageRow[] }) {
  const max = Math.max(...rows.map((r) => r.spent_usd), 0.000001);
  return (
    <div className="rounded-xl border border-white/10 p-4">
      <h3 className="text-sm font-medium">{title}</h3>
      {rows.length === 0 && <p className="mt-3 text-sm text-zinc-500">No usage yet.</p>}
      <ul className="mt-3 space-y-2.5">
        {rows.map((r) => (
          <li key={r.key} className="text-sm">
            <div className="flex justify-between gap-3">
              <span className="truncate text-zinc-300">{r.label}</span>
              <span className="shrink-0 tabular-nums text-zinc-400">
                {usd(r.spent_usd)} · {r.jobs} {r.jobs === 1 ? "job" : "jobs"}
              </span>
            </div>
            <div className="mt-1 h-1.5 rounded-full bg-white/5">
              <div className="h-1.5 rounded-full bg-violet-400" style={{ width: `${(r.spent_usd / max) * 100}%` }} />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Daily({ rows, days }: { rows: UsageRow[]; days: number }) {
  const byDay = Object.fromEntries(rows.map((r) => [r.key, r]));
  const series = Array.from({ length: days }, (_, i) => {
    const d = new Date();
    d.setDate(d.getDate() - (days - 1 - i));
    const key = d.toISOString().slice(0, 10);
    return { key, spent: byDay[key]?.spent_usd ?? 0, jobs: byDay[key]?.jobs ?? 0 };
  });
  const max = Math.max(...series.map((s) => s.spent), 0.000001);
  return (
    <div className="rounded-xl border border-white/10 p-4">
      <h3 className="text-sm font-medium">Daily spend</h3>
      <div className="mt-4 flex h-28 items-end gap-[3px]">
        {series.map((s) => (
          <div
            key={s.key}
            title={`${s.key}: ${usd(s.spent)} (${s.jobs} jobs)`}
            className="flex-1 rounded-t-sm bg-violet-400/80 hover:bg-violet-300"
            style={{ height: `${Math.max((s.spent / max) * 100, s.spent > 0 ? 4 : 1)}%`, opacity: s.spent > 0 ? 1 : 0.2 }}
          />
        ))}
      </div>
      <div className="mt-1 flex justify-between text-xs text-zinc-500">
        <span>{series[0]?.key}</span>
        <span>Today</span>
      </div>
    </div>
  );
}

function BillingPage() {
  const api = useApi();
  const params = useSearchParams();
  const { current, can } = useWorkspace();
  const { billing, refreshBilling } = useBilling();
  const [usage, setUsage] = useState<UsageReport | null>(null);
  const [entries, setEntries] = useState<CreditEntry[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [limit, setLimit] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [days, setDays] = useState(30);
  const owner = can("manage_billing");
  const base = current ? `/v1/workspaces/${current.id}` : "";
  const checkout = params.get("checkout");

  const load = useCallback(async () => {
    if (!base) return;
    const [u, page] = await Promise.all([
      api<UsageReport>(`${base}/billing/usage?days=${days}`),
      api<Page<CreditEntry>>(`${base}/billing/entries?limit=25`),
    ]);
    setUsage(u);
    setEntries(page.items);
    setCursor(page.next_cursor);
  }, [api, base, days]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial load
    load();
    if (checkout === "success") refreshBilling();
  }, [load, checkout, refreshBilling]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- mirror the saved limit into the input
    setLimit(billing?.monthly_limit_usd != null ? String(billing.monthly_limit_usd) : "");
  }, [billing?.monthly_limit_usd]);

  async function more() {
    const page = await api<Page<CreditEntry>>(`${base}/billing/entries?limit=25&cursor=${encodeURIComponent(cursor!)}`);
    setEntries((all) => [...all, ...page.items]);
    setCursor(page.next_cursor);
  }

  async function buy(amount: number) {
    setError(null);
    setBusy(amount);
    try {
      if (billing?.payments_enabled) {
        const { url } = await api<{ url: string }>(`${base}/billing/checkout`, {
          method: "POST",
          body: JSON.stringify({ amount_usd: amount }),
        });
        window.location.assign(url);
        return;
      }
      await api(`${base}/billing/dev-topup`, { method: "POST", body: JSON.stringify({ amount_usd: amount }) });
      await Promise.all([refreshBilling(), load()]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't start checkout");
    }
    setBusy(null);
  }

  async function saveLimit() {
    setError(null);
    try {
      await api(`${base}/billing/limit`, {
        method: "PUT",
        body: JSON.stringify({ monthly_limit_usd: limit.trim() === "" ? null : Number(limit) }),
      });
      await refreshBilling();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save the limit");
    }
  }

  if (!current || !billing) return <p className="text-zinc-500">Loading…</p>;
  const canBuy = owner && (billing.payments_enabled || billing.dev_topup_enabled);
  const wsLimit = billing.monthly_limit_usd;
  const myLimit = billing.my_monthly_limit_usd;

  return (
    <div className="mx-auto max-w-5xl">
      <h1 className="text-2xl font-semibold">Billing</h1>
      <p className="mt-1 text-sm text-zinc-400">
        You pay the model provider&apos;s price plus a {Math.round(billing.platform_fee * 100)}% platform fee. Credits never expire.
      </p>

      {checkout === "success" && (
        <p className="mt-4 rounded-lg border border-emerald-400/30 bg-emerald-400/10 p-3 text-sm text-emerald-200">
          Payment received. Your credits will show up in a few seconds.
        </p>
      )}
      {checkout === "canceled" && (
        <p className="mt-4 rounded-lg border border-white/10 p-3 text-sm text-zinc-400">Checkout canceled. You weren&apos;t charged.</p>
      )}

      <div className="mt-6 grid gap-3 sm:grid-cols-3">
        <Card label="Credit balance" value={usd(billing.balance_usd)} sub={current.is_personal ? "Your personal workspace" : current.name} />
        <Card
          label="Spent this month"
          value={usd(billing.spent_this_month_usd)}
          sub={wsLimit != null ? `of ${usd(wsLimit)} workspace limit` : "No workspace limit"}
        />
        <Card
          label="Your spend this month"
          value={usd(billing.my_spent_this_month_usd)}
          sub={myLimit != null ? `of ${usd(myLimit)} personal limit` : "No personal limit"}
        />
      </div>

      {owner && (
        <section className="mt-8 rounded-xl border border-white/10 p-5" id="buy-credits">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="font-medium">Add credits</h2>
            {!billing.payments_enabled && billing.dev_topup_enabled && (
              <span className="rounded-full bg-amber-400/15 px-2 py-0.5 text-xs text-amber-300">Test mode: no card needed</span>
            )}
          </div>
          {canBuy ? (
            <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-5">
              {billing.credit_packs_usd.map((amount) => (
                <button
                  key={amount}
                  onClick={() => buy(amount)}
                  disabled={busy !== null}
                  className="rounded-xl border border-white/10 bg-white/[0.03] px-4 py-4 text-left hover:border-violet-400/60 hover:bg-violet-400/10 disabled:opacity-50"
                >
                  <span className="block text-xl font-semibold">${amount}</span>
                  <span className="text-xs text-zinc-500">{busy === amount ? "Opening…" : "in credits"}</span>
                </button>
              ))}
            </div>
          ) : (
            <p className="mt-3 text-sm text-zinc-400">Payments aren&apos;t set up on this server yet.</p>
          )}
          <p className="mt-3 text-xs text-zinc-500">Secure card payment through Stripe. Receipts are emailed to you.</p>

          <div className="mt-6 border-t border-white/10 pt-5">
            <h3 className="text-sm font-medium">Monthly spending limit</h3>
            <p className="mt-1 text-xs text-zinc-500">
              Generations stop when the workspace has spent this much in a calendar month. Leave empty for no limit.
              {!current.is_personal && <> Set limits for individual people on the <Link href="/studio/team" className="underline">Team</Link> page.</>}
            </p>
            <div className="mt-3 flex max-w-sm gap-2">
              <div className="flex flex-1 items-center rounded-lg border border-white/10 bg-black/30 px-3">
                <span className="text-zinc-500">$</span>
                <input
                  id="workspace-limit"
                  inputMode="decimal"
                  value={limit}
                  onChange={(e) => setLimit(e.target.value.replace(/[^0-9.]/g, ""))}
                  placeholder="No limit"
                  className="w-full bg-transparent px-2 py-2 outline-none"
                />
              </div>
              <button onClick={saveLimit} className="rounded-lg border border-white/15 px-4 text-sm hover:bg-white/5">Save</button>
            </div>
          </div>
        </section>
      )}
      {!owner && (
        <p className="mt-6 rounded-lg border border-white/10 p-4 text-sm text-zinc-400">
          The workspace owner manages credits and limits. Below is your own usage.
        </p>
      )}
      {error && <p className="mt-3 text-sm text-red-400">{error}</p>}

      <section className="mt-10">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-medium">
            Usage {usage && <span className="text-zinc-500">· {usd(usage.total_usd)} across {usage.jobs} {usage.jobs === 1 ? "job" : "jobs"}</span>}
          </h2>
          <div className="flex gap-1 text-sm">
            {[7, 30, 90].map((d) => (
              <button
                key={d}
                onClick={() => setDays(d)}
                className={`rounded-full px-3 py-1 ${days === d ? "bg-white text-black" : "border border-white/15 text-zinc-300"}`}
              >
                {d} days
              </button>
            ))}
          </div>
        </div>
        {usage && (
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <div className="md:col-span-2">
              <Daily rows={usage.by_day} days={days} />
            </div>
            <Bars title="By model" rows={usage.by_model} />
            {!current.is_personal && (owner || can("manage_members")) ? <Bars title="By person" rows={usage.by_member} /> : null}
          </div>
        )}
      </section>

      <section className="mt-10">
        <h2 className="font-medium">Activity</h2>
        <div className="mt-3 overflow-x-auto rounded-xl border border-white/10">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wide text-zinc-500">
              <tr className="border-b border-white/10">
                <th className="px-4 py-2 font-normal">When</th>
                <th className="px-4 py-2 font-normal">What</th>
                <th className="px-4 py-2 text-right font-normal">Amount</th>
                <th className="px-4 py-2 text-right font-normal">Balance</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {entries.map((e) => (
                <tr key={e.id}>
                  <td className="whitespace-nowrap px-4 py-2 text-zinc-400">{new Date(e.created_at).toLocaleString()}</td>
                  <td className="px-4 py-2">
                    {e.description ?? kindLabel[e.kind]}
                  </td>
                  <td className={`whitespace-nowrap px-4 py-2 text-right tabular-nums ${e.amount_micros >= 0 ? "text-emerald-300" : ""}`}>
                    {e.amount_micros >= 0 ? "+" : "−"}
                    {usd(Math.abs(e.amount_micros) / 1e6)}
                  </td>
                  <td className="whitespace-nowrap px-4 py-2 text-right tabular-nums text-zinc-400">{usd(e.balance_after_micros / 1e6)}</td>
                </tr>
              ))}
              {entries.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-6 text-center text-zinc-500">No activity yet.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {cursor && (
          <button onClick={more} className="mt-4 rounded-lg border border-white/15 px-4 py-2 text-sm">Load more</button>
        )}
      </section>
    </div>
  );
}

export default function Page() {
  return (
    <Suspense>
      <BillingPage />
    </Suspense>
  );
}
