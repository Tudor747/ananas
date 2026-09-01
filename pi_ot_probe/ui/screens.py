"""Short operator-facing messages sized for a 16x2 LCD."""


def scan_progress(completed: int, total: int) -> tuple[str, str]:
    return "SCANNING...", f"{completed}/{total} DEVICES"


def finding(title: str, severity: str) -> tuple[str, str]:
    return title[:16], f"RISK: {severity.upper()}"

