#ifndef PACKET_MONITOR_H
#define PACKET_MONITOR_H

#include <Arduino.h>

// New lifecycle
void monitorEnter();
void monitorLoop();
void monitorExit();

// Backward compatibility: alias for enter
void monitorSetup();

#endif