"""Database row models and schema definitions.

The application deliberately uses the standard-library SQLite driver at this
stage. Domain dataclasses remain independent of storage, making a later ORM
migration possible without changing scanners or user interfaces.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SiteRow:
    id: int
    name: str
    created_at: str


@dataclass(frozen=True, slots=True)
class AssetRow:
    id: int
    site_id: int
    ip: str
    mac: str | None
    hostname: str | None
    device_type: str
    risk_score: int


SCHEMA_STATEMENTS: tuple[str, ...] = (
    """CREATE TABLE IF NOT EXISTS sites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS scans (
        id TEXT PRIMARY KEY,
        site_id INTEGER NOT NULL REFERENCES sites(id),
        level INTEGER NOT NULL CHECK(level BETWEEN 0 AND 3),
        profile TEXT NOT NULL,
        target TEXT NOT NULL,
        simulation INTEGER NOT NULL DEFAULT 0,
        authorized INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL,
        started_at TEXT,
        finished_at TEXT,
        assets_found INTEGER NOT NULL DEFAULT 0,
        findings_found INTEGER NOT NULL DEFAULT 0,
        cancelled INTEGER NOT NULL DEFAULT 0,
        error TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS assets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        site_id INTEGER NOT NULL REFERENCES sites(id),
        ip TEXT NOT NULL,
        mac TEXT,
        hostname TEXT,
        vendor TEXT,
        device_type TEXT NOT NULL,
        criticality TEXT NOT NULL,
        confidence REAL NOT NULL,
        risk_score INTEGER NOT NULL CHECK(risk_score BETWEEN 0 AND 100),
        source TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'up',
        discovery_reason TEXT,
        hostnames_json TEXT NOT NULL DEFAULT '[]',
        first_seen TEXT NOT NULL,
        last_seen TEXT NOT NULL,
        UNIQUE(site_id, ip)
    )""",
    """CREATE TABLE IF NOT EXISTS interfaces (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
        name TEXT NOT NULL, mac TEXT, addresses_json TEXT NOT NULL,
        observed_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS ports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
        port INTEGER NOT NULL CHECK(port BETWEEN 1 AND 65535),
        transport TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'open',
        observed_at TEXT NOT NULL, UNIQUE(asset_id, port, transport)
    )""",
    """CREATE TABLE IF NOT EXISTS services (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
        port INTEGER NOT NULL, transport TEXT NOT NULL, name TEXT NOT NULL,
        product TEXT, version TEXT, evidence TEXT, state TEXT NOT NULL DEFAULT 'open',
        reason TEXT, method TEXT, confidence INTEGER, extra_info TEXT, tunnel TEXT,
        cpes_json TEXT NOT NULL DEFAULT '[]', observed_at TEXT NOT NULL,
        UNIQUE(asset_id, port, transport)
    )""",
    """CREATE TABLE IF NOT EXISTS protocols (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
        name TEXT NOT NULL, port INTEGER, confidence REAL NOT NULL,
        evidence TEXT, observed_at TEXT NOT NULL,
        UNIQUE(asset_id, name, port)
    )""",
    """CREATE TABLE IF NOT EXISTS wifi_access_points (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        site_id INTEGER NOT NULL REFERENCES sites(id),
        ssid TEXT NOT NULL, bssid TEXT NOT NULL, signal_dbm INTEGER,
        channel INTEGER, encryption TEXT, first_seen TEXT NOT NULL,
        last_seen TEXT NOT NULL, signal_percent INTEGER, frequency_mhz INTEGER,
        band TEXT, authentication TEXT, cipher TEXT, radio_type TEXT,
        network_type TEXT, mode TEXT, rate TEXT, source TEXT NOT NULL DEFAULT 'unknown',
        UNIQUE(site_id, bssid)
    )""",
    """CREATE TABLE IF NOT EXISTS scan_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scan_id TEXT NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
        plugin TEXT NOT NULL, asset_id INTEGER REFERENCES assets(id),
        result_json TEXT NOT NULL, created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS web_observations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
        scheme TEXT NOT NULL, host TEXT NOT NULL, port INTEGER NOT NULL,
        requested_path TEXT NOT NULL, status_code INTEGER NOT NULL,
        status_reason TEXT, http_version TEXT, headers_json TEXT NOT NULL,
        tls_json TEXT, observed_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS scan_assets (
        scan_id TEXT NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
        asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
        observed_at TEXT NOT NULL,
        PRIMARY KEY(scan_id, asset_id)
    )""",
    """CREATE TABLE IF NOT EXISTS findings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scan_id TEXT NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
        asset_id INTEGER REFERENCES assets(id), asset TEXT NOT NULL,
        category TEXT NOT NULL, title TEXT NOT NULL, severity TEXT NOT NULL,
        risk_score INTEGER NOT NULL CHECK(risk_score BETWEEN 0 AND 100),
        confidence REAL NOT NULL, technical_reason TEXT NOT NULL,
        human_explanation TEXT NOT NULL, recommendation TEXT NOT NULL,
        evidence TEXT NOT NULL, created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS risk_scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
        finding_id INTEGER REFERENCES findings(id) ON DELETE CASCADE,
        score INTEGER NOT NULL CHECK(score BETWEEN 0 AND 100),
        severity TEXT NOT NULL, factors_json TEXT NOT NULL, created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS baselines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        site_id INTEGER NOT NULL REFERENCES sites(id), name TEXT NOT NULL,
        created_at TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1
    )""",
    """CREATE TABLE IF NOT EXISTS baseline_assets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        baseline_id INTEGER NOT NULL REFERENCES baselines(id) ON DELETE CASCADE,
        identity TEXT NOT NULL, snapshot_json TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS changes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        site_id INTEGER NOT NULL REFERENCES sites(id), scan_id TEXT REFERENCES scans(id),
        change_type TEXT NOT NULL, asset_identity TEXT, details_json TEXT NOT NULL,
        detected_at TEXT NOT NULL, acknowledged_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS update_packs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version TEXT NOT NULL UNIQUE, sha256 TEXT NOT NULL, signature TEXT NOT NULL,
        compatible INTEGER NOT NULL, installed_at TEXT NOT NULL, active INTEGER NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS capture_metadata (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scan_id TEXT REFERENCES scans(id), interface TEXT NOT NULL, bpf_filter TEXT,
        started_at TEXT NOT NULL, stopped_at TEXT, packets INTEGER NOT NULL DEFAULT 0,
        bytes INTEGER NOT NULL DEFAULT 0, pcap_path TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL, user_action TEXT NOT NULL, scan_type TEXT,
        target TEXT, profile TEXT, security_level INTEGER, plugin TEXT,
        result TEXT, duration_ms INTEGER, cancelled INTEGER NOT NULL DEFAULT 0,
        errors TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_assets_site ON assets(site_id)",
    "CREATE INDEX IF NOT EXISTS idx_findings_scan ON findings(scan_id)",
    "CREATE INDEX IF NOT EXISTS idx_scan_assets_asset ON scan_assets(asset_id)",
    "CREATE INDEX IF NOT EXISTS idx_web_observations_asset ON web_observations(asset_id)",
    "CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp)",
)
