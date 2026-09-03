# Pi-OT Security Probe Architecture

## Scope and principles

This repository contains a Phase 1 foundation plus the runnable V4 local
inventory application in `kali_demo/`. The application supports bounded Nmap
host discovery, single-host service checks, managed-mode Wi-Fi inventory,
baselines, raw exports, and one-request HTTP/HTTPS metadata inspection.

The design is offline-first, evidence-oriented, hardware-independent, and
conservative around industrial systems. It reports observations without risk
scores, grades, inferred vulnerabilities, or inferred device classifications.

## Components

```text
Buttons -> UI controller -> Scan orchestrator -> Scanner / plugins
   |              |                 |                  |
  LCD         progress events   safety policy     observations
                                      |
                          evidence normalization
                                      |
                              SQLite repository
                                      |
                         authenticated local API
```

- `core`: storage- and UI-independent asset, scan, protocol, service, Wi-Fi,
  change, and progress models. Legacy score fields remain storage-compatible
  but are not used by active product paths.
- `config`: environment settings and profile safety policy. INDUSTRIAL defaults
  to passive collection and the lowest request rate.
- `scanners`: scanner contract, cancellation token, supplemental artifacts, and
  lifecycle orchestrator. The scanner yields progress so the UI event loop is
  never held for the duration of a scan.
- `simulation`: synthetic site snapshots. The changed scenario demonstrates a
  new device, a removed device, a new PLC port, a duplicate/open AP, PLC/HMI
  identification and repeatable observation changes.
- `plugins`: explicit in-process registry and an asynchronous plugin contract.
  Update packs cannot add Python modules or register executable code.
- `analysis`: legacy experimental modules retained for compatibility; not
  invoked by the CLI, engineering API, or V4 browser application.
- `database`: explicit SQLite schema and a narrow repository boundary.
- `ui`: hardware-independent LCD and button contracts. `MockLCD` renders an
  exact 16x2 display in any terminal.
- `api`: local FastAPI application factory. Every route requires a bearer token
  of at least 32 characters; no default credential exists.
- `discovery`, `wifi`, `ot`, `baseline`, `capture`, `updates`, `reports`, and
  `system`: replaceable subsystem boundaries for later phases.

## Data flow

1. The LCD, CLI, or API creates a `Scan` with a site, profile, level, and target.
2. The orchestrator checks that the scanner permits that level. Level 3 also
   requires explicit authorization and one host address, not a subnet.
3. A short-lived scan record is created before work begins.
4. The scanner asynchronously yields `ScanProgress` observations and checks its
   cancellation token between operations.
5. Raw observations are normalized without assigning a risk or vulnerability.
6. Parameterized SQLite statements upsert assets and evidence. Auxiliary
   Wi-Fi and change observations use the same repository boundary.
7. Completion, cancellation, and failure all finalize the scan and append an
   audit entry. Exceptions are retained and then propagated.
8. The LCD receives only short progress messages. The authenticated API
   exposes detailed stored records to engineers.

## Scan levels and safety gates

| Level | Name | Intended behavior | Gate |
|---:|---|---|---|
| 0 | Passive | Observe existing traffic and configuration | No transmitted probes |
| 1 | Discovery | Slow, bounded host/port enumeration | Explicit target and profile limits |
| 2 | Verify | Reachability, public banners, TLS/HTTP checks | Operator confirmation and rate limits |
| 3 | Active Test | Individually selected safe plugins | One selected host, confirmation, authorization, audit, cancellation |

Level 3 will never accept a CIDR or an implicit whole-network target. A future
UI controller must collect the required confirmation(s), set `authorized`, and
keep the ACTION/BACK cancellation route available. INDUSTRIAL requires one
confirmation for verification and two for active testing. Plugin metadata
declares its maximum safety level, OT suitability, and confirmation need.

## Hardware abstraction

`LCD` and the button manager do not import Raspberry Pi libraries. The terminal
implementations support development and automated tests. Phase 2 GPIO drivers
will implement the same contracts and read pin assignments only from hardware
configuration. Similarly, `WifiInterface` separates built-in managed-mode Wi-Fi
from a future USB monitor-mode adapter.

This keeps scanner, database, evidence, and UI logic runnable on ordinary Linux,
macOS, and Windows machines. Hardware import failures cannot break simulation.

## Persistence model

SQLite tables cover sites, scans, assets, interfaces, ports, services,
protocols, APs, web observations, scan results, legacy findings/score storage, baselines, snapshots,
changes, capture metadata, signed update packs, and the audit log. Every dynamic
value is passed as a query parameter. Foreign keys are enabled per connection.

Asset identity is currently `(site, IP)` for the first runnable slice. Phase 3
must introduce baseline identity reconciliation using MAC, IP, hostname, and
confidence so DHCP changes are represented correctly rather than overwriting
history.

## Appliance security model

- Bind management to `127.0.0.1` unless an administrator deliberately changes
  it. Network exposure and TLS termination are deployment decisions.
- Require a randomly generated API token through `PI_OT_API_TOKEN`; source code
  contains no credentials. Browser sessions and CSRF controls belong to the
  later web UI, while the current API uses bearer authentication.
- Run the service as `pi-ot-probe`, not root. The systemd unit denies new
  privileges, protects the filesystem, uses a private temporary directory, and
  grants write access only to the data directory.
- Give capture/network helpers narrowly scoped Linux capabilities or sudo rules
  later; never run the entire web/UI process as root.
- Never construct shell commands from input. Future trusted-tool adapters use
  argument arrays, validated interfaces/targets, timeouts, bounded output, and
  cancellation.
- Store the database and secrets with restrictive permissions. Audit all active
  operations, including result, duration, cancellation, and error.
- Treat update JSON as untrusted data. Phase 6 must validate schema,
  compatibility, version, hash, and a pinned-key digital signature before an
  atomic activation. Previous packs remain available for rollback. Packs cannot
  deliver executable Python.

## Phase boundaries

1. Foundation: models, schema, scanner/plugin contracts, simulation, Quick
   Audit, mock LCD, authenticated API skeleton, and tests.
2. V2 preview in `kali_demo/`: cross-platform interface detection, real bounded
   Nmap host discovery, explicitly confirmed single-host service verification,
   progress/cancellation, raw evidence, HTTP/TLS metadata, and JSON/CSV reports.
3. V3 preview in `kali_demo/`: named baseline snapshots, scan-to-asset evidence,
   automatic change comparison, acknowledgement, historical changes, and safe
   Wi-Fi AP inventory. Raspberry Pi GPIO/LCD drivers remain to be integrated.
4. Passive-first Modbus, S7, OPC UA, BACnet, and EtherNet/IP identification.
5. Confirmed, rate-limited verification plugins; safe defaults only.
6. Signed data-only update packs and rollback.
