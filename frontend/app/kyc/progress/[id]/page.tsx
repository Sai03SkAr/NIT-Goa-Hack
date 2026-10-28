"use client";
import { use, useEffect, useState } from "react";
import Link from "next/link";
import clsx from "clsx";
import { ArrowRight, Bot, Brain, CheckCircle2, CircleDashed, FileSearch, Fingerprint, GitMerge, Network, Scale, ScanFace, ShieldQuestion, Sparkles, Database } from "lucide-react";
import { BandBadge, Logo, RiskBar, SimBadge, riskColor } from "@/components/ui";
import { API } from "@/lib/api";

type Ev = { node: string; module?: string; risk?: number; reasons?: string[]; latency_ms?: number; prob?: number; band?: string;
  forced?: string | null; fraud_label?: string; fraud_action?: string; step_up?: { voice: number; simulated: boolean }; summary?: string; error?: string };

const NODES: { id: string; label: string; icon: any; sub: string }[] = [
  { id: "ingest", label: "Ingest", icon: Database, sub: "consent · uploads · telemetry" },
  { id: "document", label: "Document agent", icon: FileSearch, sub: "signed QR · OCR · checksums · forensics" },
  { id: "biometric", label: "Biometric agent", icon: ScanFace, sub: "face match · reuse · liveness · virtual cam" },
  { id: "behavior", label: "Behavior agent", icon: Bot, sub: "typing · paste · velocity · rhythm links" },
  { id: "registry", label: "Registry agent", icon: Fingerprint, sub: "UIDAI · PAN · telecom · CKYC · bureau" },
  { id: "correlation", label: "Correlation agent", icon: Network, sub: "identity graph · rings · families" },
  { id: "fusion", label: "Fusion", icon: GitMerge, sub: "hard rules → calibrated XGBoost → SHAP" },
  { id: "step_up", label: "Step-up", icon: ShieldQuestion, sub: "voice check (simulated)" },
  { id: "decide", label: "Decide", icon: Scale, sub: "band · fraud type · action" },
  { id: "explain", label: "Explain", icon: Brain, sub: "LLM summary from reason codes only" },
  { id: "persist", label: "Persist", icon: CheckCircle2, sub: "SQLite + audit log" },
];

