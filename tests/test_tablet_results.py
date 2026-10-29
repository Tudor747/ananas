"""Result accuracy and scan failures; all network/USB inputs are fixtures."""
import json
from pathlib import Path
import subprocess

import pytest

from pi_ot_probe.collectors.interfaces import LocalNetwork
from pi_ot_probe.tablet.backend import Observation, summarize
from pi_ot_probe.tablet.network_results import add_neighbor_macs, completed_run, port_result
from pi_ot_probe.tablet.presentation import format_result
from tests.test_tablet import native, messages
from tests.test_peripherals import wait_until


def finished(hosts=""):
    return f'<nmaprun>{hosts}<runstats><finished exit="success"/></runstats></nmaprun>'


def test_wifi_details_sorted_unique_and_limit_visible():
    rows = Observation([
        {"ssid": "near", "bssid": "a", "rssi_dbm": -50, "channel": 6, "security": "WPA2-PSK", "band": "2.4 GHz"},
        {"ssid": "far", "bssid": "b", "rssi_dbm": -85, "channel": 1},
        {"ssid": "near", "bssid": "a", "rssi_dbm": -45, "channel": 6, "security": "WPA2-PSK", "band": "2.4 GHz"},
    ], {"truncated": True, "reported": 64, "total_found": 70, "result_limit": 64})
    result = summarize("wifi", rows)
    text = format_result(result)
    assert result["count"] == 2 and result["records"][0]["rssi_dbm"] == -45
    assert "WPA2-PSK" in text and "BSSID: a" in text and "Channel: 6" in text
    assert "64 of 70" in text
    assert "not reported (update ESP-A firmware)" in text


@pytest.mark.parametrize("kind, hint", [("wifi", "2.4 GHz"), ("ir", "remote"), ("ble", "Classic Bluetooth"), ("rfid", "tag")])
def test_empty_results_explain_scope_and_next_step(kind, hint):
    text = format_result(summarize(kind, []))
    assert "No observations received" in text and hint in text


def test_partial_samples_are_saved_when_scan_fails(native, monkeypatch):
    app, _ = native
    def execute(*args, **kwargs):
        app._local.samples.append({"ssid": "received before failure", "rssi_dbm": -55})
        raise OSError("USB disconnected")
    monkeypatch.setattr(app, "execute", execute)
    app.start("wifi", authorized=True)
    wait_until(lambda: not app.busy)
    error = next(m for m in messages(app) if m["kind"] == "error")
    saved = json.loads(Path(error["path"]).read_text())
    assert saved["status"] == "error"
    text = format_result(error["result"])
    assert "SCAN FAILED" in text and "USB disconnected" in text and "received before failure" in text
    assert not any(p["kind"] == "done" for p in messages(app))


def test_ip_discovery_requests_names_and_explains_missing_data(native, monkeypatch):
    app, _ = native
    async def networks():
        return [LocalNetwork("eth0", "192.168.1.2", "192.168.1.0/24", "192.168.1.0/24")]
    monkeypatch.setattr("pi_ot_probe.tablet.backend.discover_local_networks", networks)
    captured = []
    def scan(args):
        captured.extend(args)
        return finished('<host><status state="up" reason="syn-ack"/>'
                        '<address addrtype="ipv4" addr="192.168.1.10"/>'
                        '<hostnames><hostname name="printer.lan" type="PTR"/></hostnames></host>'), ""
    monkeypatch.setattr(app, "run_nmap", scan)
    result = app.network_scan("192.168.1.0/24")
    assert "-n" not in captured and "-sn" in captured
    text = format_result(result)
    assert "printer.lan" in text and "Pi eth0: 192.168.1.2" in text and "MAC: not observed" in text
    assert "192.168.1.10" in app.discovered_hosts


def test_neighbor_cache_only_enriches_detected_hosts_on_selected_interface():
    assets = [{"ip": "192.168.1.10"}, {"ip": "192.168.1.11"}]
    add_neighbor_macs(assets, json.dumps([
        {"dst": "192.168.1.10", "dev": "eth0", "lladdr": "aa:bb:cc:dd:ee:ff", "state": ["STALE"]},
        {"dst": "192.168.1.11", "dev": "other", "lladdr": "aa:bb:cc:dd:ee:00", "state": ["REACHABLE"]},
        {"dst": "192.168.1.12", "dev": "eth0", "lladdr": "aa:bb:cc:dd:ee:01", "state": ["REACHABLE"]},
    ]), {"eth0"})
    assert len(assets) == 2 and assets[0]["mac"] == "AA:BB:CC:DD:EE:FF"
    assert assets[0]["mac_source"] == "Pi neighbor cache"
    assert "mac" not in assets[1]


def test_port_check_keeps_states_and_distinguishes_guessed_service():
    document = finished('<host><address addrtype="ipv4" addr="192.168.1.10"/><ports>'
                        '<extraports state="closed" count="18"/>'
                        '<port protocol="tcp" portid="22"><state state="open" reason="syn-ack"/>'
                        '<service name="ssh" method="probed" product="OpenSSH" version="9.2"/></port>'
                        '<port protocol="tcp" portid="443"><state state="filtered" reason="no-response"/>'
                        '<service name="https" method="table"/></port></ports></host>')
    result = port_result(document, {"ip": "192.168.1.10"})
    text = format_result(result)
    assert result["port_states"] == {"closed": 18, "open": 1, "filtered": 1}
    assert "OpenSSH 9.2" in text and "not verified" in text and "443: filtered" in text
    assert not result.get("incomplete")


def test_timeout_and_empty_nmap_output_are_not_clean_closed_results():
    result = port_result(finished(), {"ip": "192.168.1.10"})
    assert result["incomplete"] and "not proof" in format_result(result)
    with pytest.raises(RuntimeError, match="completion"):
        completed_run("<nmaprun/>")
    with pytest.raises(RuntimeError, match="incomplete"):
        completed_run("<nmaprun>")


def test_inspection_only_targets_a_recently_discovered_local_host(native, monkeypatch):
    app, _ = native
    monkeypatch.setattr(app, "run_nmap", lambda *a: pytest.fail("must not scan"))
    with pytest.raises(ValueError, match="latest IP scan"):
        app.inspect_host("8.8.8.8")
    app.discovered_hosts = {"192.168.1.10": {"ip": "192.168.1.10"}}
    async def networks(): return []
    monkeypatch.setattr("pi_ot_probe.tablet.backend.discover_local_networks", networks)
    with pytest.raises(ValueError, match="active local"):
        app.inspect_host("192.168.1.10")


def test_inspect_command_is_bounded_and_uses_connect_scan(native, monkeypatch):
    app, _ = native
    app.discovered_hosts = {"192.168.1.10": {"ip": "192.168.1.10"}}
    async def networks():
        return [LocalNetwork("eth0", "192.168.1.2", "192.168.1.0/24", "192.168.1.0/24")]
    monkeypatch.setattr("pi_ot_probe.tablet.backend.discover_local_networks", networks)
    def run(args, timeout):
        assert args[-1] == "192.168.1.10" and timeout == 60
        assert "-sT" in args and "-sV" in args and "--version-light" in args
        assert args[args.index("--top-ports") + 1] == "20"
        return finished(), ""
    monkeypatch.setattr(app, "run_nmap", run)
    assert app.inspect_host("192.168.1.10")["incomplete"]
