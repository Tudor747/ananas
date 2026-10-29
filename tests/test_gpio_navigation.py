"""Pi handoff regressions: simulated GPIO and the real Tk menu, without physical pins."""
import gc
import queue
from types import SimpleNamespace

import pytest

from pi_ot_probe.tablet.gpio_buttons import GPIOButtons


class Root:
    def __init__(self):
        self.timers = {}
        self.destroy_callback = None
        self.exists = True
        self.count = 0

    def bind(self, event, callback, add):
        assert event == "<Destroy>" and add == "+"
        self.destroy_callback = callback
        return "destroy-binding"

    def unbind(self, event, binding):
        self.destroy_callback = None

    def winfo_exists(self):
        return self.exists

    def after(self, delay, callback):
        assert delay == 30
        self.count += 1
        self.timers[self.count] = callback
        return self.count

    def after_cancel(self, token):
        self.timers.pop(token, None)

    def tick(self):
        assert len(self.timers) == 1
        token, callback = next(iter(self.timers.items()))
        del self.timers[token]
        callback()


class Button:
    def __init__(self, pin, pull_up, bounce_time):
        assert pull_up is True and bounce_time == .06
        self.pin = pin
        self.is_pressed = False
        self.closed = False

    def close(self):
        self.closed = True


@pytest.fixture
def gpio():
    root, actions, now = Root(), [], [0.0]
    driver = GPIOButtons(root, actions.append, button_factory=Button, clock=lambda: now[0])
    yield driver, root, actions, now
    driver.close()


def test_exact_pin_mapping_and_no_power_switch(gpio):
    driver, _, _, _ = gpio
    assert {name: b.pin for name, b in driver.buttons.items()} == {
        "left": 5, "up": 6, "down": 13, "right": 26, "ok": 19}
    assert all(b.pin != 16 for b in driver.buttons.values())


@pytest.mark.parametrize("name", ["left", "up", "down", "right", "ok"])
def test_polled_values_are_debounced_and_held_press_is_not_repeated(gpio, name):
    driver, root, actions, now = gpio
    button = driver.buttons[name]
    button.is_pressed = True
    root.tick()
    now[0] = .03
    button.is_pressed = False
    root.tick()
    now[0] = .04
    button.is_pressed = True
    root.tick()
    now[0] = .08
    root.tick()
    assert not actions
    now[0] = .11
    root.tick()
    now[0] = 2
    root.tick()
    assert actions == [name]
    button.is_pressed = False
    root.tick()
    now[0] = 2.07
    root.tick()
    button.is_pressed = True
    root.tick()
    now[0] = 2.14
    root.tick()
    assert actions == [name, name]


def test_held_at_start_waits_for_release():
    def held(*args, **kwargs):
        button = Button(*args, **kwargs)
        button.is_pressed = True
        return button
    root, actions, now = Root(), [], [0.0]
    driver = GPIOButtons(root, actions.append, button_factory=held, clock=lambda: now[0])
    try:
        now[0] = 1
        root.tick()
        assert actions == []
        driver.buttons["ok"].is_pressed = False
        root.tick()
        now[0] = 1.07
        root.tick()
        driver.buttons["ok"].is_pressed = True
        root.tick()
        now[0] = 1.14
        root.tick()
        assert actions == ["ok"]
    finally:
        driver.close()


def test_only_one_poll_chain_and_close_is_idempotent(gpio):
    driver, root, actions, _ = gpio
    for _ in range(5):
        driver.poll()
    assert len(root.timers) == 1
    queued = next(iter(root.timers.values()))
    driver.close()
    driver.close()
    queued()  # Even a timer already dispatched by Tk cannot resume polling.
    assert not root.timers and not actions
    assert all(button.closed for button in driver.buttons.values())


def test_partial_setup_failure_closes_previously_opened_buttons():
    created = []
    def fail_on_third(*args, **kwargs):
        if len(created) == 2:
            raise OSError("GPIO already in use")
        created.append(Button(*args, **kwargs))
        return created[-1]
    root = Root()
    with pytest.raises(OSError, match="already in use"):
        GPIOButtons(root, lambda _: None, button_factory=fail_on_third)
    assert all(button.closed for button in created)
    assert not root.timers


