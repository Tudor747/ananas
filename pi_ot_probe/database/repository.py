"""Small, explicit SQLite repository for probe state."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import json
from pathlib import Path
import sqlite3
from typing import Iterator

from pi_ot_probe.core.models import Asset, ChangeEvent, Finding, Scan, WifiAccessPoint
from pi_ot_probe.database.models import SCHEMA_STATEMENTS


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class Repository:
    """Persistence boundary; each operation owns a short transaction."""

    def __init__(self, database_path: Path | str) -> None:
        self.database_path = Path(database_path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            for statement in SCHEMA_STATEMENTS:
                connection.execute(statement)

    def ensure_site(self, name: str, now: datetime) -> int:
        normalized = name.strip()
        if not normalized or len(normalized) > 100:
            raise ValueError("site name must contain 1-100 characters")
        timestamp = now.isoformat()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO sites(name, created_at, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(name) DO UPDATE SET updated_at=excluded.updated_at",
                (normalized, timestamp, timestamp),
            )
            row = connection.execute("SELECT id FROM sites WHERE name = ?", (normalized,)).fetchone()
            assert row is not None
            return int(row["id"])

    def create_scan(self, scan: Scan, site_id: int) -> None:
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO scans(
                    id, site_id, level, profile, target, simulation, authorized, status,
                    started_at, finished_at, assets_found, findings_found, cancelled, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    scan.id, site_id, int(scan.level), scan.profile.value, scan.target,
                    int(scan.simulation), int(scan.authorized), scan.status.value, _iso(scan.started_at),
                    _iso(scan.finished_at), scan.assets_found, scan.findings_found,
                    int(scan.cancelled), scan.error,
                ),
            )

    def update_scan(self, scan: Scan) -> None:
        with self.connect() as connection:
            connection.execute(
                """UPDATE scans SET status=?, started_at=?, finished_at=?,
                    assets_found=?, findings_found=?, cancelled=?, error=? WHERE id=?""",
                (
                    scan.status.value, _iso(scan.started_at), _iso(scan.finished_at),
                    scan.assets_found, scan.findings_found, int(scan.cancelled),
                    scan.error, scan.id,
                ),
            )

    def upsert_asset(self, site_id: int, asset: Asset) -> int:
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO assets(
                    site_id, ip, mac, hostname, vendor, device_type, criticality,
                    confidence, risk_score, source, first_seen, last_seen
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(site_id, ip) DO UPDATE SET
                    mac=excluded.mac, hostname=excluded.hostname, vendor=excluded.vendor,
                    device_type=excluded.device_type, criticality=excluded.criticality,
                    confidence=excluded.confidence, risk_score=excluded.risk_score,
                    source=excluded.source, last_seen=excluded.last_seen""",
                (
                    site_id, asset.ip, asset.mac, asset.hostname, asset.vendor,
                    asset.device_type, asset.criticality, asset.confidence,
                    asset.risk_score, asset.source, _iso(asset.first_seen), _iso(asset.last_seen),
                ),
            )
            row = connection.execute(
                "SELECT id FROM assets WHERE site_id=? AND ip=?", (site_id, asset.ip)
            ).fetchone()
            assert row is not None
            asset_id = int(row["id"])
            asset.id = asset_id
            observed_at = _iso(asset.last_seen)
            for port in sorted(set(asset.ports)):
                connection.execute(
                    """INSERT INTO ports(asset_id, port, transport, observed_at)
                    VALUES (?, ?, 'tcp', ?) ON CONFLICT(asset_id, port, transport)
                    DO UPDATE SET observed_at=excluded.observed_at""",
                    (asset_id, port, observed_at),
                )
            for service in asset.services:
                connection.execute(
                    """INSERT INTO services(asset_id, port, transport, name, product, version, evidence, observed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(asset_id, port, transport)
                    DO UPDATE SET name=excluded.name, product=excluded.product,
                    version=excluded.version, evidence=excluded.evidence, observed_at=excluded.observed_at""",
                    (asset_id, service.port, service.transport, service.name, service.product,
                     service.version, service.evidence, observed_at),
                )
            for protocol in asset.protocols:
                connection.execute(
                    """INSERT INTO protocols(asset_id, name, port, confidence, evidence, observed_at)
                    VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(asset_id, name, port)
                    DO UPDATE SET confidence=excluded.confidence, evidence=excluded.evidence,
                    observed_at=excluded.observed_at""",
                    (asset_id, protocol.name, protocol.port, protocol.confidence,
                     protocol.evidence, observed_at),
                )
            return asset_id

    def add_finding(self, scan_id: str, asset_id: int | None, finding: Finding) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO findings(
                    scan_id, asset_id, asset, category, title, severity, risk_score,
                    confidence, technical_reason, human_explanation, recommendation,
                    evidence, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (scan_id, asset_id, finding.asset, finding.category, finding.title,
                 finding.severity.value, finding.risk_score, finding.confidence,
                 finding.technical_reason, finding.human_explanation,
                 finding.recommendation, finding.evidence, _iso(finding.created_at)),
            )
            finding.id = int(cursor.lastrowid)
            finding.scan_id = scan_id
            return finding.id

    def upsert_access_point(self, site_id: int, access_point: WifiAccessPoint, observed_at: datetime) -> None:
        timestamp = observed_at.isoformat()
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO wifi_access_points(
                    site_id, ssid, bssid, signal_dbm, channel, encryption, first_seen, last_seen
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(site_id, bssid) DO UPDATE SET ssid=excluded.ssid,
                    signal_dbm=excluded.signal_dbm, channel=excluded.channel,
                    encryption=excluded.encryption, last_seen=excluded.last_seen""",
                (site_id, access_point.ssid, access_point.bssid, access_point.signal_dbm,
                 access_point.channel, access_point.encryption, timestamp, timestamp),
            )

    def add_change(self, site_id: int, scan_id: str, change: ChangeEvent, detected_at: datetime) -> None:
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO changes(site_id, scan_id, change_type, asset_identity,
                    details_json, detected_at) VALUES (?, ?, ?, ?, ?, ?)""",
                (site_id, scan_id, change.change_type, change.asset_identity,
                 json.dumps({"summary": change.summary}), detected_at.isoformat()),
            )

    def add_audit_entry(
        self, *, timestamp: datetime, user_action: str, scan: Scan,
        result: str, duration_ms: int, errors: str | None = None
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO audit_log(timestamp, user_action, scan_type, target,
                    profile, security_level, result, duration_ms, cancelled, errors)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (timestamp.isoformat(), user_action, "quick_audit", scan.target,
                 scan.profile.value, int(scan.level), result, duration_ms,
                 int(scan.cancelled), errors),
            )

    def list_assets(self, site: str) -> list[dict[str, object]]:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT a.* FROM assets a JOIN sites s ON s.id=a.site_id
                WHERE s.name=? ORDER BY a.ip""", (site,)
            ).fetchall()
            return [dict(row) for row in rows]

    def list_scans(self, limit: int = 100) -> list[dict[str, object]]:
        safe_limit = max(1, min(limit, 500))
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM scans ORDER BY started_at DESC LIMIT ?", (safe_limit,)
            ).fetchall()
            return [dict(row) for row in rows]

    def list_findings(self, limit: int = 100) -> list[dict[str, object]]:
        safe_limit = max(1, min(limit, 500))
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM findings ORDER BY created_at DESC LIMIT ?", (safe_limit,)
            ).fetchall()
            return [dict(row) for row in rows]

    def counts(self) -> dict[str, int]:
        names = ("sites", "scans", "assets", "findings", "audit_log")
        with self.connect() as connection:
            return {
                name: int(connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
                for name in names
            }
