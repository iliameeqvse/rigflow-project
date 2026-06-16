"use client";

import { ShaderAnimation } from "@/components/ui/shader-animation";

/**
 * Full-bleed backdrop built on <ShaderAnimation />.
 *
 * The raw shader renders bright RGB rays on pure black at full viewport size.
 * This wrapper keeps that animation clearly visible while fading it into the
 * brand background at the very top and bottom so it blends into the page.
 * Foreground content stays legible because the forms/headlines sit on their
 * own blurred cards above it.
 *
 * Drop it as the first child of a `relative` / `isolate` section. It is
 * absolutely positioned at `-z-10` and ignores pointer events.
 */
export function ShaderBackdrop({
  intensity = 0.9,
  className = "",
}: {
  /** Opacity of the shader layer (0–1). Lower = subtler. */
  intensity?: number;
  className?: string;
}) {
  return (
    <div
      aria-hidden
      className={`pointer-events-none absolute inset-0 -z-10 overflow-hidden bg-background ${className}`}
    >
      {/* The animated shader itself */}
      <div className="absolute inset-0" style={{ opacity: intensity }}>
        <ShaderAnimation />
      </div>

      {/* Soft vertical fades into the page background, top and bottom only,
          so the bright center of the animation stays visible. */}
      <div className="absolute inset-x-0 top-0 h-40 bg-gradient-to-b from-background to-transparent" />
      <div className="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-background to-transparent" />
    </div>
  );
}
