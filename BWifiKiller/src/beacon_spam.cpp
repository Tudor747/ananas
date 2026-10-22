#include <Arduino.h>
#include <WiFi.h>
#include <esp_wifi.h>
#include <U8g2lib.h>
#include "beacon_spam.h"
#include "ui_theme.h"

extern U8G2 u8g2; 
bool isSpamming = false;

// Animation variables
unsigned long lastAnimUpdate = 0;
int animFrame = 0;
extern int total_ssids;

static void drawBeaconIcon(int x, int y, int frame) {
    u8g2.drawTriangle(x + 4, y + 18, x + 10, y + 5, x + 16, y + 18);
    u8g2.drawDisc(x + 10, y + 5, 2);
    if (frame >= 1) u8g2.drawCircle(x + 10, y + 5, 5, U8G2_DRAW_UPPER_LEFT | U8G2_DRAW_UPPER_RIGHT);
    if (frame >= 2) u8g2.drawCircle(x + 10, y + 5, 8, U8G2_DRAW_UPPER_LEFT | U8G2_DRAW_UPPER_RIGHT);
    if (frame >= 3) u8g2.drawCircle(x + 10, y + 5, 11, U8G2_DRAW_UPPER_LEFT | U8G2_DRAW_UPPER_RIGHT);
}

static void drawBeaconIdle() {
    UiTheme::drawHeader(u8g2, "BEACON SPAM", "READY");
    drawBeaconIcon(15, 27, (millis() / 160) % 4);
    u8g2.setFont(u8g2_font_6x10_tr);
    u8g2.drawStr(47, 36, "BEACONS");
    u8g2.setFont(u8g2_font_5x7_tr);
    u8g2.drawStr(48, 48, "READY");
    UiTheme::drawMiniWave(u8g2, 49, 62, millis() / 100);
}

static void drawBeaconActive(int frame) {
    UiTheme::drawHeader(u8g2, "BEACON SPAM", "ON");
    drawBeaconIcon(11, 29, frame);
    u8g2.setFont(u8g2_font_6x10_tr);
    u8g2.drawStr(43, 31, "INJECTING");
    u8g2.setFont(u8g2_font_5x7_tr);
    u8g2.setCursor(44, 42);
    u8g2.print("SSID "); u8g2.print(total_ssids);
    for (int b = 0; b < 8; b++) {
        int barHeight = 3 + ((frame + b * 2) % 14);
        u8g2.drawBox(45 + b * 9, 63 - barHeight, 5, barHeight);
    }
}

const char* ssids[] = {
    "👹You_Are_An_Asshole", "💀WiFi_For_Assholes", "😈Free_WiFi", "📡Hey_You_In_Black",
    "🔥Put_The_Vagina_In_Me", "👾I_Am_Watching_You", "💣Dwarfs_and_horses", "😱Gay_porn",
    "🤖AMLO_is_a_faggot", "🔞Only_Morena_AMLO", "🧠Sheinbaum_sucks_it", "⚠️Whoever_reads_is_a_faggot",
    "🐍Connect_and_I_hack_you", "💥May_The_Devil_Bless_You", "🔍Suck_my_dick", "👽Pay_for_your_internet", 
    "🔥Fucking_Poor", "💾Free_Whores", "🚨I_Fucked_Your_Mom", "🖕Suck_A_Lemon_Asshole",
    "🤌Your_Mom_Is_A_Man", "🤡Whoever_Connects_Is_A_Clown", "🧼Bathe_You_Pig", "🕵️Cisen_Unit_04",
    "👮Space_Patrol_69", "🤮Your_Face_Is_Gross", "🍄I_Sell_Magic_Mushrooms", "🧨Caution_Explosive",
    "🌚I_Like_You_When_Quiet", "🥀Virgin_At_40", "🍗Free_Fried_Chicken", "🍖Smells_Like_Death",
    "🦶I_Love_Your_Feet", "👅Lick_My_Spit", "🧟Zombie_In_Your_Garage", "👺I_Am_Your_Father_SOB",
    "🍕Pineapple_Pizza_Sux", "🌑Dark_As_Your_Conscience", "💊Take_Your_Medicine", "📉Your_IQ_Is_0"
};
int total_ssids = 40; 

