"""Assessment conclusions stay within evidence and reviews follow its revision."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from pi_ot_probe.application.assessment import build_assessment
from pi_ot_probe.application.instruments import InstrumentWorkspace
from pi_ot_probe.database.repository import Repository
from pi_ot_probe.domain.models import utc_now
from pi_ot_probe.reports.assessment import assessment_markdown


def observed_state():
    return {
        "current_site": "Office", "access_points": [],
        "assets": [{"ip": "192.168.50.10", "ports": [
            {"port": 23, "observed_at": "2026-01-01T00:00:00+00:00"},
            {"port": 3389, "observed_at": "2026-01-01T00:00:00+00:00"},
        ], "services_checked_at": "2026-01-01T00:00:00+00:00",
            "verification_scan_id": "scan-one", "web_observations": []}],
    }


class AssessmentEvidenceTests(unittest.TestCase):
    def test_port_numbers_produce_review_leads_not_vulnerability_claims(self):
        report = build_assessment(observed_state(), [])
        self.assertEqual(len(report["findings"]), 2)
        telnet, rdp = report["findings"]
        self.assertIn("Possible", telnet["title"])
        self.assertIn("does not identify", telnet["implication"])
        self.assertIn("unknown", rdp["implication"])
        self.assertEqual(telnet["evidence"]["scan_id"], "scan-one")
        self.assertNotIn("risk_score", telnet)
        self.assertTrue(all(item["recommendation"] for item in report["findings"]))

    def test_empty_or_clean_inventory_never_reports_a_clean_bill_of_health(self):
        report = build_assessment({"current_site": None, "assets": []}, [])
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["coverage"][0]["status"], "not assessed")
        self.assertIn("does not mean secure", report["limitations"])
        state = observed_state()
        state["assets"][0]["ports"] = []
        report = build_assessment(state, [])
        self.assertIn("1 of 1", report["coverage"][1]["detail"])
        self.assertEqual(report["coverage"][1]["status"], "partial")

    def test_wifi_does_not_assign_ownership_or_flag_wpa_and_owe_as_open(self):
        state = {"assets": [], "access_points": [
            {"ssid": "Nearby", "bssid": "AA", "authentication": "Open", "encryption": "None"},
            {"ssid": "Protected", "bssid": "BB", "authentication": "WPA2-Personal", "cipher": "None"},
            {"ssid": "Enhanced", "bssid": "CC", "authentication": "Open OWE", "cipher": "None"},
            {"ssid": "Legacy", "bssid": "DD", "encryption": "WEP"},
        ]}
        findings = build_assessment(state, [])["findings"]
        self.assertEqual({item["rule"] for item in findings}, {"wifi-open", "wifi-wep"})
        self.assertTrue(all("Ownership" in item["implication"] for item in findings))

    def test_latest_web_observation_only_and_no_certificate_trust_inference(self):
        state = observed_state()
        state["assets"][0]["ports"] = []
        state["assets"][0]["web_observations"] = [
            {"id": 2, "scheme": "http", "port": 80, "status_code": 301},
            {"id": 1, "scheme": "http", "port": 80, "status_code": 200},
            {"id": 3, "scheme": "https", "port": 443, "tls": {"protocol": "TLSv1.3", "certificate_validation": "not performed"}},
        ]
        report = build_assessment(state, [])
        self.assertEqual(len(report["findings"]), 1)
        self.assertEqual(report["findings"][0]["evidence"]["id"], 2)
        self.assertIn("redirect", report["findings"][0]["implication"])
        state["assets"][0]["web_observations"][2]["tls"]["protocol"] = "TLSv1.1"
        self.assertIn("legacy-tls", {item["rule"] for item in build_assessment(state, [])["findings"]})

    def test_markdown_escapes_operator_text_and_retains_coverage(self):
        report = build_assessment(observed_state(), [])
        report["findings"][0]["title"] = "<script>alert(1)</script> [link](https://example.org)"
        report["findings"][0]["evidence"]["untrusted"] = "```\n# forged heading"
        document = assessment_markdown(report)
        self.assertNotIn("<script>", document)
        self.assertNotIn("[link](https://example.org)", document)
        self.assertIn("````json", document)
        self.assertIn("Assessment coverage", document)
        self.assertIn("Improvement:", document)


class InstrumentPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.repository = Repository(Path(self.directory.name) / "test.db")
        self.workspace = InstrumentWorkspace(self.repository)
        self.instrument = self.workspace.register("ESP A", "ESP32 / unknown", "BWifiKill / unknown", "Two antennas")
        self.repository.ensure_site("Office", utc_now())
        self.repository.ensure_site("Other site", utc_now())

    def record(self, **overrides):
        values = {
            "site": "Office", "instrument_id": self.instrument["id"], "category": "wifi",
            "title": "Manual survey", "subject": "AA:BB:CC:DD:EE:FF", "location": "Reception",
            "evidence": "Operator recorded channel and signal from the ESP display.",
            "recommendation": "Confirm this AP belongs to the site.",
            "observed_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
        }
        return self.workspace.record(**(values | overrides))

    def test_unknown_hardware_is_supported_without_claiming_connection(self):
        self.assertEqual(self.instrument["connection_status"], "not verified")
        self.assertEqual(self.instrument["integration"], "manual")
        with self.assertRaises(ValueError):
            self.workspace.register("ESP A", "unknown", "unknown", "")

    def test_field_evidence_is_persistent_manual_and_site_scoped(self):
        recorded = self.record()
        self.assertEqual(recorded["instrument_name"], "ESP A")
        self.assertEqual(self.workspace.observations("Other site"), [])
        reopened = InstrumentWorkspace(Repository(self.repository.database_path))
        report = reopened.assessment({"current_site": "Office", "assets": []})
        self.assertEqual(len(report["findings"]), 1)
        self.assertEqual(report["findings"][0]["basis"], "manual observation")
        self.assertEqual(report["findings"][0]["evidence"]["location"], "Reception")

    def test_invalid_observations_do_not_persist(self):
        for override in (
            {"site": "missing"}, {"instrument_id": 999}, {"category": "invalid"},
            {"evidence": "   "}, {"observed_at": datetime(2025, 1, 1)},
            {"observed_at": utc_now() + timedelta(days=1)},
        ):
            with self.subTest(override=override), self.assertRaises(ValueError):
                self.record(**override)
        self.assertEqual(self.workspace.observations("Office"), [])

    def test_reviews_are_bound_to_site_and_evidence_revision(self):
        state = observed_state()
        finding_id = self.workspace.assessment(state)["findings"][0]["id"]
        with self.assertRaises(ValueError):
            self.workspace.review(state, finding_id, "remediated", "")
        self.workspace.review(state, finding_id, "investigating", "Service owner contacted")
        self.assertEqual(self.workspace.assessment(state)["findings"][0]["status"], "investigating")
        other = deepcopy(state)
        other["current_site"] = "Other site"
        self.assertEqual(self.workspace.assessment(other)["findings"][0]["status"], "new")
        newer = deepcopy(state)
        newer["assets"][0]["verification_scan_id"] = "scan-two"
        self.assertEqual(self.workspace.assessment(newer)["findings"][0]["status"], "new")
        with self.assertRaises(ValueError):
            self.workspace.review(newer, finding_id, "reviewed", "Old evidence")
