#pragma once
#include <Arduino.h>
#include "app_config.h"

// ESP-A controller: switches from each GPIO to GND, using internal pull-ups.
// Change pins and timing in BWifiKiller/include/app_config.h.
namespace ControllerButtons {
struct Key {
    uint8_t pin;
    const char* action;
    bool repeat;
    bool raw = false, stable = false, armed = false;
    uint32_t changed = 0, pressed = 0, repeated = 0;
    Key(uint8_t p, const char* a, bool r = false) : pin(p), action(a), repeat(r) {}
};
static Key keys[] = {
    {AppConfig::BTN_UP, "up", true}, {AppConfig::BTN_DOWN, "down", true},
    {AppConfig::BTN_BACK, "back"}, {AppConfig::BTN_AUX, "select"},
    {AppConfig::BTN_OK, "ok"}
};
inline void setup() {
    for (auto& key : keys) {
        pinMode(key.pin, INPUT_PULLUP);
        key.raw = key.stable = digitalRead(key.pin) == LOW;
        key.armed = !key.raw; // A switch held during boot must first be released.
        key.changed = millis();
    }
}
inline void poll(void (*emit)(const char*)) {
    uint32_t now = millis();
    for (auto& key : keys) {
        bool raw = digitalRead(key.pin) == LOW;
        if (raw != key.raw) { key.raw = raw; key.changed = now; }
        if (raw != key.stable && now - key.changed >= AppConfig::INPUT_DEBOUNCE_MS) {
            key.stable = raw;
            if (!raw) key.armed = true;
            else if (key.armed) {
                key.pressed = key.repeated = now;
                emit(key.action);
            }
        } else if (key.stable && key.raw && key.armed && key.repeat &&
                   now - key.pressed >= AppConfig::INPUT_REPEAT_DELAY_MS &&
                   now - key.repeated >= AppConfig::INPUT_REPEAT_RATE_MS) {
            key.repeated = now;
            emit(key.action);
        }
    }
}
}
