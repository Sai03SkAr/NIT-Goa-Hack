"use client";
import clsx from "clsx";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ShieldCheck, UserPlus } from "lucide-react";
import type { Band } from "@/lib/api";
import { TYPE_COLORS } from "@/lib/theme";

export { TYPE_COLORS };

export const bandColor: Record<string, string> = { APPROVE: "var(--approve)", REVIEW: "var(--review)", REJECT: "var(--reject)" };
const BAND_LABEL: Record<string, string> = { APPROVE: "Approved", REVIEW: "Needs review", REJECT: "Rejected" };

export function BandBadge({ band, size = "sm" }: { band?: Band | string | null; size?: "sm" | "lg" }) {
  if (!band) return null;
  const c = bandColor[band] ?? "var(--muted)";
  return (
    <span className={clsx("inline-flex items-center rounded-full font-medium whitespace-nowrap",
      size === "lg" ? "px-3.5 py-1 text-[15px]" : "px-2 py-px text-xs")}
      style={{ color: c, background: `color-mix(in srgb, ${c} 9%, var(--panel))`, border: `1px solid color-mix(in srgb, ${c} 28%, transparent)` }}>
      {BAND_LABEL[band] ?? band}
    </span>
  );
}

export function riskColor(r: number) {
  return r >= 0.7 ? "var(--reject)" : r >= 0.3 ? "var(--review)" : "var(--approve)";
}

/** Inline risk meter: a short bar with no background track, plus the number. */
export function RiskBar({ value, className }: { value: number; className?: string }) {
  return (
    <div className={clsx("h-1 w-full rounded-full bg-bg-2", className)}>
      <div className="h-full rounded-full" style={{ width: `${Math.max(3, value * 100)}%`, background: riskColor(value) }} />
    </div>
  );
}

export function Stat({ label, value, hint, accent }: { label: string; value: React.ReactNode; hint?: string; accent?: string }) {
  return (
    <div className="panel px-4 py-3.5">
      <div className="label">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums tracking-tight" style={{ color: accent }}>{value}</div>
      {hint && <div className="mt-0.5 text-xs text-dim">{hint}</div>}
    </div>
  );
}

export function SimBadge() {
  return <span className="chip" style={{ color: "var(--sim)", borderColor: "color-mix(in srgb, var(--sim) 35%, transparent)" }}>Simulated</span>;
}

export function Section({ title, right, children, className }: { title: string; right?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <section className={clsx("panel p-5", className)}>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-[15px] font-semibold">{title}</h3>
        {right}
      </div>
      {children}
    </section>
  );
}

export function Logo({ sub }: { sub?: string }) {
  return (
    <Link href="/" className="flex items-center gap-2.5">
      <span className="grid size-8 place-items-center rounded-lg bg-brand">
        <ShieldCheck className="size-[18px] text-white" strokeWidth={2.2} />
      </span>
      <span className="leading-tight">
        <span className="block font-semibold tracking-tight">TrueID Shield</span>
        {sub && <span className="block text-xs text-dim">{sub}</span>}
      </span>
    </Link>
  );
}

const NAV = [
  { href: "/dashboard", label: "Review queue" },
  { href: "/dashboard/graph", label: "Identity graph" },
  { href: "/dashboard/metrics", label: "Evaluation" },
  { href: "/dashboard/attack-lab", label: "Attack Lab" },
  { href: "/dashboard/chat", label: "Investigator" },
];

export function AnalystShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  return (
    <div className="min-h-[100dvh]">
      <header className="sticky top-0 z-30 border-b border-line bg-panel">
        <div className="mx-auto flex h-14 max-w-[1400px] items-center gap-8 px-6">
          <Logo />
          <nav className="flex h-full items-stretch gap-1 overflow-x-auto">
            {NAV.map(({ href, label }) => {
              const active = href === "/dashboard" ? path === href || path.startsWith("/dashboard/case") : path.startsWith(href);
              return (
                <Link key={href} href={href} className={clsx("flex items-center border-b-2 px-3 text-sm whitespace-nowrap transition-colors",
                  active ? "border-brand font-medium text-fg" : "border-transparent text-muted hover:text-fg")}>
                  {label}
                </Link>
              );
            })}
          </nav>
          <Link href="/kyc" className="btn ml-auto"><UserPlus className="size-4" />New application</Link>
        </div>
      </header>
      <main className="mx-auto max-w-[1400px] px-6 py-7">{children}</main>
    </div>
  );
}

export function TypeChip({ type, label }: { type: string; label?: string }) {
  if (!type || type === "none") return <span className="text-xs text-dim">None</span>;
  const c = TYPE_COLORS[type] ?? "#8a93a2";
  return <span className="chip" style={{ color: c, borderColor: `color-mix(in srgb, ${c} 35%, transparent)` }}>{label ?? type.replace("_", " ")}</span>;
}

export function pct(x?: number | null, d = 1) {
  return x == null ? "n/a" : `${(x * 100).toFixed(d)}%`;
}

export function PageHeader({ title, children, right }: { title: string; children?: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-[22px] font-semibold tracking-tight">{title}</h1>
        {children && <p className="mt-1 max-w-3xl text-sm leading-relaxed text-muted">{children}</p>}
      </div>
      {right}
    </div>
  );
}
