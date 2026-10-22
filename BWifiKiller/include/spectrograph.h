#ifndef SPECTROGRAPH_H
#define SPECTROGRAPH_H

#include <Arduino.h>
#include <U8g2lib.h>

// New lifecycle
void spectrographEnter();
void spectrographLoop();
void spectrographExit();

// Backward compatibility: alias for enter
void spectrographSetup();

#endif