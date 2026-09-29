"""Targets support for bounded, real local observations."""

from __future__ import annotations

import ipaddress
from pi_ot_probe.collectors.interfaces import LocalNetwork, _is_rfc1918

MAX_TARGET_ADDRESSES = 256


def validate_target(target: str, local_networks: list[LocalNetwork]) -> ipaddress.IPv4Network:
    """Require a small RFC1918 subnet contained in an active local interface."""
    try:
        network = ipaddress.ip_network(target, strict=True)
    except ValueError as exc:
        raise ValueError("target must be a canonical IPv4 network such as 192.168.1.0/24") from exc
    if not isinstance(network, ipaddress.IPv4Network):
        raise ValueError("only IPv4 discovery is currently supported")
    if not _is_rfc1918(network):
        raise ValueError("target must be an RFC1918 private network")
    if network.num_addresses > MAX_TARGET_ADDRESSES:
        raise ValueError("target is too large; select a /24 or smaller network")
    active_networks = [ipaddress.ip_network(item.network) for item in local_networks]
    if not any(network.subnet_of(active) for active in active_networks):
        raise ValueError("target must belong to an active local interface")
    return network
