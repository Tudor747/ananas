#include "about_info.h"
#include "app_config.h"
#include "input_manager.h"
#include "ui_theme.h"
#include <U8g2lib.h>

extern U8G2_SSD1306_128X64_NONAME_F_HW_I2C u8g2;
// No longer needed: extern bool runningApp (main.cpp handles BACK)
//                    #define BTN_BACK/UP/DOWN (pins live in AppConfig
//                    and are read through the Input API)

static int about_scroll = 0;

struct MatrixDrop {
    int x;
    float y;
    float speed;
    char val;
};

static MatrixDrop drops[12];

static const char* about_lines[] = {
    "Dev: PepeAngell",
    "ESP32 DevKit",
    "Display: SSD1306",
    "RF: nRF24 PA/LNA",
    "Suite: BWifiKill",
    "Version: 4.0",
    "Build: V4 Visual",
    "IG: pepeangelll",
    "Git: pepeangell5",
    "FB: esp32tools"
};

static const int ABOUT_LINE_COUNT = sizeof(about_lines) / sizeof(about_lines[0]);
static const int ABOUT_MAX_SCROLL = (ABOUT_LINE_COUNT * 11) - 43;

static void initMatrix() {
    for (int i = 0; i < 12; i++) {
        drops[i].x = random(0, 128);
        drops[i].y = (float)random(-64, 0);
        drops[i].speed = (float)random(10, 32) / 10.0;
        drops[i].val = (random(0, 2) == 0) ? (char)random(48, 58) : (char)random(65, 71);
    }
}

static void drawMatrixBackground() {
    u8g2.setFont(u8g2_font_4x6_tf);
    u8g2.setDrawColor(1);
    for (int i = 0; i < 12; i++) {
        u8g2.drawGlyph(drops[i].x, (int)drops[i].y, drops[i].val);
        drops[i].y += drops[i].speed;
        if (drops[i].y > 64) {
            drops[i].y = (float)random(-20, 0);
            drops[i].x = random(0, 128);
            drops[i].val = (random(0, 2) == 0) ? (char)random(48, 58) : (char)random(65, 71);
        }
    }
}

static void drawScrollRail() {
    if (ABOUT_MAX_SCROLL <= 0) return;
    int railY = 22;
    int railH = 35;
    int markerH = 10;
    int markerY = railY + ((railH - markerH) * about_scroll) / ABOUT_MAX_SCROLL;
    u8g2.drawVLine(116, railY, railH);
    u8g2.drawBox(115, markerY, 3, markerH);
}

static void drawAboutWindow() {
    u8g2.setDrawColor(0);
    u8g2.drawBox(6, 17, 116, 46);
    u8g2.setDrawColor(1);
    u8g2.drawRFrame(6, 17, 116, 46, 3);

    u8g2.setFont(u8g2_font_6x10_tr);
    for (int i = 0; i < ABOUT_LINE_COUNT; i++) {
        int y = 29 + (i * 11) - about_scroll;
        if (y > 19 && y < 63) {
            u8g2.drawStr(12, y, about_lines[i]);
        }
    }

    drawScrollRail();
}

// =============================================================
// Lifecycle: enter / loop / exit
// =============================================================

void aboutEnter() {
    // Clean initial state on every entry
    about_scroll = 0;
    initMatrix();

    // Prevent a button held in the menu from carrying over here
    Input.resetAll();
}

void aboutExit() {
    // Reset so the next entry can start at the top
    about_scroll = 0;
}

void aboutLoop() {
    // Continuous scrolling while UP/DOWN is held.
    // The natural drawing frame rate (matrix + text + sendBuffer)
    // sets the pace: no delay() or manual throttling is needed.
    if (Input.held(BTN_ID_UP) && about_scroll > 0) {
        about_scroll -= 3;
    }
    if (Input.held(BTN_ID_DOWN) && about_scroll < ABOUT_MAX_SCROLL) {
        about_scroll += 3;
    }
    // BACK is no longer handled here; main.cpp catches it through Input.pressed
    // and triggers Host.shutdown(), which calls aboutExit().

    u8g2.clearBuffer();
    drawMatrixBackground();
    drawAboutWindow();

    u8g2.setDrawColor(0);
    u8g2.drawBox(0, 0, 128, 17);
    u8g2.setDrawColor(1);
    UiTheme::drawHeader(u8g2, "ABOUT", UiTheme::FIRMWARE_VERSION);

    UiTheme::drawMiniWave(u8g2, 4, 63, millis() / 90);
    u8g2.sendBuffer();
}
