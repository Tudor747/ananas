// Shared scanner helpers extracted from wifiscan.cpp / wifi_channel_scan.cpp.
// MIT License, Copyright (c) 2026 PepeAngell. See ../LICENSE.
#pragma once
#include <WiFi.h>

namespace WifiObservation {
constexpr uint32_t SCAN_DWELL_MS = 500;

inline uint8_t signalBars(int rssi) {
    if (rssi > -55) return 4;
    if (rssi > -70) return 3;
    if (rssi > -85) return 2;
    return 1;
}

inline const char* securityName(wifi_auth_mode_t mode) {
    switch (mode) {
        case WIFI_AUTH_OPEN: return "Open";
        case WIFI_AUTH_WEP: return "WEP";
        case WIFI_AUTH_WPA_PSK: return "WPA-PSK";
        case WIFI_AUTH_WPA2_PSK: return "WPA2-PSK";
        case WIFI_AUTH_WPA_WPA2_PSK: return "WPA/WPA2-PSK";
        case WIFI_AUTH_WPA2_ENTERPRISE: return "WPA2-Enterprise";
        case WIFI_AUTH_WPA3_PSK: return "WPA3-PSK";
        case WIFI_AUTH_WPA2_WPA3_PSK: return "WPA2/WPA3-PSK";
        default: return "Unknown";
    }
}

inline int frequencyMhz(int channel) {
    return channel == 14 ? 2484 : channel >= 1 && channel <= 13 ? 2407 + channel * 5 : 0;
}
}
