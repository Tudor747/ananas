"""Repeatable live checks on this computer; no subnet or hardware required."""

from __future__ import annotations

import argparse
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import platform
import threading

from kali_demo.real_scanner import (
    _run_command, discover_local_networks, find_nmap, parse_service_xml,
)
from kali_demo.web_inspector import inspect_website
from pi_ot_probe.core.models import Asset, utc_now


class LocalHandler(BaseHTTPRequestHandler):
    def handle(self) -> None:
        # A TCP connect scan closes the socket without issuing an HTTP request.
        self.connection.settimeout(5)
        try:
            super().handle()
        except (ConnectionResetError, BrokenPipeError, TimeoutError):
            pass

    def do_HEAD(self) -> None:
        self.send_response(200)
        self.send_header("X-Probe-Check", "local-live-check")
        self.send_header("Set-Cookie", "local-test-cookie=redact-me")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        pass


async def run_checks() -> dict:
    report = {
        "generated_at": utc_now().isoformat(),
        "platform": platform.system(),
        "mode": "live-local-check",
        "scope": "Local interface configuration and a temporary HTTP server on 127.0.0.1",
        "checks": [],
    }
    checks = report["checks"]
    try:
        networks = await discover_local_networks()
        checks.append({"name": "interfaces", "status": "passed",
                       "observations": [item.to_dict() for item in networks]})
    except Exception as exc:
        checks.append({"name": "interfaces", "status": "failed", "error": str(exc)})

    server = None
    thread = None
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 0), LocalHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        try:
            observation = await inspect_website("127.0.0.1", port, "http")
            headers = {item["name"].lower(): item["value"] for item in observation.headers}
            passed = (observation.status_code == 200
                      and headers.get("x-probe-check") == "local-live-check"
                      and headers.get("set-cookie") == "[redacted by data-minimization policy]")
            checks.append({"name": "http", "status": "passed" if passed else "failed",
                           "observation": observation.to_dict()})
        except Exception as exc:
            checks.append({"name": "http", "status": "failed", "error": str(exc)})

        nmap = find_nmap()
        if not nmap:
            checks.append({"name": "nmap_tcp", "status": "skipped", "reason": "Nmap is not installed or discoverable"})
        else:
            command = [nmap, "-sT", "-Pn", "-n", "-p", str(port),
                       "--max-retries", "0", "--host-timeout", "15s", "-oX", "-", "127.0.0.1"]
            try:
                raw = await _run_command(*command, timeout=20)
                asset = parse_service_xml(raw, Asset(ip="127.0.0.1"))
                checks.append({"name": "nmap_tcp", "status": "passed" if port in asset.ports else "failed",
                               "command": command, "observed_ports": asset.ports, "raw_xml": raw})
            except Exception as exc:
                checks.append({"name": "nmap_tcp", "status": "failed", "command": command, "error": str(exc)})
    except Exception as exc:
        checks.append({"name": "loopback_server", "status": "failed", "error": str(exc)})
    finally:
        if server:
            if thread and thread.is_alive():
                await asyncio.to_thread(server.shutdown)
                thread.join(timeout=2)
            server.server_close()
    report["status"] = ("failed" if any(item["status"] == "failed" for item in checks)
                        else "partial" if any(item["status"] == "skipped" for item in checks) else "passed")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("kali_demo/data/local-check.json"))
    args = parser.parse_args()
    report = asyncio.run(run_checks())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for check in report["checks"]:
        print(f"{check['status'].upper()}: {check['name']}")
        if check.get("error") or check.get("reason"):
            print(f"  {check.get('error') or check.get('reason')}")
    print(f"Actual observations: {args.output.resolve()}")
    return 1 if report["status"] == "failed" else 2 if report["status"] == "partial" else 0


if __name__ == "__main__":
    raise SystemExit(main())
