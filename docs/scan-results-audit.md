# Tablet scan results: audit and changes

Reviewed 29 October 2026 against the native tablet collectors, result formatter,
and `firmware/node_a`, B and C profiles. These findings come from source and
fixture tests; scans on the physical Pi have not been repeated here.

## Problems corrected

| Tool / path | Previous behavior | Updated behavior |
| --- | --- | --- |
| ESP-A Wi-Fi | No security information; first 30 APs silently capped | Security type and band in each result; up to 64 observations, with total/reported counts and a truncation flag |
| BLE | First 20 advertisements silently capped | Up to 64; total and reported counts shown |
| Wi-Fi / BLE list | Device order and duplicates obscured useful results | Unique identities sorted by reported RSSI, strongest first |
| IP discovery | `-n` disabled DNS; only 80/443 probed without raw-packet privileges | DNS enabled; discovery probes 22/80/443/445/3389, retaining rate and timeout limits |
| IP results | Only IP, hostname and MAC rendered | Interface and Pi address, hostname, MAC/vendor when available, response reason and Nmap warnings |
| MAC addresses | Often absent in an unprivileged scan | Enrich already-discovered hosts from the Pi neighbor cache, restricted to the selected interface and labelled as cached |
| TCP ports | Never scanned from the tablet | After discovery, choose `Check ports: IP` for 20 common TCP ports and light service/version identification on that host |
| Port results | No native tablet workflow | Open/closed/filtered counts, individual reported states, probed products/versions and explicitly labelled port-name hints |
| Scan errors | Only a notice, separate from the results; live preview could overwrite the error | Readable failed/cancelled report with retained partial radio samples and JSON report on disk |
| Successful empty result | Generic “no samples” | Tool-specific scope and next checks; never treats no observations as proof of no devices |
| Pi Wi-Fi, IR, RFID, CC1101, combined scans | Often raw JSON or missing explanations | Structured text with units, IDs actually supplied, and collection limits |
| Button navigation | Result box required navigating past form controls | Scan completion enters the result reader automatically; Up/Down scroll and Left returns to controls |
| IR / RFID | Five-second collection window | Ten seconds to press a remote or present a tag |

The IP collector verifies completion in Nmap XML. Missing/failed completion,
timeout, or missing port states are not reported as a clean inventory of closed
ports. Cached neighbors are never added as newly discovered live hosts.

## Limits that remain

| Tool | What it measures | What it does not provide |
| --- | --- | --- |
| ESP-A Wi-Fi | Passive 2.4 GHz AP inventory: SSID, BSSID, RSSI, channel and advertised security | 5/6 GHz, client lists, IP addresses of nearby APs, passwords, traffic capture or verified distance |
| Pi Wi-Fi Scan | NetworkManager inventory from the Pi adapter | Guaranteed coverage of all bands; dBm is estimated from NetworkManager's percentage |
| IP Scanner | Responding IPv4 hosts on a selected attached private subnet, at most 256 addresses | Devices behind another router, other nearby Wi-Fi networks, guaranteed discovery through firewalls/client isolation; IPv6 |
| Host port check | 20 common TCP ports on one recently discovered local host, optional per host | All 65,535 ports, UDP, OS fingerprinting, guaranteed versions or vulnerability assessment |
| Wi-Fi Radar / BT Analyzer | Three successive signal snapshots | Location, bearing, exact distance, or proof that a device vanished |
| Channel Scan | Observed AP count per Wi-Fi channel | Channel airtime or actual congestion |
| BLE | Passive BLE advertisements; advertised names may be absent | Classic Bluetooth discovery, pairing, remote control or reliable device/vendor identification |
| nRF / scope / heatmap / advisor | Carrier-threshold samples, including 26 sampled channels for sweep | Wi-Fi packet decoding, full spectrum coverage, calibrated RSSI or oscilloscope waveforms |
| nRF link test | One packet from radio 1 to radio 2 | Reverse direction, range or antenna-gain measurement |
| CC1101 | 433.92 MHz RSSI and packet validity for the configured FSK profile | Universal 433 MHz remote decoding; raw packet payloads are not retained |
| RFID | Tag detection and family; UID length | Raw UID (redacted by firmware), memory dumps or cloning |
| Infrared | Decoded protocol, bit count, hex value, repeat/overflow flags | Raw timing capture or a native tablet transmit/learned-remote workflow |

`node_c_ir_tx` can transmit a single 32-bit NEC code through the protocol; normal
`node_c` remains receive-only. Packet Monitor, nRF Chat and BT Remote remain
unimplemented menu entries. Only one tablet job runs at a time.

A hidden Wi-Fi SSID has not necessarily been decoded. A BSSID is the AP's radio
address, not a discovered client's MAC. The ESP does not join scanned Wi-Fi
networks; IP discovery uses whichever network the Pi itself is connected to.

Nmap's discovery and DNS behavior is documented in its
[host discovery reference](https://nmap.org/book/man-host-discovery.html) and
[DNS reference](https://nmap.org/book/host-discovery-dns.html). Light service
identification uses [`-sV --version-light`](https://nmap.org/book/man-version-detection).

## Applying and checking the change

Update the Pi application and restart its existing autostart instance once.
Use the same GPIO/ESP setup as before. Do not launch a second tablet instance.

The added Wi-Fi security fields and scan-count metadata require rebuilding and
flashing **ESP-A with `node_a`**. Updating Python alone does not change firmware.
Older node A firmware still works, but results state when security or counts
were not reported. B/C do not need reflashing for these presentation changes.

1. Wi-Fi Scanner: compare a known nearby 2.4 GHz AP's SSID/BSSID/channel/security.
2. IP Scanner: choose the interface containing the Pi's actual LAN address.
   Compare responding hosts against known LAN devices. Missing DNS names and
   MACs are allowed; investigate filtered/sleeping hosts separately.
3. Exit the reader with Left, choose `Check ports: IP`, then OK. Confirm an open
   known service is shown. A table-based service label must not claim a version.
4. Unplug ESP-A during a scan: the result must say failed/incomplete and retain
   any already-received samples. Stop a scan: it must say cancelled/incomplete.
5. Reports are in `data/tablet-reports/`. Each report includes status, source,
   elapsed time and result; firmware completion counts are retained when supplied.
