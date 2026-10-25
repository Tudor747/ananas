#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$project_root"
tablet_python="$project_root/.venv-pi/bin/python"
if [[ ! -x "$tablet_python" ]]; then
  printf 'Install first: bash scripts/setup-tablet.sh\n' >&2
  exit 1
fi
exec "$tablet_python" -m pi_ot_probe.tablet "$@"
