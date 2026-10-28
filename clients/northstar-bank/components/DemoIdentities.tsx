"use client";
/** Demo mode helper: identities that exist in the built-in mock registry, plus ways to trigger fraud signals.
 * Hidden when the site is connected to the real TrueID backend. Identical in both client sites. */
import { useEffect, useState } from "react";
import { FlaskConical, X } from "lucide-react";

type Id = { name: string; dob: string; gender: string; id_number: string; pan: string; phone: string };

export function DemoIdentities() {
  const [ids, setIds] = useState<Id[]>([]);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    fetch("/api/demo/identities").then((r) => r.json()).then((j) => setIds(j.identities ?? [])).catch(() => {});
  }, []);
  if (!ids.length) return null;
  return (
    <div className="relative z-40 flex justify-end">
      {/* panel */}
      {open && (
        <div role="dialog" aria-label="Test identities" className="absolute right-0 top-full mt-2 w-[min(calc(100vw-2rem),26rem)] max-h-[70vh] overflow-auto rounded-2xl border border-line bg-surface p-4 text-sm shadow-[0_18px_50px_-20px_rgba(0,0,0,.35)]">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="font-semibold">Test identities</div>
              <p className="mt-0.5 text-muted">Demo mode: TrueID isn&apos;t connected, so these are the only people in the mock registry.</p>
            </div>
            <button aria-label="Close" className="rounded-full p-1 text-muted hover:text-ink" onClick={() => setOpen(false)}><X className="size-4" /></button>
          </div>
          <ul className="mt-3 space-y-2">
            {ids.map((i) => (
              <li key={i.id_number} className="rounded-xl bg-mist/70 px-3 py-2">
                <div className="font-medium">{i.name}</div>
                <div className="mt-0.5 grid grid-cols-[auto_1fr] gap-x-3 tabular-nums text-muted">
                  <span>DOB</span><span className="select-all text-ink">{i.dob}</span>
                  <span>ID</span><span className="select-all text-ink">{i.id_number}</span>
                  <span>PAN</span><span className="select-all text-ink">{i.pan}</span>
                  <span>Mobile</span><span className="select-all text-ink">{i.phone}</span>
                </div>
              </li>
            ))}
          </ul>
          <div className="mt-3 font-medium">To see a rejection</div>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-muted">
            <li>Use a real ID number with a different name or date of birth.</li>
            <li>Submit the same ID number twice under two different names.</li>
            <li>Paste every field instead of typing, and submit within 20 seconds.</li>
          </ul>
        </div>
      )}
      <button onClick={() => setOpen(!open)} aria-expanded={open}
        className="inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3.5 py-1.5 text-sm font-medium">
        <FlaskConical className="size-4" />Test data
      </button>
    </div>
  );
}
