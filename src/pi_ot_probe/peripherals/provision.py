"""Inspect one explicitly selected USB endpoint before adding it to the allowlist."""
import argparse
import json
import secrets
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from .manager import serial_open
from .protocol import Decoder

ROLE_HARDWARE = {"A": "dual nRF24 / Wi-Fi / BLE", "B": "CC1101 433 MHz / RC522", "C": "infrared"}


def probe_port(port, role="auto", *, details=False):
    """Bound startup/open as well as HELLO; never let one USB port block the others."""
    args = [sys.executable, "-m", "pi_ot_probe.peripherals.provision"]
    if details:
        args.append("--inspect")
    args.extend(["--node", role, "--port", port])
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=25)
    except subprocess.TimeoutExpired as exc:
        progress = exc.stderr or ""
        if isinstance(progress, bytes):
            progress = progress.decode("utf-8", errors="replace")
        phase = progress.strip().splitlines()[-1] if progress.strip() else "Starting USB identification"
        raise ValueError(
            f"USB identification timed out after 25 seconds on {port}. "
            f"Last step: {phase}. No board identity confirmed. "
            "Close other serial monitors and retry Find & connect; other boards can stay plugged in."
        ) from exc
    try:
        data = json.loads(result.stdout)
    except (ValueError, TypeError) as exc:
        detail = (result.stdout + (result.stderr or "")).strip()[-1200:]
        raise ValueError(f"Invalid identification response on {port}: {detail}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Invalid identification response on {port}: expected a JSON object")
    if result.returncode:
        raise ValueError(f"{port}: {data.get('error', 'USB identification failed')}")
    return data


def inspect_all():
    """Read identities and radio checks on every attached USB endpoint, without saving."""
    from .ports import serial_ports

    def inspect(endpoint):
        try:
            return {**endpoint, **probe_port(endpoint["port"], details=True)}
        except (ValueError, OSError) as exc:
            return {**endpoint, "error": str(exc)}

    endpoints = serial_ports()
    if not endpoints:
        return {"ports": [], "error": "No USB serial boards detected."}
    with ThreadPoolExecutor(max_workers=3) as executor:
        return {"ports": list(executor.map(inspect, endpoints))}


def role_mismatch(port, expected, observed):
    actual = observed["node"]
    return (f"This board is ESP-{actual}, not ESP-{expected}. "
            f"USB: {port}. Firmware role: {ROLE_HARDWARE[actual]}. "
            f"Chip: {observed['device']}; firmware: {observed.get('firmware', 'unknown')}. "
            f"If this is your {ROLE_HARDWARE[expected]} board, it needs the node_{expected.lower()} firmware. "
            "Changing USB sockets or selecting another role cannot change the flashed firmware. "
            "Use Find & connect to identify the attached boards, or connect only the intended board to verify its chip ID.")


def identify(port, roles=("A", "B", "C"), *, timeout=8, clock=time.monotonic, details=False):
    """Send only HELLO; report actual role/identity and useful startup failures."""
    session = secrets.token_hex(16)
    decoder = Decoder()
    deadline, next_send = clock() + timeout, 0
    startup = ""
    while clock() < deadline:
        if clock() >= next_send:
            for role in roles:
                request = {"v": 1, "node": role, "session": session,
                           "id": 1, "command": "HELLO", "args": {}}
                raw = ("\n" + json.dumps(request) + "\n").encode()
                if port.write(raw) != len(raw):
                    raise OSError("Incomplete USB identification write; check the cable and retry.")
            next_send = clock() + 1
        chunk = port.read(256)
        startup = (startup + chunk.decode("utf-8", errors="replace"))[-8192:]
        for frame in decoder.feed(chunk):
            if (frame.node in roles and frame.session == session and frame.type == "reply"
                    and frame.command == "HELLO" and frame.id == 1):
                result = {"node": frame.node, "device": frame.device}
                if details:
                    result.update(firmware=frame.firmware, health=frame.health,
                                  hardware=frame.payload.get("hardware", {}))
                return result
    if any(marker in startup for marker in ("Guru Meditation", "assert failed", "Brownout", "Rebooting...")):
        raise TimeoutError("ESP is crashing or restarting before HELLO. Check its serial boot log and firmware.")
    if startup.strip():
        raise TimeoutError("USB data received, but no Sentinel HELLO. Check the installed node_a/node_b/node_c firmware.")
    raise TimeoutError("No USB reply. Check board power, data cable and firmware; press the ESP RESET button and retry.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port")
    parser.add_argument("--node", choices=["A", "B", "C", "auto"])
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--inspect", action="store_true", help="include firmware and peripheral diagnostics; never save an assignment")
    parser.add_argument("--inspect-all", action="store_true", help="inspect every attached USB board independently; close the app first; never save assignments")
    args = parser.parse_args()
    if args.inspect_all:
        if args.port or args.node or args.list or args.inspect:
            parser.error("use --inspect-all on its own")
        result = inspect_all()
        print(json.dumps(result, indent=2))
        return int("error" in result or any("error" in p for p in result["ports"]))
    if args.list:
        from .ports import serial_ports
        print(json.dumps(serial_ports(), indent=2))
        return 0
    if not args.port or not args.node:
        parser.error("use --list, or --port and --node")
    try:
        print(f"Opening USB port {args.port}", file=sys.stderr, flush=True)
        port = serial_open(args.port)
        try:
            print("Waiting for firmware HELLO", file=sys.stderr, flush=True)
            result = identify(port, details=True)
            if args.node != "auto" and result["node"] != args.node:
                raise ValueError(role_mismatch(args.port, args.node, result))
            if not args.inspect:
                result = {key: result[key] for key in ("node", "device")}
            print(json.dumps({**result, "port": args.port}, indent=2))
            return 0
        finally:
            port.close()
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