def test_destroy_cleanup_ignores_child_widgets(gpio):
    driver, root, _, _ = gpio
    root.destroy_callback(SimpleNamespace(widget=object()))
    assert driver.active
    root.destroy_callback(SimpleNamespace(widget=root))
    assert not driver.active and not root.timers


def test_callback_failure_preserves_buttons_for_next_action(gpio):
    driver, root, actions, now = gpio
    def broken(_):
        raise RuntimeError("callback failed")
    driver.callback = broken
    driver.buttons["ok"].is_pressed = True
    root.tick()
    now[0] = .07
    root.tick()
    assert driver.active and root.timers
    assert not any(button.closed for button in driver.buttons.values())
    driver.callback = actions.append
    driver.buttons["left"].is_pressed = True
    root.tick()
    now[0] = .14
    root.tick()
    assert actions == ["left"]


def test_callback_can_close_during_poll(gpio):
    driver, root, _, now = gpio
    driver.callback = lambda _: driver.close()
    driver.buttons["left"].is_pressed = True
    driver.buttons["right"].is_pressed = True
    root.tick()
    now[0] = .07
    root.tick()
    assert not driver.active and not root.timers


@pytest.fixture
def ui(monkeypatch):
    tk = pytest.importorskip("tkinter")
    from pi_ot_probe.tablet.app import TabletApp
    class Backend:
        def __init__(self):
            self.messages = queue.Queue()
            self.busy, self.closed, self.job_id = False, False, 0
            self.runs = []
        def state(self): return [{"node": n, "connection": "online", "health": "ready"} for n in "ABC"]
        def start(self, key, authorized=False, **kwargs):
            if key != "usb" and not authorized:
                raise ValueError("Confirm permission first")
            self.runs.append(key)
            self.last_options = kwargs
            self.job_id += 1
            self.busy = True
        def stop(self): self.busy = False
        def close(self): self.closed = True
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"No graphical display for Tk checks: {exc}")
    root.withdraw()
    root.attributes("-alpha", 0)
    monkeypatch.setattr(TabletApp, "refresh_choices", lambda _: None)
    backend = Backend()
    app = TabletApp(root, backend, fullscreen=False, size=(480, 320), enable_gpio=False)
    root.deiconify()
    root.update()
    yield app, root, backend
    app.closing = True
    try:
        # Tcl timers outlive destroyed callback commands when another test creates
        # a Tk interpreter. Dispose timers and Variables on their owning thread.
        for token in root.tk.call("after", "info"):
            root.after_cancel(token)
        root.destroy()
    except tk.TclError:
        pass
    for name, value in list(vars(app).items()):
        if isinstance(value, tk.Variable):
            setattr(app, name, None)
    app.controller.app = None
    app.controller.selected = None
    app = None
    gc.collect()


def test_gpio_navigation_page_limits_single_item_and_back(ui):
    from pi_ot_probe.tablet.catalog import CATEGORIES
    app, root, _ = ui
    app.gpio_navigate("down")
    assert app.controller.selected == app.body.winfo_children()[1]
    app.gpio_navigate("down")
    assert app.page == 1
    app.gpio_navigate("up")
    assert app.page == 0
    for _ in range(10):
        app.gpio_navigate("right")
    root.update()
    assert app.page == (len(CATEGORIES) - 1) // 2
    assert len(app.body.winfo_children()) == 1
    app.gpio_navigate("down")
    app.gpio_navigate("ok")
    root.update()
    assert app.category == CATEGORIES[-1] and app.page == 0
    app.gpio_navigate("left")
    root.update()
    assert app.category is None and app.page == 0
    app.gpio_navigate("right")
    app.gpio_navigate("left")
    assert app.page == 0
    app.gpio_navigate("left")
    assert app.page == 0


