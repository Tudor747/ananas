import unittest
import tempfile
from pathlib import Path

from kali_demo.app import create_app


class DemoAppTests(unittest.TestCase):
    def test_app_exposes_only_bounded_discovery_routes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            application = create_app(Path(directory) / "demo.db")
            paths = {route.path for route in application.routes}
            self.assertIn("/api/real/run", paths)
            self.assertIn("/api/real/verify", paths)
            self.assertIn("/api/baseline", paths)
            self.assertIn("/api/wifi/refresh", paths)
            self.assertIn("/api/real/web", paths)
            self.assertIn("/api/reports/site.json", paths)
            self.assertIn("/api/reports/assets.csv", paths)
            self.assertIn("/api/cancel", paths)
            self.assertIn("/api/networks", paths)
            self.assertIn("/api/state", paths)
            self.assertIn("/api/validation/scenarios", paths)
            self.assertIn("/api/changes/{change_id}/triage", paths)
            self.assertNotIn("/api/simulation/run", paths)
            self.assertNotIn("/api/scan-target", paths)

    def test_dashboard_contains_analyst_workspaces(self) -> None:
        static = Path(__file__).resolve().parents[1] / "static" / "index.html"
        document = static.read_text(encoding="utf-8")
        self.assertIn('data-tab="change-review"', document)
        self.assertIn('data-tab="validation"', document)
        self.assertIn('id="tab-evidence"', document)
        self.assertIn("Change Review", document)
        self.assertIn("Validation Lab", document)
        self.assertNotIn("severity", document.lower())

    def test_frontend_is_split_into_editable_modules(self) -> None:
        static = Path(__file__).resolve().parents[1] / "static"
        document = (static / "index.html").read_text(encoding="utf-8")
        self.assertIn('type="module"', document)
        for module in ("app.js", "api.js", "dom.js", "renderers.js"):
            self.assertTrue((static / module).is_file(), module)


if __name__ == "__main__":
    unittest.main()
