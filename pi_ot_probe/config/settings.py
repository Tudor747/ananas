"""Environment-driven settings with safe local defaults."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    database_path: Path = Path("data/pi_ot_probe.db")
    simulation_mode: bool = False
    log_level: str = "INFO"
    management_host: str = "127.0.0.1"
    management_port: int = 8080
    lcd_columns: int = 16
    lcd_rows: int = 2
    api_token: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_path=Path(os.getenv("PI_OT_DATABASE", "data/pi_ot_probe.db")),
            simulation_mode=_as_bool(os.getenv("SIMULATION_MODE")),
            log_level=os.getenv("PI_OT_LOG_LEVEL", "INFO").upper(),
            management_host=os.getenv("PI_OT_MANAGEMENT_HOST", "127.0.0.1"),
            management_port=int(os.getenv("PI_OT_MANAGEMENT_PORT", "8080")),
            api_token=os.getenv("PI_OT_API_TOKEN"),
        )
