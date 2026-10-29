"use client";
import clsx from "clsx";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { BarChart3, Inbox, KeyRound, LogOut, Menu, MessagesSquare, Network, ShieldCheck, Sparkles, Swords, UserPlus, X } from "lucide-react";
import { type Band, ApiError, get, post } from "@/lib/api";
import { TYPE_COLORS } from "@/lib/theme";
import { AssistantDock } from "@/components/Assistant";

export { TYPE_COLORS };

export const bandColor: Record<string, string> = { APPROVE: "var(--approve)", REVIEW: "var(--review)", REJECT: "var(--reject)" };
export const BAND_LABEL: Record<string, string> = { APPROVE: "Approved", REVIEW: "Needs review", REJECT: "Rejected" };
const BAND_STAMP: Record<string, string> = { APPROVE: "Approved", REVIEW: "Review", REJECT: "Rejected" };

/** Small stamp-style decision label for lists: uppercase display type on a tinted plate. */
export function BandBadge({ band, size = "sm" }: { band?: Band | string | null; size?: "sm" | "lg" }) {
  if (!band) return null;
  const c = bandColor[band] ?? "var(--muted)";
  return (
    <span className={clsx("inline-flex items-center rounded-[6px] font-[family-name:var(--font-bricolage)] font-bold uppercase whitespace-nowrap tracking-[0.1em]",
      size === "lg" ? "px-3 py-1 text-[13px]" : "px-2 py-0.5 text-[11.5px]")}
      style={{ color: c, background: `color-mix(in srgb, ${c} 10%, var(--panel))` }}>
      {BAND_STAMP[band] ?? band}
    </span>
  );
}

/** The case verdict as a tilted rubber stamp. */
export function Stamp({ band }: { band: Band | string }) {
  return <span className="stamp" style={{ color: bandColor[band] ?? "var(--muted)" }}>{BAND_STAMP[band] ?? band}</span>;
}

export function riskColor(r: number) {
  return r >= 0.7 ? "var(--reject)" : r >= 0.3 ? "var(--review)" : "var(--approve)";
}
export const riskWord = (r: number) => (r >= 0.7 ? "High" : r >= 0.3 ? "Medium" : "Low");

/** Inline risk meter on a soft track, coloured by band. */
export function RiskBar({ value, className }: { value: number; className?: string }) {
  return (
    <div className={clsx("h-1.5 w-full rounded-full bg-bg-2", className)}>
      <div className="h-full rounded-full" style={{ width: `${Math.max(3, value * 100)}%`, background: riskColor(value) }} />
    </div>
  );
}

/** Ring gauge for one probability: the number, its band word, never a bare score. */
export function RiskRing({ value, size = 84, label = "fraud risk" }: { value: number | null; size?: number; label?: string }) {
  const r = (size - 10) / 2, c = 2 * Math.PI * r;
  const v = value ?? 0, col = value == null ? "var(--dim)" : riskColor(v);
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--bg-2)" strokeWidth={8} />
        {value != null && <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={col} strokeWidth={8} strokeLinecap="round"
          strokeDasharray={`${Math.max(0.02, v) * c} ${c}`} />}
      </svg>
      <div className="absolute inset-0 grid place-content-center text-center leading-tight">
        <span className="mono text-[17px] font-semibold tabular-nums" style={{ color: col }}>{value == null ? "n/a" : v.toFixed(2)}</span>
        <span className="text-[10.5px] text-dim">{value == null ? "model off" : `${riskWord(v)} ${label.split(" ").pop()}`}</span>
      </div>
    </div>
  );
}

const TONES: Record<string, string> = { brand: "var(--brand)", approve: "var(--approve)", review: "var(--review)", reject: "var(--reject)", muted: "var(--muted)" };

