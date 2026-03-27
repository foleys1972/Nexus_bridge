import React from "react";
import { useNavigate } from "react-router-dom";
import { apiFetch } from "../api";
import { setTokens } from "../auth";

export function LoginPage() {
  const nav = useNavigate();
  const [username, setUsername] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const submit = React.useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const res = await apiFetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password })
      });
      if (!res.ok) {
        throw new Error(`login_failed_${res.status}`);
      }
      const json = await res.json();
      if (!json?.access_token) {
        throw new Error("login_failed_invalid_response");
      }
      setTokens({ access_token: String(json.access_token), refresh_token: json.refresh_token ? String(json.refresh_token) : undefined });
      nav("/");
    } catch (e: any) {
      setError(e?.message ?? "login_failed");
    } finally {
      setLoading(false);
    }
  }, [nav, password, username]);

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-sm rounded border border-slate-800 bg-slate-950 p-5 text-zinc-200 space-y-4">
        <div className="text-xl font-semibold text-white">NexusBridge</div>
        <div className="text-sm text-zinc-400">Sign in to continue</div>

        {error ? <div className="rounded border border-red-900 bg-red-950 p-3 text-red-200">{error}</div> : null}

        <input
          className="w-full rounded border border-slate-800 bg-slate-900 p-2"
          placeholder="Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
        />
        <input
          className="w-full rounded border border-slate-800 bg-slate-900 p-2"
          placeholder="Password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
        />

        <button
          className="w-full rounded bg-sky-600 px-3 py-2 text-white disabled:opacity-50"
          disabled={loading || !username || !password}
          onClick={() => void submit()}
        >
          {loading ? "Signing in..." : "Sign In"}
        </button>

        <div className="text-xs text-zinc-500">
          Backend: <span className="font-mono">/api/auth/login</span>
        </div>
      </div>
    </div>
  );
}
