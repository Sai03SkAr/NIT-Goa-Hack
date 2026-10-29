"use client";
import { use, useEffect, useState } from "react";
import Link from "next/link";
import clsx from "clsx";
import { AlertTriangle, Bot, Building2, Check, ChevronRight, FileSearch, Fingerprint, Minus, Network, ScanFace, Sparkles, X } from "lucide-react";
import { Avatar, Finding, RiskRing, Section, SimBadge, Stamp, TypeChip, featureLabel, readable, riskColor, when } from "@/components/ui";
import { IdentityGraph, type GLink, type GNode } from "@/components/Graph";
import { type CaseDetail, type EvidenceCheck, type ModuleResult, del, fileUrl, get, post } from "@/lib/api";

type Tab = "overview" | "document" | "face" | "linked" | "session";
const TABS: [Tab, string][] = [["overview", "Overview"], ["document", "Document"], ["face", "Face & liveness"], ["linked", "Linked applications"], ["session", "Session"]];

/** Each module as a dial in the signal strip, and the tab that holds its detail. */
const MOD: Record<string, { label: string; tab: Tab; icon: any }> = {
  document: { label: "Document", tab: "document", icon: FileSearch },
  biometric: { label: "Face", tab: "face", icon: ScanFace },
  behavior: { label: "Behaviour", tab: "session", icon: Bot },
  registry: { label: "Registry", tab: "overview", icon: Fingerprint },
  correlation: { label: "Linked apps", tab: "linked", icon: Network },
  network: { label: "Other banks", tab: "linked", icon: Building2 },
};

export default function CasePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [c, setC] = useState<CaseDetail | null>(null);
  const [g, setG] = useState<{ nodes: GNode[]; links: GLink[] } | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [err, setErr] = useState("");
  const load = () => get<CaseDetail>(`/api/apps/${id}`).then(setC).catch((e) => setErr(String(e)));
  useEffect(() => { load(); get(`/api/graph?app_id=${id}&hops=2`).then(setG).catch(() => {}); }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (err) return <div className="panel p-6 text-reject">{err}</div>;
  if (!c) return <div className="space-y-4">{[120, 96, 420].map((h) => <div key={h} className="animate-pulse rounded-2xl bg-bg-2" style={{ height: h }} />)}</div>;
  const mod = (n: string) => c.modules.find((m) => m.module === n);
  const linked = g ? Math.max(0, g.nodes.length - 1) : 0;

  return (
    <div className="space-y-5">
      <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-[13px] text-dim">
        <Link href="/dashboard" className="hover:text-fg">Review queue</Link><ChevronRight className="size-3.5" /><span className="mono text-fg">{c.app_id}</span>
      </nav>

      <Verdict c={c} />
      <SignalStrip modules={c.modules} onOpen={setTab} />

      <div className="grid grid-cols-1 items-start gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0 space-y-5">
          <div className="tabs" role="tablist" aria-label="Case sections">
            {TABS.map(([k, l]) => (
              <button key={k} role="tab" aria-selected={tab === k} className="tab" onClick={() => setTab(k)}>
                {l}{k === "linked" && linked > 0 && <span className={clsx("mono text-xs", tab === k ? "text-white/70" : "text-reject")}>{linked}</span>}
              </button>
            ))}
          </div>

          {tab === "overview" && <>
            <Consistency c={c} />
            <EvidencePanel checks={c.evidence ?? []} policy={c.policy_version} />
            <ShapPanel shap={c.shap} />
            <Section title="All findings" sub="Grouped by the check that raised them">
              <div className="grid gap-x-8 gap-y-4 sm:grid-cols-2">
                {c.modules.map((m) => (
                  <div key={m.module}>
                    <div className="mb-1.5 text-[13px] font-medium">{MOD[m.module]?.label ?? m.module}</div>
                    <ul className="space-y-1.5">{m.reasons.length ? m.reasons.map((r) => <Finding key={r.code} text={r.text} code={r.code} weight={r.weight} />)
                      : <li className="text-sm text-dim">Nothing unusual.</li>}</ul>
                  </div>
                ))}
              </div>
            </Section>
          </>}
          {tab === "document" && <DocumentPanel c={c} m={mod("document")} />}
          {tab === "face" && <FaceTrio c={c} m={mod("biometric")} />}
          {tab === "linked" && <>
            <Section title="Identity graph" sub="Applications within two links of this one" right={<span className="text-xs text-dim">{linked} linked application{linked === 1 ? "" : "s"}</span>}>
              {g && g.nodes.length > 1 ? <IdentityGraph nodes={g.nodes} links={g.links} focus={c.app_id} height={440} /> :
                <div className="grid h-[240px] place-items-center rounded-xl bg-bg-2 text-sm text-dim">No strong links to other applications</div>}
            </Section>
            <div className="grid gap-5 md:grid-cols-2">
              <ReasonCard title="Inside this bank" m={mod("correlation")} empty="Not linked to other applications by face, device or rhythm." />
              <ReasonCard title="At other institutions" m={mod("network")} empty="The cross-institution network had no conflict for these identifiers."
                note="Only hashed identifiers are shared between banks, never names or documents." />
            </div>
          </>}
          {tab === "session" && <>
            <SessionContext c={c} />
            <ReasonCard title="Typing and navigation" m={mod("behavior")} empty="Typing rhythm and navigation look human." />
          </>}
        </div>

        <aside className="space-y-5 xl:sticky xl:top-6">
          <OverridePanel c={c} onDone={load} />
          <Section title="Summary" right={<span className="chip"><Sparkles className="size-3" />AI</span>}>
            <p className="text-sm leading-relaxed">{readable(c.summary)}</p>
            <p className="mt-2 text-xs text-dim">Written only from the findings on this page. The decision is never the AI's.</p>
          </Section>
          <AuditTrail c={c} />
        </aside>
      </div>
    </div>
  );
}

