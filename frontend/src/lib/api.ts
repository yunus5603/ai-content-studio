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
  created_by_id: string;
  job_id: string | null;
  width: number | null;
  height: number | null;
  duration_seconds: number | null;
  kind: "upload" | "output";
  media_type: "image" | "video";
  content_type: string;
  filename: string | null;
  size_bytes: number;
  created_at: string;
  url: string | null;
};

export type Operation = "text_to_image" | "image_edit" | "inpaint" | "text_to_video" | "image_to_video";
export type InputRole = "image" | "mask" | "first_frame" | "last_frame";
export type JobInput = { asset_id: string; role: InputRole };

export type Job = {
  id: string;
  operation: Operation;
  provider: string;
  model: string;
  prompt: string | null;
  params: Record<string, unknown>;
  inputs: JobInput[];
  status: "queued" | "running" | "succeeded" | "failed" | "canceled";
  progress: number;
  error: string | null;
  created_at: string;
  finished_at: string | null;
  estimated_cost_usd: number;
  estimated_price_usd: number;
  cost_usd: number | null;
  price_usd: number | null;
  hold_micros: number;
  charged_micros: number | null;
  outputs: Asset[];
};

export type ParamValue = string | number | boolean;

export type ParamSpec = {
  name: string;
  label: string;
  type: "enum" | "int" | "float" | "bool" | "text" | "size";
  default: ParamValue | null;
  options: { value: ParamValue; label: string | null }[];
  min: number | null;
  max: number | null;
  step: number | null;
  help: string | null;
  advanced: boolean;
  operations: string[];
  when: Record<string, ParamValue[]>;
};

export type InputSpec = { role: InputRole; label: string; media_type: "image" | "video"; min: number; max: number };

export type ModelSpec = {
  id: string;
  provider: "openai" | "vertex" | "debug";
  model: string;
  name: string;
  family: string;
  media_type: "image" | "video";
  description: string;
  status: "ga" | "preview" | "deprecated";
  shutdown_date: string | null;
  tags: string[];
  operations: { operation: Operation; inputs: InputSpec[] }[];
  params: ParamSpec[];
  pricing: { unit: "image" | "second"; verified: boolean };
};

export type Catalog = { platform_fee: number; operations: Record<Operation, string>; models: ModelSpec[] };
export type Estimate = { params: Record<string, ParamValue>; provider_cost_usd: number; price_usd: number };
export type Share = {
  id: string;
  token: string;
  asset_id: string;
  created_at: string;
  expires_at: string | null;
  include_prompt: boolean;
};

export type Member = { user: User; role: Role; created_at: string; monthly_limit_micros: number | null };

export type BillingSummary = {
  balance_usd: number;
  spent_this_month_usd: number;
  my_spent_this_month_usd: number;
  monthly_limit_usd: number | null;
  my_monthly_limit_usd: number | null;
  credit_packs_usd: number[];
  payments_enabled: boolean;
  dev_topup_enabled: boolean;
  platform_fee: number;
};
export type CreditEntry = {
  id: string;
  kind: "signup_grant" | "purchase" | "job_hold" | "job_settle" | "adjustment";
  amount_micros: number;
  balance_after_micros: number;
  job_id: string | null;
  user_id: string | null;
  description: string | null;
  created_at: string;
};
export type UsageRow = { key: string; label: string; jobs: number; spent_usd: number };
export type UsageReport = {
  days: number;
  total_usd: number;
  jobs: number;
  by_day: UsageRow[];
  by_model: UsageRow[];
  by_member: UsageRow[];
};
export type AdminOverview = {
  days: number;
  revenue_usd: number;
  customer_spend_usd: number;
  provider_cost_usd: number;
  margin_usd: number;
  outstanding_credit_usd: number;
  free_credit_granted_usd: number;
  jobs: number;
  failed_jobs: number;
  users: number;
  new_users: number;
  workspaces: number;
  by_model: UsageRow[];
  by_day: UsageRow[];
};
export type AdminWorkspaceRow = {
  id: string;
  name: string;
  owner_email: string;
  balance_usd: number;
  purchased_usd: number;
  spent_usd: number;
  jobs: number;
  created_at: string;
};
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
