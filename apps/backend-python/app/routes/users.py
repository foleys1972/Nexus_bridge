from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.deps import require_admin
from app.auth.passwords import hash_password
from app.db import Db
from app.deps import get_db

router = APIRouter(prefix="/users")


def _utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _norm_role(role: str) -> str:
    v = (role or "").strip().lower()
    if v in {"admin", "administrator"}:
        return "admin"
    if v in {"operator", "ops"}:
        return "operator"
    if v in {"read_only", "readonly", "viewer", "view", "read-only", "read only"}:
        return "read_only"
    return v


_ALLOWED_ROLES = {"admin", "operator", "read_only"}


class CreateUserRequest(BaseModel):
    email: str
    password: str
    role: str


class UpdateUserRequest(BaseModel):
    role: str | None = None
    password: str | None = None


@router.get("")
async def list_users(
    db: Db = Depends(get_db),
    _user: dict = Depends(require_admin),
):
    async with db.conn.execute(
        "SELECT id, email, role, created_at FROM users ORDER BY created_at DESC"
    ) as cur:
        rows = await cur.fetchall()

    out = []
    for user_id, email, role, created_at in rows:
        out.append({"id": user_id, "email": email, "role": _norm_role(str(role)), "created_at": created_at})
    return {"users": out}


@router.post("")
async def create_user(
    body: CreateUserRequest,
    db: Db = Depends(get_db),
    _user: dict = Depends(require_admin),
):
    email = (body.email or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="invalid_email")

    role = _norm_role(body.role)
    if role not in _ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail="invalid_role")

    if not body.password or len(body.password) < 8:
        raise HTTPException(status_code=400, detail="password_too_short")

    async with db.conn.execute("SELECT id FROM users WHERE email = ?", (email,)) as cur:
        row = await cur.fetchone()
    if row:
        raise HTTPException(status_code=409, detail="email_exists")

    user_id = str(uuid4())
    await db.conn.execute(
        "INSERT INTO users (id, email, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, email, hash_password(body.password), role, _utcnow()),
    )
    await db.conn.commit()

    return {"id": user_id}


@router.put("/{user_id}")
async def update_user(
    user_id: str,
    body: UpdateUserRequest,
    db: Db = Depends(get_db),
    _user: dict = Depends(require_admin),
):
    async with db.conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="not_found")

    fields: list[str] = []
    values: list[object] = []

    if body.role is not None:
        role = _norm_role(body.role)
        if role not in _ALLOWED_ROLES:
            raise HTTPException(status_code=400, detail="invalid_role")
        fields.append("role = ?")
        values.append(role)

    if body.password is not None:
        if not body.password or len(body.password) < 8:
            raise HTTPException(status_code=400, detail="password_too_short")
        fields.append("password_hash = ?")
        values.append(hash_password(body.password))

    if not fields:
        return {"ok": True}

    values.append(user_id)
    await db.conn.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", tuple(values))
    await db.conn.commit()
    return {"ok": True}


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    db: Db = Depends(get_db),
    _user: dict = Depends(require_admin),
):
    async with db.conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="not_found")

    await db.conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    await db.conn.commit()
    return {"ok": True}
