"""Readable device status and results, independent of Tk widgets."""
import json

from .catalog import NODE_NAMES


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
        return f"{row.get('ssid') or '(hidden SSID)'}\n  {row.get('rssi_dbm', '?')} dBm · channel {row.get('channel', '?')} · {row.get('bssid', '')}"
    if "address" in row and "rssi_dbm" in row:
        return f"{row.get('name') or 'Unnamed BLE device'}\n  {row['rssi_dbm']} dBm · {row['address']}"
    if "nrf1_carrier" in row:
        return f"nRF channel {row.get('channel')} · radio 1: {bool(row['nrf1_carrier'])} · radio 2: {bool(row.get('nrf2_carrier'))}"
    return json.dumps(row, ensure_ascii=False, default=str)


def format_result(result):
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
    if "records" in result:
        return "\n\n".join(pretty_record(r) for r in result["records"]) or "Observation completed. No samples were reported."
    if "assets" in result:
        return (f"{result['target']} · {len(result['assets'])} hosts\n\n" +
                "\n\n".join(f"{a['ip']} · {a.get('hostname') or 'unnamed'}\n{a.get('mac') or 'MAC not observed'}" for a in result["assets"]))
    if "snapshots" in result:
        return "\n\n".join(f"Snapshot {i + 1}\n" + ("\n".join(pretty_record(r) for r in rows) or "No observations")
                             for i, rows in enumerate(result["snapshots"]))
    if "tx_completed" in result:
        return (f"Transmit completed: {result['tx_completed']}\nMatching packet received: {result.get('matching_packet_received')}\n"
                "Transmission alone does not prove reception.")
    if "access_points_per_channel" in result:
        return "Observed access points by channel\n\n" + ("\n".join(
            f"Channel {channel}: {count} AP(s)" for channel, count in result["access_points_per_channel"].items())
            or "No access points observed") + "\n\n" + result["note"]
    if "devices_per_rssi_bin_dbm" in result:
        return "Bluetooth signal distribution\n\n" + ("\n".join(
            f"{low} to {int(low) + 9} dBm: {count} device(s)"
            for low, count in result["devices_per_rssi_bin_dbm"].items()) or "No BLE devices observed")
    if "sampled_channels" in result:
        return "\n".join(f"Channel {r['channel']}: {r['hit_fraction']:.0%} hits ({r['samples']} samples per radio)"
                         for r in result["sampled_channels"]) + "\n\n" + result["note"]
    if "baseline_created" in result:
        return (("First snapshot saved." if result["baseline_created"] else "Compared with the previous snapshot.") +
                f"\nObserved now: {len(result['currently_observed'])}\n"
                f"Newly observed: {', '.join(result['newly_observed']) or 'none'}\n"
                f"Not observed this time: {', '.join(result['not_observed_this_time']) or 'none'}\n\n" + result["note"])
    return json.dumps(result, indent=2, ensure_ascii=False, default=str)


