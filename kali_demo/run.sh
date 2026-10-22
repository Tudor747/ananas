#!/usr/bin/env bash
set -euo pipefail
# Use the current application and shared setup from any working directory.
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ ! -f "$project_root/pyproject.toml" || ! -f "$project_root/run.sh" ]]; then
  echo "Keep kali_demo inside the full repository; the application is in src/pi_ot_probe/." >&2
  exit 1
fi
exec bash "$project_root/run.sh" "$@"
