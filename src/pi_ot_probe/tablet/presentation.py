"""Readable device status and results, independent of Tk widgets."""
import json

from .catalog import NODE_NAMES
from .wifi_results import ap_details, track_summary


def connection_summary(states):
    labels = []
    for state in states:
        connection = state["connection"]
        label = {"unconfigured": "setup", "connecting": "linking"}.get(connection, connection)
        if connection == "online":
            label = "HW error" if state.get("health") == "error" else state.get("health", "online")
        labels.append(f"{state['node']}: {label}")
    return "  |  ".join(labels)


def describe_node(state):
    role = state["node"]
    connection = state["connection"]
    lines = [f"ESP-{role} · {NODE_NAMES[role]}"]
    if connection == "online":
        lines.append(f"USB connected · hardware {state.get('health', 'unknown')}")
        if state.get("health") == "error":
            lines.append("A peripheral failed its check. Other sensors may still work.")
    elif connection == "unconfigured":
        lines.append("Not set up yet. Open USB Setup and choose this role.")
    else:
        lines.append(f"USB {connection}. Check the cable and close other serial apps; reconnect is automatic.")
    for key, label in (("port", "Port"), ("device", "Device"), ("firmware", "Firmware"), ("error", "Last error")):
        if state.get(key):
            lines.append(f"{label}: {state[key]}")
    return "\n".join(lines)


def pretty_record(row):
    if "ssid" in row:
        details = ap_details(row)
        if not any(row.get(k) for k in ("security", "authentication", "encryption")):
            details = [(label, "not reported (update ESP-A firmware)" if label == "Security" else value)
                       for label, value in details]
        return str(details[0][1]) + "\n" + "\n".join(f"  {label}: {value}" for label, value in details[1:])
    if "address" in row and "rssi_dbm" in row:
        return f"{row.get('name') or 'Unnamed BLE device'}\n  {row['rssi_dbm']} dBm · {row['address']}"
    if "nrf1_carrier" in row:
        return f"nRF channel {row.get('channel')} · radio 1: {bool(row['nrf1_carrier'])} · radio 2: {bool(row.get('nrf2_carrier'))}"
    if row.get("sensor") == "ir":
        return (f"IR: {row.get('protocol', 'Unknown protocol')} / {row.get('bits', '?')} bits\n"
                f"  Code (hex): {row.get('value_hex', 'not decoded')}\n"
                f"  Repeat: {bool(row.get('repeat'))} / buffer overflow: {bool(row.get('overflow'))}")
    if row.get("sensor") == "rfid":
        return f"RFID tag: {row.get('tag_family', 'unknown family')}\n  UID: {row.get('uid', 'not reported')} ({row.get('uid_bytes', '?')} bytes)"
    if row.get("sensor") == "cc1101":
        if "packet_valid" in row:
            return f"433 MHz packet: {'valid' if row['packet_valid'] else 'invalid'} / {row.get('packet_bytes', '?')} bytes\n  {row.get('profile', '')}"
        return f"{row.get('frequency_mhz', 433.92)} MHz / RSSI: {row.get('rssi_dbm', '?')} dBm"
    return json.dumps(row, ensure_ascii=False, default=str)


def observation_notes(result):
    metadata = result.get("observation", {})
    if metadata.get("truncated"):
        return f"\n\nPARTIAL INVENTORY: firmware returned {metadata.get('reported', '?')} of {metadata.get('total_found', '?')} observations (limit {metadata.get('result_limit', '?')})."
    if "total_found" in metadata:
        return f"\n\nFirmware reported {metadata['total_found']} observations in this scan."
    if result.get("kind") in {"wifi", "ble"}:
        return "\n\nOlder firmware did not report a total count; additional results may have been capped."
    return ""


