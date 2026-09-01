"""Interfaces implemented by passive, discovery, and verification scanners."""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass

from pi_ot_probe.core.models import ChangeEvent, ScanLevel, ScanProfile, ScanProgress, WifiAccessPoint


class ScanCancelled(Exception):
    """Raised when an operator requests an emergency scan cancellation."""


class CancellationToken:
    def __init__(self) -> None:
        self._event = asyncio.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise ScanCancelled("scan cancelled by operator")


@dataclass(frozen=True, slots=True)
class ScanContext:
    site: str
    target: str
    level: ScanLevel
    profile: ScanProfile
    authorized: bool = False


@dataclass(frozen=True, slots=True)
class ScanArtifacts:
    access_points: tuple[WifiAccessPoint, ...] = ()
    changes: tuple[ChangeEvent, ...] = ()


class Scanner(ABC):
    """A bounded scanner that streams progress and honors cancellation."""

    name: str
    maximum_level: ScanLevel

    @abstractmethod
    def scan(
        self, context: ScanContext, cancellation: CancellationToken
    ) -> AsyncIterator[ScanProgress]:
        raise NotImplementedError

    def artifacts(self) -> ScanArtifacts:
        return ScanArtifacts()
