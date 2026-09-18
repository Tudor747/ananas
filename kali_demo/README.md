# Raw network inventory and website inspector

This is a separate, local browser application for safe Pi-OT Security Probe
host discovery. Its tabbed analyst workspace separates overview, change
review, controlled validation, current evidence, and scan history. It
detects active private IPv4 interfaces, lets the operator select one local
subnet, and stores real responding devices in SQLite.

The default scan is deliberately limited to Nmap host discovery (`-sn`). It
also provides an optional **Check 20 TCP ports** action for one selected asset. It
uses a TCP connect scan of only 20 common ports, capped at five connections per
second. It does not detect versions or operating systems, run NSE scripts, test
credentials, exploit devices, or perform denial-of-service actions.

Targets are restricted to directly connected RFC1918 networks of 256 addresses
or fewer. The operator must explicitly confirm authorization, all scans have
timeouts, and every operation can be cancelled and is audit logged.

The application presents observations rather than risk scores. It does not
infer a device type from a hostname or vendor, and it displays missing values as
**Not observed**. It retains the raw fields supplied by its bounded collectors:
IP/MAC/vendor/hostnames, host status and reason, structured service details,
SSID/BSSID and radio details, timestamps, sources, scan history, and HTTP/TLS
metadata when a discovered website is explicitly inspected.

Named site baselines provide automatic comparison after discovery, new and
removed device detection, MAC/IP and new-port changes, Wi-Fi AP inventory,
change acknowledgement, and downloadable JSON/CSV reports.

Per-scan asset snapshots keep historical evidence from changing when an asset
is checked again. Only assets from the latest completed discovery are shown as
current, cancelled scans never produce removal signals, and service evidence is
shown as not checked after a new discovery until the host is verified again.

The Change Review workspace presents the observed differences without assigning
a score or severity. It supports New, Investigating, Confirmed observation,
Expected change, and Resolved states with analyst notes. The Validation Lab is
a controlled view over the bounded collectors; planned OT identity checks
remain visibly disabled.

## Developer map

The application is split by responsibility so a manual edit has one obvious
home:

- `app.py` coordinates scans and defines the local HTTP routes.
- `contracts.py` contains validated API request bodies.
- `state_builder.py` converts immutable SQLite observations into dashboard data.
- `scenarios.py` contains the descriptions shown in Validation Lab.
- `real_scanner.py`, `wifi_inventory.py`, and `web_inspector.py` are collectors.
- `baseline.py` compares observations; `reports.py` creates raw exports.
- `static/app.js` handles user actions, `static/api.js` handles HTTP calls,
  `static/renderers.js` builds views, and `static/dom.js` contains DOM helpers.

Keep raw collector fields in the database/state path even when the interface
does not yet display them. Add presentation wording in the renderer instead of
turning missing evidence into a guessed value.

## Start on Kali

Install the Python prerequisites once:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nmap iproute2
```

From the cloned project:

```bash
cd kali_demo
bash run.sh
```

Open <http://127.0.0.1:8088> in the Kali browser. Select a detected local
private network, confirm that you are authorized to assess it, and click
**Discover devices**. The inventory records IP, MAC/vendor data when Nmap can
observe it, hostname when available, source, timestamps, and audit history.
Use **Check 20 TCP ports** on an individual asset only when the additional TCP
connections are acceptable. Create a baseline after reviewing the inventory;
later discovery runs are compared automatically.

After a web port is observed, **Inspect HTTP/HTTPS** sends one `HEAD /` request,
does not follow redirects, and records the response status, headers, TLS
protocol/cipher and certificate fingerprint. It reports facts without grading
them. Certificate validation is not performed for this local-IP observation and
that limitation is shown in the raw details. `Set-Cookie` values are redacted so
the inventory does not become a store of session credentials.

Only assess networks you own or have explicit permission to test. Host
discovery transmits ICMP/TCP discovery probes, or ARP on a directly connected
Ethernet network when Nmap has sufficient privileges.

Stop the server with `Ctrl+C`. Its SQLite database is stored at
`kali_demo/data/demo.db` and is ignored by Git.

To use a different local port:

```bash
PI_OT_DEMO_PORT=8090 bash run.sh
```

The launcher always binds to `127.0.0.1`. Do not expose this application to
another interface. It has no user authentication because it is designed solely
for a single local Kali operator.

## Test without opening a browser

For actual results from your own computer, run this from the repository root:

```powershell
python -m kali_demo.local_check
```

This reads the current local interfaces, starts a temporary HTTP server bound
to `127.0.0.1`, collects its HTTP response using the real inspector, and uses
Nmap to check that server's single TCP port. It closes the server afterward.
No Raspberry Pi, OT equipment, or subnet scan is needed. The server is a
controlled local test endpoint, not an observation of an external device.

Actual interface data, HTTP headers (with cookies redacted), the Nmap command,
and raw Nmap XML are saved in `kali_demo/data/local-check.json`.
Each check reports passed, failed, or skipped; unavailable Nmap is explicitly
skipped. Exit codes are 0 for passed, 1 for failed, and 2 for partial results.
Use `--output path/to/report.json` to save another report. This check covers
plain HTTP and TCP; it does not verify TLS, Wi-Fi, or OT protocols.

From the project root, with the project dependencies installed:

```bash
python -m unittest discover -s kali_demo/tests -v
```

You can also verify the API after starting it:

```bash
curl http://127.0.0.1:8088/api/health
curl http://127.0.0.1:8088/api/networks
curl -X POST http://127.0.0.1:8088/api/real/run \
  -H 'Content-Type: application/json' \
  -d '{"target":"192.168.1.0/24","authorized":true}'
