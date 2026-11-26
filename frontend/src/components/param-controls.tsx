"use client";

import { useState } from "react";
import type { ParamSpec, ParamValue } from "@/lib/api";
import { isActive } from "@/lib/catalog";

const field = "w-full rounded-lg border border-line bg-surface px-2.5 py-2 text-sm outline-none focus:border-brand";

function SizeControl({ spec, value, onChange }: { spec: ParamSpec; value: ParamValue; onChange: (v: ParamValue) => void }) {
  const preset = spec.options.some((o) => o.value === value);
  const [custom, setCustom] = useState(!preset);
  return (
    <div className="space-y-2">
      <select
        className={field}
        value={custom ? "__custom" : String(value)}
        onChange={(e) => {
          if (e.target.value === "__custom") {
            setCustom(true);
          } else {
            setCustom(false);
            onChange(e.target.value);
          }
        }}
      >
        {spec.options.map((o) => (
          <option key={String(o.value)} value={String(o.value)}>
            {o.label ?? String(o.value)}
          </option>
        ))}
        <option value="__custom">Custom…</option>
      </select>
      {custom && (
        <input className={field} placeholder="e.g. 1792x1024" defaultValue={preset ? "" : String(value)} onBlur={(e) => onChange(e.target.value.trim())} />
      )}
    </div>
  );
}

function Control({ spec, value, onChange }: { spec: ParamSpec; value: ParamValue | undefined; onChange: (v: ParamValue | undefined) => void }) {
  switch (spec.type) {
    case "enum":
      if (spec.options.length <= 3 && spec.options.every((o) => String(o.label ?? o.value).length < 14)) {
        return (
          <div className="flex gap-1 rounded-lg border border-line bg-surface p-1">
            {spec.options.map((o) => (
              <button
                type="button"
                key={String(o.value)}
                onClick={() => onChange(o.value)}
                className={`flex-1 rounded-md px-2 py-1 text-sm ${value === o.value ? "bg-ink text-white shadow-soft" : "text-ink-2 hover:bg-surface-2"}`}
              >
                {o.label ?? String(o.value)}
              </button>
            ))}
          </div>
        );
      }
      return (
        <select
          className={field}
          value={String(value ?? "")}
          onChange={(e) => onChange(spec.options.find((o) => String(o.value) === e.target.value)?.value)}
        >
          {spec.options.map((o) => (
            <option key={String(o.value)} value={String(o.value)}>
              {o.label ?? String(o.value)}
            </option>
          ))}
        </select>
      );
    case "bool":
      return (
        <button
          type="button"
          role="switch"
          aria-checked={!!value}
          onClick={() => onChange(!value)}
          className={`relative h-6 w-11 rounded-full transition ${value ? "bg-brand" : "bg-surface-3"}`}
        >
          <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition ${value ? "left-5" : "left-0.5"}`} />
        </button>
      );
    case "int":
    case "float":
      return (
        <input
          type="number"
          className={field}
          value={value === undefined ? "" : String(value)}
          min={spec.min ?? undefined}
          max={spec.max ?? undefined}
          step={spec.step ?? (spec.type === "int" ? 1 : "any")}
          onChange={(e) => onChange(e.target.value === "" ? undefined : Number(e.target.value))}
        />
      );
    case "size":
      return <SizeControl spec={spec} value={value ?? ""} onChange={onChange} />;
    default:
      return (
        <input
          className={field}
          value={value === undefined ? "" : String(value)}
          maxLength={spec.max ?? undefined}
          onChange={(e) => onChange(e.target.value || undefined)}
        />
      );
  }
}

export function ParamControls({
  specs,
  values,
  onChange,
}: {
  specs: ParamSpec[];
  values: Record<string, ParamValue>;
  onChange: (name: string, value: ParamValue | undefined) => void;
}) {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const visible = specs.filter((s) => isActive(s, values));
  const basic = visible.filter((s) => !s.advanced);
  const advanced = visible.filter((s) => s.advanced);

  const render = (s: ParamSpec) => (
    <label key={s.name} className="block">
      <span className="mb-1 flex items-center justify-between text-xs text-muted">
        {s.label}
      </span>
      <Control spec={s} value={values[s.name]} onChange={(v) => onChange(s.name, v)} />
      {s.help && <span className="mt-1 block text-xs text-subtle">{s.help}</span>}
    </label>
  );

  return (
    <div className="space-y-4">
      {basic.map(render)}
      {advanced.length > 0 && (
        <div>
          <button type="button" onClick={() => setShowAdvanced(!showAdvanced)} className="text-xs text-muted hover:text-ink">
            {showAdvanced ? "▾" : "▸"} Advanced ({advanced.length})
          </button>
          {showAdvanced && <div className="mt-3 space-y-4">{advanced.map(render)}</div>}
        </div>
      )}
    </div>
  );
}
