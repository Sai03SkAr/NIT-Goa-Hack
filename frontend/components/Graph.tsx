"use client";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState } from "react";
import { TYPE_COLORS, bandColor } from "@/components/ui";

const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), { ssr: false });

export type GNode = { id: string; name?: string; band?: string | null; fraud_type?: string | null; source?: string | null; community?: number | null; x?: number; y?: number };
export type GLink = { source: string; target: string; w: number; kinds: string[] };

const KIND_COLOR: Record<string, string> = {
  face: "#fb7185", device: "#fbbf24", phone: "#38bdf8", email_stem: "#c084fc", keystroke: "#5eead4", address: "#94a3b8", id_hash: "#f472b6", ip: "#475569",
};

export function IdentityGraph({ nodes, links, focus, height = 420, colorBy = "band", highlight }: {
  nodes: GNode[]; links: GLink[]; focus?: string; height?: number; colorBy?: "band" | "type"; highlight?: Set<string>;
}) {
  const wrap = useRef<HTMLDivElement>(null);
  const fg = useRef<any>(null);
  const [w, setW] = useState(0);
  useEffect(() => {
    const measure = () => wrap.current && setW(wrap.current.clientWidth);
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);
  // positions come from the backend (per-component spring layout); pin them so clusters stay readable
  const data = useMemo(() => ({ nodes: nodes.map((n) => ({ ...n, fx: n.x, fy: n.y })), links: links.map((l) => ({ ...l })) }), [nodes, links]);
  useEffect(() => {
    // pinned nodes never fire onEngineStop; fit once the dynamically imported graph has mounted
    let tries = 0;
    const t = setInterval(() => {
      if (fg.current) { fg.current.zoomToFit(400, 30); clearInterval(t); } else if (++tries > 40) clearInterval(t);
    }, 150);
    return () => clearInterval(t);
  }, [w, data]);
  return (
    <div ref={wrap} style={{ height }} className="relative overflow-hidden rounded-xl border border-line bg-bg-2/60">
      {w > 0 && <ForceGraph2D
        ref={fg} onEngineStop={() => fg.current?.zoomToFit(400, 40)}
        graphData={data} width={w} height={height} backgroundColor="rgba(0,0,0,0)" cooldownTicks={20}
        linkColor={(l: any) => KIND_COLOR[[...l.kinds].sort((a: string, b: string) => kindRank(a) - kindRank(b))[0]] ?? "#334155"}
        linkWidth={(l: any) => 0.6 + 2.2 * l.w}
        nodeCanvasObject={(n: any, ctx, scale) => {
          const c = colorBy === "type" ? (TYPE_COLORS[n.fraud_type ?? "none"] ?? "#64748b") : (bandColor[n.band] ?? "#64748b");
          const r = n.id === focus ? 7 : 4.5;
          if (highlight?.has(n.id) || n.id === focus) {
            ctx.beginPath(); ctx.arc(n.x, n.y, r + 4, 0, 2 * Math.PI); ctx.fillStyle = `${c}33`; ctx.fill();
          }
          ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, 2 * Math.PI); ctx.fillStyle = c; ctx.fill();
          ctx.lineWidth = 1 / scale; ctx.strokeStyle = "#0b1120"; ctx.stroke();
          if (scale > 1.6 || n.id === focus) {
            ctx.font = `${10 / scale}px ui-sans-serif`; ctx.fillStyle = "#cbd5e1"; ctx.textAlign = "center";
            ctx.fillText(n.name ?? n.id, n.x, n.y + r + 9 / scale);
          }
        }}
        nodeLabel={(n: any) => `${n.id} · ${n.name ?? ""} · ${n.band ?? ""} · ${n.fraud_type ?? ""}`}
        onNodeClick={(n: any) => window.open(`/dashboard/case/${n.id}`, "_self")}
      />}
      <div className="pointer-events-none absolute bottom-2 left-2 flex flex-wrap gap-1.5">
        {Object.entries(KIND_COLOR).map(([k, c]) => (
          <span key={k} className="chip bg-bg/70 text-[10px]"><span className="size-1.5 rounded-full" style={{ background: c }} />{k.replace("_", " ")}</span>
        ))}
      </div>
    </div>
  );
}

const ORDER = ["face", "id_hash", "device", "keystroke", "email_stem", "phone", "address", "ip"];
const kindRank = (k: string) => (ORDER.indexOf(k) === -1 ? 99 : ORDER.indexOf(k));
