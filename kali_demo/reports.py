"""V2 offline JSON and CSV report generation."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any

from pi_ot_probe.core.models import utc_now


def site_report(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "report_version": "1.0",
        "generated_at": utc_now().isoformat(),
        "site": state.get("current_site"),
        "mode": state.get("mode"),
        "summary": state.get("counts", {}),
        "baseline": state.get("baseline"),
        "assets": state.get("assets", []),
        "findings": state.get("findings", []),
        "baseline_changes": state.get("changes", []),
        "wifi_access_points": state.get("access_points", []),
        "recent_scans": state.get("scans", []),
    }


def assets_csv(state: dict[str, Any]) -> str:
    fields = (
        "ip", "mac", "hostname", "vendor", "device_type", "criticality",
        "ports", "services", "protocols", "risk_score", "confidence", "source", "last_seen",
    )
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for asset in state.get("assets", []):
        writer.writerow(asset)
    return output.getvalue()
