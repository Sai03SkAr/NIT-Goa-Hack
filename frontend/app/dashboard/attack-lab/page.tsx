"use client";
import { useEffect, useMemo, useState } from "react";
import clsx from "clsx";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Crosshair, Play, ShieldCheck, Swords } from "lucide-react";
import { Section, Stat, pct, Finding } from "@/components/ui";
import { type AppRow, fileUrl, get, post } from "@/lib/api";
import { AXIS, BRAND, BRAND_2, GRID, MUTED, REJECT, REVIEW, TOOLTIP } from "@/lib/theme";


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
        <h1 className="display text-[32px] leading-[1.1]">Attack Lab</h1>
        <p className="mt-1 max-w-4xl text-sm text-muted">We attack our own system. Each attack perturbs real test cases, re-runs the real document and biometric extraction, and re-scores with the trained fusion. Sample: {d.n_sample} test applications ({d.n_fraud} fraud).</p>
        {d.evaluation_kind && <p className="mt-1 max-w-4xl text-xs text-dim">Evaluation kind: {d.evaluation_kind}.</p>}
      </div>
      {adaptive && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <Stat label="Adaptive attacker, recall before" value={pct(adaptive.recall_before)} />
          <Stat label="Recall after greedy evasion" value={pct(adaptive.recall_after)} accent="var(--brand)" hint="attacker changes only what they control" />
          <Stat label="Controllable features" value={adaptive.controllable.length} hint="typing, email, device, IP, timing, links" />
          <Stat label="Can't be faked" value="face, history, crypto" accent="var(--approve)" hint="registry, SIM age, QR signature" />
        </div>
      )}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[300px_minmax(0,1fr)]">
        <div className="panel h-fit p-2">
          {attacks.map((a) => (
            <button key={a.id} onClick={() => setSel(a.id)} className={clsx("w-full rounded-lg px-3 py-2.5 text-left transition", sel === a.id ? "bg-brand-soft" : "hover:bg-bg-2")}>
              <div className="flex items-center gap-2 text-sm font-medium"><Swords className="size-3.5 text-reject" />{a.name}</div>
              <div className="mt-0.5 pl-5 text-[11px] text-dim">{a.target}</div>
            </button>
          ))}
        </div>
        <div className="space-y-6">
          <Section title={cur.name} right={<span className="chip whitespace-normal text-approve"><ShieldCheck className="size-3" />{cur.defense}</span>}>
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
          <Line dataKey="fused_auc" name="Fused ROC-AUC" stroke={BRAND_2} strokeWidth={2} dot />
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
  const [err, setErr] = useState("");
  useEffect(() => { get<AppRow[]>("/api/apps?band=APPROVE&source=seed&limit=40").then((r) => { setApps(r); setAppId(r[0]?.app_id ?? ""); }).catch(() => setApps([])); }, []);
  const levels = useMemo(() => atk.levels, [atk]);
  async function run() {
    setBusy(true); setRes(null); setErr("");
    try { setRes(await post("/api/attack/live", { app_id: appId, attack: atk.id, level: levels[lv] ?? 0 })); }
    catch (e) { setErr(`The attack could not run: ${e instanceof Error ? e.message : e}. It needs the card images and models on the server.`); }
    finally { setBusy(false); }
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
      {err && <p className="mt-3 text-sm text-reject">{err}</p>}
      {!apps.length && <p className="mt-3 text-sm text-dim">No approved seeded applications to attack yet. Seed the database first (scripts/build_all.sh).</p>}
      {res && (
        <div className="fade-up mt-5 grid gap-5 lg:grid-cols-2">
          {(["before", "after"] as const).map((k) => <AttackResult key={k} title={k === "before" ? "Clean card" : "Forged card"} r={res[k]} />)}
        </div>
      )}
    </Section>
  );
}

type Side = { image: string; risk: number; forensic: number; reasons: { code: string; text: string; weight: number }[]; ocr?: Record<string, string>;
  qr?: Record<string, string>; qr_valid?: boolean; trufor?: { score: number; heatmap: string } | null };

