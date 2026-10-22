#include <Arduino.h>
#include <RF24.h>
#include "app_config.h"
#include "usb_diagnostics.h"
#include "usb_diagnostics_protocol.h"

extern RF24 jam1;
extern RF24 jam2;

void pollUsbDiagnostics(bool appRunning) {
    static UsbDiagnostics::Parser parser;
    // Bound work per frame so input noise cannot starve the existing menu.
    for (unsigned int budget = 0; budget < 96 && Serial.available(); ++budget) {
        const auto command = parser.feed(static_cast<char>(Serial.read()));
        if (command == UsbDiagnostics::Command::None) continue;
        const bool selfTest = command == UsbDiagnostics::Command::SelfTest;
        Serial.printf("{\"protocol\":\"piot-usb-v1\",\"id\":\"%s\",\"command\":\"%s\","
                      "\"status\":\"%s\",\"firmware\":\"BWifiKill USB diagnostics v1\","
                      "\"uptime_ms\":%lu,\"app_running\":%s",
                      parser.id(), selfTest ? "SELFTEST" : "PING",
                      selfTest && appRunning ? "busy" : "ok",
                      static_cast<unsigned long>(millis()), appRunning ? "true" : "false");
        if (selfTest && !appRunning) {
            // SPI register checks only. No RF transmission or radio reconfiguration.
            Serial.printf(",\"nrf1_spi\":%s,\"nrf2_spi\":%s,\"button_levels\":{"
                          "\"up\":%d,\"down\":%d,\"ok\":%d,\"back\":%d,\"aux\":%d},"
                          "\"display\":\"not_tested\",\"switches\":\"not_tested\"",
                          jam1.isChipConnected() ? "true" : "false",
                          jam2.isChipConnected() ? "true" : "false",
                          digitalRead(AppConfig::BTN_UP), digitalRead(AppConfig::BTN_DOWN),
                          digitalRead(AppConfig::BTN_OK), digitalRead(AppConfig::BTN_BACK),
                          digitalRead(AppConfig::BTN_AUX));
        }
        Serial.println("}");
    }
}
