"use client";
import { use, useEffect, useState } from "react";
import clsx from "clsx";
import { Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Bot, Check, FileSearch, Fingerprint, Network, ScanFace, Sparkles, X } from "lucide-react";
import { BandBadge, Finding, RiskBar, Section, SimBadge, TypeChip, featureLabel, readable, riskColor } from "@/components/ui";
import { IdentityGraph, type GLink, type GNode } from "@/components/Graph";
import { APPROVE, AXIS, MUTED, REJECT, TOOLTIP } from "@/lib/theme";
import { type CaseDetail, type EvidenceCheck, type ModuleResult, del, fileUrl, get, post } from "@/lib/api";

const ICON: Record<string, any> = { document: FileSearch, biometric: ScanFace, behavior: Bot, registry: Fingerprint, correlation: Network };

export default function CasePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [c, setC] = useState<CaseDetail | null>(null);
  const [g, setG] = useState<{ nodes: GNode[]; links: GLink[] } | null>(null);
  const [err, setErr] = useState("");
  const load = () => get<CaseDetail>(`/api/apps/${id}`).then(setC).catch((e) => setErr(String(e)));
  useEffect(() => { load(); get(`/api/graph?app_id=${id}&hops=2`).then(setG).catch(() => {}); }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (err) return <div className="panel p-6 text-reject">{err}</div>;
  if (!c) return <div className="text-muted">Loading case…</div>;
  const mod = (n: string) => c.modules.find((m) => m.module === n);
  const doc = mod("document"), bio = mod("biometric");

  return (
    <div className="space-y-6">
      <div className="panel flex flex-wrap items-center gap-6 p-6">
        <div>
          <div className="label">Application <span className="mono">{c.app_id}</span> ({c.source})</div>
          <h1 className="mt-1 text-2xl font-semibold">{c.name}</h1>
          <div className="mono mt-1 text-xs text-dim">ID ···· {c.id_last4} · {c.ts.replace("T", " ")}</div>
        </div>
        <div className="flex items-center gap-4">
          <BandBadge band={c.band} size="lg" />
          <div className="w-48"><div className="text-xs text-muted">Model fraud probability</div>
            {c.prob == null ? <div className="text-sm text-review">model unavailable</div>
              : <><div className="mono text-xl" style={{ color: riskColor(c.prob) }}>{c.prob.toFixed(3)}</div><RiskBar value={c.prob} /></>}
            {c.forced === "REJECT" && <div className="mt-1.5 text-xs text-muted">Rejected by an evidence rule, not the model</div>}
            {c.forced === "REVIEW" && <div className="mt-1.5 text-xs text-muted">Held: required evidence incomplete</div>}</div>
        </div>
        {c.band !== "APPROVE" && (
          <div className="min-w-[260px] flex-1 rounded-lg border border-line bg-bg-2 p-4">
            <div className="flex items-center gap-2"><TypeChip type={c.fraud_type} label={c.fraud_label} />{c.stepped_up && <span className="chip">stepped up</span>}</div>
            <div className="mt-2 text-sm"><span className="text-muted">Recommended action: </span>{c.action}</div>
            {!!c.rule_codes?.filter((r) => !r.startsWith("EV_")).length && <ul className="mt-3 space-y-1">
              {c.rule_codes.filter((r) => !r.startsWith("EV_")).map((r) => <Finding key={r} code={r} weight={0.5} text={c.rule_texts?.[r] ?? r} />)}</ul>}
          </div>
        )}
        {c.truth_type && <span className="chip ml-auto" title="Ground truth from the synthetic generator (seeded data only)">truth: {c.truth_type}</span>}
      </div>

      <EvidencePanel checks={c.evidence ?? []} policy={c.policy_version} />

      <div className="grid gap-4 md:grid-cols-5">
        {c.modules.map((m) => <ModuleCard key={m.module} m={m} />)}
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <DocumentPanel c={c} m={doc} />
        <FaceTrio c={c} m={bio} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Section title="Identity graph · 2 hops" right={<span className="text-xs text-dim">{g?.nodes.length ?? 0} linked applications</span>}>
          {g && g.nodes.length > 1 ? <IdentityGraph nodes={g.nodes} links={g.links} focus={c.app_id} height={340} /> :
            <div className="grid h-[340px] place-items-center rounded-xl border border-line text-sm text-dim">No strong links to other applications</div>}
        </Section>
        <ShapPanel shap={c.shap} />
      </div>

      <SessionContext c={c} />

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <Section title="Analyst summary" right={<span className="chip"><Sparkles className="size-3" />written only from the findings above</span>}>
          <p className="text-sm leading-relaxed text-fg">{readable(c.summary)}</p>
        </Section>
        <OverridePanel c={c} onDone={load} />
      </div>
    </div>
  );
}

