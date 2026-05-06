"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { listAnimations, type Animation } from "@/lib/api";

export default function AnimationLibraryPage() {
  const [animations, setAnimations] = useState<Animation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    listAnimations()
      .then(({ data }) => setAnimations(data))
      .catch(() => setError("Unable to load animations right now."))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return animations;
    return animations.filter(
      (a) =>
        a.name.toLowerCase().includes(q) ||
        a.tags.some((t) => t.toLowerCase().includes(q)) ||
        a.category?.name.toLowerCase().includes(q),
    );
  }, [animations, query]);

  return (
    <div className="relative isolate min-h-[100svh] overflow-hidden pt-32 pb-20">
      <div className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute -top-1/3 left-1/2 h-[55vh] w-[55vh] -translate-x-1/2 rounded-full bg-accent/10 blur-[140px] [animation:var(--animate-aurora-3)]" />
      </div>

      <div className="mx-auto w-full max-w-7xl px-6">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
          className="flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between"
        >
          <div>
            <span className="font-mono text-xs uppercase tracking-[0.25em] text-accent">
              // Library
            </span>
            <h1 className="mt-3 text-balance text-4xl font-bold tracking-[-0.02em] text-foreground sm:text-5xl">
              Animations
            </h1>
            <p className="mt-3 max-w-xl text-muted-foreground">
              Reusable clips ready for retargeting onto any rig. Browse what your
              team uploaded, or contribute your own.
            </p>
          </div>

          <Link
            href="/upload-animation"
            className="group inline-flex items-center gap-2 self-start rounded-full border border-border bg-surface/60 px-4 py-2 text-sm font-medium text-foreground backdrop-blur transition-colors hover:border-accent/50 sm:self-auto"
          >
            <PlusIcon className="h-4 w-4 text-accent" />
            Upload animation
          </Link>
        </motion.div>

        {/* Search */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.1 }}
          className="mt-8 flex items-center gap-3 rounded-full border border-border bg-surface/40 px-5 py-3 backdrop-blur focus-within:border-accent/40 focus-within:ring-2 focus-within:ring-accent/15"
        >
          <SearchIcon className="h-4 w-4 text-muted" />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by name, tag, or category…"
            className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted focus:outline-none"
          />
          {query && (
            <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted">
              {filtered.length} match{filtered.length === 1 ? "" : "es"}
            </span>
          )}
        </motion.div>

        {/* Loading skeletons */}
        {loading && (
          <div className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <div
                key={i}
                className="h-44 animate-pulse rounded-2xl border border-border bg-surface/40"
              />
            ))}
          </div>
        )}

        {/* Error */}
        {error && !loading && (
          <div className="mt-10 rounded-xl border border-danger/30 bg-danger/10 px-5 py-4 text-sm text-danger">
            {error}
          </div>
        )}

        {/* Empty */}
        {!loading && !error && animations.length === 0 && (
          <EmptyState />
        )}

        {/* No search match */}
        {!loading && !error && animations.length > 0 && filtered.length === 0 && (
          <div className="mt-10 rounded-xl border border-border bg-surface/40 px-6 py-10 text-center text-sm text-muted-foreground">
            No animations match{" "}
            <span className="font-mono text-foreground">&ldquo;{query}&rdquo;</span>.
          </div>
        )}

        {/* Grid */}
        {!loading && !error && filtered.length > 0 && (
          <div className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {filtered.map((animation, i) => (
              <Card key={animation.id} animation={animation} index={i} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function Card({ animation, index }: { animation: Animation; index: number }) {
  return (
    <motion.article
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: 0.5,
        delay: Math.min(index * 0.04, 0.3),
        ease: [0.16, 1, 0.3, 1],
      }}
      className="group relative overflow-hidden rounded-2xl border border-border bg-surface/60 p-5 backdrop-blur transition-all hover:-translate-y-0.5 hover:border-accent/40"
    >
      {/* Top accent strip on hover */}
      <span className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-accent/0 to-transparent transition-all duration-300 group-hover:via-accent/70" />

      <div className="flex items-start justify-between gap-3">
        <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-background/60 px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.2em] text-accent">
          <span className="h-1 w-1 rounded-full bg-accent" />
          {animation.category?.name ?? "Uncategorized"}
        </span>
        {animation.is_looping && (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-accent/10 px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.2em] text-accent">
            <LoopIcon className="h-2.5 w-2.5" />
            Loop
          </span>
        )}
      </div>

      <h2 className="mt-4 text-lg font-semibold tracking-[-0.01em] text-foreground">
        {animation.name}
      </h2>

      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] uppercase tracking-[0.18em] text-muted">
        <span>{animation.frame_rate} fps</span>
        <span className="text-border-strong">·</span>
        <span>{animation.duration_frames} frames</span>
        {animation.like_count > 0 && (
          <>
            <span className="text-border-strong">·</span>
            <span className="flex items-center gap-1">
              <HeartIcon className="h-3 w-3" />
              {animation.like_count}
            </span>
          </>
        )}
      </div>

      {animation.tags.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-1.5">
          {animation.tags.slice(0, 4).map((tag) => (
            <span
              key={tag}
              className="rounded-md border border-border bg-background/60 px-2 py-0.5 text-xs text-muted-foreground"
            >
              {tag}
            </span>
          ))}
          {animation.tags.length > 4 && (
            <span className="text-xs text-muted">+{animation.tags.length - 4}</span>
          )}
        </div>
      )}
    </motion.article>
  );
}

function EmptyState() {
  return (
    <div className="mt-12 flex flex-col items-center rounded-2xl border border-dashed border-border bg-surface/30 px-6 py-16 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-border bg-background text-accent">
        <FilmIcon className="h-6 w-6" />
      </div>
      <h2 className="mt-5 text-xl font-semibold text-foreground">
        Library&apos;s empty
      </h2>
      <p className="mt-2 max-w-sm text-sm text-muted-foreground">
        Upload your first animation to start building a shared library your
        team can retarget onto any rig.
      </p>
      <Link
        href="/upload-animation"
        className="group mt-6 inline-flex items-center gap-2 rounded-full bg-accent px-5 py-2.5 text-sm font-semibold text-background shadow-[var(--shadow-glow-accent)] transition-transform hover:scale-[1.02]"
      >
        Upload animation
        <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
      </Link>
    </div>
  );
}

function PlusIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={className} fill="none">
      <path d="M8 3v10M3 8h10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}
function SearchIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="7" />
      <line x1="20" y1="20" x2="16" y2="16" />
    </svg>
  );
}
function FilmIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <line x1="3" y1="9" x2="21" y2="9" />
      <line x1="3" y1="15" x2="21" y2="15" />
      <line x1="8" y1="4" x2="8" y2="20" />
      <line x1="16" y1="4" x2="16" y2="20" />
    </svg>
  );
}
function LoopIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={className} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 8a5 5 0 0 1 10 0" />
      <path d="M11 6l2 2-2 2" />
      <path d="M13 8a5 5 0 0 1-10 0" />
      <path d="M5 10l-2-2 2-2" />
    </svg>
  );
}
function HeartIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={className} fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
      <path d="M8 13s-5-3.4-5-7a3 3 0 0 1 5-2 3 3 0 0 1 5 2c0 3.6-5 7-5 7z" />
    </svg>
  );
}
function ArrowRight({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={className} fill="none">
      <path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
