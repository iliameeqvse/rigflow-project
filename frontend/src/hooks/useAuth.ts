import { useState, useEffect, useCallback } from "react";
import { getUser, clearAuth, StoredUser } from "@/lib/api";

export function useAuth() {
  const [user, setUser] = useState<StoredUser | null>(null);
  const [checked, setChecked] = useState(false);

  const refresh = useCallback(() => {
    setUser(getUser());
    setChecked(true);
  }, []);

  useEffect(() => {
    refresh();

    // "authchange" is dispatched manually by login/signup in the SAME tab
    window.addEventListener("authchange", refresh);

    // "storage" fires when localStorage changes in a DIFFERENT tab
    const storageHandler = (e: StorageEvent) => {
      if (e.key === "user" || e.key === "access" || e.key === null) {
        refresh();
      }
    };
    window.addEventListener("storage", storageHandler);

    return () => {
      window.removeEventListener("authchange", refresh);
      window.removeEventListener("storage", storageHandler);
    };
  }, [refresh]);

  const logout = useCallback(() => {
    clearAuth();
    setUser(null);
    window.dispatchEvent(new Event("authchange"));
    window.location.href = "/";
  }, []);

  return {
    user,
    loggedIn: !!user,
    checked,
    logout,
    refresh,
  };
}