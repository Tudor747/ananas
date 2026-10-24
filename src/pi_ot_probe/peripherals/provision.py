"""Inspect one explicitly selected USB endpoint before adding it to the allowlist."""
import argparse
import json
import secrets
import time

from .manager import serial_open
from .protocol import Decoder


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port")
    parser.add_argument("--node", choices=["A", "B", "C"])
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    if args.list:
        from serial.tools.list_ports import comports
        print(json.dumps([{"port": p.device, "description": p.description,
                           "usb_serial": p.serial_number} for p in comports()], indent=2))
        return 0
    if not args.port or not args.node:
        parser.error("use --list, or --port and --node")
    session = secrets.token_hex(16)
    request = {"v": 1, "node": args.node, "session": session,
               "id": 1, "command": "HELLO", "args": {}}
    decoder = Decoder()
    try:
        port = serial_open(args.port)
        try:
            deadline, next_send = time.monotonic() + 8, 0
            while time.monotonic() < deadline:
                if time.monotonic() >= next_send:
                    port.write(("\n" + json.dumps(request) + "\n").encode())
                    next_send = time.monotonic() + 1
                for frame in decoder.feed(port.read(256)):
                    if (frame.node == args.node and frame.session == session and frame.type == "reply"
                            and frame.command == "HELLO" and frame.id == 1):
                        print(json.dumps({"node": frame.node, "port": args.port, "device": frame.device}, indent=2))
                        return 0
            raise TimeoutError("No matching HELLO. Check selected role and headless firmware profile.")
        finally:
            port.close()
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
