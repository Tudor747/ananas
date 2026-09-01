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
            self.assertIn("/api/reports/site.json", paths)
            self.assertIn("/api/reports/assets.csv", paths)
            self.assertIn("/api/cancel", paths)
            self.assertIn("/api/networks", paths)
            self.assertIn("/api/state", paths)
            self.assertNotIn("/api/simulation/run", paths)
            self.assertNotIn("/api/scan-target", paths)


if __name__ == "__main__":
    unittest.main()
