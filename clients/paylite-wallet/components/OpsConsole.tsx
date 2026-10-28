"use client";
/** Partner operations console: the bank's view of TrueID Shield verdicts for its own applicants.
 * Shared between the demo partners; colours come from each app's theme tokens. */
import { useEffect, useState } from "react";
import clsx from "clsx";
import { Check, LogOut, Minus, RefreshCw } from "lucide-react";

type Reason = { module: string; code: string; text: string; weight: number };
type App = {
  application_id: string; reference: string; submitted_at: string; status: "processing" | "completed" | "error";
  applicant: Record<string, string>; partner_checks: Record<string, boolean>; capture: Record<string, string>;
  decision?: "APPROVE" | "REVIEW" | "REJECT"; risk_score?: number; fraud_label?: string; fraud_type?: string;
  recommended_action?: string; reasons?: Reason[]; modules?: { module: string; risk: number; simulated: boolean }[];
  decision_rules?: string[]; summary?: string; error?: string;
};

export const CHECKS: [string, string][] = [
  ["mobile_otp", "Mobile OTP"], ["email_otp", "Email OTP"], ["pan_nsdl", "PAN checked with NSDL"],
  ["digilocker_identity", "Identity from DigiLocker"], ["live_selfie", "Live selfie (liveness)"],
  ["signature", "Signature"], ["esign_otp", "eSign"], ["geolocation", "Location"],
];
const MODULES: Record<string, string> = {
  document: "Document", biometric: "Face and liveness", behavior: "Session behaviour", registry: "Registries", correlation: "Cross-application links",
};
const CAPTURE: Record<string, string> = {
  camera: "live camera", live_camera: "live camera", digilocker_file: "DigiLocker e-ID file", gallery_upload: "photo upload",
};

function Decision({ a }: { a: App }) {
  if (a.status === "processing") return <span className="inline-flex items-center gap-1.5 text-muted"><RefreshCw className="size-3.5 animate-spin" />Checking</span>;
  if (a.status === "error") return <span className="text-err">Error</span>;
  const d = a.decision!;
  return (
    <span className={clsx("inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold",
      d === "APPROVE" && "bg-ok/12 text-ok", d === "REVIEW" && "bg-warn/12 text-warn", d === "REJECT" && "bg-err/12 text-err")}>
      {d === "APPROVE" ? "Approve" : d === "REVIEW" ? "Review" : "Reject"}
    </span>
  );
}

function Risk({ v }: { v?: number }) {
  if (v == null) return <span className="text-faint">–</span>;
  const pct = Math.round(v * 100);
  return (
    <span className="inline-flex items-center gap-2 tabular-nums">
      <span className="h-1.5 w-14 overflow-hidden rounded-full bg-line">
        <span className={clsx("block h-full rounded-full", v < 0.3 ? "bg-ok" : v < 0.7 ? "bg-warn" : "bg-err")} style={{ width: `${Math.max(4, pct)}%` }} />
      </span>
      {pct}
    </span>
  );
}

