"""Wi-Fi presentation data adapted from BWifiKiller's scanner/channel/radar views.

Signal bars and the 4 dB trend threshold follow BWifiKiller/src/wifiscan.cpp,
wifi_channel_scan.cpp and wifi_radar.cpp (MIT, Copyright (c) 2026 PepeAngell;
see BWifiKiller/LICENSE). Keep every BSSID when several radios share an SSID.
"""
from collections import Counter


def signal_dbm(row):
    value = row.get("rssi_dbm")
    if value is None and row.get("signal_percent") is not None:
        value = row.get("signal_dbm")
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def signal_bars(row):
    value = signal_dbm(row)
    return 0 if value is None else 4 if value > -55 else 3 if value > -70 else 2 if value > -85 else 1


def signal_label(row):
    value = signal_dbm(row)
    if value is None:
        return "RSSI not reported"
    return f"{'~' if row.get('rssi_dbm') is None else ''}{value:g} dBm"


def security(row):
    return row.get("security") or row.get("authentication") or row.get("encryption") or "Not reported"


def hidden(row):
    return row.get("hidden", not row.get("ssid") or row["ssid"] == "<hidden>")


def unique_aps(records):
    """One strongest observation per radio, never merge different hidden/shared SSIDs."""
    unique = {}
    for index, record in enumerate(records):
        if "ssid" not in record and "bssid" not in record:
            continue
        row = dict(record)
        identity = str(row.get("bssid") or f"missing:{index}").casefold()
        old = unique.get(identity)
        strength = signal_dbm(row)
        previous = signal_dbm(old) if old else None
        if old is None or (strength is not None and (previous is None or strength >= previous)):
            unique[identity] = row
    return sorted(unique.values(), key=lambda r: (-(signal_dbm(r) if signal_dbm(r) is not None else -999),
                                                  str(r.get("ssid", "")).casefold(), str(r.get("bssid", ""))))


def channel_summary(records):
    rows = unique_aps(records)
    counts = Counter(r["channel"] for r in rows if isinstance(r.get("channel"), int) and r["channel"] > 0)
    return dict(sorted(counts.items()))


def ap_details(row):
    band = row.get("band")
    channel = row.get("channel")
    frequency = row.get("frequency_mhz")
    derived = False
    if frequency is None and band == "2.4 GHz" and isinstance(channel, int) and 1 <= channel <= 14:
        frequency = 2484 if channel == 14 else 2407 + channel * 5
        derived = True
    lines = [("SSID", row.get("ssid") if not hidden(row) else "Hidden / not broadcast"),
             ("BSSID", row.get("bssid") or "Not reported"),
             ("Signal", signal_label(row)),
             ("Channel", str(channel) if channel else "Not reported"),
             ("Band", band or "Not reported"),
             ("Security", security(row)),
             ("Visibility", "Hidden" if hidden(row) else "Visible")]
    if row.get("signal_percent") is not None:
        lines.append(("Signal quality", f"{row['signal_percent']}% reported; dBm estimated"))
    if frequency:
        lines.append(("Frequency", f"{frequency} MHz" + (" (from channel)" if derived else "")))
    for key, label in (("cipher", "Cipher"), ("radio_type", "Radio"), ("mode", "Mode"),
                       ("rate", "Rate"), ("network_type", "Network type"), ("source", "Source")):
        if row.get(key):
            lines.append((label, str(row[key])))
    return lines


def track_summary(snapshots, bssid):
    identity = bssid.casefold()
    samples = [next((r for r in unique_aps(rows) if str(r.get("bssid", "")).casefold() == identity), None)
               for rows in snapshots]
    values = [signal_dbm(row) if row else None for row in samples]
    observed = [value for value in values if value is not None]
    latest = values[-1] if values else None
    previous = values[-2] if len(values) > 1 else None
    delta = latest - previous if latest is not None and previous is not None else None
    trend = ("NOT OBSERVED" if latest is None else "FIRST READING" if len(values) == 1 else
             "REACQUIRED" if previous is None else "STRONGER" if delta >= 4 else
             "WEAKER" if delta <= -4 else "STABLE")
    return {"bssid": bssid, "values": values, "current": latest, "delta_db": delta, "trend": trend,
            "minimum": min(observed) if observed else None, "maximum": max(observed) if observed else None,
            "seen": len(observed), "total": len(values), "missed": len(values) - len(observed)}