// Improved packet structure for compatibility
uint8_t packet[150] = { 
    0x80, 0x00, 0x00, 0x00, 
    0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 
    0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 
    0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
    0x64, 0x00, 0x11, 0x04 // ESS capability + short preamble
};

void drawXAntenna(int x, int y, int frame) {
    u8g2.drawTriangle(x+4, y+10, x+8, y+2, x+12, y+10); 
    u8g2.drawDisc(x+8, y+2, 2); 
    if (frame >= 1) u8g2.drawCircle(x+8, y+2, 4, U8G2_DRAW_UPPER_LEFT|U8G2_DRAW_UPPER_RIGHT);
    if (frame >= 2) u8g2.drawCircle(x+8, y+2, 7, U8G2_DRAW_UPPER_LEFT|U8G2_DRAW_UPPER_RIGHT);
    if (frame >= 3) u8g2.drawCircle(x+8, y+2, 10, U8G2_DRAW_UPPER_LEFT|U8G2_DRAW_UPPER_RIGHT);
}

void beaconSpamLoop() {
    if (digitalRead(32) == LOW) { 
        isSpamming = !isSpamming;
        if (isSpamming) {
            WiFi.mode(WIFI_STA);
            esp_wifi_set_promiscuous(true);
        } else {
            esp_wifi_set_promiscuous(false);
            WiFi.mode(WIFI_OFF);
        }
        delay(400);
    }

    if (isSpamming) {
        while (isSpamming) {
            for (int i = 0; i < total_ssids; i++) {
                // --- IPHONE 13 BYPASS IMPROVEMENT: RANDOM MAC ---
                packet[10] = 0x00; packet[11] = 0x16; packet[12] = 0xEA; // Vendor Intel/Cisco
                packet[13] = random(0, 255); packet[14] = random(0, 255); packet[15] = (uint8_t)i;
                memcpy(&packet[16], &packet[10], 6); // BSSID = Source

                // SSID
                int len = strlen(ssids[i]);
                packet[36] = 0x00; packet[37] = len; 
                for (int j = 0; j < len; j++) packet[38 + j] = ssids[i][j]; 
                
                int p = 38 + len;
                // Rates (crucial for iPhone)
                packet[p++] = 0x01; packet[p++] = 0x08;
                packet[p++] = 0x82; packet[p++] = 0x84; packet[p++] = 0x8b; packet[p++] = 0x96;
                packet[p++] = 0x24; packet[p++] = 0x30; packet[p++] = 0x48; packet[p++] = 0x6c;

                // Channel
                packet[p++] = 0x03; packet[p++] = 0x01;
                int ch = random(1, 11); // Avoid problematic high channels
                packet[p++] = (uint8_t)ch;

                // --- IPHONE 13 BYPASS IMPROVEMENT: RSN (WPA2) ---
                packet[p++] = 0x30; packet[p++] = 0x14; 
                packet[p++] = 0x01; packet[p++] = 0x00; packet[p++] = 0x00; packet[p++] = 0x0f;
                packet[p++] = 0xac; packet[p++] = 0x04; packet[p++] = 0x01; packet[p++] = 0x00;
                packet[p++] = 0x00; packet[p++] = 0x0f; packet[p++] = 0xac; packet[p++] = 0x04;
                packet[p++] = 0x01; packet[p++] = 0x00; packet[p++] = 0x00; packet[p++] = 0x0f;
                packet[p++] = 0xac; packet[p++] = 0x02; packet[p++] = 0x00; packet[p++] = 0x00;

                esp_wifi_set_channel(ch, WIFI_SECOND_CHAN_NONE);
                esp_wifi_80211_tx(WIFI_IF_STA, packet, p, false);
                
                // --- ANIMATION MANAGEMENT ---
                if (millis() - lastAnimUpdate > 100) {
                    lastAnimUpdate = millis();
                    animFrame = (animFrame + 1) % 4;
                    u8g2.clearBuffer();
                    drawBeaconActive(animFrame);
                    u8g2.sendBuffer();
                }

                if (digitalRead(25) == LOW) { 
                    isSpamming = false;
                    esp_wifi_set_promiscuous(false);
                    WiFi.mode(WIFI_OFF);
                    return;
                }
            }
            yield();
        }
    } else {
        u8g2.clearBuffer();
        drawBeaconIdle();
        u8g2.sendBuffer();
    }
}
