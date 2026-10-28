"""USB failure isolation and provenance exercised without physical hardware."""
import json
import threading
import time

import pytest

from pi_ot_probe.database.repository import Repository
from pi_ot_probe.peripherals.manager import NodeManager, load_config
from pi_ot_probe.peripherals.protocol import Command, Decoder, MAX_FRAME, NodeConfig
from pi_ot_probe.peripherals.store import EvidenceStore


def frame(**changes):
    return {"v": 1, "node": "A", "device": "chip-A", "boot": "boot-1", "session": "s1",
            "firmware": "test-fixture", "seq": 1, "uptime_ms": 1, "type": "reply",
            "command": "HELLO", "id": 1, "health": "ready", "payload": {}, **changes}


def wire(**changes):
    return json.dumps(frame(**changes)).encode() + b"\n"


def wait_until(predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition timed out")
        time.sleep(.01)


class FakeSerial:
    def __init__(self, node="A", wrong_identity=False, reject_observe=False):
        self.node = node
        self.buffer = bytearray()
        self.commands = []
        self.seq = 0
        self.closed = False
        self.wrong_identity = wrong_identity
        self.reject_observe = reject_observe
        self.drop = False
        self.health = "ready"

    def write(self, raw):
        request = json.loads(raw)
        self.commands.append(request)
        if self.drop or (self.reject_observe and request["command"] == "OBSERVE"):
            return len(raw)
        self.seq += 1
        self.buffer.extend(wire(node=self.node, device="wrong" if self.wrong_identity else f"chip-{self.node}",
                                seq=self.seq, session=request["session"], id=request["id"],
                                command=request["command"], health=self.health))
        return len(raw)

    def read(self, count):
        if self.closed:
            raise OSError("cable removed")
        time.sleep(.002)
        result = bytes(self.buffer[:count])
        del self.buffer[:count]
        return result

    def close(self):
        self.closed = True


def config(node="A"):
    return NodeConfig(node=node, port=f"port-{node}", device=f"chip-{node}")


def test_handshake_recovers_when_startup_drops_first_hello(tmp_path):
    class StartingSerial(FakeSerial):
        def write(self, raw):
            self.drop = not self.commands
            return super().write(raw)

    port = StartingSerial()
    store = EvidenceStore(Repository(tmp_path / "startup.db"))
    manager = NodeManager([config()], store, lambda _: port)
    manager.start()
    try:
        wait_until(lambda: manager.state()[0]["connection"] == "online")
        hellos = [c for c in port.commands if c["command"] == "HELLO"]
        assert len(hellos) == 2
        assert hellos[0] == hellos[1]
    finally:
        manager.stop()


def test_fragmentation_overflow_resynchronization():
    decoder = Decoder()
    assert decoder.feed(b"boot log\n" + b"x" * (MAX_FRAME + 1)) == []
    assert decoder.feed(b"tail\n" + wire()[:15]) == []
    assert decoder.feed(wire()[15:])[0].device == "chip-A"
    assert decoder.rejected == 2


@pytest.mark.parametrize("changes", [{"seq": True}, {"seq": -1}, {"v": True}, {"v": 1.0}, {"node": "D"},
                                    {"payload": {"value": float("nan")}}, {"extra": "x"}])
def test_invalid_frames_rejected(changes):
    decoder = Decoder()
    assert decoder.feed(wire(**changes)) == []
    assert decoder.rejected == 1


def test_command_authorization_and_role_boundaries():
    with pytest.raises(ValueError):
        Command(command="OBSERVE", args={"sensor": "rfid", "duration_ms": 1000}).check("B")
    authorized = dict(authorized=True, operator="tester", purpose="owned lab tag")
    Command(command="OBSERVE", args={"sensor": "rfid", "duration_ms": 1000}, **authorized).check("B")
    with pytest.raises(ValueError):
        Command(command="OBSERVE", args={"sensor": "rfid", "duration_ms": 1000}, **authorized).check("A")
    with pytest.raises(ValueError):
        Command(command="TRANSMIT", args={"code": 10}, **authorized).check("A")


def test_duplicate_config_rejected(tmp_path):
    path = tmp_path / "nodes.json"
    path.write_text(json.dumps([config().model_dump(), config().model_dump()]))
    with pytest.raises(ValueError, match="duplicate"):
        load_config(path)


def test_three_nodes_wrong_identity_isolated_and_evidence_persisted(tmp_path):
    store = EvidenceStore(Repository(tmp_path / "evidence.db"))
    ports = {f"port-{n}": FakeSerial(n, wrong_identity=n == "B") for n in "ABC"}
    manager = NodeManager([config(n) for n in "ABC"], store, ports.__getitem__)
    manager.start()
    try:
        wait_until(lambda: manager.state()[0]["connection"] == "online" and manager.state()[2]["connection"] == "online")
        wait_until(lambda: manager.state()[1]["connection"] == "offline")
        with pytest.raises(ValueError, match="online"):
            manager.command("B", Command(command="STATUS"))
        manager.command("C", Command(command="STATUS"))
        wait_until(lambda: any(e["node"] == "C" and e["kind"] == "reply" and e["data"]["command"] == "STATUS" for e in store.events()))
    finally:
        manager.stop()
    assert all(s["connection"] == "offline" for s in manager.state())
    restored = EvidenceStore(Repository(tmp_path / "evidence.db"))
    assert any(e["kind"] == "disconnect" for e in restored.events())
    assert "not independently verified" in restored.markdown()


def test_stop_preempts_missing_observe_ack(tmp_path):
    store = EvidenceStore(Repository(tmp_path / "e.db"))
    port = FakeSerial(reject_observe=True)
    manager = NodeManager([config()], store, lambda _: port)
    manager.start()
    try:
        wait_until(lambda: manager.state()[0]["connection"] == "online")
        manager.command("A", Command(command="OBSERVE", authorized=True, operator="test", purpose="lab",
                                     args={"sensor": "nrf", "duration_ms": 1000}))
        wait_until(lambda: any(c["command"] == "OBSERVE" for c in port.commands))
        started = time.monotonic()
        manager.command("A", Command(command="STOP"))
        wait_until(lambda: any(c["command"] == "STOP" for c in port.commands), timeout=1)
        assert time.monotonic() - started < 1
        assert any(e["kind"] == "cancelled" for e in store.events())
    finally:
        manager.stop()


def test_reconnect_new_session_and_no_command_replay(tmp_path):
    store = EvidenceStore(Repository(tmp_path / "e.db"))
    ports = [FakeSerial(), FakeSerial()]
    attempts = []
    def opener(_):
        port = ports[min(len(attempts), 1)]
        attempts.append(port)
        return port
    manager = NodeManager([config()], store, opener)
    manager.start()
    try:
        wait_until(lambda: manager.state()[0]["connection"] == "online")
        old_session = manager.state()[0]["session"]
        ports[0].closed = True
        wait_until(lambda: manager.state()[0]["connection"] == "offline")
        wait_until(lambda: manager.state()[0]["connection"] == "online", timeout=4)
        assert manager.state()[0]["session"] != old_session
        assert all(c["command"] in {"HELLO", "STATUS"} for c in ports[1].commands)
    finally:
        manager.stop()


def test_gap_duplicate_and_old_session_frames(tmp_path):
    store = EvidenceStore(Repository(tmp_path / "e.db"))
    port = FakeSerial()
    manager = NodeManager([config()], store, lambda _: port)
    manager.start()
    try:
        wait_until(lambda: manager.state()[0]["connection"] == "online")
        session = manager.state()[0]["session"]
        port.buffer.extend(wire(type="event", command="OBSERVE", seq=10, session="old-session", payload={"sensor":"nrf"}))
        port.seq = 11
        port.buffer.extend(wire(type="event", command="OBSERVE", seq=11, session=session, payload={"sensor":"nrf"}))
        wait_until(lambda: any(e["kind"] == "sequence_gap" for e in store.events()))
        assert not any(e["data"].get("session") == "old-session" for e in store.events())
        port.buffer.extend(wire(type="event", command="OBSERVE", seq=11, session=session, payload={"sensor":"nrf"}))
        wait_until(lambda: manager.state()[0]["connection"] == "offline")
        assert "sequence" in manager.state()[0]["error"]
    finally:
        manager.stop()


def test_replay_labels_and_validation(tmp_path):
    from pi_ot_probe.peripherals.replay import import_replay
    store = EvidenceStore(Repository(tmp_path / "e.db"))
    path = tmp_path / "export.json"
    data = {"schema":"rf-sentinel-evidence-v1", "events":[{"kind":"reply", "received_at":"original-time", "data":frame()}]}
    path.write_text(json.dumps(data))
    assert import_replay(path, store) == 1
    assert store.events()[0]["provenance"] == "replay"
    assert store.events()[0]["data"]["original_received_at"] == "original-time"
    data["events"][0]["data"]["node"] = "unknown"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        import_replay(path, store)
    assert len(store.events()) == 1


def test_reconnected_node_rejects_command_from_previous_session(tmp_path):
    from pi_ot_probe.peripherals.manager import NodeWorker
    worker = NodeWorker(config(), EvidenceStore(Repository(tmp_path / "db")))
    worker.session = "new-session"
    worker.update(connection="online")
    with pytest.raises(ValueError, match="reconnected"):
        worker.enqueue(Command(command="STATUS"), expected_session="old-session")
    assert not worker.queue
    worker.stop()
    with pytest.raises(ValueError, match="online"):
        worker.enqueue(Command(command="STATUS"))


def test_serial_close_failure_does_not_kill_reconnect_worker(tmp_path):
    class BrokenClose(FakeSerial):
        def close(self):
            super().close()
            raise OSError("USB driver close failed")

    first, replacement = BrokenClose(), FakeSerial()
    attempts = []
    def open_port(_):
        port = replacement if attempts else first
        attempts.append(port)
        return port

    manager = NodeManager([config()], EvidenceStore(Repository(tmp_path / "db")), open_port)
    manager.start()
    try:
        wait_until(lambda: manager.state()[0]["connection"] == "online")
        manager.start()
        assert len(attempts) == 1
        first.closed = True
        wait_until(lambda: len(attempts) == 2 and manager.state()[0]["connection"] == "online", timeout=4)
    finally:
        manager.stop()


def test_idle_heartbeats_keep_connections_alive_without_repeated_evidence(tmp_path):
    store = EvidenceStore(Repository(tmp_path / "db"))
    port = FakeSerial()
    manager = NodeManager([config()], store, lambda _: port)
    manager.start()
    try:
        wait_until(lambda: manager.state()[0].get("last_seq", 0) >= 4, timeout=5)
        replies = lambda: [e for e in store.events() if e["kind"] == "reply" and e["data"]["command"] == "STATUS"]
        assert len(replies()) == 1
        port.health = "error"
        wait_until(lambda: manager.state()[0]["health"] == "error")
        assert len(replies()) == 2
        request = manager.command("A", Command(command="STATUS"))
        wait_until(lambda: any(e["data"]["id"] == request for e in replies()))
        assert len(replies()) == 3
    finally:
        manager.stop()


def test_aliases_for_same_usb_port_cannot_be_assigned_twice(tmp_path):
    endpoint = tmp_path / "ttyUSB0"
    endpoint.touch()
    alias = tmp_path / "stable-name"
    try:
        alias.symlink_to(endpoint)
    except OSError:
        pytest.skip("Creating symlinks is not permitted")
    path = tmp_path / "nodes.json"
    path.write_text(json.dumps([
        {"node": "A", "port": str(endpoint), "device": "a"},
        {"node": "B", "port": str(alias), "device": "b"},
    ]))
    with pytest.raises(ValueError, match="duplicate.*port"):
        load_config(path)


@pytest.mark.parametrize("field", ["node", "port", "device"])
def test_manager_rejects_duplicate_assignments_without_opening_ports(tmp_path, field):
    second = config("B").model_dump()
    second[field] = getattr(config("A"), field)
    with pytest.raises(ValueError, match=f"duplicate node configuration {field}"):
        NodeManager([config("A"), NodeConfig(**second)],
                    EvidenceStore(Repository(tmp_path / "db")),
                    lambda _: pytest.fail("invalid configuration must not open USB"))


def test_stop_preempts_an_already_expired_reply(tmp_path, monkeypatch):
    from pi_ot_probe.peripherals.manager import NodeWorker
    clock = [100.0]
    monkeypatch.setattr("pi_ot_probe.peripherals.manager.time.monotonic", lambda: clock[0])
    store = EvidenceStore(Repository(tmp_path / "db"))
    worker = NodeWorker(config(), store)
    worker.session = "test-session"
    append = store.append

    def record(node, session, kind, data, provenance="usb"):
        append(node, session, kind, data, provenance)
        if kind == "reply" and data["command"] == "HELLO":
            worker.enqueue(Command(command="STATUS"))
        elif kind == "sent" and data["command"] == "STATUS":
            clock[0] += 5
            worker.enqueue(Command(command="STOP"))
        elif kind == "reply" and data["command"] == "STOP":
            worker.stop_event.set()

    monkeypatch.setattr(store, "append", record)
    port = FakeSerial()
    worker.connected(port)
    assert [c["command"] for c in port.commands] == ["HELLO", "STATUS", "STOP"]


def test_all_three_observe_concurrently_and_reconnect_independently(tmp_path):
    rendezvous = threading.Barrier(3)

    class ConcurrentSerial(FakeSerial):
        def write(self, raw):
            request = json.loads(raw)
            if request["command"] == "OBSERVE":
                # All three workers must enter OBSERVE before any can finish.
                rendezvous.wait(timeout=3)
            result = super().write(raw)
            if request["command"] == "OBSERVE":
                for payload in ({"sample": self.node}, {"complete": True}):
                    self.seq += 1
                    self.buffer.extend(wire(node=self.node, device=f"chip-{self.node}",
                                            seq=self.seq, session=request["session"],
                                            id=request["id"], type="event", command="OBSERVE",
                                            payload={"sensor": request["args"]["sensor"], **payload}))
            return result

    ports = {f"port-{n}": ConcurrentSerial(n) for n in "ABC"}
    store = EvidenceStore(Repository(tmp_path / "db"))
    manager = NodeManager([config(n) for n in "ABC"], store, ports.__getitem__)
    manager.start()
    try:
        wait_until(lambda: all(s["connection"] == "online" for s in manager.state()))
        sessions = {s["node"]: s["session"] for s in manager.state()}
        requests = {}
        for node, sensor in zip("ABC", ("nrf", "cc1101", "ir")):
            requests[node] = manager.command(node, Command(
                command="OBSERVE", authorized=True, operator="test", purpose="concurrency",
                args={"sensor": sensor, "duration_ms": 1000}))
        wait_until(lambda: sum(e["kind"] == "event" and e["data"]["payload"].get("complete", False)
                               for e in store.events()) == 3)
        events = [e for e in store.events() if e["kind"] == "event"]
        assert len(events) == 6
        for event in events:
            assert event["session"] == sessions[event["node"]]
            assert event["data"]["id"] == requests[event["node"]]
            assert event["data"]["device"] == f"chip-{event['node']}"

        disconnected = ports["port-B"]
        ports["port-B"] = ConcurrentSerial("B")
        disconnected.closed = True
        wait_until(lambda: manager.state()[1]["connection"] == "offline")
        for node in "AC":
            request = manager.command(node, Command(command="STATUS"))
            wait_until(lambda: any(e["node"] == node and e["kind"] == "reply" and
                                   e["data"]["id"] == request for e in store.events()))
        wait_until(lambda: manager.state()[1]["connection"] == "online", timeout=4)
        assert manager.state()[1]["session"] != sessions["B"]
        assert all(s["session"] == sessions[s["node"]] for s in manager.state() if s["node"] != "B")
        assert not any(c["command"] == "OBSERVE" for c in ports["port-B"].commands)
    finally:
        manager.stop()
    assert all(port.closed for port in ports.values())
