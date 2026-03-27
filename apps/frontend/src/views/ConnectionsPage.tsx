import React from "react";
import { apiFetch } from "../api";

export function ConnectionsPage() {
  const pollCommands = React.useMemo(
    () => [
      "get_calls",
      "get_zones",
      "get_users",
      "get_turrets",
      "get_events",
      "get_version",
      "get_tpos",
      "get_lines",
      "get_shared_profiles",
      "get_health_api_report"
    ],
    []
  );

  type Site = {
    id: string;
    site_name: string;
    wss_url: string;
    latitude?: number | null;
    longitude?: number | null;
    is_active: boolean;
    status: string;
    subscribe_calls: boolean;
    subscribe_presence: boolean;
    subscribe_alerts: boolean;
    subscribe_events: boolean;
  };

  type PollRule = {
    command: string;
    enabled: boolean;
    interval_seconds: number;
  };

  const [sites, setSites] = React.useState<Site[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const [pollRulesBySiteId, setPollRulesBySiteId] = React.useState<Record<string, PollRule[]>>({});
  const [pollSavingBySiteId, setPollSavingBySiteId] = React.useState<Record<string, boolean>>({});

  const [pollModalSiteId, setPollModalSiteId] = React.useState<string | null>(null);
  const [editSiteId, setEditSiteId] = React.useState<string | null>(null);

  const loadSites = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch("/api/sites");
      if (!res.ok) throw new Error(`failed_to_load_sites_${res.status}`);
      const json = await res.json();
      setSites(json.sites ?? []);

      const nextPollRules: Record<string, PollRule[]> = {};
      await Promise.all(
        (json.sites ?? []).map(async (s: Site) => {
          try {
            const rr = await apiFetch(`/api/sites/${s.id}/poll-rules`);
            if (!rr.ok) return;
            const rj = await rr.json();
            const rules: PollRule[] = rj.rules ?? [];
            const byCmd = new Map(rules.map((r: PollRule) => [r.command, r] as const));
            nextPollRules[s.id] = pollCommands.map((c: string) =>
              byCmd.get(c) ?? { command: c, enabled: false, interval_seconds: 60 }
            );
          } catch {
            nextPollRules[s.id] = pollCommands.map((c: string) => ({ command: c, enabled: false, interval_seconds: 60 }));
          }
        })
      );
      setPollRulesBySiteId(nextPollRules);
    } catch (e: any) {
      setError(e?.message ?? "failed_to_load_sites");
    } finally {
      setLoading(false);
    }
  }, [pollCommands]);

  const [editName, setEditName] = React.useState("");
  const [editWssUrl, setEditWssUrl] = React.useState("");
  const [editToken, setEditToken] = React.useState("");
  const [editLat, setEditLat] = React.useState("");
  const [editLng, setEditLng] = React.useState("");
  const [editSaving, setEditSaving] = React.useState(false);

  const openEditSite = React.useCallback((s: Site) => {
    setEditSiteId(s.id);
    setEditName(s.site_name);
    setEditWssUrl(s.wss_url);
    setEditToken("");
    setEditLat(s.latitude != null ? String(s.latitude) : "");
    setEditLng(s.longitude != null ? String(s.longitude) : "");
  }, []);

  const saveEditSite = React.useCallback(async () => {
    if (!editSiteId) return;
    setEditSaving(true);
    try {
      const patch: any = {
        site_name: editName,
        wss_url: editWssUrl,
        latitude: editLat ? Number(editLat) : null,
        longitude: editLng ? Number(editLng) : null
      };
      if (editToken) {
        patch.token = editToken;
      }
      await apiFetch(`/api/sites/${editSiteId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch)
      });
      setEditSiteId(null);
      await loadSites();
    } finally {
      setEditSaving(false);
    }
  }, [editLat, editLng, editName, editSiteId, editToken, editWssUrl, loadSites]);

  type CreatedConnection = {
    id: string;
    token: string;
    name: string;
    allowed_site_ids: string[];
  };

  type ExistingConnection = {
    id: string;
    name: string;
    revoked: boolean;
    latitude: number | null;
    longitude: number | null;
    enhanced_messaging?: boolean;
    allowed_site_ids?: string[];
    created_at: string;
  };

  type ActiveConnection = {
    conn_id: string;
    name?: string;
    enhanced_messaging?: boolean;
    revoked?: boolean;
    client_host?: string | null;
    connected_at?: number;
    subscribed_site_ids?: string[];
  };

  const [connName, setConnName] = React.useState("");
  const [connAllowedSiteIds, setConnAllowedSiteIds] = React.useState<Record<string, boolean>>({});
  const [connCreating, setConnCreating] = React.useState(false);
  const [createdConn, setCreatedConn] = React.useState<CreatedConnection | null>(null);
  const [connError, setConnError] = React.useState<string | null>(null);

  const [existingConnections, setExistingConnections] = React.useState<ExistingConnection[]>([]);
  const [activeConnections, setActiveConnections] = React.useState<ActiveConnection[]>([]);

  const loadConnections = React.useCallback(async () => {
    try {
      const res = await apiFetch("/api/connections");
      if (!res.ok) return;
      const json = await res.json();
      setExistingConnections(json.connections ?? []);
    } catch {
      setExistingConnections([]);
    }
  }, []);

  const loadActiveConnections = React.useCallback(async () => {
    try {
      const res = await apiFetch("/api/connections/active");
      if (!res.ok) return;
      const json = await res.json();
      setActiveConnections(json.active ?? []);
    } catch {
      setActiveConnections([]);
    }
  }, []);

  const [newSiteName, setNewSiteName] = React.useState("");
  const [newWssUrl, setNewWssUrl] = React.useState("");
  const [newToken, setNewToken] = React.useState("");
  const [newSiteLat, setNewSiteLat] = React.useState("");
  const [newSiteLng, setNewSiteLng] = React.useState("");
  const [subCalls, setSubCalls] = React.useState(true);
  const [subPresence, setSubPresence] = React.useState(false);
  const [subAlerts, setSubAlerts] = React.useState(false);
  const [subEvents, setSubEvents] = React.useState(false);

  React.useEffect(() => {
    void loadSites();
  }, [loadSites]);

  React.useEffect(() => {
    void loadConnections();
  }, [loadConnections]);

  React.useEffect(() => {
    void loadActiveConnections();
    const t = window.setInterval(() => void loadActiveConnections(), 5000);
    return () => window.clearInterval(t);
  }, [loadActiveConnections]);

  const activeByConnId = React.useMemo(() => {
    const m = new Map<string, ActiveConnection>();
    for (const a of activeConnections) {
      if (a.conn_id) m.set(a.conn_id, a);
    }
    return m;
  }, [activeConnections]);

  const [editConnId, setEditConnId] = React.useState<string | null>(null);
  const [editConnName, setEditConnName] = React.useState("");
  const [editConnLat, setEditConnLat] = React.useState("");
  const [editConnLng, setEditConnLng] = React.useState("");
  const [editConnEnhanced, setEditConnEnhanced] = React.useState(false);
  const [editConnAllowedSiteIds, setEditConnAllowedSiteIds] = React.useState<Record<string, boolean>>({});
  const [editConnSaving, setEditConnSaving] = React.useState(false);

  const openEditConnection = React.useCallback(
    (c: ExistingConnection) => {
      setEditConnId(c.id);
      setEditConnName(c.name);
      setEditConnLat(c.latitude != null ? String(c.latitude) : "");
      setEditConnLng(c.longitude != null ? String(c.longitude) : "");
      setEditConnEnhanced(!!c.enhanced_messaging);
      const allowed = new Set((c.allowed_site_ids ?? []).map(String));
      const next: Record<string, boolean> = {};
      for (const s of sites) {
        next[s.id] = allowed.has(s.id);
      }
      setEditConnAllowedSiteIds(next);
    },
    [sites]
  );

  const saveEditConnection = React.useCallback(async () => {
    if (!editConnId) return;
    setEditConnSaving(true);
    try {
      const allowed_site_ids = sites.filter((s) => !!editConnAllowedSiteIds[s.id]).map((s) => s.id);
      const patch: any = {
        name: editConnName,
        latitude: editConnLat ? Number(editConnLat) : null,
        longitude: editConnLng ? Number(editConnLng) : null,
        enhanced_messaging: editConnEnhanced,
        allowed_site_ids
      };
      await apiFetch(`/api/connections/${editConnId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch)
      });
      setEditConnId(null);
      await loadConnections();
      await loadActiveConnections();
    } finally {
      setEditConnSaving(false);
    }
  }, [editConnAllowedSiteIds, editConnEnhanced, editConnId, editConnLat, editConnLng, editConnName, loadActiveConnections, loadConnections, sites]);

  const editConnModal = React.useMemo(() => {
    if (!editConnId) return null;
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
        <div className="w-full max-w-2xl rounded border border-slate-800 bg-slate-950 p-4 text-zinc-200">
          <div className="flex items-center justify-between">
            <div className="text-lg font-semibold">Edit Incoming Connection</div>
            <button className="rounded bg-slate-800 px-3 py-2" onClick={() => setEditConnId(null)}>
              Close
            </button>
          </div>

          <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
            <input
              className="rounded border border-slate-800 bg-slate-900 p-2"
              placeholder="Connection name"
              value={editConnName}
              onChange={(e) => setEditConnName(e.target.value)}
            />
            <label className="flex items-center gap-2 text-sm text-zinc-300">
              <input
                type="checkbox"
                checked={editConnEnhanced}
                onChange={(e) => setEditConnEnhanced(e.target.checked)}
              />
              Enhanced messaging
            </label>
            <input
              className="rounded border border-slate-800 bg-slate-900 p-2"
              placeholder="Latitude (optional)"
              value={editConnLat}
              onChange={(e) => setEditConnLat(e.target.value)}
            />
            <input
              className="rounded border border-slate-800 bg-slate-900 p-2"
              placeholder="Longitude (optional)"
              value={editConnLng}
              onChange={(e) => setEditConnLng(e.target.value)}
            />
          </div>

          <div className="mt-3 rounded border border-slate-800 bg-slate-900/40 p-3">
            <div className="text-zinc-300 mb-2">Allowed sites</div>
            {sites.length === 0 ? (
              <div className="text-sm text-zinc-400">No sites loaded.</div>
            ) : (
              <div className="flex flex-wrap gap-4">
                {sites.map((s) => (
                  <label key={s.id} className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={!!editConnAllowedSiteIds[s.id]}
                      onChange={(e) =>
                        setEditConnAllowedSiteIds((p) => ({
                          ...p,
                          [s.id]: e.target.checked
                        }))
                      }
                    />
                    {s.site_name}
                  </label>
                ))}
              </div>
            )}
          </div>

          <div className="mt-4 flex items-center justify-end gap-3">
            <button
              className="rounded bg-sky-600 px-3 py-2 text-white disabled:opacity-50"
              onClick={() => void saveEditConnection()}
              disabled={editConnSaving || !editConnName}
            >
              {editConnSaving ? "Saving..." : "Save"}
            </button>
          </div>
        </div>
      </div>
    );
  }, [editConnAllowedSiteIds, editConnEnhanced, editConnId, editConnLat, editConnLng, editConnName, editConnSaving, saveEditConnection, sites]);

  const updateSite = React.useCallback(
    async (
      id: string,
      patch: Partial<
        Pick<Site, "subscribe_calls" | "subscribe_presence" | "subscribe_alerts" | "subscribe_events" | "is_active">
      >
    ) => {
      await apiFetch(`/api/sites/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch)
      });
      await loadSites();
    },
    [loadSites]
  );

  const connectSite = React.useCallback(
    async (id: string) => {
      await apiFetch(`/api/sites/${id}/connect`, { method: "POST" });
      await loadSites();
    },
    [loadSites]
  );

  const disconnectSite = React.useCallback(
    async (id: string) => {
      await apiFetch(`/api/sites/${id}/disconnect`, { method: "POST" });
      await loadSites();
    },
    [loadSites]
  );

  const deleteSite = React.useCallback(
    async (id: string) => {
      const ok = window.confirm("Delete this site? This will remove its polling rules/state.");
      if (!ok) return;
      await apiFetch(`/api/sites/${id}`, { method: "DELETE" });
      await loadSites();
    },
    [loadSites]
  );

  const createSite = React.useCallback(async () => {
    setError(null);
    try {
      const res = await apiFetch("/api/sites", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          site_name: newSiteName,
          wss_url: newWssUrl,
          token: newToken,
          latitude: newSiteLat ? Number(newSiteLat) : null,
          longitude: newSiteLng ? Number(newSiteLng) : null,
          is_active: true,
          subscribe_calls: subCalls,
          subscribe_presence: subPresence,
          subscribe_alerts: subAlerts,
          subscribe_events: subEvents
        })
      });
      if (!res.ok) throw new Error(`failed_to_create_site_${res.status}`);
      setNewSiteName("");
      setNewWssUrl("");
      setNewToken("");
      setNewSiteLat("");
      setNewSiteLng("");
      await loadSites();
    } catch (e: any) {
      setError(e?.message ?? "failed_to_create_site");
    }
  }, [loadSites, newSiteName, newToken, newWssUrl, subAlerts, subCalls, subEvents, subPresence]);

  const [connLat, setConnLat] = React.useState("");
  const [connLng, setConnLng] = React.useState("");

  const setPollRule = React.useCallback(
    (siteId: string, command: string, patch: Partial<PollRule>) => {
      setPollRulesBySiteId((prev: Record<string, PollRule[]>) => {
        const list =
          prev[siteId] ?? pollCommands.map((c: string) => ({ command: c, enabled: false, interval_seconds: 60 }));
        const next = list.map((r: PollRule) => (r.command === command ? { ...r, ...patch } : r));
        return { ...prev, [siteId]: next };
      });
    },
    [pollCommands]
  );

  const savePollRules = React.useCallback(
    async (siteId: string) => {
      const rules = pollRulesBySiteId[siteId] ?? [];
      setPollSavingBySiteId((p: Record<string, boolean>) => ({ ...p, [siteId]: true }));
      try {
        const res = await apiFetch(`/api/sites/${siteId}/poll-rules`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ rules })
        });
        if (!res.ok) throw new Error(`failed_to_save_poll_rules_${res.status}`);
        await loadSites();
      } finally {
        setPollSavingBySiteId((p: Record<string, boolean>) => ({ ...p, [siteId]: false }));
      }
    },
    [pollRulesBySiteId, loadSites]
  );

  const createConnectionToken = React.useCallback(async () => {
    setConnError(null);
    setConnCreating(true);
    try {
      const allowed_site_ids = sites.filter((s) => !!connAllowedSiteIds[s.id]).map((s) => s.id);
      const res = await apiFetch("/api/connections/token", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: connName,
          allowed_site_ids,
          latitude: connLat ? Number(connLat) : null,
          longitude: connLng ? Number(connLng) : null
        })
      });
      if (!res.ok) throw new Error(`failed_to_create_token_${res.status}`);
      const json = await res.json();
      setCreatedConn({ id: json.id, token: json.token, name: connName, allowed_site_ids });
      await loadConnections();
    } catch (e: any) {
      setConnError(e?.message ?? "failed_to_create_token");
    } finally {
      setConnCreating(false);
    }
  }, [connAllowedSiteIds, connName, loadConnections, sites, connLat, connLng]);

  const revokeConnectionToken = React.useCallback(async () => {
    if (!createdConn) return;
    setConnError(null);
    try {
      const res = await apiFetch(`/api/connections/${createdConn.id}/revoke`, { method: "POST" });
      if (!res.ok) throw new Error(`failed_to_revoke_${res.status}`);
      setCreatedConn(null);
      await loadConnections();
    } catch (e: any) {
      setConnError(e?.message ?? "failed_to_revoke");
    }
  }, [createdConn, loadConnections]);

  const PollRulesModal = React.useCallback(
    ({ site }: { site: Site }) => {
      const rules = pollRulesBySiteId[site.id] ?? [];
      const saving = !!pollSavingBySiteId[site.id];
      return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-3xl rounded border border-slate-800 bg-slate-950 p-4 text-zinc-200">
            <div className="flex items-center justify-between">
              <div className="text-lg font-semibold">Get Commands: {site.site_name}</div>
              <button className="rounded bg-slate-800 px-3 py-2" onClick={() => setPollModalSiteId(null)}>
                Close
              </button>
            </div>
            <div className="mt-3 overflow-auto">
              <table className="min-w-full border-separate border-spacing-y-2">
                <thead className="text-left text-zinc-400">
                  <tr>
                    <th className="px-2">Command</th>
                    <th className="px-2">Enabled</th>
                    <th className="px-2">Interval (sec)</th>
                  </tr>
                </thead>
                <tbody>
                  {rules.map((r: PollRule) => (
                    <tr key={r.command} className="bg-slate-900/60">
                      <td className="px-2 py-2 text-zinc-200 font-mono">{r.command}</td>
                      <td className="px-2 py-2">
                        <input
                          type="checkbox"
                          checked={r.enabled}
                          onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                            setPollRule(site.id, r.command, { enabled: e.target.checked })
                          }
                        />
                      </td>
                      <td className="px-2 py-2">
                        <input
                          className="w-28 rounded border border-slate-800 bg-slate-900 p-1"
                          type="number"
                          min={1}
                          value={r.interval_seconds}
                          onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                            setPollRule(site.id, r.command, {
                              interval_seconds: Math.max(1, Number(e.target.value || "1"))
                            })
                          }
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="mt-4 flex items-center justify-end gap-3">
              <button
                className="rounded bg-sky-600 px-3 py-2 text-white disabled:opacity-50"
                onClick={() => void savePollRules(site.id)}
                disabled={saving}
              >
                {saving ? "Saving..." : "Save"}
              </button>
            </div>
          </div>
        </div>
      );
    },
    [pollRulesBySiteId, pollSavingBySiteId, savePollRules, setPollRule]
  );

  const editSiteModal = React.useMemo(() => {
    if (!editSiteId) return null;
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
        <div className="w-full max-w-2xl rounded border border-slate-800 bg-slate-950 p-4 text-zinc-200">
          <div className="flex items-center justify-between">
            <div className="text-lg font-semibold">Edit Site</div>
            <button className="rounded bg-slate-800 px-3 py-2" onClick={() => setEditSiteId(null)}>
              Close
            </button>
          </div>

          <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
            <input
              className="rounded border border-slate-800 bg-slate-900 p-2"
              placeholder="Site name"
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
            />
            <input
              className="rounded border border-slate-800 bg-slate-900 p-2"
              placeholder="wss://.../api"
              value={editWssUrl}
              onChange={(e) => setEditWssUrl(e.target.value)}
            />
            <input
              className="rounded border border-slate-800 bg-slate-900 p-2"
              placeholder="New token (leave blank to keep current)"
              value={editToken}
              onChange={(e) => setEditToken(e.target.value)}
            />
            <div />
            <input
              className="rounded border border-slate-800 bg-slate-900 p-2"
              placeholder="Latitude (optional)"
              value={editLat}
              onChange={(e) => setEditLat(e.target.value)}
            />
            <input
              className="rounded border border-slate-800 bg-slate-900 p-2"
              placeholder="Longitude (optional)"
              value={editLng}
              onChange={(e) => setEditLng(e.target.value)}
            />
          </div>

          <div className="mt-4 flex items-center justify-end gap-3">
            <button
              className="rounded bg-sky-600 px-3 py-2 text-white disabled:opacity-50"
              onClick={() => void saveEditSite()}
              disabled={editSaving || !editName || !editWssUrl}
            >
              {editSaving ? "Saving..." : "Save"}
            </button>
          </div>
        </div>
      </div>
    );
  }, [editLat, editLng, editName, editSaving, editSiteId, editToken, editWssUrl, saveEditSite]);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Connection Configuration</h1>

      <div className="rounded border border-slate-800 bg-slate-950 p-4 text-zinc-200 space-y-3">
        <div className="text-lg font-semibold">Add Site</div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <input
            className="rounded border border-slate-800 bg-slate-900 p-2"
            placeholder="Site name"
            value={newSiteName}
            onChange={(e) => setNewSiteName(e.target.value)}
          />
          <input
            className="rounded border border-slate-800 bg-slate-900 p-2"
            placeholder="wss://.../api"
            value={newWssUrl}
            onChange={(e) => setNewWssUrl(e.target.value)}
          />
          <input
            className="rounded border border-slate-800 bg-slate-900 p-2"
            placeholder="API token"
            value={newToken}
            onChange={(e) => setNewToken(e.target.value)}
          />
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <input
            className="rounded border border-slate-800 bg-slate-900 p-2"
            placeholder="Latitude (optional)"
            value={newSiteLat}
            onChange={(e) => setNewSiteLat(e.target.value)}
          />
          <input
            className="rounded border border-slate-800 bg-slate-900 p-2"
            placeholder="Longitude (optional)"
            value={newSiteLng}
            onChange={(e) => setNewSiteLng(e.target.value)}
          />
        </div>

        <div className="flex flex-wrap gap-4">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={subCalls}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setSubCalls(e.target.checked)}
            />
            calls
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={subPresence}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setSubPresence(e.target.checked)}
            />
            presence
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={subAlerts}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setSubAlerts(e.target.checked)}
            />
            alerts
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={subEvents}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setSubEvents(e.target.checked)}
            />
            events
          </label>
        </div>

        <div className="flex items-center gap-3">
          <button
            className="rounded bg-sky-600 px-3 py-2 text-white disabled:opacity-50"
            onClick={() => void createSite()}
            disabled={!newSiteName || !newWssUrl || !newToken}
          >
            Create
          </button>
          {error ? <div className="text-red-400">{error}</div> : null}
        </div>
      </div>

      <div className="rounded border border-slate-800 bg-slate-950 p-4 text-zinc-200">
        <div className="flex items-center justify-between">
          <div className="text-lg font-semibold">Sites</div>
          <button className="rounded bg-slate-800 px-3 py-2" onClick={() => void loadSites()}>
            Refresh
          </button>
        </div>

        {loading ? <div className="mt-3 text-zinc-400">Loading...</div> : null}

        <div className="mt-3 overflow-auto">
          <table className="min-w-full border-separate border-spacing-y-2">
            <thead className="text-left text-zinc-400">
              <tr>
                <th className="px-2">Name</th>
                <th className="px-2">WSS URL</th>
                <th className="px-2">Actions</th>
                <th className="px-2">Get Commands</th>
                <th className="px-2">Active</th>
                <th className="px-2">Status</th>
                <th className="px-2">calls</th>
                <th className="px-2">presence</th>
                <th className="px-2">alerts</th>
                <th className="px-2">events</th>
              </tr>
            </thead>
            <tbody>
              {sites.map((s) => (
                <tr key={s.id} className="bg-slate-900/60">
                  <td className="px-2 py-2 font-medium text-zinc-100">{s.site_name}</td>
                  <td className="px-2 py-2 text-zinc-300">{s.wss_url}</td>
                  <td className="px-2 py-2">
                    <div className="flex items-center gap-2">
                      <button
                        className="rounded bg-emerald-700 px-2 py-1 text-white disabled:opacity-50"
                        onClick={() => void connectSite(s.id)}
                        disabled={s.is_active}
                      >
                        Connect
                      </button>
                      <button
                        className="rounded bg-rose-700 px-2 py-1 text-white disabled:opacity-50"
                        onClick={() => void disconnectSite(s.id)}
                        disabled={!s.is_active}
                      >
                        Disconnect
                      </button>
                      <button
                        className="rounded bg-sky-700 px-2 py-1 text-white disabled:opacity-50"
                        onClick={() => void updateSite(s.id, { is_active: true })}
                        disabled={s.is_active}
                      >
                        Enable
                      </button>
                      <button
                        className="rounded bg-slate-700 px-2 py-1 text-white disabled:opacity-50"
                        onClick={() => void updateSite(s.id, { is_active: false })}
                        disabled={!s.is_active}
                      >
                        Disable
                      </button>
                      <button
                        className="rounded bg-slate-800 px-2 py-1 text-white"
                        onClick={() => openEditSite(s)}
                      >
                        Edit Site
                      </button>
                      <button
                        className="rounded bg-slate-700 px-2 py-1 text-white"
                        onClick={() => void deleteSite(s.id)}
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                  <td className="px-2 py-2">
                    <button
                      className="rounded bg-slate-800 px-3 py-1"
                      onClick={() => setPollModalSiteId(s.id)}
                    >
                      Edit
                    </button>
                  </td>
                  <td className="px-2 py-2">
                    <input
                      type="checkbox"
                      checked={s.is_active}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                        void updateSite(s.id, { is_active: e.target.checked })
                      }
                    />
                  </td>
                  <td className="px-2 py-2 text-zinc-300">{s.status}</td>
                  <td className="px-2 py-2">
                    <input
                      type="checkbox"
                      checked={s.subscribe_calls}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                        void updateSite(s.id, { subscribe_calls: e.target.checked })
                      }
                    />
                  </td>
                  <td className="px-2 py-2">
                    <input
                      type="checkbox"
                      checked={s.subscribe_presence}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                        void updateSite(s.id, { subscribe_presence: e.target.checked })
                      }
                    />
                  </td>
                  <td className="px-2 py-2">
                    <input
                      type="checkbox"
                      checked={s.subscribe_alerts}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                        void updateSite(s.id, { subscribe_alerts: e.target.checked })
                      }
                    />
                  </td>
                  <td className="px-2 py-2">
                    <input
                      type="checkbox"
                      checked={s.subscribe_events}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                        void updateSite(s.id, { subscribe_events: e.target.checked })
                      }
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="rounded border border-slate-800 bg-slate-950 p-4 text-zinc-200 space-y-3">
        <div className="text-lg font-semibold">Incoming Connections (Token)</div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <input
            className="rounded border border-slate-800 bg-slate-900 p-2"
            placeholder="Connection name"
            value={connName}
            onChange={(e) => setConnName(e.target.value)}
          />
          <div className="text-zinc-400 text-sm">
            Create an access token for an external app. The app connects to <span className="font-mono">wss://servername/api</span>,
            sends an <span className="font-mono">auth</span> command with the 32-character token, then can send
            <span className="font-mono">{"{"}"action":"subscribe_site","site_id":"..."{"}"}</span>.
          </div>
        </div>

        <div className="rounded border border-slate-800 bg-slate-900/40 p-3">
          <div className="flex items-center justify-between">
            <div className="text-zinc-300 mb-2">Allowed sites</div>
            <button className="rounded bg-slate-800 px-3 py-2" onClick={() => void loadSites()}>
              Refresh Sites
            </button>
          </div>

          {sites.length === 0 ? (
            <div className="text-sm text-zinc-400">No sites loaded. Create a site above, or check that the backend is reachable.</div>
          ) : (
            <div className="flex flex-wrap gap-4">
              {sites.map((s) => (
                <label key={s.id} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={!!connAllowedSiteIds[s.id]}
                    onChange={(e) => setConnAllowedSiteIds((p) => ({ ...p, [s.id]: e.target.checked }))}
                  />
                  {s.site_name}
                </label>
              ))}
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <input
            className="rounded border border-slate-800 bg-slate-900 p-2"
            placeholder="Integration latitude (optional)"
            value={connLat}
            onChange={(e) => setConnLat(e.target.value)}
          />
          <input
            className="rounded border border-slate-800 bg-slate-900 p-2"
            placeholder="Integration longitude (optional)"
            value={connLng}
            onChange={(e) => setConnLng(e.target.value)}
          />
        </div>

        <div className="flex items-center gap-3">
          <button
            className="rounded bg-sky-600 px-3 py-2 text-white disabled:opacity-50"
            onClick={() => void createConnectionToken()}
            disabled={connCreating || !connName || sites.filter((s) => !!connAllowedSiteIds[s.id]).length === 0}
          >
            {connCreating ? "Creating..." : "Create Token"}
          </button>
          {connError ? <div className="text-red-400">{connError}</div> : null}
        </div>

        {createdConn ? (
          <div className="rounded border border-slate-800 bg-slate-900/40 p-3 space-y-2">
            <div className="text-zinc-300">Created</div>
            <div className="text-sm text-zinc-400">Connection ID</div>
            <div className="font-mono text-zinc-200 break-all">{createdConn.id}</div>
            <div className="text-sm text-zinc-400">Token</div>
            <div className="font-mono text-zinc-200 break-all">{createdConn.token}</div>
            <div className="text-sm text-zinc-400">WebSocket URL</div>
            <div className="font-mono text-zinc-200 break-all">wss://servername/api</div>
            <div className="text-sm text-zinc-400">Dev URL</div>
            <div className="font-mono text-zinc-200 break-all">ws://localhost:3000/api</div>
            <div className="text-sm text-zinc-400">Auth payload</div>
            <div className="font-mono text-zinc-200 break-all">{`{"command":"auth","command_ref":"...","args":{"token":"${createdConn.token}"}}`}</div>
            <div className="flex items-center justify-end">
              <button className="rounded bg-rose-700 px-3 py-2 text-white" onClick={() => void revokeConnectionToken()}>
                Revoke
              </button>
            </div>
          </div>
        ) : null}

        <div className="rounded border border-slate-800 bg-slate-900/40 p-3 space-y-2">
          <div className="flex items-center justify-between">
            <div className="text-zinc-300">Existing incoming connections</div>
            <button className="rounded bg-slate-800 px-3 py-2" onClick={() => void loadConnections()}>
              Refresh
            </button>
          </div>

          {existingConnections.length === 0 ? (
            <div className="text-sm text-zinc-400">None yet.</div>
          ) : (
            <div className="overflow-auto">
              <table className="min-w-full border-separate border-spacing-y-2">
                <thead className="text-left text-zinc-400">
                  <tr>
                    <th className="px-2">Name</th>
                    <th className="px-2">Active</th>
                    <th className="px-2">Enhanced</th>
                    <th className="px-2">Created</th>
                    <th className="px-2">Revoked</th>
                    <th className="px-2">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {existingConnections.map((c) => (
                    <tr key={c.id} className="bg-slate-900/60">
                      <td className="px-2 py-2 text-zinc-200">{c.name}</td>
                      <td className="px-2 py-2 text-zinc-200">
                        {activeByConnId.has(c.id) ? "true" : "false"}
                      </td>
                      <td className="px-2 py-2 text-zinc-200">{String(!!c.enhanced_messaging)}</td>
                      <td className="px-2 py-2 text-zinc-400 text-sm">{c.created_at}</td>
                      <td className="px-2 py-2 text-zinc-200">{String(c.revoked)}</td>
                      <td className="px-2 py-2">
                        <div className="flex items-center gap-2">
                          <button className="rounded bg-slate-800 px-3 py-2 text-white" onClick={() => openEditConnection(c)}>
                            Edit
                          </button>
                          <button
                            className="rounded bg-rose-700 px-3 py-2 text-white disabled:opacity-50"
                            disabled={c.revoked}
                            onClick={async () => {
                              await apiFetch(`/api/connections/${c.id}/revoke`, { method: "POST" });
                              await loadConnections();
                              await loadActiveConnections();
                            }}
                          >
                            Revoke
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {pollModalSiteId ? <PollRulesModal site={sites.find((s) => s.id === pollModalSiteId)!} /> : null}
      {editSiteModal}
      {editConnModal}
    </div>
  );
}
