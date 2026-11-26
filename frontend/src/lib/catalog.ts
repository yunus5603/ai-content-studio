"use client";

import { useEffect, useState } from "react";
import type { Catalog, ModelSpec, Operation, ParamSpec, ParamValue } from "./api";
import { config } from "./config";

let cached: Promise<Catalog> | null = null;

export function fetchCatalog(): Promise<Catalog> {
  if (!cached) {
    cached = fetch(`${config.apiUrl}/v1/catalog`).then((r) => {
      if (!r.ok) throw new Error("Could not load models");
      return r.json();
    });
    cached.catch(() => {
      cached = null;
    });
  }
  return cached;
}

export function useCatalog() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    fetchCatalog().then(setCatalog, (e: Error) => setError(e.message));
  }, []);
  return { catalog, error };
}

export const IMAGE_OPS: Operation[] = ["text_to_image", "image_edit", "inpaint"];
export const VIDEO_OPS: Operation[] = ["text_to_video", "image_to_video"];

export function modelsFor(catalog: Catalog, op: Operation): ModelSpec[] {
  return catalog.models.filter((m) => m.operations.some((o) => o.operation === op));
}

export function paramsFor(model: ModelSpec, op: Operation): ParamSpec[] {
  return model.params.filter((p) => p.operations.length === 0 || p.operations.includes(op));
}

export function defaultsFor(model: ModelSpec, op: Operation): Record<string, ParamValue> {
  const out: Record<string, ParamValue> = {};
  for (const p of paramsFor(model, op)) if (p.default != null) out[p.name] = p.default;
  return out;
}

/** Whether a param should show, given the current values (its `when` conditions). */
export function isActive(p: ParamSpec, values: Record<string, ParamValue>): boolean {
  return Object.entries(p.when).every(([k, allowed]) => allowed.includes(values[k]));
}

/** Params to send: only active ones, so hidden conditional params aren't rejected. */
export function activeValues(model: ModelSpec, op: Operation, values: Record<string, ParamValue>) {
  const out: Record<string, ParamValue> = {};
  for (const p of paramsFor(model, op)) {
    const v = values[p.name];
    if (v !== undefined && v !== "" && isActive(p, values)) out[p.name] = v;
  }
  return out;
}
