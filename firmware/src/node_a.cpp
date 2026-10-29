// Headless RF Sentinel profile. Existing BWifiKill menu profiles remain separate.
#include <Arduino.h>
#include <SPI.h>
#include <RF24.h>
#include <WiFi.h>
#include <esp_wifi.h>
#include <BLEDevice.h>
#include <BLEScan.h>
#include "app_config.h"
#include "wifi_observation.h"
#include "sentinel_protocol.h"
#include "sentinel_buttons.h"

// Use a conservative bus clock instead of the legacy profile's 16 MHz.
static constexpr uint32_t NRF_SPI_HZ = 4000000;
RF24 radio1(AppConfig::NRF1_CE, AppConfig::NRF1_CSN, NRF_SPI_HZ);
RF24 radio2(AppConfig::NRF2_CE, AppConfig::NRF2_CSN, NRF_SPI_HZ);
static bool ready1 = false, ready2 = false, active = false, bleInitialized = false;
static String sensor;
static uint32_t until = 0, lastSample = 0;
static uint8_t channel = 76;
static BLEScan* bleScan = nullptr;
static volatile bool bleFinished = false;
static int wifiResultIndex = 0;
static constexpr int SCAN_RESULT_LIMIT = 64;

const char* hardwareHealth() { return active ? "busy" : (ready1 && ready2 ? "ready" : "error"); }
void hardwareStop() {
    if (ready1) { radio1.stopListening(); radio1.powerDown(); }
    if (ready2) { radio2.stopListening(); radio2.powerDown(); }
    esp_wifi_scan_stop(); WiFi.scanDelete(); WiFi.mode(WIFI_OFF);
    if (bleScan) bleScan->stop();
    active = false;
}
static void finish(const char* error = nullptr, int found = -1, int reported = -1) {
    hardwareStop();
    auto result = Sentinel::event(sensor.c_str());
    result["complete"] = true;
    if (found >= 0) {
        result["total_found"] = found;
        result["reported"] = reported;
        result["truncated"] = found > reported;
        result["result_limit"] = SCAN_RESULT_LIMIT;
    }
    if (error) result["error"] = error;
    Sentinel::emit();
}
bool hardwareCommand(const char* cmd, JsonObjectConst args, JsonObject result) {
    if (!strcmp(cmd, "TRANSMIT")) {
        if (args["test"] != "nrf_link") return false;
        if (active || !ready1 || !ready2) { result["error"] = "stop observation and check both radios first"; return true; }
        const uint8_t address[6] = "RFSX1";
        const uint8_t packet[8] = {'R','F','S','X','T','E','S','T'};
        for (RF24* radio : {&radio1, &radio2}) {
            radio->powerUp(); radio->setAutoAck(false); radio->setRetries(0,0);
            radio->setChannel(channel); radio->setDataRate(RF24_1MBPS);
            radio->setPALevel(RF24_PA_MIN); radio->setPayloadSize(sizeof(packet));
            radio->setCRCLength(RF24_CRC_16); radio->flush_rx(); radio->flush_tx();
        }
        radio2.openReadingPipe(1,address); radio2.startListening();
        radio1.openWritingPipe(address); radio1.stopListening();
        bool sent = radio1.write(packet,sizeof(packet));
        uint32_t start = millis();
        while (!radio2.available() && millis()-start < 15) delay(1);
        bool received = false;
        if (radio2.available()) { uint8_t incoming[8]; radio2.read(incoming,sizeof(incoming)); received = !memcmp(incoming,packet,sizeof(packet)); }
        hardwareStop();
        result["test"] = "nrf_link"; result["packets_requested"] = 1;
        result["tx_completed"] = sent; result["matching_packet_received"] = received;
        result["channel"] = channel; result["elapsed_ms"] = millis()-start;
        result["auto_ack"] = false;
        return true;
    }
    if (!strcmp(cmd, "SET_CONFIG")) {
        if (active || !args["channel"].is<unsigned>() || args["channel"].as<unsigned>() > 125) return false;
        channel = args["channel"]; result["channel"] = channel; return true;
    }
    if (strcmp(cmd, "OBSERVE") || !args["sensor"].is<const char*>() || !args["duration_ms"].is<uint32_t>()) return false;
    uint32_t duration = args["duration_ms"];
    String chosen = args["sensor"].as<String>();
    if (duration < 100 || duration > 10000 || (chosen != "nrf" && chosen != "wifi" && chosen != "ble")) return false;
    if (active) { result["error"] = "busy; stop first"; return true; }
    if (chosen == "nrf") {
        if (!ready1 || !ready2) { result["error"] = "one or both nRF SPI checks failed"; return true; }
        for (RF24* radio : {&radio1, &radio2}) {
            radio->setAutoAck(false); radio->setChannel(channel); radio->powerUp(); radio->startListening();
        }
    } else if (chosen == "wifi") {
        WiFi.mode(WIFI_STA); wifiResultIndex = 0;
        // Passive asynchronous scan, no association and no probe requests.
        int scan = WiFi.scanNetworks(true, true, true, WifiObservation::SCAN_DWELL_MS);
        if (scan == WIFI_SCAN_FAILED) {
            hardwareStop(); result["error"] = "Wi-Fi scan start failed"; return true;
        }
    } else {
        if (!bleInitialized) { BLEDevice::init(""); bleInitialized = true; bleScan = BLEDevice::getScan(); }
        bleScan->clearResults(); bleScan->setActiveScan(false); bleFinished = false;
        if (!bleScan->start((duration + 999) / 1000, [](BLEScanResults){bleFinished = true;}, false)) {
            hardwareStop(); result["error"] = "BLE scan start failed"; return true;
        }
    }
    sensor = chosen; active = true; until = millis() + duration;
    Sentinel::observationId = Sentinel::requestId;
    result["started"] = true; result["duration_ms"] = duration; return true;
}
void hardwarePoll() {
    if (!active) return;
    bool expired = (int32_t)(millis() - until) >= 0;
    if (sensor == "wifi") {
        int count = WiFi.scanComplete();
        if (count == WIFI_SCAN_FAILED) { finish("Wi-Fi scan failed"); return; }
        if (count >= 0) {
            if (wifiResultIndex < count && wifiResultIndex < SCAN_RESULT_LIMIT) {
                int i = wifiResultIndex++; auto p = Sentinel::event("wifi");
                p["ssid"] = WiFi.SSID(i).substring(0,32); p["bssid"] = WiFi.BSSIDstr(i);
                p["rssi_dbm"] = WiFi.RSSI(i); p["channel"] = WiFi.channel(i);
                p["security"] = WifiObservation::securityName(WiFi.encryptionType(i));
                p["hidden"] = WiFi.SSID(i).length() == 0;
                p["frequency_mhz"] = WifiObservation::frequencyMhz(WiFi.channel(i));
                p["band"] = "2.4 GHz"; Sentinel::emit();
            } else finish(nullptr, count, wifiResultIndex);
        } else if (expired) {
            finish("Wi-Fi scan did not finish within the observation window");
        }
        // Once scanning ends, drain the bounded result set even at the deadline.
        return;
    } else if (sensor == "ble" && (bleFinished || expired)) {
        // The BLE callback can arrive after our millisecond deadline. Stop reception
        // before reading its cached results instead of reporting an empty success.
        hardwareStop();
        BLEScanResults results = bleScan->getResults();
        // Cap the result batch and do not retain advertisement payloads.
        int reported = 0;
        for (int i = 0; i < results.getCount() && i < SCAN_RESULT_LIMIT; ++i) {
            BLEAdvertisedDevice device = results.getDevice(i); auto p = Sentinel::event("ble");
            p["address"] = device.getAddress().toString(); p["rssi_dbm"] = device.getRSSI();
            p["name"] = device.getName().substr(0,40); Sentinel::emit();
            ++reported;
        }
        auto completed = Sentinel::event("ble");
        completed["complete"] = true;
        completed["total_found"] = results.getCount(); completed["reported"] = reported;
        completed["truncated"] = results.getCount() > reported;
        completed["result_limit"] = SCAN_RESULT_LIMIT;
        Sentinel::emit();
    } else if (sensor == "nrf" && millis() - lastSample >= 250) {
        lastSample = millis(); auto p = Sentinel::event("nrf");
        p["channel"] = channel; p["nrf1_carrier"] = radio1.testRPD(); p["nrf2_carrier"] = radio2.testRPD();
        p["interpretation"] = "carrier threshold only; not Wi-Fi/BLE decoding or peer packet validation";
        Sentinel::emit();
        radio1.stopListening(); radio2.stopListening(); radio1.startListening(); radio2.startListening();
    }
    if (active && (int32_t)(millis() - until) >= 0) finish();
}
void setup() {
    Sentinel::setup();
    ControllerButtons::setup();
    // Both radios share MISO: deselect both before either begin() touches SPI.
    for (uint8_t pin : {AppConfig::NRF1_CSN, AppConfig::NRF2_CSN}) {
        digitalWrite(pin, HIGH); pinMode(pin, OUTPUT);
    }
    for (uint8_t pin : {AppConfig::NRF1_CE, AppConfig::NRF2_CE}) {
        digitalWrite(pin, LOW); pinMode(pin, OUTPUT);
    }
    SPI.begin();
    delay(100); // Allow both module supplies to settle before probing registers.
    ready1 = radio1.begin(); ready2 = radio2.begin(); hardwareStop();
}
void loop() { Sentinel::poll(); ControllerButtons::poll(Sentinel::button); delay(1); }
