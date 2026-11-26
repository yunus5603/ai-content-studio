"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { IconActivity, IconCard, IconGrid, IconLogout, IconMail, IconShield, IconSparkles, IconUsers, IconWand } from "@/components/icons";
import { Logo } from "@/components/logo";
import { useApi } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { BillingProvider, useBilling } from "@/lib/billing";
import { usd } from "@/lib/format";
import { WorkspaceProvider, useWorkspace } from "@/lib/workspace";

const nav = [
  { href: "/studio", label: "Create", icon: IconSparkles },
  { href: "/studio/copilot", label: "Copilot", icon: IconWand },
  { href: "/studio/gallery", label: "Gallery", icon: IconGrid },
  { href: "/studio/jobs", label: "Jobs", icon: IconActivity },
  { href: "/studio/team", label: "Team", icon: IconUsers },
  { href: "/studio/billing", label: "Billing", icon: IconCard },
];

function NavLink({ href, label, icon: Icon, active, className = "" }: { href: string; label: string; icon: typeof IconGrid; active: boolean; className?: string }) {
  return (
    <Link
      href={href}
      className={`group relative flex shrink-0 items-center gap-2.5 rounded-xl px-3 py-2 text-sm transition-colors duration-200 ${
        active ? "bg-surface text-ink shadow-soft ring-1 ring-line" : "text-muted hover:bg-surface-2 hover:text-ink"
      } ${className}`}
    >
      <Icon className={`h-[18px] w-[18px] transition-colors ${active ? "text-brand" : "text-subtle group-hover:text-ink-2"}`} />
      {label}
    </Link>
  );
}

function BalanceChip() {
  const { billing } = useBilling();
  if (!billing) return null;
  const low = billing.balance_usd < 0.5;
  return (
    <Link
      href="/studio/billing"
      id="balance-chip"
      className={`group flex items-center justify-between rounded-xl border px-3 py-2.5 text-sm shadow-soft transition hover:shadow-card ${low ? "border-warning/30 bg-warning/10" : "border-line bg-surface"}`}
    >
      <span className="flex items-center gap-2 text-muted">
        <span className={`h-2 w-2 rounded-full ${low ? "bg-warning" : "bg-success"}`} />
        Credits
      </span>
      <span className={`font-semibold tabular-nums ${low ? "text-warning" : "text-ink"}`}>{usd(billing.balance_usd)}</span>
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
          <p className="text-danger">{error}</p>
          <button onClick={refresh} className="btn btn-secondary mt-4">Try again</button>
        </div>
      </div>
    );
  }
  if (!me || !current) return <Loading />;

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="z-30 flex flex-col gap-5 border-b border-line bg-canvas/90 p-4 backdrop-blur md:sticky md:top-0 md:h-screen md:w-64 md:shrink-0 md:border-b-0 md:border-r">
        <div className="px-1 pt-1">
          <Logo />
        </div>
        <div>
          <label htmlFor="workspace-select" className="label px-1">Workspace</label>
          <select
            id="workspace-select"
            value={current.id}
            onChange={(e) => (e.target.value === "__new" ? newWorkspace() : select(e.target.value))}
            disabled={creating}
            className="input cursor-pointer"
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
        <nav className="-mx-1 flex gap-1 overflow-x-auto px-1 pb-1 md:mx-0 md:flex-col md:overflow-visible md:px-0">
          {nav.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              className={`rounded-lg px-3 py-2 text-sm ${pathname === n.href || (n.href !== "/studio" && pathname.startsWith(n.href)) ? "bg-white/10 text-white" : "text-zinc-400 hover:bg-white/5 hover:text-white"}`}
            >
              {n.label}
            </Link>
          ))}
          {me.user.is_platform_admin && (
            <NavLink href="/studio/admin" label="Admin" icon={IconShield} active={pathname === "/studio/admin"} />
          )}
          {me.pending_invitations > 0 && (
            <NavLink
              href="/studio/invitations"
              label={`Invitations (${me.pending_invitations})`}
              icon={IconMail}
              active={pathname === "/studio/invitations"}
              className="text-brand"
            />
          )}
        </nav>
        <div className="mt-auto hidden items-center gap-3 rounded-xl border border-line bg-surface p-2.5 text-sm shadow-soft md:flex">
          <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-gradient-to-br from-brand to-[#f0508c] text-xs font-semibold uppercase text-white">
            {me.user.email.slice(0, 1)}
          </span>
          <p className="min-w-0 flex-1 truncate text-ink-2">{me.user.email}</p>
          <button onClick={signOut} className="rounded-lg p-1.5 text-subtle transition hover:bg-surface-2 hover:text-ink" aria-label="Sign out" title="Sign out">
            <IconLogout className="h-4 w-4" />
          </button>
        </div>
      </aside>
      <main className="min-w-0 flex-1 p-4 md:p-8 lg:p-10">
        <div key={pathname} className="animate-page">
          {children}
        </div>
      </main>
    </div>
  );
}

function Loading() {
  return (
    <div className="grid min-h-screen place-items-center">
      <div className="flex flex-col items-center gap-4 text-sm text-subtle">
        <span className="h-9 w-9 animate-spin rounded-full border-2 border-line-strong border-t-brand" />
        Loading your studio…
      </div>
    </div>
  );
}

export default function StudioLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [user, loading, router]);

  if (loading || !user) return <Loading />;
  return (
    <WorkspaceProvider key={user.email}>
      <BillingProvider>
        <Shell>{children}</Shell>
      </BillingProvider>
    </WorkspaceProvider>
  );
}
