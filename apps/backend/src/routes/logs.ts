import { Router, type Request, type Response } from "express";
import fs from "node:fs";
import path from "node:path";
import type { AppConfig } from "../lib/config.js";
import { authRequired } from "../middleware/rbac.js";

export function logsRouter(config: AppConfig): Router {
  const r = Router();
  r.use(authRequired);

  r.get("/tree", (_req: Request, res: Response) => {
    const root = path.resolve(process.cwd(), "../../", config.logging.base_path);
    if (!fs.existsSync(root)) {
      res.json({ root, entries: [] });
      return;
    }

    const entries = fs.readdirSync(root, { withFileTypes: true }).map((d: fs.Dirent) => ({
      name: d.name,
      type: d.isDirectory() ? "dir" : "file"
    }));
    res.json({ root, entries });
  });

  return r;
}
