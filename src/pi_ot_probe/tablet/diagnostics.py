"""Read-only checks, usable through SSH without loading the GUI."""
import asyncio
import importlib
import os
import shutil
import sys
from pathlib import Path

from pi_ot_probe.collectors.interfaces import discover_local_networks
from pi_ot_probe.peripherals.ports import serial_ports


def discover_choices():
    """A missing serial package must not hide usable network interfaces, or vice versa."""
    ports, networks, errors = [], [], []
    try:
        ports = serial_ports()
    except Exception as exc:
        errors.append(f"USB discovery: {exc}")
    try:
        networks = [n.to_dict() for n in asyncio.run(discover_local_networks())]
    except Exception as exc:
        errors.append(f"Network discovery: {exc}")
    return {"ports": ports, "networks": networks, "errors": errors}


def dependencies(config_path=None):
    checks = [{"name": "Python 3.11+", "ok": sys.version_info >= (3, 11),
               "required": True, "detail": sys.version.split()[0]}]
    for module, package in (("tkinter", "sudo apt install python3-tk"),
                            ("serial", 'python -m pip install -e ".[hardware]"'),
                            ("psutil", 'python -m pip install -e ".[hardware]"')):
        try:
            importlib.import_module(module)
            ok, detail = True, "Installed"
        except (ImportError, OSError) as exc:
            ok, detail = False, f"{package} ({exc})"
        checks.append({"name": module, "ok": ok, "required": True, "detail": detail})
    for name, detail in (("nmap", "IP Scanner: sudo apt install nmap"),
                         ("ip", "Interface fallback: sudo apt install iproute2"),
                         ("nmcli", "Pi Wi-Fi Scan: needs NetworkManager managing the Wi-Fi adapter")):
        path = shutil.which(name)
        checks.append({"name": name, "ok": bool(path), "required": False, "detail": path or detail})
    desktop = sys.platform != "linux" or bool(os.environ.get("DISPLAY"))
    checks.append({"name": "Desktop session", "ok": desktop, "required": False,
                   "detail": "Desktop display available" if desktop else
                   "Launch from the Pi desktop. A plain SSH session cannot show the window. Tk uses X11/XWayland."})
    if config_path is not None:
        from pi_ot_probe.peripherals.manager import load_config
        try:
            nodes = load_config(config_path) if Path(config_path).exists() else []
            checks.append({"name": "Node configuration", "ok": bool(nodes), "required": False,
                           "detail": str(config_path) if nodes else "System > USB Setup can identify a connected ESP."})
            for node in nodes:
                ok = sys.platform != "linux" or os.access(node.port, os.R_OK | os.W_OK)
                checks.append({"name": f"ESP-{node.node} serial access", "ok": ok, "required": False,
                               "detail": node.port if ok else
                               f"Cannot access {node.port}. Check connection and dialout membership; log out/in after changing groups."})
        except (OSError, ValueError) as exc:
            checks.append({"name": "Node configuration", "ok": False, "required": False, "detail": str(exc)})
    return checks
