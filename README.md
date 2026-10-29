# RF Sentinel X · Pi + three ESP32 nodes

**Native Pi touchscreen app:** run `bash scripts/setup-tablet.sh` once, then
`bash run-tablet.sh` from the Pi desktop. See [the tablet guide](docs/tablet-app.md)
for the BWifiKiller-style menu, actual feature coverage, dependencies and optional
desktop startup. Stop the web app before giving the native app the ESP USB port.

The Raspberry Pi 5 now has a local peripheral console at
**http://127.0.0.1:8088/console**, alongside the network assessment website at `/`.
It routes bounded USB commands to three independently identified ESP32 nodes,
records replies/events in SQLite, and exports source-labelled evidence.

- **A:** two nRF24L01+ radios, ESP Wi-Fi/BLE observations, one-packet nRF peer test.
- **B:** CC1101 433 MHz receiver and RC522 RFID observations.
- **C:** KY-022 IR reception and optionally enabled KY-005 single-frame NEC output.

All three current firmware profiles live in `firmware/` and run without a local
ESP menu. `BWifiKiller/` retains the earlier standalone builds and a compatibility
entry point for node A.
No devices have been flashed or physically validated in this implementation.
Exact ESP variants, B/C wiring, output circuitry and screen behavior need your
manual verification. IR output is disabled in the default build.

**Start here:** [test the dual 2.4 GHz PCB and launch on Raspberry Pi](docs/first-pcb-test.md).

For “this board is ESP-B/C, not ESP-A” or “HW error”, see
[USB identity and per-radio checks](docs/esp-usb-troubleshooting.md).

| Your board | App role | PlatformIO profile in `firmware/` |
| --- | --- | --- |
| ESP1: two nRF24L01+ radios | A | `node_a` |
| ESP2: CC1101 + RC522 RFID | B | `node_b` |
| ESP3: IR receiver/transmitter | C | `node_c`; later `node_c_ir_tx` |

See the [firmware directory](firmware/README.md) for builds and
[integration reference](docs/sentinel-integration.md) for protocol and GPIO details.

No USB ports are opened until `RF_SENTINEL_NODES` points to an explicit node
configuration. Install `.[hardware]` for serial support. Existing network launch
commands below also serve the console.

## Network assessment and earlier firmware

The same app serves network inventory, bounded service checks, HTTP/TLS
observations, Wi-Fi inventory, baselines and assessment reports at `/`.
See [the practical workflow](docs/practical-assessment.md) for capabilities.

`BWifiKiller/` contains the earlier standalone ESP firmware with its original
license. Its menu and `piot-usb-v1` diagnostic interface are separate from the
current three-node console. [SSH and USB testing](docs/ssh-and-usb-testing.md)
documents that older diagnostic workflow; use the ESP1-first guide above for
`node_a`, `node_b` and `node_c`.

## Start on Windows

Install Python 3.11+ and Nmap. From PowerShell:

```powershell
cd D:\proiecte\ananas
Set-ExecutionPolicy -Scope Process Bypass
.\run.ps1
```

Open **http://127.0.0.1:8088**. The launcher creates `.venv/` and installs the
Python dependencies. Keep PowerShell open; press Ctrl+C to stop. To use another
port, run `.\run.ps1 -Port 8090`. Nmap is needed for scans, not to open the UI.

On Linux, install Python, venv support, and Nmap, then run `bash run.sh`.
The `kali_demo` launcher starts the same current app; see the
[Kali setup and checks](kali_demo/README.md). Use `bash run.sh --help` for options.
See [usage](docs/usage.md) for detailed setup and collector limits.

## Find your way around

```text
src/pi_ot_probe/       Python application and website assets
  web/                App assembly, HTTP routes, request schemas, frontend
  application/        Scan workflows, baselines, dashboard data
  collectors/         Real OS, Nmap, Wi-Fi, and HTTP/TLS observations
  domain/             Shared data objects (Asset, Scan, Service, ...)
  database/           SQLite schema, persistence, snapshot queries
  scanners/           Scanner contract, progress, cancellation, lifecycle
  reports/            Export generation
  config/             Settings, paths, logging, scan policies
  diagnostics/        Live checks on your local computer
  management_api/     Separate authenticated engineering API
  simulation/         Explicit synthetic CLI example
  peripherals/        Three-node USB transport, provisioning and evidence
  hardware/           LCD/button contracts and terminal mocks
  plugins/            Optional plugin contracts and registry
  experimental/       Deferred adapters and legacy analysis
firmware/             Current ESP1/A, ESP2/B, ESP3/C profiles and shared protocol
BWifiKiller/          Earlier standalone firmware and shared ESP1 PCB pin map
tests/                Automated tests, including tests/web/
docs/                 Usage, architecture, and learning guide
scripts/              Environment/deployment helpers
deployment/           Linux service configuration
data/                 Local generated data (ignored by Git)
kali_demo/            Compatibility entry points and existing local data
run.ps1 / run.sh      Website launchers
pyproject.toml        Package, dependency, and test configuration
```

Start learning with [the development guide](docs/development.md). It explains
which files to edit and traces a button click through the application.
See [architecture](docs/architecture.md) for boundaries and data flow.

## Test your changes

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pi_ot_probe.diagnostics.local_check
```

The last command saves actual local observations to `data/local-check.json`.
It tests a temporary loopback HTTP server and one TCP port, not a subnet.

Existing `kali_demo/data/demo.db` is automatically reused. New installations
write to `data/inventory.db`. Set `PI_OT_DEMO_DATABASE` to choose another path.
The website is intended for one local operator and binds to `127.0.0.1`.
