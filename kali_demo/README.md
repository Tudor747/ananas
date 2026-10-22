# Run the assessment workstation on Kali

This is a compatibility/development guide. The appliance uses a Raspberry Pi
as its only host and exactly one ESP with four buttons, two switches, and two
2.4 GHz antennas. The planned Pi menu shows two large buttons at a time with
swipe and button scrolling. See the
[current hardware and screen requirements](../docs/hardware-and-screen.md).

`kali_demo` starts the current Pi + ESP Assessment Workstation, including network
discovery, service checks, Wi-Fi inventory, baselines, Findings & Improvements,
ESP Toolkit, and report exports. The application source is in `src/pi_ot_probe/`.
Keep this folder inside the full repository.

## Install and start

Use Python 3.11 or newer. In a Kali terminal, install the system prerequisites:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nmap iproute2
```

From the repository root:

```bash
bash kali_demo/run.sh
```

Or, if your terminal is already inside `kali_demo`:

```bash
bash run.sh
```

The launcher creates a Python environment in the repository root and installs
the current application. First-time setup needs access to the Python package
index unless the dependencies are cached. Run the launcher as your normal user.

Open **http://127.0.0.1:8088** in the browser on the same Kali computer or VM.
Keep the terminal open; press **Ctrl+C** to stop the server.

## Setup and checks

These commands run from the repository root:

```bash
# Install without starting the server.
bash kali_demo/run.sh --setup

# Check interfaces, a temporary loopback HTTP server and one local TCP port.
bash kali_demo/run.sh --check --no-install

# Start with installed dependencies, including when offline.
bash kali_demo/run.sh --no-install

# Use another port if 8088 is occupied.
bash kali_demo/run.sh --port 8090 --no-install
```

Checks write `data/local-check.json` relative to the repository root. Exit codes
are 0 for passed, 1 for failed, and 2 for partial results when a dependency such
as Nmap is unavailable. They do not scan your subnet.
To save a separate report, add `--output data/kali-check.json` to `--check`.

Once the page opens, select your own network, confirm authorization, and choose
**Discover devices**. Select a discovered device for **Check 20 TCP ports**,
review **Findings & Improvements**, and export a report. ESP Toolkit stores
instrument records and manual observations; registration does not connect an ESP.

Wi-Fi inventory uses `nmcli` from NetworkManager and needs an available Wi-Fi
interface. A VM's virtual Ethernet interface does not expose the host's Wi-Fi
radio. See [usage](../docs/usage.md) for collector limits and configuration.

## Troubleshooting

- **`$'\r': command not found` or `invalid option ... pipefail`:** the shell file
  has Windows line endings. This repository now pins `.sh` files to LF. To
  repair an older copy, run from the repository root:
  `sed -i 's/\r$//' run.sh kali_demo/run.sh`.
- **`Permission denied` when running `./run.sh`:** use `bash run.sh`; executable
  permission is not required for that command.
- **Python or venv errors:** install the prerequisites above and check
  `python3 --version`. A broken environment produces its path in the error;
  rename that environment directory and rerun setup.
- **A checkout copied from Windows:** Windows and Linux Python environments are
  incompatible. The launcher uses `.venv-linux/` when `.venv/` contains a Windows
  environment, preserving the Windows environment.
- **`Address already in use`:** use `--port 8090`, then open
  `http://127.0.0.1:8090`.
- **The browser cannot connect:** check the terminal for a startup error and
  open the URL inside Kali if running in a VM. The server binds to `127.0.0.1`.
- **No devices discovered:** verify that Kali has an interface on the intended
  network. A VM using NAT may see only its virtual subnet; check the VM network
  configuration for your lab.

On Windows PowerShell, use `./run.ps1` from this folder or the repository root.
Git Bash also supports `bash kali_demo/run.sh` from the repository root.

## Existing data

An existing `kali_demo/data/demo.db` is reused automatically. Fresh installations
use `data/inventory.db` in the repository root. Set `PI_OT_DEMO_DATABASE` to use
another database. The old `kali_demo/.venv/` is retained; the launchers use the
environment in the repository root.