export default function Progress({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [evs, setEvs] = useState<Record<string, Ev>>({});
  const [order, setOrder] = useState<string[]>([]);
  const [done, setDone] = useState(false);
  const [t0] = useState(() => performance.now());
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const es = new EventSource(`${API}/api/apply/${id}/events`);
    es.addEventListener("node", (m) => {
      const ev: Ev = JSON.parse((m as MessageEvent).data);
      setEvs((p) => ({ ...p, [ev.node]: { ...p[ev.node], ...ev } }));
      setOrder((o) => [...o, ev.node]);
    });
    es.addEventListener("done", () => { setDone(true); es.close(); });
    es.onerror = () => es.close();
    return () => es.close();
  }, [id]);
  useEffect(() => {
    if (done) return;
    const t = setInterval(() => setElapsed((performance.now() - t0) / 1000), 100);
    return () => clearInterval(t);
  }, [done, t0]);

  const decision = evs.decide ?? evs.fusion;
  const stepped = !!evs.step_up;
  const parallel = ["document", "biometric", "behavior", "registry"];
  const running = (n: string) => !evs[n] && !done && (
    n === "ingest" ? true : parallel.includes(n) ? !!evs.ingest : n === "correlation" ? parallel.every((p) => evs[p]) :
    n === "fusion" ? !!evs.correlation : n === "decide" ? !!evs.fusion && !(evs.fusion.band === "REVIEW" && !stepped && !evs.fusion.forced) :
    n === "explain" ? !!evs.decide : n === "persist" ? !!evs.explain : false);

  return (
    <div className="grid-bg min-h-screen">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
        <Logo /><span className="chip mono">{id} · {done ? "complete" : `${elapsed.toFixed(1)}s`}</span>
      </header>
      <main className="mx-auto grid max-w-6xl gap-6 px-6 pb-20 lg:grid-cols-[1.25fr_1fr]">
        <section className="panel p-6">
          <div className="label mb-4">LangGraph pipeline · live</div>
          <Node n={NODES[0]} ev={evs.ingest} running={running("ingest")} />
          <Connector />
          <div className="grid gap-3 sm:grid-cols-2">
            {NODES.slice(1, 5).map((n) => <Node key={n.id} n={n} ev={evs[n.id]} running={running(n.id)} compact />)}
          </div>
          <Connector />
          {NODES.slice(5).map((n, i) => {
            if (n.id === "step_up" && !stepped) return <div key={n.id} className="ml-6 border-l border-dashed border-line-2 py-1 pl-4 text-xs text-dim">step-up only if fusion lands in REVIEW</div>;
            return <div key={n.id}>{i > 0 && <Connector />}<Node n={n} ev={evs[n.id]} running={running(n.id)} /></div>;
          })}
        </section>

        <aside className="space-y-6">
          <section className={clsx("panel p-6 transition", done && "fade-up")}>
            <div className="label">Decision</div>
            {decision?.band ? (
              <>
                <div className="mt-3 flex items-center gap-4">
                  <BandBadge band={decision.band} size="lg" />
                  <div className="text-sm text-muted">fraud probability <span className="mono text-fg">{decision.prob?.toFixed(3)}</span></div>
                </div>
                <RiskBar value={decision.prob ?? 0} className="mt-4" />
                {decision.forced && <div className="mt-3 text-xs text-muted">Forced by hard rule (deterministic, auditable)</div>}
                {evs.decide?.fraud_label && evs.decide.band !== "APPROVE" && (
                  <div className="mt-5 rounded-xl border border-line-2 bg-bg-2/60 p-4">
                    <div className="label">Pattern</div><div className="mt-1 font-semibold">{evs.decide.fraud_label}</div>
                    <div className="label mt-3">Recommended action</div><div className="mt-1 text-sm">{evs.decide.fraud_action}</div>
                  </div>
                )}
                {stepped && <div className="mt-4 flex items-center gap-2 text-sm text-muted">Step-up voice score <span className="mono text-fg">{evs.step_up?.step_up?.voice}</span><SimBadge /></div>}
              </>
            ) : <div className="mt-4 flex items-center gap-2 text-sm text-muted"><CircleDashed className="size-4 animate-spin" />Agents are working…</div>}
          </section>
          {evs.explain?.summary && (
            <section className="panel fade-up p-6">
              <div className="flex items-center gap-2"><Sparkles className="size-4 text-brand" /><div className="label">Analyst summary</div></div>
              <p className="mt-3 text-sm leading-relaxed text-fg/90">{evs.explain.summary}</p>
            </section>
          )}
          {evs.error && <section className="panel p-6 text-sm text-reject">Pipeline error: {evs.error.error}</section>}
          {done && <Link href={`/dashboard/case/${id}`} className="btn btn-primary w-full">Open case in analyst console <ArrowRight className="size-4" /></Link>}
          <div className="panel p-4 text-xs text-dim">Event log: <span className="mono">{order.join(" → ")}</span></div>
        </aside>
      </main>
    </div>
  );
}

function Connector() { return <div className="ml-6 h-4 border-l border-line-2" />; }

function Node({ n, ev, running, compact }: { n: (typeof NODES)[number]; ev?: Ev; running: boolean; compact?: boolean }) {
  const I = n.icon;
  const has = !!ev;
  const risk = ev?.risk;
  return (
    <div className={clsx("rounded-xl border p-3.5 transition-all duration-500",
      has ? "border-line-2 bg-panel-2/80" : running ? "border-brand/50 bg-brand/5" : "border-line bg-bg-2/40 opacity-60")}>
      <div className="flex items-center gap-3">
        <span className={clsx("grid size-8 shrink-0 place-items-center rounded-lg", running && "pulse")}
          style={{ background: has ? `color-mix(in srgb, ${risk != null ? riskColor(risk) : "var(--brand)"} 15%, transparent)` : "rgba(255,255,255,.03)" }}>
          <I className="size-4" style={{ color: has ? (risk != null ? riskColor(risk) : "var(--brand)") : "var(--dim)" }} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-sm font-semibold">{n.label}
            {ev?.latency_ms != null && <span className="mono text-[10px] font-normal text-dim">{ev.latency_ms}ms</span>}
          </div>
          {!compact && <div className="truncate text-xs text-dim">{n.sub}</div>}
        </div>
        {risk != null && <span className="mono text-sm" style={{ color: riskColor(risk) }}>{risk.toFixed(2)}</span>}
        {ev?.band && <BandBadge band={ev.band} />}
      </div>
      {compact && <div className="mt-1 truncate text-[11px] text-dim">{n.sub}</div>}
      {risk != null && <RiskBar value={risk} className="mt-2.5" />}
      {!!ev?.reasons?.length && (
        <div className="mt-2.5 flex flex-wrap gap-1">
          {ev.reasons.slice(0, compact ? 3 : 6).map((r) => <span key={r} className="chip mono text-[10px]">{r}</span>)}
          {ev.reasons.length > (compact ? 3 : 6) && <span className="chip text-[10px]">+{ev.reasons.length - (compact ? 3 : 6)}</span>}
        </div>
      )}
    </div>
  );
}
