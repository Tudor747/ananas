"""Evidence-backed assessment leads; no inferred vulnerabilities or risk scores."""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
import re
from typing import Any


PORT_REVIEWS = {
    21: ("Possible FTP service exposed", "medium",
         "TCP/21 is reachable. The service and whether it protects credentials are not confirmed.",
         "Identify the service. If plaintext FTP is in use, migrate to SFTP or an approved encrypted alternative; restrict access."),
    23: ("Possible Telnet service exposed", "medium",
         "TCP/23 is reachable. Telnet commonly lacks transport encryption, but a port number alone does not identify the protocol.",
         "Confirm the service. Replace plaintext Telnet administration with SSH where supported and restrict management access."),
    445: ("File-sharing service exposure to review", "low",
          "TCP/445 is reachable from the assessment network. SMB version, permissions and authentication were not tested.",
          "Confirm the service and business need; review allowed source networks, share permissions and SMB configuration."),
    3389: ("Remote desktop exposure to review", "medium",
           "TCP/3389 is reachable from the assessment network. Authentication, MFA and internet exposure are unknown.",
           "Confirm the service and restrict remote administration to approved management paths; review authentication with the owner."),
    5900: ("Remote screen-sharing exposure to review", "medium",
           "TCP/5900 is reachable. The protocol, encryption and access controls need confirmation.",
           "Confirm the service, restrict source networks, and verify authenticated, encrypted remote access."),
}

REVIEW_STATES = {"new", "investigating", "reviewed", "accepted_risk", "remediated"}
FIELD_CATEGORIES = {"wifi", "bluetooth", "rf", "network", "detection_validation", "other"}


def _finding(
    rule: str, subject: str, title: str, priority: str, evidence: dict[str, Any],
    implication: str, recommendation: str, *, basis: str = "observed exposure",
) -> dict[str, Any]:
    # Reviews belong to an exact evidence revision: a new observation needs review.
    identity = json.dumps([rule, subject, evidence], sort_keys=True, ensure_ascii=True)
    return {
        "id": sha256(identity.encode()).hexdigest(), "rule": rule, "subject": subject,
        "title": title, "priority": priority, "basis": basis, "evidence": evidence,
        "implication": implication, "recommendation": recommendation,
        "status": "new", "note": "", "reviewed_at": None,
    }


