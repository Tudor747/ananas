"""Run node A's actual observation loop against deterministic radio stubs."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def node_a_binary(tmp_path_factory):
    compiler = shutil.which("g++")
    json_headers = ROOT / "firmware/.pio/libdeps/node_a/ArduinoJson/src"
    if not compiler or not json_headers.is_dir():
        pytest.skip("Requires g++ and the ArduinoJson dependency from a node_a build")
    folder = tmp_path_factory.mktemp("node-a-driver")
    (folder / "mock_hardware.h").write_text(r'''
#pragma once
#include <cstdint>
#include <cstring>
#include <string>
#include <iostream>
#include <ArduinoJson.h>
class String : public std::string {
public:
    using std::string::string;
    using std::string::operator=;
    String substring(size_t start, size_t end) const { return String(substr(start, end-start).c_str()); }
};
inline void convertFromJson(JsonVariantConst value, String& result) { result = value.as<const char*>(); }
inline void convertToJson(const String& value, JsonVariant result) { result.set(value.c_str()); }
inline uint32_t clock_ms = 0;
inline uint32_t millis() { return clock_ms; }
inline void delay(unsigned ms) { clock_ms += ms; }
inline struct SPIClass { void begin() {} } SPI;
constexpr int RF24_1MBPS = 1, RF24_PA_MIN = 0, RF24_CRC_16 = 2;
class RF24 {
public:
    RF24(int, int, int) {}
    bool begin() { return true; }
    void stopListening() {} void startListening() {} void powerDown() {} void powerUp() {}
    void setAutoAck(bool) {} void setRetries(int, int) {} void setChannel(int) {}
    void setDataRate(int) {} void setPALevel(int) {} void setPayloadSize(int) {} void setCRCLength(int) {}
    void flush_rx() {} void flush_tx() {} void openReadingPipe(int, const uint8_t*) {}
    void openWritingPipe(const uint8_t*) {} void read(uint8_t*, size_t) {}
    bool write(const uint8_t*, size_t) { return true; }
    bool available() { return false; } bool testRPD() { return false; }
};
constexpr int WIFI_OFF = 0, WIFI_STA = 1, WIFI_SCAN_RUNNING = -1, WIFI_SCAN_FAILED = -2;
inline struct WiFiClass {
    int scan_result = WIFI_SCAN_RUNNING;
    void mode(int) {} void scanDelete() {}
    int scanNetworks(bool, bool, bool, int) { return WIFI_SCAN_RUNNING; }
    int scanComplete() { return scan_result; }
    String SSID(int i) { return i ? "AP two" : "AP one"; }
    String BSSIDstr(int i) { return i ? "02:00:00:00:00:02" : "02:00:00:00:00:01"; }
    int RSSI(int) { return -50; } int channel(int) { return 6; }
} WiFi;
inline void esp_wifi_scan_stop() {}
struct BLEAddress { std::string toString() { return "02:00:00:00:00:03"; } };
struct BLEAdvertisedDevice {
    BLEAddress getAddress() { return {}; }
    int getRSSI() { return -60; }
    std::string getName() { return "Cached BLE result"; }
};
struct BLEScanResults {
    int getCount() { return 1; }
    BLEAdvertisedDevice getDevice(int) { return {}; }
};
struct BLEScan {
    void stop() {} void clearResults() {} void setActiveScan(bool) {}
    bool start(unsigned, void (*)(BLEScanResults), bool) { return true; }
    BLEScanResults getResults() { return {}; }
};
struct BLEDevice {
    static void init(const char*) {}
    static BLEScan* getScan() { static BLEScan scan; return &scan; }
};
''', encoding="utf-8")
    for name in ("Arduino.h", "SPI.h", "RF24.h", "WiFi.h", "esp_wifi.h", "BLEDevice.h", "BLEScan.h"):
        (folder / name).write_text('#include "mock_hardware.h"\n', encoding="utf-8")
    (folder / "sentinel_protocol.h").write_text(r'''
#include "mock_hardware.h"
namespace Sentinel {
    inline uint32_t requestId = 1, observationId = 0;
    inline StaticJsonDocument<1024> document;
    inline JsonObject event(const char* sensor) {
        document.clear(); document["sensor"] = sensor; return document.as<JsonObject>();
    }
    inline void emit() { serializeJson(document, std::cout); std::cout << '\n'; }
    inline void setup() {} inline void poll() {}
}
''', encoding="utf-8")
    (folder / "main.cpp").write_text(r'''
#include "mock_hardware.h"
void setup();
bool hardwareCommand(const char*, JsonObjectConst, JsonObject);
void hardwarePoll();
int main(int argc, char** argv) {
    setup();
    std::string scenario = argv[1];
    StaticJsonDocument<512> args, result;
    args["sensor"] = scenario == "ble_late" ? "ble" : "wifi";
    args["duration_ms"] = 100;
    if (!hardwareCommand("OBSERVE", args.as<JsonObjectConst>(), result.to<JsonObject>())) return 2;
    clock_ms = 200;
    WiFi.scan_result = scenario == "wifi_failed" ? WIFI_SCAN_FAILED :
                       scenario == "wifi_timeout" ? WIFI_SCAN_RUNNING : 2;
    for (int i = 0; i < 4; ++i) hardwarePoll();
}
''', encoding="utf-8")
    binary = folder / ("node-a-test.exe" if os.name == "nt" else "node-a-test")
    subprocess.run([compiler, "-std=c++17", "-static", "-I", str(folder), "-I", str(json_headers),
                    "-I", str(ROOT / "BWifiKiller/include"), str(folder / "main.cpp"),
                    str(ROOT / "firmware/src/node_a.cpp"), "-o", str(binary)],
                   check=True, capture_output=True, text=True, timeout=60)
    return binary


@pytest.mark.parametrize("scenario,field,expected", [("ble_late", "name", ["Cached BLE result"]),
                                                   ("wifi_late", "ssid", ["AP one", "AP two"])])
def test_cached_scan_results_survive_observation_deadline(node_a_binary, scenario, field, expected):
    result = subprocess.run([str(node_a_binary), scenario], capture_output=True, text=True, check=True, timeout=5)
    events = [json.loads(line) for line in result.stdout.splitlines()]
    assert [e[field] for e in events if field in e] == expected
    assert events[-1]["complete"] is True


@pytest.mark.parametrize("scenario", ["wifi_failed", "wifi_timeout"])
def test_failed_wifi_scan_is_not_reported_as_empty_success(node_a_binary, scenario):
    result = subprocess.run([str(node_a_binary), scenario], capture_output=True, text=True, check=True, timeout=5)
    events = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(events) == 1
    assert events[0]["complete"] is True
    assert events[0]["error"]
