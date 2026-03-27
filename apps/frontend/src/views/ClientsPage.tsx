import React from "react";
import { apiFetch } from "../api";

export function ClientsPage() {
  type ActiveConnection = {
    conn_id: string;
    name?: string;
    enhanced_messaging?: boolean;
    revoked?: boolean;
    client_host?: string | null;
    connected_at?: number;
    subscribed_site_ids?: string[];
  };

  const [active, setActive] = React.useState<ActiveConnection[]>([]);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    try {
      setError(null);
      const res = await apiFetch("/api/connections/active");
      if (!res.ok) throw new Error(`failed_to_load_${res.status}`);
      const json = await res.json();
      setActive(json.active ?? []);
    } catch (e: any) {
      setError(e?.message ?? "failed_to_load");
      setActive([]);
    }
  }, []);

  React.useEffect(() => {
    void load();
    const t = window.setInterval(() => void load(), 2000);
    return () => window.clearInterval(t);
  }, [load]);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Client Monitor</h1>

      {error ? <div className="rounded border border-red-900 bg-red-950 p-3 text-red-200">{error}</div> : null}

      <div className="rounded border border-slate-800 bg-slate-950 p-4 text-zinc-200">
        <div className="mb-3 text-sm text-zinc-400">Active connections: {active.length}</div>
        <div className="overflow-auto">
          <table className="min-w-[900px] table-auto border-collapse text-sm">
            <thead>
              <tr className="text-left text-zinc-400">
                <th className="border-b border-slate-800 p-2">Connection</th>
                <th className="border-b border-slate-800 p-2">Name</th>
                <th className="border-b border-slate-800 p-2">Enhanced</th>
                <th className="border-b border-slate-800 p-2">Revoked</th>
                <th className="border-b border-slate-800 p-2">Client Host</th>
                <th className="border-b border-slate-800 p-2">Connected</th>
                <th className="border-b border-slate-800 p-2">Subscribed Sites</th>
              </tr>
            </thead>
            <tbody>
              {active.map((c) => (
                <tr key={c.conn_id} className="hover:bg-slate-900/40">
                  <td className="border-b border-slate-900 p-2 font-mono">{c.conn_id}</td>
                  <td className="border-b border-slate-900 p-2">{c.name ?? ""}</td>
                  <td className="border-b border-slate-900 p-2">{c.enhanced_messaging ? "Yes" : "No"}</td>
                  <td className="border-b border-slate-900 p-2">{c.revoked ? "Yes" : "No"}</td>
                  <td className="border-b border-slate-900 p-2 font-mono">{c.client_host ?? ""}</td>
                  <td className="border-b border-slate-900 p-2">
                    {c.connected_at ? new Date(c.connected_at * 1000).toLocaleString() : ""}
                  </td>
                  <td className="border-b border-slate-900 p-2 font-mono">
                    {(c.subscribed_site_ids ?? []).join(", ")}
                  </td>
                </tr>
              ))}
              {active.length === 0 ? (
                <tr>
                  <td className="p-3 text-zinc-400" colSpan={7}>
                    No active incoming clients.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
