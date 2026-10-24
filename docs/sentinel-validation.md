# RF Sentinel implementation validation

## Repository organization check: 2026-10-23

- Canonical ESP1 source moved to `firmware/src/node_a.cpp`; the existing
  `BWifiKiller/src/sentinel_main.cpp` is a compatibility include.
- PlatformIO built `firmware` profiles `node_a`, `node_b`, `node_c` and
  `node_c_ir_tx` successfully for classic `esp32dev`.
- Python suite: 73 tests passed in 39.09 seconds.
- Documentation links, ESP1-only JSON template and `git diff --check` passed.
- No USB uploads or physical hardware tests were performed. Follow
  [the ESP1-first guide](first-pcb-test.md) for bench validation.
- The older binary hashes below describe the earlier build, not this revision.

## Earlier integration validation

Date: 2026-10-22 (Europe/Bucharest).

Base repository commit: `a9ff4010e8450165a0be3932ec61d82e3eab4985`. Implementation is in the working tree; no commit or hardware upload was performed.

## Checks completed

- Baseline before implementation: 57 pytest tests passed.
- Final suite: 73 pytest tests passed in 22.36 seconds.
- JavaScript syntax: `node --check src/pi_ot_probe/web/static/js/console.js` passed.
- Local diagnostic: interface enumeration, temporary loopback HTTP and Nmap TCP checks passed. Observations are in `data/local-check.json` (local, ignored).
- Real loopback HTTP tests exercised console assets, command authorization, origin rejection, serial-fixture dispatch, persistent replies and exports.
- Serial fixtures covered three-node isolation, identity mismatch, oversized/fragmented frames, stale sessions, sequence gaps/duplicates, reconnect and STOP preemption.
- PlatformIO compiled node A, B, C and the explicit IR-TX-enabled C profile successfully for classic `esp32dev` with Espressif32 6.4.0 / Arduino 2.0.11.
- `git diff --check` passed (only repository CRLF conversion notices).

## Compiled artifacts

These application binaries are build evidence. Use the documented PlatformIO upload commands so bootloader/partition offsets are handled correctly.

| Profile | Application binary bytes | SHA-256 |
| --- | ---: | --- |
| `sentinel_a` | 1497168 | `a3472351f7bce0d459c87ad8d0f3a28f8882178a4dc125d993ed451f6b4611f5` |
| `node_b` | 309472 | `a4f30b9976e66e26ba94b2b074ba080125adccae8b4576994b9eb36f6adc4171` |
| `node_c` | 353904 | `cdc9af102b82496ab8d51e3c7025ed14ea1bbdbcab3b253b871d523996cdb1c3` |
| `node_c_ir_tx` | 355104 | `3176b8cfb69072fe1d41f1c741f698194c7ba8e4dcd1f60ede18315e51a53854` |

## Not verified

- No physical Pi/ESP USB sessions, radio traffic, RFID reads, IR output, or GPIO/power measurements were performed.
- No touchscreen or visual browser QA was available; HTTP assets and JavaScript syntax were checked. Actual HSD28309 EI geometry and touch remain manual tests.
- Actual ESP variants are still unidentified. The compiled target must match the purchased boards before flashing.
- B/C pin defaults follow the preliminary document schematic, not an as-built electrical review.
- Node A is a new observation-focused headless BWifiKiller profile, not remote access to every legacy menu feature.
- Peripheral evidence is displayed and exported separately from network findings. Temporal proximity is not automatically classified as a security incident.

Use [the manual integration guide](sentinel-integration.md) for configuration, flashing and H01-H08 acceptance tests.
