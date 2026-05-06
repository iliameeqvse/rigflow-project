import { useCallback, useSyncExternalStore } from "react";
import { clearAuth, StoredUser } from "@/lib/api";

// Subscribes to both same-tab "authchange" events (dispatched manually by
// login/signup/logout) and cross-tab "storage" events.
function subscribe(callback: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  const onStorage = (e: StorageEvent) => {
    if (e.key === "user" || e.key === "access" || e.key === null) callback();
  };
  window.addEventListener("authchange", callback);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener("authchange", callback);
    window.removeEventListener("storage", onStorage);
  };
}

// localStorage.getItem returns the same string for unchanged data, but
// JSON.parse produces a fresh object every call. useSyncExternalStore
// requires the snapshot to be referentially stable when nothing changed,
// so we cache the parsed user against the raw localStorage string.
let cachedRaw: string | null = null;
let cachedUser: StoredUser | null = null;

function getSnapshot(): StoredUser | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem("user");
  if (raw === cachedRaw) return cachedUser;
  cachedRaw = raw;
  try {
    cachedUser = raw ? (JSON.parse(raw) as StoredUser) : null;
  } catch {
    cachedUser = null;
  }
  return cachedUser;
}

function getServerSnapshot(): StoredUser | null {
  // No localStorage on the server — emit null so SSR markup doesn't claim a
  // logged-in state that the client may not have.
  return null;
}

// `checked` flips to true once we've taken at least one client-side
// snapshot, so the header can hide auth chips during the very first SSR
// paint (avoids flicker between "no user" and "user").
function getCheckedSnapshot(): boolean {
  return typeof window !== "undefined";
}

function getCheckedServerSnapshot(): boolean {
  return false;
}

export function useAuth() {
  const user = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const checked = useSyncExternalStore(
    subscribe,
    getCheckedSnapshot,
    getCheckedServerSnapshot,
  );

  const logout = useCallback(() => {
    clearAuth();
    if (typeof window !== "undefined") {
      window.dispatchEvent(new Event("authchange"));
      window.location.href = "/";
    }
  }, []);

  // Keep the same surface the components consume.
  const refresh = useCallback(() => {
    if (typeof window !== "undefined") {
      window.dispatchEvent(new Event("authchange"));
    }
  }, []);

  return {
    user,
    loggedIn: !!user,
    checked,
    logout,
    refresh,
  };
}
