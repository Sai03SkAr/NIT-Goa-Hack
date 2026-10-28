"use client";
import { use, useEffect, useState } from "react";
import Link from "next/link";
import clsx from "clsx";
import { ArrowRight, Bot, Check, Brain, CheckCircle2, CircleDashed, FileSearch, Fingerprint, GitMerge, Network, Scale, ScanFace, ShieldQuestion, Sparkles, Database } from "lucide-react";
import { BandBadge, Finding, Logo, readable, RiskBar, SimBadge, riskColor } from "@/components/ui";
import { ApiError, type CaseDetail, type EvidenceCheck, get } from "@/lib/api";
import { applicantMessage } from "@/lib/applicantMessage";

type Ev = { node: string; module?: string; risk?: number; reasons?: string[]; reason_texts?: Record<string, string>; rule_codes?: string[]; latency_ms?: number; prob?: number; band?: string;
  forced?: string | null; fraud_label?: string; fraud_action?: string; step_up?: { voice: number; simulated: boolean }; summary?: string; error?: string;
  unresolved?: string[]; model_status?: string; approval_eligible?: boolean };
type Result = { done: boolean; band?: string; reasons?: string[]; evidence?: EvidenceCheck[]; error?: boolean };

const NODES: { id: string; simple: string; label: string; icon: any; sub: string }[] = [
  { id: "ingest", simple: "Application received", label: "Ingest", icon: Database, sub: "consent · uploads · telemetry" },
  { id: "document", simple: "ID card", label: "Document agent", icon: FileSearch, sub: "signed QR · OCR · checksums · forensics" },
  { id: "biometric", simple: "Face", label: "Biometric agent", icon: ScanFace, sub: "face match · reuse · liveness · virtual cam" },
  { id: "behavior", simple: "Form activity", label: "Behavior agent", icon: Bot, sub: "typing · paste · velocity · rhythm links" },
  { id: "registry", simple: "Official records", label: "Registry agent", icon: Fingerprint, sub: "UIDAI · PAN · telecom · CKYC · bureau" },
  { id: "correlation", simple: "Past applications", label: "Correlation agent", icon: Network, sub: "identity graph · rings · families" },
  { id: "fusion", simple: "Combining the results", label: "Fusion", icon: GitMerge, sub: "calibrated XGBoost → evidence policy → band" },
  { id: "step_up", simple: "Extra check", label: "Step-up", icon: ShieldQuestion, sub: "voice check (simulated, shown only)" },
  { id: "decide", simple: "Decision", label: "Decide", icon: Scale, sub: "band · fraud type · action" },
  { id: "explain", simple: "Summary", label: "Explain", icon: Brain, sub: "LLM summary from reason codes only" },
  { id: "persist", simple: "Saved securely", label: "Persist", icon: CheckCircle2, sub: "SQLite + audit log" },
];

