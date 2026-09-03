#!/usr/bin/env bash
set -euo pipefail

demo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "$demo_dir/.." && pwd)"
venv_dir="$demo_dir/.venv"
port="${PI_OT_DEMO_PORT:-8088}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required. Install it with: sudo apt install python3 python3-venv" >&2
  exit 1
fi

if ! command -v nmap >/dev/null 2>&1; then
  echo "Nmap is required for real discovery. Install it with: sudo apt install nmap" >&2
  exit 1
fi

if [[ ! -x "$venv_dir/bin/python" ]] || ! "$venv_dir/bin/python" -m pip --version >/dev/null 2>&1; then
  echo "Creating Kali demo virtual environment..."
  python3 -m venv --clear "$venv_dir" || {
    echo "Could not create a complete environment. Run: sudo apt install python3-venv python3-pip" >&2
    exit 1
  }
fi

"$venv_dir/bin/python" -m pip install --quiet --upgrade pip
"$venv_dir/bin/python" -m pip install --quiet --editable "$project_root"

echo "Pi-OT Kali demo: http://127.0.0.1:$port"
echo "Authorized local scans can send rate-limited probes. Press Ctrl+C to stop."
exec "$venv_dir/bin/python" -m uvicorn kali_demo.app:app \
  --app-dir "$project_root" \
  --host 127.0.0.1 \
  --port "$port"
