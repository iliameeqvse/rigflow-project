"use client";

const ITEMS = [
  ".fbx",
  "auto-skinned",
  ".glb",
  "rigify metarig",
  ".gltf",
  "FK + IK controls",
  ".obj",
  "T-pose detection",
  "blender headless",
  "GLB export",
  "websocket progress",
  "no manual cleanup",
];

export function Marquee() {
  return (
    <div className="relative overflow-hidden border-y border-border bg-surface/30 py-6">
      {/* Edge fades */}
      <div className="pointer-events-none absolute inset-y-0 left-0 z-10 w-32 bg-gradient-to-r from-background to-transparent" />
      <div className="pointer-events-none absolute inset-y-0 right-0 z-10 w-32 bg-gradient-to-l from-background to-transparent" />

      <div className="flex w-max items-center [animation:var(--animate-marquee)]">
        <Track />
        <Track aria-hidden />
      </div>
    </div>
  );
}

function Track({ "aria-hidden": ariaHidden }: { "aria-hidden"?: boolean }) {
  return (
    <ul aria-hidden={ariaHidden} className="flex shrink-0 items-center gap-10 px-5">
      {ITEMS.map((item, i) => (
        <li key={`${item}-${i}`} className="flex items-center gap-10">
          <span className="font-mono text-sm uppercase tracking-[0.22em] text-muted-foreground">
            {item}
          </span>
          <span className="h-1 w-1 rounded-full bg-accent/60" />
        </li>
      ))}
    </ul>
  );
}
