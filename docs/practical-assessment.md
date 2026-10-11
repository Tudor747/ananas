# Practical Pi + ESP workflow

This branch targets general business networks, Wi-Fi and servers. Commercial
engagement management is deferred. The existing `BWifiKiller/` source and
firmware are unchanged. Unknown ESP board/radio models do not block the local
software workflow.

## What works now

1. Start `run.ps1` on Windows or `run.sh` on Linux and open
   `http://127.0.0.1:8088`.
2. In **ESP Toolkit**, register each instrument you actually have. Leave the
   model and firmware marked unverified if needed. A record does not detect a
   USB device or establish a command connection.
3. Select an attached private network and run discovery. Verify selected hosts
   to collect the existing 20-port TCP observations. Inspect an observed web
   port or refresh Wi-Fi when appropriate.
4. Open **Findings & Improvements**. The application produces review leads for
   selected service exposures, plaintext HTTP responses, a legacy TLS protocol
   if actually negotiated, and open/WEP Wi-Fi advertisements reported by the OS.
5. Use the ESP's own controls for field observations. Record the title, subject,
   location, observed time, displayed evidence and next action in **ESP Toolkit**.
   These observations attach to the latest successfully discovered network and
   remain explicitly operator supplied. Enter text evidence, not passwords.
6. Review each observation. Accepting a risk or marking it remediated requires
   a note. That status records an operator decision; it does not run a retest.
7. Export **Bullet-point report** (Markdown) or **Evidence JSON**. Reports include
   findings, improvements, evidence, review notes, and coverage limitations.

Instrument registration works before discovery. Field evidence requires a
current network. There is no physical ESP connection required for these records,
and no automatic ESP data ingestion is claimed. Register a separate instrument
record for a different configuration or firmware; records are append-only in
this first version. Evidence entries are also preserved rather than overwritten.

## How to interpret findings

- TCP/21 and TCP/23 suggest possible FTP/Telnet exposure; the protocol must be
  confirmed before concluding that credentials are sent in plaintext.
- TCP/445, TCP/3389 and TCP/5900 produce access-review suggestions. They do not
  establish weak authentication, missing MFA or an exploitable vulnerability.
- A plaintext HTTP response prompts a check of sensitive workflows and redirects.
  It does not establish that a login uses HTTP.
- Wi-Fi findings require ownership confirmation. Previously observed APs can
  remain in the database; timestamps matter.
- A new evidence revision starts a fresh review. A changed or newly repeated
  observation does not inherit an old remediation decision.
- A new discovery resets current service evidence; rerun verification before
  interpreting the current exposure assessment.
- No findings does not mean secure. The coverage panel lists unassessed areas.

The legacy experimental risk engine remains disabled. The new assessment layer
uses transparent review priorities and recommendations, with no overall network
score and no CVE assertions.

## Unchanged firmware integration boundary

The checked-in firmware has no general serial command parser or structured
Wi-Fi/BLE/RF result stream. Its HTTP dashboard exports the captive-portal log,
not scanner inventory. The Pi application neither imports that log nor controls
the ESP. The installed firmware version still needs verification on hardware.

For now:

- Pi/PC: automated network observations, comparison, review and reporting.
- ESP: operator-controlled instrument, with manual evidence recorded on the Pi.
- Second ESP: another instrument record when available, not an assumed online
  sensor or automatic extension of coverage.

USB power/serial wiring alone will not create the missing firmware API.

## Next technical increments

1. Identify the exact ESP/radio hardware and verify available read interfaces.
2. Add validated service profiles and structured external-tool imports.
3. Add hostname-aware TLS trust/expiry checks and approved-AP comparisons.
4. Record source network zones and validate agreed reachability between zones.
5. Add offline capture analysis and verified product/version enrichment.
6. For detection validation, compare an agreed test with client-provided alert
   evidence. The current manual category can preserve expected/actual results;
   it is not an automated red-team or SIEM integration.

Pi deployment, authentication beyond loopback, and any monitor-mode adapter
support need separate verification. This iteration retains the existing local,
single-operator model and discovery limits.

## Implementation map

- `application/assessment.py`: deterministic evidence-to-review rules and coverage.
- `application/instruments.py`: instrument records, field evidence, review revisions.
- `web/routes/assessment.py`: local JSON endpoints.
- `reports/assessment.py`: JSON and escaped Markdown export.
- `web/static/js/views/assessment.js`: findings and instrument views.
- `tests/web/test_assessment.py`: rule semantics and persistence boundaries.

Three additive SQLite tables hold instruments, field observations and reviews.
Existing scan evidence and baselines are preserved. JSON exports are the portable
representation of the currently displayed assessment, not a database backup.
