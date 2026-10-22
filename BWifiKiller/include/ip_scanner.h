#ifndef IP_SCANNER_H
#define IP_SCANNER_H

#include <Arduino.h>

// New lifecycle
void ipScannerEnter();
void ipScannerLoop();
void ipScannerExit();

// Backward compatibility: alias for enter
void ipScannerSetup();

#endif