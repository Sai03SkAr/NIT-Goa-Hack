"use client";
import { useEffect, useState } from "react";
import clsx from "clsx";
import { Activity, ArrowRight, Check, Database, FlaskConical, GraduationCap, HeartPulse, Lightbulb, Play, RotateCcw, Scale, ShieldCheck, X } from "lucide-react";
import { EmptyState, PageHeader, Section, featureLabel, pct, when } from "@/components/ui";
import { ApplicantTips, type Coaching } from "@/components/Tips";
import { get, post } from "@/lib/api";

type Tab = "proposals" | "drift" | "feedback" | "coaching" | "history";
const TABS: [Tab, string][] = [["proposals", "Proposals"], ["drift", "Drift & health"], ["feedback", "Feedback"], ["coaching", "Applicant coaching"], ["history", "History"]];
const KIND: Record<string, { label: string; icon: any; color: string }> = {
  bands: { label: "Decision bands", icon: Scale, color: "var(--brand)" },
  retrain: { label: "Challenger model", icon: FlaskConical, color: "var(--brand)" },
  advisory: { label: "Signal advisory", icon: Lightbulb, color: "var(--review)" },
  health: { label: "Check health", icon: HeartPulse, color: "var(--reject)" },
  coaching: { label: "Coaching gap", icon: GraduationCap, color: "var(--approve)" },
};
const STATUS_TONE: Record<string, string> = { stable: "var(--approve)", ok: "var(--approve)", watch: "var(--review)", surge: "var(--review)",
  drift: "var(--reject)", unavailable: "var(--reject)", unknown: "var(--dim)" };

export default function Learning() {
  const [tab, setTab] = useState<Tab>("proposals");
  const [ov, setOv] = useState<any>(null);
  const [props, setProps] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const load = () => Promise.all([get("/api/learning/overview"), get("/api/learning/proposals")])
    .then(([o, p]) => { setOv(o); setProps(p); setErr(""); }).catch((e) => setErr(String(e)));
  useEffect(() => { load(); }, []);

  async function cycle() {
    setBusy(true);
    try { await post("/api/learning/cycle"); await load(); setTab("proposals"); } catch (e) { setErr(String(e)); } finally { setBusy(false); }
  }

  if (err && !ov) return <div className="panel p-6 text-reject">{err}</div>;
  if (!ov) return <div className="space-y-4">{[80, 170, 420].map((h) => <div key={h} className="animate-pulse rounded-2xl bg-bg-2" style={{ height: h }} />)}</div>;
  const open = props.filter((p) => p.status === "proposed");

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Insights" title="Learning loop"
        right={<>
          {ov.last_cycle && <span className="text-xs text-dim">Last cycle {when(ov.last_cycle.ts)} · {ov.last_cycle.trigger}</span>}
          <button className="btn btn-primary min-h-11" onClick={cycle} disabled={busy}><Play className={clsx("size-4", busy && "animate-pulse")} />{busy ? "Learning…" : "Run a learning cycle"}</button>
        </>}>
        TrueID learns from what analysts decide and proposes how to improve. Nothing changes until an analyst approves it, and every change can be rolled back.
      </PageHeader>

      <Loop ov={ov} onOpen={setTab} />

      <div className="tabs" role="tablist" aria-label="Learning sections">
        {TABS.map(([k, l]) => (
          <button key={k} role="tab" aria-selected={tab === k} className="tab" onClick={() => setTab(k)}>
            {l}{k === "proposals" && open.length > 0 && <span className={clsx("mono text-xs", tab === k ? "text-white/70" : "text-brand")}>{open.length}</span>}
          </button>
        ))}
      </div>
      {err && <p className="text-sm text-reject">{err}</p>}

      {tab === "proposals" && <Proposals props={props} ov={ov} onChange={load} />}
      {tab === "drift" && <Drift />}
      {tab === "feedback" && <Feedback fb={ov.feedback} />}
      {tab === "coaching" && <CoachingTab />}
      {tab === "history" && <History props={props} />}
    </div>
  );
}

