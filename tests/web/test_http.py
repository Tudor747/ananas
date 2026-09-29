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
