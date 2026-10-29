"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import clsx from "clsx";
import { CheckCircle2, ChevronRight, Files, Network, RefreshCw, Search } from "lucide-react";
import { Avatar, BandBadge, EmptyState, PageHeader, RiskBar, Stat, TYPE_COLORS, TypeChip, pct, riskColor, when } from "@/components/ui";
import { type AppRow, get } from "@/lib/api";

const BANDS = ["REVIEW", "REJECT", "APPROVE", "ALL"] as const;
const BAND_TAB: Record<string, string> = { ALL: "All", REJECT: "Rejected", REVIEW: "Needs review", APPROVE: "Approved" };
const TYPES = ["all", "ring", "first_party", "third_party", "mule", "bot", "tampered", "injection", "inconclusive"];
const TYPE_NAMES: Record<string, string> = { all: "All patterns", ring: "Synthetic ring", first_party: "First-party / Frankenstein",
  third_party: "Third-party fabricated", mule: "Possible mule recruitment", bot: "Bot / scripted", tampered: "Tampered document",
  injection: "Capture integrity / replay", inconclusive: "Incomplete evidence" };
const SOURCE: Record<string, string> = { live: "Live", seed: "", ring_sim: "Ring sim" };
/* Brighter decision colours for the dark summary tile. */
const BAR: Record<string, string> = { APPROVE: "#2fa374", REVIEW: "#e0a040", REJECT: "#e06048" };