curl -X POST http://127.0.0.1:8088/api/real/verify \
  -H 'Content-Type: application/json' \
  -d '{"host":"192.168.1.10","authorized":true}'
curl -X POST http://127.0.0.1:8088/api/real/web \
  -H 'Content-Type: application/json' \
  -d '{"host":"192.168.1.10","port":80,"scheme":"http","authorized":true}'
curl -X POST http://127.0.0.1:8088/api/baseline \
  -H 'Content-Type: application/json' \
  -d '{"name":"Approved site"}'
curl http://127.0.0.1:8088/api/state
curl -OJ http://127.0.0.1:8088/api/reports/site.json
curl -OJ http://127.0.0.1:8088/api/reports/assets.csv
```

The API rejects public networks, networks not attached to the machine, targets
larger than `/24`, and requests without authorization confirmation. Use
`POST /api/cancel` to stop an in-progress discovery or service-check scan.

Wi-Fi inventory requires NetworkManager/nmcli on Linux or WLAN AutoConfig/netsh
on Windows. Refreshing Wi-Fi requires the authorization checkbox. Linux uses a
normal Wi-Fi scan through NetworkManager; it does not enable monitor mode,
capture client traffic, deauthenticate stations, or store packets.

## Start on Windows

Install Python 3 and the official Nmap for Windows package first. The Nmap
installer is available from <https://nmap.org/download> and normally installs
Npcap as part of the setup.

Open PowerShell in the project directory and run:

```powershell
cd D:\proiecte\ananas\kali_demo
Set-ExecutionPolicy -Scope Process Bypass
.\run.ps1
```

Then open <http://127.0.0.1:8088>. The cross-platform adapter reads active IPv4
configuration through `psutil` without administrator rights; PowerShell and
iproute2 remain fallback adapters. It does not require WSL, Kali, Bash, or
Docker. If Nmap was installed while PowerShell was already open, start a new
PowerShell window so its command path refreshes.
If Nmap is installed on another drive, add the directory containing `nmap.exe`
to `PATH` before running the launcher.

If port 8088 is already occupied, stop the old server with `Ctrl+C` or use:

```powershell
$env:PI_OT_DEMO_PORT = "8090"
.\run.ps1
```

## Known limits and remaining appliance work

- Hostnames depend on DNS/Nmap; MAC/vendor normally appear only on the local
  layer-2 segment, and hidden SSIDs can remain unnamed.
- Windows and NetworkManager expose different Wi-Fi fields. Monitor-mode/Kismet
  integration would be needed for richer passive radio metadata.
- The service check covers 20 common TCP ports. A wider scan should be a
  separately confirmed profile with clear traffic and time limits.
- Real Raspberry Pi LCD/GPIO, restricted system-service permissions,
  authenticated remote management, bounded packet metadata capture, and safe OT
  protocol identification still need hardware integration testing.
- PDF reports and signed offline intelligence updates remain later deliverables.
