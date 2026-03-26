from __future__ import annotations

import asyncio
import gzip
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclass(frozen=True)
class RetentionPolicy:
    retention_days: int
    gzip_after_days: int


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _is_log_file(p: Path) -> bool:
    return p.is_file() and (p.name.endswith(".log") or p.name.endswith(".log.gz"))


def _compress_file(src: Path) -> Path:
    dst = src.with_suffix(src.suffix + ".gz")
    with open(src, "rb") as f_in, gzip.open(dst, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    src.unlink(missing_ok=True)
    return dst


def _file_mtime_utc(p: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None


async def apply_retention(base_dir: Path, policy: RetentionPolicy) -> None:
    cutoff_delete = _utcnow() - timedelta(days=policy.retention_days)
    cutoff_gzip = _utcnow() - timedelta(days=policy.gzip_after_days)

    def _walk_and_apply() -> None:
        if not base_dir.exists():
            return

        for p in base_dir.rglob("*"):
            if not _is_log_file(p):
                continue

            mtime = _file_mtime_utc(p)
            if not mtime:
                continue

            if mtime < cutoff_delete:
                p.unlink(missing_ok=True)
                continue

            if p.name.endswith(".log") and mtime < cutoff_gzip:
                _compress_file(p)

    await asyncio.to_thread(_walk_and_apply)