def test_gpio_can_select_permission_run_and_return_from_tool(ui):
    import tkinter as tk
    app, root, backend = ui
    app.gpio_buttons = SimpleNamespace(active=True, close=lambda: None)
    app.open_category("Wi-Fi")
    app.gpio_navigate("ok")
    # No root.update between presses: selection must track the newly built tool.
    app.gpio_navigate("ok")
    assert app.tool.key == "wifi" and app.authorized.get()
    assert isinstance(app.controller.selected, tk.Checkbutton)
    for _ in range(10):
        if app.controller.selected == app.run_button:
            break
        app.gpio_navigate("down")
    app.gpio_navigate("ok")
    assert backend.runs == ["wifi"]
    app.set_result("\n".join(f"Reading {i}" for i in range(100)))
    for _ in range(len(app.controller.items())):
        if app.controller.selected == app.result_widget:
            break
        app.gpio_navigate("down")
    assert app.controller.selected == app.result_widget
    app.gpio_navigate("ok")
    assert app.controller.reading and "LEFT / OK" in app.controls_hint.get()
    before = app.result_widget.yview()
    app.gpio_navigate("down")
    assert app.result_widget.yview()[0] > before[0]
    app.gpio_navigate("left")
    assert not app.controller.reading and app.tool.key == "wifi"
    app.gpio_navigate("left")
    root.update()
    assert not backend.busy and app.tool is None and app.category == "Wi-Fi"
    app.home()
    root.update()
    assert app.category is None and app.page == 0
    assert app.controller.selected == app.body.winfo_children()[0]


def test_touch_rebuild_then_gpio_select_has_valid_selection(ui):
    app, root, _ = ui
    app.gpio_navigate("down")
    # Invoke the actual touchscreen controls without GPIO handling.
    app.body.winfo_children()[0].invoke()
    root.update()
    assert app.category == "System"
    app.gpio_navigate("ok")
    root.update()
    assert app.tool.key == "usb"


def test_gpio_setup_failure_leaves_gui_usable(ui, monkeypatch):
    app, root, _ = ui
    def fail(*args):
        raise ImportError("gpiozero missing")
    monkeypatch.setattr("pi_ot_probe.tablet.app.GPIOButtons", fail)
    app.start_gpio()
    assert app.gpio_buttons is None
    app.body.winfo_children()[0].invoke()
    root.update()
    assert app.category == "System"


@pytest.mark.parametrize("size", [(320, 240), (480, 320), (800, 480)])
def test_usb_setup_entirely_with_buttons(ui, size):
    app, root, backend = ui
    root.geometry(f"{size[0]}x{size[1]}")
    app.ports = [{"port": f"/dev/serial/by-path/usb-socket-{i}", "description": "CP2102"}
                 for i in range(3)]
    app.gpio_navigate("ok")  # System
    app.gpio_navigate("ok")  # USB Setup
    app.gpio_navigate("down")  # Manual setup
    app.gpio_navigate("ok")
    app.gpio_navigate("down")  # B
    app.gpio_navigate("ok")
    assert app.usb_step == "port" and app.role.get() == "B"
    app.gpio_navigate("down")  # second USB device
    app.gpio_navigate("ok")
    assert app.usb_step == "confirm"
    assert app.selected_port.get() == app.ports[1]["port"]
    assert not backend.runs
    root.update()
    app.gpio_navigate("ok")
    assert backend.runs == ["usb"]
    assert backend.last_options["role"] == "B"
    assert backend.last_options["port"] == app.ports[1]["port"]
    backend.busy = False
    backend.messages.put({"kind": "done", "job": backend.job_id, "path": "report.json", "result": {}})
    app.poll()
    root.update()
    assert app.usb_step == "done"
    app.gpio_navigate("ok")
    assert app.usb_step == "start"


def test_usb_assigned_ports_back_and_disconnected_selection(ui):
    app, root, backend = ui
    backend.state = lambda: [{"node": "B", "connection": "online", "port": "/dev/ttyUSB0"}]
    app.ports = [{"port": f"/dev/ttyUSB{i}", "description": "CP2102"} for i in range(2)]
    app.gpio_navigate("ok")
    app.gpio_navigate("ok")
    app.gpio_navigate("down")
    app.gpio_navigate("ok")  # Manual setup
    app.gpio_navigate("ok")  # A
    app.gpio_navigate("ok")  # only free USB1
    assert app.selected_port.get() == "/dev/ttyUSB1"
    app.gpio_navigate("left")
    assert app.usb_step == "port"
    app.gpio_navigate("ok")
    backend.messages.put({"kind": "choices", "ports": app.ports[:1], "networks": []})
    app.poll()
    root.update()
    assert app.selected_port.get() == "/dev/ttyUSB1"  # Never silently switch to B's port.
    assert str(app.run_button.cget("state")) == "disabled"
    app.gpio_navigate("ok")
    assert not backend.runs