function Verdict({ c }: { c: CaseDetail }) {
  const ruled = c.rule_codes?.filter((r) => !r.startsWith("EV_")) ?? [];
  const tone = c.band === "APPROVE" ? "var(--approve)" : c.band === "REVIEW" ? "var(--review)" : "var(--reject)";
  return (
    <section aria-label="Verdict" className="panel flex flex-wrap items-center gap-x-8 gap-y-5 p-6">
      <div className="flex min-w-0 flex-[1_1_280px] items-center gap-4">
        <Avatar name={c.name} size={56} />
        <div className="min-w-0">
          <h1 className="display truncate text-[30px] leading-tight">{c.name}</h1>
          <div className="mono mt-1 text-[12.5px] text-dim">{c.app_id} · ID ···· {c.id_last4} · {c.source.replace("partner:", "via ")} · {when(c.ts)}</div>
        </div>
      </div>
      <div className="flex items-center gap-5">
        <RiskRing value={c.prob} size={92} />
        <div className="space-y-2">
          <Stamp band={c.band} />
          {c.forced === "REJECT" && <div className="text-xs text-muted">Set by an evidence rule</div>}
          {c.forced === "REVIEW" && <div className="text-xs text-muted">Held: evidence incomplete</div>}
        </div>
      </div>
      <div className="flex-[1_1_280px] rounded-xl border p-4" style={{ background: `color-mix(in srgb, ${tone} 6%, var(--panel))`, borderColor: `color-mix(in srgb, ${tone} 22%, transparent)` }}>
        {c.band === "APPROVE" ? <>
          <div className="flex items-center gap-2 font-medium text-approve"><Check className="size-4" />Every required check passed</div>
          <div className="mt-1 text-sm text-muted">No action needed.</div>
        </> : <>
          <div className="flex flex-wrap items-center gap-2"><TypeChip type={c.fraud_type} label={c.fraud_label} />{c.stepped_up && <span className="chip">stepped up</span>}</div>
          <div className="mt-2 text-sm"><span className="text-muted">Next step: </span>{c.action}</div>
          {!!ruled.length && <ul className="mt-2 space-y-1">{ruled.map((r) => <Finding key={r} code={r} weight={0.5} text={c.rule_texts?.[r] ?? r} />)}</ul>}
        </>}
        {c.truth_type && <div className="mt-2 text-[11.5px] text-dim" title="Ground truth from the synthetic generator (seeded data only)">Generator truth: {c.truth_type}</div>}
      </div>
    </section>
  );
}

