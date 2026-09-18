"""Build the dashboard read model from immutable scan observations.

This module contains database reads only. Keeping it separate from FastAPI and
scan execution makes the meaning of "current" data easier to review and test.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from kali_demo.baseline import BaselineManager
from pi_ot_probe.database.repository import Repository


def _json_value(raw: object, default: Any) -> Any:
    """Decode a SQLite JSON field, returning a safe default when it is invalid."""
    if raw is None:
        return default
    try:
        return json.loads(str(raw))
    except (json.JSONDecodeError, TypeError):
        return default


def _current_discovery(connection: sqlite3.Connection) -> sqlite3.Row | None:
    """Return the newest successful discovery across all sites."""
    return connection.execute(
        """SELECT sc.id, sc.rowid AS scan_rowid, sc.site_id, sc.simulation,
            sc.started_at, sc.finished_at, s.name AS site_name
        FROM scans sc
        JOIN sites s ON s.id=sc.site_id
        WHERE sc.level=1 AND sc.status='completed'
        ORDER BY sc.rowid DESC LIMIT 1"""
    ).fetchone()


def _web_observations(
    connection: sqlite3.Connection,
    asset_id: int,
    discovery_finished_at: str | None,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """SELECT id, scheme, host, port, requested_path AS path, status_code,
            status_reason, http_version, headers_json, tls_json, observed_at
        FROM web_observations
        WHERE asset_id=? AND (? IS NULL OR observed_at>=?)
        ORDER BY observed_at DESC LIMIT 10""",
        (asset_id, discovery_finished_at, discovery_finished_at),
    ).fetchall()
    observations = [dict(row) for row in rows]
    for observation in observations:
        observation["headers"] = _json_value(observation.pop("headers_json"), [])
        observation["tls"] = _json_value(observation.pop("tls_json"), None)
    return observations


def _latest_verification(
    connection: sqlite3.Connection,
    asset_id: int,
    site_id: int,
    discovery_rowid: int,
) -> tuple[dict[str, Any], str | None]:
    row = connection.execute(
        """SELECT sa.snapshot_json, sa.observed_at
        FROM scan_assets sa
        JOIN scans sc ON sc.id=sa.scan_id
        WHERE sa.asset_id=? AND sc.site_id=? AND sc.level=2
            AND sc.status='completed' AND sc.rowid>?
        ORDER BY sc.rowid DESC LIMIT 1""",
        (asset_id, site_id, discovery_rowid),
    ).fetchone()
    if not row:
        return {}, None
    return _json_value(row["snapshot_json"], {}), row["observed_at"]


def _assets(
    connection: sqlite3.Connection,
    discovery: sqlite3.Row,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """SELECT a.id, a.ip, a.mac, a.hostname, a.vendor, a.source,
            a.status, a.discovery_reason, a.hostnames_json,
            a.first_seen, a.last_seen, sa.snapshot_json
        FROM assets a
        JOIN scan_assets sa ON sa.asset_id=a.id
        WHERE a.site_id=? AND sa.scan_id=?
        ORDER BY a.ip""",
        (discovery["site_id"], discovery["id"]),
    ).fetchall()

    assets: list[dict[str, Any]] = []
    for row in rows:
        asset = dict(row)
        snapshot = _json_value(asset.pop("snapshot_json"), {})
        for field in (
            "ip", "mac", "hostname", "vendor", "source", "status",
            "discovery_reason", "first_seen", "last_seen",
        ):
            if field in snapshot:
                asset[field] = snapshot[field]
        asset["hostnames"] = snapshot.get(
            "hostnames", _json_value(asset.pop("hostnames_json"), [])
        )

        verified, verified_at = _latest_verification(
            connection,
            int(asset["id"]),
            int(discovery["site_id"]),
            int(discovery["scan_rowid"]),
        )
        asset["ports"] = [
            {
                "port": port,
                "transport": "tcp",
                "state": "open",
                "observed_at": verified_at,
            }
            for port in sorted(set(verified.get("ports", [])))
        ]
        asset["services"] = verified.get("services", [])
        for service in asset["services"]:
            service["observed_at"] = verified_at
        asset["protocols"] = verified.get("protocols", [])
        asset["web_observations"] = _web_observations(
            connection, int(asset["id"]), discovery["finished_at"]
        )
        assets.append(asset)
    return assets


def _changes(connection: sqlite3.Connection, site_id: int) -> list[dict[str, Any]]:
    rows = connection.execute(
        """SELECT id, change_type, asset_identity, details_json, detected_at,
            acknowledged_at, triage_status, analyst_note, updated_at
        FROM changes WHERE site_id=? ORDER BY detected_at DESC LIMIT 100""",
        (site_id,),
    ).fetchall()
    changes = [dict(row) for row in rows]
    for change in changes:
        details = _json_value(change.pop("details_json"), {})
        change["summary"] = details.get("summary", "")
        change["details"] = details
    return changes


def _access_points(connection: sqlite3.Connection, site_id: int) -> list[dict[str, Any]]:
    rows = connection.execute(
        """SELECT ssid, bssid, signal_dbm AS signal_dbm_estimated,
            signal_percent, channel, frequency_mhz, band, authentication,
            encryption, cipher, radio_type, network_type, mode, rate, source,
            first_seen, last_seen
        FROM wifi_access_points WHERE site_id=?
        ORDER BY last_seen DESC, signal_dbm DESC""",
        (site_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _scans(connection: sqlite3.Connection, site_id: int) -> list[dict[str, Any]]:
    rows = connection.execute(
        """SELECT id, status, target, level, assets_found, started_at,
            finished_at, cancelled, error
        FROM scans WHERE site_id=? ORDER BY rowid DESC LIMIT 25""",
        (site_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def build_dashboard_state(
    repository: Repository,
    baselines: BaselineManager,
    operation: dict[str, object],
) -> dict[str, object]:
    """Return the complete, score-free state consumed by the browser UI."""
    repository.initialize()
    with repository.connect() as connection:
        discovery = _current_discovery(connection)
        if discovery is None:
            return {
                "mode": "ready",
                "network_traffic": False,
                "current_site": None,
                "counts": {
                    "sites": 0, "scans": 0, "assets": 0,
                    "audit_log": 0, "changes": 0, "access_points": 0,
                },
                "operation": dict(operation),
                "baseline": None,
                "assets": [],
                "changes": [],
                "access_points": [],
                "scans": [],
            }

        site_id = int(discovery["site_id"])
        site_name = str(discovery["site_name"])
        assets = _assets(connection, discovery)
        changes = _changes(connection, site_id)
        access_points = _access_points(connection, site_id)
        scans = _scans(connection, site_id)
        counts = {
            "sites": 1,
            "scans": int(connection.execute(
                "SELECT COUNT(*) FROM scans WHERE site_id=?", (site_id,)
            ).fetchone()[0]),
            "assets": len(assets),
            "audit_log": int(connection.execute(
                "SELECT COUNT(*) FROM audit_log"
            ).fetchone()[0]),
            "changes": len(changes),
            "access_points": len(access_points),
        }

    return {
        "mode": "simulation" if discovery["simulation"] else "real_discovery",
        "network_traffic": not bool(discovery["simulation"]),
        "current_site": site_name,
        "counts": counts,
        "operation": dict(operation),
        "baseline": baselines.status(site_name),
        "assets": assets,
        "changes": changes,
        "access_points": access_points,
        "scans": scans,
    }
