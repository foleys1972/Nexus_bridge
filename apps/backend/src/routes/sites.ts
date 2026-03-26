import { Router, type Request, type Response } from "express";
import { randomUUID } from "node:crypto";
import type { Db } from "../lib/db.js";
import { encryptToBase64 } from "../lib/crypto.js";
import { authRequired, requireRole } from "../middleware/rbac.js";

export function sitesRouter(db: Db): Router {
  const r = Router();
  r.use(authRequired);

  r.get("/", (_req: Request, res: Response) => {
    const sites = db
      .prepare(
        "SELECT id, site_name, wss_url, command_interval_cron, log_retention_days, max_file_size_mb, is_active, status, last_connected_at, last_error, created_at, updated_at FROM sites ORDER BY site_name"
      )
      .all();
    res.json({ sites });
  });

  r.post("/", requireRole(["Admin", "Operator"]), (req: Request, res: Response) => {
    const body = (req.body ?? {}) as {
      site_name?: string;
      wss_url?: string;
      token?: string;
      command_interval_cron?: string;
      log_retention_days?: number;
      max_file_size_mb?: number;
      is_active?: boolean;
    };

    if (!body.site_name || !body.wss_url || !body.token) {
      res.status(400).json({ error: "invalid_request" });
      return;
    }

    const now = new Date().toISOString();
    const id = randomUUID();
    db.prepare(
      "INSERT INTO sites (id, site_name, wss_url, token_enc, command_interval_cron, log_retention_days, max_file_size_mb, is_active, status, last_connected_at, last_error, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)"
    ).run(
      id,
      body.site_name,
      body.wss_url,
      encryptToBase64(body.token),
      body.command_interval_cron ?? "*/5 * * * *",
      body.log_retention_days ?? 30,
      body.max_file_size_mb ?? 50,
      body.is_active ? 1 : 0,
      "DISCONNECTED",
      now,
      now
    );

    res.status(201).json({ id });
  });

  r.put("/:id/connect", requireRole(["Admin", "Operator"]), (req: Request, res: Response) => {
    const { id } = req.params;
    db.prepare("UPDATE sites SET status = ?, updated_at = ? WHERE id = ?").run(
      "CONNECTING",
      new Date().toISOString(),
      id
    );
    res.json({ ok: true });
  });

  r.put(
    "/:id/disconnect",
    requireRole(["Admin", "Operator"]),
    (req: Request, res: Response) => {
    const { id } = req.params;
    db.prepare("UPDATE sites SET status = ?, updated_at = ? WHERE id = ?").run(
      "DISCONNECTED",
      new Date().toISOString(),
      id
    );
    res.json({ ok: true });
    }
  );

  return r;
}
