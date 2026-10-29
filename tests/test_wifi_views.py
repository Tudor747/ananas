"""Wi-Fi identity, evidence and real Tk navigation regressions; no live scans."""
from types import SimpleNamespace

import pytest

from pi_ot_probe.tablet.backend import Observation, summarize
from pi_ot_probe.tablet.catalog import BY_KEY
from pi_ot_probe.tablet.wifi_results import ap_details, signal_bars, signal_dbm, track_summary, unique_aps
from tests.test_gpio_navigation import ui
from tests.test_tablet import native, messages


def ap(index=1, **values):
    return {"ssid": "Shared network", "bssid": f"AA:BB:CC:DD:EE:{index:02X}", "channel": 6,
            "rssi_dbm": -48, "security": "WPA2-PSK", "band": "2.4 GHz", **values}


def complete(app, backend, rows, key="wifi", **values):
    app.authorized.set(True)
    app.show_tool(BY_KEY[key])
    app.run_tool()
    backend.busy = False
    backend.messages.put({"kind": "done", "job": backend.job_id, "path": "fixture.json",
                          "result": {**summarize("channels" if key == "channels" else "wifi", rows), **values}})
    app.poll_once()
    app.root.update()
    return app.wifi_view


def test_radio_identity_keeps_shared_and_hidden_ssids_and_strongest_duplicate():
    rows = [ap(rssi_dbm=-80), ap(bssid="aa:bb:cc:dd:ee:01"), ap(2), ap(3, ssid=""), ap(4, ssid="")]
    result = unique_aps(rows)
    assert len(result) == 4 and result[0]["rssi_dbm"] == -48
    assert len([row for row in result if not row["ssid"]]) == 2
    assert len(rows) == 5  # Source observations are preserved.


def test_signal_missing_and_estimated_never_masquerades_as_measured():
    assert signal_dbm({"signal_dbm": -100, "signal_percent": None}) is None
    assert signal_dbm({"rssi_dbm": -61, "signal_percent": None}) == -61
    assert signal_bars(ap(rssi_dbm=-55)) == 3
    details = dict(ap_details({"ssid": "Pi", "signal_dbm": -70, "signal_percent": 60}))
    assert details["Signal"] == "~-70 dBm"
    assert "estimated" in details["Signal quality"]


def test_channels_preserve_ap_details_and_truncation():
    rows = Observation([ap(), ap(2, channel=11), ap(bssid="aa:bb:cc:dd:ee:01")],
                       {"truncated": True, "reported": 64, "total_found": 80})
    result = summarize("channels", rows)
    assert result["access_points_per_channel"] == {6: 1, 11: 1}
    assert len(result["records"]) == 2
    assert result["records"][1]["security"] == "WPA2-PSK"
    assert result["observation"]["truncated"]
    assert dict(ap_details(ap(channel=14)))["Frequency"] == "2484 MHz (from channel)"


def test_radar_tracks_bssid_and_does_not_reuse_missing_or_other_ap_signal():
    snapshots = [[ap()], [ap(2, rssi_dbm=-20)], [ap(rssi_dbm=-40)], [ap(rssi_dbm=-47)]]
    target = ap()["bssid"].lower()
    missing = track_summary(snapshots[:2], target)
    assert missing["current"] is None and missing["trend"] == "NOT OBSERVED"
    assert missing["values"] == [-48, None]
    assert track_summary(snapshots[:3], target)["trend"] == "REACQUIRED"
    final = track_summary(snapshots, target)
    assert final["trend"] == "WEAKER" and final["delta_db"] == -7
    assert final["missed"] == 1 and final["minimum"] == -48


