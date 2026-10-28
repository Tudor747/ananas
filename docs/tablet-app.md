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
the results. **Stop all** cancels the current job and sends STOP to every connected
ESP. Home/Back also stop active work.
The X button closes the app and stops its devices. Escape leaves fullscreen;
F11 toggles it. The Pi's five GPIO buttons can control the same highlighted
selection; touchscreen and keyboard input remain available.

## Raspberry Pi 5 GPIO navigation

The handoff's GPIO mapping is in `GPIOButtons.PINS` in
[`src/pi_ot_probe/tablet/gpio_buttons.py`](../src/pi_ot_probe/tablet/gpio_buttons.py).
These are **BCM GPIO numbers**, not physical header positions:

| Button | BCM GPIO | Action |
| --- | --- | --- |
| LEFT | 5 | Previous menu page; parent menu on the first page; back from a tool |
| UP | 6 | Previous item on the page, or previous tool control |
| DOWN | 13 | Next item on the page, or next tool control |
| RIGHT | 26 | Next menu page |
| OK / SELECT | 19 | Activate the highlighted item or control |

Each momentary button connects its GPIO to common ground. Internal pull-ups are
enabled. GPIO 16 belongs to the planned ON/OFF switch and is **not opened or used**.
No ESP firmware or `BWifiKiller` changes are needed for these Pi buttons.

UP/DOWN stop at the first/last menu item; LEFT/RIGHT change pages. Single-item
pages keep a valid highlight. In a tool, use UP/DOWN and OK to toggle permission,
select a USB role/port, Run, or Stop all. Select the result box with OK to read it;
UP/DOWN then scroll the output and LEFT/OK leave result-reading mode. The next
LEFT returns from the tool. Entering a new page selects its first item; tool
screens initially highlight the permission checkbox when present.

The driver samples on Tk's event loop every 30 ms and requires a stable input for
60 ms. Each press fires once; holding a button does not repeat. A button already
held at startup must be released and pressed again. One cancellable timer owns
polling; shutdown, window destruction, read errors, and partial initialization
release opened buttons. A GPIO setup failure is logged and leaves touch/keyboard
usable. Linux launches try GPIO automatically; Windows/macOS previews do not.

The Pi environment described in the handoff already has these packages:

```bash
sudo apt install python3-gpiozero python3-lgpio
```

Ensure `.venv-pi/pyvenv.cfg` contains `include-system-site-packages = true`, so
the app can import the Debian packages. The driver defaults `GPIOZERO_PIN_FACTORY`
to `lgpio` if it is not already set, including launches from the desktop autostart
entry. Existing startup scripts and desktop entries are unchanged. Launch normally:

```bash
cd /home/pi1/Desktop/ananas
bash run-tablet.sh
```

The handoff reports that the earlier Pi version worked after reboot; this local
integration was checked with simulated GPIO and desktop Tk tests, not on a Pi.
On the actual device, check every direction, page boundaries, a single-item page,
permission/Run/Stop, touch input, closing/reopening, and startup after reboot.

## Five-button controller on ESP-A (older optional input)

Change the button GPIO numbers in
[`BWifiKiller/include/app_config.h`](../BWifiKiller/include/app_config.h).
The `node_a` firmware uses these same definitions:

| Button | Definition | Default ESP GPIO | Native Pi menu action |
| --- | --- | --- | --- |
| Up | `BTN_UP` | 26 | Move the highlight up; hold to repeat |
| Down | `BTN_DOWN` | 33 | Move the highlight down; hold to repeat |
| Back | `BTN_BACK` | 25 | Stop active work and return to the previous menu |
| Select | `BTN_AUX` | 27 | Open the highlighted item or toggle a setting |
| OK | `BTN_OK` | 32 | Run the current tool; open the highlighted item on menus |

Wire each momentary button between its **ESP-A GPIO and GND**. The firmware uses
internal pull-ups, so pressing a button pulls its input low. These are ESP GPIO
numbers, not Raspberry Pi header positions. Keep button pins separate from the
SPI/radio pins. Pins and debounce/repeat timings are in the same configuration file.
Select and OK trigger once per press; holding them does not repeat an operation.

Build and upload the updated ESP-A firmware after changing pins:

```sh
pio run -d firmware -e node_a
pio run -d firmware -e node_a -t upload --upload-port YOUR_A_PORT
```

Close the tablet/serial monitor before uploading, then restart `bash run-tablet.sh`
with the updated Python code. B/C can stay on their existing firmware. Buttons
travel over A's existing USB connection and control the native Tk menu only.
First pair ESP-A using a keyboard or an existing `data/nodes.json`; its physical
buttons become available after USB identification. Keyboard equivalents are
Up/Down, Left or Backspace for Back, Space or Right for Select, and Enter for OK.

The green outline marks the selected control. Up/Down automatically cross menu
pages and scroll tool settings into view. Select the permission checkbox before
OK; the controller uses the same authorization checks as the Run button. To read
long output, highlight the result box and press Select, then use Up/Down to scroll.
Back or Select leaves result reading without leaving the tool. Select **Stop all**
to stop work while keeping the tool visible. No touchscreen is required for these
flows. Old/disconnected USB presses are discarded and input is not replayed from
saved evidence. Physical wiring still needs testing on the actual board.

