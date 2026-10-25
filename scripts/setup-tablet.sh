#!/usr/bin/env bash
# Run on Raspberry Pi OS / Debian. Does not replace network configuration.
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
autostart=()
if [[ $# -eq 1 && "${1:-}" == "--autostart" ]]; then
  autostart=(--autostart)
elif [[ $# -ne 0 ]]; then
  printf 'Usage: bash scripts/setup-tablet.sh [--autostart]\n' >&2
  exit 1
fi
if [[ "$(id -u)" == 0 ]]; then
  printf 'Run as your normal Pi user; the installer uses sudo for apt.\n' >&2
  exit 1
fi
sudo apt update
sudo apt install -y python3 python3-venv python3-pip python3-tk nmap iproute2
python3 -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ is required"'
if [[ ! -x .venv-pi/bin/python ]]; then
  if [[ -e .venv-pi/pyvenv.cfg ]]; then
    printf '.venv-pi exists but is unusable. Rename it and rerun setup.\n' >&2
    exit 1
  fi
  python3 -m venv .venv-pi
fi
.venv-pi/bin/python -m pip install -e '.[hardware]'
if ! id -nG | tr ' ' '\n' | grep -qx dialout; then
  sudo usermod -aG dialout "$(id -un)"
  printf 'Serial access: log out of the Pi desktop and SSH, then log back in.\n'
fi
.venv-pi/bin/python scripts/install-tablet-desktop.py "${autostart[@]}"
.venv-pi/bin/python -m pi_ot_probe.tablet --check
printf '\nStart from the Pi desktop: bash run-tablet.sh\n'
printf 'Stop the web server and serial monitors before starting the native app.\n'
if ! command -v nmcli >/dev/null 2>&1; then
  printf 'Optional Pi Wi-Fi scanning needs NetworkManager. ESP Wi-Fi scanning already works without it.\n'
fi