const STATUS_STYLE: Record<string, string> = {
  PASS: "text-approve", FAIL: "text-reject", UNAVAILABLE: "text-review", NOT_PROVIDED: "text-review", SIMULATED: "text-sim",
};
const STATUS_TEXT: Record<string, string> = {
  PASS: "passed", FAIL: "failed", UNAVAILABLE: "could not check", NOT_PROVIDED: "not provided", SIMULATED: "simulated",
};

/** Every required check with its status: automatic approval needs all of them to pass. */
function EvidencePanel({ checks, policy }: { checks: EvidenceCheck[]; policy?: string }) {
  if (!checks.length) return null;
  const open = checks.filter((x) => x.required && x.status !== "PASS").length;
  return (
    <Section title="Required evidence" right={<span className="text-xs text-dim">{open ? `${open} check${open > 1 ? "s" : ""} not passed: no automatic approval` : "all required checks passed"}{policy && ` · ${policy}`}</span>}>
      <ul className="grid gap-x-8 gap-y-1.5 text-sm sm:grid-cols-2 lg:grid-cols-3">
        {checks.map((x) => (
          <li key={x.check} className="flex items-center justify-between gap-3 border-b border-line/60 py-1">
            <span className={x.required ? "text-fg" : "text-muted"}>{x.label}{x.source && x.source !== "server" && <span className="ml-1.5 text-[11px] text-dim">({x.source})</span>}</span>
            <span className={clsx("shrink-0 text-xs font-medium", STATUS_STYLE[x.status])}>{STATUS_TEXT[x.status]}</span>
          </li>
        ))}
      </ul>
    </Section>
  );
}

function ModuleCard({ m }: { m: ModuleResult }) {
  const I = ICON[m.module] ?? FileSearch;
  return (
    <div className="panel p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-semibold capitalize"><I className="size-4" style={{ color: riskColor(m.risk) }} />{m.module}</div>
        <span className="mono text-sm" style={{ color: riskColor(m.risk) }}>{m.risk.toFixed(2)}</span>
      </div>
      <RiskBar value={m.risk} className="mt-2" />
      <ul className="mt-3 space-y-1.5 [&_li]:text-xs">
        {m.reasons.length ? m.reasons.map((r) => <Finding key={r.code} text={r.text} code={r.code} weight={r.weight} />)
          : <li className="text-dim">Nothing unusual found.</li>}
      </ul>
    </div>
  );
}

