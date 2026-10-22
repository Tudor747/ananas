# Pi-OT Security Probe - Technical Programming Guide

SSH operation and optional ESP USB self-tests are documented in
[SSH and USB testing](../docs/ssh-and-usb-testing.md). The new firmware addition must be flashed
before the ESP can answer; physical deployment has not been verified here.

## Current appliance scope (2026-10-21)

The Raspberry Pi is the sole deployment host, with exactly one ESP companion,
four physical buttons, two switches, and two 2.4 GHz antennas. The planned
interactive Pi screen shows two large primary menu buttons at a time and
supports slide/swipe navigation plus button scrolling. Screen specifications,
control mappings, radio wiring, and the Pi-to-ESP connection remain open; see
[hardware and screen requirements](../docs/hardware-and-screen.md).

This menu and physical input integration are requirements, not implemented
features. Windows/Linux/Kali references below describe existing software
compatibility and development options, not a requirement for a separate PC.

## 1. Pi-OT Security Probe

Pi-OT Security Probe is a local, offline-first engineering console for collecting and reviewing bounded network evidence. The working software runs on Windows, Linux, or Kali without Raspberry Pi hardware. It is designed for an authorized operator who needs a readable inventory of devices, selected service observations, web metadata, Wi-Fi access-point information, and changes over time.

The program intentionally reports observations rather than inferred vulnerabilities, risk scores, or guessed device types. This keeps the output traceable: every displayed fact has a collector, a scan record, a timestamp, and stored evidence behind it.

- Primary interface: a FastAPI website bound to 127.0.0.1:8088 by the root run.ps1 or run.sh launcher.
- Main live features: attached-network discovery, confirmed single-host TCP checks, one-request HTTP/HTTPS inspection, Wi-Fi inventory, baselines, change review, and JSON/CSV exports.
- Development goal: code is organised by responsibility under src/pi_ot_probe so an edit has one obvious home.
- Non-goal: exploit testing, password testing, broad port scanning, operating-system detection, NSE scripts, packet capture, and production OT protocol interaction.

| Audience | What they use it for |
| --- | --- |
| Local operator | Discover and review real evidence on an authorized private network. |
| Developer | Change one layer at a time and validate it with fixtures plus local live checks. |
| Reviewer | Trace a UI observation back to stored scan evidence and a collector. |

## 2. Runtime and source layout

The project uses a Python src layout. The package is installed in editable mode during development, so source changes are used immediately after the server restarts. The root launchers create a virtual environment, install the project, and start uvicorn with pi_ot_probe.web.app:app.

The earlier kali_demo folder is retained only for compatibility launchers and existing local SQLite data. New work belongs in src/pi_ot_probe. This separation removes the ambiguity between the runnable web application, hardware ideas, simulation support, and unfinished experiments.

- docs/development.md is the learning map: it names the file to change for a UI label, route, collector, baseline rule, or report.
- tests/web contains feature tests for the website, collectors, baselines, reports, and live loopback HTTP assembly.

| Folder | Responsibility |
| --- | --- |
| web/ | Application assembly, HTTP routes, request schemas, security headers, HTML, CSS, JavaScript views. |
| application/ | Use cases: scan coordination, baselines, dashboard state, validation-lab descriptions. |
| collectors/ | Adapters for interfaces, target policy, subprocess execution, Nmap, Wi-Fi, and HTTP/TLS. |
| domain/ | Shared typed records: Asset, Service, Scan, protocol and Wi-Fi observations. |
| database/ | SQLite schema, repository methods, and current-asset reconstruction. |
| scanners/ | Scanner contract, cancellation token, lifecycle orchestration, progress, and audit logging. |
| reports/ and diagnostics/ | Raw JSON/CSV exports and a repeatable local-machine verification command. |
| experimental/ and hardware/ | Deferred work; isolated so it cannot blur live website behavior. |

## 3. How a browser action becomes stored evidence

