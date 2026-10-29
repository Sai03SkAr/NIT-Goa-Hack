"use client";
import clsx from "clsx";
import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AlertTriangle, ShieldCheck } from "lucide-react";
import { PageHeader, Section, Stat, TYPE_COLORS, featureLabel, pct } from "@/components/ui";
import { get, post } from "@/lib/api";
import { AXIS, BRAND, BRAND_2, GRID, MUTED, REJECT, REVIEW, TOOLTIP } from "@/lib/theme";

type View = "overview" | "patterns" | "checks" | "unseen" | "thresholds" | "method";
const VIEWS: [View, string][] = [["overview", "Overview"], ["patterns", "By fraud pattern"], ["checks", "What each check adds"], ["unseen", "Unseen fraud"], ["thresholds", "Thresholds"], ["method", "How it was measured"]];
const TYPE_NAME: Record<string, string> = { ring: "Synthetic ring", first_party: "First-party / Frankenstein", third_party: "Third-party fabricated",
  bot: "Bot / scripted", tampered: "Tampered document", injection: "Capture replay", mule: "Possible mule" };

export default function Metrics() {
  const [d, setD] = useState<any>(null);
  const [cfg, setCfg] = useState<any>(null);
  const [view, setView] = useState<View>("overview");
  const [err, setErr] = useState("");
  useEffect(() => {
    get("/api/metrics").then(setD).catch((e) => setErr(String(e)));
    get("/api/config").then(setCfg).catch(() => {});
  }, []);
  if (err) return <div className="panel p-6 text-reject">{err}</div>;
  if (!d) return <div className="space-y-4">{[60, 160, 360].map((h) => <div key={h} className="animate-pulse rounded-2xl bg-bg-2" style={{ height: h }} />)}</div>;
  const m = d.metrics, abl = d.ablation as any[];
  const perType = Object.entries(m.per_type).filter(([t]) => t !== "genuine" && t !== "hard_negative")
    .map(([t, v]: any) => ({ key: t, name: TYPE_NAME[t] ?? t.replace("_", " "), recall: v.flag_rate, n: v.n }))
    .sort((a, b) => b.recall - a.recall);
  const cm = m.confusion;
  const single = abl.filter((a) => a.setting.endsWith("only"));
  const loo = abl.filter((a) => a.setting.startsWith("all except"));
  const fused = abl.filter((a) => a.setting.startsWith("fused"));
  const caught = Math.round(m.recall_fdr * 100), flagged = Math.round(m.fpr * 100);

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Insights" title="Evaluation"
        right={d.provenance?.git_commit && <span className="mono text-xs text-dim">commit {d.provenance.git_commit} · {d.provenance.policy_version}</span>}>
        How well TrueID separates real applicants from synthetic ones, on held-out applications the model never trained on.
      </PageHeader>

      <section aria-label="Headline" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div className="flex flex-col justify-between gap-3 rounded-2xl bg-brand p-5 text-white sm:col-span-2">
          <div className="text-[13px] text-white/70">In one sentence</div>
          <p className="display text-[24px] leading-[1.25]">Catches {caught} of every 100 synthetic identities, while sending {flagged} in 100 genuine customers to a human check.</p>
          <div className="text-xs text-white/60">Genuine customers are never auto-rejected on the score alone: a flag means review, not refusal.</div>
        </div>
        <Stat icon={ShieldCheck} tone="approve" label="Fraud caught" value={pct(m.recall_fdr)} hint={m.ci95 ? `95% interval ${pct(m.ci95.recall_fdr[0], 0)}–${pct(m.ci95.recall_fdr[1], 0)}` : "recall on fraud"} />
        <Stat icon={AlertTriangle} tone="review" label="False alarms" value={pct(m.fpr, 1)} hint="genuine customers sent to review" />
      </section>

      <div className="tabs" role="tablist" aria-label="Evaluation views">
        {VIEWS.map(([k, l]) => <button key={k} role="tab" aria-selected={view === k} className="tab" onClick={() => setView(k)}>{l}</button>)}
      </div>

      {view === "overview" && <div className="grid gap-5 lg:grid-cols-[1fr_1fr]">
        <Section title="Outcomes on the test set" sub="What actually happened to each application (flag = review or reject)">
          <div className="grid grid-cols-[96px_1fr_1fr] gap-2 text-sm">
            <span /><span className="text-xs text-dim">Model let through</span><span className="text-xs text-dim">Model flagged</span>
            <span className="self-center text-xs text-dim">Really genuine</span><Outcome v={cm.tn} text="correctly let through" tone="approve" /><Outcome v={cm.fp} text="false alarms" tone="review" />
            <span className="self-center text-xs text-dim">Really fraud</span><Outcome v={cm.fn} text="missed" tone="reject" /><Outcome v={cm.tp} text="caught" tone="approve" />
          </div>
          <div className="mt-5 flex flex-wrap gap-2">{Object.entries(m.band_counts).map(([b, n]: any) => <span key={b} className="chip"><span className="mono">{n}</span> {b.toLowerCase()}</span>)}</div>
        </Section>
        <Section title="Every number" sub="Hover a term for what it means">
          <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {([
              ["Precision", pct(m.precision), "Of the flagged applications, how many were really fraud"],
              ["F1", m.f1.toFixed(3), "Balance of precision and recall"],
              ["ROC-AUC", m.roc_auc.toFixed(3), "Chance a random fraud scores above a random genuine applicant"],
              ["PR-AUC", m.pr_auc.toFixed(3), "Precision–recall trade-off across all cut-offs"],
              ["Fraud in riskiest 3%", pct(m.fdr_at_top3pct), "Share of all fraud found in the top 3% of scores"],
              ["Fraud in riskiest 5%", pct(m.fdr_at_top5pct), "Share of all fraud found in the top 5% of scores"],
              ["Reject precision", pct(m.reject_precision), "Of auto-rejected applications, how many were fraud"],
              ["Reject recall", pct(m.reject_recall), "Of all fraud, how much was auto-rejected"],
              ["Batch time p50 / p95", `${(m.latency_ms.p50 / 1000).toFixed(1)} / ${(m.latency_ms.p95 / 1000).toFixed(1)} s`, "5 parallel CPU workers, cold models; live is about 0.3 s warm"],
            ] as const).map(([k, v, t]) => (
              <div key={k} className="well px-3 py-2.5" title={t}><dt className="text-xs text-dim">{k}</dt><dd className="mono mt-0.5 text-[15px]">{v}</dd></div>
            ))}
          </dl>
        </Section>
      </div>}

      {view === "patterns" && <div className="grid gap-5 lg:grid-cols-[1.3fr_1fr]">
        <Section title="Fraud caught, by pattern" sub="Amber marks patterns below 90%, where the next model should improve">
          <div className="grid grid-cols-[minmax(130px,200px)_1fr_48px_56px] items-center gap-x-3 gap-y-3 text-[13.5px]">
            {perType.map((p) => {
              const col = p.recall >= 0.9 ? "var(--approve)" : "var(--review)";
              return [
                <span key={p.key + "l"} className="flex items-center gap-2"><span className="size-2 shrink-0 rounded-full" style={{ background: TYPE_COLORS[p.key] ?? MUTED }} />{p.name}</span>,
                <span key={p.key + "b"} className="h-3 rounded bg-bg-2"><span className="block h-full rounded" style={{ width: `${p.recall * 100}%`, background: col }} /></span>,
                <span key={p.key + "v"} className="mono text-right" style={{ color: col }}>{pct(p.recall, 0)}</span>,
                <span key={p.key + "n"} className="mono text-right text-xs text-dim">n={p.n}</span>,
              ];
            })}
          </div>
        </Section>
        <Section title="Genuine people who look odd" sub="False-flag rate for hard negatives, by subgroup">
          <div className="space-y-3">
            {Object.entries(m.hard_negative_false_flag_by_sub).map(([k, v]: any) => (
              <div key={k} className="flex items-center gap-3 text-sm"><span className="w-28 capitalize text-muted">{k.replaceAll("_", " ")}</span>
                <div className="h-2.5 flex-1 rounded bg-bg-2"><div className="h-full rounded bg-review" style={{ width: `${v * 100}%` }} /></div>
                <span className="mono w-14 text-right text-xs">{pct(v)}</span></div>
            ))}
          </div>
          <p className="mt-4 text-xs leading-relaxed text-dim">Families share address and phone; hostel students share an IP and have new SIMs; transliterated names differ from the registry. Specificity weighting, IP down-weighting and the family exception keep these low.</p>
        </Section>
      </div>}

      {view === "checks" && <>
        <Section title="Each check alone vs all of them together" sub="The case for multi-source correlation: no single check comes close to the fused model">
          <ResponsiveContainer width="100%" height={320}>
            <BarChart data={[...single, ...fused].map((a) => ({ ...a, name: a.setting.replace(" only", "").replace("fused (all modules)", "fused").replace("fused + evidence policy", "fused + policy") }))}>
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis dataKey="name" {...AXIS} />
              <YAxis domain={[0, 1]} {...AXIS} />
              <Tooltip {...TOOLTIP} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="roc_auc" name="ROC-AUC" fill={BRAND} radius={[3, 3, 0, 0]} />
              <Bar dataKey="recall" name="Fraud caught" fill={BRAND_2} radius={[3, 3, 0, 0]} />
              <Bar dataKey="fpr" name="False alarms" fill={REJECT} radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Section>
        <div className="grid gap-5 lg:grid-cols-2">
          <Section title="Leave one check out" sub="How much the model loses when one check is removed">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[420px] text-sm">
                <thead><tr className="text-left text-xs text-dim"><th className="py-1.5 font-medium">Setting</th><th className="font-medium">ROC-AUC</th><th className="font-medium">PR-AUC</th><th className="font-medium">Caught</th><th className="font-medium">False alarms</th></tr></thead>
                <tbody className="mono text-xs">
                  {[...loo, ...fused].map((a) => (
                    <tr key={a.setting} className={a.setting.startsWith("fused") ? "border-t border-line font-medium" : "border-t border-line/60"}>
                      <td className="py-2 font-sans">{a.setting}</td><td>{a.roc_auc}</td><td>{a.pr_auc}</td><td>{pct(a.recall)}</td><td>{pct(a.fpr)}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>
          <Section title="Features the model leans on" right={<span className="chip text-approve">{m.leakage_check}</span>}>
            <div className="space-y-2">
              {m.top_features.slice(0, 10).map((f: any) => (
                <div key={f.feature} className="flex items-center gap-3 text-[13px]">
                  <span className="w-52 truncate text-muted" title={f.feature}>{featureLabel(f.feature)}</span>
                  <div className="h-2 flex-1 rounded bg-bg-2"><div className="h-full rounded bg-brand" style={{ width: `${(f.gain / m.top_features[0].gain) * 100}%` }} /></div>
                  <span className="mono w-12 text-right text-xs text-dim">{f.gain.toFixed(1)}</span>
                </div>
              ))}
            </div>
          </Section>
        </div>
      </>}

      {view === "thresholds" && <div className="grid gap-5 lg:grid-cols-[1.6fr_1fr]">
        {m.cost_curve ? (
          <Section title="Choosing the approve cut-off" sub={`Total cost if a missed fraud costs ${m.cost_curve.fn_cost}× a false alarm; chosen on the ${m.cost_curve.chosen_on}`}>
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={m.cost_curve.points}>
                <CartesianGrid stroke={GRID} />
                <XAxis dataKey="t" {...AXIS} />
                <YAxis {...AXIS} />
                <Tooltip {...TOOLTIP} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <ReferenceLine x={m.cost_curve.recommended_approve_below} stroke={MUTED} strokeDasharray="4 4" />
                <Line dataKey="cost_cal" name="Cost, calibration split" stroke={BRAND} dot={false} strokeWidth={2} />
                <Line dataKey="cost_test" name="Cost, test split" stroke={REVIEW} dot={false} strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
            <p className="mt-2 text-xs text-dim">Recommended cut-off {m.cost_curve.recommended_approve_below} (current {m.cost_curve.current_approve_below}); test cost {m.cost_curve.test_cost_recommended} vs {m.cost_curve.test_cost_current} at the current setting. Cases held by an evidence rule are always flagged.</p>
          </Section>
        ) : <Section title="Choosing the approve cut-off"><p className="text-sm text-dim">No cost curve in this evaluation run.</p></Section>}
        {cfg ? <BandsEditor cfg={cfg} /> : <Section title="Decision bands"><p className="text-sm text-dim">Configuration not available.</p></Section>}
      </div>}

      {view === "unseen" && <Unseen m={m} fed={d.federated} />}

      {view === "method" && <Section title="How these numbers were made">
        <div className="max-w-3xl space-y-3 text-sm leading-relaxed text-muted">
          <p><span className="font-medium text-fg">What counts as a flag. </span>{m.definition}.</p>
          <p><span className="font-medium text-fg">Data. </span>{d.provenance?.evaluation_kind ?? "Synthetic population"}. Time-based split: train on days 0–15, calibrate on 16–19, test on 20–29. Random JPEG, resize and noise on every class. Hard negatives (families, hostels, transliterated names, new-to-credit) appear in both train and test.</p>
          <p><span className="font-medium text-fg">Which score. </span>ROC and PR-AUC are on the {m.ranking_metrics_on ?? "model probability"}; caught, false alarms and band counts are on the {m.decision_metrics_on ?? "policy bands"}.
            {m.held_by_evidence != null && <> {pct(m.held_by_evidence)} of all test cases had at least one required check not passed, so they could not be approved whatever the score.</>}</p>
          {m.ci95 && <p><span className="font-medium text-fg">Uncertainty. </span>95% bootstrap intervals: caught {pct(m.ci95.recall_fdr[0])}–{pct(m.ci95.recall_fdr[1])}, false alarms {pct(m.ci95.fpr[0], 2)}–{pct(m.ci95.fpr[1], 2)}, ROC-AUC {m.ci95.roc_auc[0].toFixed(3)}–{m.ci95.roc_auc[1].toFixed(3)}.</p>}
          <p><span className="font-medium text-fg">What we claim. </span>Relative gains: fusing the checks beats any single one (see “What each check adds”). Absolute numbers on synthetic data will be lower on real traffic.</p>
        </div>
      </Section>}
    </div>
  );
}

function Outcome({ v, text, tone }: { v: number; text: string; tone: "approve" | "review" | "reject" }) {
  const c = `var(--${tone})`;
  return (
    <div className="rounded-xl px-4 py-4" style={{ background: `color-mix(in srgb, ${c} 8%, var(--panel))` }}>
      <div className="display text-[28px] leading-none tabular-nums" style={{ color: c }}>{v}</div>
      <div className="mt-1 text-[13px] text-muted">{text}</div>
    </div>
  );
}

function BandsEditor({ cfg }: { cfg: any }) {
  const [b, setB] = useState(cfg.bands);
  const [saved, setSaved] = useState(false);
  return (
    <Section title="Decision bands" sub="Applied to the live pipeline straight away">
      <div className="flex h-3 overflow-hidden rounded-full" aria-hidden>
        <span style={{ width: `${b.approve_below * 100}%`, background: "var(--approve)" }} />
        <span style={{ width: `${(b.reject_at - b.approve_below) * 100}%`, background: "var(--review)" }} />
        <span className="flex-1" style={{ background: "var(--reject)" }} />
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <label><span className="label">Approve below</span>
          <input className="input mono mt-1" type="number" step="0.05" min={0} max={1} value={b.approve_below} onChange={(e) => { setSaved(false); setB({ ...b, approve_below: +e.target.value }); }} /></label>
        <label><span className="label">Reject at or above</span>
          <input className="input mono mt-1" type="number" step="0.05" min={0} max={1} value={b.reject_at} onChange={(e) => { setSaved(false); setB({ ...b, reject_at: +e.target.value }); }} /></label>
      </div>
      <p className="mt-3 text-xs text-dim">Between the two, cases go to review. Evidence rules still hold or reject a case whatever its score.</p>
      <button className="btn btn-primary mt-4 w-full" onClick={() => post("/api/config/bands", b).then(() => setSaved(true))}>{saved ? "Saved" : "Apply"}</button>
    </Section>
  );
}

/** Zero-day fraud, the label-free genuine profile and its federated version (docs/IDRBT_INNOVATION.md). */
function Unseen({ m, fed }: { m: any; fed: any }) {
  const zd: any[] = m.zero_day ?? [], gp = m.genuine_profile;
  const cell = (v: number) => <span className={clsx("mono", v >= 0.9 ? "text-approve" : v >= 0.5 ? "text-review" : "text-reject")}>{pct(v, 0)}</span>;
  return (
    <div className="space-y-5">
      <Section title="Fraud the model has never seen" sub="Retrain without one fraud type, then test on that type">
        {zd.length ? <>
          <div className="grid grid-cols-[minmax(130px,1.2fr)_repeat(3,minmax(80px,1fr))] gap-x-4 gap-y-2 text-sm">
            <span className="text-xs text-dim">Unseen type</span><span className="text-xs text-dim">Model alone</span>
            <span className="text-xs text-dim">Genuine profile alone</span><span className="text-xs text-dim">Live system</span>
            {zd.map((r) => [<span key={r.type}>{TYPE_NAME[r.type] ?? r.type} <span className="text-xs text-dim">({r.n_test})</span></span>,
              <span key={r.type + "m"}>{cell(r.model_only)}</span>, <span key={r.type + "p"}>{cell(r.profile_only)}</span>, <span key={r.type + "l"}>{cell(r.live_system)}</span>])}
          </div>
          <p className="mt-3 max-w-3xl text-xs text-dim">A trained model only knows fraud it was shown. The genuine profile never saw any fraud, and the evidence policy checks facts
            an attacker can't fake: three layers that cover each other's blind spots.</p>
        </> : <p className="text-sm text-dim">Run the build to compute this table.</p>}
      </Section>
      <div className="grid gap-5 lg:grid-cols-2">
        <Section title="Genuine profile" sub="Explainable one-class rules, after IDRBT (COMSNETS 2025)">
          {gp ? <div className="space-y-2 text-sm">
            <p>Learnt from {gp.trained_on}.</p>
            <p>ROC-AUC <span className="mono">{gp.roc_auc_no_fraud_labels.toFixed(3)}</span> · outside the profile: <span className="mono text-reject">{pct(gp.fraud_outside, 0)}</span> of fraud,
              <span className="mono text-review"> {pct(gp.genuine_outside, 1)}</span> of genuine.</p>
            <p className="text-xs text-dim">Works for a bank with no labelled fraud yet. Shown on every case as readable rules; it never decides,
              because as a gate it held more genuine people without catching more fraud.</p>
          </div> : <p className="text-sm text-dim">Not trained yet.</p>}
        </Section>
        <Section title="Banks learning together" sub="One-shot federation, after IDRBT's FedPNN">
          {fed?.rows ? <>
            <ul className="divide-y divide-line text-[13.5px]">
              {fed.rows.map((r: any) => (
                <li key={r.setting} className="flex items-baseline justify-between gap-3 py-2">
                  <span className="leading-snug">{r.setting}</span>
                  <span className="mono shrink-0 text-xs">AUC {r.roc_auc.toFixed(3)} · fraud {pct(r.fraud_outside, 0)}</span>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-xs text-dim">Each bank shares only cluster summaries, never a customer row. {fed.note}</p>
          </> : <p className="text-sm text-dim">Run eval/federated_profile.py to compute this.</p>}
        </Section>
      </div>
    </div>
  );
}
