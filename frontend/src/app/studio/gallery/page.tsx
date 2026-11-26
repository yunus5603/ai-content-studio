"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AssetModal } from "@/components/asset-modal";
import { MediaTile } from "@/components/media";
import { type Asset, type Page, useApi } from "@/lib/api";
import { useCatalog } from "@/lib/catalog";
import { useWorkspace } from "@/lib/workspace";

const filters = [
  { label: "All", query: "" },
  { label: "Generated", query: "kind=output" },
  { label: "Uploads", query: "kind=upload" },
  { label: "Images", query: "media_type=image" },
  { label: "Videos", query: "media_type=video" },
];

export default function GalleryPage() {
  const api = useApi();
  const { current } = useWorkspace();
  const [filter, setFilter] = useState("");
  const [items, setItems] = useState<Asset[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState<Asset | null>(null);
  const { catalog } = useCatalog();
  const models = useMemo(() => Object.fromEntries((catalog?.models ?? []).map((m) => [m.id, m])), [catalog]);

  const load = useCallback(
    async (after: string | null) => {
      if (!current) return;
      setLoading(true);
      const params = new URLSearchParams(filter);
      if (after) params.set("cursor", after);
      const page = await api<Page<Asset>>(`/v1/workspaces/${current.id}/assets?${params}`);
      setItems((prev) => (after ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
      setLoading(false);
    },
    [api, current, filter],
  );

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reload when filter or workspace changes
    load(null);
  }, [load]);

  return (
    <div>
      <h1 className="text-2xl font-semibold">Gallery</h1>
      <div className="mt-4 flex flex-wrap gap-2">
        {filters.map((f) => (
          <button
            key={f.label}
            onClick={() => setFilter(f.query)}
            className={`rounded-full px-3 py-1 text-sm ${filter === f.query ? "bg-white text-black" : "border border-white/15 text-zinc-300"}`}
          >
            {f.label}
          </button>
        ))}
      </div>
      {!loading && items.length === 0 && <p className="mt-10 text-zinc-500">Nothing here yet.</p>}
      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {items.map((a) => (
          <MediaTile key={a.id} asset={a} onOpen={setOpen} />
        ))}
      </div>
      {open && (
        <AssetModal
          asset={open}
          models={models}
          onClose={() => setOpen(null)}
          onDeleted={(id) => {
            setItems((all) => all.filter((a) => a.id !== id));
            setOpen(null);
          }}
        />
      )}
      {cursor && (
        <button onClick={() => load(cursor)} className="mt-6 rounded-lg border border-white/15 px-4 py-2 text-sm">
          Load more
        </button>
      )}
    </div>
  );
}
