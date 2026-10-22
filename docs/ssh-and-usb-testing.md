# Test the Raspberry Pi and ESP over SSH

Updated 2026-10-22. The Pi runs Raspberry Pi OS. The ESP connects to it using a
USB data cable. Normal diagnostic operation needs no button presses or screen
interaction. SSH controls the Pi; the Pi diagnostic client exchanges requests
with the ESP over USB serial.

## What is available

| Check/control | Available behavior |
| --- | --- |
| Pi local checks | Existing interface, loopback HTTP and Nmap checks |
| Pi application | Start/stop in an SSH shell; inspect or cancel through its local HTTP API |
| USB enumeration | Lists serial ports without opening them; does not identify firmware |
| ESP round trip | New diagnostic firmware answers a request with its unique ID |
| ESP radio checks | Reads whether each nRF24 responds over SPI; does not transmit RF |
| ESP button inputs | Reads existing GPIO levels; does not emulate presses or remap controls |
| Physical switches, display, touch, antennas | Not verified by these electronic self-tests |

The new source implements a diagnostic interface, not full ESP tool control or
Wi-Fi/BLE/RF scan-result streaming. Existing ESP Toolkit records remain manual.
The installed ESP cannot answer until this updated firmware is flashed. Bundled
files under `BWifiKiller/binarios/` still contain the original firmware.

## Enable SSH and connect

