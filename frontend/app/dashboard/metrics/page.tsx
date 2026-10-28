"use client";
import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Section, Stat, TYPE_COLORS, pct } from "@/components/ui";
import { get, post } from "@/lib/api";

const TT = { contentStyle: { background: "#0f172a", border: "1px solid #1e293b", borderRadius: 10, fontSize: 12 } };

export default function Metrics() {
  const [d, setD] = useState<any>(null);
  const [cfg, setCfg] = useState<any>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    get("/api/metrics").then(setD).catch((e) => setErr(String(e)));
    get("/api/config").then(setCfg).catch(() => {});
  }, []);
  if (err) return <div className="panel p-6 text-reject">{err}</div>;
  if (!d) return <div className="text-muted">Loading metrics…</div>;
  const m = d.metrics, abl = d.ablation as any[];
  const perType = Object.entries(m.per_type).filter(([t]) => t !== "genuine" && t !== "hard_negative")
    .map(([t, v]: any) => ({ type: t.replace("_", " "), key: t, recall: v.flag_rate, n: v.n }));
  const cm = m.confusion;
  const single = abl.filter((a) => a.setting.endsWith("only"));
  const loo = abl.filter((a) => a.setting.startsWith("all except"));
  const fused = abl.filter((a) => a.setting.startsWith("fused"));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Evaluation</h1>
        <p className="mt-1 max-w-4xl text-sm text-muted">{m.definition}. Time-based split (train days 0–15, calibrate 16–19, test 20–29), random JPEG/resize/noise on every class, hard negatives (families, hostels, transliteration, new-to-credit) in both train and test. We claim <span className="text-fg">relative</span> gains — see the ablation.</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label="Fraud detection rate" value={pct(m.recall_fdr)} hint="recall on fraud" accent="var(--brand)" />
        <Stat label="Precision" value={pct(m.precision)} />
        <Stat label="F1" value={m.f1.toFixed(3)} />
        <Stat label="False positive rate" value={pct(m.fpr, 2)} accent={m.fpr > 0.1 ? "var(--review)" : "var(--approve)"} />
        <Stat label="ROC-AUC" value={m.roc_auc.toFixed(3)} />
        <Stat label="PR-AUC" value={m.pr_auc.toFixed(3)} />
      </div>
      <div className="grid gap-4 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label="FDR @ top 3%" value={pct(m.fdr_at_top3pct)} hint="share of fraud in riskiest 3%" />
        <Stat label="FDR @ top 5%" value={pct(m.fdr_at_top5pct)} />
        <Stat label="Reject precision" value={pct(m.reject_precision)} />
        <Stat label="Reject recall" value={pct(m.reject_recall)} />
        <Stat label="Latency p50" value={`${Math.round(m.latency_ms.p50)} ms`} hint="CPU, all modules" />
        <Stat label="Latency p95" value={`${Math.round(m.latency_ms.p95)} ms`} />
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
        <Section title="Ablation: each module alone vs fused (ROC-AUC / recall)" right={<span className="text-xs text-dim">the proof of multi-source correlation</span>}>
          <ResponsiveContainer width="100%" height={330}>
            <BarChart data={[...single, ...fused].map((a) => ({ ...a, name: a.setting.replace(" only", "").replace("fused (all modules)", "fused").replace("fused + hard rules", "fused + rules") }))}>
              <CartesianGrid stroke="#1e293b" vertical={false} />
              <XAxis dataKey="name" stroke="#8b9ab3" fontSize={11} />
              <YAxis domain={[0, 1]} stroke="#5b6a84" fontSize={11} />
              <Tooltip {...TT} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="roc_auc" name="ROC-AUC" fill="#22d3ee" radius={[4, 4, 0, 0]} />
              <Bar dataKey="recall" name="Recall (FDR)" fill="#5eead4" radius={[4, 4, 0, 0]} />
              <Bar dataKey="fpr" name="FPR" fill="#fb7185" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Section>
        <Section title="Confusion matrix (flag = REVIEW or REJECT)">
          <div className="grid grid-cols-[auto_1fr_1fr] gap-2 text-center text-sm">
            <div /><div className="label">pred genuine</div><div className="label">pred fraud</div>
            <div className="label self-center">genuine</div><Cell2 v={cm.tn} good /><Cell2 v={cm.fp} />
            <div className="label self-center">fraud</div><Cell2 v={cm.fn} /><Cell2 v={cm.tp} good />
          </div>
          <div className="mt-5 label">Bands on test set</div>
          <div className="mt-2 flex gap-2">{Object.entries(m.band_counts).map(([b, n]: any) => <span key={b} className="chip">{b}: {n}</span>)}</div>
          {cfg && <BandsEditor cfg={cfg} />}
        </Section>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Section title="Recall per fraud type">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={perType}>
              <CartesianGrid stroke="#1e293b" vertical={false} />
              <XAxis dataKey="type" stroke="#8b9ab3" fontSize={11} /><YAxis domain={[0, 1]} stroke="#5b6a84" fontSize={11} />
              <Tooltip {...TT} formatter={(v: any) => pct(v)} />
              <Bar dataKey="recall" radius={[4, 4, 0, 0]}>{perType.map((p) => <Cell key={p.key} fill={TYPE_COLORS[p.key] ?? "#94a3b8"} />)}</Bar>
            </BarChart>
          </ResponsiveContainer>
        </Section>
        <Section title="Leave-one-module-out (ROC-AUC)">
          <table className="w-full text-sm">
            <thead><tr className="label text-left"><th className="py-1.5">Setting</th><th>ROC-AUC</th><th>PR-AUC</th><th>Recall</th><th>FPR</th></tr></thead>
            <tbody className="mono text-xs">
              {[...loo, ...fused].map((a) => (
                <tr key={a.setting} className="border-t border-line/60"><td className="py-1.5 font-sans">{a.setting}</td><td>{a.roc_auc}</td><td>{a.pr_auc}</td><td>{pct(a.recall)}</td><td>{pct(a.fpr)}</td></tr>
              ))}
            </tbody>
          </table>
        </Section>
      </div>

      {m.cost_curve && (
        <Section title={`Cost curve: choosing the APPROVE cut-off (missed fraud = ${m.cost_curve.fn_cost}× a false alarm)`}
          right={<span className="text-xs text-dim">chosen on the {m.cost_curve.chosen_on}; hard-rule cases always flagged</span>}>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={m.cost_curve.points}>
              <CartesianGrid stroke="#1e293b" />
              <XAxis dataKey="t" stroke="#8b9ab3" fontSize={11} />
              <YAxis stroke="#5b6a84" fontSize={11} />
              <Tooltip {...TT} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <ReferenceLine x={m.cost_curve.recommended_approve_below} stroke="#5eead4" strokeDasharray="4 4" />
              <Line dataKey="cost_cal" name="Cost · calibration split" stroke="#22d3ee" dot={false} strokeWidth={2} />
              <Line dataKey="cost_test" name="Cost · test split" stroke="#fbbf24" dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
          <p className="mt-2 text-xs text-dim">Recommended APPROVE cut-off {m.cost_curve.recommended_approve_below} (current {m.cost_curve.current_approve_below}); test cost {m.cost_curve.test_cost_recommended} vs {m.cost_curve.test_cost_current} at the current setting.</p>
        </Section>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Section title="Hard negatives: genuine people who look odd" right={<span className="text-xs text-dim">false-flag rate by subgroup</span>}>
          <div className="space-y-2">
            {Object.entries(m.hard_negative_false_flag_by_sub).map(([k, v]: any) => (
              <div key={k} className="flex items-center gap-3 text-sm"><span className="w-28 capitalize text-muted">{k}</span>
                <div className="h-2 flex-1 rounded-full bg-white/5"><div className="h-full rounded-full bg-review" style={{ width: `${v * 100}%` }} /></div>
                <span className="mono w-14 text-right text-xs">{pct(v)}</span></div>
            ))}
          </div>
          <p className="mt-4 text-xs text-dim">Families share address/phone; hostel students share an IP and have new SIMs; transliterated names differ from the registry. Specificity weighting, IP down-weighting and the family exception keep these low.</p>
        </Section>
        <Section title="Top model features · leakage check" right={<span className="chip text-approve">{m.leakage_check}</span>}>
          <div className="space-y-1.5">
            {m.top_features.slice(0, 10).map((f: any) => (
              <div key={f.feature} className="flex items-center gap-3 text-xs">
                <span className="mono w-52 truncate text-muted">{f.feature}</span>
                <div className="h-1.5 flex-1 rounded-full bg-white/5"><div className="h-full rounded-full bg-brand-2" style={{ width: `${(f.gain / m.top_features[0].gain) * 100}%` }} /></div>
                <span className="mono w-12 text-right text-dim">{f.gain.toFixed(1)}</span>
              </div>
            ))}
          </div>
        </Section>
      </div>
    </div>
  );
}

