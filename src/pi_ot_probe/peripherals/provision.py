"""Inspect one explicitly selected USB endpoint before adding it to the allowlist."""
import argparse
import json
import secrets
import time

from .manager import serial_open
from .protocol import Decoder


def identify(port, roles=("A", "B", "C"), *, timeout=8, clock=time.monotonic):
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
                port.write(("\n" + json.dumps(request) + "\n").encode())
            next_send = clock() + 1
        chunk = port.read(256)
        startup = (startup + chunk.decode("utf-8", errors="replace"))[-8192:]
        for frame in decoder.feed(chunk):
            if (frame.node in roles and frame.session == session and frame.type == "reply"
                    and frame.command == "HELLO" and frame.id == 1):
                return {"node": frame.node, "device": frame.device}
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
    args = parser.parse_args()
    if args.list:
        from .ports import serial_ports
        print(json.dumps(serial_ports(), indent=2))
        return 0
    if not args.port or not args.node:
        parser.error("use --list, or --port and --node")
    try:
        port = serial_open(args.port)
        try:
            result = identify(port)
            if args.node != "auto" and result["node"] != args.node:
                raise ValueError(f"This board is ESP-{result['node']}, not ESP-{args.node}. Choose role {result['node']}.")
            print(json.dumps({**result, "port": args.port}, indent=2))
            return 0
        finally:
            port.close()
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
