"""Privilege separation policy helpers."""

from pathlib import Path


def private_file_mode(path: Path) -> None:
    path.chmod(0o600)