The frontend deliberately separates control, API calls, DOM helpers, and visual views. web/static/js/app.js owns button events and refresh behavior. api.js sends requests and turns failed responses into useful errors. The view modules render data with textContent, so network-provided strings are never treated as HTML.

FastAPI receives the request in a small route group. A Pydantic request schema validates the body. The route calls ProbeService rather than performing a scan directly. This keeps HTTP status handling separate from operational logic and allows the service to be tested without a browser.

| Step | Code path | Purpose |
| --- | --- | --- |
| 1 | web/static/js/app.js → api.js | Read UI input and send a JSON request. |
| 2 | web/routes/scans.py + web/schemas.py | Validate input and translate exceptions to HTTP responses. |
| 3 | application/service.py | Confirm authorization, serialize operations, choose a collector, track progress. |
| 4 | collectors/*.py | Read local state or run a bounded external tool. |
| 5 | scanners/orchestrator.py | Persist scan state, snapshots, audit events, cancellation, and errors. |
| 6 | application/dashboard.py | Build score-free current state from immutable observations. |
| 7 | web/static/js/views/*.js | Render inventory, changes, history, Wi-Fi, and validation information. |

```text
POST /api/real/run  →  DiscoveryRequest  →  ProbeService.run_real()
→ validate_target()  →  NmapDiscoveryScanner  →  ScanOrchestrator.run()
→ SQLite scan_assets snapshot  →  GET /api/state  →  renderAssets()
```

## 4. How local networks are discovered and approved

Network discovery starts by reading the local computer, not by probing the network. collectors/interfaces.py prefers psutil to enumerate active IPv4 interfaces. On Windows it can fall back to a PowerShell adapter; on Linux it can fall back to iproute2 JSON. Loopback and non-private addresses are excluded from discoverable targets.

Each active RFC1918 interface becomes a LocalNetwork record containing the interface name, local address, full connected network, and a safe target. A broad private interface such as 10.0.0.0/8 is never exposed as an unrestricted scan. The UI offers a target limited to a maximum of 256 addresses, normally a /24.

- The website asks the operator to select a local target; it does not accept arbitrary Internet targets.
- The target validation is on the server, so modifying browser JavaScript cannot bypass it.

| Validation rule | Why it exists |
| --- | --- |
| IPv4 only | Keeps the first collector and target model explicit and bounded. |
| RFC1918 only | Rejects public and special-use ranges. |
| Canonical network required | Rejects ambiguous forms such as a host address with a subnet suffix. |
| Maximum 256 addresses | Prevents accidental broad discovery; /24 or smaller only. |
| Must be a subnet of an active interface | Prevents scanning an unrelated private network. |
| Explicit authorization flag | The server rejects discovery before any Nmap process is created. |

```text
validate_target('192.168.100.0/24', local_networks)
# Accepts only an attached RFC1918 IPv4 network with <= 256 addresses.
```

## 5. Bounded collectors: Nmap, web, and Wi-Fi

The discovery collector runs Nmap host discovery only: -sn, a limited maximum rate, one retry, a host timeout, XML output, and a three-minute outer timeout. XML is parsed into Asset records only when Nmap says the host is up. The parser retains IP, MAC, vendor, hostnames, discovery reason, source, and timestamp when observed.

Service verification is a separate, explicitly confirmed operation for one asset from the current discovery. It runs a TCP connect scan against Nmap's 20 common ports, with a maximum rate of five connections per second, one retry, a per-host timeout, and an outer one-minute timeout. It records only open TCP ports and Nmap's structured service details.

- collectors/process.py uses argument arrays, captures output, and kills a timed-out subprocess before raising an error.
- No collector runs OS detection, version scans as a purpose, NSE scripts, credential tests, exploit code, deauthentication, monitor mode, or packet capture.

| Collector | Network action | Evidence retained |
| --- | --- | --- |
| Host discovery | Nmap -sn on an approved /24-or-smaller subnet. | Up hosts, IP/MAC/vendor/hostnames, Nmap reason. |
| Service verification | Nmap TCP connect scan of 20 ports on one selected host. | Open ports, service name, product/version fields when Nmap returns them. |
| HTTP/HTTPS inspection | One HEAD / request to an already observed web port; no redirect following. | Status, headers, HTTP version, TLS details, certificate fingerprint; Set-Cookie values are redacted. |
| Wi-Fi inventory | Normal OS-managed scan through nmcli or netsh after confirmation. | SSID/BSSID, signal, channel, encryption and other OS-provided radio fields. |

## 6. Scan lifecycle, cancellation, and evidence integrity

Every collector implements the Scanner contract and receives a ScanContext plus a shared CancellationToken. The token is checked before and between operations. The service keeps one active token and one active scanner, protected by an asyncio lock, so two scans cannot overwrite progress or make cancellation ambiguous.

ScanOrchestrator creates a short-lived scan record before collection begins. As each collector yields a ScanProgress event, the orchestrator upserts the current asset record and links an immutable JSON snapshot to the scan. The snapshot is the historical evidence; later asset updates cannot rewrite what an earlier scan observed.

- Progress is shown as completed, total, and message; the scan itself never blocks the UI event loop.
- The active product route passes analyze_risk=False. Stored data is displayed as evidence rather than a severity score.

| Outcome | Stored result |
| --- | --- |
| Completed | Scan finalised, snapshots retained, optional collector artifacts stored, audit entry written. |
| Cancelled | Scan marked cancelled and audited. It does not replace the current discovery or create false removals. |
| Failed | Error retained on the scan and in audit history; exception returns to the route for an HTTP error. |
| Task cancellation | Persistence happens before asyncio cancellation is propagated. |

```text
asset_id = repository.upsert_asset(site_id, progress.asset)
repository.link_scan_asset(scan.id, asset_id, observed_at, progress.asset)
# The link stores the immutable observation for this scan.
```

## 7. SQLite model and the meaning of current state

SQLite is the local evidence store. Repository methods own connection setup, foreign-key enforcement, parameterized statements, schema initialization, and table writes. Dynamic values are always bound as SQL parameters. The database stores sites, scans, assets, ports, services, protocols, Wi-Fi access points, web observations, scan-to-asset snapshots, baselines, changes, and audit events.

The assets table is a convenient current record with storage identity (site, IP). It is not the historical truth. scan_assets.snapshot_json preserves the full Asset that a collector yielded. The dashboard deliberately finds the latest completed discovery and uses its snapshots as current inventory. A later completed verification may overlay service information only for that discovered asset.

- Current state excludes cancelled and failed discovery scans.
- Web metadata is filtered to observations collected after the current discovery finished, avoiding stale evidence.
- CSV export neutralizes spreadsheet formulas in user-controlled strings; JSON and CSV export the raw dashboard state rather than grades.

| Data object | Role in the system |
| --- | --- |
| sites | Named scope for scans and observations. |
| scans | Lifecycle state, target, level, timestamps, counts, cancellation, error. |
| assets / ports / services / protocols | Latest observed records used for lookup and queries. |
| scan_assets | Immutable JSON snapshot of an asset at a particular scan. |
| web_observations | Raw bounded HTTP/TLS observations tied to the asset. |
| baselines / baseline_assets | Named reference snapshot with active status. |
| changes | Detected difference, analyst review state, note, and timestamps. |
| audit_log | Operator action, result, duration, target, and error evidence. |

## 8. Baselines and change detection

After reviewing a completed discovery, the operator can create a named baseline. The baseline stores asset and Wi-Fi snapshots, not live rows that may change later. Later completed scans are compared against the selected baseline and differences enter a review queue. Analysts can acknowledge a record and set its status to New, Investigating, Confirmed observation, Expected change, or Resolved with a note.

Identity is deliberately conservative. The baseline comparison first reserves unique, case-normalized MAC matches. It only falls back to IP when there is no unique MAC match. This avoids a DHCP reassignment at one IP stealing the match from a device that moved to another IP. Missing MAC data is treated as missing evidence, not a MAC change.

- A cancelled discovery never produces removal changes.
- A new discovery resets current service evidence until that host is checked again, preventing old ports from looking current.
- Persistent multi-factor identity reconciliation across MAC, IP, hostname, and confidence is a future improvement; hostname alone is not identity.

| Detected condition | How it is derived |
| --- | --- |
| New device | Current asset has no resolved baseline match. |
| Device removed | Baseline asset has no resolved current match after a completed discovery. |
| MAC/IP changed | A unique MAC match has a different IP, or both observed MAC values differ on an IP match. |
| New port | A port exists in current verified evidence and not in the baseline snapshot. |
| Wi-Fi difference | BSSID-backed access point observations differ from the baseline. |

## 9. Safety model, security controls, and level 3

The local website binds to 127.0.0.1 and is designed for one local operator. It has browser security headers: no framing, no MIME sniffing, a same-origin content-security policy, no referrer, and no-store caching. The separate management_api package is a different engineering API and requires a bearer token with at least 32 characters; it is not the browser application's default backend.

Safety is enforced in layers: route validation, service authorization checks, attached-target policy, scan level rules, low rate limits, subprocess timeouts, one active operation, cancellation, immutable evidence, and audit entries. This means the browser is not trusted as the only gate.

- Read-only does not mean risk-free: a protocol request still transmits traffic and can affect fragile or legacy industrial equipment.
- Level 3 needs a lab-safe simulator or device, explicit authorization, one selected host, rate limits, cancellation, evidence logging, and test coverage before it can be enabled.
- No Raspberry Pi is required to develop the website or test levels 1–2 on an authorized local machine.

| Level | Current behavior |
| --- | --- |
| 0 — Passive | Modelled in the scanner contract; no packet capture implementation in the current website. |
| 1 — Discovery | Available: bounded Nmap host discovery on an authorized attached private subnet. |
| 2 — Verify | Available: confirmed one-host TCP check, web metadata inspection, and OS-managed Wi-Fi inventory. |
| 3 — Active test | Not available: planned protocol-specific read-only identity requests for one approved lab device. |

## 10. Running, testing, and extending the program

On Windows, run PowerShell from the repository root and execute .\run.ps1. The launcher creates .venv if needed, installs the editable project, and starts the local website. The first launch needs Python 3.11+ and Nmap for discovery. The UI itself can open without Nmap, but live discovery and port checks require it.

The project uses three complementary forms of validation. Unit and integration tests use controlled fixtures for repeatability. A live loopback website test starts the real FastAPI app and checks HTML, imported JavaScript modules, APIs, exports, headers, and authorization behavior. The local diagnostics command reads real local interfaces, starts a temporary 127.0.0.1 HTTP server, collects its response, and checks the server's open TCP port with Nmap.

- Use short comments for decisions and constraints, such as why a timeout exists or why a snapshot must stay immutable.
- Test behavior, not implementation names. The test suite currently contains 39 tests, including real local-loopback assembly coverage.
- Next programming priorities: stronger device identity reconciliation, safe OT lab simulators and level-3 checks, PDF export, and signed data-only update packs.

| When changing… | Start here |
| --- | --- |
| Page layout, labels, CSS | web/static/index.html, css/styles.css, js/views/ |
| Button action or API error | web/static/js/app.js and api.js |
| Endpoint or input | web/routes/ and web/schemas.py |
| Scan workflow | application/service.py and scanners/orchestrator.py |
| Nmap / interface policy | collectors/nmap.py, interfaces.py, targets.py |
| Stored state / report | database/, application/dashboard.py, reports/site.py |

```text
cd D:\proiecte\ananas
.\run.ps1
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pi_ot_probe.diagnostics.local_check
```

## Source basis

This document describes the implementation in `src/pi_ot_probe`, its tests, and the local launchers in this repository. It deliberately describes implemented behavior and separately labels deferred work.
