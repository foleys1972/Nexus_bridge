import React from "react";
import { createBrowserRouter } from "react-router-dom";
import { AppLayout } from "./ui/AppLayout";
import { DashboardPage } from "./views/DashboardPage";
import { ConnectionsPage } from "./views/ConnectionsPage";
import { ClientsPage } from "./views/ClientsPage";
import { LogsPage } from "./views/LogsPage";
import { UsersPage } from "./views/UsersPage";
import { SettingsPage } from "./views/SettingsPage";
import { ReportingPage } from "./views/ReportingPage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppLayout />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: "connections", element: <ConnectionsPage /> },
      { path: "clients", element: <ClientsPage /> },
      { path: "logs", element: <LogsPage /> },
      { path: "users", element: <UsersPage /> },
      { path: "settings", element: <SettingsPage /> },
      { path: "reporting", element: <ReportingPage /> }
    ]
  }
]);
