"use client";
import { useEffect, useState } from "react";
import clsx from "clsx";
import { Radar, Zap } from "lucide-react";
import { IdentityGraph, type GLink, type GNode } from "@/components/Graph";
import { Stat } from "@/components/ui";
import { ApiError, get, post } from "@/lib/api";

export default function GraphPage() {
  const [g, setG] = useState<{ nodes: GNode[]; links: GLink[]; communities: number } | null>(null);
  const [colorBy, setColorBy] = useState<"band" | "type">("type");
  const [sim, setSim] = useState<{ busy: boolean; ids: string[]; err?: string }>({ busy: false, ids: [] });
  const [minSize, setMinSize] = useState(3);
  const load = () => get(`/api/graph?min_size=${minSize}`).then(setG).catch(() => setG({ nodes: [], links: [], communities: 0 }));
  useEffect(() => { load(); }, [minSize]); // eslint-disable-line react-hooks/exhaustive-deps

  async function ringSim() {
    setSim({ busy: true, ids: [] });
    try {
      const r = await post<{ app_ids: string[] }>("/api/ring-sim");
      setSim({ busy: false, ids: r.app_ids });
      load();
    } catch (e) {
      setSim({ busy: false, ids: [], err: e instanceof ApiError && e.status === 404 ? "The ring simulator is a demo tool and is turned off on this server." : `The ring simulator failed: ${e instanceof Error ? e.message : e}` });
    }
  }
  const comps = g ? new Set(g.nodes.map((n) => n.community)).size : 0;
  const flagged = g ? g.nodes.filter((n) => n.band !== "APPROVE").length : 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="display text-[32px] leading-[1.1]">Identity graph</h1>
          <p className="mt-1 max-w-3xl text-sm text-muted">Applications joined by specificity-weighted links. Rare shared values (a face, a device) are strong; common ones (a CGNAT IP) are weak. Louvain communities separate rings from families.</p>
        </div>
        <button className={clsx("btn btn-primary px-5 py-2.5", sim.busy && "pulse")} disabled={sim.busy} onClick={ringSim}>
          <Zap className="size-4" />{sim.busy ? "Injecting 8 applicants through the pipeline…" : "Fraud Ring Simulator"}
        </button>
      </div>
      <div className="grid gap-4 sm:grid-cols-4">
        <Stat label="Linked applications" value={g?.nodes.length ?? "-"} />
        <Stat label="Strong links" value={g?.links.length ?? "-"} />
        <Stat label="Communities" value={comps || "-"} />
        <Stat label="Flagged in clusters" value={flagged} accent="var(--reject)" />
      </div>
      <div className="panel p-4">
        <div className="mb-3 flex flex-wrap items-center gap-3 text-sm">
          <span className="label">Color by</span>
          {(["type", "band"] as const).map((k) => (
            <button key={k} className={clsx("rounded-md px-3 py-1 text-sm", colorBy === k ? "bg-bg-2 font-medium text-fg" : "text-muted hover:text-fg")} onClick={() => setColorBy(k)}>{k === "type" ? "Fraud pattern" : "Decision"}</button>
          ))}
          <span className="label ml-4">Min cluster size</span>
          <input type="range" min={2} max={8} value={minSize} onChange={(e) => setMinSize(+e.target.value)} />
          <span className="mono text-xs">{minSize}</span>
          {sim.err && <span className="ml-auto text-sm text-reject">{sim.err}</span>}
          {!!sim.ids.length && <span className="chip ml-auto text-brand"><Radar className="size-3" />{sim.ids.length} ring applicants added, ringed in the graph</span>}
        </div>
        {g ? <IdentityGraph nodes={g.nodes} links={g.links} height={640} colorBy={colorBy} highlight={new Set(sim.ids)} /> :
          <div className="grid h-[640px] place-items-center text-muted">Loading graph…</div>}
      </div>
    </div>
  );
}
