"""Policy values for each scanning profile."""

from dataclasses import dataclass

from pi_ot_probe.core.models import ScanLevel, ScanProfile


@dataclass(frozen=True, slots=True)
class ProfilePolicy:
    profile: ScanProfile
    default_level: ScanLevel
    packets_per_second: int
    connection_timeout_seconds: float
    verification_confirmation: bool
    active_confirmation_count: int


PROFILES: dict[ScanProfile, ProfilePolicy] = {
    ScanProfile.OFFICE: ProfilePolicy(ScanProfile.OFFICE, ScanLevel.DISCOVERY, 20, 2.0, True, 1),
    ScanProfile.INDUSTRIAL: ProfilePolicy(ScanProfile.INDUSTRIAL, ScanLevel.PASSIVE, 2, 5.0, True, 2),
    ScanProfile.CUSTOM: ProfilePolicy(ScanProfile.CUSTOM, ScanLevel.PASSIVE, 5, 3.0, True, 2),
}
