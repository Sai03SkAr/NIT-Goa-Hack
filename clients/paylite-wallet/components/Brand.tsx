import Link from "next/link";

export function Mark({ className = "size-7" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <rect width="32" height="32" rx="9" fill="var(--color-mango)" />
      <path d="M10 23V9h7a5 5 0 0 1 0 10h-4" stroke="var(--color-plum)" strokeWidth="3.2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function Logo({ light = false }: { light?: boolean }) {
  return (
    <Link href="/" className={`flex items-center gap-2 text-lg font-bold tracking-[-0.02em] ${light ? "text-white" : "text-ink"}`}>
      <Mark />PayLite
    </Link>
  );
}
