#!/usr/bin/env bash
# Read-only snapshot over SSH; leaves the running tablet and USB connections alone.
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root" || exit 1
printf '\nTime and uptime\n'
date -Is
uptime
printf '\nTablet processes\n'
pgrep -af '[p]i_ot_probe.tablet' || true
printf '\nDesktop sessions\n'
systemctl is-active display-manager || true
loginctl list-sessions || true
printf '\nUSB devices and serial paths\n'
lsusb
ls -l /dev/serial/by-id/ /dev/serial/by-path/ 2>/dev/null || true
printf '\nPi power/throttling status (raw firmware report)\n'
if command -v vcgencmd >/dev/null 2>&1; then
    vcgencmd get_throttled
fi
printf '\nRecent tablet log\n'
tail -n 100 data/tablet.log 2>/dev/null || true
printf '\nKernel USB, power and display messages\n'
journalctl -k -b --no-pager 2>/dev/null | grep -Ei 'under.voltage|over.current|usb|drm|panel' | tail -n 60
