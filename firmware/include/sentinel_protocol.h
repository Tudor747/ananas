#pragma once
#include <Arduino.h>
#include <ArduinoJson.h>
#ifndef SENTINEL_BUILD_ID
#define SENTINEL_BUILD_ID "unversioned"
#endif

// Called only on the Arduino loop thread. Drivers must return promptly.
void hardwareStop();
const char* hardwareHealth();
bool hardwareCommand(const char* command, JsonObjectConst args, JsonObject result);
void hardwarePoll();

namespace Sentinel {
static const char* role = SENTINEL_ROLE;
static char device[20], boot[20], session[65] = "";
static uint32_t sequence = 0, requestId = 0, lastRequest = 0, lastHost = 0;
static uint32_t observationId = 0;
static char line[1025];
static size_t used = 0;
static bool discard = false;
static StaticJsonDocument<3072> response;

inline JsonObject begin(const char* type, const char* command, uint32_t id, const char* health) {
    response.clear();
    response["v"] = 1; response["node"] = role;
    response["device"] = device; response["boot"] = boot;
    response["session"] = session; response["firmware"] = "rf-sentinel-1.0.0/" SENTINEL_BUILD_ID;
    response["seq"] = ++sequence; response["uptime_ms"] = millis();
    response["type"] = type; response["command"] = command;
    response["id"] = id; response["health"] = health;
    return response.createNestedObject("payload");
}
inline void emit() { serializeJson(response, Serial); Serial.println(); }
inline void button(const char* action) {
    if (!session[0]) return;
    auto p = begin("event", "INPUT", 0, hardwareHealth());
    p["action"] = action;
    emit();
}
inline JsonObject event(const char* sensor) {
    JsonObject p = begin("event", "OBSERVE", observationId, hardwareHealth());
    p["sensor"] = sensor;
    p["clock"] = "device_uptime_unsynchronized";
    return p;
}
inline void setup() {
    Serial.begin(115200);
    snprintf(device, sizeof(device), "%012llX", ESP.getEfuseMac());
    snprintf(boot, sizeof(boot), "%08lX%08lX", (unsigned long)esp_random(), (unsigned long)esp_random());
    // Identity is shown once for provisioning; it is not a protocol reply.
    Serial.printf("RF_SENTINEL node=%s device=%s build=1.0.0\n", role, device);
}
inline void handle() {
    StaticJsonDocument<1536> doc;
    if (deserializeJson(doc, line, used) || !doc.is<JsonObject>()) return;
    if (doc["v"] != 1 || !doc["node"].is<const char*>() || strcmp(doc["node"], role) ||
        !doc["command"].is<const char*>() || !doc["session"].is<const char*>() ||
        !doc["id"].is<uint32_t>() || !doc["args"].is<JsonObject>()) return;
    const char* cmd = doc["command"];
    const char* incoming = doc["session"];
    if (!strlen(incoming) || strlen(incoming) > 64) return;
    uint32_t id = doc["id"];
    bool hello = !strcmp(cmd, "HELLO");
    if (hello) {
        hardwareStop();
        strlcpy(session, incoming, sizeof(session));
        lastRequest = 0;
    } else if (!session[0] || strcmp(incoming, session)) return;
    // Never repeat an output on a duplicate request. ID 0 is reserved for shutdown STOP.
    if (!hello && id <= lastRequest && !(id == 0 && !strcmp(cmd, "STOP"))) return;
    if (id) lastRequest = id;
    lastHost = millis(); requestId = id;
    JsonObject result = begin("reply", cmd, id, hardwareHealth());
    if (hello || !strcmp(cmd, "STATUS")) {
        result["role"] = role;
        result["hardware_verified"] = false;
        result["mode"] = "pi_controlled";
        // Optional, read-only peripheral initialization details. Older firmware
        // remains compatible; a failed peripheral is separate from USB identity.
        hardwareCommand("STATUS", doc["args"].as<JsonObjectConst>(), result);
    } else if (!strcmp(cmd, "STOP")) {
        hardwareStop(); result["stopped"] = true;
    } else {
        bool supported = !strcmp(cmd, "OBSERVE") || !strcmp(cmd, "SET_CONFIG") || !strcmp(cmd, "TRANSMIT");
        if (!supported || !hardwareCommand(cmd, doc["args"].as<JsonObjectConst>(), result)) {
            response["health"] = "unsupported";
            if (!result.containsKey("error")) result["error"] = "unsupported command or arguments";
        }
    }
    if (response["health"] != "unsupported") response["health"] = result.containsKey("error") ? "error" : hardwareHealth();
    emit();
}
inline void poll() {
    for (unsigned budget = 0; budget < 128 && Serial.available(); ++budget) {
        char ch = Serial.read();
        if (ch == '\n') {
            if (!discard && used) handle();
            used = 0; discard = false;
        } else if (!discard) {
            if (used >= sizeof(line)-1) { used = 0; discard = true; }
            else line[used++] = ch;
        }
    }
    if (session[0] && millis() - lastHost > 5000) {
        hardwareStop(); session[0] = 0;
    }
    if (session[0]) hardwarePoll();
}
}