function SignalStrip({ modules, onOpen }: { modules: ModuleResult[]; onOpen: (t: Tab) => void }) {
  return (
    <section aria-label="Signals by check" className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
      {modules.map((m) => {
        const meta = MOD[m.module] ?? { label: m.module, tab: "overview" as Tab, icon: FileSearch };
        const col = riskColor(m.risk), hot = m.risk >= 0.3, I = meta.icon;
        return (
          <button key={m.module} onClick={() => onOpen(meta.tab)} title={`Open ${meta.label.toLowerCase()} detail`}
            className="panel flex min-h-[44px] flex-col gap-2 p-3.5 text-left transition-shadow hover:shadow-[var(--shadow-lg)]"
            style={hot ? { borderColor: col, boxShadow: `inset 0 0 0 1px ${col}` } : undefined}>
            <span className="flex items-center justify-between gap-2 text-sm font-medium">
              <span className="flex items-center gap-1.5"><I className="size-4" style={{ color: hot ? col : "var(--dim)" }} />{meta.label}</span>
              <span className="mono text-[13px]" style={{ color: col }}>{m.risk.toFixed(2)}</span>
            </span>
            <span className="h-1.5 rounded-full bg-bg-2"><span className="block h-full rounded-full" style={{ width: `${Math.max(3, m.risk * 100)}%`, background: col }} /></span>
            <span className={clsx("line-clamp-2 text-[12.5px] leading-snug", hot ? "" : "text-dim")} style={hot ? { color: col } : undefined}>
              {m.reasons[0]?.text ?? (m.simulated ? "Simulated" : "Nothing unusual")}</span>
          </button>
        );
      })}
    </section>
  );
}

type Tone = "ok" | "warn" | "bad" | "na";
type Cell = { tone: Tone; text: string };
const ok = (text: string): Cell => ({ tone: "ok", text }), warn = (text: string): Cell => ({ tone: "warn", text });
const bad = (text: string): Cell => ({ tone: "bad", text }), na = (text: string): Cell => ({ tone: "na", text });
const CELL: Record<Tone, string> = {
  ok: "bg-[color-mix(in_srgb,var(--approve)_8%,var(--panel))] text-approve",
  warn: "bg-[color-mix(in_srgb,var(--review)_10%,var(--panel))] text-review",
  bad: "bg-[color-mix(in_srgb,var(--reject)_9%,var(--panel))] text-reject",
  na: "bg-bg-2 text-dim",
};
const CELL_ICON: Record<Tone, any> = { ok: Check, warn: AlertTriangle, bad: X, na: Minus };

