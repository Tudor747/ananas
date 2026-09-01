import unittest

from kali_demo.reports import assets_csv, site_report
from kali_demo.wifi_inventory import parse_nmcli, parse_windows_netsh


class WifiParserTests(unittest.TestCase):
    def test_nmcli_parser_preserves_bssid_colons_and_open_network(self) -> None:
        document = "Factory:AA\\:BB\\:CC\\:DD\\:EE\\:FF:80:6:WPA2\nGuest:11\\:22\\:33\\:44\\:55\\:66:50:11:--\n"
        access_points = parse_nmcli(document)
        self.assertEqual(access_points[0].bssid, "AA:BB:CC:DD:EE:FF")
        self.assertEqual(access_points[0].signal_dbm, -60)
        self.assertTrue(access_points[1].suspicious)

    def test_windows_netsh_parser_reads_multiple_bssids(self) -> None:
        document = """SSID 1 : Factory
    Authentication : WPA2-Personal
    BSSID 1 : aa:bb:cc:dd:ee:01
         Signal : 90%
         Channel : 6
    BSSID 2 : aa:bb:cc:dd:ee:02
         Signal : 70%
         Channel : 11
"""
        access_points = parse_windows_netsh(document)
        self.assertEqual(len(access_points), 2)
        self.assertEqual(access_points[1].channel, 11)


class ReportTests(unittest.TestCase):
    def test_reports_contain_asset_and_baseline_sections(self) -> None:
        state = {
            "current_site": "SITE", "mode": "real_discovery",
            "counts": {"assets": 1}, "baseline": {"name": "Approved"},
            "assets": [{"ip": "192.168.1.10", "mac": "AA", "hostname": "host",
                        "vendor": "Vendor", "device_type": "server", "criticality": "normal",
                        "ports": "22", "services": "ssh", "protocols": "", "risk_score": 20,
                        "confidence": .8, "source": "test", "last_seen": "now"}],
            "findings": [], "changes": [], "access_points": [], "scans": [],
        }
        report = site_report(state)
        self.assertEqual(report["site"], "SITE")
        self.assertEqual(report["baseline"]["name"], "Approved")
        csv_document = assets_csv(state)
        self.assertIn("192.168.1.10", csv_document)
        self.assertIn("services", csv_document.splitlines()[0])


if __name__ == "__main__":
    unittest.main()
