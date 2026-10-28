"use client";
import { useEffect, useMemo, useState } from "react";
import clsx from "clsx";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Crosshair, Play, ShieldCheck, Swords } from "lucide-react";
import { Section, Stat, pct } from "@/components/ui";
import { type AppRow, get, post } from "@/lib/api";

const TT = { contentStyle: { background: "#0f172a", border: "1px solid #1e293b", borderRadius: 10, fontSize: 12 } };

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
          <Stat label="Adaptive attacker · recall before" value={pct(adaptive.recall_before)} />
          <Stat label="Recall after greedy evasion" value={pct(adaptive.recall_after)} accent="var(--brand)" hint="attacker changes only what they control" />
          <Stat label="Controllable features" value={adaptive.controllable.length} hint="typing, email, device, IP, timing, links" />
          <Stat label="Can't be faked" value="face · history · crypto" accent="var(--approve)" hint="registry, SIM age, QR signature" />
        </div>
      )}
      <div className="grid gap-6 lg:grid-cols-[300px_1fr]">
        <div className="panel h-fit p-2">
          {attacks.map((a) => (
            <button key={a.id} onClick={() => setSel(a.id)} className={clsx("w-full rounded-lg px-3 py-2.5 text-left transition", sel === a.id ? "bg-white/[0.06]" : "hover:bg-white/[0.03]")}>
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
          <CartesianGrid stroke="#1e293b" />
          <XAxis dataKey="level" stroke="#8b9ab3" fontSize={11} label={{ value: a.x, position: "insideBottom", offset: -2, fill: "#5b6a84", fontSize: 11 }} />
          <YAxis domain={[0, 1]} stroke="#5b6a84" fontSize={11} />
          <Tooltip {...TT} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line dataKey="fused_recall" name="Fused recall" stroke="#5eead4" strokeWidth={2.5} dot />
          <Line dataKey="fused_auc" name="Fused ROC-AUC" stroke="#22d3ee" strokeWidth={2} dot />
          <Line dataKey="doc_only_auc" name="Document module alone · AUC" stroke="#fbbf24" strokeDasharray="5 4" dot />
          <Line dataKey="pixel_only_auc" name="Pixel forensics alone · AUC" stroke="#fb7185" strokeDasharray="3 3" dot />
          <Line dataKey="fused_fpr" name="Fused FPR" stroke="#a78bfa" strokeWidth={1.5} dot />
        </LineChart>
      </ResponsiveContainer>
      <p className="mt-2 text-xs text-dim">Single pixel-level detectors degrade as image quality drops; the fused decision holds because QR signatures, registries, biometrics and the graph don't depend on pixels.</p>
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
          <td className="mono py-2.5 text-right">{typeof r.value === "number" ? (r.value <= 1 && !String(r.detector).startsWith("n ") ? pct(r.value) : r.value) : r.value ?? "—"}</td>
        </tr>))}
      </tbody>
    </table>
  );
}

function Adaptive({ a }: { a: any }) {
  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={a.per_type}>
        <CartesianGrid stroke="#1e293b" vertical={false} />
        <XAxis dataKey="type" stroke="#8b9ab3" fontSize={11} /><YAxis domain={[0, 1]} stroke="#5b6a84" fontSize={11} />
        <Tooltip {...TT} formatter={(v: any) => pct(v)} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar dataKey="before" name="Recall before attack" fill="#334155" radius={[4, 4, 0, 0]} />
        <Bar dataKey="after" name="Recall after adaptive attack" fill="#5eead4" radius={[4, 4, 0, 0]} />
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
          {apps.map((a) => <option key={a.app_id} value={a.app_id}>{a.app_id} · {a.name}</option>)}
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
                  <span className="mono">doc risk {res[k].risk.toFixed(2)} · pixel {res[k].forensic.toFixed(2)}</span></div>
                <div className="mt-2 flex flex-wrap gap-1">{res[k].reasons.length ? res[k].reasons.map((r: string) => <span key={r} className="chip mono text-[10px]">{r}</span>) : <span className="text-xs text-dim">no signals</span>}</div>
                <div className="mono mt-2 text-[11px] text-dim">printed DOB {res[k].ocr?.dob || "—"} · signed QR DOB {res[k].qr?.d ?? "—"} · QR {res[k].qr_valid ? "valid" : "invalid/missing"}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </Section>
  );
}
