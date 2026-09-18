"""Validated request bodies used by the local demonstration API."""

from pydantic import BaseModel, Field


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
