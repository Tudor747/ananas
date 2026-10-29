"""Native app jobs. USB and subprocess work never runs on the Tk event thread."""
from __future__ import annotations

import asyncio
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime, timezone
import getpass
import ipaddress
import json
import logging
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time

from pi_ot_probe.collectors.interfaces import discover_local_networks
from pi_ot_probe.collectors.nmap import find_nmap, parse_nmap_xml
from pi_ot_probe.collectors.targets import validate_target
from pi_ot_probe.collectors.wifi import discover_wifi
from pi_ot_probe.collectors.process import run_command
from pi_ot_probe.database.repository import Repository
from pi_ot_probe.peripherals.manager import NodeManager, load_config, port_key, validate_configs
from pi_ot_probe.peripherals.protocol import Command, NodeConfig
from pi_ot_probe.peripherals.ports import serial_ports
from pi_ot_probe.peripherals.store import EvidenceStore
from .catalog import BY_KEY
from .diagnostics import dependencies
from .network_results import completed_run, add_neighbor_macs, port_result

logger = logging.getLogger(__name__)


class Observation(list):
    def __init__(self, records, metadata):
        super().__init__(records)
        self.metadata = metadata


def summarize(action, records):
    """Summaries only use observed samples, never invented measurements."""
    metadata = getattr(records, "metadata", {})
    if action == "channels":
        aps = {r["bssid"]: r for r in records if "bssid" in r}
        return {"kind": "wifi", "access_points_per_channel": dict(sorted(Counter(r["channel"] for r in aps.values()).items())),
                "observation": metadata, "note": "AP counts, not channel airtime or utilization"}
    if action == "bt_spectrum":
        devices = {r["address"]: r for r in records if "address" in r}
        bins = Counter((int(r["rssi_dbm"]) // 10) * 10 for r in devices.values() if "rssi_dbm" in r)
        return {"kind": "ble", "devices_per_rssi_bin_dbm": dict(sorted(bins.items())),
                "observation": metadata, "note": "RSSI bins span 10 dB; this is not a frequency spectrum"}
    if action in {"sweep", "advisor"}:
        channels = {}
        for row in records:
            if "channel" not in row or "nrf1_carrier" not in row:
                continue
            value = channels.setdefault(row["channel"], {"channel": row["channel"], "samples": 0,
                                                        "radio1_hits": 0, "radio2_hits": 0})
            value["samples"] += 1
            value["radio1_hits"] += int(bool(row["nrf1_carrier"]))
            value["radio2_hits"] += int(bool(row["nrf2_carrier"]))
        rows = list(channels.values())
        for row in rows:
            row["hit_fraction"] = (row["radio1_hits"] + row["radio2_hits"]) / (2 * row["samples"])
        if action == "advisor":
            rows.sort(key=lambda r: (r["hit_fraction"], r["channel"]))
        return {"sampled_channels": rows, "note": "Carrier threshold only; unsampled channels are unknown. Not a Wi-Fi channel recommendation."}
    if action in {"wifi", "ble"}:
        identity = "bssid" if action == "wifi" else "address"
        unique = {}
        for index, row in enumerate(records):
            unique[row.get(identity, str(index))] = row
        records = sorted(unique.values(), key=lambda r: r.get("rssi_dbm", -999), reverse=True)
    return {"kind": action, "records": list(records), "count": len(records), "observation": metadata}


class TabletBackend:
    def __init__(self, config_path, database_path, output_dir, manager_factory=NodeManager):
        self.config_path = Path(config_path)
        self.output_dir = Path(output_dir)
        self.store = EvidenceStore(Repository(database_path))
        self.manager_factory = manager_factory
        self.config_error = ""
        try:
            configs = load_config(self.config_path) if self.config_path.exists() else []
        except (OSError, ValueError) as exc:
            configs = []
            self.config_error = str(exc)
        self.manager = manager_factory(configs, self.store)
        self.messages = queue.Queue()
        self.cancelled = threading.Event()
        self.closing = threading.Event()
        self.thread = None
        self.busy = False
        self.last_result = None
        self.job_id = 0
        self._local = threading.local()
        self.command_lock = threading.Lock()
        self.discovered_hosts = {}
        self.manager.start()

    def emit(self, kind, **values):
        self.messages.put({"kind": kind, "job": getattr(self._local, "job", None), **values})

    def state(self):
        return self.manager.state()

    def button_actions(self):
        return self.manager.button_actions()

    def start(self, key, authorized=False, **options):
        if getattr(self, "_stop_thread", None) is not None and self._stop_thread.is_alive():
            raise ValueError("Stopping the previous operation. Try again in a moment.")
        if self.busy or self.closing.is_set():
            raise ValueError("An operation is running. Stop it or wait for completion.")
        tool = BY_KEY[key]
        if tool.action is None:
            raise ValueError(tool.unavailable)
        if (tool.node or tool.action in {"ip", "pi_wifi"}) and not authorized:
            raise ValueError("Confirm permission for this test first.")
        self.cancelled.clear()
        self.busy = True
        self.job_id += 1
        job_id = self.job_id

        def work():
            self._local.job = job_id
            self._local.samples = []
            started = time.monotonic()
            def report(result, status):
                return {"tool": key, "title": tool.title, "status": status,
                        "received_at": datetime.now(timezone.utc).isoformat(),
                        "elapsed_seconds": round(time.monotonic() - started, 2),
                        "source": f"ESP-{tool.node} USB" if tool.node else "Raspberry Pi", "result": result}
            def failed(kind, message):
                result = {"kind": tool.action, "status": kind, "error": message,
                          "records": list(self._local.samples)}
                path = None
                try:
                    path = str(self.save_report(report(result, kind)))
                except OSError:
                    logger.exception("Could not save incomplete scan report")
                self.emit(kind, message=message, result=result, path=path)
            try:
                result = self.execute(tool.action, tool.node, tool.title, **options)
                self._check_cancelled()
                self.last_result = report(result, "complete")
                saved = self.save_report(self.last_result)
                self.emit("done", result=result, path=str(saved))
            except InterruptedError:
                failed("cancelled", "Stopped by user. This scan is incomplete.")
            except Exception as exc:
                logger.exception("Tablet job %s (%s) failed", job_id, key)
                failed("error", str(exc))
            finally:
                self.busy = False

        self.thread = threading.Thread(target=work, name="tablet-job", daemon=True)
        self.thread.start()

    def _check_cancelled(self):
        if self.cancelled.is_set() or self.closing.is_set():
            raise InterruptedError("Stopped")

    def request(self, node, command, args, purpose, duration=0):
        self._check_cancelled()
        before = self.store.latest_id()
        state = next(s for s in self.state() if s["node"] == node)
        if state["connection"] != "online":
            raise ValueError(f"ESP-{node}: {state.get('error') or state['connection']}. Use System > USB Setup if unconfigured.")
        session = state["session"]
        # STOP and submission share a lock so cancelled work cannot restart a device.
        with self.command_lock:
            self._check_cancelled()
            request_id = self.manager.command(
                node, Command(command=command, args=args, authorized=True,
                              operator=getpass.getuser()[:80], purpose=purpose[:200]),
                expected_session=session)
        deadline = time.monotonic() + duration / 1000 + 10
        records = []
        while time.monotonic() < deadline:
            self._check_cancelled()
            state = next(s for s in self.state() if s["node"] == node)
            if state["connection"] != "online" or state.get("session") != session:
                raise OSError(f"ESP-{node} disconnected: {state.get('error') or 'connection changed'}")
            for event in self.store.events(after=before, limit=200):
                before = event["id"]
                data = event["data"]
                if (event["node"] != node or event["session"] != session or
                        event["kind"] not in {"reply", "event"} or
                        data.get("id") != request_id or data.get("command") != command):
                    continue
                payload = data["payload"]
                if payload.get("error"):
                    raise ValueError(str(payload["error"]))
                if data["health"] == "unsupported":
                    raise ValueError("The installed firmware does not support this command.")
                if command != "OBSERVE":
                    return payload
                if event["kind"] == "event":
                    if payload.get("sensor") != args["sensor"]:
                        raise ValueError(f"ESP-{node} returned a different sensor for this observation")
                    if payload.get("complete"):
                        return Observation(records, {k: v for k, v in payload.items() if k not in {"complete", "sensor"}})
                    records.append(payload)
                    if hasattr(self._local, "samples"):
                        self._local.samples.append(payload)
                    self.emit("sample", payload=payload)
            if self.cancelled.wait(.05):
                self._check_cancelled()
        self.stop()
        raise TimeoutError(f"No completed {command} result from ESP-{node}")

    def observe(self, sensor, purpose, duration=None, node="A"):
        duration = duration if duration is not None else {"wifi": 8000, "ir": 10000, "rfid": 10000}.get(sensor, 5000)
        return self.request(node, "OBSERVE", {"sensor": sensor, "duration_ms": duration}, purpose, duration)

    def execute(self, action, node, purpose, **options):
        if action in {"wifi", "ble", "nrf", "cc1101", "rfid", "ir", "scope"}:
            return summarize(action, self.observe("nrf" if action == "scope" else action, purpose, node=node))
        if action in {"channels", "bt_spectrum"}:
            return summarize(action, self.observe("wifi" if action == "channels" else "ble", purpose))
        if action in {"radar", "bt_analyzer"}:
            snapshots = []
            for i in range(3):
                self.emit("progress", message=f"Snapshot {i + 1}/3")
                snapshots.append(self.observe("wifi" if action == "radar" else "ble", purpose))
            return {"snapshots": snapshots, "observations": [getattr(rows, "metadata", {}) for rows in snapshots],
                    "kind": "wifi" if action == "radar" else "ble",
                    "note": "Separate signal snapshots; addresses may rotate. No distance or bearing measurement."}
        if action == "sentinel":
            records = self.observe("wifi", purpose)
            path = self.output_dir / "wifi-snapshot.json"
            old = json.loads(path.read_text()) if path.exists() else None
            current = {r["bssid"]: r for r in records if "bssid" in r}
            result = {"baseline_created": old is None, "currently_observed": list(current.values()),
                      "newly_observed": sorted(current.keys() - (old or {}).keys()),
                      "not_observed_this_time": sorted((old or {}).keys() - current.keys()),
                      "kind": "wifi", "observation": getattr(records, "metadata", {}),
                      "note": "Compared with the preceding snapshot; absence is not proof of a missing device."}
            self.output_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(current, indent=2), encoding="utf-8")
            return result
        if action in {"sweep", "advisor"}:
            records = []
            for index, channel in enumerate(range(0, 126, 5)):
                self.emit("progress", message=f"Receive sample {index + 1}/26 · nRF channel {channel}")
                self.request("A", "SET_CONFIG", {"channel": channel}, purpose)
                records.extend(self.observe("nrf", purpose, duration=350))
            # The following packet test explicitly sets its own channel.
            return summarize(action, records)
        if action == "link":
            self.request("A", "SET_CONFIG", {"channel": 76}, purpose)
            return self.request("A", "TRANSMIT", {"test": "nrf_link"}, purpose)
        if action == "coex":
            result = {"note": "Sequential inventories; not simultaneous measurements or proof of interference.", "observations": {}}
            for sensor in ("wifi", "ble", "nrf"):
                self.emit("progress", message=f"Observing {sensor}")
                result[sensor] = self.observe(sensor, purpose)
                result["observations"][sensor] = getattr(result[sensor], "metadata", {})
            return result
        if action == "ip":
            if options.get("host"):
                return self.inspect_host(options["host"])
            return self.network_scan(options.get("target", ""))
        if action == "pi_wifi":
            return {"source": "Pi NetworkManager", "access_points": [asdict(ap) for ap in asyncio.run(discover_wifi())]}
        if action == "dependencies":
            return {"checks": dependencies(self.config_path)}
        if action == "pair":
            if options.get("auto"):
                return self.pair_all()
            if options.get("forget"):
                return self.unpair(options.get("role", "A"))
            return self.pair(options.get("role", "A"), options["port"])
        if action == "logs":
            return {"events": self.store.events(after=max(0, self.store.latest_id() - 100), limit=100)}
        if action in {"overview", "about"}:
            return {"nodes": self.state(), "configuration": str(self.config_path.resolve()),
                    "configuration_error": self.config_error, "python": sys.version.split()[0],
                    "interface": "Native Tk touchscreen", "reports": str(self.output_dir.resolve())}
        raise ValueError("This action is handled by the display.")

    def network_scan(self, target):
        networks = asyncio.run(discover_local_networks())
        validated = validate_target(target, networks)
        self.discovered_hosts = {}
        self.emit("progress", message=f"Discovering {validated}; allow up to three minutes")
        document, warning = self.run_nmap(["-sn", "-PS22,80,443,445,3389", "--max-rate", "20",
                                          "--max-retries", "1", "--host-timeout", "15s", str(validated)])
        completed_run(document)
        assets = [a.to_dict() for a in parse_nmap_xml(document)]
        assets.sort(key=lambda a: ipaddress.ip_address(a["ip"]))
        interfaces = [n for n in networks if validated.subnet_of(ipaddress.ip_network(n.network))]
        warnings = [warning] if warning else []
        if sys.platform == "linux":
            try:
                neighbors = asyncio.run(run_command("ip", "-j", "neigh", "show", timeout=3))
                add_neighbor_macs(assets, neighbors, {n.interface for n in interfaces})
            except (OSError, RuntimeError, ValueError) as exc:
                warnings.append(f"MAC lookup unavailable: {exc}")
        self.discovered_hosts = {a["ip"]: a for a in assets}
        return {"scan": "discovery", "target": str(validated), "source": "Pi Nmap host discovery",
                "interfaces": [n.to_dict() for n in interfaces], "assets": assets, "warnings": warnings,
                "note": "Only responding hosts are listed. Firewalls, sleep and Wi-Fi client isolation can hide devices. "
                        "Names require reverse DNS; MAC/vendor may be unavailable. Ports are checked separately."}

    def inspect_host(self, host):
        if host not in self.discovered_hosts:
            raise ValueError("Choose a host from the latest IP scan first.")
        validate_target(host + "/32", asyncio.run(discover_local_networks()))
        self.emit("progress", message=f"Checking 20 common TCP ports on {host}; allow up to a minute")
        document, warning = self.run_nmap(["-sT", "-Pn", "-n", "--top-ports", "20", "-sV", "--version-light",
                                          "--max-rate", "10", "--max-retries", "1", "--host-timeout", "45s", host], 60)
        result = port_result(document, self.discovered_hosts[host])
        if warning:
            result["warnings"].append(warning)
        return result

    def run_nmap(self, arguments, timeout=180):
        binary = find_nmap()
        if not binary:
            raise ValueError("Nmap is missing. Install on the Pi: sudo apt install nmap")
        process = subprocess.Popen([binary, *arguments[:-1], "-oX", "-", arguments[-1]],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + timeout
            while True:
                self._check_cancelled()
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Nmap exceeded {timeout} seconds. Scan incomplete; try a smaller target or check the connection.")
                try:
                    stdout, stderr = process.communicate(timeout=.2)
                    break
                except subprocess.TimeoutExpired:
                    pass
            if process.returncode:
                raise RuntimeError(stderr.decode(errors="replace")[:1000] or "Nmap failed")
            return stdout.decode(errors="replace"), stderr.decode(errors="replace").strip()[:1000]
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()

    def pair(self, role, port):
        if role not in {"A", "B", "C"}:
            raise ValueError("Choose role A, B or C")
        if not port or not port.strip():
            raise ValueError("Select a USB port first, then tap Connect.")
        current = load_config(self.config_path) if self.config_path.exists() else []
        if any(c.node != role and port_key(c.port) == port_key(port) for c in current):
            raise ValueError("This USB port is already assigned to another ESP. Select its own port.")
        self.emit("progress", message=f"Identifying ESP-{role}; USB connections are paused briefly...")
        self.manager.stop()
        try:
            self._check_cancelled()
            result = subprocess.run([sys.executable, "-m", "pi_ot_probe.peripherals.provision",
                                     "--node", role, "--port", port],
                                    capture_output=True, text=True, timeout=12)
            if result.returncode:
                raise ValueError((result.stdout + result.stderr).strip()[-600:])
            identified = NodeConfig.model_validate(json.loads(result.stdout))
            if identified.node != role or port_key(identified.port) != port_key(port):
                raise ValueError("USB identity result does not match the selected role and port")
            current = [c for c in current if c.node != role] + [identified]
            self._check_cancelled()
            self.save_configuration(current)
            return identified.model_dump()
        finally:
            if not self.closing.is_set():
                self.manager.start()

    def pair_all(self):
        """Identify USB boards concurrently, retaining disconnected assignments."""
        ports = serial_ports()
        if not ports:
            raise ValueError("No USB serial boards detected. Plug in an ESP with a data cable and try again.")
        current = load_config(self.config_path) if self.config_path.exists() else []
        self.emit("progress", message="Finding ESPs... USB connections pause briefly.")
        self.manager.stop()

        def probe(port):
            result = subprocess.run([sys.executable, "-m", "pi_ot_probe.peripherals.provision",
                                     "--node", "auto", "--port", port],
                                    capture_output=True, text=True, timeout=15)
            if result.returncode:
                try:
                    detail = json.loads(result.stdout)["error"]
                except (ValueError, KeyError):
                    detail = (result.stdout + result.stderr).strip()[-400:]
                raise ValueError(detail)
            config = NodeConfig.model_validate(json.loads(result.stdout))
            if port_key(config.port) != port_key(port):
                raise ValueError("Identified USB port does not match the selected port")
            return config

        try:
            self._check_cancelled()
            found, errors = [], []
            with ThreadPoolExecutor(max_workers=3) as executor:
                pending = {executor.submit(probe, p["port"]): p["port"] for p in ports}
                for future in as_completed(pending):
                    self._check_cancelled()
                    try:
                        found.append(future.result())
                    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
                        errors.append(f"{pending[future]}: {exc}")
            if not found:
                raise ValueError("No ESP identified. " + "\n".join(errors))
            validate_configs(found)
            roles = {c.node for c in found}
            combined = [c for c in current if c.node not in roles] + sorted(found, key=lambda c: c.node)
            try:
                validate_configs(combined)
            except ValueError as exc:
                raise ValueError("A saved board has a conflicting USB assignment. Reconnect all boards and retry, "
                                 "or forget the old assignment in Choose ESP manually.") from exc
            self._check_cancelled()
            self.save_configuration(combined)
            return {"connected": [c.model_dump() for c in found], "unidentified": errors}
        finally:
            if not self.closing.is_set():
                self.manager.start()

    def unpair(self, role):
        """Forget a port assignment, retaining reports, USB evidence and other roles."""
        current = load_config(self.config_path) if self.config_path.exists() else []
        if role not in {c.node for c in current}:
            raise ValueError(f"ESP-{role} has no saved setup")
        self.manager.stop()
        try:
            self._check_cancelled()
            self.save_configuration([c for c in current if c.node != role])
            return {"node": role, "unconfigured": True}
        finally:
            if not self.closing.is_set():
                self.manager.start()

    def save_configuration(self, configs):
        """Called with USB workers stopped, before reconnecting the saved roles."""
        configs = validate_configs(configs)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        if self.config_path.exists():
            self.config_path.with_suffix(".json.bak").write_bytes(self.config_path.read_bytes())
        temporary = self.config_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps([c.model_dump() for c in configs], indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.config_path)
        self.manager = self.manager_factory(configs, self.store)
        self.config_error = ""

    def save_report(self, value):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
        path.write_text(json.dumps(value, indent=2, default=str) + "\n", encoding="utf-8")
        return path

    def stop(self):
        with self.command_lock:
            self.cancelled.set()
            for state in self.state():
                if state["connection"] == "online":
                    try:
                        self.manager.command(state["node"], Command(command="STOP"))
                    except ValueError:
                        logger.debug("ESP-%s went offline before STOP", state["node"], exc_info=True)

    def stop_async(self):
        # Serial/evidence locks must not block the Tk thread or GPIO polling.
        self.cancelled.set()
        if getattr(self, "_stop_thread", None) is None or not self._stop_thread.is_alive():
            self._stop_thread = threading.Thread(target=self.stop, name="tablet-stop", daemon=True)
            self._stop_thread.start()

    def close(self):
        if self.closing.is_set():
            return
        self.closing.set()
        self.stop()
        if self.thread:
            self.thread.join(timeout=15)
        self.manager.stop()
