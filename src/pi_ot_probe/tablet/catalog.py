"""Original menu names with explicit implementation and hardware requirements."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Tool:
    key: str
    title: str
    category: str
    action: str | None
    description: str
    node: str | None = None
    unavailable: str = ""


CATEGORIES = ("System", "Wi-Fi", "RF Tools", "Bluetooth", "Other boards", "Games", "Illegal")
NODE_NAMES = {"A": "Wi-Fi / BLE / nRF", "B": "433 MHz / RFID", "C": "Infrared"}
TOOLS = (
    Tool("wifi", "Wi-Fi Scanner", "Wi-Fi", "wifi", "Nearby 2.4 GHz access points observed by ESP-A.", "A"),
    Tool("radar", "Wi-Fi Radar", "Wi-Fi", "radar", "Three signal snapshots. Signal strength does not measure distance or bearing.", "A"),
    Tool("channels", "Channel Scan", "Wi-Fi", "channels", "Count observed access points by Wi-Fi channel. This is not channel utilization.", "A"),
    Tool("packets", "Packet Monitor", "Wi-Fi", None, "Original packet monitoring tool.", "A", "The installed node firmware does not stream packet-monitor data."),
    Tool("sentinel", "Sentinel Mode", "Wi-Fi", "sentinel", "Compare with the previous saved Wi-Fi snapshot. Missing APs may simply not have been observed.", "A"),
    Tool("ip", "IP Scanner", "Wi-Fi", "ip", "Find responding hosts on the Pi's local network (up to 256 addresses). Then select a host to check 20 common TCP ports."),
    Tool("dashboard", "Web Dashboard", "Wi-Fi", "overview", "Native device overview. The original ESP access-point dashboard is not running in node_a."),
    Tool("analyzer", "Analyzer", "RF Tools", "nrf", "Carrier threshold samples from both nRF radios on the current channel.", "A"),
    Tool("heatmap", "RF Heatmap", "RF Tools", "sweep", "Receive-only samples at 26 nRF channels (every fifth channel). Unsampled frequencies remain unknown.", "A"),
    Tool("advisor", "CH Advisor", "RF Tools", "advisor", "Rank sampled nRF channels by carrier hits. This is not a Wi-Fi channel recommendation.", "A"),
    Tool("link", "nRF Link", "RF Tools", "link", "One packet from radio 1 to radio 2 at minimum power on channel 76. Both radios must initialize.", "A"),
    Tool("chat", "nRF Chat", "RF Tools", None, "Original peer messaging tool.", "A", "Requires a peer and a messaging protocol; current firmware only supports a one-packet link test."),
    Tool("coex", "BT/WiFi Coex", "RF Tools", "coex", "Sequential Wi-Fi, BLE and nRF observations. These cannot establish interference or simultaneous coexistence.", "A"),
    Tool("scope", "Dual nRF Scope", "RF Tools", "scope", "Two carrier-threshold traces, about four samples per second. This is not an analog oscilloscope.", "A"),
    Tool("ble", "BT Scanner", "Bluetooth", "ble", "Passive Bluetooth LE advertisement inventory. Classic Bluetooth is not scanned.", "A"),
    Tool("bt_analyzer", "BT Analyzer", "Bluetooth", "bt_analyzer", "Three BLE snapshots and signal histories for observed addresses.", "A"),
    Tool("bt_spectrum", "BT Spectrum", "Bluetooth", "bt_spectrum", "BLE signal-strength distribution. No frequency spectrum is available from this firmware.", "A"),
    Tool("remote", "BT Remote", "Bluetooth", None, "Original Bluetooth remote tool.", "A", "Bluetooth HID pairing and remote commands are not implemented in node_a."),
    *tuple(Tool(key, title, "Illegal", None, "Original BWifiKiller menu entry.", "A", reason) for key, title, reason in (
        ("jammer", "Channel Jammer", "Not enabled: radio interference transmission is not provided."),
        ("full_sweep", "Full Sweep", "Not enabled: broadband interference transmission is not provided."),
        ("bt_jammer", "BT Jammer", "Not enabled: radio interference transmission is not provided."),
        ("beacon_spam", "Beacon Spam", "Not enabled: broadcast spam is not provided."),
        ("ble_spam", "BLE Spam (POP)", "Not enabled: unsolicited Bluetooth popup broadcasts are not provided."),
        ("hybrid", "Hybrid Mode", "Not enabled: combined interference and spam are not provided."),
        ("portal", "Evil Portal", "Not enabled: credential collection and impersonation are not provided."),
        ("deauther", "Deauther", "Not enabled: broadcast disconnect attacks are not provided."),
    )),
    Tool("arcade", "Arcade", "Games", "memory", "Touch memory game for the Pi. The original ESP arcade games have not been ported."),
    Tool("usb", "USB Setup", "System", "pair", "Connect each ESP once by its role and USB port. Existing assignments are preserved."),
    Tool("slave", "Devices", "System", "overview", "Live status for all three ESPs. Tap USB Setup to add a board or change its port."),
    Tool("logs", "View Logs", "System", "logs", "Recent device evidence, replies and errors. Export a JSON report to the Pi."),
    Tool("about", "About", "System", "about", "App version, screen size and feature availability."),
    Tool("dependencies", "Dependencies", "System", "dependencies", "Check Python packages, Nmap, USB permissions and desktop availability."),
    Tool("pi_wifi", "Pi Wi-Fi Scan", "System", "pi_wifi", "Use NetworkManager on the Pi. ESP Wi-Fi scanning does not need NetworkManager."),
    Tool("cc1101", "433 MHz / CC1101", "Other boards", "cc1101", "Receive RSSI from node B's configured radio.", "B"),
    Tool("rfid", "RFID / RC522", "Other boards", "rfid", "Observe a compatible tag with node B.", "B"),
    Tool("ir", "Infrared Receiver", "Other boards", "ir", "Listen for 10 seconds. Point a remote at ESP-C's IR receiver and press a button.", "C"),
)
BY_KEY = {tool.key: tool for tool in TOOLS}


def category_tools(category):
    return [tool for tool in TOOLS if tool.category == category]
