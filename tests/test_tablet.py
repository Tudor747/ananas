"""Native jobs tested with serial fixtures; no live RF or network scans."""
import json
from pathlib import Path
import queue
import subprocess
import time

import pytest

from pi_ot_probe.collectors.interfaces import LocalNetwork
from pi_ot_probe.peripherals.manager import NodeManager
from pi_ot_probe.tablet.backend import TabletBackend, summarize
from pi_ot_probe.tablet.catalog import BY_KEY, CATEGORIES, TOOLS
from tests.test_peripherals import FakeSerial, wait_until, wire


class ObservationSerial(FakeSerial):
    def __init__(self, complete=True):
        super().__init__()
        self.complete = complete

    def write(self, raw):
        request = json.loads(raw)
        result = super().write(raw)
        if request["command"] == "OBSERVE":
            for request_id, payload in (
                (999, {"sensor": "wifi", "ssid": "wrong request", "bssid": "wrong", "channel": 1}),
                (request["id"], {"sensor": "wifi", "ssid": "test AP", "bssid": "00:11:22:33:44:55", "channel": 6, "rssi_dbm": -48}),
            ):
                self.seq += 1
                self.buffer.extend(wire(seq=self.seq, session=request["session"], type="event", command="OBSERVE",
                                        id=request_id, health="error", payload=payload))
            if self.complete:
                self.seq += 1
                self.buffer.extend(wire(seq=self.seq, session=request["session"], type="event", command="OBSERVE",
                                        id=request["id"], payload={"sensor": "wifi", "complete": True}))
        return result


@pytest.fixture
def native(tmp_path):
    config = tmp_path / "nodes.json"
    config.write_text(json.dumps([{"node": "A", "port": "fake", "device": "chip-A"}]))
    port = ObservationSerial()
    app = TabletBackend(config, tmp_path / "db.sqlite", tmp_path / "reports",
                        lambda configs, store: NodeManager(configs, store, lambda _: port))
    wait_until(lambda: app.state()[0]["connection"] == "online")
    yield app, port
    app.close()


def messages(app):
    result = []
    while True:
        try:
            result.append(app.messages.get_nowait())
        except queue.Empty:
            return result


def test_native_scan_correlates_request_and_preserves_hardware_error(native):
    app, port = native
    app.start("wifi", authorized=True)
    wait_until(lambda: not app.busy)
    output = messages(app)
    done = next(m for m in output if m["kind"] == "done")
    assert [r["ssid"] for r in done["result"]["records"]] == ["test AP"]
    assert Path(done["path"]).exists()
    saved = json.loads(Path(done["path"]).read_text())
    assert saved["source"] == "ESP-A USB"
    assert all(m["job"] == app.job_id for m in output)


def test_stop_cancels_observation_and_does_not_save_success(native):
    app, port = native
    port.complete = False
    app.start("wifi", authorized=True)
    wait_until(lambda: any(c["command"] == "OBSERVE" for c in port.commands))
    app.stop()
    wait_until(lambda: not app.busy)
    wait_until(lambda: any(c["command"] == "STOP" for c in port.commands))
    assert any(m["kind"] == "cancelled" for m in messages(app))
    assert app.last_result is None


def test_concurrent_or_unapproved_operations_rejected(native):
    app, port = native
    with pytest.raises(ValueError, match="permission"):
        app.start("wifi")
    port.complete = False
    app.start("wifi", authorized=True)
    with pytest.raises(ValueError, match="operation"):
        app.start("ble", authorized=True)


def test_unavailable_tools_cannot_dispatch(native):
    app, port = native
    count = len(port.commands)
    for tool in TOOLS:
        if tool.action is None:
            with pytest.raises(ValueError):
                app.start(tool.key, authorized=True)
    assert not any(c["command"] in {"OBSERVE", "TRANSMIT"} for c in port.commands[count:])
    assert "Illegal" in CATEGORIES
    assert len([t for t in TOOLS if t.category == "Illegal"]) == 8


def test_summaries_use_unique_devices_and_sample_denominators():
    rows = [{"bssid": "one", "channel": 6}, {"bssid": "one", "channel": 6}, {"bssid": "two", "channel": 1}]
    assert summarize("channels", rows)["access_points_per_channel"] == {1: 1, 6: 1}
    rows = [{"channel": 5, "nrf1_carrier": True, "nrf2_carrier": False},
            {"channel": 5, "nrf1_carrier": False, "nrf2_carrier": False},
            {"channel": 10, "nrf1_carrier": False, "nrf2_carrier": False}]
    channels = summarize("advisor", rows)["sampled_channels"]
    assert [r["channel"] for r in channels] == [10, 5]
    assert channels[1]["hit_fraction"] == .25
    assert all(r["channel"] in {5, 10} for r in channels)


