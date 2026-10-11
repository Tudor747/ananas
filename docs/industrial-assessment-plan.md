# Industrial assessment workstation: proposed build specification

Status: long-term design proposal, 2026-10-10. The selected first scope is now
general business networks, Wi-Fi and servers, focused on practical tooling.
Commercial engagement management is deferred at the user's request. Exact ESP
and radio models remain unknown; work proceeds with manual instrument records.

The first implementation adds findings and improvements, coverage reporting,
manual ESP observations, review decisions and Markdown/JSON reports. See
[the practical workflow](practical-assessment.md) for what is implemented.
The remaining capabilities below are proposals, not verified hardware features.

## Objective and fixed constraints

Build the `esp` branch into an on-site assessment workstation for a freelance
cybersecurity service. The operator should be able to explain each client's
exposures, supported security findings, recommended improvements, and retest
results using traceable evidence.

- Raspberry Pi 5 is the planned application host.
- Two ESP devices are planned; exact boards and attached radios are unconfirmed.
- Three antennas or fewer is a design preference; whether this means external
  antennas or all antennas remains unconfirmed.
- Preserve all files under `BWifiKiller/` and the firmware already installed on
  the user's ESP. No reflash is required by this proposal.
- Reuse the working Python application and its collection and evidence layers.
- Do not assume the installed firmware matches the checked-in source: the
  firmware README distinguishes original binaries from translated local source.

## Findings from the existing firmware source

| Interface | Observed implementation | Integration consequence |
| --- | --- | --- |
| USB serial | `Serial.begin(115200)` and limited diagnostics; no general command parser or scan-result stream found | USB does not currently provide remote scan control or structured inventory |
| Dashboard HTTP | `/`, `/get-logs`, `/download-logs`, `/clear-logs` in `include/web_server.h` | This is a log viewer, not a general sensor API |
| Exported log | `/logins.txt`, populated by `src/evil_portal.cpp` with submitted identifiers/passwords and network labels | Do not treat this as Wi-Fi/BLE inventory; do not automatically import it into client reports |
| ESP-NOW slave control | A boolean state message, fixed peer settings, and broadcast sends | Not a general two-device telemetry or Pi control protocol |
| Tool lifecycle | One current application selected by the menu host | Do not promise concurrent dashboard, BLE, Wi-Fi, and RF operation |
| Dashboard addressing | The same AP configuration for each unchanged unit | Simultaneous access to two identical dashboard networks needs separate routing/interfaces or sequential sessions |
| RF heatmap/advisor/scope | Channel sampling using `testCarrier()` | Treat outputs as relative activity indicators, not calibrated spectrum measurements or protocol identification |

The initial ESP integration is therefore a device registry plus operator-led
workflows and manual evidence attachments. A hardware session must verify actual
firmware behavior before enabling any optional adapter. Button automation is
not part of the first implementation: it would not produce reliable structured
sensor data and would depend on hidden menu state.

## Proposed division of responsibilities

```text
Operator browser
    -> Pi application
       -> clients, engagements, approved scope, and asset ownership
       -> Pi collectors and imported tool results
       -> evidence store and reviewed findings
       -> executive report, technical appendix, remediation, retesting

ESP unit A and ESP unit B, firmware unchanged
    -> operator selects a tool on each device
    -> operator records observation, location, time, device, and attachment
    -> Pi evidence store, explicitly labelled as operator supplied
```

Client network access and instrument-management access should be distinct.
Do not bridge them automatically. Ethernet is the primary proposed assessment
connection. A SPAN/mirror port or TAP would supply passive OT visibility when
provided by the client; an ordinary switch connection does not expose all
traffic. Raspberry Pi packet capture and OT decoding are new work, not existing
capabilities.

The ESP32 targeted by this firmware provides 2.4 GHz Wi-Fi/Bluetooth. Do not
promise 5/6 GHz coverage from it. Pi 5 has dual-band Wi-Fi, Bluetooth, Ethernet,
and USB, but monitor-mode capability must be verified for the exact adapter,
driver, and OS. Additional antenna count does not establish protocol coverage.
The bill of materials remains open until boards, radios, roles, and power needs
are confirmed.

