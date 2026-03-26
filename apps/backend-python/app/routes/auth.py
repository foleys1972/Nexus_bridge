from __future__ import annotations

import json
import os
import secrets
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.config import AppConfig
from app.db import Db
from app.deps import get_cfg, get_db
from app.auth.deps import get_current_user
from app.auth.jwt import sign_access_token, sign_refresh_token
from app.auth.passwords import hash_password, verify_password

router = APIRouter(prefix="/auth")


class LoginRequest(BaseModel):
    email: str
    password: str


class OidcLoginResponse(BaseModel):
    authorization_url: str


@router.post("/login")
async def login(
    body: LoginRequest,
    db: Db = Depends(get_db),
    cfg: AppConfig = Depends(get_cfg),
):
    async with db.conn.execute(
        "SELECT id, password_hash, role FROM users WHERE email = ?", (body.email,)
    ) as cur:
        row = await cur.fetchone()

    if not row:
        raise HTTPException(status_code=401, detail="invalid_credentials")

    user_id, password_hash, role = row
    if not verify_password(body.password, password_hash):
        raise HTTPException(status_code=401, detail="invalid_credentials")

    return {
        "access_token": sign_access_token(jwt_secret=cfg.security.jwt_secret, sub=user_id, role=role),
        "refresh_token": sign_refresh_token(
            jwt_secret=cfg.security.jwt_secret, sub=user_id, role=role
        ),
    }


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return {"id": user.get("id"), "role": user.get("role")}


def _utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _env_csv(name: str) -> set[str]:
    raw = os.environ.get(name) or ""
    out: set[str] = set()
    for part in raw.split(","):
        p = part.strip()
        if p:
            out.add(p)
    return out


def _oidc_cfg() -> dict:
    tenant_id = (os.environ.get("AZURE_AD_TENANT_ID") or os.environ.get("OIDC_AAD_TENANT_ID") or "").strip()
    client_id = (os.environ.get("AZURE_AD_CLIENT_ID") or os.environ.get("OIDC_CLIENT_ID") or "").strip()
    client_secret = (os.environ.get("AZURE_AD_CLIENT_SECRET") or os.environ.get("OIDC_CLIENT_SECRET") or "").strip()
    redirect_uri = (os.environ.get("AZURE_AD_REDIRECT_URI") or os.environ.get("OIDC_REDIRECT_URI") or "").strip()

    if not tenant_id or not client_id or not client_secret or not redirect_uri:
        raise HTTPException(status_code=500, detail="oidc_not_configured")

    authority = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0"
    return {
        "tenant_id": tenant_id,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "authorize_url": f"{authority}/authorize",
        "token_url": f"{authority}/token",
        "jwks_url": f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys",
        "scope": (os.environ.get("AZURE_AD_SCOPE") or os.environ.get("OIDC_SCOPE") or "openid profile email").strip(),
        "admin_group_ids": _env_csv("AZURE_AD_ADMIN_GROUP_IDS") | _env_csv("OIDC_ADMIN_GROUP_IDS"),
        "operator_group_ids": _env_csv("AZURE_AD_OPERATOR_GROUP_IDS") | _env_csv("OIDC_OPERATOR_GROUP_IDS"),
        "read_only_group_ids": _env_csv("AZURE_AD_READONLY_GROUP_IDS") | _env_csv("OIDC_READONLY_GROUP_IDS"),
    }


def _http_post_form(url: str, form: dict[str, str]) -> dict:
    data = urllib.parse.urlencode(form).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"oidc_token_exchange_failed:{type(e).__name__}")


def _http_get_json(url: str) -> dict:
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"oidc_fetch_failed:{type(e).__name__}")


def _map_groups_to_role(groups: set[str], cfg: dict) -> str:
    if groups & set(cfg.get("admin_group_ids") or set()):
        return "admin"
    if groups & set(cfg.get("operator_group_ids") or set()):
        return "operator"
    if groups & set(cfg.get("read_only_group_ids") or set()):
        return "read_only"
    return "read_only"


