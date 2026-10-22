#ifndef WIFISCAN_H
#define WIFISCAN_H

#include <Arduino.h>

// New lifecycle (enter/loop/exit pattern)
void wifiscanEnter();
void wifiscanLoop();
void wifiscanExit();

// Backward compatibility: old name retained as an alias for Enter
void wifiscanSetup();

#endif