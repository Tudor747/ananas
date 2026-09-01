"""A safe scanner producing realistic but entirely synthetic observations."""

from __future__ import annotations

from collections.abc import AsyncIterator
import asyncio
from dataclasses import dataclass

from pi_ot_probe.core.models import (
    Asset,
    ChangeEvent,
    ProtocolObservation,
    ScanLevel,
    ScanProgress,
    Service,
    WifiAccessPoint,
)
from pi_ot_probe.scanners.base import CancellationToken, ScanArtifacts, ScanContext, Scanner


@dataclass(frozen=True, slots=True)
class SimulationSnapshot:
    assets: list[Asset]
    access_points: list[WifiAccessPoint]
    changes: list[ChangeEvent]


def build_snapshot(scenario: str = "changed") -> SimulationSnapshot:
    """Build repeatable snapshots used by demos and tests.

    ``baseline`` is a quiet initial site. ``changed`` demonstrates a new
    device, removed device, new port, rogue AP, PLC detection, and a high-risk
    finding input. No addresses are contacted.
    """
    router = Asset(
        ip="192.168.1.1", mac="02:00:00:00:00:01", hostname="gateway",
        vendor="Example Networks", device_type="router", ports=[53, 80],
        services=[Service(53, "udp", "dns"), Service(80, name="http")],
        risk_score=18, criticality="high", confidence=0.98, source="simulation",
    )
    engineer = Asset(
        ip="192.168.1.10", mac="02:00:00:00:00:10", hostname="ENG-WS01",
        vendor="Example Computing", device_type="engineering workstation",
        ports=[22], services=[Service(22, name="ssh")], risk_score=27,
        criticality="high", confidence=0.94, source="simulation",
    )
    plc = Asset(
        ip="192.168.1.20", mac="02:00:00:00:00:20", hostname="PLC01",
        vendor="Siemens", device_type="PLC", ports=[102],
        services=[Service(102, name="iso-tsap", evidence="synthetic S7 endpoint")],
        protocols=[ProtocolObservation("S7", 102, 0.92, "synthetic port and fingerprint")],
        risk_score=64, criticality="high", confidence=0.92, source="simulation",
    )
    hmi = Asset(
        ip="192.168.1.21", mac="02:00:00:00:00:21", hostname="HMI01",
        vendor="Example Automation", device_type="HMI", ports=[80, 502],
        services=[Service(80, name="http"), Service(502, name="modbus")],
        protocols=[ProtocolObservation("Modbus/TCP", 502, 0.96, "synthetic protocol response")],
        risk_score=88, criticality="high", confidence=0.96, source="simulation",
    )
    camera = Asset(
        ip="192.168.1.40", mac="02:00:00:00:00:40", hostname="CAM01",
        vendor="Example Vision", device_type="camera", ports=[80, 554],
        services=[Service(80, name="http"), Service(554, name="rtsp")],
        risk_score=42, confidence=0.89, source="simulation",
    )
    baseline_assets = [router, engineer, plc, camera]
    if scenario == "baseline":
        return SimulationSnapshot(
            assets=baseline_assets,
            access_points=[WifiAccessPoint("FACTORY", "02:AA:00:00:00:01", -43, 6, "WPA2")],
            changes=[],
        )
    if scenario != "changed":
        raise ValueError("scenario must be 'baseline' or 'changed'")
    plc.ports.append(80)
    plc.services.append(Service(80, name="http", evidence="synthetic newly observed service"))
    assets = [router, engineer, plc, hmi, camera]
    return SimulationSnapshot(
        assets=assets,
        access_points=[
            WifiAccessPoint("FACTORY", "02:AA:00:00:00:01", -43, 6, "WPA2"),
            WifiAccessPoint("FACTORY", "02:AA:00:00:99:99", -37, 11, "OPEN", suspicious=True),
        ],
        changes=[
            ChangeEvent("new_device", hmi.ip, "HMI appeared since the baseline"),
            ChangeEvent("removed_device", "192.168.1.30", "historian is no longer observed"),
            ChangeEvent("new_port", plc.ip, "TCP/80 newly observed on PLC01"),
            ChangeEvent("new_wifi_ap", "02:AA:00:00:99:99", "duplicate open FACTORY SSID"),
        ],
    )


class SimulationScanner(Scanner):
    name = "simulation"
    maximum_level = ScanLevel.DISCOVERY

    def __init__(self, scenario: str = "changed", delay_seconds: float = 0.05) -> None:
        self.snapshot = build_snapshot(scenario)
        self.delay_seconds = max(0.0, delay_seconds)

    async def scan(
        self, context: ScanContext, cancellation: CancellationToken
    ) -> AsyncIterator[ScanProgress]:
        total = len(self.snapshot.assets)
        for index, asset in enumerate(self.snapshot.assets, start=1):
            cancellation.raise_if_cancelled()
            if self.delay_seconds:
                await asyncio.sleep(self.delay_seconds)
            yield ScanProgress(index, total, f"Found {asset.device_type}", asset)

    def artifacts(self) -> ScanArtifacts:
        return ScanArtifacts(tuple(self.snapshot.access_points), tuple(self.snapshot.changes))