/** KPI tile: label with an icon, a big display number, and one line of context. */
export function Stat({ label, value, hint, accent, icon: Icon, tone }: { label: string; value: React.ReactNode; hint?: string; accent?: string; icon?: any; tone?: keyof typeof TONES }) {
  const c = tone ? TONES[tone] : accent;
  return (
    <div className="panel flex flex-col gap-1 p-5">
      <div className="flex items-center gap-2 text-[13px] text-dim">
        {Icon && <Icon className="size-4" strokeWidth={2} style={{ color: c ?? "var(--brand)" }} />}<span className="truncate">{label}</span>
      </div>
      <div className="display mt-2 text-[32px] leading-none tabular-nums" style={{ color: tone ? undefined : accent }}>{value}</div>
      {hint && <div className="mt-1 text-[12.5px] leading-snug text-dim">{hint}</div>}
    </div>
  );
}

export function SimBadge() {
  return <span className="chip" style={{ color: "var(--sim)", borderColor: "color-mix(in srgb, var(--sim) 35%, transparent)" }}>Simulated</span>;
}

export function Section({ title, sub, right, children, className, pad = true }: { title: string; sub?: string; right?: React.ReactNode; children: React.ReactNode; className?: string; pad?: boolean }) {
  return (
    <section className={clsx("panel", pad && "p-5", className)}>
      <div className={clsx("mb-4 flex flex-wrap items-start justify-between gap-3", !pad && "px-5 pt-5")}>
        <div>
          <h3 className="display text-[17px]">{title}</h3>
          {sub && <p className="mt-0.5 text-[13px] text-dim">{sub}</p>}
        </div>
        {right}
      </div>
      {children}
    </section>
  );
}

export function EmptyState({ icon: Icon = Inbox, title, children }: { icon?: any; title: string; children?: React.ReactNode }) {
  return (
    <div className="grid place-items-center px-6 py-14 text-center">
      <span className="grid size-11 place-items-center rounded-2xl bg-bg-2 text-dim"><Icon className="size-5" /></span>
      <p className="mt-3 font-medium">{title}</p>
      {children && <p className="mt-1 max-w-md text-sm text-muted">{children}</p>}
    </div>
  );
}

/** Initials avatar, coloured from the name so the same person always looks the same. */
export function Avatar({ name, size = 32 }: { name: string; size?: number }) {
  const init = name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase() || "?";
  const hue = [...name].reduce((h, ch) => (h * 31 + ch.charCodeAt(0)) % 360, 7);
  return (
    <span className="grid shrink-0 place-items-center rounded-[10px] font-semibold" aria-hidden
      style={{ width: size, height: size, fontSize: size * 0.38, color: `hsl(${hue} 45% 32%)`, background: `hsl(${hue} 70% 94%)` }}>{init}</span>
  );
}

export function Logo({ sub }: { sub?: string }) {
  return (
    <Link href="/" className="flex items-center gap-2.5">
      <span className="grid size-8 place-items-center rounded-[9px] bg-ink">
        <ShieldCheck className="size-[18px] text-white" strokeWidth={2.2} />
      </span>
      <span className="leading-tight">
        <span className="display block text-[16px] tracking-[-0.01em]">TrueID Shield</span>
        {sub && <span className="block text-xs text-dim">{sub}</span>}
      </span>
    </Link>
  );
}

const NAV = [
  { group: "Operations", items: [
    { href: "/dashboard", label: "Review queue", icon: Inbox },
    { href: "/dashboard/graph", label: "Identity graph", icon: Network },
    { href: "/dashboard/chat", label: "Investigator", icon: MessagesSquare },
  ] },
  { group: "Insights", items: [
    { href: "/dashboard/metrics", label: "Evaluation", icon: BarChart3 },
    { href: "/dashboard/attack-lab", label: "Attack Lab", icon: Swords },
    { href: "/dashboard/learning", label: "Learning loop", icon: Sparkles },
  ] },
];

