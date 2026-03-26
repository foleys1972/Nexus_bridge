from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from fastapi import WebSocket

from app.metrics import metrics


@dataclass
class DownstreamClient:
    ws: WebSocket
    conn_id: str
    allowed_site_ids: set[str]
    subscribed_site_ids: set[str]
    enhanced_messaging: bool
    connected_at: float
    client_host: str | None


class ProxyHub:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._clients: dict[int, DownstreamClient] = {}

    async def register(self, c: DownstreamClient) -> None:
        async with self._lock:
            self._clients[id(c.ws)] = c

    async def unregister(self, c: DownstreamClient) -> None:
        async with self._lock:
            self._clients.pop(id(c.ws), None)

    async def list_active(self) -> list[dict[str, Any]]:
        async with self._lock:
            clients = list(self._clients.values())

        out: list[dict[str, Any]] = []
        for c in clients:
            out.append(
                {
                    "conn_id": c.conn_id,
                    "client_host": c.client_host,
                    "connected_at": c.connected_at,
                    "enhanced_messaging": bool(c.enhanced_messaging),
                    "subscribed_site_ids": sorted(list(c.subscribed_site_ids)),
                }
            )
        return out

    async def broadcast_site_event(self, site_id: str, site_name: str | None, payload: dict[str, Any]) -> None:
        legacy_msg = json.dumps(payload)
        async with self._lock:
            clients = list(self._clients.values())

        for c in clients:
            if site_id in c.subscribed_site_ids:
                try:
                    if c.enhanced_messaging:
                        await c.ws.send_text(
                            json.dumps(
                                {
                                    "command": "event",
                                    "data": payload,
                                    "meta": {
                                        "site_id": site_id,
                                        "site_name": site_name,
                                    },
                                }
                            )
                        )
                    else:
                        await c.ws.send_text(legacy_msg)
                    await metrics.inc_down_out(c.conn_id)
                except Exception:
                    pass


hub = ProxyHub()
