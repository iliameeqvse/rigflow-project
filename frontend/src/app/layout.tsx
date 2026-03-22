"use client";

import type { Metadata } from "next";
import Link from "next/link";
import { Geist, Geist_Mono } from "next/font/google";
import { useAuth } from "@/hooks/useAuth";
import { useState } from "react";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

function Header() {
  const { user, loggedIn, checked, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);

  // Avatar initials fallback
  const initials = user
    ? (user.username ?? user.email).slice(0, 2).toUpperCase()
    : "";

  return (
    <header
      style={{
        width: "100%",
        padding: "1rem 1.5rem",
        borderBottom: "1px solid #1f1f2e",
        background: "radial-gradient(circle at top left, #1b1b2f, #050510)",
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        boxSizing: "border-box",
        position: "relative",
        zIndex: 100,
      }}
    >
      {/* Logo */}
      <Link
        href="/"
        style={{
          fontSize: "1.2rem",
          fontWeight: 800,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: "#ffffff",
          textDecoration: "none",
        }}
      >
        Rigflow
      </Link>

      {/* Nav */}
      <nav style={{ display: "flex", gap: "0.75rem", alignItems: "center", fontSize: "0.9rem" }}>
        {/* Only render auth UI after we've checked localStorage (prevents flicker) */}
        {!checked ? null : loggedIn ? (
          /* ── Logged-in state ── */
          <div style={{ position: "relative" }}>
            <button
              onClick={() => setMenuOpen((o) => !o)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
                background: "rgba(108,99,255,0.15)",
                border: "1px solid rgba(108,99,255,0.4)",
                borderRadius: 999,
                padding: "0.35rem 0.75rem 0.35rem 0.4rem",
                cursor: "pointer",
                color: "#fff",
              }}
            >
              {/* Avatar circle */}
              <div
                style={{
                  width: 28,
                  height: 28,
                  borderRadius: "50%",
                  background: user?.avatar
                    ? "transparent"
                    : "linear-gradient(135deg,#6c63ff,#00d4ff)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: "0.7rem",
                  fontWeight: 700,
                  overflow: "hidden",
                  flexShrink: 0,
                }}
              >
                {user?.avatar ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={user.avatar} alt="avatar" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                ) : (
                  initials
                )}
              </div>
              <span style={{ fontWeight: 600, maxWidth: 100, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {user?.username ?? user?.email}
              </span>
              <span style={{ fontSize: "0.65rem", opacity: 0.7 }}>▼</span>
            </button>

            {/* Dropdown */}
            {menuOpen && (
              <div
                style={{
                  position: "absolute",
                  top: "calc(100% + 8px)",
                  right: 0,
                  background: "#12121e",
                  border: "1px solid #2a2a3d",
                  borderRadius: 10,
                  minWidth: 180,
                  boxShadow: "0 8px 30px rgba(0,0,0,0.5)",
                  overflow: "hidden",
                }}
              >
                <div style={{ padding: "0.6rem 1rem", borderBottom: "1px solid #1e1e2e", fontSize: "0.8rem", color: "#888" }}>
                  {user?.email}
                </div>
                <Link
                  href="/upload"
                  onClick={() => setMenuOpen(false)}
                  style={{ display: "block", padding: "0.7rem 1rem", color: "#ccc", textDecoration: "none", fontSize: "0.9rem" }}
                >
                  📦 Upload model
                </Link>
                <Link
                  href="/upload-animation"
                  onClick={() => setMenuOpen(false)}
                  style={{ display: "block", padding: "0.7rem 1rem", color: "#ccc", textDecoration: "none", fontSize: "0.9rem" }}
                >
                  🎞️ Upload animation
                </Link>
                <button
                  onClick={() => { setMenuOpen(false); logout(); }}
                  style={{
                    display: "block",
                    width: "100%",
                    textAlign: "left",
                    padding: "0.7rem 1rem",
                    background: "none",
                    border: "none",
                    borderTop: "1px solid #1e1e2e",
                    color: "#f87171",
                    cursor: "pointer",
                    fontSize: "0.9rem",
                  }}
                >
                  Sign out
                </button>
              </div>
            )}
          </div>
        ) : (
          /* ── Logged-out state ── */
          <>
            <Link href="/login" style={{ color: "#b0b0ff", textDecoration: "none" }}>
              Log in
            </Link>
            <Link
              href="/signup"
              style={{
                padding: "0.4rem 0.9rem",
                borderRadius: 999,
                border: "1px solid rgba(108,99,255,0.7)",
                background: "linear-gradient(135deg, rgba(108,99,255,0.3), rgba(0,212,255,0.3))",
                color: "#ffffff",
                textDecoration: "none",
                fontWeight: 600,
              }}
            >
              Get started
            </Link>
          </>
        )}
      </nav>

      {/* Close dropdown when clicking outside */}
      {menuOpen && (
        <div
          onClick={() => setMenuOpen(false)}
          style={{ position: "fixed", inset: 0, zIndex: -1 }}
        />
      )}
    </header>
  );
}

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
        <Header />
        <main>{children}</main>
      </body>
    </html>
  );
}