"""Nmap support for bounded, real local observations."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import ipaddress
import os
import shutil
import sys
import xml.etree.ElementTree as ET
from pi_ot_probe.domain.models import Asset, ScanLevel, ScanProgress, Service, utc_now
from pi_ot_probe.scanners.base import CancellationToken, ScanContext, Scanner

NMAP_TIMEOUT_SECONDS = 180


def find_nmap() -> str | None:
    """Locate Nmap from PATH or its standard Windows installer directories."""
    located = shutil.which("nmap")
    if located:
        return located
    if sys.platform != "win32":
        return None
    roots = (os.getenv("ProgramFiles"), os.getenv("ProgramFiles(x86)"))
    for root in roots:
        if not root:
            continue
        candidate = os.path.join(root, "Nmap", "nmap.exe")
        if os.path.isfile(candidate):
            return candidate
    return None


def parse_nmap_xml(document: str) -> list[Asset]:
    """Parse Nmap's stable XML format without trusting interactive text output."""
    try:
        root = ET.fromstring(document)
    except ET.ParseError as exc:
        raise RuntimeError("Nmap returned malformed XML") from exc
    assets: list[Asset] = []
    for host in root.findall("host"):
        status_node = host.find("status")
        if status_node is None or status_node.get("state") != "up":
            continue
        ipv4 = host.find("address[@addrtype='ipv4']")
        if ipv4 is None or not ipv4.get("addr"):
            continue
        mac_node = host.find("address[@addrtype='mac']")
        hostname_nodes = host.findall("hostnames/hostname")
        hostnames = [
            {"name": node.get("name", ""), "type": node.get("type", "unknown")}
            for node in hostname_nodes if node.get("name")
        ]
        hostname = hostnames[0]["name"] if hostnames else None
        vendor = mac_node.get("vendor") if mac_node is not None else None
        assets.append(Asset(
            ip=ipv4.get("addr", ""),
            mac=mac_node.get("addr") if mac_node is not None else None,
            hostname=hostname,
            vendor=vendor,
            source="nmap-host-discovery",
            status=status_node.get("state", "unknown"),
            discovery_reason=status_node.get("reason"),
            hostnames=hostnames,
        ))
    return assets


def parse_service_xml(document: str, base_asset: Asset) -> Asset:
    """Merge open TCP ports from one confirmed connect scan into an asset."""
    try:
        root = ET.fromstring(document)
    except ET.ParseError as exc:
        raise RuntimeError("Nmap returned malformed service XML") from exc
    ports: list[int] = []
    services: list[Service] = []
    for port_node in root.findall("host/ports/port"):
        if port_node.get("protocol") != "tcp":
            continue
        state_node = port_node.find("state")
        if state_node is None or state_node.get("state") != "open":
            continue
        try:
            port = int(port_node.get("portid", ""))
        except ValueError:
            continue
        service_node = port_node.find("service")
        name = service_node.get("name", "unknown") if service_node is not None else "unknown"
        ports.append(port)
        services.append(Service(
            port=port,
            transport="tcp",
            name=name,
            product=service_node.get("product") if service_node is not None else None,
            version=service_node.get("version") if service_node is not None else None,
            evidence="Nmap TCP connect scan reported the port open",
            state=state_node.get("state", "unknown"),
            reason=state_node.get("reason"),
            method=service_node.get("method") if service_node is not None else None,
            confidence=(int(service_node.get("conf")) if service_node is not None
                        and service_node.get("conf", "").isdigit() else None),
            extra_info=service_node.get("extrainfo") if service_node is not None else None,
            tunnel=service_node.get("tunnel") if service_node is not None else None,
            cpes=[node.text for node in service_node.findall("cpe") if node.text]
                if service_node is not None else [],
        ))
    return Asset(
        id=base_asset.id,
        ip=base_asset.ip,
        mac=base_asset.mac,
        hostname=base_asset.hostname,
        vendor=base_asset.vendor,
        device_type=base_asset.device_type,
        interfaces=list(base_asset.interfaces),
        ports=sorted(set(base_asset.ports + ports)),
        services=list(base_asset.services) + services,
        protocols=list(base_asset.protocols),
        first_seen=base_asset.first_seen,
        last_seen=utc_now(),
        risk_score=base_asset.risk_score,
        criticality=base_asset.criticality,
        confidence=base_asset.confidence,
        source="nmap-service-verification",
        status=base_asset.status,
        discovery_reason=base_asset.discovery_reason,
        hostnames=list(base_asset.hostnames),
    )


