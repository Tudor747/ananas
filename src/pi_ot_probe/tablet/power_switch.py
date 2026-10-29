"""GPIO16 ON/OFF input. Controls software only, never display power."""
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
