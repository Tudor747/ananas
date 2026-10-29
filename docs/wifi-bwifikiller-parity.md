# Native Wi-Fi scanner: BWifiKiller comparison

The Pi touchscreen now uses BWifiKiller's list → AP details and channel → AP list
→ details workflows. These views occupy the available screen instead of placing
a large report underneath the setup form. Wi-Fi Scanner, Channel Scan, Wi-Fi
Radar and System → Pi Wi-Fi Scan use the new browser. Other tools retain their
existing result readers.

| Reference | Native implementation |
| --- | --- |
| `BWifiKiller/src/wifiscan.cpp` | Strongest-first AP list, signal bars, hidden SSIDs, full SSID/BSSID/security details and counts for radios sharing an SSID |
| `BWifiKiller/src/wifi_channel_scan.cpp` | Channels 1–14, counts and bars, selected channel's APs, individual AP details |
| `BWifiKiller/src/wifi_radar.cpp` | Select a BSSID, then track RSSI with a live history and stronger/weaker/stable trend using the original 4 dB threshold |
| `BWifiKiller/include/wifi_observation.h` | Shared C++ signal thresholds and 500 ms scan dwell used by the original scanner modules and/or node A; security names and channel frequencies for node A |
| `tablet/wifi_results.py` | Python adaptations of the list, signal and trend rules; original MIT attribution retained |

The OLED drawing code requires ESP32/U8g2. The Pi renders the equivalent workflow
in Tk (`tablet/wifi_view.py`). It retains every radio's BSSID, including separate
radios with the same SSID; repeated observations of one BSSID are deduplicated
case-insensitively. Each scan keeps its strongest observation of that radio.

## Controls and information

- **Up/Down:** select an AP/channel or scroll AP details.
- **OK:** open the selection. In Radar details, start a 12-scan tracking run;
  while tracking, OK stops it. In ordinary AP details, OK returns to the list.
- **Left/Back:** return one level. Back from the list returns to scan setup.
- **Right:** rescan, or stop a running observation. ESP controllers without a
  Right action can select the final **Rescan** row with Up/Down and OK.
- **Touch:** tap a row to open it; swipe to move or scroll; use Back/Rescan/Stop.

AP details include the full SSID and BSSID, RSSI, channel, band, advertised
security and hidden/visible status. Frequency, cipher, radio type, mode, rate,
network type and source are shown when available. Pi percentage-based dBm is
marked with `~` and explained as an estimate. Unknown RSSI stays unknown.
The nmcli parser now accepts frequency units such as `2437 MHz`.

Channel Scan preserves the AP records in its saved report as well as the counts.
Firmware result caps are visible as **PARTIAL**. Zero on a channel means no AP
was observed in that scan; counts do not measure channel airtime.

Radar selects by BSSID, so another radio with the same SSID cannot substitute its
signal. A missing target produces a gap and **NOT OBSERVED**, followed by
**REACQUIRED** if it returns. The chart shows RSSI, not a physical location.
The 12 observations scan all supported ESP channels, allowing a target that
changes channels to reappear. This takes longer than the original target-channel
radar. Completed snapshots, timestamps and individual truncation metadata are
saved; Stop/errors retain completed snapshots and label the run incomplete.

## Apply to the existing Pi installation

`dist/rf-sentinel-tablet-update.tar.gz` contains the changed Python modules,
firmware sources/shared headers, tests and documentation. It is an update for an
existing checkout; it does not contain your saved USB configuration or database.
Stop the running tablet app, extract into the project folder, then restart with
the existing launcher. Do not start a second instance against the same USB ports.

The new native views work with older node A firmware. To get the 500 ms per-channel
scan dwell and explicit hidden/frequency fields, rebuild and flash **node_a**:

```sh
python -m platformio run -d firmware -e node_a
# After selecting the actual ESP-A USB port:
python -m platformio run -d firmware -e node_a -t upload --upload-port YOUR_ESP_A_PORT
```

The ESP remains a passive 2.4 GHz receiver during Wi-Fi observations. The longer
scan dwell improves the opportunity to receive beacons but still cannot guarantee
every AP will appear. B and C need no firmware update for these scanner changes.

## Validation and remaining coverage

Automated checks exercise parsing, identity/deduplication, channel details,
missing/estimated signal values, Radar updates, failure/cancellation, USB request
correlation and real Tk button/touch navigation at 240×240, 320×240, 480×320 and
800×480. The node A observation loop is also compiled against radio fixtures;
the current node A, B and C PlatformIO profiles compile successfully.
Local interface discovery, loopback HTTP and loopback Nmap TCP checks pass.

The full Python run completed with 177 passed and one skipped Tk check on this
Windows/Python 3.14 host; that check passed in an isolated run. Repeated Tk
interpreter creation sometimes fails to load an installed Tcl resource here.
The earlier startup-test failure was traced to test GUI objects being finalized
on a later worker thread; test teardown now cancels timers and collects GUI
cycles on the main thread. An elevated verification attempt also encountered
temporary-directory permission errors and is not counted as a passing run.

These are software/build checks, not physical validation of the Pi, its display,
ESP boards, wiring or RF reception. On the Pi, compare known APs against their
SSID/BSSID/channel/security, try an empty channel, track an AP while moving the
receiver, stop midway, and disconnect ESP-A during a scan. Confirm that partial
results stay visibly incomplete and all navigation remains usable.

This is not a complete port of every standalone BWifiKiller tool. Packet Monitor,
nRF Chat and BT Remote still have no native implementation; their menu entries
remain marked unavailable. See [the tablet guide](tablet-app.md) and
[existing coverage audit](scan-results-audit.md) for the other tools.
