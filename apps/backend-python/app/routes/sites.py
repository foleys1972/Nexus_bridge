from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db import Db
from app.deps import get_db
from app.auth.deps import require_operator, require_read_only

router = APIRouter(prefix="/sites")


POLL_COMMANDS: tuple[str, ...] = (
    "get_calls",
    "get_zones",
    "get_users",
    "get_turrets",
    "get_events",
    "get_version",
    "get_tpos",
    "get_lines",
    "get_shared_profiles",
    "get_health_api_report",
)


def _utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class SiteCreateRequest(BaseModel):
    site_name: str
    wss_url: str
    token: str
    latitude: float | None = None
    longitude: float | None = None
    command_interval_cron: str | None = None
    log_retention_days: int | None = None
    max_file_size_mb: int | None = None
    is_active: bool | None = None

    subscribe_calls: bool | None = None
    subscribe_presence: bool | None = None
    subscribe_alerts: bool | None = None
    subscribe_events: bool | None = None


class PollRule(BaseModel):
    command: str
    enabled: bool
    interval_seconds: int


class PutPollRulesRequest(BaseModel):
    rules: list[PollRule]


class SiteUpdateRequest(BaseModel):
    site_name: str | None = None
    wss_url: str | None = None
    token: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    command_interval_cron: str | None = None
    log_retention_days: int | None = None
    max_file_size_mb: int | None = None
    is_active: bool | None = None

    subscribe_calls: bool | None = None
    subscribe_presence: bool | None = None
    subscribe_alerts: bool | None = None
    subscribe_events: bool | None = None


@router.get("")
async def list_sites(
    db: Db = Depends(get_db),
    _user: dict = Depends(require_read_only),
):
    q = """
    SELECT
      id,
      site_name,
      wss_url,
      latitude,
      longitude,
      command_interval_cron,
      log_retention_days,
      max_file_size_mb,
      is_active,
      status,
      last_connected_at,
      last_error,
      subscribe_calls,
      subscribe_presence,
      subscribe_alerts,
      subscribe_events,
      created_at,
      updated_at
    FROM sites
    ORDER BY site_name
    """

    async with db.conn.execute(q) as cur:
        rows = await cur.fetchall()

    sites = []
    for r in rows:
        (
            site_id,
            site_name,
            wss_url,
            latitude,
            longitude,
            command_interval_cron,
            log_retention_days,
            max_file_size_mb,
            is_active,
            status,
            last_connected_at,
            last_error,
            subscribe_calls,
            subscribe_presence,
            subscribe_alerts,
            subscribe_events,
            created_at,
            updated_at,
        ) = r
        sites.append(
            {
                "id": site_id,
                "site_name": site_name,
                "wss_url": wss_url,
                "latitude": latitude,
                "longitude": longitude,
                "command_interval_cron": command_interval_cron,
                "log_retention_days": log_retention_days,
                "max_file_size_mb": max_file_size_mb,
                "is_active": bool(is_active),
                "status": status,
                "last_connected_at": last_connected_at,
                "last_error": last_error,
                "subscribe_calls": bool(subscribe_calls),
                "subscribe_presence": bool(subscribe_presence),
                "subscribe_alerts": bool(subscribe_alerts),
                "subscribe_events": bool(subscribe_events),
                "created_at": created_at,
                "updated_at": updated_at,
            }
        )

    return {"sites": sites}


@router.post("")
async def create_site(
    body: SiteCreateRequest,
    db: Db = Depends(get_db),
    _user: dict = Depends(require_operator),
):
    if not body.site_name or not body.wss_url or not body.token:
        raise HTTPException(status_code=400, detail="invalid_request")

    now = _utcnow()
    site_id = str(uuid4())

    await db.conn.execute(
        """
        INSERT INTO sites (
          id, site_name, wss_url, token_enc, latitude, longitude,
          command_interval_cron, log_retention_days, max_file_size_mb,
          is_active, status, last_connected_at, last_error,
          subscribe_calls, subscribe_presence, subscribe_alerts, subscribe_events,
          created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?)
        """,
        (
            site_id,
            body.site_name,
            body.wss_url,
            body.token,  # placeholder until we add encryption back in Python
            body.latitude,
            body.longitude,
            body.command_interval_cron or "*/5 * * * *",
            body.log_retention_days or 30,
            body.max_file_size_mb or 50,
            1 if (body.is_active is True) else 0,
            "DISCONNECTED",
            1 if (body.subscribe_calls is True) else 0,
            1 if (body.subscribe_presence is True) else 0,
            1 if (body.subscribe_alerts is True) else 0,
            1 if (body.subscribe_events is True) else 0,
            now,
            now,
        ),
    )
    await db.conn.commit()

    return {"id": site_id}


