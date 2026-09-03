from collections.abc import AsyncIterator
import ipaddress
import socket
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from kali_demo.app import DemoService
from kali_demo.real_scanner import (
    LocalNetwork, parse_nmap_xml, parse_service_xml,
    parse_windows_interface_json, validate_target, discover_local_networks,
)
from pi_ot_probe.core.models import Asset, ScanLevel, ScanProgress, Service, WifiAccessPoint
from pi_ot_probe.scanners.base import CancellationToken, ScanContext, Scanner
from kali_demo.web_inspector import WebObservation


NMAP_XML = """<?xml version="1.0"?>
<nmaprun scanner="nmap">
  <host>
    <status state="up" reason="arp-response"/>
    <address addr="192.168.50.1" addrtype="ipv4"/>
    <address addr="AA:BB:CC:DD:EE:01" addrtype="mac" vendor="Router Labs"/>
    <hostnames><hostname name="gateway.local" type="PTR"/></hostnames>
  </host>
  <host>
    <status state="down" reason="no-response"/>
    <address addr="192.168.50.2" addrtype="ipv4"/>
  </host>
  <host>
    <status state="up" reason="echo-reply"/>
    <address addr="192.168.50.20" addrtype="ipv4"/>
  </host>
</nmaprun>"""

SERVICE_XML = """<?xml version="1.0"?>
<nmaprun><host><status state="up"/><ports>
  <port protocol="tcp" portid="22"><state state="open"/><service name="ssh"/></port>
  <port protocol="tcp" portid="80"><state state="closed"/><service name="http"/></port>
  <port protocol="tcp" portid="443"><state state="open"/><service name="https"/></port>
</ports></host></nmaprun>"""


class TargetValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.local = [LocalNetwork("eth0", "192.168.50.10", "192.168.48.0/20", "192.168.50.0/24")]

    def test_accepts_small_attached_private_network(self) -> None:
        target = validate_target("192.168.50.0/24", self.local)
        self.assertEqual(target, ipaddress.ip_network("192.168.50.0/24"))

    def test_rejects_public_unattached_and_large_targets(self) -> None:
        for target in ("8.8.8.0/24", "192.168.80.0/24", "192.168.48.0/20"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                validate_target(target, self.local)

    def test_rejects_noncanonical_target(self) -> None:
        with self.assertRaisesRegex(ValueError, "canonical"):
            validate_target("192.168.50.3/24", self.local)


class NmapXmlTests(unittest.TestCase):
    def test_parser_returns_only_up_hosts(self) -> None:
        assets = parse_nmap_xml(NMAP_XML)
        self.assertEqual([asset.ip for asset in assets], ["192.168.50.1", "192.168.50.20"])
        self.assertEqual(assets[0].mac, "AA:BB:CC:DD:EE:01")
        self.assertEqual(assets[0].vendor, "Router Labs")
        self.assertEqual(assets[0].hostname, "gateway.local")
        self.assertEqual(assets[0].hostnames, [{"name": "gateway.local", "type": "PTR"}])
        self.assertEqual(assets[0].discovery_reason, "arp-response")
        self.assertEqual(assets[0].source, "nmap-host-discovery")

    def test_parser_rejects_malformed_xml(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "malformed"):
            parse_nmap_xml("<broken>")

    def test_service_parser_keeps_only_open_tcp_ports(self) -> None:
        asset = parse_service_xml(SERVICE_XML, Asset(ip="192.168.50.20", ports=[502]))
        self.assertEqual(asset.ports, [22, 443, 502])
        self.assertEqual([service.name for service in asset.services], ["ssh", "https"])
        self.assertEqual(asset.source, "nmap-service-verification")


class WindowsInterfaceTests(unittest.TestCase):
    def test_powershell_json_creates_safe_private_targets(self) -> None:
        document = """[
          {"InterfaceAlias":"Ethernet","IPAddress":"192.168.7.24","PrefixLength":24},
          {"InterfaceAlias":"VPN","IPAddress":"10.20.33.4","PrefixLength":16},
          {"InterfaceAlias":"Public","IPAddress":"203.0.113.4","PrefixLength":24}
        ]"""
        networks = parse_windows_interface_json(document)
        self.assertEqual([item.safe_target for item in networks], ["192.168.7.0/24", "10.20.33.0/24"])


class CrossPlatformInterfaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_psutil_adapter_needs_no_privileged_platform_command(self) -> None:
        fake_psutil = SimpleNamespace(
            net_if_stats=lambda: {"Ethernet": SimpleNamespace(isup=True)},
            net_if_addrs=lambda: {"Ethernet": [SimpleNamespace(
                family=socket.AF_INET, address="192.168.9.15", netmask="255.255.255.0"
            )]},
        )
        with patch.dict("sys.modules", {"psutil": fake_psutil}):
            networks = await discover_local_networks()
        self.assertEqual(networks[0].safe_target, "192.168.9.0/24")


class FakeNmapScanner(Scanner):
    name = "fake-nmap"
    maximum_level = ScanLevel.DISCOVERY

    def __init__(self, target: ipaddress.IPv4Network) -> None:
        self.target = target

    @staticmethod
    def available() -> bool:
        return True

    def cancel(self) -> None:
        return None

    async def scan(
        self, context: ScanContext, cancellation: CancellationToken
    ) -> AsyncIterator[ScanProgress]:
        yield ScanProgress(1, 1, "Found host", Asset(
            ip="192.168.50.1", mac="AA:BB:CC:DD:EE:01", source="nmap-host-discovery"
        ))


class FakeServiceScanner(Scanner):
    name = "fake-service"
    maximum_level = ScanLevel.VERIFY

    def __init__(self, asset: Asset) -> None:
        self.asset = asset

    def cancel(self) -> None:
        return None

    async def scan(
        self, context: ScanContext, cancellation: CancellationToken
    ) -> AsyncIterator[ScanProgress]:
        self.asset.ports = [23]
        self.asset.services = [Service(23, name="telnet")]
        yield ScanProgress(1, 1, "Verified", self.asset)


class RealDiscoveryServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_discovery_requires_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = DemoService(Path(directory) / "demo.db")
            with self.assertRaises(PermissionError):
                await service.run_real("192.168.50.0/24", False)

    async def test_real_discovery_persists_non_simulated_scan(self) -> None:
        local = [LocalNetwork("eth0", "192.168.50.10", "192.168.50.0/24", "192.168.50.0/24")]
        with tempfile.TemporaryDirectory() as directory:
            service = DemoService(Path(directory) / "demo.db")
            with (
                patch("kali_demo.app.discover_local_networks", new=AsyncMock(return_value=local)),
                patch("kali_demo.app.NmapDiscoveryScanner", FakeNmapScanner),
            ):
                result = await service.run_real("192.168.50.0/24", True)
            state = service.state()

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["assets"], 1)
            self.assertEqual(state["mode"], "real_discovery")
            self.assertTrue(state["network_traffic"])
            self.assertEqual(state["assets"][0]["source"], "nmap-host-discovery")
            self.assertEqual(state["counts"]["audit_log"], 1)

    async def test_service_verification_is_single_host_and_keeps_raw_observation(self) -> None:
        local = [LocalNetwork("eth0", "192.168.50.10", "192.168.50.0/24", "192.168.50.0/24")]
        with tempfile.TemporaryDirectory() as directory:
            service = DemoService(Path(directory) / "demo.db")
            with (
                patch("kali_demo.app.discover_local_networks", new=AsyncMock(return_value=local)),
                patch("kali_demo.app.NmapDiscoveryScanner", FakeNmapScanner),
            ):
                await service.run_real("192.168.50.0/24", True)
            with (
                patch("kali_demo.app.discover_local_networks", new=AsyncMock(return_value=local)),
                patch("kali_demo.app.NmapServiceScanner", FakeServiceScanner),
            ):
                result = await service.verify_services("192.168.50.1", True)
            state = service.state()

            self.assertEqual(result["open_ports"], [23])
            self.assertEqual(state["assets"][0]["ports"][0]["port"], 23)
            self.assertEqual(state["assets"][0]["services"][0]["name"], "telnet")
            self.assertNotIn("findings", state)

    async def test_wifi_refresh_persists_aps_and_compares_with_baseline(self) -> None:
        local = [LocalNetwork("eth0", "192.168.50.10", "192.168.50.0/24", "192.168.50.0/24")]
        with tempfile.TemporaryDirectory() as directory:
            service = DemoService(Path(directory) / "demo.db")
            with (
                patch("kali_demo.app.discover_local_networks", new=AsyncMock(return_value=local)),
                patch("kali_demo.app.NmapDiscoveryScanner", FakeNmapScanner),
            ):
                await service.run_real("192.168.50.0/24", True)
            service.create_baseline("Before Wi-Fi")
            access_point = WifiAccessPoint("Factory", "AA:BB:CC:DD:EE:FF", -45, 6, "WPA2")
            with patch("kali_demo.app.discover_wifi", new=AsyncMock(return_value=[access_point])):
                result = await service.refresh_wifi(True)
            state = service.state()

            self.assertEqual(result, {"access_points": 1, "changes": 1})
            self.assertEqual(len(state["access_points"]), 1)
            self.assertEqual(state["changes"][0]["change_type"], "new_wifi_ap")

    async def test_web_inspection_requires_an_observed_port_and_stores_raw_headers(self) -> None:
        local = [LocalNetwork("eth0", "192.168.50.10", "192.168.50.0/24", "192.168.50.0/24")]
        with tempfile.TemporaryDirectory() as directory:
            service = DemoService(Path(directory) / "demo.db")
            with (
                patch("kali_demo.app.discover_local_networks", new=AsyncMock(return_value=local)),
                patch("kali_demo.app.NmapDiscoveryScanner", FakeNmapScanner),
            ):
                await service.run_real("192.168.50.0/24", True)
            with (
                patch("kali_demo.app.discover_local_networks", new=AsyncMock(return_value=local)),
                patch("kali_demo.app.NmapServiceScanner", FakeServiceScanner),
            ):
                await service.verify_services("192.168.50.1", True)
            observation = WebObservation(
                "http", "192.168.50.1", 23, "/", 200, "OK", "HTTP/1.1",
                [{"name": "Server", "value": "test"}],
            )
            with (
                patch("kali_demo.app.discover_local_networks", new=AsyncMock(return_value=local)),
                patch("kali_demo.app.inspect_website", new=AsyncMock(return_value=observation)),
            ):
                result = await service.inspect_web("192.168.50.1", 23, "http", True)
            state = service.state()

            self.assertEqual(result["status_code"], 200)
            self.assertEqual(
                state["assets"][0]["web_observations"][0]["headers"][0]["name"], "Server"
            )
            with self.assertRaises(ValueError):
                await service.inspect_web("192.168.50.1", 80, "http", True)


if __name__ == "__main__":
    unittest.main()
