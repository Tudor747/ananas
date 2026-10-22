#include <Arduino.h>
#include <U8g2lib.h>
#include <WiFi.h>
#include <RF24.h>
#include <ESP32Ping.h>
#include <AsyncUDP.h>
#include <DNSServer.h>
#include <ESPAsyncWebServer.h>
#include <esp_wifi.h>

#include "spectrograph.h"
#include "rf_heatmap.h"
#include "channel_advisor.h"
#include "coex_view.h"
#include "dual_nrf_scope.h"
#include "nrf_link.h"
#include "nrf_chat.h"
#include "jammer.h"
#include "wifiscan.h"
#include "total_jammer.h"
#include "btscan.h"
#include "bt_jammer.h"
#include "beacon_spam.h"
#include "hybrid_attack.h"
#include "ip_scanner.h"
#include "snake_game.h"
#include "packet_monitor.h"
#include "gui_helper.h"
#include "slave_control.h"
#include "web_dashboard.h"
#include "about_info.h"
#include "evil_portal.h"
#include "web_server.h"
#include "log_viewer.h"
#include "ble_spam.h"
#include "bt_remote.h"
#include "bt_analyzer.h"
#include "bt_spectrum.h"
#include "centinela.h"
#include "games_menu.h"
#include "ui_theme.h"
#include "wifi_radar.h"
#include "wifi_channel_scan.h"
#include "menu_catalog.h"
#include "Deauther.h"

// --- NEW: Phase 0 helpers ---
#include "app_config.h"
#include "input_manager.h"
#include "app_lifecycle.h"
#include "usb_diagnostics.h"

// --- PROTOTYPES ---
void wifiscanSetup(); void wifiscanLoop();
void jammerSetup(); void jammerLoop();
void spectrographSetup(); void spectrographLoop();
void totalJammerSetup(); void totalJammerLoop();
void btscanSetup(); void btscanLoop();
void btJammerSetup(); void btJammerLoop();
void beaconSpamLoop(); void bleSpamEnter(); void bleSpamLoop(); void bleSpamExit();
void hybridAttackLoop();
void evilPortalLoop(); void logViewerLoop();
void startWebServer();
void btRemoteLoop();
void btAnalyzerEnter(); void btAnalyzerLoop(); void btAnalyzerExit();
void centinelaLoop();
void wifiscanEnter(); 
void wifiscanExit();

// --- STATE VARIABLES (identical to the original) ---
RTC_DATA_ATTR bool forceBleMode = false;
bool isTotalAttacking = false;
bool isHybridActive = false;
String target_ssid = "None";
int target_channel = 1;

// Literal constructors - do not reorder them, to preserve the wiring
U8G2_SSD1306_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, 22, 21);
RF24 jam1(5, 17, 16000000);
RF24 jam2(16, 4, 16000000);

AsyncWebServer asyncServer(AppConfig::WEB_PORT);

int   menu_index   = 0;
int   category_index = 0;
int   category_app_index = 0;
bool  browsingCategoryApps = false;
float currentPos   = 0;
bool  runningApp   = false;
int   TOTAL_OPTIONS = 30;

// --- MENU LABELS (identical) ---
const char* menu_labels[] = {
    "WIFI SCANNER",    // 0
    "WIFI RADAR",      // 1
    "CHANNEL SCAN",    // 2
    "ANALYZER",      // 3
    "BT SCANNER",      // 4
    "PACKET MONITOR",  // 5
    "SENTINEL MODE",  // 6
    "CHANNEL JAMMER",    // 7
    "FULL SWEEP",   // 8
    "BT JAMMER",       // 9
    "BEACON SPAM",     // 10
    "BLE SPAM (POP)",  // 11
    "HYBRID MODE",    // 12
    "EVIL PORTAL",     // 13
    "IP SCANNER",      // 14
    "SLAVE CONTROL", // 15
    "WEB DASHBOARD",   // 16
    "BT REMOTE",       // 17
    "VIEW LOGS",       // 18
    "ARCADE",          // 19
    "ABOUT",           // 20
    "BT ANALYZER",     // 21
    "BT SPECTRUM",     // 22
    "RF HEATMAP",      // 23
    "CH ADVISOR",      // 24
    "NRF LINK",        // 25
    "NRF CHAT",        // 26
    "BT/WIFI COEX",    // 27
    "DUAL NRF SCOPE",  // 28
    "DEAUTHER"         // 29
};