def build_assessment(state: dict[str, Any], field_observations: list[dict[str, Any]]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    assets = state.get("assets", [])
    for asset in assets:
        for port in asset.get("ports", []):
            number = port["port"]
            if number not in PORT_REVIEWS:
                continue
            title, priority, implication, recommendation = PORT_REVIEWS[number]
            findings.append(_finding(
                f"tcp-{number}", asset["ip"], title, priority,
                {"source": "Nmap TCP connect", "port": number, "transport": "tcp",
                 "observed_at": port.get("observed_at"),
                 "scan_id": asset.get("verification_scan_id")},
                implication, recommendation,
            ))
        # Dashboard observations are newest first; avoid duplicate leads for one endpoint.
        seen: set[tuple[str, int]] = set()
        for web in asset.get("web_observations", []):
            endpoint = (web["scheme"], web["port"])
            if endpoint in seen:
                continue
            seen.add(endpoint)
            evidence = {key: web.get(key) for key in (
                "id", "scheme", "host", "port", "status_code", "observed_at",
            )}
            evidence["source"] = "HTTP HEAD observation"
            subject = f"{web['scheme']}://{asset['ip']}:{web['port']}"
            if web["scheme"] == "http":
                findings.append(_finding(
                    "http-transport", subject, "Unencrypted HTTP response observed", "low", evidence,
                    "This response used plaintext HTTP. Login behavior and sensitive content were not inspected; a redirect may already be present.",
                    "Check that sensitive workflows require HTTPS and that any HTTP endpoint redirects as intended. Validate TLS separately.",
                ))
            tls = web.get("tls") or {}
            if tls.get("protocol") in {"TLSv1", "TLSv1.0", "TLSv1.1", "SSLv2", "SSLv3"}:
                findings.append(_finding(
                    "legacy-tls", subject, "Legacy TLS protocol negotiated", "high",
                    {**evidence, "tls_protocol": tls["protocol"]},
                    "The recorded connection negotiated an obsolete transport protocol.",
                    "Review client compatibility, disable obsolete protocol versions, enable supported TLS, and repeat the handshake check.",
                    basis="observed configuration",
                ))

    for ap in state.get("access_points", []):
        modes = {str(ap.get(key) or "").strip().upper() for key in ("authentication", "encryption", "cipher")}
        if any(re.search(r"\bWEP\b", mode) for mode in modes):
            title, rule = "WEP advertised by a nearby access point", "wifi-wep"
        elif modes & {"OPEN", "NONE"} and not any("OWE" in mode or "WPA" in mode for mode in modes):
            title, rule = "Open Wi-Fi access point observed", "wifi-open"
        else:
            continue
        findings.append(_finding(
            rule, ap["bssid"], title, "medium",
            {"source": ap.get("source"), "ssid": ap["ssid"], "bssid": ap["bssid"],
             "authentication": ap.get("authentication"), "encryption": ap.get("encryption"),
             "cipher": ap.get("cipher"), "observed_at": ap.get("last_seen")},
            "The OS reported this security mode. Ownership, present availability and access to business networks are unverified.",
            "Confirm ownership. For an in-scope AP, review its security mode and guest isolation; replace WEP and protect business access with an approved modern configuration.",
            basis="observed advertisement; ownership unverified",
        ))

    for observation in field_observations:
        findings.append(_finding(
            "field-observation", observation["subject"], observation["title"], "review",
            {"source": "operator entry", **observation},
            "Operator-supplied evidence. The application has not independently collected or verified this observation.",
            observation["recommendation"] or "Corroborate the observation and record a specific improvement or expected behavior.",
            basis="manual observation",
        ))

    checked = sum(bool(asset.get("services_checked_at")) for asset in assets)
    web_count = sum(len(asset.get("web_observations", [])) for asset in assets)
    coverage = [
        {"area": "Device inventory", "status": "observed" if state.get("current_site") else "not assessed",
         "detail": f"{len(assets)} devices in the latest completed discovery; nonresponding devices may be missed."},
        {"area": "TCP exposure", "status": "partial" if checked else "not assessed",
         "detail": f"{checked} of {len(assets)} current devices checked, 20 common TCP ports per device; no UDP coverage."},
        {"area": "HTTP / TLS metadata", "status": "partial" if web_count else "not assessed",
         "detail": f"{web_count} current recorded responses; no certificate trust, expiry, application login or content assessment."},
        {"area": "Wi-Fi", "status": "partial" if state.get("access_points") else "not assessed",
         "detail": "OS observations may be retained from earlier surveys. Ownership, client isolation and unobserved bands are unverified."},
        {"area": "ESP instruments", "status": "manual only",
         "detail": "Unchanged BWifiKill firmware has no verified scan telemetry or remote command API. Records do not prove a device is connected."},
        {"area": "Versions, CVEs and credentials", "status": "not assessed",
         "detail": "No verified software inventory, vulnerability matching, password or account-policy checks."},
        {"area": "Segmentation and internet exposure", "status": "not assessed",
         "detail": "Reachability from this collector does not establish access from other zones or the internet."},
        {"area": "Detection and response", "status": "manual only" if any(o["category"] == "detection_validation" for o in field_observations) else "not assessed",
         "detail": "No SIEM/EDR integration; record expected and actual alert evidence as a manual validation observation."},
    ]
    order = {"high": 0, "medium": 1, "low": 2, "review": 3}
    findings.sort(key=lambda item: (order[item["priority"]], item["subject"], item["title"]))
    return {
        "site": state.get("current_site"), "findings": findings, "coverage": coverage,
        "counts": dict(Counter(item["priority"] for item in findings)),
        "limitations": "Review priorities are triage suggestions, not vulnerability scores. No findings does not mean secure. Review status is an operator decision, not an automated retest.",
    }
