#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$project_root"
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install --quiet --editable .
echo "Website: http://127.0.0.1:${PI_OT_DEMO_PORT:-8088} (Ctrl+C to stop)"
exec .venv/bin/python -m uvicorn pi_ot_probe.web.app:app --host 127.0.0.1 --port "${PI_OT_DEMO_PORT:-8088}"
