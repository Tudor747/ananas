"""USB diagnostics distinguish a round trip from port detection or stale output."""
import argparse
import json
import unittest
from unittest.mock import patch

from pi_ot_probe.diagnostics.esp_check import exchange, run_checks, MAX_LINE, bounded_timeout


class FakePort:
    def __init__(self, change=None, noise=b"", fragment=17):
        self.pending = bytearray()
        self.change = change
        self.noise = noise
        self.fragment = fragment
        self.commands = []

    def write(self, data):
        _, command, request_id = data.decode().strip().split()
        self.commands.append(command)
        reply = {"protocol": "piot-usb-v1", "id": request_id, "command": command,
                 "status": "ok", "nrf1_spi": True, "nrf2_spi": True,
                 "button_levels": {k: 1 for k in ("up", "down", "ok", "back", "aux")}}
        if self.change:
            self.change(reply)
        self.pending.extend(self.noise + json.dumps(reply).encode() + b"\r\n")
        return len(data)

    def read(self, count):
        result = bytes(self.pending[:min(count, self.fragment)])
        del self.pending[:len(result)]
        return result


class EspCheckTests(unittest.TestCase):
    def test_round_trip_with_fragmented_replies_and_noisy_boot_logs(self):
        port = FakePort(noise=b"boot log\n\xff\n[]\n" + b"X" * (MAX_LINE + 3) + b"\n")
        result = run_checks(port, 1)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(port.commands, ["PING", "SELFTEST"])
        self.assertEqual(result["checks"][-1]["status"], "observed")
        self.assertTrue(any("display" in item for item in result["limitations"]))

    def test_disconnected_radio_is_a_failure_despite_successful_usb(self):
        result = run_checks(FakePort(lambda r: r.update(nrf2_spi=False)), 1)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["checks"][0]["status"], "passed")
        self.assertEqual(result["checks"][2]["status"], "failed")

    def test_busy_tool_is_partial_not_hardware_failure(self):
        def busy(reply):
            if reply["command"] == "SELFTEST":
                reply["status"] = "busy"
        result = run_checks(FakePort(busy), 1)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["checks"][-1]["status"], "skipped")

    def test_missing_and_malformed_evidence_never_pass(self):
        for change in (lambda r: r.pop("nrf1_spi"), lambda r: r.update(nrf1_spi="true"),
                       lambda r: r.update(button_levels={}), lambda r: r.update(status="unknown"),
                       lambda r: r.update(status=[])):
            with self.subTest(change=change):
                self.assertEqual(run_checks(FakePort(change), 1)["status"], "failed")

    def test_stale_reply_and_wrong_protocol_time_out(self):
        for change in (lambda r: r.update(id="stale"), lambda r: r.update(protocol="other"),
                       lambda r: r.update(command="other")):
            # Advance a deterministic clock instead of waiting for a physical timeout.
            ticks = iter(i / 100 for i in range(1000))
            with patch("pi_ot_probe.diagnostics.esp_check.time.monotonic", side_effect=lambda: next(ticks)):
                result = run_checks(FakePort(change), 1)
            self.assertEqual(result["status"], "failed")
            self.assertIn("No matching", result["checks"][-1]["error"])

    def test_rejects_other_commands_before_writing(self):
        port = FakePort()
        with self.assertRaises(ValueError):
            exchange(port, "START", 1)
        self.assertEqual(port.commands, [])

    def test_timeout_bounds(self):
        for value in ("nan", "inf", "0", "31"):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                bounded_timeout(value)
