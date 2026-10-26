"""List USB endpoints without opening them; prefer stable Linux device names."""
from pathlib import Path

from .manager import port_key


def serial_ports():
    from serial.tools.list_ports import comports

    aliases = {}
    for folder in (Path("/dev/serial/by-id"), Path("/dev/serial/by-path")):
        if folder.is_dir():
            for path in sorted(folder.iterdir()):
                if path.exists():
                    aliases.setdefault(port_key(str(path)), str(path))
    return [{"port": aliases.get(port_key(p.device), p.device),
             "description": p.description or "USB serial device", "usb_serial": p.serial_number}
            for p in sorted(comports(), key=lambda p: p.device)]
