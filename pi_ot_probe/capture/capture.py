"""Capture limits shared by a future libpcap/tcpdump adapter."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CaptureLimits:
    maximum_duration_seconds: int = 300
    maximum_file_bytes: int = 50 * 1024 * 1024
    rotation_files: int = 2

