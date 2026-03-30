from __future__ import annotations

from pathlib import Path
import os
import sys
import traceback

import uvicorn


def _load_dotenv(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = (raw or "").strip()
        if not s or s.startswith("#"):
            continue
        if "=" not in s:
            continue
        k, v = s.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _get_base_dir() -> Path:
    if _is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _write_crash_log(log_dir: Path, exc: BaseException) -> None:
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        p = log_dir / "exe-crash.log"
        p.write_text(
            "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
            encoding="utf-8",
            errors="ignore",
        )
    except Exception:
        pass


def _write_startup_log(log_dir: Path, lines: list[str]) -> None:
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        p = log_dir / "exe-startup.log"
        p.write_text("\n".join(lines) + "\n", encoding="utf-8", errors="ignore")
    except Exception:
        pass


def main() -> None:
    base_dir = _get_base_dir()
    _load_dotenv(base_dir / ".env")

    os.environ.setdefault("NB_BASE_DIR", str(base_dir))
    os.environ.setdefault("NB_FRONTEND_DIR", str((base_dir / "frontend").resolve()))

    logs_dir = Path(os.environ.get("LOG_BASE_PATH") or (base_dir / "logs")).resolve()
    os.environ.setdefault("CONFIG_PATH", str((base_dir / "config.yaml").resolve()))
    os.environ.setdefault("LOG_BASE_PATH", str(logs_dir))
    logs_dir.mkdir(parents=True, exist_ok=True)

    startup_lines = [
        f"frozen={_is_frozen()}",
        f"base_dir={base_dir}",
        f"config_path={os.environ.get('CONFIG_PATH')}",
        f"log_base_path={os.environ.get('LOG_BASE_PATH')}",
        f"dotenv_path={(base_dir / '.env').resolve()}",
        f"dotenv_exists={(base_dir / '.env').exists()}",
        f"jwt_secret_set={bool(os.environ.get('JWT_SECRET'))}",
        f"encryption_key_set={bool(os.environ.get('ENCRYPTION_KEY_BASE64'))}",
    ]
    _write_startup_log(logs_dir, startup_lines)
    print("\n".join(["NexusBridge EXE startup:"] + startup_lines), flush=True)

    host = os.environ.get("NB_HOST") or "0.0.0.0"
    port = int(os.environ.get("NB_PORT") or "3000")

    from app.main import app as fastapi_app

    try:
        uvicorn.run(
            fastapi_app,
            host=host,
            port=port,
            log_level="debug",
            access_log=True,
            ws_ping_interval=None,
            ws_ping_timeout=None,
        )
        print("\nNexusBridge server stopped.", flush=True)
        if _is_frozen():
            input("\nServer stopped. Press Enter to exit...")
    except BaseException as exc:
        _write_crash_log(logs_dir, exc)
        print("\nNexusBridge failed to start.")
        print(f"Crash log written to: {logs_dir / 'exe-crash.log'}")
        print("\nError:")
        traceback.print_exc()
        if _is_frozen():
            input("\nPress Enter to exit...")
        raise


if __name__ == "__main__":
    main()
