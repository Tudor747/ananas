"""Safety-bounded Nmap host discovery for directly connected private networks."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass
import ipaddress
import json
import shutil
import xml.etree.ElementTree as ET

from pi_ot_probe.core.models import Asset, ScanLevel, ScanProgress
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
        status = host.find("status")
        if status is None or status.get("state") != "up":
            continue
        ipv4 = host.find("address[@addrtype='ipv4']")
        if ipv4 is None or not ipv4.get("addr"):
            continue
        mac_node = host.find("address[@addrtype='mac']")
        hostname_node = host.find("hostnames/hostname")
        hostname = hostname_node.get("name") if hostname_node is not None else None
        vendor = mac_node.get("vendor") if mac_node is not None else None
        device_type = "unknown"
        identity = f"{hostname or ''} {vendor or ''}".lower()
        if any(word in identity for word in ("router", "gateway")):
            device_type = "router"
        elif any(word in identity for word in ("camera", "hikvision", "axis")):
            device_type = "camera"
        assets.append(Asset(
            ip=ipv4.get("addr", ""),
            mac=mac_node.get("addr") if mac_node is not None else None,
            hostname=hostname,
            vendor=vendor,
            device_type=device_type,
            confidence=0.85 if device_type != "unknown" else 0.55,
            source="nmap-host-discovery",
        ))
    return assets


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
    """Read active IPv4 interfaces through iproute2 without transmitting packets."""
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
            try:
                network = ipaddress.ip_network(f"{address}/{prefix}", strict=False)
            except ValueError:
                continue
            if not isinstance(network, ipaddress.IPv4Network) or not _is_rfc1918(network):
                continue
            safe_prefix = max(24, network.prefixlen)
            safe_target = ipaddress.ip_network(f"{address}/{safe_prefix}", strict=False)
            results.append(LocalNetwork(name, address, str(network), str(safe_target)))
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
        return shutil.which("nmap") is not None

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
        nmap_binary = shutil.which("nmap")
        if not nmap_binary:
            raise RuntimeError("Nmap is required (install package: nmap)")
        arguments = (
            nmap_binary,
            "-sn",
            "-n",
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
