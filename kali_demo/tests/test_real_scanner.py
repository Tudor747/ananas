from collections.abc import AsyncIterator
import ipaddress
import tempfile
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

from kali_demo.app import DemoService
from kali_demo.real_scanner import LocalNetwork, parse_nmap_xml, validate_target
from pi_ot_probe.core.models import Asset, ScanLevel, ScanProgress
from pi_ot_probe.scanners.base import CancellationToken, ScanContext, Scanner


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
        self.assertEqual(assets[0].device_type, "router")
        self.assertEqual(assets[0].source, "nmap-host-discovery")

    def test_parser_rejects_malformed_xml(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "malformed"):
            parse_nmap_xml("<broken>")


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


if __name__ == "__main__":
    unittest.main()
