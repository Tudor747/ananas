# V2/V3 discovery and baseline app

This is a separate, local browser application for safe Pi-OT Security Probe
host discovery. It detects active private IPv4 interfaces, lets the operator
select one local subnet, and stores real responding devices in SQLite.

The default scan is deliberately limited to Nmap host discovery (`-sn`). V2
also provides an optional **Verify services** action for one selected asset. It
uses a TCP connect scan of only 20 common ports, capped at five connections per
second. It does not detect versions or operating systems, run NSE scripts, test
credentials, exploit devices, or perform denial-of-service actions.

Targets are restricted to directly connected RFC1918 networks of 256 addresses
or fewer. The operator must explicitly confirm authorization, all scans have
timeouts, and every operation can be cancelled and is audit logged.

V3 adds named site baselines, automatic comparison after discovery, new and
removed device detection, MAC/IP and new-port changes, Wi-Fi AP inventory,
change acknowledgement, and downloadable JSON/CSV reports.

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
Use **Verify services** on an individual asset only when the additional TCP
connections are acceptable. Create a baseline after reviewing the inventory;
later discovery runs are compared automatically.

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
curl -X POST http://127.0.0.1:8088/api/baseline \
  -H 'Content-Type: application/json' \
  -d '{"name":"Approved site"}'
curl http://127.0.0.1:8088/api/state
curl -OJ http://127.0.0.1:8088/api/reports/site.json
curl -OJ http://127.0.0.1:8088/api/reports/assets.csv
```

The API rejects public networks, networks not attached to the machine, targets
larger than `/24`, and requests without authorization confirmation. Use
`POST /api/cancel` to stop an in-progress discovery or service-verification scan.

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

If port 8088 is already occupied, stop the old server with `Ctrl+C` or use:

```powershell
$env:PI_OT_DEMO_PORT = "8090"
.\run.ps1
```
