"""Read-only, adapter-neutral Wi-Fi inventory for V3 baselines."""

from __future__ import annotations

import shutil
import sys

from pi_ot_probe.core.models import WifiAccessPoint
from kali_demo.real_scanner import _run_command


def _signal_to_dbm(value: str) -> int:
    try:
        percent = max(0, min(100, int(value.strip().rstrip("%"))))
    except ValueError:
        return -100
    return round(percent / 2 - 100)


def _signal_percent(value: str) -> int | None:
    try:
        return max(0, min(100, int(value.strip().rstrip("%"))))
    except ValueError:
        return None


def _frequency_band(frequency_mhz: int | None, channel: int) -> str | None:
    if frequency_mhz:
        if 2400 <= frequency_mhz < 2500:
            return "2.4 GHz"
        if 4900 <= frequency_mhz < 5925:
            return "5 GHz"
        if 5925 <= frequency_mhz < 7125:
            return "6 GHz"
    if 1 <= channel <= 14:
        return "2.4 GHz"
    if channel > 14:
        return "5/6 GHz"
    return None


def _split_nmcli(line: str) -> list[str]:
    fields: list[str] = []
    current: list[str] = []
    escaped = False
    for character in line:
        if escaped:
            current.append(character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(character)
    fields.append("".join(current))
    return fields


def parse_nmcli(document: str) -> list[WifiAccessPoint]:
    access_points: list[WifiAccessPoint] = []
    for line in document.splitlines():
        fields = _split_nmcli(line)
        if len(fields) not in {5, 8}:
            continue
        ssid, bssid, signal, channel, security = fields[:5]
        frequency, mode, rate = fields[5:] if len(fields) == 8 else ("", "", "")
        if not bssid:
            continue
        try:
            parsed_channel = int(channel)
        except ValueError:
            parsed_channel = 0
        try:
            parsed_frequency = int(frequency)
        except ValueError:
            parsed_frequency = None
        encryption = "OPEN" if security.strip() in {"", "--"} else security.strip()
        access_points.append(WifiAccessPoint(
            ssid=ssid or "<hidden>",
            bssid=bssid.upper(),
            signal_dbm=_signal_to_dbm(signal),
            channel=parsed_channel,
            encryption=encryption,
            suspicious=encryption == "OPEN",
            signal_percent=_signal_percent(signal),
            frequency_mhz=parsed_frequency,
            band=_frequency_band(parsed_frequency, parsed_channel),
            authentication=encryption,
            mode=mode or None,
            rate=rate or None,
            source="NetworkManager nmcli",
        ))
    return access_points


def parse_windows_netsh(document: str) -> list[WifiAccessPoint]:
    access_points: list[WifiAccessPoint] = []
    ssid = "<hidden>"
    authentication = "UNKNOWN"
    cipher = "UNKNOWN"
    network_type: str | None = None
    current: dict[str, str] | None = None

    def finish() -> None:
        nonlocal current
        if not current or not current.get("bssid"):
            current = None
            return
        try:
            channel = int(current.get("channel", "0"))
        except ValueError:
            channel = 0
        signal = current.get("signal", "0")
        access_points.append(WifiAccessPoint(
            ssid=ssid or "<hidden>",
            bssid=current["bssid"].upper(),
            signal_dbm=_signal_to_dbm(current.get("signal", "0")),
            channel=channel,
            encryption=cipher if cipher != "UNKNOWN" else authentication,
            suspicious=authentication.upper() in {"OPEN", "NONE"},
            signal_percent=_signal_percent(signal),
            frequency_mhz=None,
            band=_frequency_band(None, channel),
            authentication=authentication,
            cipher=cipher,
            radio_type=current.get("radio_type"),
            network_type=network_type,
            source="Windows netsh",
        ))
        current = None

    for raw_line in document.splitlines():
        line = raw_line.strip()
        lower = line.lower()
        if lower.startswith("ssid ") and not lower.startswith("bssid") and ":" in line:
            finish()
            ssid = line.split(":", 1)[1].strip() or "<hidden>"
        elif lower.startswith("authentication") and ":" in line:
            authentication = line.split(":", 1)[1].strip() or "UNKNOWN"
        elif lower.startswith("encryption") and ":" in line:
            cipher = line.split(":", 1)[1].strip() or "UNKNOWN"
        elif lower.startswith("network type") and ":" in line:
            network_type = line.split(":", 1)[1].strip() or None
        elif lower.startswith("bssid ") and ":" in line:
            finish()
            current = {"bssid": line.split(":", 1)[1].strip()}
        elif current is not None and lower.startswith("signal") and ":" in line:
            current["signal"] = line.split(":", 1)[1].strip()
        elif current is not None and lower.startswith("channel") and ":" in line:
            current["channel"] = line.split(":", 1)[1].strip()
        elif current is not None and lower.startswith("radio type") and ":" in line:
            current["radio_type"] = line.split(":", 1)[1].strip()
    finish()
    return access_points


async def discover_wifi() -> list[WifiAccessPoint]:
    if sys.platform == "win32":
        netsh = shutil.which("netsh.exe") or shutil.which("netsh")
        if not netsh:
            raise RuntimeError("Windows netsh is required for Wi-Fi inventory")
        output = await _run_command(netsh, "wlan", "show", "networks", "mode=bssid")
        return parse_windows_netsh(output)

    nmcli = shutil.which("nmcli")
    if not nmcli:
        raise RuntimeError("NetworkManager nmcli is required for Wi-Fi inventory")
    output = await _run_command(
        nmcli, "-t", "--escape", "yes", "-f",
        "SSID,BSSID,SIGNAL,CHAN,SECURITY,FREQ,MODE,RATE",
        "device", "wifi", "list", "--rescan", "yes",
    )
    return parse_nmcli(output)
