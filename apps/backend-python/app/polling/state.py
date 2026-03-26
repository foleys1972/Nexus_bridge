from __future__ import annotations

from datetime import datetime, timezone

from app.db import Db


def _utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


async def get_last_id(db: Db, *, site_id: str, command: str) -> int | None:
    async with db.conn.execute(
        "SELECT last_id FROM site_poll_state WHERE site_id = ? AND command = ?",
        (site_id, command),
    ) as cur:
        row = await cur.fetchone()
    if not row:
        return None
    last_id = row[0]
    return int(last_id) if last_id is not None else None


async def set_last_id(db: Db, *, site_id: str, command: str, last_id: int | None) -> None:
    await db.conn.execute(
        """
        INSERT INTO site_poll_state (site_id, command, last_id, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(site_id, command) DO UPDATE SET
          last_id = excluded.last_id,
          updated_at = excluded.updated_at
        """,
        (site_id, command, int(last_id) if last_id is not None else None, _utcnow()),
    )
    await db.conn.commit()
