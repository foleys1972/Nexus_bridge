from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re


_INDEX_RE = re.compile(r"^(?P<prefix>.+)_(?P<date>\d{4}-\d{2}-\d{2})_(?P<idx>\d{3})\.log$")


@dataclass(frozen=True)
class RotationPolicy:
    max_size_bytes: int


def _today_utc() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


def current_log_path(dir_path: Path, prefix: str, *, date_str: str | None = None) -> Path:
    date = date_str or _today_utc()
    dir_path.mkdir(parents=True, exist_ok=True)

    max_idx = 0
    for p in dir_path.iterdir():
        if not p.is_file():
            continue
        m = _INDEX_RE.match(p.name)
        if not m:
            continue
        if m.group("prefix") != prefix:
            continue
        if m.group("date") != date:
            continue
        try:
            idx = int(m.group("idx"))
        except ValueError:
            continue
        max_idx = max(max_idx, idx)

    if max_idx == 0:
        max_idx = 1

    return dir_path / f"{prefix}_{date}_{max_idx:03d}.log"


def should_rotate(path: Path, policy: RotationPolicy) -> bool:
    if not path.exists():
        return False
    try:
        size = path.stat().st_size
    except OSError:
        return False
    return size > policy.max_size_bytes


def next_log_path(path: Path) -> Path:
    m = _INDEX_RE.match(path.name)
    if not m:
        raise ValueError("invalid log filename")

    idx = int(m.group("idx")) + 1
    prefix = m.group("prefix")
    date = m.group("date")
    return path.with_name(f"{prefix}_{date}_{idx:03d}.log")
