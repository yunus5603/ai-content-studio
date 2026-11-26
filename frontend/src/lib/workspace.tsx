"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { type Me, type Workspace, useApi } from "./api";

type WorkspaceState = {
  me: Me | null;
  current: Workspace | null;
  select: (id: string) => void;
  refresh: () => Promise<void>;
  can: (permission: string) => boolean;
  error: string | null;
};

const Ctx = createContext<WorkspaceState | null>(null);
const KEY = "studio.workspace";

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const api = useApi();
  const [me, setMe] = useState<Me | null>(null);
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await api<Me>("/v1/me");
      setMe(data);
      setError(null);
      setCurrentId((prev) => {
        let saved: string | null = prev;
        if (!saved) {
          try {
            saved = localStorage.getItem(KEY);
          } catch {}
        }
        return data.workspaces.some((w) => w.id === saved) ? saved : (data.workspaces[0]?.id ?? null);
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not reach the server");
    }
  }, [api]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial data load
    refresh();
  }, [refresh]);

  const select = useCallback((id: string) => {
    setCurrentId(id);
    try {
      localStorage.setItem(KEY, id);
    } catch {}
  }, []);

  const current = me?.workspaces.find((w) => w.id === currentId) ?? null;
  const can = useCallback((p: string) => !!current?.permissions.includes(p), [current]);

  return <Ctx.Provider value={{ me, current, select, refresh, can, error }}>{children}</Ctx.Provider>;
}

export function useWorkspace(): WorkspaceState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useWorkspace must be used inside WorkspaceProvider");
  return ctx;
}
