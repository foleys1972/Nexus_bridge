from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.config import AppConfig
from app.crypto import decrypt_from_b64
from app.db import Db
from app.deps import get_cfg, get_db
from app.auth.deps import get_current_user
from app.auth.jwt import sign_access_token, sign_refresh_token
from app.auth.passwords import hash_password, verify_password

router = APIRouter(prefix="/auth")


class LoginRequest(BaseModel):
    username: str | None = None
    email: str | None = None
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    db: Db = Depends(get_db),
    cfg: AppConfig = Depends(get_cfg),
):
    ident = (body.username or body.email or "").strip()
    if not ident:
        raise HTTPException(status_code=400, detail="missing_username")

    rs = getattr(request.app.state, "runtime_settings", None)
    rsd = rs if isinstance(rs, dict) else {}

    def _env_str(name: str) -> str | None:
        if name not in os.environ:
            return None
        return (os.environ.get(name) or "").strip()

    def _env_bool(name: str) -> bool | None:
        if name not in os.environ:
            return None
        raw = (os.environ.get(name) or "").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    def _rs_str(key: str) -> str:
        v = rsd.get(key)
        return (str(v) if v is not None else "").strip()

    def _rs_bool(key: str) -> bool:
        raw = _rs_str(key).lower()
        return raw in {"1", "true", "yes", "on"}

    def _effective_str(env_name: str, rs_key: str, default: str = "") -> str:
        ev = _env_str(env_name)
        if ev is not None and ev != "":
            return ev
        rv = _rs_str(rs_key)
        if rv:
            return rv
        return default

    ev_enabled = _env_bool("LDAP_ENABLED")
    ldap_enabled = bool(ev_enabled) if ev_enabled is not None else _rs_bool("ldap_enabled")

    if ldap_enabled:
        ldap_url = _effective_str("LDAP_URL", "ldap_url", "")
        base_dn = _effective_str("LDAP_BASE_DN", "ldap_base_dn", "")
        user_filter = _effective_str("LDAP_USER_FILTER", "ldap_user_filter", "(sAMAccountName={username})")
        user_dn_template = _effective_str("LDAP_USER_DN_TEMPLATE", "ldap_user_dn_template", "")
        bind_dn = _effective_str("LDAP_BIND_DN", "ldap_bind_dn", "")

        env_bind_pw = _env_str("LDAP_BIND_PASSWORD")
        if env_bind_pw is not None and env_bind_pw != "":
            bind_password = env_bind_pw
        else:
            bind_password = decrypt_from_b64(_rs_str("ldap_bind_password_enc"))

        group_attr = _effective_str("LDAP_GROUP_ATTR", "ldap_group_attr", "memberOf")
        mail_attr = _effective_str("LDAP_MAIL_ATTR", "ldap_mail_attr", "mail")

        def _csv(name: str) -> set[str]:
            ev = _env_str(name)
            raw = ev if (ev is not None and ev != "") else _rs_str(
                {
                    "LDAP_ALLOWED_GROUPS": "ldap_allowed_groups",
                    "LDAP_ADMIN_GROUPS": "ldap_admin_groups",
                    "LDAP_OPERATOR_GROUPS": "ldap_operator_groups",
                    "LDAP_READ_ONLY_GROUPS": "ldap_read_only_groups",
                }.get(name, "")
            )
            out: set[str] = set()
            for part in raw.split(","):
                p = part.strip()
                if p:
                    out.add(p)
            return out

        allowed_groups = _csv("LDAP_ALLOWED_GROUPS")
        admin_groups = _csv("LDAP_ADMIN_GROUPS")
        operator_groups = _csv("LDAP_OPERATOR_GROUPS")
        read_only_groups = _csv("LDAP_READ_ONLY_GROUPS")

        if not ldap_url or not base_dn:
            raise HTTPException(status_code=500, detail="ldap_not_configured")

        def _norm_group_value(v: str) -> str:
            return (v or "").strip().lower()

        def _map_groups_to_role(groups: set[str]) -> str:
            gnorm = {_norm_group_value(g) for g in groups}
            if {_norm_group_value(g) for g in admin_groups} & gnorm:
                return "admin"
            if {_norm_group_value(g) for g in operator_groups} & gnorm:
                return "operator"
            if {_norm_group_value(g) for g in read_only_groups} & gnorm:
                return "read_only"
            return "read_only"

        def _ldap_auth() -> tuple[str, str]:
            from ldap3 import ALL, Connection, Server

            server = Server(ldap_url, get_info=ALL)

            # Find user DN + attributes.
            user_dn = ""
            user_mail = ""
            user_groups: set[str] = set()

            if user_dn_template:
                user_dn = user_dn_template.format(username=ident)
            else:
                if not bind_dn or not bind_password:
                    raise HTTPException(status_code=500, detail="ldap_bind_not_configured")

                c = Connection(server, user=bind_dn, password=bind_password, auto_bind=True)
                f = user_filter.format(username=ident)
                ok = c.search(search_base=base_dn, search_filter=f, attributes=[group_attr, mail_attr])
                if not ok or not c.entries:
                    raise HTTPException(status_code=401, detail="invalid_credentials")

                e = c.entries[0]
                user_dn = str(getattr(e, "entry_dn", "") or "")
                try:
                    if mail_attr and hasattr(e, mail_attr):
                        mv = getattr(e, mail_attr).value
                        user_mail = str(mv or "").strip().lower()
                except Exception:
                    user_mail = ""

                try:
                    if group_attr and hasattr(e, group_attr):
                        g = getattr(e, group_attr).values
                        if isinstance(g, (list, tuple, set)):
                            for x in g:
                                xs = str(x or "").strip()
                                if xs:
                                    user_groups.add(xs)
                        else:
                            xs = str(g or "").strip()
                            if xs:
                                user_groups.add(xs)
                except Exception:
                    user_groups = set()

            if not user_dn:
                raise HTTPException(status_code=401, detail="invalid_credentials")

            # Validate password by binding as user.
            cu = Connection(server, user=user_dn, password=body.password, auto_bind=True)
            cu.unbind()

            if allowed_groups:
                ag = {_norm_group_value(g) for g in allowed_groups}
                gnorm = {_norm_group_value(g) for g in user_groups}
                if not (ag & gnorm):
                    raise HTTPException(status_code=403, detail="not_approved")

            role = _map_groups_to_role(user_groups)
            email = (user_mail or ident).strip().lower()
            if not email:
                email = ident.strip().lower()
            return email, role

        email, role = await run_in_threadpool(_ldap_auth)

        # Auto-provision/update local user for auditability and admin UI.
        async with db.conn.execute("SELECT id FROM users WHERE email = ?", (email,)) as cur:
            row = await cur.fetchone()
        if row:
            user_id = str(row[0])
            await db.conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        else:
            user_id = str(uuid4())
            await db.conn.execute(
                "INSERT INTO users (id, email, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, email, hash_password(os.urandom(32).hex()), role, _utcnow()),
            )
        await db.conn.commit()

        return {
            "access_token": sign_access_token(jwt_secret=cfg.security.jwt_secret, sub=user_id, role=role),
            "refresh_token": sign_refresh_token(jwt_secret=cfg.security.jwt_secret, sub=user_id, role=role),
        }

    # Local DB auth fallback.
    async with db.conn.execute(
        "SELECT id, password_hash, role FROM users WHERE email = ?", (ident,)
    ) as cur:
        row = await cur.fetchone()

    if not row:
        raise HTTPException(status_code=401, detail="invalid_credentials")

    user_id, password_hash, role = row
    if not verify_password(body.password, password_hash):
        raise HTTPException(status_code=401, detail="invalid_credentials")

    return {
        "access_token": sign_access_token(jwt_secret=cfg.security.jwt_secret, sub=user_id, role=role),
        "refresh_token": sign_refresh_token(jwt_secret=cfg.security.jwt_secret, sub=user_id, role=role),
    }


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return {"id": user.get("id"), "role": user.get("role")}


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    db: Db = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    user_id = str(user.get("id") or "")
    if not user_id:
        raise HTTPException(status_code=401, detail="unauthorized")

    if not body.new_password or len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="password_too_short")

    async with db.conn.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="not_found")

    password_hash = row[0]
    if not verify_password(body.current_password, password_hash):
        raise HTTPException(status_code=401, detail="invalid_credentials")

    await db.conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (hash_password(body.new_password), user_id),
    )
    await db.conn.commit()
    return {"ok": True}


def _utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat()
