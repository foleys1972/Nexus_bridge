from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.config import AppConfig
from app.deps import get_cfg, get_db
from app.db import Db
from app.auth.deps import require_admin, require_read_only

router = APIRouter(prefix="/settings")


def _utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class PutSettingsRequest(BaseModel):
    bt_max_commands_per_second: int | None = None
    log_base_path: str | None = None


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
    return {
        "bt_defaults": {
            "heartbeat_interval_seconds": cfg.bt_defaults.heartbeat_interval_seconds,
            "reconnect_attempts": cfg.bt_defaults.reconnect_attempts,
            "command_timeout_seconds": cfg.bt_defaults.command_timeout_seconds,
            "max_commands_per_second": effective_max_cps,
        },
        "logging": {
            "base_path": (rs.get("log_base_path") if isinstance(rs, dict) and isinstance(rs.get("log_base_path"), str) else None)
            or cfg.logging.base_path,
            "default_rotation_size_mb": cfg.logging.default_rotation_size_mb,
            "default_retention_days": cfg.logging.default_retention_days,
            "compression_after_days": cfg.logging.compression_after_days,
        },
    }


@router.put("")
async def put_settings(
    body: PutSettingsRequest,
    request: Request,
    db: Db = Depends(get_db),
    _user: dict = Depends(require_admin),
):
    if body.bt_max_commands_per_second is None and body.log_base_path is None:
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

        await db.conn.commit()
    except Exception:
        await db.conn.rollback()
        raise

    return {"ok": True}