/** The four stages as one band: what came in, what moved, what is proposed, what was decided. */
function Loop({ ov, onOpen }: { ov: any; onOpen: (t: Tab) => void }) {
  const fb = ov.feedback, d = ov.drift, p = ov.proposals;
  const stages = [
    { n: "01", name: "Collect", icon: Database, tab: "feedback" as Tab, value: fb.analyst.toLocaleString(), unit: "analyst decisions",
      sub: `${fb.since_last_cycle} new · next cycle after ${ov.next_cycle_in} more`, tone: "var(--brand)" },
    { n: "02", name: "Monitor", icon: Activity, tab: "drift" as Tab, value: String(d.alerts), unit: d.alerts === 1 ? "alert" : "alerts",
      sub: `score drift: ${d.score.status}${d.top_feature ? ` · ${featureLabel(d.top_feature.feature)} ${d.top_feature.status}` : ""}`, tone: d.alerts ? "var(--review)" : "var(--approve)" },
    { n: "03", name: "Propose", icon: Lightbulb, tab: "proposals" as Tab, value: String(p.open), unit: "open proposals",
      sub: ov.challenger.ready ? "challenger model in training" : "challenger: " + (ov.challenger.why ?? "idle").replace(/\.$/, "").toLowerCase(), tone: p.open ? "var(--brand)" : "var(--dim)" },
    { n: "04", name: "Govern", icon: ShieldCheck, tab: "history" as Tab, value: String(p.applied), unit: "applied",
      sub: `${p.rolled_back} rolled back · bands ${ov.bands.approve_below} / ${ov.bands.reject_at}`, tone: "var(--approve)" },
  ];
  return (
    <section aria-label="Learning loop" className="relative overflow-hidden rounded-2xl bg-ink p-2 text-white">
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        {stages.map((s, i) => (
          <button key={s.name} onClick={() => onOpen(s.tab)}
            className="group relative flex min-h-[132px] flex-col justify-between rounded-xl bg-white/[0.04] p-4 text-left transition-colors hover:bg-white/[0.09]">
            <span className="flex items-center justify-between">
              <span className="flex items-center gap-2 text-[13px] text-white/60"><span className="mono text-white/40">{s.n}</span>{s.name}</span>
              <s.icon className="size-4" style={{ color: s.tone }} />
            </span>
            <span className="mt-3 flex items-baseline gap-2"><span className="display text-[34px] leading-none">{s.value}</span><span className="text-sm text-white/60">{s.unit}</span></span>
            <span className="mt-2 line-clamp-2 text-xs leading-snug text-white/50">{s.sub}</span>
            {i < 3 && <ArrowRight className="absolute -right-3.5 top-1/2 z-10 hidden size-5 -translate-y-1/2 rounded-full bg-ink p-0.5 text-white/40 xl:block" />}
          </button>
        ))}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 px-3 pb-1.5 pt-3 text-xs text-white/45">
        <span className="flex items-center gap-2"><RotateCcw className="size-3.5" />Approved changes feed the next cycle, so the loop keeps closing.</span>
        <span>Labels are analyst decisions only. The system never learns from its own verdicts.</span>
      </div>
    </section>
  );
}

