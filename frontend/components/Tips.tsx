"use client";
import { CheckCircle2, Lightbulb, UserCheck } from "lucide-react";

export type Tip = { check: string; title: string; steps: string[]; blocking: boolean; why: string; resolution_rate: number | null; seen: number | null };
export type Coaching = { app_id: string; headline: string; tips: Tip[]; manual_review: boolean; note: string | null };

/** What an applicant can fix, in the order it matters. Shown to applicants and previewed by analysts. */
export function ApplicantTips({ c, compact = false }: { c: Coaching; compact?: boolean }) {
  const done = !c.tips.length && !c.manual_review;
  return (
    <div className="space-y-3">
      <div className="flex items-start gap-3">
        <span className={`grid size-9 shrink-0 place-items-center rounded-xl ${done ? "bg-[color-mix(in_srgb,var(--approve)_12%,var(--panel))] text-approve" : "bg-brand-soft text-brand"}`}>
          {done ? <CheckCircle2 className="size-5" /> : c.tips.length ? <Lightbulb className="size-5" /> : <UserCheck className="size-5" />}
        </span>
        <div>
          <p className="font-medium leading-snug">{c.headline}</p>
          {c.note && <p className="mt-0.5 text-sm text-muted">{c.note}</p>}
        </div>
      </div>
      {c.tips.length > 0 && (
        <ol className="space-y-2.5">
          {c.tips.map((t, i) => (
            <li key={t.check} className="rounded-xl border border-line bg-panel p-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="mono grid size-6 place-items-center rounded-md bg-ink text-xs text-white">{i + 1}</span>
                <span className="font-medium">{t.title}</span>
                {t.blocking && <span className="chip text-review">needed for approval</span>}
              </div>
              <ul className={`mt-2.5 space-y-1.5 text-sm text-muted ${compact ? "" : "pl-8"}`}>
                {t.steps.map((s) => <li key={s} className="flex gap-2"><span className="mt-[7px] size-1 shrink-0 rounded-full bg-dim" />{s}</li>)}
              </ul>
              {t.resolution_rate != null && t.seen != null && t.seen >= 5 && (
                <p className="mt-2.5 text-xs text-dim">Usually resolved: {Math.round(t.resolution_rate * 100)}% of people held for this were approved in the end.</p>
              )}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
