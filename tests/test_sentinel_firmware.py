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
#include <cassert>
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
constexpr int HIGH = 1, LOW = 0, OUTPUT = 1;
inline int pin_levels[40] = {}, pin_modes[40] = {};
inline void digitalWrite(int pin, int level) { pin_levels[pin] = level; }
inline void pinMode(int pin, int mode) { pin_modes[pin] = mode; }
inline struct SPIClass { void begin() {} } SPI;
constexpr int RF24_1MBPS = 1, RF24_PA_MIN = 0, RF24_CRC_16 = 2;
class RF24 {
public:
    int speed;
    RF24(int, int, int hz) : speed(hz) {}
    bool begin() {
        // Model shared-bus contention and a module requiring a slower clock.
        return speed <= 4000000 && clock_ms >= 100 &&
               pin_modes[17] == OUTPUT && pin_levels[17] == HIGH &&
               pin_modes[4] == OUTPUT && pin_levels[4] == HIGH &&
               pin_modes[5] == OUTPUT && pin_levels[5] == LOW &&
               pin_modes[16] == OUTPUT && pin_levels[16] == LOW;
    }
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
const char* hardwareHealth();
bool hardwareCommand(const char*, JsonObjectConst, JsonObject);
void hardwarePoll();
int main(int argc, char** argv) {
    setup();
    assert(std::string(hardwareHealth()) == "ready");
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


def test_node_b_keeps_rfid_bus_when_cc1101_is_missing(node_a_binary):
    folder = node_a_binary.parent
    (folder / "RadioLib.h").write_text(r'''
#include "mock_hardware.h"
constexpr int RADIOLIB_NC = -1, RADIOLIB_ERR_NONE = 0;
constexpr int RADIOLIB_ERR_PACKET_TOO_LONG = -2, MSBFIRST = 1, SPI_MODE0 = 0;
inline bool bus_running = true;
inline int digitalRead(int) { return 0; }
struct SPISettings { SPISettings(int, int, int) {} };
struct Module {
    bool owns_bus;
    Module(int,int,int,int) : owns_bus(true) {}
    Module(int,int,int,int,SPIClass&,SPISettings) : owns_bus(false) {}
};
struct CC1101 {
    Module* module;
    CC1101(Module* m) : module(m) {}
    int begin(double) {
        // RadioLib 6.6.0 terminates its owned SPI interface on chip-not-found.
        if (module->owns_bus) bus_running = false;
        return -1;
    }
    void standby() {} int startReceive() { return 0; }
    size_t getPacketLength() { return 0; }
    int readData(uint8_t*,size_t) { return 0; } int getRSSI() { return -90; }
};
''', encoding="utf-8")
    (folder / "MFRC522.h").write_text(r'''
#include "mock_hardware.h"
using byte = uint8_t;
struct MFRC522 {
    enum { VersionReg = 0 };
    struct { int size = 4, sak = 0; } uid;
    MFRC522(int,int) {}
    void PCD_Init() { assert(bus_running); }
    byte PCD_ReadRegister(int) { return bus_running ? 0x92 : 0; }
    void PCD_AntennaOff() {} void PCD_AntennaOn() { assert(bus_running); }
    bool PICC_IsNewCardPresent() { return true; }
    bool PICC_ReadCardSerial() { return true; }
    static int PICC_GetType(int) { return 0; }
    static const char* PICC_GetTypeName(int) { return "test tag"; }
    void PICC_HaltA() {} void PCD_StopCrypto1() {}
};
''', encoding="utf-8")
    # Node B supplies explicit shared SPI pins.
    mock = folder / "mock_hardware.h"
    mock.write_text(mock.read_text().replace("void begin() {}", "void begin(int=18,int=19,int=23) {}"))
    (folder / "main_b.cpp").write_text(r'''
#include "mock_hardware.h"
void setup();
bool hardwareCommand(const char*, JsonObjectConst, JsonObject);
void hardwarePoll();
int main() {
    setup();
    StaticJsonDocument<512> args, result;
    args["sensor"] = "rfid"; args["duration_ms"] = 1000;
    assert(hardwareCommand("OBSERVE", args.as<JsonObjectConst>(), result.to<JsonObject>()));
    assert(result["started"] == true);
    clock_ms = 300; hardwarePoll();
}
''', encoding="utf-8")
    binary = folder / ("node-b-test.exe" if os.name == "nt" else "node-b-test")
    subprocess.run([shutil.which("g++"), "-std=c++17", "-static", "-I", str(folder),
                    "-I", str(ROOT / "firmware/.pio/libdeps/node_a/ArduinoJson/src"),
                    "-I", str(ROOT / "firmware/include"), str(folder / "main_b.cpp"),
                    str(ROOT / "firmware/src/node_b.cpp"), "-o", str(binary)],
                   check=True, capture_output=True, text=True, timeout=60)
    result = subprocess.run([str(binary)], check=True, capture_output=True, text=True, timeout=5)
    assert json.loads(result.stdout)["tag_seen"] is True