If SSH is not already enabled, enable it once in Raspberry Pi OS using
`sudo raspi-config` -> Interface Options -> SSH. You can also enable SSH when
preparing the SD card with Raspberry Pi Imager. Use your configured username,
not an assumed `pi` account. See the
[official SSH setup](https://www.raspberrypi.com/documentation/computers/remote-access.html#ssh).

On your computer, replace `USERNAME` and `PI_ADDRESS` with the Pi's account and
hostname/IP. This opens a shell and forwards the website to your computer:

```bash
ssh -L 18088:127.0.0.1:8088 USERNAME@PI_ADDRESS
```

`BWifiKiller/` is included directly in the main repository, including the USB
diagnostic source, original documentation, and license. No separate firmware
clone or submodule setup is required. Once the changes are committed and pushed:

```bash
git clone https://github.com/Tudor747/ananas.git
```

Local uncommitted changes are not delivered by cloning GitHub. A fresh clone is
the simplest setup if an older checkout contains a separately cloned
`BWifiKiller/` repository; preserve any local work before replacing that checkout.
If copying files instead, include `BWifiKiller/` but exclude Windows virtual
environments and `.pio` build directories. The commands below assume `~/ananas`.

## Pi setup and checks in the SSH shell

```bash
cd ~/ananas
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nmap iproute2
bash run.sh --setup
source .venv/bin/activate
python -m pip install -e ".[hardware]"
bash run.sh --check --no-install
```

If the launcher selected `.venv-linux` because a Windows environment was copied,
activate `.venv-linux/bin/activate` instead. Python 3.11+ is required.

Start the website with `bash run.sh --no-install`. Leave this SSH session open
and use a second SSH shell for other commands. Open **http://127.0.0.1:18088** on
your computer to use the Pi dashboard through the tunnel. The Pi website stays
bound to loopback. Ctrl+C in its shell stops it. Automatic boot startup and the
new two-option touch menu remain separate work.

These commands work in the second SSH shell while the website is running:

```bash
curl --fail http://127.0.0.1:8088/api/health
curl --fail http://127.0.0.1:8088/api/state
curl --fail -X POST http://127.0.0.1:8088/api/cancel
```

## Identify the USB connection

Activate the same Python environment in this shell. Plug the ESP into the Pi,
then list ports:

```bash
cd ~/ananas
source .venv/bin/activate
python -m pi_ot_probe.diagnostics.esp_check --list
ls -l /dev/serial/by-id/
```

Use the entry corresponding to your ESP. Compare before/after plugging it in
if there are multiple ports. Set `ESP_PORT` to the actual path, for example:

```bash
ESP_PORT='/dev/serial/by-id/REPLACE_WITH_YOUR_ESP_ENTRY'
```

Some devices do not provide a stable by-id name; use their listed `/dev/ttyUSB0`
or `/dev/ttyACM0` path instead. A listed USB-to-serial adapter proves enumeration,
not that the ESP application or radios work.

For a serial permission error, check `ls -l "$ESP_PORT"` and `id`. On Pi OS the
port is normally owned by group `dialout`. If so, add your account once:

```bash
sudo usermod -aG dialout "$USER"
```

Disconnect and reconnect SSH for the group change to apply. Close other serial
monitors before testing or uploading. Do not run the whole application as root.

## Install the diagnostic firmware once

This replaces the ESP's installed firmware with the updated local source;
the physical button mapping is preserved. Source
and installed firmware may differ, including interface language. Retain your
original firmware backup if you need to restore the exact installed build.

With the ESP attached to the Pi, build and upload from the SSH shell:

```bash
python -m pip install platformio
python -m platformio run -d BWifiKiller -e esp32diag
python -m platformio run -d BWifiKiller -e esp32diag -t upload --upload-port "$ESP_PORT"
```

The `esp32diag` profile keeps the standard SDK's raw-frame validation. The legacy
`esp32dev` profile requires a separately patched SDK and otherwise fails to link
with a duplicate `ieee80211_raw_frame_sanity_check` symbol. USB tests do not need
that override; raw-frame bypass-dependent features are not supported by the
diagnostic profile. No shared SDK files are modified.

The first build needs internet access and downloads the ESP32 toolchain and
libraries. Do not upload an old file from `binarios/` for this feature. Automatic
upload depends on the board's USB reset circuit. If it cannot enter the
bootloader automatically, a one-time physical BOOT/reset step may be necessary;
normal self-tests do not require those buttons.

## Run the ESP self-test

```bash
python -m pi_ot_probe.diagnostics.esp_check --port "$ESP_PORT" --output data/esp-check.json
```

The command sends only `PING` and `SELFTEST` at 115200 baud, with bounded waits,
fresh request IDs, and retries during startup. It does not launch ESP tools or
write configuration. DTR/RTS are deasserted before opening; some USB drivers can
still reset the board when opening a port. The client waits for startup replies.

- `usb_round_trip: passed`: a matching protocol reply arrived from the ESP.
- `nrf1_spi` / `nrf2_spi`: each chip responded to the SPI connection check.
- `button_pin_levels: observed`: current input levels only; 0 is low/pressed
  and 1 high/released with the reference pull-up wiring. AUX may be unwired on
  the user's four-button assembly; an unwired pull-up can read high normally.
- Exit 0: all implemented electronic checks passed. This is not a whole-device
  certification; the report lists untested components.
- Exit 1: serial/protocol failure, malformed observations, or a failed radio check.
- Exit 2: ESP replied but has an active tool, so its self-test was skipped.

The firmware polls diagnostics from its main loop. A tool with a blocking loop
can delay all replies until it returns; a timeout alone does not prove broken
hardware. Start from the idle menu after power-up for hands-off diagnostics.
The test does not toggle the on/off switch or draw test patterns. Physical
button movement, switch operation, display pixels, touch accuracy, and antenna
performance still need physical observation or a separate test fixture.

## Protocol and validation

Requests are newline-delimited ASCII: `PIOT1 PING ID` or `PIOT1 SELFTEST ID`.
IDs contain 1-32 alphanumeric characters. Responses are one-line JSON with
`protocol: piot-usb-v1`, the same `id`, `command`, and `status`. Unknown or
oversized requests are ignored. `SELFTEST` returns `busy` while a tool runs.
The Python client ignores unrelated boot logs and stale/wrong-protocol replies.

Host tests compile the actual C++ diagnostic handler against hardware stubs and
exercise it using the Python client. This verifies interoperability, malformed
input handling, busy states, and failed radio reporting, not real hardware.

Local validation on 2026-10-22: all 57 Python tests passed, including the native
C++ handler/client tests. PlatformIO built `esp32diag` successfully (1,775,389
bytes flash, 80,960 bytes static RAM). The artifact is generated at
`BWifiKiller/.pio/build/esp32diag/firmware.bin`; it is not an updated bundled
binary or proof of hardware behavior. No Pi deployment or ESP flashing was
performed. The user will clone and run the hardware checks over their existing
SSH connection.

Implementation references:
[pySerial API](https://pyserial.readthedocs.io/en/latest/pyserial_api.html),
[RF24 chip connection check](https://nrf24.github.io/RF24/classRF24.html), and
[ESP32 USB reset behavior](https://docs.espressif.com/projects/esptool/en/latest/esp32/advanced-topics/boot-mode-selection.html).
