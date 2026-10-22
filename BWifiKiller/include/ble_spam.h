#ifndef BLE_SPAM_H
#define BLE_SPAM_H

#include <Arduino.h>

// BLE SPAM: transmits fake BLE advertisements.
// Protocols: Apple Continuity, Samsung, Microsoft Swift Pair, and Google.
// CHAOS MODE rotates through protocols for controlled testing.
// Educational/demo use: run only in your own or an authorized lab.

void runBLESpam();
void bleSpamEnter();
void bleSpamLoop();
void bleSpamExit();

#endif
