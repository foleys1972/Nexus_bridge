from __future__ import annotations

from datetime import datetime, timezone
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.config import AppConfig
from app.crypto import encrypt_to_b64
from app.deps import get_cfg, get_db
from app.db import Db
from app.auth.deps import require_admin, require_read_only

router = APIRouter(prefix="/settings")


def _utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class PutSettingsRequest(BaseModel):
    bt_max_commands_per_second: int | None = None
    downstream_overload_max_inflight: int | None = None
    downstream_overload_hard_max_inflight: int | None = None
    wba_ping_notification_enabled: bool | None = None
    log_base_path: str | None = None
    ldap: dict | None = None


@router.get("")
async def get_settings(
    request: Request,
    cfg: AppConfig = Depends(get_cfg),
    _user: dict = Depends(require_read_only),
):
    effective_max_cps = cfg.bt_defaults.max_commands_per_second
    rs = getattr(request.app.state, "runtime_settings", None)
    if isinstance(rs, dict) and isinstance(rs.get("bt_max_commands_per_second"), int):
        effective_max_cps = int(rs["bt_max_commands_per_second"])

    rs_ldap = rs if isinstance(rs, dict) else {}

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
        v = rs_ldap.get(key)
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

    def _effective_csv(env_name: str, rs_key: str) -> list[str]:
        src = _effective_str(env_name, rs_key, "")
        out: list[str] = []
        for part in src.split(","):
            p = part.strip()
            if p:
                out.append(p)
        return out

    ev_enabled = _env_bool("LDAP_ENABLED")
    ldap_enabled = bool(ev_enabled) if ev_enabled is not None else _rs_bool("ldap_enabled")
    ldap_url = _effective_str("LDAP_URL", "ldap_url", "")
    ldap_base_dn = _effective_str("LDAP_BASE_DN", "ldap_base_dn", "")
    ldap_user_filter = _effective_str("LDAP_USER_FILTER", "ldap_user_filter", "(sAMAccountName={username})")
    ldap_user_dn_template = _effective_str("LDAP_USER_DN_TEMPLATE", "ldap_user_dn_template", "")
    ldap_bind_dn = _effective_str("LDAP_BIND_DN", "ldap_bind_dn", "")
    ldap_group_attr = _effective_str("LDAP_GROUP_ATTR", "ldap_group_attr", "memberOf")
    ldap_mail_attr = _effective_str("LDAP_MAIL_ATTR", "ldap_mail_attr", "mail")

    effective_overload_soft = 100
    effective_overload_hard = 200
    if isinstance(rs, dict) and isinstance(rs.get("downstream_overload_max_inflight"), int):
        effective_overload_soft = int(rs["downstream_overload_max_inflight"])
    if isinstance(rs, dict) and isinstance(rs.get("downstream_overload_hard_max_inflight"), int):
        effective_overload_hard = int(rs["downstream_overload_hard_max_inflight"])

    effective_ping_notification_enabled = True
    if isinstance(rs, dict) and "wba_ping_notification_enabled" in rs:
        effective_ping_notification_enabled = str(rs.get("wba_ping_notification_enabled") or "").strip().lower() in {"1", "true", "yes", "on"}

    return {
        "bt_defaults": {
            "heartbeat_interval_seconds": cfg.bt_defaults.heartbeat_interval_seconds,
            "reconnect_attempts": cfg.bt_defaults.reconnect_attempts,
            "command_timeout_seconds": cfg.bt_defaults.command_timeout_seconds,
            "max_commands_per_second": effective_max_cps,
        },
        "overload_protection": {
            "downstream_overload_max_inflight": effective_overload_soft,
            "downstream_overload_hard_max_inflight": effective_overload_hard,
        },
        "wba": {
            "ping_notification_enabled": bool(effective_ping_notification_enabled),
        },
        "logging": {
            "base_path": (rs.get("log_base_path") if isinstance(rs, dict) and isinstance(rs.get("log_base_path"), str) else None)
            or cfg.logging.base_path,
            "default_rotation_size_mb": cfg.logging.default_rotation_size_mb,
            "default_retention_days": cfg.logging.default_retention_days,
            "compression_after_days": cfg.logging.compression_after_days,
        },
        "ldap": {
            "enabled": ldap_enabled,
            "url": ldap_url,
            "base_dn": ldap_base_dn,
            "user_filter": ldap_user_filter,
            "user_dn_template": ldap_user_dn_template,
            "bind_dn": ldap_bind_dn,
            "bind_password_set": bool(_env_str("LDAP_BIND_PASSWORD") or _rs_str("ldap_bind_password_enc")),
            "group_attr": ldap_group_attr,
            "mail_attr": ldap_mail_attr,
            "allowed_groups": _effective_csv("LDAP_ALLOWED_GROUPS", "ldap_allowed_groups"),
            "admin_groups": _effective_csv("LDAP_ADMIN_GROUPS", "ldap_admin_groups"),
            "operator_groups": _effective_csv("LDAP_OPERATOR_GROUPS", "ldap_operator_groups"),
            "read_only_groups": _effective_csv("LDAP_READ_ONLY_GROUPS", "ldap_read_only_groups"),
        },
    }


