#!/usr/bin/env python3
"""Integrate safe BWifiKiller-style lab modules under RF Sentinel's Illegal tab.

Run in /home/pi1/Desktop/ananas. Preserves local Pi overrides and GPIO16 code.
Does not flash any board. No jamming, unsolicited popup flooding,
credential capture, or forced disconnection is implemented.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime
from pathlib import Path
import shutil
import sys

ROOT = Path.cwd()
FILES = {
    "catalog": ROOT / "src/pi_ot_probe/tablet/catalog.py",
    "backend": ROOT / "src/pi_ot_probe/tablet/backend.py",
    "app": ROOT / "src/pi_ot_probe/tablet/app.py",
    "protocol": ROOT / "src/pi_ot_probe/peripherals/protocol.py",
    "node_a": ROOT / "firmware/src/node_a.cpp",
}


def once(s: str, original: str, replacement: str, description: str) -> str:
    count = s.count(original)
    if count != 1:
        raise ValueError(f"{description}: expected one anchor, found {count}")
    return s.replace(original, replacement, 1)


def catalog(s):
    # Existing entries move, retaining their keys so no UI/report identity changes.
    for key, original, replacement in (
        ("packets", 'Tool("packets", "Packet Monitor", "Wi-Fi", None, "Original packet monitoring tool.", "A", "The installed node firmware does not stream packet-monitor data."),',
         'Tool("packets", "Packet Monitor", "Illegal", "packet_watch", "Receive-only 802.11 frame counters and deauth/disassoc statistics, channel-hopping. No payload or MAC capture.", "A"),'),
        ("chat", 'Tool("chat", "nRF Chat", "RF Tools", None, "Original peer messaging tool.", "A", "Requires a peer and a messaging protocol; current firmware only supports a one-packet link test."),',
         'Tool("chat", "nRF Chat", "Illegal", "nrf_chat", "One bounded text packet between the two radios on the same ESP-A board; not communication with arbitrary peers.", "A"),'),
        ("remote", 'Tool("remote", "BT Remote", "Bluetooth", None, "Original Bluetooth remote tool.", "A", "Bluetooth HID pairing and remote commands are not implemented in node_a."),',
         'Tool("remote", "BT Remote", "Illegal", "bt_remote_inventory", "Inspect locally paired Bluetooth devices on the Pi. Remote button injection is not implemented."),'),
    ):
        s = once(s, original, replacement, f"catalog {key}")

    prefix = '    *tuple(Tool(key, title, "Illegal", None, "Original BWifiKiller menu entry.", "A", reason) for key, title, reason in ('
    start = s.find(prefix)
    end_marker = '    Tool("arcade", "Arcade", "Games", "memory"'
    if start < 0 or s.find(end_marker, start) < 0:
        raise ValueError("catalog: missing former Illegal tuple or arcade marker")
    end = s.index(end_marker, start)
    safe = '''    Tool("beacon_spam", "Beacon Spam", "Illegal", "beacon_lab", "Bounded, standard ESP32 test access point named RF_Sentinel_Lab. No fake AP flooding.", "A"),
    Tool("ble_spam", "BLE Spam (POP)", "Illegal", "ble_ad_lab", "Advertise one clearly identified RF_Sentinel_Lab BLE device for a few seconds. No pairing-popup spoofing.", "A"),
    Tool("jammer", "Channel Jammer", "Illegal", "channels", "Safe channel-activity alternative: count observed access points. No radio interference.", "A"),
    Tool("full_sweep", "Full Sweep", "Illegal", "sweep", "Reuse existing passive nRF sweep; 26 sampled channels. No transmissions.", "A"),
    Tool("bt_jammer", "BT Jammer", "Illegal", "bt_spectrum", "Safe BLE RSSI survey, not a jammer.", "A"),
    Tool("hybrid", "Hybrid Mode", "Illegal", "coex", "Reuse existing sequential Wi-Fi, BLE and nRF observations, without injection.", "A"),
    Tool("portal", "Evil Portal", "Illegal", "portal_demo", "Offline self-labelled portal demonstration on the Pi. No phishing, DNS interception or credentials."),
    Tool("deauther", "Deauther", "Illegal", "deauth_watch", "Passive counter for Wi-Fi deauth/disassociation frames. No packets transmitted.", "A"),
'''
    s = s[:start] + safe + s[end:]
    for key in ("beacon_spam","ble_spam","jammer","full_sweep","bt_jammer","hybrid","portal","deauther","packets","chat","remote"):
        if s.count(f'Tool("{key}",') != 1:
            raise ValueError(f"catalog: duplicate or missing key {key}")
    return s


def protocol(s):
    s = once(s,
        '"A": {"nrf", "wifi", "ble"}',
        '"A": {"nrf", "wifi", "ble", "packets", "deauth", "beacon_lab", "ble_ad_lab"}',
        "protocol ROLES")
    old = '''        elif node == "A" and self.args == {"test": "nrf_link"}:
            return
'''
    new = '''        elif node == "A" and self.args == {"test": "nrf_link"}:
            return
        elif (node == "A" and self.command == "TRANSMIT"
              and set(self.args) == {"test", "message"}
              and self.args.get("test") == "nrf_chat_loopback"
              and isinstance(self.args.get("message"), str)
              and 1 <= len(self.args["message"].encode("utf-8")) <= 24):
            return
'''
    return once(s, old, new, "protocol nrf chat")


def backend(s):
    anchor = '    def execute(self, action, node, purpose, **options):\n'
    added = '''    def execute(self, action, node, purpose, **options):
        # BWifiKiller laboratory substitutes live only under the Illegal menu.
        lab_sensors = {
            "packet_watch": "packets",
            "deauth_watch": "deauth",
            "beacon_lab": "beacon_lab",
            "ble_ad_lab": "ble_ad_lab",
        }
        if action in lab_sensors:
            sensor = lab_sensors[action]
            duration = 4000 if sensor in {"beacon_lab", "ble_ad_lab"} else 7000
            result = self.observe(sensor, purpose, duration=duration, node="A")
            return {"kind": action, "records": list(result),
                    "count": len(result), "observation": result.metadata,
                    "note": "Bounded laboratory operation; see tool description for capabilities."}
        if action == "nrf_chat":
            message = str(options.get("message", "RF Sentinel lab"))
            if not 1 <= len(message.encode("utf-8")) <= 24:
                raise ValueError("Message must be between 1 and 24 UTF-8 bytes")
            return self.request("A", "TRANSMIT",
                                {"test": "nrf_chat_loopback", "message": message}, purpose)
        if action == "bt_remote_inventory":
            import shutil
            executable = shutil.which("bluetoothctl")
            if not executable:
                raise ValueError("BlueZ bluetoothctl is not installed on the Pi")
            result = subprocess.run([executable, "devices", "Paired"],
                                    capture_output=True, text=True, timeout=10)
            if result.returncode:
                raise ValueError(result.stderr.strip() or "Bluetooth service unavailable")
            return {"kind": "paired_bluetooth_inventory", "devices": result.stdout.strip().splitlines(),
                    "note": "Local pairing inventory only; no remote control commands have been sent."}
        if action == "portal_demo":
            # Purely local, offline preview. Never accepts or saves user inputs.
            self.output_dir.mkdir(parents=True, exist_ok=True)
            page = self.output_dir / "rf-sentinel-portal-demo.html"
            page.write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>RF Sentinel Portal Demo</title><style>body{background:#101923;color:#fff;font-family:sans-serif;margin:5em auto;max-width:580px}h1{color:#4ee3b3}</style><h1>RF Sentinel - Offline Portal Demo</h1><p>This is a clearly labelled local preview, not a captive portal. No password collection.</p></html>', encoding="utf-8")
            return {"kind": "offline_portal_demo", "file": str(page.resolve()),
                    "note": "Open this HTML file locally on the Pi. This is not an active captive portal."}
'''
    return once(s, anchor, added, "backend execute")


def app(s):
    s = once(s,
        'GRAPH_ACTIONS = {"wifi", "radar", "channels", "sentinel", "ble", "bt_analyzer",',
        'GRAPH_ACTIONS = {"packet_watch", "deauth_watch", "wifi", "radar", "channels", "sentinel", "ble", "bt_analyzer",',
        "app graph actions")
    s = once(s,
        '        self.target = tk.StringVar(root)\n',
        '        self.target = tk.StringVar(root)\n        self.chat_message = tk.StringVar(root, "RF Sentinel lab")\n',
        "app init chat field")
    s = once(s,
        '        content = self.scroll_area()\n        self.label(content, tool.description, MUTED)\n',
        '''        content = self.scroll_area()
        self.label(content, tool.description, MUTED)
        if tool.action == "nrf_chat":
            self.label(content, "Message (1-24 UTF-8 bytes):", MUTED)
            tk.Entry(content, textvariable=self.chat_message, bg=PANEL,
                     fg=TEXT, insertbackground=TEXT, relief="flat").pack(fill="x", pady=3)
''',
        "app tool form")
    s = once(s,
        '    def run_tool(self, **options):\n        if not self.tool:\n            return\n',
        '''    def run_tool(self, **options):
        if not self.tool:
            return
        if self.tool.action == "nrf_chat":
            options["message"] = self.chat_message.get()
''',
        "app run_tool chat")
    s = once(s,
        '        action = self.tool.action\n        if action in {"channels", "bt_spectrum"}:\n',
        '''        action = self.tool.action
        if action in {"packet_watch", "deauth_watch"}:
            rows = [r for r in self.samples if "total_packets" in r][-24:]
            if not rows:
                graph.create_text(10, 18, anchor="nw", fill=MUTED,
                                  text="Waiting for passive Wi-Fi frame counts...")
                return
            scale = max(1, max(int(row.get("total_packets", 0)) for row in rows))
            step = (width - 20) / max(1, len(rows))
            for i, row in enumerate(rows):
                x = 10 + i * step
                total = max(0, int(row.get("total_packets", 0)))
                deauth = max(0, int(row.get("deauth_frames", 0)))
                bar_height = total * 90 / scale
                graph.create_rectangle(x, 115 - bar_height, x + max(2, step - 2), 115,
                                       fill=ACCENT, outline="")
                if deauth:
                    graph.create_rectangle(x, 115 - deauth * 90 / scale,
                                           x + max(2, step - 2), 115,
                                           fill="#ffb5a5", outline="")
            graph.create_text(8, 5, anchor="nw", text="Frames / 500 ms (red: deauth)", fill=MUTED)
            return
        if action in {"channels", "bt_spectrum"}:
''',
        "app packet graph")
    return s


def node_a(s):
    s = once(s,
        '#include "sentinel_buttons.h"\n',
        '#include "sentinel_buttons.h"\n#include <BLEAdvertising.h>\n',
        "node_a BLE include")
    s = once(s,
        'const char* hardwareHealth()',
        '''// Receive-only Wi-Fi counters. Callback never retains frames, MACs or payloads.
static portMUX_TYPE packetMux = portMUX_INITIALIZER_UNLOCKED;
static volatile bool packetWatching = false;
static volatile uint32_t packetTotal = 0, packetData = 0, packetMgmt = 0;
static volatile uint32_t packetDeauth = 0, packetDisassoc = 0;
static uint8_t packetChannel = 1;
static BLEAdvertising* labAdvertising = nullptr;
static void onPassiveWifiFrame(void* raw, wifi_promiscuous_pkt_type_t type) {
    if (!packetWatching || raw == nullptr) return;
    bool deauth = false, disassoc = false;
    if (type == WIFI_PKT_MGMT) {
        auto* pkt = reinterpret_cast<wifi_promiscuous_pkt_t*>(raw);
        if (pkt->rx_ctrl.sig_len >= 24) {
            const uint8_t subtype = (pkt->payload[0] >> 4) & 0x0f;
            deauth = (subtype == 12);
            disassoc = (subtype == 10);
        }
    }
    portENTER_CRITICAL_ISR(&packetMux);
    ++packetTotal;
    if (type == WIFI_PKT_DATA) ++packetData;
    if (type == WIFI_PKT_MGMT) ++packetMgmt;
    if (deauth) ++packetDeauth;
    if (disassoc) ++packetDisassoc;
    portEXIT_CRITICAL_ISR(&packetMux);
}

const char* hardwareHealth()''',
        "node_a packet globals")
    s = once(s,
        '''void hardwareStop() {
    if (ready1)''',
        '''void hardwareStop() {
    packetWatching = false;
    esp_wifi_set_promiscuous(false);
    esp_wifi_set_promiscuous_rx_cb(nullptr);
    if (labAdvertising) labAdvertising->stop();
    if (ready1)''',
        "node_a hardwareStop")
    s = once(s,
        '''        if (args["test"] != "nrf_link") return false;
        if (active || !ready1 || !ready2)''',
        '''        const bool isChat = args["test"] == "nrf_chat_loopback";
        if (!isChat && args["test"] != "nrf_link") return false;
        String msg = isChat ? args["message"].as<String>() : String("RFSXTEST");
        if (isChat && (msg.length() < 1 || msg.length() > 24)) return false;
        if (active || !ready1 || !ready2)''',
        "node_a nrf chat test switch")
    s = once(s,
        '''        const uint8_t packet[8] = {'R','F','S','X','T','E','S','T'};
''',
        '''        uint8_t packet[32] = {0};
        const size_t packetLen = msg.length();
        memcpy(packet, msg.c_str(), packetLen);
''',
        "node_a transmit packet")
    s = once(s,
        '''radio->setPayloadSize(sizeof(packet));''',
        '''radio->setPayloadSize(packetLen);''',
        "node_a transmit payload size")
    s = once(s,
        '''bool sent = radio1.write(packet,sizeof(packet));''',
        '''bool sent = radio1.write(packet, packetLen);''',
        "node_a transmit write")
    s = once(s,
        '''uint8_t incoming[8]; radio2.read(incoming,sizeof(incoming)); received = !memcmp(incoming,packet,sizeof(packet));''',
        '''uint8_t incoming[32] = {0}; radio2.read(incoming, packetLen); received = !memcmp(incoming, packet, packetLen);''',
        "node_a transmit read")
    s = once(s,
        '''        result["test"] = "nrf_link"; result["packets_requested"] = 1;
''',
        '''        result["test"] = isChat ? "nrf_chat_loopback" : "nrf_link";
        result["packets_requested"] = 1;
        if (isChat) { result["message"] = msg; result["scope"] = "same_board_loopback"; }
''',
        "node_a nrf chat metadata")
    s = once(s,
        '''    if (duration < 100 || duration > 10000 || (chosen != "nrf" && chosen != "wifi" && chosen != "ble")) return false;
''',
        '''    if (duration < 100 || duration > 10000 ||
        (chosen != "nrf" && chosen != "wifi" && chosen != "ble" &&
         chosen != "packets" && chosen != "deauth" &&
         chosen != "beacon_lab" && chosen != "ble_ad_lab")) return false;
    if ((chosen == "beacon_lab" || chosen == "ble_ad_lab") && duration > 5000) return false;
''',
        "node_a supported observe modes")
    s = once(s,
        '''    } else {
        if (!bleInitialized) { BLEDevice::init(""); bleInitialized = true; bleScan = BLEDevice::getScan(); }
''',
        '''    } else if (chosen == "packets" || chosen == "deauth") {
        WiFi.mode(WIFI_STA);
        packetChannel = 1;
        portENTER_CRITICAL(&packetMux);
        packetTotal = packetData = packetMgmt = packetDeauth = packetDisassoc = 0;
        portEXIT_CRITICAL(&packetMux);
        esp_wifi_set_promiscuous_rx_cb(&onPassiveWifiFrame);
        if (esp_wifi_set_channel(packetChannel, WIFI_SECOND_CHAN_NONE) != ESP_OK ||
            esp_wifi_set_promiscuous(true) != ESP_OK) {
            hardwareStop(); result["error"] = "passive Wi-Fi monitor setup failed"; return true;
        }
        packetWatching = true;
    } else if (chosen == "beacon_lab") {
        WiFi.mode(WIFI_AP);
        if (!WiFi.softAP("RF_Sentinel_Lab", "RFSentinelLab2026", 1, false, 1)) {
            hardwareStop(); result["error"] = "lab access point startup failed"; return true;
        }
    } else if (chosen == "ble_ad_lab") {
        if (!bleInitialized) {
            BLEDevice::init("RF_Sentinel_Lab"); bleInitialized = true;
            bleScan = BLEDevice::getScan();
        }
        if (bleScan) bleScan->stop();
        labAdvertising = BLEDevice::getAdvertising();
        BLEAdvertisementData data;
        data.setFlags(0x06);
        data.setName("RF_Sentinel_Lab");
        labAdvertising->setAdvertisementData(data);
        labAdvertising->setScanResponse(false);
        labAdvertising->setMinInterval(0x00a0);
        labAdvertising->setMaxInterval(0x0140);
        labAdvertising->start();
    } else {
        if (!bleInitialized) { BLEDevice::init("RF_Sentinel_Lab"); bleInitialized = true; bleScan = BLEDevice::getScan(); }
''',
        "node_a observe mode selection")
    s = once(s,
        '''    sensor = chosen; active = true; until = millis() + duration;
''',
        '''    sensor = chosen; active = true; until = millis() + duration;
    lastSample = millis();
''',
        "node_a mode start")
    s = once(s,
        '''    if (sensor == "wifi") {
        int count = WiFi.scanComplete();
''',
        '''    if ((sensor == "packets" || sensor == "deauth") && millis() - lastSample >= 500) {
        lastSample = millis();
        uint32_t total, data, mgmt, deauth, disassoc;
        portENTER_CRITICAL(&packetMux);
        total = packetTotal; data = packetData; mgmt = packetMgmt;
        deauth = packetDeauth; disassoc = packetDisassoc;
        packetTotal = packetData = packetMgmt = packetDeauth = packetDisassoc = 0;
        portEXIT_CRITICAL(&packetMux);
        auto p = Sentinel::event(sensor.c_str());
        p["channel"] = packetChannel;
        p["interval_ms"] = 500;
        p["total_packets"] = total;
        p["data_packets"] = data;
        p["management_packets"] = mgmt;
        p["deauth_frames"] = deauth;
        p["disassoc_frames"] = disassoc;
        Sentinel::emit();
        ++packetChannel; if (packetChannel > 11) packetChannel = 1;
        esp_wifi_set_channel(packetChannel, WIFI_SECOND_CHAN_NONE);
    } else if ((sensor == "beacon_lab" || sensor == "ble_ad_lab") && expired) {
        auto p = Sentinel::event(sensor.c_str());
        p["mode"] = sensor == "beacon_lab" ? "single_standard_test_ap" : "named_ble_advertising";
        p["identity"] = "RF_Sentinel_Lab";
        p["duration_limited"] = true;
        Sentinel::emit();
        finish(); return;
    }
    if (sensor == "wifi") {
        int count = WiFi.scanComplete();
''',
        "node_a polling new modes")
    # Counter observations must not complete before final sample when duration < 500 ms.
    return s


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write changes after preflight; default is dry run")
    args = parser.parse_args()
    if not (ROOT / "run-tablet.sh").is_file():
        raise SystemExit("STOP: run from the root of the ananas project")
    if any(not f.is_file() for f in FILES.values()):
        raise SystemExit("STOP: missing project file(s): " + ", ".join(str(f) for f in FILES.values() if not f.is_file()))
    originals = {k: p.read_text(encoding="utf-8") for k, p in FILES.items()}
    if '"packet_watch"' in originals["catalog"]:
        raise SystemExit("STOP: an Illegal Lab integration appears to be installed already")
    edits = {
        "catalog": catalog(originals["catalog"]),
        "backend": backend(originals["backend"]),
        "app": app(originals["app"]),
        "protocol": protocol(originals["protocol"]),
        "node_a": node_a(originals["node_a"]),
    }
    for kind in ("catalog", "backend", "app", "protocol"):
        ast.parse(edits[kind], filename=str(FILES[kind]))
    if 'def on_power_switch' not in edits["app"] or '_gpio16_reboot' not in edits["app"]:
        raise ValueError("Refusing to continue: local GPIO16 auto reboot feature not present in app.py")
    if not args.apply:
        print("DRY RUN SUCCESS: 5 files are compatible, Python syntax is valid, GPIO16 code is retained.")
        print("Run again with --apply to write changes. ESP firmware is NOT flashed.")
        return
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backups = {}
    for key, p in FILES.items():
        dest = p.with_name(f"{p.name}.before_illegal_lab_{timestamp}.bak")
        shutil.copy2(p, dest)
        backups[key] = dest
    staged = {}
    try:
        for key, p in FILES.items():
            tmp = p.with_name(f"{p.name}.illegal_lab_tmp")
            tmp.write_text(edits[key], encoding="utf-8")
            shutil.copymode(p, tmp)
            staged[key] = tmp
        for key, p in FILES.items():
            staged[key].replace(p)
    except Exception:
        for key, p in FILES.items():
            if key in backups:
                shutil.copy2(backups[key], p)
        raise
    finally:
        for path in staged.values():
            path.unlink(missing_ok=True)
    print("SUCCESS: Illegal Lab integrated into 5 project files.")
    print("Eleven Illegal-tab entries configured; no harmful radio flood/jamming implemented.")
    print("Backups:")
    for key, p in backups.items(): print(f"  {key}: {p}")
    print("NEXT: build 'node_a' firmware with PlatformIO; upload only after it compiles.")

if __name__ == "__main__":
    try: main()
    except (ValueError, SyntaxError, OSError) as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        sys.exit(1)
