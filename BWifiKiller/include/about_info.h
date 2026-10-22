#ifndef ABOUT_INFO_H
#define ABOUT_INFO_H

#include <Arduino.h>

void aboutEnter();   // NEW: called once by Host.launch()
void aboutLoop();
void aboutExit();    // NEW: called once by Host.shutdown()

#endif