class NmapDiscoveryScanner(Scanner):
    """Level 1 host discovery only: no port scan, scripts, OS detection, or versions."""

    name = "nmap-safe-host-discovery"
    maximum_level = ScanLevel.DISCOVERY

    def __init__(self, target: ipaddress.IPv4Network, max_rate: int = 10) -> None:
        self.target = target
        self.max_rate = max(1, min(max_rate, 20))
        self._process: asyncio.subprocess.Process | None = None

    @staticmethod
    def available() -> bool:
        return find_nmap() is not None

    def cancel(self) -> None:
        if self._process and self._process.returncode is None:
            try:
                self._process.terminate()
            except ProcessLookupError:
                pass

    async def scan(
        self, context: ScanContext, cancellation: CancellationToken
    ) -> AsyncIterator[ScanProgress]:
        cancellation.raise_if_cancelled()
        nmap_binary = find_nmap()
        if not nmap_binary:
            raise RuntimeError("Nmap is required (install package: nmap)")
        arguments = (
            nmap_binary,
            "-sn",
            "--max-rate", str(self.max_rate),
            "--max-retries", "1",
            "--host-timeout", "10s",
            "-oX", "-",
            str(self.target),
        )
        self._process = await asyncio.create_subprocess_exec(
            *arguments,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                self._process.communicate(), timeout=NMAP_TIMEOUT_SECONDS
            )
        except TimeoutError:
            self._process.kill()
            await self._process.communicate()
            raise RuntimeError("Nmap discovery exceeded the three-minute safety timeout") from None
        cancellation.raise_if_cancelled()
        if self._process.returncode != 0:
            message = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(message or "Nmap host discovery failed")
        assets = parse_nmap_xml(stdout.decode("utf-8", errors="replace"))
        total = len(assets)
        for index, asset in enumerate(assets, start=1):
            cancellation.raise_if_cancelled()
            yield ScanProgress(index, total, f"Found host {asset.ip}", asset)


class NmapServiceScanner(Scanner):
    """Confirmed TCP connect scan of Nmap's 20 most common ports on one asset."""

    name = "nmap-safe-service-verification"
    maximum_level = ScanLevel.VERIFY

    def __init__(self, asset: Asset, max_rate: int = 5) -> None:
        self.asset = asset
        self.max_rate = max(1, min(max_rate, 10))
        self._process: asyncio.subprocess.Process | None = None

    @staticmethod
    def available() -> bool:
        return find_nmap() is not None

    def cancel(self) -> None:
        if self._process and self._process.returncode is None:
            try:
                self._process.terminate()
            except ProcessLookupError:
                pass

    async def scan(
        self, context: ScanContext, cancellation: CancellationToken
    ) -> AsyncIterator[ScanProgress]:
        cancellation.raise_if_cancelled()
        nmap_binary = find_nmap()
        if not nmap_binary:
            raise RuntimeError("Nmap is required (install package: nmap)")
        arguments = (
            nmap_binary,
            "-sT",
            "-Pn",
            "-n",
            "--top-ports", "20",
            "--max-rate", str(self.max_rate),
            "--max-retries", "1",
            "--host-timeout", "30s",
            "-oX", "-",
            self.asset.ip,
        )
        self._process = await asyncio.create_subprocess_exec(
            *arguments,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(self._process.communicate(), timeout=60)
        except TimeoutError:
            self._process.kill()
            await self._process.communicate()
            raise RuntimeError("service verification exceeded the one-minute safety timeout") from None
        cancellation.raise_if_cancelled()
        if self._process.returncode != 0:
            message = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(message or "Nmap service verification failed")
        asset = parse_service_xml(stdout.decode("utf-8", errors="replace"), self.asset)
        yield ScanProgress(1, 1, f"Verified services on {asset.ip}", asset)
