from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.logging.rotation import RotationPolicy, current_log_path, next_log_path, should_rotate


@dataclass(frozen=True)
class LogWrite:
    path_dir: Path
    prefix: str
    rotation: RotationPolicy
    payload: dict[str, Any]


class AsyncLogWriter:
    def __init__(self) -> None:
        self._q: asyncio.Queue[LogWrite] = asyncio.Queue(maxsize=50_000)
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()

    async def start(self) -> None:
        if self._task:
            return
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stopping.set()
        if self._task:
            await self._task

    async def enqueue(self, w: LogWrite) -> None:
        await self._q.put(w)

    async def _run(self) -> None:
        while True:
            if self._stopping.is_set() and self._q.empty():
                return

            w = await self._q.get()
            try:
                await asyncio.to_thread(self._write_one, w)
            finally:
                self._q.task_done()

    def _write_one(self, w: LogWrite) -> None:
        path = current_log_path(w.path_dir, w.prefix)
        if should_rotate(path, w.rotation):
            path = next_log_path(path)

        line = json.dumps(
            {
                "ts": datetime.now(tz=timezone.utc).isoformat(),
                **w.payload,
            },
            separators=(",", ":"),
        )

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a+", encoding="utf-8", newline="\n") as f:
            f.write(line + "\n")
            f.flush()
