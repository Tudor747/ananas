#ifndef APP_LIFECYCLE_H
#define APP_LIFECYCLE_H

#include <Arduino.h>

// =============================================================
// AppHost
// -------------------------------------------------------------
// Replaces the if/else if (menu_index == X) cascade
// in main.cpp with a declarative app registry.
//
// Each app exposes UP TO three functions:
//   - enter(): called once on entry (formerly Setup)
//   - loop(): called every frame while the app is active
//   - exit(): called once on exit; resources are released HERE
//              (WiFi.mode(WIFI_OFF), BLE.deinit(), nRF.powerDown,
//               esp_now_deinit, server.end(), etc.)
//
// The purpose of exit() is to remove the ESP.restart() calls
// previously needed because exiting left dirty state.
// Any of the three pointers can be nullptr.
// =============================================================

typedef void (*AppFn)();

struct App {
    const char* name;
    AppFn       enter;
    AppFn       loop;
    AppFn       exit;
};

class AppHost {
public:
    void registerApps(const App* list, uint8_t count);

    // Launch the app at the given index. If one is already running,
    // first call its exit() for cleanup, then call enter()
    // on the new app.
    void launch(uint8_t index);

    // Close the current app (call its exit()) and return to the menu.
    void shutdown();

    // Run the current app's loop(). Call every frame.
    void tick();

    bool        isRunning()   const { return current >= 0; }
    int8_t      currentIndex() const { return current; }
    const char* currentName() const {
        return (current >= 0 && apps) ? apps[current].name : "none";
    }
    uint8_t     count() const { return appCount; }
    const App*  appAt(uint8_t i) const {
        return (i < appCount) ? &apps[i] : nullptr;
    }

private:
    const App* apps     = nullptr;
    uint8_t    appCount = 0;
    int8_t     current  = -1;
};

extern AppHost Host;

#endif // APP_LIFECYCLE_H