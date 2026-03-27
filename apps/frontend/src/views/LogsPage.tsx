import React from "react";
import { apiFetch, getApiBase } from "../api";
import { getAccessToken } from "../auth";

export function LogsPage() {
  const [treePath, setTreePath] = React.useState<string>("");
  const [tree, setTree] = React.useState<{ root: string; path: string; entries: { name: string; type: string }[] } | null>(null);
  const [treeError, setTreeError] = React.useState<string | null>(null);

  const [selectedSiteId, setSelectedSiteId] = React.useState<string>("");
  const [selectedLogType, setSelectedLogType] = React.useState<string>("");

  const [tailLines, setTailLines] = React.useState<string[]>([]);
  const [tailError, setTailError] = React.useState<string | null>(null);
  const [tailRunning, setTailRunning] = React.useState<boolean>(false);
  const tailAbortRef = React.useRef<AbortController | null>(null);

  const loadTree = React.useCallback(async (path: string) => {
    setTreeError(null);
    try {
      const qs = path ? `?path=${encodeURIComponent(path)}` : "";
      const res = await apiFetch(`/api/logs/tree${qs}`);
      if (!res.ok) throw new Error(`failed_to_load_tree_${res.status}`);
      const json = await res.json();
      setTree(json);
      setTreePath(json?.path ?? "");
    } catch (e: any) {
      setTreeError(e?.message ?? "failed_to_load_tree");
      setTree(null);
    }
  }, []);

  React.useEffect(() => {
    void loadTree("");
    return () => {
      tailAbortRef.current?.abort();
    };
  }, [loadTree]);

  const pathParts = React.useMemo(() => {
    const p = (treePath || "").trim();
    if (!p) return [] as string[];
    return p.split(/[/\\]+/).filter(Boolean);
  }, [treePath]);

  const stopTail = React.useCallback(() => {
    tailAbortRef.current?.abort();
    tailAbortRef.current = null;
    setTailRunning(false);
  }, []);

  const startTail = React.useCallback(async (siteId: string, logType: string) => {
    stopTail();
    setTailLines([]);
    setTailError(null);
    setTailRunning(true);

    const token = getAccessToken();
    if (!token) {
      setTailError("not_authenticated");
      setTailRunning(false);
      return;
    }

    const controller = new AbortController();
    tailAbortRef.current = controller;

    try {
      const url = `${getApiBase()}/api/logs/tail/${encodeURIComponent(siteId)}/${encodeURIComponent(logType)}`;
      const res = await fetch(url, {
        method: "GET",
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: "text/event-stream"
        },
        signal: controller.signal
      });
      if (!res.ok) throw new Error(`failed_to_tail_${res.status}`);
      if (!res.body) throw new Error("no_stream");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        let idx: number;
        while ((idx = buffer.indexOf("\n\n")) >= 0) {
          const event = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);

          const m = event.match(/^data:\s*(.*)$/m);
          if (!m) continue;
          const payload = (m[1] ?? "").replace(/\\n/g, "\n");
          setTailLines((prev) => {
            const next = prev.length > 500 ? prev.slice(prev.length - 400) : prev.slice();
            next.push(payload);
            return next;
          });
        }
      }
    } catch (e: any) {
      if (e?.name === "AbortError") return;
      setTailError(e?.message ?? "failed_to_tail");
    } finally {
      setTailRunning(false);
    }
  }, [stopTail]);

  const onEntryClick = React.useCallback(
    async (name: string, type: string) => {
      if (type === "dir") {
        const next = treePath ? `${treePath}/${name}` : name;
        await loadTree(next);
        return;
      }
    },
    [loadTree, treePath]
  );

  const canSelectSite = pathParts.length === 0;
  const canSelectLogType = pathParts.length === 1;
  const selectedFromPathSite = canSelectLogType ? pathParts[0] : "";

  React.useEffect(() => {
    if (canSelectLogType) {
      setSelectedSiteId(selectedFromPathSite);
    }
  }, [canSelectLogType, selectedFromPathSite]);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Log Explorer</h1>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="rounded border border-slate-800 bg-slate-950 p-4 text-zinc-200 space-y-3">
          <div className="flex items-center justify-between">
            <div className="text-lg font-semibold">Log Tree</div>
            <button className="rounded bg-slate-800 px-3 py-2" onClick={() => void loadTree(treePath)}>
              Refresh
            </button>
          </div>

          {treeError ? <div className="rounded border border-red-900 bg-red-950 p-3 text-red-200">{treeError}</div> : null}

          <div className="flex flex-wrap items-center gap-2 text-sm">
            <button
              className="rounded bg-slate-800 px-2 py-1"
              onClick={() => void loadTree("")}
              disabled={!treePath}
            >
              Root
            </button>
            {pathParts.map((p, i) => {
              const sub = pathParts.slice(0, i + 1).join("/");
              return (
                <button
                  key={`${p}-${i}`}
                  className="rounded bg-slate-800 px-2 py-1"
                  onClick={() => void loadTree(sub)}
                >
                  {p}
                </button>
              );
            })}
          </div>

          <div className="max-h-[420px] overflow-auto rounded border border-slate-800">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-slate-950">
                <tr className="border-b border-slate-800">
                  <th className="p-2 text-left">Name</th>
                  <th className="p-2 text-left">Type</th>
                </tr>
              </thead>
              <tbody>
                {(tree?.entries ?? []).map((e) => (
                  <tr key={e.name} className="border-b border-slate-900 hover:bg-slate-900">
                    <td className="p-2">
                      <button className="text-sky-300" onClick={() => void onEntryClick(e.name, e.type)}>
                        {e.name}
                      </button>
                    </td>
                    <td className="p-2">{e.type}</td>
                  </tr>
                ))}
                {!tree?.entries?.length ? (
                  <tr>
                    <td className="p-2 text-slate-400" colSpan={2}>
                      No entries
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>

          <div className="rounded border border-slate-800 bg-slate-900/30 p-3 text-sm text-slate-200 space-y-1">
            <div className="font-semibold">How to use</div>
            <div>1) Click a site folder</div>
            <div>2) Click a log type folder</div>
            <div>3) Click Start Tail on the right</div>
          </div>
        </div>

        <div className="rounded border border-slate-800 bg-slate-950 p-4 text-zinc-200 space-y-3">
          <div className="flex items-center justify-between">
            <div className="text-lg font-semibold">Tail</div>
            <div className="flex items-center gap-2">
              <button
                className="rounded bg-slate-800 px-3 py-2 disabled:opacity-50"
                onClick={() => {
                  setTailLines([]);
                  setTailError(null);
                }}
                disabled={!tailLines.length}
              >
                Clear
              </button>
              <button
                className="rounded bg-slate-800 px-3 py-2 disabled:opacity-50"
                onClick={stopTail}
                disabled={!tailRunning}
              >
                Stop
              </button>
            </div>
          </div>

          {tailError ? <div className="rounded border border-red-900 bg-red-950 p-3 text-red-200">{tailError}</div> : null}

          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <input
              className="rounded border border-slate-800 bg-slate-900 p-2"
              placeholder={canSelectSite ? "Select a site from the tree" : "Site ID"}
              value={selectedSiteId}
              onChange={(e) => setSelectedSiteId(e.target.value)}
              disabled={!canSelectSite}
            />
            <input
              className="rounded border border-slate-800 bg-slate-900 p-2"
              placeholder={canSelectLogType ? "Select a log type from the tree" : "Log type"}
              value={selectedLogType}
              onChange={(e) => setSelectedLogType(e.target.value)}
              disabled={!canSelectLogType}
            />
          </div>

          <div className="flex items-center justify-end">
            <button
              className="rounded bg-sky-600 px-3 py-2 text-white disabled:opacity-50"
              disabled={!selectedSiteId || !selectedLogType || tailRunning}
              onClick={() => void startTail(selectedSiteId, selectedLogType)}
            >
              {tailRunning ? "Tailing..." : "Start Tail"}
            </button>
          </div>

          <pre className="max-h-[520px] overflow-auto rounded border border-slate-800 bg-black p-3 text-xs text-zinc-200 whitespace-pre-wrap">
            {tailLines.join("")}
          </pre>
        </div>
      </div>
    </div>
  );
}
