"""Explainable local risk scoring; protocol exposure is not called a vulnerability."""

from __future__ import annotations

from pi_ot_probe.core.models import Asset, Finding, Severity


OT_PROTOCOL_WEIGHTS = {
    "Modbus/TCP": 30,
    "S7": 25,
    "OPC UA": 18,
    "BACnet/IP": 24,
    "EtherNet/IP": 24,
}

LEGACY_TCP_EXPOSURES = {
    21: ("FTP-LIKELY PORT OPEN", 48, "FTP commonly sends credentials and data without transport encryption."),
    23: ("TELNET-LIKELY PORT OPEN", 68, "Telnet commonly sends administrative sessions without encryption."),
    445: ("SMB PORT EXPOSED", 42, "SMB is reachable from the assessed network segment."),
    3389: ("REMOTE DESKTOP EXPOSED", 45, "Remote Desktop is reachable from the assessed network segment."),
}


def severity_for(score: int) -> Severity:
    if score >= 85:
        return Severity.CRITICAL
    if score >= 65:
        return Severity.HIGH
    if score >= 40:
        return Severity.MEDIUM
    if score >= 15:
        return Severity.LOW
    return Severity.INFO


class RiskEngine:
    """Calculate contextual, confidence-adjusted scores from observed facts."""

    def evaluate(self, asset: Asset) -> list[Finding]:
        findings: list[Finding] = []
        for protocol in asset.protocols:
            if protocol.name not in OT_PROTOCOL_WEIGHTS:
                continue
            score = 20 + OT_PROTOCOL_WEIGHTS[protocol.name]
            if asset.criticality == "high":
                score += 20
            if protocol.port in asset.ports:
                score += 15
            score = min(100, round(score * (0.7 + 0.3 * protocol.confidence)))
            severity = severity_for(score)
            asset.risk_score = max(asset.risk_score, score)
            findings.append(Finding(
                title=f"{protocol.name.upper()} FOUND",
                asset=asset.ip,
                technical_reason=(
                    f"{protocol.name} was identified on {asset.ip}"
                    + (f" TCP/{protocol.port}." if protocol.port else ".")
                ),
                human_explanation=(
                    "An industrial-control service is reachable from the observed network segment. "
                    "This is exposure evidence, not proof of a vulnerability."
                ),
                recommendation=(
                    f"Confirm that only required systems can reach {protocol.name} and review "
                    "network segmentation and device access controls."
                ),
                severity=severity,
                risk_score=score,
                confidence=protocol.confidence,
                evidence=protocol.evidence or f"Observed {protocol.name}",
                category="ot_protocol_exposure",
            ))
        for port in sorted(set(asset.ports) & LEGACY_TCP_EXPOSURES.keys()):
            title, base_score, explanation = LEGACY_TCP_EXPOSURES[port]
            score = min(100, base_score + (15 if asset.criticality == "high" else 0))
            asset.risk_score = max(asset.risk_score, score)
            findings.append(Finding(
                title=title,
                asset=asset.ip,
                technical_reason=(
                    f"TCP/{port} accepted a connection. The service label is inferred from the "
                    "well-known port; no version or vulnerability probe was run."
                ),
                human_explanation=explanation + " This exposure is not proof of a vulnerability.",
                recommendation=(
                    f"Confirm the required service on TCP/{port}, restrict access to approved systems, "
                    "and use an encrypted replacement where applicable."
                ),
                severity=severity_for(score),
                risk_score=score,
                confidence=0.75,
                evidence=f"Nmap TCP connect scan reported TCP/{port} open",
                category="service_exposure",
            ))
        return findings
