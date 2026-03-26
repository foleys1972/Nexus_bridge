from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LogPaths:
    base: Path

    def system_dir(self) -> Path:
        return self.base / "system"

    def site_dir(self, site_id: str) -> Path:
        return self.base / site_id

    def site_type_dir(self, site_id: str, log_type: str) -> Path:
        return self.site_dir(site_id) / log_type