static void deautherLoop() {
    runDeauther();
    runningApp = false;
}

// =============================================================
// App table: { name, enter(), loop(), exit() }
// - enter() = formerly xxxSetup() in the original cascade
// - loop() = formerly xxxLoop() in the original cascade
// - exit() = nullptr for now; each module's .cpp remains unchanged
//
// Each module's internal behavior remains intact. This table
// only changes dispatch from main.cpp, not module logic.
// =============================================================
static const App apps[] = {
    /*  0 */ { "WIFI SCANNER",    wifiscanEnter,      wifiscanLoop,      wifiscanExit },
    /*  1 */ { "WIFI RADAR",      wifiRadarEnter,     wifiRadarLoop,     wifiRadarExit },
    /*  2 */ { "CHANNEL SCAN",    wifiChannelScanEnter, wifiChannelScanLoop, wifiChannelScanExit },
    /*  3 */ { "ANALYZER",      spectrographEnter,  spectrographLoop,  spectrographExit },
    /*  4 */ { "BT SCANNER",      btscanSetup,        btscanLoop,        btscanExit },
    /*  5 */ { "PACKET MONITOR",  monitorEnter,       monitorLoop,       monitorExit      },
    /*  6 */ { "SENTINEL MODE",  centinelaEnter,     centinelaLoop,     centinelaExit    },
    /*  7 */ { "CHANNEL JAMMER",    jammerSetup,        jammerLoop,        nullptr },
    /*  8 */ { "FULL SWEEP",   totalJammerSetup,   totalJammerLoop,   nullptr },
    /*  9 */ { "BT JAMMER",       btJammerSetup,      btJammerLoop,      nullptr },
    /* 10 */ { "BEACON SPAM",     nullptr,            beaconSpamLoop,    nullptr },
    /* 11 */ { "BLE SPAM (POP)",  bleSpamEnter,       bleSpamLoop,       bleSpamExit },
    /* 12 */ { "HYBRID MODE",    nullptr,            hybridAttackLoop,  nullptr },
    /* 13 */ { "EVIL PORTAL",     nullptr,            evilPortalLoop,    nullptr },
    /* 14 */ { "IP SCANNER",      ipScannerEnter,     ipScannerLoop,     ipScannerExit    },
    /* 15 */ { "SLAVE CONTROL", slaveControlEnter,  slaveControlLoop,  slaveControlExit },
    /* 16 */ { "WEB DASHBOARD",   startWebServer,     webDashboardLoop,  nullptr },
    /* 17 */ { "BT REMOTE",       btRemoteEnter,      btRemoteLoop,      btRemoteExit },
    /* 18 */ { "VIEW LOGS",       nullptr,            logViewerLoop,     nullptr },
    /* 19 */ { "ARCADE",          gamesEnter,         gamesLoop,         gamesExit },
    /* 20 */ { "ABOUT",           aboutEnter,         aboutLoop,         aboutExit },
    /* 21 */ { "BT ANALYZER",     btAnalyzerEnter,    btAnalyzerLoop,    btAnalyzerExit },
    /* 22 */ { "BT SPECTRUM",     btSpectrumEnter,    btSpectrumLoop,    btSpectrumExit },
    /* 23 */ { "RF HEATMAP",      rfHeatmapEnter,     rfHeatmapLoop,     rfHeatmapExit },
    /* 24 */ { "CH ADVISOR",      channelAdvisorEnter, channelAdvisorLoop, channelAdvisorExit },
    /* 25 */ { "NRF LINK",        nrfLinkEnter,       nrfLinkLoop,       nrfLinkExit },
    /* 26 */ { "NRF CHAT",        nrfChatEnter,       nrfChatLoop,       nrfChatExit },
    /* 27 */ { "BT/WIFI COEX",    coexViewEnter,      coexViewLoop,      coexViewExit },
    /* 28 */ { "DUAL NRF SCOPE",  dualNrfScopeEnter,  dualNrfScopeLoop,  dualNrfScopeExit },
    /* 29 */ { "DEAUTHER",        nullptr,            deautherLoop,      nullptr },
};
static const uint8_t APPS_COUNT = sizeof(apps) / sizeof(App);


