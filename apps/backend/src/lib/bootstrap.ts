import { randomUUID } from "node:crypto";
import bcrypt from "bcrypt";
import type { Db } from "./db.js";

export async function ensureAdminUser(db: Db): Promise<void> {
  const email = process.env.ADMIN_EMAIL;
  const password = process.env.ADMIN_PASSWORD;
  if (!email || !password) return;

  const existing = db.prepare("SELECT id FROM users WHERE email = ?").get(email) as
    | { id: string }
    | undefined;
  if (existing) return;

  const hash = await bcrypt.hash(password, 12);
  db.prepare(
    "INSERT INTO users (id, email, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)"
  ).run(randomUUID(), email, hash, "Admin", new Date().toISOString());
}
