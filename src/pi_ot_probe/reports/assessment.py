"""Portable assessment summaries with explicit source and coverage limitations."""

import html
import json
import re
from typing import Any

from pi_ot_probe.domain.models import utc_now


def assessment_report(assessment: dict[str, Any]) -> dict[str, Any]:
    return {"report_version": "1.0", "generated_at": utc_now().isoformat(), **assessment}


def _text(value: object) -> str:
    # Untrusted network names and operator notes stay text in rendered Markdown.
    value = html.escape(str(value), quote=False).replace("\r", " ").replace("\n", " / ")
    return re.sub(r"([\\`*_{}\[\]()#+.!|>~\-])", r"\\\1", value)


def assessment_markdown(assessment: dict[str, Any]) -> str:
    report = assessment_report(assessment)
    lines = [
        "# Network assessment", "", f"Network: {_text(report['site'] or 'No discovery yet')}",
        f"Generated: {_text(report['generated_at'])}", "", _text(report["limitations"]),
        "", "## Findings and improvements", "",
    ]
    if not report["findings"]:
        lines.append("No review leads in the collected evidence. See unassessed areas below.")
    for item in report["findings"]:
        lines.extend([
            f"### {_text(item['title'])}", "",
            f"- Subject: {_text(item['subject'])}",
            f"- Review priority: {_text(item['priority'])}; basis: {_text(item['basis'])}",
            f"- Status: {_text(item['status'])}",
            f"- Meaning: {_text(item['implication'])}",
            f"- Improvement: {_text(item['recommendation'])}",
            f"- Review note: {_text(item['note'] or 'Not reviewed')}",
            f"- Evidence revision: {_text(item['id'])}", "",
        ])
        evidence = json.dumps(item["evidence"], indent=2, ensure_ascii=True)
        longest = max((len(match) for match in re.findall(r"`+", evidence)), default=0)
        fence = "`" * max(3, longest + 1)
        lines.extend([f"{fence}json", evidence, fence, ""])
    lines.extend(["## Assessment coverage", ""])
    for area in report["coverage"]:
        lines.append(f"- **{_text(area['area'])} — {_text(area['status'])}:** {_text(area['detail'])}")
    return "\n".join(lines) + "\n"
