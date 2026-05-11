"use client";

import { motion, useMotionValue, useSpring, useTransform } from "framer-motion";
import { ReactNode, useRef } from "react";
import { Reveal } from "./Reveal";

const FEATURES = [
  {
    title: "Rigify metarig",
    body:
      "Industry-standard humanoid skeleton, fit to your mesh bounds with FK/IK controls baked in.",
    icon: <ArmatureIcon />,
  },
  {
    title: "Custom landmarks",
    body:
      "Override auto-fit with six landmarks — chin, wrists, groin, ankles — placed in the 3D editor.",
    icon: <LandmarkIcon />,
  },
  {
    title: "Animation library",
    body:
      "Browse, upload, and retarget reusable clips. Approved animations are shared across your team.",
    icon: <AnimateIcon />,
  },
  {
    title: "GLB export",
    body:
      "Skinned, weight-painted GLB ready for Three.js, Unity, Unreal — no manual cleanup.",
    icon: <ExportIcon />,
  },
  {
    title: "Live progress",
    body:
      "WebSocket updates stream rig status as Blender processes your mesh — no polling, no refresh.",
    icon: <LiveIcon />,
  },
  {
    title: "Resilient reruns",
    body:
      "A failed rerig keeps your previous good GLB serving. Specific error codes, not silent breakage.",
    icon: <ShieldIcon />,
  },
];

export function Features() {
  return (
    <section id="features" className="relative py-32 sm:py-40">
      <div className="mx-auto max-w-7xl px-6">
        <Reveal className="max-w-3xl">
          <span className="font-mono text-xs uppercase tracking-[0.25em] text-accent">
            {"// What's inside"}
          </span>
          <h2 className="mt-4 text-balance text-4xl font-bold tracking-[-0.02em] text-foreground sm:text-5xl">
            Built for the boring parts you&apos;d rather skip.
          </h2>
          <p className="mt-5 max-w-2xl text-lg text-muted-foreground">
            Every feature exists because we got tired of the same step ourselves.
            Sensible defaults, but everything is overridable.
          </p>
        </Reveal>

        <div className="mt-16 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f, i) => (
            <Reveal key={f.title} delay={(i % 3) * 0.06}>
              <FeatureCard title={f.title} body={f.body} icon={f.icon} />
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

function FeatureCard({
  title,
  body,
  icon,
}: {
  title: string;
  body: string;
  icon: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const mx = useMotionValue(0);
  const my = useMotionValue(0);
  const rotateX = useSpring(useTransform(my, [-0.5, 0.5], [6, -6]), {
    stiffness: 200,
    damping: 18,
  });
  const rotateY = useSpring(useTransform(mx, [-0.5, 0.5], [-6, 6]), {
    stiffness: 200,
    damping: 18,
  });
  const glareX = useTransform(mx, [-0.5, 0.5], ["0%", "100%"]);
  const glareY = useTransform(my, [-0.5, 0.5], ["0%", "100%"]);

  function onMove(e: React.MouseEvent<HTMLDivElement>) {
    const r = ref.current?.getBoundingClientRect();
    if (!r) return;
    mx.set((e.clientX - r.left) / r.width - 0.5);
    my.set((e.clientY - r.top) / r.height - 0.5);
  }
  function onLeave() {
    mx.set(0);
    my.set(0);
  }

  return (
    <motion.div
      ref={ref}
      onMouseMove={onMove}
      onMouseLeave={onLeave}
      style={{ rotateX, rotateY, transformStyle: "preserve-3d" }}
      className="group relative h-full overflow-hidden rounded-2xl border border-border bg-surface/70 p-7 backdrop-blur transition-colors hover:border-border-strong"
    >
      {/* Glare */}
      <motion.div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300 group-hover:opacity-100"
        style={{
          background: useTransform(
            [glareX, glareY],
            ([x, y]) =>
              `radial-gradient(circle 240px at ${x} ${y}, rgba(163,230,53,0.18), transparent 60%)`,
          ),
        }}
      />
      <div className="relative" style={{ transform: "translateZ(20px)" }}>
        <div className="inline-flex h-11 w-11 items-center justify-center rounded-lg border border-border bg-background text-accent">
          {icon}
        </div>
        <h3 className="mt-5 text-lg font-semibold text-foreground">{title}</h3>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          {body}
        </p>
      </div>
    </motion.div>
  );
}

/* Icons (Lucide-ish strokes) */
function ArmatureIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="4" r="1.5" />
      <circle cx="12" cy="12" r="1.5" />
      <circle cx="12" cy="20" r="1.5" />
      <circle cx="6" cy="9" r="1.25" />
      <circle cx="18" cy="9" r="1.25" />
      <line x1="12" y1="5.5" x2="12" y2="10.5" />
      <line x1="12" y1="13.5" x2="12" y2="18.5" />
      <line x1="11" y1="11.5" x2="7" y2="9.5" />
      <line x1="13" y1="11.5" x2="17" y2="9.5" />
    </svg>
  );
}
function LandmarkIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="2" fill="currentColor" stroke="none" />
      <line x1="12" y1="3" x2="12" y2="6" />
      <line x1="12" y1="18" x2="12" y2="21" />
      <line x1="3" y1="12" x2="6" y2="12" />
      <line x1="18" y1="12" x2="21" y2="12" />
    </svg>
  );
}
function AnimateIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="6,4 20,12 6,20" />
    </svg>
  );
}
function ExportIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3v12" />
      <path d="M7 8l5-5 5 5" />
      <path d="M5 21h14" />
    </svg>
  );
}
function LiveIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 12c2-4 5-6 9-6s7 2 9 6c-2 4-5 6-9 6s-7-2-9-6z" />
      <circle cx="12" cy="12" r="2.2" fill="currentColor" stroke="none" />
    </svg>
  );
}
function ShieldIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6l8-3z" />
      <path d="M9 12l2 2 4-4" />
    </svg>
  );
}
