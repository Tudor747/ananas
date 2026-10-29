#!/usr/bin/env python3
"""Install GPIO16 software ON/OFF support into ananas native tablet app.

Targets the vFin code layout inspected on 2026-10-29.
The TFT/backlight and Raspberry Pi power are intentionally untouched.
No Git commit/push is performed.
"""
from __future__ import annotations

import argparse
import datetime
import os
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent
APP = ROOT / "src/pi_ot_probe/tablet/app.py"
BACKEND = ROOT / "src/pi_ot_probe/tablet/backend.py"
ENTRY = ROOT / "src/pi_ot_probe/tablet/__main__.py"
SWITCH = ROOT / "src/pi_ot_probe/tablet/power_switch.py"

SWITCH_CODE = '''"""GPIO16 ON/OFF input. Controls software only, never display power."""
import logging
import os
import time

logger = logging.getLogger(__name__)


class PowerSwitch:
    """Switch to GND with internal pull-up: HIGH=ON, LOW=OFF.

    GPIO polling and callbacks run on the Tk thread. The initial state is
    reported immediately, then level changes are debounced for 80 ms.
    """

    PIN = 16
    POLL_MS = 50
    DEBOUNCE_SECONDS = 0.08

    def __init__(self, root, callback, *, button_factory=None, clock=time.monotonic):
        self.root, self.callback, self.clock = root, callback, clock
        self.active = True
        self._button = None
        self._after_id = None
        self._raw = self._stable = None
        self._changed = 0.0
        try:
            if button_factory is None:
                os.environ.setdefault("GPIOZERO_PIN_FACTORY", "lgpio")
                from gpiozero import Button
                button_factory = Button
            self._button = button_factory(self.PIN, pull_up=True, bounce_time=0.06)
            self._raw = self._stable = bool(self._button.is_pressed)
            self._changed = self.clock()
            self.callback(not self._stable)
            self._schedule()
        except Exception:
            self.close()
            raise

    def _schedule(self):
        if self.active and self._after_id is None:
            self._after_id = self.root.after(self.POLL_MS, self._poll)

    def _poll(self):
        self._after_id = None
        if not self.active:
            return
        try:
            if not self.root.winfo_exists():
                self.close()
                return
            raw = bool(self._button.is_pressed)
            now = self.clock()
            if raw != self._raw:
                self._raw, self._changed = raw, now
            if raw != self._stable and now - self._changed >= self.DEBOUNCE_SECONDS:
                self._stable = raw
                try:
                    self.callback(not raw)
                except Exception:
                    logger.exception("GPIO16 switch callback failed")
        except Exception:
            logger.exception("GPIO16 input lost; releasing its pin for retry")
            self.close()
        finally:
            self._schedule()

    def close(self):
        if not self.active:
            return
        self.active = False
        if self._after_id is not None:
            try:
                self.root.after_cancel(self._after_id)
            except Exception:
                logger.debug("GPIO16 timer already removed", exc_info=True)
            self._after_id = None
        if self._button is not None:
            try:
                self._button.close()
            except Exception:
                logger.exception("Could not release GPIO16")
            self._button = None
'''


def replace_once(source: str, before: str, after: str, label: str) -> str:
    count = source.count(before)
    if count != 1:
        raise RuntimeError(f"Unexpected version at {label}: expected 1 match, found {count}. No changes applied.")
    return source.replace(before, after, 1)


