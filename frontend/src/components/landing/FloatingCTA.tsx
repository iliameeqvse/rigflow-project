"use client";

import Link from "next/link";
import { motion, AnimatePresence, useMotionValueEvent, useScroll } from "framer-motion";
import { useState } from "react";
import { useAuth } from "@/hooks/useAuth";

export function FloatingCTA() {
  const { loggedIn, checked } = useAuth();
  const [visible, setVisible] = useState(false);
  const { scrollY } = useScroll();

  // Show after the user has scrolled ~70% of the first viewport — past the
  // hero, where the original CTAs are no longer in view.
  useMotionValueEvent(scrollY, "change", (y) => {
    if (typeof window === "undefined") return;
    const threshold = window.innerHeight * 0.7;
    setVisible(y > threshold);
  });

  const isAuthed = checked && loggedIn;
  const href = isAuthed ? "/upload" : "/signup";
  const label = isAuthed ? "Open the app" : "Try RigFlow free";

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0, y: 24, scale: 0.92 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 24, scale: 0.92 }}
          transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
          className="fixed bottom-6 right-6 z-50 sm:bottom-8 sm:right-8"
        >
          <Link
            href={href}
            className="group relative flex items-center gap-2 overflow-hidden rounded-full bg-accent px-5 py-3 text-sm font-semibold text-background shadow-[0_8px_30px_-4px_rgba(204,255,0,0.5)] transition-transform hover:scale-[1.03] active:scale-[0.98]"
          >
            {/* Pulsing glow halo */}
            <span className="pointer-events-none absolute inset-0 -z-10 rounded-full bg-accent blur-xl opacity-50 animate-pulse" />
            <BoltIcon className="h-4 w-4" />
            <span className="relative z-10">{label}</span>
            <span className="pointer-events-none absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/45 to-transparent group-hover:animate-[shimmer_1.1s_ease-in-out]" />
          </Link>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function BoltIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={className} fill="currentColor">
      <path d="M9 1L3 9h4l-1 6 6-8H8l1-6z" />
    </svg>
  );
}
