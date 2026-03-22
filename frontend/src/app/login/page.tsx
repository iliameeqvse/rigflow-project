"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import api, { saveAuth } from "@/lib/api";

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
      saveAuth(data.access, data.refresh, data.user);
      // Tell the header to re-read localStorage right now
      window.dispatchEvent(new Event("authchange"));
      router.push("/");
    } catch (err: any) {
      const data = err.response?.data;
      let msg = "Login failed. Please check your credentials.";
      if (data) {
        if (data.detail) {
          msg = data.detail;
        } else if (typeof data === "object") {
          const firstKey = Object.keys(data)[0];
          const val = data[firstKey];
          msg = Array.isArray(val) ? val[0] : String(val);
        }
      }
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        maxWidth: 420,
        margin: "4rem auto",
        padding: "2.5rem 2rem",
        borderRadius: 16,
        background: "radial-gradient(circle at top, #141422, #050510)",
        border: "1px solid #27273a",
        boxShadow: "0 18px 45px rgba(0,0,0,0.55)",
      }}
    >
      <h1 style={{ fontSize: "1.6rem", fontWeight: 800, marginBottom: "0.5rem" }}>
        Welcome back
      </h1>
      <p style={{ color: "#a0a0c0", marginBottom: "1.8rem" }}>
        Sign in to manage your rigs and uploads.
      </p>

      {error && (
        <div
          style={{
            background: "rgba(255,107,107,0.06)",
            border: "1px solid rgba(255,107,107,0.3)",
            borderRadius: 10,
            padding: "0.75rem 1rem",
            color: "#ff8585",
            fontSize: "0.9rem",
            marginBottom: "1.4rem",
          }}
        >
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} style={{ display: "grid", gap: "1.1rem" }}>
        <div>
          <label style={{ display: "block", marginBottom: "0.4rem", fontSize: "0.9rem", fontWeight: 600 }}>
            Email
          </label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            style={{
              width: "100%", padding: "0.75rem 1rem", borderRadius: 10,
              border: "1px solid #2b2b3e", background: "#060612",
              color: "#ffffff", boxSizing: "border-box",
            }}
          />
        </div>

        <div>
          <label style={{ display: "block", marginBottom: "0.4rem", fontSize: "0.9rem", fontWeight: 600 }}>
            Password
          </label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            style={{
              width: "100%", padding: "0.75rem 1rem", borderRadius: 10,
              border: "1px solid #2b2b3e", background: "#060612",
              color: "#ffffff", boxSizing: "border-box",
            }}
          />
        </div>

        <button
          type="submit"
          disabled={loading}
          style={{
            marginTop: "0.5rem", width: "100%", padding: "0.85rem",
            borderRadius: 999, border: "none",
            background: loading ? "#26263a" : "linear-gradient(135deg, #6c63ff, #00d4ff)",
            color: "#ffffff", fontWeight: 700,
            cursor: loading ? "wait" : "pointer",
          }}
        >
          {loading ? "Signing in…" : "Sign in"}
        </button>

        <p style={{ textAlign: "center", color: "#888", fontSize: "0.875rem", margin: 0 }}>
          Don&apos;t have an account?{" "}
          <a href="/signup" style={{ color: "#a78bfa", textDecoration: "none" }}>Sign up</a>
        </p>
      </form>
    </div>
  );
}