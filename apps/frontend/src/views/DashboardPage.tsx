import React from "react";
import { MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import { apiFetch } from "../api";

type Site = {
  id: string;
  site_name: string;
  status: string;
  latitude: number | null;
  longitude: number | null;
};

type Integration = {
  id: string;
  name: string;
  revoked: boolean;
  latitude: number | null;
  longitude: number | null;
};

function FitBounds({ points }: { points: Array<[number, number]> }) {
  const map = useMap();
  const lastKeyRef = React.useRef<string>("");
  React.useEffect(() => {
    if (!points.length) return;
    const key = points.map((p) => `${p[0].toFixed(6)},${p[1].toFixed(6)}`).join(";");
    if (key === lastKeyRef.current) return;
    lastKeyRef.current = key;

    if (points.length === 1) {
      map.setView(L.latLng(points[0][0], points[0][1]), 8);
      return;
    }

    const b = L.latLngBounds(points.map((p) => L.latLng(p[0], p[1])));
    map.fitBounds(b.pad(0.2), { maxZoom: 10 });
  }, [map, points]);
  return null;
}

const siteIcon = new L.DivIcon({
  className: "",
  html: '<div style="width:14px;height:14px;border-radius:9999px;background:#38bdf8;border:2px solid #0ea5e9;"></div>',
  iconSize: [14, 14],
  iconAnchor: [7, 7]
});

const integrationIcon = new L.DivIcon({
  className: "",
  html: '<div style="width:14px;height:14px;border-radius:9999px;background:#34d399;border:2px solid #059669;"></div>',
  iconSize: [14, 14],
  iconAnchor: [7, 7]
});

const revokedIntegrationIcon = new L.DivIcon({
  className: "",
  html: '<div style="width:14px;height:14px;border-radius:9999px;background:#94a3b8;border:2px solid #64748b;"></div>',
  iconSize: [14, 14],
  iconAnchor: [7, 7]
});

export function DashboardPage() {
  const [sites, setSites] = React.useState<Site[]>([]);
  const [integrations, setIntegrations] = React.useState<Integration[]>([]);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    setError(null);
    try {
      const [sr, cr] = await Promise.all([apiFetch("/api/sites"), apiFetch("/api/connections")]);
      if (!sr.ok) throw new Error(`failed_to_load_sites_${sr.status}`);
      if (!cr.ok) throw new Error(`failed_to_load_connections_${cr.status}`);
      const sj = await sr.json();
      const cj = await cr.json();
      setSites(sj.sites ?? []);
      setIntegrations(cj.connections ?? []);
    } catch (e: any) {
      setError(e?.message ?? "failed_to_load");
    }
  }, []);

  React.useEffect(() => {
    void load();
    const t = window.setInterval(() => void load(), 5000);
    return () => window.clearInterval(t);
  }, [load]);

  const sitePoints: Array<[number, number]> = React.useMemo(
    () =>
      sites
        .filter((s) => Number.isFinite(s.latitude) && Number.isFinite(s.longitude))
        .map((s) => [s.latitude as number, s.longitude as number]),
    [sites]
  );
  const integrationPoints: Array<[number, number]> = React.useMemo(
    () =>
      integrations
        .filter((c) => Number.isFinite(c.latitude) && Number.isFinite(c.longitude))
        .map((c) => [c.latitude as number, c.longitude as number]),
    [integrations]
  );
  const allPoints = React.useMemo(
    () => [...sitePoints, ...integrationPoints],
    [sitePoints, integrationPoints]
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Global Map</h1>
        <button className="rounded bg-slate-800 px-3 py-2 text-zinc-200" onClick={() => void load()}>
          Refresh
        </button>
      </div>

      {error ? <div className="text-red-400">{error}</div> : null}

      <div className="rounded border border-slate-800 bg-slate-950 p-3 text-zinc-200">
        <div className="flex flex-wrap gap-4 text-sm">
          <div className="flex items-center gap-2">
            <span className="inline-block h-3 w-3 rounded-full bg-sky-400" /> WBA Sites
          </div>
          <div className="flex items-center gap-2">
            <span className="inline-block h-3 w-3 rounded-full bg-emerald-400" /> Incoming Integrations
          </div>
          <div className="text-zinc-400">Only entries with lat/lng are shown.</div>
        </div>
      </div>

      <div className="rounded border border-slate-800 bg-slate-950 overflow-hidden" style={{ height: 520 }}>
        <MapContainer center={[20, 0]} zoom={2} style={{ height: "100%", width: "100%" }}>
          <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
          <FitBounds points={allPoints} />

          {sites
            .filter((s) => Number.isFinite(s.latitude) && Number.isFinite(s.longitude))
            .map((s) => (
              <Marker
                key={s.id}
                position={[s.latitude as number, s.longitude as number]}
                icon={siteIcon}
              >
                <Popup>
                  <div className="space-y-1">
                    <div className="font-semibold">{s.site_name}</div>
                    <div className="text-xs">{s.id}</div>
                    <div className="text-xs">Status: {s.status}</div>
                  </div>
                </Popup>
              </Marker>
            ))}

          {integrations
            .filter((c) => Number.isFinite(c.latitude) && Number.isFinite(c.longitude))
            .map((c) => (
              <Marker
                key={c.id}
                position={[c.latitude as number, c.longitude as number]}
                icon={c.revoked ? revokedIntegrationIcon : integrationIcon}
              >
                <Popup>
                  <div className="space-y-1">
                    <div className="font-semibold">{c.name}</div>
                    <div className="text-xs">{c.id}</div>
                    <div className="text-xs">Revoked: {String(c.revoked)}</div>
                  </div>
                </Popup>
              </Marker>
            ))}
        </MapContainer>
      </div>
    </div>
  );
}
