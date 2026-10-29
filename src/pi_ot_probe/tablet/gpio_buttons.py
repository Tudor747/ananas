"""Pi GPIO navigation polled on the Tk thread; importing this needs no GPIO library."""
import logging
import os
import time

logger = logging.getLogger(__name__)


class GPIOButtons:
    # BCM GPIO numbers. GPIO 16 is the unimplemented ON/OFF switch: do not claim it.
    PINS = {"left": 5, "up": 6, "down": 13, "right": 26, "ok": 19}
    POLL_MS = 30
    DEBOUNCE_SECONDS = 0.06

    def __init__(self, root, callback, *, button_factory=None, clock=time.monotonic):
        self.root, self.callback, self.clock = root, callback, clock
        self.buttons, self.previous, self.raw, self.changed = {}, {}, {}, {}
        self.active = True
        self._after_id = None
        self._destroy_binding = None
        self._polling = False
        try:
            if button_factory is None:
                from gpiozero import Button
                # Desktop autostart does not inherit an interactive terminal's export.
                os.environ.setdefault("GPIOZERO_PIN_FACTORY", "lgpio")
                button_factory = Button
            for name, pin in self.PINS.items():
                button = button_factory(pin, pull_up=True, bounce_time=self.DEBOUNCE_SECONDS)
                self.buttons[name] = button
                self.previous[name] = self.raw[name] = bool(button.is_pressed)
                self.changed[name] = self.clock()
            self._destroy_binding = root.bind("<Destroy>", self._destroyed, add="+")
            self.poll()
            if not self.active:
                raise RuntimeError("GPIO polling could not start")
        except Exception:
            self.close()  # Includes buttons successfully opened before a later failure.
            raise

    def _destroyed(self, event):
        if event.widget is self.root:
            self.close()

    def _tick(self):
        self._after_id = None
        self.poll()

    def poll(self):
        # Calling poll twice must never create two timer chains.
        if not self.active or self._after_id is not None or self._polling:
            return
        self._polling = True
        try:
            if not self.root.winfo_exists():
                self.close()
                return
            now = self.clock()
            for name, button in self.buttons.items():
                if not self.active:
                    break
                pressed = bool(button.is_pressed)
                if pressed != self.raw[name]:
                    self.raw[name], self.changed[name] = pressed, now
                # Debounce the polled value itself, not just GPIO Zero's event callbacks.
                if pressed != self.previous[name] and now - self.changed[name] >= self.DEBOUNCE_SECONDS:
                    self.previous[name] = pressed
                    if pressed:
                        try:
                            self.callback(name)
                        except Exception:
                            # A stale menu widget must not disable every physical button.
                            # Do not replay the failed action: wait for the next press.
                            logger.exception("GPIO action %s failed; buttons remain active", name)
            if self.active:
                self._after_id = self.root.after(self.POLL_MS, self._tick)
        except Exception:
            logger.exception("GPIO polling stopped; touchscreen and keyboard remain available")
            self.close()
        finally:
            self._polling = False

    def close(self):
        if not self.active:
            return
        self.active = False
        if self._after_id is not None:
            try:
                self.root.after_cancel(self._after_id)
            except Exception:
                logger.debug("GPIO timer was already destroyed", exc_info=True)
            self._after_id = None
        if self._destroy_binding is not None:
            try:
                self.root.unbind("<Destroy>", self._destroy_binding)
            except Exception:
                logger.debug("GPIO destroy binding was already removed", exc_info=True)
            self._destroy_binding = None
        for button in self.buttons.values():
            try:
                button.close()
            except Exception:
                logger.exception("Could not release GPIO button")
