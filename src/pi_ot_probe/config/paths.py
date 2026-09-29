"""Resolve data paths once; collectors and routes should not guess directories."""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
STATIC_DIR = Path(__file__).resolve().parents[1] / "web" / "static"


def default_database() -> Path:
    configured = os.getenv("PI_OT_DEMO_DATABASE")
    if configured:
        return Path(configured).expanduser()
    # Reuse existing data without copying a potentially open SQLite database.
    legacy = PROJECT_ROOT / "kali_demo" / "data" / "demo.db"
    if legacy.is_file():
        return legacy
    return Path.cwd() / "data" / "inventory.db"
