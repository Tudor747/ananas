#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$project_root"
tablet_python="$project_root/.venv-pi/bin/python"
if [[ ! -x "$tablet_python" ]]; then
  printf 'Install first: bash scripts/setup-tablet.sh\n' >&2
  exit 1
fi
# Desktop shortcut and autostart must not compete for GPIO/serial devices.
case " $* " in
  *" --check "*|*" --list-tools "*) exec "$tablet_python" -m pi_ot_probe.tablet "$@" ;;
esac
exec flock --nonblock --conflict-exit-code 73 \
  "${XDG_RUNTIME_DIR:-/tmp}/rf-sentinel-tablet-$(id -u).lock" \
  "$tablet_python" -m pi_ot_probe.tablet "$@"
