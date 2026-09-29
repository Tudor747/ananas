# Run and use the local website

## Windows

Install Python 3.11 or newer and [Nmap](https://nmap.org/download).
Nmap's installer normally includes Npcap. If Nmap is on another drive, add its
directory to PATH. Open a new PowerShell window after installation.

```powershell
cd D:\proiecte\ananas
Set-ExecutionPolicy -Scope Process Bypass
.\run.ps1
```

Open http://127.0.0.1:8088. The launcher sets up `.venv/` automatically.
Use `.\run.ps1 -Port 8090` if the port is occupied. Stop with Ctrl+C.
The old `kali_demo/run.ps1` delegates to this launcher.

## Linux / Kali

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nmap iproute2
bash run.sh
```

Run the launcher from the repository root. To select a different port:
`PI_OT_DEMO_PORT=8090 bash run.sh`.

## Working with real observations

1. Select an attached private network and confirm authorization.
2. **Discover devices** runs bounded host discovery (`nmap -sn`).
3. **Check 20 TCP ports** optionally checks one discovered device, at up to five
   connections per second. Only run it where those connections are acceptable.
4. **Inspect HTTP/HTTPS** sends one `HEAD /` request to an observed web port.
5. Create a named baseline after reviewing the inventory. Later observations
   appear in Change Review with review states and analyst notes.
6. Export JSON or CSV to retain the collected observations.

Targets must be directly attached RFC1918 networks of 256 addresses or fewer.
Discovery and service checks support cancellation and record an audit trail.
Hostnames depend on DNS/Nmap. MAC/vendor usually require the same layer-2
segment. Missing evidence is shown as **Not observed**.

HTTP inspection records headers, status, TLS protocol/cipher, and certificate
fingerprint. It does not follow redirects or validate the TLS certificate;
the stored observation makes this limitation explicit. Cookie values are
redacted. These are observations, not security grades.

Wi-Fi inventory uses NetworkManager/nmcli on Linux or WLAN AutoConfig/netsh on
Windows. It requires operator confirmation. Available fields differ by OS.
It does not use monitor mode, capture client traffic, or deauthenticate devices.

## Data and settings

- `PI_OT_DEMO_PORT`: website port (default 8088).
- `PI_OT_DEMO_DATABASE`: explicit website SQLite path.
- Existing `kali_demo/data/demo.db` is reused automatically.
- Fresh installations use `data/inventory.db` from the working directory.

The launchers bind to `127.0.0.1`; the website is for one local operator and
has no user authentication. No database or schema migration is needed for the
new source layout.

## Local software checks

After starting the launcher once to install dependencies:

```powershell
.\.venv\Scripts\python.exe -m pi_ot_probe.diagnostics.local_check
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
```

The local check reads interfaces and tests a temporary HTTP server and single
TCP port on `127.0.0.1`. Actual headers and Nmap XML go to
`data/local-check.json`. Use `--output path/to/report.json` for another file.
Exit codes: 0 passed, 1 failed, 2 partial because a dependency was unavailable.
TLS, Wi-Fi scanning, and OT protocols are outside this check's scope.

The test suite uses fixtures plus a live loopback website test. It does not
perform a subnet scan. You can also run it without pytest using
`.\.venv\Scripts\python.exe -m unittest discover -s tests -v`.

## Other entry points

The synthetic CLI remains explicit and sends no network packets:

```powershell
.\.venv\Scripts\python.exe -m pi_ot_probe quick-audit --simulation --no-lcd --json
```

The separate engineering API requires `PI_OT_API_TOKEN` containing at least
32 random characters and starts with `python -m pi_ot_probe serve`. It binds
to `127.0.0.1:8080` by default. Requests use `Authorization: Bearer <token>`.
Linux deployment configuration lives in `deployment/`; it is not required to
run the website locally.
