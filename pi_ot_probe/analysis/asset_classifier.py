"""Future replaceable asset classification boundary."""

from pi_ot_probe.core.models import Asset


def classify(asset: Asset) -> str:
    """Return an existing evidence-backed class, or ``unknown``."""
    return asset.device_type if asset.confidence >= 0.5 else "unknown"
