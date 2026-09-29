"""Reconstruct a current asset from immutable discovery and verification records."""
from datetime import datetime
import json
from pi_ot_probe.domain.models import Asset, Service
from pi_ot_probe.database.repository import Repository


def load_current_asset(
    repository: Repository, host: str, *, include_latest_verification: bool = True
) -> tuple[str, Asset]:
    """Load an asset from the latest successfully completed discovery."""
    repository.initialize()
    with repository.connect() as connection:
        discovery = connection.execute(
            """SELECT sc.id AS scan_id, sc.rowid AS scan_rowid,
                sc.site_id, s.name
            FROM scans sc
            JOIN sites s ON s.id=sc.site_id
            WHERE sc.level=1 AND sc.status='completed'
            ORDER BY sc.rowid DESC LIMIT 1"""
        ).fetchone()
        if not discovery:
            raise ValueError("run host discovery before verifying a device")
        row = connection.execute(
            """SELECT a.*, sa.snapshot_json FROM assets a JOIN scan_assets sa
            ON sa.asset_id=a.id WHERE a.site_id=? AND a.ip=? AND sa.scan_id=?""",
            (discovery["site_id"], host, discovery["scan_id"]),
        ).fetchone()
        if not row:
            raise ValueError("select a device from the current asset inventory")
        try:
            observed = json.loads(row["snapshot_json"] or "{}")
        except (json.JSONDecodeError, TypeError):
            observed = {}
        ports: list[int] = []
        services: list[Service] = []
        if include_latest_verification:
            verification = connection.execute(
                """SELECT sa.snapshot_json FROM scan_assets sa JOIN scans sc
                ON sc.id=sa.scan_id WHERE sa.asset_id=? AND sc.site_id=? AND sc.level=2
                AND sc.status='completed' AND sc.rowid>? ORDER BY sc.rowid DESC LIMIT 1""",
                (row["id"], discovery["site_id"], discovery["scan_rowid"]),
            ).fetchone()
            if verification and verification["snapshot_json"]:
                try:
                    verified = json.loads(verification["snapshot_json"])
                except (json.JSONDecodeError, TypeError):
                    verified = {}
                ports = [int(port) for port in verified.get("ports", [])]
                services = [Service(**item) for item in verified.get("services", [])]
        asset = Asset(
            id=int(row["id"]), ip=observed.get("ip", row["ip"]),
            mac=observed.get("mac", row["mac"]),
            hostname=observed.get("hostname", row["hostname"]),
            vendor=observed.get("vendor", row["vendor"]),
            device_type=observed.get("device_type", row["device_type"]), ports=ports,
            services=services,
            first_seen=datetime.fromisoformat(observed.get("first_seen", row["first_seen"])),
            last_seen=datetime.fromisoformat(observed.get("last_seen", row["last_seen"])),
            risk_score=int(observed.get("risk_score", row["risk_score"])),
            criticality=observed.get("criticality", row["criticality"]),
            confidence=float(observed.get("confidence", row["confidence"])),
            source=observed.get("source", row["source"]),
            status=observed.get("status", row["status"]),
            discovery_reason=observed.get("discovery_reason", row["discovery_reason"]),
            hostnames=observed.get("hostnames", json.loads(row["hostnames_json"] or "[]")),
        )
        return str(discovery["name"]), asset