export default function Queue() {
  const [rows, setRows] = useState<AppRow[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [band, setBand] = useState<(typeof BANDS)[number]>("REVIEW");
  const [ftype, setFtype] = useState("all");
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  async function load() {
    setLoading(true);
    const p = new URLSearchParams({ limit: "400" });
    if (band !== "ALL") p.set("band", band);
    if (ftype !== "all") p.set("ftype", ftype);
    if (q) p.set("q", q);
    try {
      const [r, s] = await Promise.all([get<AppRow[]>(`/api/apps?${p}`), get("/api/stats")]);
      setRows([...r].sort((a, b) => (b.prob ?? -1) - (a.prob ?? -1))); setStats(s); setErr("");
    } catch (e) { setErr(String(e)); } finally { setLoading(false); }
  }
  useEffect(() => { load(); }, [band, ftype]); // eslint-disable-line react-hooks/exhaustive-deps

  const count = (b: string) => (!stats ? null : b === "ALL" ? stats.total : stats.bands[b] ?? 0);
  const open = stats ? (stats.bands.REVIEW ?? 0) : 0;
  const COLS = "grid-cols-[6px_minmax(200px,1.4fr)_110px_minmax(130px,0.9fr)_minmax(200px,1.1fr)_minmax(170px,1.2fr)_96px]";
  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Operations" title="Review queue"
        right={<button className="btn min-h-11" onClick={load}><RefreshCw className={clsx("size-4", loading && "animate-spin")} />Refresh</button>}>
        Riskiest cases first. The colour spine on each case file is its fraud risk: the deeper, the riskier.
      </PageHeader>

      {stats && (
        <section aria-label="Today" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <div className="flex flex-col justify-between gap-4 rounded-2xl bg-ink p-5 text-white sm:col-span-2">
            <div className="text-[13px] text-white/65">Waiting for an analyst</div>
            <div className="flex items-baseline gap-3"><span className="display text-[52px] leading-none">{open.toLocaleString()}</span><span className="text-white/65">of {stats.total.toLocaleString()} applications</span></div>
            <div className="flex h-2.5 gap-0.5 overflow-hidden rounded-full" aria-hidden>
              {(["APPROVE", "REVIEW", "REJECT"] as const).map((b) => <span key={b} style={{ flex: stats.bands[b] ?? 0, background: BAR[b] }} />)}
            </div>
            <div className="flex flex-wrap gap-4 text-[12.5px] text-white/65">
              {(["APPROVE", "REVIEW", "REJECT"] as const).map((b) => <span key={b}><span style={{ color: BAR[b] }}>●</span> {BAND_TAB[b]} {(stats.bands[b] ?? 0).toLocaleString()}</span>)}
            </div>
          </div>
          <Stat icon={Network} tone="reject" label="In fraud rings" value={(stats.types.ring ?? 0).toLocaleString()} hint="linked by face, device or rhythm" />
          <Stat icon={Files} tone="brand" label="Submitted live" value={(stats.live ?? 0).toLocaleString()} hint="from the KYC flow and partner sites" />
          <Stat icon={CheckCircle2} tone="approve" label="Auto-approved" value={pct((stats.bands.APPROVE ?? 0) / stats.total, 0)} hint="every required check passed" />
        </section>
      )}

      <section aria-label="Filters" className="flex flex-wrap items-center gap-3">
        <div className="tabs" role="tablist" aria-label="Decision">
          {BANDS.map((b) => (
            <button key={b} role="tab" aria-selected={band === b} className="tab" onClick={() => setBand(b)}>
              {BAND_TAB[b]}{count(b) != null && <span className="mono text-xs opacity-70">{count(b)!.toLocaleString()}</span>}
            </button>
          ))}
        </div>
        <form className="relative ml-auto w-full sm:w-80" onSubmit={(e) => { e.preventDefault(); load(); }}>
          <Search className="absolute left-3 top-3.5 size-4 text-dim" />
          <input aria-label="Search" className="input min-h-11 pl-9 text-sm" placeholder="Name or application ID, then Enter" value={q} onChange={(e) => setQ(e.target.value)} />
        </form>
        <div className="flex w-full flex-wrap gap-1.5" role="group" aria-label="Fraud pattern">
          {TYPES.map((t) => (
            <button key={t} aria-pressed={ftype === t} onClick={() => setFtype(t)}
              className={clsx("min-h-9 rounded-full border px-3 text-[13px] transition-colors",
                ftype === t ? "border-brand bg-brand-soft text-brand" : "border-line-2 bg-panel text-muted hover:text-fg")}>
              {t !== "all" && <span className="mr-1.5 inline-block size-1.5 rounded-full align-middle" style={{ background: TYPE_COLORS[t] }} aria-hidden />}{TYPE_NAMES[t]}
              {stats?.types?.[t] != null && t !== "all" && <span className="mono ml-1.5 text-[11px] text-dim">{stats.types[t]}</span>}
            </button>
          ))}
        </div>
      </section>

      {err && <div className="panel px-5 py-6 text-sm text-reject">The backend is not reachable. Start it with ./scripts/run_backend.sh. ({err})</div>}

      <section aria-label="Cases" className="-mx-1 overflow-x-auto px-1 pb-1">
        <div className="min-w-[1010px] space-y-2">
          <div className={clsx("grid gap-4 pr-4 text-xs text-dim", COLS)}>
            <span /><span>Applicant</span><span>Decision</span><span>Fraud risk</span><span>Pattern</span><span>Next step</span><span className="text-right">Submitted</span>
          </div>
          {rows.map((r) => {
            const col = r.prob == null ? "var(--dim)" : riskColor(r.prob);
            return (
              <Link key={r.app_id} href={`/dashboard/case/${r.app_id}`}
                className={clsx("panel group grid items-center gap-4 overflow-hidden py-3 pr-4 transition-[box-shadow,transform] hover:-translate-y-px hover:shadow-[var(--shadow-lg)]", COLS)}>
                <span className="-my-3 self-stretch" style={{ background: col, opacity: r.prob == null ? 0.3 : 0.35 + r.prob * 0.65 }} aria-hidden />
                <span className="flex min-w-0 items-center gap-3">
                  <Avatar name={r.name} size={36} />
                  <span className="min-w-0">
                    <span className="block truncate font-medium">{r.name}</span>
                    <span className="mono flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs text-dim"><span className="whitespace-nowrap">{r.app_id} <span aria-hidden>·</span></span><span className="whitespace-nowrap">ID ···· {r.id_last4}</span>
                      {SOURCE[r.source] !== "" && <span className="chip px-1.5 py-0 font-sans text-[10.5px]">{SOURCE[r.source] ?? r.source.replace("partner:", "")}</span>}</span>
                  </span>
                </span>
                <span><BandBadge band={r.band} />{r.status !== "open" && <span className="mt-1 block text-xs capitalize text-dim">analyst: {r.status.replaceAll("_", " ")}</span>}</span>
                <span>{r.prob == null ? <span className="text-xs text-review">model unavailable</span>
                  : <span className="flex items-center gap-3"><RiskBar value={r.prob} /><span className="mono w-9 text-xs font-medium" style={{ color: col }}>{r.prob.toFixed(2)}</span></span>}</span>
                <span className="min-w-0"><TypeChip type={r.fraud_type} label={r.fraud_type === "none" ? undefined : r.fraud_label} /></span>
                <span className="line-clamp-2 text-[13px] text-muted" title={r.action}>{r.band === "APPROVE" ? <span className="text-dim">None</span> : r.action}</span>
                <span className="flex items-center justify-end gap-1 whitespace-nowrap text-xs text-dim">{when(r.ts)}<ChevronRight className="size-4 opacity-0 transition-opacity group-hover:opacity-100" /></span>
              </Link>
            );
          })}
        </div>
        {loading && !rows.length && <div className="space-y-2">{[0, 1, 2, 3, 4].map((i) => <div key={i} className="h-16 animate-pulse rounded-2xl bg-bg-2" />)}</div>}
        {!rows.length && !loading && !err && <div className="panel"><EmptyState title="No applications match these filters">Try another decision tab or pattern, or clear the search.</EmptyState></div>}
        {!!rows.length && <div className="pt-3 text-xs text-dim">Showing {rows.length.toLocaleString()} application{rows.length > 1 ? "s" : ""}{band !== "ALL" && ` · ${BAND_TAB[band].toLowerCase()}`}</div>}
      </section>
    </div>
  );
}
