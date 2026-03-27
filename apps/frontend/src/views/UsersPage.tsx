import React from "react";
import { apiFetch } from "../api";

export function UsersPage() {
  type Me = { id: string; role: string };
  type UserRow = { id: string; email: string; role: string; created_at: string };

  const [me, setMe] = React.useState<Me | null>(null);
  const [users, setUsers] = React.useState<UserRow[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [forbidden, setForbidden] = React.useState(false);

  const load = React.useCallback(async () => {
    setError(null);
    setForbidden(false);
    setLoading(true);
    try {
      const mr = await apiFetch("/api/auth/me");
      if (!mr.ok) throw new Error(`failed_to_load_me_${mr.status}`);
      const mj = await mr.json();
      setMe({ id: String(mj?.id || ""), role: String(mj?.role || "") });

      const res = await apiFetch("/api/users");
      if (res.status === 403) {
        setForbidden(true);
        setUsers([]);
        return;
      }
      if (!res.ok) throw new Error(`failed_to_load_users_${res.status}`);
      const json = await res.json();
      setUsers((json?.users ?? []) as UserRow[]);
    } catch (e: any) {
      setError(e?.message ?? "failed_to_load");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  const [createEmail, setCreateEmail] = React.useState("");
  const [createPassword, setCreatePassword] = React.useState("");
  const [createRole, setCreateRole] = React.useState("operator");
  const [creating, setCreating] = React.useState(false);

  const createUser = React.useCallback(async () => {
    setError(null);
    setCreating(true);
    try {
      const res = await apiFetch("/api/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: createEmail, password: createPassword, role: createRole })
      });
      if (res.status === 403) {
        setForbidden(true);
        return;
      }
      if (!res.ok) throw new Error(`failed_to_create_${res.status}`);
      setCreateEmail("");
      setCreatePassword("");
      setCreateRole("operator");
      await load();
    } catch (e: any) {
      setError(e?.message ?? "failed_to_create");
    } finally {
      setCreating(false);
    }
  }, [createEmail, createPassword, createRole, load]);

  const [editUserId, setEditUserId] = React.useState<string | null>(null);
  const [editEmail, setEditEmail] = React.useState("");
  const [editRole, setEditRole] = React.useState("operator");
  const [editPassword, setEditPassword] = React.useState("");
  const [saving, setSaving] = React.useState(false);

  const openEdit = React.useCallback((u: UserRow) => {
    setEditUserId(u.id);
    setEditEmail(u.email);
    setEditRole(u.role);
    setEditPassword("");
  }, []);

  const saveEdit = React.useCallback(async () => {
    if (!editUserId) return;
    setError(null);
    setSaving(true);
    try {
      const body: any = { role: editRole };
      if (editPassword) body.password = editPassword;
      const res = await apiFetch(`/api/users/${editUserId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      if (res.status === 403) {
        setForbidden(true);
        return;
      }
      if (!res.ok) throw new Error(`failed_to_save_${res.status}`);
      setEditUserId(null);
      await load();
    } catch (e: any) {
      setError(e?.message ?? "failed_to_save");
    } finally {
      setSaving(false);
    }
  }, [editPassword, editRole, editUserId, load]);

  const deleteUser = React.useCallback(
    async (u: UserRow) => {
      const ok = window.confirm(`Delete user ${u.email}?`);
      if (!ok) return;
      setError(null);
      try {
        const res = await apiFetch(`/api/users/${u.id}`, { method: "DELETE" });
        if (res.status === 403) {
          setForbidden(true);
          return;
        }
        if (!res.ok) throw new Error(`failed_to_delete_${res.status}`);
        await load();
      } catch (e: any) {
        setError(e?.message ?? "failed_to_delete");
      }
    },
    [load]
  );

  const editModal = React.useMemo(() => {
    if (!editUserId) return null;
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
        <div className="w-full max-w-xl rounded border border-slate-800 bg-slate-950 p-4 text-zinc-200">
          <div className="flex items-center justify-between">
            <div className="text-lg font-semibold">Edit User</div>
            <button className="rounded bg-slate-800 px-3 py-2" onClick={() => setEditUserId(null)}>
              Close
            </button>
          </div>

          <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
            <input
              className="rounded border border-slate-800 bg-slate-900 p-2"
              value={editEmail}
              disabled
            />
            <select
              className="rounded border border-slate-800 bg-slate-900 p-2"
              value={editRole}
              onChange={(e) => setEditRole(e.target.value)}
            >
              <option value="admin">admin</option>
              <option value="operator">operator</option>
              <option value="read_only">read_only</option>
            </select>
            <input
              className="rounded border border-slate-800 bg-slate-900 p-2 md:col-span-2"
              placeholder="New password (optional, min 8 chars)"
              type="password"
              value={editPassword}
              onChange={(e) => setEditPassword(e.target.value)}
            />
          </div>

          <div className="mt-4 flex items-center justify-end gap-3">
            <button
              className="rounded bg-sky-600 px-3 py-2 text-white disabled:opacity-50"
              onClick={() => void saveEdit()}
              disabled={saving}
            >
              {saving ? "Saving..." : "Save"}
            </button>
          </div>
        </div>
      </div>
    );
  }, [editEmail, editPassword, editRole, editUserId, saving, saveEdit]);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">User Management</h1>

      <div className="rounded border border-slate-800 bg-slate-950 p-4 text-zinc-200">
        <div className="flex items-center justify-between">
          <div className="text-sm text-zinc-400">
            Signed in as <span className="font-mono">{me?.id ?? ""}</span> ({me?.role ?? ""})
          </div>
          <button className="rounded bg-slate-800 px-3 py-2" onClick={() => void load()}>
            Refresh
          </button>
        </div>
      </div>

      {error ? <div className="rounded border border-red-900 bg-red-950 p-3 text-red-200">{error}</div> : null}
      {forbidden ? (
        <div className="rounded border border-amber-900 bg-amber-950 p-3 text-amber-200">
          This page is admin-only. Log in with an admin account.
        </div>
      ) : null}

      <div className="rounded border border-slate-800 bg-slate-950 p-4 text-zinc-200 space-y-3">
        <div className="text-lg font-semibold">Create User</div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <input
            className="rounded border border-slate-800 bg-slate-900 p-2"
            placeholder="email"
            value={createEmail}
            onChange={(e) => setCreateEmail(e.target.value)}
          />
          <input
            className="rounded border border-slate-800 bg-slate-900 p-2"
            placeholder="password (min 8 chars)"
            type="password"
            value={createPassword}
            onChange={(e) => setCreatePassword(e.target.value)}
          />
          <select
            className="rounded border border-slate-800 bg-slate-900 p-2"
            value={createRole}
            onChange={(e) => setCreateRole(e.target.value)}
          >
            <option value="admin">admin</option>
            <option value="operator">operator</option>
            <option value="read_only">read_only</option>
          </select>
        </div>
        <div className="flex items-center justify-end">
          <button
            className="rounded bg-sky-600 px-3 py-2 text-white disabled:opacity-50"
            onClick={() => void createUser()}
            disabled={creating || !createEmail || !createPassword}
          >
            {creating ? "Creating..." : "Create"}
          </button>
        </div>
      </div>

      <div className="rounded border border-slate-800 bg-slate-950 p-4 text-zinc-200">
        <div className="mb-3 flex items-center justify-between">
          <div className="text-lg font-semibold">Users</div>
          {loading ? <div className="text-sm text-zinc-400">Loading...</div> : null}
        </div>
        <div className="overflow-auto">
          <table className="min-w-[900px] table-auto border-collapse text-sm">
            <thead>
              <tr className="text-left text-zinc-400">
                <th className="border-b border-slate-800 p-2">Email</th>
                <th className="border-b border-slate-800 p-2">Role</th>
                <th className="border-b border-slate-800 p-2">Created</th>
                <th className="border-b border-slate-800 p-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="hover:bg-slate-900/40">
                  <td className="border-b border-slate-900 p-2 font-mono">{u.email}</td>
                  <td className="border-b border-slate-900 p-2">{u.role}</td>
                  <td className="border-b border-slate-900 p-2 text-zinc-400">{u.created_at}</td>
                  <td className="border-b border-slate-900 p-2">
                    <div className="flex items-center gap-2">
                      <button className="rounded bg-slate-800 px-3 py-2" onClick={() => openEdit(u)}>
                        Edit
                      </button>
                      <button className="rounded bg-rose-700 px-3 py-2 text-white" onClick={() => void deleteUser(u)}>
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {users.length === 0 ? (
                <tr>
                  <td className="p-3 text-zinc-400" colSpan={4}>
                    No users.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>

      {editModal}
    </div>
  );
}