/** The console is analyst-only: the server enforces it, this just asks for the key once per session. */
function SignIn({ onDone }: { onDone: () => void }) {
  const [key, setKey] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setErr("");
    try { await post("/api/auth/login", { key }); onDone(); }
    catch (x) { setErr(x instanceof ApiError && x.status === 401 ? "That key is not right." : x instanceof ApiError && x.status === 429 ? "Too many attempts. Wait a minute." : String(x)); }
    finally { setBusy(false); }
  }
  return (
    <div className="grid min-h-[100dvh] place-items-center bg-[radial-gradient(60%_50%_at_50%_0%,var(--brand-soft),transparent)] px-6">
      <form onSubmit={submit} className="panel w-full max-w-sm p-7 shadow-[var(--shadow-lg)]">
        <Logo />
        <h1 className="display mt-6 text-[22px]">Analyst sign-in</h1>
        <p className="mt-1 text-sm text-muted">Case files hold identity documents, so the console needs the analyst key. It is in <span className="mono text-xs">backend/.secrets/analyst_key</span> on the server.</p>
        <label className="mt-5 block">
          <span className="label">Analyst key</span>
          <input type="password" autoComplete="current-password" className="input mono mt-1.5" value={key} onChange={(e) => setKey(e.target.value)} autoFocus />
        </label>
        {err && <p className="mt-2 text-sm text-reject">{err}</p>}
        <button className="btn btn-primary mt-5 w-full" disabled={!key || busy}><KeyRound className="size-4" />{busy ? "Signing in…" : "Sign in"}</button>
        <Link href="/kyc" className="mt-4 block text-center text-xs text-dim underline-offset-2 hover:underline">Applying for an account? Go to verification</Link>
      </form>
    </div>
  );
}

