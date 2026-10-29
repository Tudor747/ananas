#include <Arduino.h>
#include <SPI.h>
#include <RadioLib.h>
#include <MFRC522.h>
#include "sentinel_pins.h"
#include "sentinel_protocol.h"

// The application owns this bus because RC522 shares it. The default Module
// constructor lets RadioLib end SPI when CC1101 detection fails.
CC1101 radio = new Module(SENTINEL_CC_CS, SENTINEL_CC_GDO0, RADIOLIB_NC, RADIOLIB_NC,
                         SPI, SPISettings(2000000, MSBFIRST, SPI_MODE0));
MFRC522 rfid(SENTINEL_RFID_CS, SENTINEL_RFID_RST);
static bool ccReady = false, rfidReady = false, active = false;
static String sensor;
static uint32_t until = 0, lastSample = 0;

const char* hardwareHealth() { return active ? "busy" : (ccReady && rfidReady ? "ready" : "error"); }
void hardwareStop() {
    if (ccReady) radio.standby();
    if (rfidReady) rfid.PCD_AntennaOff();
    active = false;
}
bool hardwareCommand(const char* cmd, JsonObjectConst args, JsonObject result) {
    if (!strcmp(cmd, "STATUS")) {
        auto hw = result.createNestedObject("hardware");
        hw["cc1101_spi"] = ccReady; hw["rc522_spi"] = rfidReady;
        return true;
    }
    if (strcmp(cmd, "OBSERVE") || !args["sensor"].is<const char*>() || !args["duration_ms"].is<uint32_t>()) return false;
    uint32_t duration = args["duration_ms"];
    String chosen = args["sensor"].as<String>();
    if (duration < 100 || duration > 10000 || (chosen != "cc1101" && chosen != "rfid")) return false;
    if (active) { result["error"] = "busy; stop the current observation first"; return true; }
    if ((chosen == "cc1101" && !ccReady) || (chosen == "rfid" && !rfidReady)) {
        result["error"] = "peripheral initialization failed"; return true;
    }
    if (chosen == "cc1101") {
        int16_t status = radio.startReceive();
        if (status != RADIOLIB_ERR_NONE) { result["error"] = "receiver start failed"; result["driver_status"] = status; return true; }
    } else rfid.PCD_AntennaOn();
    sensor = chosen; active = true; until = millis() + duration;
    Sentinel::observationId = Sentinel::requestId;
    result["started"] = true; result["sensor"] = sensor;
    result["duration_ms"] = duration;
    return true;
}
void hardwarePoll() {
    if (!active) return;
    if ((int32_t)(millis() - until) >= 0) {
        hardwareStop(); auto p = Sentinel::event(sensor.c_str()); p["complete"] = true; Sentinel::emit(); return;
    }
    if (millis() - lastSample < 250) return;
    lastSample = millis();
    if (sensor == "cc1101") {
        if (digitalRead(SENTINEL_CC_GDO0)) {
            size_t length = radio.getPacketLength();
            uint8_t packet[64];
            int16_t status = length <= sizeof(packet) ? radio.readData(packet, length) : RADIOLIB_ERR_PACKET_TOO_LONG;
            auto received = Sentinel::event("cc1101");
            received["packet_bytes"] = length; received["driver_status"] = status;
            received["packet_valid"] = status == RADIOLIB_ERR_NONE;
            received["profile"] = "RadioLib default FSK at 433.92 MHz";
            received["payload"] = "not retained";
            Sentinel::emit(); radio.startReceive();
        }
        auto p = Sentinel::event("cc1101");
        p["frequency_mhz"] = 433.92; p["rssi_dbm"] = radio.getRSSI();
        p["interpretation"] = "receiver RSSI; no packet decoding claimed";
        Sentinel::emit();
    } else if (rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
        auto p = Sentinel::event("rfid");
        p["tag_seen"] = true; p["uid_bytes"] = rfid.uid.size;
        p["uid"] = "redacted";
        p["tag_family"] = MFRC522::PICC_GetTypeName(MFRC522::PICC_GetType(rfid.uid.sak));
        Sentinel::emit(); rfid.PICC_HaltA(); rfid.PCD_StopCrypto1();
    }
}
void setup() {
    Sentinel::setup();
    pinMode(SENTINEL_CC_CS, OUTPUT); digitalWrite(SENTINEL_CC_CS, HIGH);
    pinMode(SENTINEL_RFID_CS, OUTPUT); digitalWrite(SENTINEL_RFID_CS, HIGH);
    SPI.begin(SENTINEL_SPI_SCK, SENTINEL_SPI_MISO, SENTINEL_SPI_MOSI);
    ccReady = radio.begin(433.92) == RADIOLIB_ERR_NONE;
    rfid.PCD_Init();
    byte version = rfid.PCD_ReadRegister(MFRC522::VersionReg);
    rfidReady = version != 0 && version != 0xFF;
    hardwareStop();
}
void loop() { Sentinel::poll(); delay(1); }