For a desktop preview:

```bash
bash run-tablet.sh --windowed --size 320x240
```

If the Pi has only a text console, a graphical desktop and X11/XWayland are
required for Tk. A plain SSH session can run checks but cannot display the app
on the Pi's screen. Native Wayland desktops normally provide XWayland; a
display connection must actually be available, not just a DISPLAY variable.

## First use

1. Open **System > USB Setup** (System is on the first home page). You can also
   tap the connection strip at the top when no boards are configured.
2. Select role A for `node_a`, choose the ESP USB port, and tap **Connect**. This reads
   the identity, backs up an existing configuration, and preserves other roles.
3. Wait for **A: ready** or **A: HW error**. Both mean USB identification succeeded;
   tap the connection strip for **Devices**, which shows live details for A/B/C.
   Hardware error is a separate firmware health
   report. On node A, failed nRF initialization can coexist with working Wi-Fi/BLE.
4. Open **Wi-Fi > Wi-Fi Scanner**, confirm permission for the test, and tap Run.
   Scans finish after a bounded observation. An empty result is shown as such.
5. Review the signal bars and observed values. Completed reports are saved under
   `data/tablet-reports/`; **System > View Logs** provides recent USB evidence.

The current `node_a`, `node_b`, and `node_c` USB commands are reused. The native
app works with existing profiles that respond to HELLO. The updated `node_a`
also fixes BLE results lost at the deadline, Wi-Fi results cut short at the deadline,
and failed Wi-Fi scans reported as empty successes; rebuild/upload A to get those
firmware fixes. Original BWifiKiller standalone binaries use a different interface.

## Working with all three boards

| Role | Firmware | Tablet tools |
| --- | --- | --- |
| A | `node_a` | Wi-Fi, Bluetooth, RF Tools |
| B | `node_b` | Other boards > 433 MHz / CC1101 and RFID / RC522 |
| C | `node_c` | Other boards > Infrared Receiver |

Set up B and C in the same USB Setup screen. Ports already assigned to another
role are labelled and disabled. Each connection checks the board's stored device
identity, so a swapped cable cannot silently send A's commands to B. Setup briefly
pauses all USB workers, preserves the other roles, and reconnects them afterwards.
An existing configuration is backed up to `nodes.json.bak` before a successful change.

On Linux, the port picker prefers `/dev/serial/by-id/` and falls back to
`/dev/serial/by-path/` when available. A by-path name depends on the USB socket:
keep those boards in the same sockets. With only `/dev/ttyUSB*` names available,
recheck assignments after reconnecting cables or rebooting. Stable names prevent
renumbering problems; the ESP identity check remains the final guard.
If two ports have swapped, use **Forget ESP-A setup** and **Forget ESP-B setup**
under the corresponding role, then connect each again to its current port. This
removes only the selected assignment and keeps evidence, reports and other roles.

All three connections stay online independently. The tablet runs one selected tool
at a time; a healthy A/C connection continues if B disconnects. Reconnection is
automatic, but an interrupted test must be started again explicitly. Commands,
especially transmissions, are never replayed after a disconnect. Tools for an
offline board keep Run disabled and show the connection problem and setup shortcut.

If boards repeatedly restart when all three are plugged in, check the Pi supply,
USB cables, hub power and peripheral supplies before changing software. The
automated checks do not validate the power budget or physical wiring.

## Finding a problem

- Tap the connection strip or open **System > Devices** for each board's port,
  device ID, firmware build, hardware health and last connection error.
- **System > View Logs** shows USB commands, observations and connection failures.
  Repeated unchanged background STATUS replies are omitted; operator requests,
  health transitions and timeout failures remain recorded. Device sequence numbers
  can therefore jump between stored heartbeat records without implying lost USB data.
  Identical connection errors are recorded once until the error changes or a
  connection succeeds; unplugged boards still retry every two seconds.
- Full Python error traces are written to `data/tablet.log` by default, next to the
  selected database. Logs rotate at 1 MB with two backups. Reports remain in
  `data/tablet-reports/`; USB evidence remains in `data/tablet.db`.
- A USB connection with `HW error` is different from a disconnected ESP. For
  example, failed nRF initialization need not prevent ESP-A's Wi-Fi scanner working.
- An empty result means a completed observation found no samples. A firmware scan
  error or timeout is shown as an error, and no successful report is saved for it.

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
| Devices (formerly Slave Control) | Live A/B/C overview and Stop all; original slave protocol is not ported |
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

`src/pi_ot_probe/tablet/` contains the catalog, backend, diagnostics, result
formatting (`presentation.py`) and Tk UI (`app.py`).
The app reuses the existing bounded `NodeManager` and USB evidence store. It
uses `data/tablet.db` by default, separate from the web database. `--database`,
`--nodes`, and `--reports` override paths; `RF_SENTINEL_NODES` also selects the
node configuration. The launcher changes directory to the repository root.

Tests use serial fixtures and isolated local databases. Layout checks cover
320x240, 480x320 and 800x480 where Tk is available. These are not physical Pi,
touchscreen or radio validation. No live network or RF scans are run by tests.
