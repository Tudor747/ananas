# Kali Linux demo

This is a separate, local browser demonstration of the Pi-OT Security Probe
foundation. It runs only the deterministic simulation scanner. It has no input
for an IP address, interface, subnet, or real scanner and sends no network
traffic.

## Start on Kali

Install the Python prerequisites once:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
```

From the cloned project:

```bash
cd kali_demo
bash run.sh
```

Open <http://127.0.0.1:8088> in the Kali browser. Select **Changed site** to
demonstrate five synthetic assets, S7 and Modbus/TCP identification, contextual
findings, a new HMI, a removed historian, a new PLC port, and a duplicate open
Wi-Fi access point. Select **Quiet baseline** for the smaller initial snapshot.

Stop the server with `Ctrl+C`. Its SQLite database is stored at
`kali_demo/data/demo.db` and is ignored by Git.

To use a different local port:

```bash
PI_OT_DEMO_PORT=8090 bash run.sh
```

The launcher always binds to `127.0.0.1`. Do not expose this demonstration
server to another interface; it intentionally has no authentication because it
can perform only local synthetic scans.

## Test without opening a browser

From the project root, with the project dependencies installed:

```bash
python -m unittest discover -s kali_demo/tests -v
```

You can also verify the API after starting it:

```bash
curl http://127.0.0.1:8088/api/health
curl -X POST http://127.0.0.1:8088/api/run \
  -H 'Content-Type: application/json' \
  -d '{"scenario":"changed"}'
curl http://127.0.0.1:8088/api/state
```