@router.put("")
async def put_settings(
    body: PutSettingsRequest,
    request: Request,
    db: Db = Depends(get_db),
    _user: dict = Depends(require_admin),
):
    if (
        body.bt_max_commands_per_second is None
        and body.downstream_overload_max_inflight is None
        and body.downstream_overload_hard_max_inflight is None
        and body.wba_ping_notification_enabled is None
        and body.log_base_path is None
        and body.ldap is None
    ):
        raise HTTPException(status_code=400, detail="invalid_request")
    if not hasattr(request.app.state, "runtime_settings") or not isinstance(request.app.state.runtime_settings, dict):
        request.app.state.runtime_settings = {}

    await db.conn.execute("BEGIN")
    try:
        if body.bt_max_commands_per_second is not None:
            if body.bt_max_commands_per_second < 1 or body.bt_max_commands_per_second > 100:
                raise HTTPException(status_code=400, detail="out_of_range")
            await db.conn.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                  value = excluded.value,
                  updated_at = excluded.updated_at
                """,
                ("bt_max_commands_per_second", str(int(body.bt_max_commands_per_second)), _utcnow()),
            )
            request.app.state.runtime_settings["bt_max_commands_per_second"] = int(body.bt_max_commands_per_second)

        if body.downstream_overload_max_inflight is not None:
            v = int(body.downstream_overload_max_inflight)
            if v < 1 or v > 100_000:
                raise HTTPException(status_code=400, detail="out_of_range")
            await db.conn.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                  value = excluded.value,
                  updated_at = excluded.updated_at
                """,
                ("downstream_overload_max_inflight", str(v), _utcnow()),
            )
            request.app.state.runtime_settings["downstream_overload_max_inflight"] = v

        if body.downstream_overload_hard_max_inflight is not None:
            v = int(body.downstream_overload_hard_max_inflight)
            if v < 1 or v > 100_000:
                raise HTTPException(status_code=400, detail="out_of_range")
            await db.conn.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                  value = excluded.value,
                  updated_at = excluded.updated_at
                """,
                ("downstream_overload_hard_max_inflight", str(v), _utcnow()),
            )
            request.app.state.runtime_settings["downstream_overload_hard_max_inflight"] = v

        if body.wba_ping_notification_enabled is not None:
            v = "1" if bool(body.wba_ping_notification_enabled) else "0"
            await db.conn.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                  value = excluded.value,
                  updated_at = excluded.updated_at
                """,
                ("wba_ping_notification_enabled", v, _utcnow()),
            )
            request.app.state.runtime_settings["wba_ping_notification_enabled"] = v

        if body.log_base_path is not None:
            v = body.log_base_path.strip()
            if not v:
                raise HTTPException(status_code=400, detail="invalid_log_base_path")
            await db.conn.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                  value = excluded.value,
                  updated_at = excluded.updated_at
                """,
                ("log_base_path", v, _utcnow()),
            )
            request.app.state.runtime_settings["log_base_path"] = v

        if body.ldap is not None:
            if not isinstance(body.ldap, dict):
                raise HTTPException(status_code=400, detail="invalid_ldap")

            async def _upsert(key: str, value: str) -> None:
                await db.conn.execute(
                    """
                    INSERT INTO app_settings (key, value, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                      value = excluded.value,
                      updated_at = excluded.updated_at
                    """,
                    (key, value, _utcnow()),
                )
                request.app.state.runtime_settings[key] = value

            def _as_csv(v: object) -> str:
                if v is None:
                    return ""
                if isinstance(v, list):
                    parts: list[str] = []
                    for x in v:
                        s = str(x or "").strip()
                        if s:
                            parts.append(s)
                    return ",".join(parts)
                return str(v).strip()

            if "enabled" in body.ldap:
                en = bool(body.ldap.get("enabled"))
                await _upsert("ldap_enabled", "1" if en else "0")

            if "url" in body.ldap:
                await _upsert("ldap_url", str(body.ldap.get("url") or "").strip())
            if "base_dn" in body.ldap:
                await _upsert("ldap_base_dn", str(body.ldap.get("base_dn") or "").strip())
            if "user_filter" in body.ldap:
                await _upsert("ldap_user_filter", str(body.ldap.get("user_filter") or "").strip())
            if "user_dn_template" in body.ldap:
                await _upsert("ldap_user_dn_template", str(body.ldap.get("user_dn_template") or "").strip())
            if "bind_dn" in body.ldap:
                await _upsert("ldap_bind_dn", str(body.ldap.get("bind_dn") or "").strip())
            if "group_attr" in body.ldap:
                await _upsert("ldap_group_attr", str(body.ldap.get("group_attr") or "").strip())
            if "mail_attr" in body.ldap:
                await _upsert("ldap_mail_attr", str(body.ldap.get("mail_attr") or "").strip())

            if "allowed_groups" in body.ldap:
                await _upsert("ldap_allowed_groups", _as_csv(body.ldap.get("allowed_groups")))
            if "admin_groups" in body.ldap:
                await _upsert("ldap_admin_groups", _as_csv(body.ldap.get("admin_groups")))
            if "operator_groups" in body.ldap:
                await _upsert("ldap_operator_groups", _as_csv(body.ldap.get("operator_groups")))
            if "read_only_groups" in body.ldap:
                await _upsert("ldap_read_only_groups", _as_csv(body.ldap.get("read_only_groups")))

            # write-only secret: if provided, we update it. empty string clears.
            if "bind_password" in body.ldap:
                enc = encrypt_to_b64(str(body.ldap.get("bind_password") or ""))
                await _upsert("ldap_bind_password_enc", enc)

        await db.conn.commit()
    except Exception:
        await db.conn.rollback()
        raise

    return {"ok": True}
