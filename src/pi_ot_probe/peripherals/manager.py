"""One bounded serial worker per allowlisted node; failure never blocks its peers."""
from __future__ import annotations

from collections import deque
import json
import logging
import os
import queue
from pathlib import Path
import secrets
import threading
import time

from .protocol import BUTTON_ACTIONS, Command, Decoder, NodeConfig, ROLES

logger = logging.getLogger(__name__)


def port_key(port):
    """Compare USB aliases as the same endpoint, including Linux by-id paths."""
    return os.path.normcase(os.path.realpath(port))


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
    return validate_configs(raw)


def validate_configs(configs):
    """Apply the same identity and endpoint checks to every configuration source."""
    nodes = [NodeConfig.model_validate(item) for item in configs]
    if len(nodes) > 3:
        raise ValueError("node configuration must contain at most three entries")
    for key in ("node", "port", "device"):
        values = [port_key(n.port) if key == "port" else getattr(n, key) for n in nodes]
        if len(set(values)) != len(nodes):
            raise ValueError(f"duplicate node configuration {key}")
    return nodes


class NodeWorker:
    def __init__(self, config, store, opener=serial_open, on_input=None):
        self.config, self.store, self.opener = config, store, opener
        self.on_input = on_input
        self.lock = threading.RLock()
        # UI snapshots must never wait for serial writes or evidence transactions.
        self.state_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.queue = deque()
        self.counter = 0
        self.session = ""
        self.state = {"node": config.node, "device": config.device, "port": config.port,
                      "connection": "offline", "health": "unknown", "error": None}
        self.thread = None

    def snapshot(self):
        with self.state_lock:
            return dict(self.state)

    def update(self, **values):
        with self.state_lock:
            self.state.update(values)

    def enqueue(self, command, expected_session=None):
        command.check(self.config.node)
        with self.lock:
            if self.stop_event.is_set() or self.state["connection"] != "online":
                raise ValueError("node is not identified and online")
            if expected_session is not None and expected_session != self.session:
                raise ValueError("node reconnected before the command was queued; run the test again")
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
        with self.lock:
            if self.thread and self.thread.is_alive():
                if self.stop_event.is_set():
                    raise RuntimeError(f"ESP-{self.config.node} is still stopping")
                return
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
                self.update(connection="connecting", health="unknown")
                port = self.opener(self.config.port)
                self.session = secrets.token_hex(16)
                self.connected(port)
            except Exception as exc:
                reason = str(exc)[:300]
                previous_error = self.snapshot().get("error")
                self.update(connection="offline", health="unknown", error=reason)
                if reason != previous_error:
                    logger.warning("ESP-%s connection failed: %s", self.config.node, reason, exc_info=True)
                    self.store.append(self.config.node, self.session, "disconnect", {"reason": reason}, "host")
            finally:
                # Refuse new work before releasing the port or cancelling its queue.
                self.update(connection="offline", health="unknown")
                if port is not None:
                    try:
                        # Best effort only: the device also has a local duration/watchdog limit.
                        port.write(self.encode("STOP", 0, {}))
                    except Exception:
                        logger.debug("ESP-%s shutdown STOP failed", self.config.node, exc_info=True)
                    try:
                        port.close()
                    except Exception:
                        logger.warning("ESP-%s serial close failed", self.config.node, exc_info=True)
                with self.lock:
                    for request_id, queued in self.queue:
                        self.store.append(self.config.node, self.session, "cancelled",
                                          {"id": request_id, "command": queued.command}, "host")
                    self.queue.clear()
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
        last_status = None

        def send(command, request_id, args, heartbeat=False):
            nonlocal pending
            raw = self.encode(command, request_id, args)
            if command == "HELLO":
                # Discard any partial input left by startup or an earlier connection.
                raw = b"\n" + raw
            if port.write(raw) != len(raw):
                raise OSError("incomplete serial write")
            pending = (request_id, command, time.monotonic() + 4, heartbeat)
            if not heartbeat:
                self.store.append(self.config.node, self.session, "sent", json.loads(raw), "host")

        with self.lock:
            self.counter += 1
            hello_id = self.counter
        send("HELLO", hello_id, {})
        hello_deadline = time.monotonic() + 8
        next_hello = time.monotonic() + 1
        try:
            while not self.stop_event.is_set():
                now = time.monotonic()
                if not identified and now >= hello_deadline:
                    raise TimeoutError("HELLO timed out after 8 seconds of handshake retries")
                with self.lock:
                    stopping = bool(self.queue and self.queue[0][1].command == "STOP")
                if identified and pending and now >= pending[2] and not stopping:
                    raise TimeoutError(f"{pending[1]} timed out; command was not retried")
                for frame in decoder.feed(port.read(256)):
                    record = True
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
                        if pending[3]:
                            status = (frame.health, frame.payload)
                            record = status != last_status
                            last_status = status
                        pending = None
                        next_heartbeat = now + 1
                    elif frame.command == "INPUT":
                        if (frame.node != "A" or frame.id != 0 or set(frame.payload) != {"action"} or
                                not isinstance(frame.payload["action"], str) or
                                frame.payload["action"] not in BUTTON_ACTIONS):
                            raise ValueError("invalid controller input")
                        # Live input only: replayed evidence must never press buttons.
                        record = False
                        if self.on_input:
                            self.on_input(frame.node, self.session, frame.payload["action"])
                    elif frame.command != "OBSERVE" or frame.payload.get("sensor") not in ROLES[self.config.node]:
                        raise ValueError("unexpected event sensor/command")
                    # Keep health changes and operator requests, not identical idle heartbeats.
                    if record:
                        self.store.append(self.config.node, self.session, frame.type, frame.model_dump())
                    self.update(health=frame.health, last_seq=last_seq, last_seen=time.time(), error=None)
                if decoder.rejected != rejected:
                    self.store.append(self.config.node, self.session, "malformed_frame",
                                      {"count": decoder.rejected - rejected}, "host")
                    rejected = decoder.rejected
                # Only identification is retried; never replay an operation.
                if not identified and time.monotonic() >= next_hello:
                    send("HELLO", hello_id, {})
                    next_hello = time.monotonic() + 1
                # A STOP can preempt a lost reply; it never waits for timeout.
                with self.lock:
                    if self.stop_event.is_set():
                        break
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
                        send("STATUS", self.counter, {}, heartbeat=True)
        finally:
            if pending:
                self.store.append(self.config.node, self.session, "unconfirmed",
                                  {"id": pending[0], "command": pending[1]}, "host")


class NodeManager:
    def __init__(self, configs, store, opener=serial_open):
        self.store = store
        self.inputs = queue.Queue(maxsize=32)
        self.workers = {c.node: NodeWorker(c, store, opener, self._input) for c in validate_configs(configs)}

    def _input(self, node, session, action):
        try:
            self.inputs.put_nowait((time.monotonic(), node, session, action))
        except queue.Full:
            pass

    def button_actions(self):
        """Drain fresh presses on the UI thread, dropping stale/disconnected input."""
        actions = []
        for _ in range(32):
            try:
                received, node, session, action = self.inputs.get_nowait()
            except queue.Empty:
                break
            state = self.workers[node].snapshot()
            if (time.monotonic() - received < 1 and state["connection"] == "online" and
                    state.get("session") == session):
                actions.append(action)
        return actions

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

    def command(self, node, command, expected_session=None):
        if node not in self.workers:
            raise ValueError("node is not configured")
        return self.workers[node].enqueue(command, expected_session=expected_session)
