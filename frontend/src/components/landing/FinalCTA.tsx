"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { Reveal } from "./Reveal";
import { useAuth } from "@/hooks/useAuth";

export function FinalCTA() {
  const { loggedIn, checked } = useAuth();
  const isAuthed = checked && loggedIn;
  const primaryHref = isAuthed ? "/upload" : "/signup";
  const primaryLabel = isAuthed ? "Upload a model" : "Start rigging — it's free";

  return (
    <section className="relative overflow-hidden py-32 sm:py-40">
      {/* Animated radial */}
      <div className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute left-1/2 top-1/2 h-[80vh] w-[80vh] -translate-x-1/2 -translate-y-1/2 rounded-full bg-accent/15 blur-[180px] [animation:var(--animate-aurora-1)]" />
      </div>

      {/* Conic ring */}
      <motion.div
        aria-hidden
        animate={{ rotate: 360 }}
        transition={{ duration: 60, repeat: Infinity, ease: "linear" }}
        className="pointer-events-none absolute left-1/2 top-1/2 h-[800px] w-[800px] -translate-x-1/2 -translate-y-1/2 opacity-30"
        style={{
          background:
            "conic-gradient(from 0deg, transparent 0deg, rgba(163,230,53,0.4) 90deg, transparent 180deg, rgba(139,92,246,0.3) 270deg, transparent 360deg)",
          maskImage: "radial-gradient(circle, transparent 50%, black 51%, transparent 70%)",
          WebkitMaskImage: "radial-gradient(circle, transparent 50%, black 51%, transparent 70%)",
        }}
      />

      <div className="relative mx-auto max-w-3xl px-6 text-center">
        <Reveal>
          <span className="font-mono text-xs uppercase tracking-[0.25em] text-accent">
            {"// Ship it"}
          </span>
        </Reveal>

        <Reveal delay={0.08}>
          <h2 className="mt-5 text-balance text-5xl font-bold leading-[1.05] tracking-[-0.03em] text-foreground sm:text-6xl">
            Drop a mesh.{" "}
            <span className="bg-gradient-to-br from-accent to-accent-soft bg-clip-text text-transparent">
              Get a rigged character.
            </span>
          </h2>
        </Reveal>

        <Reveal delay={0.16}>
          <p className="mx-auto mt-6 max-w-xl text-pretty text-lg text-muted-foreground">
            Free to start. No credit card. Your first rig is ready before your
            coffee finishes brewing.
          </p>
        </Reveal>

        <Reveal delay={0.24}>
          <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
            <Link
              href={primaryHref}
              className="group relative inline-flex items-center gap-2 overflow-hidden rounded-full bg-accent px-7 py-3.5 text-sm font-semibold text-background shadow-[var(--shadow-glow-accent)] transition-transform hover:scale-[1.02] active:scale-[0.98]"
            >
              <span className="relative z-10">{primaryLabel}</span>
              <ArrowRight className="relative z-10 h-4 w-4 transition-transform group-hover:translate-x-0.5" />
              <span className="pointer-events-none absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/45 to-transparent group-hover:animate-[shimmer_1.1s_ease-in-out]" />
            </Link>
            {!isAuthed && (
              <Link
                href="/login"
                className="inline-flex items-center gap-2 rounded-full border border-border bg-surface/40 px-6 py-3.5 text-sm font-medium text-foreground backdrop-blur transition-colors hover:border-border-strong hover:bg-surface"
              >
                Log in
              </Link>
            )}
            {isAuthed && (
              <Link
                href="/animations"
                className="inline-flex items-center gap-2 rounded-full border border-border bg-surface/40 px-6 py-3.5 text-sm font-medium text-foreground backdrop-blur transition-colors hover:border-border-strong hover:bg-surface"
              >
                Browse animations
              </Link>
            )}
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function ArrowRight({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" fill="none" className={className}>
      <path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
