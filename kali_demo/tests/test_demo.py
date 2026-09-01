import tempfile
from pathlib import Path
import unittest

from kali_demo.app import DemoService, create_app


class DemoServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_changed_demo_exercises_the_full_offline_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = DemoService(Path(directory) / "demo.db")
            result = await service.run("changed")
            state = service.state()

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["assets"], 5)
            self.assertEqual(result["findings"], 2)
            self.assertFalse(state["network_traffic"])
            self.assertEqual(state["mode"], "simulation")
            self.assertEqual(len(state["assets"]), 5)
            self.assertEqual(len(state["changes"]), 4)
            self.assertEqual(len(state["access_points"]), 2)
            self.assertTrue(any(asset["protocols"] == "S7" for asset in state["assets"]))
            self.assertTrue(any(ap["encryption"] == "OPEN" for ap in state["access_points"]))
            self.assertEqual(state["counts"]["audit_log"], 1)

    async def test_baseline_scenario_has_no_synthetic_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = DemoService(Path(directory) / "demo.db")
            result = await service.run("baseline")
            state = service.state()

            self.assertEqual(result["assets"], 4)
            self.assertEqual(state["changes"], [])
            self.assertEqual(len(state["access_points"]), 1)

    async def test_switching_scenarios_shows_the_selected_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = DemoService(Path(directory) / "demo.db")
            await service.run("changed")
            await service.run("baseline")
            state = service.state()

            self.assertEqual(state["current_site"], "KALI_DEMO_BASELINE")
            self.assertEqual(len(state["assets"]), 4)
            self.assertEqual(state["changes"], [])
            self.assertEqual(len(state["scans"]), 2)

    async def test_unknown_scenario_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = DemoService(Path(directory) / "demo.db")
            with self.assertRaises(ValueError):
                await service.run("real-network")


class DemoAppTests(unittest.TestCase):
    def test_app_exposes_only_fixed_demo_routes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            application = create_app(Path(directory) / "demo.db")
            paths = {route.path for route in application.routes}
            self.assertIn("/api/run", paths)
            self.assertIn("/api/state", paths)
            self.assertNotIn("/api/scan-target", paths)


if __name__ == "__main__":
    unittest.main()