## Product workflow

1. Create client, site, and engagement.
2. Record authorized targets, exclusions, zones, test window, and allowed checks.
3. Select assessment vantage point and connect only the intended collector.
4. Collect observations or attach reviewed external evidence.
5. Correlate observations with client-approved assets and configuration evidence.
6. Draft findings with evidence, impact, confidence, and specific remediation.
7. Review and publish a versioned client report.
8. Assign remediation owners and perform a follow-up assessment.

An assessment from one network zone proves reachability only from that zone.
Internet exposure requires a separate authorized external vantage point or
appropriate firewall/NAT evidence. A visible SSID does not establish client
ownership or that the access point is unauthorized.

## Capabilities to build

| Capability | First implementation | Evidence requirement / limit |
| --- | --- | --- |
| Engagement management | Clients, sites, scope, exclusions, dates, test modes | Existing global current-site behavior must be replaced by explicit engagement selection |
| Hardware registry | Two named ESP records with model, firmware, connection and tested capabilities | Record unknown capabilities as unknown; no invented connection status |
| Inventory | Reuse host discovery and service evidence | Persist interface, zone and collector identity with every observation |
| Exposure review | Service exposure and configuration findings | An open port is exposure; software vulnerability requires additional evidence |
| Wireless review | Approved AP list, observed security mode, manual survey evidence | Unknown APs are candidates for investigation, not automatically rogue APs |
| Segmentation review | Expected reachability matrix and bounded checks from approved zones | Requires access to the actual source zones; not inferred from one subnet |
| Web/TLS checks | Add hostname-aware trust, expiry and configuration checks | Existing HEAD inspection deliberately does not validate certificates |
| Vulnerability enrichment | Import verified identity/version data and reference advisories | Track advisory source/date and prerequisites; banner matches remain candidate findings |
| OT visibility | Start with approved asset/config exports and offline capture imports | Live passive capture and protocol decoding require separate implementation and validation |
| Detection validation | Record controlled test, expected telemetry, actual alert and timestamps | Access to client logs/SIEM evidence is required to assess detection |
| Remediation/retest | Owner, target date, fix evidence and retest result | Preserve original findings and historical report versions |

Credentialed configuration review can later add patch state, account policy,
remote access, backup and logging coverage. These cannot be inferred reliably
from radio activity or unauthenticated network discovery.

## Finding and evidence model

Proposed entities:

- Client -> Site -> Engagement -> NetworkZone.
- Instrument: model, firmware identity, capabilities, connection and validation.
- AssessmentRun: engagement, collector version, scope, vantage point, parameters,
  start/end, outcome and coverage gaps.
- Evidence: engagement, source, collection method, collection/import times,
  attachment hash, redaction status and original observation.
- Finding: title, category, affected assets, evidence references, observation,
  analyst interpretation, confidence, impact, severity rationale, remediation,
  owner, status and retest.
- ValidationExercise: agreed objective, allowed actions, expected detections,
  actual telemetry, timing, outcome and cleanup record.
- ReportVersion: engagement, included finding/evidence revisions, author and date.

Keep these dimensions separate:

- Evidence status: observed, inferred, unverified, not assessed.
- Finding lifecycle: draft, reviewed, accepted risk, remediation planned, fixed,
  retested, reopened.
- Severity: informational through critical, with a written justification.
- Confidence: strength of supporting evidence, independent of impact.

Use source hashes to detect changed attachments; do not describe a local editable
database as tamper-proof. Keep sensitive client artifacts out of Git. Scope every
query and export to the selected engagement, including attachments and reports.

Example finding, fictional:

> Engineering workstation management service reachable from guest VLAN.
> Evidence: approved single-host connection test from the guest-zone collector,
> recorded at a specified time, plus owner-confirmed asset role.
> Impact: expands the reachable management surface beyond the intended zone.
> Recommendation: restrict access to the management zone and approved jump host.
> Retest: confirm denied access from guest and intended access from management.

Do not infer missing MFA, an exploitable software flaw, or internet exposure from
that connection test alone.

