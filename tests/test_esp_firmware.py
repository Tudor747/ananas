"""Compile the actual diagnostic handler against host hardware stubs.

This tests framing and Python/C++ interoperability, not physical hardware.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from pi_ot_probe.diagnostics.esp_check import run_checks

ROOT = Path(__file__).resolve().parents[1]


class FirmwareProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("g++")
        if not compiler:
            raise unittest.SkipTest("g++ is needed for the native firmware protocol test")
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        folder = Path(cls.directory.name)
        (folder / "Arduino.h").write_text('''#pragma once
#include <cstdint>
#include <cstdio>
#include <string>
using String = std::string;
struct MockSerial {
    std::string input;
    size_t index = 0;
    int available() { return input.size() - index; }
    int read() { return input[index++]; }
    template<typename... Args> void printf(const char* fmt, Args... args) { std::printf(fmt, args...); }
    void println(const char* text) { std::puts(text); }
};
extern MockSerial Serial;
inline unsigned long millis() { return 1234; }
inline int digitalRead(int pin) { return pin == 26 ? 0 : 1; }
''', encoding="utf-8")
        (folder / "RF24.h").write_text('''#pragma once
struct RF24 { bool connected = true; bool isChipConnected() { return connected; } };
''', encoding="utf-8")
        (folder / "main.cpp").write_text('''#include <iostream>
#include <iterator>
#include "Arduino.h"
#include "RF24.h"
#include "usb_diagnostics.h"
MockSerial Serial;
RF24 jam1, jam2;
int main(int argc, char** argv) {
    const std::string mode = argc > 1 ? argv[1] : "idle";
    jam2.connected = mode != "missing";
    Serial.input = std::string(std::istreambuf_iterator<char>(std::cin), {});
    while (Serial.available()) pollUsbDiagnostics(mode == "busy");
}
''', encoding="utf-8")
        cls.binary = folder / ("firmware-test.exe" if os.name == "nt" else "firmware-test")
        subprocess.run([compiler, "-std=c++11", "-static", "-I", str(folder), "-I",
                        str(ROOT / "BWifiKiller/include"), str(folder / "main.cpp"),
                        str(ROOT / "BWifiKiller/src/usb_diagnostics.cpp"), "-o", str(cls.binary)],
                       check=True, capture_output=True, timeout=60)

    def invoke(self, data, mode="idle"):
        return subprocess.run([str(self.binary), mode], input=data, capture_output=True,
                              check=True, timeout=5).stdout

    def test_python_client_against_actual_cpp_handler(self):
        invoke = self.invoke
        class Port:
            def __init__(self, mode):
                self.pending = b""
                self.mode = mode
            def write(self, data):
                self.pending += invoke(data, self.mode)
                return len(data)
            def read(self, count):
                data, self.pending = self.pending[:count], self.pending[count:]
                return data
        for mode, status in (("idle", "passed"), ("busy", "partial"), ("missing", "failed")):
            with self.subTest(mode=mode):
                report = run_checks(Port(mode), 2)
                self.assertEqual(report["status"], status)
                if mode == "idle":
                    self.assertEqual(report["checks"][-1]["levels"]["up"], 0)

    def test_invalid_frames_do_not_trigger_commands_and_parser_recovers(self):
        invalid = [b"PIOT1 START abc\n", b'PIOT1 PING bad"id\n', b"PIOT1 PING \n",
                   b"PIOT1 PING " + b"a" * 33 + b"\n", b"PIOT1 PING abc\x00\n",
                   b"X" * 100 + b"PIOT1 SELFTEST hidden\n"]
        for frame in invalid:
            with self.subTest(frame=frame):
                self.assertEqual(self.invoke(frame), b"")
                output = self.invoke(frame + b"PIOT1 PING next123\r\n")
                self.assertEqual(output.count(b'"command":"PING"'), 1)
                self.assertIn(b'"id":"next123"', output)
