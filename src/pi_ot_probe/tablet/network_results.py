"""Interpret completed Nmap output without turning missing evidence into facts."""
from collections import Counter
import json
import re
import xml.etree.ElementTree as ET


def completed_run(document):
    try:
        root = ET.fromstring(document)
    except ET.ParseError as exc:
        raise RuntimeError("Nmap returned incomplete or malformed results; the scan did not complete.") from exc
    if root.tag != "nmaprun":
        raise RuntimeError("Unexpected Nmap output")
    finished = root.find("runstats/finished")
    if finished is None or finished.get("exit") != "success":
        raise RuntimeError("Nmap did not complete successfully: " +
                           (finished.get("errormsg", "missing completion record") if finished is not None else "missing completion record"))
    return root


def add_neighbor_macs(assets, document, interfaces):
    """Enrich already discovered hosts; a cached neighbor is not proof of liveness."""
    rows = json.loads(document)
    if not isinstance(rows, list):
        return
    known = {a["ip"]: a for a in assets}
    for row in rows:
        if not isinstance(row, dict) or row.get("dev") not in interfaces:
            continue
        asset = known.get(row.get("dst"))
        mac = row.get("lladdr", "")
        if (asset is None or asset.get("mac") or not isinstance(mac, str) or
                not re.fullmatch(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", mac)):
            continue
        if set(row.get("state", [])) & {"FAILED", "INCOMPLETE"}:
            continue
        asset["mac"] = mac.upper()
        asset["mac_source"] = "Pi neighbor cache"


def port_result(document, asset):
    root = completed_run(document)
    host = next((h for h in root.findall("host")
                 if any(a.get("addr") == asset["ip"] for a in h.findall("address[@addrtype='ipv4']"))), None)
    result = {"scan": "ports", "host": asset, "ports": [], "port_states": {},
              "scope": "20 most common TCP ports; light service identification", "warnings": []}
    if host is None or host.get("timedout") == "true":
        result["warnings"].append("Host timed out or returned no port results. This is not proof that all ports are closed.")
        result["incomplete"] = True
        return result
    counts = Counter()
    for extra in host.findall("ports/extraports"):
        counts[extra.get("state", "unknown")] += int(extra.get("count", 0))
    for p in host.findall("ports/port"):
        state = p.find("state")
        if p.get("protocol") != "tcp" or state is None:
            continue
        service = p.find("service")
        details = dict(service.attrib) if service is not None else {}
        row = {"port": int(p.get("portid")), "state": state.get("state", "unknown"),
               "reason": state.get("reason", "not reported"), "service": details}
        result["ports"].append(row)
        counts[row["state"]] += 1
    result["port_states"] = dict(counts)
    result["ports"].sort(key=lambda p: (p["state"] != "open", p["port"]))
    if sum(counts.values()) < 20:
        result["incomplete"] = True
        result["warnings"].append(f"Only {sum(counts.values())}/20 port states were reported; the result may be incomplete.")
    return result
