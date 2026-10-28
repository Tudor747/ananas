# RF Sentinel X: three-node integration

For the first PCB test, start with [ESP1-first setup](first-pcb-test.md).

The Raspberry Pi 5 owns the menu at `http://127.0.0.1:8088/console`.
The existing network assessment remains at `/`. Its network limits and collectors
are unchanged, including OS-provided Wi-Fi inventory on the Pi. No monitor mode,
packet injection, or additional 5 GHz acquisition capability is implied.

The new firmware runs without a local menu. The Pi sends a named command, arguments,
and request ID to a particular USB node; the node acknowledges it and sends events.
A plain “OK” would not identify which operation or node the user selected.

## Implemented source

| Node | Profile | Operations |
| --- | --- | --- |
| A | `firmware`, `node_a` | Two nRF SPI checks and carrier observations; explicit single-packet nRF1→nRF2 test; passive ESP Wi-Fi and BLE inventories |
| B | `firmware`, `node_b` | CC1101 receive RSSI and compatible default-profile packets at 433.92 MHz; RC522 tag-family observations with UID redacted |
| C | `firmware`, `node_c` | KY-022 IR decoding; optional single 32-bit NEC transmission via KY-005 |

`node_a` is the headless profile in `firmware/`, sharing the established nRF pin
configuration in `BWifiKiller/include/app_config.h`. The older `sentinel_a` profile
is a compatibility entry point to the same source. It does not link or remotely execute the legacy
menu tools. Original `esp32dev`/`esp32diag` builds remain available separately.
There is no generic remote command to invoke jamming, deauthentication or portal tools.
The old `piot-usb-v1` PING/SELFTEST interface is separate from the new protocol.

All three firmware profiles target the existing classic `esp32dev` build platform.
The actual ESP32 variants remain unknown. Verify the board markings before flashing;
successful compilation does not establish ESP32-C3/S3 compatibility.

## GPIO defaults

GPIO numbers below are signal numbers, **not header positions**.

| Node | Signal | GPIO | Source |
| --- | --- | --- | --- |
| A | nRF1 CE / CSN | 5 / 17 | Existing `BWifiKiller/include/app_config.h` |
| A | nRF2 CE / CSN | 16 / 4 | Existing code |
| A/B | SPI SCK / MISO / MOSI | 18 / 19 / 23 | Classic ESP32 SPI defaults / report Figure 6.1 |
| B | CC1101 CS / GDO0 | 5 / 2 | Preliminary report Figure 6.1 |
| B | RC522 SS / RST | 21 / 22 | Preliminary report Figure 6.1 |
| C | KY-005 TX / KY-022 RX | 19 / 21 | Preliminary report Figure 6.1 |

B/C assignments are transcribed design defaults, not verified wiring instructions.
Check them against the actual modules, supply rails and board variants. Overrides
are in `firmware/include/sentinel_pins.h`. The screenshot does not validate power
connections, LED drive current or boot-pin behavior. No assembly was tested here.

## Build and manually flash

Install PlatformIO Core. From the repository root:

```sh
pio run -d firmware -e node_a
pio run -d firmware -e node_b -e node_c
```

After identifying each board and verifying its wiring, manually upload one at a time:

```sh
pio run -d firmware -e node_a -t upload --upload-port YOUR_A_PORT
pio run -d firmware -e node_b -t upload --upload-port YOUR_B_PORT
pio run -d firmware -e node_c -t upload --upload-port YOUR_C_PORT
```

IR output defaults to disabled. After verifying KY-005's output stage, build and
upload the explicit `node_c_ir_tx` profile instead of `node_c`:

```sh
pio run -d firmware -e node_c_ir_tx
pio run -d firmware -e node_c_ir_tx -t upload --upload-port YOUR_C_PORT
```

Each command sends one NEC frame, with no repeats.
The host requires an operator, test purpose and affirmative authorization for
observations/configuration/transmissions. RFID observation energizes the reader;
it is not passive RF reception. Neither nRF nor IR transmission retries automatically.

## Identify and configure USB nodes

Use the project's Python environment:

```sh
python -m pip install -e ".[hardware]"
python -m pi_ot_probe.peripherals.provision --list
python -m pi_ot_probe.peripherals.provision --node A --port YOUR_A_PORT
python -m pi_ot_probe.peripherals.provision --node B --port YOUR_B_PORT
python -m pi_ot_probe.peripherals.provision --node C --port YOUR_C_PORT
```

Provisioning opens only the named port and performs HELLO. It prints the device's
stable eFuse identity; it does not prove peripheral health. Each serial monitor
must be closed before the application opens its port. Prefer `/dev/serial/by-id/...`
on Linux; where bridge serial numbers are absent/duplicated use unique by-path
names and preserve USB socket assignments. An identity mismatch is rejected.

Copy `deployment/nodes.example.json` to `data/nodes.json`, replacing its values with
the three provisioning results. Partial configuration is allowed while bringing up
one node at a time. Duplicate roles, device identities and ports are rejected.

Linux:

```sh
export RF_SENTINEL_NODES="$PWD/data/nodes.json"
bash run.sh
```

PowerShell:

```powershell
$env:RF_SENTINEL_NODES = "$PWD/data/nodes.json"
.\run.ps1
```

With no configuration, the app still opens and shows all nodes as unconfigured.
Run a single Uvicorn worker: several workers must not compete for the same ports.
Node IDs are local allowlist checks, not cryptographic device authentication.

