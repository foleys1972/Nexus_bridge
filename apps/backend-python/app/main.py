from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

import json
import contextlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import time
import gzip

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import websockets

from app.config import AppConfig, load_config
from app.config import effective_log_base_path
from app.db import Db, init_db
from app.auth.passwords import hash_password
from app.routes import health as health_route
from app.routes import auth as auth_route
from app.routes import sites as sites_route
from app.routes import connections as connections_route
from app.routes import metrics as metrics_route
from app.routes import settings as settings_route
from app.routes import users as users_route
from app.logging.api import router as logs_router
from app.logging.rotation import RotationPolicy
from app.logging.writer import AsyncLogWriter, LogWrite
from app.logging.retention import RetentionPolicy, apply_retention
import asyncio

from app.proxy.server import DownstreamClient, hub
from app.polling.state import get_last_id, set_last_id
from app.metrics import metrics


def create_app() -> FastAPI:
    app = FastAPI(title="NexusBridge Command Center API", version="0.1.0", redirect_slashes=False)

    log = logging.getLogger("uvicorn.error")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\\d+)?$",
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )

    @dataclass
    class _WbaClient:
        site_id: str
        site_name: str
        wss_url: str
        token: str
        ws: Any | None
        recv_task: asyncio.Task | None
        pending: dict[str, asyncio.Future]
        lock: asyncio.Lock
        stop: asyncio.Event
        throttle_lock: asyncio.Lock
        next_send_at: float

    async def _set_site_status(
        app: FastAPI,
        *,
        site_id: str,
        status: str,
        last_error: str | None = None,
        last_connected_at: str | None = None,
    ) -> None:
        await app.state.db.conn.execute(
            """
            UPDATE sites
            SET status = ?, last_error = ?, last_connected_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                status,
                last_error,
                last_connected_at,
                datetime.now(tz=timezone.utc).isoformat(),
                site_id,
            ),
        )
        await app.state.db.conn.commit()

    GET_COMMANDS: set[str] = {
        "get_calls",
        "get_zones",
        "get_users",
        "get_turrets",
        "get_events",
        "get_version",
        "get_tpos",
        "get_lines",
        "get_shared_profiles",
        "get_health_api_report",
    }

    def _latest_log_file(dir_path: Path) -> Path | None:
        if not dir_path.exists() or not dir_path.is_dir():
            return None
        latest: Path | None = None
        latest_mtime = -1.0
        for p in dir_path.glob("*.log"):
            if not p.is_file():
                continue
            try:
                mtime = p.stat().st_mtime
            except OSError:
                continue
            if mtime > latest_mtime:
                latest = p
                latest_mtime = mtime
        for p in dir_path.glob("*.log.gz"):
            if not p.is_file():
                continue
            try:
                mtime = p.stat().st_mtime
            except OSError:
                continue
            if mtime > latest_mtime:
                latest = p
                latest_mtime = mtime
        return latest

    def _read_last_json_line(path: Path) -> dict | None:
        try:
            if path.name.endswith(".gz"):
                with gzip.open(path, "rt", encoding="utf-8", errors="ignore") as f:
                    lines = f.read().splitlines()
            else:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.read().splitlines()
        except OSError:
            return None

        for raw in reversed(lines):
            s = (raw or "").strip()
            if not s:
                continue
            try:
                v = json.loads(s)
            except Exception:
                continue
            if isinstance(v, dict):
                return v
        return None

    async def _get_cached_poll_response(*, site_id: str, command: str) -> dict | None:
        if command not in GET_COMMANDS:
            return None
        base = Path(effective_log_base_path(app.state.cfg, getattr(app.state, "runtime_settings", None))).resolve()
        dir_path = base / site_id / command
        latest = await asyncio.to_thread(_latest_log_file, dir_path)
        if not latest:
            return None
        entry = await asyncio.to_thread(_read_last_json_line, latest)
        if not entry:
            return None
        payload = entry.get("payload")
        poll_args = entry.get("args") if isinstance(entry.get("args"), dict) else None
        if isinstance(payload, dict):
            out = dict(payload)
            if isinstance(poll_args, dict):
                out["_nb_poll_args"] = poll_args
            return out
        return None

    def _is_cache_compatible(*, command: str, req_args: dict[str, Any], cached_resp: dict[str, Any]) -> bool:
        poll_args = cached_resp.get("_nb_poll_args") if isinstance(cached_resp.get("_nb_poll_args"), dict) else {}

        # Remove non-filter routing hints
        req_args = {k: v for k, v in (req_args or {}).items() if k != "site_id"}

        # If the caller wants any args and we don't know what the poll used, be conservative.
        if req_args and not poll_args:
            return False

        # get_calls: allow cache if request.from_id >= poll.from_id (cache is a subset of newer calls)
        if command == "get_calls":
            req_from = req_args.get("from_id")
            poll_from = poll_args.get("from_id")
            if req_from is None:
                # request wants default (server decides). cached poll is acceptable.
                return True
            if poll_from is None:
                return False
            try:
                return int(req_from) >= int(poll_from)
            except Exception:
                return False

        # get_events: must match category; allow from_id rule as above
        if command == "get_events":
            req_cat = req_args.get("category")
            poll_cat = poll_args.get("category")
            if req_cat is not None and poll_cat is not None and str(req_cat) != str(poll_cat):
                return False
            if req_cat is not None and poll_cat is None:
                return False
            req_from = req_args.get("from_id")
            poll_from = poll_args.get("from_id")
            if req_from is None:
                return True
            if poll_from is None:
                return False
            try:
                return int(req_from) >= int(poll_from)
            except Exception:
                return False

        # Default: exact args match. If request sends no args, cache is fine.
        if not req_args:
            return True
        return req_args == poll_args

    async def _load_subscribe_categories(app: FastAPI, *, site_id: str) -> set[str]:
        async with app.state.db.conn.execute(
            """
            SELECT subscribe_calls, subscribe_presence, subscribe_alerts, subscribe_events
            FROM sites WHERE id = ?
            """,
            (site_id,),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return set()
        subscribe_calls, subscribe_presence, subscribe_alerts, subscribe_events = row

        cats: set[str] = set()
        if subscribe_calls:
            cats.add("calls")
        if subscribe_presence:
            cats.add("presence")
        if subscribe_alerts:
            cats.add("alerts")
        if subscribe_events:
            cats.add("events")
        return cats

    async def _wba_send_json(c: _WbaClient, payload: dict[str, Any]) -> None:
        max_cps = int(
            (app.state.runtime_settings.get("bt_max_commands_per_second") if hasattr(app.state, "runtime_settings") else None)
            or getattr(app.state.cfg.bt_defaults, "max_commands_per_second", 5)
            or 5
        )
        if max_cps < 1:
            max_cps = 1
        interval_s = 1.0 / float(max_cps)

        async with c.throttle_lock:
            now = asyncio.get_running_loop().time()
            wait_s = c.next_send_at - now
            if wait_s > 0:
                try:
                    await asyncio.wait_for(c.stop.wait(), timeout=wait_s)
                    raise RuntimeError("wba_stopping")
                except asyncio.TimeoutError:
                    pass
            c.next_send_at = max(c.next_send_at, now) + interval_s

        async with c.lock:
            if not c.ws:
                raise RuntimeError("wba_not_connected")
            await c.ws.send(json.dumps(payload, separators=(",", ":")))
        await metrics.inc_bt_sent(c.site_id)

    async def _wba_request(c: _WbaClient, payload: dict[str, Any], *, timeout_s: float) -> dict[str, Any]:
        command_ref = str(payload.get("command_ref") or "")
        if not command_ref:
            raise ValueError("missing_command_ref")
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        c.pending[command_ref] = fut
        try:
            await _wba_send_json(c, payload)
            return await asyncio.wait_for(fut, timeout=timeout_s)
        finally:
            c.pending.pop(command_ref, None)

    async def _wba_recv_loop(app: FastAPI, c: _WbaClient) -> None:
        assert c.ws is not None
        while not c.stop.is_set():
            try:
                raw = await c.ws.recv()
            except Exception:
                # connection lost
                c.stop.set()
                return
            try:
                msg = json.loads(raw)
            except Exception:
                continue

            await metrics.inc_bt_recv(c.site_id)

            if isinstance(msg, dict) and msg.get("command") == "response":
                ref = str(msg.get("command_ref") or "")
                fut = c.pending.get(ref)
                if fut and not fut.done():
                    fut.set_result(msg)
                continue

            rotation = RotationPolicy(max_size_bytes=app.state.cfg.logging.default_rotation_size_mb * 1024 * 1024)
            root = Path(app.state.cfg.logging.base_path).resolve()
            log_type = "notify"
            if isinstance(msg, dict):
                cmd = msg.get("command")
                if isinstance(cmd, str) and cmd:
                    log_type = cmd
            await app.state.log_writer.enqueue(
                LogWrite(
                    path_dir=root / c.site_id / log_type,
                    prefix=log_type,
                    rotation=rotation,
                    payload={"site_id": c.site_id, "payload": msg},
                )
            )
            await hub.broadcast_site_event(c.site_id, c.site_name, {"site_id": c.site_id, "payload": msg})

    async def _wba_connect(app: FastAPI, c: _WbaClient) -> None:
        c.ws = await websockets.connect(c.wss_url)

        auth_ref = str(uuid4())
        auth_payload = {
            "command": "auth",
            "command_ref": auth_ref,
            "args": {"token": c.token},
        }
        await _wba_request(c, auth_payload, timeout_s=app.state.cfg.bt_defaults.command_timeout_seconds)

        c.recv_task = asyncio.create_task(_wba_recv_loop(app, c))

        ctd_ref = str(uuid4())
        ctd_payload = {
            "command": "service_ctd",
            "command_ref": ctd_ref,
            "args": {},
        }
        try:
            await _wba_request(c, ctd_payload, timeout_s=app.state.cfg.bt_defaults.command_timeout_seconds)
        except Exception:
            pass

    async def _wba_disconnect(c: _WbaClient) -> None:
        c.stop.set()
        if c.recv_task:
            c.recv_task.cancel()
        if c.ws:
            try:
                await asyncio.wait_for(c.ws.close(), timeout=5)
            except Exception:
                pass
        c.ws = None

    async def _wba_subscribe(app: FastAPI, c: _WbaClient, cats: set[str]) -> None:
        if not cats:
            return
        ref = str(uuid4())
        payload = {
            "command": "subscribe",
            "command_ref": ref,
            "args": {"categories": sorted(cats)},
        }
        await _wba_request(c, payload, timeout_s=app.state.cfg.bt_defaults.command_timeout_seconds)

    async def _wba_unsubscribe(app: FastAPI, c: _WbaClient, cats: set[str]) -> None:
        if not cats:
            return
        ref = str(uuid4())
        payload = {
            "command": "unsubscribe",
            "command_ref": ref,
            "args": {"categories": sorted(cats)},
        }
        await _wba_request(c, payload, timeout_s=app.state.cfg.bt_defaults.command_timeout_seconds)

    async def _poll_once(app: FastAPI, c: _WbaClient, command: str) -> None:
        rotation = RotationPolicy(max_size_bytes=app.state.cfg.logging.default_rotation_size_mb * 1024 * 1024)
        root = Path(effective_log_base_path(app.state.cfg, getattr(app.state, "runtime_settings", None))).resolve()
        timeout_s = float(app.state.cfg.bt_defaults.command_timeout_seconds)

        async def emit(payload: dict[str, Any]) -> None:
            await app.state.log_writer.enqueue(
                LogWrite(
                    path_dir=root / c.site_id / command,
                    prefix=command,
                    rotation=rotation,
                    payload=payload,
                )
            )
            await hub.broadcast_site_event(c.site_id, c.site_name, payload)

        if command == "get_calls":
            last_id = await get_last_id(app.state.db, site_id=c.site_id, command="get_calls")
            args: dict[str, Any] = {}
            if last_id is not None:
                args["from_id"] = last_id

            max_seen: int | None = last_id
            current = 1
            last = 1
            while current <= last:
                ref = str(uuid4())
                req = {"command": "get_calls", "command_ref": ref, "args": args}
                resp = await _wba_request(c, req, timeout_s=timeout_s)
                data = (resp.get("data") or {}) if isinstance(resp, dict) else {}
                current = int(data.get("current_batch") or 1)
                last = int(data.get("last_batch") or 1)
                calls = data.get("calls") or []
                if isinstance(calls, list):
                    for call in calls:
                        if isinstance(call, dict) and isinstance(call.get("call_id"), int):
                            cid = int(call["call_id"])
                            if max_seen is None or cid > max_seen:
                                max_seen = cid

                await emit(
                    {
                        "site_id": c.site_id,
                        "type": "poll_result",
                        "command": "get_calls",
                        "args": dict(args),
                        "payload": resp,
                    }
                )

                if current >= last:
                    break

            if max_seen is not None:
                await set_last_id(app.state.db, site_id=c.site_id, command="get_calls", last_id=max_seen)
            return

        if command == "get_events":
            for category in ("calls", "presences"):
                state_key = f"get_events:{category}"
                last_id = await get_last_id(app.state.db, site_id=c.site_id, command=state_key)
                args = {"category": category}
                if last_id is not None:
                    args["from_id"] = last_id

                max_seen: int | None = last_id
                current = 1
                last = 1
                while current <= last:
                    ref = str(uuid4())
                    req = {"command": "get_events", "command_ref": ref, "args": args}
                    resp = await _wba_request(c, req, timeout_s=timeout_s)
                    data = (resp.get("data") or {}) if isinstance(resp, dict) else {}
                    current = int(data.get("current_batch") or 1)
                    last = int(data.get("last_batch") or 1)
                    events = data.get("events") or []
                    if isinstance(events, list):
                        for ev in events:
                            if isinstance(ev, dict) and isinstance(ev.get("event_id"), int):
                                eid = int(ev["event_id"])
                                if max_seen is None or eid > max_seen:
                                    max_seen = eid

                    await emit(
                        {
                            "site_id": c.site_id,
                            "type": "poll_result",
                            "command": "get_events",
                            "category": category,
                            "args": dict(args),
                            "payload": resp,
                        }
                    )

                    if current >= last:
                        break

                if max_seen is not None:
                    await set_last_id(app.state.db, site_id=c.site_id, command=state_key, last_id=max_seen)
            return

        ref = str(uuid4())
        args: dict[str, Any] = {}
        req = {"command": command, "command_ref": ref, "args": args}
        resp = await _wba_request(c, req, timeout_s=timeout_s)
        await emit({"site_id": c.site_id, "type": "poll_result", "command": command, "args": dict(args), "payload": resp})

    async def _poll_rule_loop(app: FastAPI, c: _WbaClient, command: str, interval_seconds: int) -> None:
        while not c.stop.is_set():
            try:
                await _poll_once(app, c, command)
            except Exception:
                pass
            try:
                await asyncio.wait_for(c.stop.wait(), timeout=float(interval_seconds))
            except asyncio.TimeoutError:
                continue

    async def _reconcile_poll_tasks(
        app: FastAPI,
        c: _WbaClient,
        *,
        poll_tasks: dict[str, tuple[int, asyncio.Task]],
    ) -> None:
        async with app.state.db.conn.execute(
            """
            SELECT command, interval_seconds
            FROM site_poll_rules
            WHERE site_id = ? AND enabled = 1
            """,
            (c.site_id,),
        ) as cur:
            rules = await cur.fetchall()

        desired: dict[str, int] = {str(cmd): int(interval) for cmd, interval in rules}

        # stop removed rules
        for cmd, (_, t) in list(poll_tasks.items()):
            if cmd not in desired:
                t.cancel()
                poll_tasks.pop(cmd, None)

        # start new / restart changed interval
        for cmd, interval in desired.items():
            cur_entry = poll_tasks.get(cmd)
            if cur_entry and cur_entry[0] == interval and not cur_entry[1].done():
                continue
            if cur_entry:
                cur_entry[1].cancel()
            poll_tasks[cmd] = (interval, asyncio.create_task(_poll_rule_loop(app, c, cmd, interval)))

    async def _reconcile_subscriptions(app: FastAPI, c: _WbaClient, *, current: set[str]) -> set[str]:
        desired = await _load_subscribe_categories(app, site_id=c.site_id)
        if desired == current:
            return current

        to_unsub = current - desired
        to_sub = desired - current
        try:
            if to_unsub:
                await _wba_unsubscribe(app, c, to_unsub)
            if to_sub:
                await _wba_subscribe(app, c, to_sub)
        except Exception:
            # if subscription reconciliation fails, keep old set and try again later
            return current

        return desired

    async def _site_runner(app: FastAPI, site_row: tuple[Any, ...]) -> None:
        (
            site_id,
            site_name,
            wss_url,
            token,
        ) = site_row

        c = _WbaClient(
            site_id=str(site_id),
            site_name=str(site_name),
            wss_url=str(wss_url),
            token=str(token),
            ws=None,
            recv_task=None,
            pending={},
            lock=asyncio.Lock(),
            stop=asyncio.Event(),
            throttle_lock=asyncio.Lock(),
            next_send_at=0.0,
        )

        # Register client for downstream routing
        if not hasattr(app.state, "wba_clients_by_site_id"):
            app.state.wba_clients_by_site_id = {}
        app.state.wba_clients_by_site_id[c.site_id] = c

        reconnect_attempts = int(app.state.cfg.bt_defaults.reconnect_attempts)
        attempt = 0

        while not app.state.shutdown_event.is_set():
            # ensure site still active
            async with app.state.db.conn.execute(
                "SELECT is_active, wss_url, token_enc FROM sites WHERE id = ?",
                (c.site_id,),
            ) as cur:
                row = await cur.fetchone()

            if not row or not bool(row[0]):
                await _set_site_status(app, site_id=c.site_id, status="DISCONNECTED", last_error=None)
                return

            c.wss_url = str(row[1])
            c.token = str(row[2])
            c.stop = asyncio.Event()
            c.pending = {}

            poll_tasks: dict[str, tuple[int, asyncio.Task]] = {}
            current_subs: set[str] = set()
            try:
                await _set_site_status(app, site_id=c.site_id, status="CONNECTING", last_error=None)
                await _wba_connect(app, c)
                await _set_site_status(
                    app,
                    site_id=c.site_id,
                    status="CONNECTED",
                    last_error=None,
                    last_connected_at=datetime.now(tz=timezone.utc).isoformat(),
                )

                # initial subscriptions
                current_subs = await _load_subscribe_categories(app, site_id=c.site_id)
                await _wba_subscribe(app, c, current_subs)

                # initial poll rules
                await _reconcile_poll_tasks(app, c, poll_tasks=poll_tasks)

                # periodic reload loop
                while not app.state.shutdown_event.is_set() and not c.stop.is_set():
                    await asyncio.sleep(5)
                    await _reconcile_poll_tasks(app, c, poll_tasks=poll_tasks)
                    current_subs = await _reconcile_subscriptions(app, c, current=current_subs)

            except Exception as e:
                err = str(e)[:500]
                await _set_site_status(app, site_id=c.site_id, status="ERROR", last_error=err)
            finally:
                for _, t in poll_tasks.values():
                    t.cancel()
                await _wba_disconnect(c)

                # Keep registry in sync
                if getattr(app.state, "wba_clients_by_site_id", None) is not None:
                    # only remove if it's still the same object (avoid race with restart)
                    if app.state.wba_clients_by_site_id.get(c.site_id) is c:
                        app.state.wba_clients_by_site_id.pop(c.site_id, None)

            if app.state.shutdown_event.is_set():
                await _set_site_status(app, site_id=c.site_id, status="DISCONNECTED", last_error=None)
                return

            attempt += 1
            if reconnect_attempts > 0 and attempt > reconnect_attempts:
                await _set_site_status(app, site_id=c.site_id, status="ERROR", last_error="reconnect_attempts_exceeded")
                return

            backoff = min(60, 2 ** min(attempt, 6))
            await _set_site_status(app, site_id=c.site_id, status="RECONNECTING", last_error=None)
            try:
                await asyncio.wait_for(app.state.shutdown_event.wait(), timeout=float(backoff))
            except asyncio.TimeoutError:
                continue

    async def _polling_supervisor(app: FastAPI) -> None:
        tasks: dict[str, asyncio.Task] = {}
        try:
            while True:
                async with app.state.db.conn.execute(
                    """
                    SELECT id, site_name, wss_url, token_enc
                    FROM sites
                    WHERE is_active = 1
                    """
                ) as cur:
                    sites = await cur.fetchall()

                active_ids = {str(s[0]) for s in sites}
                for site_id, t in list(tasks.items()):
                    if site_id not in active_ids:
                        t.cancel()
                        tasks.pop(site_id, None)

                for s in sites:
                    site_id = str(s[0])
                    if site_id in tasks:
                        continue
                    tasks[site_id] = asyncio.create_task(_site_runner(app, s))

                await asyncio.sleep(10)
        finally:
            for t in tasks.values():
                t.cancel()

    @app.on_event("startup")
    async def _startup() -> None:
        app.state.cfg = load_config(os.environ.get("CONFIG_PATH"))
        app.state.db = await init_db()

        app.state.wba_clients_by_site_id: dict[str, _WbaClient] = {}

        app.state.runtime_settings = {}
        try:
            async with app.state.db.conn.execute("SELECT key, value FROM app_settings") as cur:
                rows = await cur.fetchall()
            for k, v in rows:
                if k == "bt_max_commands_per_second":
                    try:
                        app.state.runtime_settings["bt_max_commands_per_second"] = int(v)
                    except Exception:
                        pass
                if k == "log_base_path":
                    if isinstance(v, str) and v.strip():
                        app.state.runtime_settings["log_base_path"] = v.strip()
        except Exception:
            pass

        app.state.shutdown_event = asyncio.Event()

        app.state.log_writer = AsyncLogWriter()
        await app.state.log_writer.start()

        async def _retention_loop() -> None:
            policy = RetentionPolicy(
                retention_days=app.state.cfg.logging.default_retention_days,
                gzip_after_days=app.state.cfg.logging.compression_after_days,
            )
            base_dir = Path(app.state.cfg.logging.base_path)
            while True:
                await apply_retention(base_dir, policy)
                await asyncio.sleep(6 * 60 * 60)

        app.state.retention_task = asyncio.create_task(_retention_loop())

        app.state.polling_task = asyncio.create_task(_polling_supervisor(app))

        admin_ident = (os.environ.get("ADMIN_USERNAME") or os.environ.get("ADMIN_EMAIL") or "").strip()
        admin_password = (os.environ.get("ADMIN_PASSWORD") or "").strip()

        async with app.state.db.conn.execute("SELECT COUNT(1) FROM users") as cur:
            row = await cur.fetchone()
        user_count = int(row[0] if row else 0)

        # Bootstrap rules:
        # - If env vars are provided, ensure that user exists.
        # - Otherwise, if DB has no users, create default admin/admin.
        if admin_ident and admin_password:
            async with app.state.db.conn.execute(
                "SELECT id FROM users WHERE email = ?", (admin_ident,)
            ) as cur:
                row = await cur.fetchone()

            if not row:
                await app.state.db.conn.execute(
                    "INSERT INTO users (id, email, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)",
                    (
                        str(uuid4()),
                        admin_ident,
                        hash_password(admin_password),
                        "admin",
                        datetime.now(tz=timezone.utc).isoformat(),
                    ),
                )
                await app.state.db.conn.commit()
            else:
                # Allow credential reset via env vars.
                await app.state.db.conn.execute(
                    "UPDATE users SET password_hash = ?, role = ? WHERE email = ?",
                    (hash_password(admin_password), "admin", admin_ident),
                )
                await app.state.db.conn.commit()
        else:
            # Default local admin: ensure it exists so a fresh install always has a working login.
            # If you'd like to override this, set ADMIN_USERNAME + ADMIN_PASSWORD.
            async with app.state.db.conn.execute(
                "SELECT id FROM users WHERE email = ?", ("admin",)
            ) as cur:
                row = await cur.fetchone()
            if not row:
                await app.state.db.conn.execute(
                    "INSERT INTO users (id, email, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)",
                    (
                        str(uuid4()),
                        "admin",
                        hash_password("admin"),
                        "admin",
                        datetime.now(tz=timezone.utc).isoformat(),
                    ),
                )
                await app.state.db.conn.commit()

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        async def _cancel_and_wait(task: asyncio.Task | None, *, timeout_s: float) -> None:
            if not task:
                return
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await asyncio.wait_for(task, timeout=timeout_s)

        if getattr(app.state, "shutdown_event", None):
            app.state.shutdown_event.set()

        await _cancel_and_wait(getattr(app.state, "polling_task", None), timeout_s=10)
        await _cancel_and_wait(getattr(app.state, "retention_task", None), timeout_s=10)

        if getattr(app.state, "log_writer", None):
            with contextlib.suppress(Exception):
                await asyncio.wait_for(app.state.log_writer.stop(), timeout=10)

        db: Db = app.state.db
        with contextlib.suppress(Exception):
            await asyncio.wait_for(db.conn.close(), timeout=5)

    app.include_router(health_route.router, prefix="/api")
    app.include_router(auth_route.router, prefix="/api")
    app.include_router(users_route.router, prefix="/api")
    app.include_router(sites_route.router, prefix="/api")
    app.include_router(connections_route.router, prefix="/api")
    app.include_router(metrics_route.router, prefix="/api")
    app.include_router(settings_route.router, prefix="/api")
    app.include_router(logs_router, prefix="/api")

    async def _downstream_ws(ws: WebSocket) -> None:
        log.info("downstream_ws_connect client=%s path=/api", getattr(ws, "client", None))
        await ws.accept()

        async def _send_downstream_response(*, ref: str, success: bool, data: dict | None = None, error: str | None = None) -> None:
            payload: dict[str, Any] = {
                "command": "response",
                "command_ref": ref,
                "success": bool(success),
            }
            if error is not None:
                payload["error"] = {"message": error}
            if data is not None:
                payload["data"] = data
            await ws.send_text(json.dumps(payload))

        # BT/WBA-style auth: first message must be {"command":"auth","command_ref":"...","args":{"token":"<32>"}}
        try:
            raw = await asyncio.wait_for(ws.receive_text(), timeout=10)
            first = json.loads(raw)
        except Exception:
            await ws.close(code=4401)
            return

        if not isinstance(first, dict) or first.get("command") != "auth":
            await ws.send_text(json.dumps({"ok": False, "error": "auth_required"}))
            await ws.close(code=4401)
            return

        command_ref = str(first.get("command_ref") or "")
        args = first.get("args") if isinstance(first.get("args"), dict) else {}
        token = str((args or {}).get("token") or "")

        async def _send_auth_reply(*, ref: str, ok: bool, data: dict | None = None, error: str | None = None, legacy_prefix: str) -> None:
            # TSN/WBA-style: auth replies are regular `response` messages with a boolean `success`.
            # Keep the same command_ref as the request.
            await _send_downstream_response(ref=ref, success=bool(ok), data=data, error=error)
        if not token:
            await _send_auth_reply(ref=command_ref, ok=False, error="missing_token", legacy_prefix="auth")
            await ws.close(code=4401)
            return

        async with app.state.db.conn.execute(
            "SELECT id, allowed_site_ids_json, enhanced_messaging, revoked FROM app_connections WHERE token = ?",
            (token,),
        ) as cur:
            row = await cur.fetchone()

        if not row:
            await _send_auth_reply(ref=command_ref, ok=False, error="invalid_token", legacy_prefix="auth")
            await ws.close(code=4403)
            return

        conn_id, allowed_site_ids_json, enhanced_messaging, revoked = row
        if revoked:
            await _send_auth_reply(ref=command_ref, ok=False, error="revoked", legacy_prefix="auth")
            await ws.close(code=4403)
            return

        try:
            allowed = set(json.loads(allowed_site_ids_json))
        except Exception:
            allowed = set()

        # Capability negotiation: effective enhanced messaging is only enabled if
        # (a) the connection is marked enhanced in DB, AND
        # (b) the app declares capabilities.enhanced_messaging=true in auth args.
        caps = (args or {}).get("capabilities") if isinstance((args or {}).get("capabilities"), dict) else {}
        app_supports_enhanced = bool((caps or {}).get("enhanced_messaging"))
        effective_enhanced = bool(enhanced_messaging) and app_supports_enhanced

        auth_timeout_s = int(getattr(app.state.cfg.security, "wba_auth_timeout_seconds", 0) or 0)
        auth_grace_s = int(getattr(app.state.cfg.security, "wba_auth_gracetime_seconds", 0) or 0)
        if auth_timeout_s < 0:
            auth_timeout_s = 0
        if auth_grace_s < 0:
            auth_grace_s = 0
        if auth_timeout_s and auth_grace_s and auth_grace_s >= auth_timeout_s:
            auth_grace_s = max(0, auth_timeout_s - 1)

        auth_lock = asyncio.Lock()
        authed_token = token
        authed_at = time.monotonic()
        reauth_notified = False
        ws_closed = False

        ping_enabled = bool(getattr(app.state.cfg.security, "wba_ping_enabled", True))
        ping_interval_s = int(getattr(app.state.cfg.security, "wba_ping_interval_seconds", 5) or 5)
        if ping_interval_s < 1:
            ping_interval_s = 1

        async def _send_server_notification(*, ref: str, message: str) -> None:
            await ws.send_text(json.dumps({"command": "server notification", "command_ref": ref, "message": message}))

        async def _reauth_scheduler() -> None:
            nonlocal authed_at, reauth_notified, ws_closed
            if not auth_timeout_s or not auth_grace_s:
                return
            while True:
                async with auth_lock:
                    if ws_closed:
                        return
                    local_authed_at = authed_at

                notify_in = (auth_timeout_s - auth_grace_s) - (time.monotonic() - local_authed_at)
                if notify_in > 0:
                    await asyncio.sleep(notify_in)

                async with auth_lock:
                    if ws_closed:
                        return
                    if authed_at != local_authed_at:
                        continue
                    reauth_notified = True

                await _send_server_notification(
                    ref="authentication expiry",
                    message="Your authentication token is about to expire, please re-authenticate",
                )
                await metrics.inc_down_out(str(conn_id))

                grace_left = auth_grace_s - (time.monotonic() - (local_authed_at + (auth_timeout_s - auth_grace_s)))
                if grace_left > 0:
                    await asyncio.sleep(grace_left)

                async with auth_lock:
                    if ws_closed:
                        return
                    if authed_at != local_authed_at:
                        continue

                await _send_server_notification(ref="session expired", message="Session is expired")
                await metrics.inc_down_out(str(conn_id))
                with contextlib.suppress(Exception):
                    await ws.close(code=4401)
                async with auth_lock:
                    ws_closed = True
                return

        async def _ping_loop() -> None:
            nonlocal ws_closed
            if not ping_enabled:
                return
            while True:
                await asyncio.sleep(ping_interval_s)
                async with auth_lock:
                    if ws_closed:
                        return
                try:
                    # WBA specifies a websocket ping frame. Starlette doesn't expose ping frames,
                    # so we emit an application-level ping message to keep client listeners alive.
                    now_ms = int(time.time() * 1000)
                    await ws.send_text(json.dumps({"command": "ping", "command_ref": str(now_ms), "data": {}}))
                    await ws.send_text(
                        json.dumps(
                            {
                                "command": "server notification",
                                "command_ref": "ping",
                                "message": "ping",
                            }
                        )
                    )
                    await metrics.inc_down_out(str(conn_id))
                except Exception:
                    async with auth_lock:
                        ws_closed = True
                    return

        await _send_auth_reply(
            ref=command_ref,
            ok=True,
            data={
                "capabilities": {
                    "enhanced_messaging": effective_enhanced,
                    "multi_site": effective_enhanced,
                    "site_id_routing": effective_enhanced,
                    "ctd": True,
                }
            },
            legacy_prefix="auth",
        )

        log.info("downstream_ws_authed conn_id=%s", str(conn_id))

        client = DownstreamClient(
            ws=ws,
            conn_id=str(conn_id),
            allowed_site_ids=allowed,
            subscribed_site_ids=set(),
            enhanced_messaging=bool(effective_enhanced),
            connected_at=time.time(),
            client_host=getattr(getattr(ws, "client", None), "host", None),
        )
        await hub.register(client)

        reauth_task = asyncio.create_task(_reauth_scheduler())
        ping_task = asyncio.create_task(_ping_loop())

        try:
            while True:
                raw = await ws.receive_text()
                await metrics.inc_down_in(str(conn_id))
                msg = json.loads(raw)

                if isinstance(msg, dict):
                    log.info(
                        "downstream_ws_in conn_id=%s cmd=%s ref=%s",
                        str(conn_id),
                        str(msg.get("command") or ""),
                        str(msg.get("command_ref") or ""),
                    )

                if isinstance(msg, dict) and msg.get("command") == "ping":
                    ref = str(msg.get("command_ref") or "")
                    await ws.send_text(json.dumps({"command": "pong", "command_ref": ref, "ok": True, "data": {}}))
                    await metrics.inc_down_out(str(conn_id))
                    continue

                if isinstance(msg, dict):
                    cmd = str(msg.get("command") or "")
                    ref = str(msg.get("command_ref") or "")
                    margs = msg.get("args") if isinstance(msg.get("args"), dict) else {}

                    def _get_site_id_from_args() -> str:
                        return str((margs or {}).get("site_id") or "")

                    async def _route_to_site(*, site_id: str) -> None:
                        if not site_id:
                            await _send_downstream_response(ref=ref, success=False, error="site_id_required")
                            await metrics.inc_down_out(str(conn_id))
                            return
                        if site_id not in client.allowed_site_ids:
                            await _send_downstream_response(ref=ref, success=False, error="forbidden_site")
                            await metrics.inc_down_out(str(conn_id))
                            return

                        upstream = getattr(app.state, "wba_clients_by_site_id", {}).get(site_id)
                        if not upstream or not getattr(upstream, "ws", None):
                            await _send_downstream_response(ref=ref, success=False, error="site_not_connected")
                            await metrics.inc_down_out(str(conn_id))
                            return

                        upstream_payload = dict(msg)
                        upstream_payload["command_ref"] = str(uuid4())
                        if "args" in upstream_payload and isinstance(upstream_payload.get("args"), dict):
                            # do not forward routing hint upstream
                            upstream_payload["args"] = {k: v for k, v in (upstream_payload.get("args") or {}).items() if k != "site_id"}

                        try:
                            cached = None
                            if cmd in GET_COMMANDS:
                                cached = await _get_cached_poll_response(site_id=site_id, command=cmd)
                            if isinstance(cached, dict):
                                if _is_cache_compatible(command=cmd, req_args=margs or {}, cached_resp=cached):
                                    out = dict(cached)
                                    out.pop("_nb_poll_args", None)
                                    out["command"] = "response"
                                    out["command_ref"] = ref
                                    if "success" not in out:
                                        out["success"] = bool(out.get("ok"))
                                        out.pop("ok", None)
                                    await ws.send_text(json.dumps(out))
                                    await metrics.inc_down_out(str(conn_id))
                                    return

                            resp = await _wba_request(
                                upstream,
                                upstream_payload,
                                timeout_s=float(app.state.cfg.bt_defaults.command_timeout_seconds),
                            )
                            if isinstance(resp, dict):
                                out = dict(resp)
                                out["command"] = "response"
                                out["command_ref"] = ref
                                # ensure TSN-style success boolean exists
                                if "success" not in out:
                                    out["success"] = bool(out.get("ok"))
                                    out.pop("ok", None)
                                await ws.send_text(json.dumps(out))
                            else:
                                await _send_downstream_response(ref=ref, success=False, error="invalid_upstream_response")
                        except Exception as e:
                            await _send_downstream_response(ref=ref, success=False, error=str(e)[:200])

                        await metrics.inc_down_out(str(conn_id))

                    # CTD is supported in both legacy and enhanced
                    if cmd == "service_ctd":
                        site_id = _get_site_id_from_args()
                        if not site_id:
                            # legacy fallback: if exactly one site is allowed, route there
                            if len(client.allowed_site_ids) == 1:
                                site_id = next(iter(client.allowed_site_ids))
                            else:
                                await _send_downstream_response(ref=ref, success=False, error="site_id_required")
                                await metrics.inc_down_out(str(conn_id))
                                continue
                        await _route_to_site(site_id=site_id)
                        continue

                    # Legacy cached GET support: if not enhanced and exactly one site allowed,
                    # satisfy get_* from cached poll log (or fallback to upstream).
                    if (not client.enhanced_messaging) and cmd in GET_COMMANDS and len(client.allowed_site_ids) == 1:
                        site_id = next(iter(client.allowed_site_ids))
                        await _route_to_site(site_id=site_id)
                        continue

                    # Enhanced pass-through for other commands: require enhanced mode + site_id
                    if client.enhanced_messaging and cmd and cmd not in {"auth", "subscribe", "ping", "pong"}:
                        # allow NexusBridge-specific subscribe_site/unsubscribe_site to fall through to existing handlers
                        if cmd not in {"subscribe_site", "unsubscribe_site"}:
                            site_id = _get_site_id_from_args()
                            await _route_to_site(site_id=site_id)
                            continue

                if isinstance(msg, dict) and msg.get("command") == "subscribe":
                    ref = str(msg.get("command_ref") or "")
                    args = msg.get("args") if isinstance(msg.get("args"), dict) else {}
                    category = str((args or {}).get("category") or "")
                    # WBA-style: accept subscription requests. NexusBridge currently routes by site_id,
                    # so this is a no-op for compatibility.
                    payload: dict[str, Any] = {
                        "command": "response",
                        "command_ref": ref,
                        "ok": True,
                        "success": True,
                        "data": {"subscribed": bool(category), "category": category},
                    }
                    await ws.send_text(json.dumps(payload))
                    await metrics.inc_down_out(str(conn_id))
                    continue

                if isinstance(msg, dict) and msg.get("command") == "auth":
                    ref = str(msg.get("command_ref") or "")
                    margs = msg.get("args") if isinstance(msg.get("args"), dict) else {}
                    mtok = str((margs or {}).get("token") or "")

                    async with auth_lock:
                        allow_now = (not auth_timeout_s or not auth_grace_s) or reauth_notified
                        same_token = (mtok == authed_token)

                    if not mtok:
                        await _send_auth_reply(ref=ref, ok=False, error="missing_token", legacy_prefix="reauth")
                        await metrics.inc_down_out(str(conn_id))
                        continue

                    if not allow_now:
                        await _send_auth_reply(ref=ref, ok=False, error="already_authenticated", legacy_prefix="reauth")
                        await metrics.inc_down_out(str(conn_id))
                        continue

                    if not same_token:
                        await _send_auth_reply(ref=ref, ok=False, error="invalid_token", legacy_prefix="reauth")
                        await metrics.inc_down_out(str(conn_id))
                        with contextlib.suppress(Exception):
                            await ws.close(code=4403)
                        break

                    async with auth_lock:
                        authed_at = time.monotonic()
                        reauth_notified = False

                    await _send_auth_reply(ref=ref, ok=True, data=None, legacy_prefix="reauth")
                    await metrics.inc_down_out(str(conn_id))
                    continue

                # Downstream control messages (NexusBridge-specific)
                action = msg.get("action") if isinstance(msg, dict) else None
                command = msg.get("command") if isinstance(msg, dict) else None

                if action == "subscribe_site" or command == "subscribe_site":
                    site_id = str((msg or {}).get("site_id") or "")
                    if site_id and site_id in client.allowed_site_ids:
                        client.subscribed_site_ids.add(site_id)
                        await ws.send_text(json.dumps({"ok": True, "action": "subscribe_site", "site_id": site_id}))
                        await metrics.inc_down_out(str(conn_id))
                    else:
                        await ws.send_text(json.dumps({"ok": False, "error": "forbidden_or_missing_site"}))
                        await metrics.inc_down_out(str(conn_id))
                    continue

                if action == "unsubscribe_site" or command == "unsubscribe_site":
                    site_id = str((msg or {}).get("site_id") or "")
                    client.subscribed_site_ids.discard(site_id)
                    await ws.send_text(json.dumps({"ok": True, "action": "unsubscribe_site", "site_id": site_id}))
                    await metrics.inc_down_out(str(conn_id))
                    continue

                await ws.send_text(json.dumps({"ok": False, "error": "unknown_action"}))
                await metrics.inc_down_out(str(conn_id))

        except WebSocketDisconnect:
            log.info("downstream_ws_disconnect conn_id=%s", str(conn_id))
            pass
        except Exception:
            log.exception("downstream_ws_error conn_id=%s", str(conn_id))
            pass
        finally:
            log.info(
                "downstream_ws_finally conn_id=%s state=%s",
                str(conn_id),
                getattr(ws, "client_state", None),
            )
            with contextlib.suppress(Exception):
                reauth_task.cancel()
            with contextlib.suppress(Exception):
                ping_task.cancel()
            async with auth_lock:
                ws_closed = True
            await hub.unregister(client)

    @app.websocket("/api")
    async def api_ws_endpoint(ws: WebSocket):
        await _downstream_ws(ws)

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await _downstream_ws(ws)

    return app


app = create_app()
