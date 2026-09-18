"""Offline raw-observation JSON and CSV report generation."""

from __future__ import annotations

import csv
from io import StringIO
import json
from typing import Any

from pi_ot_probe.core.models import utc_now


def site_report(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "report_version": "2.0",
        "generated_at": utc_now().isoformat(),
        "site": state.get("current_site"),
        "mode": state.get("mode"),
        "observation_counts": state.get("counts", {}),
        "baseline": state.get("baseline"),
        "assets": state.get("assets", []),
        "baseline_changes": state.get("changes", []),
        "wifi_access_points": state.get("access_points", []),
        "recent_scans": state.get("scans", []),
    }


def assets_csv(state: dict[str, Any]) -> str:
    fields = (
        "ip", "mac", "hostname", "vendor", "status", "discovery_reason",
        "hostnames", "ports", "services", "protocols", "source", "first_seen", "last_seen",
    )
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for asset in state.get("assets", []):
        row = dict(asset)
        for field in ("hostnames", "ports", "services", "protocols"):
            row[field] = json.dumps(row.get(field, []), sort_keys=True)
        for field, value in row.items():
            if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
                row[field] = "'" + value
        writer.writerow(row)
    return output.getvalue()