function DocumentPanel({ c, m }: { c: CaseDetail; m?: ModuleResult }) {
  const [view, setView] = useState<"card" | "ela" | "trufor">("card");
  const [tf, setTf] = useState<{ score: number; heatmap: string } | { error: string } | null>(null);
  async function showTrufor() {
    setView("trufor");
    if (tf && !("error" in tf)) return;
    setTf(null);
    try { setTf(await get(`/api/apps/${c.app_id}/trufor`)); } catch (e) { setTf({ error: String(e).includes("503") ? "TruFor is not installed. Run ./scripts/setup_trufor.sh" : String(e) }); }
  }
  const ev = m?.evidence ?? {};
  const qr = ev.qr ?? {};
  const ocr = ev.ocr ?? {};
  const form = c.form_masked ?? {};
  const rows: [string, string | undefined, string | undefined, string | undefined][] = [
    ["Name", qr.n, ocr.name, form.name?.toUpperCase()],
    ["Date of birth", qr.d, ocr.dob, form.dob],
    ["ID (last 4)", qr.id?.slice(-4), ocr.id_number?.slice(-4), form.id_number?.slice(-4)],
    ["Issued", qr.i, ocr.issue_date, "n/a"],
  ];
  return (
    <Section title="Document evidence" right={
      <div className="flex items-center gap-2">
        <span className={clsx("chip", ev.qr_signature_valid ? "text-approve" : ev.qr_status === "INVALID_SIGNATURE" ? "text-reject" : "text-review")}>
          {ev.qr_signature_valid ? "QR signature valid" : ({ INVALID_SIGNATURE: "QR signature INVALID", UNTRUSTED_KEY: "QR signed by an unknown key",
            MALFORMED: "QR unreadable or malformed", NOT_FOUND: "No readable QR", NO_TRUSTED_KEYS: "No issuer key configured" } as Record<string, string>)[ev.qr_status] ?? "No readable QR"}</span>
        <div className="flex rounded-lg bg-bg-2 p-0.5 text-xs">
          {([["card", "Card"], ["ela", "ELA"], ["trufor", "TruFor"]] as const).map(([k, l]) => (
            <button key={k} onClick={() => (k === "trufor" ? showTrufor() : setView(k))}
              className={clsx("rounded-md px-2.5 py-1", view === k ? "bg-panel font-medium shadow-sm" : "text-muted hover:text-fg")}>{l}</button>
          ))}
        </div>
      </div>}>
      {view === "trufor" && !tf ? <div className="grid aspect-[1000/630] place-items-center rounded-lg border border-line bg-bg-2 text-sm text-muted">Running TruFor (first run loads the model, about 10 s)</div>
        : <img src={view === "ela" ? fileUrl(`/api/apps/${c.app_id}/ela.png`) : view === "trufor" && tf && !("error" in tf) ? fileUrl(tf.heatmap) : fileUrl(c.card_path)} alt="card" className="w-full rounded-lg border border-line" />}
      {view === "trufor" && tf && ("error" in tf
        ? <p className="mt-2 text-sm text-reject">{tf.error}</p>
        : <p className="mt-2 text-sm text-muted">TruFor (CVPR 2023) score <span className="mono font-medium text-fg">{tf.score.toFixed(3)}</span>. Red marks pixels it thinks were manipulated.
            It is shown as evidence only and never changes the decision: on our cards it also flags the genuinely pasted photo, and it misses edited text fields that the signed QR catches.</p>)}
      <table className="mt-4 w-full text-sm">
        <thead><tr className="text-left text-xs text-muted"><th className="py-1.5">Field</th><th>Signed QR</th><th>Printed (OCR)</th><th>Form</th></tr></thead>
        <tbody className="mono text-xs">
          {rows.map(([k, a, b, f]) => {
            const mismatch = a && b && a.replace(/\s/g, "") !== b.replace(/\s/g, "");
            return (
              <tr key={k} className="border-t border-line/60">
                <td className="py-1.5 font-sans text-muted">{k}</td><td>{a ?? "missing"}</td>
                <td className={mismatch ? "font-semibold text-reject" : ""}>{b || "unreadable"}</td><td>{f ?? "n/a"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {ev.forensics && (
        <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted">
          <span className="chip">pixel forensics {ev.forensics.score}</span>
          <span className="chip">texture ratio {ev.forensics.tex_ratio}</span>
          <span className="chip">font dev {ev.forensics.font_dev}</span>
        </div>
      )}
    </Section>
  );
}

function FaceTrio({ c, m }: { c: CaseDetail; m?: ModuleResult }) {
  const ev = m?.evidence ?? {};
  const thr = ev.threshold ?? 0.35;
  const sim = (x?: number | null) => (x == null || Number.isNaN(x) ? "n/a" : x.toFixed(2));
  const ok = (x?: number | null) => x != null && !Number.isNaN(x) && x >= thr;
  const live = ev.liveness ?? {};
  const d = live.detail ?? {};
  const cam: string[] = ev.camera ?? [];
  const virtual = !!m?.features?.bio_virtual_cam;
  return (
    <Section title="Biometrics" right={<span className="text-xs text-dim">ArcFace threshold {thr} (set at 0.1% false accepts)</span>}>
      <div className="grid grid-cols-3 gap-3">
        {[["Selfie", fileUrl(c.selfie_path)], ["Card portrait", null], ["Registry photo", fileUrl(ev.registry_face_url)]].map(([l, src], i) => (
          <div key={String(l)}>
            <div className="aspect-[4/5] overflow-hidden rounded-lg border border-line bg-bg-2">
              {i === 1 ? <div className="h-full w-full bg-cover" style={{ backgroundImage: `url(${fileUrl(c.card_path)})`, backgroundSize: "417%", backgroundPosition: "5.3% 36%" }} />
                : src ? <img src={String(src)} alt={String(l)} className="h-full w-full object-cover" /> : <div className="grid h-full place-items-center text-xs text-dim">not in registry</div>}
            </div>
            <div className="mt-1.5 text-center text-xs text-muted">{l}</div>
          </div>
        ))}
      </div>
      <div className="mt-4 space-y-2 text-sm">
        <Pair label="Selfie ↔ card" v={sim(ev.sim_card)} ok={ok(ev.sim_card)} />
        <Pair label="Selfie ↔ registry" v={sim(ev.sim_registry)} ok={ok(ev.sim_registry)} />
        <Pair label="Face reused under another name" v={String(ev.reuse?.diff_name ?? 0)} ok={!(ev.reuse?.diff_name > 0)} />
        <Pair label={`Liveness (${live.source === "synthetic fixture" ? "synthetic fixture" : "server-verified"})`}
          v={({ PASS: "passed", FAIL: "failed", NOT_PROVIDED: "not provided", UNAVAILABLE: "could not check" } as Record<string, string>)[live.status] ?? "n/a"} ok={live.status === "PASS"} />
        {d.turn_deltas && <Pair label="Head turns vs neutral" v={`${(d.sequence ?? []).join(", ").replaceAll("_", " ")}: ${d.turn_deltas.join(" / ")}`} ok={live.status === "PASS"} />}
        {d.sim_to_selfie && <Pair label="Frames match the selfie" v={d.sim_to_selfie.join(" / ")} ok={!live.codes?.includes("BIO_FRAMES_INCONSISTENT")} />}
        <Pair label="Camera (browser-reported)" v={cam.length ? cam.join(", ") : "not reported"} ok={!virtual && cam.length > 0} />
        <Pair label="Same picture seen before" v={String(m?.features?.bio_media_reuse ?? 0)} ok={!(Number(m?.features?.bio_media_reuse) > 0)} />
        <div className="flex items-center justify-between text-xs text-dim"><span>Voice step-up {c.step_up?.voice != null && `score ${c.step_up.voice}`} (never used in the decision)</span><SimBadge /></div>
      </div>
    </Section>
  );
}

function Pair({ label, v, ok }: { label: string; v: string; ok: boolean }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-muted">{label}</span>
      <span className={clsx("mono flex items-center gap-1.5 text-xs", ok ? "text-approve" : "text-reject")}>{ok ? <Check className="size-3.5" /> : <X className="size-3.5" />}{v}</span>
    </div>
  );
}

function ShapPanel({ shap }: { shap: CaseDetail["shap"] }) {
  const data = [...(shap ?? [])].reverse().map((s) => ({ name: `${featureLabel(s.feature)}${s.value != null ? ` = ${s.value}` : ""}`, v: s.shap }));
  return (
    <Section title="Why: SHAP top-5 drivers" right={<span className="text-xs text-dim">+ pushes toward fraud</span>}>
      {data.length ? (
        <ResponsiveContainer width="100%" height={340}>
          <BarChart data={data} layout="vertical" margin={{ left: 10, right: 20 }}>
            <XAxis type="number" {...AXIS} />
            <YAxis type="category" dataKey="name" width={230} {...AXIS} />
            <ReferenceLine x={0} stroke={MUTED} />
            <Tooltip {...TOOLTIP} formatter={(v: any) => Number(v).toFixed(3)} />
            <Bar dataKey="v" radius={3}>{data.map((d) => <Cell key={d.name} fill={d.v > 0 ? REJECT : APPROVE} />)}</Bar>
          </BarChart>
        </ResponsiveContainer>
      ) : <div className="text-sm text-dim">Model not trained yet.</div>}
    </Section>
  );
}

function OverridePanel({ c, onDone }: { c: CaseDetail; onDone: () => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  async function erase() {
    if (!confirm(`Permanently delete ${c.app_id}: the record, card and selfie images, and its graph link? This cannot be undone.`)) return;
    await del(`/api/apps/${c.app_id}`);
    window.location.href = "/dashboard";
  }
  async function act(status: string) {
    setBusy(true);
    setMsg("");
    try {
      const r = await post<{ pending_second_approval?: boolean }>(`/api/apps/${c.app_id}/override`, { status, note });
      setNote(""); onDone();
      if (r.pending_second_approval) setMsg("Recorded. Approving a case the system rejected needs a second analyst to confirm.");
    } catch (e) { setMsg(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  }
  return (
    <Section title="Analyst decision & audit log" right={<span className="chip capitalize">{c.status}</span>}>
      <textarea className="input h-20 resize-none text-sm" placeholder="Reason for your decision (kept in the audit log)" value={note} onChange={(e) => setNote(e.target.value)} />
      <div className="mt-3 flex gap-2">
        <button className="btn flex-1" disabled={busy || !note} onClick={() => act("approved")}><Check className="size-4 text-approve" />Approve</button>
        <button className="btn btn-danger flex-1" disabled={busy || !note} onClick={() => act("rejected")}><X className="size-4" />Reject</button>
      </div>
      {msg && <p className="mt-2 text-xs text-review">{msg}</p>}
      <p className="mt-2 text-xs text-dim">Your decision is recorded next to the automated one, which is never changed. Going against it needs a reason of at least 20 characters.</p>
      <ol className="mt-4 max-h-44 space-y-2 overflow-auto text-xs">
        {c.audit.map((a, i) => (
          <li key={i} className="flex gap-3 border-l border-line-2 pl-3">
            <span className="mono text-dim">{a.ts.replace("T", " ").slice(0, 19)}</span>
            <span><span className="text-fg">{a.actor}</span> · {a.action}{a.note && <span className="text-muted">: {a.note}</span>}
              {a.hash && <span className="mono ml-1.5 text-[10px] text-dim" title="Hash-chained: editing any earlier entry breaks the chain">#{a.hash.slice(0, 8)}</span>}</span>
          </li>
        ))}
        {!c.audit.length && <li className="text-dim">Seeded case: no audit entries yet.</li>}
      </ol>
      <div className="mt-4 flex items-center justify-between border-t border-line pt-3 text-xs text-dim">
        <span>Uploaded images are deleted automatically after the retention period.</span>
        <button className="text-reject underline-offset-2 hover:underline" onClick={erase}>Erase applicant data</button>
      </div>
    </Section>
  );
}

function SessionContext({ c }: { c: CaseDetail }) {
  const x = c.context;
  if (!x) return null;
  const g = x.geo;
  const map = g ? "https://www.openstreetmap.org/?mlat=" + g.lat + "&mlon=" + g.lng + "#map=16/" + g.lat + "/" + g.lng : null;
  const geoText = g ? g.lat.toFixed(5) + ", " + g.lng.toFixed(5) + (g.accuracy != null ? " (±" + g.accuracy + " m)" : "") : "";
  return (
    <Section title="Session context" right={<span className="text-xs text-dim">captured per RBI V-CIP, recorded not scored</span>}>
      <dl className="grid gap-x-8 gap-y-3 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-dim">Geo-tag (GPS)</dt>
          <dd className="mt-0.5">
            {g ? <span>{geoText} {map ? <a href={map} target="_blank" className="text-brand hover:underline">map</a> : null}</span>
               : <span className="text-review">not provided</span>}
          </dd>
        </div>
        <div>
          <dt className="text-dim">Network (IP)</dt>
          <dd className="mt-0.5">{x.ip ? x.ip : <span className="text-dim">local / behind proxy (cannot geolocate)</span>}</dd>
        </div>
        <div>
          <dt className="text-dim">Consent</dt>
          <dd className="mt-0.5">{x.consent && x.consent.version ? "accepted (" + x.consent.version + ")" : <span className="text-dim">n/a</span>}</dd>
        </div>
      </dl>
    </Section>
  );
}
