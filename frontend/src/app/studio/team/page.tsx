"use client";

import { useCallback, useEffect, useState } from "react";
import { type Invitation, type Member, type Role, useApi } from "@/lib/api";
import { usd } from "@/lib/format";
import { useWorkspace } from "@/lib/workspace";

const assignable: Role[] = ["viewer", "member", "admin"];
const roleHelp: Record<Role, string> = {
  viewer: "Can browse the gallery and jobs",
  member: "Can also upload and generate",
  admin: "Can also manage people",
  owner: "Full control, including billing",
};

export default function TeamPage() {
  const api = useApi();
  const { me, current, can, refresh } = useWorkspace();
  const [members, setMembers] = useState<Member[]>([]);
  const [invites, setInvites] = useState<Invitation[]>([]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("member");
  const [error, setError] = useState<string | null>(null);
  const manage = can("manage_members");

  const load = useCallback(async () => {
    if (!current) return;
    setMembers(await api<Member[]>(`/v1/workspaces/${current.id}/members`));
    setInvites(manage ? await api<Invitation[]>(`/v1/workspaces/${current.id}/invitations`) : []);
  }, [api, current, manage]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial load
    load();
  }, [load]);

  async function act(fn: () => Promise<unknown>) {
    setError(null);
    try {
      await fn();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    }
  }

  if (!current || !me) return null;
  const base = `/v1/workspaces/${current.id}`;

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-2xl font-semibold">Team</h1>
      <p className="mt-1 text-sm text-zinc-400">
        {current.name} · your role: {current.role}
      </p>

      {current.is_personal ? (
        <p className="mt-6 rounded-lg border border-white/10 p-4 text-sm text-zinc-400">
          This is your personal workspace. Create a team workspace from the workspace menu to invite people.
        </p>
      ) : (
        manage && (
          <form
            className="mt-6 flex flex-wrap gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              act(() => api(`${base}/invitations`, { method: "POST", body: JSON.stringify({ email, role }) })).then(() => setEmail(""));
            }}
          >
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="teammate@company.com"
              className="min-w-0 flex-1 rounded-lg border border-white/10 bg-black/30 px-3 py-2"
            />
            <select value={role} onChange={(e) => setRole(e.target.value as Role)} className="rounded-lg border border-white/10 bg-black/40 px-2">
              {assignable.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
            <button className="rounded-lg bg-white px-4 py-2 font-medium text-black">Invite</button>
          </form>
        )
      )}
      {error && <p className="mt-3 text-sm text-red-400">{error}</p>}

      <h2 className="mt-8 text-sm uppercase tracking-wide text-zinc-500">Members</h2>
      <ul className="mt-2 divide-y divide-white/10 rounded-xl border border-white/10">
        {members.map((m) => {
          const isMe = m.user.id === me.user.id;
          return (
            <li key={m.user.id} className="flex flex-wrap items-center justify-between gap-2 p-3">
              <div>
                <p className="text-sm">{m.user.display_name ?? m.user.email} {isMe && <span className="text-zinc-500">(you)</span>}</p>
                <p className="text-xs text-zinc-500">{m.user.email}</p>
              </div>
              <div className="flex items-center gap-3">
                {!current.is_personal &&
                  (manage ? (
                    <button
                      title="Monthly spending limit for this person"
                      onClick={() => {
                        const cur = m.monthly_limit_micros != null ? String(m.monthly_limit_micros / 1e6) : "";
                        const v = prompt(`Monthly spending limit for ${m.user.email} in USD (empty for none)`, cur);
                        if (v === null) return;
                        act(() =>
                          api(`${base}/members/${m.user.id}/limit`, {
                            method: "PUT",
                            body: JSON.stringify({ monthly_limit_usd: v.trim() === "" ? null : Number(v) }),
                          }),
                        );
                      }}
                      className="rounded-md border border-white/10 px-2 py-1 text-xs text-zinc-400 hover:text-white"
                    >
                      {m.monthly_limit_micros != null ? `${usd(m.monthly_limit_micros / 1e6)}/mo` : "No limit"}
                    </button>
                  ) : (
                    m.monthly_limit_micros != null && (
                      <span className="text-xs text-zinc-500">{usd(m.monthly_limit_micros / 1e6)}/mo</span>
                    )
                  ))}
                {manage && m.role !== "owner" ? (
                  <select
                    value={m.role}
                    title={roleHelp[m.role]}
                    onChange={(e) => act(() => api(`${base}/members/${m.user.id}`, { method: "PATCH", body: JSON.stringify({ role: e.target.value }) }))}
                    className="rounded-md border border-white/10 bg-black/40 px-2 py-1 text-sm"
                  >
                    {assignable.map((r) => (
                      <option key={r} value={r}>{r}</option>
                    ))}
                  </select>
                ) : (
                  <span className="text-sm text-zinc-400" title={roleHelp[m.role]}>{m.role}</span>
                )}
                {m.role !== "owner" && (manage || isMe) && (
                  <button
                    onClick={() => act(async () => {
                      await api(`${base}/members/${m.user.id}`, { method: "DELETE" });
                      if (isMe) await refresh();
                    })}
                    className="text-sm text-zinc-500 hover:text-red-400"
                  >
                    {isMe ? "Leave" : "Remove"}
                  </button>
                )}
              </div>
            </li>
          );
        })}
      </ul>

      {invites.length > 0 && (
        <>
          <h2 className="mt-8 text-sm uppercase tracking-wide text-zinc-500">Pending invitations</h2>
          <ul className="mt-2 divide-y divide-white/10 rounded-xl border border-white/10">
            {invites.map((i) => (
              <li key={i.id} className="flex items-center justify-between p-3 text-sm">
                <span>{i.email} <span className="text-zinc-500">as {i.role}</span></span>
                <button onClick={() => act(() => api(`${base}/invitations/${i.id}`, { method: "DELETE" }))} className="text-zinc-500 hover:text-red-400">
                  Revoke
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
