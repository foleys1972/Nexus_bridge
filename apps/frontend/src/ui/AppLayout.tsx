import React from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useNavigate } from "react-router-dom";
import { clearTokens } from "../auth";

const linkBase =
  "block rounded px-3 py-2 text-sm transition hover:bg-slate-900 hover:text-white";

export function AppLayout() {
  const nav = useNavigate();
  return (
    <div className="min-h-screen grid grid-cols-[260px_1fr]">
      <aside className="border-r border-slate-800 bg-slate-950 p-4">
        <div className="flex items-center justify-between">
          <div className="text-lg font-semibold text-white">NexusBridge</div>
          <button
            className="rounded bg-slate-800 px-3 py-2 text-xs text-zinc-200"
            onClick={() => {
              clearTokens();
              nav("/login");
            }}
          >
            Sign out
          </button>
        </div>
        <div className="mt-6 space-y-1">
          <NavLink
            to="/"
            end
            className={({ isActive }) =>
              `${linkBase} ${isActive ? "bg-slate-900 text-white" : "text-zinc-200"}`
            }
          >
            Dashboard
          </NavLink>
          <NavLink
            to="/connections"
            className={({ isActive }) =>
              `${linkBase} ${isActive ? "bg-slate-900 text-white" : "text-zinc-200"}`
            }
          >
            Connections
          </NavLink>
          <NavLink
            to="/clients"
            className={({ isActive }) =>
              `${linkBase} ${isActive ? "bg-slate-900 text-white" : "text-zinc-200"}`
            }
          >
            Client Monitor
          </NavLink>
          <NavLink
            to="/logs"
            className={({ isActive }) =>
              `${linkBase} ${isActive ? "bg-slate-900 text-white" : "text-zinc-200"}`
            }
          >
            Log Explorer
          </NavLink>
          <NavLink
            to="/users"
            className={({ isActive }) =>
              `${linkBase} ${isActive ? "bg-slate-900 text-white" : "text-zinc-200"}`
            }
          >
            Users
          </NavLink>
          <NavLink
            to="/settings"
            className={({ isActive }) =>
              `${linkBase} ${isActive ? "bg-slate-900 text-white" : "text-zinc-200"}`
            }
          >
            Settings
          </NavLink>
          <NavLink
            to="/reporting"
            className={({ isActive }) =>
              `${linkBase} ${isActive ? "bg-slate-900 text-white" : "text-zinc-200"}`
            }
          >
            Reporting
          </NavLink>
        </div>
      </aside>

      <main className="p-6">
        <Outlet />
      </main>
    </div>
  );
}
