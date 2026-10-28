"use client";
import { useEffect, useRef, useState } from "react";
import { Eraser } from "lucide-react";

/** Draw-to-sign pad. Reports "signed" once there is enough ink to be a signature rather than a tap. */
export function SignaturePad({ onChange }: { onChange: (signed: boolean) => void }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const ink = useRef(0);
  const last = useRef<{ x: number; y: number } | null>(null);
  const [empty, setEmpty] = useState(true);

  useEffect(() => {
    const c = ref.current!;
    const r = c.getBoundingClientRect();
    c.width = r.width * devicePixelRatio; c.height = r.height * devicePixelRatio;
    const g = c.getContext("2d")!;
    g.scale(devicePixelRatio, devicePixelRatio);
    g.lineWidth = 2.2; g.lineCap = "round"; g.lineJoin = "round"; g.strokeStyle = "#13201d";
  }, []);

  const pos = (e: React.PointerEvent) => { const r = ref.current!.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };

  function move(e: React.PointerEvent) {
    if (!last.current) return;
    const p = pos(e), g = ref.current!.getContext("2d")!;
    g.beginPath(); g.moveTo(last.current.x, last.current.y); g.lineTo(p.x, p.y); g.stroke();
    ink.current += Math.hypot(p.x - last.current.x, p.y - last.current.y);
    last.current = p;
    if (ink.current > 150 && empty) { setEmpty(false); onChange(true); }
  }

  function clear() {
    const c = ref.current!;
    c.getContext("2d")!.clearRect(0, 0, c.width, c.height);
    ink.current = 0; setEmpty(true); onChange(false);
  }

  return (
    <div>
      <div className="relative">
        <canvas ref={ref} aria-label="Signature pad: draw your signature" className="h-44 w-full touch-none rounded-xl border border-line bg-surface"
          onPointerDown={(e) => { (e.target as HTMLCanvasElement).setPointerCapture(e.pointerId); last.current = pos(e); }}
          onPointerMove={move} onPointerUp={() => (last.current = null)} onPointerLeave={() => (last.current = null)} />
        <div className="pointer-events-none absolute inset-x-6 bottom-10 border-b border-line" />
        {empty && <div className="pointer-events-none absolute inset-0 grid place-items-center text-sm text-faint">Sign here with your mouse or finger</div>}
      </div>
      <button type="button" className="btn mt-3" onClick={clear}><Eraser className="size-4" />Clear</button>
    </div>
  );
}
