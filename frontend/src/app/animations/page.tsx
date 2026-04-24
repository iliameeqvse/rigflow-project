"use client";

import { useEffect, useState } from "react";
import { listAnimations, type Animation } from "@/lib/api";

export default function AnimationLibraryPage() {
  const [animations, setAnimations] = useState<Animation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listAnimations()
      .then(({ data }) => setAnimations(data))
      .catch(() => setError("Unable to load animations right now."))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-screen bg-slate-950 px-6 py-12 text-slate-100">
      <main className="mx-auto w-full max-w-6xl">
        <h1 className="text-3xl font-bold md:text-4xl">Animation library</h1>
        <p className="mt-2 text-slate-400">
          Reusable clips available for preview and retargeting.
        </p>

        {loading && <p className="mt-8 text-slate-300">Loading animations…</p>}
        {error && <p className="mt-8 text-rose-400">{error}</p>}

        {!loading && !error && animations.length === 0 && (
          <p className="mt-8 text-slate-300">
            No animations available yet. Upload one to start your library.
          </p>
        )}

        <section className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {animations.map((animation) => (
            <article
              key={animation.id}
              className="rounded-2xl border border-slate-800 bg-slate-900 p-5"
            >
              <p className="text-xs uppercase tracking-[0.2em] text-cyan-400">
                {animation.category?.name ?? "Uncategorized"}
              </p>
              <h2 className="mt-2 text-xl font-semibold">{animation.name}</h2>
              <div className="mt-4 flex flex-wrap gap-2 text-xs text-slate-300">
                <span className="rounded-full border border-slate-700 px-2 py-1">
                  {animation.frame_rate} fps
                </span>
                <span className="rounded-full border border-slate-700 px-2 py-1">
                  {animation.duration_frames} frames
                </span>
                <span className="rounded-full border border-slate-700 px-2 py-1">
                  {animation.is_looping ? "Loop" : "One-shot"}
                </span>
              </div>
              {animation.tags.length > 0 && (
                <p className="mt-4 text-sm text-slate-400">
                  Tags: {animation.tags.join(", ")}
                </p>
              )}
            </article>
          ))}
        </section>
      </main>
    </div>
  );
}