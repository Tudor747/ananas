# Architecture

The appliance target is one Raspberry Pi host and one ESP with four physical
buttons, two switches, and two 2.4 GHz antennas. The planned Pi screen presents
two large menu buttons at a time, with swipe and button scrolling. See
[hardware and screen requirements](hardware-and-screen.md) for input decisions.
The flow below describes the existing website; the new menu and hardware input
adapter are not implemented. Both touch and physical navigation should feed the
same menu state, with an input adapter chosen after wiring and transport are known.

All Python code lives in `src/pi_ot_probe`. The website is assembled in
`web/app.py`; `application/service.py` coordinates its work without importing
FastAPI. This allows the same behavior to be tested without a browser.

## Request and observation flow

```text
Browser controller (web/static/js/app.js)
    -> HTTP client (js/api.js)
    -> Route + validated input (web/routes/, web/schemas.py)
    -> Use case (application/service.py)
    -> Target policy + collector (collectors/)
    -> Scan lifecycle (scanners/orchestrator.py)
    -> SQLite (database/)

SQLite -> dashboard read model (application/dashboard.py)
       -> /api/state -> browser views (js/views/)
```

Routes translate request errors to HTTP responses. The service owns operation
state, scan locking, cancellation, and baseline comparison. Collectors run the
external tools and parse their outputs. The orchestrator owns scan status,
evidence persistence, progress notifications, and audit entries. Views build
DOM from observations and receive callbacks for user actions.

## Responsibilities

| Area | Responsibility |
| --- | --- |
| `domain` | Shared records and enums; no web framework or hardware imports |
| `database` | Schema, migrations, parameterized SQL, immutable evidence |
| `collectors/interfaces.py` | Read active local interfaces |
| `collectors/targets.py` | Validate bounded, attached private targets |
| `collectors/process.py` | Run a subprocess with a timeout and captured output |
| `collectors/nmap.py` | Nmap execution and XML parsing |
| `collectors/http.py`, `wifi.py` | Web metadata and OS Wi-Fi inventory |
| `application/baselines.py` | Baseline snapshots, differences, review state |
| `application/dashboard.py` | Compose the browser's current evidence view |
| `database/current_asset.py` | Reconstruct an asset for a verification operation |
| `web/routes` | Inventory, scan, baseline, and export endpoint groups |
| `reports/site.py` | JSON and CSV exports |

## Evidence and identity

Assets are stored by `(site, IP)`. Each scan also stores an immutable JSON
snapshot. Current devices come from the latest completed discovery; only later
completed verification scans overlay their service data. A cancelled or failed
discovery does not generate removal signals or replace the current inventory.

Baseline comparison reserves unique normalized MAC matches before falling back
to IP. Missing MAC evidence is not a MAC change. Persistent device identity
across scans remains future work; a hostname alone does not establish identity.

Legacy finding/score columns remain for storage compatibility. The website
does not compute or display risk scores. The reorganization does not alter the
SQLite schema or move an existing database.

## Collection boundaries

Discovery is Nmap host discovery on a directly attached RFC1918 network of at
most 256 addresses. Verification is a confirmed TCP connect scan of 20 common
ports on one discovered host. HTTP inspection sends one HEAD request to a
previously observed port. All target validation remains server-side.

The scan contracts retain levels 0 (passive), 1 (discovery), 2 (verification),
and 3 (individually authorized active testing). Level 3 accepts one host only.
Planned OT checks are disabled. The website does not run exploits, credential
tests, NSE scripts, or operating-system detection.

The local website has no user login and binds to loopback. Its middleware sets
browser security headers. The separate `management_api/` requires a bearer
token; it is not the website backend. Remote authenticated website management
is future work.

## Assessment and ESP instruments

`application/assessment.py` derives review leads and coverage limitations from
current evidence. It does not activate the legacy risk engine or claim CVEs.
`application/instruments.py` stores operator-defined instruments, manual field
observations and review decisions. Findings refer to exact evidence revisions;
new observations need new reviews. New tables are additive.

`web/routes/assessment.py` exposes these local workflows. Field observations
and reviews are scoped to the current network, with a submitted site guard to
reject stale forms. `reports/assessment.py` exports Markdown and JSON with
evidence, recommendations and unassessed areas. ESP registration is bookkeeping,
not a physical connection or remote-control interface. See
`practical-assessment.md` for the implemented workflow.

Separately, `diagnostics/esp_check.py` talks to the optional diagnostic firmware
in `BWifiKiller/src/usb_diagnostics.cpp`. It uses explicit serial-port selection,
request IDs and bounded waits for PING/SELFTEST. The ESP reads radio SPI response
and button pin levels without launching tools. Results are CLI JSON, not website
inventory or scanner telemetry. See [SSH and USB testing](ssh-and-usb-testing.md).

## Packaging and compatibility

`pyproject.toml` discovers packages under `src` and includes HTML, CSS, and
JavaScript as package data. Use an editable install during development.
The root launchers create a local virtual environment and start
`pi_ot_probe.web.app:app`.

`config/paths.py` resolves packaged static files and the website database.
An explicit `PI_OT_DEMO_DATABASE` takes precedence. An existing repository
database at `kali_demo/data/demo.db` is reused; fresh installations use
`data/inventory.db` relative to the working directory.

The old `kali_demo` launchers delegate to the new entry points. Hardware mocks
are in `hardware/`, unfinished adapters in `experimental/`, and the synthetic
Quick Audit in `simulation/`. These are separate from live website collectors.

## Work intentionally deferred

Real GPIO/LCD drivers, packet capture, OT protocol identification, remote
website authentication, PDF reports, and signed data-only update packs with
rollback remain unfinished. See `development.md` for work you can do and test
on an ordinary computer.
