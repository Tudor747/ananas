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

    def write(self, raw):
        request = json.loads(raw)
        self.commands.append(request)
        if self.drop or (self.reject_observe and request["command"] == "OBSERVE"):
            return len(raw)
        self.seq += 1
        self.buffer.extend(wire(node=self.node, device="wrong" if self.wrong_identity else f"chip-{self.node}",
                                seq=self.seq, session=request["session"], id=request["id"], command=request["command"]))
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
