"""Regression checks for ambiguous USB bridges, identification and pairing."""
import json
import subprocess
import threading
from types import SimpleNamespace

import pytest

from pi_ot_probe.peripherals import ports, provision
from pi_ot_probe.peripherals.manager import NodeWorker
from pi_ot_probe.tablet.backend import TabletBackend
from tests.test_peripherals import FakeSerial, config, wire, wait_until
from pi_ot_probe.database.repository import Repository
from pi_ot_probe.peripherals.store import EvidenceStore
from pi_ot_probe.tablet.presentation import describe_node, format_result


def test_identification_tries_roles_without_observing_or_transmitting():
    class Board(FakeSerial):
        def write(self, raw):
            if json.loads(raw)["node"] == self.node:
                return super().write(raw)
            return len(raw)
    board = Board("C")
    assert provision.identify(board) == {"node": "C", "device": "chip-C"}
    assert {r["command"] for r in board.commands} == {"HELLO"}


@pytest.mark.parametrize("output, expected", [
    (b"assert failed: spinlock_acquire\nRebooting...", "crashing"),
    (b"Original firmware\n", "installed node_a"),
    (b"", "No USB reply"),
])
def test_identification_reports_reason(output, expected):
    now = [0]
    class Port:
        def write(self, data): return len(data)
        def read(self, count):
            now[0] += 1
            return output
    with pytest.raises(TimeoutError, match=expected):
        provision.identify(Port(), clock=lambda: now[0], timeout=2)


def test_usb_paths_do_not_use_shared_0001_alias_or_onboard_uart(monkeypatch, tmp_path):
    from serial.tools import list_ports
    devices = [SimpleNamespace(device=f"ttyUSB{i}", serial_number="0001", vid=0x10c4,
                               description="CP2102") for i in range(2)]
    devices.append(SimpleNamespace(device="ttyAMA10", serial_number=None, vid=None, description="UART"))
    monkeypatch.setattr(list_ports, "comports", lambda: devices)
    folders = {}
    for name in ("by-id", "by-path"):
        folders[name] = tmp_path / name
        folders[name].mkdir()
    (folders["by-id"] / "controller_0001").touch()
    for i in range(2):
        (folders["by-path"] / f"socket-{i}").touch()
    monkeypatch.setattr(ports, "Path", lambda path: folders[path.rsplit("/", 1)[-1]])
    monkeypatch.setattr(ports, "port_key", lambda path: "ttyUSB1" if path.endswith("controller_0001")
                        else f"ttyUSB{path[-1]}" if "socket-" in path else path)
    result = ports.serial_ports()
    assert [p["port"] for p in result] == [str(folders["by-path"] / f"socket-{i}") for i in range(2)]


def test_ui_snapshot_does_not_wait_for_usb_command_lock():
    worker = NodeWorker(config(), None)
    ready, release = threading.Event(), threading.Event()
    def slow_io():
        with worker.lock:
            ready.set()
            release.wait(3)
    thread = threading.Thread(target=slow_io)
    thread.start()
    assert ready.wait(1)
    try:
        completed = threading.Event()
        reader = threading.Thread(target=lambda: (worker.snapshot(), completed.set()))
        reader.start()
        assert completed.wait(.5), "UI snapshot blocked behind serial/evidence I/O"
    finally:
        release.set()
        thread.join()
        reader.join()


@pytest.fixture
def backend(tmp_path):
    class Manager:
        def __init__(self, configs, store): self.configs, self.running = configs, False
        def start(self): self.running = True
        def stop(self): self.running = False
        def state(self): return []
    path = tmp_path / "nodes.json"
    path.write_text(json.dumps([{"node": "B", "port": "old-B", "device": "chip-B"}]))
    app = TabletBackend(path, tmp_path / "db", tmp_path / "out", Manager)
    yield app
    app.close()


def test_find_connects_actual_roles_and_preserves_absent_board(backend, monkeypatch):
    monkeypatch.setattr("pi_ot_probe.tablet.backend.serial_ports", lambda: [{"port": "usb-C"}, {"port": "usb-A"}])
    def run(args, **kwargs):
        assert not backend.manager.running
        role = args[-1][-1]
        return subprocess.CompletedProcess(args, 0, json.dumps({"node": role, "port": args[-1], "device": f"chip-{role}"}))
    monkeypatch.setattr(subprocess, "run", run)
    result = backend.pair_all()
    assert {c["node"] for c in result["connected"]} == {"A", "C"}
    assert {c["node"] for c in json.loads(backend.config_path.read_text())} == {"A", "B", "C"}
    assert backend.manager.running
    assert backend.config_path.with_suffix(".json.bak").exists()


def test_find_failure_preserves_file_and_reconnects_existing_nodes(backend, monkeypatch):
    before = backend.config_path.read_bytes()
    monkeypatch.setattr("pi_ot_probe.tablet.backend.serial_ports", lambda: [{"port": "usb"}])
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, '{"error":"ESP is crashing"}'))
    with pytest.raises(ValueError, match="ESP is crashing"):
        backend.pair_all()
    assert backend.config_path.read_bytes() == before
    assert backend.manager.running


