"""Descriptions for the bounded checks shown in the Validation Lab."""

VALIDATION_SCENARIOS = (
    {
        "id": "host-discovery",
        "name": "Network presence validation",
        "level": 1,
        "traffic": "ICMP/TCP discovery or local ARP, maximum 256 addresses",
        "purpose": "Validate new-device and missing-device visibility.",
        "available": True,
    },
    {
        "id": "service-verification",
        "name": "Single-host exposure validation",
        "level": 2,
        "traffic": "TCP connect checks for 20 common ports at up to five connections/second",
        "purpose": "Validate unexpected-port and service-change detection.",
        "available": True,
    },
    {
        "id": "web-metadata",
        "name": "Web and TLS evidence check",
        "level": 2,
        "traffic": "One HEAD request to a previously observed local web port",
        "purpose": "Record HTTP headers, TLS parameters, and certificate fingerprint changes.",
        "available": True,
    },
    {
        "id": "ot-read-only",
        "name": "Read-only OT identity checks",
        "level": 3,
        "traffic": "Protocol-specific identity requests on one lab-approved device",
        "purpose": "Planned capability; disabled until hardware safety testing is complete.",
        "available": False,
    },
)
