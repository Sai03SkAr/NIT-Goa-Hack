import Link from "next/link";

/** Four-point star mark: the one place the brass accent lives. */
export function Star({ className = "size-5" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden>
      <path d="M12 1.5 14.2 9.8 22.5 12 14.2 14.2 12 22.5 9.8 14.2 1.5 12 9.8 9.8Z" fill="var(--color-brass)" />
    </svg>
  );
}

export function Logo() {
  return (
    <Link href="/" className="flex items-center gap-2 text-[1.05rem] font-semibold tracking-[-0.01em] text-ink">
      <Star />
      Northstar Bank
    </Link>
  );
}

export function Header({ right }: { right?: React.ReactNode }) {
  return (
    <header className="border-b border-line bg-surface">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
        <Logo />
        <div className="text-sm text-muted">{right}</div>
      </div>
    </header>
  );
}
