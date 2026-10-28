"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { get } from "@/lib/api";

type Abl = { setting: string; roc_auc: number; recall: number; fpr: number };

/** Live numbers from the last evaluation run (precomputed/metrics.json), so the landing page never shows made-up figures. */
export function Evidence() {
  const [d, setD] = useState<{ metrics: any; ablation?: Abl[]; provenance?: any } | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => { get("/api/metrics").then(setD).catch(() => setFailed(true)); }, []);

  if (failed) return <p className="mt-8 text-sm text-dim">Evaluation results appear here once the backend is running.</p>;
  if (!d) return <div className="mt-8 h-40 animate-pulse rounded-xl bg-bg-2" />;

  const m = d.metrics;
  const abl = d.ablation ?? [];
  const single = abl.filter((a) => a.setting.endsWith(" only"));
  const fused = abl.find((a) => a.setting === "fused (all modules)");
  const max = Math.max(...abl.map((a) => a.roc_auc), 0.001);
  const ci = (k: string) => (m.ci95?.[k] ? ` (95% CI ${(m.ci95[k][0] * (k === "roc_auc" ? 1 : 100)).toFixed(k === "roc_auc" ? 3 : 0)}–${(m.ci95[k][1] * (k === "roc_auc" ? 1 : 100)).toFixed(k === "roc_auc" ? 3 : 0)})` : "");
  const rows = [...single, ...(fused ? [fused] : [])];

  return (
    <div className="mt-10 grid gap-10 lg:grid-cols-[1fr_1.4fr]">
      <dl className="grid grid-cols-2 gap-x-8 gap-y-6 self-start">
        {[["Fraud held or rejected", `${(m.recall_fdr * 100).toFixed(0)}%`, ci("recall_fdr")], ["Genuine users held", `${(m.fpr * 100).toFixed(1)}%`, ci("fpr")],
          ["ROC-AUC (model)", m.roc_auc.toFixed(3), ci("roc_auc")], ["Precision of flags", `${(m.precision * 100).toFixed(0)}%`, ""]].map(([k, v, c]) => (
          <div key={k}>
            <dt className="text-sm text-muted">{k}</dt>
            <dd className="mt-1 text-3xl font-semibold tabular-nums tracking-tight">{v}</dd>
            {c && <dd className="mt-0.5 text-[11px] text-dim">{c.trim()}</dd>}
          </div>
        ))}
        <p className="col-span-2 text-sm text-dim">
          {m.n_test} synthetic test applications, {m.n_fraud} of them fraudulent, scored on later days than the model was trained on.
          {d.provenance?.evaluation_kind && <> Liveness in these rows is generator-labelled, not a live camera.</>}{" "}
          <Link href="/dashboard/metrics" className="text-brand underline-offset-2 hover:underline">Full evaluation</Link>
        </p>
      </dl>
      {rows.length > 0 && <div>
        <div className="text-sm font-medium">ROC-AUC by source: each one alone, then combined</div>
        <ul className="mt-4 space-y-2.5">
          {rows.map((a) => {
            const isFused = a === fused;
            return (
              <li key={a.setting} className="grid grid-cols-[120px_1fr_52px] items-center gap-3 text-sm">
                <span className={isFused ? "font-semibold" : "text-muted"}>{isFused ? "Combined" : a.setting.replace(" only", "").replace(/^\w/, (c) => c.toUpperCase())}</span>
                <span className="h-2 rounded-sm" style={{ width: `${(a.roc_auc / max) * 100}%`, background: isFused ? "var(--brand)" : "#c3cad6" }} />
                <span className="mono text-right tabular-nums">{a.roc_auc.toFixed(3)}</span>
              </li>
            );
          })}
        </ul>
      </div>}
    </div>
  );
}
