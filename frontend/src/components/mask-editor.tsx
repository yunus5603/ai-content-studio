"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Paint over the part of an image you want regenerated.
 * Exports a PNG the size of the image: painted areas transparent, the rest opaque
 * (the format OpenAI's edit endpoint expects).
 */
export function MaskEditor({
  imageUrl,
  onDone,
  onClose,
}: {
  imageUrl: string;
  onDone: (mask: Blob) => void;
  onClose: () => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  const [brush, setBrush] = useState(48);
  const drawing = useRef(false);
  const last = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => {
    const img = new Image();
    img.onload = () => setSize({ w: img.naturalWidth, h: img.naturalHeight });
    img.src = imageUrl;
  }, [imageUrl]);

  function point(e: React.PointerEvent<HTMLCanvasElement>) {
    const canvas = canvasRef.current!;
    const rect = canvas.getBoundingClientRect();
    return { x: ((e.clientX - rect.left) / rect.width) * canvas.width, y: ((e.clientY - rect.top) / rect.height) * canvas.height };
  }

  function stroke(to: { x: number; y: number }) {
    const ctx = canvasRef.current!.getContext("2d")!;
    const scale = canvasRef.current!.width / canvasRef.current!.getBoundingClientRect().width;
    ctx.strokeStyle = "rgba(167, 139, 250, 0.6)";
    ctx.fillStyle = "rgba(167, 139, 250, 0.6)";
    ctx.lineWidth = brush * scale;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.globalCompositeOperation = "source-over";
    const from = last.current ?? to;
    ctx.beginPath();
    ctx.moveTo(from.x, from.y);
    ctx.lineTo(to.x, to.y);
    ctx.stroke();
    last.current = to;
  }

  function clear() {
    const c = canvasRef.current!;
    c.getContext("2d")!.clearRect(0, 0, c.width, c.height);
  }

  function exportMask() {
    const src = canvasRef.current!;
    const out = document.createElement("canvas");
    out.width = src.width;
    out.height = src.height;
    const ctx = out.getContext("2d")!;
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, out.width, out.height);
    // Punch out wherever the user painted.
    ctx.globalCompositeOperation = "destination-out";
    ctx.drawImage(src, 0, 0);
    out.toBlob((blob) => blob && onDone(blob), "image/png");
  }

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-ink/30 backdrop-blur-sm animate-fade-in p-4">
      <div className="mb-3 flex flex-wrap items-center gap-4 text-sm">
        <span className="font-medium">Paint the area to change</span>
        <label className="flex items-center gap-2 text-muted">
          Brush
          <input type="range" min={8} max={160} value={brush} onChange={(e) => setBrush(Number(e.target.value))} />
        </label>
        <button onClick={clear} className="text-muted hover:text-ink">Clear</button>
        <span className="ml-auto flex gap-2">
          <button onClick={onClose} className="rounded-lg border border-line-strong px-3 py-1.5">Cancel</button>
          <button onClick={exportMask} className="btn btn-primary">Use mask</button>
        </span>
      </div>
      <div className="relative mx-auto flex min-h-0 flex-1 items-center justify-center">
        {size ? (
          <div className="relative max-h-full" style={{ aspectRatio: `${size.w} / ${size.h}`, height: "100%" }}>
            {/* eslint-disable-next-line @next/next/no-img-element -- signed storage URL */}
            <img src={imageUrl} alt="" className="absolute inset-0 h-full w-full select-none object-contain" draggable={false} />
            <canvas
              ref={canvasRef}
              width={size.w}
              height={size.h}
              className="absolute inset-0 h-full w-full cursor-crosshair touch-none"
              onPointerDown={(e) => {
                drawing.current = true;
                last.current = null;
                e.currentTarget.setPointerCapture(e.pointerId);
                stroke(point(e));
              }}
              onPointerMove={(e) => drawing.current && stroke(point(e))}
              onPointerUp={() => {
                drawing.current = false;
                last.current = null;
              }}
            />
          </div>
        ) : (
          <p className="text-subtle">Loading image…</p>
        )}
      </div>
    </div>
  );
}
