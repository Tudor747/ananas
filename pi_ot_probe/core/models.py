"""Transport-independent domain models for the probe."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum, IntEnum
from typing import Any
from uuid import uuid4


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class ScanLevel(IntEnum):
    PASSIVE = 0
    DISCOVERY = 1
    VERIFY = 2
    ACTIVE_TEST = 3


class ScanProfile(str, Enum):
    OFFICE = "office"
    INDUSTRIAL = "industrial"
    CUSTOM = "custom"


class ScanStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(slots=True)
class Service:
    port: int
    transport: str = "tcp"
    name: str = "unknown"
    product: str | None = None
    version: str | None = None
    evidence: str | None = None
    state: str = "open"
    reason: str | None = None
    method: str | None = None
    confidence: int | None = None
    extra_info: str | None = None
    tunnel: str | None = None
    cpes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ProtocolObservation:
    name: str
    port: int | None = None
    confidence: float = 0.0
    evidence: str | None = None


@dataclass(slots=True)
class NetworkInterface:
    name: str
    mac: str | None = None
    addresses: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Asset:
    ip: str
    mac: str | None = None
    hostname: str | None = None
    vendor: str | None = None
    device_type: str = "unknown"
    interfaces: list[NetworkInterface] = field(default_factory=list)
    ports: list[int] = field(default_factory=list)
    services: list[Service] = field(default_factory=list)
    protocols: list[ProtocolObservation] = field(default_factory=list)
    first_seen: datetime = field(default_factory=utc_now)
    last_seen: datetime = field(default_factory=utc_now)
    risk_score: int = 0
    criticality: str = "normal"
    confidence: float = 0.0
    id: int | None = None
    source: str = "unknown"
    status: str = "up"
    discovery_reason: str | None = None
    hostnames: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Risk:
    score: int
    severity: Severity
    title: str
    asset: str
    technical_reason: str
    human_explanation: str
    recommendation: str
    confidence: float = 1.0


@dataclass(slots=True)
class Finding:
    title: str
    asset: str
    technical_reason: str
    human_explanation: str
    recommendation: str
    severity: Severity
    risk_score: int
    confidence: float
    evidence: str
    category: str = "security"
    id: int | None = None
    scan_id: str | None = None
    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class Scan:
    site: str
    level: ScanLevel
    profile: ScanProfile
    target: str
    simulation: bool = False
    authorized: bool = False
    id: str = field(default_factory=lambda: str(uuid4()))
    status: ScanStatus = ScanStatus.PENDING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    assets_found: int = 0
    findings_found: int = 0
    cancelled: bool = False
    error: str | None = None


@dataclass(slots=True)
class ScanProgress:
    completed: int
    total: int
    message: str
    asset: Asset | None = None


@dataclass(slots=True)
class WifiAccessPoint:
    ssid: str
    bssid: str
    signal_dbm: int
    channel: int
    encryption: str
    suspicious: bool = False
    signal_percent: int | None = None
    frequency_mhz: int | None = None
    band: str | None = None
    authentication: str | None = None
    cipher: str | None = None
    radio_type: str | None = None
    network_type: str | None = None
    mode: str | None = None
    rate: str | None = None
    source: str = "unknown"


@dataclass(slots=True)
class ChangeEvent:
    change_type: str
    asset_identity: str
    summary: str