def host_details(asset):
    return (f"{asset['ip']} / {asset.get('hostname') or 'no DNS name'}\n"
            f"  MAC: {asset.get('mac') or 'not observed'}"
            + (f" ({asset['mac_source']})" if asset.get("mac_source") else "") +
            f"\n  Vendor: {asset.get('vendor') or 'not identified'}\n"
            f"  Response: {asset.get('discovery_reason') or 'not reported'}")


def format_result(result):
    if result.get("status") in {"error", "cancelled"}:
        text = ("SCAN FAILED" if result["status"] == "error" else "SCAN STOPPED") + " - incomplete results\n\n" + result["error"]
        rows = result.get("records", [])
        return text + f"\n\n{len(rows)} samples received before stopping:\n" + ("\n\n".join(map(pretty_record, rows)) or "No samples received.")
    if result.get("scan") == "ports":
        counts = result["port_states"]
        lines = [host_details(result["host"]), result["scope"],
                 "States: " + (", ".join(f"{count} {state}" for state, count in counts.items()) or "none reported")]
        for row in result["ports"]:
            service = row["service"]
            name = service.get("name", "unknown service")
            evidence = "identified by probe" if service.get("method") == "probed" else "port-name hint; not verified"
            details = " ".join(str(service[k]) for k in ("product", "version", "extrainfo") if service.get(k))
            lines.append(f"TCP {row['port']}: {row['state']} / {name}\n  {evidence}" + (f"\n  {details}" if details else ""))
        lines.extend(result.get("warnings", []))
        lines.append("Only these 20 TCP ports were checked. UDP and OS identification are not included.")
        return "\n\n".join(lines)
    if result.get("unconfigured"):
        return f"ESP-{result['node']} setup forgotten. Choose its current USB port and tap Connect."
    if "nodes" in result:
        text = "\n\n".join(describe_node(s) for s in result["nodes"])
        if result.get("configuration_error"):
            text += f"\n\nConfiguration error: {result['configuration_error']}"
        for key, label in (("configuration", "Configuration"), ("reports", "Reports"),
                           ("python", "Python"), ("screen_pixels", "Screen"),
                           ("window_pixels", "Window"), ("available_tools", "Available tools")):
            if key in result:
                text += f"\n\n{label}: {result[key]}"
        return text
    if "node" in result and "device" in result:
        return (f"ESP-{result['node']} saved. Waiting for USB to reconnect.\n\n"
                f"Port: {result['port']}\nDevice: {result['device']}\n\n"
                "To add another board, select its role and USB port, then tap Connect.")
    if "events" in result:
        return "\n\n".join(
            f"{e['received_at']} · ESP-{e['node']} · {e['kind']}\n"
            f"{json.dumps(e['data'], ensure_ascii=False)}" for e in result["events"]
        ) or "No USB events recorded yet."
    if "checks" in result:
        return "\n\n".join(f"{'OK' if c['ok'] else 'MISSING'} · {c['name']}\n{c['detail']}" for c in result["checks"])
    if "target_bssid" in result:
        track = track_summary(result.get("snapshots", []), result["target_bssid"])
        current = f"{track['current']} dBm" if track["current"] is not None else "Not observed"
        span = f"{track['minimum']} to {track['maximum']} dBm" if track["minimum"] is not None else "No readings"
        return (f"Target: {track['bssid']}\n{track['trend']}\n"
                f"Current: {current}\nSeen: {track['seen']}/{track['total']} scans\n"
                f"Range: {span}\n\n" + result.get("note", ""))
    if "access_points_per_channel" in result:
        counts = "\n".join(f"Channel {ch}: {n} AP(s)" for ch, n in result["access_points_per_channel"].items())
        return "Observed access points by channel\n\n" + (counts or "No access points observed") + "\n\n" + result["note"] + observation_notes(result) + "\n\n" + "\n\n".join(map(pretty_record, result.get("records", [])))
    if "records" in result:
        rows, kind = result["records"], result.get("kind", "")
        notes = {"wifi": "ESP-A: 2.4 GHz access points. Connected clients and their IPs are not collected.",
                 "ble": "BLE advertisements only. Classic Bluetooth devices and silent devices may not appear.",
                 "ir": "Point a remote at the IR receiver and press a button during the 10-second scan.",
                 "rfid": "Present a compatible tag during the 10-second scan; remove and re-present it for another reading. UID is redacted by firmware.",
                 "cc1101": "433.92 MHz RSSI. Packet reception requires the matching FSK profile; arbitrary remotes may not decode.",
                 "nrf": "Carrier threshold only; no signal strength, packets, or network identities are decoded."}
        text = f"{len(rows)} observations\n\n" + ("\n\n".join(map(pretty_record, rows)) or
                "No observations received. This does not prove that no devices are present.")
        if kind in notes:
            text += "\n\n" + notes[kind]
        return text + observation_notes(result)
    if "assets" in result:
        interface = "\n".join(f"Pi {n['interface']}: {n['address']}" for n in result.get("interfaces", []))
        return (f"{result['target']} / {len(result['assets'])} responding hosts\n{interface}\n\n" +
                ("\n\n".join(map(host_details, result["assets"])) or
                 "No hosts responded. Check the selected subnet and Pi connection; sleeping or filtered devices can be missed.") +
                "\n\n" + result.get("note", "Ports were not checked by host discovery.") +
                "\n\n" + "\n".join(result.get("warnings", [])))
    if "access_points" in result:
        rows = result["access_points"]
        return f"{result.get('source', 'Pi Wi-Fi')}: {len(rows)} access points\n\n" + ("\n\n".join(map(pretty_record, rows)) or
                "No access points returned. Check Wi-Fi is enabled and managed by NetworkManager.")
    if all(key in result for key in ("wifi", "ble", "nrf")):
        return result["note"] + "\n\n" + "\n\n".join(
            key.upper() + "\n" + ("\n\n".join(map(pretty_record, result[key])) or "No observations") +
            observation_notes({"kind": key, "observation": result.get("observations", {}).get(key, {})})
            for key in ("wifi", "ble", "nrf"))
    if "snapshots" in result:
        metadata = result.get("observations", [{}] * len(result["snapshots"]))
        return "\n\n".join(f"Snapshot {i + 1}\n" + ("\n".join(pretty_record(r) for r in rows) or "No observations")
                             + observation_notes({"kind": result.get("kind"), "observation": metadata[i]})
                             for i, rows in enumerate(result["snapshots"])) + "\n\n" + result.get("note", "")
    if "tx_completed" in result:
        return (f"Transmit completed: {result['tx_completed']}\nMatching packet received: {result.get('matching_packet_received')}\n"
                "Transmission alone does not prove reception.")
    if "devices_per_rssi_bin_dbm" in result:
        return "Bluetooth signal distribution\n\n" + ("\n".join(
            f"{low} to {int(low) + 9} dBm: {count} device(s)"
            for low, count in result["devices_per_rssi_bin_dbm"].items()) or "No BLE devices observed") + observation_notes(result)
    if "sampled_channels" in result:
        return "\n".join(f"Channel {r['channel']}: {r['hit_fraction']:.0%} hits ({r['samples']} samples per radio)"
                         for r in result["sampled_channels"]) + "\n\n" + result["note"]
    if "baseline_created" in result:
        return (("First snapshot saved." if result["baseline_created"] else "Compared with the previous snapshot.") +
                f"\nObserved now: {len(result['currently_observed'])}\n"
                f"Newly observed: {', '.join(result['newly_observed']) or 'none'}\n"
                f"Not observed this time: {', '.join(result['not_observed_this_time']) or 'none'}\n\n" + result["note"] +
                "\n\n" + "\n\n".join(map(pretty_record, result["currently_observed"])) + observation_notes(result))
    return json.dumps(result, indent=2, ensure_ascii=False, default=str)


