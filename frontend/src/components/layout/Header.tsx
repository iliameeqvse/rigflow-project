"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useAuth } from "@/hooks/useAuth";

export function Header() {
  const { user, loggedIn, checked, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const initials = user
    ? (user.username ?? user.email).slice(0, 2).toUpperCase()
    : "";

  return (
    <header
      className={`fixed top-0 inset-x-0 z-50 transition-all duration-300 ${
        scrolled
          ? "bg-background/70 backdrop-blur-xl border-b border-border/60"
          : "bg-transparent border-b border-transparent"
      }`}
    >
      <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
        <Link href="/" className="group flex items-center gap-2.5">
          <LogoMark />
          <span className="font-mono text-sm font-semibold tracking-[0.18em] text-foreground">
            RIGFLOW
          </span>
        </Link>

        <nav className="hidden md:flex items-center gap-8 text-sm text-muted-foreground">
          <a href="#pipeline" className="hover:text-foreground transition-colors">
            Pipeline
          </a>
          <a href="#features" className="hover:text-foreground transition-colors">
            Features
          </a>
          <Link href="/animations" className="hover:text-foreground transition-colors">
            Animations
          </Link>
        </nav>

        <div className="flex items-center gap-2">
          {!checked ? (
            <div className="h-9 w-32" />
          ) : loggedIn ? (
            <div className="relative">
              <button
                onClick={() => setMenuOpen((o) => !o)}
                className="flex items-center gap-2 rounded-full border border-border bg-surface/60 backdrop-blur px-2.5 py-1.5 text-sm transition-colors hover:border-border-strong"
              >
                <div className="flex h-7 w-7 items-center justify-center overflow-hidden rounded-full bg-gradient-to-br from-accent to-accent-soft text-[0.7rem] font-bold text-background">
                  {user?.avatar ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={user.avatar} alt="" className="h-full w-full object-cover" />
                  ) : (
                    initials
                  )}
                </div>
                <span className="max-w-[110px] truncate font-medium text-foreground">
                  {user?.username ?? user?.email}
                </span>
                <ChevronIcon className={`h-3 w-3 text-muted transition-transform ${menuOpen ? "rotate-180" : ""}`} />
              </button>

              <AnimatePresence>
                {menuOpen && (
                  <>
                    <div
                      onClick={() => setMenuOpen(false)}
                      className="fixed inset-0 z-40"
                    />
                    <motion.div
                      initial={{ opacity: 0, y: -8, scale: 0.98 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, y: -8, scale: 0.98 }}
                      transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
                      className="absolute right-0 top-[calc(100%+8px)] z-50 min-w-[220px] overflow-hidden rounded-xl border border-border-strong bg-surface shadow-2xl"
                    >
                      <div className="px-4 py-3 border-b border-border text-xs text-muted">
                        {user?.email}
                      </div>
                      <MenuLink href="/upload" onClick={() => setMenuOpen(false)}>
                        Upload model
                      </MenuLink>
                      <MenuLink href="/upload-animation" onClick={() => setMenuOpen(false)}>
                        Upload animation
                      </MenuLink>
                      <MenuLink href="/animations" onClick={() => setMenuOpen(false)}>
                        Animation library
                      </MenuLink>
                      <button
                        onClick={() => {
                          setMenuOpen(false);
                          logout();
                        }}
                        className="block w-full border-t border-border px-4 py-2.5 text-left text-sm text-danger transition-colors hover:bg-surface-2"
                      >
                        Sign out
                      </button>
                    </motion.div>
                  </>
                )}
              </AnimatePresence>
            </div>
          ) : (
            <>
              <Link
                href="/login"
                className="rounded-full px-4 py-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
              >
                Log in
              </Link>
              <Link
                href="/signup"
                className="group relative overflow-hidden rounded-full bg-accent px-4 py-2 text-sm font-semibold text-background transition-transform hover:scale-[1.02] active:scale-[0.98]"
              >
                <span className="relative z-10">Get started</span>
                <span className="pointer-events-none absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/40 to-transparent group-hover:animate-[shimmer_1s_ease-in-out]" />
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}

function MenuLink({
  href,
  onClick,
  children,
}: {
  href: string;
  onClick?: () => void;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      onClick={onClick}
      className="block px-4 py-2.5 text-sm text-muted-foreground transition-colors hover:bg-surface-2 hover:text-foreground"
    >
      {children}
    </Link>
  );
}

function LogoMark() {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      className="text-accent transition-transform group-hover:rotate-12"
      fill="none"
    >
      <circle cx="12" cy="4" r="2" fill="currentColor" />
      <circle cx="12" cy="12" r="2" fill="currentColor" />
      <circle cx="12" cy="20" r="2" fill="currentColor" />
      <circle cx="4" cy="12" r="2" fill="currentColor" />
      <circle cx="20" cy="12" r="2" fill="currentColor" />
      <line x1="12" y1="4" x2="12" y2="20" stroke="currentColor" strokeWidth="1.25" />
      <line x1="4" y1="12" x2="20" y2="12" stroke="currentColor" strokeWidth="1.25" />
    </svg>
  );
}

function ChevronIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 12 12" className={className} fill="none">
      <path d="M3 5l3 3 3-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
