#include <Arduino.h>
#include <IRremoteESP8266.h>
#include <IRrecv.h>
#include <IRsend.h>
#include <IRutils.h>
#include "sentinel_pins.h"
#include "sentinel_protocol.h"

IRrecv receiver(SENTINEL_IR_RX, 512, 15, true);
IRsend transmitter(SENTINEL_IR_TX);
static bool active = false;
static uint32_t until = 0, lastEvent = 0;
const char* hardwareHealth() { return active ? "busy" : "ready"; }
void hardwareStop() { if (active) receiver.disableIRIn(); active = false; }
bool hardwareCommand(const char* cmd, JsonObjectConst args, JsonObject result) {
    if (!strcmp(cmd, "OBSERVE")) {
        if (args["sensor"] != "ir" || !args["duration_ms"].is<uint32_t>()) return false;
        uint32_t duration = args["duration_ms"];
        if (duration < 100 || duration > 10000) return false;
        if (active) { result["error"] = "busy; stop first"; return true; }
        Sentinel::observationId = Sentinel::requestId;
        receiver.enableIRIn(); active = true; until = millis() + duration;
        result["started"] = true; result["duration_ms"] = duration; return true;
    }
    if (!strcmp(cmd, "TRANSMIT")) {
        if (!args["code"].is<uint32_t>()) return false;
#if SENTINEL_ENABLE_IR_TX
        hardwareStop(); transmitter.sendNEC(args["code"].as<uint32_t>(), 32, 0);
        result["frames_sent"] = 1; result["protocol"] = "NEC";
        result["received_by_target"] = "not verified";
        return true;
#else
        result["error"] = "IR output disabled; verify output stage and enable SENTINEL_ENABLE_IR_TX";
        return false;
#endif
    }
    return false;
}
void hardwarePoll() {
    if (!active) return;
    if ((int32_t)(millis() - until) >= 0) { hardwareStop(); auto p = Sentinel::event("ir"); p["complete"] = true; Sentinel::emit(); return; }
    decode_results result;
    if (receiver.decode(&result)) {
        if (millis() - lastEvent >= 100) {
            auto p = Sentinel::event("ir");
            p["protocol"] = typeToString(result.decode_type);
            p["bits"] = result.bits; p["value_hex"] = uint64ToString(result.value, 16);
            p["overflow"] = result.overflow; p["repeat"] = result.repeat;
            Sentinel::emit(); lastEvent = millis();
        }
        receiver.resume();
    }
}
void setup() {
    Sentinel::setup();
#if SENTINEL_ENABLE_IR_TX
    transmitter.begin();
#endif
}
void loop() { Sentinel::poll(); delay(1); }
