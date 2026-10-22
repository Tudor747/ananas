#include "app_lifecycle.h"

AppHost Host;

void AppHost::registerApps(const App* list, uint8_t count) {
    apps     = list;
    appCount = count;
    current  = -1;
}

void AppHost::launch(uint8_t index) {
    if (!apps || index >= appCount) return;

    // If an app is already running, close it cleanly first.
    // This prevents dirty state between modules.
    if (current >= 0 && apps[current].exit) {
        apps[current].exit();
    }

    current = (int8_t)index;

    if (apps[current].enter) {
        apps[current].enter();
    }
}

void AppHost::shutdown() {
    if (current < 0 || !apps) return;
    if (apps[current].exit) {
        apps[current].exit();
    }
    current = -1;
}

void AppHost::tick() {
    if (current < 0 || !apps) return;
    if (apps[current].loop) {
        apps[current].loop();
    }
}