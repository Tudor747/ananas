from collections.abc import AsyncIterator
import tempfile
from pathlib import Path
import unittest

from pi_ot_probe.core.models import Scan, ScanLevel, ScanProfile, ScanProgress
from pi_ot_probe.database.repository import Repository
from pi_ot_probe.plugins.base import PluginMetadata, SecurityPlugin
from pi_ot_probe.plugins.registry import PluginRegistry
from pi_ot_probe.scanners.base import CancellationToken, ScanContext, Scanner
from pi_ot_probe.scanners.orchestrator import ScanOrchestrator


class ActiveScanner(Scanner):
    name = "test-active"
    maximum_level = ScanLevel.ACTIVE_TEST

    async def scan(
        self, context: ScanContext, cancellation: CancellationToken
    ) -> AsyncIterator[ScanProgress]:
        if False:
            yield ScanProgress(0, 0, "")


class TestPlugin(SecurityPlugin):
    metadata = PluginMetadata("safe-test", "test", None, ScanLevel.PASSIVE, True, False)


class SafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_active_scan_requires_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            orchestrator = ScanOrchestrator(Repository(Path(directory) / "probe.db"))
            scan = Scan("SITE", ScanLevel.ACTIVE_TEST, ScanProfile.OFFICE, "192.0.2.1")
            with self.assertRaises(PermissionError):
                await orchestrator.run(
                    scan=scan, scanner=ActiveScanner(), cancellation=CancellationToken()
                )

    async def test_active_scan_rejects_network_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            orchestrator = ScanOrchestrator(Repository(Path(directory) / "probe.db"))
            scan = Scan(
                "SITE", ScanLevel.ACTIVE_TEST, ScanProfile.OFFICE, "192.0.2.0/24",
                authorized=True,
            )
            with self.assertRaisesRegex(ValueError, "one explicitly selected host"):
                await orchestrator.run(
                    scan=scan, scanner=ActiveScanner(), cancellation=CancellationToken()
                )


class PluginRegistryTests(unittest.TestCase):
    def test_duplicate_plugin_name_is_rejected(self) -> None:
        registry = PluginRegistry()
        registry.register(TestPlugin())
        with self.assertRaises(ValueError):
            registry.register(TestPlugin())


if __name__ == "__main__":
    unittest.main()
