"use client";

import { useCallback, useEffect, useState } from "react";
import { type MyInvitation, useApi } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";

export default function InvitationsPage() {
  const api = useApi();
  const { refresh, select } = useWorkspace();
  const [invites, setInvites] = useState<MyInvitation[]>([]);

  const load = useCallback(async () => setInvites(await api<MyInvitation[]>("/v1/me/invitations")), [api]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial load
    load();
  }, [load]);

  async function respond(invite: MyInvitation, accept: boolean) {
    await api(`/v1/me/invitations/${invite.id}/${accept ? "accept" : "decline"}`, { method: "POST" });
    await refresh();
    if (accept) select(invite.workspace_id);
    await load();
  }

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-2xl font-semibold">Invitations</h1>
      {invites.length === 0 && <p className="mt-6 text-zinc-500">No pending invitations.</p>}
      <ul className="mt-6 space-y-3">
        {invites.map((i) => (
          <li key={i.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 p-4">
            <span>
              <span className="font-medium">{i.workspace_name}</span>
              <span className="text-zinc-400"> invited you as {i.role}</span>
            </span>
            <span className="flex gap-2">
              <button onClick={() => respond(i, true)} className="rounded-lg bg-white px-3 py-1.5 text-sm font-medium text-black">Accept</button>
              <button onClick={() => respond(i, false)} className="rounded-lg border border-white/15 px-3 py-1.5 text-sm">Decline</button>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
