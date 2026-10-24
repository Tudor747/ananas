# Firmware for the three ESP boards

Build and upload from the repository root. All current Pi-controlled firmware is
under this directory; each ESP gets only its own profile.

| Board label | USB role | Hardware assumed by the source | Profile | Source |
| --- | --- | --- | --- | --- |
| ESP1 | A | Two nRF24L01+ 2.4 GHz modules | `node_a` | `src/node_a.cpp` |
| ESP2 | B | CC1101 433 MHz + RC522 RFID | `node_b` | `src/node_b.cpp` |
| ESP3 | C | KY-022 IR receiver + KY-005 transmitter | `node_c` (receive first) | `src/node_c.cpp` |

```sh
pio run -d firmware -e node_a
pio run -d firmware -e node_b
pio run -d firmware -e node_c
```

Append `-t upload --upload-port YOUR_PORT` to upload the selected profile.
All profiles currently target classic `esp32dev`; verify board/module markings
and PCB wiring before uploading. IR output requires the separate `node_c_ir_tx`
profile after checking the output circuit.

- `include/sentinel_protocol.h`: shared USB JSON protocol.
- `include/sentinel_pins.h`: ESP2/ESP3 pin defaults and IR output switch.
- `../BWifiKiller/include/app_config.h`: established ESP1 PCB pin map.
- `build_identity.py`: source/profile fingerprint embedded in firmware.
- `../BWifiKiller/`: earlier standalone firmware; its `sentinel_a` environment
  remains compatible and includes the canonical `src/node_a.cpp`.

Start with [the first-PCB walkthrough](../docs/first-pcb-test.md).
