#ifndef DEAUTHER_H
#define DEAUTHER_H

#include <Arduino.h>

// ═══════════════════════════════════════════════════════════════════════════
//  DEAUTHER - disconnects WiFi clients using deauth frames
//  · Scan APs → Select AP → [Scan clients | Broadcast | Rambo mode]
//  * Educational/pentesting use on your own networks
//  * USE ON OTHER PEOPLE'S NETWORKS IS ILLEGAL
// ═══════════════════════════════════════════════════════════════════════════

void runDeauther();

#endif
