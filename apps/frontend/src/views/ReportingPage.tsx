import React from "react";
import { apiFetch } from "../api";

type TrafficSnapshot = {
  window_seconds: number;
  bt_sent_per_minute: Record<string, number>;
  bt_recv_per_minute: Record<string, number>;
  downstream_in_per_minute: Record<string, number>;
  downstream_out_per_minute: Record<string, number>;
};

export function ReportingPage() {
  const [data, setData] = React.useState<TrafficSnapshot | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    setError(null);
    try {
      const res = await apiFetch("/api/metrics/traffic");
      if (!res.ok) throw new Error(`failed_to_load_${res.status}`);
      const json = (await res.json()) as TrafficSnapshot;
      setData(json);
    } catch (e: any) {
      setError(e?.message ?? "failed_to_load");
    }
  }, []);

  React.useEffect(() => {
    void load();
    const t = window.setInterval(() => void load(), 2000);
    return () => window.clearInterval(t);
  }, [load]);

  const rows = (m: Record<string, number>) => Object.entries(m).sort((a, b) => b[1] - a[1]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Reporting</h1>
        <button className="rounded bg-slate-800 px-3 py-2 text-zinc-200" onClick={() => void load()}>
          Refresh
        </button>
      </div>

      {error ? <div className="text-red-400">{error}</div> : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="rounded border border-slate-800 bg-slate-950 p-4 text-zinc-200">
          <div className="font-semibold">Outgoing BT/WBA (per {data?.window_seconds ?? 60}s)</div>
          <div className="mt-3 overflow-auto">
            <table className="min-w-full border-separate border-spacing-y-2">
              <thead className="text-left text-zinc-400">
                <tr>
                  <th className="px-2">Site ID</th>
                  <th className="px-2">Sent</th>
                  <th className="px-2">Recv</th>
                </tr>
              </thead>
              <tbody>
                {rows(data?.bt_sent_per_minute ?? {}).map(([siteId, sent]) => (
                  <tr key={siteId} className="bg-slate-900/60">
                    <td className="px-2 py-2 font-mono">{siteId}</td>
                    <td className="px-2 py-2">{sent}</td>
                    <td className="px-2 py-2">{(data?.bt_recv_per_minute ?? {})[siteId] ?? 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="rounded border border-slate-800 bg-slate-950 p-4 text-zinc-200">
          <div className="font-semibold">Incoming Apps (per {data?.window_seconds ?? 60}s)</div>
          <div className="mt-3 overflow-auto">
            <table className="min-w-full border-separate border-spacing-y-2">
              <thead className="text-left text-zinc-400">
                <tr>
                  <th className="px-2">Connection ID</th>
                  <th className="px-2">In</th>
                  <th className="px-2">Out</th>
                </tr>
              </thead>
              <tbody>
                {rows(data?.downstream_in_per_minute ?? {}).map(([connId, incoming]) => (
                  <tr key={connId} className="bg-slate-900/60">
                    <td className="px-2 py-2 font-mono">{connId}</td>
                    <td className="px-2 py-2">{incoming}</td>
                    <td className="px-2 py-2">{(data?.downstream_out_per_minute ?? {})[connId] ?? 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="text-zinc-400 text-sm">Counts are rolling-window message totals. They reset on server restart.</div>
    </div>
  );
}
