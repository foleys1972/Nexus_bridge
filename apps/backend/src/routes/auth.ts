import { Router, type Request, type Response } from "express";
import bcrypt from "bcrypt";
import type { Db } from "../lib/db.js";
import { signAccessToken, signRefreshToken, type Role } from "../lib/auth.js";

export function authRouter(db: Db): Router {
  const r = Router();

  r.post("/login", async (req: Request, res: Response) => {
    const { email, password } = (req.body ?? {}) as { email?: string; password?: string };
    if (!email || !password) {
      res.status(400).json({ error: "invalid_request" });
      return;
    }

    const row = db
      .prepare("SELECT id, password_hash, role FROM users WHERE email = ?")
      .get(email) as { id: string; password_hash: string; role: Role } | undefined;

    if (!row) {
      res.status(401).json({ error: "invalid_credentials" });
      return;
    }

    const ok = await bcrypt.compare(password, row.password_hash);
    if (!ok) {
      res.status(401).json({ error: "invalid_credentials" });
      return;
    }

    res.json({
      access_token: signAccessToken({ sub: row.id, role: row.role }),
      refresh_token: signRefreshToken({ sub: row.id, role: row.role })
    });
  });

  return r;
}