def prepare():
    app, backend, entry = (p.read_text(encoding="utf-8") for p in (APP, BACKEND, ENTRY))
    if SWITCH.exists() or "from .power_switch import PowerSwitch" in app:
        raise RuntimeError("GPIO16 support seems already installed. Nothing changed.")
    app = replace_once(app,
        "from .gpio_buttons import GPIOButtons\n",
        "from .gpio_buttons import GPIOButtons\nfrom .power_switch import PowerSwitch\n",
        "tablet/app.py GPIO import")
    app = replace_once(app,
        "        self.gpio_buttons = None\n        self.gpio_requested =",
        "        self.gpio_buttons = None\n        self.power_switch = None\n        self.switch_enabled = True\n        self.gpio_requested =",
        "tablet/app.py initialization")
    app = replace_once(app,
        "        self._gpio_retry_at = 0\n",
        "        self._gpio_retry_at = 0\n        self._switch_retry_at = 0\n",
        "tablet/app.py retry timer")
    app = replace_once(app,
        "    def gpio_navigate(self, direction):\n        if not self.closing:\n            self.controller.navigate_gpio(direction)\n",
'''    def start_power_switch(self):
        if self.closing or (self.power_switch is not None and self.power_switch.active):
            return
        self.close_power_switch()
        self._switch_retry_at = time.monotonic() + 5
        try:
            self.power_switch = PowerSwitch(self.root, self.on_power_switch)
            logger.info("GPIO16 software ON/OFF switch activated")
        except Exception as exc:
            logger.warning("GPIO16 unavailable; app remains usable: %s", exc)

    def on_power_switch(self, enabled):
        if self.closing or self.switch_enabled == enabled:
            return
        self.switch_enabled = enabled
        self.backend.set_power_enabled(enabled)
        if enabled:
            self.notice.set("Switch ON: ready. Restart stopped tools manually.")
        else:
            self.notice.set("Switch OFF: operations stopped. Pi and display stay on.")
        logger.info("GPIO16 switch: %s", "ON" if enabled else "OFF")

    def close_power_switch(self):
        if self.power_switch is not None:
            try:
                self.power_switch.close()
            except Exception:
                logger.exception("GPIO16 cleanup failed")
            self.power_switch = None

    def gpio_navigate(self, direction):
        if not self.closing and self.switch_enabled:
            self.controller.navigate_gpio(direction)
''',
        "tablet/app.py switch integration")
    app = replace_once(app,
        "    def run_tool(self, **options):\n        if not self.tool:\n            return\n",
'''    def run_tool(self, **options):
        if not self.tool:
            return
        if not self.switch_enabled:
            self.notice.set("Switch OFF: move switch to ON to run tools.")
            return
''',
        "tablet/app.py run guard")
    app = replace_once(app,
'''        if (self.gpio_requested and time.monotonic() >= self._gpio_retry_at and
                (self.gpio_buttons is None or not self.gpio_buttons.active)):
            self.start_gpio()
''',
'''        if (self.gpio_requested and time.monotonic() >= self._gpio_retry_at and
                (self.gpio_buttons is None or not self.gpio_buttons.active)):
            self.start_gpio()
        if (self.gpio_requested and time.monotonic() >= self._switch_retry_at and
                (self.power_switch is None or not self.power_switch.active)):
            self.start_power_switch()
''',
        "tablet/app.py poll switch initialization")
    app = replace_once(app,
        "        self.status.set(connection_summary(states))\n",
        '        self.status.set(connection_summary(states) if self.switch_enabled else "Switch OFF - operations paused")\n',
        "tablet/app.py status")
    app = replace_once(app,
'''        for action in getattr(self.backend, "button_actions", lambda: [])():
            self.controller.handle(action)
''',
'''        for action in getattr(self.backend, "button_actions", lambda: [])():
            if self.switch_enabled:
                self.controller.handle(action)
''',
        "tablet/app.py ESP controller input")
    app = replace_once(app,
'''        self.closing = True
        self.close_gpio()
''',
'''        self.closing = True
        self.close_power_switch()
        self.close_gpio()
''',
        "tablet/app.py close cleanup")
    backend = replace_once(backend,
'''        self.busy = False
        self.last_result = None
''',
'''        self.busy = False
        self.power_enabled = True
        self.last_result = None
''',
        "tablet/backend.py power state")
    backend = replace_once(backend,
'''    def start(self, key, authorized=False, **options):
        if getattr(self, "_stop_thread", None) is not None and self._stop_thread.is_alive():
''',
'''    def set_power_enabled(self, enabled):
        """Software pause; do not stop Pi, close USB manager, or power off TFT."""
        self.power_enabled = bool(enabled)
        if not self.power_enabled:
            self.stop_async()

    def start(self, key, authorized=False, **options):
        if not self.power_enabled:
            raise ValueError("Switch OFF: move switch to ON before starting a tool.")
        if getattr(self, "_stop_thread", None) is not None and self._stop_thread.is_alive():
''',
        "tablet/backend.py start guard")
    entry = replace_once(entry,
'''            if window is not None:
                window.close_gpio()
''',
'''            if window is not None:
                window.close_power_switch()
                window.close_gpio()
''',
        "tablet/__main__.py exit cleanup")
    return {APP: app, BACKEND: backend, ENTRY: entry, SWITCH: SWITCH_CODE}


def main():
    parser = argparse.ArgumentParser(description="Verify and optionally install GPIO16 in a locally modified ananas checkout")
    parser.add_argument("--apply", action="store_true", help="Back up and apply the verified changes. Without this flag: read-only check.")
    args = parser.parse_args()
    for target in (APP, BACKEND, ENTRY):
        if not target.is_file():
            raise RuntimeError(f"Missing {target}. Put this script in the ananas repository root.")

    # Deliberately support a dirty working tree: never throw away user changes.
    # Strict exact-string anchors in prepare() validate the real, locally edited files.
    changes = subprocess.run(["git", "status", "--short"], cwd=ROOT,
                             capture_output=True, text=True, check=True)
    if changes.stdout.strip():
        print("NOTICE: Local Git changes exist. They will NOT be discarded or reset.")
        print(changes.stdout.rstrip())

    # All source matching and syntax checks happen before any writes or backups.
    files = prepare()
    for target, content in files.items():
        compile(content, str(target), "exec")
    print("CHECK PASSED: All insertion points match the CURRENT Pi source and all generated Python syntax is valid.")
    for target in files:
        print(("CREATE " if target == SWITCH else "PATCH  ") + str(target.relative_to(ROOT)))
    if not args.apply:
        print("READ-ONLY CHECK: No files changed. To install: python3 install_gpio16_switch_safe.py --apply")
        return

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = ROOT.parent / f"ananas-switch-backup-{stamp}"
    backup.mkdir(parents=True, exist_ok=False)
    originals = {}
    for target in (APP, BACKEND, ENTRY):
        originals[target] = target.read_bytes()
        destination = backup / target.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, destination)
    (backup / "git-status-before.txt").write_text(changes.stdout, encoding="utf-8")
    diff = subprocess.run(["git", "diff", "HEAD", "--binary"], cwd=ROOT,
                          capture_output=True, check=True)
    (backup / "all-tracked-local-changes.patch").write_bytes(diff.stdout)
    applied = []
    try:
        for target, content in files.items():
            temporary = target.with_name(target.name + ".gpio16.tmp")
            try:
                temporary.write_text(content, encoding="utf-8")
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
            applied.append(target)
    except BaseException:
        for target in applied:
            if target in originals:
                target.write_bytes(originals[target])
            elif target == SWITCH:
                target.unlink(missing_ok=True)
        print("FAILED DURING WRITE: Original target files restored; backup retained:", backup)
        raise
    print("SUCCESS: GPIO16 software switch installed. No Git commit, push or reboot was performed.")
    print("BACKUP:", backup)
    print("Run: .venv-pi/bin/python -m compileall -q src/pi_ot_probe/tablet")
    print("Then restart only the tablet application (not Raspberry Pi).")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"INSTALL FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
