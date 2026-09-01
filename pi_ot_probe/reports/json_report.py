"""JSON report serialization helper."""

import json
from typing import Any


def render(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, default=str)

