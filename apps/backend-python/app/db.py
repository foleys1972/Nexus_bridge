from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import aiosqlite
import os
import secrets


@dataclass(frozen=True)
class Db:
    conn: aiosqlite.Connection


async def ensure_dirs() -> None:
    base = Path(os.environ.get("DB_BASE_DIR") or Path(__file__).resolve().parents[3])
    (base / "data").mkdir(parents=True, exist_ok=True)
    (base / "logs").mkdir(parents=True, exist_ok=True)


async def init_db() -> Db:
    await ensure_dirs()
    default_db_path = Path(__file__).resolve().parents[3] / "data" / "app.db"
    db_path = Path(os.environ.get("DB_PATH") or default_db_path)
    conn = await aiosqlite.connect(str(db_path))
    await conn.execute("PRAGMA journal_mode=WAL")

    await conn.executescript(
        """
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
          latitude REAL,
          longitude REAL,
          command_interval_cron TEXT NOT NULL,
          log_retention_days INTEGER NOT NULL,
          max_file_size_mb INTEGER NOT NULL,
          is_active INTEGER NOT NULL,
          status TEXT NOT NULL,
          last_connected_at TEXT,
          last_error TEXT,
          subscribe_calls INTEGER NOT NULL DEFAULT 0,
          subscribe_presence INTEGER NOT NULL DEFAULT 0,
          subscribe_alerts INTEGER NOT NULL DEFAULT 0,
          subscribe_events INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS app_connections (
          id TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          token TEXT,
          latitude REAL,
          longitude REAL,
          enhanced_messaging INTEGER NOT NULL DEFAULT 0,
          allowed_site_ids_json TEXT NOT NULL,
          revoked INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS app_settings (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS site_poll_rules (
          site_id TEXT NOT NULL,
          command TEXT NOT NULL,
          enabled INTEGER NOT NULL DEFAULT 0,
          interval_seconds INTEGER NOT NULL,
          updated_at TEXT NOT NULL,
          PRIMARY KEY (site_id, command)
        );

        CREATE TABLE IF NOT EXISTS site_poll_state (
          site_id TEXT NOT NULL,
          command TEXT NOT NULL,
          last_id INTEGER,
          updated_at TEXT NOT NULL,
          PRIMARY KEY (site_id, command)
        );
        """
    )

    await _migrate_sites(conn)
    await _migrate_app_connections(conn)
    await conn.commit()

    return Db(conn=conn)


async def _migrate_sites(conn: aiosqlite.Connection) -> None:
    async with conn.execute("PRAGMA table_info(sites)") as cur:
        rows = await cur.fetchall()
    cols = {r[1] for r in rows}

    async def add_col(sql: str) -> None:
        await conn.execute(sql)

    if "subscribe_calls" not in cols:
        await add_col("ALTER TABLE sites ADD COLUMN subscribe_calls INTEGER NOT NULL DEFAULT 0")
    if "subscribe_presence" not in cols:
        await add_col("ALTER TABLE sites ADD COLUMN subscribe_presence INTEGER NOT NULL DEFAULT 0")
    if "subscribe_alerts" not in cols:
        await add_col("ALTER TABLE sites ADD COLUMN subscribe_alerts INTEGER NOT NULL DEFAULT 0")
    if "subscribe_events" not in cols:
        await add_col("ALTER TABLE sites ADD COLUMN subscribe_events INTEGER NOT NULL DEFAULT 0")

    if "latitude" not in cols:
        await add_col("ALTER TABLE sites ADD COLUMN latitude REAL")
    if "longitude" not in cols:
        await add_col("ALTER TABLE sites ADD COLUMN longitude REAL")

    # Ensure poll rules table exists for older DBs (CREATE TABLE IF NOT EXISTS is idempotent)
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS site_poll_rules (
          site_id TEXT NOT NULL,
          command TEXT NOT NULL,
          enabled INTEGER NOT NULL DEFAULT 0,
          interval_seconds INTEGER NOT NULL,
          updated_at TEXT NOT NULL,
          PRIMARY KEY (site_id, command)
        )
        """
    )

    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS site_poll_state (
          site_id TEXT NOT NULL,
          command TEXT NOT NULL,
          last_id INTEGER,
          updated_at TEXT NOT NULL,
          PRIMARY KEY (site_id, command)
        )
        """
    )


async def _migrate_app_connections(conn: aiosqlite.Connection) -> None:
    async with conn.execute("PRAGMA table_info(app_connections)") as cur:
        rows = await cur.fetchall()
    cols = {r[1] for r in rows}

    if "token" not in cols:
        await conn.execute("ALTER TABLE app_connections ADD COLUMN token TEXT")

    if "latitude" not in cols:
        await conn.execute("ALTER TABLE app_connections ADD COLUMN latitude REAL")
    if "longitude" not in cols:
        await conn.execute("ALTER TABLE app_connections ADD COLUMN longitude REAL")

    if "enhanced_messaging" not in cols:
        await conn.execute("ALTER TABLE app_connections ADD COLUMN enhanced_messaging INTEGER NOT NULL DEFAULT 0")

    async with conn.execute("SELECT id FROM app_connections WHERE token IS NULL") as cur:
        missing = await cur.fetchall()
    for (conn_id,) in missing:
        tok = secrets.token_hex(16)
        await conn.execute("UPDATE app_connections SET token = ? WHERE id = ?", (tok, str(conn_id)))
