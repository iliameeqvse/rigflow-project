import Link from "next/link";

export function Footer() {
  return (
    <footer className="border-t border-border bg-background">
      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-6 py-10 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2.5">
          <svg width="18" height="18" viewBox="0 0 24 24" className="text-accent" fill="none">
            <circle cx="12" cy="4" r="2" fill="currentColor" />
            <circle cx="12" cy="12" r="2" fill="currentColor" />
            <circle cx="12" cy="20" r="2" fill="currentColor" />
            <circle cx="4" cy="12" r="2" fill="currentColor" />
            <circle cx="20" cy="12" r="2" fill="currentColor" />
            <line x1="12" y1="4" x2="12" y2="20" stroke="currentColor" strokeWidth="1.25" />
            <line x1="4" y1="12" x2="20" y2="12" stroke="currentColor" strokeWidth="1.25" />
          </svg>
          <span className="font-mono text-xs tracking-[0.2em] text-muted">
            RIGFLOW · © {new Date().getFullYear()}
          </span>
        </div>

        <nav className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-muted-foreground">
          <Link href="/upload" className="hover:text-foreground">Upload</Link>
          <Link href="/animations" className="hover:text-foreground">Animations</Link>
          <Link href="/login" className="hover:text-foreground">Log in</Link>
          <Link href="/signup" className="hover:text-foreground">Sign up</Link>
        </nav>
      </div>
    </footer>
  );
}