function Cell2({ v, good }: { v: number; good?: boolean }) {
  return <div className="rounded-xl border border-line-2 py-6 text-2xl font-semibold tabular-nums" style={{ color: good ? "var(--approve)" : "var(--reject)", background: good ? "rgba(52,211,153,.06)" : "rgba(251,113,133,.06)" }}>{v}</div>;
}

function BandsEditor({ cfg }: { cfg: any }) {
  const [b, setB] = useState(cfg.bands);
  const [saved, setSaved] = useState(false);
  return (
    <div className="mt-5 rounded-xl border border-line p-3">
      <div className="label">Decision bands (live pipeline)</div>
      <div className="mt-2 flex items-center gap-2 text-xs">
        APPROVE &lt; <input className="input w-20 py-1 text-xs" type="number" step="0.05" value={b.approve_below} onChange={(e) => setB({ ...b, approve_below: +e.target.value })} />
        ≤ REVIEW &lt; <input className="input w-20 py-1 text-xs" type="number" step="0.05" value={b.reject_at} onChange={(e) => setB({ ...b, reject_at: +e.target.value })} /> ≤ REJECT
        <button className="btn ml-auto py-1 text-xs" onClick={() => post("/api/config/bands", b).then(() => setSaved(true))}>{saved ? "Saved" : "Apply"}</button>
      </div>
    </div>
  );
}
