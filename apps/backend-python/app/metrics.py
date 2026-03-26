from __future__ import annotations

import asyncio
import time
from collections import deque


class _WindowCounter:
    def __init__(self, *, window_s: float) -> None:
        self._window_s = float(window_s)
        self._events: dict[str, deque[float]] = {}

    def inc(self, key: str, *, now: float) -> None:
        q = self._events.get(key)
        if q is None:
            q = deque()
            self._events[key] = q
        q.append(now)

    def snapshot_per_minute(self, *, now: float) -> dict[str, int]:
        cutoff = now - self._window_s
        out: dict[str, int] = {}
        for k, q in list(self._events.items()):
            while q and q[0] < cutoff:
                q.popleft()
            if q:
                out[k] = len(q)
            else:
                self._events.pop(k, None)
        return out


class Metrics:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._bt_sent = _WindowCounter(window_s=60)
        self._bt_recv = _WindowCounter(window_s=60)
        self._down_in = _WindowCounter(window_s=60)
        self._down_out = _WindowCounter(window_s=60)

    async def inc_bt_sent(self, site_id: str) -> None:
        now = time.time()
        async with self._lock:
            self._bt_sent.inc(site_id, now=now)

    async def inc_bt_recv(self, site_id: str) -> None:
        now = time.time()
        async with self._lock:
            self._bt_recv.inc(site_id, now=now)

    async def inc_down_in(self, conn_id: str) -> None:
        now = time.time()
        async with self._lock:
            self._down_in.inc(conn_id, now=now)

    async def inc_down_out(self, conn_id: str) -> None:
        now = time.time()
        async with self._lock:
            self._down_out.inc(conn_id, now=now)

    async def snapshot(self) -> dict:
        now = time.time()
        async with self._lock:
            return {
                "window_seconds": 60,
                "bt_sent_per_minute": self._bt_sent.snapshot_per_minute(now=now),
                "bt_recv_per_minute": self._bt_recv.snapshot_per_minute(now=now),
                "downstream_in_per_minute": self._down_in.snapshot_per_minute(now=now),
                "downstream_out_per_minute": self._down_out.snapshot_per_minute(now=now),
            }


metrics = Metrics()