function Proposals({ props, ov, onChange }: { props: any[]; ov: any; onChange: () => void }) {
  const [filter, setFilter] = useState<"open" | "applied" | "closed">("open");
  const ORDER = ["bands", "retrain", "health", "advisory", "coaching"];
  const shown = props.filter((p) => filter === "open" ? p.status === "proposed" : filter === "applied" ? p.status === "applied"
    : !["proposed", "applied"].includes(p.status))
    .sort((a, b) => Number(b.applicable) - Number(a.applicable) || ORDER.indexOf(a.kind) - ORDER.indexOf(b.kind));
  const ch = ov.challenger;
  return (
    <div className="grid grid-cols-1 items-start gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
      <div className="min-w-0 space-y-4">
        <div className="seg">
          {([["open", "Open"], ["applied", "Applied"], ["closed", "Closed"]] as const).map(([k, l]) => (
            <button key={k} aria-pressed={filter === k} onClick={() => setFilter(k)}>{l} <span className="mono text-xs text-dim">{props.filter((p) => k === "open" ? p.status === "proposed" : k === "applied" ? p.status === "applied" : !["proposed", "applied"].includes(p.status)).length}</span></button>
          ))}
        </div>
        {shown.map((p) => <ProposalCard key={p.id} p={p} onChange={onChange} />)}
        {!shown.length && <div className="panel"><EmptyState icon={Lightbulb} title={filter === "open" ? "No open proposals" : "Nothing here yet"}>
          {filter === "open" ? "Run a learning cycle, or wait for more analyst decisions. A cycle also runs by itself after every 10 decisions." : "Decisions on proposals show up here."}</EmptyState></div>}
      </div>
      <aside className="space-y-5 xl:sticky xl:top-6">
        <Section title="Challenger model" sub="Retrained with analyst feedback, tested against the live model">
          <div className="flex items-baseline justify-between text-sm"><span className="text-muted">Analyst decisions</span><span className="mono">{ch.labels} / {ch.needed}</span></div>
          <div className="mt-2 h-2 rounded-full bg-bg-2"><div className="h-full rounded-full bg-brand" style={{ width: `${Math.min(100, (ch.labels / ch.needed) * 100)}%` }} /></div>
          <p className={clsx("mt-3 text-sm", ch.ready ? "text-approve" : "text-muted")}>{ch.ready ? "Ready: the next cycle trains a challenger." : ch.why}</p>
          <ul className="mt-3 space-y-1.5 text-xs text-dim">
            <li>Never worse on the original test set</li><li>Better on decisions it has not seen</li><li>Promoted only by an analyst, with rollback</li>
          </ul>
        </Section>
        <Section title="Live decision bands">
          <BandBar bands={ov.bands} />
          <p className="mt-3 text-xs text-dim">Required evidence rules sit outside the loop. Changing them is a policy change ({ov.policy_version}) and needs sign-off.</p>
        </Section>
      </aside>
    </div>
  );
}

function BandBar({ bands, label }: { bands: { approve_below: number; reject_at: number }; label?: string }) {
  return (
    <div>
      {label && <div className="mb-1 text-xs text-dim">{label}</div>}
      <div className="flex h-3 overflow-hidden rounded-full" aria-hidden>
        <span style={{ width: `${bands.approve_below * 100}%`, background: "var(--approve)" }} />
        <span style={{ width: `${(bands.reject_at - bands.approve_below) * 100}%`, background: "var(--review)" }} />
        <span className="flex-1" style={{ background: "var(--reject)" }} />
      </div>
      <div className="mono mt-1 flex justify-between text-[11px] text-dim"><span>0</span><span>approve &lt; {bands.approve_below}</span><span>reject ≥ {bands.reject_at}</span><span>1</span></div>
    </div>
  );
}

