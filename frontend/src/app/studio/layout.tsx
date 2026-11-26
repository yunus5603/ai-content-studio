"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Logo } from "@/components/logo";
import { useApi } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { BillingProvider, useBilling } from "@/lib/billing";
import { usd } from "@/lib/format";
import { WorkspaceProvider, useWorkspace } from "@/lib/workspace";

const nav = [
  { href: "/studio", label: "Create" },
  { href: "/studio/gallery", label: "Gallery" },
  { href: "/studio/jobs", label: "Jobs" },
  { href: "/studio/team", label: "Team" },
  { href: "/studio/billing", label: "Billing" },
];

function BalanceChip() {
  const { billing } = useBilling();
  if (!billing) return null;
  const low = billing.balance_usd < 0.5;
  return (
    <Link
      href="/studio/billing"
      id="balance-chip"
      className={`flex items-center justify-between rounded-lg border px-3 py-2 text-sm ${low ? "border-amber-400/40 bg-amber-400/10" : "border-white/10 bg-white/5"} hover:border-white/30`}
    >
      <span className="text-zinc-400">Credits</span>
      <span className={`font-medium tabular-nums ${low ? "text-amber-300" : "text-white"}`}>{usd(billing.balance_usd)}</span>
    </Link>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  const { me, current, select, refresh, error } = useWorkspace();
  const { signOut } = useAuth();
  const api = useApi();
  const pathname = usePathname();
  const [creating, setCreating] = useState(false);

  async function newWorkspace() {
    const name = prompt("Name your team workspace");
    if (!name) return;
    setCreating(true);
    try {
      const ws = await api<{ id: string }>("/v1/workspaces", { method: "POST", body: JSON.stringify({ name }) });
      await refresh();
      select(ws.id);
    } finally {
      setCreating(false);
    }
  }

  if (error) {
    return (
      <div className="grid min-h-screen place-items-center px-4 text-center">
        <div>
          <p className="text-red-400">{error}</p>
          <button onClick={refresh} className="mt-4 rounded-lg border border-white/15 px-4 py-2">Try again</button>
        </div>
      </div>
    );
  }
  if (!me || !current) return <div className="grid min-h-screen place-items-center text-zinc-500">Loading…</div>;

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="flex flex-col gap-6 border-b border-white/10 p-4 md:w-60 md:border-b-0 md:border-r">
        <Logo />
        <div>
          <label className="mb-1 block text-xs uppercase tracking-wide text-zinc-500">Workspace</label>
          <select
            value={current.id}
            onChange={(e) => (e.target.value === "__new" ? newWorkspace() : select(e.target.value))}
            disabled={creating}
            className="w-full rounded-lg border border-white/10 bg-black/40 px-2 py-2 text-sm"
          >
            {me.workspaces.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name} ({w.role})
              </option>
            ))}
            <option value="__new">+ New team workspace</option>
          </select>
        </div>
        <BalanceChip />
        <nav className="flex gap-1 overflow-x-auto md:flex-col">
          {nav.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              className={`rounded-lg px-3 py-2 text-sm ${pathname === n.href ? "bg-white/10 text-white" : "text-zinc-400 hover:bg-white/5 hover:text-white"}`}
            >
              {n.label}
            </Link>
          ))}
          {me.user.is_platform_admin && (
            <Link
              href="/studio/admin"
              className={`rounded-lg px-3 py-2 text-sm ${pathname === "/studio/admin" ? "bg-white/10 text-white" : "text-zinc-400 hover:bg-white/5 hover:text-white"}`}
            >
              Admin
            </Link>
          )}
          {me.pending_invitations > 0 && (
            <Link href="/studio/invitations" className="rounded-lg px-3 py-2 text-sm text-violet-300 hover:bg-white/5">
              Invitations ({me.pending_invitations})
            </Link>
          )}
        </nav>
        <div className="mt-auto hidden text-sm md:block">
          <p className="truncate text-zinc-400">{me.user.email}</p>
          <button onClick={signOut} className="mt-1 text-zinc-500 hover:text-white">Sign out</button>
        </div>
      </aside>
      <main className="flex-1 p-4 md:p-8">{children}</main>
    </div>
  );
}

export default function StudioLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [user, loading, router]);

  if (loading || !user) return <div className="grid min-h-screen place-items-center text-zinc-500">Loading…</div>;
  return (
    <WorkspaceProvider key={user.email}>
      <BillingProvider>
        <Shell>{children}</Shell>
      </BillingProvider>
    </WorkspaceProvider>
  );
}
