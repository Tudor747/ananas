#pragma once

#include <stddef.h>
#include <string.h>

namespace UsbDiagnostics {
enum class Command { None, Ping, SelfTest };

// Fixed-size framing, independent of Arduino so malformed input can be tested
// on a host. Oversized lines are discarded in full, including command-like tails.
class Parser {
public:
    Command feed(char value) {
        if (value == '\n') {
            Command command = Command::None;
            if (!overflow) {
                if (used && line[used - 1] == '\r') --used;
                line[used] = '\0';
                const char* token = nullptr;
                if (strncmp(line, "PIOT1 PING ", 11) == 0) {
                    command = Command::Ping;
                    token = line + 11;
                } else if (strncmp(line, "PIOT1 SELFTEST ", 15) == 0) {
                    command = Command::SelfTest;
                    token = line + 15;
                }
                if (token) {
                    const size_t length = strlen(token);
                    if (!length || length > 32) command = Command::None;
                    for (size_t i = 0; i < length; ++i) {
                        const char c = token[i];
                        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                              (c >= '0' && c <= '9'))) command = Command::None;
                    }
                    if (command != Command::None) strcpy(requestId, token);
                }
            }
            used = 0;
            overflow = false;
            return command;
        }
        if (static_cast<unsigned char>(value) < 32 && value != '\r') overflow = true;
        if (!overflow) {
            if (used < sizeof(line) - 1) line[used++] = value;
            else overflow = true;
        }
        return Command::None;
    }

    const char* id() const { return requestId; }

private:
    char line[80] = {};
    char requestId[33] = {};
    size_t used = 0;
    bool overflow = false;
};
} // namespace UsbDiagnostics