## Blue-team and red-team workflows

Blue-team work should cover inventory, configuration review, exposure,
segmentation, baselines, telemetry gaps, remediation, and retesting.

Red-team work should be represented as objective-led, explicitly scoped
exercises with evidence of the actions and defensive response. Running a
vulnerability scan is not equivalent to a red-team engagement. The first
implementation should support controlled validation and exercise evidence;
expanding executable checks depends on the selected customer and lab fixtures.

Production OT profiles should begin with passive/imported evidence. Protocol
requests, even read-only ones, need device-specific validation and an agreed
window. Disruptive RF features in the unchanged firmware should not become
automatic Pi assessment actions. The Pi cannot enforce limits on a separately
operated ESP; UI restrictions must not claim otherwise.

## Proposed implementation order and acceptance criteria

### Future milestone: deliverable for the first client (deferred)

- Engagement selection and explicit client data isolation.
- Device registry with honest firmware capability labels.
- Manual evidence entry/attachments for ESP observations and configuration review.
- Findings editor with evidence links, confidence, impact and remediation.
- Client report with executive bullets, affected assets, prioritized actions,
  technical evidence, methods, and untested areas.
- Reuse existing collectors only within their current verified bounds.

Acceptance: two sample engagements cannot read or export each other's evidence;
an ESP observation is clearly manual; every published finding has evidence and
remediation; reports include coverage limitations; `BWifiKiller/` is unchanged.

### Milestone 2: stronger technical assessments

- Server-side scope enforcement for all supported collectors and imports.
- Source-zone awareness, custom bounded service checks, and improved TLS evidence.
- Approved AP comparison and clearer baseline change coverage.
- Structured Nmap and other supported tool imports with collector provenance.
- Analyst-reviewed advisory matching from verified product identity.
- Retest workflow and before/after report.

Acceptance: out-of-scope targets are rejected, unsupported CVE claims are not
published as confirmed, source zones appear in findings, and cancellations and
timeouts retain an accurate audit record.

### Milestone 3: OT and detection engineering

- Offline packet-capture ingestion and verified protocol parsers.
- Passive capture from a provided mirror/TAP interface.
- Agreed reachability matrix for IT/OT zones.
- Detection exercise timeline with client-provided alert evidence.
- Individually validated OT identity collectors where operationally appropriate.

Acceptance: passive capture does not run active discovery; capture limits and
drops are reported; protocol labels require packet evidence; missing traffic is
not presented as proof of absence; device checks are verified in a lab first.

### Milestone 4: appliance deployment

- Pi installation and health checks for storage, interfaces, clock and collectors.
- Authentication before exposing management beyond loopback.
- Appropriate local storage protection, backup/restore and retention controls.
- Stable device naming and interface roles; no automatic client-network bridge.
- Documented hardware compatibility and verified resource limits.

## Decisions still needed

1. Exact ESP boards, nRF modules, installed firmware, wiring and antenna meaning.
2. Confirmed first technical scope: general business networks, Wi-Fi and servers.
3. Service packaging is deferred; focus on practical capabilities.
4. Whether manual ESP operation is acceptable while preserving firmware.
5. Expected client access: Ethernet, mirror port, VLANs, configurations, test
   accounts and defensive logs.
6. Hardware budget, Pi OS preference, report language and output formats.

## Reference material

- Local firmware: `BWifiKiller/include/web_server.h`,
  `BWifiKiller/include/app_config.h`, `BWifiKiller/src/main.cpp`,
  `BWifiKiller/src/app_lifecycle.cpp`, `BWifiKiller/src/slave.control.cpp`.
- Existing application boundaries: `docs/architecture.md`, `docs/usage.md`.
- [Raspberry Pi 5 specifications](https://www.raspberrypi.com/products/raspberry-pi-5/).
- [ESP32 product overview](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32/product-overview.html).
- [NIST SP 800-82 Rev. 3, Guide to OT Security](https://csrc.nist.gov/pubs/sp/800/82/r3/final):
  OT performance, reliability and safety considerations. Use as design guidance;
  this product does not establish compliance or certification.