function NavLinks({ path, onNavigate }: { path: string; onNavigate?: () => void }) {
  return (
    <nav className="space-y-5">
      {NAV.map(({ group, items }) => (
        <div key={group}>
          <div className="eyebrow px-3 pb-1.5">{group}</div>
          <ul className="space-y-0.5">
            {items.map(({ href, label, icon: Icon }) => {
              const active = href === "/dashboard" ? path === href || path.startsWith("/dashboard/case") : path.startsWith(href);
              return (
                <li key={href}>
                  <Link href={href} onClick={onNavigate} aria-current={active ? "page" : undefined}
                    className={clsx("flex items-center gap-2.5 rounded-[10px] px-3 py-2 text-sm transition-colors",
                      active ? "bg-ink font-medium text-white" : "text-muted hover:bg-bg-2 hover:text-fg")}>
                    <Icon className="size-[17px]" strokeWidth={active ? 2.2 : 1.9} />{label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

export function AnalystShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const [auth, setAuth] = useState<boolean | null>(null);
  const [open, setOpen] = useState(false);
  const check = () => get<{ analyst: boolean }>("/api/auth/me").then((r) => setAuth(r.analyst)).catch(() => setAuth(false));
  useEffect(() => { check(); }, []);
  if (auth === null) return <div className="grid min-h-[100dvh] place-items-center text-sm text-dim">Loading…</div>;
  if (!auth) return <SignIn onDone={check} />;
  const signOut = () => post("/api/auth/logout").then(() => setAuth(false));
  return (
    <div className="min-h-[100dvh] lg:grid lg:grid-cols-[248px_1fr]">
      {/* sidebar (desktop) */}
      <aside className="sticky top-0 hidden h-[100dvh] flex-col border-r border-line bg-panel px-3 py-5 lg:flex">
        <div className="px-2"><Logo sub="Analyst console" /></div>
        <div className="mt-7 flex-1 overflow-y-auto"><NavLinks path={path} /></div>
        <div className="space-y-2 border-t border-line px-1 pt-4">
          <Link href="/kyc" className="btn btn-primary w-full"><UserPlus className="size-4" />New application</Link>
          <button className="btn btn-ghost w-full justify-start text-muted" onClick={signOut}><LogOut className="size-4" />Sign out</button>
        </div>
      </aside>
      {/* top bar (mobile / tablet) */}
      <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-line bg-panel px-4 lg:hidden">
        <Logo />
        <button className="btn btn-ghost" aria-label="Menu" onClick={() => setOpen((o) => !o)}>{open ? <X className="size-5" /> : <Menu className="size-5" />}</button>
      </header>
      {open && (
        <div className="fixed inset-x-0 top-14 z-30 border-b border-line bg-panel p-4 shadow-[var(--shadow-lg)] lg:hidden">
          <NavLinks path={path} onNavigate={() => setOpen(false)} />
          <div className="mt-4 flex gap-2"><Link href="/kyc" className="btn btn-primary flex-1"><UserPlus className="size-4" />New application</Link>
            <button className="btn" onClick={signOut} aria-label="Sign out"><LogOut className="size-4" /></button></div>
        </div>
      )}
      <main className="min-w-0 px-4 pb-24 pt-6 sm:px-6 lg:px-8 lg:pt-8"><div className="mx-auto max-w-[1360px]">{children}</div></main>
      <AssistantDock />
    </div>
  );
}

export function TypeChip({ type, label }: { type: string; label?: string }) {
  if (!type || type === "none") return <span className="text-xs text-dim">None</span>;
  const c = TYPE_COLORS[type] ?? "#8a93a2";
  return (
    <span className="chip" style={{ color: c, borderColor: `color-mix(in srgb, ${c} 30%, transparent)`, background: `color-mix(in srgb, ${c} 6%, var(--panel))` }}>
      <span className="size-1.5 rounded-full" style={{ background: c }} aria-hidden />{label ?? type.replace("_", " ")}
    </span>
  );
}

export function pct(x?: number | null, d = 1) {
  return x == null ? "n/a" : `${(x * 100).toFixed(d)}%`;
}

/** "2026-10-29T14:05:00" -> "Today 14:05" / "Yesterday 09:12" / "27 Oct 16:40". */
export function when(ts?: string) {
  if (!ts) return "";
  const d = new Date(ts), now = new Date();
  const day = (x: Date) => x.toDateString();
  const hm = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  if (day(d) === day(now)) return `Today ${hm}`;
  if (day(d) === day(new Date(now.getTime() - 864e5))) return `Yesterday ${hm}`;
  return `${d.toLocaleDateString("en-GB", { day: "numeric", month: "short" })} ${hm}`;
}

export function PageHeader({ title, children, right, eyebrow }: { title: string; children?: React.ReactNode; right?: React.ReactNode; eyebrow?: string }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        {eyebrow && <div className="eyebrow mb-1">{eyebrow}</div>}
        <h1 className="display text-[32px] leading-[1.1]">{title}</h1>
        {children && <p className="mt-1 max-w-3xl text-sm leading-relaxed text-muted">{children}</p>}
      </div>
      {right && <div className="flex flex-wrap items-center gap-2">{right}</div>}
    </div>
  );
}

/** One finding in plain language. The internal code stays available on hover for analysts and logs. */
export function Finding({ text, code, weight = 0.3 }: { text: string; code?: string; weight?: number }) {
  const color = weight < 0 ? "var(--approve)" : weight >= 0.4 ? "var(--reject)" : weight > 0 ? "var(--review)" : "var(--dim)";
  return (
    <li className="flex items-start gap-2.5 text-sm leading-snug" title={code}>
      <span className="mt-[7px] size-1.5 shrink-0 rounded-full" style={{ background: color }} aria-hidden />
      <span className="text-fg">{text}</span>
    </li>
  );
}

/** Summaries cite codes in [BRACKETS] so the LLM guardrail can check them; readers don't need to see them. */
export const readable = (text?: string) => (text ?? "").replace(/\s*\[[A-Z0-9_]+\]/g, "");

const AREA: Record<string, string> = { doc: "Card", bio: "Face", beh: "Behaviour", reg: "Registry", cor: "Linked applications" };
const WORDS: Record<string, string> = { sim: "SIM", qr: "QR", ocr: "OCR", pan: "PAN", ks: "keystroke", iki: "key interval",
  vel: "velocity", ckyc: "CKYC", cv: "variation", dob: "DOB", id: "ID", comp: "cluster", ip: "IP", "24h": "24 h", "7d": "7 days", "1h": "1 h" };
/** doc_risk -> "Card: risk"; reg_sim_age_days -> "Registry: SIM age days". */
export function featureLabel(f: string) {
  const [area, ...rest] = f.split("_");
  const words = rest.map((w) => WORDS[w] ?? w).join(" ");
  return AREA[area] ? `${AREA[area]}: ${words}` : f.replaceAll("_", " ");
}