static void performBackCleanup() {
    esp_wifi_set_promiscuous(false);
    jam1.stopConstCarrier();
    jam2.stopConstCarrier();
    if (menu_index == 16) asyncServer.end();

    bool keepWifiConnection = (menu_index == 0 && WiFi.status() == WL_CONNECTED);
    if (!keepWifiConnection) {
        WiFi.mode(WIFI_OFF);
    }
}


static bool needsRestartAfterExit(int idx) {
        return false;
}

void setup() {
    Serial.begin(115200);
    u8g2.begin();

    Input.begin();
    Host.registerApps(apps, APPS_COUNT);

    
    for (int i = 0; i <= 100; i += 5) {
        UiTheme::drawSplashFrame(u8g2, i, i / 5);
        u8g2.sendBuffer();
        delay(35);
    }

    // Early initialization identical to the original
    jam1.begin();
    jam2.begin();
}

void loop() {
    pollUsbDiagnostics(runningApp);
    Input.update();

    if (!runningApp) {
        // --- MENU NAVIGATION ---
        // repeating() = first pulse + smooth auto-repeat (replaces delay(200))
        if (Input.repeating(BTN_ID_UP)) {
            if (browsingCategoryApps) {
                const MenuCategory& cat = menuCategoryAt(category_index);
                category_app_index--;
                if (category_app_index < 0) category_app_index = cat.count - 1;
                menu_index = menuCategoryAppIndex(category_index, category_app_index);
            } else {
                category_index--;
                if (category_index < 0) category_index = menuCategoryCount() - 1;
            }
        }
        if (Input.repeating(BTN_ID_DOWN)) {
            if (browsingCategoryApps) {
                const MenuCategory& cat = menuCategoryAt(category_index);
                category_app_index++;
                if (category_app_index >= cat.count) category_app_index = 0;
                menu_index = menuCategoryAppIndex(category_index, category_app_index);
            } else {
                category_index++;
                if (category_index >= menuCategoryCount()) category_index = 0;
            }
        }

        drawBruceMenu();

        if (Input.pressed(BTN_ID_OK)) {
            if (!browsingCategoryApps) {
                browsingCategoryApps = true;
                category_app_index = 0;
                menu_index = menuCategoryAppIndex(category_index, category_app_index);
                delay(180);
            } else {
                menu_index = menuCategoryAppIndex(category_index, category_app_index);
                runningApp = true;
            Host.launch(menu_index);   // call enter() if defined
                delay(300);                 // preserve the original entry debounce
            }
        }

        if (Input.pressed(BTN_ID_BACK) && browsingCategoryApps) {
            browsingCategoryApps = false;
            delay(180);
        }
    } else {
        // --- EXECUTION ---
        Host.tick();   // call the current module's loop()

        // CASE A: the module exited internally (set runningApp = false).
        // Some modules (about, ble_spam in menu, bt_remote, slave_control...)
        // do this through their own digitalRead(25). Synchronize Host here
        // and perform the same cleanup as the BACK handler.
        if (!runningApp && Host.isRunning()) {
            Host.shutdown();
            performBackCleanup();
            if (needsRestartAfterExit(menu_index)) {
                ESP.restart();
            }
            return;
        }

        // CASE B: BACK handled from main.cpp (fallback).
        // Same exception as before: IP Scanner (14) handles its own BACK.
        if (Input.pressed(BTN_ID_BACK) && menu_index != 14) {
            runningApp = false;
            Host.shutdown();
            performBackCleanup();
            delay(300);
            if (needsRestartAfterExit(menu_index)) {
                ESP.restart();
            }
        }
    }
}
