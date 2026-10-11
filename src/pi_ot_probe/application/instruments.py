"""Local records for unchanged field instruments, evidence and assessment reviews."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pi_ot_probe.application.assessment import FIELD_CATEGORIES, REVIEW_STATES, build_assessment
from pi_ot_probe.database.repository import Repository
from pi_ot_probe.domain.models import utc_now


def _text(value: str, label: str, maximum: int, *, required: bool = True) -> str:
    normalized = value.strip()
    if (required and not normalized) or len(normalized) > maximum:
        raise ValueError(f"{label} must contain {'1' if required else '0'}-{maximum} characters")
    return normalized


class InstrumentWorkspace:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def instruments(self) -> list[dict[str, Any]]:
        self.repository.initialize()
        with self.repository.connect() as connection:
            return [{**dict(row), "integration": "manual", "connection_status": "not verified"}
                    for row in connection.execute("SELECT * FROM assessment_instruments ORDER BY id")]

    def register(self, name: str, model: str, firmware: str, notes: str) -> dict[str, Any]:
        values = (
            _text(name, "name", 80), _text(model, "model", 120),
            _text(firmware, "firmware", 120), _text(notes, "notes", 2000, required=False),
            utc_now().isoformat(),
        )
        self.repository.initialize()
        with self.repository.connect() as connection:
            if connection.execute("SELECT id FROM assessment_instruments WHERE name=?", (values[0],)).fetchone():
                raise ValueError("an instrument with this name is already registered")
            cursor = connection.execute(
                "INSERT INTO assessment_instruments(name, model, firmware, notes, created_at) VALUES (?, ?, ?, ?, ?)", values,
            )
            instrument_id = cursor.lastrowid
        return next(item for item in self.instruments() if item["id"] == instrument_id)

    def observations(self, site: str | None) -> list[dict[str, Any]]:
        if not site:
            return []
        self.repository.initialize()
        with self.repository.connect() as connection:
            return [dict(row) for row in connection.execute(
                """SELECT o.*, i.name AS instrument_name, i.model, i.firmware
                FROM field_observations o JOIN assessment_instruments i ON i.id=o.instrument_id
                JOIN sites s ON s.id=o.site_id WHERE s.name=? ORDER BY o.observed_at DESC, o.id DESC""", (site,),
            )]

    def record(self, site: str, instrument_id: int, category: str, title: str,
               subject: str, location: str, evidence: str, recommendation: str,
               observed_at: datetime) -> dict[str, Any]:
        if category not in FIELD_CATEGORIES:
            raise ValueError("unknown observation category")
        now = utc_now()
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("observation time must include a timezone")
        if observed_at > now:
            raise ValueError("observation time cannot be in the future")
        values = (
            _text(title, "title", 160), _text(subject, "subject", 200),
            _text(location, "location", 200, required=False), _text(evidence, "evidence", 4000),
            _text(recommendation, "recommendation", 2000, required=False),
        )
        self.repository.initialize()
        with self.repository.connect() as connection:
            site_row = connection.execute("SELECT id FROM sites WHERE name=?", (site,)).fetchone()
            if not site_row:
                raise ValueError("unknown site")
            if not connection.execute("SELECT id FROM assessment_instruments WHERE id=?", (instrument_id,)).fetchone():
                raise ValueError("register the instrument before recording evidence")
            cursor = connection.execute(
                """INSERT INTO field_observations(site_id, instrument_id, category,
                title, subject, location, evidence, recommendation, observed_at, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (site_row["id"], instrument_id, category, *values,
                 observed_at.astimezone(timezone.utc).isoformat(), now.isoformat()),
            )
            observation_id = cursor.lastrowid
        return next(item for item in self.observations(site) if item["id"] == observation_id)

    def assessment(self, state: dict[str, Any]) -> dict[str, Any]:
        self.repository.initialize()
        site = state.get("current_site")
        result = build_assessment(state, self.observations(site))
        with self.repository.connect() as connection:
            reviews = {row["finding_id"]: dict(row) for row in connection.execute(
                """SELECT r.* FROM assessment_reviews r JOIN sites s ON s.id=r.site_id
                WHERE s.name=?""", (site,),
            )}
        for finding in result["findings"]:
            review = reviews.get(finding["id"])
            if review:
                finding.update(status=review["status"], note=review["note"], reviewed_at=review["updated_at"])
        return result

    def review(self, state: dict[str, Any], finding_id: str, status: str, note: str) -> None:
        if status not in REVIEW_STATES:
            raise ValueError("invalid finding status")
        note = _text(note, "review note", 2000, required=False)
        if status in {"accepted_risk", "remediated"} and not note:
            raise ValueError("record the reason or retest evidence before closing a finding")
        if not any(item["id"] == finding_id for item in self.assessment(state)["findings"]):
            raise ValueError("finding is no longer part of the current evidence; refresh the assessment")
        with self.repository.connect() as connection:
            site = connection.execute("SELECT id FROM sites WHERE name=?", (state["current_site"],)).fetchone()
            connection.execute(
                """INSERT INTO assessment_reviews(site_id, finding_id, status, note, updated_at)
                VALUES (?, ?, ?, ?, ?) ON CONFLICT(site_id, finding_id) DO UPDATE SET
                status=excluded.status, note=excluded.note, updated_at=excluded.updated_at""",
                (site["id"], finding_id, status, note, utc_now().isoformat()),
            )
