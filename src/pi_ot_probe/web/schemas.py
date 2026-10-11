"""Validated request bodies used by the local demonstration API."""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Literal
from pi_ot_probe.domain.models import utc_now


class AuthorizedRequest(BaseModel):
    """Base request for an action that transmits network traffic."""

    authorized: bool


class DiscoveryRequest(AuthorizedRequest):
    target: str


class ServiceVerificationRequest(AuthorizedRequest):
    host: str


class WifiInventoryRequest(AuthorizedRequest):
    pass


class WebsiteInspectionRequest(AuthorizedRequest):
    host: str
    port: int = Field(ge=1, le=65535)
    scheme: str


class BaselineRequest(BaseModel):
    name: str = Field(default="Site baseline", min_length=1, max_length=100)


class ChangeReviewRequest(BaseModel):
    status: str
    note: str = Field(default="", max_length=2000)


class InstrumentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    model: str = Field(default="ESP32; exact board unverified", min_length=1, max_length=120)
    firmware: str = Field(default="BWifiKill; version unverified", min_length=1, max_length=120)
    notes: str = Field(default="", max_length=2000)


class FieldObservationRequest(BaseModel):
    site: str = Field(min_length=1, max_length=100)
    instrument_id: int = Field(ge=1)
    category: Literal["wifi", "bluetooth", "rf", "network", "detection_validation", "other"]
    title: str = Field(min_length=1, max_length=160)
    subject: str = Field(min_length=1, max_length=200)
    location: str = Field(default="", max_length=200)
    evidence: str = Field(min_length=1, max_length=4000)
    recommendation: str = Field(default="", max_length=2000)
    observed_at: datetime = Field(default_factory=utc_now)


class AssessmentReviewRequest(BaseModel):
    site: str = Field(min_length=1, max_length=100)
    status: Literal["new", "investigating", "reviewed", "accepted_risk", "remediated"]
    note: str = Field(default="", max_length=2000)