def test_usb_forget_requires_confirmation(ui):
    app, root, backend = ui
    backend.state = lambda: [{"node": "A", "connection": "online", "port": "/dev/ttyUSB0"}]
    app.gpio_navigate("ok")
    app.gpio_navigate("ok")
    app.gpio_navigate("down")
    app.gpio_navigate("ok")  # Manual setup
    app.gpio_navigate("ok")  # A
    app.gpio_navigate("down")  # Refresh -> Forget (no detected ports)
    app.gpio_navigate("ok")
    assert app.usb_step == "forget" and not backend.runs
    app.poll()
    app.gpio_navigate("ok")
    assert backend.last_options["forget"] is True


def test_find_esps_needs_no_role_or_port_selection_and_error_is_readable(ui):
    app, root, backend = ui
    app.gpio_navigate("ok")
    app.gpio_navigate("ok")
    app.gpio_navigate("ok")
    assert backend.last_options["auto"] is True
    backend.busy = False
    backend.messages.put({"kind": "error", "job": backend.job_id,
                          "message": "ESP is crashing.\n" * 25})
    app.poll_once()
    root.update()
    assert app.usb_step == "error"
    for _ in range(len(app.controller.items())):
        if app.controller.selected == app.result_widget:
            break
        app.gpio_navigate("down")
    app.gpio_navigate("ok")
    assert app.controller.reading
    app.gpio_navigate("left")
    app.gpio_navigate("left")
    assert app.usb_step == "start"


def test_menu_update_recovers_after_backend_error(ui, monkeypatch):
    app, root, backend = ui
    original = backend.state
    def fail(): raise OSError("temporary state failure")
    monkeypatch.setattr(backend, "state", fail)
    app.poll()  # Must schedule the next update, rather than killing the event chain.
    monkeypatch.setattr(backend, "state", original)
    app.gpio_navigate("ok")
    app.gpio_navigate("ok")
    assert app.usb_step == "start"


def test_ip_results_and_port_inspection_use_buttons_only(ui):
    from pi_ot_probe.tablet.catalog import BY_KEY
    app, root, backend = ui
    app.authorized.set(True)
    app.show_tool(BY_KEY["ip"])
    app.run_tool()
    backend.busy = False
    backend.messages.put({"kind": "done", "job": backend.job_id, "path": "report.json",
                          "result": {"scan": "discovery", "target": "192.168.1.0/24",
                                     "assets": [{"ip": "192.168.1.10", "hostname": "test-host"}]}})
    app.poll_once()
    assert app.controller.reading and app.controller.selected == app.result_widget
    assert "test-host" in app.result_text
    app.gpio_navigate("left")  # Leave reader without leaving the tool.
    for _ in range(len(app.controller.items())):
        if app.controller.selected in app.host_actions.winfo_children():
            break
        app.gpio_navigate("down")
    app.gpio_navigate("ok")
    assert backend.last_options["host"] == "192.168.1.10"


def test_error_after_samples_is_not_overwritten_by_live_preview(ui):
    from pi_ot_probe.tablet.catalog import BY_KEY
    app, root, backend = ui
    app.authorized.set(True)
    app.show_tool(BY_KEY["wifi"])
    app.run_tool()
    backend.messages.put({"kind": "sample", "job": backend.job_id, "payload": {"ssid": "partial"}})
    backend.messages.put({"kind": "error", "job": backend.job_id, "message": "USB removed"})
    app.poll_once()
    assert "SCAN FAILED" in app.result_text and "partial" in app.result_text
    assert app.controller.reading


def test_app_starts_gpio_once_and_stops_it_before_backend_shutdown(ui, monkeypatch):
    app, root, backend = ui
    instances = []
    class FakeGPIO:
        active = True
        def __init__(self, *args): instances.append(self)
        def close(self): self.active = False
    monkeypatch.setattr("pi_ot_probe.tablet.app.GPIOButtons", FakeGPIO)
    app.start_gpio()
    app.start_gpio()
    assert len(instances) == 1
    destroyed = []
    root.bind("<Destroy>", lambda e: destroyed.append(True) if e.widget is root else None, add="+")
    app.close()
    assert not instances[0].active and app.gpio_buttons is None
    app.gpio_navigate("ok")
    # Join the existing asynchronous shutdown through Tk's scheduled finish.
    import time
    deadline = time.monotonic() + 2
    while not destroyed and time.monotonic() < deadline:
        root.update()
        time.sleep(.01)
    assert backend.closed and destroyed
