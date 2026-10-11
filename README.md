# Pi + ESP Assessment Workstation

A local website for business network inventory, bounded service checks,
HTTP/TLS observations, Wi-Fi inventory, baselines, and evidence-backed assessment
review. It adds an operator-controlled companion workspace for existing
BWifiKill ESP instruments without changing their firmware. It runs on an
ordinary computer; Raspberry Pi 5 is the planned portable host.

**Findings & Improvements** links observed exposure to specific follow-up actions
and exports a bullet-point Markdown report or evidence JSON. Priorities are
review suggestions, not vulnerability scores. **ESP Toolkit** registers unknown
hardware and preserves manual observations with source, time and location.
The unchanged firmware does not expose a verified scan telemetry/control API;
registration does not establish a physical connection.

See [the practical workflow](docs/practical-assessment.md) for the current
capabilities, limits, and next technical steps.

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
  hardware/           LCD/button contracts and terminal mocks
  plugins/            Optional plugin contracts and registry
  experimental/       Deferred adapters and legacy analysis
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