function ProposalCard({ p, onChange }: { p: any; onChange: () => void }) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const k = KIND[p.kind] ?? KIND.advisory;
  async function act(action: string) {
    setBusy(true); setMsg("");
    try { await post(`/api/learning/proposals/${p.id}`, { action }); onChange(); } catch (e) { setMsg(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  }
  const advisory = ["advisory", "health", "coaching"].includes(p.kind);
  return (
    <article className="panel overflow-hidden">
      <div className="h-1" style={{ background: k.color }} />
      <div className="p-5">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="chip" style={{ color: k.color }}><k.icon className="size-3.5" />{k.label}</span>
          <span className="mono text-dim">{p.id} · {when(p.ts)}</span>
          {p.status !== "proposed" && <span className="chip capitalize">{p.status.replace("_", " ")}{p.decided_by && ` · ${p.decided_by.replace("analyst:", "")}`}</span>}
        </div>
        <h3 className="display mt-3 text-[19px] leading-snug">{p.title}</h3>
        <p className="mt-1.5 text-sm leading-relaxed text-muted">{p.rationale}</p>

        {p.kind === "bands" && p.impact?.before && <BandsImpact p={p} />}
        {p.kind === "retrain" && <RetrainImpact r={p.impact} />}
        {advisory && p.evidence && <AdvisoryFacts p={p} />}

        {!!p.safeguards?.length && (
          <ul className="mt-4 grid gap-1.5 text-[13px] sm:grid-cols-2">
            {p.safeguards.map((g: any) => (
              <li key={g.rule} className="flex items-start gap-2">
                {g.ok ? <Check className="mt-0.5 size-4 shrink-0 text-approve" /> : <X className="mt-0.5 size-4 shrink-0 text-reject" />}
                <span>{g.rule} <span className="mono text-xs text-dim">{g.value}</span></span>
              </li>
            ))}
          </ul>
        )}

        <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-line pt-4">
          {p.status === "proposed" && !advisory && <button className="btn btn-primary min-h-10" disabled={busy || !p.applicable} onClick={() => act("apply")}><Check className="size-4" />Apply to live system</button>}
          {p.status === "proposed" && advisory && <button className="btn min-h-10" disabled={busy} onClick={() => act("acknowledge")}><Check className="size-4" />Acknowledge</button>}
          {p.status === "proposed" && <button className="btn btn-ghost min-h-10 text-muted" disabled={busy} onClick={() => act("dismiss")}>Dismiss</button>}
          {p.status === "applied" && <button className="btn btn-danger min-h-10" disabled={busy} onClick={() => act("rollback")}><RotateCcw className="size-4" />Roll back</button>}
          {p.status === "proposed" && !advisory && !p.applicable && <span className="text-xs text-reject">A safeguard did not pass, so this cannot be applied.</span>}
          {advisory && p.status === "proposed" && <span className="text-xs text-dim">Advisory only: it never changes the live system.</span>}
          {msg && <span className="text-xs text-reject">{msg}</span>}
        </div>
      </div>
    </article>
  );
}

function BandsImpact({ p }: { p: any }) {
  const b = p.impact.before, a = p.impact.after;
  const curve: { t: number; cost: number }[] = p.evidence?.curve ?? [];
  const max = Math.max(1, ...curve.map((c) => c.cost));
  const x = (t: number) => 8 + ((t - 0.05) / 0.55) * 284, y = (c: number) => 74 - (c / max) * 62;
  const rows: [string, (v: any) => string][] = [["Cost", (v) => String(Math.round(v.cost))], ["Fraud caught", (v) => pct(v.recall, 0)], ["False alarms", (v) => pct(v.false_alarms, 0)]];
  return (
    <div className="mt-4 grid gap-4 rounded-xl bg-bg-2/60 p-4 lg:grid-cols-[1fr_1fr]">
      <div className="space-y-3">
        <BandBar bands={b} label="Now" />
        <BandBar bands={a} label="Proposed" />
      </div>
      <div>
        <table className="w-full text-sm">
          <thead><tr className="text-left text-xs text-dim"><th className="font-medium" /><th className="font-medium">Now</th><th className="font-medium">Proposed</th></tr></thead>
          <tbody className="mono text-[13px]">
            {rows.map(([k, f]) => <tr key={k}><td className="py-1 font-sans text-muted">{k}</td><td>{f(b)}</td><td className="font-medium text-brand">{f(a)}</td></tr>)}
          </tbody>
        </table>
        {curve.length > 0 && (
          <svg viewBox="0 0 300 84" className="mt-2 w-full" role="img" aria-label="Cost at each approve cut-off">
            <polyline fill="none" stroke="var(--line-2)" strokeWidth="1" points="8,74 292,74" />
            <polyline fill="none" stroke="var(--brand)" strokeWidth="2" points={curve.map((c) => `${x(c.t)},${y(c.cost)}`).join(" ")} />
            <line x1={x(b.approve_below)} x2={x(b.approve_below)} y1="6" y2="74" stroke="var(--dim)" strokeDasharray="3 3" />
            <circle cx={x(a.approve_below)} cy={y(a.cost)} r="4" fill="var(--brand)" />
            <text x={x(b.approve_below) + 4} y="14" fontSize="9" fill="var(--dim)">now</text>
            <text x={Math.min(x(a.approve_below) + 6, 250)} y={y(a.cost) - 6} fontSize="9" fill="var(--brand)">proposed</text>
          </svg>
        )}
      </div>
    </div>
  );
}

function RetrainImpact({ r }: { r: any }) {
  if (!r?.base_test) return null;
  return (
    <table className="mt-4 w-full text-sm">
      <thead><tr className="text-left text-xs text-dim"><th className="font-medium">ROC-AUC on</th><th className="font-medium">Live model</th><th className="font-medium">Challenger</th><th className="font-medium">Cases</th></tr></thead>
      <tbody className="mono text-[13px]">
        <tr className="border-t border-line"><td className="py-1.5 font-sans">Original test split</td><td>{r.base_test.champion}</td><td>{r.base_test.challenger}</td><td>{r.base_test.n}</td></tr>
        <tr className="border-t border-line"><td className="py-1.5 font-sans">Held-out analyst decisions</td><td>{r.feedback_holdout.champion ?? "n/a"}</td><td>{r.feedback_holdout.challenger ?? "n/a"}</td><td>{r.feedback_holdout.n}</td></tr>
      </tbody>
    </table>
  );
}

function AdvisoryFacts({ p }: { p: any }) {
  const e = p.evidence;
  const facts: [string, string][] = p.kind === "advisory" ? [["Cases", String(e.n)], ["Confirmed fraud", pct(e.fraud_rate, 0)], ...(e.in_review != null ? [["Sat in review", String(e.in_review)] as [string, string]] : [])]
    : p.kind === "coaching" ? [["Held by it", String(e.held)], ["Held only by it", String(e.only)], ["Approved after review", pct(e.resolution_rate, 0)]]
    : e.fail_recent != null ? [["Failing now", pct(e.fail_recent, 0)], ["Failing before", pct(e.fail_ref, 0)], ["Could not run", pct(e.unavailable_recent, 0)]]
    : e.psi != null ? [["PSI", String(e.psi)], ["Status", e.status]] : [];
  if (!facts.length) return null;
  return (
    <dl className="mt-4 flex flex-wrap gap-2">
      {facts.map(([k, v]) => <div key={k} className="well px-3 py-2"><dt className="text-[11px] text-dim">{k}</dt><dd className="mono text-sm">{v}</dd></div>)}
    </dl>
  );
}

function Drift() {
  const [d, setD] = useState<any>(null);
  useEffect(() => { get("/api/learning/drift").then(setD).catch(() => {}); }, []);
  if (!d) return <div className="h-80 animate-pulse rounded-2xl bg-bg-2" />;
  const score = d.score.psi ?? 0;
  const maxF = Math.max(0.5, ...d.features.map((f: any) => Math.min(f.psi, 2)));
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1fr_1.4fr]">
        <Section title="Fraud-score drift" sub="Population stability index, recent window vs reference">
          <div className="display text-[44px] leading-none" style={{ color: STATUS_TONE[d.score.status] }}>{d.score.psi ?? "n/a"}</div>
          <div className="mt-1 text-sm capitalize text-muted">{d.score.status}</div>
          <div className="relative mt-5 h-3 overflow-hidden rounded-full" aria-hidden>
            <div className="absolute inset-y-0 left-0 bg-[color-mix(in_srgb,var(--approve)_30%,var(--panel))]" style={{ width: "20%" }} />
            <div className="absolute inset-y-0 bg-[color-mix(in_srgb,var(--review)_30%,var(--panel))]" style={{ left: "20%", width: "30%" }} />
            <div className="absolute inset-y-0 right-0 bg-[color-mix(in_srgb,var(--reject)_30%,var(--panel))]" style={{ left: "50%" }} />
            <div className="absolute inset-y-[-2px] w-1 rounded bg-ink" style={{ left: `${Math.min(99, (score / 0.5) * 100)}%` }} />
          </div>
          <div className="mono mt-1 flex justify-between text-[11px] text-dim"><span>0</span><span>0.1 watch</span><span>0.25 drift</span><span>0.5+</span></div>
          <dl className="mt-5 grid grid-cols-2 gap-2 text-sm">
            <div className="well px-3 py-2"><dt className="text-xs text-dim">Reference</dt><dd className="mono text-[13px]">{d.reference.n} apps</dd><dd className="text-[11px] text-dim">{d.reference.from?.slice(0, 10)} → {d.reference.to?.slice(0, 10)}</dd></div>
            <div className="well px-3 py-2"><dt className="text-xs text-dim">Recent</dt><dd className="mono text-[13px]">{d.recent.n} apps</dd><dd className="text-[11px] text-dim">{d.recent.from?.slice(0, 10)} → {d.recent.to?.slice(0, 10)}</dd></div>
          </dl>
        </Section>
        <Section title="Feature drift" sub="Which inputs changed most. Long bars mean applicants now look different from what the model saw.">
          <div className="space-y-2.5">
            {d.features.map((f: any) => (
              <div key={f.feature} className="grid grid-cols-[minmax(120px,210px)_1fr_64px] items-center gap-3 text-[13px]">
                <span className="truncate text-muted" title={f.feature}>{featureLabel(f.feature)}</span>
                <span className="relative h-2.5 rounded bg-bg-2">
                  <span className="absolute inset-y-0 left-0 rounded" style={{ width: `${(Math.min(f.psi, 2) / maxF) * 100}%`, background: STATUS_TONE[f.status] }} />
                  <span className="absolute inset-y-[-3px] w-px bg-dim" style={{ left: `${(0.25 / maxF) * 100}%` }} title="drift threshold" />
                </span>
                <span className="mono text-right" style={{ color: STATUS_TONE[f.status] }}>{f.psi}</span>
              </div>
            ))}
            {!d.features.length && <p className="text-sm text-dim">Not enough applications yet.</p>}
          </div>
        </Section>
      </div>
      <Section title="Check health" sub="Is each evidence check still running, and failing as often as usual?">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[620px] text-sm">
            <thead><tr className="text-left text-xs text-dim"><th className="py-2 font-medium">Check</th><th className="font-medium">Failing before</th><th className="font-medium">Failing now</th><th className="font-medium">Could not run</th><th className="font-medium">Status</th></tr></thead>
            <tbody>
              {d.checks.map((c: any) => (
                <tr key={c.check} className="border-t border-line/70">
                  <td className="py-2 pr-3">{c.label}{!c.required && <span className="ml-1.5 text-[11px] text-dim">info</span>}</td>
                  <td className="mono text-[13px]">{pct(c.fail_ref, 0)}</td><td className="mono text-[13px]">{pct(c.fail_recent, 0)}</td><td className="mono text-[13px]">{pct(c.unavailable_recent, 0)}</td>
                  <td><span className="chip capitalize" style={{ color: STATUS_TONE[c.status] }}>{c.status === "ok" ? "healthy" : c.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>
      <Section title="Decision mix" sub="Share of applications in each band">
        {(["reference", "recent"] as const).map((w) => (
          <div key={w} className="mt-2 grid grid-cols-[80px_1fr] items-center gap-3 text-sm first:mt-0">
            <span className="capitalize text-muted">{w}</span>
            <div className="flex h-6 overflow-hidden rounded-lg text-[11px] text-white">
              {(["APPROVE", "REVIEW", "REJECT"] as const).map((b) => { const v = d.bands[w][b] ?? 0; return v > 0 &&
                <span key={b} className="grid place-items-center" style={{ width: `${v * 100}%`, background: `var(--${b.toLowerCase()})` }}>{v >= 0.08 ? pct(v, 0) : ""}</span>; })}
            </div>
          </div>
        ))}
      </Section>
    </div>
  );
}

function Feedback({ fb }: { fb: any }) {
  const maxDay = Math.max(1, ...fb.per_day.map((d: any) => d.n));
  const cell = (band: string, k: string) => fb.agreement?.[band]?.[k] ?? 0;
  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
      <Section title="Where the labels come from" sub="Only analyst decisions teach the system. Its own verdicts never do.">
        <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {[["All labels", fb.total], ["From analysts", fb.analyst], ["Analysts", fb.analysts], ["Went against the system", fb.against_automated]].map(([k, v]) => (
            <div key={k} className="well px-3 py-2.5"><dt className="text-xs text-dim">{k}</dt><dd className="display mt-1 text-[24px] leading-none">{Number(v).toLocaleString()}</dd></div>
          ))}
        </dl>
        <div className="mt-5">
          <div className="flex justify-between text-xs text-dim"><span>Largest share written by one analyst</span><span className="mono">{pct(fb.top_analyst_share, 0)} (limit 60%)</span></div>
          <div className="relative mt-1.5 h-2.5 rounded-full bg-bg-2">
            <div className="h-full rounded-full" style={{ width: `${fb.top_analyst_share * 100}%`, background: fb.top_analyst_share > 0.6 ? "var(--reject)" : "var(--brand)" }} />
            <div className="absolute inset-y-[-3px] w-0.5 bg-ink" style={{ left: "60%" }} />
          </div>
          <p className="mt-2 text-xs text-dim">If one person wrote most of the feedback, their judgement (or a compromised account) could steer the model, so proposals are blocked above the limit.</p>
        </div>
        {fb.per_day.length > 0 && <>
          <div className="mt-5 text-xs text-dim">Decisions per day</div>
          <div className="mt-2 flex h-20 items-end gap-[3px]">
            {fb.per_day.map((d: any) => <span key={d.day} title={`${d.day}: ${d.n}`} className="flex-1 rounded-t bg-brand/70" style={{ height: `${(d.n / maxDay) * 100}%` }} />)}
          </div>
        </>}
      </Section>
      <Section title="System vs analyst" sub="How analysts decided cases in each automated band">
        <div className="grid grid-cols-[96px_1fr_1fr] gap-2 text-sm">
          <span /><span className="text-xs text-dim">Analyst approved</span><span className="text-xs text-dim">Analyst rejected</span>
          {(["APPROVE", "REVIEW", "REJECT"] as const).map((b) => (
            <div key={b} className="contents">
              <span className="self-center text-xs capitalize text-dim">System: {b.toLowerCase()}</span>
              {(["approved", "rejected"] as const).map((k) => {
                const agree = (b === "APPROVE") === (k === "approved");
                const tone = b === "REVIEW" ? "var(--brand)" : agree ? "var(--approve)" : "var(--reject)";
                return <div key={k} className="rounded-xl px-4 py-3" style={{ background: `color-mix(in srgb, ${tone} 8%, var(--panel))` }}>
                  <div className="display text-[24px] leading-none" style={{ color: tone }}>{cell(b, k)}</div>
                  <div className="mt-1 text-xs text-muted">{b === "REVIEW" ? "resolved review" : agree ? "agreed" : "overruled"}</div>
                </div>;
              })}
            </div>
          ))}
        </div>
        <p className="mt-4 text-xs text-dim">Overruled automatic decisions are the most valuable labels: they show where the model is wrong. Approving what the system rejected needs a second analyst.</p>
      </Section>
    </div>
  );
}

function CoachingTab() {
  const [c, setC] = useState<any>(null);
  const [id, setId] = useState("");
  const [preview, setPreview] = useState<Coaching | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => { get("/api/learning/coaching").then(setC).catch(() => {}); }, []);
  async function show(e: React.FormEvent) {
    e.preventDefault(); setErr(""); setPreview(null);
    try { setPreview(await get(`/api/learning/tips/${encodeURIComponent(id.trim())}`)); } catch { setErr("No application with that ID."); }
  }
  if (!c) return <div className="h-80 animate-pulse rounded-2xl bg-bg-2" />;
  const max = Math.max(1, ...c.friction.map((f: any) => f.held));
  return (
    <div className="grid grid-cols-1 items-start gap-5 lg:grid-cols-[1.2fr_1fr]">
      <div className="space-y-5">
        <Section title="Where genuine people get stuck" sub="Fixable checks that held applications, and how often those people were approved in the end">
          <div className="space-y-4">
            {c.friction.map((f: any) => (
              <div key={f.check}>
                <div className="flex flex-wrap items-baseline justify-between gap-2 text-sm"><span className="font-medium">{f.title}</span>
                  <span className="text-xs text-dim"><span className="mono">{f.held}</span> held · <span className="mono">{f.only}</span> by this alone</span></div>
                <div className="mt-1.5 h-2.5 rounded bg-bg-2"><div className="h-full rounded bg-review" style={{ width: `${(f.held / max) * 100}%` }} /></div>
                {f.resolution_rate != null && <div className="mt-1 text-xs text-muted"><span className="mono text-approve">{pct(f.resolution_rate, 0)}</span> approved after analyst review</div>}
              </div>
            ))}
            {!c.friction.length && <p className="text-sm text-dim">No applicant has been held by a fixable check yet.</p>}
          </div>
        </Section>
        <Section title="What applicants are told" sub="Only issues they can fix. Fraud signals are never explained, so the tips cannot be used to tune an attack.">
          <div className="grid gap-3 sm:grid-cols-2">
            {c.catalog.map((t: any) => (
              <div key={t.check} className="well p-3.5">
                <div className="text-sm font-medium">{t.title}</div>
                <ul className="mt-1.5 space-y-1 text-xs text-muted">{t.steps.map((s: string) => <li key={s}>{s}</li>)}</ul>
              </div>
            ))}
          </div>
        </Section>
      </div>
      <Section title="Preview an applicant's tips" sub="Exactly what the applicant sees on their result page" className="lg:sticky lg:top-6">
        <form onSubmit={show} className="flex gap-2">
          <input className="input mono min-h-11" placeholder="Application ID, e.g. L0412" value={id} onChange={(e) => setId(e.target.value)} />
          <button className="btn min-h-11" disabled={!id.trim()}>Show</button>
        </form>
        {err && <p className="mt-2 text-sm text-reject">{err}</p>}
        <div className="mt-4">{preview ? <ApplicantTips c={preview} compact /> : <p className="text-sm text-dim">Enter an application ID from the queue.</p>}</div>
      </Section>
    </div>
  );
}

function History({ props }: { props: any[] }) {
  const [cycles, setCycles] = useState<any[] | null>(null);
  useEffect(() => { get("/api/learning/cycles").then(setCycles).catch(() => setCycles([])); }, []);
  const decided = props.filter((p) => p.decided_ts).sort((a, b) => b.decided_ts.localeCompare(a.decided_ts));
  return (
    <div className="grid grid-cols-1 items-start gap-5 lg:grid-cols-2">
      <Section title="Decisions on proposals" sub="Every one is also in the hash-chained audit log">
        <ol className="space-y-3 text-sm">
          {decided.map((p) => (
            <li key={p.id} className={clsx("border-l-2 pl-3", p.status === "applied" ? "border-approve" : p.status === "rolled_back" ? "border-reject" : "border-line-2")}>
              <div className="mono text-[11.5px] text-dim">{p.decided_ts.replace("T", " ").slice(0, 16)} · {p.decided_by.replace("analyst:", "")} · {p.status.replace("_", " ")}</div>
              <div>{p.title}</div>
            </li>
          ))}
          {!decided.length && <li className="text-dim">No proposal has been decided yet.</li>}
        </ol>
      </Section>
      <Section title="Learning cycles">
        {cycles == null ? <div className="h-40 animate-pulse rounded-xl bg-bg-2" /> : (
          <ol className="space-y-3 text-sm">
            {cycles.map((c) => (
              <li key={c.id} className="flex items-start justify-between gap-3 border-b border-line/70 pb-3 last:border-0">
                <div>
                  <div className="mono text-[11.5px] text-dim">{c.id} · {c.trigger} · {c.duration_ms} ms</div>
                  <div className="mt-0.5">{c.proposals} proposal{c.proposals === 1 ? "" : "s"} from {c.labels} labels{c.summary?.drift_alerts ? `, ${c.summary.drift_alerts} drift alerts` : ""}</div>
                </div>
                <span className="shrink-0 text-xs text-dim">{when(c.ts)}</span>
              </li>
            ))}
            {!cycles.length && <li className="text-dim">No cycle has run yet.</li>}
          </ol>
        )}
      </Section>
    </div>
  );
}