def test_find_refuses_duplicate_roles(backend, monkeypatch):
    before = backend.config_path.read_bytes()
    monkeypatch.setattr("pi_ot_probe.tablet.backend.serial_ports", lambda: [{"port": "usb1"}, {"port": "usb2"}])
    def run(args, **kwargs):
        return subprocess.CompletedProcess(args, 0, json.dumps({"node": "C", "port": args[-1], "device": args[-1]}))
    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(ValueError, match="duplicate"):
        backend.pair_all()
    assert backend.config_path.read_bytes() == before
    assert backend.manager.running


def test_cancelled_discovery_does_not_save_partial_configuration(backend, monkeypatch):
    before = backend.config_path.read_bytes()
    monkeypatch.setattr("pi_ot_probe.tablet.backend.serial_ports", lambda: [{"port": "usb-C"}])
    def run(args, **kwargs):
        backend.cancelled.set()
        return subprocess.CompletedProcess(args, 0, json.dumps({"node": "C", "port": "usb-C", "device": "chip-C"}))
    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(InterruptedError):
        backend.pair_all()
    assert backend.config_path.read_bytes() == before
    assert backend.manager.running


def test_stop_does_not_hold_ui_and_new_job_waits_for_stop(backend, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    def slow_stop():
        entered.set()
        release.wait(3)
    monkeypatch.setattr(backend, "stop", slow_stop)
    try:
        backend.stop_async()
        assert entered.wait(1) and backend.cancelled.is_set()
        with pytest.raises(ValueError, match="Stopping"):
            backend.start("usb", auto=True)
    finally:
        release.set()
        backend._stop_thread.join()


def test_stale_other_role_frame_does_not_break_fresh_identification(tmp_path):
    port = FakeSerial()
    port.buffer.extend(wire(node="C", device="chip-C", session="old-provisioning-session"))
    worker = NodeWorker(config(), EvidenceStore(Repository(tmp_path / "e.db")), lambda _: port)
    worker.start()
    try:
        wait_until(lambda: worker.snapshot()["connection"] == "online")
        assert worker.snapshot()["error"] is None
        assert len([c for c in port.commands if c["command"] == "HELLO"]) == 1
    finally:
        worker.stop()


def test_hardware_failure_is_reported_per_radio_while_usb_stays_online(tmp_path):
    class Board(FakeSerial):
        def write(self, raw):
            request = json.loads(raw)
            self.commands.append(request)
            self.seq += 1
            self.buffer.extend(wire(seq=self.seq, session=request["session"], id=request["id"],
                                    command=request["command"], health="error",
                                    payload={"hardware": {"nrf1_spi": True, "nrf2_spi": False}}))
            return len(raw)
    port = Board()
    worker = NodeWorker(config(), EvidenceStore(Repository(tmp_path / "hw.db")), lambda _: port)
    worker.start()
    try:
        wait_until(lambda: worker.snapshot().get("hardware", {}).get("nrf2_spi") is False)
        state = worker.snapshot()
        assert state["connection"] == "online" and state["health"] == "error"
        text = describe_node(state)
        assert "nRF radio 1: SPI check passed" in text and "nRF radio 2: SPI check failed" in text
        assert "USB connected" in text
    finally:
        worker.stop()


def test_role_mismatch_explains_firmware_instead_of_relabelling(monkeypatch, capsys):
    port = FakeSerial("C")
    monkeypatch.setattr(provision, "serial_open", lambda _: port)
    monkeypatch.setattr("sys.argv", ["provision", "--node", "A", "--port", "usb-nrf"])
    assert provision.main() == 1
    message = json.loads(capsys.readouterr().out)["error"]
    assert "ESP-C, not ESP-A" in message and "node_a" in message
    assert "chip-C" in message and "usb-nrf" in message
    assert port.closed and {r["command"] for r in port.commands} == {"HELLO"}


def test_inspect_reports_firmware_identity_without_changing_configuration(monkeypatch, capsys):
    port = FakeSerial("B")
    monkeypatch.setattr(provision, "serial_open", lambda _: port)
    monkeypatch.setattr("sys.argv", ["provision", "--node", "auto", "--port", "usb-433", "--inspect"])
    assert provision.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["node"] == "B" and result["device"] == "chip-B"
    assert result["firmware"] == "test-fixture" and result["health"] == "ready"


def test_find_replaces_stale_port_assignment_but_preserves_unrelated_board(backend, monkeypatch):
    old = [{"node": "A", "port": "usb0", "device": "old-A"},
           {"node": "C", "port": "absent-C", "device": "chip-C"}]
    backend.config_path.write_text(json.dumps(old))
    monkeypatch.setattr("pi_ot_probe.tablet.backend.serial_ports", lambda: [{"port": "usb0"}])
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        a, 0, json.dumps({"node": "B", "port": "usb0", "device": "chip-B"})))
    result = backend.pair_all()
    saved = json.loads(backend.config_path.read_text())
    assert {c["node"] for c in saved} == {"B", "C"}
    assert result["replaced_assignments"] == [old[0]]
    assert json.loads(backend.config_path.with_suffix(".json.bak").read_text()) == old
    text = format_result(result)
    assert "No ESP-A firmware" in text and "Replaced stale assignments: ESP-A" in text


def test_unused_standby_does_not_touch_usb_on_shutdown(monkeypatch):
    from pi_ot_probe.tablet.usb_standby import USBStandby
    calls = []
    monkeypatch.setattr(USBStandby, "_power", staticmethod(lambda state: calls.append(state)))
    standby = USBStandby(SimpleNamespace())
    standby.shutdown()
    assert calls == [] and not standby.thread.is_alive()
