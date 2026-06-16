"use client";

import { motion, useInView, useScroll, useTransform } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { Reveal } from "./Reveal";
import ShaderBackground from "@/components/ui/shader-background";

const STEPS = [
  {
    n: "01",
    title: "Upload mesh",
    body:
      "Drop an .fbx, .glb, .gltf, or .obj. We normalize scale, axis, and units automatically.",
    code: ["POST /api/v1/rigs/", "→ accept fbx | glb | gltf | obj", "→ status: pending"],
  },
  {
    n: "02",
    title: "Auto-rig with Rigify",
    body:
      "A headless Blender worker fits a Rigify metarig to your mesh — or to landmarks you place.",
    code: ["blender --background", "  --python autorig.py", "  --bones armature.json"],
  },
  {
    n: "03",
    title: "Download rigged GLB",
    body:
      "Skinned mesh, weighted, exported as GLB. Drop straight into Three.js, Unity, or Unreal.",
    code: ["GET /api/v1/rigs/:id", "→ status: complete", "→ rigged_glb.url"],
  },
];

export function Pipeline() {
  const sectionRef = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({
    target: sectionRef,
    offset: ["start end", "end start"],
  });
  const lineHeight = useTransform(scrollYProgress, [0.1, 0.7], ["0%", "100%"]);

  return (
    <section
      id="pipeline"
      ref={sectionRef}
      className="relative isolate py-32 sm:py-40"
    >
      {/* Animated lime shader backdrop, scoped to this section */}
      <div aria-hidden className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
        <ShaderBackground className="absolute inset-0 h-full w-full" />
        {/* Scrim + edge fades keep the steps and code blocks legible */}
        <div className="absolute inset-0 bg-background/70" />
        <div className="absolute inset-x-0 top-0 h-40 bg-gradient-to-b from-background to-transparent" />
        <div className="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-background to-transparent" />
      </div>

      <div className="mx-auto max-w-7xl px-6">
        <Reveal className="max-w-3xl">
          <span className="font-mono text-xs uppercase tracking-[0.25em] text-accent">
            {"// Pipeline"}
          </span>
          <h2 className="mt-4 text-balance text-4xl font-bold tracking-[-0.02em] text-foreground sm:text-5xl">
            Three steps. No rigging chair time.
          </h2>
          <p className="mt-5 max-w-xl text-lg text-muted-foreground">
            What used to take hours of bone placement and weight painting now
            runs end-to-end in the cloud while you do something else.
          </p>
        </Reveal>

        <div className="relative mt-20">
          {/* Vertical progress line */}
          <div
            aria-hidden
            className="absolute left-[27px] top-0 hidden h-full w-px bg-border md:block"
          />
          <motion.div
            aria-hidden
            style={{ height: lineHeight }}
            className="absolute left-[27px] top-0 hidden w-px bg-gradient-to-b from-accent via-accent to-transparent md:block"
          />

          <ol className="space-y-12 md:space-y-16">
            {STEPS.map((step, i) => (
              <Reveal key={step.n} delay={i * 0.08}>
                <li className="relative grid grid-cols-1 gap-6 md:grid-cols-[80px_1fr] md:gap-10">
                  <div className="relative">
                    <div className="relative z-10 flex h-14 w-14 items-center justify-center rounded-full border border-border bg-surface font-mono text-sm text-accent shadow-[var(--shadow-soft)]">
                      <span className="absolute inset-0 rounded-full bg-accent/10 blur-md" />
                      <span className="relative">{step.n}</span>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 lg:items-start">
                    <div>
                      <h3 className="text-2xl font-semibold tracking-[-0.01em] text-foreground sm:text-3xl">
                        {step.title}
                      </h3>
                      <p className="mt-3 max-w-md text-muted-foreground">
                        {step.body}
                      </p>
                    </div>

                    <CodeBlock lines={step.code} />
                  </div>
                </li>
              </Reveal>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}

function CodeBlock({ lines }: { lines: string[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-80px" });
  const [progress, setProgress] = useState(0);

  // Total characters across all lines drive the typing progress.
  const totalChars = lines.reduce((sum, l) => sum + l.length, 0);

  useEffect(() => {
    if (!inView) return;
    let raf = 0;
    let i = 0;
    const tick = () => {
      i = Math.min(i + 1, totalChars);
      setProgress(i);
      if (i < totalChars) raf = window.setTimeout(tick, 18) as unknown as number;
    };
    raf = window.setTimeout(tick, 280) as unknown as number;
    return () => window.clearTimeout(raf);
  }, [inView, totalChars]);

  // Slice lines according to progress.
  const sliced: string[] = [];
  let remaining = progress;
  for (const line of lines) {
    if (remaining <= 0) {
      sliced.push("");
      continue;
    }
    if (remaining >= line.length) {
      sliced.push(line);
      remaining -= line.length;
    } else {
      sliced.push(line.slice(0, remaining));
      remaining = 0;
    }
  }

  const typing = progress < totalChars;
  const activeLineIndex = sliced.findIndex((s, i) => s.length < lines[i].length);

  return (
    <div ref={ref} className="overflow-hidden rounded-xl border border-border bg-surface/70 backdrop-blur">
      <div className="flex items-center gap-1.5 border-b border-border px-4 py-2.5">
        <span className="h-2.5 w-2.5 rounded-full bg-border-strong" />
        <span className="h-2.5 w-2.5 rounded-full bg-border-strong" />
        <span className="h-2.5 w-2.5 rounded-full bg-border-strong" />
        <span className="ml-3 font-mono text-[10px] uppercase tracking-[0.2em] text-muted">
          rigflow.api
        </span>
        {typing && inView && (
          <span className="ml-auto flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.2em] text-accent">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
            live
          </span>
        )}
      </div>
      <pre className="px-4 py-4 font-mono text-[12.5px] leading-relaxed">
        {sliced.map((text, i) => {
          const isActive = i === activeLineIndex;
          return (
            <div key={i} className="flex items-start gap-3 min-h-[1.4em]">
              <span className="select-none text-muted/50">{String(i + 1).padStart(2, "0")}</span>
              <span className={i === 0 ? "text-accent" : "text-muted-foreground"}>
                {text}
                {isActive && typing && (
                  <span className="ml-0.5 inline-block h-[1em] w-[2px] -mb-[2px] animate-pulse bg-accent align-middle" />
                )}
              </span>
            </div>
          );
        })}
      </pre>
    </div>
  );
}
