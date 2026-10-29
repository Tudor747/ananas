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
    Tool("radar", "Wi-Fi Radar", "Wi-Fi", "radar", "Select an AP, then track its RSSI over 12 scans with a live graph and signal trend.", "A"),
    Tool("channels", "Channel Scan", "Wi-Fi", "channels", "Browse channels, open their AP list, then inspect each radio. Counts show observed APs, not airtime.", "A"),
    Tool("packets", "Packet Monitor", "Illegal", "packet_watch", "Receive-only 802.11 frame counters and deauth/disassoc statistics, channel-hopping. No payload or MAC capture.", "A"),
    Tool("sentinel", "Sentinel Mode", "Wi-Fi", "sentinel", "Compare with the previous saved Wi-Fi snapshot. Missing APs may simply not have been observed.", "A"),
    Tool("ip", "IP Scanner", "Wi-Fi", "ip", "Find responding hosts on the Pi's local network (up to 256 addresses). Then select a host to check 20 common TCP ports."),
    Tool("dashboard", "Web Dashboard", "Wi-Fi", "overview", "Native device overview. The original ESP access-point dashboard is not running in node_a."),
    Tool("analyzer", "Analyzer", "RF Tools", "nrf", "Carrier threshold samples from both nRF radios on the current channel.", "A"),
    Tool("heatmap", "RF Heatmap", "RF Tools", "sweep", "Receive-only samples at 26 nRF channels (every fifth channel). Unsampled frequencies remain unknown.", "A"),
    Tool("advisor", "CH Advisor", "RF Tools", "advisor", "Rank sampled nRF channels by carrier hits. This is not a Wi-Fi channel recommendation.", "A"),
    Tool("link", "nRF Link", "RF Tools", "link", "One packet from radio 1 to radio 2 at minimum power on channel 76. Both radios must initialize.", "A"),
    Tool("chat", "nRF Chat", "Illegal", "nrf_chat", "One bounded text packet between the two radios on the same ESP-A board; not communication with arbitrary peers.", "A"),
    Tool("coex", "BT/WiFi Coex", "RF Tools", "coex", "Sequential Wi-Fi, BLE and nRF observations. These cannot establish interference or simultaneous coexistence.", "A"),
    Tool("scope", "Dual nRF Scope", "RF Tools", "scope", "Two carrier-threshold traces, about four samples per second. This is not an analog oscilloscope.", "A"),
    Tool("ble", "BT Scanner", "Bluetooth", "ble", "Passive Bluetooth LE advertisement inventory. Classic Bluetooth is not scanned.", "A"),
    Tool("bt_analyzer", "BT Analyzer", "Bluetooth", "bt_analyzer", "Three BLE snapshots and signal histories for observed addresses.", "A"),
    Tool("bt_spectrum", "BT Spectrum", "Bluetooth", "bt_spectrum", "BLE signal-strength distribution. No frequency spectrum is available from this firmware.", "A"),
    Tool("remote", "BT Remote", "Illegal", "bt_remote_inventory", "Inspect locally paired Bluetooth devices on the Pi. Remote button injection is not implemented."),
    Tool("beacon_spam", "Beacon Spam", "Illegal", "beacon_lab", "Bounded, standard ESP32 test access point named RF_Sentinel_Lab. No fake AP flooding.", "A"),
    Tool("ble_spam", "BLE Spam (POP)", "Illegal", "ble_ad_lab", "Advertise one clearly identified RF_Sentinel_Lab BLE device for a few seconds. No pairing-popup spoofing.", "A"),
    Tool("jammer", "Channel Jammer", "Illegal", "channels", "Safe channel-activity alternative: count observed access points. No radio interference.", "A"),
    Tool("full_sweep", "Full Sweep", "Illegal", "sweep", "Reuse existing passive nRF sweep; 26 sampled channels. No transmissions.", "A"),
    Tool("bt_jammer", "BT Jammer", "Illegal", "bt_spectrum", "Safe BLE RSSI survey, not a jammer.", "A"),
    Tool("hybrid", "Hybrid Mode", "Illegal", "coex", "Reuse existing sequential Wi-Fi, BLE and nRF observations, without injection.", "A"),
    Tool("portal", "Evil Portal", "Illegal", "portal_demo", "Offline self-labelled portal demonstration on the Pi. No phishing, DNS interception or credentials."),
    Tool("deauther", "Deauther", "Illegal", "deauth_watch", "Passive counter for Wi-Fi deauth/disassociation frames. No packets transmitted.", "A"),
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
