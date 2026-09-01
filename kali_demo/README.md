# Kali Linux demo

This is a separate, local browser application for safe Pi-OT Security Probe
host discovery. It detects active private IPv4 interfaces, lets the operator
select one local subnet, and stores real responding devices in SQLite.

The real scan is deliberately limited to Nmap host discovery (`-sn`): it does
not scan ports, detect versions or operating systems, run NSE scripts, test
credentials, exploit devices, or perform denial-of-service actions. Targets are
restricted to directly connected RFC1918 networks of 256 addresses or fewer.
The operator must explicitly confirm authorization, scans are capped at 10
probes per second, timeout after three minutes, and can be cancelled.

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
curl http://127.0.0.1:8088/api/state
```

The API rejects public networks, networks not attached to the machine, targets
larger than `/24`, and requests without authorization confirmation. Use
`POST /api/cancel` to stop an in-progress discovery scan.
