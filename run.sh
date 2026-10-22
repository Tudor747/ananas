#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$project_root"

usage() {
  cat <<'HELP'
Usage: bash run.sh [--port PORT] [--setup | --check] [--no-install]

  --port PORT    Website port (default: PI_OT_DEMO_PORT or 8088).
  --setup        Install dependencies, then exit without starting the website.
  --check        Run local interface, HTTP and Nmap checks, then exit.
  --output PATH  Diagnostic JSON destination (with --check only).
  --no-install   Reuse installed dependencies without contacting the package index.
  -h, --help     Show this help.

Open http://127.0.0.1:8088 in a browser on this computer after starting.
For Kali prerequisites and troubleshooting, see kali_demo/README.md.
HELP
}

fail() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

port="${PI_OT_DEMO_PORT:-8088}"
mode="start"
install=true
check_output=""
while (( $# )); do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --port)
      (( $# >= 2 )) || fail "--port requires a number."
      port="$2"
      shift 2
      ;;
    --setup|--check)
      [[ "$mode" == "start" ]] || fail "Use only one of --setup and --check."
      mode="${1#--}"
      shift
      ;;
    --output)
      (( $# >= 2 )) && [[ -n "$2" ]] || fail "--output requires a path."
      check_output="$2"
      shift 2
      ;;
    --no-install) install=false; shift ;;
    *) fail "Unknown argument: $1. Run bash run.sh --help." ;;
  esac
done
[[ -z "$check_output" || "$mode" == "check" ]] || fail "--output requires --check."
[[ "$port" =~ ^[0-9]{1,5}$ ]] || fail "Port must be between 1 and 65535."
port=$((10#$port))
(( port >= 1 && port <= 65535 )) || fail "Port must be between 1 and 65535."

# A checkout may be shared by Windows and WSL. Never overwrite the other
# platform's environment; virtual environments cannot be moved between OSes.
venv_dir=".venv"
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    python_command="python"
    python_relative="Scripts/python.exe"
    if [[ -d .venv/bin && ! -f .venv/Scripts/python.exe ]]; then
      venv_dir=".venv-windows"
    fi
    ;;
  *)
    python_command="python3"
    python_relative="bin/python"
    if [[ -d .venv/Scripts && ! -e .venv/bin/python ]]; then
      venv_dir=".venv-linux"
    fi
    ;;
esac
venv_python="$venv_dir/$python_relative"

if [[ ! -x "$venv_python" ]]; then
  [[ "$install" == true ]] || fail "No usable environment at $venv_dir. Run without --no-install first."
  [[ ! -f "$venv_dir/pyvenv.cfg" ]] || fail "The environment at $venv_dir is broken. Rename it and rerun to create a fresh one."
  command -v "$python_command" >/dev/null 2>&1 || fail "Install Python 3.11 or newer. On Kali: sudo apt install python3 python3-venv python3-pip"
  "$python_command" -c 'import sys; sys.exit(sys.version_info < (3, 11))' || fail "A working Python 3.11 or newer is required."
  printf 'Creating Python environment: %s\n' "$venv_dir"
  "$python_command" -m venv "$venv_dir" || fail "Could not create the environment. On Kali, install python3-venv and python3-pip, then retry."
fi
"$venv_python" -c 'import sys; sys.exit(sys.version_info < (3, 11))' || fail "The environment at $venv_dir needs a working Python 3.11 or newer."

if [[ "$install" == true ]]; then
  printf 'Installing project dependencies (internet may be needed)...\n'
  "$venv_python" -m pip install --disable-pip-version-check --editable . || fail "Dependency installation failed. Check the pip error above. Use --no-install only if setup previously succeeded."
fi
"$venv_python" -c 'import fastapi, psutil, uvicorn, pi_ot_probe' || fail "Application dependencies are unavailable. Run again without --no-install."

case "$mode" in
  setup)
    printf 'Setup complete. Start with: bash run.sh --no-install\n'
    exit 0
    ;;
  check)
    exec "$venv_python" -m pi_ot_probe.diagnostics.local_check --output "${check_output:-data/local-check.json}"
    ;;
esac

if ! command -v nmap >/dev/null 2>&1; then
  printf 'Nmap was not found on PATH. Discovery needs Nmap; the website can still open.\n'
fi
printf 'Website: http://127.0.0.1:%s (Ctrl+C to stop)\n' "$port"
exec "$venv_python" -m uvicorn pi_ot_probe.web.app:app --host 127.0.0.1 --port "$port"
