#pragma once
// B/C defaults transcribed from Figure 6.1, not an electrically verified pinout.
// Override these macros in platformio.ini after checking the actual boards.
#ifndef SENTINEL_SPI_SCK
#define SENTINEL_SPI_SCK 18
#define SENTINEL_SPI_MISO 19
#define SENTINEL_SPI_MOSI 23
#endif
#ifndef SENTINEL_CC_CS
#define SENTINEL_CC_CS 5
#define SENTINEL_CC_GDO0 2
#endif
#ifndef SENTINEL_RFID_CS
#define SENTINEL_RFID_CS 21
#define SENTINEL_RFID_RST 22
#endif
#ifndef SENTINEL_IR_TX
#define SENTINEL_IR_TX 19
#define SENTINEL_IR_RX 21
#endif
// Keep outputs disabled until wiring/output-stage verification by the operator.
#ifndef SENTINEL_ENABLE_IR_TX
#define SENTINEL_ENABLE_IR_TX 0
#endif
