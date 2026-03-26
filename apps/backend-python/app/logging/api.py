from __future__ import annotations

import asyncio
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import AppConfig, effective_log_base_path
from app.deps import get_cfg, get_log_writer
from app.logging.rotation import RotationPolicy
from app.logging.writer import AsyncLogWriter, LogWrite
from app.auth.deps import require_operator, require_read_only

router = APIRouter(prefix="/logs")


@router.get("/tree")
async def tree(
    request: Request,
    cfg: AppConfig = Depends(get_cfg),
    _user: dict = Depends(require_read_only),
):
    root = Path(effective_log_base_path(cfg, getattr(request.app.state, "runtime_settings", None))).resolve()
    if not root.exists():
        return {"root": str(root), "entries": []}

    entries = []
    for d in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        entries.append({"name": d.name, "type": "dir" if d.is_dir() else "file"})

    return {"root": str(root), "entries": entries}


class EmitLogRequest(BaseModel):
    site_id: str
    log_type: str
    payload: dict


@router.post("/emit")
async def emit(
    body: EmitLogRequest,
    request: Request,
    cfg: AppConfig = Depends(get_cfg),
    lw: AsyncLogWriter = Depends(get_log_writer),
    _user: dict = Depends(require_operator),
):
    root = Path(effective_log_base_path(cfg, getattr(request.app.state, "runtime_settings", None))).resolve()
    dir_path = root / body.site_id / body.log_type

    rotation = RotationPolicy(max_size_bytes=cfg.logging.default_rotation_size_mb * 1024 * 1024)
    await lw.enqueue(
        LogWrite(
            path_dir=dir_path,
            prefix=body.log_type,
            rotation=rotation,
            payload=body.payload,
        )
    )

    return {"ok": True}


async def _tail_file(path: Path, *, poll_interval: float = 0.25) -> AsyncGenerator[bytes, None]:
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="log_not_found")

    with open(path, "rb") as f:
        f.seek(0, 2)
        while True:
            data = f.readline()
            if data:
                yield b"data: " + data.replace(b"\n", b"\\n") + b"\n\n"
                continue

            await asyncio.sleep(poll_interval)


@router.get("/tail/{site_id}/{log_type}")
async def tail(
    site_id: str,
    log_type: str,
    request: Request,
    cfg: AppConfig = Depends(get_cfg),
    _user: dict = Depends(require_read_only),
):
    root = Path(effective_log_base_path(cfg, getattr(request.app.state, "runtime_settings", None))).resolve()
    dir_path = root / site_id / log_type
    if not dir_path.exists():
        raise HTTPException(status_code=404, detail="log_dir_not_found")

    latest = None
    for p in dir_path.glob("*.log"):
        if not p.is_file():
            continue
        if latest is None:
            latest = p
            continue
        try:
            if p.stat().st_mtime > latest.stat().st_mtime:
                latest = p
        except OSError:
            continue

    if not latest:
        raise HTTPException(status_code=404, detail="log_not_found")

    return StreamingResponse(_tail_file(latest), media_type="text/event-stream")
