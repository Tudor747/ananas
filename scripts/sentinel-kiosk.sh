#!/usr/bin/env bash
# Run within the Pi's logged-in graphical desktop; the application must be running.
set -eu
for browser in chromium chromium-browser; do
    if command -v "$browser" >/dev/null 2>&1; then
        exec "$browser" --kiosk --no-first-run http://127.0.0.1:8088/console
    fi
done
echo 'Chromium was not found. Open http://127.0.0.1:8088/console in the Pi browser.' >&2
exit 1