export function OpsConsole({ brand, profileNote }: { brand: React.ReactNode; profileNote: string }) {
  const [apps, setApps] = useState<App[] | null>(null);
  const [err, setErr] = useState("");
  const [sel, setSel] = useState<string | null>(null);

  useEffect(() => {
    let stop = false;
    const load = async () => {
      try {
        const r = await fetch("/api/ops/applications");
        const j = await r.json();
        if (stop) return;
        if (!r.ok) setErr(j.error ?? j.detail ?? "Couldn't load applications");
        else { setErr(""); setApps(j.applications); }
      } catch { if (!stop) setErr("Couldn't reach this site's server."); }
      if (!stop) setTimeout(load, 3000);
    };
    load();
    return () => { stop = true; };
  }, []);

  const picked = apps?.find((a) => a.application_id === sel) ?? null;
  const count = (d: string) => apps?.filter((a) => a.decision === d).length ?? 0;

  return (
    <div className="min-h-dvh">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6">
          <div className="flex items-center gap-3">{brand}<span className="text-sm text-muted">Operations</span></div>
          <button className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink"
            onClick={async () => { await fetch("/api/ops/login", { method: "DELETE" }); location.href = "/ops/login"; }}>
            <LogOut className="size-4" />Sign out
          </button>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-[-0.02em]">KYC applications</h1>
            <p className="mt-1 max-w-[70ch] text-sm text-muted">{profileNote} Verdicts come from TrueID Shield and refresh every few seconds.</p>
          </div>
          {apps && (
            <p className="text-sm text-muted">
              {apps.length} total, <span className="text-ok">{count("APPROVE")} approve</span>, <span className="text-warn">{count("REVIEW")} review</span>,{" "}
              <span className="text-err">{count("REJECT")} reject</span>
            </p>
          )}
        </div>
        {err && <p role="alert" className="error mt-4">{err}</p>}

        <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_26rem]">
          <div className="self-start overflow-x-auto rounded-2xl border border-line bg-surface">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="border-b border-line text-muted">
                <tr>{["Reference", "Applicant", "Submitted", "Decision", "Risk", "Pattern"].map((h) => <th key={h} className="px-4 py-3 font-medium">{h}</th>)}</tr>
              </thead>
              <tbody>
                {apps?.length === 0 && (
                  <tr><td colSpan={6} className="px-4 py-10 text-center text-muted">No applications yet. Submit one from the onboarding flow and it appears here.</td></tr>
                )}
                {apps?.map((a) => (
                  <tr key={a.application_id} onClick={() => setSel(a.application_id)}
                    className={clsx("cursor-pointer border-b border-line last:border-0 hover:bg-mist/50", sel === a.application_id && "bg-mist")}>
                    <td className="whitespace-nowrap px-4 py-3 font-medium tabular-nums">
                      <button className="text-left" onClick={() => setSel(a.application_id)}>{a.reference || a.application_id}</button>
                    </td>
                    <td className="px-4 py-3">{a.applicant.name}</td>
                    <td className="whitespace-nowrap px-4 py-3 tabular-nums text-muted">{a.submitted_at.replace("T", " ").slice(5, 16)}</td>
                    <td className="px-4 py-3"><Decision a={a} /></td>
                    <td className="px-4 py-3"><Risk v={a.risk_score} /></td>
                    <td className="px-4 py-3 text-muted">{a.status === "completed" && a.decision !== "APPROVE" ? a.fraud_label : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <aside className="rounded-2xl border border-line bg-surface p-5 lg:sticky lg:top-6 lg:self-start">
            {!picked ? (
              <p className="text-sm text-muted">Select an application to see why TrueID reached its decision and which of your own checks ran.</p>
            ) : (
              <div>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-lg font-semibold">{picked.applicant.name}</div>
                    <div className="text-sm tabular-nums text-muted">{picked.reference}, TrueID ID {picked.application_id}</div>
                  </div>
                  <Decision a={picked} />
                </div>
                {picked.status === "completed" && (
                  <>
                    <div className="mt-4 rounded-xl bg-mist/70 p-4 text-sm">
                      <div className="font-medium">{picked.fraud_label}</div>
                      <div className="mt-1 text-muted">Next step: {picked.recommended_action}</div>
                    </div>
                    <h3 className="mt-6 text-sm font-semibold">Why</h3>
                    {picked.reasons!.length === 0 ? <p className="mt-2 text-sm text-muted">No risk signals.</p> : (
                      <ul className="mt-2 space-y-2 text-sm">
                        {picked.reasons!.slice(0, 8).map((r) => (
                          <li key={r.module + r.code} className="flex gap-2">
                            <span className={clsx("mt-1.5 size-1.5 shrink-0 rounded-full", r.weight >= 0.4 ? "bg-err" : "bg-warn")} />
                            <span>{r.text} <span className="text-faint">({MODULES[r.module] ?? r.module})</span></span>
                          </li>
                        ))}
                      </ul>
                    )}
                    <h3 className="mt-6 text-sm font-semibold">Risk by area</h3>
                    <dl className="mt-2 space-y-1.5 text-sm">
                      {picked.modules!.map((m) => (
                        <div key={m.module} className="flex items-center justify-between gap-3">
                          <dt className="text-muted">{MODULES[m.module] ?? m.module}</dt><dd><Risk v={m.risk} /></dd>
                        </div>
                      ))}
                    </dl>
                  </>
                )}
                {picked.status === "error" && <p className="error mt-4">{picked.error}</p>}
                <h3 className="mt-6 text-sm font-semibold">Checks your onboarding ran</h3>
                <ul className="mt-2 grid grid-cols-1 gap-1.5 text-sm sm:grid-cols-2 lg:grid-cols-1">
                  {CHECKS.map(([k, label]) => {
                    const on = !!picked.partner_checks[k];
                    return (
                      <li key={k} className={clsx("flex items-center gap-2", !on && "text-faint")}>
                        {on ? <Check className="size-4 text-ok" /> : <Minus className="size-4" />}{label}
                      </li>
                    );
                  })}
                </ul>
                <p className="mt-3 text-xs text-muted">
                  ID card from {CAPTURE[picked.capture.card] ?? "unknown"}, selfie from {CAPTURE[picked.capture.selfie] ?? "unknown"}.
                </p>
              </div>
            )}
          </aside>
        </div>
      </main>
    </div>
  );
}
