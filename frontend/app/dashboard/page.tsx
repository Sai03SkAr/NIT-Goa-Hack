"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import clsx from "clsx";
import { RefreshCw, Search } from "lucide-react";
import { BandBadge, RiskBar, Stat, TypeChip, pct } from "@/components/ui";
import { type AppRow, get } from "@/lib/api";

const BANDS = ["ALL", "REJECT", "REVIEW", "APPROVE"] as const;
const TYPES = ["all", "ring", "first_party", "third_party", "bot", "tampered", "injection"];

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


  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Review queue</h1>
          <p className="mt-1 text-sm text-muted">Every application with its calibrated risk, band, detected pattern and recommended action.</p>
        </div>
        <button className="btn" onClick={load}><RefreshCw className={clsx("size-4", loading && "animate-spin")} />Refresh</button>
      </div>

      {stats && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <Stat label="Applications" value={stats.total.toLocaleString()} hint={`${stats.live} live / simulated`} />
          <Stat label="Approved" value={stats.bands.APPROVE ?? 0} accent="var(--approve)" hint={pct((stats.bands.APPROVE ?? 0) / stats.total)} />
          <Stat label="In review" value={stats.bands.REVIEW ?? 0} accent="var(--review)" hint={pct((stats.bands.REVIEW ?? 0) / stats.total)} />
          <Stat label="Rejected" value={stats.bands.REJECT ?? 0} accent="var(--reject)" hint={pct((stats.bands.REJECT ?? 0) / stats.total)} />
          <Stat label="Synthetic rings" value={stats.types.ring ?? 0} accent="#fb7185" hint="cluster members flagged" />
        </div>
      )}

      <div className="panel p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex rounded-lg border border-line-2 p-0.5">
            {BANDS.map((b) => (
              <button key={b} onClick={() => setBand(b)} className={clsx("rounded-md px-3 py-1 text-xs font-semibold transition", band === b ? "bg-white/10 text-fg" : "text-muted hover:text-fg")}>{b}</button>
            ))}
          </div>
          <select className="input w-44 py-1.5 text-sm" value={ftype} onChange={(e) => setFtype(e.target.value)}>
            {TYPES.map((t) => <option key={t} value={t}>{t === "all" ? "All patterns" : t.replace("_", " ")}</option>)}
          </select>
          <form className="relative ml-auto w-72" onSubmit={(e) => { e.preventDefault(); load(); }}>
            <Search className="absolute left-3 top-2.5 size-4 text-dim" />
            <input className="input py-1.5 pl-9 text-sm" placeholder="Search name or application ID" value={q} onChange={(e) => setQ(e.target.value)} />
          </form>
        </div>
      </div>

      {err && <div className="panel p-4 text-sm text-reject">Backend not reachable: {err}</div>}

      <div className="panel overflow-hidden">
        <table className="w-full text-sm">
          <thead className="border-b border-line bg-white/[0.02] text-left">
            <tr className="label">
              <th className="px-4 py-3">Application</th><th className="px-4 py-3">Applicant</th><th className="px-4 py-3 w-48">Risk</th>
              <th className="px-4 py-3">Band</th><th className="px-4 py-3">Pattern</th><th className="px-4 py-3">Recommended action</th>
              <th className="px-4 py-3">Status</th><th className="px-4 py-3">Submitted</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.app_id} className="border-b border-line/60 transition hover:bg-white/[0.03]">
                <td className="px-4 py-2.5">
                  <Link href={`/dashboard/case/${r.app_id}`} className="mono text-brand hover:underline">{r.app_id}</Link>
                  {r.source !== "seed" && <span className="chip ml-2 text-[10px]">{r.source}</span>}
                </td>
                <td className="px-4 py-2.5"><div>{r.name}</div><div className="mono text-[11px] text-dim">ID ···· {r.id_last4}</div></td>
                <td className="px-4 py-2.5"><div className="flex items-center gap-3"><RiskBar value={r.prob} /><span className="mono w-10 text-xs text-muted">{r.prob.toFixed(2)}</span></div></td>
                <td className="px-4 py-2.5"><BandBadge band={r.band} /></td>
                <td className="px-4 py-2.5"><TypeChip type={r.fraud_type} label={r.fraud_type === "none" ? undefined : r.fraud_label} /></td>
                <td className="max-w-[260px] truncate px-4 py-2.5 text-xs text-muted">{r.band === "APPROVE" ? "—" : r.action}</td>
                <td className="px-4 py-2.5 text-xs capitalize text-muted">{r.status}</td>
                <td className="mono px-4 py-2.5 text-xs text-dim">{r.ts.replace("T", " ").slice(0, 16)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!rows.length && !loading && <div className="p-10 text-center text-sm text-muted">No applications match.</div>}
      </div>
    </div>
  );
}