The native tablet's USB Setup picker also prefers stable Linux names and checks
for aliases of a port already assigned to another node. See the
[three-board tablet workflow](tablet-app.md#working-with-all-three-boards).
Routine unchanged background STATUS records are suppressed to limit idle
database growth; operator STATUS requests, health changes and failures are retained.

All three configured boards can remain plugged in: each has its own USB worker
and session. The native tablet runs one foreground tool at a time while maintaining
all three connections; the transport supports observations on separate nodes at
the same time. Automated serial fixtures cover simultaneous A/B/C observations,
event attribution, and B reconnecting while A/C continue answering commands.
These tests do not verify USB power, cabling, or actual sensor behavior.

## Screen operation

Open `/console`. It presents two module buttons per page, vertical swipe paging,
large Previous/Next controls, node connection states, operator/test inputs and
Stop All. The layout adapts to viewport dimensions; no HSD28309 EI resolution is
assumed. Run `bash scripts/sentinel-kiosk.sh` inside the Pi desktop for full-screen
Chromium. Physical GPIO button-to-Pi navigation is not implemented; use touchscreen
or browser keyboard focus controls. ESP button wiring is not repurposed.

Select a module, enter operator/purpose, confirm authorization, and press Observe.
A request being queued is not a successful hardware result: inspect its correlated
reply and events. Use the separate nRF test button for one over-the-air packet.
On the IR page, expand the NEC test panel to send a hexadecimal code if output was
enabled in the firmware build.

## Transport and failure behavior

- 115200 baud; newline-delimited UTF-8 JSON. Host receive limit: 4096 bytes;
  firmware request limit: 1024 bytes. Oversized frames are discarded through newline.
- HELLO binds a fresh random host session to the configured role and device ID.
  Every reply/event includes firmware, boot ID, monotonic device sequence and uptime.
- One worker per node, heartbeat once per second when idle; a missing reply times
  out after four seconds. Reopen attempts wait two seconds. Commands are not replayed
  across connections. A boot-ID change forces a new handshake.
- STOP preempts a pending request and cancels queued work. Firmware observations
  last at most ten seconds; losing valid host traffic stops acquisition after five
  seconds. A single already-started IR/nRF frame finishes before STOP can be processed.
- Sequence gaps and malformed frames are logged. Network operations retain their
  existing independent cancellation workflow.

Request example:

```json
{"v":1,"node":"B","session":"random-host-session","id":12,"command":"OBSERVE","args":{"sensor":"rfid","duration_ms":5000}}
```

Reply/event fields: `v`, `node`, `device`, `boot`, `session`, `firmware`, `seq`,
`uptime_ms`, `type`, `command`, `id`, `health`, `payload`. A reply's ID matches its
request. Observation events carry the originating observation request ID.
Supported commands are HELLO, STATUS, OBSERVE, STOP, nRF SET_CONFIG (channel), and
bounded TRANSMIT (one nRF peer test or one NEC IR code). No arbitrary driver/register
commands are exposed.

## Evidence and limitations

`peripheral_events` in the app's SQLite database keeps operator intent, host actions,
USB replies/events and connection failures separately from manual field notes.
Records include host UTC reception time, node and session. USB fields retain the
device firmware version and boot ID. Device uptime is not a synchronized wall clock.
Firmware versions include a source-content hash and build-profile identity generated
by `firmware/build_identity.py`; retain the pinned dependency manifest with each run.
The timeline is a chronological record, not automatic causal correlation or a
vulnerability assessment of radio activity.

`GET /api/peripheral-events?after=0&limit=200` pages forward by record ID.
`/api/reports/peripherals.json` and `.md` export at most 1000 records per request;
continue with `after=<last_id>`. Preserve every page for a full evidence archive.
The UI shows up to 60 recent records and hides routine STATUS replies.
No retention purge runs automatically; archive and manage the database as needed.

For a clearly labelled offline demonstration, import a previously exported JSON page:

```sh
python -m pi_ot_probe.peripherals.replay saved-peripherals.json
```

Imported device records appear with `replay` provenance and retain their original
receive timestamps inside the record. Replay never opens a USB port, dispatches a
command or makes an offline node appear connected. Repeat for each export page.

No real hardware measurements, screen tests, power tests or USB unplug trials have
been performed by this implementation session. Use the manual acceptance record
below before describing any function as physically verified.

## Manual acceptance record

For every run record: operator, UTC date, source commit/build, board markings,
firmware hashes, wiring revision, power supply, stimulus, expected result, actual
result, raw export filenames and failures. Keep failed trials too.

| Test | Procedure | Evidence to retain |
| --- | --- | --- |
| H01 | Identify A/B/C, swap USB enumeration order, unplug one while others operate | Identity/session records; offline state; unaffected peers |
| H02 | Observe both nRF chips, then send one nRF1→nRF2 test packet | SPI health, TX completion and matching received-packet result separately |
| H03 | Apply a compatible known 433.92 MHz FSK stimulus | Peer settings, RSSI, packet validity; no arbitrary-protocol claim |
| H04 | Present compatible and incompatible RFID tags; repeat removals/readings | Redacted tag-family events and trial counts |
| H05 | Receive a known remote; enable verified TX stage and send one NEC code | Received code, transmitted frame status, target response; stop behavior |
| H06 | Record Pi screen connector/resolution and test all menu pages | Touch, swipe, button navigation, readable screenshots |
| H07 | Measure supply rails and resets under simultaneous operation | Actual voltage/current/temperature readings and setup |
| H08 | Export records, restart app, verify persistence and request correlation | Complete paginated JSON, firmware/build identifiers and repeated runs |

## Driver references

Driver usage follows the upstream [MFRC522 examples](https://github.com/miguelbalboa/rfid),
[RadioLib CC1101 API](https://jgromes.github.io/RadioLib/class_c_c1101.html), and
[IRremoteESP8266 API](https://crankyoldgit.github.io/IRremoteESP8266/doxygen/html/).
Pinned versions are in the PlatformIO manifests. These libraries do not establish
the electrical correctness of the actual assembly.
