// Headless RF Sentinel profile. Existing BWifiKill menu profiles remain separate.
#include <Arduino.h>
#include <SPI.h>
#include <RF24.h>
#include <WiFi.h>
#include <esp_wifi.h>
#include <BLEDevice.h>
#include <BLEScan.h>
#include "app_config.h"
#include "sentinel_protocol.h"
#include "sentinel_buttons.h"
#include <BLEAdvertising.h>

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

// Receive-only Wi-Fi counters. Callback never retains frames, MACs or payloads.
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

const char* hardwareHealth() { return active ? "busy" : (ready1 && ready2 ? "ready" : "error"); }
void hardwareStop() {
    packetWatching = false;
    esp_wifi_set_promiscuous(false);
    esp_wifi_set_promiscuous_rx_cb(nullptr);
    if (labAdvertising) labAdvertising->stop();
    if (ready1) { radio1.stopListening(); radio1.powerDown(); }
    if (ready2) { radio2.stopListening(); radio2.powerDown(); }
    esp_wifi_scan_stop(); WiFi.scanDelete(); WiFi.mode(WIFI_OFF);
    if (bleScan) bleScan->stop();
    active = false;
}
static void finish(const char* error = nullptr) {
    hardwareStop();
    auto result = Sentinel::event(sensor.c_str());
    result["complete"] = true;
    if (error) result["error"] = error;
    Sentinel::emit();
}
bool hardwareCommand(const char* cmd, JsonObjectConst args, JsonObject result) {
    if (!strcmp(cmd, "TRANSMIT")) {
        const bool isChat = args["test"] == "nrf_chat_loopback";
        if (!isChat && args["test"] != "nrf_link") return false;
        String msg = isChat ? args["message"].as<String>() : String("RFSXTEST");
        if (isChat && (msg.length() < 1 || msg.length() > 24)) return false;
        if (active || !ready1 || !ready2) { result["error"] = "stop observation and check both radios first"; return true; }
        const uint8_t address[6] = "RFSX1";
        uint8_t packet[32] = {0};
        const size_t packetLen = msg.length();
        memcpy(packet, msg.c_str(), packetLen);
        for (RF24* radio : {&radio1, &radio2}) {
            radio->powerUp(); radio->setAutoAck(false); radio->setRetries(0,0);
            radio->setChannel(channel); radio->setDataRate(RF24_1MBPS);
            radio->setPALevel(RF24_PA_MIN); radio->setPayloadSize(packetLen);
            radio->setCRCLength(RF24_CRC_16); radio->flush_rx(); radio->flush_tx();
        }
        radio2.openReadingPipe(1,address); radio2.startListening();
        radio1.openWritingPipe(address); radio1.stopListening();
        bool sent = radio1.write(packet, packetLen);
        uint32_t start = millis();
        while (!radio2.available() && millis()-start < 15) delay(1);
        bool received = false;
        if (radio2.available()) { uint8_t incoming[32] = {0}; radio2.read(incoming, packetLen); received = !memcmp(incoming, packet, packetLen); }
        hardwareStop();
        result["test"] = isChat ? "nrf_chat_loopback" : "nrf_link";
        result["packets_requested"] = 1;
        if (isChat) { result["message"] = msg; result["scope"] = "same_board_loopback"; }
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
    if (duration < 100 || duration > 10000 ||
        (chosen != "nrf" && chosen != "wifi" && chosen != "ble" &&
         chosen != "packets" && chosen != "deauth" &&
         chosen != "beacon_lab" && chosen != "ble_ad_lab")) return false;
    if ((chosen == "beacon_lab" || chosen == "ble_ad_lab") && duration > 5000) return false;
    if (active) { result["error"] = "busy; stop first"; return true; }
    if (chosen == "nrf") {
        if (!ready1 || !ready2) { result["error"] = "one or both nRF SPI checks failed"; return true; }
        for (RF24* radio : {&radio1, &radio2}) {
            radio->setAutoAck(false); radio->setChannel(channel); radio->powerUp(); radio->startListening();
        }
    } else if (chosen == "wifi") {
        WiFi.mode(WIFI_STA); wifiResultIndex = 0;
        // Passive asynchronous scan, no association and no probe requests.
        int scan = WiFi.scanNetworks(true, true, true, 120);
        if (scan == WIFI_SCAN_FAILED) {
            hardwareStop(); result["error"] = "Wi-Fi scan start failed"; return true;
        }
    } else if (chosen == "packets" || chosen == "deauth") {
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
        bleScan->clearResults(); bleScan->setActiveScan(false); bleFinished = false;
        if (!bleScan->start((duration + 999) / 1000, [](BLEScanResults){bleFinished = true;}, false)) {
            hardwareStop(); result["error"] = "BLE scan start failed"; return true;
        }
    }
    sensor = chosen; active = true; until = millis() + duration;
    lastSample = millis();
    Sentinel::observationId = Sentinel::requestId;
    result["started"] = true; result["duration_ms"] = duration; return true;
}
void hardwarePoll() {
    if (!active) return;
    bool expired = (int32_t)(millis() - until) >= 0;
    if ((sensor == "packets" || sensor == "deauth") && millis() - lastSample >= 500) {
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
        if (count == WIFI_SCAN_FAILED) { finish("Wi-Fi scan failed"); return; }
        if (count >= 0) {
            if (wifiResultIndex < count && wifiResultIndex < 30) {
                int i = wifiResultIndex++; auto p = Sentinel::event("wifi");
                p["ssid"] = WiFi.SSID(i).substring(0,32); p["bssid"] = WiFi.BSSIDstr(i);
                p["rssi_dbm"] = WiFi.RSSI(i); p["channel"] = WiFi.channel(i); Sentinel::emit();
            } else finish();
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
        for (int i = 0; i < results.getCount() && i < 20; ++i) {
            BLEAdvertisedDevice device = results.getDevice(i); auto p = Sentinel::event("ble");
            p["address"] = device.getAddress().toString(); p["rssi_dbm"] = device.getRSSI();
            p["name"] = device.getName().substr(0,40); Sentinel::emit();
        }
        auto completed = Sentinel::event("ble");
        completed["complete"] = true;
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