@router.put("/{site_id}")
async def update_site(
    site_id: str,
    body: SiteUpdateRequest,
    db: Db = Depends(get_db),
    _user: dict = Depends(require_operator),
):
    async with db.conn.execute("SELECT id FROM sites WHERE id = ?", (site_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="not_found")

    fields = []
    params: list[object] = []

    def set_field(col: str, value: object):
        fields.append(f"{col} = ?")
        params.append(value)

    if body.site_name is not None:
        set_field("site_name", body.site_name)
    if body.wss_url is not None:
        set_field("wss_url", body.wss_url)
    if body.token is not None:
        set_field("token_enc", body.token)
    if body.latitude is not None:
        set_field("latitude", float(body.latitude))
    if body.longitude is not None:
        set_field("longitude", float(body.longitude))
    if body.command_interval_cron is not None:
        set_field("command_interval_cron", body.command_interval_cron)
    if body.log_retention_days is not None:
        set_field("log_retention_days", int(body.log_retention_days))
    if body.max_file_size_mb is not None:
        set_field("max_file_size_mb", int(body.max_file_size_mb))
    if body.is_active is not None:
        set_field("is_active", 1 if body.is_active else 0)

    if body.subscribe_calls is not None:
        set_field("subscribe_calls", 1 if body.subscribe_calls else 0)
    if body.subscribe_presence is not None:
        set_field("subscribe_presence", 1 if body.subscribe_presence else 0)
    if body.subscribe_alerts is not None:
        set_field("subscribe_alerts", 1 if body.subscribe_alerts else 0)
    if body.subscribe_events is not None:
        set_field("subscribe_events", 1 if body.subscribe_events else 0)

    set_field("updated_at", _utcnow())

    if not fields:
        return {"ok": True}

    params.append(site_id)
    await db.conn.execute(
        f"UPDATE sites SET {', '.join(fields)} WHERE id = ?",
        tuple(params),
    )
    await db.conn.commit()

    return {"ok": True}


@router.delete("/{site_id}")
async def delete_site(
    site_id: str,
    db: Db = Depends(get_db),
    _user: dict = Depends(require_operator),
):
    async with db.conn.execute("SELECT id FROM sites WHERE id = ?", (site_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="not_found")

    await db.conn.execute("BEGIN")
    try:
        await db.conn.execute("DELETE FROM site_poll_rules WHERE site_id = ?", (site_id,))
        await db.conn.execute("DELETE FROM site_poll_state WHERE site_id = ?", (site_id,))
        await db.conn.execute("DELETE FROM sites WHERE id = ?", (site_id,))
        await db.conn.commit()
    except Exception:
        await db.conn.rollback()
        raise

    return {"ok": True}


@router.get("/{site_id}/poll-rules")
async def get_poll_rules(
    site_id: str,
    db: Db = Depends(get_db),
    _user: dict = Depends(require_read_only),
):
    async with db.conn.execute("SELECT id FROM sites WHERE id = ?", (site_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="not_found")

    async with db.conn.execute(
        "SELECT command, enabled, interval_seconds FROM site_poll_rules WHERE site_id = ?",
        (site_id,),
    ) as cur:
        rows = await cur.fetchall()

    by_cmd = {r[0]: {"enabled": bool(r[1]), "interval_seconds": int(r[2])} for r in rows}

    rules = []
    for cmd in POLL_COMMANDS:
        if cmd in by_cmd:
            rules.append({"command": cmd, **by_cmd[cmd]})
        else:
            rules.append({"command": cmd, "enabled": False, "interval_seconds": 60})

    return {"site_id": site_id, "rules": rules}


@router.put("/{site_id}/poll-rules")
async def put_poll_rules(
    site_id: str,
    body: PutPollRulesRequest,
    db: Db = Depends(get_db),
    _user: dict = Depends(require_operator),
):
    async with db.conn.execute("SELECT id FROM sites WHERE id = ?", (site_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="not_found")

    now = _utcnow()

    for r in body.rules:
        if r.command not in POLL_COMMANDS:
            raise HTTPException(status_code=400, detail=f"unknown_command:{r.command}")
        if r.interval_seconds < 1:
            raise HTTPException(status_code=400, detail=f"invalid_interval:{r.command}")

    await db.conn.execute("BEGIN")
    try:
        for r in body.rules:
            await db.conn.execute(
                """
                INSERT INTO site_poll_rules (site_id, command, enabled, interval_seconds, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(site_id, command) DO UPDATE SET
                  enabled = excluded.enabled,
                  interval_seconds = excluded.interval_seconds,
                  updated_at = excluded.updated_at
                """,
                (site_id, r.command, 1 if r.enabled else 0, int(r.interval_seconds), now),
            )
        await db.conn.commit()
    except Exception:
        await db.conn.rollback()
        raise

    return {"ok": True}


@router.post("/{site_id}/connect")
async def connect_site(
    site_id: str,
    db: Db = Depends(get_db),
    _user: dict = Depends(require_operator),
):
    async with db.conn.execute("SELECT id FROM sites WHERE id = ?", (site_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="not_found")

    now = _utcnow()
    await db.conn.execute(
        """
        UPDATE sites
        SET is_active = 1,
            status = 'DISCONNECTED',
            last_error = NULL,
            updated_at = ?
        WHERE id = ?
        """,
        (now, site_id),
    )
    await db.conn.commit()
    return {"ok": True}


@router.post("/{site_id}/disconnect")
async def disconnect_site(
    site_id: str,
    db: Db = Depends(get_db),
    _user: dict = Depends(require_operator),
):
    async with db.conn.execute("SELECT id FROM sites WHERE id = ?", (site_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="not_found")

    now = _utcnow()
    await db.conn.execute(
        """
        UPDATE sites
        SET is_active = 0,
            status = 'DISCONNECTED',
            last_error = NULL,
            updated_at = ?
        WHERE id = ?
        """,
        (now, site_id),
    )
    await db.conn.commit()
    return {"ok": True}
