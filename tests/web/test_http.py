"""Exercise the assembled website over real loopback HTTP after layout changes."""
import json
from pathlib import Path
import re
import socket
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

import uvicorn

from pi_ot_probe.web.app import create_app
from pi_ot_probe.domain.models import Scan, ScanLevel, ScanProfile, ScanStatus, utc_now


class WebsiteHttpTests(unittest.TestCase):
    def test_pages_modules_api_and_authorization_work_together(self):
        with tempfile.TemporaryDirectory() as directory, socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            base = f"http://127.0.0.1:{listener.getsockname()[1]}"
            server = uvicorn.Server(uvicorn.Config(
                create_app(Path(directory) / "test.db"), log_level="error",
            ))
            thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
            thread.start()
            try:
                deadline = time.monotonic() + 10
                while not server.started and thread.is_alive() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(server.started, "website did not start")

                def get(path):
                    with urlopen(urljoin(base, path), timeout=5) as response:
                        self.assertEqual(response.status, 200)
                        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
                        return response.read().decode()

                document = get("/")
                self.assertIn("/console", document)
                console = get("/console")
                self.assertIn("RF Sentinel X", console)
                self.assertIn("/static/js/console.js", console)
                self.assertIn("OBSERVE", get("/static/js/console.js"))
                self.assertIn(".module", get("/static/css/console.css"))
                self.assertEqual(len(json.loads(get("/api/nodes"))["nodes"]), 3)
                self.assertEqual(json.loads(get("/api/peripheral-events"))["events"], [])
                self.assertFalse(json.loads(get("/api/reports/peripherals.json"))["hardware_verified"])
                self.assertIn("RF Sentinel peripheral evidence", get("/api/reports/peripherals.md"))
                resources = re.findall(r'(?:src|href)="(/static/[^\"]+)"', document)
                self.assertGreaterEqual(len(resources), 2)
                # Follow JavaScript imports, catching paths broken by a folder move.
                visited = set()
                while resources:
                    resource = resources.pop()
                    if resource in visited:
                        continue
                    visited.add(resource)
                    body = get(resource)
                    if resource.endswith(".js"):
                        for dependency in re.findall(r'from\s+"([^"]+)"', body):
                            resources.append(urljoin(resource, dependency))
                self.assertIn("/static/js/views/assets.js", visited)
                self.assertEqual(json.loads(get("/api/health"))["status"], "ready")
                self.assertEqual(json.loads(get("/api/state"))["assets"], [])
                self.assertIn("assets", json.loads(get("/api/reports/site.json")))
                self.assertIn("ip,mac,hostname", get("/api/reports/assets.csv"))
                self.assertEqual(json.loads(get("/api/assessment"))["findings"], [])
                self.assertIn("Assessment coverage", get("/api/reports/assessment.md"))
                self.assertIn("coverage", json.loads(get("/api/reports/assessment.json")))

                def post(path, payload):
                    request = Request(base + path, method="POST", data=json.dumps(payload).encode(),
                                      headers={"Content-Type": "application/json"})
                    return urlopen(request, timeout=5)

                with self.assertRaises(HTTPError) as disconnected:
                    post("/api/nodes/A/commands", {"command": "OBSERVE", "authorized": True,
                         "operator": "test", "purpose": "fixture", "args": {"sensor": "nrf", "duration_ms": 1000}})
                self.assertEqual(disconnected.exception.code, 400)
                disconnected.exception.close()

                with post("/api/instruments", {"name": "ESP A"}) as response:
                    self.assertEqual(response.status, 201)
                    instrument = json.loads(response.read())
                    self.assertEqual(instrument["connection_status"], "not verified")
                self.assertEqual(len(json.loads(get("/api/instruments"))["instruments"]), 1)
                with self.assertRaises(HTTPError) as stale:
                    post("/api/field-observations", {
                        "site": "not-current", "instrument_id": instrument["id"], "category": "wifi",
                        "title": "Test", "subject": "AP", "evidence": "Recorded locally",
                    })
                self.assertEqual(stale.exception.code, 400)
                stale.exception.close()
                with self.assertRaises(HTTPError) as invalid:
                    post("/api/instruments", {"name": "   "})
                self.assertEqual(invalid.exception.code, 400)
                invalid.exception.close()
                # Seed a completed discovery fixture, never a network scan, then
                # exercise the whole manual evidence -> review -> report workflow.
                repository = server.config.app.state.probe_service.repository
                site_id = repository.ensure_site("Office", utc_now())
                repository.create_scan(Scan(
                    site="Office", level=ScanLevel.DISCOVERY, profile=ScanProfile.OFFICE,
                    target="simulation://http-test", simulation=True,
                    status=ScanStatus.COMPLETED, started_at=utc_now(), finished_at=utc_now(),
                ), site_id)
                with post("/api/field-observations", {
                    "site": "Office", "instrument_id": instrument["id"], "category": "detection_validation",
                    "title": "Alert validation", "subject": "Lab sensor",
                    "evidence": "Expected test alert was recorded by the operator.",
                    "recommendation": "Retain the alert timestamp and verify response time.",
                }) as response:
                    self.assertEqual(response.status, 201)
                finding = json.loads(get("/api/assessment"))["findings"][0]
                self.assertEqual(finding["basis"], "manual observation")
                with post(f"/api/assessment/{finding['id']}/review", {
                    "site": "Office", "status": "reviewed", "note": "Evidence inspected",
                }) as response:
                    self.assertTrue(json.loads(response.read())["saved"])
                exported = json.loads(get("/api/reports/assessment.json"))["findings"][0]
                self.assertEqual(exported["status"], "reviewed")
                self.assertEqual(exported["note"], "Evidence inspected")
                self.assertIn("Alert validation", get("/api/reports/assessment.md"))
                request = Request(base + "/api/real/run", method="POST",
                                  data=json.dumps({"target": "192.168.1.0/24", "authorized": False}).encode(),
                                  headers={"Content-Type": "application/json"})
                with self.assertRaises(HTTPError) as error:
                    urlopen(request, timeout=5)
                self.assertEqual(error.exception.code, 403)
                error.exception.close()
            finally:
                server.should_exit = True
                thread.join(timeout=10)
                self.assertFalse(thread.is_alive(), "website did not shut down")
