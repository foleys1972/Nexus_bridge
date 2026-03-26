import React from "react";

export function SettingsPage() {
  const apiBase = (import.meta as any).env?.VITE_API_BASE_URL || "http://localhost:3000";
  const [data, setData] = React.useState<any>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [saving, setSaving] = React.useState(false);
  const [maxCpsDraft, setMaxCpsDraft] = React.useState<string>("");
  const [logBasePathDraft, setLogBasePathDraft] = React.useState<string>("");

  const load = React.useCallback(async () => {
    setError(null);
    try {
      const res = await fetch(`${apiBase}/api/settings`);
      if (!res.ok) throw new Error(`failed_to_load_${res.status}`);
      const json = await res.json();
      setData(json);
      const cur = json?.bt_defaults?.max_commands_per_second;
      if (typeof cur === "number") {
        setMaxCpsDraft(String(cur));
      }
      const lbp = json?.logging?.base_path;
      if (typeof lbp === "string") {
        setLogBasePathDraft(lbp);
      }
    } catch (e: any) {
      setError(e?.message ?? "failed_to_load");
    }
  }, [apiBase]);

  const save = React.useCallback(async () => {
    setError(null);
    setSaving(true);
    try {
      const n = Number(maxCpsDraft);
      const res = await fetch(`${apiBase}/api/settings`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          bt_max_commands_per_second: Math.max(1, Math.floor(n || 1)),
          log_base_path: logBasePathDraft
        })
      });
      if (!res.ok) throw new Error(`failed_to_save_${res.status}`);
      await load();
    } catch (e: any) {
      setError(e?.message ?? "failed_to_save");
    } finally {
      setSaving(false);
    }
  }, [apiBase, load, maxCpsDraft]);

  const saveLogging = React.useCallback(async () => {
    setError(null);
    setSaving(true);
    try {
      const res = await fetch(`${apiBase}/api/settings`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ log_base_path: logBasePathDraft })
      });
      if (!res.ok) throw new Error(`failed_to_save_${res.status}`);
      await load();
    } catch (e: any) {
      setError(e?.message ?? "failed_to_save");
    } finally {
      setSaving(false);
    }
  }, [apiBase, load, logBasePathDraft]);

  React.useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Settings</h1>

      {error ? <div className="text-red-400">{error}</div> : null}

      <div className="rounded border border-slate-800 bg-slate-950 p-4 text-zinc-200 space-y-3">
        <div className="flex items-center justify-between">
          <div className="text-lg font-semibold">Runtime Settings</div>
          <button className="rounded bg-slate-800 px-3 py-2" onClick={() => void load()}>
            Refresh
          </button>
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div className="rounded border border-slate-800 bg-slate-900/40 p-3">
            <div className="text-zinc-300 font-semibold">BT Throttling</div>
            <div className="mt-2 text-sm text-zinc-400">Max commands per second (per site)</div>
            <div className="mt-2 flex items-center gap-3">
              <input
                className="w-28 rounded border border-slate-800 bg-slate-900 p-2 font-mono text-zinc-200"
                type="number"
                min={1}
                max={100}
                value={maxCpsDraft}
                onChange={(e) => setMaxCpsDraft(e.target.value)}
              />
              <button
                className="rounded bg-sky-600 px-3 py-2 text-white disabled:opacity-50"
                onClick={() => void save()}
                disabled={saving}
              >
                {saving ? "Saving..." : "Save"}
              </button>
            </div>
            <div className="mt-2 text-xs text-zinc-500">
              Set via `.env` with `BT_MAX_COMMANDS_PER_SECOND` or via `config.yaml`.
            </div>
          </div>

          <div className="rounded border border-slate-800 bg-slate-900/40 p-3">
            <div className="text-zinc-300 font-semibold">Logging</div>
            <div className="mt-2 text-sm text-zinc-400">Base path</div>
            <div className="mt-2 flex items-center gap-3">
              <input
                className="w-full rounded border border-slate-800 bg-slate-900 p-2 font-mono text-zinc-200"
                value={logBasePathDraft}
                onChange={(e) => setLogBasePathDraft(e.target.value)}
              />
              <button
                className="rounded bg-sky-600 px-3 py-2 text-white disabled:opacity-50"
                onClick={() => void saveLogging()}
                disabled={saving || !logBasePathDraft}
              >
                {saving ? "Saving..." : "Save"}
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="rounded border border-slate-800 bg-slate-950 p-4 text-zinc-200">
        Access control and user management settings will be added here.
      </div>
    </div>
  );
}
