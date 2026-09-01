# Pi-OT Security Probe

Safe Phase 1 foundation for an offline-first Raspberry Pi IoT/OT security
appliance. The current Quick Audit uses synthetic data only and does not contact
the network.

## Requirements

- Python 3.11 or newer
- No third-party package is needed for the simulation CLI or unit tests
- FastAPI and Uvicorn are needed only for the engineering API

## Run the simulated Quick Audit

From the repository root:

```bash
python -m pi_ot_probe quick-audit --simulation
```

This renders a mock 16x2 LCD, runs the `changed` scenario, and creates
`data/pi_ot_probe.db`. Useful alternatives:

```bash
python -m pi_ot_probe quick-audit --simulation --scenario baseline
python -m pi_ot_probe quick-audit --simulation --no-lcd --json
SIMULATION_MODE=true python -m pi_ot_probe quick-audit
```

PowerShell environment syntax is:

```powershell
$env:SIMULATION_MODE = "true"
python -m pi_ot_probe quick-audit
```

The changed scenario contains five devices and synthetic examples of a new HMI,
a removed historian, a new PLC web port, an open duplicate SSID, S7/Modbus
detection, and high contextual risk. Findings explicitly describe service
exposure rather than claiming a vulnerability.

Press `Ctrl+C` to abort the CLI. Scanner implementations also receive a shared
cancellation token and must check it between operations.

## Run tests

```bash
python -m unittest discover -s tests -v
```

Or, after installing development requirements:

```bash
python -m pip install -e ".[dev]"
pytest
```

## Run the local engineering API

Generate and export a private token; there is no default credential:

```bash
export PI_OT_API_TOKEN="replace-with-at-least-32-random-characters"
python -m pi_ot_probe serve
```

PowerShell:

```powershell
$env:PI_OT_API_TOKEN = "replace-with-at-least-32-random-characters"
python -m pi_ot_probe serve
```

It binds to `127.0.0.1:8080` by default. Send the token as
`Authorization: Bearer <token>`. Configuration variables include
`PI_OT_DATABASE`, `PI_OT_LOG_LEVEL`, `PI_OT_MANAGEMENT_HOST`, and
`PI_OT_MANAGEMENT_PORT`.

## Repository map

See [ARCHITECTURE.md](ARCHITECTURE.md) for components, data flow, scan levels,
hardware abstraction, persistence, security controls, and phased boundaries.
Real network probing, GPIO, packet capture, Wi-Fi scanning, and OT protocol
traffic are intentionally deferred until the foundation is reviewed.
