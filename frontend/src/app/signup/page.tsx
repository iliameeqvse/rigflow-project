"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import api, { extractApiError, saveAuth } from "@/lib/api";

export default function SignupPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [username, setUsername] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const { data } = await api.post("/auth/register/", { email, password, username });
      saveAuth(data.access, data.refresh, data.user);
      window.dispatchEvent(new Event("authchange"));
      router.push("/");
    } catch (err: unknown) {
      setError(extractApiError(err, "Sign up failed. Please try again."));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative isolate min-h-[100svh] overflow-hidden pt-32 pb-16">
      <div className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute -top-1/3 right-1/4 h-[60vh] w-[60vh] rounded-full bg-accent/15 blur-[140px] [animation:var(--animate-aurora-2)]" />
        <div className="absolute bottom-0 left-1/4 h-[55vh] w-[55vh] rounded-full bg-cyan/20 blur-[140px] [animation:var(--animate-aurora-1)]" />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 16, filter: "blur(8px)" }}
        animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
        transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
        className="relative mx-auto w-full max-w-md px-6"
      >
        <div className="overflow-hidden rounded-2xl border border-border bg-surface/70 backdrop-blur-xl shadow-[var(--shadow-soft)]">
          <div className="h-px bg-gradient-to-r from-transparent via-accent/60 to-transparent" />

          <div className="px-8 py-10">
            <span className="font-mono text-xs uppercase tracking-[0.25em] text-accent">
              {"// Get started"}
            </span>
            <h1 className="mt-3 text-3xl font-bold tracking-[-0.02em] text-foreground">
              Create your account
            </h1>
            <p className="mt-2 text-sm text-muted-foreground">
              Free forever. Save rigs, share animations, sync devices.
            </p>

            <AnimatePresence>
              {error && (
                <motion.div
                  initial={{ opacity: 0, y: -8, height: 0 }}
                  animate={{ opacity: 1, y: 0, height: "auto" }}
                  exit={{ opacity: 0, y: -8, height: 0 }}
                  className="mt-5 overflow-hidden"
                  role="alert"
                >
                  <div className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-2.5 text-sm text-danger">
                    {error}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            <form onSubmit={handleSubmit} className="mt-6 grid gap-4">
              <Field label="Email" htmlFor="email">
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoComplete="email"
                  className={inputCls}
                />
              </Field>

              <Field label="Username" htmlFor="username">
                <input
                  id="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                  autoComplete="username"
                  className={inputCls}
                />
              </Field>

              <Field label="Password" htmlFor="password" hint="min 8 chars">
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={8}
                  autoComplete="new-password"
                  className={inputCls}
                />
              </Field>

              <PrimaryButton loading={loading} loadingLabel="Creating account…">
                Create account
              </PrimaryButton>

              <p className="text-center text-sm text-muted">
                Already have an account?{" "}
                <Link href="/login" className="font-medium text-accent hover:underline">
                  Sign in
                </Link>
              </p>
            </form>
          </div>
        </div>
      </motion.div>
    </div>
  );
}

const inputCls =
  "w-full rounded-lg border border-border bg-background/60 px-4 py-2.5 text-foreground placeholder:text-muted transition-colors focus:border-accent/50 focus:bg-background focus:outline-none focus:ring-2 focus:ring-accent/15";

function Field({
  label,
  htmlFor,
  children,
  hint,
}: {
  label: string;
  htmlFor: string;
  children: React.ReactNode;
  hint?: React.ReactNode;
}) {
  return (
    <div>
      <label
        htmlFor={htmlFor}
        className="mb-1.5 flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground"
      >
        <span>{label}</span>
        {hint && <span className="normal-case tracking-normal text-muted">{hint}</span>}
      </label>
      {children}
    </div>
  );
}

function PrimaryButton({
  children,
  loading,
  loadingLabel,
}: {
  children: React.ReactNode;
  loading?: boolean;
  loadingLabel?: string;
}) {
  return (
    <button
      type="submit"
      disabled={loading}
      className="group relative mt-2 flex h-11 w-full items-center justify-center overflow-hidden rounded-full bg-accent font-semibold text-background shadow-[var(--shadow-glow-accent)] transition-transform hover:scale-[1.01] active:scale-[0.99] disabled:cursor-wait disabled:opacity-80"
    >
      <span className="relative z-10 flex items-center gap-2 text-sm">
        {loading && <Spinner />}
        {loading ? loadingLabel : children}
      </span>
      {!loading && (
        <span className="pointer-events-none absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/45 to-transparent group-hover:animate-[shimmer_1.1s_ease-in-out]" />
      )}
    </button>
  );
}

function Spinner() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4 animate-spin" fill="none">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" opacity="0.25" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}
