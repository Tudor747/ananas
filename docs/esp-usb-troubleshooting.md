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
2. Connect **only the nRF board**. Use System → USB Setup → Find & connect.
   Record its reported role and chip ID. If it reports B/C, verify and flash
   `node_a` to that board's actual USB port; do not select B/C merely to bypass
   the error. Disconnect it and identify the 433 MHz board the same way (B).
3. Reconnect both boards and run Find & connect again. The app prefers stable
   `/dev/serial/by-path/` names for bridges with duplicate USB serial numbers.
   `/dev/ttyUSB0` and `/dev/ttyUSB1` can swap after reconnection.
4. Open Devices to distinguish **USB connected** from a peripheral SPI failure.

For a text inspection on the Pi, stop the app first, then use its Python:

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
both nRF modules to initialize; node B checks both CC1101 and RC522. A missing
RC522 therefore produces an aggregate hardware error even when CC1101 works.
Wi-Fi/BLE on A and individually healthy sensors on B remain usable.

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
