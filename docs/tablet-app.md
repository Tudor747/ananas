# Native Raspberry Pi tablet app

The native Python/Tk app runs directly on the Pi desktop. It does not need
Chromium, a web server, an SSH tunnel, or another computer during normal use.
The menu includes the original BWifiKiller category and tool names. Availability
is shown explicitly: several entries have a Pi equivalent, others remain
unavailable. This is not a complete port of the standalone ESP firmware.

## Install on the Pi

From an SSH session or a Pi terminal, in the existing project folder:

```bash
cd ~/Desktop/ananas
bash scripts/setup-tablet.sh
```

The installer uses apt for Python, Tk, Nmap and iproute2; installs the project
with its serial dependency into `.venv-pi`; adds the current user to `dialout`
if needed; and creates an RF Sentinel Tablet launcher. Internet access and
sudo are needed for installation. Existing `data/nodes.json` is retained.
If group membership changes, log out of both the desktop and SSH and log in again.
Desktop environments may ask you to mark the launcher as trusted before opening it.

For optional startup **at graphical desktop login**:

```bash
.venv-pi/bin/python scripts/install-tablet-desktop.py --autostart
```

This does not enable desktop auto-login or change the Pi's boot settings. To
remove this optional startup entry, delete only
`~/.config/autostart/rf-sentinel-tablet.desktop`.

## Open the screen

Stop the web server and close `screen`/other serial monitors first. The native
app opens the same ESP ports exclusively. Both interfaces cannot control the
same ESP simultaneously.

Run **in a terminal on the Pi's graphical desktop**:

```bash
cd ~/Desktop/ananas
bash run-tablet.sh
```

The window starts full screen using the detected display resolution. There are
two large choices per menu page. Swipe vertically or use Previous/Next; tap a
tool to open it. Home and Back are always accessible. Scroll tool pages using
the right scrollbar or drag the descriptions; drag inside results to scroll
the results. Stop cancels a running operation. Home/Back also stop active work.
The X button closes the app and stops its devices. Escape leaves fullscreen;
F11 toggles it. No physical GPIO button mapping is added.

For a desktop preview:

```bash
bash run-tablet.sh --windowed --size 320x240
```

If the Pi has only a text console, a graphical desktop and X11/XWayland are
required for Tk. A plain SSH session can run checks but cannot display the app
on the Pi's screen. Native Wayland desktops normally provide XWayland; a
display connection must actually be available, not just a DISPLAY variable.

## First use

1. If the node is unconfigured, open **System > USB Setup**.
2. Select role A for `node_a`, choose the ESP USB port, and tap Run. This reads
   the identity, backs up an existing configuration, and preserves other roles.
3. Wait for **A: USB online**. Hardware error is a separate firmware health
   report. On node A, failed nRF initialization can coexist with working Wi-Fi/BLE.
4. Open **Wi-Fi > Wi-Fi Scanner**, confirm permission for the test, and tap Run.
   Scans finish after a bounded observation. An empty result is shown as such.
5. Review the signal bars and observed values. Completed reports are saved under
   `data/tablet-reports/`; **System > View Logs** provides recent USB evidence.

The current `node_a`, `node_b`, and `node_c` USB commands are reused. The native
app itself requires no new firmware upload if those profiles already respond to
HELLO. Original BWifiKiller standalone binaries use a different interface.

## Feature coverage

| Category / original tools | Native implementation |
| --- | --- |
| Wi-Fi Scanner | Passive ESP 2.4 GHz AP inventory and RSSI bars |
| Wi-Fi Radar | Three signal snapshots; no bearing or distance claims |
| Channel Scan | Unique observed AP counts by channel; not channel utilization |
| Sentinel Mode | Compare with the previous saved Wi-Fi snapshot |
| IP Scanner | Pi Nmap host discovery on a selected local private subnet, max 256 addresses |
| Web Dashboard | Native node overview; not the original ESP-hosted website |
| Analyzer / Dual nRF Scope | Two binary carrier-threshold traces |
| RF Heatmap / CH Advisor | Receive samples on channels 0,5,...,125; rank measured hit fractions |
| nRF Link | One packet from radio 1 to radio 2, channel 76, minimum power |
| BT/WiFi Coex | Sequential Wi-Fi, BLE and nRF inventories; no inference of interference |
| BT Scanner / BT Analyzer | Passive BLE inventory and three signal snapshots |
| BT Spectrum | RSSI histogram; not an RF frequency spectrum |
| Arcade | A new touch memory game; original ESP games are not ported |
| Slave Control | Native node overview and STOP; original slave protocol is not ported |
| View Logs / About | Local evidence, runtime and screen information |
| Additional System tools | Dependencies, automatic USB identity setup, Pi Wi-Fi scan |
| Additional B/C tools | CC1101 reception, RC522 tag observations, IR reception |
| Packet Monitor / nRF Chat / BT Remote | Unavailable: missing firmware transport or pairing support |
| Illegal category | Original eight names are visible with unavailable explanations; no interference, spam, credential-collection or broadcast-disconnect controls |

The passive nRF sweep leaves the radios configured to the last sampled channel
(125). The next Link test explicitly sets channel 76. Radio measurements require
healthy nRF hardware; installing Python packages cannot fix its wiring or supply.
The Link result must show both TX completed and matching packet received to
demonstrate reception. The single direction test does not establish range.

## Dependencies and SSH diagnostics

```bash
cd ~/Desktop/ananas
bash run-tablet.sh --check
```

This checks the machine where it runs. It opens no GUI and sends no probes.
Missing optional components do not prevent the core app opening.

| Dependency | Needed for |
| --- | --- |
| Python 3.11+, python3-venv, python3-pip | Runtime and installation |
| python3-tk | Native window; installed using apt, not pip |
| `.[hardware]` | Existing project dependencies and pyserial |
| nmap | IP Scanner only; no pip Nmap wrapper is required |
| iproute2 | Linux interface-discovery fallback |
| NetworkManager / nmcli | Pi Wi-Fi Scan only; ESP scanning does not need it |
| dialout membership | Linux USB serial access |
| Graphical desktop / display server | Show the touch window |

The installer does not change network services. If `nmcli` is missing, inspect
which service manages the Pi before switching to NetworkManager, especially
when connected through SSH. The dependency page identifies this optional gap.
PlatformIO is needed only when compiling/uploading firmware, not for operating
the tablet. Nmap is invoked as the logged-in user, without sudo.

## Files and validation

`src/pi_ot_probe/tablet/` contains the catalog, backend, diagnostics and Tk UI.
The app reuses the existing bounded `NodeManager` and USB evidence store. It
uses `data/tablet.db` by default, separate from the web database. `--database`,
`--nodes`, and `--reports` override paths; `RF_SENTINEL_NODES` also selects the
node configuration. The launcher changes directory to the repository root.

Tests use serial fixtures and isolated local databases. Layout checks cover
320x240, 480x320 and 800x480 where Tk is available. These are not physical Pi,
touchscreen or radio validation. No live network or RF scans are run by tests.
