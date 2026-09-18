from collections.abc import AsyncIterator
import tempfile
from pathlib import Path
import unittest

from kali_demo.baseline import BaselineManager
from pi_ot_probe.core.models import Asset, Scan, ScanLevel, ScanProfile, ScanProgress
from pi_ot_probe.database.repository import Repository
from pi_ot_probe.scanners.base import CancellationToken, ScanCancelled, ScanContext, Scanner
from pi_ot_probe.scanners.orchestrator import ScanOrchestrator


class AssetScanner(Scanner):
    name = "baseline-fixture"
    maximum_level = ScanLevel.DISCOVERY

    def __init__(self, assets: list[Asset]) -> None:
        self.assets = assets

    async def scan(
        self, context: ScanContext, cancellation: CancellationToken
    ) -> AsyncIterator[ScanProgress]:
        for index, asset in enumerate(self.assets, start=1):
            yield ScanProgress(index, len(self.assets), "fixture", asset)


class CancelledScanner(Scanner):
    name = "cancelled-fixture"
    maximum_level = ScanLevel.DISCOVERY

    async def scan(
        self, context: ScanContext, cancellation: CancellationToken
    ) -> AsyncIterator[ScanProgress]:
        raise ScanCancelled("cancelled for test")
        yield


async def run_discovery(repository: Repository, assets: list[Asset]) -> Scan:
    scan = Scan(
        site="TEST_SITE", level=ScanLevel.DISCOVERY, profile=ScanProfile.INDUSTRIAL,
        target="192.168.1.0/24", authorized=True,
    )
    await ScanOrchestrator(repository).run(
        scan=scan, scanner=AssetScanner(assets), cancellation=CancellationToken()
    )
    return scan


class BaselineTests(unittest.IsolatedAsyncioTestCase):
    async def test_reassigned_ip_does_not_steal_a_mac_match(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Repository(Path(directory) / "baseline.db")
            manager = BaselineManager(repository)
            await run_discovery(repository, [
                Asset(ip="192.168.1.10", mac="AA:00:00:00:00:10"),
                Asset(ip="192.168.1.20", mac="AA:00:00:00:00:20"),
            ])
            manager.create("TEST_SITE", "Before DHCP changes")
            later = await run_discovery(repository, [
                Asset(ip="192.168.1.10", mac="aa:00:00:00:00:20"),
            ])
            changes = manager.compare("TEST_SITE", later.id)
            self.assertEqual([item["change_type"] for item in changes],
                             ["device_removed", "mac_ip_changed"])
            self.assertEqual(changes[1]["previous_ip"], "192.168.1.20")
            self.assertEqual(changes[1]["current_ip"], "192.168.1.10")

    async def test_missing_mac_is_not_reported_as_identity_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Repository(Path(directory) / "baseline.db")
            manager = BaselineManager(repository)
            await run_discovery(repository, [Asset(ip="192.168.1.10", mac="AA:00:00:00:00:10")])
            manager.create("TEST_SITE", "Before")
            later = await run_discovery(repository, [Asset(ip="192.168.1.10")])
            self.assertEqual(manager.compare("TEST_SITE", later.id), [])

    async def test_comparison_finds_new_removed_device_and_new_port(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Repository(Path(directory) / "baseline.db")
            manager = BaselineManager(repository)
            await run_discovery(repository, [
                Asset(ip="192.168.1.10", mac="AA:00:00:00:00:10", ports=[22]),
                Asset(ip="192.168.1.20", mac="AA:00:00:00:00:20"),
            ])
            created = manager.create("TEST_SITE", "Factory approved")
            self.assertEqual(created["assets"], 2)

            later = await run_discovery(repository, [
                Asset(ip="192.168.1.10", mac="AA:00:00:00:00:10", ports=[22, 80]),
                Asset(ip="192.168.1.30", mac="AA:00:00:00:00:30"),
            ])
            changes = manager.compare("TEST_SITE", later.id)
            change_types = {change["change_type"] for change in changes}
            self.assertEqual(change_types, {"new_device", "device_removed", "new_port"})
            status = manager.status("TEST_SITE")
            self.assertIsNotNone(status)
            self.assertEqual(status["assets"], 2)

            with repository.connect() as connection:
                change_id = int(connection.execute(
                    "SELECT id FROM changes WHERE scan_id=? LIMIT 1", (later.id,)
                ).fetchone()[0])
            self.assertTrue(manager.acknowledge("TEST_SITE", change_id))
            manager.compare("TEST_SITE", later.id)
            with repository.connect() as connection:
                self.assertEqual(connection.execute(
                    "SELECT COUNT(*) FROM changes WHERE scan_id=?", (later.id,)
                ).fetchone()[0], 3)
                self.assertIsNotNone(connection.execute(
                    "SELECT acknowledged_at FROM changes WHERE id=?", (change_id,)
                ).fetchone()[0])

    async def test_cancelled_scan_never_creates_removal_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Repository(Path(directory) / "baseline.db")
            manager = BaselineManager(repository)
            await run_discovery(repository, [Asset(ip="192.168.1.10")])
            manager.create("TEST_SITE", "Approved")
            cancelled = Scan(
                site="TEST_SITE", level=ScanLevel.DISCOVERY,
                profile=ScanProfile.INDUSTRIAL, target="192.168.1.0/24", authorized=True,
            )
            outcome = await ScanOrchestrator(repository).run(
                scan=cancelled, scanner=CancelledScanner(), cancellation=CancellationToken()
            )
            self.assertTrue(outcome.scan.cancelled)
            self.assertEqual(manager.compare("TEST_SITE", cancelled.id), [])
            with repository.connect() as connection:
                self.assertEqual(connection.execute(
                    "SELECT COUNT(*) FROM changes WHERE scan_id=?", (cancelled.id,)
                ).fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
