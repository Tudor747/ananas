"""Interfaces support for bounded, real local observations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import ipaddress
import json
import shutil
import socket
import sys
from pi_ot_probe.collectors.process import run_command

RFC1918_NETWORKS = tuple(ipaddress.ip_network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


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
        raw = await run_command(
            powershell, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script
        )
        return parse_windows_interface_json(raw)

    ip_binary = shutil.which("ip")
    if not ip_binary:
        raise RuntimeError("iproute2 is required (install package: iproute2)")
    raw = await run_command(ip_binary, "-j", "-4", "addr", "show", "up")
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
