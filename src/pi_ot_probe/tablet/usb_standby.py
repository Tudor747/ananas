"""Control alimentare USB la GPIO16; ecranul TFT nu este modificat."""
import logging
import subprocess
import threading
import time

log = logging.getLogger(__name__)


class USBStandby:
    def __init__(self, backend):
        self.backend = backend
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.desired = None
        self.applied = None
        self.exiting = False
        self.thread = threading.Thread(
            target=self._loop, name="gpio16-usb-power", daemon=True
        )
        self.thread.start()

    def request(self, enabled):
        with self.lock:
            self.desired = bool(enabled)
            self.wake.set()

    def _wanted(self):
        with self.lock:
            return self.desired

    @staticmethod
    def _power(state):
        for hub in (2, 4):
            cmd = [
                "sudo", "-n", "/usr/sbin/uhubctl",
                "-l", str(hub), "-a", state
            ]
            result = subprocess.run(
                cmd, text=True, capture_output=True, timeout=10
            )
            if result.returncode:
                raise RuntimeError(
                    f"Hub {hub}, {state}: "
                    f"{(result.stderr or result.stdout)[-300:]}"
                )

    def _disable(self):
        b = self.backend
        try:
            b.stop_async()
            deadline = time.monotonic() + 25

            while time.monotonic() < deadline:
                if self._wanted() is True:
                    return
                working = b.thread is not None and b.thread.is_alive()
                stopping = getattr(b, "_stop_thread", None)
                stopping = stopping is not None and stopping.is_alive()
                if not working and not stopping:
                    break
                time.sleep(0.15)
            else:
                log.error(
                    "GPIO16 USB OFF aborted: timeout waiting for operations"
                )
                return

            if self._wanted() is True:
                return

            b.manager.stop()

            if any(
                w.thread is not None and w.thread.is_alive()
                for w in b.manager.workers.values()
            ):
                log.error(
                    "GPIO16 USB OFF aborted: serial worker still active"
                )
                return

            if self._wanted() is True:
                return

            self._power("off")
            self.applied = False
            log.info("GPIO16 USB VBUS: OFF (hubs 2,4)")

        except Exception:
            log.exception(
                "GPIO16 USB OFF failed; attempting to restore power"
            )
            try:
                self._power("on")
            except Exception:
                log.exception("GPIO16 USB recovery failed")
            self.applied = None

    def _enable(self):
        try:
            self._power("on")
            if not self.backend.closing.is_set():
                # USB port readiness wait
                from pathlib import Path
                ports = [w.config.port for w in self.backend.manager.workers.values()]
                deadline = time.monotonic() + 8
                while self._wanted() is True and not self.backend.closing.is_set():
                    missing = [port for port in ports if not Path(port).exists()]
                    if not missing:
                        time.sleep(1)
                        break
                    if time.monotonic() >= deadline:
                        log.warning('GPIO16 USB ports not ready: %s', missing)
                        break
                    time.sleep(0.2)
                if self._wanted() is True and not self.backend.closing.is_set():
                    self.backend.manager.start()
            self.applied = True
            log.info("GPIO16 USB VBUS: ON (hubs 2,4)")
        except Exception:
            self.applied = None
            log.exception("GPIO16 USB power-on failed")

    def _loop(self):
        while True:
            self.wake.wait()
            self.wake.clear()

            with self.lock:
                target = self.desired
                exiting = self.exiting

            if target is True and self.applied is not True:
                self._enable()
            elif target is False and self.applied is not False:
                self._disable()

            if exiting:
                return

            if self._wanted() != target:
                self.wake.set()

    def shutdown(self):
        # La inchiderea normala a aplicatiei, USB revine pe ON.
        with self.lock:
            # Closing an app that never used standby must not toggle USB power.
            if self.desired is not None or self.applied is not None:
                self.desired = True
            self.exiting = True
            self.wake.set()

        self.thread.join(timeout=50)
        if self.thread.is_alive():
            log.error(
                "GPIO16 USB power thread did not finish; state unknown"
            )
