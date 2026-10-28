# Test ESP1 first, then add ESP2 and ESP3

The Raspberry Pi runs the Python application and touchscreen/browser menu.
Each ESP runs its own firmware and connects to the Pi by USB. You can test ESP1
alone; ESP2 and ESP3 can stay disconnected and unconfigured.

| Your board | App role | Upload this profile | What it tests |
| --- | --- | --- | --- |
| ESP1: two 2.4 GHz antennas | A | `firmware/node_a` | Two nRF24 SPI interfaces and one packet from radio 1 to radio 2 |
| ESP2: 433 MHz + RFID | B | `firmware/node_b` | CC1101 reception and RC522 tag detection |
| ESP3: IR transmitter + receiver | C | `firmware/node_c` | IR reception; use `node_c_ir_tx` later for transmission |

These names describe PlatformIO environments, not binary filenames. The code
assumes classic ESP32 boards and the module types above. Antenna frequency alone
does not identify a module: check the markings before using this firmware.

## 1. Check the dual-radio PCB

With power disconnected, compare PCB connections against this source pin map.
GPIO numbers are not physical header positions.

| Signal | ESP32 GPIO |
| --- | --- |
| Both radios: SCK | 18 |
| Both radios: MISO | 19 |
| Both radios: MOSI | 23 |
| Radio 1: CE / CSN | 5 / 17 |
| Radio 2: CE / CSN | 16 / 4 |

The node A profile uses a 4 MHz SPI clock, holds both radios deselected before
initialization, and allows 100 ms for their supplies to settle. These startup
changes require rebuilding and uploading `node_a`; updating the Pi application
or changing `nodes.json` does not update the ESP firmware.

Check for solder bridges, correct module orientation and common ground. Verify
the supply voltage required by the actual module/adapter and its regulator;
do not infer power pins from the GPIO table. Attach the intended antennas before
the packet test. Power the PCB and check its module supply rails before testing RF.
Use a USB data cable. The two external radios are separate from ESP-native Wi-Fi
and BLE, so finding Wi-Fi networks does not validate either external antenna.

## 2. Prepare the Raspberry Pi

Run these in the repository directory on the Pi, with Python 3.11 or newer:

```sh
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
python3 -m venv .venv-pi
.venv-pi/bin/python -m pip install -e ".[hardware]" platformio
sudo usermod -aG dialout "$USER"
```

Log out and back in after changing the serial group. Nmap is optional for this
PCB test; install it later for the network assessment features. This dedicated
Pi environment also avoids reusing a Windows `.venv` copied with the repository.

## 3. Flash ESP1 only

Connect only ESP1 for the initial upload. List available USB ports:

```sh
.venv-pi/bin/python -m pi_ot_probe.peripherals.provision --list
ls -l /dev/serial/by-id/
```

Set `ESP1_PORT` to its real path, replacing the example, then upload:

```sh
ESP1_PORT=/dev/serial/by-id/REPLACE_WITH_ESP1
.venv-pi/bin/pio run -d firmware -e node_a
.venv-pi/bin/pio run -d firmware -e node_a -t upload --upload-port "$ESP1_PORT"
.venv-pi/bin/python -m pi_ot_probe.peripherals.provision --node A --port "$ESP1_PORT"
```

The last command prints an object containing `node`, `port`, and `device`.
This proves a USB handshake with the selected firmware, not radio health.
Close any serial monitor before provisioning or starting the app.
If by-id is unavailable or duplicated, use a unique `/dev/serial/by-path/` path.

On Windows, use PlatformIO with the same `-d firmware -e node_a` options and
the actual `COM` port. Provision again on the Pi to obtain its Linux port path.

## 4. Configure just ESP1 and start the app

```sh
mkdir -p data
cp -n deployment/nodes.esp1.example.json data/nodes.json
nano data/nodes.json
```

Replace the example object with the provisioning result, keeping the surrounding
`[` and `]`. The file must contain only ESP1 for this first test. If a configuration
already exists, inspect it before editing; the copy command preserves it.

