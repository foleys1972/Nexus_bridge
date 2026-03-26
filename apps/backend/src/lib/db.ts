import fs from "node:fs";
import path from "node:path";
import Database from "better-sqlite3";

export type Db = Database.Database;

export function ensureDataDir(): void {
  fs.mkdirSync(path.resolve(process.cwd(), "../../data"), { recursive: true });
  fs.mkdirSync(path.resolve(process.cwd(), "../../logs"), { recursive: true });
}

export function initDb(): Db {
  const dbPath = path.resolve(process.cwd(), "../../data/app.db");
  const db = new Database(dbPath);
  db.pragma("journal_mode = WAL");

  db.exec(`
    CREATE TABLE IF NOT EXISTS users (
      id TEXT PRIMARY KEY,
      email TEXT NOT NULL UNIQUE,
      password_hash TEXT NOT NULL,
      role TEXT NOT NULL,
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS sites (
      id TEXT PRIMARY KEY,
      site_name TEXT NOT NULL,
      wss_url TEXT NOT NULL,
      token_enc TEXT NOT NULL,
      command_interval_cron TEXT NOT NULL,
      log_retention_days INTEGER NOT NULL,
      max_file_size_mb INTEGER NOT NULL,
      is_active INTEGER NOT NULL,
      status TEXT NOT NULL,
      last_connected_at TEXT,
      last_error TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
  `);

  return db;
}
