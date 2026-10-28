"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import clsx from "clsx";
import { RefreshCw, Search } from "lucide-react";
import { BandBadge, PageHeader, RiskBar, Stat, TypeChip, pct } from "@/components/ui";
import { type AppRow, get } from "@/lib/api";

const BANDS = ["ALL", "REJECT", "REVIEW", "APPROVE"] as const;
const TYPES = ["all", "ring", "first_party", "third_party", "mule", "bot", "tampered", "injection", "inconclusive"];
const TYPE_NAMES: Record<string, string> = { all: "All patterns", ring: "Synthetic ring", first_party: "First-party / Frankenstein",
  third_party: "Third-party fabricated", mule: "Possible mule recruitment", bot: "Bot / scripted", tampered: "Tampered document",
  injection: "Capture integrity / replay", inconclusive: "Incomplete evidence" };

export default function Queue() {
  const [rows, setRows] = useState<AppRow[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [band, setBand] = useState<(typeof BANDS)[number]>("ALL");
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
      setRows(r); setStats(s); setErr("");
    } catch (e) { setErr(String(e)); } finally { setLoading(false); }
  }
  useEffect(() => { load(); }, [band, ftype]); // eslint-disable-line react-hooks/exhaustive-deps


  const BAND_TAB: Record<string, string> = { ALL: "All", REJECT: "Rejected", REVIEW: "Needs review", APPROVE: "Approved" };
  const open = stats ? (stats.bands.REVIEW ?? 0) : 0;
  return (
    <div className="space-y-6">
      <PageHeader title="Review queue" right={<button className="btn" onClick={load}><RefreshCw className={clsx("size-4", loading && "animate-spin")} />Refresh</button>}>
        Every application with its fraud probability, decision, detected pattern and the recommended next step.
      </PageHeader>

      {stats && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <Stat label="Applications" value={stats.total.toLocaleString()} hint={stats.live ? `${stats.live} submitted live` : "seeded history"} />
          <Stat label="Approved" value={stats.bands.APPROVE ?? 0} hint={pct((stats.bands.APPROVE ?? 0) / stats.total)} />
          <Stat label="Needs review" value={open} accent={open ? "var(--review)" : undefined} hint={pct(open / stats.total)} />
          <Stat label="Rejected" value={stats.bands.REJECT ?? 0} accent="var(--reject)" hint={pct((stats.bands.REJECT ?? 0) / stats.total)} />
          <Stat label="In fraud rings" value={stats.types.ring ?? 0} hint="linked by face, device or rhythm" />
        </div>
      )}

      <div className="panel overflow-hidden">
        <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3">
          <div className="flex rounded-lg bg-bg-2 p-0.5">
            {BANDS.map((b) => (
              <button key={b} onClick={() => setBand(b)} className={clsx("rounded-md px-3 py-1 text-sm transition-colors",
                band === b ? "bg-panel font-medium text-fg shadow-sm" : "text-muted hover:text-fg")}>{BAND_TAB[b]}</button>
            ))}
          </div>
          <select aria-label="Fraud pattern" className="input w-60 py-1.5 text-sm" value={ftype} onChange={(e) => setFtype(e.target.value)}>
            {TYPES.map((t) => <option key={t} value={t}>{TYPE_NAMES[t]}</option>)}
          </select>
          <form className="relative ml-auto w-72" onSubmit={(e) => { e.preventDefault(); load(); }}>
            <Search className="absolute left-3 top-2.5 size-4 text-dim" />
            <input aria-label="Search" className="input py-1.5 pl-9 text-sm" placeholder="Search name or application ID" value={q} onChange={(e) => setQ(e.target.value)} />
          </form>
        </div>

        {err && <div className="px-4 py-6 text-sm text-reject">The backend is not reachable. Start it with ./scripts/run_backend.sh. ({err})</div>}

        <table className="w-full text-sm">
          <thead className="bg-bg-2 text-left text-xs text-muted">
            <tr>
              <th className="px-4 py-2.5 font-medium">Application</th><th className="px-4 py-2.5 font-medium">Applicant</th>
              <th className="w-44 px-4 py-2.5 font-medium">Fraud probability</th><th className="px-4 py-2.5 font-medium">Decision</th>
              <th className="px-4 py-2.5 font-medium">Pattern</th><th className="px-4 py-2.5 font-medium">Next step</th>
              <th className="px-4 py-2.5 font-medium">Submitted</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rows.map((r) => (
              <tr key={r.app_id} className="transition-colors hover:bg-panel-2">
                <td className="px-4 py-2.5">
                  <Link href={`/dashboard/case/${r.app_id}`} className="mono font-medium text-brand hover:underline">{r.app_id}</Link>
                  {r.source !== "seed" && <span className="chip ml-2 text-[11px]">{r.source}</span>}
                </td>
                <td className="px-4 py-2.5"><div>{r.name}</div><div className="mono text-xs text-dim">ID ending {r.id_last4}</div></td>
                <td className="px-4 py-2.5">{r.prob == null ? <span className="text-xs text-review">model unavailable</span> : <div className="flex items-center gap-3"><RiskBar value={r.prob} /><span className="mono w-9 text-xs text-muted">{r.prob.toFixed(2)}</span></div>}</td>
                <td className="px-4 py-2.5"><BandBadge band={r.band} />{r.status !== "open" && <div className="mt-1 text-xs capitalize text-dim">analyst: {r.status.replaceAll("_", " ")}</div>}</td>
                <td className="px-4 py-2.5"><TypeChip type={r.fraud_type} label={r.fraud_type === "none" ? undefined : r.fraud_label} /></td>
                <td className="max-w-[260px] truncate px-4 py-2.5 text-xs text-muted" title={r.action}>{r.band === "APPROVE" ? "None" : r.action}</td>
                <td className="mono px-4 py-2.5 text-xs text-dim">{r.ts.replace("T", " ").slice(0, 16)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading && !rows.length && <div className="space-y-2 p-4">{[0, 1, 2, 3, 4].map((i) => <div key={i} className="h-9 animate-pulse rounded bg-bg-2" />)}</div>}
        {!rows.length && !loading && !err && <div className="p-10 text-center text-sm text-muted">No applications match these filters.</div>}
      </div>
    </div>
  );
}
