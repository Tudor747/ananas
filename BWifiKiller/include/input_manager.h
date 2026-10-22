#ifndef INPUT_MANAGER_H
#define INPUT_MANAGER_H

#include <Arduino.h>
#include "app_config.h"

// =============================================================
// InputManager
// -------------------------------------------------------------
// Replaces the pattern:
//     if (digitalRead(BTN_UP) == LOW) { ...; delay(200); }
// with an event-based API, no delay(), and proper debouncing.
//
// TYPICAL USAGE in each app loop:
//
//   Input.update();                              // once per frame
//   if (Input.pressed(BTN_ID_OK))   { ... }
//   if (Input.repeating(BTN_ID_UP)) { menu_idx--; }
//   if (Input.longPressed(BTN_ID_BACK)) { hardExit(); }
//
// "repeating" = first pulse + held auto-repeat (ideal for menus).
// "pressed" = falling edge only (ideal for confirmations).
// "longPressed" = fires ONCE when the threshold is crossed.
//
// CONSUME:
//   When a module with subviews (e.g. wifiscan details)
//   handles an event and does NOT want main.cpp to process it too,
//   call Input.consume(BTN_ID_BACK) to mark it handled
//   for this frame. The next Input.update() call clears it.
// =============================================================

enum ButtonId : uint8_t {
    BTN_ID_UP = 0,
    BTN_ID_DOWN,
    BTN_ID_OK,
    BTN_ID_BACK,
    BTN_ID_AUX,
    BTN_COUNT
};

enum ButtonEvent : uint8_t {
    EVT_NONE = 0,
    EVT_PRESSED,      // Edge: just pressed
    EVT_RELEASED,     // Edge: just released
    EVT_REPEAT,       // Auto-repeat while held
    EVT_LONG_PRESS    // Hold crossed the threshold (fires once)
};

class InputManager {
public:
    void begin();
    void update();

    // Queries
    ButtonEvent event(ButtonId id) const   { return events[id]; }
    bool        held(ButtonId id) const    { return stableState[id]; }
    uint32_t    heldMs(ButtonId id) const;

    // Convenience methods (used 95% of the time)
    bool pressed(ButtonId id) const     { return events[id] == EVT_PRESSED; }
    bool released(ButtonId id) const    { return events[id] == EVT_RELEASED; }
    bool repeating(ButtonId id) const   {
        return events[id] == EVT_PRESSED || events[id] == EVT_REPEAT;
    }
    bool longPressed(ButtonId id) const { return events[id] == EVT_LONG_PRESS; }

    // Mark an event handled so another consumer (e.g. main.cpp)
    // sees EVT_NONE this frame. Useful for modules with subviews.
    void consume(ButtonId id);

    // Clear all state. Call in appEnter() so a button held
    // when leaving the previous app does not carry into the new one.
    void resetAll();

private:
    static const uint8_t PINS[BTN_COUNT];

    bool        stableState[BTN_COUNT]  = {false};
    bool        rawPrev[BTN_COUNT]      = {false};
    uint32_t    lastEdgeMs[BTN_COUNT]   = {0};
    uint32_t    pressStartMs[BTN_COUNT] = {0};
    uint32_t    lastRepeatMs[BTN_COUNT] = {0};
    bool        longFired[BTN_COUNT]    = {false};
    ButtonEvent events[BTN_COUNT]       = {EVT_NONE};
};

extern InputManager Input;

#endif // INPUT_MANAGER_H