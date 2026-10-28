"use client";
import { useEffect, useMemo, useState } from "react";
import clsx from "clsx";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Crosshair, Play, ShieldCheck, Swords } from "lucide-react";
import { Section, Stat, pct } from "@/components/ui";
import { type AppRow, fileUrl, get, post } from "@/lib/api";
import { AXIS, BRAND, GRID, MUTED, REJECT, REVIEW, TOOLTIP } from "@/lib/theme";


export default function AttackLab() {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState("");
  const [sel, setSel] = useState<string>("jpeg");
  useEffect(() => { get("/api/attacks").then(setD).catch((e) => setErr(String(e))); }, []);
  if (err) return <div className="panel p-6 text-sm text-muted">Attack results not computed yet. Run <span className="mono text-fg">python eval/run_attacks.py</span>. ({err})</div>;
  if (!d) return <div className="text-muted">Loading attack results…</div>;
  const attacks: any[] = d.attacks;
  const cur = attacks.find((a) => a.id === sel) ?? attacks[0];
  const adaptive = attacks.find((a) => a.kind === "adaptive");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Attack Lab</h1>
        <p className="mt-1 max-w-4xl text-sm text-muted">We attack our own system. Each attack perturbs real test cases, re-runs the real document and biometric extraction, and re-scores with the trained fusion. Sample: {d.n_sample} test applications ({d.n_fraud} fraud).</p>
      </div>
      {adaptive && (
        <div className="grid gap-4 md:grid-cols-4">
          <Stat label="Adaptive attacker, recall before" value={pct(adaptive.recall_before)} />
          <Stat label="Recall after greedy evasion" value={pct(adaptive.recall_after)} accent="var(--brand)" hint="attacker changes only what they control" />
          <Stat label="Controllable features" value={adaptive.controllable.length} hint="typing, email, device, IP, timing, links" />
          <Stat label="Can't be faked" value="face, history, crypto" accent="var(--approve)" hint="registry, SIM age, QR signature" />
        </div>
      )}
      <div className="grid gap-6 lg:grid-cols-[300px_1fr]">
        <div className="panel h-fit p-2">
          {attacks.map((a) => (
            <button key={a.id} onClick={() => setSel(a.id)} className={clsx("w-full rounded-lg px-3 py-2.5 text-left transition", sel === a.id ? "bg-brand-soft" : "hover:bg-bg-2")}>
              <div className="flex items-center gap-2 text-sm font-medium"><Swords className="size-3.5 text-reject" />{a.name}</div>
              <div className="mt-0.5 pl-5 text-[11px] text-dim">{a.target}</div>
            </button>
          ))}
        </div>
        <div className="space-y-6">
          <Section title={cur.name} right={<span className="chip text-approve"><ShieldCheck className="size-3" />{cur.defense}</span>}>
            {cur.kind === "sweep" && <Sweep a={cur} />}
            {cur.kind === "single" && <SingleTable a={cur} />}
            {cur.kind === "adaptive" && <Adaptive a={cur} />}
          </Section>
          <LiveAttack />
        </div>
      </div>
    </div>
  );
}

function Sweep({ a }: { a: any }) {
  return (
    <>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={a.points}>
          <CartesianGrid stroke={GRID} />
          <XAxis dataKey="level" {...AXIS} label={{ value: a.x, position: "insideBottom", offset: -2, fill: MUTED, fontSize: 11 }} />
          <YAxis domain={[0, 1]} {...AXIS} />
          <Tooltip {...TOOLTIP} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line dataKey="fused_recall" name="Fused recall" stroke={BRAND} strokeWidth={2.5} dot />
          <Line dataKey="fused_auc" name="Fused ROC-AUC" stroke="#8fa2d8" strokeWidth={2} dot />
          <Line dataKey="doc_only_auc" name="Document module alone, AUC" stroke={REVIEW} strokeDasharray="5 4" dot />
          <Line dataKey="pixel_only_auc" name="Pixel forensics alone, AUC" stroke={REJECT} strokeDasharray="3 3" dot />
          <Line dataKey="fused_fpr" name="Genuine flagged (review or reject)" stroke={MUTED} strokeWidth={1.5} dot />
          <Line dataKey="genuine_rejected" name="Genuine rejected" stroke={REJECT} strokeWidth={2} dot />
          <Line dataKey="fraud_approved" name="Fraud approved" stroke="#8a6a00" strokeWidth={2} dot />
        </LineChart>
      </ResponsiveContainer>
      <p className="mt-2 text-xs text-dim">Single pixel-level detectors degrade as image quality drops. The fused decision holds because signed QRs, registries and the graph don't depend on pixels; when photos are too poor to judge, people are asked to retake (review) rather than rejected.</p>
    </>
  );
}

