import unittest

from pi_ot_probe.simulation.scanner import build_snapshot


class SimulationTests(unittest.TestCase):
    def test_changed_scenario_contains_requested_events(self) -> None:
        snapshot = build_snapshot("changed")
        self.assertEqual(len(snapshot.assets), 5)
        change_types = {change.change_type for change in snapshot.changes}
        self.assertEqual(
            change_types,
            {"new_device", "removed_device", "new_port", "new_wifi_ap"},
        )
        self.assertTrue(any(ap.suspicious and ap.encryption == "OPEN" for ap in snapshot.access_points))
        protocols = {protocol.name for asset in snapshot.assets for protocol in asset.protocols}
        self.assertIn("S7", protocols)
        self.assertIn("Modbus/TCP", protocols)

    def test_unknown_scenario_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_snapshot("unsafe")


if __name__ == "__main__":
    unittest.main()

