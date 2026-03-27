import React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { apiFetch } from "../api";
import { clearTokens, getAccessToken } from "../auth";

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const loc = useLocation();
  const [checking, setChecking] = React.useState(true);
  const [ok, setOk] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;
    async function run() {
      const token = getAccessToken();
      if (!token) {
        if (!cancelled) {
          setOk(false);
          setChecking(false);
        }
        return;
      }
      try {
        const res = await apiFetch("/api/auth/me");
        if (!res.ok) {
          clearTokens();
          if (!cancelled) {
            setOk(false);
            setChecking(false);
          }
          return;
        }
        if (!cancelled) {
          setOk(true);
          setChecking(false);
        }
      } catch {
        clearTokens();
        if (!cancelled) {
          setOk(false);
          setChecking(false);
        }
      }
    }
    void run();
    return () => {
      cancelled = true;
    };
  }, []);

  if (checking) {
    return (
      <div className="min-h-screen flex items-center justify-center text-zinc-200">
        Checking session...
      </div>
    );
  }

  if (!ok) {
    return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  }

  return <>{children}</>;
}
