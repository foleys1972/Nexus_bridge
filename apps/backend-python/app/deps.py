from __future__ import annotations

from fastapi import Request

from app.config import AppConfig
from app.db import Db
from app.logging.writer import AsyncLogWriter


def get_cfg(request: Request) -> AppConfig:
    return request.app.state.cfg


def get_db(request: Request) -> Db:
    return request.app.state.db


def get_log_writer(request: Request) -> AsyncLogWriter:
    return request.app.state.log_writer
