#ifndef APP_CONFIG_H
#define APP_CONFIG_H

#include <Arduino.h>

// =============================================================
// Central firmware configuration.
// Everything previously scattered as #define in each .cpp
// lives here. To change a pin, version, shared text,
// or scan limit, this is the only file to edit.
// =============================================================

namespace AppConfig {

    // ---------- Buttons ----------
    // Also used by firmware/node_a to control the native Raspberry Pi menu.
    // Wire each momentary switch between its GPIO and GND (INPUT_PULLUP).
    constexpr uint8_t  BTN_UP    = 26;
    constexpr uint8_t  BTN_DOWN  = 33;
    constexpr uint8_t  BTN_OK    = 32;
    constexpr uint8_t  BTN_BACK  = 25;
    constexpr uint8_t  BTN_AUX   = 27;   // SELECT on the Pi controller; OK runs the tool.

    // ---------- I2C / Display ----------
    constexpr uint8_t  I2C_SDA   = 21;
    constexpr uint8_t  I2C_SCL   = 22;
    constexpr uint8_t  SCREEN_W  = 128;
    constexpr uint8_t  SCREEN_H  = 64;

    // ---------- nRF24 ----------
    constexpr uint8_t  NRF1_CE   = 5;
    constexpr uint8_t  NRF1_CSN  = 17;
    constexpr uint8_t  NRF2_CE   = 16;
    constexpr uint8_t  NRF2_CSN  = 4;
    constexpr uint32_t NRF_SPI_HZ = 16000000;

    // ---------- Firmware / Identity ----------
    constexpr const char* FIRMWARE_NAME    = "BWifiKill";
    constexpr const char* FIRMWARE_VERSION = "V4.0";
    constexpr const char* BUILD_LABEL      = "V4 Visual";
    constexpr const char* BOARD_NAME       = "ESP32 DevKit";
    constexpr const char* DEV_HANDLE       = "PepeAngell";

    // ---------- Web Dashboard AP ----------
    constexpr const char* WEB_AP_SSID      = "BWifiKill_V4";
    constexpr const char* WEB_AP_PASSWORD  = "bwifikill40";
    constexpr const char* WEB_AP_IP        = "192.168.4.1";
    constexpr uint16_t    WEB_PORT         = 80;

    // ---------- Social links (About) ----------
    constexpr const char* SOCIAL_INSTAGRAM = "pepeangelll";
    constexpr const char* SOCIAL_GITHUB    = "pepeangell5";
    constexpr const char* SOCIAL_FACEBOOK  = "esp32tools";

    // ---------- Input timings (ms) ----------
    // Debounce: time an edge must remain stable
    constexpr uint16_t INPUT_DEBOUNCE_MS     = 30;
    // Hold duration before auto-repeat starts
    constexpr uint16_t INPUT_REPEAT_DELAY_MS = 350;
    // Auto-repeat interval once active
    constexpr uint16_t INPUT_REPEAT_RATE_MS  = 90;
    // Hold duration for a long press (fires once)
    constexpr uint16_t INPUT_LONG_PRESS_MS   = 600;

    // ---------- Passive scanner limits ----------
    constexpr uint8_t  WIFI_SCAN_MAX_NETWORKS = 30;
    constexpr uint16_t WIFI_SCAN_TIMEOUT_MS   = 3000;
    constexpr uint8_t  BT_SCAN_DURATION_S     = 5;
    constexpr uint8_t  BT_SCAN_MAX_DEVICES    = 25;
    constexpr uint8_t  IP_SCAN_BATCH_SIZE     = 8;   // parallel hosts
    constexpr uint16_t IP_SCAN_PING_TIMEOUT_MS = 250;

    // ---------- Log viewer ----------
    constexpr const char* LOG_FILE_PATH = "/logins.txt";
    constexpr uint8_t     LOG_LINES_PER_PAGE = 6;

    // ---------- Common UI text ----------
    constexpr const char* TXT_RUNNING   = "RUNNING";
    constexpr const char* TXT_STOPPED   = "STOPPED";
    constexpr const char* TXT_READY     = "READY";
    constexpr const char* TXT_BACK_EXIT = "BACK = EXIT";
    constexpr const char* TXT_OK_START  = "OK = START";

} // namespace AppConfig

#endif // APP_CONFIG_H
