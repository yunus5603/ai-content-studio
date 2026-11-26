"use client";

import { useCallback } from "react";
import { useAuth } from "./auth";
import { config } from "./config";

export type Role = "viewer" | "member" | "admin" | "owner";

export type User = {
  id: string;
  email: string;
  display_name: string | null;
  photo_url: string | null;
  is_platform_admin: boolean;
};

export type Workspace = {
  id: string;
  name: string;
  is_personal: boolean;
  owner_id: string;
  created_at: string;
  role: Role;
  permissions: string[];
};

export type Me = { user: User; workspaces: Workspace[]; pending_invitations: number };

export type Asset = {
  id: string;
  job_id: string | null;
  kind: "upload" | "output";
  media_type: "image" | "video";
  content_type: string;
  filename: string | null;
  size_bytes: number;
  created_at: string;
  url: string | null;
};

export type Job = {
  id: string;
  operation: string;
  provider: string;
  model: string;
  prompt: string | null;
  status: "queued" | "running" | "succeeded" | "failed" | "canceled";
  progress: number;
  error: string | null;
  created_at: string;
  outputs: Asset[];
};

export type Member = { user: User; role: Role; created_at: string };
export type Invitation = { id: string; workspace_id: string; email: string; role: Role; created_at: string };
export type MyInvitation = Invitation & { workspace_name: string };
export type Page<T> = { items: T[]; next_cursor: string | null };

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

/** Returns a fetch function that adds auth headers and parses JSON / errors. */
export function useApi() {
  const { authHeaders } = useAuth();
  return useCallback(
    async <T,>(path: string, init: RequestInit = {}): Promise<T> => {
      const headers = new Headers(init.headers);
      for (const [k, v] of Object.entries((await authHeaders()) ?? {})) headers.set(k, v);
      if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
      const res = await fetch(`${config.apiUrl}${path}`, { ...init, headers });
      if (!res.ok) {
        let message = res.statusText;
        try {
          const body = await res.json();
          message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
        } catch {}
        throw new ApiError(res.status, message);
      }
      return (res.status === 204 ? undefined : await res.json()) as T;
    },
    [authHeaders],
  );
}
