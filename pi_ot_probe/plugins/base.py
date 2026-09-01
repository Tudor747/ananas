"""Contract for expandable identification and verification plugins."""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass
from typing import Any

from pi_ot_probe.core.models import Asset, Finding, ScanLevel
from pi_ot_probe.scanners.base import CancellationToken, ScanContext


@dataclass(frozen=True, slots=True)
class PluginMetadata:
    name: str
    description: str
    protocol: str | None
    safety_level: ScanLevel
    ot_safe: bool
    requires_confirmation: bool


class SecurityPlugin(ABC):
    """Base class with safe no-op defaults for optional plugin phases."""

    metadata: PluginMetadata

    async def detect(
        self, asset: Asset, context: ScanContext, cancellation: CancellationToken
    ) -> list[Finding]:
        cancellation.raise_if_cancelled()
        return []

    async def verify(
        self, asset: Asset, context: ScanContext, cancellation: CancellationToken
    ) -> list[Finding]:
        cancellation.raise_if_cancelled()
        return []

    async def analyze(self, asset: Asset, observations: list[Any]) -> list[Finding]:
        return []

    async def report(self, findings: list[Finding]) -> dict[str, Any]:
        return {"plugin": self.metadata.name, "findings": len(findings)}