```sh
export RF_SENTINEL_NODES="$PWD/data/nodes.json"
.venv-pi/bin/python -m uvicorn pi_ot_probe.web.app:app --host 127.0.0.1 --port 8088 --workers 1
```

Leave that terminal running. On the Pi open **http://127.0.0.1:8088/console**.
Press Ctrl+C in the terminal to stop. Repeat the export and launch command after
a reboot. For a full-screen browser, run `bash scripts/sentinel-kiosk.sh` in a
second terminal inside the Pi desktop.

From another computer, forward the local port instead:

```sh
ssh -L 8088:127.0.0.1:8088 YOUR_PI_USER@YOUR_PI_ADDRESS
```

Then open the same URL on that computer while the SSH session remains open.

## 5. Run the first PCB test

1. Confirm ESP32-A shows **online** and health **ready**. B/C being unconfigured
   is expected. Ready means both radio initialization checks passed at boot.
2. Choose **2.4 GHz · nRF**, enter operator and purpose, and check the authorization
   box. Select a short duration (for example 1000 ms), then press **Observe**.
3. Look for `nrf1_carrier` and `nrf2_carrier` events and a `complete: true` event.
   Either carrier flag can legitimately be false in a quiet environment. These
   are threshold observations, not decoded Wi-Fi or proof of antenna performance.
4. After observation completes, press the separate nRF packet-test button once.
   In its reply require BOTH `tx_completed: true` and
   `matching_packet_received: true`. With auto-ack disabled, TX completion alone
   does not prove reception. The firmware uses minimum PA level and sends one packet.
5. Repeat manually a few times and retain results. This checks radio 1 TX to radio
   2 RX only; it does not establish reverse-direction operation, range or antenna gain.
6. Unplug/reconnect ESP1: verify it goes offline and returns online. Start a fresh
   observation. Export evidence using the console JSON/Markdown links.

| Symptom | Next check |
| --- | --- |
| No USB port | Data cable, USB socket, board power, USB bridge enumeration |
| Permission denied | Log in again after joining `dialout`; check device ownership |
| HELLO timeout | Correct port, role A, `node_a` firmware, no other serial program |
| Identity mismatch | Re-provision the actual ESP and correct `device` in JSON |
| Online but health error | Both radio supplies, shared SPI wiring, individual CE/CSN, reset after repair |
| TX true, received false | Both antennas/modules, supply stability, CE/CSN wiring; retain failed result |
| App sees no configuration | Export `RF_SENTINEL_NODES` in the same terminal before launch |

## 6. Add ESP2 and ESP3 after ESP1 passes

Stop the app while flashing/provisioning. Use the same upload pattern with
`-e node_b` for ESP2 and `-e node_c` for ESP3. Provision with `--node B` / `--node C`.
Append their returned objects to `data/nodes.json` (comma-separated inside the
array), then restart the app. The full template is `deployment/nodes.example.json`.

- **ESP2 / 433 MHz:** select CC1101 and Observe. Expect RSSI events. A packet test
  requires a known transmitter matching the firmware's RadioLib default FSK
  profile at 433.92 MHz; an arbitrary 433 MHz remote may not decode.
- **ESP2 / RFID:** select RC522 and Observe while presenting a compatible tag.
  Expect `tag_seen: true`, a tag family and a redacted UID. Remove/re-present the
  tag for repeated trials.
- **ESP3 / receive:** select Infrared and Observe, then press a known remote.
  Expect protocol, bit count and `value_hex`. Ready status alone cannot detect a
  missing IR receiver.
- **ESP3 / transmit:** after verifying the actual transmitter circuit, upload
  `node_c_ir_tx`. Send a known NEC code for your test device from the IR panel.
  Confirm the target responds; `frames_sent: 1` alone does not prove reception.

See [integration details](sentinel-integration.md) for B/C GPIO defaults, the
protocol and the full acceptance checklist. No physical PCB has been tested here.
