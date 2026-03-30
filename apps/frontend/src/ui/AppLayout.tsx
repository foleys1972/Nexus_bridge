import React from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { clearTokens, getAccessToken } from "../auth";

const linkBase =
  "block rounded px-3 py-2 text-sm transition hover:bg-slate-900 hover:text-white";

export function AppLayout() {
  const nav = useNavigate();
  const [hasToken, setHasToken] = React.useState<boolean>(() => !!getAccessToken());

  React.useEffect(() => {
    const id = window.setInterval(() => setHasToken(!!getAccessToken()), 500);
    return () => window.clearInterval(id);
  }, []);

  return (
    <div className="min-h-screen grid grid-cols-[260px_1fr]">
      <aside className="border-r border-slate-800 bg-slate-950 p-4">
        <div className="text-lg font-semibold text-white">NexusBridge</div>
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
        <div className="mb-4 flex items-center justify-end">
          {hasToken ? (
            <button
              className="rounded bg-slate-800 px-3 py-2 text-sm text-white"
              onClick={() => {
                clearTokens();
                setHasToken(false);
                nav("/login", { replace: true });
              }}
            >
              Logout
            </button>
          ) : (
            <button
              className="rounded bg-sky-600 px-3 py-2 text-sm text-white"
              onClick={() => nav("/login")}
            >
              Login
            </button>
          )}
        </div>
        <Outlet />
      </main>
    </div>
  );
}
