"""List USB serial ports or run bounded ESP diagnostics, including over SSH."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import secrets
import time

from pi_ot_probe.domain.models import utc_now

PROTOCOL = "piot-usb-v1"
MAX_LINE = 2048


def exchange(port, command: str, timeout: float) -> dict:
    """Match a fresh request ID; ignore boot logs, stale replies and other protocols."""
    if command not in {"PING", "SELFTEST"}:
        raise ValueError("Only PING and SELFTEST are supported")
    request_id = secrets.token_hex(8)
    deadline = time.monotonic() + timeout
    retry_at = 0.0
    line = bytearray()
    discarding = False
    while time.monotonic() < deadline:
        if time.monotonic() >= retry_at:
            # Leading newline resynchronizes a partially received older request.
            port.write(f"\nPIOT1 {command} {request_id}\n".encode("ascii"))
            retry_at = time.monotonic() + 1.0
        chunk = port.read(256)
        for value in chunk:
            if value == 10:
                raw = bytes(line)
                line.clear()
                if discarding:
                    discarding = False
                    continue
                try:
                    reply = json.loads(raw)
                except (ValueError, UnicodeDecodeError, RecursionError):
                    continue
                if (isinstance(reply, dict) and reply.get("protocol") == PROTOCOL
                        and reply.get("id") == request_id and reply.get("command") == command):
                    if reply.get("status") not in ("ok", "busy"):
                        raise ValueError("ESP returned an invalid diagnostic status")
                    return reply
            elif not discarding:
                if len(line) >= MAX_LINE:
                    line.clear()
                    discarding = True
                else:
                    line.append(value)
    raise TimeoutError(
        f"No matching {command} reply. Check the port, diagnostic firmware and whether "
        "the ESP is in a blocking tool. USB detection alone does not prove data transfer."
    )


def run_checks(port, timeout: float) -> dict:
    report = {
        "generated_at": utc_now().isoformat(), "mode": "esp-usb-self-test",
        "status": "failed", "checks": [],
        "limitations": [
            "SPI response does not test antennas or over-the-air radio performance.",
            "Button levels do not test physical movement; AUX may be unwired on a four-button unit.",
            "Power switches, display pixels and Pi touch input are not tested.",
        ],
    }
    checks = report["checks"]
    try:
        ping = exchange(port, "PING", timeout)
        if ping["status"] != "ok":
            raise ValueError("ESP did not acknowledge PING")
        checks.append({"name": "usb_round_trip", "status": "passed", "response": ping})
        result = exchange(port, "SELFTEST", timeout)
        if result["status"] == "busy":
            checks.append({"name": "esp_self_test", "status": "skipped",
                           "reason": "ESP tool is active; self-test requires the idle menu."})
            report["status"] = "partial"
            return report
        for key in ("nrf1_spi", "nrf2_spi"):
            if type(result.get(key)) is not bool:
                raise ValueError(f"Invalid or missing {key} observation")
        levels = result.get("button_levels")
        if (not isinstance(levels, dict) or set(levels) != {"up", "down", "ok", "back", "aux"}
                or any(type(v) is not int or v not in (0, 1) for v in levels.values())):
            raise ValueError("Invalid or missing button input observations")
        for key in ("nrf1_spi", "nrf2_spi"):
            checks.append({"name": key, "status": "passed" if result[key] else "failed"})
        checks.append({"name": "button_pin_levels", "status": "observed",
                       "levels": levels, "meaning": "0 = low/pressed, 1 = high/released with reference wiring"})
        report["status"] = "failed" if any(c["status"] == "failed" for c in checks) else "passed"
    except (OSError, ValueError) as exc:
        checks.append({"name": "esp_protocol", "status": "failed", "error": str(exc)})
    return report


def bounded_timeout(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or not 1 <= number <= 30:
        raise argparse.ArgumentTypeError("timeout must be between 1 and 30 seconds")
    return number


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--list", action="store_true", help="enumerate ports without opening them")
    action.add_argument("--port", help="explicit ESP device, preferably /dev/serial/by-id/... on Pi")
    parser.add_argument("--timeout", type=bounded_timeout, default=5.0, help="seconds per command (1-30)")
    parser.add_argument("--output", type=Path, help="also save the JSON report")
    args = parser.parse_args(argv)
    try:
        import serial
        from serial.tools import list_ports
    except ImportError:
        print(json.dumps({"status": "failed", "error": 'Install the hardware extra: python -m pip install -e ".[hardware]"'}))
        return 1

    try:
        if args.list:
            ports = [{"device": p.device, "description": p.description, "vid": p.vid,
                      "pid": p.pid, "serial_number": p.serial_number}
                     for p in sorted(list_ports.comports(), key=lambda p: p.device)]
            report = {"status": "observed", "ports": ports,
                      "note": "Port enumeration only; no port opened and no ESP identity verified."}
        else:
            # Set line states before opening to avoid deliberate auto-reset. Some
            # USB drivers still glitch these lines, so firmware startup is retried.
            connection = serial.Serial(port=None, baudrate=115200, timeout=0.1,
                                       write_timeout=1, exclusive=True if os.name == "posix" else None)
            try:
                connection.dtr = False
                connection.rts = False
                connection.port = args.port
                connection.open()
                report = run_checks(connection, args.timeout)
                report["port"] = args.port
            finally:
                connection.close()
    except (OSError, ValueError) as exc:
        report = {"status": "failed", "error": str(exc),
                  "hint": "Check device path, serial permissions and other serial monitors."}
    output = json.dumps(report, indent=2) + "\n"
    print(output, end="")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    return {"failed": 1, "partial": 2}.get(report["status"], 0)


if __name__ == "__main__":
    raise SystemExit(main())
