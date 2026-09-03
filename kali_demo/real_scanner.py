"""Safety-bounded Nmap host discovery for directly connected private networks."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass
import ipaddress
import json
import os
import shutil
import socket
import sys
import xml.etree.ElementTree as ET

from pi_ot_probe.core.models import Asset, ScanLevel, ScanProgress, Service, utc_now
from pi_ot_probe.scanners.base import CancellationToken, ScanContext, Scanner


RFC1918_NETWORKS = tuple(
    ipaddress.ip_network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)
MAX_TARGET_ADDRESSES = 256
NMAP_TIMEOUT_SECONDS = 180


@dataclass(frozen=True, slots=True)
class LocalNetwork:
    interface: str
    address: str
    network: str
    safe_target: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _is_rfc1918(network: ipaddress.IPv4Network) -> bool:
    return any(network.subnet_of(private) for private in RFC1918_NETWORKS)


def _local_network(interface: str, address: str, prefix: int) -> LocalNetwork | None:
    try:
        network = ipaddress.ip_network(f"{address}/{prefix}", strict=False)
    except ValueError:
        return None
    if not isinstance(network, ipaddress.IPv4Network) or not _is_rfc1918(network):
        return None
    safe_prefix = max(24, network.prefixlen)
    safe_target = ipaddress.ip_network(f"{address}/{safe_prefix}", strict=False)
    return LocalNetwork(interface, address, str(network), str(safe_target))


def parse_windows_interface_json(document: str) -> list[LocalNetwork]:
    """Convert fixed-property Get-NetIPAddress JSON into local network choices."""
    try:
        decoded = json.loads(document)
    except json.JSONDecodeError as exc:
        raise RuntimeError("could not parse Windows interface output") from exc
    entries = decoded if isinstance(decoded, list) else [decoded]
    results: list[LocalNetwork] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        try:
            prefix = int(entry.get("PrefixLength", 32))
        except (TypeError, ValueError):
            continue
        item = _local_network(
            str(entry.get("InterfaceAlias", "")),
            str(entry.get("IPAddress", "")),
            prefix,
        )
        if item:
            results.append(item)
    return results


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


def validate_target(target: str, local_networks: list[LocalNetwork]) -> ipaddress.IPv4Network:
    """Require a small RFC1918 subnet contained in an active local interface."""
    try:
        network = ipaddress.ip_network(target, strict=True)
    except ValueError as exc:
        raise ValueError("target must be a canonical IPv4 network such as 192.168.1.0/24") from exc
    if not isinstance(network, ipaddress.IPv4Network):
        raise ValueError("only IPv4 discovery is currently supported")
    if not _is_rfc1918(network):
        raise ValueError("target must be an RFC1918 private network")
    if network.num_addresses > MAX_TARGET_ADDRESSES:
        raise ValueError("target is too large; select a /24 or smaller network")
    active_networks = [ipaddress.ip_network(item.network) for item in local_networks]
    if not any(network.subnet_of(active) for active in active_networks):
        raise ValueError("target must belong to an active local interface")
    return network


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


async def _run_command(*arguments: str, timeout: float = 15) -> str:
    process = await asyncio.create_subprocess_exec(
        *arguments,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError:
        process.kill()
        await process.communicate()
        raise RuntimeError(f"command timed out: {arguments[0]}") from None
    if process.returncode != 0:
        message = stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(message or f"command failed: {arguments[0]}")
    return stdout.decode("utf-8", errors="replace")


async def discover_local_networks() -> list[LocalNetwork]:
    """Read active IPv4 interfaces locally without transmitting packets."""
    try:
        import psutil
    except ImportError:
        psutil = None
    if psutil is not None:
        results: list[LocalNetwork] = []
        stats = psutil.net_if_stats()
        for name, addresses in psutil.net_if_addrs().items():
            if name in stats and not stats[name].isup:
                continue
            for address_info in addresses:
                if address_info.family != socket.AF_INET or address_info.address == "127.0.0.1":
                    continue
                try:
                    prefix = ipaddress.ip_network(f"0.0.0.0/{address_info.netmask}").prefixlen
                except ValueError:
                    continue
                item = _local_network(name, address_info.address, prefix)
                if item and item not in results:
                    results.append(item)
        return results

    if sys.platform == "win32":
        powershell = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
        if not powershell:
            raise RuntimeError("Windows PowerShell is required for interface discovery")
        script = (
            "$ErrorActionPreference='Stop'; "
            "@(Get-NetIPAddress -AddressFamily IPv4 -AddressState Preferred | "
            "Where-Object { $_.IPAddress -ne '127.0.0.1' -and -not $_.SkipAsSource } | "
            "Select-Object InterfaceAlias,IPAddress,PrefixLength) | ConvertTo-Json -Compress"
        )
        raw = await _run_command(
            powershell, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script
        )
        return parse_windows_interface_json(raw)

    ip_binary = shutil.which("ip")
    if not ip_binary:
        raise RuntimeError("iproute2 is required (install package: iproute2)")
    raw = await _run_command(ip_binary, "-j", "-4", "addr", "show", "up")
    try:
        interfaces = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("could not parse iproute2 interface output") from exc
    results: list[LocalNetwork] = []
    for interface in interfaces:
        name = str(interface.get("ifname", ""))
        if name == "lo":
            continue
        for address_info in interface.get("addr_info", []):
            if address_info.get("family") != "inet" or address_info.get("scope") != "global":
                continue
            address = str(address_info.get("local", ""))
            prefix = int(address_info.get("prefixlen", 32))
            item = _local_network(name, address, prefix)
            if item:
                results.append(item)
    return results


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
