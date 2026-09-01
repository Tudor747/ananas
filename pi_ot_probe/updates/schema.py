"""Update schema boundary; executable plugin delivery is explicitly forbidden."""

ALLOWED_KEYS = {
    "version", "vendors", "service_rules", "device_fingerprints",
    "ot_fingerprints", "risk_rules", "cve_metadata", "recommendations",
}

