#!/usr/bin/env sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this deployment helper as root." >&2
    exit 1
fi

install -d -o pi-ot-probe -g pi-ot-probe -m 0750 /var/lib/pi-ot-probe
install -d -o root -g pi-ot-probe -m 0750 /etc/pi-ot-probe
install -o root -g root -m 0644 pi-ot-probe.service /etc/systemd/system/pi-ot-probe.service
echo "Create /etc/pi-ot-probe/environment with PI_OT_API_TOKEN and PI_OT_DATABASE."
echo "Then run: systemctl daemon-reload && systemctl enable --now pi-ot-probe"