/** Each fact as each source states it, so an analyst sees at a glance where the story breaks. */
function Consistency({ c }: { c: CaseDetail }) {
  const ev = c.modules.find((m) => m.module === "document")?.evidence ?? {};
  const bio = c.modules.find((m) => m.module === "biometric")?.evidence ?? {};
  const netCodes = (c.modules.find((m) => m.module === "network")?.reasons ?? []).map((r) => r.code);
  const status = (k: string) => c.evidence?.find((x) => x.check === k)?.status;
  const norm = (x?: string) => (x ?? "").replace(/[\s-]/g, "").toUpperCase();
  const last4 = (x?: string) => norm(x).slice(-4);
  const qr = ev.qr ?? {}, ocr = ev.ocr ?? {}, form = c.form_masked ?? {};
  const signed = !!ev.qr_signature_valid;

  const qrCell = (v?: string, show?: string): Cell => !v ? na("no readable QR") : signed ? ok(show ?? v) : bad(`${show ?? v} (signature not valid)`);
  const cmp = (v: string | undefined, ref: string | undefined, f = norm, missing = "unreadable"): Cell =>
    !v ? warn(missing) : !ref ? ok(v) : f(v) === f(ref) ? ok("matches") : bad(`reads ${v}`);
  const reg = (s?: string): Cell => s === "PASS" ? ok("matches") : s === "FAIL" ? bad("does not match") : na(s === "UNAVAILABLE" ? "not reachable" : "not checked");
  const net = status("network");
  const netName: Cell = netCodes.includes("COR_NET_ID_OTHER_NAME") ? warn("other name elsewhere") : net === "PASS" ? ok("no conflict") : na("not checked");
  const netId: Cell = netCodes.includes("COR_NET_PRIOR_REJECT") ? bad("rejected at another bank")
    : netCodes.includes("COR_NET_ID_OTHER_NAME") ? warn("used under another name") : net === "PASS" ? ok("no conflict") : na("not checked");
  const thr = bio.threshold ?? 0.35;
  const face = (x?: number | null): Cell => x == null || Number.isNaN(x) ? na("not compared") : x >= thr ? ok(`match ${x.toFixed(2)}`) : bad(`no match ${x.toFixed(2)}`);

  const rows: [string, Cell[]][] = [
    ["Name", [qrCell(qr.n), cmp(ocr.name, qr.n), cmp(form.name, qr.n ?? ocr.name, norm, "not given"), reg(status("registry_identity")), netName]],
    ["Date of birth", [qrCell(qr.d), cmp(ocr.dob, qr.d), cmp(form.dob, qr.d ?? ocr.dob, norm, "not given"), reg(status("registry_identity")), na("not shared")]],
    ["ID number", [qrCell(qr.id && `···· ${last4(qr.id)}`), cmp(ocr.id_number && `···· ${last4(ocr.id_number)}`, qr.id && `···· ${last4(qr.id)}`),
      cmp(form.id_number && `···· ${last4(form.id_number)}`, qr.id && `···· ${last4(qr.id)}`, norm, "not given"), reg(status("registry_identity")), netId]],
    ["Face", [na("not in QR"), face(bio.sim_card), na("n/a"), face(bio.sim_registry), na("never shared")]],
  ];
  return (
    <Section title="Do the sources agree?" sub="Each fact, as each source states it" right={<Legend />}>
      <div className="-mx-1 overflow-x-auto px-1">
        <table className="w-full min-w-[640px] border-separate border-spacing-1.5 text-[13px]">
          <thead><tr className="text-left text-xs text-dim">
            <th className="w-28" />{["Signed QR", "Printed card", "Form", "Registry", "Other banks"].map((h) => <th key={h} className="px-1 font-medium">{h}</th>)}
          </tr></thead>
          <tbody>
            {rows.map(([k, cells]) => (
              <tr key={k}>
                <th className="pr-2 text-left font-medium">{k}</th>
                {cells.map((x, i) => { const I = CELL_ICON[x.tone]; return (
                  <td key={i} className={clsx("rounded-[9px] px-2.5 py-2", CELL[x.tone])}>
                    <span className={clsx("flex items-center gap-1.5", i === 0 && x.tone === "ok" && "mono text-[12.5px]")}><I className="size-3.5 shrink-0" />{x.text}</span>
                  </td>); })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  );
}

function Legend() {
  return (
    <div className="flex flex-wrap gap-3 text-xs text-dim">
      {(["ok", "warn", "bad"] as Tone[]).map((t) => { const I = CELL_ICON[t]; return (
        <span key={t} className={clsx("flex items-center gap-1", CELL[t].split(" ").pop())}><I className="size-3.5" />{{ ok: "agrees", warn: "check", bad: "conflict" }[t as "ok"]}</span>); })}
    </div>
  );
}

const STATUS_TEXT: Record<string, string> = {
  PASS: "passed", FAIL: "failed", UNAVAILABLE: "could not check", NOT_PROVIDED: "not provided", SIMULATED: "simulated",
};
const STATUS_COLOR: Record<string, string> = {
  PASS: "var(--approve)", FAIL: "var(--reject)", UNAVAILABLE: "var(--review)", NOT_PROVIDED: "var(--review)", SIMULATED: "var(--sim)",
};

/** Required checks as "X of N passed" with what failed first; passed checks fold away. */
function EvidencePanel({ checks, policy }: { checks: EvidenceCheck[]; policy?: string }) {
  if (!checks.length) return null;
  const req = checks.filter((x) => x.required);
  const failing = req.filter((x) => x.status !== "PASS");
  const alerts = checks.filter((x) => !x.required && x.status === "FAIL");
  const passed = req.length - failing.length;
  return (
    <Section title="Required evidence" sub={failing.length ? "Automatic approval needs every required check to pass" : "Every required check passed"}
      right={<span className="text-sm"><b className="mono">{passed} of {req.length}</b> <span className="text-muted">passed</span>{policy && <span className="mono ml-2 text-xs text-dim">{policy}</span>}</span>}>
      <div className="flex gap-[3px]" aria-hidden>
        {[...failing, ...req.filter((x) => x.status === "PASS")].map((x) => <span key={x.check} className="h-2 flex-1 rounded-[3px]" style={{ background: STATUS_COLOR[x.status] }} title={x.label} />)}
      </div>
      {(failing.length > 0 || alerts.length > 0) && (
        <ul className="mt-4 space-y-2">
          {[...failing, ...alerts].map((x) => (
            <li key={x.check} className="flex items-start justify-between gap-3 rounded-xl border px-3.5 py-2.5 text-sm"
              style={{ borderColor: `color-mix(in srgb, ${STATUS_COLOR[x.status]} 28%, transparent)`, background: `color-mix(in srgb, ${STATUS_COLOR[x.status]} 6%, var(--panel))` }}>
              <span>{x.label}{!x.required && <span className="ml-1.5 text-xs text-dim">(alert only: holds the case for review)</span>}</span>
              <span className="shrink-0 text-xs font-medium" style={{ color: STATUS_COLOR[x.status] }}>{STATUS_TEXT[x.status]}</span>
            </li>
          ))}
        </ul>
      )}
      <details className="group mt-4 border-t border-line pt-3">
        <summary className="cursor-pointer list-none text-sm text-muted hover:text-fg"><ChevronRight className="mr-1 inline size-4 transition-transform group-open:rotate-90" />Show all {checks.length} checks</summary>
        <ul className="mt-3 grid gap-x-8 gap-y-1 text-sm sm:grid-cols-2">
          {checks.map((x) => (
            <li key={x.check} className="flex items-center justify-between gap-3 border-b border-line/70 py-1.5">
              <span className={x.required ? "" : "text-muted"}>{x.label}{x.source && x.source !== "server" && <span className="ml-1.5 text-[11px] text-dim">({x.source})</span>}</span>
              <span className="shrink-0 text-xs font-medium" style={{ color: STATUS_COLOR[x.status] }}>{STATUS_TEXT[x.status]}</span>
            </li>
          ))}
        </ul>
      </details>
    </Section>
  );
}

/** Top model drivers as plain bars: red pushes toward fraud, green away from it. */
function ShapPanel({ shap }: { shap: CaseDetail["shap"] }) {
  const rows = shap ?? [];
  const max = Math.max(0.01, ...rows.map((s) => Math.abs(s.shap)));
  return (
    <Section title="What drove the score" sub="The five features that moved this case's fraud risk the most">
      {rows.length ? (
        <div className="grid grid-cols-[minmax(140px,240px)_1fr_56px] items-center gap-x-4 gap-y-3 text-[13.5px]">
          {rows.map((s) => {
            const col = s.shap > 0 ? "var(--reject)" : "var(--approve)";
            return [
              <span key={s.feature + "l"} className="leading-snug">{featureLabel(s.feature)}{s.value != null && <span className="mono ml-1 text-xs text-dim">= {s.value}</span>}</span>,
              <span key={s.feature + "b"} className="h-2.5 rounded bg-bg-2"><span className="block h-full rounded" style={{ width: `${(Math.abs(s.shap) / max) * 100}%`, background: col }} /></span>,
              <span key={s.feature + "v"} className="mono text-right" style={{ color: col }}>{s.shap > 0 ? "+" : "−"}{Math.abs(s.shap).toFixed(2)}</span>,
            ];
          })}
        </div>
      ) : <div className="text-sm text-dim">Model not trained yet.</div>}
    </Section>
  );
}

function ReasonCard({ title, m, empty, note }: { title: string; m?: ModuleResult; empty: string; note?: string }) {
  return (
    <Section title={title} right={m && <span className="mono text-sm" style={{ color: riskColor(m.risk) }}>{m.risk.toFixed(2)}</span>}>
      <ul className="space-y-2">{m?.reasons.length ? m.reasons.map((r) => <Finding key={r.code} text={r.text} code={r.code} weight={r.weight} />)
        : <li className="text-sm text-dim">{m ? empty : "This check did not run for this case."}</li>}</ul>
      {note && <p className="mt-3 text-xs text-dim">{note}</p>}
    </Section>
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
  const qrText = ev.qr_signature_valid ? "QR signature valid" : ({ INVALID_SIGNATURE: "QR signature INVALID", UNTRUSTED_KEY: "QR signed by an unknown key",
    MALFORMED: "QR unreadable or malformed", NOT_FOUND: "No readable QR", NO_TRUSTED_KEYS: "No issuer key configured" } as Record<string, string>)[ev.qr_status] ?? "No readable QR";
  return (
    <Section title="The card" sub="What was uploaded, and what the pixel checks see"
      right={<span className={clsx("chip", ev.qr_signature_valid ? "text-approve" : ev.qr_status === "INVALID_SIGNATURE" ? "text-reject" : "text-review")}>{qrText}</span>}>
      <div className="seg mb-3">
        {([["card", "Card"], ["ela", "Error levels"], ["trufor", "TruFor"]] as const).map(([k, l]) => (
          <button key={k} aria-pressed={view === k} onClick={() => (k === "trufor" ? showTrufor() : setView(k))}>{l}</button>
        ))}
      </div>
      {view === "trufor" && !tf ? <div className="grid aspect-[1000/630] place-items-center rounded-xl bg-bg-2 text-sm text-muted">Running TruFor (first run loads the model, about 10 s)</div>
        : <img src={view === "ela" ? fileUrl(`/api/apps/${c.app_id}/ela.png`) : view === "trufor" && tf && !("error" in tf) ? fileUrl(tf.heatmap) : fileUrl(c.card_path)} alt="Uploaded card" className="w-full rounded-xl border border-line" />}
      {view === "trufor" && tf && ("error" in tf
        ? <p className="mt-2 text-sm text-reject">{tf.error}</p>
        : <p className="mt-2 text-sm text-muted">TruFor (CVPR 2023) score <span className="mono font-medium text-fg">{tf.score.toFixed(3)}</span>. Red marks pixels it thinks were manipulated.
            It is shown as evidence only and never changes the decision: on our cards it also flags the genuinely pasted photo, and it misses edited text fields that the signed QR catches.</p>)}
      {view === "ela" && <p className="mt-2 text-sm text-muted">Error-level analysis: edited regions often re-compress differently and glow brighter than the rest of the card.</p>}
      {ev.forensics && (
        <dl className="mt-4 grid grid-cols-3 gap-3 text-sm">
          {[["Pixel forensics", ev.forensics.score], ["Texture ratio", ev.forensics.tex_ratio], ["Font deviation", ev.forensics.font_dev]].map(([k, v]) => (
            <div key={k} className="well px-3 py-2.5"><dt className="text-xs text-dim">{k}</dt><dd className="mono mt-0.5">{v}</dd></div>
          ))}
        </dl>
      )}
      <ul className="mt-4 space-y-1.5">{m?.reasons.map((r) => <Finding key={r.code} text={r.text} code={r.code} weight={r.weight} />)}</ul>
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
    <Section title="Face & liveness" sub={`ArcFace match threshold ${thr}, set at 0.1% false accepts`}>
      <div className="grid grid-cols-3 gap-3">
        {[["Selfie", fileUrl(c.selfie_path)], ["Card portrait", null], ["Registry photo", fileUrl(ev.registry_face_url)]].map(([l, src], i) => (
          <figure key={String(l)}>
            <div className="aspect-[4/5] overflow-hidden rounded-xl border border-line bg-bg-2">
              {i === 1 ? <div className="h-full w-full bg-cover" style={{ backgroundImage: `url(${fileUrl(c.card_path)})`, backgroundSize: "417%", backgroundPosition: "5.3% 36%" }} />
                : src ? <img src={String(src)} alt={String(l)} className="h-full w-full object-cover" /> : <div className="grid h-full place-items-center text-xs text-dim">not in registry</div>}
            </div>
            <figcaption className="mt-1.5 text-center text-xs text-muted">{l}</figcaption>
          </figure>
        ))}
      </div>
      <div className="mt-5 divide-y divide-line text-sm">
        <Pair label="Selfie ↔ card" v={sim(ev.sim_card)} ok={ok(ev.sim_card)} />
        <Pair label="Selfie ↔ registry" v={sim(ev.sim_registry)} ok={ok(ev.sim_registry)} />
        <Pair label="Face reused under another name" v={String(ev.reuse?.diff_name ?? 0)} ok={!(ev.reuse?.diff_name > 0)} />
        <Pair label={`Liveness (${live.source === "synthetic fixture" ? "synthetic fixture" : "server-verified"})`}
          v={({ PASS: "passed", FAIL: "failed", NOT_PROVIDED: "not provided", UNAVAILABLE: "could not check" } as Record<string, string>)[live.status] ?? "n/a"} ok={live.status === "PASS"} />
        {d.turn_deltas && <Pair label="Head turns vs neutral" v={`${(d.sequence ?? []).join(", ").replaceAll("_", " ")}: ${d.turn_deltas.join(" / ")}`} ok={live.status === "PASS"} />}
        {d.frames != null && <Pair label="Motion frames analysed" v={String(d.frames)} ok={live.status === "PASS"} />}
        {d.sim_to_selfie && <Pair label="Frames match the selfie" v={d.sim_to_selfie.join(" / ")} ok={!live.codes?.includes("BIO_FRAMES_INCONSISTENT")} />}
        <Pair label="Camera (browser-reported)" v={cam.length ? cam.join(", ") : "not reported"} ok={!virtual && cam.length > 0} />
        <Pair label="Same picture seen before" v={String(m?.features?.bio_media_reuse ?? 0)} ok={!(Number(m?.features?.bio_media_reuse) > 0)} />
        <div className="flex items-center justify-between py-2 text-xs text-dim"><span>Voice step-up {c.step_up?.voice != null && `score ${c.step_up.voice}`} (never used in the decision)</span><SimBadge /></div>
      </div>
    </Section>
  );
}

function Pair({ label, v, ok }: { label: string; v: string; ok: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3 py-2">
      <span className="text-muted">{label}</span>
      <span className={clsx("mono flex items-center gap-1.5 text-right text-xs", ok ? "text-approve" : "text-reject")}>{ok ? <Check className="size-3.5 shrink-0" /> : <X className="size-3.5 shrink-0" />}{v}</span>
    </div>
  );
}

/** The analyst's own call, on an ink panel so it is the one place on the page that asks for action. */
function OverridePanel({ c, onDone }: { c: CaseDetail; onDone: () => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
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
    <section className="rounded-2xl bg-ink p-5 text-white">
      <div className="flex items-center justify-between gap-2">
        <h2 className="display text-[19px]">Your decision</h2>
        <span className="rounded-full bg-white/10 px-2.5 py-0.5 text-xs capitalize text-white/80">{c.status.replaceAll("_", " ")}</span>
      </div>
      <p className="mt-1.5 text-[13px] leading-relaxed text-white/65">Recorded next to the automated decision, which never changes. Going against it needs a reason of at least 20 characters.</p>
      <label htmlFor="note" className="mt-4 block text-xs text-white/65">Reason (kept in the audit log)</label>
      <textarea id="note" className="mt-1.5 h-24 w-full resize-none rounded-[10px] border border-white/15 bg-white/5 px-3 py-2 text-sm text-white outline-none placeholder:text-white/35 focus:border-white/40"
        placeholder="What you checked and why" value={note} onChange={(e) => setNote(e.target.value)} />
      <div className="mt-3 grid grid-cols-2 gap-2">
        <button className="btn min-h-11 border-white bg-white text-approve hover:bg-white/90" disabled={busy || !note} onClick={() => act("approved")}><Check className="size-4" />Approve</button>
        <button className="btn min-h-11 border-reject bg-reject text-white hover:bg-reject/90" disabled={busy || !note} onClick={() => act("rejected")}><X className="size-4" />Reject</button>
      </div>
      {msg && <p className="mt-2 text-xs text-[#f3c27a]">{msg}</p>}
    </section>
  );
}

function AuditTrail({ c }: { c: CaseDetail }) {
  async function erase() {
    if (!confirm(`Permanently delete ${c.app_id}: the record, card and selfie images, and its graph link? This cannot be undone.`)) return;
    await del(`/api/apps/${c.app_id}`);
    window.location.href = "/dashboard";
  }
  return (
    <Section title="Audit trail" sub="Hash-chained: editing any entry breaks the chain">
      <ol className="max-h-64 space-y-3 overflow-auto text-[13px]">
        {c.audit.map((a, i) => (
          <li key={i} className={clsx("border-l-2 pl-3", a.actor === "system" ? "border-line-2" : "border-brand")}>
            <div className="mono text-[11.5px] text-dim">{a.ts.replace("T", " ").slice(0, 16)}{a.hash && ` · #${a.hash.slice(0, 8)}`}</div>
            <div><span className="font-medium">{a.actor}</span> · {a.action.replace("decision:", "decided ")}{a.note && <span className="text-muted">: {a.note}</span>}</div>
          </li>
        ))}
        {!c.audit.length && <li className="text-dim">Seeded case: no audit entries yet.</li>}
      </ol>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-line pt-3 text-xs text-dim">
        <span>Images are deleted after the retention period.</span>
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
    <Section title="Session" sub="Captured per RBI V-CIP: recorded, not scored">
      <dl className="grid gap-3 text-sm sm:grid-cols-3">
        <div className="well px-3.5 py-3">
          <dt className="text-xs text-dim">Geo-tag (GPS)</dt>
          <dd className="mono mt-1 text-[13px]">
            {g ? <span>{geoText} {map ? <a href={map} target="_blank" rel="noreferrer" className="font-sans text-brand hover:underline">map</a> : null}</span>
               : <span className="font-sans text-review">not provided</span>}
          </dd>
        </div>
        <div className="well px-3.5 py-3">
          <dt className="text-xs text-dim">Network (IP)</dt>
          <dd className="mono mt-1 text-[13px]">{x.ip ? x.ip : <span className="font-sans text-dim">local / behind proxy</span>}</dd>
        </div>
        <div className="well px-3.5 py-3">
          <dt className="text-xs text-dim">Consent</dt>
          <dd className="mt-1 text-[13px]">{x.consent && x.consent.version ? <>accepted <span className="mono text-xs text-dim">{x.consent.version}</span></> : <span className="text-dim">n/a</span>}</dd>
        </div>
      </dl>
    </Section>
  );
}
