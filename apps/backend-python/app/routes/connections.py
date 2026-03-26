from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import get_db
from app.db import Db
from app.proxy.server import hub
from app.auth.deps import require_operator, require_read_only

router = APIRouter(prefix="/connections")


def _utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class CreateConnectionRequest(BaseModel):
    name: str
    allowed_site_ids: list[str]
    latitude: float | None = None
    longitude: float | None = None


class UpdateConnectionRequest(BaseModel):
    name: str | None = None
    allowed_site_ids: list[str] | None = None
    latitude: float | None = None
    longitude: float | None = None
    enhanced_messaging: bool | None = None


@router.get("")
async def list_connections(
    db: Db = Depends(get_db),
    _user: dict = Depends(require_read_only),
):
    async with db.conn.execute(
        "SELECT id, name, latitude, longitude, enhanced_messaging, allowed_site_ids_json, revoked, created_at FROM app_connections ORDER BY created_at DESC"
    ) as cur:
        rows = await cur.fetchall()

    out = []
    for r in rows:
        conn_id, name, latitude, longitude, enhanced_messaging, allowed_site_ids_json, revoked, created_at = r
        try:
            allowed_site_ids = json.loads(allowed_site_ids_json or "[]")
            if not isinstance(allowed_site_ids, list):
                allowed_site_ids = []
        except Exception:
            allowed_site_ids = []
        out.append(
            {
                "id": conn_id,
                "name": name,
                "latitude": latitude,
                "longitude": longitude,
                "enhanced_messaging": bool(enhanced_messaging),
                "allowed_site_ids": allowed_site_ids,
                "revoked": bool(revoked),
                "created_at": created_at,
            }
        )
    return {"connections": out}


@router.get("/active")
async def list_active_connections(
    db: Db = Depends(get_db),
    _user: dict = Depends(require_read_only),
):
    active = await hub.list_active()
    conn_ids = [a.get("conn_id") for a in active if a.get("conn_id")]
    if not conn_ids:
        return {"active": []}

    placeholders = ",".join(["?"] * len(conn_ids))
    async with db.conn.execute(
        f"SELECT id, name, enhanced_messaging, revoked FROM app_connections WHERE id IN ({placeholders})",
        tuple(conn_ids),
    ) as cur:
        rows = await cur.fetchall()

    meta_by_id = {str(r[0]): {"name": r[1], "enhanced_messaging": bool(r[2]), "revoked": bool(r[3])} for r in rows}

    out = []
    for a in active:
        cid = str(a.get("conn_id") or "")
        out.append({**a, **meta_by_id.get(cid, {}), "conn_id": cid})

    out.sort(key=lambda x: x.get("connected_at") or 0, reverse=True)
    return {"active": out}


@router.put("/{conn_id}")
async def update_connection(
    conn_id: str,
    body: UpdateConnectionRequest,
    db: Db = Depends(get_db),
    _user: dict = Depends(require_operator),
):
    async with db.conn.execute("SELECT id FROM app_connections WHERE id = ?", (conn_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="not_found")

    fields: list[str] = []
    values: list[object] = []

    if body.name is not None:
        fields.append("name = ?")
        values.append(body.name)
    if body.latitude is not None:
        fields.append("latitude = ?")
        values.append(body.latitude)
    if body.longitude is not None:
        fields.append("longitude = ?")
        values.append(body.longitude)
    if body.enhanced_messaging is not None:
        fields.append("enhanced_messaging = ?")
        values.append(1 if body.enhanced_messaging else 0)
    if body.allowed_site_ids is not None:
        fields.append("allowed_site_ids_json = ?")
        values.append(json.dumps(body.allowed_site_ids))

    if not fields:
        return {"ok": True}

    values.append(conn_id)
    await db.conn.execute(f"UPDATE app_connections SET {', '.join(fields)} WHERE id = ?", tuple(values))
    await db.conn.commit()
    return {"ok": True}


@router.post("/token")
async def create_token(
    body: CreateConnectionRequest,
    db: Db = Depends(get_db),
    _user: dict = Depends(require_operator),
):
    if not body.name or not body.allowed_site_ids:
        raise HTTPException(status_code=400, detail="invalid_request")

    conn_id = str(uuid4())
    token = secrets.token_hex(16)
    await db.conn.execute(
        "INSERT INTO app_connections (id, name, token, latitude, longitude, enhanced_messaging, allowed_site_ids_json, revoked, created_at) VALUES (?, ?, ?, ?, ?, 0, ?, 0, ?)",
        (conn_id, body.name, token, body.latitude, body.longitude, json.dumps(body.allowed_site_ids), _utcnow()),
    )
    await db.conn.commit()

    return {"id": conn_id, "token": token}


@router.post("/{conn_id}/revoke")
async def revoke_token(
    conn_id: str,
    db: Db = Depends(get_db),
    _user: dict = Depends(require_operator),
):
    await db.conn.execute("UPDATE app_connections SET revoked = 1 WHERE id = ?", (conn_id,))
    await db.conn.commit()
    return {"ok": True}