function SingleTable({ a }: { a: any }) {
  return (
    <table className="w-full text-sm">
      <thead><tr className="label text-left"><th className="py-2">Detector / measurement</th><th className="text-right">Result</th></tr></thead>
      <tbody>{a.rows.map((r: any) => (
        <tr key={r.detector} className="border-t border-line/60">
          <td className="py-2.5 text-muted">{r.detector}</td>
          <td className="mono py-2.5 text-right">{typeof r.value === "number" ? (r.value <= 1 && !String(r.detector).startsWith("n ") ? pct(r.value) : r.value) : r.value ?? "-"}</td>
        </tr>))}
      </tbody>
    </table>
  );
}

function Adaptive({ a }: { a: any }) {
  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={a.per_type}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="type" {...AXIS} /><YAxis domain={[0, 1]} {...AXIS} />
        <Tooltip {...TOOLTIP} formatter={(v: any) => pct(v)} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar dataKey="before" name="Recall before attack" fill="#c3cad6" radius={[3, 3, 0, 0]} />
        <Bar dataKey="after" name="Recall after adaptive attack" fill={BRAND} radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

const LIVE = [
  { id: "poisson_dob", label: "Poisson DOB edit (hero)", levels: [0] },
  { id: "jpeg", label: "JPEG quality", levels: [60, 40, 25] },
  { id: "noise", label: "Gaussian noise", levels: [10, 20, 35] },
  { id: "recapture", label: "Screen recapture", levels: [0.5, 1, 1.5] },
];

function LiveAttack() {
  const [apps, setApps] = useState<AppRow[]>([]);
  const [appId, setAppId] = useState("");
  const [atk, setAtk] = useState(LIVE[0]);
  const [lv, setLv] = useState(0);
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { get<AppRow[]>("/api/apps?band=APPROVE&source=seed&limit=40").then((r) => { setApps(r); setAppId(r[0]?.app_id ?? ""); }); }, []);
  const levels = useMemo(() => atk.levels, [atk]);
  async function run() {
    setBusy(true); setRes(null);
    try { setRes(await post("/api/attack/live", { app_id: appId, attack: atk.id, level: levels[lv] ?? 0 })); } finally { setBusy(false); }
  }
  return (
    <Section title="Run one attack live" right={<span className="chip"><Crosshair className="size-3" />on a genuine, approved card</span>}>
      <div className="flex flex-wrap items-center gap-3">
        <select className="input w-56 py-1.5 text-sm" value={appId} onChange={(e) => setAppId(e.target.value)}>
          {apps.map((a) => <option key={a.app_id} value={a.app_id}>{a.app_id}, {a.name}</option>)}
        </select>
        <select className="input w-56 py-1.5 text-sm" value={atk.id} onChange={(e) => { setAtk(LIVE.find((x) => x.id === e.target.value)!); setLv(0); }}>
          {LIVE.map((l) => <option key={l.id} value={l.id}>{l.label}</option>)}
        </select>
        {levels.length > 1 && <div className="flex items-center gap-2 text-xs"><span className="label">strength</span>
          <input type="range" min={0} max={levels.length - 1} value={lv} onChange={(e) => setLv(+e.target.value)} /><span className="mono">{levels[lv]}</span></div>}
        <button className="btn btn-primary ml-auto" disabled={busy || !appId} onClick={run}><Play className="size-4" />{busy ? "Attacking…" : "Run attack"}</button>
      </div>
      {res && (
        <div className="fade-up mt-5 grid gap-5 lg:grid-cols-[1.2fr_1fr]">
          <img src={res.image} alt="attacked card" className="rounded-lg border border-line" />
          <div className="space-y-3 text-sm">
            {(["before", "after"] as const).map((k) => (
              <div key={k} className="rounded-xl border border-line-2 p-3">
                <div className="flex items-center justify-between"><span className="label">{k === "before" ? "Clean card" : "Attacked card"}</span>
                  <span className="mono">doc risk {res[k].risk.toFixed(2)}, pixel {res[k].forensic.toFixed(2)}</span></div>
                <div className="mt-2 flex flex-wrap gap-1">{res[k].reasons.length ? res[k].reasons.map((r: string) => <span key={r} className="chip mono text-[10px]">{r}</span>) : <span className="text-xs text-dim">no signals</span>}</div>
                <div className="mono mt-2 text-[11px] text-dim">printed DOB {res[k].ocr?.dob || "-"}, signed QR DOB {res[k].qr?.d ?? "-"}, QR {res[k].qr_valid ? "valid" : "invalid/missing"}</div>
                {res[k].trufor && <div className="mt-1 text-xs text-muted">TruFor score <span className="mono text-fg">{res[k].trufor.score.toFixed(3)}</span>{" "}
                  <a href={fileUrl(res[k].trufor.heatmap)} target="_blank" className="text-brand hover:underline">heatmap</a></div>}
              </div>
            ))}
          </div>
        </div>
      )}
    </Section>
  );
}
