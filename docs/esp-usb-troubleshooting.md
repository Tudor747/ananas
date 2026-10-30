# ESP identity and hardware checks after merging temp into mama

## The nRF and 433 MHz boards

| Physical board | Firmware profile | Reported role |
| --- | --- | --- |
| Dual nRF24 PCB | `node_a` | A |
| CC1101 433 MHz + optional RC522 | `node_b` | B |
| Infrared board | `node_c` | C |

The USB handshake reports the role compiled into the firmware, plus the ESP's
unique chip ID. Changing USB sockets or choosing a different role in the menu
does not change that firmware. If only the nRF and 433 MHz boards are attached
and a fresh identification reports C, inspect their flashed profiles. The app
must not silently rename that board to A.

1. Stop other copies of the tablet app, web console and serial monitors.
2. Leave all boards connected. Use System → USB Setup → Find & connect.
   Each USB port is identified independently; a timeout on the infrared board
   does not discard successful identification of the nRF and 433 MHz boards.
   Record reported roles, chip IDs and ports. A firmware mismatch must be
   corrected on the verified physical board, not bypassed by selecting another role.
3. The app prefers stable
   `/dev/serial/by-path/` names for bridges with duplicate USB serial numbers.
   `/dev/ttyUSB0` and `/dev/ttyUSB1` can swap after reconnection.
4. Open Devices to distinguish **USB connected** from a peripheral SPI failure.

For a text inspection on the Pi, stop the app first, leave all boards plugged
in, then use its Python:

```sh
.venv-pi/bin/python -m pi_ot_probe.peripherals.provision --inspect-all
```

The report includes each USB port, firmware role, chip ID and available radio
checks. Failed ports have their own error entries. No assignments are saved.
Each probe has an eight-second HELLO window and a 25-second process limit to
allow Python startup and USB opening on the Pi. A process timeout includes
the last reported step; it does not establish the board's identity. Older ESP
firmware may not provide individual radio checks. Close serial monitors and
the web console too, so they do not compete for the ports.

To inspect a specific endpoint instead:

```sh
.venv-pi/bin/python -m pi_ot_probe.peripherals.provision --list
.venv-pi/bin/python -m pi_ot_probe.peripherals.provision --node auto --port /dev/ttyUSB0 --inspect
```

Replace the port with the endpoint actually listed. Inspection sends only HELLO
and does not save a configuration or flash firmware. With current firmware it
also returns `nrf1_spi`/`nrf2_spi` or `cc1101_spi`/`rc522_spi` in `hardware`.
Older firmware can identify correctly but supplies no per-peripheral details.

## What HW error means

A working USB handshake can coexist with a failed peripheral. Node A expects
both nRF modules to initialize; this behavior is unchanged. Node B supports
CC1101 alone, RC522 alone, or both. It reports ready when at least one initializes
and error when neither initializes. Each peripheral's check remains visible;
commands for a missing or failed module return a specific unavailable error.
Older node B firmware may report an aggregate error when only one module is
present. Flash the updated `node_b` firmware to apply this change; updating the
Pi app alone is insufficient. Wi-Fi/BLE on A remain usable despite an nRF error.

New firmware supplies the individual initialization results in HELLO/STATUS,
and Devices displays each check. These are SPI initialization checks, not an
antenna/range or over-the-air link test. For an nRF failure check both modules,
3.3 V power, common ground and the PCB's CE/CSN/SPI connections. Node A reports
the configured CE/CSN pins and SPI clock in its inspection response.

Build the intended profile before flashing the single identified board:

```sh
python -m platformio run -d firmware -e node_a
python -m platformio run -d firmware -e node_a -t upload --upload-port YOUR_NRF_BOARD_PORT
```

Use `node_b` for the 433 MHz board. The merge itself does not flash any hardware.

## Software corrections

- Ignore buffered replies from older USB sessions before checking their role.
  Fresh replies still must match both configured role and chip ID.
- Find & connect replaces stale assignments whose endpoint or chip is now
  occupied by an identified board, reports the replacements and keeps the
  previous configuration in `nodes.json.bak`. Unrelated absent boards are retained.
- Role mismatch errors show the actual chip, firmware and required profile.
- Devices separates USB connectivity from individual peripheral failures.
- Closing the app without using standby no longer tries to toggle USB power.

The merge retains mama's Wi-Fi browser/radar and temp's GPIO16 standby, USB power
control, cursor positioning and bounded lab tools. GPIO16's existing OFF→ON
reboot behavior is retained. Those Pi-specific power/display actions require
physical verification; no USB power commands or reboot were run on the Pi here.
