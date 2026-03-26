from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
import yaml


@dataclass(frozen=True)
class ServerConfig:
    host: str
    port: int


@dataclass(frozen=True)
class LoggingConfig:
    base_path: str
    default_rotation_size_mb: int
    default_retention_days: int
    compression_after_days: int


@dataclass(frozen=True)
class SecurityConfig:
    jwt_secret: str
    session_timeout_minutes: int
    max_clients: int
    wba_auth_timeout_seconds: int
    wba_auth_gracetime_seconds: int
    wba_ping_enabled: bool
    wba_ping_interval_seconds: int


@dataclass(frozen=True)
class BtDefaults:
    heartbeat_interval_seconds: int
    reconnect_attempts: int
    command_timeout_seconds: int
    max_commands_per_second: int


@dataclass(frozen=True)
class AppConfig:
    server: ServerConfig
    logging: LoggingConfig
    security: SecurityConfig
    bt_defaults: BtDefaults


def effective_log_base_path(cfg: AppConfig, runtime_settings: dict | None) -> str:
    if isinstance(runtime_settings, dict):
        v = runtime_settings.get("log_base_path")
        if isinstance(v, str) and v.strip():
            return v.strip()
    return cfg.logging.base_path


def load_config(config_path: str | None) -> AppConfig:
    p = Path(config_path or os.environ.get("CONFIG_PATH") or "config.yaml").resolve()
    raw = p.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)

    jwt_secret = os.environ.get("JWT_SECRET")
    if not jwt_secret:
        repo_root = Path(__file__).resolve().parents[3]
        env_path = repo_root / ".env"
        if env_path.exists():
            load_dotenv(dotenv_path=env_path, override=False)
        jwt_secret = os.environ.get("JWT_SECRET")
    if not jwt_secret:
        raise RuntimeError("JWT_SECRET is required")

    log_base_path = os.environ.get("LOG_BASE_PATH") or str(data["logging"]["base_path"])

    env_max_cps = os.environ.get("BT_MAX_COMMANDS_PER_SECOND")
    max_cps = int(env_max_cps) if (env_max_cps and env_max_cps.isdigit()) else None
    if max_cps is None:
        max_cps = int((data.get("bt_defaults") or {}).get("max_commands_per_second") or 5)

    return AppConfig(
        server=ServerConfig(
            host=str(data["server"]["host"]),
            port=int(data["server"]["port"]),
        ),
        logging=LoggingConfig(
            base_path=log_base_path,
            default_rotation_size_mb=int(data["logging"]["default_rotation_size_mb"]),
            default_retention_days=int(data["logging"]["default_retention_days"]),
            compression_after_days=int(data["logging"]["compression_after_days"]),
        ),
        security=SecurityConfig(
            jwt_secret=jwt_secret,
            session_timeout_minutes=int(data["security"]["session_timeout_minutes"]),
            max_clients=int(data["security"]["max_clients"]),
            wba_auth_timeout_seconds=int((data.get("security") or {}).get("wba_auth_timeout_seconds") or 0),
            wba_auth_gracetime_seconds=int((data.get("security") or {}).get("wba_auth_gracetime_seconds") or 0),
            wba_ping_enabled=bool((data.get("security") or {}).get("wba_ping_enabled", True)),
            wba_ping_interval_seconds=int((data.get("security") or {}).get("wba_ping_interval_seconds") or 5),
        ),
        bt_defaults=BtDefaults(
            heartbeat_interval_seconds=int(data["bt_defaults"]["heartbeat_interval_seconds"]),
            reconnect_attempts=int(data["bt_defaults"]["reconnect_attempts"]),
            command_timeout_seconds=int(data["bt_defaults"]["command_timeout_seconds"]),
            max_commands_per_second=max_cps,
        ),
    )