@router.get("/oidc/login", response_model=OidcLoginResponse)
async def oidc_login():
    cfg = _oidc_cfg()
    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)

    params = {
        "client_id": cfg["client_id"],
        "response_type": "code",
        "redirect_uri": cfg["redirect_uri"],
        "response_mode": "query",
        "scope": cfg["scope"],
        "state": state,
        "nonce": nonce,
    }
    url = cfg["authorize_url"] + "?" + urllib.parse.urlencode(params)

    # The frontend can either call this endpoint and redirect, or we can return the URL.
    return {"authorization_url": url}


@router.get("/oidc/callback")
async def oidc_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    db: Db = Depends(get_db),
    app_cfg: AppConfig = Depends(get_cfg),
):
    if error:
        raise HTTPException(status_code=401, detail=f"oidc_error:{error}")
    if not code:
        raise HTTPException(status_code=400, detail="missing_code")
    _ = state  # reserved for CSRF protection if we add server-side state storage

    ocfg = _oidc_cfg()
    token = _http_post_form(
        ocfg["token_url"],
        {
            "client_id": ocfg["client_id"],
            "client_secret": ocfg["client_secret"],
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": ocfg["redirect_uri"],
        },
    )

    id_token = str(token.get("id_token") or "")
    if not id_token:
        raise HTTPException(status_code=401, detail="missing_id_token")

    # Validate id_token signature with Azure AD JWKS.
    from jose import jwt  # local import to avoid unused in other deployments

    header = jwt.get_unverified_header(id_token)
    kid = str(header.get("kid") or "")
    if not kid:
        raise HTTPException(status_code=401, detail="missing_kid")

    jwks = _http_get_json(ocfg["jwks_url"])
    keys = jwks.get("keys") if isinstance(jwks, dict) else None
    if not isinstance(keys, list):
        raise HTTPException(status_code=502, detail="invalid_jwks")

    key = None
    for k in keys:
        if isinstance(k, dict) and str(k.get("kid") or "") == kid:
            key = k
            break
    if not key:
        raise HTTPException(status_code=401, detail="jwks_kid_not_found")

    # python-jose can accept a JWK dict as key.
    try:
        claims = jwt.decode(
            id_token,
            key,
            algorithms=["RS256"],
            audience=ocfg["client_id"],
            options={"verify_at_hash": False},
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"invalid_id_token:{type(e).__name__}")

    # Extract identity.
    email = (
        str(claims.get("preferred_username") or "")
        or str(claims.get("email") or "")
        or str(claims.get("upn") or "")
    ).strip().lower()
    if not email:
        raise HTTPException(status_code=401, detail="missing_email")

    groups_raw = claims.get("groups")
    groups: set[str] = set()
    if isinstance(groups_raw, list):
        for g in groups_raw:
            gs = str(g or "").strip()
            if gs:
                groups.add(gs)

    role = _map_groups_to_role(groups, ocfg)

    # Auto-provision/update local user for auditability and admin UI.
    async with db.conn.execute("SELECT id FROM users WHERE email = ?", (email,)) as cur:
        row = await cur.fetchone()

    if row:
        user_id = str(row[0])
        await db.conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
    else:
        user_id = secrets.token_hex(16)
        await db.conn.execute(
            "INSERT INTO users (id, email, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, email, hash_password(secrets.token_urlsafe(48)), role, _utcnow()),
        )
    await db.conn.commit()

    # Issue local JWTs that the frontend/API already understands.
    access = sign_access_token(jwt_secret=app_cfg.security.jwt_secret, sub=user_id, role=role)
    refresh = sign_refresh_token(jwt_secret=app_cfg.security.jwt_secret, sub=user_id, role=role)

    # If your frontend is hosted at https://servername/nexus_bridge, you can optionally set
    # a redirect target via OIDC_UI_REDIRECT (e.g. https://servername/nexus_bridge/#/login).
    ui_redirect = (os.environ.get("OIDC_UI_REDIRECT") or os.environ.get("AZURE_AD_UI_REDIRECT") or "").strip()
    if ui_redirect:
        q = urllib.parse.urlencode({"access_token": access, "refresh_token": refresh})
        return RedirectResponse(url=f"{ui_redirect}?{q}")

    return {"access_token": access, "refresh_token": refresh}