def test_ip_scan_validates_target_before_launch(native, monkeypatch):
    app, _ = native
    async def networks():
        return [LocalNetwork("eth0", "192.168.1.2", "192.168.1.0/24", "192.168.1.0/24")]
    monkeypatch.setattr("pi_ot_probe.tablet.backend.discover_local_networks", networks)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("must not launch Nmap"))
    for target in ("8.8.8.8/32", "192.168.0.0/16", "192.168.2.0/24", "--script=anything"):
        with pytest.raises(ValueError):
            app.network_scan(target)


def test_cancel_terminates_nmap_child(native, monkeypatch):
    app, _ = native
    async def networks():
        return [LocalNetwork("eth0", "192.168.1.2", "192.168.1.0/24", "192.168.1.0/24")]
    class Process:
        returncode = None
        terminated = False
        def communicate(self, timeout):
            if self.terminated:
                self.returncode = -1
                return b"", b""
            app.cancelled.set()
            raise subprocess.TimeoutExpired("nmap", timeout)
        def poll(self): return self.returncode
        def terminate(self): self.terminated = True
    process = Process()
    monkeypatch.setattr("pi_ot_probe.tablet.backend.discover_local_networks", networks)
    monkeypatch.setattr("pi_ot_probe.tablet.backend.find_nmap", lambda: "nmap")
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: process)
    with pytest.raises(InterruptedError):
        app.network_scan("192.168.1.0/24")
    assert process.terminated


def test_receive_sweep_never_transmits_and_link_uses_explicit_channel(native, monkeypatch):
    app, _ = native
    requests = []
    def request(node, command, args, purpose, duration=0):
        requests.append((command, args))
        if command == "OBSERVE":
            return []
        return {"accepted": True}
    monkeypatch.setattr(app, "request", request)
    app.execute("sweep", "A", "fixture")
    assert len([c for c, _ in requests if c == "OBSERVE"]) == 26
    assert all(c != "TRANSMIT" for c, _ in requests)
    requests.clear()
    app.execute("link", "A", "fixture")
    assert requests == [("SET_CONFIG", {"channel": 76}), ("TRANSMIT", {"test": "nrf_link"})]


def test_pair_failure_keeps_configuration_and_restarts_manager(native, monkeypatch):
    app, port = native
    before = app.config_path.read_bytes()
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, '{"error":"No HELLO"}', ""))
    with pytest.raises(ValueError, match="No HELLO"):
        app.pair("A", "fake")
    assert app.config_path.read_bytes() == before
    assert app.manager.workers["A"].thread.is_alive()


def test_pair_saves_actual_identity_preserving_other_nodes(tmp_path, monkeypatch):
    class Manager:
        def __init__(self, configs, store):
            self.configs = configs
        def start(self): pass
        def stop(self): pass
        def state(self): return []
    config = tmp_path / "nodes.json"
    original = [{"node": "B", "port": "port-b", "device": "chip-b"}]
    config.write_text(json.dumps(original))
    app = TabletBackend(config, tmp_path / "db", tmp_path / "out", Manager)
    actual = {"node": "A", "port": "port-a", "device": "ABC123"}
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, json.dumps(actual), ""))
    try:
        assert app.pair("A", "port-a") == actual
        assert json.loads(config.read_text()) == original + [actual]
        assert json.loads(config.with_suffix(".json.bak").read_text()) == original
    finally:
        app.close()


def test_no_window_needed_for_cli_checks(monkeypatch, capsys):
    from pi_ot_probe.tablet.__main__ import main
    monkeypatch.setattr("pi_ot_probe.tablet.diagnostics.dependencies", lambda _: [
        {"name": "test", "ok": True, "required": True, "detail": "fixture"}])
    assert main(["--check"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["ok"]


@pytest.mark.parametrize("size", [(320, 240), (480, 320), (800, 480)])
def test_native_layout_and_navigation(size, monkeypatch):
    tk = pytest.importorskip("tkinter")
    from pi_ot_probe.tablet.app import TabletApp
    class Backend:
        busy = False
        messages = queue.Queue()
        def state(self): return [{"node": "A", "connection": "unconfigured"}]
        def stop(self): pass
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("No graphical display is available for layout checks")
    root.withdraw()
    root.attributes("-alpha", 0)
    monkeypatch.setattr(TabletApp, "refresh_choices", lambda _: None)
    try:
        app = TabletApp(root, Backend(), fullscreen=False, size=size)
        root.deiconify()
        root.update()
        assert root.winfo_width() == size[0]
        tiles = app.body.winfo_children()
        assert len(tiles) == 2
        assert all(t.winfo_height() >= 40 for t in tiles)
        app.open_category("Wi-Fi")
        app.turn_page(1)
        assert app.page == 1
        app.show_tool(BY_KEY["wifi"])
        root.update()
        assert app.run_button.winfo_height() >= 35
        assert app.footer.winfo_y() + app.footer.winfo_height() <= size[1]
        app.show_tool(BY_KEY["arcade"])
        root.update()
        assert len(app.body.winfo_children()) == 12
        app.home()
        root.update()
        assert len(app.body.winfo_children()) == 2
        assert all(t.winfo_height() >= 40 for t in app.body.winfo_children())
    finally:
        root.destroy()