def test_radar_backend_publishes_completed_snapshots_and_counts(native, monkeypatch):
    backend, _ = native
    scans = []
    def observe(sensor, purpose):
        scans.append(sensor)
        return Observation([ap()], {"total_found": 1, "reported": 1})
    monkeypatch.setattr(backend, "observe", observe)
    inventory = backend.execute("radar", "A", "fixture")
    assert inventory["records"][0]["bssid"] == ap()["bssid"] and len(scans) == 1
    result = backend.execute("radar", "A", "fixture", wifi_target=ap()["bssid"])
    updates = [m for m in messages(backend) if m["kind"] == "wifi_snapshot"]
    assert len(updates) == 12 and len(scans) == 13
    assert len(updates[0]["result"]["snapshots"]) == 1
    assert len(result["snapshots"]) == 12 and len(result["observed_at"]) == 12
    with pytest.raises(ValueError, match="valid BSSID"):
        backend.execute("radar", "A", "fixture", wifi_target="invalid")


@pytest.mark.parametrize("size", [(240, 240), (320, 240), (480, 320), (800, 480)])
def test_native_ap_list_details_rescan_and_full_ssid_with_dpad(ui, size):
    app, root, backend = ui
    root.geometry(f"{size[0]}x{size[1]}")
    long_name = "Long network with unicode Ș ț 🚀"
    view = complete(app, backend, [ap(ssid=long_name), ap(2, rssi_dbm=-72)])
    assert view.canvas.winfo_height() >= 48
    app.gpio_navigate("down")
    app.gpio_navigate("ok")
    assert view.mode == "detail" and view.target["bssid"] == ap(2)["bssid"]
    app.gpio_navigate("left")
    app.gpio_navigate("up")
    app.gpio_navigate("ok")
    text = " ".join(view.canvas.itemcget(i, "text") for i in view.canvas.find_all())
    assert long_name in text and ap()["bssid"] in text
    for _ in range(30): app.gpio_navigate("down")
    assert view.offset == view.max_offset
    app.gpio_navigate("left")
    app.gpio_navigate("right")
    assert backend.runs == ["wifi", "wifi"] and view.scanning


def test_channel_drilldown_back_empty_channel_and_touch(ui):
    app, root, backend = ui
    view = complete(app, backend, [ap(), ap(2, channel=11)], "channels")
    app.gpio_navigate("ok")  # Empty channel 1.
    assert view.mode == "list" and not view.choices()
    app.gpio_navigate("left")
    for _ in range(5): app.gpio_navigate("down")
    app.gpio_navigate("ok")
    assert view.channel == 6 and len(view.choices()) == 1
    view.press(SimpleNamespace(y=10))
    view.release(SimpleNamespace(y=10))
    assert view.mode == "detail" and view.target["channel"] == 6
    app.gpio_navigate("left")
    app.gpio_navigate("left")
    assert view.mode == "channels" and view.index == 5


def test_live_radar_keeps_target_and_shows_missing_and_stopped_state(ui):
    app, root, backend = ui
    view = complete(app, backend, [ap(), ap(2)], "radar")
    app.gpio_navigate("ok")
    app.gpio_navigate("ok")
    assert backend.last_options["wifi_target"] == ap()["bssid"] and view.mode == "track"
    result = {"kind": "wifi", "target_bssid": ap()["bssid"], "snapshots": [[ap()], [ap(2)]]}
    backend.messages.put({"kind": "wifi_snapshot", "job": backend.job_id, "result": result})
    app.poll_once()
    text = " ".join(view.canvas.itemcget(i, "text") for i in view.canvas.find_all() if view.canvas.type(i) == "text")
    assert "NOT OBSERVED" in text and view.target["bssid"] == ap()["bssid"]
    app.gpio_navigate("ok")  # Can stop with buttons alone.
    assert not backend.busy
    backend.messages.put({"kind": "cancelled", "job": backend.job_id, "message": "Stopped",
                          "result": {**result, "status": "cancelled", "error": "Stopped"}})
    app.poll_once()
    assert "STOPPED" in view.summary.cget("text")
    app.gpio_navigate("left")
    assert view.mode == "detail"
