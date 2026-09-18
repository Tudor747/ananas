"""Site baseline snapshots and raw observation comparison."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from pi_ot_probe.core.models import utc_now
from pi_ot_probe.database.repository import Repository


class BaselineManager:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    @staticmethod
    def _site_id(connection: Any, site: str) -> int:
        row = connection.execute("SELECT id FROM sites WHERE name=?", (site,)).fetchone()
        if not row:
            raise ValueError("site has no completed discovery scan")
        return int(row["id"])

    @staticmethod
    def _latest_discovery_scan(connection: Any, site_id: int) -> str:
        row = connection.execute(
            """SELECT id FROM scans WHERE site_id=? AND level=1 AND status='completed'
            ORDER BY rowid DESC LIMIT 1""",
            (site_id,),
        ).fetchone()
        if not row:
            raise ValueError("run a completed host discovery before creating a baseline")
        return str(row["id"])

    @staticmethod
    def _asset_snapshots(connection: Any, site_id: int, scan_id: str) -> list[dict[str, Any]]:
        rows = connection.execute(
            """SELECT a.*, sa.snapshot_json FROM assets a
            JOIN scan_assets sa ON sa.asset_id=a.id
            WHERE a.site_id=? AND sa.scan_id=? ORDER BY a.ip""",
            (site_id, scan_id),
        ).fetchall()
        snapshots: list[dict[str, Any]] = []
        for row in rows:
            asset_id = int(row["id"])
            raw_snapshot = row["snapshot_json"]
            if raw_snapshot:
                try:
                    observed = json.loads(raw_snapshot)
                except (json.JSONDecodeError, TypeError):
                    observed = None
                if isinstance(observed, dict):
                    services = {
                        f"{item.get('transport', 'tcp')}/{item.get('port')}": item.get("name", "unknown")
                        for item in observed.get("services", []) if isinstance(item, dict)
                    }
                    protocols = [
                        str(item.get("name")) for item in observed.get("protocols", [])
                        if isinstance(item, dict) and item.get("name")
                    ]
                    snapshots.append({
                        "kind": "asset",
                        "_asset_id": asset_id,
                        "ip": observed.get("ip", row["ip"]),
                        "mac": observed.get("mac"),
                        "hostname": observed.get("hostname"),
                        "vendor": observed.get("vendor"),
                        "device_type": observed.get("device_type", "unknown"),
                        "ports": sorted(set(observed.get("ports", []))),
                        "services": services,
                        "protocols": protocols,
                    })
                    continue
            ports = [int(item[0]) for item in connection.execute(
                "SELECT port FROM ports WHERE asset_id=? ORDER BY port", (asset_id,)
            ).fetchall()]
            services = {
                f"{item['transport']}/{item['port']}": item["name"]
                for item in connection.execute(
                    "SELECT port, transport, name FROM services WHERE asset_id=?", (asset_id,)
                ).fetchall()
            }
            protocols = [str(item[0]) for item in connection.execute(
                "SELECT name FROM protocols WHERE asset_id=? ORDER BY name", (asset_id,)
            ).fetchall()]
            snapshots.append({
                "kind": "asset",
                "_asset_id": asset_id,
                "ip": row["ip"],
                "mac": row["mac"],
                "hostname": row["hostname"],
                "vendor": row["vendor"],
                "device_type": row["device_type"],
                "ports": ports,
                "services": services,
                "protocols": protocols,
            })
        return snapshots

    @classmethod
    def _current_asset_snapshots(
        cls, connection: Any, site_id: int, through_scan_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Build current state from the latest discovery plus later per-host checks."""
        scan_limit = None
        if through_scan_id:
            scan_limit = connection.execute(
                "SELECT rowid FROM scans WHERE id=? AND site_id=?",
                (through_scan_id, site_id),
            ).fetchone()
            if not scan_limit:
                raise ValueError("scan does not belong to the selected site")
        query = """SELECT id, rowid FROM scans WHERE site_id=? AND level=1
            AND status='completed'"""
        parameters: list[Any] = [site_id]
        if scan_limit:
            query += " AND rowid<=?"
            parameters.append(int(scan_limit["rowid"]))
        discovery = connection.execute(query + " ORDER BY rowid DESC LIMIT 1", parameters).fetchone()
        if not discovery:
            return []
        snapshots = cls._asset_snapshots(connection, site_id, str(discovery["id"]))
        for snapshot in snapshots:
            asset_id = snapshot.get("_asset_id")
            verification_query = """SELECT sa.snapshot_json FROM scan_assets sa
                JOIN scans sc ON sc.id=sa.scan_id WHERE sa.asset_id=? AND sc.site_id=?
                AND sc.level=2 AND sc.status='completed' AND sc.rowid>?"""
            verification_parameters: list[Any] = [asset_id, site_id, int(discovery["rowid"])]
            if scan_limit:
                verification_query += " AND sc.rowid<=?"
                verification_parameters.append(int(scan_limit["rowid"]))
            verification = connection.execute(
                verification_query + " ORDER BY sc.rowid DESC LIMIT 1",
                verification_parameters,
            ).fetchone()
            if not verification or not verification["snapshot_json"]:
                continue
            try:
                observed = json.loads(verification["snapshot_json"])
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(observed, dict):
                continue
            snapshot["ports"] = sorted(set(observed.get("ports", [])))
            snapshot["services"] = {
                f"{item.get('transport', 'tcp')}/{item.get('port')}": item.get("name", "unknown")
                for item in observed.get("services", []) if isinstance(item, dict)
            }
            snapshot["protocols"] = [
                str(item.get("name")) for item in observed.get("protocols", [])
                if isinstance(item, dict) and item.get("name")
            ]
        return snapshots

    @staticmethod
    def _wifi_snapshots(connection: Any, site_id: int) -> list[dict[str, Any]]:
        return [{
            "kind": "wifi",
            "ssid": row["ssid"],
            "bssid": row["bssid"],
            "channel": row["channel"],
            "encryption": row["encryption"],
        } for row in connection.execute(
            """SELECT ssid, bssid, channel, encryption FROM wifi_access_points
            WHERE site_id=? ORDER BY bssid""", (site_id,)
        ).fetchall()]

    def create(self, site: str, name: str = "Site baseline") -> dict[str, object]:
        normalized = name.strip()
        if not normalized or len(normalized) > 100:
            raise ValueError("baseline name must contain 1-100 characters")
        self.repository.initialize()
        now = utc_now().isoformat()
        with self.repository.connect() as connection:
            site_id = self._site_id(connection, site)
            scan_id = self._latest_discovery_scan(connection, site_id)
            snapshots = self._current_asset_snapshots(connection, site_id)
            if not snapshots:
                raise ValueError("the latest discovery has no assets to baseline")
            snapshots.extend(self._wifi_snapshots(connection, site_id))
            connection.execute("UPDATE baselines SET active=0 WHERE site_id=?", (site_id,))
            cursor = connection.execute(
                "INSERT INTO baselines(site_id, name, created_at, active) VALUES (?, ?, ?, 1)",
                (site_id, normalized, now),
            )
            baseline_id = int(cursor.lastrowid)
            for snapshot in snapshots:
                snapshot = {key: value for key, value in snapshot.items() if key != "_asset_id"}
                if snapshot["kind"] == "asset":
                    identity = f"asset:{snapshot.get('mac') or snapshot['ip']}"
                else:
                    identity = f"wifi:{snapshot['bssid']}"
                connection.execute(
                    """INSERT INTO baseline_assets(baseline_id, identity, snapshot_json)
                    VALUES (?, ?, ?)""",
                    (baseline_id, identity, json.dumps(snapshot, sort_keys=True)),
                )
        return {
            "id": baseline_id,
            "name": normalized,
            "site": site,
            "assets": sum(item["kind"] == "asset" for item in snapshots),
            "access_points": sum(item["kind"] == "wifi" for item in snapshots),
            "created_at": now,
        }

    def status(self, site: str | None) -> dict[str, object] | None:
        if not site:
            return None
        self.repository.initialize()
        with self.repository.connect() as connection:
            row = connection.execute(
                """SELECT b.id, b.name, b.created_at FROM baselines b
                JOIN sites s ON s.id=b.site_id WHERE s.name=? AND b.active=1
                ORDER BY b.id DESC LIMIT 1""", (site,)
            ).fetchone()
            if not row:
                return None
            counts = connection.execute(
                """SELECT
                    SUM(CASE WHEN snapshot_json LIKE '%\"kind\": \"asset\"%' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN snapshot_json LIKE '%\"kind\": \"wifi\"%' THEN 1 ELSE 0 END)
                FROM baseline_assets WHERE baseline_id=?""", (row["id"],)
            ).fetchone()
            return {
                "id": int(row["id"]),
                "name": row["name"],
                "created_at": row["created_at"],
                "assets": int(counts[0] or 0),
                "access_points": int(counts[1] or 0),
            }

    def compare(self, site: str, scan_id: str) -> list[dict[str, object]]:
        self.repository.initialize()
        detected_at = utc_now().isoformat()
        with self.repository.connect() as connection:
            site_id = self._site_id(connection, site)
            baseline = connection.execute(
                """SELECT id FROM baselines WHERE site_id=? AND active=1
                ORDER BY id DESC LIMIT 1""", (site_id,)
            ).fetchone()
            if not baseline:
                return []
            comparison_scan = connection.execute(
                "SELECT level, status FROM scans WHERE id=? AND site_id=?",
                (scan_id, site_id),
            ).fetchone()
            if not comparison_scan or comparison_scan["status"] != "completed":
                return []
            stored = [json.loads(row[0]) for row in connection.execute(
                "SELECT snapshot_json FROM baseline_assets WHERE baseline_id=?",
                (baseline["id"],),
            ).fetchall()]
            old_assets = [item for item in stored if item.get("kind") == "asset"]
            old_wifi = [item for item in stored if item.get("kind") == "wifi"]
            current_assets = (
                self._asset_snapshots(connection, site_id, scan_id)
                if int(comparison_scan["level"]) == 1
                else self._current_asset_snapshots(connection, site_id, scan_id)
            )
            current_wifi = self._wifi_snapshots(connection, site_id)
            changes: list[dict[str, object]] = []
            matched: set[int] = set()

            def record(change_type: str, identity: str, summary: str, **details: object) -> None:
                changes.append({
                    "change_type": change_type,
                    "asset_identity": identity,
                    "summary": summary,
                    **details,
                })

            def mac_key(asset: dict[str, Any]) -> str | None:
                value = asset.get("mac")
                return str(value).replace("-", ":").upper() if value else None

            # Reserve all unambiguous MAC matches before IP fallback: a reused
            # address must not steal a device that moved elsewhere through DHCP.
            old_counts = Counter(mac_key(item) for item in old_assets)
            current_counts = Counter(mac_key(item) for item in current_assets)
            matches: dict[int, int] = {}
            for old_index, old in enumerate(old_assets):
                key = mac_key(old)
                if key and old_counts[key] == current_counts[key] == 1:
                    index = next(i for i, item in enumerate(current_assets) if mac_key(item) == key)
                    matches[old_index] = index
                    matched.add(index)
            for old_index, old in enumerate(old_assets):
                if old_index in matches:
                    continue
                index = next((i for i, item in enumerate(current_assets)
                              if i not in matched and item.get("ip") == old.get("ip")), None)
                if index is not None:
                    matches[old_index] = index
                    matched.add(index)

            for old_index, old in enumerate(old_assets):
                match_index = matches.get(old_index)
                identity = str(old.get("mac") or old.get("ip"))
                if match_index is None:
                    record("device_removed", identity, f"Device {old.get('ip')} was not observed")
                    continue
                matched.add(match_index)
                current = current_assets[match_index]
                mac_changed = bool(mac_key(old) and mac_key(current)
                                   and mac_key(old) != mac_key(current))
                if old.get("ip") != current.get("ip") or mac_changed:
                    record("mac_ip_changed", identity, "Device network identity changed",
                           previous_ip=old.get("ip"), current_ip=current.get("ip"),
                           previous_mac=old.get("mac"), current_mac=current.get("mac"))
                new_ports = sorted(set(current.get("ports", [])) - set(old.get("ports", [])))
                if new_ports:
                    record("new_port", str(current["ip"]),
                           f"New TCP ports observed: {', '.join(map(str, new_ports))}", ports=new_ports)
                old_services = old.get("services", {})
                changed_services = {
                    key: value for key, value in current.get("services", {}).items()
                    if key in old_services and old_services[key] != value
                }
                if changed_services:
                    record("service_changed", str(current["ip"]), "A known service changed",
                           services=changed_services)
                new_protocols = sorted(set(current.get("protocols", [])) - set(old.get("protocols", [])))
                if new_protocols:
                    record("new_ot_protocol", str(current["ip"]),
                           f"New OT protocols observed: {', '.join(new_protocols)}",
                           protocols=new_protocols)

            for index, current in enumerate(current_assets):
                if index not in matched:
                    record("new_device", str(current.get("mac") or current["ip"]),
                           f"New device observed at {current['ip']}")

            old_bssids = {str(item["bssid"]).upper() for item in old_wifi}
            for access_point in current_wifi:
                if str(access_point["bssid"]).upper() not in old_bssids:
                    record("new_wifi_ap", str(access_point["bssid"]),
                           f"New Wi-Fi AP observed: {access_point['ssid']}")

            existing = {
                (row["change_type"], row["asset_identity"]): int(row["id"])
                for row in connection.execute(
                    """SELECT id, change_type, asset_identity FROM changes WHERE scan_id=?""",
                    (scan_id,),
                ).fetchall()
            }
            for change in changes:
                key = (change["change_type"], change["asset_identity"])
                if key in existing:
                    connection.execute(
                        "UPDATE changes SET details_json=? WHERE id=?",
                        (json.dumps(change, sort_keys=True), existing[key]),
                    )
                else:
                    connection.execute(
                        """INSERT INTO changes(site_id, scan_id, change_type, asset_identity,
                        details_json, detected_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (site_id, scan_id, change["change_type"], change["asset_identity"],
                         json.dumps(change, sort_keys=True), detected_at, detected_at),
                    )
            return changes

    def compare_latest(self, site: str) -> list[dict[str, object]]:
        with self.repository.connect() as connection:
            site_id = self._site_id(connection, site)
            scan_id = self._latest_discovery_scan(connection, site_id)
        return self.compare(site, scan_id)

    def acknowledge(self, site: str, change_id: int) -> bool:
        with self.repository.connect() as connection:
            cursor = connection.execute(
                """UPDATE changes SET acknowledged_at=?, triage_status='benign_change',
                    updated_at=? WHERE id=? AND site_id=(
                    SELECT id FROM sites WHERE name=?)""",
                (utc_now().isoformat(), utc_now().isoformat(), change_id, site),
            )
            return cursor.rowcount == 1

    def triage(self, site: str, change_id: int, status: str, note: str) -> bool:
        allowed = {"new", "investigating", "benign_change", "confirmed", "remediated"}
        if status not in allowed:
            raise ValueError("invalid triage status")
        normalized_note = note.strip()
        if len(normalized_note) > 2000:
            raise ValueError("analyst note must be 2000 characters or fewer")
        now = utc_now().isoformat()
        acknowledged_at = now if status in {"benign_change", "remediated"} else None
        with self.repository.connect() as connection:
            cursor = connection.execute(
                """UPDATE changes SET triage_status=?, analyst_note=?, updated_at=?,
                    acknowledged_at=COALESCE(?, acknowledged_at) WHERE id=? AND site_id=(
                    SELECT id FROM sites WHERE name=?)""",
                (status, normalized_note or None, now, acknowledged_at, change_id, site),
            )
            return cursor.rowcount == 1
