"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import { motion } from "framer-motion";
import { useAuth } from "@/hooks/useAuth";

const HeroScene = dynamic(() => import("./HeroScene"), { ssr: false });

const headline = ["Auto-rig", "characters", "in", "seconds."];

export function Hero() {
  const { loggedIn, checked } = useAuth();
  const primaryHref = checked && loggedIn ? "/upload" : "/signup";
  const primaryLabel = checked && loggedIn ? "Open the app" : "Try it free";

  return (
    <section className="relative isolate min-h-[100svh] overflow-hidden pt-32 pb-24">
      {/* Aurora gradient background */}
      <div className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute -top-1/3 -left-1/4 h-[80vh] w-[80vh] rounded-full bg-accent/20 blur-[140px] [animation:var(--animate-aurora-1)]" />
        <div className="absolute top-1/4 -right-1/4 h-[70vh] w-[70vh] rounded-full bg-violet/25 blur-[140px] [animation:var(--animate-aurora-2)]" />
        <div className="absolute bottom-0 left-1/3 h-[60vh] w-[60vh] rounded-full bg-accent/15 blur-[160px] [animation:var(--animate-aurora-3)]" />
      </div>

      {/* Subtle grid */}
      <div
        className="pointer-events-none absolute inset-0 -z-10 opacity-[0.18]"
        style={{
          backgroundImage:
            "linear-gradient(to right, rgba(163,230,53,0.08) 1px, transparent 1px), linear-gradient(to bottom, rgba(163,230,53,0.08) 1px, transparent 1px)",
          backgroundSize: "64px 64px",
          maskImage:
            "radial-gradient(ellipse at center, black 30%, transparent 75%)",
          WebkitMaskImage:
            "radial-gradient(ellipse at center, black 30%, transparent 75%)",
        }}
      />

      <div className="relative mx-auto grid max-w-7xl grid-cols-1 items-center gap-10 px-6 lg:grid-cols-[1.1fr_1fr]">
        <div>
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
            className="inline-flex items-center gap-2 rounded-full border border-border bg-surface/60 px-3 py-1.5 backdrop-blur"
          >
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-accent" />
            </span>
            <span className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
              v1.0 · auto-rigging pipeline
            </span>
          </motion.div>

          <h1 className="mt-7 text-balance text-5xl font-bold leading-[1.05] tracking-[-0.03em] text-foreground sm:text-6xl lg:text-[5.5rem]">
            {headline.map((word, i) => (
              <motion.span
                key={i}
                initial={{ opacity: 0, y: 28, filter: "blur(10px)" }}
                animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                transition={{
                  duration: 0.85,
                  delay: 0.15 + i * 0.08,
                  ease: [0.16, 1, 0.3, 1],
                }}
                className="mr-[0.25em] inline-block"
              >
                {word === "in" ? (
                  <span className="bg-gradient-to-br from-accent to-accent-soft bg-clip-text text-transparent">
                    {word}
                  </span>
                ) : word === "seconds." ? (
                  <span className="bg-gradient-to-br from-accent to-accent-soft bg-clip-text text-transparent">
                    {word}
                  </span>
                ) : (
                  word
                )}
              </motion.span>
            ))}
          </h1>

          <motion.p
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.6, ease: [0.16, 1, 0.3, 1] }}
            className="mt-6 max-w-xl text-pretty text-lg text-muted-foreground sm:text-xl"
          >
            Drop a mesh. RigFlow runs Blender + Rigify in the cloud and hands
            you a production-ready GLB rig — bones, weights, and all.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.75, ease: [0.16, 1, 0.3, 1] }}
            className="mt-9 flex flex-wrap items-center gap-3"
          >
            <Link
              href={primaryHref}
              className="group relative inline-flex items-center gap-2 overflow-hidden rounded-full bg-accent px-6 py-3 text-sm font-semibold text-background shadow-[var(--shadow-glow-accent)] transition-transform hover:scale-[1.02] active:scale-[0.98]"
            >
              <span className="relative z-10">{primaryLabel}</span>
              <ArrowRight className="relative z-10 h-4 w-4 transition-transform group-hover:translate-x-0.5" />
              <span className="pointer-events-none absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/45 to-transparent group-hover:animate-[shimmer_1.1s_ease-in-out]" />
            </Link>
            <a
              href="#pipeline"
              className="group inline-flex items-center gap-2 rounded-full border border-border bg-surface/40 px-6 py-3 text-sm font-medium text-foreground backdrop-blur transition-colors hover:border-border-strong hover:bg-surface"
            >
              See the pipeline
              <ChevronDown className="h-4 w-4 text-muted transition-transform group-hover:translate-y-0.5" />
            </a>
          </motion.div>

          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 1, delay: 1.1 }}
            className="mt-12 flex flex-wrap items-center gap-x-6 gap-y-2 font-mono text-[11px] uppercase tracking-[0.2em] text-muted"
          >
            <span className="flex items-center gap-2">
              <Dot /> Blender + Rigify
            </span>
            <span className="flex items-center gap-2">
              <Dot /> .fbx · .glb · .obj
            </span>
            <span className="flex items-center gap-2">
              <Dot /> GLB output
            </span>
          </motion.div>
        </div>

        <motion.div
          initial={{ opacity: 0, scale: 0.94 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 1.1, delay: 0.4, ease: [0.16, 1, 0.3, 1] }}
          className="relative h-[420px] sm:h-[520px] lg:h-[620px]"
        >
          <div className="absolute inset-0">
            <HeroScene />
          </div>
          {/* Frame */}
          <div className="pointer-events-none absolute inset-4 rounded-2xl border border-border/40" />
          <div className="pointer-events-none absolute left-4 top-4 font-mono text-[10px] uppercase tracking-[0.2em] text-muted">
            armature.preview
          </div>
          <div className="pointer-events-none absolute right-4 bottom-4 font-mono text-[10px] uppercase tracking-[0.2em] text-accent">
            ● live
          </div>
        </motion.div>
      </div>

      {/* Bottom fade into next section */}
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-32 bg-gradient-to-b from-transparent to-background" />
    </section>
  );
}

function Dot() {
  return <span className="inline-block h-1 w-1 rounded-full bg-accent" />;
}

function ArrowRight({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" fill="none" className={className}>
      <path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ChevronDown({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" fill="none" className={className}>
      <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
