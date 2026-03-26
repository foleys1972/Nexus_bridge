from __future__ import annotations

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import AppConfig
from app.auth.jwt import verify_token
from app.deps import get_cfg

bearer = HTTPBearer(auto_error=False)


def _norm_role(role: object) -> str:
    v = str(role or "").strip().lower()
    if v in {"admin", "administrator"}:
        return "admin"
    if v in {"operator", "ops"}:
        return "operator"
    if v in {"read_only", "readonly", "viewer", "view"}:
        return "read_only"
    # Legacy capitalization currently used by seed logic
    if v == "admin":
        return "admin"
    if v == "operator":
        return "operator"
    if v in {"read only", "read-only"}:
        return "read_only"
    return v


def get_current_user(
    cfg: AppConfig = Depends(get_cfg),
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict:
    if not creds or creds.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="missing_token")

    try:
        payload = verify_token(jwt_secret=cfg.security.jwt_secret, token=creds.credentials)
        return {"id": payload.get("sub"), "role": _norm_role(payload.get("role"))}
    except Exception:
        raise HTTPException(status_code=401, detail="invalid_token")


def require_role(allowed: set[str]):
    def _dep(user: dict = Depends(get_current_user)) -> dict:
        allowed_norm = {_norm_role(a) for a in allowed}
        if _norm_role(user.get("role")) not in allowed_norm:
            raise HTTPException(status_code=403, detail="forbidden")
        return user

    return _dep


require_admin = require_role({"admin"})
require_operator = require_role({"admin", "operator"})
require_read_only = require_role({"admin", "operator", "read_only"})
