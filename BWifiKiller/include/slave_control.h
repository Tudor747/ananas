#ifndef SLAVE_CONTROL_H
#define SLAVE_CONTROL_H

#include <Arduino.h>

typedef struct struct_comando {
    bool estado;
} struct_comando;

// Existing API
void slaveControlSetup();
void slaveControlLoop();

// Optional new API
void slaveControlEnter();
void slaveControlExit();

#endif