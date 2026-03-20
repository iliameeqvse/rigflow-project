"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { setAuthTokens } from "@/lib/auth";

interface LoginErrorShape {
  detail?: string;
  error?: string;
}

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const { data } = await api.post("/auth/login/", { email, password });
      if (data.access && data.refresh) {
        setAuthTokens(data.access, data.refresh);
      }
      router.replace("/");
    } catch (err: unknown) {
      const maybeError = err as {
        response?: { data?: LoginErrorShape };
        message?: string;
      };

      const msg =
        maybeError.response?.data?.detail ||
        maybeError.response?.data?.error ||
        maybeError.message ||
        "Login failed. Please check your credentials.";

      setError(String(msg));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto my-16 w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900 px-8 py-10 text-slate-100 shadow-2xl">
      <h1 className="text-3xl font-bold">Welcome back</h1>
      <p className="mt-2 text-slate-400">Sign in to manage your rigs and uploads.</p>

      {error && (
        <div className="mt-6 rounded-lg border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="mt-6 space-y-4">
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          placeholder="Email"
          className="w-full rounded-lg border border-slate-700 bg-slate-950 px-4 py-3"
        />

        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          placeholder="Password"
          className="w-full rounded-lg border border-slate-700 bg-slate-950 px-4 py-3"
        />

        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg bg-gradient-to-r from-violet-500 to-cyan-400 px-4 py-3 font-semibold text-slate-950 disabled:cursor-not-allowed disabled:from-slate-700 disabled:to-slate-700 disabled:text-slate-400"
        >
          {loading ? "Signing in..." : "Sign in"}
        </button>
      </form>
    </div>
  );
}