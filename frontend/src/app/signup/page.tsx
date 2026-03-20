"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

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
      await api.post("/auth/register/", { email, password, username });
      router.push("/login");
    } catch (err: unknown) {
      const maybeError = err as {
        response?: { data?: Record<string, unknown> | string };
      };
      const data = maybeError.response?.data;

      let msg = "Sign up failed. Please try again.";
      if (data) {
        if (typeof data === "object") {
          const firstKey = Object.keys(data)[0];
          const firstVal = data[firstKey];
          msg = Array.isArray(firstVal)
            ? `${firstKey}: ${firstVal[0]}`
            : data.detail || data.error || msg;
        } else if (typeof data === "string") {
          msg = data;
        }
      }

      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto my-16 w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900 px-8 py-10 text-slate-100 shadow-2xl">
      <h1 className="text-3xl font-bold">Create your RigFlow account</h1>
      <p className="mt-2 text-slate-400">Save rigs, upload animations, and sync projects.</p>

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
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
          placeholder="Username"
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
          {loading ? "Creating account..." : "Create account"}
        </button>
      </form>
    </div>
  );
}