export default function Progress({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [evs, setEvs] = useState<Record<string, Ev>>({});
  const [order, setOrder] = useState<string[]>([]);
  const [done, setDone] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [t0] = useState(() => performance.now());
  const [elapsed, setElapsed] = useState(0);
  // applicants see plain next steps; presenters/analysts can switch on the full technical view
  const [tech, setTech] = useState(false);
  useEffect(() => { try { setTech(localStorage.getItem("trueid-tech") === "1"); } catch {} }, []);
  const toggleTech = () => setTech((t) => { try { localStorage.setItem("trueid-tech", t ? "0" : "1"); } catch {} return !t; });

  useEffect(() => {
    // progress by polling (works through the same-origin proxy; event streams get buffered)
    let after = 0, stop = false;
    const restore = () => get<CaseDetail>(`/api/apps/${id}`).then((c) => {
      // analysts reopening an older case: rebuild the view from the saved record
      const restored: Record<string, Ev> = { ingest: { node: "ingest" } };
      for (const m of c.modules) restored[m.module] = { node: m.module, module: m.module, risk: m.risk, reasons: m.reasons.map((r) => r.code),
        reason_texts: Object.fromEntries(m.reasons.map((r) => [r.code, r.text])), latency_ms: m.latency_ms };
      for (const n of ["fusion", "explain", "persist"]) restored[n] = { node: n };
      restored.decide = { node: "decide", band: c.band, prob: c.prob ?? undefined, forced: c.forced, rule_codes: c.rule_codes, fraud_label: c.fraud_label, fraud_action: c.action };
      restored.explain = { node: "explain", summary: c.summary };
      setEvs(restored); setOrder(["restored from saved case"]); setDone(true);
      setResult({ done: true, band: c.band, reasons: c.modules.flatMap((m) => m.reasons.filter((r) => r.weight > 0).map((r) => r.code)), evidence: c.evidence });
    }).catch(() => setEvs((p) => ({ ...p, error: { node: "error", error: "This application could not be found in this browser session." } })));
    const tick = async () => {
      if (stop) return;
      try {
        const r = await get<{ events: Ev[]; next: number; done: boolean }>(`/api/apply/${id}/events?after=${after}`);
        after = r.next;
        if (r.events.length) {
          setEvs((p) => { const n = { ...p }; for (const ev of r.events) n[ev.node] = { ...n[ev.node], ...ev }; return n; });
          setOrder((o) => [...o, ...r.events.map((e) => e.node)]);
        }
        if (r.done) {
          setResult(await get<Result>(`/api/apply/${id}/result`));
          setDone(true);
          return;
        }
      } catch (e) {
        if (e instanceof ApiError && (e.status === 404 || e.status === 401)) return restore();
      }
      setTimeout(tick, 600);
    };
    tick();
    return () => { stop = true; };
  }, [id]);
  useEffect(() => {
    if (done) return;
    const t = setInterval(() => setElapsed((performance.now() - t0) / 1000), 100);
    return () => clearInterval(t);
  }, [done, t0]);

  const decision = evs.decide ?? evs.fusion;
  const allCodes = [...(result?.reasons ?? Object.values(evs).flatMap((e) => e.reasons ?? [])), ...(evs.decide?.rule_codes ?? evs.fusion?.rule_codes ?? []),
    ...(result?.evidence ?? []).filter((c) => c.status !== "PASS").map((c) => `EV_${c.check.toUpperCase()}_${c.status}`)];
  const band = result?.band ?? decision?.band;
  const msg = applicantMessage(done ? band : undefined, allCodes);
  const stepped = !!evs.step_up;
  const parallel = ["document", "biometric", "behavior", "registry"];
  const running = (n: string) => !evs[n] && !done && (
    n === "ingest" ? true : parallel.includes(n) ? !!evs.ingest : n === "correlation" ? parallel.every((p) => evs[p]) :
    n === "fusion" ? !!evs.correlation : n === "decide" ? !!evs.fusion && !(evs.fusion.band === "REVIEW" && !stepped) :
    n === "explain" ? !!evs.decide : n === "persist" ? !!evs.explain : false);

  return (
    <div className="min-h-[100dvh]">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
        <Logo /><span className="chip mono">{id} · {done ? "complete" : `${elapsed.toFixed(1)}s`}</span>
      </header>
      <main className="mx-auto grid max-w-6xl gap-6 px-6 pb-20 lg:grid-cols-[1.25fr_1fr]">
        <section className="panel p-6">
          <h1 className="mb-1 text-lg font-semibold">Checking your application</h1>
          <p className="mb-5 text-sm text-muted">Each check runs independently; the decision combines all of them.</p>
          <Node n={NODES[0]} ev={evs.ingest} running={running("ingest")} tech={tech} />
          <Connector />
          <div className="grid gap-3 sm:grid-cols-2">
            {NODES.slice(1, 5).map((n) => <Node key={n.id} n={n} ev={evs[n.id]} running={running(n.id)} compact tech={tech} />)}
          </div>
          <Connector />
          {NODES.slice(5).map((n, i) => {
            if (n.id === "step_up" && !stepped) return !tech ? null : <div key={n.id} className="ml-6 border-l border-dashed border-line-2 py-1 pl-4 text-xs text-dim">step-up only if fusion lands in REVIEW</div>;
            return <div key={n.id}>{i > 0 && <Connector />}<Node n={n} ev={evs[n.id]} running={running(n.id)} tech={tech} /></div>;
          })}
        </section>

        <aside className="space-y-6">
          <section className="panel p-6" aria-live="polite">
            {done && band ? (
              <div>
                <BandBadge band={band} size="lg" />
                <h2 className="mt-4 text-xl font-semibold tracking-tight">{msg.title}</h2>
                <p className="mt-2 leading-relaxed text-muted">{msg.body}</p>
                {msg.action && <Link href={msg.action.href} className="btn btn-primary mt-5">{msg.action.label}</Link>}
              </div>
            ) : <div className="flex items-center gap-2 text-muted"><CircleDashed className="size-4 animate-spin" />Checking your application</div>}
          </section>
          <label className="flex cursor-pointer items-center justify-between rounded-lg border border-line bg-panel px-4 py-2.5 text-sm">
            <span>Technical details <span className="text-dim">(for reviewers and demos)</span></span>
            <input type="checkbox" checked={tech} onChange={toggleTech} className="size-4 accent-brand" />
          </label>
          {tech && <>
          <section className={clsx("panel p-6 transition", done && "fade-up")}>
            <div className="label">Decision</div>
            {decision?.band ? (
              <>
                <div className="mt-3 flex items-center gap-4">
                  <BandBadge band={decision.band} size="lg" />
                  <div className="text-sm text-muted">{decision.prob == null ? "Risk model unavailable: a person decides"
                    : <>Model fraud probability <span className="mono text-fg">{decision.prob.toFixed(3)}</span></>}</div>
                </div>
                {decision.prob != null && <RiskBar value={decision.prob} className="mt-4" />}
                {decision.forced === "REJECT" && <div className="mt-3 text-xs text-muted">Set by a fixed evidence rule (the signed card data was contradicted), not by the model.</div>}
                {!!evs.fusion?.unresolved?.length && <div className="mt-3 text-xs text-muted">Not approvable automatically until these checks pass: <span className="text-fg">{evs.fusion.unresolved.join(", ").replaceAll("_", " ")}</span></div>}
                {evs.decide?.fraud_label && evs.decide.band !== "APPROVE" && (
                  <div className="mt-5 rounded-lg border border-line bg-bg-2 p-4">
                    <div className="label">Pattern</div><div className="mt-1 font-semibold">{evs.decide.fraud_label}</div>
                    <div className="label mt-3">Recommended action</div><div className="mt-1 text-sm">{evs.decide.fraud_action}</div>
                  </div>
                )}
                {stepped && <div className="mt-4 flex items-center gap-2 text-sm text-muted">Step-up voice score <span className="mono text-fg">{evs.step_up?.step_up?.voice}</span><SimBadge /><span className="text-xs text-dim">shown only, not used in the decision</span></div>}
              </>
            ) : <div className="mt-4 flex items-center gap-2 text-sm text-muted"><CircleDashed className="size-4 animate-spin" />Running checks</div>}
          </section>
          {evs.explain?.summary && (
            <section className="panel fade-up p-6">
              <div className="flex items-center gap-2"><Sparkles className="size-4 text-brand" /><div className="label">Analyst summary</div></div>
              <p className="mt-3 text-sm leading-relaxed text-fg">{readable(evs.explain.summary)}</p>
            </section>
          )}
          {done && <Link href={`/dashboard/case/${id}`} className="btn w-full">Open case in analyst console <ArrowRight className="size-4" /></Link>}
          <div className="panel p-4 text-xs text-dim">Event log: <span className="mono">{order.join(" → ")}</span></div>
          </>}
          {evs.error && <section className="panel p-6 text-sm text-reject">Something went wrong while checking. Please try again. {tech && evs.error.error}</section>}
        </aside>
      </main>
    </div>
  );
}

function Connector() { return <div className="ml-6 h-4 border-l border-line-2" />; }

function Node({ n, ev, running, compact, tech }: { n: (typeof NODES)[number]; ev?: Ev; running: boolean; compact?: boolean; tech?: boolean }) {
  const I = n.icon;
  const has = !!ev;
  const risk = tech ? ev?.risk : undefined;
  return (
    <div className={clsx("rounded-xl border p-3.5 transition-all duration-500",
      has ? "border-line bg-panel" : running ? "border-brand bg-brand-soft" : "border-line bg-bg-2 text-dim")}>
      <div className="flex items-center gap-3">
        <span className={clsx("grid size-8 shrink-0 place-items-center rounded-lg", running && "working")}
          style={{ background: has ? `color-mix(in srgb, ${risk != null ? riskColor(risk) : "var(--brand)"} 10%, var(--panel))` : "var(--panel)" }}>
          <I className="size-4" style={{ color: has ? (risk != null ? riskColor(risk) : "var(--brand)") : "var(--dim)" }} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-sm font-semibold">{tech ? n.label : n.simple}
            {tech && ev?.latency_ms != null && <span className="mono text-[10px] font-normal text-dim">{ev.latency_ms}ms</span>}
          </div>
          {tech && !compact && <div className="truncate text-xs text-dim">{n.sub}</div>}
        </div>
        {risk != null && <span className="mono text-sm" style={{ color: riskColor(risk) }}>{risk.toFixed(2)}</span>}
        {tech && ev?.band && <BandBadge band={ev.band} />}
        {!tech && ev && <Check className="size-4 text-approve" aria-label="done" />}
      </div>
      {tech && compact && <div className="mt-1 truncate text-[11px] text-dim">{n.sub}</div>}
      {risk != null && <RiskBar value={risk} className="mt-2.5" />}
      {tech && !!ev?.reasons?.length && (
        <ul className="mt-2.5 space-y-1 [&_li]:text-xs">
          {ev.reasons.slice(0, compact ? 3 : 6).map((r) => <Finding key={r} code={r} text={ev.reason_texts?.[r] ?? r} />)}
          {ev.reasons.length > (compact ? 3 : 6) && <li className="pl-4 text-dim">and {ev.reasons.length - (compact ? 3 : 6)} more</li>}
        </ul>
      )}
    </div>
  );
}
