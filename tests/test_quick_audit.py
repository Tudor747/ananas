import asyncio
import tempfile
from pathlib import Path
import unittest

from pi_ot_probe.core.models import Scan, ScanLevel, ScanProfile, ScanStatus
from pi_ot_probe.database.repository import Repository
from pi_ot_probe.scanners.base import CancellationToken
from pi_ot_probe.scanners.orchestrator import ScanOrchestrator
from pi_ot_probe.simulation.scanner import SimulationScanner


class QuickAuditTests(unittest.IsolatedAsyncioTestCase):
    async def test_quick_audit_persists_assets_findings_artifacts_and_audit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Repository(Path(directory) / "probe.db")
            scan = Scan(
                site="FACTORY_A",
                level=ScanLevel.DISCOVERY,
                profile=ScanProfile.INDUSTRIAL,
                target="simulation://test",
                simulation=True,
            )
            outcome = await ScanOrchestrator(repository).run(
                scan=scan,
                scanner=SimulationScanner("changed", delay_seconds=0),
                cancellation=CancellationToken(),
            )
            self.assertEqual(outcome.scan.status, ScanStatus.COMPLETED)
            self.assertEqual(len(outcome.assets), 5)
            self.assertEqual(len(outcome.findings), 2)
            self.assertEqual(repository.counts(), {
                "sites": 1, "scans": 1, "assets": 5, "findings": 2, "audit_log": 1,
            })
            with repository.connect() as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM changes").fetchone()[0], 4)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM wifi_access_points").fetchone()[0], 2)

    async def test_pre_cancelled_scan_finishes_as_cancelled_and_is_audited(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Repository(Path(directory) / "probe.db")
            token = CancellationToken()
            token.cancel()
            scan = Scan(
                site="FACTORY_A",
                level=ScanLevel.DISCOVERY,
                profile=ScanProfile.INDUSTRIAL,
                target="simulation://test",
                simulation=True,
            )
            outcome = await ScanOrchestrator(repository).run(
                scan=scan,
                scanner=SimulationScanner(delay_seconds=0),
                cancellation=token,
            )
            self.assertEqual(outcome.scan.status, ScanStatus.CANCELLED)
            self.assertTrue(outcome.scan.cancelled)
            self.assertEqual(repository.counts()["audit_log"], 1)

    async def test_task_cancellation_is_persisted_before_propagation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Repository(Path(directory) / "probe.db")
            scan = Scan(
                site="FACTORY_A",
                level=ScanLevel.DISCOVERY,
                profile=ScanProfile.INDUSTRIAL,
                target="simulation://test",
                simulation=True,
            )
            task = asyncio.create_task(ScanOrchestrator(repository).run(
                scan=scan,
                scanner=SimulationScanner(delay_seconds=1),
                cancellation=CancellationToken(),
            ))
            await asyncio.sleep(0.01)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertEqual(scan.status, ScanStatus.CANCELLED)
            self.assertTrue(scan.cancelled)
            self.assertEqual(repository.counts()["audit_log"], 1)


if __name__ == "__main__":
    unittest.main()
