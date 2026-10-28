"use client";
import clsx from "clsx";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, FlaskConical, GitBranch, LayoutList, MessageSquareText, ShieldCheck, UserPlus } from "lucide-react";
import type { Band } from "@/lib/api";

export const bandColor: Record<string, string> = { APPROVE: "var(--approve)", REVIEW: "var(--review)", REJECT: "var(--reject)" };

export function BandBadge({ band, size = "sm" }: { band?: Band | string | null; size?: "sm" | "lg" }) {
  if (!band) return null;
  const c = bandColor[band] ?? "var(--muted)";
  return (
    <span className={clsx("inline-flex items-center gap-1.5 rounded-full font-semibold tracking-wide",
      size === "lg" ? "px-4 py-1.5 text-base" : "px-2.5 py-0.5 text-[11px]")}
      style={{ color: c, background: `color-mix(in srgb, ${c} 13%, transparent)`, border: `1px solid color-mix(in srgb, ${c} 35%, transparent)` }}>
      <span className="size-1.5 rounded-full" style={{ background: c }} />{band}
    </span>
  );
}

export function riskColor(r: number) {
  return r >= 0.7 ? "var(--reject)" : r >= 0.3 ? "var(--review)" : "var(--approve)";
}

export function RiskBar({ value, className }: { value: number; className?: string }) {
  return (
    <div className={clsx("h-1.5 w-full overflow-hidden rounded-full bg-white/5", className)}>
      <div className="h-full rounded-full transition-all duration-700" style={{ width: `${Math.max(2, value * 100)}%`, background: riskColor(value) }} />
    </div>
  );
}

export function Stat({ label, value, hint, accent }: { label: string; value: React.ReactNode; hint?: string; accent?: string }) {
  return (
    <div className="panel p-4">
      <div className="label">{label}</div>
      <div className="mt-1.5 text-2xl font-semibold tabular-nums" style={{ color: accent }}>{value}</div>
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </div>
  );
}

export function SimBadge() {
  return <span className="chip" style={{ color: "var(--sim)", borderColor: "color-mix(in srgb, var(--sim) 40%, transparent)" }}>SIMULATED</span>;
}

export function Section({ title, right, children, className }: { title: string; right?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <section className={clsx("panel p-5", className)}>
      <div className="mb-4 flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold tracking-wide text-fg/90">{title}</h3>
        {right}
      </div>
      {children}
    </section>
  );
}

export function Logo() {
  return (
    <Link href="/" className="flex items-center gap-2.5">
      <span className="grid size-8 place-items-center rounded-lg" style={{ background: "linear-gradient(135deg,#5eead4,#22d3ee)" }}>
        <ShieldCheck className="size-5 text-[#04201d]" strokeWidth={2.4} />
      </span>
      <span className="font-semibold tracking-tight">TrueID <span className="text-brand">Shield</span></span>
    </Link>
  );
}

const NAV = [
  { href: "/dashboard", label: "Queue", icon: LayoutList },
  { href: "/dashboard/graph", label: "Identity graph", icon: GitBranch },
  { href: "/dashboard/metrics", label: "Metrics", icon: Activity },
  { href: "/dashboard/attack-lab", label: "Attack Lab", icon: FlaskConical },
  { href: "/dashboard/chat", label: "Investigator", icon: MessageSquareText },
];

export function AnalystShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 border-b border-line bg-bg/80 backdrop-blur">
        <div className="mx-auto flex max-w-[1400px] items-center gap-6 px-6 py-3">
          <Logo />
          <nav className="flex items-center gap-1">
            {NAV.map(({ href, label, icon: I }) => {
              const active = href === "/dashboard" ? path === href || path.startsWith("/dashboard/case") : path.startsWith(href);
              return (
                <Link key={href} href={href} className={clsx("flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm transition",
                  active ? "bg-white/5 text-fg" : "text-muted hover:text-fg")}>
                  <I className="size-4" />{label}
                </Link>
              );
            })}
          </nav>
          <div className="ml-auto flex items-center gap-3">
            <span className="chip"><span className="size-1.5 rounded-full bg-approve" />Analyst console</span>
            <Link href="/kyc" className="btn"><UserPlus className="size-4" />New applicant</Link>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-[1400px] px-6 py-6">{children}</main>
    </div>
  );
}

export const TYPE_COLORS: Record<string, string> = {
  none: "#64748b", first_party: "#f472b6", third_party: "#c084fc", ring: "#fb7185", bot: "#fbbf24",
  tampered: "#38bdf8", injection: "#f97316",
};

export function TypeChip({ type, label }: { type: string; label?: string }) {
  if (!type || type === "none") return <span className="text-xs text-dim">—</span>;
  const c = TYPE_COLORS[type] ?? "#94a3b8";
  return <span className="chip" style={{ color: c, borderColor: `color-mix(in srgb, ${c} 40%, transparent)` }}>{label ?? type.replace("_", " ")}</span>;
}

export function pct(x?: number | null, d = 1) {
  return x == null ? "—" : `${(x * 100).toFixed(d)}%`;
}
