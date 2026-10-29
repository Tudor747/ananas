"""List USB endpoints without opening them; prefer stable Linux device names."""
from pathlib import Path
from collections import Counter

from .manager import port_key


def serial_ports():
    from serial.tools.list_ports import comports

    devices = list(comports())
    serials = Counter(p.serial_number for p in devices if p.serial_number)
    by_id, by_path = {}, {}
    for folder in (Path("/dev/serial/by-id"), Path("/dev/serial/by-path")):
        if folder.is_dir():
            for path in sorted(folder.iterdir()):
                if path.exists():
                    aliases = by_id if folder.name == "by-id" else by_path
                    aliases.setdefault(port_key(str(path)), str(path))
    result = []
    for device in sorted(devices, key=lambda p: p.device):
        # Exclude onboard UARTs (e.g. ttyAMA10), which are not USB ESP connections.
        if device.vid is None:
            continue
        key = port_key(device.device)
        # Common CP2102 boards all advertise 0001, even when only one is plugged in.
        ambiguous = device.serial_number in {None, "", "0001"} or serials[device.serial_number] > 1
        stable = by_path.get(key) if ambiguous else by_id.get(key)
        result.append({"port": stable or by_path.get(key) or device.device,
                       "description": device.description or "USB serial device",
                       "usb_serial": device.serial_number})
    return result