function AttackResult({ title, r }: { title: string; r: Side }) {
  const [view, setView] = useState<"card" | "trufor">("card");
  const found = r.reasons.filter((x) => x.weight > 0);
  const rows: [string, string | undefined, string | undefined][] = [
    ["Name", r.ocr?.name, r.qr?.n], ["Date of birth", r.ocr?.dob, r.qr?.d], ["ID number", r.ocr?.id_number, r.qr?.id],
  ];
  const same = (a?: string, b?: string) => !a || !b || a.replace(/\s/g, "").toUpperCase() === b.replace(/\s/g, "").toUpperCase();
  return (
    <div className="rounded-xl border border-line bg-panel p-4">
      <div className="flex items-center justify-between gap-3">
        <span className="font-medium">{title}</span>
        <span className={clsx("rounded-full px-2.5 py-0.5 text-xs font-medium", found.length ? "bg-reject/10 text-reject" : "bg-approve/10 text-approve")}>
          {found.length ? `${found.length} finding${found.length > 1 ? "s" : ""}` : "No findings"}
        </span>
      </div>
      <div className="mt-3 overflow-hidden rounded-lg border border-line">
        <img src={view === "trufor" && r.trufor ? fileUrl(r.trufor.heatmap) : r.image} alt={view === "trufor" ? `TruFor heatmap of the ${title.toLowerCase()}` : title}
          className="block w-full" />
      </div>
      <div className="mt-2 flex items-center justify-between gap-3">
        <div className="flex rounded-lg bg-bg-2 p-0.5 text-xs" role="tablist">
          {([["card", "Card"], ["trufor", "TruFor heatmap"]] as const).map(([v, l]) => (
            <button key={v} role="tab" aria-selected={view === v} disabled={v === "trufor" && !r.trufor} onClick={() => setView(v)}
              className={clsx("whitespace-nowrap rounded-md px-2.5 py-1 disabled:opacity-40", view === v ? "bg-panel font-medium shadow-sm" : "text-muted hover:text-fg")}>{l}</button>
          ))}
        </div>
        {r.trufor ? <span className="text-xs text-muted">TruFor score <span className="tabular-nums text-fg">{r.trufor.score.toFixed(2)}</span></span>
          : <span className="text-xs text-dim">TruFor not installed</span>}
      </div>
      {view === "trufor" && r.trufor && <p className="mt-1.5 text-xs text-dim">Red marks pixels TruFor believes were manipulated. Shown as evidence only; it never changes the decision.</p>}
      <dl className="mt-3 grid grid-cols-3 gap-3 text-xs">
        {[["Document risk", r.risk.toFixed(2)], ["Pixel forensics", r.forensic.toFixed(2)], ["Issuer signature", r.qr_valid ? "Valid" : "Missing or invalid"]].map(([k, v]) => (
          <div key={k}><dt className="text-dim">{k}</dt><dd className="mt-0.5 text-sm tabular-nums text-fg">{v}</dd></div>
        ))}
      </dl>
      <table className="mt-3 w-full text-xs">
        <thead><tr className="text-left text-dim"><th className="py-1 font-normal">Field</th><th className="font-normal">Printed on card</th><th className="font-normal">Signed in QR</th></tr></thead>
        <tbody className="tabular-nums">
          {rows.map(([k, printed, signed]) => (
            <tr key={k} className="border-t border-line/60">
              <td className="py-1.5 text-muted">{k}</td>
              <td className={same(printed, signed) ? "text-fg" : "font-medium text-reject"}>{printed || "unreadable"}</td>
              <td className="text-fg">{signed ?? "none"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {found.length > 0 && <ul className="mt-3 space-y-1.5 border-t border-line pt-3">{found.map((x) => <Finding key={x.code} text={x.text} code={x.code} weight={x.weight} />)}</ul>}
    </div>
  );
}
