"""CSV asset report helper."""

import csv
from io import StringIO
from typing import Any


def render_assets(assets: list[dict[str, Any]]) -> str:
    if not assets:
        return ""
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=list(assets[0]))
    writer.writeheader()
    writer.writerows(assets)
    return output.getvalue()
