"""One bounded serial worker per allowlisted node; failure never blocks its peers."""
from __future__ import annotations

from collections import deque
import json
import os
from pathlib import Path
import secrets
import threading
import time

from .protocol import Command, Decoder, NodeConfig, ROLES


def serial_open(path):
    import serial
    port = serial.Serial(port=None, baudrate=115200, timeout=0.05, write_timeout=0.5)
    port.dtr = False
    port.rts = False
    if os.name == "posix":
        port.exclusive = True
    port.port = path
    port.open()
    return port


def load_config(path=None):
    path = path or os.environ.get("RF_SENTINEL_NODES")
    if not path:
        return []
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list) or len(raw) > 3:
        raise ValueError("node configuration must be a list of at most three entries")
    nodes = [NodeConfig.model_validate(item) for item in raw]
    for key in ("node", "port", "device"):
        if len({getattr(n, key) for n in nodes}) != len(nodes):
            raise ValueError(f"duplicate node configuration {key}")
    return nodes


class NodeWorker:
    def __init__(self, config, store, opener=serial_open):
        self.config, self.store, self.opener = config, store, opener
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.queue = deque()
        self.counter = 0
        self.session = ""
        self.state = {"node": config.node, "device": config.device, "port": config.port,
                      "connection": "offline", "health": "unknown", "error": None}
        self.thread = None

    def snapshot(self):
        with self.lock:
            return dict(self.state)

    def update(self, **values):
        with self.lock:
            self.state.update(values)

    def enqueue(self, command):
        command.check(self.config.node)
        with self.lock:
            if self.state["connection"] != "online":
                raise ValueError("node is not identified and online")
            if len(self.queue) >= 8 and command.command != "STOP":
                raise ValueError("node command queue is full")
            self.counter += 1
            item = (self.counter, command)
            if command.command == "STOP":
                # Cancel queued work so it cannot restart acquisition after STOP.
                for request_id, queued in self.queue:
                    self.store.append(self.config.node, self.session, "cancelled",
                                      {"id": request_id, "command": queued.command}, "host")
                self.queue.clear()
                self.queue.appendleft(item)
            else:
                self.queue.append(item)
            self.store.append(self.config.node, self.session, "queued",
                              {"id": self.counter, **command.model_dump()}, "operator")
            return self.counter

    def start(self):
        self.stop_event.clear()
        self.thread = threading.Thread(target=self.run, name=f"sentinel-{self.config.node}", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=6)

    def run(self):
        while not self.stop_event.is_set():
            port = None
            try:
                self.update(connection="connecting", health="unknown", error=None)
                port = self.opener(self.config.port)
                self.session = secrets.token_hex(16)
                self.connected(port)
            except Exception as exc:
                self.update(connection="offline", health="unknown", error=str(exc)[:300])
                self.store.append(self.config.node, self.session, "disconnect", {"reason": str(exc)[:300]}, "host")
            finally:
                if port is not None:
                    try:
                        # Best effort only: the device also has a local duration/watchdog limit.
                        port.write(self.encode("STOP", 0, {}))
                    except Exception:
                        pass
                    port.close()
                with self.lock:
                    for request_id, queued in self.queue:
                        self.store.append(self.config.node, self.session, "cancelled",
                                          {"id": request_id, "command": queued.command}, "host")
                    self.queue.clear()
                self.update(connection="offline", health="unknown")
            self.stop_event.wait(2)

    def encode(self, command, request_id, args):
        return (json.dumps({"v": 1, "node": self.config.node, "session": self.session,
                            "id": request_id, "command": command, "args": args}, separators=(",", ":")) + "\n").encode()

    def connected(self, port):
        decoder = Decoder()
        last_seq = 0
        boot = None
        identified = False
        pending = None
        next_heartbeat = 0
        rejected = 0

        def send(command, request_id, args):
            nonlocal pending
            raw = self.encode(command, request_id, args)
            if port.write(raw) != len(raw):
                raise OSError("incomplete serial write")
            pending = (request_id, command, time.monotonic() + 4)
            self.store.append(self.config.node, self.session, "sent", json.loads(raw), "host")

        with self.lock:
            self.counter += 1
            hello_id = self.counter
        send("HELLO", hello_id, {})
        try:
            while not self.stop_event.is_set():
                now = time.monotonic()
                if pending and now >= pending[2]:
                    raise TimeoutError(f"{pending[1]} timed out; command was not retried")
                for frame in decoder.feed(port.read(256)):
                    if frame.node != self.config.node or frame.device != self.config.device:
                        raise ValueError("USB identity does not match configured node/device")
                    if frame.session != self.session:
                        continue  # Buffered reply from an earlier connection.
                    if not identified:
                        if frame.type != "reply" or frame.command != "HELLO" or frame.id != hello_id:
                            continue
                        boot = frame.boot
                        identified = True
                        self.update(connection="online", firmware=frame.firmware, boot=boot, session=self.session)
                    if frame.boot != boot:
                        raise ValueError("node restarted; a fresh HELLO is required")
                    if frame.seq <= last_seq:
                        raise ValueError("duplicate or out-of-order sequence")
                    if last_seq and frame.seq != last_seq + 1:
                        self.store.append(self.config.node, self.session, "sequence_gap",
                                          {"after": last_seq, "before": frame.seq}, "host")
                    last_seq = frame.seq
                    if frame.type == "reply":
                        if not pending or (frame.id, frame.command) != pending[:2]:
                            self.store.append(self.config.node, self.session, "unmatched_reply", frame.model_dump())
                            continue
                        pending = None
                        next_heartbeat = now + 1
                    elif frame.command != "OBSERVE" or frame.payload.get("sensor") not in ROLES[self.config.node]:
                        raise ValueError("unexpected event sensor/command")
                    self.store.append(self.config.node, self.session, frame.type, frame.model_dump())
                    self.update(health=frame.health, last_seq=last_seq, last_seen=time.time(), error=None)
                if decoder.rejected != rejected:
                    self.store.append(self.config.node, self.session, "malformed_frame",
                                      {"count": decoder.rejected - rejected}, "host")
                    rejected = decoder.rejected
                # A STOP can preempt a lost reply; it never waits for timeout.
                with self.lock:
                    item = None
                    if identified and self.queue and (not pending or self.queue[0][1].command == "STOP"):
                        item = self.queue.popleft()
                    if item:
                        if pending:
                            self.store.append(self.config.node, self.session, "cancelled",
                                              {"id": pending[0], "command": pending[1]}, "host")
                        send(item[1].command, item[0], item[1].args)
                    elif identified and not pending and now >= next_heartbeat:
                        self.counter += 1
                        send("STATUS", self.counter, {})
        finally:
            if pending:
                self.store.append(self.config.node, self.session, "unconfirmed",
                                  {"id": pending[0], "command": pending[1]}, "host")


class NodeManager:
    def __init__(self, configs, store, opener=serial_open):
        self.store = store
        self.workers = {c.node: NodeWorker(c, store, opener) for c in configs}

    def start(self):
        for worker in self.workers.values():
            worker.start()

    def stop(self):
        for worker in self.workers.values():
            worker.stop_event.set()
        for worker in self.workers.values():
            worker.stop()

    def state(self):
        return [self.workers[n].snapshot() if n in self.workers else
                {"node": n, "connection": "unconfigured", "health": "unknown"} for n in ROLES]

    def command(self, node, command):
        if node not in self.workers:
            raise ValueError("node is not configured")
        return self.workers[node].enqueue(command)
